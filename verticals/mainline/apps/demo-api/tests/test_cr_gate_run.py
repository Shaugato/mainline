# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
"""``POST /v1/demo/cr-gate-run`` against the DEPLOYED seed, and what it may not claim.

Everything here runs against ``tests/conftest.py``'s ``demo_database`` — the database built
by applying ``db/seeds/demo/{demo_world,demo_permit}.sql`` through
``scripts/deploy/seed_demo.py``'s own applier. Not a parallel world: the change request
these tests drive is the row a judge's browser reaches, and its identifier is read back out
of the database by the fixture rather than typed here. A test that cannot disagree with the
code it tests proves nothing, and a fixture that mints its own subject cannot disagree with
a seed it has never met.

THE RUN IS SAFE TO SHARE WITH EVERY OTHER MODULE IN THIS DIRECTORY, and that is a property
of the thing under test rather than an arrangement made here: it persists nothing. The
assertions below check that claim from the outside as well as from the payload — an
independent connection reads the ``change_request`` row, its ``cr_event`` count and its
``merge_record`` count before and after and requires them byte-identical.

WHAT THIS FILE IS MOST CAREFUL ABOUT
------------------------------------
Three claims a reader would be right to distrust, each asserted here rather than asserted
in prose somewhere:

* **The CHECK and the trigger are different objects.** ``cr_gate_closed_when_merged`` is a
  ``CHECK`` in ``pg_catalog.pg_constraint``; ``mainline.fn_cr_merge_gate`` is a function
  and is in no catalog of constraints. Beat 2 names the first and beat 3 names the second,
  and a run that put the trigger's name on the CHECK's beat would be making a claim the
  kernel does not make. ``test_the_check_and_the_trigger_are_not_the_same_object`` fails on
  that.
* **The dropped beat was dropped for a real reason.** The kernel procedure is not played
  because ``mainline_api`` cannot reach the gate through it. The two facts that make that
  true are checked against the database and against ``db/GRANTS.yaml`` — the transition
  ``checks_materialised → merged`` is not a row in ``mainline.subject_transition``, and the
  grant line the payload CITES really does give ``mainline.cr_event`` ``SELECT`` and not
  ``INSERT``.
* **The persistence check can fail.** ``test_a_run_whose_fences_fail_is_caught`` removes
  both fences and requires the check to say so. A verifier that has never failed has never
  discriminated.
"""

from __future__ import annotations

import json
import re
import shutil
import uuid
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import psycopg
import pytest
from mainline_demo_api import cr_gate_run as cr_module
from mainline_demo_api import gate_run as gate_run_module
from mainline_demo_api.cr_gate_run import (
    CR_CF01_EXHIBIT,
    CR_CF01_SQLSTATE,
    CR_CF03_EXHIBIT,
    CR_CF03_SQLSTATE,
    CR_GATE_RUN_SCHEMA_ID,
    KERNEL_PROCEDURE_ABSENT_SQLSTATE,
    cr_gate_run,
)
from mainline_demo_api.scenario import ScenarioNotSeeded, from_env, resolve_cr_id
from mainline_demo_api.transitions import TRANSITION_RESOURCES, handle_transition
from psycopg.types.json import Jsonb

from conftest import CONTRACTS_DIR, REPO_ROOT, SchemaRegistry

pytestmark = pytest.mark.requires_cluster

_HERE = Path(__file__).resolve().parent
_CONTRACT = _HERE.parent / "contracts" / "cr-gate-run.schema.json"
GRANTS_YAML = REPO_ROOT / "verticals/mainline/db/GRANTS.yaml"


# ═══════════════════════════════════════════════════════════════════════════════════════
# fixtures
# ═══════════════════════════════════════════════════════════════════════════════════════


@pytest.fixture
def cr_conn(demo_dsn: str) -> Iterator[psycopg.Connection[Any]]:
    """A connection to the seeded database with ``autocommit`` OFF.

    Not the conftest's ``conn``: that one is ``db.connection()``, which ``db._open`` opens
    in autocommit, and ``cr_gate_run`` refuses such a connection outright — the three beats
    sharing one transaction is the property the endpoint exists to show. The autocommit
    path is exercised through ``handle_transition`` further down, which is where the
    borrow-and-give-back actually lives.
    """
    with psycopg.connect(demo_dsn, autocommit=False) as connection:
        yield connection


@pytest.fixture(scope="module")
def run_once(demo_database: tuple[str, dict[str, str]]) -> dict[str, Any]:
    """ONE run, shared by every assertion about its payload.

    Module-scoped because the run costs a round trip per beat and asserts nothing about
    repetition; the two tests that ARE about repetition open their own connections. Sharing
    it is safe for exactly the reason the endpoint exists to demonstrate — it persists
    nothing — and ``test_the_subject_is_byte_identical_after_the_call`` proves that
    independently rather than assuming it here.
    """
    dsn = demo_database[0]
    with psycopg.connect(dsn, autocommit=False) as connection:
        return cr_gate_run(connection, run_id="w3-cr-selftest")


