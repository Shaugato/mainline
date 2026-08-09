# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""``execute_gate`` — one explicit SERIALIZABLE transaction, one ``CALL``, one verdict.

Everything difficult about the merge lives in the database. What is left for the client
is small and each part of it is normative:

1. **The isolation level is ASSERTED, never inherited.** ``SET TRANSACTION ISOLATION
   LEVEL SERIALIZABLE`` is issued as the first statement of every attempt
   (``spec/errors.md`` §2.1). A pool default is a setting somebody can change in a
   deploy without changing a line of code, and the gate's correctness argument rests
   entirely on the level actually in force. Issuing the statement puts it in the wire
   log, where an auditor can see it.
2. **The whole transaction is the retry unit.** ``run_gate`` re-enters this function's
   inner callable from ``BEGIN``, never re-issues a statement.
3. **The verdict is discriminated, not caught.** ``40001`` retries; the four refusal
   codes are attempted exactly once, ever; ``42501`` is a fact about the writer; and
   anything else is :class:`~trappoint_core.errors.UnmodelledRefusal`.

**No model call is on this path, and there is no place to put one.** By the time anyone
presses merge, ``open_blocking`` is already an integer (ARCHITECTURE.md §6.5), which is
why the p95 budget of 120 ms server-side closes at all.

The procedure name is composed from the binding's schema and the subject kind — the two
things a substrate is allowed to know — and both are validated against an allowlist
before they reach SQL, so a caller cannot compose an identifier out of user input.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from contextlib import AbstractContextManager
from dataclasses import dataclass
from typing import Any, Final, Protocol

import psycopg
from psycopg import sql as pgsql

from .errors import GateRefused
from .retry import DEFAULT_POLICY, GateObserver, RetryPolicy, run_gate

__all__ = [
    "ISOLATION_STATEMENT",
    "SUBJECT_KINDS",
    "ConnectionSource",
    "MergeRequest",
    "call_statement",
    "execute_gate",
    "procedure_name",
]

#: Issued as the first statement of every gate transaction. Verbatim, so a wire log or a
#: `SHOW transaction_isolation` in a conformance case can be compared against this
#: constant rather than against a remembered sentence.
ISOLATION_STATEMENT: Final = "SET TRANSACTION ISOLATION LEVEL SERIALIZABLE"

#: The gated subject kinds TRAPPOINT defines. A vertical adds a kind by adding a
#: ``[[subject]]`` to its binding AND to this set in the same MINOR — the two must move
#: together, because the procedure name is derived from the kind.
SUBJECT_KINDS: Final[frozenset[str]] = frozenset({"permit", "change_request"})

_SCHEMA_RE: Final = re.compile(r"^[a-z_][a-z0-9_]*$")


class _Connection(Protocol):
    """The slice of a psycopg connection this module uses."""

    def cursor(self) -> Any:
        """Return a cursor."""

    def commit(self) -> None:
        """Commit the open transaction."""

    def rollback(self) -> None:
        """Roll the open transaction back."""


class ConnectionSource(Protocol):
    """A ``psycopg_pool.ConnectionPool``, or anything that hands out one connection.

    Typed structurally rather than as the pool class so a conformance case can pass a
    single dedicated connection — the interleaving tests need two callers whose
    connections they control, which a pool will not promise.
    """

    def connection(self) -> AbstractContextManager[Any]:
        """Yield a connection for the duration of a ``with`` block."""


@dataclass(frozen=True, slots=True)
class MergeRequest:
    """Everything one merge needs, and nothing the database can derive for itself.

    ``clearance_digest``, ``prev_digest``, ``site_code`` and the observed obligation
    count are absent ON PURPOSE: the procedure computes each from the base tables, so a
    client cannot assert a clearance set the database does not hold.

    Attributes:
        schema: the binding's business schema, e.g. ``mainline``.
        subject_kind: one of :data:`SUBJECT_KINDS`.
        subject_id: the permit or change request being merged.
        merged_commit: the 32-byte commit the merge records.
        merged_by: the acting subject identifier; goes on the event and the ledger.
        actor_kind: ``human``/``agent``/``service``/``external`` — the ledger's own
            chain-of-custody vocabulary.
        payload: the event payload. The procedure appends what the gate observed.
        canon_bytes: RFC 8785 JCS bytes of the ledger payload, produced by the CLIENT.
            SQL cannot canonicalise to JCS — CockroachDB's JSONB key ordering is not
            reproducible by a third party — so a server-computed leaf would be a hash
            nobody outside the cluster could recompute.
        payload_ver: which canonicaliser produced ``canon_bytes``; the offline verifier
            dispatches on it.
        leaf_hash: ``SHA-256(0x00 || canon_bytes)``, RFC 6962 §2.1, client-computed.
        gate_epoch: the epoch the caller believes the subject is at, carried onto a
            refusal so the payload is reproducible. Advisory only — the procedure reads
            the epoch itself and pins that.
    """

    schema: str
    subject_kind: str
    subject_id: str
    merged_commit: bytes
    merged_by: str
    actor_kind: str
    payload: str
    canon_bytes: bytes
    payload_ver: int
    leaf_hash: bytes
    gate_epoch: int | None = None

    def __post_init__(self) -> None:
        """Refuse a request that could not produce a well-formed ``CALL``."""
        if self.subject_kind not in SUBJECT_KINDS:
            raise ValueError(
                f"unknown subject kind {self.subject_kind!r}; TRAPPOINT gates "
                f"{sorted(SUBJECT_KINDS)}"
            )
        if _SCHEMA_RE.match(self.schema) is None:
            raise ValueError(
                f"{self.schema!r} is not a bare lower-case SQL identifier; the binding's "
                "schema is composed into an object name and is never quoted user input"
            )


