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

EVERY TRANSACTION IN THIS FILE, AND WHAT GUARDS IT
---------------------------------------------------
There is exactly ONE multi-statement transaction here — :func:`_seed_permit`, twelve
statements ending in a read-modify-write on ``mainline.permit`` — and it is now run by
:func:`trappoint_testkit.txn.run_txn`, which retries the WHOLE transaction from ``BEGIN`` on
a fresh connection when the database answers ``40001``. The loop itself is
``trappoint_core.retry.run_gate``; nothing here re-implements one, because a second loop
would be a second SQLSTATE taxonomy and ``spec/errors.md`` §2.1 already owns the first.

The other three connection sites are deliberately NOT retried, and each says why where it
is: ``w4_conn`` and ``shared_conn`` LEND a connection to ``handle_transition``, whose own
transaction is the unit a ``40001`` would restart (that guard lives in the deployment
package under R11, which forbids it importing ``trappoint_core``); ``bare_permit`` is
autocommit, so each statement is an implicit transaction CockroachDB restarts server-side
and there is no multi-statement unit to be the subject of a client retry.

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
from mainline_demo_api.gate_run import gate_run as gate_run_fn
from mainline_demo_api.health import health
from mainline_demo_api.retry import DEFAULT_POLICY
from mainline_demo_api.transitions import (
    INVOKE_SCHEMA_ID,
    TRANSITION_RESOURCES,
    handle_transition,
)
from psycopg.types.json import Jsonb
from test_gate_run import w4_database  # noqa: F401 - re-exported so pytest can resolve it
from trappoint_testkit.txn import from_dsn, run_txn

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

    **THIS FUNCTION NO LONGER COMMITS, AND IT NO LONGER ROLLS BACK.** It is the WORK half of
    one whole transaction; :func:`fresh_history` hands it to
    :func:`trappoint_testkit.txn.run_txn`, which opens a fresh connection, states the
    isolation level, runs this to completion, commits it, and — on ``40001`` — throws the
    connection away and runs the WHOLE of it again. That granularity is the requirement, not
    a preference: ``spec/errors.md`` §2.1 forbids retrying a statement, because a statement
    replayed into a transaction CockroachDB has already aborted is not a retry of anything.

    What was here before: twelve statements over seven tables, two of which read the
    previous ``permit_event``'s ``chain_digest`` and then ``UPDATE mainline.permit`` — a
    read-modify-write on one row — ending in a single ``.commit()`` with no retry of any
    kind. ``tests/concurrency/test_seed_permit_needs_retry.py`` transcribes that shape and
    races two callers at one subject against the LOCAL single-node CockroachDB v26.2.5:
    ``40001`` in 6 of 6 races, one loser per race, and the loser's entire history — recall
    run, receipt, the line that displayed the obligation, the event that claimed it disposed
    of — gone. So this is not a Cloud-only hazard and was never provably absent here; it was
    merely never raced.

    **Every identifier is minted INSIDE this function**, and that has become load-bearing: a
    retry runs the body again from the top, so a ``uuid4`` hoisted into the fixture would be
    replayed and the second attempt would meet its own first attempt's key — a ``23505``,
    which the loop must attempt exactly once and must never retry.

    *w4_conn* is the connection ``run_txn`` opened for THIS attempt and nothing else holds.
    It keeps psycopg's default ``tuple_row`` because :data:`_SITE_SQL`'s row is read by
    POSITION, which is what the fixture opened by hand before.
    """
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
    # THE VOCABULARY THIS CHECK OFFERS, added 2026-08-14 with the resolver that reads it.
    #
    # `_seed_permit` mints its OWN check with a fresh uuid, so the demo seed's vocabulary does not
    # cover it and `defeaters.resolve_defeater_vocabulary` refuses the signature with
    # `422 demo_history_not_seeded`. That refusal is CORRECT and is not worked around here: a
    # disposition pins `vocab_sha256`, the digest of the option set the signer was shown, and a
    # check offering nothing has no such digest — 0064's rationale calls a signature that pins
    # nothing "a click-through with a signature on it". So this fixture now seeds what any real
    # obligation would carry, rather than the test asserting that an unsignable check can be signed.
    #
    # The digest is aggregated from the rows under a deterministic ORDER BY, exactly as the demo
    # seeds do, and NOT written down: a literal would be a constant that merely looks like a hash
    # and would silently describe the wrong set the moment an option is added. The codes are the
    # permit-side three, because this fixture mints a permit obligation against the same isolation
    # clause the demo uses.
    w4_conn.execute(
        "WITH options (defeater_code, prompt) AS (VALUES "
        "  ('ENERGY_SOURCE_ABSENT', 'Which stored-energy source was surveyed and found absent?'), "
        "  ('MECHANISM_PRESENT_AND_VERIFIED', 'Which isolation point was locked, and who verified "
        "it at zero?'), "
        "  ('WORK_NOT_INTRUSIVE', 'Which task was assessed as non-intrusive, and against which "
        "method statement?')), "
        "vocab AS (SELECT digest(string_agg(defeater_code || chr(31) || prompt, chr(30) "
        "  ORDER BY defeater_code), 'sha256') AS sha FROM options) "
        "INSERT INTO mainline.defeater_option (check_id, defeater_code, prompt, vocab_sha256) "
        "SELECT %s, o.defeater_code, o.prompt, v.sha FROM options AS o CROSS JOIN vocab AS v",
        (check_id,),
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
    # No commit. `run_txn` owns it — see this function's docstring. A commit here would
    # make the retried unit a PART of the transaction, and `TransactionNotCommittable`
    # exists to refuse that rather than let it pass quietly.
    return _History(permit_id, check_id, site_id)


@pytest.fixture
def w4_conn(w4_database: str) -> Iterator[psycopg.Connection[Any]]:  # noqa: F811
    """A connection to the w4 scratch database. Named apart from the conftest's `conn`.

    DELIBERATELY NOT RETRIED, and the reason is that this connection is not a transaction
    site at all: it is the connection a test LENDS to ``handle_transition``, standing in for
    the one ``app.handler`` lends it on a Function URL invocation. The transaction is opened
    and closed inside ``transitions.py``, so the unit a ``40001`` would have to restart is
    the request — which is what ``mainline_demo_api.retry`` guards, inside the deployment
    package, under RULING R11 (the Lambda may not import ``trappoint_core``). A ``run_txn``
    wrapped round a connection borrowed by somebody else's transaction is the exact mistake
    ``spec/errors.md`` §2.1 names, so there is nothing for this fixture to wrap.
    """
    with psycopg.connect(w4_database, autocommit=False) as connection:
        yield connection


@pytest.fixture
def fresh_history(w4_database: str) -> _History:  # noqa: F811
    """A brand-new permit with one open obligation. Its own subject, so tests cannot collide.

    **THE RETRY OWNS THE CONNECTION, WHICH IS WHY THIS FIXTURE NO LONGER OPENS ONE.** It
    used to ``psycopg.connect`` and hand the open connection to :func:`_seed_permit`, which
    committed. Handing an already-open connection to a retry is the failure ``spec/errors.md``
    §2.1 describes, and :class:`trappoint_testkit.txn.ConnectionNotFresh` makes that call
    impossible to write: there is no parameter that accepts a connection, only a factory.
    :func:`~trappoint_testkit.txn.from_dsn` builds the factory; ``run_txn`` opens a NEW
    connection per attempt, so a poisoned one is discarded rather than replayed into.

    It is also no longer a generator. Nothing downstream reads from the seeding connection —
    every test does its own reads on ``w4_conn`` — and holding one open for the life of the
    test was what made the commit look like the end of a scope rather than the end of a
    transaction.
    """
    import os

    permit_id = os.environ["MAINLINE_DEMO_PERMIT_ID"]
    signer = os.environ["MAINLINE_DEMO_SIGNER_SUB"]
    return run_txn(
        from_dsn(w4_database),
        lambda conn: _seed_permit(conn, permit_id, signer),
        subject_kind="permit",
    )


@pytest.fixture
def bare_permit(w4_database: str) -> Iterator[uuid.UUID]:  # noqa: F811
    """A permit and nothing else — no recall run, no obligation, state 'draft'.

    The subject a precondition failure is about. Nothing here is fabricated to produce an
    error: this is simply a permit that has not been through recall yet, which is what
    every permit is on the day it is drafted.

    NOT RETRIED, and the reason is measurable rather than a judgement call: the connection
    is ``autocommit=True``, so each of the two statements is its own implicit transaction
    and CockroachDB restarts an implicit transaction SERVER-side. There is no multi-statement
    unit here for a client retry to be OF — which is also why ``from_dsn`` refuses
    ``autocommit=True`` outright rather than accepting it and retrying the last statement.
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


