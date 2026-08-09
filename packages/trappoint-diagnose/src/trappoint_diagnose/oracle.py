# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""THE DATABASE AS THE ORACLE — savepoint probes, and the six rules that keep them safe.

``SAVEPOINT p; <apply candidate subset>; <attempt the transition>; ROLLBACK TO SAVEPOINT p``

CockroachDB supports general-purpose nested savepoints, so the loop is legal. What makes
it *correct* is that the thing answering ``admissible?`` is the same constraint engine
that produced the refusal being explained.

Six hard constraints, and each one is enforced here rather than documented:

1. **The probe transaction is SEPARATE from the gate transaction.** ``SavepointOracle``
   refuses at construction a connection that is already inside one. This is not
   fastidiousness: row locks are PRESERVED across ``ROLLBACK TO SAVEPOINT`` in
   CockroachDB (unlike PostgreSQL), so a probe sharing the gate's connection would leave
   the gate holding locks it never took — and a diagnosis that can change the gate's
   behaviour is not a diagnosis.
2. **It is rolled back unconditionally, in a `finally`.** ``probe_transaction()`` rolls
   back and closes whatever happened inside it, including when the oracle raised, the
   plan raised, or the caller did.
3. **The budget is bounded** and the payload reports what it spent. Past the cap the
   emitter degrades to ``diagnosis="none"`` with ``probe_budget_exhausted`` rather than
   blocking.
4. **It never runs on the completion path.** Structurally: this module is imported by the
   diagnoser, which runs after a refusal, and rule 1 makes sharing the gate's transaction
   impossible.
5. **A statement timeout is set on the probe session**, so a probe that finds a slow plan
   cannot hold locks while a human reads a screen.
6. **An unmodelled error is not an answer.** If the attempt fails with anything outside
   the REFUSE-class codes, the oracle raises rather than reporting "inadmissible". A probe
   that reported a permissions error as a refusal would produce a minimal unsatisfiable
   subset of the wrong thing.

