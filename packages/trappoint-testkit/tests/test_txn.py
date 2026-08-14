# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""The adapter's own contract, asserted with no cluster anywhere.

What is under test here is **not** the retry taxonomy — ``trappoint_core.retry`` owns that
and ``tests/concurrency/test_retry_taxonomy_spy.py`` watches it. What is under test is the
half the adapter adds: *which connection did each attempt receive, and what happened to the
one that failed*. Those are exactly the questions a live-cluster test answers worst. A
database can tell you a transaction succeeded; only a double can tell you the second
attempt ran on a **new** connection, that the first was rolled back and closed and never
handed out again, and that ``SET TRANSACTION ISOLATION LEVEL SERIALIZABLE`` was the first
statement of every attempt rather than of the first.

So every connection here is a recording double satisfying
:class:`~trappoint_testkit.txn.TransactionalConnection`, every failure is a real
``psycopg.Error`` subclass carrying a chosen SQLSTATE — a duck type would slip past
``run_gate``, which catches ``psycopg.Error`` and never ``Exception`` — and the clock, the
sleep and the jitter source are all injected, so the ladder is asserted without being
spent. The live half of this claim, against a real ``40001`` from a real cluster, is
``tests/concurrency/test_seed_permit_needs_retry.py``. Neither substitutes for the other.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Any

import psycopg
import pytest

pytest.importorskip(
    "trappoint_core",
    reason=(
        "trappoint_testkit.txn is an adapter over `trappoint_core.retry.run_gate`; without "
        "the substrate there is nothing to adapt. `uv sync --package trappoint-core` "
        "installs it. A SKIP IS NOT EVIDENCE."
    ),
)

from psycopg.pq import TransactionStatus
from trappoint_testkit.txn import (
    ISOLATION_SQL,
    ConnectionNotFresh,
    TransactionNotCommittable,
    from_dsn,
    run_txn,
)

from trappoint_core.errors import (
    REFUSAL_SQLSTATES,
    RETRYABLE_SQLSTATE,
    AuthorisationDenied,
    GateRefused,
    RetryBudgetExhausted,
    UnmodelledRefusal,
)
from trappoint_core.retry import RecordingObserver, RetryPolicy

#: A ladder whose ceilings are exact powers of the base until the cap bites, so a
#: deterministic jitter source makes the delays themselves an exact expectation.
LADDER = RetryPolicy(max_attempts=5, base_delay_s=0.02, cap_delay_s=0.1)

#: `base·2ⁿ` for n = 0..3, clipped at the cap. Written out rather than computed, so this
#: test disagrees with `full_jitter` when `full_jitter` changes instead of following it.
LADDER_CEILINGS = [0.02, 0.04, 0.08, 0.1]


class _Refusal(psycopg.Error):
    """A driver-shaped exception carrying a chosen SQLSTATE.

    A real ``psycopg.Error`` subclass, for the reason ``test_retry_taxonomy_spy.py`` gives:
    the loop catches ``psycopg.Error`` and never ``Exception``, and a stand-in with the
    right attributes would slip past that deliberate narrowness. ``_sqlstate`` is assigned
    before ``super().__init__`` because psycopg's constructor reads ``self.sqlstate``.
    """

    def __init__(self, sqlstate: str, constraint: str = "fn_permit_merge_gate") -> None:
        """Build a refusal carrying *sqlstate* and the ``refused by`` clause."""
        self._sqlstate = sqlstate
        super().__init__(f"TRAPPOINT_REF: refused by mainline.{constraint}")

    @property
    def sqlstate(self) -> str:  # type: ignore[override]
        """The code the loop discriminates on."""
        return self._sqlstate


class _Ceilings(random.Random):
    """A jitter source that always returns the top of the range.

    Full jitter draws ``U(0, ceiling)``; a source that returns the ceiling turns the
    ladder from a distribution into an exact list, so :data:`LADDER_CEILINGS` can be
    asserted element by element. Asserting ``0 <= delay <= cap`` would pass against a
    ladder that had stopped doubling.
    """

    def uniform(self, a: float, b: float) -> float:
        """Return the top of the range rather than a draw from it."""
        del a  # full jitter's low end is always 0.0; the ceiling is what is being asserted
        return b


@dataclass
class _Info:
    """The one connection attribute the adapter reads."""

    transaction_status: int = int(TransactionStatus.IDLE)