def test_the_six_declared_resources_are_exactly_these() -> None:
    """Four kernel transitions and two demo drivers. An EQUALITY, never a subset check.

    The sixth is ``cr_gate_run`` — ``POST /v1/demo/cr-gate-run`` — and it is the mirror of
    ``demo_gate_run`` against the second gated subject. Written as a set equality so that a
    seventh resource appearing here without the rest of its declaration is a red rather
    than a silent pass: ``app.py::_routes()``'s own record of this demo's headline defect
    is every beat implemented and none of it reachable, and a POST that is in this table
    and in no ``Route`` row is the same defect with the halves swapped.
    """
    assert set(TRANSITION_RESOURCES) == {
        "materialise_checks",
        "sign_disposition",
        "merge_permit",
        "suspend_permit",
        "demo_gate_run",
        "cr_gate_run",
    }


def test_neither_demo_driver_takes_a_path_parameter_or_mutates() -> None:
    """``(None, None, False)`` for both, and for the second one that is a SAFETY property.

    ``_demo_guard``'s whole decision is ``subject_id == scenario.permit_id``. A change
    request identifier never equals a permit identifier, so a mutating change-request
    transition would fall past the ``demo_subject_write_protected`` branch, reach
    ``_demo_subject_is_established``, find the permit IS seeded, and be LET THROUGH — an
    unguarded, irreversible, unauthenticated write on the seeded demo change request, which
    is the shape ``evidence/deploy/demo-guard-armed.json`` records one subject over.

    The guard is not widened to cover it, because nothing in this wave needs that and
    widening it now is how the committing route gets added later without the argument being
    had. What is asserted instead is the shape that makes the guard unnecessary: no path
    parameter, so ``handle_transition`` never reaches ``_uuid_param``; no procedure; and no
    mutation, because the whole transaction is rolled back.
    """
    for key in ("demo_gate_run", "cr_gate_run"):
        param_name, procedure, mutates = TRANSITION_RESOURCES[key]
        assert param_name is None, key
        assert procedure is None, key
        assert mutates is False, key
    mutating = {key for key, (_p, _proc, m) in TRANSITION_RESOURCES.items() if m}
    assert all(TRANSITION_RESOURCES[key][0] in ("permit_id", "check_id") for key in mutating), (
        "a mutating resource whose path parameter is neither permit_id nor check_id would "
        "not be resolved to a permit by handle_transition, so _demo_guard would either be "
        "skipped or asked about a subject it cannot recognise. Both are the hole this "
        "wave declined to open."
    )


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
# 40001, INDUCED — answered as an UNDECIDED transaction, never as an absent database
#
# THE CONFLICT BELOW IS THE DATABASE'S, NOT A DOUBLE'S. Nothing here plants an exception. A
# SECOND session commits a write to the row the transition has just read, in the window
# between that read and the transition's own write, and CockroachDB v26.2.5 — SERIALIZABLE
# by default — aborts the transition with 40001 RETRY_SERIALIZABLE. The monkeypatch decides
# only WHEN the second session runs; the conflict, the SQLSTATE, the abort and the retry
# are all the cluster's.
#
# "UNTESTABLE WITHOUT A MANAGED CLUSTER" IS FALSE AND MAY NOT BE CLAIMED. `db.py:33` says a
# single-node local cluster "never produces RETRY_SERIALIZABLE"; this repository has now
# refuted that three times on 127.0.0.1:26257 — a prior lead raced two connections over two
# rows and measured 40001 six times out of six; `qa/cluster-known-red.json` records twelve
# SerializationFailures over six node ids from one deliberately-shared scratch database;
# and the defect these two tests close was reproduced by the whole suite twice in a row
# with no contention arranged at all. `crdb_internal` and `system` are RESTRICTED on
# CockroachDB Cloud's Basic tier, so contention must be INDUCED and the SQLSTATE OBSERVED,
# which is what these do.
#
# WHAT WAS MEASURED HERE BEFORE THE REPAIR, at 7535670, from a whole-suite --junitxml:
# `test_sign_disposition_then_merge_commits` and `test_suspending_a_merged_permit_commits`
# both `assert 503 == 200`, body `{'error': 'database_unreachable', 'detail': 'restart
# transaction: TransactionRetryWithProtoRefreshError…'}`. The node id moved between runs;
# the shape never did. These two tests are the shape, held still.
# ═══════════════════════════════════════════════════════════════════════════════════════


