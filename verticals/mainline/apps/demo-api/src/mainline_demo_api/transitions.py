# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
"""The six POST resources: four kernel transitions, and the two demo drivers.

ONE ENTRY POINT, and its signature is fixed between this worker and ``w3-api-core-reads``:

    handle_transition(resource_key, path_params, body, conn) -> (http_status, payload)

``payload`` is the **complete response envelope** — ``envelope_version``, ``resource``,
``schema_id``, ``staged``, ``provenance``, ``data`` — not the bare ``data`` member. The
caller serialises it and sends it with ``http_status``; it does not wrap it again. That
split is chosen rather than the other one because ``resource`` and ``schema_id`` are
functions of the resource key, and a second module re-deriving them is a second place for
them to be wrong. If a caller *does* wrap it, the console's schema validation fails loudly
on the next request rather than rendering something plausible, which is the failure mode
worth having.

The four resources are declared in ``verticals/mainline/apps/console/src/data/resources.ts``
and governed by ``contracts/invoke.schema.json``:

======================  ==========================================================
``materialise_checks``  ``POST /v1/permits/{permit_id}/checks:materialise``
``sign_disposition``    ``POST /v1/checks/{check_id}/disposition``
``merge_permit``        ``POST /v1/permits/{permit_id}/merge``
``suspend_permit``      ``POST /v1/permits/{permit_id}/suspend``
======================  ==========================================================

plus the two demo drivers, each governed by a contract this app owns:

====================  ====================================================================
``demo_gate_run``     ``POST /v1/demo/gate-run`` — ``contracts/gate-run.schema.json``
``cr_gate_run``       ``POST /v1/demo/cr-gate-run`` — ``contracts/cr-gate-run.schema.json``
====================  ====================================================================

They are the same claim from both sides: you cannot ISSUE a permit that relies on a clause
a past incident's blame reaches, and you cannot quietly EDIT AWAY that clause either.
**Neither takes a path parameter**, both roll their whole transaction back, and both prove
``persisted: false`` from a fingerprint they measured rather than asserting it. See the
note beside ``cr_gate_run`` in :data:`TRANSITION_RESOURCES` for why the second one's
``(None, None, False)`` shape is a safety decision — ``_demo_guard`` decides on
``subject_id == scenario.permit_id`` and a change-request identifier never equals a permit
identifier, so a MUTATING change-request transition would have walked straight past it.

A REFUSAL IS A NORMAL RESPONSE
------------------------------
Not an exception at the HTTP layer, and not a 500. The database refusing a merge is the
product working, so a refusal comes back as a well-formed envelope whose ``data.outcome``
is ``refused`` and whose ``data.refusal`` is the ``spec/wire`` payload verbatim. The
console's ``transport.ts`` turns exactly that into a ``RefusalError`` carrying the payload;
it never composes a sentence, and neither does this module. Every ``sqlstate``,
``constraint`` and ``message`` here comes out of the driver's error object.

    ==========  ======  ====================================================
    outcome     status  meaning
    ==========  ======  ====================================================
    committed   200     the transition happened
    refused     409     the database refused it, and named what refused
    retry       503     ``40001`` — UNDECIDED. Nothing happened, and nothing
                        was decided. The caller re-attempts, or does not.
    ==========  ======  ====================================================

EVERY POST ON THIS PAGE RETRIES ``40001``, AND ONLY ``40001``
------------------------------------------------------------
``spec/errors.md`` §2.1 is normative and has no carve-out: *"retry the whole transaction,
from BEGIN, never a statement; capped exponential backoff with full jitter; a bounded
attempt count; and a final surfaced refusal when the budget is exhausted."* Each of the
five functions below IS one whole transaction — ``_prepare`` rolls back and states the
isolation level, the work follows, and one ``commit()`` ends it — so one call to one of
them is exactly one attempt, and :func:`handle_transition` runs that call under
:func:`mainline_demo_api.retry.run_transaction`.

**This paragraph used to say the opposite**, and the correction is worth reading rather
than skipping. It said: *"There is no retry helper on the four committing paths and there
will not be one … a helper that re-sent a merge because a socket closed is a helper that
can issue a permit twice."* The hazard in that sentence is real and it is NOT ``40001``.
``40001`` is a transaction the database **aborted**: nothing was written, nothing was
decided, and re-attempting it cannot issue anything twice. The outcome that is genuinely
ambiguous — *"the commit may or may not have landed"* — is ``40003``, and §1.1 lists it as
a **defect** a conformant client MUST NOT treat as a serialization failure.
:func:`mainline_demo_api.retry.classify_for_retry` therefore calls ``40003`` unmodelled and
never retries it. The old paragraph conflated the two codes and, in doing so, denied the
four committing paths the one behaviour the specification requires of them.

What it cost, measured on this tree at ``7535670`` before the repair: a ``40001`` raised by
any statement OUTSIDE an inner ``except psycopg.Error`` — ``_permit_epoch``, ``_prepare``,
``_demo_subject_is_established``, ``resolve_credential_id``, and **every ``conn.commit()``**
— reached :func:`handle_transition`'s last handler, which catches ``psycopg.OperationalError``.
``psycopg.errors.SerializationFailure`` *is* an ``OperationalError`` in psycopg 3.3.4, so
the caller was told ``503 database_unreachable``: a sentence that is false, because the
database answered, and unactionable, because the correct advice for ``40001`` is to attempt
again. Two whole-suite tests failed on it in the same run — ``sign_disposition`` then
``merge_permit`` — and the node id moved between runs while the shape never did.

The four refusal codes are still attempted **exactly once, ever** (§4): a client that
retries a ``23514`` writes five identical refusals for one attempted history.
:func:`~mainline_demo_api.retry.run_transaction` re-raises every decided outcome
unchanged after one attempt, and the once-only property is asserted directly by a spy.

WHEN THE BUDGET IS SPENT, THE ANSWER IS STILL ``503``, AND IT NAMES THE RIGHT CONDITION
---------------------------------------------------------------------------------------
``spec/errors.md`` §5: an undecided transaction has no reason set and MUST NOT be
represented as a refusal. So an exhausted budget surfaces as ``503``/``outcome: retry`` —
the outcome ``contracts/invoke.schema.json`` already declares — when the ``40001`` was
caught by a transition and turned into that envelope, and as a plain
``503 transaction_undecided`` carrying ``sqlstate: "40001"`` when it arrived as an
exception from a statement no transition guards. Neither is ``database_unreachable``, and
neither is a refusal.

``POST /v1/demo/gate-run`` is retried for a second reason on top of the first: it
**persists nothing** — every beat is fenced by a savepoint, the whole transaction is rolled
back, and a fingerprint taken before and after is in the response — and it is the endpoint
two judges press at the same moment.

Client errors — an unknown resource, a malformed identifier, a body that cannot be
honoured, a subject that does not exist — return a status of 4xx and a **plain
``{"error", "detail"}`` object, never an envelope**. That is deliberate: the console's
transport treats a non-2xx body that is not an envelope as a transport failure, which is
the correct diagnosis for "the client asked wrongly". Dressing a client mistake as a gate
refusal would put a fabricated exhibit in front of a reader.

THE DEMO SUBJECT IS WRITE-PROTECTED
-----------------------------------
The seeded demo permit is a shared, public, single-copy resource, and three of the four
transitions above are irreversible on it — a permit cannot be un-merged, and
``dispositioned -> checks_materialised`` would move it out of the state the gate run needs.
One judge pressing one button must not be able to brick the demo for the next. So a
mutating transition aimed at the demo subject is refused with ``423 Locked`` and a plain
error that says which endpoint to use instead, unless ``MAINLINE_DEMO_ALLOW_MUTATION`` is
set. The demo subject is driven through ``POST /v1/demo/gate-run``, which rolls back.

AND THE GUARD FAILS CLOSED WHEN IT CANNOT SAY WHICH SUBJECT THAT IS
-------------------------------------------------------------------
That is the second half, and it is the half a 31-agent audit found missing. The guard's
whole decision is ``subject_id == scenario.permit_id``, and ``scenario.permit_id`` comes
from :func:`mainline_demo_api.scenario.from_env`, which reads ``MAINLINE_DEMO_PERMIT_ID``
and **falls back to a uuid5 derivation nothing has ever seeded**. The demo Function URL
carries ``authorization_type = NONE`` (``infra/envs/demo/main.tf:312``), so an absent
environment variable did not merely misconfigure the guard — it armed it at an identifier
no caller would ever send and left the four committing POSTs above reachable by any
stranger, against a DSN role holding the matching UPDATE and EXECUTE grants.

Measured on 2026-08-13 against a freshly seeded local node, with the variable unset and
every request aimed at the identifier the seed actually minted:

    materialise_checks -> 200   state dispositioned -> checks_materialised, head_seq 2 -> 3,
    sign_disposition   -> 200   open_blocking 1 -> 0, +1 permit_event, +1 disposition,
                                +1 exposure_receipt, +1 exposure_line

— an anonymous caller closing the very obligation the gate proof turns on. Recorded in
``evidence/deploy/demo-guard-armed.json``.

So a comparison is not enough. **A write path that cannot establish which subject is the
protected one refuses instead of permitting.** :func:`_demo_guard` therefore ESTABLISHES the
demo subject — it asks the database whether ``scenario.permit_id`` is a row — before it is
willing to conclude "this is some other subject, let it through". When that row is absent
the deployment cannot say what it is protecting, and every mutating transition is refused
with ``423 demo_subject_unidentified``. That refusal deliberately says a different sentence
from ``demo_subject_write_protected``: asserting that a subject IS the demo subject when the
deployment cannot name the demo subject would be a fabricated exhibit, and this module does
not produce those.

This closes the asymmetry rather than the instance. :func:`scenario.resolve` already refuses
an unseeded history with ``ScenarioNotSeeded`` / ``422 demo_history_not_seeded``, so the READ
path has always known that "the demo history is not here" is a thing it must say out loud;
the WRITE path used to treat the same condition as permission. The same probe also catches a
mistyped override, a deploy pointed at the wrong database and a Lambda whose environment was
edited by hand — one closed class, not four remembered instances.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import os
import uuid
from collections.abc import Iterator, Mapping
from datetime import UTC, datetime
from typing import Any, Final

import psycopg
from psycopg.types.json import Jsonb

from .cr_gate_run import CR_GATE_RUN_SCHEMA_ID, cr_gate_run
from .credentials import resolve_credential_id
from .defeaters import resolve_defeater_vocabulary
from .gate_run import DEMO_DEFEATER_CODE, GATE_RUN_SCHEMA_ID, canonical_json, gate_run
from .refusal import RETRYABLE_SQLSTATE, classify, diagnose, refusal_payload, rfc3339
from .retry import DEFAULT_POLICY, RetryBudgetExhausted, run_transaction
from .scenario import ENV_PREFIX, Scenario, ScenarioNotSeeded, from_env, positional

__all__ = [
    "CONTRACT_BASE",
    "INVOKE_SCHEMA_ID",
    "TRANSITION_RESOURCES",
    "handle_transition",
]

CONTRACT_BASE: Final = "https://console.mainline.trappoint.org/contracts/1.0/"
INVOKE_SCHEMA_ID: Final = f"{CONTRACT_BASE}invoke.schema.json"

#: resource key -> (path parameter, procedure name, mutates the subject).
#: The procedure names are the closed enum ``contracts/invoke.schema.json`` declares; the
#: kernel's API surface is a thin authenticator in front of exactly one server-side
#: procedure per endpoint, and this table is where that correspondence is written down.
TRANSITION_RESOURCES: Final[Mapping[str, tuple[str | None, str | None, bool]]] = {
    "materialise_checks": ("permit_id", "trappoint.materialise_checks", True),
    "sign_disposition": ("check_id", "trappoint.sign_disposition", True),
    "merge_permit": ("permit_id", "trappoint.merge_permit", True),
    "suspend_permit": ("permit_id", "trappoint.suspend_permit", True),
    "demo_gate_run": (None, None, False),
    # ── THE SIXTH, AND ITS SHAPE IS A SAFETY DECISION RATHER THAN A CONVENTION ──────
    #
    # `(None, None, False)`: no path parameter, no kernel procedure, does not mutate. The
    # first of those three is what keeps `_demo_guard` out of the picture, and that is
    # deliberate, because THE GUARD WOULD NOT HAVE HELD.
    #
    # `_demo_guard`'s whole decision is `subject_id == scenario.permit_id`. A change
    # request identifier never equals the permit identifier, so a MUTATING change-request
    # transition would fall past the `demo_subject_write_protected` branch, reach
    # `_demo_subject_is_established`, find the permit IS seeded, and be let through — an
    # unguarded, irreversible, unauthenticated write on the seeded demo change request.
    # That is not hypothetical: it is the exact shape of the defect
    # `evidence/deploy/demo-guard-armed.json` records, one subject over.
    #
    # So there is no committing change-request route, in this wave or by accident, and the
    # guard is NOT widened to prepare for one — widening it now is how the route gets added
    # next week without the argument being had. `cr_gate_run` needs no guard because there
    # is nothing to guard: every write beat is fenced by its own savepoint and the whole
    # transaction is rolled back, which the payload proves rather than asserts.
    "cr_gate_run": (None, None, False),
}

_OK: Final = 200
_REFUSED: Final = 409
_RETRY: Final = 503

#: `mainline.disposition.rationale` carries a length CHECK; the API caps the input before
#: the database does, so an over-long rationale is a 422 the caller can fix rather than a
#: refusal that looks like the gate deciding something.
_RATIONALE_MIN: Final = 120
_RATIONALE_MAX: Final = 4000


# ═══════════════════════════════════════════════════════════════════════════════════════
# envelope
# ═══════════════════════════════════════════════════════════════════════════════════════


def _error(status: int, error: str, detail: str, **extra: Any) -> tuple[int, dict[str, Any]]:
    """Build a client-facing failure. NOT an envelope, on purpose — see the module docstring."""
    return status, {"error": error, "detail": detail, **extra}


def _ref(kind: str, obj: str) -> dict[str, Any]:
    """Name where a payload came from, in ``common.schema.json#/$defs/statement_ref`` shape.

    ``text`` is null: this API does not disclose the statement body. The contract provides
    for that explicitly — *"null when the read API declined to disclose it"* — and naming
    the object without quoting the SQL is a smaller claim than quoting SQL that a later
    edit could make untrue.
    """
    return {"kind": kind, "object": obj, "text": None, "sql_path": None}


def _envelope(
    resource: str,
    schema_id: str,
    data: Any,
    *,
    staged: bool = False,
    staged_note: str | None = None,
    statement_refs: list[dict[str, Any]] | None = None,
    provenance: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    now = datetime.now(UTC)
    return {
        "envelope_version": 1,
        "resource": resource,
        "schema_id": schema_id,
        "observed_at": rfc3339(now),
        # The API process's clock. The console renders server-vs-local skew from it; it is
        # not the cluster's clock, and the two are different facts. Every value in `data`
        # that came from a timestamp column carries the DATABASE's clock instead.
        "server_date": rfc3339(now),
        "staged": staged,
        "staged_note": staged_note,
        "statement_refs": statement_refs or [],
        "provenance": provenance or [],
        "data": data,
    }


def _invoke(
    procedure: str,
    http_status: int,
    outcome: str,
    subject_id: str,
    gate_epoch: int,
    *,
    committed: dict[str, Any] | None = None,
    refusal: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "procedure": procedure,
        "http_status": http_status,
        "outcome": outcome,
        "subject_kind": "permit",
        "subject_id": subject_id,
        "gate_epoch": gate_epoch,
        "committed": committed,
        "refusal": refusal,
        "sql_round_trip": None,
    }


_REFUSAL_PROVENANCE: Final[list[dict[str, str]]] = [
    {"pointer": "/outcome", "chip": "derived"},
    {"pointer": "/gate_epoch", "chip": "db:column"},
    {"pointer": "/refusal/sqlstate", "chip": "db:constraint"},
    {"pointer": "/refusal/constraint", "chip": "db:constraint"},
    {"pointer": "/refusal/message", "chip": "db:constraint"},
    {"pointer": "/refusal/mus", "chip": "db:column"},
    {"pointer": "/refusal/naa", "chip": "derived"},
]

_COMMITTED_PROVENANCE: Final[list[dict[str, str]]] = [
    {"pointer": "/outcome", "chip": "derived"},
    {"pointer": "/gate_epoch", "chip": "db:column"},
    {"pointer": "/committed/merged_commit", "chip": "db:column"},
    {"pointer": "/committed/merged_at", "chip": "db:column"},
    {"pointer": "/committed/clearance_digest", "chip": "db:column"},
]


# ═══════════════════════════════════════════════════════════════════════════════════════
# small helpers
# ═══════════════════════════════════════════════════════════════════════════════════════


def _sha(*parts: bytes | str) -> bytes:
    digest = hashlib.sha256()
    for part in parts:
        digest.update(part.encode("utf-8") if isinstance(part, str) else part)
    return digest.digest()


def _uuid_param(path_params: Mapping[str, Any], name: str) -> uuid.UUID:
    raw = str(path_params.get(name, "")).strip()
    if not raw:
        raise ValueError(f"path parameter {name!r} is required")
    try:
        return uuid.UUID(raw)
    except ValueError as exc:
        raise ValueError(f"path parameter {name!r} is not a UUID: {raw!r}") from exc


def _text(body: Mapping[str, Any], key: str, default: str | None, *, limit: int) -> str:
    value = body.get(key, default)
    if value is None:
        raise ValueError(f"body member {key!r} is required")
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"body member {key!r} must be a non-empty string")
    if len(value) > limit:
        raise ValueError(f"body member {key!r} is longer than {limit} characters")
    return value


@contextlib.contextmanager
def _borrowed(conn: psycopg.Connection[Any]) -> Iterator[psycopg.Connection[Any]]:
    """Clear *conn*'s ``autocommit`` for the length of one request, and hand it back on.

    THE CONNECTION IS BORROWED, NOT OWNED, AND IT IS MODULE-SCOPE. ``db.connection()``
    opens ONE psycopg connection per Lambda execution environment and keeps it: a fresh
    pgwire connection to CockroachDB Cloud in Singapore costs a TLS handshake plus an auth
    round trip — 3.15 s measured from Australia — so a connection per invocation would make
    the demo feel broken. ``db._open`` opens that one connection with ``autocommit=True``,
    and ``health.py`` publishes that fact in prose as the reason the health path is
    structurally incapable of answering 503 on a marker-less database.

    Every transition in this module needs the opposite for the length of its own work: one
    transaction spanning several statements, which means the flag has to come off. Until
    2026-08-13 it came off and never went back on — ``_prepare`` and ``_demo_gate_run`` each
    flipped it on the shared connection and returned — so the guarantee ``health.py``
    documents was silently withdrawn by the first gate run and every request after it
    inherited the withdrawal. Measured on this tree, through ``handle_transition``, against
    a seeded local node: one ``POST /v1/demo/gate-run`` answered 200 and left
    ``conn.autocommit`` ``False``; the next ``SELECT 1`` therefore opened an implicit
    transaction that nothing closed; and ``GET /v1/health`` answered
    ``503 unreachable [25P02] current transaction is aborted, commands ignored until end of
    transaction block``. On the deployed marker-carrying cluster the same leak strands the
    warm connection ``INTRANS`` instead — an idle-in-transaction ``40001`` amplifier that
    the health alarm cannot see, because there the health statement succeeds.

    So the flag is taken and given back in ONE place, and this is that place. It is a
    context manager rather than two hand-rolled ``try``/``finally`` blocks so that the
    clear and the restore cannot drift apart again: there is now exactly one assignment to
    ``conn.autocommit`` in this module, and it is inside the ``finally`` of the only
    function that ever clears it. An early return, a raise, a 423 refusal and a ``40001``
    all leave through the same door.
    """
    borrowed_autocommit = conn.autocommit
    if borrowed_autocommit:
        conn.autocommit = False
    try:
        yield conn
    finally:
        # THE ORDER IS LOAD-BEARING. psycopg refuses to change `autocommit` on a connection
        # whose transaction status is not IDLE — `_check_intrans_gen` raises
        # `ProgrammingError: can't change 'autocommit' now: connection in transaction status
        # INTRANS` — so the rollback is what MAKES the restore possible, not a courtesy
        # beside it. It is also this function's published contract restated: the connection
        # is left with no transaction in progress, whatever happened. `rollback()` on an
        # already-idle connection costs no round trip.
        with contextlib.suppress(psycopg.Error):
            conn.rollback()
        if conn.autocommit != borrowed_autocommit:
            # After that rollback the only way this assignment raises is a connection that
            # is no longer usable — closed, or a socket that died mid-request — and on one
            # of those the flag cannot be inherited by anybody: `db.connection()` proves the
            # cached connection with `SELECT 1` on every acquisition and replaces it when
            # that fails. Raising from here would replace whatever the caller was actually
            # reporting with a bookkeeping complaint about a socket that is already gone.
            # Narrow and named — `psycopg.Error`, never a bare or blanket except.
            with contextlib.suppress(psycopg.Error):
                conn.autocommit = borrowed_autocommit


def _prepare(conn: psycopg.Connection[Any]) -> None:
    """Put *conn* in the one state every transition needs, and say so explicitly.

    ``spec/errors.md`` §2.1: the isolation level is issued by the client on every attempt,
    never inherited from a pool default. A procedure that silently ran at whatever the
    session offered would make the one line of the client that matters unauditable — and
    on a warm Lambda the session is by definition a reused one.

    IT DOES NOT CLEAR ``autocommit``, AND THAT IS THE POINT. :func:`_borrowed` clears it
    once, at the entry point, and gives it back; a second place that cleared it would be a
    second place that could forget to. What is left here is a tripwire rather than a
    branch: under :func:`handle_transition` the flag is already off by the time this runs,
    so the ``raise`` below is unreachable in normal operation and fires only if a future
    caller reaches a transition without borrowing the connection first. That is worth
    reporting loudly, because a transition running in autocommit is not a slower
    transition — it is a different one. ``_materialise_checks`` would commit its exposure
    receipt, then commit each exposure line, and then fail to append the transition event,
    leaving a receipt in the ledger for a transition that never happened. A defect in this
    module reaches the caller as an exception, and it should.
    """
    if conn.autocommit:
        raise RuntimeError(
            "mainline_demo_api.transitions._prepare was handed a connection in autocommit. "
            "Every transition in this module is ONE transaction — the exposure receipt and "
            "its lines and the event that justifies them commit together or not at all — so "
            "the flag must be off before the first statement. transitions._borrowed() is "
            "what clears it, and handle_transition is what enters it. This is a defect in "
            "this module, not a gate refusal, and it is not reported as one."
        )
    conn.rollback()
    conn.execute("SET TRANSACTION ISOLATION LEVEL SERIALIZABLE")


#: The existence question, and nothing else. Not ``resolve()``: that reads eight columns and
#: two subqueries to DESCRIBE the demo history, and a guard that failed because a projection
#: counter disagreed with an anti-join would be refusing writes for a reason that has nothing
#: to do with whether it knows which subject to protect. The only fact this decision needs is
#: whether the identifier the deployment calls the demo subject names a row here.
_DEMO_SUBJECT_SQL: Final = "SELECT 1 FROM mainline.permit WHERE permit_id = %s"


def _mutation_allowed() -> bool:
    """Report whether the operator of THIS deployment has explicitly taken the lock off.

    Read from the environment on every call rather than cached: on a warm Lambda the
    configuration can change between invocations, and a guard that remembered the answer
    from a cold start would be enforcing a policy the deployment has since withdrawn — or,
    worse, one it has since imposed.
    """
    return os.environ.get("MAINLINE_DEMO_ALLOW_MUTATION", "").strip() not in ("", "0", "false")


def _demo_subject_is_established(conn: psycopg.Connection[Any], scenario: Scenario) -> bool:
    """Report whether the subject this deployment calls the demo subject is in this database.

    One row-existence read, joining whatever transaction the caller already has open, so it
    sees the same snapshot as the decision it is about to inform.

    ``OperationalError`` is re-raised rather than answered. "There was nothing to ask" and
    "the gate refused" are different findings and only one of them is about the product —
    the distinction :func:`handle_transition` draws with its ``503 database_unreachable``,
    and dressing an unreachable cluster as a ``423`` would put a refusal in front of a
    reader that nothing refused. Every other driver error IS answered, with ``False``: a
    guard that cannot read ``mainline.permit`` — no such relation, no such grant — has
    established nothing, and the whole point of this function is that establishing nothing
    means refusing.

    ``40001`` LEAVES BY THAT SAME DOOR AND IS NOT ANSWERED EITHER, which used to be an
    accident and is now the point. ``psycopg.errors.SerializationFailure`` is an
    ``OperationalError``, so a serialization restart on this one read propagates instead of
    becoming ``False``. Answering ``False`` would refuse the write with
    ``demo_subject_unidentified`` — a claim that the demo subject is not in this database —
    on the evidence of a transaction the database threw away before it could look. The
    caller of this function runs inside :func:`mainline_demo_api.retry.run_transaction`, so
    what propagation actually buys is a whole re-attempt of the transition, at which point
    the read is asked again and answers for real.
    """
    try:
        row = positional(conn, _DEMO_SUBJECT_SQL, (scenario.permit_id,)).fetchone()
    except psycopg.OperationalError:
        raise
    except psycopg.Error:
        return False
    return row is not None


def _demo_guard(
    conn: psycopg.Connection[Any], subject_id: uuid.UUID, scenario: Scenario
) -> tuple[int, dict[str, Any]] | None:
    """Refuse a mutating transition the demo cannot afford, or ``None`` to let it through.

    THE ORDER OF THE THREE QUESTIONS IS THE DESIGN.

    1. Has this deployment's operator lifted the lock? Then nothing below applies, and no
       statement is issued to decide that.
    2. Is this the demo subject? Then refuse, and say exactly that. This branch touches no
       row: the answer is a comparison of identifiers, which is what makes the refusal
       stateable about a DEPLOYMENT — the guard holds at an identifier whose permit is in
       another database entirely.
    3. Only now, having concluded "some other subject", is the conclusion itself checked.
       It rests entirely on ``scenario.permit_id`` being the right identifier, and that
       value is an environment variable with a fallback nothing seeded, so the conclusion
       is worth exactly as much as the premise. If the demo subject is not in this
       database, the premise is unfounded and the write is refused.

    Step 3 is the whole fix, and it costs one row-existence read on the path that was
    already going to write. Nothing about it is a policy this module invented: the READ path
    has always refused an unseeded history (``ScenarioNotSeeded`` / ``422``) rather than
    guessing, and this is that same rule, finally applied to the path where guessing is
    irreversible.
    """
    if _mutation_allowed():
        return None

    if subject_id == scenario.permit_id:
        return _error(
            423,
            "demo_subject_write_protected",
            "This is the seeded demo subject, and it is a single shared copy that a "
            "hundred judges read. Every transition on this path is irreversible on it — a "
            "permit is never un-merged — so one caller must not be able to brick the demo "
            "for the next. Drive the gate through POST /v1/demo/gate-run, which plays the "
            "same four beats in one transaction and rolls all of it back. Set "
            "MAINLINE_DEMO_ALLOW_MUTATION=1 in a deployment you own to lift this.",
            subject_id=str(subject_id),
            use_instead="POST /v1/demo/gate-run",
        )

    if _demo_subject_is_established(conn, scenario):
        return None

    return _error(
        423,
        "demo_subject_unidentified",
        f"This deployment cannot say which subject its demo protects: it is configured to "
        f"protect {scenario.permit_id}, and no mainline.permit with that identifier is in "
        "this database. The endpoints on this path commit irreversibly and this one is "
        "reachable without authentication, so a guard that cannot name the subject it is "
        "guarding refuses rather than assumes. Nothing was written. Set "
        f"{ENV_PREFIX}PERMIT_ID to the permit this deployment actually seeded — an absent "
        "value falls back to a uuid5 derivation that nothing seeds — or drive the gate "
        "through POST /v1/demo/gate-run, which will report the same missing history as "
        "422 demo_history_not_seeded.",
        subject_id=str(subject_id),
        demo_subject_id=str(scenario.permit_id),
        use_instead="POST /v1/demo/gate-run",
    )


def _permit_epoch(
    conn: psycopg.Connection[Any], permit_id: uuid.UUID
) -> tuple[int, int, str] | None:
    row = positional(
        conn,
        "SELECT gate_epoch, head_seq, state::STRING FROM mainline.permit WHERE permit_id = %s",
        (permit_id,),
    ).fetchone()
    return (int(row[0]), int(row[1]), str(row[2])) if row else None


def _refused(
    conn: psycopg.Connection[Any],
    procedure: str,
    subject_id: uuid.UUID,
    exc: psycopg.Error,
    attempt: dict[str, Any],
) -> tuple[int, dict[str, Any]]:
    """Translate a driver exception into the response the console is written against."""
    conn.rollback()
    found = diagnose(exc)
    kind = classify(found)

    if kind == "retry":
        # UNDECIDED. Not a refusal, and it carries no reason set: `refusal` is null and
        # `spec/wire/refusal.schema.json` excludes 40001 from its sqlstate enum for exactly
        # this reason. The caller decides whether to attempt again.
        anchor = _permit_epoch(conn, subject_id)
        conn.rollback()
        return _RETRY, _envelope(
            _resource_of(procedure),
            INVOKE_SCHEMA_ID,
            _invoke(
                procedure,
                _RETRY,
                "retry",
                str(subject_id),
                anchor[0] if anchor else 0,
            ),
            provenance=[{"pointer": "/outcome", "chip": "derived"}],
        )

    if kind != "refused":
        return _error(
            500,
            "unmodelled_sqlstate",
            f"{found.sqlstate or '(no sqlstate)'}: {found.message}. This code is outside "
            "the refusal taxonomy (23514, 23503, 23505, P0001, 40001, 42501) or carried no "
            "exhibit. spec/errors.md §1.1 makes that a defect to be reported, not an edge "
            "case to be smoothed over, so it is NOT returned as a gate refusal.",
            sqlstate=found.sqlstate or None,
            constraint_source=found.constraint_source,
        )

    anchor = _permit_epoch(conn, subject_id)
    gate_epoch = anchor[0] if anchor else 0
    payload = refusal_payload(
        conn,
        found,
        subject_kind="permit",
        subject_id=str(subject_id),
        gate_epoch=gate_epoch,
        attempt=attempt,
    )
    conn.rollback()
    return _REFUSED, _envelope(
        _resource_of(procedure),
        INVOKE_SCHEMA_ID,
        _invoke(
            procedure,
            _REFUSED,
            "refused",
            str(subject_id),
            int(payload.get("gate_epoch", gate_epoch)),
            refusal=payload,
        ),
        statement_refs=[_ref("procedure", procedure)],
        provenance=_REFUSAL_PROVENANCE,
    )


def _resource_of(procedure: str) -> str:
    for key, (_, proc, _mutates) in TRANSITION_RESOURCES.items():
        if proc == procedure:
            return key
    raise KeyError(procedure)


def _is_undecided(result: tuple[int, dict[str, Any]]) -> bool:
    """Report whether a transition ANSWERED ``40001`` instead of raising it.

    A ``40001`` reaches this module by one of two doors, and both have to be retried or the
    loop covers half the surface. The statement inside a transition's own
    ``except psycopg.Error`` hands it to :func:`_refused`, which classifies it ``retry`` and
    returns the ``503``/``outcome: retry`` envelope — a RETURNED value, not an exception,
    so :func:`~mainline_demo_api.retry.run_transaction` cannot see it without a predicate.
    Every other statement — ``_prepare``, ``_permit_epoch``, the credential and vocabulary
    reads, and every ``commit()`` — raises, which the loop sees by itself.

    The test is both the status AND the outcome, never the status alone: ``503`` is also
    what this module answers for an unreachable database, and re-running a transition
    because the socket is gone would spend the whole budget discovering that four more
    times. ``outcome: retry`` is produced in exactly one place, from
    :func:`mainline_demo_api.refusal.classify` returning ``retry``, which happens for
    ``40001`` and for no other code.
    """
    status, body = result
    if status != _RETRY:
        return False
    data = body.get("data")
    return isinstance(data, dict) and data.get("outcome") == "retry"


# ═══════════════════════════════════════════════════════════════════════════════════════
# merge_permit
# ═══════════════════════════════════════════════════════════════════════════════════════

_MERGE_SQL: Final = "CALL mainline.merge_permit(%s, %s, %s, %s, %s, %s, %s, %s)"


def _merge_permit(
    conn: psycopg.Connection[Any],
    permit_id: uuid.UUID,
    body: Mapping[str, Any],
    scenario: Scenario,
) -> tuple[int, dict[str, Any]]:
    """Call ``mainline.merge_permit``. The money path: refused by name, or committed."""
    procedure = "trappoint.merge_permit"
    merged_by = _text(body, "merged_by", scenario.signer_sub, limit=256)
    actor_kind = _text(body, "actor_kind", "human", limit=32)
    if actor_kind not in ("human", "agent", "service"):
        raise ValueError("body member 'actor_kind' must be one of human, agent, service")

    _prepare(conn)
    anchor = _permit_epoch(conn, permit_id)
    if anchor is None:
        conn.rollback()
        return _error(404, "no_such_permit", f"no mainline.permit with permit_id {permit_id}")
    gate_epoch, _head, _state = anchor

    payload = {"permit": str(permit_id), "merged_by": merged_by, "source": "POST /v1/permits/merge"}
    canon, _impl = canonical_json(payload)
    leaf = hashlib.sha256(b"\x00" + canon).digest()

    try:
        conn.execute(
            _MERGE_SQL,
            (
                permit_id,
                scenario.merged_commit,
                merged_by,
                actor_kind,
                Jsonb(payload),
                canon,
                1,
                leaf,
            ),
        )
    except psycopg.Error as exc:
        return _refused(
            conn, procedure, permit_id, exc, {"kind": "merge", "gate_epoch": gate_epoch}
        )

    # By POSITION, and it has to be: CockroachDB names both `encode(...)` columns `encode`,
    # so a dict row would keep three of these four values and drop one silently.
    record = positional(
        conn,
        "SELECT encode(merged_commit, 'hex'), merged_at, encode(clearance_digest, 'hex'), "
        "gate_epoch FROM mainline.merge_record WHERE subject_id = %s",
        (permit_id,),
    ).fetchone()
    conn.commit()

    committed = {
        "merged_commit": record[0] if record else scenario.merged_commit.hex(),
        "merged_at": (record[1].astimezone(UTC).isoformat() if record else rfc3339()),
        "clearance_digest": record[2] if record else None,
        "checkpoint_tree_size": None,
        "ledger_seq": None,
    }
    return _OK, _envelope(
        "merge_permit",
        INVOKE_SCHEMA_ID,
        _invoke(
            procedure,
            _OK,
            "committed",
            str(permit_id),
            int(record[3]) if record else gate_epoch,
            committed=committed,
        ),
        statement_refs=[
            _ref("procedure", "mainline.merge_permit"),
            _ref("table", "mainline.merge_record"),
        ],
        provenance=_COMMITTED_PROVENANCE,
    )


# ═══════════════════════════════════════════════════════════════════════════════════════
# suspend_permit
# ═══════════════════════════════════════════════════════════════════════════════════════

_APPEND_EVENT_SQL: Final = """
INSERT INTO mainline.permit_event
       (permit_id, seq, prev_seq, from_state, to_state, subject_kind, actor_sub, payload,
        prev_digest)
