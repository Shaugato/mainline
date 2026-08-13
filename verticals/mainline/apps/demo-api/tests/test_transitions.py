# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
"""The four POST transitions, against a real migrated CockroachDB node.

Every refusal asserted here is the DATABASE's, produced by writing a row it will not
accept: a merge with an open obligation, and a state transition that is not in
``mainline.subject_transition``. Neither is provoked by a flag or a fixture that stands in
for one — the point of a gate whose rules are constraints is that you cannot ask it to
pretend, so these tests do not.

Each test that mutates gets its own seeded history, because the transitions are real and
irreversible: a permit is never un-merged, and ``dispositioned -> checks_materialised``
does not come back. Sharing one subject across them would make the suite order-dependent,
which is the failure mode that ends with someone deleting an assertion to make a run green.

``w4_database`` comes from ``test_gate_run`` for the reason stated there: this worker owns
two test files and not the conftest, and pytest's default ``prepend`` import mode puts the
tests directory on ``sys.path``. The ``w4_`` prefix keeps these clear of the fixtures
``w3-api-core-reads`` declares in ``tests/conftest.py`` under the names ``demo_database``
and ``conn``.

AND THE CONNECTION IS BORROWED, WHICH IS THE LAST SECTION OF THIS FILE
----------------------------------------------------------------------
Every test above takes ``w4_conn``, a connection this file opened with
``autocommit=False``. That is the right fixture for "what does the transition do", and it
is structurally incapable of seeing what the transitions did to the connection itself: the
flag they cleared was already clear, so clearing it again and never putting it back looked
like nothing at all. The Lambda's connection is the opposite — ``db._open`` opens it with
``autocommit=True``, module-scope, reused across invocations — and on that connection the
same code left the flag cleared, so the request AFTER any gate run or signature inherited a
session whose promise ``health.py`` publishes in prose had been silently withdrawn.

The last section therefore drives the transitions on ``db.connection()`` itself and asserts
what the caller gets back, not merely what the caller was told. Same lesson as the row
factory, in a third costume: a fixture that cannot disagree with the code proves nothing.
"""

from __future__ import annotations

import ast
import contextlib
import uuid
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import psycopg
import pytest
from mainline_demo_api import db as db_mod
from mainline_demo_api import transitions as transitions_mod
from mainline_demo_api.gate_run import GATE_RUN_SCHEMA_ID
from mainline_demo_api.health import health
from mainline_demo_api.transitions import (
    INVOKE_SCHEMA_ID,
    TRANSITION_RESOURCES,
    handle_transition,
)
from psycopg.types.json import Jsonb
from test_gate_run import w4_database  # noqa: F401 - re-exported so pytest can resolve it

pytestmark = pytest.mark.requires_cluster

#: `contracts/invoke.schema.json#/$defs/invoke_result` — required, and additionalProperties
#: false. Transcribed so a member added here without a contract change fails a test rather
#: than the console's validator, which would report it as a TAMPERED transport.
_INVOKE_REQUIRED = (
    "procedure",
    "http_status",
    "outcome",
    "subject_kind",
    "subject_id",
    "gate_epoch",
    "refusal",
)
_INVOKE_ALLOWED = {*_INVOKE_REQUIRED, "committed", "sql_round_trip"}

_ENVELOPE_REQUIRED = ("envelope_version", "resource", "schema_id", "staged", "provenance", "data")


def _sha(*parts: bytes | str) -> bytes:
    import hashlib

    digest = hashlib.sha256()
    for part in parts:
        digest.update(part.encode("utf-8") if isinstance(part, str) else part)
    return digest.digest()


#: The site the demo history was seeded into, and everything about it a second permit can
#: reuse. `mainline.site` declares `CONSTRAINT site_role_unique UNIQUE (site_role)` and the
#: repository's seeder hard-codes the role `proof_site`, so calling it twice against one
#: database is a 23505 — measured. A fresh SITE per test is therefore not available; a
#: fresh PERMIT inside the existing site is, and it is also the more faithful fixture,
#: because two permits at one site is what a real deployment looks like.
_SITE_SQL = """
SELECT s.site_id, s.site_role::STRING, pc.clause_uuid, pc.commit_id, bc.precursor_event_id,
       (SELECT policy_version FROM mainline_meas.recall_policy ORDER BY policy_version LIMIT 1)
  FROM mainline.permit p
  JOIN mainline.site s ON s.site_id = p.site_id
  JOIN mainline.permit_clause pc ON pc.permit_id = p.permit_id
  JOIN mainline.blocking_check bc ON bc.permit_id = p.permit_id
 WHERE p.permit_id = %s
 LIMIT 1
"""


class _History:
    """The identifiers one seeded permit minted. Same three fields the proof's History uses."""

    def __init__(self, permit_id: uuid.UUID, check_id: uuid.UUID, site_id: uuid.UUID) -> None:
        self.permit_id = permit_id
        self.check_id = check_id
        self.site_id = site_id