class _ConflictingWriter:
    """A second session that commits a write to one permit row, on cue and up to *budget*.

    ``horizon_at`` is the column, deliberately: it is on the row every transition reads for
    its ``gate_epoch``/``head_seq``/``state`` anchor, and it is read by no assertion in this
    file, so the conflict lands on the key that matters without changing a value any test
    is about. The write commits — ``autocommit=True`` — because an UNCOMMITTED write would
    make the transition BLOCK on an intent rather than meet a serialization failure, and a
    test that hangs is not a test that measured anything.
    """

    def __init__(self, dsn: str, permit_id: uuid.UUID, budget: int) -> None:
        self.dsn = dsn
        self.permit_id = permit_id
        self.budget = budget
        self.fired = 0

    def write(self) -> None:
        """Commit one conflicting write, while the budget lasts."""
        if self.fired >= self.budget:
            return
        self.fired += 1
        with psycopg.connect(self.dsn, autocommit=True) as other:
            other.execute(
                "UPDATE mainline.permit SET horizon_at = horizon_at + INTERVAL '1 second' "
                "WHERE permit_id = %s",
                (self.permit_id,),
            )


def _contend_after_the_permit_read(
    monkeypatch: pytest.MonkeyPatch, writer: _ConflictingWriter
) -> None:
    """Fire *writer* immediately after every ``transitions._permit_epoch``.

    That call is the transition's anchor read and it happens BEFORE the transition has
    written anything, so the conflicting session finds no intent to block on. Installing it
    at any later point would deadlock the two sessions instead of racing them, which is a
    different experiment and a worse one.
    """
    real = transitions_mod._permit_epoch

    def instrumented(conn: psycopg.Connection[Any], permit_id: uuid.UUID) -> Any:
        anchor = real(conn, permit_id)
        writer.write()
        return anchor

    monkeypatch.setattr(transitions_mod, "_permit_epoch", instrumented)


