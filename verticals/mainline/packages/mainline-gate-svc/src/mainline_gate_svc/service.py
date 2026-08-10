# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""``merge_permit`` — the whole service, and there is deliberately not much of it.

One function, one transaction, one ``CALL``. Everything difficult about a MAINLINE merge
lives in ``mainline.merge_permit`` (migration ``0117``) and in the constraints that fire
on its last write; what is left for a client is small, and each remaining part is a
normative sentence from ``spec/errors.md`` rather than a design choice:

1. **The isolation level is asserted, never inherited.** ``SET TRANSACTION ISOLATION
   LEVEL SERIALIZABLE`` is the first statement of every attempt (§2.1), issued verbatim
   from ``trappoint_core.ISOLATION_STATEMENT`` so a wire log can be compared against a
   constant rather than against a remembered sentence.
2. **The retry unit is the whole transaction**, from ``BEGIN``. :func:`run_gate`
   re-enters the callable below; it never re-issues a statement into a poisoned
   transaction.
3. **A refusal is surfaced, never swallowed.** :class:`~trappoint_core.GateRefused`
   propagates out of :func:`merge_permit` with its SQLSTATE and its constraint name
   intact. There is no ``except Exception`` in this module and no boolean return value
   that a caller could mistake for a verdict — a merge that returns is a merge that
   committed.
4. **A refusal is attempted exactly once, ever** (§4). That is a property of
   :func:`run_gate`, and :class:`MergeOutcome` carries the observed retry list so a
   caller can see it rather than assume it.

**There is no model on this path and nowhere to put one.** By the time anyone presses
merge, the obligation count is already an integer in the database. See
``pyproject.toml``'s dependency preamble for the enforced form of that sentence, and
``tests/test_no_model_in_closure.py`` for the assertion.
"""

from __future__ import annotations

import time
from base64 import b64decode
from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any, Final

import mainline_domain
import psycopg

from trappoint_core import (
    ISOLATION_STATEMENT,
    MergeRequest,
    RecordingObserver,
    RetryPolicy,
    run_gate,
)
from trappoint_core.gate import ConnectionSource, call_statement

from .config import GateConfig, GateServiceError, retry_policy

__all__ = [
    "MERGE_CALL_FIELDS",
    "ConnectionUnavailable",
    "DirectConnection",
    "MergeOutcome",
    "WrongBinding",
    "call_parameters",
    "connection_source",
    "merge_permit",
    "merge_request_from_mapping",
]

#: The eight ``mainline.merge_permit`` parameters, in declaration order, named as
#: :class:`~trappoint_core.MergeRequest` fields.
#:
#: Written as field NAMES rather than as a hand-built tuple so the mapping from the
#: request record to the ``CALL`` is one list a reader can compare against migration
#: ``0117``'s signature in a single glance. ``test_refusal_shape`` asserts that its
#: length equals the number of placeholders in
#: :func:`~trappoint_core.gate.call_statement`, so a parameter added to the procedure
#: without a matching entry here is a red test rather than a ``42883`` in production.
#:
#: ``clearance_digest``, ``prev_digest``, ``site_code`` and the observed obligation count
#: are absent because the SERVER computes them from the base tables. A client cannot
#: assert a clearance set the database does not hold.
MERGE_CALL_FIELDS: Final[tuple[str, ...]] = (
    "subject_id",
    "merged_commit",
    "merged_by",
    "actor_kind",
    "payload",
    "canon_bytes",
    "payload_ver",
    "leaf_hash",
)


class WrongBinding(GateServiceError):
    """The request names a schema or subject kind this service does not gate."""

    def __init__(self, expected: str, received: str, what: str) -> None:
        """Name what was expected, what arrived, and which of the two it was."""
        super().__init__(
            f"MAINLINE: gate service refused the request — {what} is {received!r} but this "
            f"service gates {expected!r}. The procedure name is composed from the binding's "
            f"schema and the subject kind, so a mismatch here would compose a CALL against "
            f"another vertical's gate."
        )
        self.expected = expected
        self.received = received


class ConnectionUnavailable(GateServiceError):
    """The database could not be reached. **Not** a gate verdict.

    Deliberately not a ``psycopg.Error`` by the time it leaves this module: if a failed
    connect propagated as one, :func:`run_gate` would classify it against the SQLSTATE
    taxonomy and a machine that is merely unreachable would be reported as
    ``UnmodelledRefusal`` — "the database refused for a reason nobody modelled" — which
    is a sentence about the gate, and the gate never ran.
    """

    def __init__(self, redacted_dsn: str, cause: str) -> None:
        """Build the condition from a redacted DSN and the driver's own message."""
        super().__init__(
            f"MAINLINE: gate service could not reach {redacted_dsn} — {cause}. "
            "The transaction is undecided; nothing was refused and nothing was merged."
        )
        self.redacted_dsn = redacted_dsn


