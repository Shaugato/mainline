# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""The release lane's one irreducible assertion: the database refuses the merge.

This module runs ``scripts/proof/gate_refusal.py`` end to end against a cluster and
asserts, from the evidence the script emits, that:

* the migration chain applied **in full** and reached ``0115_fn_permit_merge_gate``;
* **no** migration failed, for any reason at all;
* the ``check_materialised`` weld projected the counter, bumped the epoch and emitted
  the CDC signal — read back from ``mainline_ops.outbox``, not assumed;
* a merge attempted with an open, undisposed obligation was **REFUSED**, with the exact
  SQLSTATE and the exact exhibit ``spec/conformance/manifest.toml`` fixes for CF-01;
* a merge attempted against a counter forced to zero was **REFUSED** by
  ``mainline.fn_permit_merge_gate`` (CF-03) — the case no CHECK can hold;
* the same merge was **ADMITTED** once a disposition was signed;
* the evidence carries **no caveats**.

The admission is not a formality. **A gate that always refuses is a broken gate**, and a
release test that asserted only the refusal would pass against a schema in which nothing
can ever merge.

WHAT CHANGED ON 2026-08-10, AND WHY THE REMOVAL IS THE POINT
------------------------------------------------------------
Until this wave, ``test_no_migration_failed_for_an_unexplained_reason`` tolerated any
migration failure attributable to one of five tables that had consumers and no producer
(``mainline_ops.outbox``, ``mainline.identity_assignment``, ``mainline.patrol_run``,
``mainline_meas.agent_action``, ``mainline_meas.standing``). Fifteen files failed on
every run and the lane was green.

The producer-completion wave authored those tables, plus two the census could not see —
``mainline_meas.person_measure_policy`` and ``mainline_ops.site_register_signal`` —
because CockroachDB names only the FIRST absent relation in a statement. So the
tolerance is **deleted**, not narrowed: ``UNPRODUCED_TABLES`` in the proof script is now
``()``, every residual failure lands in ``chain.failures_unexplained``, and this module
additionally asserts ``failed_count == 0`` and ``applied_count == files`` directly.
A test that forgives a known-bad set stops noticing when the set grows.

And a subtraction is not a deliverable, so the tolerance is replaced by an addition:
``test_the_trigger_did_the_projection`` and its siblings assert the sentence

    *the trigger projected the counter, emitted the CDC signal, bumped the epoch,
    and the gate refused*

clause by clause, against values read out of ``mainline.permit`` and
``mainline_ops.outbox`` after the fact.

PL-2 — RED BEFORE GREEN
-----------------------
Both generations of this test were observed RED before they were green, and both
transcripts are verbatim in ``docs/release/gate-refusal-proof.md``: the first against a
tree in which ``0049z`` declared a column called ``family``, the second against a tree
with ``0121_trg_check_materialised.sql`` removed, which takes the projection assertions
from 10/10 to 1/10 while every refusal still lands. A suite that has never been red
asserts nothing.

THE CLUSTER
-----------
No container is started here. The DSN comes from the environment, under any of the four
spellings the repository's fixtures already honour — ``MAINLINE_TEST_DSN``,
``TRAPPOINT_DSN``, ``COCKROACH_URL``, ``CRDB_URL`` — so this test joins whatever session
cluster the testkit has stood up rather than adding a fourteenth one. With none set, or
with none reachable, the test SKIPS: "there was no database" is not evidence that the
gate admitted anything, and reporting it as a failure would train a reader to ignore it.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
PROOF = REPO_ROOT / "scripts" / "proof" / "gate_refusal.py"

#: The seam recorded in `docs/leads/quality-repair.md` §1.4: every cluster fixture in the
#: repository checks these first, before reaching for Docker.
DSN_ENV_NAMES = ("MAINLINE_TEST_DSN", "TRAPPOINT_DSN", "COCKROACH_URL", "CRDB_URL", "LOCAL_DSN")

#: A database of its own, so this lane can never disturb another worker's cluster state.
PROOF_DATABASE = "release_gate_refusal_proof"

CF01_SQLSTATE, CF01_EXHIBIT = "23514", "gate_closed_when_issued"
CF03_SQLSTATE, CF03_EXHIBIT = "P0001", "mainline.fn_permit_merge_gate"

#: `0121_trg_check_materialised.sql` welds `mainline.fn_check_materialised` (0101) to
#: `mainline.blocking_check`. The counter source string is the proof's own vocabulary and
#: is asserted verbatim, because "who wrote this counter" is the whole question.
COUNTER_SOURCE_TRIGGER = "trigger check_materialised -> mainline.fn_check_materialised"
OUTBOX_KIND = "check_opened"