def _sign(w4_conn: psycopg.Connection[Any], check_id: uuid.UUID) -> None:
    """Close the obligation so the merge that follows is admitted rather than refused."""
    status, payload = handle_transition(
        "sign_disposition",
        {"check_id": str(check_id)},
        {"kind": "applied", "rationale": _GUARD_RATIONALE},
        w4_conn,
    )
    assert status == 200, payload


def test_this_single_local_node_really_does_produce_40001_and_it_is_an_operational_error(
    w4_database: str,  # noqa: F811
    fresh_history: Any,
) -> None:
    """The premise of the two tests below, observed as a SQLSTATE rather than as a status.

    NO APPLICATION CODE RUNS HERE. Two plain psycopg connections, one row, and the classic
    read-then-conflicting-write order that ``SERIALIZABLE`` is defined to refuse. What is
    asserted is the driver's own exception: its SQLSTATE, and — the second assertion, which
    is the whole of finding F-2 — the class it inherits from.

    ``db.py:33`` states that a single-node local cluster "never produces
    RETRY_SERIALIZABLE", and ``test_gate_run.py:389`` restates it. This is the third
    independent refutation of that sentence on 127.0.0.1:26257 and the cheapest one to
    re-run. It matters because the claim was load-bearing: while it stood, the 40001 path
    was believed untestable here, so it was never tested, so the misdiagnosis below it
    survived two waves.

    ``psycopg.errors.SerializationFailure`` being a ``psycopg.OperationalError`` is the
    entire mechanism by which ``handle_transition``'s "no cluster is not a refusal" handler
    used to swallow 40001 and answer ``database_unreachable``. Pinning it here means the day
    psycopg reparents that class is the day this test says so, rather than the day the
    handler silently stops catching what it was written to catch.
    """
    permit_id = fresh_history.permit_id
    with psycopg.connect(w4_database, autocommit=False) as first:
        first.execute("SET TRANSACTION ISOLATION LEVEL SERIALIZABLE")
        anchor = first.execute(
            "SELECT state::STRING FROM mainline.permit WHERE permit_id = %s", (permit_id,)
        ).fetchone()
        assert anchor is not None

        with psycopg.connect(w4_database, autocommit=True) as second:
            second.execute(
                "UPDATE mainline.permit SET horizon_at = horizon_at + INTERVAL '1 second' "
                "WHERE permit_id = %s",
                (permit_id,),
            )

        def write_then_commit() -> None:
            """The conflicting half. CockroachDB may refuse at either statement.

            Whether the restart surfaces on the UPDATE (``RETRY_WRITE_TOO_OLD``) or on the
            COMMIT (``RETRY_SERIALIZABLE — failed preemptive refresh``) is the cluster's
            choice and is exactly what this test must not pin: both are ``40001``, and a
            test that demanded one of them would fail on a version that chose the other.
            """
            first.execute(
                "UPDATE mainline.permit SET horizon_at = horizon_at + INTERVAL '2 seconds' "
                "WHERE permit_id = %s",
                (permit_id,),
            )
            first.commit()

        with pytest.raises(psycopg.errors.SerializationFailure) as caught:
            write_then_commit()
        first.rollback()

    assert caught.value.sqlstate == "40001", caught.value.sqlstate
    assert isinstance(caught.value, psycopg.OperationalError), (
        "SerializationFailure is not an OperationalError in this psycopg, so "
        "handle_transition's `except psycopg.OperationalError` no longer sees 40001 at "
        "all and the branch that classifies it there is now unreachable — read it before "
        "trusting anything else in this section"
    )


