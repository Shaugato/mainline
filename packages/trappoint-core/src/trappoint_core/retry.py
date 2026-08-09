# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""The discriminating retry loop. Forty lines, hand-written, and that is the point.

``spec/errors.md`` §4 states the property this module exists to hold:

    A refusal is **attempted exactly once, ever**. Not once per retry budget; once.

The reason is evidentiary, not performance-related. The refusal ledger records
*decisions the gate made*. A client that retries a ``23514`` writes five identical
refusals for one attempted history, and the count of refusals stops being a count of
anything — and an opposing expert reading it sees a system that repeatedly attempted a
write the database had already refused, which is an unhelpful sentence to explain.

**Why no decorator.** ``tenacity``, ``backoff``, ``retrying`` and ``stamina`` are
forbidden imports repository-wide under ``.importlinter`` contract 4. A decorator that
retries "on exception" cannot distinguish an undecided transaction from a decided
refusal, and the difference between those two is the product. Making the policy a
decorator argument also puts it somewhere nobody reads; here it is a loop with five
branches and one screen.

**Full jitter, not equal jitter.** The failure being defended against is N gate workers
colliding on one hot subject and then retrying in lockstep. Equal jitter keeps a
synchronised herd synchronised for its first retry; full jitter — ``U(0, min(cap,
base·2ⁿ))`` — spreads it immediately.