@dataclass(frozen=True, slots=True)
class DirectConnection:
    """A :class:`~trappoint_core.gate.ConnectionSource` that opens one connection per attempt.

    A pool is deliberately not used, and the reason is the retry contract rather than
    performance. ``run_gate`` re-enters the whole transaction on ``40001``; a pooled
    connection handed back in an aborted state answers every subsequent statement with
    ``25P02``, which ``spec/errors.md`` §1.1 names as a client bug in transaction
    handling. One connection per attempt makes that state unreachable, and it is why
    ``psycopg[binary]`` is declared without the ``pool`` extra.

    The session settings are applied while ``autocommit`` is still on, so that the first
    statement of the gate transaction really is ``SET TRANSACTION ISOLATION LEVEL
    SERIALIZABLE`` — a ``SET`` issued after ``BEGIN`` would either fail or, worse,
    silently apply to a transaction whose level had already been fixed.
    """

    config: GateConfig

    @contextmanager
    def connection(self) -> Iterator[psycopg.Connection[Any]]:
        """Yield one connection with the session settings already in force."""
        try:
            conn: psycopg.Connection[Any] = psycopg.connect(
                self.config.dsn,
                autocommit=True,
                connect_timeout=self.config.connect_timeout_s,
                application_name=self.config.application_name,
                options=self.config.libpq_options,
            )
        except psycopg.OperationalError as exc:
            raise ConnectionUnavailable(self.config.redacted_dsn(), str(exc).strip()) from exc
        try:
            conn.autocommit = False
            yield conn
        finally:
            conn.close()


def connection_source(config: GateConfig) -> ConnectionSource:
    """Return the default connection source for *config*."""
    return DirectConnection(config)


@dataclass(frozen=True, slots=True)
class MergeOutcome:
    """What one *successful* merge did, and what it cost.

    There is no ``refused`` variant and no ``ok`` flag. A refusal leaves this function by
    being raised, so a caller cannot handle it by forgetting to check a field — which is
    exactly how a refusal becomes a silence in a product whose deliverable is the
    refusal.

    Attributes:
        subject_id: the permit that merged.
        schema: the binding schema the ``CALL`` was composed against.
        subject_kind: ``permit``.
        attempts: how many whole transactions were run. ``1`` unless ``40001`` was met.
        retried_sqlstates: every code that was retried, in order. Only ``40001`` can
            appear here; a caller that finds anything else has found a defect in
            ``trappoint_core.retry``, and the field exists so that claim is checkable
            rather than assumed.
        elapsed_ms: wall time across all attempts, including backoff sleeps.
        isolation_statement: the statement actually issued, verbatim.
        domain_version: the resident ``mainline_domain`` build. The deterministic domain
            decides what the obligations are; recording which build was in the process
            when a merge committed is the difference between an audit that can be
            re-run and one that cannot.
        application_name: what the cluster saw in ``SHOW SESSIONS``.
    """

    subject_id: str
    schema: str
    subject_kind: str
    attempts: int
    retried_sqlstates: tuple[str, ...]
    elapsed_ms: float
    isolation_statement: str
    domain_version: str
    application_name: str

    def as_dict(self) -> dict[str, Any]:
        """Return the outcome as plain JSON-safe types, for the CLI and for logs."""
        return {
            "merged": True,
            "subject_id": self.subject_id,
            "schema": self.schema,
            "subject_kind": self.subject_kind,
            "attempts": self.attempts,
            "retried_sqlstates": list(self.retried_sqlstates),
            "elapsed_ms": round(self.elapsed_ms, 3),
            "isolation_statement": self.isolation_statement,
            "domain_version": self.domain_version,
            "application_name": self.application_name,
        }


def call_parameters(request: MergeRequest) -> tuple[Any, ...]:
    """Return the eight ``CALL`` parameters in :data:`MERGE_CALL_FIELDS` order."""
    return tuple(getattr(request, field) for field in MERGE_CALL_FIELDS)