#: What the script writes into `blocking_check.severity`; `fn_check_project` (BEFORE
#: INSERT, 0120) overwrites it from `clause_blame_current`. A signal carrying this value
#: would mean the BEFORE trigger never ran.
CLIENT_SUPPLIED_SEVERITY = 0


def _dsn() -> str | None:
    for name in DSN_ENV_NAMES:
        value = os.environ.get(name)
        if value:
            return value
    return None


@pytest.fixture(scope="module")
def proof(tmp_path_factory: pytest.TempPathFactory) -> dict:
    """Run the proof once and hand every test the evidence it emitted."""
    dsn = _dsn()
    if dsn is None:
        pytest.skip(
            "no cluster DSN. Set one of " + ", ".join(DSN_ENV_NAMES) + " to run the release proof."
        )
    assert PROOF.is_file(), f"the proof script is missing: {PROOF}"

    out = tmp_path_factory.mktemp("gate-refusal") / "proof.json"
    completed = subprocess.run(
        [
            sys.executable,
            str(PROOF),
            "--dsn",
            dsn,
            "--database",
            PROOF_DATABASE,
            "--out",
            str(out),
        ],
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
        timeout=900,
        check=False,
    )
    if completed.returncode == 2:
        pytest.skip(
            "the proof could not reach a cluster (exit 2), which is not evidence about the "
            f"gate:\n{completed.stderr.strip()}"
        )
    assert out.is_file(), (
        "the proof wrote no evidence file. stdout:\n"
        f"{completed.stdout}\nstderr:\n{completed.stderr}"
    )
    evidence = json.loads(out.read_text(encoding="utf-8"))
    evidence["_stdout"] = completed.stdout
    evidence["_stderr"] = completed.stderr
    evidence["_returncode"] = completed.returncode
    return evidence


def test_the_chain_reached_the_merge_gate(proof: dict) -> None:
    chain = proof["chain"]
    assert chain["reached_0115_fn_permit_merge_gate"], (
        "the migration chain never reached 0115_fn_permit_merge_gate, so nothing below is a "
        "statement about the gate. Unexplained failures: "
        + json.dumps(chain["failures_unexplained"], indent=2)
    )


def test_no_table_is_left_without_a_producer(proof: dict) -> None:
    """The ratchet. ``UNPRODUCED_TABLES`` is empty and must stay empty.

    This is not a restatement of the next test — it asserts the *tolerance mechanism*
    itself is switched off. As long as this list is empty, ``_classify`` in the proof
    script cannot return ``unproduced_dependency`` for anything, so no migration failure
    can ever be forgiven. Re-populating the list to make a red run green would fail here
    first, which is exactly the review this assertion exists to force.
    """
    enumerated = proof["chain"]["unproduced_tables_enumerated"]
    assert enumerated == [], (
        "the proof is again tolerating migration failures attributable to tables with no "
        f"producer: {enumerated}. Seven producers were authored on 2026-08-10 precisely so "
        "this list could be emptied; re-populating it re-opens a hole in the release lane."
    )


def test_every_migration_applied(proof: dict) -> None:
    """No failure of any kind, and every file accounted for.

    ``failed_count == 0`` and ``applied_count == files`` are asserted together on purpose:
    the first would still pass if the discovery step silently found no files at all, and
    a proof that applied nothing is not a proof that everything applied.
    """
    chain = proof["chain"]
    assert chain["failures_unexplained"] == [], (
        f"{len(chain['failures_unexplained'])} migration(s) failed:\n"
        + json.dumps(chain["failures_unexplained"], indent=2)
    )
    assert chain["failed_count"] == 0, (
        f"{chain['failed_count']} migration(s) did not apply:\n"
        + json.dumps(chain["failures_unexplained"], indent=2)
    )
    assert chain["files"] > 0, "no migrations were discovered at all"
    assert chain["applied_count"] == chain["files"], (
        f"{chain['applied_count']} of {chain['files']} migrations applied. Forward-only means "
        "every file below the first gap is unexecuted by the runner a deployment uses."
    )


def test_every_gate_object_exists(proof: dict) -> None:
    absent = sorted(name for name, ok in proof["gate_objects"].items() if not ok)
    assert absent == [], f"gate objects absent from the applied schema: {absent}"


# ─────────────────────────────────────────────────────────────────────────────────────
# THE PROJECTION — the sentence this wave added, asserted clause by clause
# ─────────────────────────────────────────────────────────────────────────────────────


