# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""Interleavings you can shrink, because the schedule is data.

Hypothesis is single-threaded and real anomalies need concurrency. Threads spawned inside
a test give you concurrency and take away shrinking: a forty-step failure stays a
forty-step failure because the interleaving that produced it was never recorded, let
alone reduced.

The resolution is to **generate the schedule**. :func:`interleavings` emits a list of
actor ids; :class:`TxnScheduler` holds one open psycopg 3 connection per actor, each in
its own thread, and passes a token so that exactly one statement is executing at a time,
in the generated order. Because the schedule is ordinary shrinkable Hypothesis data, a
forty-step counterexample reduces to the three-step interleaving that actually breaks the
gate.

This is the achievable form of deterministic simulation against a hosted database. You
cannot determinise CockroachDB's clock, its leaseholders or its internal retries — and
you do not need to, because **the invariant is DB-side**. What you can determinise is
your side of the wire, and that is enough to make a counterexample a recipe.

**BLOCKED is a first-class outcome.** An actor whose statement is still waiting on a lock
past :attr:`TxnScheduler.block_timeout` is recorded ``BLOCKED`` and the scheduler moves
on. Two consequences, both deliberate:

* While an actor is blocked, its statement *is* in flight beside the next actor's. The
  one-statement-at-a-time property is a property of the *unblocked* path, and a scheduler
  that pretended otherwise would deadlock itself on the first lock conflict.
* ``BLOCKED`` is recorded in the trace, so a history that never contended is
  distinguishable from one that did. A concurrency suite in which nothing ever blocked
  has not tested concurrency.

**Why the generated element is an actor id and not an ``(actor_id, step)`` pair.** The
step index of a transaction's next statement is not free: a transaction runs its own
statements in order, so the only legal step for an actor is the one after the last it
executed. Generating it as well would double the search space with values that are either
redundant or invalid, and Hypothesis shrinks a smaller space better. The pairs are still
what a failure report shows — :meth:`Trace.pairs` reconstructs them — so the artefact the
brief asks for is produced, it is simply derived rather than drawn.
"""

from __future__ import annotations

import contextlib
import threading
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any, Final

import psycopg
from hypothesis import strategies as st

from .adapter import verdict_of
from .model import Accept, Refuse, Verdict

__all__ = [
    "ABORTED",
    "BLOCKED",
    "TIMED_OUT",
    "Statement",
    "StepOutcome",
    "Trace",
    "TxnScheduler",
    "interleavings",
]

#: The status of a step whose statement was still waiting on a lock when its turn ended.
BLOCKED = "blocked"
#: ``57014``: the statement waited past ``statement_timeout`` and the server cancelled it.
#: NOT a taxonomy violation — it is the harness's own bound firing, and a scheduler that
#: asserted the gate's taxonomy over it would fail on its own timeout.
TIMED_OUT = "timed-out"
#: ``25P02`` and friends: this actor's transaction is already aborted, so its remaining
#: statements say nothing. Recorded rather than hidden, because a trace full of these is a
#: trace whose later turns proved nothing.
ABORTED = "aborted"

_TAXONOMY: Final = frozenset({"40001", "23514", "23503", "23505", "P0001"})
_TIMEOUT_SQLSTATE: Final = "57014"


@dataclass(frozen=True, slots=True)
class Statement:
    """One statement of one actor's transaction."""

    label: str
    sql: str
    params: tuple[Any, ...] = ()


@dataclass(frozen=True, slots=True)
class StepOutcome:
    """What one scheduled turn produced."""

    actor: int
    step: int
    label: str
    status: str
    """``"ok"``, ``"refused"``, :data:`BLOCKED`, :data:`TIMED_OUT`, :data:`ABORTED`, or
    ``"exhausted"`` when the actor had no statement left to run on its turn."""
    verdict: Verdict | None = None
    detail: str = ""
    """The SQLSTATE and message for a non-taxonomy outcome. Empty otherwise."""

    def __str__(self) -> str:
        """One line of a failure report."""
        tail = f"{self.verdict or ''} {self.detail}".strip()
        return f"a{self.actor}/s{self.step} {self.label}: {self.status} {tail}".rstrip()