**The spy.** :class:`RecordingObserver` records every attempt, retry and outcome, so the
once-only property is asserted DIRECTLY by the conformance suite rather than inferred
from a passing test. The observer is a parameter rather than a global because two
concurrent gate calls must not share one recording.
"""

from __future__ import annotations

import random
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Protocol

import psycopg

from .errors import (
    DENIED_SQLSTATE,
    REFUSAL_SQLSTATES,
    RETRYABLE_SQLSTATE,
    AuthorisationDenied,
    RetryBudgetExhausted,
    UnmodelledRefusal,
    diagnose,
    gate_refused,
    sqlstate_of,
)

__all__ = [
    "DEFAULT_POLICY",
    "GateObserver",
    "RecordingObserver",
    "RetryPolicy",
    "full_jitter",
    "run_gate",
]


@dataclass(frozen=True, slots=True)
class RetryPolicy:
    """Capped exponential backoff with full jitter, and a bounded attempt count.

    Attributes:
        max_attempts: total attempts including the first. Bounded on purpose: past a
            few hundred milliseconds of contention the honest answer is that something
            is holding a conflicting transaction, and saying so beats retrying under a
            budget the caller's own deadline has already outlived.
        base_delay_s: the first ceiling.
        cap_delay_s: the largest ceiling. §6.5 budgets ``30 ms`` at p95 for one retry
            allowance, so the whole ladder must stay inside a merge's latency budget.
    """

    max_attempts: int = 5
    base_delay_s: float = 0.02
    cap_delay_s: float = 0.5

    def __post_init__(self) -> None:
        """Refuse a policy that cannot hold the property this module exists for."""
        if self.max_attempts < 1:
            raise ValueError("max_attempts must be at least 1: a gate call is attempted")
        if self.base_delay_s < 0 or self.cap_delay_s < self.base_delay_s:
            raise ValueError("delays must satisfy 0 <= base_delay_s <= cap_delay_s")


#: The policy the gate service uses unless a caller has a measured reason not to.
DEFAULT_POLICY: RetryPolicy = RetryPolicy()


def full_jitter(attempt: int, policy: RetryPolicy, rng: random.Random) -> float:
    """Return ``U(0, min(cap, base·2^attempt))`` seconds for a zero-based *attempt*."""
    ceiling = min(policy.cap_delay_s, policy.base_delay_s * (2**attempt))
    return rng.uniform(0.0, ceiling)


class GateObserver(Protocol):
    """What a spy must implement to watch the loop.

    Deliberately four methods rather than one event stream: the conformance assertion is
    "``40001`` was retried and the four refusal codes were not", and a shape that makes
    that a comparison of two lists is a shape that cannot be misread.
    """

    def attempted(self, attempt: int) -> None:
        """Record that an attempt is about to be made, zero-based."""

    def retried(self, attempt: int, sqlstate: str, delay_s: float) -> None:
        """Record that *sqlstate* was judged retryable and a sleep is about to happen."""

    def refused(self, attempt: int, sqlstate: str, constraint: str) -> None:
        """Record that the gate decided; the loop raises immediately afterwards."""

    def succeeded(self, attempt: int) -> None:
        """Record that the operation returned normally."""


@dataclass(slots=True)
class RecordingObserver:
    """A concrete :class:`GateObserver` that records what happened, in order.

    ``refusals`` is the list the once-only assertion reads: exactly one entry, and no
    entry in ``retries`` sharing its SQLSTATE.
    """

    attempts: list[int] = field(default_factory=list)
    retries: list[tuple[int, str, float]] = field(default_factory=list)
    refusals: list[tuple[int, str, str]] = field(default_factory=list)
    successes: list[int] = field(default_factory=list)

    def attempted(self, attempt: int) -> None:
        """Record an attempt."""
        self.attempts.append(attempt)

    def retried(self, attempt: int, sqlstate: str, delay_s: float) -> None:
        """Record a retry and the delay chosen for it."""
        self.retries.append((attempt, sqlstate, delay_s))

    def refused(self, attempt: int, sqlstate: str, constraint: str) -> None:
        """Record a refusal and the exhibit it carried."""
        self.refusals.append((attempt, sqlstate, constraint))

    def succeeded(self, attempt: int) -> None:
        """Record a success."""
        self.successes.append(attempt)

    def attempts_for(self, sqlstate: str) -> int:
        """Return how many times *sqlstate* was met, retried or refused.

        The once-only property is ``attempts_for(code) == 1`` for every code in
        :data:`~trappoint_core.errors.REFUSAL_SQLSTATES`.
        """
        met = [state for _, state, _ in self.retries] + [state for _, state, _ in self.refusals]
        return met.count(sqlstate)


def run_gate[T](
    operation: Callable[[], T],
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
    """Run *operation* under the SQLSTATE contract, retrying ``40001`` and only ``40001``.

    *operation* must be the WHOLE transaction, from ``BEGIN``: ``spec/errors.md`` §2.1
    forbids retrying a statement, because a statement replayed into a poisoned
    transaction is not a retry of anything.

    Args:
        operation: a callable that opens a transaction, does the work and commits.
        subject_kind: carried onto :class:`~trappoint_core.errors.GateRefused`.
        subject_id: carried onto the refusal.
        gate_epoch: the epoch observed when the attempt began, carried onto the refusal.
        policy: the backoff ladder and the attempt bound.
        observer: the spy. ``None`` means nobody is watching.
        sleep: injected so a test can assert the ladder without spending it.
        rng: injected so a test of jitter is reproducible.
        now: injected monotonic clock, for the elapsed time on exhaustion.

    Returns:
        Whatever *operation* returned.

    Raises:
        GateRefused: one of the four refusal codes. Attempted exactly once, ever.
        AuthorisationDenied: ``42501``. The writer never reached the gate.
        UnmodelledRefusal: any other SQLSTATE, or an exception carrying none.
        RetryBudgetExhausted: ``40001`` survived the budget; the transaction is
            undecided, which is not the same thing as refused.
    """
    generator = rng if rng is not None else random.SystemRandom()
    started = now()
    attempt = 0
    while attempt < policy.max_attempts:
        if observer is not None:
            observer.attempted(attempt)
        try:
            result = operation()
        except psycopg.Error as exc:
            # `psycopg.Error`, never `Exception`. Not a style choice: a blanket catch is
            # how a refusal becomes a silence, and a bug inside `operation` — a
            # KeyboardInterrupt, an AttributeError in the caller's payload builder —
            # must propagate as itself rather than be classified as a database verdict.
            state = sqlstate_of(exc)
            if state in REFUSAL_SQLSTATES:
                refusal = gate_refused(
                    exc, subject_kind=subject_kind, subject_id=subject_id, gate_epoch=gate_epoch
                )
                if observer is not None:
                    observer.refused(attempt, refusal.sqlstate, refusal.constraint)
                raise refusal from exc
            if state == DENIED_SQLSTATE:
                raise AuthorisationDenied(diagnose(exc).message) from exc
            if state != RETRYABLE_SQLSTATE:
                raise UnmodelledRefusal(state or "", diagnose(exc).message) from exc
            delay = full_jitter(attempt, policy, generator)
            if observer is not None:
                observer.retried(attempt, state, delay)
            attempt += 1
            if attempt < policy.max_attempts:
                sleep(delay)
        else:
            if observer is not None:
                observer.succeeded(attempt)
            return result
    raise RetryBudgetExhausted(policy.max_attempts, now() - started)