def test_a_40001_induced_on_the_merge_path_is_retried_and_the_merge_commits(
    w4_conn: psycopg.Connection[Any],
    w4_database: str,  # noqa: F811
    fresh_history: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """One real serialization failure, and the caller never learns it happened.

    ``spec/errors.md`` §2.1: the retried unit is the WHOLE transaction, from ``BEGIN``. The
    conflicting session commits once, the first attempt is aborted by the database, the
    second attempt reads at a later timestamp and commits — and the answer is the 200 the
    endpoint owes, not a 503 about a database that was never unreachable.

    The assertion that the writer fired is not decoration. Without it a run in which the
    race simply did not happen would pass this test for the wrong reason, and a test that
    can pass without its own premise is the failure mode this file exists to refuse.
    """
    _sign(w4_conn, fresh_history.check_id)

    writer = _ConflictingWriter(w4_database, fresh_history.permit_id, budget=1)
    _contend_after_the_permit_read(monkeypatch, writer)

    status, payload = handle_transition(
        "merge_permit", {"permit_id": str(fresh_history.permit_id)}, {}, w4_conn
    )

    assert writer.fired == 1, "the conflicting write never ran, so nothing was contended"
    assert status == 200, payload
    data = _assert_envelope(payload, "merge_permit", INVOKE_SCHEMA_ID)
    _assert_invoke(data, "trappoint.merge_permit", "committed", 200)

    state = w4_conn.execute(
        "SELECT state::STRING FROM mainline.permit WHERE permit_id = %s",
        (fresh_history.permit_id,),
    ).fetchone()
    merges = w4_conn.execute(
        "SELECT count(*) FROM mainline.merge_record WHERE subject_id = %s",
        (fresh_history.permit_id,),
    ).fetchone()
    w4_conn.rollback()
    assert state[0] == "merged"
    assert merges[0] == 1, (
        "the retry must be a fresh ATTEMPT, not a replay: a 40001 aborts the transaction, "
        "so re-running it can leave exactly one merge_record and never two"
    )


def test_a_40001_on_every_attempt_is_undecided_and_is_never_database_unreachable(
    w4_conn: psycopg.Connection[Any],
    w4_database: str,  # noqa: F811
    fresh_history: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Contend on EVERY attempt, spend the budget, and read what the caller is told.

    This is the assertion the repair is for. ``spec/errors.md`` §5 requires an exhausted
    budget to be surfaced as a distinct condition and NOT as a refusal; what it was
    surfaced as until 2026-08-14 was ``database_unreachable``, which is neither — it is a
    false statement about the cluster.

    Both shapes of the honest answer are accepted, because which one arrives is decided by
    WHICH STATEMENT met the 40001 and that is the database's business, not this test's: a
    transition that caught it returns the ``503``/``outcome: retry`` envelope
    ``contracts/invoke.schema.json`` declares, and one that met it at ``commit()`` — where
    no ``except psycopg.Error`` stands — arrives as an exception and is answered
    ``transaction_undecided`` with the SQLSTATE on it. What is asserted unconditionally is
    the part that was wrong: it is a 503, it is undecided, and it is NOT
    ``database_unreachable``.
    """
    _sign(w4_conn, fresh_history.check_id)

    writer = _ConflictingWriter(w4_database, fresh_history.permit_id, budget=1_000)
    _contend_after_the_permit_read(monkeypatch, writer)

    status, payload = handle_transition(
        "merge_permit", {"permit_id": str(fresh_history.permit_id)}, {}, w4_conn
    )

    assert status == 503, payload
    assert payload.get("error") != "database_unreachable", (
        "40001 is not an unreachable database. The cluster answered, and it answered with "
        "a decision to abort; saying otherwise sends whoever is triaging to Terraform."
    )
    assert writer.fired >= DEFAULT_POLICY.max_attempts, (
        f"the conflicting write fired {writer.fired} time(s); the whole transaction is "
        f"bounded at {DEFAULT_POLICY.max_attempts} attempts and each one takes the anchor "
        "read, so fewer than that means the retry loop never ran"
    )

    if "envelope_version" in payload:
        data = _assert_envelope(payload, "merge_permit", INVOKE_SCHEMA_ID)
        _assert_invoke(data, "trappoint.merge_permit", "retry", 503)
        assert data["refusal"] is None, "an undecided transaction has no reason set (§5)"
        assert data["committed"] is None
    else:
        assert payload["error"] == "transaction_undecided", payload
        assert payload["sqlstate"] == "40001", payload
        assert payload["attempts"] == DEFAULT_POLICY.max_attempts, payload

    merges = w4_conn.execute(
        "SELECT count(*) FROM mainline.merge_record WHERE subject_id = %s",
        (fresh_history.permit_id,),
    ).fetchone()
    w4_conn.rollback()
    assert merges[0] == 0, (
        "an undecided transaction wrote nothing, on every one of its attempts. A row here "
        "would mean the budget was spent over a merge that had already landed."
    )


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
# the SECOND demo driver, on a database that does not carry its subject
#
# This scratch database is built by `scripts/proof/gate_refusal.py::seed_history`, which
# seeds a permit and no change request — measured: `grep change_request` over that file
# finds nothing. That is not a gap to be papered over here. It is the one condition
# `POST /v1/demo/cr-gate-run` has to answer honestly and that the seeded database can never
# exercise, so it is asserted where it exists: "there was nothing to ask" and "the gate did
# not refuse" are different findings and only one of them is about the product.
#
# The three-beat run against the subject that IS seeded lives in `test_cr_gate_run.py`,
# against `conftest.py`'s `demo_database` — the deployed seed.
# ═══════════════════════════════════════════════════════════════════════════════════════


def test_cr_gate_run_on_a_database_with_no_change_request_is_422_and_not_a_refusal(
    w4_conn: psycopg.Connection[Any],
) -> None:
    status, payload = handle_transition("cr_gate_run", {}, {"run_id": "w4-no-cr"}, w4_conn)
    assert status == 422, payload
    assert payload["error"] == "demo_history_not_seeded"
    assert "change_request" in payload["detail"]
    assert "MAINLINE_DEMO_CR_ID" in payload["detail"]
    # A plain {error, detail}, never an envelope: the console's transport treats a non-2xx
    # body that is not an envelope as a transport failure, which is the correct diagnosis
    # for "this deployment does not carry that subject". Dressing it as a gate refusal
    # would put a fabricated exhibit in front of a reader.
    assert "envelope_version" not in payload
    assert "sqlstate" not in payload


def test_cr_gate_run_hands_the_shared_connection_back_in_autocommit(
    shared_conn: psycopg.Connection[Any],
) -> None:
    """Same borrow, same restore — asserted on the 422 path, which is the one that returns
    early.

    ``_borrowed``'s ``finally`` is what makes this true for every exit, and a restore
    written at the bottom of a happy path would pass every other assertion in this section
    and leak here. This is the newest caller and therefore the one most likely to have been
    written without it.
    """
    status, _payload = handle_transition("cr_gate_run", {}, {}, shared_conn)
    assert status == 422
    assert shared_conn.autocommit is True
    assert _idle(shared_conn), shared_conn.info.transaction_status


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
) -> list[int]:
    """Make ``gate_run`` issue one statement and then raise *planted*.

    The statement matters: it leaves the connection ``INTRANS`` exactly as a real beat
    would, so the assertion that follows is about a restore that had to roll a live
    transaction back first, not about a flag on an idle socket.

    Returns a one-element list holding the number of times the plant fired. That IS the
    attempt count — ``gate_run`` is called once per attempt and nowhere else — so a test
    can assert how many whole transactions the retry loop ran without reaching inside it
    for a spy the deployment package does not ship.
    """
    fired = [0]

    def boom(conn: psycopg.Connection[Any], *_args: Any, **_kwargs: Any) -> None:
        fired[0] += 1
        if after_a_statement:
            conn.execute("SELECT 1")
        raise planted

    monkeypatch.setattr(transitions_mod, "gate_run", boom)
    return fired


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

    THIS EXPECTED VALUE MOVED ON 2026-08-14, AND HERE IS THE RULING THAT MOVED IT.
    ``psycopg.errors.SerializationFailure`` inherits from ``psycopg.OperationalError``
    (measured: ``SerializationFailure -> OperationalError -> DatabaseError -> Error``), so
    ``handle_transition``'s last handler claimed it and answered ``503
    database_unreachable``. This test asserted that **on purpose**, and said so: *"asserted
    here as the behaviour it IS, not as the behaviour it should be — this test is about the
    connection, and a test that quietly asserted a nicer taxonomy than the code has would
    be the same lie this section was written to close."* It was right to, and
    ``docs/diagnosis/refusal-that-writes.md`` §7 recorded the defect and asked a lead to
    rule rather than editing the expectation itself.

    ``docs/leads/ci-green-final.md`` R3 is that ruling. The code moved and the expectation
    followed it: the sentence ``database_unreachable`` is FALSE for ``40001`` — the
    database answered, and answered with a decision to abort — and ``spec/errors.md`` §5
    requires an exhausted retry budget to be surfaced as a distinct condition that is not a
    refusal. So the answer is now ``transaction_undecided``, carrying the SQLSTATE, after
    the whole transaction has been re-attempted ``retry.DEFAULT_POLICY.max_attempts``
    times. Nothing here was weakened: this test gained two assertions and lost none, and
    the one value that changed is the one a lead ruled on.

    What matters for the flag is unchanged and is still asserted last: this is a third
    distinct door out — not a return from a transition, not a raise through the caller —
    and it too gives the connection back.
    """
    fired = _plant_in_gate_run(
        monkeypatch, psycopg.errors.SerializationFailure("a planted 40001 escaping the beats")
    )
    status, payload = handle_transition("demo_gate_run", {}, {}, shared_conn)

    assert status == 503, payload
    assert payload["error"] == "transaction_undecided", payload
    assert payload["sqlstate"] == "40001", payload
    assert payload["error"] != "database_unreachable"
    assert fired[0] == DEFAULT_POLICY.max_attempts, (
        f"the whole transaction was attempted {fired[0]} time(s); spec/errors.md §2.1 "
        f"requires a bounded retry of the WHOLE transaction and the policy bounds it at "
        f"{DEFAULT_POLICY.max_attempts}. One attempt would mean the loop never ran."
    )
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


# ═══════════════════════════════════════════════════════════════════════════════════════
# the persistence check, made to FAIL — R8's control
# ═══════════════════════════════════════════════════════════════════════════════════════


class _KeepsBeatFourAndCommits:
    """A connection that swallows beat 4's savepoint rollback and then commits.

    THE PLANT, shaped by what was measured rather than by what looked plausible. Turning
    ``gate_run``'s final ``rollback()`` into a ``commit()`` **on its own persists nothing** —
    measured on 2026-08-14, ``self_persisted`` stayed ``False`` — because every beat has
    already been undone by its own ``ROLLBACK TO SAVEPOINT`` and the outer transaction has
    nothing left to commit. That is a real and welcome property of the design, and it is why
    a control that only swapped the last rollback would have been a control that could never
    fire. Both halves together are the defect the persistence check exists to catch: the
    demo keeping the admission it just demonstrated.

    Everything else is delegated, so what runs is ``gate_run`` against a real connection.
    """

    def __init__(self, inner: psycopg.Connection[Any]) -> None:
        self._inner = inner
        self.swallowed = 0
        self.rollbacks = 0

    def execute(self, query: Any, params: Any = None, **kwargs: Any) -> Any:
        if isinstance(query, str) and query == "ROLLBACK TO SAVEPOINT gate_run_beat_4":
            self.swallowed += 1
            return None
        return self._inner.execute(query, params, **kwargs)

    def rollback(self) -> None:
        # `gate_run` rolls back four times: a clean slate, after the opening reads, in the
        # `finally` that closes the beats, and after the `after` reading. The third is the
        # one whose whole job is to undo the run, and it is the one replaced here.
        self.rollbacks += 1
        if self.rollbacks == 3:
            self._inner.commit()
        else:
            self._inner.rollback()

    def __getattr__(self, name: str) -> Any:
        return getattr(self._inner, name)


def test_a_run_that_really_persists_is_caught(
    w4_database: str,  # noqa: F811
    fresh_history: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """R8: a verifier that has never failed has never discriminated. This one fails on cue.

    ``gate_run``'s persistence check was rebuilt on 2026-08-14 so that the VERDICT keys on
    ``self_persisted`` — what THIS run left behind — instead of on ``identical``, the ten
    unscoped whole-table counts, which any other caller could move (see
    ``docs/diagnosis/gate-run-fingerprint.md``). A check that stopped being able to fail
    would be a worse outcome than the red it replaced, so it is made to fail here.

    Driven against ``fresh_history`` — a permit minted for this test alone — and never
    against the demo subject: the plant genuinely commits an admission, the transitions are
    irreversible, and a plant pointed at ``PTW-PROOF-1`` would consume the subject every
    other test in this suite drives.
    """
    monkeypatch.setenv("MAINLINE_DEMO_PERMIT_ID", str(fresh_history.permit_id))
    monkeypatch.setenv("MAINLINE_DEMO_SITE_ID", str(fresh_history.site_id))

    connection = psycopg.connect(w4_database, autocommit=False)
    plant = _KeepsBeatFourAndCommits(connection)
    try:
        payload = gate_run_fn(plant)  # type: ignore[arg-type]
    finally:
        connection.close()

    assert plant.swallowed == 1, (
        "beat 4's ROLLBACK TO SAVEPOINT was never issued, so the plant removed nothing and "
        "this control ran against a transaction that was always going to be clean"
    )
    check = payload["persistence_check"]
    assert check["self_persisted"] is True, check["self_evidence"]
    assert check["self_evidence"]["minted_disposition_rows_after_rollback"] == 1, (
        "the disposition beat 4 minted did not survive a committed transaction, so the one "
        "identifier no other writer could have produced is not being read back at all"
    )
    assert (
        check["self_evidence"]["subject_row_counts_before"]
        != (check["self_evidence"]["subject_row_counts_after"])
    )
    assert payload["verdict"] == "NOT PROVEN"
    assert any("PERSISTED something" in line for line in payload["failures"]), payload["failures"]