def _classify(exc: psycopg.Error) -> tuple[str, Verdict | None, str]:
    """Turn a driver exception into ``(status, verdict, detail)``.

    The gate's refusal taxonomy is asserted in :func:`~trappoint_model.adapter.verdict_of`
    and NOT here. In a scheduler, a cancelled statement and an already-aborted transaction
    are outcomes of the harness's own bounds, and treating them as unmodelled refusals
    would make the concurrency lane fail on its timeouts instead of on the gate.
    """
    sqlstate = exc.sqlstate or ""
    if sqlstate in _TAXONOMY:
        return ("refused", verdict_of(exc), "")
    if sqlstate == _TIMEOUT_SQLSTATE:
        return (TIMED_OUT, None, f"{sqlstate}: waited past statement_timeout")
    return (ABORTED, None, f"{sqlstate}: {str(exc).splitlines()[0]}")


@dataclass(slots=True)
class Trace:
    """The ordered record of a run, and the schedule that produced it."""

    steps: list[StepOutcome] = field(default_factory=list)
    commits: list[StepOutcome] = field(default_factory=list)

    def pairs(self) -> list[tuple[int, int]]:
        """Return the ``[(actor_id, step)]`` form of the schedule actually executed."""
        return [(s.actor, s.step) for s in self.steps]

    def blocked(self) -> int:
        """How many turns ended blocked. Zero means nothing contended."""
        return sum(1 for s in self.steps if s.status == BLOCKED)

    def contended(self) -> bool:
        """Did the two transactions actually meet? Blocked, timed out, or ``40001``."""
        return (
            self.blocked() > 0
            or any(s.status == TIMED_OUT for s in self.steps)
            or any(v.sqlstate == "40001" for v in self.refusals())
        )

    def harness_errors(self) -> list[StepOutcome]:
        """Return the steps that failed inside the harness rather than at the gate.

        Always asserted empty by callers. A concurrency suite that quietly tolerated its
        own exceptions would report green for runs in which nothing was executed.
        """
        return [s for s in [*self.steps, *self.commits] if s.status == "harness-error"]

    def refusals(self) -> list[Refuse]:
        """Every refusal observed, statements and commits alike."""
        return [s.verdict for s in [*self.steps, *self.commits] if isinstance(s.verdict, Refuse)]

    def report(self) -> str:
        """Render the whole trace, one step per line. Printed on every failure."""
        return "\n".join(str(s) for s in [*self.steps, *self.commits])


def interleavings(
    n_actors: int, min_size: int = 1, max_size: int = 24
) -> st.SearchStrategy[list[int]]:
    """Generate a schedule: which actor takes the next turn, repeatedly.

    Args:
        n_actors: how many concurrent transactions the schedule addresses.
        min_size: shortest schedule to generate.
        max_size: longest. Turns beyond an actor's program length are recorded
            ``exhausted`` and cost one round trip of nothing, so a generous bound is
            cheap and lets the generator find late-commit orderings.
    """
    if n_actors < 1:
        raise ValueError("a schedule needs at least one actor")
    return st.lists(
        st.integers(min_value=0, max_value=n_actors - 1), min_size=min_size, max_size=max_size
    )


@dataclass(slots=True)
class _Actor:
    conn: psycopg.Connection[Any]
    program: Sequence[Statement]
    go: threading.Event = field(default_factory=threading.Event)
    done: threading.Event = field(default_factory=threading.Event)
    thread: threading.Thread | None = None
    pc: int = 0
    pending: bool = False
    stop: bool = False
    outcome: tuple[str, Verdict | None, str] = ("ok", None, "")
    pending_step: int = 0
    pending_label: str = ""
    committed: bool = False


