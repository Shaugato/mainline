# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""One whole transaction, one fresh connection, retried by the loop that already exists.

**THIS MODULE CONTAINS NO RETRY LOGIC AND NO SQLSTATE TAXONOMY, AND THAT IS THE POINT.**
:func:`trappoint_core.retry.run_gate` is the loop: it retries ``40001`` and only ``40001``,
it attempts each of the four refusal codes exactly once ever, and
``tests/concurrency/test_retry_taxonomy_spy.py`` watches it do so. A second loop written
here would be a second taxonomy to keep correct, and the day the two disagreed the one
nobody was spying on would win. What is missing from ``run_gate`` — deliberately, because
``trappoint-core`` must not own a connection policy — is the *connection* half of
``spec/errors.md`` §2.1, and that is all this module supplies:

    retry the **whole transaction**, from ``BEGIN``, never a statement; […] the isolation
    level MUST be set explicitly on every gate transaction
    (``SET TRANSACTION ISOLATION LEVEL SERIALIZABLE``) and never inherited from a pool
    default

Roughly nineteen call sites across this repository open a connection, do multi-statement
work, and commit. Each one that writes its own version of "and on ``40001`` discard the
connection and start the WHOLE thing again" is a place the whole/statement distinction can
be got wrong quietly. So the shape here is a **connection factory plus a callable**, never
a connection:

.. code-block:: python

    from trappoint_testkit.txn import from_dsn, run_txn


    def seed(conn):  # receives a FRESH connection, every attempt
        conn.execute("INSERT INTO … VALUES (…)")
        conn.execute("UPDATE … SET … WHERE …")
        return "seeded"  # the adapter commits; the callable must not


    run_txn(from_dsn(dsn), seed)

**Why a factory and not a connection.** A caller who hands over an already-open connection
is asking for the retry to happen *inside* a transaction that CockroachDB has already
poisoned, which §2.1 names as the mistake: a statement replayed into an aborted transaction
is not a retry of anything, and every replay would fail with the same ``40001`` until the
budget ran out — a loop that looks like diligence and is really five copies of one failure.
There is no parameter that accepts a connection, so that call cannot be written; and the
two guards below make the near misses (an autocommit connection, a connection already
inside a transaction, a callable that commits or swallows a database error on its own)
raise something a reader can act on rather than pass silently.

**What is NOT swallowed.** :class:`~trappoint_core.errors.RetryBudgetExhausted` propagates.
An undecided transaction reported as a failure is honest; reported as a success it is a
row nobody wrote and everybody believes in. Likewise :class:`GateRefused` — the gate
decided, and a decision is not a thing to retry.

**IMPORT COST, and why this is a submodule.** ``trappoint_testkit/__init__.py`` re-exports
nothing from here, on purpose. The boundary lanes install ``mainline-boundary`` and
``pytest`` and nothing else — E3 measures what a *minimal* kernel-plane environment can
reach — and the package docstring records the day an eager import cost seven jobs their
whole run. This module imports ``psycopg`` and ``trappoint_core`` at module scope because
it cannot do its job without either; nothing pays for that unless it writes
``import trappoint_testkit.txn``.
"""

from __future__ import annotations

import random
import time
from collections.abc import Callable
from contextlib import suppress
from typing import Any, Protocol

import psycopg
from psycopg.pq import TransactionStatus

from trappoint_core.errors import (
    AuthorisationDenied,
    GateRefused,
    RetryBudgetExhausted,
    UnmodelledRefusal,
)
from trappoint_core.retry import DEFAULT_POLICY, GateObserver, RetryPolicy, run_gate

__all__ = [
    "ISOLATION_SQL",
    "AuthorisationDenied",
    "ConnectionNotFresh",
    "GateRefused",
    "RetryBudgetExhausted",
    "TransactionNotCommittable",
    "TransactionalConnection",
    "UnmodelledRefusal",
    "from_dsn",
    "run_txn",
]

#: Stated on every attempt, as the first statement of the transaction. ``spec/errors.md``
#: §2.1 requires the level to be explicit and forbids inheriting it from a pool default —
#: a gate transaction that ran at whatever the pool happened to be set to has proved
#: nothing about serialisability, and CockroachDB Cloud's default is not a thing this
#: repository controls.
ISOLATION_SQL = "SET TRANSACTION ISOLATION LEVEL SERIALIZABLE"


class ConnectionNotFresh(TypeError):
    """The adapter was not given a way to obtain a fresh, unopened, non-autocommit connection.

    A ``TypeError`` rather than a runtime error because every case is a call that should
    never have been written: a connection passed where a factory belongs, a factory that
    hands back the same open connection twice, or an autocommit connection, which has no
    transaction for the retry to be *of*.
    """


class TransactionNotCommittable(RuntimeError):
    """The callable returned, but the connection was not in an open, error-free transaction.

    Two ways to get here and both are defects the adapter must not paper over:

    * the transaction is **IDLE** — the callable committed or rolled back on its own, or
      executed nothing at all. Either way the adapter can no longer make "the whole
      transaction, retried from ``BEGIN``" true, because part of the work is already
      durable and a retry would replay it.
    * the transaction is **INERROR** — a statement was refused and the callable caught it
      and returned anyway. ``COMMIT`` on a failed transaction is a ``ROLLBACK``, so
      committing here would report a success that wrote nothing.
    """


class _ConnectionInfo(Protocol):
    """The one connection attribute this adapter reads."""

    @property
    def transaction_status(self) -> int:
        """Libpq's transaction status: ``IDLE`` before ``BEGIN``, ``INTRANS`` inside one."""