VALUES (%s, %s, %s, %s, %s, 'permit', %s, %s,
        coalesce((SELECT e.chain_digest FROM mainline.permit_event e
                   WHERE e.permit_id = %s AND e.seq = %s),
                 decode(repeat('00', 32), 'hex')))
"""

_ZERO32: Final = b"\x00" * 32


def _append_transition(
    conn: psycopg.Connection[Any],
    permit_id: uuid.UUID,
    from_state: str,
    to_state: str,
    actor_sub: str,
    payload: dict[str, Any],
    head: int,
) -> None:
    """Append one event and move the head.

    Two mechanisms, both the database's, neither of them a branch in this file:

    * **The legal edge set is DATA.** ``CONSTRAINT legal_edge`` points at
      ``mainline.subject_transition``, so an illegal transition is ``23503`` against a row
      that is not there. A later commit can delete an ``if`` statement; it cannot delete a
      foreign key without a migration.
    * **The compare-and-swap is the INSERT.** ``CONSTRAINT linear UNIQUE (permit_id,
      prev_seq)`` means two writers that both read head ``n`` cannot both append after it —
      the second gets ``23505``. The chain is a chain, not a tree, and it is the table that
      says so.

    The UPDATE that follows carries the same predicate purely as a belt: inside one
    SERIALIZABLE transaction that has already inserted at ``prev_seq = head``, a zero-row
    result is unreachable, so it is reported as the defect it would be rather than dressed
    up as a refusal the gate did not make.
    """
    conn.execute(
        _APPEND_EVENT_SQL,
        (
            permit_id,
            head + 1,
            head,
            from_state,
            to_state,
            actor_sub,
            Jsonb(payload),
            permit_id,
            head,
        ),
    )
    moved = positional(
        conn,
        "UPDATE mainline.permit SET state = %s, head_seq = %s "
        "WHERE permit_id = %s AND head_seq = %s RETURNING head_seq",
        (to_state, head + 1, permit_id, head),
    ).fetchone()
    if moved is None:
        raise RuntimeError(
            f"mainline.permit {permit_id} head moved from {head} inside a SERIALIZABLE "
            "transaction that had already appended at that sequence — which CONSTRAINT "
            "linear makes unreachable. This is a defect in mainline_demo_api.transitions, "
            "not a gate refusal, and it is not reported as one."
        )


def _suspend_permit(
    conn: psycopg.Connection[Any],
    permit_id: uuid.UUID,
    body: Mapping[str, Any],
    scenario: Scenario,
) -> tuple[int, dict[str, Any]]:
    """Suspend an issued permit — the declared path when a new precursor arrives.

    Suspend and fork; never rewrite. ``merged -> suspended`` is the only legal inbound edge
    (``0017b``), so calling this on a permit that has not merged is refused by ``23503`` on
    ``legal_edge`` — which is the state machine defending itself with data, and is worth
    seeing.
    """
    procedure = "trappoint.suspend_permit"
    actor_sub = _text(body, "actor_sub", scenario.signer_sub, limit=256)
    reason = _text(body, "reason", "a precursor arrived after issue", limit=512)

    _prepare(conn)
    anchor = _permit_epoch(conn, permit_id)
    if anchor is None:
        conn.rollback()
        return _error(404, "no_such_permit", f"no mainline.permit with permit_id {permit_id}")
    gate_epoch, head, state = anchor

    try:
        _append_transition(
            conn,
            permit_id,
            state,
            "suspended",
            actor_sub,
            {"reason": reason, "source": "POST /v1/permits/suspend"},
            head,
        )
    except psycopg.Error as exc:
        return _refused(
            conn, procedure, permit_id, exc, {"kind": "suspend", "gate_epoch": gate_epoch}
        )
    conn.commit()

    return _OK, _envelope(
        "suspend_permit",
        INVOKE_SCHEMA_ID,
        _invoke(procedure, _OK, "committed", str(permit_id), gate_epoch),
        statement_refs=[
            _ref("table", "mainline.permit_event"),
            _ref("table", "mainline.subject_transition"),
        ],
        provenance=[
            {"pointer": "/outcome", "chip": "derived"},
            {"pointer": "/gate_epoch", "chip": "db:column"},
        ],
    )


# ═══════════════════════════════════════════════════════════════════════════════════════
# materialise_checks
# ═══════════════════════════════════════════════════════════════════════════════════════

_RECALL_SQL: Final = """
SELECT s.silence_receipt_id, s.policy_version, s.corpus_root
  FROM mainline_meas.silence_receipt s
 WHERE s.permit_id = %s
 ORDER BY s.silence_receipt_id
 LIMIT 1