class TxnScheduler:
    """M open transactions, one thread each, and a token that says whose turn it is.

    Use as a context manager. Connections must be **autocommit**, and the scheduler
    issues ``BEGIN`` and ``COMMIT`` itself — that is not a detail. A driver-managed
    transaction opens lazily on the first statement and closes on a context-manager exit,
    both of which are events this class has to control to the statement: an interleaving
    is only reproducible if the moment each transaction started is part of the schedule.
    """

    def __init__(
        self,
        connections: Sequence[psycopg.Connection[Any]],
        programs: Sequence[Sequence[Statement]],
        *,
        block_timeout_s: float = 0.75,
        drain_timeout_s: float = 30.0,
        statement_timeout_s: float = 5.0,
        isolation: str = "serializable",
    ) -> None:
        """Bind connections to programs.

        Args:
            connections: one per actor, already open and in AUTOCOMMIT — the scheduler
                issues ``BEGIN`` and ``COMMIT`` itself.
            programs: one statement list per actor; must match ``connections`` in length.
            block_timeout_s: how long a turn waits before the step is called
                :data:`BLOCKED`. Short on purpose — the interesting histories are the ones
                where an actor waits, and a long timeout turns a schedule into a queue.
            drain_timeout_s: how long the teardown waits for a blocked statement to
                finish before giving up on it.
            statement_timeout_s: the server-side bound. A statement that waits forever
                turns an assertion about refusal into a hung suite; when it fires the step
                is :data:`TIMED_OUT`, which is the harness's bound and never a gate
                verdict. Longer than ``block_timeout_s`` by design: BLOCKED must mean
                "still waiting", not "gave up".
            isolation: ``"serializable"`` or ``"read committed"``. Set explicitly on every
                connection, never inherited from a pool default — the READ COMMITTED
                differential is only evidence if the level is stated in the run.

        Raises:
            ValueError: the two sequences disagree in length, or a connection is not in
                autocommit — a driver-managed transaction would open and close outside the
                schedule and the interleaving would not be the one that was generated.
        """
        if len(connections) != len(programs):
            raise ValueError("one program per connection, exactly")
        not_autocommit = [i for i, c in enumerate(connections) if not c.autocommit]
        if not_autocommit:
            raise ValueError(
                f"connections {not_autocommit} are not in autocommit. The scheduler owns "
                "BEGIN and COMMIT; a driver-managed transaction would start on a statement "
                "the schedule did not choose."
            )
        self.block_timeout = block_timeout_s
        self.drain_timeout = drain_timeout_s
        self.statement_timeout = statement_timeout_s
        self.isolation = isolation
        self.actors = [
            _Actor(conn=c, program=p) for c, p in zip(connections, programs, strict=True)
        ]

    # ── lifecycle ──────────────────────────────────────────────────────────────────
    def __enter__(self) -> TxnScheduler:
        """Open one transaction per actor and start its thread."""
        for i, actor in enumerate(self.actors):
            actor.conn.execute(f"SET default_transaction_isolation = '{self.isolation}'")
            actor.conn.execute(f"SET statement_timeout = '{int(self.statement_timeout * 1000)}ms'")
            actor.conn.execute("BEGIN")
            actor.thread = threading.Thread(
                target=self._loop, args=(i,), name=f"txn-actor-{i}", daemon=True
            )
            actor.thread.start()
        return self

    def __exit__(self, *exc: object) -> None:
        """Stop every thread. Transactions are ended by :meth:`finish`, never here."""
        for actor in self.actors:
            actor.stop = True
            actor.go.set()
        for actor in self.actors:
            if actor.thread is not None:
                actor.thread.join(timeout=self.drain_timeout)

    def _loop(self, index: int) -> None:
        """One actor's whole life: wait for the token, run one statement, hand it back.

        ``done`` is set in a ``finally``. An exception that escaped this loop would leave
        the scheduler waiting on an event nobody will ever set, and a concurrency harness
        that hangs is strictly worse than one that fails: nobody reads a job that timed
        out at ninety minutes.
        """
        actor = self.actors[index]
        while True:
            actor.go.wait()
            actor.go.clear()
            if actor.stop:
                return
            statement = actor.program[actor.pc]
            try:
                try:
                    actor.conn.execute(statement.sql, statement.params)
                except psycopg.Error as exc:
                    actor.outcome = _classify(exc)
                except Exception as exc:  # noqa: BLE001 - reported, never swallowed
                    actor.outcome = ("harness-error", None, f"{type(exc).__name__}: {exc}")
                else:
                    actor.outcome = ("ok", Accept(), "")
                actor.pc += 1
            finally:
                actor.done.set()

    # ── the run ────────────────────────────────────────────────────────────────────
    def _collect(self, actor_id: int, step: int, label: str) -> StepOutcome:
        status, verdict, detail = self.actors[actor_id].outcome
        return StepOutcome(actor_id, step, label, status, verdict, detail)

    def run(self, schedule: Sequence[int]) -> Trace:
        """Execute *schedule*, one turn at a time, and return the trace."""
        trace = Trace()
        for actor_id in schedule:
            actor = self.actors[actor_id]
            if actor.pending:
                # A blocked statement gets its turn back: check whether the lock cleared
                # while other actors ran. This is where an interleaving's resolution shows
                # up, so it is recorded as its own step rather than folded into the next.
                if actor.done.wait(0):
                    actor.done.clear()
                    actor.pending = False
                    trace.steps.append(
                        self._collect(actor_id, actor.pending_step, actor.pending_label)
                    )
                else:
                    trace.steps.append(
                        StepOutcome(actor_id, actor.pending_step, actor.pending_label, BLOCKED)
                    )
                continue
            if actor.pc >= len(actor.program):
                trace.steps.append(StepOutcome(actor_id, actor.pc, "", "exhausted"))
                continue
            step = actor.pc
            label = actor.program[step].label
            actor.go.set()
            if actor.done.wait(self.block_timeout):
                actor.done.clear()
                trace.steps.append(self._collect(actor_id, step, label))
            else:
                actor.pending = True
                actor.pending_step = step
                actor.pending_label = label
                trace.steps.append(StepOutcome(actor_id, step, label, BLOCKED))
        return trace

    def finish(self, trace: Trace) -> Trace:
        """End every transaction, in the order that lets a blocked actor make progress.

        The order is the whole of this method and it is not arbitrary:

        1. **Commit the actors that are not blocked.** A blocked actor is usually blocked
           on a lock one of them holds, so committing first is what unblocks it — exactly
           as it would in production. A teardown that drained first would sit until
           ``statement_timeout``, and every trace would end in a timeout that says nothing
           about the gate.
        2. **Drain the blocked actors**, now that the lock has moved.
        3. **Commit those.**

        A ``COMMIT`` is a step like any other: it is where a SERIALIZABLE conflict is
        usually reported, so a harness that swallowed it would miss most of the ``40001``
        it exists to observe.
        """
        for actor_id, actor in enumerate(self.actors):
            if not actor.pending:
                self._end(actor_id, actor, trace)
        for actor_id, actor in enumerate(self.actors):
            if not actor.pending:
                continue
            if actor.done.wait(self.drain_timeout):
                actor.done.clear()
                actor.pending = False
                trace.steps.append(self._collect(actor_id, actor.pending_step, actor.pending_label))
            else:  # pragma: no cover - only on a genuinely stuck cluster
                trace.steps.append(
                    StepOutcome(actor_id, actor.pending_step, actor.pending_label, BLOCKED)
                )
            self._end(actor_id, actor, trace)
        return trace

    def _end(self, actor_id: int, actor: _Actor, trace: Trace) -> None:
        if actor.committed:
            return
        actor.committed = True
        try:
            actor.conn.execute("COMMIT")
        except psycopg.Error as exc:
            status, verdict, detail = _classify(exc)
            trace.commits.append(StepOutcome(actor_id, actor.pc, "COMMIT", status, verdict, detail))
            # The session may already have unwound the transaction itself, in which case
            # the ROLLBACK is redundant rather than wrong.
            with contextlib.suppress(psycopg.Error):
                actor.conn.execute("ROLLBACK")
        else:
            trace.commits.append(StepOutcome(actor_id, actor.pc, "COMMIT", "ok", Accept()))