def test_the_trigger_did_the_projection(proof: dict) -> None:
    """Not "open_blocking was 1" — **the trigger made it 1, across one INSERT.**

    The proof reads ``mainline.permit`` immediately before and immediately after the
    single ``INSERT INTO mainline.blocking_check``, with no statement in between, so the
    delta is attributable to the weld and to nothing else.
    """
    projection = proof["projection"]
    assert projection.get("captured"), (
        f"the projection was never measured: {json.dumps(projection, indent=2)}"
    )
    assert projection["trigger"]["present"], (
        "the check_materialised trigger is absent, so open_blocking was written by the "
        "proof script. The refusals below are still the database's, but the projection is "
        "not proven and this lane may not be green."
    )
    assert proof["history"]["projection_trigger_check_materialised_present"] is True
    assert proof["history"]["open_blocking_counter_written_by"] == COUNTER_SOURCE_TRIGGER, (
        "counter_source does not name the trigger: "
        f"{proof['history']['open_blocking_counter_written_by']!r}"
    )
    assert projection["open_blocking"]["before"] == 0
    assert projection["open_blocking"]["after"] == 1


def test_the_trigger_bumped_the_gate_epoch(proof: dict) -> None:
    """MI07: the epoch bump is what makes attaching a precursor to an issued subject
    physically impossible, because the completion record's composite FK carries
    ``ON UPDATE RESTRICT``. **Strictly** increased — an epoch that stands still is a pin
    that does not pin.
    """
    epoch = proof["projection"]["gate_epoch"]
    assert epoch["before"] is not None and epoch["after"] is not None
    assert epoch["after"] > epoch["before"], (
        f"gate_epoch did not move across the INSERT: {epoch['before']} -> {epoch['after']}"
    )
    assert epoch["moved"] is True


def test_the_trigger_emitted_the_cdc_signal(proof: dict) -> None:
    """The addition that replaces the retired caveat.

    ``mainline_ops.outbox`` is the one CDC-query source in the deployment (§4.1 law 11).
    A row in it is the asynchronous half of the system starting; without it the counter
    could have moved and nothing downstream would ever have heard.
    """
    outbox = proof["projection"]["outbox"]
    assert outbox["relation_present"], "mainline_ops.outbox does not exist — 0099 did not apply"
    assert outbox["rows_for_this_check"] == 1, (
        f"expected exactly one emitted signal, saw {outbox['rows_for_this_check']}: "
        + json.dumps(outbox["all_rows_for_this_check"], indent=2)
    )
    row = outbox["row"]
    assert row is not None, "no outbox row was emitted for the seeded obligation"
    assert row["kind"] == OUTBOX_KIND, f"the signal's kind is {row['kind']!r}, not {OUTBOX_KIND!r}"
    assert row["subject_id"] == proof["history"]["blocking_check_id"], (
        "the signal names a different subject than the blocking check that raised it"
    )
    assert row["site_id"] == proof["history"]["site_id"], (
        "the signal does not carry the site denormalised; a CDC query permits no joins, so "
        "a consumer could not resolve it"
    )
    assert row["signal_id"], "the emitted signal has no signal_id"
    assert row["emitted_at"] and row["expires_at"], (
        "the signal carries no TTL window; mainline_ops.outbox is allowlist entry 1 of 3 for "
        "row-level TTL and its expiry must be visible in the row"
    )


def test_the_signal_carries_the_projected_severity_not_the_clients(proof: dict) -> None:
    """The sharpest clause, because it demonstrates the ORDER of two triggers.

    ``fn_check_project`` (BEFORE INSERT, 0120) overwrites the client's ``severity`` from
    ``clause_blame_current``; ``fn_check_materialised`` (AFTER INSERT, 0121) then copies
    ``(NEW).severity`` into the signal. The proof supplies ``0`` and the closure bands the
    ancestry at ``4``. A signal reading ``4`` proves both triggers ran, in that order.
    """
    projection = proof["projection"]
    emitted = projection["outbox"]["row"]["max_severity"]
    assert projection["severity"]["supplied_by_this_script"] == CLIENT_SUPPLIED_SEVERITY
    assert emitted != CLIENT_SUPPLIED_SEVERITY, (
        "the signal carries the severity the client supplied, which means fn_check_project "
        "never overwrote it"
    )
    assert emitted == projection["severity"]["projected_onto_the_check"], (
        f"the signal carries {emitted} but the obligation row carries "
        f"{projection['severity']['projected_onto_the_check']}"
    )
    assert projection["severity"]["virulence_projected"] == "blood_major"


def test_every_projection_assertion_held(proof: dict) -> None:
    """The whole sentence, in one line, so a regression names itself."""
    projection = proof["projection"]
    broken = [a for a in projection["assertions"] if not a["holds"]]
    assert broken == [], (
        f"{len(broken)} of {projection['assertions_total']} projection assertions failed:\n"
        + json.dumps(broken, indent=2)
    )
    assert projection["assertions_held"] == projection["assertions_total"]
    assert projection["assertions_total"] >= 10, (
        "the projection block has fewer assertions than it did when this lane was written; "
        "an assertion that is deleted rather than fixed is a claim quietly withdrawn"
    )