@dataclass
class _Conn:
    """A connection-shaped recorder. One instance per attempt, and it says which one it was."""

    serial: int
    autocommit: bool = False
    info: _Info = field(default_factory=_Info)
    statements: list[str] = field(default_factory=list)
    commits: int = 0
    rollbacks: int = 0
    closes: int = 0

    def execute(self, query: Any, params: Any = None) -> Any:
        """Record the statement and enter a transaction, as a real connection would."""
        del params
        self.statements.append(str(query))
        self.info.transaction_status = int(TransactionStatus.INTRANS)
        return self

    def commit(self) -> None:
        """Record a commit and leave the transaction."""
        self.commits += 1
        self.info.transaction_status = int(TransactionStatus.IDLE)

    def rollback(self) -> None:
        """Record a rollback and leave the transaction."""
        self.rollbacks += 1
        self.info.transaction_status = int(TransactionStatus.IDLE)

    def close(self) -> None:
        """Record a close."""
        self.closes += 1

    @property
    def discarded(self) -> bool:
        """Rolled back and closed: what must happen to a connection that did not commit."""
        return self.rollbacks >= 1 and self.closes >= 1


@dataclass
class _Pool:
    """A factory that mints a NEW recorder per call and keeps every one it minted."""

    handed_out: list[_Conn] = field(default_factory=list)
    autocommit: bool = False
    already_in_transaction: bool = False

    def __call__(self) -> _Conn:
        """Hand out a connection nothing has touched — unless the test asked otherwise."""
        conn = _Conn(serial=len(self.handed_out), autocommit=self.autocommit)
        if self.already_in_transaction:
            conn.info.transaction_status = int(TransactionStatus.INTRANS)
        self.handed_out.append(conn)
        return conn


def _fails_then_succeeds(sqlstate: str, times: int) -> Any:
    """A whole-transaction callable that raises *sqlstate* *times* times, then commits."""
    seen: list[_Conn] = []

    def work(conn: _Conn) -> str:
        seen.append(conn)
        conn.execute("INSERT INTO mainline.permit (permit_id) VALUES ('…')")
        if len(seen) <= times:
            conn.info.transaction_status = int(TransactionStatus.INERROR)
            raise _Refusal(sqlstate)
        return f"committed on attempt {len(seen)}"

    work.seen = seen  # type: ignore[attr-defined]
    return work


# ═════════════════════════════════════════════════════════════════════════════════════
# an already-open connection is not accepted, in any of the three ways it could arrive
# ═════════════════════════════════════════════════════════════════════════════════════


def test_a_connection_passed_where_a_factory_belongs_is_refused() -> None:
    """The primary misuse: hand over the connection you already opened.

    It cannot be expressed as a type error alone — a caller writes ``run_txn(conn, work)``
    and Python is happy — so the adapter refuses it at runtime and says, in the message,
    why the retry could not have worked: §2.1 retries the whole transaction from ``BEGIN``.
    """
    conn = _Conn(serial=0)
    conn.execute("SELECT 1")  # it is open, which is exactly the problem

    with pytest.raises(ConnectionNotFresh) as raised:
        run_txn(conn, lambda c: c.execute("SELECT 1"))  # type: ignore[arg-type]

    assert "FACTORY" in str(raised.value)
    assert "spec/errors.md §2.1" in str(raised.value)
    assert conn.commits == 0, "a connection the adapter refused was nevertheless committed"


def test_a_factory_that_returns_an_open_connection_is_refused() -> None:
    """The subtler misuse: a factory that hands back one long-lived connection."""
    pool = _Pool(already_in_transaction=True)

    with pytest.raises(ConnectionNotFresh) as raised:
        run_txn(pool, lambda c: c.execute("SELECT 1"))

    assert "ALREADY INSIDE" in str(raised.value)
    assert len(pool.handed_out) == 1
    assert pool.handed_out[0].commits == 0


def test_an_autocommit_connection_is_refused() -> None:
    """Autocommit means every statement is its own transaction; there is nothing to retry."""
    pool = _Pool(autocommit=True)

    with pytest.raises(ConnectionNotFresh) as raised:
        run_txn(pool, lambda c: c.execute("SELECT 1"))

    assert "AUTOCOMMIT" in str(raised.value)


def test_from_dsn_will_not_build_an_autocommit_factory() -> None:
    """The convenience refuses the same misuse before a socket is ever opened."""
    with pytest.raises(ConnectionNotFresh):
        from_dsn("postgresql://nowhere/none", autocommit=True)


# ═════════════════════════════════════════════════════════════════════════════════════
# 40001 is retried, and the retried unit is the WHOLE transaction on a NEW connection
# ═════════════════════════════════════════════════════════════════════════════════════