**Measured, not assumed** (CockroachDB v26.2.5, local node, 2026-08-09): after a `23514`
inside a savepoint, ``ROLLBACK TO SAVEPOINT`` returns the transaction to a usable state
and subsequent statements in the same transaction succeed. Nested savepoints behave as
written. The probe loop rests on that measurement.
"""

from __future__ import annotations

from collections.abc import Callable, Hashable, Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any, Protocol

from .errors import OracleUnavailable, ProbeBudgetExhausted, ProbeUnsafe
from .model import REFUSE_SQLSTATES

__all__ = [
    "Connection",
    "Cursor",
    "ProbePlan",
    "SavepointOracle",
    "probe_transaction",
]

# psycopg's TransactionStatus.IDLE. Compared numerically so this module needs no import
# from a driver it does not depend on.
_TXN_IDLE = 0
_DEFAULT_STATEMENT_TIMEOUT_MS = 2000
_DEFAULT_BUDGET = 32


class Cursor(Protocol):
    """The slice of a DB-API cursor the diagnosis path uses.

    ``fetchone`` is here rather than in a second protocol because the probe loop and the
    UDF client are two halves of one seam, and splitting the cursor into a writer and a
    reader would make a caller supply two adapters for one connection.
    """

    def execute(self, query: str, params: Sequence[Any] | Mapping[str, Any] | None = ..., /) -> Any:
        """Execute one statement, with positional or named parameters."""

    def fetchone(self) -> Sequence[Any] | None:
        """Return the next row, or None when the result is exhausted."""

    def close(self) -> None:
        """Release the cursor."""


class Connection(Protocol):
    """The slice of a DB-API connection this module uses."""

    def cursor(self) -> Cursor:
        """Open a cursor."""

    def rollback(self) -> None:
        """Abandon the transaction."""

    def close(self) -> None:
        """Close the connection."""


@dataclass(frozen=True, slots=True)
class ProbePlan:
    """How to put one candidate fact in place, and how to attempt the transition.

    Supplied by the DEPLOYMENT, not by the substrate, and that seam is deliberate. The
    algorithm and the savepoint discipline are universal; what it means to "apply" a fact
    is a statement about a particular vertical's tables, and a substrate that guessed
    would be guessing about the one thing it must not.

    ``attempt`` must perform the SAME transition that was refused. A plan whose attempt
    differs from the refused write produces a minimal unsatisfiable subset of a different
    question, and there is no way to tell from the payload that it did.
    """

    apply: Callable[[Cursor, Any], None]
    attempt: Callable[[Cursor], None]
    refusal_codes: frozenset[str] = field(default=REFUSE_SQLSTATES)


class SavepointOracle:
    """An ``Oracle`` whose ``admissible()`` is answered by the database itself."""

    def __init__(
        self,
        connection: Connection,
        plan: ProbePlan,
        *,
        budget: int = _DEFAULT_BUDGET,
        savepoint_prefix: str = "tp_probe",
    ) -> None:
        """Bind the oracle to a connection it is allowed to use.

        Raises:
            ProbeUnsafe: the connection is already inside a transaction. See rule 1.
            ValueError: the budget or the savepoint prefix is unusable.
        """
        if budget < 1:
            raise ValueError("a budget below one call cannot answer any question")
        if not savepoint_prefix.isidentifier():
            # The prefix is interpolated into `SAVEPOINT <name>`, which takes an
            # identifier and not a parameter. Restricting it to a Python identifier is
            # what makes that interpolation safe, and it is checked rather than trusted.
            raise ValueError(f"savepoint prefix {savepoint_prefix!r} is not an identifier")
        self._assert_outside_transaction(connection)
        self._connection = connection
        self._plan = plan
        self._budget = budget
        self._prefix = savepoint_prefix
        self._calls = 0

    @staticmethod
    def _assert_outside_transaction(connection: Connection) -> None:
        info = getattr(connection, "info", None)
        status = getattr(info, "transaction_status", None)
        if status is None:
            return
        if int(status) != _TXN_IDLE:
            raise ProbeUnsafe(
                "the probe oracle refuses a connection that is already inside a "
                "transaction. Row locks survive ROLLBACK TO SAVEPOINT in CockroachDB, so "
                "a probe here would leave the gate's transaction holding locks it never "
                "took — and a diagnosis that can change the gate is not a diagnosis."
            )

    @property
    def calls(self) -> int:
        """Oracle calls consumed so far. This is the payload's ``probe_calls``."""
        return self._calls

    @property
    def budget(self) -> int:
        """The cap this oracle enforces."""
        return self._budget

    def admissible(self, facts: Sequence[Hashable]) -> bool:
        """Apply *facts* inside a savepoint, attempt the transition, and roll back.

        Raises:
            ProbeBudgetExhausted: the budget is spent.
            OracleUnavailable: the attempt failed with a code outside the REFUSE class, so
                the database did not answer the question that was asked.
        """
        if self._calls >= self._budget:
            raise ProbeBudgetExhausted(
                f"probe budget of {self._budget} oracle call(s) is spent; the reason set "
                "was not proven minimal, so it must not be labelled one"
            )
        self._calls += 1
        name = f"{self._prefix}_{self._calls}"
        cursor = self._connection.cursor()
        try:
            cursor.execute(f"SAVEPOINT {name}")
            try:
                for fact in facts:
                    self._plan.apply(cursor, fact)
                self._plan.attempt(cursor)
            except Exception as exc:  # noqa: BLE001 - re-raised unless it is a refusal
                return self._interpret(exc)
            else:
                return True
            finally:
                cursor.execute(f"ROLLBACK TO SAVEPOINT {name}")
        finally:
            cursor.close()

    def _interpret(self, exc: Exception) -> bool:
        sqlstate = getattr(exc, "sqlstate", None)
        if isinstance(sqlstate, str) and sqlstate in self._plan.refusal_codes:
            return False
        raise OracleUnavailable(
            f"the probe failed with {sqlstate or type(exc).__name__}, which is not a "
            "REFUSE-class outcome. The database did not answer the question that was "
            "asked, so this is not evidence of inadmissibility."
        ) from exc


@contextmanager
def probe_transaction(
    connect: Callable[[], Connection],
    plan: ProbePlan,
    *,
    budget: int = _DEFAULT_BUDGET,
    statement_timeout_ms: int = _DEFAULT_STATEMENT_TIMEOUT_MS,
) -> Iterator[SavepointOracle]:
    """Open a probe transaction, yield the oracle, and roll it back whatever happens.

    The rollback is in a ``finally`` and there is no path around it. That is the whole
    safety argument of the diagnosis path: the probe is allowed to write anything it likes
    because nothing it writes can survive. ``close()`` runs in a nested ``finally`` so a
    connection is not leaked when the rollback itself fails.

    ``connect`` is a callable rather than a connection so this function OWNS the lifetime.
    Handed a live connection, it could not promise the rollback covers everything that
    happened on it.
    """
    connection = connect()
    try:
        cursor = connection.cursor()
        try:
            # Session-level, not `SET LOCAL`: this connection exists only for the probe
            # and is closed at the end of this block, so there is nothing to leak the
            # setting into. A probe that hangs holds row locks while a human reads a
            # screen, which is the failure mode rule 5 exists to prevent.
            cursor.execute(f"SET statement_timeout = '{int(statement_timeout_ms)}ms'")
        finally:
            cursor.close()
        yield SavepointOracle(connection, plan, budget=budget)
    finally:
        try:
            connection.rollback()
        finally:
            connection.close()