def _seed_permit(w4_conn: psycopg.Connection[Any], demo_permit_id: str, signer: str) -> _History:
    """Seed one more permit into the existing site, in the state the gate is decidable in.

    A permit that relies on the already-seeded clause version, a boundary certificate, a
    recall run with its Proof of Exhausted Recall, one blocking check standing for the
    recalled precursor, an exposure receipt that showed it, and the two events by which the
    client CLAIMS every obligation is disposed of. It is not — and that claim is exactly
    what the gate exists to disbelieve.

    Nothing here bypasses a trigger. The counter is written by ``check_materialised``, the
    chain digest by ``fn_permit_event_chain``, and the closure by whatever 0115 re-derives.
    """
    w4_conn.rollback()
    row = w4_conn.execute(_SITE_SQL, (demo_permit_id,)).fetchone()
    assert row is not None, "the demo history is not seeded in this database"
    site_id, site_role, clause_uuid, commit_id, event_id, policy_version = row

    permit_id, check_id = uuid.uuid4(), uuid.uuid4()
    run_id, silence_id, receipt_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    tag = permit_id.hex[:12]

    w4_conn.execute(
        "INSERT INTO mainline.permit (permit_id, site_id, site_role, external_ref, ref_name, "
        "horizon_at) VALUES (%s, %s, %s, %s, %s, now() + INTERVAL '30 days')",
        (permit_id, site_id, site_role, f"PTW-W4-{tag}", f"refs/permits/w4-{tag}"),
    )
    w4_conn.execute(
        "INSERT INTO mainline.permit_clause (permit_id, clause_uuid, commit_id, relation) "
        "VALUES (%s, %s, %s, 'relies_on')",
        (permit_id, clause_uuid, commit_id),
    )
    w4_conn.execute(
        "INSERT INTO mainline.boundary_certificate (permit_id, cert_gen, asset_graph_version, "
        "tags_declared, tags_resolved, tags_unmodelled, under_declared) "
        "VALUES (%s, 1, 'w4-asset-graph-1', 1, 1, 0, 0)",
        (permit_id,),
    )
    w4_conn.execute(
        "INSERT INTO mainline_meas.recall_run (run_id, permit_id, site_id, corpus_commit, "
        "policy_version, index_plan_digest, index_generation, n_candidates, n_blocking, "
        "n_advisory, n_silenced, n_deduped) VALUES (%s, %s, %s, %s, %s, %s, 'g1', 1, 1, 0, 0, 0)",
        (run_id, permit_id, site_id, commit_id, policy_version, _sha("plan", tag)),
    )
    w4_conn.execute(
        "INSERT INTO mainline_meas.silence_receipt (silence_receipt_id, run_id, permit_id, "
        "corpus_root, candidate_root, theta, s, n, boundary_proof, policy_version) "
        "VALUES (%s, %s, %s, %s, %s, 0.35, 1, 1, %s, %s)",
        (
            silence_id,
            run_id,
            permit_id,
            _sha("corpus-root"),
            _sha("candidate-root", tag),
            Jsonb({"leaf_s": [], "leaf_s_plus_1": []}),
            policy_version,
        ),
    )
    w4_conn.execute(
        "INSERT INTO mainline.blocking_check (check_id, subject_kind, permit_id, site_id, "
        "clause_uuid, commit_id, precursor_event_id, origin, severity, virulence, closure_gen, "
        "recall_run_id, evidence_summary) "
        "VALUES (%s, 'permit', %s, %s, %s, %s, %s, 'blame_ancestry', 0, 'routine', 0, %s, %s)",
        (
            check_id,
            permit_id,
            site_id,
            clause_uuid,
            commit_id,
            event_id,
            run_id,
            "A recalled precursor reaches the clause this permit relies on.",
        ),
    )
    w4_conn.execute(
        "INSERT INTO mainline.exposure_receipt (receipt_id, subject_kind, permit_id, actor_sub, "
        "issued_at, issued_hlc, expires_at, corpus_root, silence_receipt_id, policy_version, "
        "total_tokens, receipt_digest) "
        "VALUES (%s, 'permit', %s, %s, now() - INTERVAL '10 minutes', cluster_logical_timestamp(), "
        "now() + INTERVAL '2 hours', %s, %s, %s, 200, %s)",
        (
            receipt_id,
            permit_id,
            signer,
            _sha("corpus-root"),
            silence_id,
            policy_version,
            _sha("receipt", tag),
        ),
    )
    w4_conn.execute(
        "INSERT INTO mainline.exposure_line (receipt_id, check_id, payload_digest, tokens) "
        "VALUES (%s, %s, %s, 200)",
        (receipt_id, check_id, _sha("line", tag)),
    )
    for seq, (frm, to) in enumerate(
        (("draft", "checks_materialised"), ("checks_materialised", "dispositioned")), start=1
    ):
        w4_conn.execute(
            "INSERT INTO mainline.permit_event (permit_id, seq, prev_seq, from_state, to_state, "
            "subject_kind, actor_sub, payload, prev_digest) "
            "VALUES (%s, %s, %s, %s, %s, 'permit', %s, %s, "
            "coalesce((SELECT e.chain_digest FROM mainline.permit_event e "
            "           WHERE e.permit_id = %s AND e.seq = %s), decode(repeat('00', 32), 'hex')))",
            (permit_id, seq, seq - 1, frm, to, signer, Jsonb({"w4": to}), permit_id, seq - 1),
        )
        w4_conn.execute(
            "UPDATE mainline.permit SET state = %s, head_seq = %s WHERE permit_id = %s",
            (to, seq, permit_id),
        )
    w4_conn.commit()
    return _History(permit_id, check_id, site_id)


@pytest.fixture
def w4_conn(w4_database: str) -> Iterator[psycopg.Connection[Any]]:  # noqa: F811
    """A connection to the w4 scratch database. Named apart from the conftest's `conn`."""
    with psycopg.connect(w4_database, autocommit=False) as connection:
        yield connection


@pytest.fixture
def fresh_history(w4_database: str) -> Iterator[_History]:  # noqa: F811
    """A brand-new permit with one open obligation. Its own subject, so tests cannot collide."""
    import os

    with psycopg.connect(w4_database, autocommit=False) as connection:
        yield _seed_permit(
            connection,
            os.environ["MAINLINE_DEMO_PERMIT_ID"],
            os.environ["MAINLINE_DEMO_SIGNER_SUB"],
        )


@pytest.fixture
def bare_permit(w4_database: str) -> Iterator[uuid.UUID]:  # noqa: F811
    """A permit and nothing else — no recall run, no obligation, state 'draft'.

    The subject a precondition failure is about. Nothing here is fabricated to produce an
    error: this is simply a permit that has not been through recall yet, which is what
    every permit is on the day it is drafted.
    """
    import os

    with psycopg.connect(w4_database, autocommit=True) as connection:
        row = connection.execute(
            "SELECT p.site_id, s.site_role::STRING FROM mainline.permit p "
            "JOIN mainline.site s ON s.site_id = p.site_id WHERE p.permit_id = %s",
            (os.environ["MAINLINE_DEMO_PERMIT_ID"],),
        ).fetchone()
        site_id, site_role = row
        permit_id = uuid.uuid4()
        connection.execute(
            "INSERT INTO mainline.permit (permit_id, site_id, site_role, external_ref, ref_name, "
            "horizon_at) VALUES (%s, %s, %s, %s, %s, now() + INTERVAL '30 days')",
            (
                permit_id,
                site_id,
                site_role,
                f"PTW-BARE-{permit_id.hex[:8]}",
                f"refs/permits/bare-{permit_id.hex[:8]}",
            ),
        )
        yield permit_id