class TransactionalConnection(Protocol):
    """The part of ``psycopg.Connection`` this adapter uses, and nothing more.

    A protocol rather than ``psycopg.Connection`` so the adapter's own guards can be
    asserted **hermetically**, with no cluster: the contract being tested is "which
    connection did each attempt receive, and was it committed or discarded", and a test
    that needed a database to ask that would be a test nobody runs on a laptop with no
    Docker. ``psycopg.Connection`` satisfies this structurally; nothing here is a
    reimplementation of it.
    """

    @property
    def autocommit(self) -> bool:
        """Whether this connection commits each statement of its own accord."""

    @property
    def info(self) -> _ConnectionInfo:
        """The connection's live status."""

    def execute(self, query: Any, params: Any = None) -> Any:
        """Run one statement."""

    def commit(self) -> None:
        """Commit the open transaction."""

    def rollback(self) -> None:
        """Abandon the open transaction."""

    def close(self) -> None:
        """Close the connection. The adapter opened it, so the adapter closes it."""


def from_dsn(dsn: str, **connect_kwargs: Any) -> Callable[[], psycopg.Connection[Any]]:
    """Return a factory that opens ONE new connection per call against *dsn*.

    The convenience exists so that the correct call is also the short one. ``autocommit``
    is pinned to ``False`` and cannot be overridden: an autocommit connection has no
    transaction to retry, and a caller who wanted one did not want this adapter.

    Args:
        dsn: the connection string.
        **connect_kwargs: forwarded to ``psycopg.connect`` — ``row_factory`` and friends.

    Returns:
        A zero-argument callable returning a fresh connection.

    Raises:
        ConnectionNotFresh: ``autocommit=True`` was requested.
    """
    if connect_kwargs.get("autocommit"):
        raise ConnectionNotFresh(
            "from_dsn(autocommit=True): this adapter owns the transaction, and an "
            "autocommit connection has none — every statement would be its own "
            "transaction, so a retry would replay only the last one"
        )
    connect_kwargs.pop("autocommit", None)

    def factory() -> psycopg.Connection[Any]:
        """Open one connection. A new one per attempt: a poisoned one is never reused."""
        return psycopg.connect(dsn, autocommit=False, **connect_kwargs)

    return factory


def _fresh(connect: Callable[[], TransactionalConnection]) -> TransactionalConnection:
    """Obtain a connection from *connect* and prove it is fresh, or refuse it by name.

    A connection this function REFUSES is not closed. Refusing is a diagnosis, not a
    lifecycle event: the offending case is a factory that handed back something it still
    owns — very possibly a long-lived connection the caller is using — and closing it would
    make a ``TypeError`` about a mis-written call into a failure somewhere else entirely.
    The adapter closes what it accepted and used; the factory owns everything it kept.
    """
    if not callable(connect):
        raise ConnectionNotFresh(
            "run_txn takes a connection FACTORY, not a connection. It was given "
            f"{type(connect).__name__}. An already-open connection cannot be the unit of "
            "retry: spec/errors.md §2.1 retries the whole transaction from BEGIN, and a "
            "statement replayed into a transaction CockroachDB has already aborted is not "
            "a retry of anything. Pass `trappoint_testkit.txn.from_dsn(dsn)`, or any "
            "zero-argument callable that opens a new connection."
        )
    conn = connect()
    if conn.autocommit:
        raise ConnectionNotFresh(
            "the connection factory returned an AUTOCOMMIT connection. There is no "
            "transaction to retry: each statement would commit on its own, so a retry "
            "would replay the last statement into a database that already holds the "
            "others. Open it with `autocommit=False`."
        )
    if conn.info.transaction_status != TransactionStatus.IDLE:
        raise ConnectionNotFresh(
            "the connection factory returned a connection that is ALREADY INSIDE a "
            f"transaction (status {conn.info.transaction_status!r}). A factory must open a "
            "new connection per call; handing back a live one makes the retry happen "
            "inside the transaction that just failed, which spec/errors.md §2.1 names as "
            "the mistake."
        )
    return conn