def merge_request_from_mapping(
    body: Mapping[str, Any], *, schema: str, subject_kind: str
) -> MergeRequest:
    """Build a :class:`~trappoint_core.MergeRequest` from a decoded JSON object.

    The three byte-valued fields arrive base64-encoded, because JSON has no bytes and
    because ``canon_bytes`` and ``leaf_hash`` are evidentiary: base64 round-trips them
    exactly, whereas any text encoding would have to choose a normalisation and a
    normalisation applied to a hash preimage is a silently different hash.

    Raises:
        KeyError: a required field is absent.
        ValueError: a field is present but not decodable.
    """
    return MergeRequest(
        schema=schema,
        subject_kind=subject_kind,
        subject_id=str(body["subject_id"]),
        merged_commit=b64decode(body["merged_commit"], validate=True),
        merged_by=str(body["merged_by"]),
        actor_kind=str(body["actor_kind"]),
        payload=str(body["payload"]),
        canon_bytes=b64decode(body["canon_bytes"], validate=True),
        payload_ver=int(body["payload_ver"]),
        leaf_hash=b64decode(body["leaf_hash"], validate=True),
        gate_epoch=None if body.get("gate_epoch") is None else int(body["gate_epoch"]),
    )


def merge_permit(
    request: MergeRequest,
    *,
    config: GateConfig,
    source: ConnectionSource | None = None,
    policy: RetryPolicy | None = None,
    observer: RecordingObserver | None = None,
    now: Callable[[], float] = time.monotonic,
) -> MergeOutcome:
    """Merge one permit, or raise the verdict the database returned.

    Args:
        request: the merge. Its ``schema`` and ``subject_kind`` must match *config*.
        config: where to connect and how hard to try.
        source: the connection source; defaults to :class:`DirectConnection`. Injected
            so a test can drive the whole path — including the retry ladder — without a
            cluster, and so a conformance case can supply two connections it controls.
        policy: the ``40001`` ladder; defaults to the one *config* describes.
        observer: the spy. One is created if none is given, because
            :class:`MergeOutcome` reports the attempt count and an unobserved run could
            only guess at it.
        now: injected monotonic clock, so a test can assert the elapsed field.

    Returns:
        :class:`MergeOutcome`. Returning at all means the transaction committed.

    Raises:
        WrongBinding: the request names another vertical's schema or another subject.
        GateRefused: ``23514``/``23503``/``23505``/``P0001`` — the gate decided *no*,
            attempted exactly once, carrying the constraint name as the exhibit.
        AuthorisationDenied: ``42501``. The writer never reached the gate.
        UnmodelledRefusal: any other SQLSTATE. A defect, not an edge case (§1.1).
        RetryBudgetExhausted: ``40001`` outlasted the budget. Undecided, not refused.
        ConnectionUnavailable: the cluster could not be reached at all.
    """
    if request.schema != config.schema:
        raise WrongBinding(config.schema, request.schema, "the request schema")
    if request.subject_kind != config.subject_kind:
        raise WrongBinding(config.subject_kind, request.subject_kind, "the request subject kind")

    pool = source if source is not None else connection_source(config)
    ladder = policy if policy is not None else retry_policy(config)
    spy = observer if observer is not None else RecordingObserver()
    statement = call_statement(request.schema, request.subject_kind)
    parameters = call_parameters(request)

    def one_transaction() -> None:
        """One whole transaction: assert the level, CALL, commit. Nothing else."""
        with pool.connection() as conn:
            cursor = conn.cursor()
            try:
                cursor.execute(ISOLATION_STATEMENT)
                cursor.execute(statement, parameters)
                conn.commit()
            except psycopg.Error:
                # Explicit, and narrow. `run_gate` may re-enter this callable on
                # `40001`, and CockroachDB answers every statement after an aborted one
                # with `25P02`. The exception is re-raised unchanged: the classification
                # is `run_gate`'s job and doing any of it here would put two
                # disagreeing taxonomies in one call path.
                conn.rollback()
                raise

    started = now()
    run_gate(
        one_transaction,
        subject_kind=request.subject_kind,
        subject_id=request.subject_id,
        gate_epoch=request.gate_epoch,
        policy=ladder,
        observer=spy,
    )
    elapsed_ms = (now() - started) * 1000.0

    return MergeOutcome(
        subject_id=request.subject_id,
        schema=request.schema,
        subject_kind=request.subject_kind,
        attempts=len(spy.attempts),
        retried_sqlstates=tuple(state for _, state, _ in spy.retries),
        elapsed_ms=elapsed_ms,
        isolation_statement=ISOLATION_STATEMENT,
        domain_version=mainline_domain.__version__,
        application_name=config.application_name,
    )