def test_40001_is_retried_on_a_fresh_connection_each_time() -> None:
    """Two conflicts, three attempts, three connections — and no connection reused.

    The count of connections is the assertion that matters. A retry that reran the work on
    the connection whose transaction CockroachDB has just aborted would replay statements
    into a poisoned transaction, which ``spec/errors.md`` §2.1 says is not a retry of
    anything; it would also produce the same ``40001`` five times and call it diligence.
    """
    pool = _Pool()
    spy = RecordingObserver()
    work = _fails_then_succeeds(RETRYABLE_SQLSTATE, times=2)

    result = run_txn(
        pool, work, policy=LADDER, observer=spy, rng=_Ceilings(0), sleep=lambda _: None
    )

    assert result == "committed on attempt 3"
    assert len(pool.handed_out) == 3, "the attempts did not each get their own connection"
    assert [c.serial for c in work.seen] == [0, 1, 2], "a connection was handed out twice"
    assert [c.commits for c in pool.handed_out] == [0, 0, 1]
    assert all(c.discarded for c in pool.handed_out[:2]), (
        "a connection whose transaction failed was not rolled back and closed"
    )
    assert pool.handed_out[2].closes == 1, "the committed connection was not closed"
    assert spy.attempts_for(RETRYABLE_SQLSTATE) == 2
    assert spy.successes == [2]
    assert not spy.refusals, "a retryable conflict was recorded as a refusal"


def test_the_isolation_level_is_stated_first_on_every_attempt() -> None:
    """§2.1: explicit on every gate transaction, never inherited from a pool default.

    On *every* attempt, not merely the first: a retry that inherited the level would be a
    transaction nobody chose the isolation of, and CockroachDB Cloud's default is not this
    repository's to set.
    """
    pool = _Pool()
    work = _fails_then_succeeds(RETRYABLE_SQLSTATE, times=2)

    run_txn(pool, work, policy=LADDER, rng=_Ceilings(0), sleep=lambda _: None)

    assert len(pool.handed_out) == 3
    for conn in pool.handed_out:
        assert conn.statements[0] == ISOLATION_SQL, (
            f"attempt {conn.serial} began with {conn.statements[:1]}, not the isolation level"
        )


# ═════════════════════════════════════════════════════════════════════════════════════
# a decision is not a conflict: each refusal is attempted exactly once, ever
# ═════════════════════════════════════════════════════════════════════════════════════


@pytest.mark.parametrize("sqlstate", sorted(REFUSAL_SQLSTATES))
def test_each_refusal_sqlstate_is_attempted_exactly_once(sqlstate: str) -> None:
    """One attempt, one connection, no commit — the ledger records one decision, not five.

    ``spec/errors.md`` §4 gives the reason and it is evidentiary: a client that retries a
    ``23514`` writes five identical refusals for one attempted history, and the count of
    refusals stops being a count of anything.
    """
    pool = _Pool()
    spy = RecordingObserver()
    work = _fails_then_succeeds(sqlstate, times=99)

    with pytest.raises(GateRefused) as raised:
        run_txn(
            pool,
            work,
            subject_kind="permit",
            subject_id="dec0de00-0007-4000-8000-000000000001",
            policy=LADDER,
            observer=spy,
            rng=_Ceilings(0),
            sleep=lambda _: None,
        )

    assert raised.value.sqlstate == sqlstate
    assert len(pool.handed_out) == 1, (
        f"{sqlstate} was attempted on {len(pool.handed_out)} connections; the contract is once, "
        "ever — and a second connection is a second attempt however it is spelled"
    )
    assert spy.attempts_for(sqlstate) == 1
    assert spy.retries == [], f"{sqlstate} was retried: {spy.retries}"
    assert pool.handed_out[0].commits == 0
    assert pool.handed_out[0].discarded


def test_42501_is_denial_and_is_not_retried() -> None:
    """The writer never reached the gate. Retrying a permission failure changes nothing."""
    pool = _Pool()
    work = _fails_then_succeeds("42501", times=99)

    with pytest.raises(AuthorisationDenied):
        run_txn(pool, work, policy=LADDER, rng=_Ceilings(0), sleep=lambda _: None)

    assert len(pool.handed_out) == 1
    assert pool.handed_out[0].discarded


def test_an_unmodelled_sqlstate_is_surfaced_as_itself() -> None:
    """A code outside the five is not silently treated as retryable, or as a refusal."""
    pool = _Pool()
    work = _fails_then_succeeds("22012", times=99)  # division_by_zero: a defect, not a verdict

    with pytest.raises(UnmodelledRefusal):
        run_txn(pool, work, policy=LADDER, rng=_Ceilings(0), sleep=lambda _: None)

    assert len(pool.handed_out) == 1