def _assert_envelope(payload: dict[str, Any], resource: str, schema_id: str) -> dict[str, Any]:
    """The response IS the envelope, not the bare `data`. See transitions.py's docstring."""
    for key in _ENVELOPE_REQUIRED:
        assert key in payload, f"envelope is missing {key!r}"
    assert payload["envelope_version"] == 1
    assert payload["resource"] == resource
    assert payload["schema_id"] == schema_id
    assert payload["staged"] is (payload["staged_note"] is not None)
    for chip in payload["provenance"]:
        assert set(chip) == {"pointer", "chip"}
        assert chip["pointer"].startswith("/")
    return payload["data"]


def _assert_invoke(data: dict[str, Any], procedure: str, outcome: str, status: int) -> None:
    assert set(data) <= _INVOKE_ALLOWED, sorted(set(data) - _INVOKE_ALLOWED)
    for key in _INVOKE_REQUIRED:
        assert key in data, f"invoke result is missing {key!r}"
    assert data["procedure"] == procedure
    assert data["outcome"] == outcome
    assert data["http_status"] == status
    assert data["subject_kind"] == "permit"
    uuid.UUID(data["subject_id"])
    assert isinstance(data["gate_epoch"], int) and data["gate_epoch"] >= 0
    # The contract's own conditional, both directions.
    assert (outcome == "refused") == (data["refusal"] is not None)


# ═══════════════════════════════════════════════════════════════════════════════════════
# routing and request validation — a client error is NEVER dressed as a gate refusal
# ═══════════════════════════════════════════════════════════════════════════════════════


def test_the_five_declared_resources_are_exactly_these() -> None:
    assert set(TRANSITION_RESOURCES) == {
        "materialise_checks",
        "sign_disposition",
        "merge_permit",
        "suspend_permit",
        "demo_gate_run",
    }


def test_unknown_resource_is_404_and_not_an_envelope(w4_conn: psycopg.Connection[Any]) -> None:
    status, payload = handle_transition("delete_everything", {}, {}, w4_conn)
    assert status == 404
    assert payload["error"] == "unknown_resource"
    assert "envelope_version" not in payload


def test_a_malformed_identifier_is_422_and_not_an_envelope(
    w4_conn: psycopg.Connection[Any],
) -> None:
    status, payload = handle_transition("merge_permit", {"permit_id": "../etc/passwd"}, {}, w4_conn)
    assert status == 422
    assert payload["error"] == "unprocessable_request"
    assert "envelope_version" not in payload


def test_a_missing_permit_is_404(w4_conn: psycopg.Connection[Any]) -> None:
    status, payload = handle_transition(
        "merge_permit", {"permit_id": str(uuid.uuid4())}, {}, w4_conn
    )
    assert status == 404
    assert payload["error"] == "no_such_permit"


def test_a_missing_check_is_404(w4_conn: psycopg.Connection[Any]) -> None:
    status, payload = handle_transition(
        "sign_disposition",
        {"check_id": str(uuid.uuid4())},
        {"rationale": "x" * 200},
        w4_conn,
    )
    assert status == 404
    assert payload["error"] == "no_such_check"


def test_a_one_word_clearance_is_refused_by_the_api_not_the_gate(
    w4_conn: psycopg.Connection[Any], fresh_history: Any
) -> None:
    status, payload = handle_transition(
        "sign_disposition",
        {"check_id": str(fresh_history.check_id)},
        {"rationale": "fine"},
        w4_conn,
    )
    assert status == 422
    assert "rationale" in payload["detail"]
    # Explicitly NOT a refusal: no envelope, no SQLSTATE, no exhibit. A short rationale is
    # the caller's mistake and saying otherwise would put a fabricated exhibit in a ledger.
    assert "envelope_version" not in payload


def test_an_undeclared_disposition_kind_is_422(
    w4_conn: psycopg.Connection[Any], fresh_history: Any
) -> None:
    status, payload = handle_transition(
        "sign_disposition",
        {"check_id": str(fresh_history.check_id)},
        {"kind": "vibes", "rationale": "y" * 200},
        w4_conn,
    )
    assert status == 422
    assert "kind" in payload["detail"]


# ═══════════════════════════════════════════════════════════════════════════════════════
# the demo subject is write-protected
#
# THESE TESTS SET `MAINLINE_DEMO_PERMIT_ID` THEMSELVES — AND THAT USED TO BE THE HOLE.
# `w4_database` points the environment at the permit the proof seeder just minted, so every
# assertion below arms the guard before driving it. That is the right fixture for "does the
# guard refuse", and it is exactly the wrong fixture for "is the guard armed in the first
# place": a deployed Lambda whose environment lacks that variable falls back to a uuid5
# derivation nothing has ever seeded, and until 2026-08-13 the guard silently permitted every
# committing POST in that state. This section was green throughout.
#
# `test_the_guard_survives_the_loss_of_its_environment_variable` below is the repair to THIS
# file's blind spot; the adversarial version — all four POSTs, on a real `db.connection()`,
# with the row counts proven unmoved — is `test_demo_guard_anonymous.py`.
# ═══════════════════════════════════════════════════════════════════════════════════════