"""

_OPEN_CHECKS_SQL: Final = """
SELECT bc.check_id
  FROM mainline.blocking_check bc
 WHERE bc.permit_id = %s
 ORDER BY bc.check_id
"""

_RECEIPT_SQL: Final = """
INSERT INTO mainline.exposure_receipt
       (receipt_id, subject_kind, permit_id, actor_sub, issued_at, issued_hlc, expires_at,
        corpus_root, silence_receipt_id, policy_version, total_tokens, receipt_digest)
VALUES (%s, 'permit', %s, %s, now(), cluster_logical_timestamp(),
        now() + INTERVAL '2 hours', %s, %s, %s, %s, %s)
"""


def _materialise_checks(
    conn: psycopg.Connection[Any],
    permit_id: uuid.UUID,
    body: Mapping[str, Any],
    scenario: Scenario,
) -> tuple[int, dict[str, Any]]:
    """Issue the exposure receipt over the subject's obligations, in ONE transaction.

    What this endpoint does NOT do is invent obligations. ``mainline.blocking_check`` rows
    are written by the recall pass — ``mainline_meas.recall_run`` and the projection
    triggers behind it — and no HTTP request in this app is going to conjure a precursor
    that no recall found. What it materialises is the half a client is entitled to ask for:
    the **exposure receipt**, which records what was actually shown, to whom and when, plus
    one ``exposure_line`` per obligation, and then the ``checks_materialised`` transition on
    the subject's own event chain.

    That is a real, complete transition and it is also the honest one. A permit with no
    Proof-of-Exhausted-Recall receipt behind it cannot be given an exposure receipt at all —
    the composite foreign key says so — and this returns ``422`` naming the missing row
    rather than fabricating one, because a fabricated silence receipt is a claim that the
    corpus was searched when it was not.
    """
    procedure = "trappoint.materialise_checks"
    actor_sub = _text(body, "actor_sub", scenario.signer_sub, limit=256)

    _prepare(conn)
    anchor = _permit_epoch(conn, permit_id)
    if anchor is None:
        conn.rollback()
        return _error(404, "no_such_permit", f"no mainline.permit with permit_id {permit_id}")
    gate_epoch, head, state = anchor

    recall = positional(conn, _RECALL_SQL, (permit_id,)).fetchone()
    if recall is None:
        conn.rollback()
        return _error(
            422,
            "no_silence_receipt",
            f"permit {permit_id} has no mainline_meas.silence_receipt, so no exposure "
            "receipt can be issued against it. A silence receipt is the Proof of Exhausted "
            "Recall the recall pass leaves behind; this API does not manufacture one, "
            "because a manufactured one asserts that a corpus was searched when it was not.",
        )
    silence_receipt_id, policy_version, corpus_root = recall

    checks = [row[0] for row in positional(conn, _OPEN_CHECKS_SQL, (permit_id,)).fetchall()]
    receipt_id = uuid.uuid4()
    tokens_each = 200
    digest = _sha(
        "exposure",
        str(receipt_id),
        json.dumps([str(c) for c in checks], separators=(",", ":")),
    )

    try:
        conn.execute(
            _RECEIPT_SQL,
            (
                receipt_id,
                permit_id,
                actor_sub,
                corpus_root,
                silence_receipt_id,
                policy_version,
                tokens_each * len(checks),
                digest,
            ),
        )
        for check_id in checks:
            conn.execute(
                "INSERT INTO mainline.exposure_line (receipt_id, check_id, payload_digest, "
                "tokens) VALUES (%s, %s, %s, %s)",
                (receipt_id, check_id, _sha("line", str(check_id)), tokens_each),
            )
        _append_transition(
            conn,
            permit_id,
            state,
            "checks_materialised",
            actor_sub,
            {
                "receipt_id": str(receipt_id),
                "obligations": len(checks),
                "source": "POST /v1/permits/checks:materialise",
            },
            head,
        )
    except psycopg.Error as exc:
        return _refused(
            conn, procedure, permit_id, exc, {"kind": "materialise", "gate_epoch": gate_epoch}
        )

    after = _permit_epoch(conn, permit_id)
    conn.commit()

    return _OK, _envelope(
        "materialise_checks",
        INVOKE_SCHEMA_ID,
        _invoke(procedure, _OK, "committed", str(permit_id), after[0] if after else gate_epoch),
        statement_refs=[
            _ref("table", "mainline.exposure_receipt"),
            _ref("table", "mainline.exposure_line"),
            _ref("table", "mainline.permit_event"),
        ],
        provenance=[
            {"pointer": "/outcome", "chip": "derived"},
            {"pointer": "/gate_epoch", "chip": "db:column"},
        ],
    )


# ═══════════════════════════════════════════════════════════════════════════════════════
# sign_disposition
# ═══════════════════════════════════════════════════════════════════════════════════════

_CHECK_SQL: Final = """
SELECT bc.permit_id, bc.site_id, p.gate_epoch,
       (SELECT r.receipt_id
          FROM mainline.exposure_receipt r
          JOIN mainline.exposure_line l ON l.receipt_id = r.receipt_id
         WHERE l.check_id = bc.check_id AND r.expires_at > now()
         ORDER BY r.issued_at DESC LIMIT 1)
  FROM mainline.blocking_check bc
  JOIN mainline.permit p ON p.permit_id = bc.permit_id
 WHERE bc.check_id = %s