def test_a_defect_in_the_callable_propagates_as_itself() -> None:
    """An ``AttributeError`` in the caller's own code is not a database verdict.

    ``run_gate`` catches ``psycopg.Error`` and never ``Exception`` precisely so that this
    stays true; the adapter must not widen it. The connection is still discarded, because
    a leaked connection holding locks would make the NEXT test's conflict inexplicable.
    """
    pool = _Pool()

    def work(conn: _Conn) -> None:
        conn.execute("SELECT 1")
        raise AttributeError("the caller's payload builder is broken")

    with pytest.raises(AttributeError):
        run_txn(pool, work, policy=LADDER, rng=_Ceilings(0), sleep=lambda _: None)

    assert len(pool.handed_out) == 1, "a defect in the callable was retried as if it were 40001"
    assert pool.handed_out[0].discarded


# ═════════════════════════════════════════════════════════════════════════════════════
# the ladder, asserted without being spent
# ═════════════════════════════════════════════════════════════════════════════════════


def test_the_backoff_ladder_doubles_to_the_cap_and_the_last_attempt_does_not_sleep() -> None:
    """Capped exponential backoff with full jitter, injected sleep, deterministic draw."""
    pool = _Pool()
    delays: list[float] = []
    work = _fails_then_succeeds(RETRYABLE_SQLSTATE, times=99)

    with pytest.raises(RetryBudgetExhausted):
        run_txn(pool, work, policy=LADDER, rng=_Ceilings(0), sleep=delays.append)

    assert delays == LADDER_CEILINGS, (
        f"the ladder was {delays}, not {LADDER_CEILINGS}: the ceiling must double from "
        "base_delay_s until cap_delay_s bites"
    )
    assert len(delays) == LADDER.max_attempts - 1, (
        "the loop slept after the attempt that exhausted the budget, which spends the "
        "caller's deadline on a wait that precedes nothing"
    )
    assert len(pool.handed_out) == LADDER.max_attempts


def test_the_retry_budget_exhausted_is_surfaced_and_never_reported_as_success() -> None:
    """An undecided transaction is not a refusal and is certainly not a commit.

    ``spec/errors.md`` §5: RETRY-class outcomes are not payloads. The adapter's whole
    contribution would be undone by an ``except RetryBudgetExhausted: return None`` — the
    caller would read a success for a transaction the database never decided.
    """
    pool = _Pool()
    spy = RecordingObserver()
    work = _fails_then_succeeds(RETRYABLE_SQLSTATE, times=99)

    with pytest.raises(RetryBudgetExhausted) as raised:
        run_txn(pool, work, policy=LADDER, observer=spy, rng=_Ceilings(0), sleep=lambda _: None)

    assert raised.value.attempts == LADDER.max_attempts
    assert not spy.refusals, "an exhausted budget was recorded as a decision the gate made"
    assert all(c.commits == 0 for c in pool.handed_out)
    assert all(c.discarded for c in pool.handed_out)


# ═════════════════════════════════════════════════════════════════════════════════════
# the callable owns the statements; the adapter owns the transaction
# ═════════════════════════════════════════════════════════════════════════════════════


def test_a_callable_that_commits_for_itself_is_refused() -> None:
    """Half a unit cannot be retried: the durable half would be replayed."""
    pool = _Pool()

    def work(conn: _Conn) -> None:
        conn.execute("INSERT INTO mainline.permit_event (seq) VALUES (1)")
        conn.commit()

    with pytest.raises(TransactionNotCommittable) as raised:
        run_txn(pool, work, policy=LADDER, rng=_Ceilings(0), sleep=lambda _: None)

    assert "no transaction open" in str(raised.value)
    assert pool.handed_out[0].discarded


def test_a_callable_that_swallows_a_database_error_is_refused() -> None:
    """``COMMIT`` on a failed transaction is a ``ROLLBACK``, so this cannot be allowed to pass.

    This is the case that would otherwise be invisible: the callable catches the refusal,
    returns a value, the adapter commits nothing at all, and the caller reads a success for
    a transaction that wrote no rows. It is the same defect class as a blanket ``except``
    and it is refused by name.
    """
    pool = _Pool()

    def work(conn: _Conn) -> str:
        conn.execute("INSERT INTO mainline.disposition (check_id) VALUES ('…')")
        try:
            raise _Refusal("23514", "gate_closed_when_issued")
        except psycopg.Error:
            conn.info.transaction_status = int(TransactionStatus.INERROR)
            return "swallowed"

    with pytest.raises(TransactionNotCommittable) as raised:
        run_txn(pool, work, policy=LADDER, rng=_Ceilings(0), sleep=lambda _: None)

    assert "IN ERROR" in str(raised.value)
    assert pool.handed_out[0].commits == 0