@pytest.fixture
def demo_check_id(w4_database: str) -> str:  # noqa: F811
    """One obligation belonging to the seeded demo subject.

    ``sign_disposition`` is addressed by the CHECK, not by the subject, so its guard runs
    inside ``_sign_disposition`` after the check has been resolved to its permit. Without a
    check that really belongs to the demo subject, the fourth committing POST cannot be
    driven at it at all — which is how the parametrisation below came to cover three of the
    four for as long as it did.
    """
    import os

    with psycopg.connect(w4_database, autocommit=True) as probe:
        row = probe.execute(
            "SELECT check_id::STRING FROM mainline.blocking_check WHERE permit_id = %s "
            "ORDER BY check_id LIMIT 1",
            (os.environ["MAINLINE_DEMO_PERMIT_ID"],),
        ).fetchone()
    assert row is not None, "the seeded demo subject carries no mainline.blocking_check"
    return str(row[0])


#: A rationale long enough to clear `_RATIONALE_MIN`. `_sign_disposition` validates the body
#: BEFORE it reaches the guard, so a short one would be a 422 that never exercised the guard.
_GUARD_RATIONALE = (
    "The recalled precursor is answered by a verified zero-energy isolation procedure "
    "re-issued after the incident, and this permit's scope is covered by it in full. "
    "Verification at zero is witnessed and recorded before any intrusive work begins."
)


def _demo_posts(permit_id: str, check_id: str) -> tuple[tuple[str, dict[str, str], Any], ...]:
    """The four committing POSTs aimed at the demo subject, with bodies that are VALID."""
    return (
        ("merge_permit", {"permit_id": permit_id}, {}),
        ("suspend_permit", {"permit_id": permit_id}, {"reason": "operator error"}),
        ("materialise_checks", {"permit_id": permit_id}, {}),
        (
            "sign_disposition",
            {"check_id": check_id},
            {"kind": "applied", "rationale": _GUARD_RATIONALE},
        ),
    )


@pytest.mark.parametrize(
    "resource", ["merge_permit", "suspend_permit", "materialise_checks", "sign_disposition"]
)
def test_the_demo_subject_cannot_be_mutated_through_a_transition(
    w4_conn: psycopg.Connection[Any], demo_check_id: str, resource: str
) -> None:
    """One judge must not be able to brick the demo for the next. All FOUR of them."""
    import os

    permit_id = os.environ["MAINLINE_DEMO_PERMIT_ID"]
    posts = {key: (params, body) for key, params, body in _demo_posts(permit_id, demo_check_id)}
    params, body = posts[resource]
    status, payload = handle_transition(resource, params, body, w4_conn)
    assert status == 423, payload
    assert payload["error"] == "demo_subject_write_protected"
    assert payload["use_instead"] == "POST /v1/demo/gate-run"
    assert "envelope_version" not in payload


def test_the_demo_subject_is_unchanged_by_the_attempt(
    w4_conn: psycopg.Connection[Any], demo_check_id: str
) -> None:
    """All four attempts, then the subject read back. A refusal that wrote is not a refusal."""
    import os

    permit_id = os.environ["MAINLINE_DEMO_PERMIT_ID"]
    columns = (
        "SELECT state::STRING, head_seq, gate_epoch, open_blocking, "
        "  (SELECT count(*) FROM mainline.permit_event e WHERE e.permit_id = p.permit_id), "
        "  (SELECT count(*) FROM mainline.merge_record m WHERE m.subject_id = p.permit_id), "
        "  (SELECT count(*) FROM mainline.disposition d WHERE d.permit_id = p.permit_id) "
        "FROM mainline.permit p WHERE p.permit_id = %s"
    )
    before = w4_conn.execute(columns, (permit_id,)).fetchone()
    w4_conn.rollback()
    for resource, params, body in _demo_posts(permit_id, demo_check_id):
        status, payload = handle_transition(resource, params, body, w4_conn)
        assert status == 423, (resource, payload)
    after = w4_conn.execute(columns, (permit_id,)).fetchone()
    w4_conn.rollback()
    assert before == after