"""

_SIGN_SQL: Final = """
INSERT INTO mainline.disposition (
  disposition_id, check_id, receipt_id, subject_kind, permit_id, site_id, kind, virulence,
  closure_gen, defeater_code, defeater_vocab_sha256, rationale, evidence_sha256, signer_sub,
  signer_rank, signer_org, signer_credential_id, countersigner_sub,
  countersigner_credential_id, signature_alg, authenticator_data, client_data_json,
  user_verified, competency_snapshot, competency_source_id, competency_sha256,
  req_compensating, req_second_signer, req_foreign_org, req_predicate, req_reassert,
  min_signer_rank, severity_snapshot, deliberation_seconds, evidence_opened,
  prior_override_count)
VALUES (%s, %s, %s, 'permit', %s, %s, %s, 'routine', 0, %s, %s, %s, %s, %s, 1, 'x', %s, %s,
        %s, 'ES256', %s, %s, true, %s, %s, %s, false, false, false, false, false, 1, 0, 0,
        true, 0)
"""

#: `mainline.disposition_kind`, migration 0012. Which of these is LEGAL for a given
#: obligation is decided by `mainline.clearance_legal` and enforced by the composite
#: foreign key `fk_clearance` — not by this list. Membership here only stops a typo from
#: reaching the database as an enum cast error, which would be a 22P02 nobody modelled
#: rather than the 23503 the lattice is entitled to raise.
_DISPOSITION_KINDS: Final[frozenset[str]] = frozenset(
    {
        "applied",
        "mitigated",
        "mechanism_absent",
        "escalated",
        "accept_residual",
        "emergency_override",
    }
)


def _sign_disposition(
    conn: psycopg.Connection[Any],
    check_id: uuid.UUID,
    body: Mapping[str, Any],
    scenario: Scenario,
) -> tuple[int, dict[str, Any]]:
    """One signature, against a clearance-lattice row that must already exist.

    Almost every column on the inserted row is PROJECTED by ``fn_disposition_project`` from
    authoritative rows and the values supplied here do not survive the write (invariant
    I02): the subject, the site, the virulence, the clearance requirements, the signer's
    rank and organisation, the competency snapshot and the reading-floor verdict are all
    read from elsewhere. What a signer actually chooses is the KIND, the defeater code, the
    rationale and the signature — and those four are what this endpoint takes.

    THE DEFEATER IS NOT PART OF WHAT IS STAGED. The code the caller names is checked for
    membership of ``mainline.defeater_option``, and the digest recorded beside it is READ
    from those rows rather than computed — so ``defeater_vocab_sha256`` on the resulting
    row pins the option set this check actually offered, which is the whole claim 0064 and
    ``disposition.schema.json`` make about that column and the one this endpoint used to
    make falsely.

    STAGED, and the envelope says so. The WebAuthn assertion is synthesised here: this demo
    has no authenticator, and the database does not verify signatures on this path. That is
    hand-authored demonstration material inside an otherwise live transition, which is
    exactly what ``envelope.staged`` exists to declare.

    Raises:
        DefeaterVocabularyAbsent: this check offers no defeater options, so a signature
            cannot pin one. A ``ScenarioNotSeeded``, which :func:`handle_transition`
            answers with ``422 demo_history_not_seeded``.
        DefeaterVocabularyAmbiguous: the check's options carry several distinct digests.
        DefeaterNotOffered: the ``defeater_code`` in the body is not one of them. A
            ``ValueError``, which :func:`handle_transition` answers with ``422
            unprocessable_request`` naming the codes that ARE offered.
    """
    procedure = "trappoint.sign_disposition"
    kind = _text(body, "kind", "applied", limit=64)
    if kind not in _DISPOSITION_KINDS:
        raise ValueError(
            f"body member 'kind' must be one of {sorted(_DISPOSITION_KINDS)}; got {kind!r}"
        )
    # The DEFAULT is the demo's own authored choice, imported rather than re-typed so that
    # this endpoint and beat 4 cannot come to disagree about which defeater the demo names.
    # It is a default and not a guarantee: whatever the caller sends, or does not send, is
    # checked against the vocabulary the database offers before the INSERT below.
    defeater_code = _text(body, "defeater_code", DEMO_DEFEATER_CODE, limit=128)
    rationale = _text(body, "rationale", None, limit=_RATIONALE_MAX)
    if len(rationale) < _RATIONALE_MIN:
        raise ValueError(
            f"body member 'rationale' is {len(rationale)} characters; the disposition "
            f"table requires a substantive one and this API asks for at least "
            f"{_RATIONALE_MIN}. A one-word clearance is not a clearance."
        )
    signer_sub = _text(body, "signer_sub", scenario.signer_sub, limit=256)
    countersigner_sub = _text(body, "countersigner_sub", scenario.countersigner_sub, limit=256)

    # THE TWIN, closed 2026-08-13. `gate_run` was corrected to RESOLVE these two ids from
    # `mainline.signing_credential` rather than derive them, because `_sha("cred","signer")`
    # is `487adc50…` while `demo_world.sql` enrols `digest('mainline-demo/credential/…')` =
    # `ff356d14…`, and beat 4 therefore failed `23503 disposition_signer_credential_id_fkey`
    # against the database that actually deploys. THIS path was not corrected with it, and
    # `test_credentials.py`'s ratchet only watches `gate_run.py` — so the identical defect
    # survived here, on the endpoint a judge reaches by signing a disposition directly.
    # That is the recurring shape once more: the instance was closed, the CLASS was not.
    #
    # Resolved BEFORE `_prepare` opens the transaction, for the reason gate_run.py:452-455
    # records: resolving after would turn "this subject has no enrolled credential" into a
    # foreign-key violation caught downstream and reported as though the GATE had refused.
    # It had not. `CredentialUnresolvable` is a `ScenarioNotSeeded`, which this module's
    # handler already answers as `422 demo_history_not_seeded` — a typed refusal naming the
    # subject and the table, which is what an unseeded database actually deserves.
    signer_credential_id = resolve_credential_id(conn, signer_sub)
    countersigner_credential_id = resolve_credential_id(conn, countersigner_sub)

    _prepare(conn)
    found = positional(conn, _CHECK_SQL, (check_id,)).fetchone()
    if found is None:
        conn.rollback()
        return _error(404, "no_such_check", f"no mainline.blocking_check with check_id {check_id}")
    permit_id, site_id, gate_epoch, receipt_id = found

    guard = _demo_guard(conn, permit_id, scenario)
    if guard is not None:
        conn.rollback()
        return guard

    if receipt_id is None:
        conn.rollback()
        return _error(
            422,
            "no_live_exposure_receipt",
            f"obligation {check_id} is covered by no unexpired mainline.exposure_receipt. "
            "A disposition's composite foreign key lands on (check_id, receipt_id): a "
            "signature may only cite a receipt that actually SHOWED the signer this "
            "obligation. Call POST /v1/permits/{permit_id}/checks:materialise first.",
            permit_id=str(permit_id),
        )

    # THE VOCABULARY THIS SIGNATURE PINS, AND WHETHER IT CONTAINS THE CODE THE CALLER SENT.
    #
    # `defeater_vocab_sha256` used to be `_sha("defeater-vocab")` here and in `gate_run` —
    # `sha256(b"defeater-vocab")`, the digest of an ASCII string, which the deployed Cloud
    # duly recorded on its one signed disposition. 0064 says the column "digests the whole
    # option set, not the row, so a signature that pins it pins the ALTERNATIVES the signer
    # declined"; `disposition.schema.json` says "a later regeneration cannot silently
    # reinterpret a past signature". A constant makes both sentences false, and it makes
    # them false silently, because nothing recomputes the digest to notice.
    #
    # The membership check beside it is the foreign key `mainline.disposition` does not
    # have: `0066_disposition.sql` constrains `defeater_code` only with
    # `disposition_defeater_code_stated CHECK (defeater_code <> '')`, so a code no screen
    # ever offered reaches the row unopposed. RULING R9 forbids adding the FK four days
    # from a deadline — migrations are rendered under a `trappoint render --check` zero-diff
    # assertion and a new constraint moves migrations.lock.json, the schema fingerprint and
    # the parity gate — so it is closed here, in the one place that can close it, and
    # recorded as a finding rather than left unwritten.
    #
    # Resolved AFTER the check has been found, unlike the credentials above: an unknown
    # check_id must stay a `404 no_such_check`, and a vocabulary read placed earlier would
    # answer a nonexistent obligation with "this check offers no defeater vocabulary" —
    # true, useless, and a worse diagnosis than the one it displaced. Nothing has been
    # written at this point, so raising here costs a rollback of two reads.
    vocabulary = resolve_defeater_vocabulary(conn, check_id)
    vocabulary.require(defeater_code)

    disposition_id = uuid.uuid4()
    try:
        conn.execute(
            _SIGN_SQL,
            (
                disposition_id,
                check_id,
                receipt_id,
                permit_id,
                site_id,
                kind,
                defeater_code,
                vocabulary.vocab_sha256,
                rationale,
                _sha("evidence", str(disposition_id)),
                signer_sub,
                signer_credential_id,
                countersigner_sub,
                countersigner_credential_id,
                _sha("authenticator", str(disposition_id)),
                canonical_json({"challenge": disposition_id.hex, "type": "webauthn.get"})[0],
                Jsonb({"authorisations": ["ISOLATION_AUTHORITY"]}),
                uuid.uuid4(),
                _sha("competency", signer_sub),
            ),
        )
    except psycopg.Error as exc:
        return _refused(
            conn,
            procedure,
            permit_id,
            exc,
            {"kind": kind, "check_id": str(check_id), "gate_epoch": int(gate_epoch)},
        )

    after = _permit_epoch(conn, permit_id)
    conn.commit()

    return _OK, _envelope(
        "sign_disposition",
        INVOKE_SCHEMA_ID,
        _invoke(
            procedure,
            _OK,
            "committed",
            str(permit_id),
            after[0] if after else int(gate_epoch),
        ),
        staged=True,
        staged_note=(
            "The WebAuthn assertion on this disposition is synthesised by the demo API: "
            "authenticator_data, client_data_json and the credential identifiers are "
            "generated, not produced by a security key, and nothing in this schema "
            "verifies a signature. Every other column on the row — the subject, the site, "
            "the virulence, the clearance requirements, the signer's rank and "
            "organisation, the competency snapshot and the reading-floor verdict — is "
            "projected by fn_disposition_project from authoritative rows and is real."
        ),
        statement_refs=[
            _ref("table", "mainline.disposition"),
            _ref("table", "mainline.clearance_legal"),
        ],
        provenance=[
            {"pointer": "/outcome", "chip": "derived"},
            {"pointer": "/gate_epoch", "chip": "db:column"},
        ],
    )


# ═══════════════════════════════════════════════════════════════════════════════════════
# the demo driver
# ═══════════════════════════════════════════════════════════════════════════════════════


def _demo_gate_run(
    conn: psycopg.Connection[Any], body: Mapping[str, Any], scenario: Scenario
) -> tuple[int, dict[str, Any]]:
    """Play the four beats and roll them back, inside the caller's borrowed connection.

    ``gate_run`` refuses a connection in autocommit — the four beats sharing ONE
    transaction is the property the demo exists to show — and this function used to buy
    that by clearing the flag itself and never putting it back. :func:`_borrowed` now owns
    both halves of that trade, so there is nothing to clear here and, more importantly,
    nothing to forget to restore.

    AND THIS IS WHERE ``40001`` IS RETRIED. ``spec/errors.md`` §2.1 requires the retried
    unit to be the whole transaction from ``BEGIN``, and one call to ``gate_run`` is
    exactly one whole transaction: it rolls back whatever it was handed, opens its own,
    plays four beats and rolls all of it back again. So the retry belongs HERE, around the
    call, and not inside ``gate_run`` around a statement — a statement replayed into a
    poisoned transaction is not a retry of anything.

    Re-running is safe because the run PERSISTS NOTHING, which is a property the payload
    proves rather than asserts: a second attempt asks the same question of the same rows.
    That used to be stated as the reason this endpoint may be retried *while the four
    committing transitions may not*. It is not that reason — it is a second, independent
    one. The four commit, and they are retried too, because a ``40001`` is a transaction
    the database aborted and re-attempting an aborted transaction is what
    ``spec/errors.md`` §2.1 requires of every one of them; see this module's docstring for
    the code that IS ambiguous and is therefore never retried.

    ``gate_run`` reports ``40001`` in its payload instead of raising, because it has to
    return the beats that DID complete, so the undecided outcome is recognised by a
    predicate on the result rather than by an exception. When the budget is spent the last
    payload is returned as it stands and this function answers ``503`` from it — the run's
    own account of what happened, which is more than a raised exception could say.
    """
    run_id = body.get("run_id")
    if run_id is not None and not isinstance(run_id, str):
        raise ValueError("body member 'run_id' must be a string when supplied")
    try:
        payload = run_transaction(
            lambda: gate_run(conn, scenario, run_id=run_id),
            undecided=lambda result: bool(result["outcome"] == "retry"),
        )
    except RetryBudgetExhausted as exhausted:
        # A ``40001`` that escaped the beats entirely — from `resolve`, from the
        # fingerprint, from the logical-clock read — and survived the budget. There is no
        # payload to surface, so the honest thing to hand on is the DATABASE's own last
        # error rather than a second exhaustion type this module would have to learn:
        # `handle_transition` already has exactly one place that turns a driver error into
        # a response, and a caller's answer must not depend on how many times the loop
        # tried before giving up. `run_transaction` chains the exhaustion from that error
        # for this purpose. The result is the answer an unretried 40001 produced before
        # this loop existed, after the retries `spec/errors.md` §2.1 requires.
        cause = exhausted.__cause__
        if isinstance(cause, psycopg.Error):
            raise cause from exhausted
        raise
    status = _RETRY if payload["outcome"] == "retry" else _OK
    return status, _envelope(
        "demo_gate_run",
        GATE_RUN_SCHEMA_ID,
        payload,
        statement_refs=[
            _ref("procedure", "mainline.merge_permit"),
            _ref("procedure", "trappoint.explain_refusal"),
            _ref("table", "mainline.permit"),
            _ref("table", "mainline.disposition"),
            _ref("table", "mainline.merge_record"),
        ],
        provenance=[
            {"pointer": "/verdict", "chip": "derived"},
            {"pointer": "/subject/open_blocking", "chip": "db:column"},
            {"pointer": "/subject/open_blocking_derived", "chip": "recomputed"},
            {"pointer": "/beats/1/sqlstate", "chip": "db:constraint"},
            {"pointer": "/beats/1/constraint", "chip": "db:constraint"},
            {"pointer": "/beats/2/sqlstate", "chip": "db:constraint"},
            {"pointer": "/beats/2/constraint", "chip": "db:constraint"},
            {"pointer": "/beats/3/observed/merge_record/clearance_digest", "chip": "db:column"},
            {"pointer": "/persistence_check/identical", "chip": "recomputed"},
            # The field the VERDICT keys on since 2026-08-14. `identical` is the ten
            # unscoped counts and is a statement about the database; this one is the
            # statement about the run, and a provenance list that named only the first
            # would point a reader at the reading the verdict is no longer read off.
            {"pointer": "/persistence_check/self_persisted", "chip": "recomputed"},
        ],
    )


def _demo_cr_gate_run(
    conn: psycopg.Connection[Any], body: Mapping[str, Any], scenario: Scenario
) -> tuple[int, dict[str, Any]]:
    """Play the three change-request beats and roll them back. The mirror of the above.

    Same borrow, same retry, same reason: one call to :func:`cr_gate_run` is exactly one
    whole transaction — it rolls back whatever it was handed, opens its own, plays the
    beats and rolls all of it back — so ``spec/errors.md`` §2.1's retried unit is the call,
    not a statement inside it.

    WHAT IT DOES NOT SHARE WITH ``demo_gate_run`` IS ITS ``statement_refs``, and the
    difference is the exhibit. This run never calls ``mainline.merge_change_request``: as
    the role a Function URL carrying ``authorization_type = NONE`` executes as, that
    procedure answers ``42501`` on ``mainline.cr_event`` rather than reaching the gate at
    all — measured, and stated in the payload as ``kernel_procedure_absent_sqlstate``. What
    the beats name instead is the TABLE and what is welded to it, because that is what
    actually refuses: the ``CHECK`` and the trigger function meet a caller who skipped the
    procedure exactly as they meet one who did not.
    """
    run_id = body.get("run_id")
    if run_id is not None and not isinstance(run_id, str):
        raise ValueError("body member 'run_id' must be a string when supplied")
    try:
        payload = run_transaction(
            lambda: cr_gate_run(conn, scenario, run_id=run_id),
            undecided=lambda result: bool(result["outcome"] == "retry"),
        )
    except RetryBudgetExhausted as exhausted:
        # Hand on the DATABASE's own last error rather than a second exhaustion type —
        # `_demo_gate_run` does the same thing for the same reason, recorded there.
        cause = exhausted.__cause__
        if isinstance(cause, psycopg.Error):
            raise cause from exhausted
        raise
    status = _RETRY if payload["outcome"] == "retry" else _OK
    return status, _envelope(
        "cr_gate_run",
        CR_GATE_RUN_SCHEMA_ID,
        payload,
        statement_refs=[
            _ref("table", "mainline.change_request"),
            _ref("procedure", "trappoint.explain_refusal"),
            _ref("table", "mainline.blocking_check"),
            _ref("table", "mainline.defeater_option"),
            _ref("view", "pg_catalog.pg_constraint"),
        ],
        provenance=[
            {"pointer": "/verdict", "chip": "derived"},
            {"pointer": "/subject/open_blocking", "chip": "db:column"},
            {"pointer": "/subject/open_blocking_derived", "chip": "recomputed"},
            {"pointer": "/subject/severity", "chip": "db:column"},
            {"pointer": "/subject/virulence", "chip": "db:column"},
            {"pointer": "/beats/0/observed/named_checks", "chip": "db:constraint"},
            {"pointer": "/beats/1/sqlstate", "chip": "db:constraint"},
            {"pointer": "/beats/1/constraint", "chip": "db:constraint"},
            {"pointer": "/beats/2/sqlstate", "chip": "db:constraint"},
            {"pointer": "/beats/2/constraint", "chip": "db:constraint"},
            {"pointer": "/persistence_check/identical", "chip": "recomputed"},
            # The field the VERDICT keys on, named for the same reason it is named on
            # `demo_gate_run`: `identical` is the ten unscoped counts and is a statement
            # about the database, and a provenance list naming only that one would point a
            # reader at the reading the verdict is not read off.
            {"pointer": "/persistence_check/self_persisted", "chip": "recomputed"},
            # NOT chipped `db:column` and not chipped at all by accident: these two are the
            # API's own words about why a beat is absent. `common.schema.json` says an
            # unclaimed provenance is better than a comfortable default, and there is no
            # chip for "a sentence we wrote about a grant row".
            {"pointer": "/kernel_procedure_absent_sqlstate", "chip": "derived"},
        ],
    )


# ═══════════════════════════════════════════════════════════════════════════════════════
# the entry point
# ═══════════════════════════════════════════════════════════════════════════════════════


def handle_transition(  # noqa: PLR0911 — one return per outcome; a shared exit would
    # have to reconstruct which of them it was, and that reconstruction is the bug.
    resource_key: str,
    path_params: Mapping[str, Any],
    body: Mapping[str, Any] | None,
    conn: psycopg.Connection[Any],
) -> tuple[int, dict[str, Any]]:
    """Perform one POST resource and return ``(http_status, response_payload)``.

    Args:
        resource_key: a key from :data:`TRANSITION_RESOURCES`. Anything else is 404.
        path_params: the interpolated path parameters, e.g. ``{"permit_id": "..."}``.
        body: the decoded JSON body, or ``None`` for an empty one.
        conn: a psycopg connection this function BORROWS for the duration of the call. It
            is left with no transaction in progress and with its ``autocommit`` flag as it
            arrived, whatever happened — see :func:`_borrowed` for why the second half of
            that sentence had to be written down and enforced rather than assumed.

    Returns:
        ``(status, payload)``. For the five known resources with a well-formed request the
        payload is a COMPLETE response envelope; for a client error it is a plain
        ``{"error", "detail"}`` object. See the module docstring for why those differ.

    This function does not raise for anything a caller can cause. A caller error is a
    status and a body; only a defect in this module reaches the caller as an exception,
    and it should.
    """
    if resource_key not in TRANSITION_RESOURCES:
        # Nothing below has touched the connection, so there is nothing to borrow or hand
        # back: an unknown resource key is decided entirely out of `TRANSITION_RESOURCES`.
        return _error(
            404,
            "unknown_resource",
            f"{resource_key!r} is not a transition resource. Declared: "
            f"{', '.join(sorted(TRANSITION_RESOURCES))}.",
        )

    payload = dict(body or {})
    scenario = from_env()
    param_name, _procedure, mutates = TRANSITION_RESOURCES[resource_key]

    # THE BORROW, AND THE ONLY ONE. Everything below runs with `autocommit` off because
    # every transition here is one transaction; `_borrowed` puts the flag back on the way
    # out of every one of the returns and raises inside it.
    with _borrowed(conn):
        try:
            # THE TWO DEMO DRIVERS, BOTH BEFORE THE PARAMETER BRANCH. Neither takes a path
            # parameter, so neither reaches `_uuid_param` and neither is ever handed to
            # `_demo_guard` — see the note beside `cr_gate_run` in TRANSITION_RESOURCES for
            # why that is the safety property and not merely the shape.
            if resource_key == "cr_gate_run":
                return _demo_cr_gate_run(conn, payload, scenario)
            if resource_key == "demo_gate_run" or param_name is None:
                return _demo_gate_run(conn, payload, scenario)

            subject = _uuid_param(path_params, param_name)

            def attempt() -> tuple[int, dict[str, Any]]:
                """ONE WHOLE ATTEMPT AT THIS TRANSITION, FROM ``BEGIN``.

                This closure is the unit ``spec/errors.md`` §2.1 names, and its boundaries
                are chosen to make that true rather than nearly true. The opening rollback
                is what makes a SECOND call a re-attempt instead of a statement issued
                after an aborted transaction (``25P02``, which §1.1 calls a client bug):
                the previous attempt died mid-transaction by definition, and psycopg leaves
                that transaction open and poisoned. On the first attempt it costs nothing —
                the connection is already ``IDLE``.

                The guard is INSIDE the unit because it issues a read, and a read is a
                statement that can meet ``40001`` like any other; leaving it outside would
                have made the retried unit smaller than the transaction it belongs to.
                Its own rollback stays where it was: `_demo_guard` may have opened a
                transaction to establish the demo subject, and this function's contract is
                that it leaves none in progress — a Lambda reuses this connection on the
                next invocation, and inheriting an idle-in-transaction session is how a
                demo starts answering 40001 to requests that never conflicted with
                anything.

                RE-RUNNING IS A FRESH ATTEMPT, NOT A REPLAY, and that is a property of the
                four functions rather than a hope about them: every identifier a re-attempt
                could collide with is minted INSIDE the transition —
                ``_materialise_checks``' ``receipt_id`` and ``_sign_disposition``'s
                ``disposition_id`` are both ``uuid.uuid4()`` at the top of the write — so a
                second attempt cannot meet its own first attempt's key and turn a
                serialization restart into a ``23505`` nobody may retry.
                """
                conn.rollback()

                if mutates and param_name == "permit_id":
                    guard = _demo_guard(conn, subject, scenario)
                    if guard is not None:
                        conn.rollback()
                        return guard

                if resource_key == "merge_permit":
                    return _merge_permit(conn, subject, payload, scenario)
                if resource_key == "suspend_permit":
                    return _suspend_permit(conn, subject, payload, scenario)
                if resource_key == "materialise_checks":
                    return _materialise_checks(conn, subject, payload, scenario)
                return _sign_disposition(conn, subject, payload, scenario)

            try:
                return run_transaction(attempt, undecided=_is_undecided)
            except RetryBudgetExhausted as exhausted:
                # Hand on the DATABASE's own last error rather than a second exhaustion
                # type. `_demo_gate_run` does the same thing for the same reason: this
                # function has exactly ONE place that turns a driver error into a response,
                # and a caller's answer must not depend on how many times the loop tried
                # before giving up. `run_transaction` chains the exhaustion from that error
                # precisely so this is possible.
                cause = exhausted.__cause__
                if isinstance(cause, psycopg.Error):
                    raise cause from exhausted
                raise

        except ValueError as exc:
            conn.rollback()
            return _error(422, "unprocessable_request", str(exc))
        except ScenarioNotSeeded as exc:
            conn.rollback()
            return _error(422, "demo_history_not_seeded", exc.detail)
        except psycopg.OperationalError as exc:
            # THE ORDER OF THESE TWO ANSWERS IS THE WHOLE OF FINDING F-2, and the branch
            # that comes first is the one that used to be missing.
            #
            # `psycopg.errors.SerializationFailure` IS a `psycopg.OperationalError` in
            # psycopg 3.3.4 — measured: SerializationFailure -> OperationalError ->
            # DatabaseError -> Error — so until 2026-08-14 every 40001 that reached here
            # was answered `database_unreachable`. That sentence is false: the database
            # answered, and answered with a decision to abort. It is also unactionable, and
            # expensively so — it sends whoever is triaging to the cluster, to Terraform,
            # to the SSM parameter and to the VPC, none of which is the thing that
            # happened. `docs/diagnosis/divergence-04-connection-semantics.md` §F-2 records
            # the reproduction; two whole-suite tests failed on it at 7535670.
            #
            # Reaching here at all now means the WHOLE transaction was re-attempted
            # `DEFAULT_POLICY.max_attempts` times and answered 40001 every time, so the
            # honest report is the one spec/errors.md §5 asks for: a distinct condition,
            # never a refusal. `refusal.classify` is the predicate, not a second copy of
            # the taxonomy — `_refused` above branches on the same call.
            with contextlib.suppress(psycopg.Error):
                conn.rollback()
            detail = " ".join(str(exc).split())[:512]
            if classify(diagnose(exc)) == "retry":
                return _error(
                    503,
                    "transaction_undecided",
                    f"{RETRYABLE_SQLSTATE} on every one of {DEFAULT_POLICY.max_attempts} "
                    f"attempts at the whole transaction. NOTHING WAS WRITTEN and nothing "
                    f"was decided: this is not a refusal and the gate never got to say "
                    f"anything. Attempt again, or do not. {detail}",
                    sqlstate=RETRYABLE_SQLSTATE,
                    attempts=DEFAULT_POLICY.max_attempts,
                )
            # No cluster is not a refusal. Keeping the two apart is what lets a red lane
            # mean something: "the gate did not refuse" and "there was nothing to ask" are
            # different findings and only one of them is about the product.
            return _error(503, "database_unreachable", detail)