def procedure_name(schema: str, subject_kind: str) -> pgsql.Identifier:
    """Compose ``<schema>.merge_<subject_kind>`` as a psycopg identifier.

    The kernel emits these procedures into the BINDING's schema rather than into the
    shared ``trappoint`` bootstrap schema, because two bindings on one cluster would
    otherwise render one object twice and the second migration would silently redefine
    the first vertical's gate. See migration ``0117``'s header.

    Raises:
        ValueError: the kind is not in :data:`SUBJECT_KINDS`, or the schema is not a
            bare lower-case identifier.
    """
    if subject_kind not in SUBJECT_KINDS:
        raise ValueError(f"unknown subject kind {subject_kind!r}")
    if _SCHEMA_RE.match(schema) is None:
        raise ValueError(f"{schema!r} is not a bare lower-case SQL identifier")
    return pgsql.Identifier(schema, f"merge_{subject_kind}")


def call_statement(schema: str, subject_kind: str) -> pgsql.Composed:
    """Return the parameterised ``CALL`` for one subject kind.

    Split out from :func:`execute_gate` so a test can assert the statement text without
    a cluster, and so the conformance runner can log exactly what it issued.
    """
    return pgsql.SQL("CALL {}(%s::UUID, %s, %s, %s, %s::JSONB, %s, %s::INT2, %s)").format(
        procedure_name(schema, subject_kind)
    )


def _parameters(request: MergeRequest) -> tuple[Any, ...]:
    return (
        request.subject_id,
        request.merged_commit,
        request.merged_by,
        request.actor_kind,
        request.payload,
        request.canon_bytes,
        request.payload_ver,
        request.leaf_hash,
    )


def _attempt(connection: _Connection, request: MergeRequest) -> None:
    """One whole transaction: assert the isolation level, CALL, commit.

    The rollback on failure is explicit rather than left to the connection's context
    manager, because ``run_gate`` may call this again on ``40001`` and CockroachDB
    refuses every statement after an aborted one with ``25P02`` — a code
    ``spec/errors.md`` §1.1 names as a client bug in transaction handling.
    """
    cursor = connection.cursor()
    try:
        cursor.execute(ISOLATION_STATEMENT)
        cursor.execute(call_statement(request.schema, request.subject_kind), _parameters(request))
        connection.commit()
    except psycopg.Error:
        connection.rollback()
        raise


def execute_gate(
    pool: ConnectionSource,
    request: MergeRequest,
    *,
    policy: RetryPolicy = DEFAULT_POLICY,
    observer: GateObserver | None = None,
) -> None:
    """Merge one subject, or raise the verdict the database returned.

    Args:
        pool: a psycopg connection pool, or any object yielding a connection from a
            ``connection()`` context manager.
        request: the merge.
        policy: the ``40001`` ladder. Only ``40001``.
        observer: a spy; :class:`~trappoint_core.retry.RecordingObserver` is the one the
            conformance suite uses to assert the once-only property directly.

    Returns:
        ``None``. A merge that returns is a merge that committed; there is deliberately
        no truthy result to mistake for one.

    Raises:
        GateRefused: ``23514``/``23503``/``23505``/``P0001``, attempted exactly once,
            carrying the constraint name or the raising object as the exhibit.
        AuthorisationDenied: ``42501`` — the writer never reached the gate.
        UnmodelledRefusal: any other SQLSTATE.
        RetryBudgetExhausted: ``40001`` outlasted the budget; undecided, not refused.
    """

    def once() -> None:
        with pool.connection() as connection:
            _attempt(connection, request)

    run_gate(
        once,
        subject_kind=request.subject_kind,
        subject_id=request.subject_id,
        gate_epoch=request.gate_epoch,
        policy=policy,
        observer=observer,
    )


def refusals_of(error: BaseException) -> Iterator[dict[str, Any]]:
    """Yield the refusal payload for *error*, or nothing if it is not a refusal.

    A generator rather than an ``Optional`` so a caller can write
    ``for payload in refusals_of(exc): ledger.record(payload)`` and get exactly the
    right behaviour for both cases without a branch that could be written the wrong way
    round. ``40001`` and ``42501`` yield nothing, which is ``spec/errors.md`` §5: an
    undecided transaction has no reason set, and a denial is a fact about the writer.
    """
    if isinstance(error, GateRefused):
        yield error.as_dict()