@pytest.fixture(scope="module")
def contract() -> dict[str, Any]:
    return json.loads(_CONTRACT.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def cr_registry(tmp_path_factory: pytest.TempPathFactory) -> SchemaRegistry:
    """The console's own contract documents PLUS this app's new one, in one registry.

    The demo API owns ``contracts/cr-gate-run.schema.json``; ``console/contracts/`` gets a
    byte-for-byte copy, and until that copy lands the envelope this payload travels in
    cannot be resolved from the console tree alone. Rather than skip — a skip is
    indistinguishable from a deleted test — the two directories are combined here, so this
    validates the ORIGINAL against the very ``envelope.schema.json``, ``common.schema.json``
    and ``refusal.schema.json`` the console's own validator loads.
    """
    if not CONTRACTS_DIR.is_dir():
        pytest.skip(
            f"the console's contracts are not present at {CONTRACTS_DIR}, so the envelope "
            "this payload travels in cannot be resolved"
        )
    staged = tmp_path_factory.mktemp("cr-contracts")
    for document in sorted(CONTRACTS_DIR.glob("*.schema.json")):
        shutil.copyfile(document, staged / document.name)
    shutil.copyfile(_CONTRACT, staged / _CONTRACT.name)
    return SchemaRegistry(staged)


def _subject_state(conn: psycopg.Connection[Any], cr_id: str) -> tuple[Any, ...]:
    """The subject row and its two owned counts, read by POSITION, in one statement."""
    row = conn.execute(
        "SELECT cr.state::STRING, cr.head_seq, cr.gate_epoch, cr.open_blocking, "
        "       cr.open_conflicts, cr.open_residue, encode(cr.merged_commit, 'hex'), "
        "       (SELECT count(*) FROM mainline.cr_event e WHERE e.cr_id = cr.cr_id), "
        "       (SELECT count(*) FROM mainline.merge_record m WHERE m.cr_id = cr.cr_id) "
        "  FROM mainline.change_request cr WHERE cr.cr_id = %s",
        (cr_id,),
    ).fetchone()
    conn.rollback()
    assert row is not None, f"no mainline.change_request with cr_id {cr_id}"
    return tuple(row)


# ═══════════════════════════════════════════════════════════════════════════════════════
# the verdict, and the three beats the kernel actually answered
# ═══════════════════════════════════════════════════════════════════════════════════════


def test_the_run_is_proven_and_persists_nothing(run_once: dict[str, Any]) -> None:
    assert run_once["verdict"] == "PROVEN", run_once["failures"]
    assert run_once["failures"] == []
    assert run_once["outcome"] == "completed"
    assert run_once["persisted"] is False
    assert run_once["schema_id"] == CR_GATE_RUN_SCHEMA_ID
    assert run_once["run_id"] == "w3-cr-selftest"


def test_the_three_beats_are_the_ones_the_kernel_answered(run_once: dict[str, Any]) -> None:
    """Names, order, SQLSTATEs, exhibits — and how each exhibit was obtained.

    ``constraint_source`` is asserted in both directions because the two beats obtain their
    name by different channels and the difference is a claim about evidence quality: beat 2
    is ``reported`` — the driver's own ``diag.constraint_name`` — and beat 3 is ``parsed``,
    recovered from the kernel's ``refused by <schema>.<object>`` clause, which
    ``spec/errors.md`` §2.5 calls the weaker diagnosis and the console renders as such.
    """
    beats = run_once["beats"]
    assert [b["name"] for b in beats] == ["read", "merge", "projection_drift_attack"]
    assert [b["ordinal"] for b in beats] == [1, 2, 3]
    assert all(b["matched_expectation"] for b in beats), [
        (b["name"], b["outcome"], b["sqlstate"], b["constraint"]) for b in beats
    ]

    assert beats[0]["outcome"] == "read"
    assert beats[0]["sqlstate"] == "00000"
    assert beats[0]["refusal"] is None

    assert beats[1]["outcome"] == "refused"
    assert beats[1]["sqlstate"] == CR_CF01_SQLSTATE == "23514"
    assert beats[1]["constraint"] == CR_CF01_EXHIBIT == "cr_gate_closed_when_merged"
    assert beats[1]["constraint_source"] == "reported"
    assert beats[1]["refusal"]["subject_kind"] == "change_request"

    assert beats[2]["outcome"] == "refused"
    assert beats[2]["sqlstate"] == CR_CF03_SQLSTATE == "P0001"
    assert beats[2]["constraint"] == CR_CF03_EXHIBIT == "mainline.fn_cr_merge_gate"
    assert beats[2]["constraint_source"] == "parsed"
    # The message is the DATABASE's, and it is what makes the attack legible: it names the
    # re-derived count against the counter this run forged. Asserted as a property of the
    # sentence rather than as the whole sentence, which the kernel owns and may reword.
    assert "re-derived open obligation count" in beats[2]["message"]
    assert "projected counter reads zero" in beats[2]["message"]


def test_the_attack_beat_really_did_forge_the_counter(run_once: dict[str, Any]) -> None:
    """The premise of beat 3, asserted rather than assumed.

    Without this a run in which the ``UPDATE`` silently matched nothing would still show
    ``P0001`` — from a different arm of the same function — and would pass every other
    assertion in this file while demonstrating nothing about projection drift.
    """
    observed = run_once["beats"][2]["observed"]
    assert observed["counter_forced_to"] == 0
    assert observed["open_blocking_derived"] >= 1
    # The first fence, observed inside the transaction: the savepoint put it back.
    assert observed["counter_after_savepoint_rollback"] == observed["open_blocking_derived"]


def test_the_check_and_the_trigger_are_not_the_same_object(
    run_once: dict[str, Any], cr_conn: psycopg.Connection[Any]
) -> None:
    """``cr_gate_closed_when_merged`` is a CHECK; ``mainline.fn_cr_merge_gate`` is not.

    They are both real, they are different objects, and a beat that put one name where the
    other belongs would be a claim the kernel does not make. The catalog decides, here.
    """
    declared = {
        str(row[0])
        for row in cr_conn.execute(
            "SELECT con.conname FROM pg_catalog.pg_constraint con "
            "JOIN pg_catalog.pg_class rel ON rel.oid = con.conrelid "
            "JOIN pg_catalog.pg_namespace nsp ON nsp.oid = rel.relnamespace "
            "WHERE nsp.nspname = 'mainline' AND rel.relname = 'change_request' "
            "  AND con.contype = 'c'"
        ).fetchall()
    }
    cr_conn.rollback()
    assert CR_CF01_EXHIBIT in declared
    assert CR_CF03_EXHIBIT not in declared, (
        "mainline.fn_cr_merge_gate is a trigger FUNCTION, not a constraint. If the catalog "
        "now declares a constraint by that name the two exhibits have collided and beat 3 "
        "can no longer be told from beat 2 by its name alone."
    )
    assert run_once["beats"][1]["constraint"] in declared
    assert run_once["beats"][2]["constraint"] not in declared


def test_the_named_checks_come_from_the_catalog(run_once: dict[str, Any]) -> None:
    """All four gate CHECKs on the subject, with the predicates the catalog reports."""
    named = run_once["beats"][0]["observed"]["named_checks"]
    by_name = {entry["constraint"]: entry["predicate"] for entry in named}
    assert set(by_name) == {
        "cr_gate_closed_when_merged",
        "cr_merge_evidence",
        "cr_conflicts_resolved_when_merged",
        "cr_identity_conserved_when_merged",
    }, sorted(by_name)
    for predicate in by_name.values():
        assert "'merged'" in predicate
    assert "open_blocking" in by_name["cr_gate_closed_when_merged"]


def test_the_obligation_is_the_one_the_blame_projected(run_once: dict[str, Any]) -> None:
    """Severity 4, ``blood_major``, ``blame_ancestry`` — and nobody typed any of the three.

    ``demo_world.sql`` §10 supplies ``0 / 'routine' / 0`` and says so in the file; every
    value here was written over it by ``fn_check_project`` from ``clause_blame_current``.
    Asserting the projected values is therefore asserting that the projection ran.
    """
    observed = run_once["beats"][0]["observed"]
    assert observed["severity"] == 4
    assert observed["virulence"] == "blood_major"
    assert observed["origin"] == "blame_ancestry"
    assert observed["counters_agree"] is True
    assert observed["open_blocking_projected"] == observed["open_blocking_derived"] >= 1
    # Three options, about the EDIT rather than about the job — see demo_world.sql §10 on
    # why reusing the permit's codes would be a code that reads plausibly and means nothing.
    assert observed["defeater_options"] == [
        "CONTROL_PRESERVED_BY_EDIT",
        "EDIT_OUTSIDE_BLAMED_ANCHOR",
        "PRECURSOR_ANSWERED_ELSEWHERE",
    ]


def test_the_subject_is_the_change_request_the_deployed_seed_carries(
    run_once: dict[str, Any], seed: dict[str, str]
) -> None:
    """Read back out of the seeded database by the fixture, never typed into this file."""
    subject = run_once["subject"]
    assert subject["subject_kind"] == "change_request"
    assert subject["subject_id"] == seed["cr_id"]
    assert subject["external_ref"] == seed["cr_external_ref"]
    assert subject["state"] == seed["cr_state"] == "checks_materialised"
    assert subject["target_ref"] == seed["cr_target_ref"]
    assert subject["merged_commit"] is None
    assert subject["open_blocking"] >= 1


def test_the_beats_shared_one_transaction(run_once: dict[str, Any]) -> None:
    """``cluster_logical_timestamp()`` is the witness, not a sentence this module writes."""
    transaction = run_once["transaction"]
    assert transaction["isolation"] == "SERIALIZABLE"
    assert transaction["disposition"] == "rolled_back"
    assert transaction["single_transaction"] is True
    assert transaction["opened_logical_timestamp"] == transaction["closed_logical_timestamp"]
    assert transaction["retry_sqlstate"] is None
    assert transaction["savepoints"] == ["cr_gate_run_beat_2", "cr_gate_run_beat_3"]
    # There is no `canonicalisation` here and its absence is load-bearing: this run never
    # calls the kernel procedure, so there is no client-side JCS and no ledger leaf to name.
    assert "canonicalisation" not in transaction


# ═══════════════════════════════════════════════════════════════════════════════════════
# persistence — proved from the payload AND from outside it
# ═══════════════════════════════════════════════════════════════════════════════════════


def test_the_ten_unscoped_counts_are_gate_runs_own_list(run_once: dict[str, Any]) -> None:
    """Not a copy of gate-run's ten. THE SAME OBJECTS, so they cannot drift apart.

    ``docs/leads/cloud-hardening-final.md`` R2 forbids narrowing that reading. A
    transcription would satisfy the rule on the day it was written and fail silently the
    first time a table joined one list and not the other, which is the *"a second copy of a
    list is a second thing to drift"* defect this repository keeps rediscovering.
    """
    assert cr_module._FINGERPRINT_TABLES is gate_run_module._FINGERPRINT_TABLES
    assert cr_module._FINGERPRINT_SQL is gate_run_module._FINGERPRINT_SQL
    assert len(gate_run_module._FINGERPRINT_TABLES) == 10
    check = run_once["persistence_check"]
    assert check["tables"] == list(gate_run_module._FINGERPRINT_TABLES)
    assert set(check["before"]["row_counts"]) == set(gate_run_module._FINGERPRINT_TABLES)
    # The two the CR path touches are NOT among the ten and were added BESIDE them.
    assert "mainline.change_request" not in check["tables"]
    assert "mainline.cr_event" not in check["tables"]
    assert check["subject_tables"] == ["mainline.cr_event", "mainline.merge_record"]


def test_the_payload_proves_persisted_false_rather_than_asserting_it(
    run_once: dict[str, Any],
) -> None:
    check = run_once["persistence_check"]
    assert check["self_persisted"] is False
    assert check["identical"] is True, check["concurrent_writes"]
    assert check["concurrent_writes"] is None
    assert check["before"] == check["after"]

    evidence = check["self_evidence"]
    assert evidence["witness_written"] is True
    assert evidence["counter_forced_to"] == 0
    assert evidence["counter_before"] == evidence["counter_after_rollback"] >= 1
    assert evidence["counter_after_savepoint_rollback"] == evidence["counter_before"]
    assert evidence["change_request_row_identical"] is True
    assert evidence["subject_row_counts_before"] == evidence["subject_row_counts_after"]
    assert set(evidence["subject_row_counts_before"]) == {
        "mainline.cr_event",
        "mainline.merge_record",
    }
    # The subject has never merged, and the run did not change that.
    assert evidence["subject_row_counts_after"]["mainline.merge_record"] == 0


def test_the_subject_is_byte_identical_after_the_call(demo_dsn: str, seed: dict[str, str]) -> None:
    """The claim checked from OUTSIDE the payload, on a connection the run never touched.

    The payload's own fingerprint is evidence; a payload that graded its own homework would
    be evidence of nothing. This reads the row, its event count and its merge count through
    a separate connection either side of a real run.
    """
    with psycopg.connect(demo_dsn, autocommit=True) as observer:
        before = _subject_state(observer, seed["cr_id"])
        with psycopg.connect(demo_dsn, autocommit=False) as driver:
            payload = cr_gate_run(driver, run_id="w3-cr-outside")
        after = _subject_state(observer, seed["cr_id"])
    assert payload["verdict"] == "PROVEN", payload["failures"]
    assert before == after, f"the change request MOVED: {before} -> {after}"


def test_two_runs_in_a_row_answer_the_same_thing(demo_dsn: str) -> None:
    """Fifty judges pressing the button at once see the same three beats. Twice is enough.

    A run that consumed its subject would answer PROVEN once and something else afterwards,
    which is the failure mode the rollback exists to prevent and the one a single-run test
    cannot see.
    """
    payloads = []
    for attempt in range(2):
        with psycopg.connect(demo_dsn, autocommit=False) as driver:
            payloads.append(cr_gate_run(driver, run_id=f"w3-cr-repeat-{attempt}"))
    for payload in payloads:
        assert payload["verdict"] == "PROVEN", payload["failures"]
    assert [b["sqlstate"] for b in payloads[0]["beats"]] == [
        b["sqlstate"] for b in payloads[1]["beats"]
    ]
    assert payloads[0]["subject"] == payloads[1]["subject"]


class _FencesFail:
    """A connection whose two rollbacks stop undoing the attack beat's forged counter.

    THE PLANT IS SHAPED BY WHAT ACTUALLY GUARDS THE RUN, not by what looks plausible. The
    forged counter is undone TWICE — by beat 3's own ``ROLLBACK TO SAVEPOINT`` and by the
    transaction's ``ROLLBACK`` — so defeating either one alone leaves the other in place
    and the persistence check would still report ``self_persisted: false``, correctly. Both
    have to go for the check to have anything to see, and that is exactly the condition it
    exists to catch.

    Beat 3's savepoint rollback cannot simply be swallowed: the statement inside it RAISED,
    so a transaction that never rolls back to the savepoint is aborted and every read after
    it is ``25P02``. The write is therefore RE-APPLIED after the fence instead, outside any
    savepoint — the same end state as a fence that failed, reached by a route CockroachDB
    permits. Then the transaction-level rollback that closes the beats is swallowed, so the
    ``after`` reading sees what the run wrote.

    **NOTHING REACHES THE DATABASE.** No ``commit()`` is issued anywhere in this class, and
    the LAST rollback — the one after the ``after`` reading — is passed straight through, so
    the forged counter is discarded before the connection is even closed. The test asserts
    that too, from a third connection, because a control that damaged the shared seeded
    subject would be a worse defect than the one it is checking for.
    """

    def __init__(self, inner: psycopg.Connection[Any], cr_id: str) -> None:
        self._inner = inner
        self._cr_id = cr_id
        self.reapplied = 0
        self.rollbacks = 0

    def execute(self, query: Any, params: Any = None, **kwargs: Any) -> Any:
        if isinstance(query, str) and query == "RELEASE SAVEPOINT cr_gate_run_beat_3":
            self.reapplied += 1
            self._inner.execute(
                "UPDATE mainline.change_request SET open_blocking = 0 WHERE cr_id = %s",
                (self._cr_id,),
            )
        return self._inner.execute(query, params, **kwargs)

    def rollback(self) -> None:
        # `cr_gate_run` rolls back four times: a clean slate, after the opening reads, in
        # the `finally` that closes the beats, and after the `after` reading. The third is
        # the one whose whole job is to undo the run, and it is the one removed here.
        self.rollbacks += 1
        if self.rollbacks != 3:
            self._inner.rollback()

    def __getattr__(self, name: str) -> Any:
        return getattr(self._inner, name)


def test_a_run_whose_fences_fail_is_caught(demo_dsn: str, seed: dict[str, str]) -> None:
    """R8's control: a verifier that has never failed has never discriminated."""
    with psycopg.connect(demo_dsn, autocommit=True) as observer:
        before = _subject_state(observer, seed["cr_id"])

        connection = psycopg.connect(demo_dsn, autocommit=False)
        plant = _FencesFail(connection, seed["cr_id"])
        try:
            payload = cr_gate_run(plant, run_id="w3-cr-control")  # type: ignore[arg-type]
        finally:
            connection.close()

        assert plant.reapplied == 1, (
            "beat 3's savepoint was never released, so the plant re-applied nothing and "
            "this control ran against a transaction that was always going to be clean"
        )
        check = payload["persistence_check"]
        assert check["self_persisted"] is True, check["self_evidence"]
        assert check["self_evidence"]["counter_after_rollback"] == 0
        assert check["self_evidence"]["change_request_row_identical"] is False
        assert payload["verdict"] == "NOT PROVEN"
        assert any("PERSISTED something" in line for line in payload["failures"]), payload[
            "failures"
        ]

        after = _subject_state(observer, seed["cr_id"])
    assert before == after, (
        "THE CONTROL ITSELF PERSISTED SOMETHING. It issues no commit and the last rollback "
        f"is passed through, so this is a defect in the control: {before} -> {after}"
    )


# ═══════════════════════════════════════════════════════════════════════════════════════
# the two absences, and the evidence they cite
# ═══════════════════════════════════════════════════════════════════════════════════════


def _grant_line(number: int) -> str:
    """One line of ``db/GRANTS.yaml``, 1-indexed as the payload cites it."""
    lines = GRANTS_YAML.read_text(encoding="utf-8").splitlines()
    assert 1 <= number <= len(lines), f"GRANTS.yaml has {len(lines)} lines; {number} cited"
    return lines[number - 1]


def _cited_lines(citations: list[str]) -> list[int]:
    return [
        int(match)
        for citation in citations
        for match in re.findall(r"GRANTS\.yaml:(\d+)", citation)
    ]


def test_the_admission_beat_is_declared_absent_and_its_citations_are_true(
    run_once: dict[str, Any],
) -> None:
    """``admission_beat: null``, in words, with two grant rows a reader can check.

    The citations are not taken on trust. ``db/GRANTS.yaml`` is opened and the cited lines
    are required to say what the payload says they say — that ``mainline_api`` holds SELECT
    and not INSERT on the two relations an exposure receipt would have to be minted in. A
    citation nobody checked is how a payload comes to describe a matrix that has moved.
    """
    assert run_once["admission_beat"] is None
    assert run_once["admission_proved_by"] == "POST /v1/demo/gate-run"
    assert len(run_once["beats"]) == 3, "an admission beat must never be invented"
    assert all(beat["outcome"] != "skipped" for beat in run_once["beats"]), (
        "a beat marked 'skipped' standing in for the admission is the exact fabrication "
        "this payload's declared absence exists to replace"
    )

    reason = run_once["admission_absent_reason"]
    for phrase in ("exposure_receipt", "exposure_line", "(check_id, receipt_id)"):
        assert phrase in reason, phrase

    numbers = _cited_lines(run_once["admission_absent_grants"])
    assert len(numbers) == 2, run_once["admission_absent_grants"]
    for number, relation in zip(numbers, ("exposure_receipt", "exposure_line"), strict=True):
        line = _grant_line(number)
        assert "mainline_api" in line, (number, line)
        assert relation in line, (number, line)
        assert "[SELECT]" in line, (number, line)
        assert "INSERT" not in line, (number, line)


def test_the_kernel_procedure_beat_is_declared_absent_with_the_measured_sqlstate(
    run_once: dict[str, Any],
) -> None:
    """The dropped beat, and the two facts that dropped it — both checked, not recited."""
    assert run_once["kernel_procedure_beat"] is None
    assert run_once["kernel_procedure_absent_sqlstate"] == KERNEL_PROCEDURE_ABSENT_SQLSTATE
    assert run_once["kernel_procedure_absent_sqlstate"] == "42501"
    reason = run_once["kernel_procedure_absent_reason"]
    assert "mainline.cr_event" in reason
    assert "42501" in reason and "23503" in reason

    numbers = _cited_lines(run_once["kernel_procedure_absent_grants"])
    assert len(numbers) == 1, run_once["kernel_procedure_absent_grants"]
    line = _grant_line(numbers[0])
    assert "mainline_api" in line and "mainline.cr_event" in line
    assert "[SELECT]" in line and "INSERT" not in line, (
        "the payload says mainline_api holds SELECT and not INSERT on mainline.cr_event, "
        f"and the line it cites says {line!r}. If INSERT has been granted, the beat this "
        "run drops is playable again — and that is a decision with an owner, not a "
        "docstring to update."
    )


def test_the_illegal_edge_is_absent_from_the_transition_lattice(
    cr_conn: psycopg.Connection[Any],
) -> None:
    """The OTHER half of why the procedure cannot be played: the edge is not representable.

    ``checks_materialised → merged`` is not a row in ``mainline.subject_transition``, so
    ``mainline.merge_change_request``'s event append is refused by a FOREIGN KEY rather than
    by a rule some later commit could delete. Read from the table, not from a comment.
    """
    rows = cr_conn.execute(
        "SELECT from_state::STRING, to_state::STRING FROM mainline.subject_transition "
        "WHERE subject_kind = 'change_request' ORDER BY 1, 2"
    ).fetchall()
    cr_conn.rollback()
    edges = {(str(a), str(b)) for a, b in rows}
    assert edges, "mainline.subject_transition declares no change_request edges at all"
    assert ("checks_materialised", "merged") not in edges
    assert ("dispositioned", "merged") in edges


def test_the_procedure_really_is_refused_from_this_state(
    cr_conn: psycopg.Connection[Any], seed: dict[str, str]
) -> None:
    """The dropped beat, actually attempted once — so its absence rests on a measurement.

    Run as whatever login this suite holds, which is not ``mainline_api``: here the refusal
    is ``23503 cr_legal_edge``, the foreign key onto the transition lattice. As
    ``mainline_api`` the same call answers ``42501`` on ``mainline.cr_event`` instead,
    because the privilege is checked while planning and the procedure never gets as far as
    the key. EITHER way it does not reach the gate, which is the whole reason the beat is
    not played; this asserts the half that is reachable from a test, and
    ``test_the_kernel_procedure_beat_is_declared_absent_with_the_measured_sqlstate`` above
    asserts the grant that produces the other half.

    Rolled back to a savepoint and then rolled back again, so the attempt writes nothing.
    """
    payload = {"change_request": seed["cr_id"], "source": "w3 self-test"}
    canon = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    cr_conn.execute("SAVEPOINT probe")
    with pytest.raises(psycopg.Error) as raised:
        cr_conn.execute(
            "CALL mainline.merge_change_request(%s, %s, %s, %s, %s, %s, %s, %s)",
            (
                seed["cr_id"],
                b"\x00" * 32,
                "demo.signer",
                "human",
                Jsonb(payload),
                canon,
                1,
                b"\x11" * 32,
            ),
        )
    cr_conn.execute("ROLLBACK TO SAVEPOINT probe")
    cr_conn.rollback()
    assert raised.value.sqlstate in ("23503", "42501"), raised.value.sqlstate
    if raised.value.sqlstate == "23503":
        assert raised.value.diag.constraint_name == "cr_legal_edge"


# ═══════════════════════════════════════════════════════════════════════════════════════
# the contract
# ═══════════════════════════════════════════════════════════════════════════════════════


def test_the_payload_satisfies_the_governing_contract_structurally(
    run_once: dict[str, Any], contract: dict[str, Any]
) -> None:
    """Required members, closed enums, and the invariants the contract declares."""
    definition = contract["$defs"]["cr_gate_run"]
    for key in definition["required"]:
        assert key in run_once, f"payload is missing required member {key!r}"
    assert set(run_once) <= set(definition["properties"]), (
        f"payload carries members the contract forbids: "
        f"{sorted(set(run_once) - set(definition['properties']))}"
    )
    assert run_once["outcome"] in definition["properties"]["outcome"]["enum"]
    assert run_once["verdict"] in definition["properties"]["verdict"]["enum"]
    assert (run_once["failures"] == []) == (run_once["verdict"] == "PROVEN")
    assert definition["properties"]["schema_id"]["const"] == CR_GATE_RUN_SCHEMA_ID
    assert contract["$id"] == CR_GATE_RUN_SCHEMA_ID

    beat_props = contract["$defs"]["beat"]["properties"]
    outcomes = contract["$defs"]["beat_outcome"]["enum"]
    names = beat_props["name"]["enum"]
    assert contract["$defs"]["cr_gate_run"]["properties"]["beats"]["maxItems"] == 3
    assert len(run_once["beats"]) == 3
    for ordinal, beat in enumerate(run_once["beats"], start=1):
        assert beat["ordinal"] == ordinal
        assert beat["name"] == names[ordinal - 1]
        assert beat["outcome"] in outcomes
        assert set(beat) == set(beat_props), sorted(set(beat) ^ set(beat_props))
        assert (beat["outcome"] == "refused") == (beat["refusal"] is not None)


def test_the_payload_validates_against_the_console_validator(
    run_once: dict[str, Any], cr_registry: SchemaRegistry
) -> None:
    """The whole ENVELOPE, through the validator ``console/src/data/schema.ts`` mirrors.

    Not the ``data`` member alone: the contract's ``allOf`` puts ``envelope.schema.json``
    beside it, and a payload that satisfied one and not the other is a payload the console
    reports as a TAMPERED transport rather than rendering.
    """
    envelope = _envelope_around(run_once)
    errors = cr_registry.validate(CR_GATE_RUN_SCHEMA_ID, envelope)
    assert errors == [], "\n".join(errors)


def _envelope_around(data: dict[str, Any]) -> dict[str, Any]:
    """The envelope ``transitions._demo_cr_gate_run`` builds, minus the driving."""
    from mainline_demo_api.refusal import rfc3339

    now = rfc3339()
    return {
        "envelope_version": 1,
        "resource": "cr_gate_run",
        "schema_id": CR_GATE_RUN_SCHEMA_ID,
        "observed_at": now,
        "server_date": now,
        "staged": False,
        "staged_note": None,
        "statement_refs": [],
        "provenance": [],
        "data": data,
    }


# ═══════════════════════════════════════════════════════════════════════════════════════
# the route, and the shape that keeps the guard out of the picture
# ═══════════════════════════════════════════════════════════════════════════════════════


def test_the_resource_is_declared_with_no_path_parameter_and_no_mutation() -> None:
    """``(None, None, False)`` — and each of the three is load-bearing.

    ``_demo_guard`` decides on ``subject_id == scenario.permit_id``, and a change request
    identifier never equals a permit identifier: a MUTATING change-request transition would
    fall past ``demo_subject_write_protected``, find the permit IS seeded, and be let
    through. Registering this resource with a path parameter or with ``mutates = True``
    would therefore put an unguarded irreversible write on an unauthenticated endpoint, so
    the shape is asserted rather than left to a comment.
    """
    assert TRANSITION_RESOURCES["cr_gate_run"] == (None, None, False)
    assert TRANSITION_RESOURCES["cr_gate_run"] == TRANSITION_RESOURCES["demo_gate_run"]


def test_it_is_reachable_through_handle_transition(conn: psycopg.Connection[Any]) -> None:
    """The endpoint, over the connection ``db.py`` actually opens — autocommit and all."""
    status, envelope = handle_transition("cr_gate_run", {}, {"run_id": "w3-cr-http"}, conn)
    assert status == 200, envelope
    assert envelope["resource"] == "cr_gate_run"
    assert envelope["schema_id"] == CR_GATE_RUN_SCHEMA_ID
    assert envelope["staged"] is False
    data = envelope["data"]
    assert data["run_id"] == "w3-cr-http"
    assert data["verdict"] == "PROVEN", data["failures"]
    assert data["persisted"] is False
    # The connection is BORROWED, not owned. `db._open` opens it in autocommit and
    # `health.py` publishes that as the reason the health path cannot 503.
    assert conn.autocommit is True
    assert conn.info.transaction_status is psycopg.pq.TransactionStatus.IDLE


def test_the_statement_refs_name_the_table_and_never_the_procedure(
    conn: psycopg.Connection[Any],
) -> None:
    """What refuses is the TABLE and what is welded to it, and the refs say so.

    ``demo_gate_run``'s first statement ref is ``mainline.merge_permit`` because that run
    calls the procedure. This one must not name ``mainline.merge_change_request``: it never
    calls it, and a reference to a procedure the run did not issue would point a reader at
    the wrong exhibit entirely.
    """
    _status, envelope = handle_transition("cr_gate_run", {}, {}, conn)
    objects = [ref["object"] for ref in envelope["statement_refs"]]
    assert "mainline.change_request" in objects
    assert "trappoint.explain_refusal" in objects
    assert "mainline.merge_change_request" not in objects
    assert "mainline.merge_permit" not in objects


def test_a_non_string_run_id_is_422(conn: psycopg.Connection[Any]) -> None:
    status, payload = handle_transition("cr_gate_run", {}, {"run_id": 7}, conn)
    assert status == 422
    assert "run_id" in payload["detail"]
    assert "envelope_version" not in payload


def test_an_autocommit_connection_is_refused(conn: psycopg.Connection[Any]) -> None:
    """Three beats in one transaction, and a connection that cannot hold one is refused.

    Called directly rather than through ``handle_transition``, which borrows the flag: this
    is the guard that makes the borrow necessary rather than merely tidy.
    """
    assert conn.autocommit is True
    with pytest.raises(ValueError, match="NOT in autocommit"):
        cr_gate_run(conn)


# ═══════════════════════════════════════════════════════════════════════════════════════
# naming the subject — read, never derived, and never guessed
# ═══════════════════════════════════════════════════════════════════════════════════════


def test_the_identifier_is_read_out_of_the_database(
    cr_conn: psycopg.Connection[Any], seed: dict[str, str]
) -> None:
    """The sole change request, chosen by the database rather than by a constant here."""
    found = resolve_cr_id(cr_conn, from_env({}))
    cr_conn.rollback()
    assert str(found) == seed["cr_id"]


def test_the_environment_override_wins(
    cr_conn: psycopg.Connection[Any], seed: dict[str, str]
) -> None:
    other = uuid.uuid4()
    assert resolve_cr_id(cr_conn, from_env({"MAINLINE_DEMO_CR_ID": str(other)})) == other
    cr_conn.rollback()
    # And with nothing set, the read still finds the seeded row rather than a fallback.
    assert str(resolve_cr_id(cr_conn, from_env({}))) == seed["cr_id"]
    cr_conn.rollback()


def test_a_change_request_that_is_not_there_is_not_a_refusal(
    cr_conn: psycopg.Connection[Any],
) -> None:
    """'There was nothing to ask' and 'the gate did not refuse' are different findings."""
    absent = from_env({"MAINLINE_DEMO_CR_ID": str(uuid.uuid4())})
    with pytest.raises(ScenarioNotSeeded) as raised:
        cr_gate_run(cr_conn, absent)
    cr_conn.rollback()
    assert "MAINLINE_DEMO_CR_ID" in str(raised.value)
    assert "change_request" in str(raised.value)


def test_the_cr_commit_is_derived_and_never_written(
    run_once: dict[str, Any], seed: dict[str, str]
) -> None:
    """32 bytes from a uuid5 anyone can recompute, and the row it names stays NULL."""
    from mainline_demo_api.scenario import EXPECTED, demo_uuid

    assert str(demo_uuid("cr-commit")) == EXPECTED["cr-commit"]
    scenario = from_env({})
    assert len(scenario.cr_merged_commit) == 32  # CONSTRAINT cr_commit_sized
    assert scenario.cr_merged_commit == demo_uuid("cr-commit").bytes * 2
    assert scenario.cr_merged_commit != scenario.merged_commit
    assert run_once["subject"]["merged_commit"] is None
    assert run_once["persistence_check"]["after"]["change_request_row"]["merged_commit"] is None
    assert seed["cr_id"] == run_once["subject"]["subject_id"]
