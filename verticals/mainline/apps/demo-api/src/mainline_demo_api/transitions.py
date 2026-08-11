# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""The five POST resources: four kernel transitions, and the demo driver.

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

plus ``demo_gate_run`` — ``POST /v1/demo/gate-run`` — governed by this app's own
``contracts/gate-run.schema.json``.

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

**There is no retry helper on this path and there will not be one.** ``40001`` is an
undecided transaction, not a failure; a helper that re-sent a merge because a socket closed
is a helper that can issue a permit twice. The outcome is surfaced and the decision keeps
an author.

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
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import os
import uuid
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any, Final

import psycopg
from psycopg.types.json import Jsonb

from .gate_run import GATE_RUN_SCHEMA_ID, canonical_json, gate_run
from .refusal import classify, diagnose, refusal_payload, rfc3339
from .scenario import Scenario, ScenarioNotSeeded, from_env

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


def _prepare(conn: psycopg.Connection[Any]) -> None:
    """Put *conn* in the one state every transition needs, and say so explicitly.

    ``spec/errors.md`` §2.1: the isolation level is issued by the client on every attempt,
    never inherited from a pool default. A procedure that silently ran at whatever the
    session offered would make the one line of the client that matters unauditable — and
    on a warm Lambda the session is by definition a reused one.
    """
    if conn.autocommit:
        conn.autocommit = False
    conn.rollback()
    conn.execute("SET TRANSACTION ISOLATION LEVEL SERIALIZABLE")


def _demo_guard(subject_id: uuid.UUID, scenario: Scenario) -> tuple[int, dict[str, Any]] | None:
    if subject_id != scenario.permit_id:
        return None
    if os.environ.get("MAINLINE_DEMO_ALLOW_MUTATION", "").strip() not in ("", "0", "false"):
        return None
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


def _permit_epoch(
    conn: psycopg.Connection[Any], permit_id: uuid.UUID
) -> tuple[int, int, str] | None:
    row = conn.execute(
        "SELECT gate_epoch, head_seq, state::STRING FROM mainline.permit WHERE permit_id = %s",
        (permit_id,),
    ).fetchone()
    return (int(row[0]), int(row[1]), row[2]) if row else None


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

    record = conn.execute(
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
    moved = conn.execute(
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

    recall = conn.execute(_RECALL_SQL, (permit_id,)).fetchone()
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

    checks = [row[0] for row in conn.execute(_OPEN_CHECKS_SQL, (permit_id,)).fetchall()]
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

    STAGED, and the envelope says so. The WebAuthn assertion is synthesised here: this demo
    has no authenticator, and the database does not verify signatures on this path. That is
    hand-authored demonstration material inside an otherwise live transition, which is
    exactly what ``envelope.staged`` exists to declare.
    """
    procedure = "trappoint.sign_disposition"
    kind = _text(body, "kind", "applied", limit=64)
    if kind not in _DISPOSITION_KINDS:
        raise ValueError(
            f"body member 'kind' must be one of {sorted(_DISPOSITION_KINDS)}; got {kind!r}"
        )
    defeater_code = _text(body, "defeater_code", "MECHANISM_PRESENT_AND_VERIFIED", limit=128)
    rationale = _text(body, "rationale", None, limit=_RATIONALE_MAX)
    if len(rationale) < _RATIONALE_MIN:
        raise ValueError(
            f"body member 'rationale' is {len(rationale)} characters; the disposition "
            f"table requires a substantive one and this API asks for at least "
            f"{_RATIONALE_MIN}. A one-word clearance is not a clearance."
        )
    signer_sub = _text(body, "signer_sub", scenario.signer_sub, limit=256)
    countersigner_sub = _text(body, "countersigner_sub", scenario.countersigner_sub, limit=256)

    _prepare(conn)
    found = conn.execute(_CHECK_SQL, (check_id,)).fetchone()
    if found is None:
        conn.rollback()
        return _error(404, "no_such_check", f"no mainline.blocking_check with check_id {check_id}")
    permit_id, site_id, gate_epoch, receipt_id = found

    guard = _demo_guard(permit_id, scenario)
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
                _sha("defeater-vocab"),
                rationale,
                _sha("evidence", str(disposition_id)),
                signer_sub,
                _sha("cred", "signer"),
                countersigner_sub,
                _sha("cred", "cosigner"),
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
    if conn.autocommit:
        conn.autocommit = False
    run_id = body.get("run_id")
    if run_id is not None and not isinstance(run_id, str):
        raise ValueError("body member 'run_id' must be a string when supplied")
    payload = gate_run(conn, scenario, run_id=run_id)
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
        conn: a psycopg connection this function owns for the duration of the call. It is
            left with no transaction in progress, whatever happened.

    Returns:
        ``(status, payload)``. For the five known resources with a well-formed request the
        payload is a COMPLETE response envelope; for a client error it is a plain
        ``{"error", "detail"}`` object. See the module docstring for why those differ.

    This function does not raise for anything a caller can cause. A caller error is a
    status and a body; only a defect in this module reaches the caller as an exception,
    and it should.
    """
    if resource_key not in TRANSITION_RESOURCES:
        return _error(
            404,
            "unknown_resource",
            f"{resource_key!r} is not a transition resource. Declared: "
            f"{', '.join(sorted(TRANSITION_RESOURCES))}.",
        )

    payload = dict(body or {})
    scenario = from_env()
    param_name, _procedure, mutates = TRANSITION_RESOURCES[resource_key]

    try:
        if resource_key == "demo_gate_run" or param_name is None:
            return _demo_gate_run(conn, payload, scenario)

        subject = _uuid_param(path_params, param_name)

        # The demo subject is write-protected on the three permit-addressed transitions.
        # sign_disposition is addressed by check_id, so its guard runs after the check has
        # been resolved to its permit — inside `_sign_disposition`.
        if mutates and param_name == "permit_id":
            guard = _demo_guard(subject, scenario)
            if guard is not None:
                return guard

        if resource_key == "merge_permit":
            return _merge_permit(conn, subject, payload, scenario)
        if resource_key == "suspend_permit":
            return _suspend_permit(conn, subject, payload, scenario)
        if resource_key == "materialise_checks":
            return _materialise_checks(conn, subject, payload, scenario)
        return _sign_disposition(conn, subject, payload, scenario)

    except ValueError as exc:
        conn.rollback()
        return _error(422, "unprocessable_request", str(exc))
    except ScenarioNotSeeded as exc:
        conn.rollback()
        return _error(422, "demo_history_not_seeded", exc.detail)
    except psycopg.OperationalError as exc:
        # No cluster is not a refusal. Keeping the two apart is what lets a red lane mean
        # something: "the gate did not refuse" and "there was nothing to ask" are different
        # findings and only one of them is about the product.
        with contextlib.suppress(psycopg.Error):
            conn.rollback()
        return _error(503, "database_unreachable", " ".join(str(exc).split())[:512])