# ─────────────────────────────────────────────────────────────────────────────────────
# THE THREE BEATS
# ─────────────────────────────────────────────────────────────────────────────────────


def test_the_merge_is_refused_when_the_precursor_has_no_disposition(proof: dict) -> None:
    """CF-01. The product, in one assertion."""
    refusal = proof["refusal"]
    assert refusal["outcome"] == "REFUSED", (
        "THE MERGE WAS ADMITTED with an open, undisposed obligation. This is the claim the "
        f"whole repository is about: {json.dumps(refusal, indent=2)}"
    )
    assert refusal["sqlstate"] == CF01_SQLSTATE
    assert refusal["constraint"] == CF01_EXHIBIT, (
        "the refusal carried the wrong exhibit. A refusal whose constraint name is not the "
        "one the manifest fixes is the right outcome for the wrong reason, and the exhibit "
        "is the product here."
    )


def test_the_refusal_is_written_to_the_refusal_ledger(proof: dict) -> None:
    ledger = proof["refusal"].get("refusal_ledger", {})
    assert ledger.get("written"), f"the refusal was not recorded: {ledger}"
    assert ledger.get("read_back"), f"the refusal row could not be read back: {ledger}"
    assert ledger["sqlstate"] == CF01_SQLSTATE
    assert ledger["constraint_name"] == CF01_EXHIBIT
    assert ledger["mus_cardinality"] >= 1
    assert ledger["gate_epoch"] == proof["projection"]["gate_epoch"]["after"], (
        "the ledgered refusal names a different gate epoch than the one the trigger left on "
        "the permit — the refusal and the projection disagree about which epoch was refused"
    )


def test_a_forced_counter_is_refused_by_the_gate_function(proof: dict) -> None:
    """CF-03. The projection is enforced, never trusted (rule P-2)."""
    drift = proof["drift_refusal"]
    assert drift["outcome"] == "REFUSED", (
        "the merge was ADMITTED against a counter forced to zero out of band. The projection "
        f"was trusted rather than enforced: {json.dumps(drift, indent=2)}"
    )
    assert drift["sqlstate"] == CF03_SQLSTATE
    assert drift["constraint"] == CF03_EXHIBIT
    assert drift["constraint_source"] == "parsed", (
        "spec/errors.md §3.1: diag.constraint_name is empty for P0001, so the exhibit must be "
        "recorded as PARSED. A P0001 claiming a reported exhibit is over-stating its diagnosis."
    )


def test_the_merge_is_admitted_once_a_disposition_is_signed(proof: dict) -> None:
    """The other half. A gate that always refuses is a broken gate, not a safe one."""
    assert proof["disposition"]["signed"], (
        f"the disposition could not be signed: {json.dumps(proof['disposition'], indent=2)}"
    )
    admission = proof["admission"]
    assert admission["outcome"] == "ADMITTED", (
        "the merge was still REFUSED after a signed disposition. A gate that cannot be "
        f"satisfied has not been shown to be a gate: {json.dumps(admission, indent=2)}"
    )
    record = admission["merge_record"]
    assert record["present"], "the merge was admitted but wrote no merge_record"
    assert record["permit_state"] == "merged"
    assert record["permit_open_blocking"] == 0
    assert len(record["clearance_digest"]) == 64, "the clearance digest is not a SHA-256"


def test_the_evidence_carries_no_caveats(proof: dict) -> None:
    """The retired apology, asserted as retired.

    Until 2026-08-10 every run carried two caveats: fifteen migrations that did not apply,
    and a counter written by the script rather than by the trigger. Both are gone, and the
    field must be **present and empty** rather than absent — a reader has to be able to see
    that the list is empty, not merely fail to find it.
    """
    assert "caveats" in proof, "the evidence file no longer publishes a caveats field at all"
    assert proof["caveats"] == [], "the run carries caveats:\n" + json.dumps(
        proof["caveats"], indent=2
    )
    assert "caveats       (none)" in proof["_stdout"], (
        "the console summary does not state that the caveat list is empty. An absent line "
        "and an empty list read the same to a human, and they are not the same thing."
    )


def test_the_proof_exits_zero(proof: dict) -> None:
    """The exit code the `just prove` recipe and the release workflow branch on."""
    assert proof["_returncode"] == 0, (
        f"gate_refusal.py exited {proof['_returncode']} — verdict {proof.get('verdict')!r}, "
        f"failures {json.dumps(proof.get('failures', []), indent=2)}\n"
        f"stdout:\n{proof['_stdout']}"
    )
    assert proof["verdict"] == "PROVEN"
    assert proof["failures"] == []