def test_the_guard_survives_the_loss_of_its_environment_variable(
    w4_conn: psycopg.Connection[Any], demo_check_id: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Take `MAINLINE_DEMO_PERMIT_ID` away and drive all four at the seeded subject anyway.

    THE TEST THIS FILE WAS MISSING. Every other assertion in this section arms the guard
    first, so none of them could see that the guard is armed BY a variable and disarmed by
    its absence. With the variable gone, ``scenario.permit_id`` is a uuid5 derivation
    nothing seeds, and — measured against the code as it stood on 2026-08-13 —
    ``materialise_checks`` and ``sign_disposition`` both answered 200 and committed on the
    demo subject, moving it out of ``dispositioned`` and closing the obligation the gate
    proof turns on.

    The guard now refuses instead, with ``demo_subject_unidentified`` rather than
    ``demo_subject_write_protected``: it cannot say this subject IS the demo subject when
    the deployment cannot say which subject that is, and claiming otherwise would be a
    fabricated exhibit.
    """
    import os

    permit_id = os.environ["MAINLINE_DEMO_PERMIT_ID"]
    monkeypatch.delenv("MAINLINE_DEMO_PERMIT_ID")

    for resource, params, body in _demo_posts(permit_id, demo_check_id):
        status, payload = handle_transition(resource, params, body, w4_conn)
        w4_conn.rollback()
        assert status == 423, (resource, status, payload)
        assert payload["error"] == "demo_subject_unidentified", (resource, payload)
        assert payload["use_instead"] == "POST /v1/demo/gate-run"
        assert "envelope_version" not in payload


# ═══════════════════════════════════════════════════════════════════════════════════════
# merge_permit — the money path
# ═══════════════════════════════════════════════════════════════════════════════════════


def test_merge_with_an_open_obligation_is_a_refused_envelope(
    w4_conn: psycopg.Connection[Any], fresh_history: Any
) -> None:
    """409, a well-formed envelope, and the exhibit the database reported."""
    status, payload = handle_transition(
        "merge_permit", {"permit_id": str(fresh_history.permit_id)}, {}, w4_conn
    )
    assert status == 409
    data = _assert_envelope(payload, "merge_permit", INVOKE_SCHEMA_ID)
    _assert_invoke(data, "trappoint.merge_permit", "refused", 409)

    refusal = data["refusal"]
    assert refusal["sqlstate"] == "23514"
    assert refusal["constraint"] == "gate_closed_when_issued"
    assert refusal["constraint_source"] == "reported"
    assert refusal["class"] == "gate"
    assert refusal["subject_id"] == str(fresh_history.permit_id)
    assert refusal["diagnosis"] == "declarative"
    assert refusal["mus"][0]["obligation_id"] == str(fresh_history.check_id)
    assert refusal["naa"]["kind"] == "dispose_obligations"
    assert data["committed"] is None


def test_a_refused_merge_persists_nothing(
    w4_conn: psycopg.Connection[Any], fresh_history: Any
) -> None:
    before = w4_conn.execute(
        "SELECT state::STRING, head_seq, gate_epoch FROM mainline.permit WHERE permit_id = %s",
        (fresh_history.permit_id,),
    ).fetchone()
    w4_conn.rollback()
    status, _ = handle_transition(
        "merge_permit", {"permit_id": str(fresh_history.permit_id)}, {}, w4_conn
    )
    assert status == 409
    after = w4_conn.execute(
        "SELECT state::STRING, head_seq, gate_epoch FROM mainline.permit WHERE permit_id = %s",
        (fresh_history.permit_id,),
    ).fetchone()
    merges = w4_conn.execute(
        "SELECT count(*) FROM mainline.merge_record WHERE subject_id = %s",
        (fresh_history.permit_id,),
    ).fetchone()
    w4_conn.rollback()
    assert before == after
    assert merges[0] == 0


# ═══════════════════════════════════════════════════════════════════════════════════════
# sign_disposition, then merge — the admission, committed for real
# ═══════════════════════════════════════════════════════════════════════════════════════


def test_sign_disposition_then_merge_commits(
    w4_conn: psycopg.Connection[Any], fresh_history: Any
) -> None:
    """The whole arc, on a subject of its own, committed rather than rolled back.

    ``gate_run`` shows this arc inside a transaction that is undone. This test shows the
    same arc as the four endpoints actually perform it — two HTTP calls, two commits — so
    that the demo's rollback is a property of the DEMO and not something the transitions
    quietly depend on.
    """
    rationale = (
        "The recalled precursor is answered by a verified zero-energy isolation procedure "
        "re-issued after the incident, and this permit's scope is covered by it in full. "
        "Verification at zero is witnessed and recorded before any intrusive work begins."
    )
    status, payload = handle_transition(
        "sign_disposition",
        {"check_id": str(fresh_history.check_id)},
        {"kind": "applied", "rationale": rationale},
        w4_conn,
    )
    assert status == 200, payload
    data = _assert_envelope(payload, "sign_disposition", INVOKE_SCHEMA_ID)
    _assert_invoke(data, "trappoint.sign_disposition", "committed", 200)
    # STAGED, and the envelope says why: the WebAuthn assertion is synthesised.
    assert payload["staged"] is True
    assert "WebAuthn" in payload["staged_note"]

    closed = w4_conn.execute(
        "SELECT open_blocking FROM mainline.permit WHERE permit_id = %s",
        (fresh_history.permit_id,),
    ).fetchone()
    w4_conn.rollback()
    assert closed[0] == 0, "the projection trigger did not close the counter"

    status, payload = handle_transition(
        "merge_permit", {"permit_id": str(fresh_history.permit_id)}, {}, w4_conn
    )
    assert status == 200, payload
    data = _assert_envelope(payload, "merge_permit", INVOKE_SCHEMA_ID)
    _assert_invoke(data, "trappoint.merge_permit", "committed", 200)
    committed = data["committed"]
    assert committed is not None
    assert len(committed["clearance_digest"]) == 64
    assert committed["merged_commit"]
    assert committed["merged_at"]

    state = w4_conn.execute(
        "SELECT state::STRING FROM mainline.permit WHERE permit_id = %s",
        (fresh_history.permit_id,),
    ).fetchone()
    w4_conn.rollback()
    assert state[0] == "merged"


def test_merging_an_already_merged_permit_is_refused_by_the_epoch_pin(
    w4_conn: psycopg.Connection[Any], fresh_history: Any
) -> None:
    """MI09: `merge_record_pkey` refuses a second merge of the same subject."""
    rationale = "z" * 200
    handle_transition(
        "sign_disposition",
        {"check_id": str(fresh_history.check_id)},
        {"kind": "applied", "rationale": rationale},
        w4_conn,
    )
    first, _ = handle_transition(
        "merge_permit", {"permit_id": str(fresh_history.permit_id)}, {}, w4_conn
    )
    assert first == 200
    second, payload = handle_transition(
        "merge_permit", {"permit_id": str(fresh_history.permit_id)}, {}, w4_conn
    )
    assert second == 409
    data = _assert_envelope(payload, "merge_permit", INVOKE_SCHEMA_ID)
    _assert_invoke(data, "trappoint.merge_permit", "refused", 409)
    # The exhibit is whatever the database named. This test asserts that it named one and
    # that it was reported rather than inferred — not which mechanism happened to fire
    # first, because that is the schema's business and not this file's.
    assert data["refusal"]["constraint"]
    assert data["refusal"]["constraint_source"] in ("reported", "parsed")
    assert data["refusal"]["sqlstate"] in ("23505", "23503", "23514", "P0001")


# ═══════════════════════════════════════════════════════════════════════════════════════
# suspend_permit — the state machine defending itself with data
# ═══════════════════════════════════════════════════════════════════════════════════════


def test_suspending_a_permit_that_never_merged_is_23503_on_legal_edge(
    w4_conn: psycopg.Connection[Any], bare_permit: uuid.UUID
) -> None:
    """`draft -> suspended` is not a row in `mainline.subject_transition`, so it is 23503.

    Not an ``if`` statement in Python that a later commit could delete: a foreign key
    against a table of legal edges. Deleting THAT takes a migration.
    """
    status, payload = handle_transition(
        "suspend_permit", {"permit_id": str(bare_permit)}, {"reason": "operator error"}, w4_conn
    )
    assert status == 409
    data = _assert_envelope(payload, "suspend_permit", INVOKE_SCHEMA_ID)
    _assert_invoke(data, "trappoint.suspend_permit", "refused", 409)
    assert data["refusal"]["sqlstate"] == "23503"
    assert data["refusal"]["constraint"] == "legal_edge"
    assert data["refusal"]["constraint_source"] == "reported"


def test_suspending_a_merged_permit_commits(
    w4_conn: psycopg.Connection[Any], fresh_history: Any
) -> None:
    """`merged -> suspended` IS a legal edge: a merged subject is stopped, never un-merged."""
    handle_transition(
        "sign_disposition",
        {"check_id": str(fresh_history.check_id)},
        {"kind": "applied", "rationale": "q" * 200},
        w4_conn,
    )
    merged, _ = handle_transition(
        "merge_permit", {"permit_id": str(fresh_history.permit_id)}, {}, w4_conn
    )
    assert merged == 200

    status, payload = handle_transition(
        "suspend_permit",
        {"permit_id": str(fresh_history.permit_id)},
        {"reason": "a precursor arrived after issue"},
        w4_conn,
    )
    assert status == 200, payload
    data = _assert_envelope(payload, "suspend_permit", INVOKE_SCHEMA_ID)
    _assert_invoke(data, "trappoint.suspend_permit", "committed", 200)

    row = w4_conn.execute(
        "SELECT p.state::STRING, e.from_state::STRING, e.to_state::STRING "
        "FROM mainline.permit p JOIN mainline.permit_event e "
        "  ON e.permit_id = p.permit_id AND e.seq = p.head_seq "
        "WHERE p.permit_id = %s",
        (fresh_history.permit_id,),
    ).fetchone()
    w4_conn.rollback()
    assert row == ("suspended", "merged", "suspended")


# ═══════════════════════════════════════════════════════════════════════════════════════
# materialise_checks — the exposure receipt, and what the API refuses to fabricate
# ═══════════════════════════════════════════════════════════════════════════════════════


def test_materialise_checks_issues_a_receipt_and_moves_the_subject(
    w4_conn: psycopg.Connection[Any], fresh_history: Any
) -> None:
    status, payload = handle_transition(
        "materialise_checks", {"permit_id": str(fresh_history.permit_id)}, {}, w4_conn
    )
    assert status == 200, payload
    data = _assert_envelope(payload, "materialise_checks", INVOKE_SCHEMA_ID)
    _assert_invoke(data, "trappoint.materialise_checks", "committed", 200)

    row = w4_conn.execute(
        "SELECT p.state::STRING, "
        "  (SELECT count(*) FROM mainline.exposure_receipt r WHERE r.permit_id = p.permit_id), "
        "  (SELECT count(*) FROM mainline.exposure_line l JOIN mainline.exposure_receipt r "
        "     ON r.receipt_id = l.receipt_id WHERE r.permit_id = p.permit_id) "
        "FROM mainline.permit p WHERE p.permit_id = %s",
        (fresh_history.permit_id,),
    ).fetchone()
    w4_conn.rollback()
    assert row[0] == "checks_materialised"
    assert row[1] == 2, "a second exposure receipt should have been issued"
    assert row[2] == 2


def test_materialise_without_a_silence_receipt_is_422_and_fabricates_nothing(
    w4_conn: psycopg.Connection[Any], bare_permit: uuid.UUID
) -> None:
    """A manufactured Proof of Exhausted Recall would assert a search that never happened."""
    status, payload = handle_transition(
        "materialise_checks", {"permit_id": str(bare_permit)}, {}, w4_conn
    )
    assert status == 422
    assert payload["error"] == "no_silence_receipt"
    assert "does not manufacture one" in payload["detail"]

    receipts = w4_conn.execute(
        "SELECT count(*) FROM mainline.exposure_receipt WHERE permit_id = %s", (bare_permit,)
    ).fetchone()
    state = w4_conn.execute(
        "SELECT state::STRING FROM mainline.permit WHERE permit_id = %s", (bare_permit,)
    ).fetchone()
    w4_conn.rollback()
    assert receipts[0] == 0
    assert state[0] == "draft"


# ═══════════════════════════════════════════════════════════════════════════════════════
# the demo driver, through the same entry point
# ═══════════════════════════════════════════════════════════════════════════════════════


def test_gate_run_is_reachable_through_handle_transition(w4_conn: psycopg.Connection[Any]) -> None:
    status, payload = handle_transition("demo_gate_run", {}, {"run_id": "w4-selftest"}, w4_conn)
    assert status == 200
    data = _assert_envelope(payload, "demo_gate_run", GATE_RUN_SCHEMA_ID)
    assert data["run_id"] == "w4-selftest"
    assert data["verdict"] == "PROVEN", data["failures"]
    assert data["persisted"] is False
    assert payload["staged"] is False
    assert [ref["object"] for ref in payload["statement_refs"]][:2] == [
        "mainline.merge_permit",
        "trappoint.explain_refusal",
    ]


def test_gate_run_leaves_the_connection_usable(w4_conn: psycopg.Connection[Any]) -> None:
    handle_transition("demo_gate_run", {}, {}, w4_conn)
    assert w4_conn.execute("SELECT 1").fetchone() == (1,)
    w4_conn.rollback()


def test_a_non_string_run_id_is_422(w4_conn: psycopg.Connection[Any]) -> None:
    status, payload = handle_transition("demo_gate_run", {}, {"run_id": 7}, w4_conn)
    assert status == 422
    assert "run_id" in payload["detail"]


# ═══════════════════════════════════════════════════════════════════════════════════════
# the shared connection is handed back the way it was borrowed
#
# THE DEFECT THIS SECTION EXISTS FOR, MEASURED BEFORE IT WAS FIXED. `transitions._prepare`
# and `transitions._demo_gate_run` each did `if conn.autocommit: conn.autocommit = False`
# on the MODULE-SCOPE connection and never restored it, while `db._open` opens that
# connection with `autocommit=True` and `health.py:106` publishes that fact in prose as the
# reason the health path is structurally incapable of answering 503 on a marker-less
# database. Driven through `handle_transition` against a seeded local node on 2026-08-13,
# before the fix:
#
#     POST /v1/demo/gate-run  -> 200, and conn.autocommit False afterwards
#     the next SELECT 1       -> answered, and left the session INTRANS
#     GET  /v1/health         -> 503 unreachable
#                                [25P02] current transaction is aborted, commands ignored
#                                until end of transaction block
#
# On the deployed marker-carrying cluster the same leak does not 503: it strands the warm
# connection idle-in-transaction, which is a 40001 amplifier no alarm in this repository
# can see. Both consequences have one cause, and it is that the connection was borrowed and
# not given back.
#
# EVERY ASSERTION BELOW RUNS ON `db.connection()`, not on an imitation of it. That is the
# whole point: `w4_conn` above opens with `autocommit=False`, so no test in the first eight
# hundred lines of this file could have disagreed with the code about this.
# ═══════════════════════════════════════════════════════════════════════════════════════


@pytest.fixture
def shared_conn(w4_database: str) -> Iterator[psycopg.Connection[Any]]:  # noqa: F811
    """The REAL module-scope connection — ``db.connection()`` — exactly as a warm Lambda has it.

    Not ``psycopg.connect(dsn, autocommit=True)``: an imitation would prove that this file
    agrees with itself, and what has to hold is that ``db.py``'s choice survives a request
    through ``transitions.py``. The teardown restores and drops it so a leak this suite
    catches cannot escape into the next test and be reported there instead.
    """
    conn = db_mod.connection(dsn=w4_database)
    try:
        yield conn
    finally:
        # `contextlib.suppress` rather than a bare `except`: the only way these raise is a
        # socket that died mid-test, which is the test's failure to report and not this
        # fixture's to mask with a second exception on the way out.
        with contextlib.suppress(psycopg.Error):
            conn.rollback()
            conn.autocommit = True
        db_mod.close()


def _idle(conn: psycopg.Connection[Any]) -> bool:
    return conn.info.transaction_status is psycopg.pq.TransactionStatus.IDLE


def test_the_shared_connection_is_the_one_db_py_opens(
    shared_conn: psycopg.Connection[Any],
    w4_database: str,  # noqa: F811
) -> None:
    """The premise every assertion below rests on, pinned rather than assumed."""
    assert shared_conn.autocommit is True
    assert db_mod.connection(dsn=w4_database) is shared_conn, (
        "db.connection() handed back a different object for the same DSN, so the "
        "'second request' assertions below would not be about the connection the first "
        "request used and would prove nothing"
    )


def test_a_gate_run_hands_the_shared_connection_back_in_autocommit(
    shared_conn: psycopg.Connection[Any],
) -> None:
    """``POST /v1/demo/gate-run`` needs the flag off. It does not get to keep it off."""
    status, payload = handle_transition(
        "demo_gate_run", {}, {"run_id": "w7-borrow-gate-run"}, shared_conn
    )
    assert status == 200, payload
    assert shared_conn.autocommit is True, (
        "the gate run kept the autocommit flag it cleared. db._open opens this connection "
        "with autocommit=True and health.py documents that as the reason the health path "
        "cannot 503; a request that withdraws it silently makes that prose false"
    )
    assert _idle(shared_conn), shared_conn.info.transaction_status


def test_sign_disposition_hands_the_shared_connection_back_in_autocommit(
    shared_conn: psycopg.Connection[Any], fresh_history: Any
) -> None:
    """The other half of the leak: ``_prepare``, reached through the signing endpoint."""
    status, payload = handle_transition(
        "sign_disposition",
        {"check_id": str(fresh_history.check_id)},
        {"kind": "applied", "rationale": _GUARD_RATIONALE},
        shared_conn,
    )
    assert status == 200, payload
    assert shared_conn.autocommit is True, (
        "sign_disposition kept the autocommit flag transitions._prepare cleared"
    )
    assert _idle(shared_conn), shared_conn.info.transaction_status


def test_the_request_after_a_gate_run_is_not_a_503(
    shared_conn: psycopg.Connection[Any],
    w4_database: str,  # noqa: F811
) -> None:
    """The consequence, asserted as the consequence: what the NEXT caller gets.

    ``GET /v1/health`` is the request that measured 503 ``[25P02]`` before the fix, and it
    is the right one to assert on: it is the only endpoint whose own module states, in
    prose, that it cannot fail this way.
    """
    assert handle_transition("demo_gate_run", {}, {"run_id": "w7-then-next"}, shared_conn)[0] == 200

    status, body = health(dsn=w4_database)
    assert status == 200, body
    assert body["ok"] is True
    assert "25P02" not in str(body), body

    again, payload = handle_transition(
        "demo_gate_run", {}, {"run_id": "w7-second-request"}, shared_conn
    )
    assert again == 200, payload
    assert payload["data"]["verdict"] == "PROVEN", payload["data"]["failures"]


def test_the_request_after_a_sign_disposition_is_not_a_503(
    shared_conn: psycopg.Connection[Any],
    w4_database: str,  # noqa: F811
    fresh_history: Any,
) -> None:
    """Same assertion, on the path that commits rather than the one that rolls back."""
    signed, payload = handle_transition(
        "sign_disposition",
        {"check_id": str(fresh_history.check_id)},
        {"kind": "applied", "rationale": _GUARD_RATIONALE},
        shared_conn,
    )
    assert signed == 200, payload

    status, body = health(dsn=w4_database)
    assert status == 200, body
    assert body["ok"] is True
    assert "25P02" not in str(body), body

    merged, payload = handle_transition(
        "merge_permit", {"permit_id": str(fresh_history.permit_id)}, {}, shared_conn
    )
    assert merged == 200, payload


def test_every_outcome_hands_the_connection_back(
    shared_conn: psycopg.Connection[Any], fresh_history: Any, demo_check_id: str
) -> None:
    """404, 422, 423 and 409 as well — an early return is an exit path like any other.

    A restore written at the bottom of the happy path would pass the two tests above and
    leak on all four of these, which is the shape the original defect had.
    """
    import os

    cases: tuple[tuple[str, str, dict[str, Any], Any, int], ...] = (
        ("unknown resource", "delete_everything", {}, {}, 404),
        ("malformed identifier", "merge_permit", {"permit_id": "../etc/passwd"}, {}, 422),
        ("no such permit", "merge_permit", {"permit_id": str(uuid.uuid4())}, {}, 404),
        (
            "the write-protected demo subject",
            "merge_permit",
            {"permit_id": os.environ["MAINLINE_DEMO_PERMIT_ID"]},
            {},
            423,
        ),
        (
            "a one-word clearance",
            "sign_disposition",
            {"check_id": demo_check_id},
            {"rationale": "fine"},
            422,
        ),
        (
            "the gate refusing a merge",
            "merge_permit",
            {"permit_id": str(fresh_history.permit_id)},
            {},
            409,
        ),
    )
    for name, resource, params, body, expected in cases:
        status, payload = handle_transition(resource, params, body, shared_conn)
        assert status == expected, (name, status, payload)
        assert shared_conn.autocommit is True, f"{name} left the connection out of autocommit"
        assert _idle(shared_conn), (name, shared_conn.info.transaction_status)


def _plant_in_gate_run(
    monkeypatch: pytest.MonkeyPatch, planted: Exception, *, after_a_statement: bool = True
) -> None:
    """Make ``gate_run`` issue one statement and then raise *planted*.

    The statement matters: it leaves the connection ``INTRANS`` exactly as a real beat
    would, so the assertion that follows is about a restore that had to roll a live
    transaction back first, not about a flag on an idle socket.
    """

    def boom(conn: psycopg.Connection[Any], *_args: Any, **_kwargs: Any) -> None:
        if after_a_statement:
            conn.execute("SELECT 1")
        raise planted

    monkeypatch.setattr(transitions_mod, "gate_run", boom)


def test_a_defect_escaping_the_handler_does_not_leak_the_flag(
    shared_conn: psycopg.Connection[Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    """The path ``handle_transition`` deliberately does NOT translate: a defect in this module.

    Its docstring says so — *"only a defect in this module reaches the caller as an
    exception, and it should"* — which makes this the one exit that skips every ``return``
    in the function. A restore written before any of those returns would leak here.
    """
    _plant_in_gate_run(monkeypatch, RuntimeError("a planted defect in this module"))
    with pytest.raises(RuntimeError, match="a planted defect"):
        handle_transition("demo_gate_run", {}, {}, shared_conn)

    assert shared_conn.autocommit is True
    assert _idle(shared_conn), shared_conn.info.transaction_status


def test_a_40001_escaping_the_beats_does_not_leak_the_flag(
    shared_conn: psycopg.Connection[Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    """A serialization failure that no ``except psycopg.Error`` inside a transition caught.

    ``psycopg.errors.SerializationFailure`` inherits from ``psycopg.OperationalError``
    (measured: ``SerializationFailure -> OperationalError -> DatabaseError -> Error``), so
    ``handle_transition``'s last handler claims it and answers ``503
    database_unreachable`` rather than re-raising. That is asserted here as the behaviour
    it IS, not as the behaviour it should be — this test is about the connection, and a
    test that quietly asserted a nicer taxonomy than the code has would be the same lie
    this section was written to close.

    What matters for the flag is that this is a third distinct door out — not a return
    from a transition, not a raise through the caller — and it too gives the connection
    back. The managed cluster is where 40001 actually happens; the demo runs on one.
    """
    _plant_in_gate_run(
        monkeypatch, psycopg.errors.SerializationFailure("a planted 40001 escaping the beats")
    )
    status, payload = handle_transition("demo_gate_run", {}, {}, shared_conn)

    assert status == 503, payload
    assert payload["error"] == "database_unreachable"
    assert shared_conn.autocommit is True
    assert _idle(shared_conn), shared_conn.info.transaction_status


#: The one function in ``transitions.py`` permitted to assign ``conn.autocommit``.
_AUTOCOMMIT_OWNER = "_borrowed"


def _autocommit_assignment_sites(source: str) -> list[tuple[str, int]]:
    """Every ``<expr>.autocommit = …`` in *source*, paired with the function it sits in."""
    found: list[tuple[str, int]] = []

    def walk(node: ast.AST, owner: str) -> None:
        for child in ast.iter_child_nodes(node):
            if isinstance(child, ast.FunctionDef | ast.AsyncFunctionDef):
                walk(child, child.name)
                continue
            if isinstance(child, ast.Assign):
                for target in child.targets:
                    if isinstance(target, ast.Attribute) and target.attr == "autocommit":
                        found.append((owner, child.lineno))
            walk(child, owner)

    walk(ast.parse(source), "<module>")
    return found


def test_only_the_borrow_context_manager_assigns_autocommit() -> None:
    """Close the CLASS, not the instance — the whole reason this defect reached its third wave.

    Two functions cleared the flag and neither restored it. Fixing both and stopping there
    leaves the next function free to make it three. This reads ``transitions.py`` and
    requires that the only assignment to ``.autocommit`` anywhere in it lives in
    :func:`transitions._borrowed`, whose ``finally`` is what puts it back. A third caller
    that clears the flag by hand fails here even if its own tests are green.
    """
    source = Path(transitions_mod.__file__).read_text(encoding="utf-8")
    sites = _autocommit_assignment_sites(source)
    assert sites, (
        "no assignment to `.autocommit` was found in transitions.py at all, so this test "
        "has lost its subject and is asserting nothing"
    )
    assert {owner for owner, _line in sites} == {_AUTOCOMMIT_OWNER}, (
        f"transitions.py assigns .autocommit outside {_AUTOCOMMIT_OWNER}(): {sites}. "
        "The flag belongs to db.connection() and is borrowed for one request; a clear "
        "written anywhere but beside its own restore is how this defect survived two waves"
    )