def _committable(conn: TransactionalConnection) -> None:
    """Refuse to commit anything that is not an open, error-free transaction."""
    status = conn.info.transaction_status
    if status == TransactionStatus.INTRANS:
        return
    if status == TransactionStatus.INERROR:
        raise TransactionNotCommittable(
            "the callable returned with the transaction IN ERROR: a statement was refused "
            "and the exception was caught inside the callable. COMMIT on a failed "
            "transaction is a ROLLBACK, so committing here would report a success that "
            "wrote nothing. Let the database's exception leave the callable — run_gate is "
            "what classifies it."
        )
    raise TransactionNotCommittable(
        f"the callable returned with no transaction open (status {status!r}). Either it "
        "committed or rolled back on its own — the adapter owns the commit, so that a "
        "retry restarts the WHOLE unit — or it executed no statement at all."
    )


def _discard(conn: TransactionalConnection) -> None:
    """Roll back and close, and never let the cleanup speak over the original failure.

    ``psycopg.Error`` and ``OSError`` only: a broken socket cannot be rolled back and a
    closed connection cannot be closed twice, and neither is news. Anything else is a real
    defect in the connection object and propagates as itself — a blanket ``except`` here
    would be the silence this repository's lint gate hard-gates ``BLE`` to prevent.
    """
    with suppress(psycopg.Error, OSError):
        conn.rollback()
    with suppress(psycopg.Error, OSError):
        conn.close()


def run_txn[T](
    connect: Callable[[], TransactionalConnection],
    work: Callable[[TransactionalConnection], T],
    *,
    subject_kind: str | None = None,
    subject_id: str | None = None,
    gate_epoch: int | None = None,
    policy: RetryPolicy = DEFAULT_POLICY,
    observer: GateObserver | None = None,
    sleep: Callable[[float], None] = time.sleep,
    rng: random.Random | None = None,
    now: Callable[[], float] = time.monotonic,
) -> T:
    """Run *work* as one whole transaction on a fresh connection, retried per §2.1.

    Each attempt: open a NEW connection, state the isolation level, run *work* to
    completion, commit, close. On failure the connection is rolled back and **closed** —
    never handed to the next attempt — and :func:`trappoint_core.retry.run_gate` decides
    whether there is a next attempt at all.

    Args:
        connect: a zero-argument callable returning a fresh, non-autocommit connection.
            :func:`from_dsn` builds one. Not a connection — see :class:`ConnectionNotFresh`.
        work: the WHOLE transaction. It receives the connection and must not commit,
            roll back, or catch the database's own exceptions.
        subject_kind: carried onto a refusal, for the exhibit.
        subject_id: carried onto a refusal.
        gate_epoch: the epoch observed when the attempt began.
        policy: the backoff ladder and the attempt bound. Forwarded unchanged.
        observer: a :class:`~trappoint_core.retry.GateObserver` — the spy that makes the
            retry/refusal tally assertable rather than inferred.
        sleep: injected so a test can assert the ladder without spending it.
        rng: injected so a test of full jitter is reproducible.
        now: injected monotonic clock, for the elapsed time on exhaustion.

    Returns:
        Whatever *work* returned on the attempt that committed.

    Raises:
        ConnectionNotFresh: *connect* is not a factory, or handed back a connection that
            is autocommit or already inside a transaction.
        TransactionNotCommittable: *work* returned without an open, error-free transaction.
        GateRefused: the gate decided. Attempted exactly once, ever.
        AuthorisationDenied: ``42501``.
        UnmodelledRefusal: a SQLSTATE outside the five modelled codes.
        RetryBudgetExhausted: ``40001`` survived the budget. **Surfaced, not swallowed:**
            the transaction is undecided, which is not the same thing as refused.
    """

    def attempt() -> T:
        """One whole transaction on a connection nothing else has touched."""
        conn = _fresh(connect)
        committed = False
        try:
            conn.execute(ISOLATION_SQL)
            result = work(conn)
            _committable(conn)
            conn.commit()
            committed = True
            return result
        finally:
            # `finally` rather than `except`, so that a KeyboardInterrupt or a defect in
            # `work` cannot leave a connection holding locks that a later attempt would
            # then wait on. The exception itself is never touched: classifying it is
            # `run_gate`'s job, and a handler here would be the silence `BLE` exists to
            # prevent.
            if committed:
                conn.close()
            else:
                _discard(conn)

    return run_gate(
        attempt,
        subject_kind=subject_kind,
        subject_id=subject_id,
        gate_epoch=gate_epoch,
        policy=policy,
        observer=observer,
        sleep=sleep,
        rng=rng,
        now=now,
    )
