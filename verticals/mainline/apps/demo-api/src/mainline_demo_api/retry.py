# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
"""``40001``, and only ``40001`` — the whole transaction, retried inside the Lambda.

WHAT THIS MODULE CONFORMS TO, AND WHY IT IS A SECOND COPY OF IT
---------------------------------------------------------------
The specification is ``spec/errors.md`` §2.1 and the reference implementation is
:mod:`trappoint_core.retry`. This module conforms to both and **imports neither**.

That is a hard constraint, not a preference. ``verticals/mainline/apps/demo-api/pyproject.toml``
pins the deployment package's dependencies to ``psycopg==3.3.4`` and
``psycopg-binary==3.3.4`` *and nothing else* — no boto3, no framework, no workspace
package — so that the artefact's behaviour does not depend on what the Lambda runtime
happens to ship this month, and
``tests/test_envelope.py::test_no_web_framework_or_aws_sdk_is_imported`` enforces it by
importing every shipped module in a fresh interpreter and reading the closure. A
``trappoint_core`` import here would either fail at cold start or drag the whole workspace
package into the zip.

A second implementation of a taxonomy is a second thing to keep correct, and this file is
where that cost is paid down rather than denied:

* The taxonomy itself is **not** restated. :data:`RETRYABLE_SQLSTATE`,
  :data:`REFUSAL_SQLSTATES` and :data:`DENIED_SQLSTATE` are imported from
  :mod:`mainline_demo_api.refusal`, which is already this package's executable copy of
  ``spec/errors.md`` and is already what ``gate_run`` and ``transitions`` classify with. So
  there is one set of codes in this package, not two.
* ``tests/test_defeaters.py::test_the_local_retry_and_trappoint_core_agree_on_the_taxonomy``
  drives THIS loop and ``trappoint_core.retry.run_gate`` over the same synthetic errors and
  asserts they classify every code identically. The test may import ``trappoint_core``;
  the runtime may not.

§2.1, OBEYED LITERALLY
----------------------
    retry the **whole transaction**, from ``BEGIN``, never a statement

:func:`run_transaction` takes a callable that IS the whole transaction. A ``run_transaction``
wrapped around one ``execute()`` inside an already-open transaction is not a retry — a
statement replayed into a poisoned transaction is a statement issued after an aborted one,
which ``spec/errors.md`` §1.1 lists as ``25P02``, a client bug, and a defect in its own
right.

    capped exponential backoff **with full jitter**; a bounded attempt count

:func:`full_jitter` is ``U(0, min(cap, base·2ⁿ))``, the same formula and the same defaults
as :class:`trappoint_core.retry.RetryPolicy`. Full jitter rather than equal jitter for the
reason that module gives: the failure being defended against is several judges colliding on
one subject and then retrying in lockstep, and equal jitter keeps a synchronised herd
synchronised through its first retry.

    the isolation level MUST be set explicitly on every gate transaction

That is the *operation's* job, not this loop's, and it is already done —
``transitions._prepare`` and ``gate_run`` each issue ``SET TRANSACTION ISOLATION LEVEL
SERIALIZABLE`` on every attempt. Because the whole transaction is the retried unit, a
re-attempt re-issues it; a loop that retried a statement would inherit whatever the session
last had, which is the auditability §2.1 is protecting.

WHAT IS NEVER RETRIED, AND WHY THAT IS THE PRODUCT
---------------------------------------------------
``23514``, ``23503``, ``23505`` and ``P0001`` are **attempted exactly once, ever**
(``spec/errors.md`` §4). Not once per budget; once. The reason is evidentiary rather than
about speed: ``mainline.refusal_ledger`` records decisions the gate made, and a client that
retries a ``23514`` writes five identical refusals for one attempted history, at which
point the count of refusals stops being a count of anything. ``42501`` is not retried
either — the writer never reached the gate, so there is nothing to re-attempt — and neither
is any unmodelled code. All of them propagate **as themselves**, unwrapped, because this
package already has one place that turns a driver error into a wire payload
(:func:`mainline_demo_api.refusal.diagnose` / :func:`~mainline_demo_api.refusal.classify`)
and a loop that re-typed them would be a second diagnosis able to disagree with the first.
That is the one intended difference from ``trappoint_core.retry``, which raises
``GateRefused``/``AuthorisationDenied``/``UnmodelledRefusal`` because it has no such caller
downstream. The *classification* is identical; only what is done with a decided outcome
differs, and the agreement test asserts the first and states the second.

WHERE IT IS APPLIED
-------------------
``POST /v1/demo/gate-run`` — see :func:`mainline_demo_api.transitions._demo_gate_run`. It
is what two judges press at the same moment, it is the one transaction in this package that
**persists nothing** (every beat is rolled back, proved by a fingerprint taken before and
after), and re-running it is therefore re-running the same read-only question. The
committing transitions — ``merge_permit``, ``sign_disposition``, ``materialise_checks``,
``suspend_permit`` — are deliberately NOT wrapped here: re-sending a merge on a caller's
behalf is how a permit gets issued twice, and ``transitions``' published contract is that
``40001`` on those paths is surfaced as ``503``/``outcome: retry`` and the decision keeps
an author.

40001 IS REPRODUCIBLE ON A SINGLE NODE, so this is not an untested guard dressed as a fix.
CockroachDB v26.2.5 runs ``SERIALIZABLE`` by default and the judge-can-sign lead measured
six deliberate two-connection races over two rows returning ``40001 …
TransactionRetryError: retry txn (RETRY_SERIALIZABLE)`` six times out of six, locally. What
CockroachDB **Cloud** adds is rate and variety — clock-uncertainty restarts, cross-node
latency, ``RETRY_WRITE_TOO_OLD`` — not existence. The Cloud behaviour of this loop is
UNPROVEN and is reported as unproven; local green does not stand in for it.
"""

from __future__ import annotations

import random
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Final, Protocol

import psycopg

from .refusal import DENIED_SQLSTATE, REFUSAL_SQLSTATES, RETRYABLE_SQLSTATE

__all__ = [
    "DEFAULT_POLICY",
    "DENIED_SQLSTATE",
    "REFUSAL_SQLSTATES",
    "RETRYABLE_SQLSTATE",
    "RecordingObserver",
    "RetryBudgetExhausted",
    "RetryObserver",
    "RetryPolicy",
    "classify_for_retry",
    "full_jitter",
    "run_transaction",
]


@dataclass(frozen=True, slots=True)
class RetryPolicy:
    """Capped exponential backoff with full jitter, and a bounded attempt count.

    The three defaults are :class:`trappoint_core.retry.RetryPolicy`'s, unchanged, so that
    the two loops differ in what they raise and in nothing else a reader has to hold in
    their head.

    Attributes:
        max_attempts: total attempts including the first. Bounded on purpose: past a few
            hundred milliseconds of contention the honest answer is that something is
            holding a conflicting transaction, and saying so beats retrying under a budget
            the caller's own deadline — a Lambda timeout, a judge's patience — has already
            outlived.
        base_delay_s: the first ceiling.
        cap_delay_s: the largest ceiling. The whole ladder must stay inside a gate run's
            latency budget; with these defaults the worst case sleep total is
            ``0.02 + 0.04 + 0.08 + 0.16 = 0.30 s`` and the expected total is half of that.
    """

    max_attempts: int = 5
    base_delay_s: float = 0.02
    cap_delay_s: float = 0.5

    def __post_init__(self) -> None:
        """Refuse a policy that cannot hold the property this module exists for."""
        if self.max_attempts < 1:
            raise ValueError(
                "max_attempts must be at least 1: a transaction is ATTEMPTED, and a policy "
                "of zero attempts would make run_transaction a function that never runs "
                "the operation and then reports the budget as exhausted"
            )
        if self.base_delay_s < 0 or self.cap_delay_s < self.base_delay_s:
            raise ValueError("delays must satisfy 0 <= base_delay_s <= cap_delay_s")


#: The policy the demo API uses unless a caller has a measured reason not to.
DEFAULT_POLICY: Final = RetryPolicy()


class RetryBudgetExhausted(RuntimeError):
    """``40001`` survived the whole budget: the transaction is still UNDECIDED.

    Deliberately not any kind of refusal, and it carries no exhibit. A budget spent without
    a decision is a distinct condition and must not be represented as a decision, because
    it is not one (``spec/errors.md`` §5): the gate never said no — it never got to say
    anything. The same distinction :class:`trappoint_core.retry`'s exception of this name
    draws, and the reason both exist.
    """

    def __init__(self, attempts: int, elapsed_s: float) -> None:
        """Build an exhaustion from the attempt count and the wall time spent."""
        super().__init__(
            f"{RETRYABLE_SQLSTATE} after {attempts} attempt(s) in {elapsed_s:.3f}s: the "
            "transaction is undecided, not refused"
        )
        self.attempts = attempts
        self.elapsed_s = elapsed_s


def classify_for_retry(sqlstate: str | None) -> str:
    """Return what this loop does with *sqlstate*, as a word, without running anything.

    ``retry`` for ``40001`` and nothing else; ``refused`` for the four codes that mean the
    gate decided; ``denied`` for ``42501``; ``unmodelled`` for everything else, including
    an exception that carried no SQLSTATE at all.

    Exposed as a pure function so the agreement with :mod:`trappoint_core.retry` can be
    asserted over the whole code space rather than over the handful of codes a test
    happens to synthesise an error for. It is the same predicate :func:`run_transaction`
    branches on — one expression, used twice, so the two cannot drift.
    """
    if sqlstate == RETRYABLE_SQLSTATE:
        return "retry"
    if sqlstate in REFUSAL_SQLSTATES:
        return "refused"
    if sqlstate == DENIED_SQLSTATE:
        return "denied"
    return "unmodelled"


def full_jitter(attempt: int, policy: RetryPolicy, rng: random.Random) -> float:
    """Return ``U(0, min(cap, base·2^attempt))`` seconds for a zero-based *attempt*."""
    ceiling = min(policy.cap_delay_s, policy.base_delay_s * (2**attempt))
    return rng.uniform(0.0, ceiling)


class RetryObserver(Protocol):
    """What a spy must implement to watch this loop.

    The same four methods :class:`trappoint_core.retry.GateObserver` declares, and for the
    same reason: the conformance assertion is "``40001`` was retried and the four refusal
    codes were not", and a shape that makes that a comparison of two lists is a shape that
    cannot be misread.
    """

    def attempted(self, attempt: int) -> None:
        """Record that an attempt is about to be made, zero-based."""

    def retried(self, attempt: int, sqlstate: str, delay_s: float) -> None:
        """Record that ``40001`` was met and a sleep is about to happen."""

    def decided(self, attempt: int, sqlstate: str) -> None:
        """Record that the attempt produced a decided outcome; the loop re-raises at once."""

    def succeeded(self, attempt: int) -> None:
        """Record that the operation returned normally."""


@dataclass(slots=True)
class RecordingObserver:
    """A concrete :class:`RetryObserver` that records what happened, in order.

    ``decisions`` is the list the once-only assertion reads: for every code in
    :data:`REFUSAL_SQLSTATES`, exactly one entry and no entry in ``retries`` sharing it.
    """

    attempts: list[int] = field(default_factory=list)
    retries: list[tuple[int, str, float]] = field(default_factory=list)
    decisions: list[tuple[int, str]] = field(default_factory=list)
    successes: list[int] = field(default_factory=list)

    def attempted(self, attempt: int) -> None:
        """Record an attempt."""
        self.attempts.append(attempt)

    def retried(self, attempt: int, sqlstate: str, delay_s: float) -> None:
        """Record a retry and the delay chosen for it."""
        self.retries.append((attempt, sqlstate, delay_s))

    def decided(self, attempt: int, sqlstate: str) -> None:
        """Record a decided outcome — refused, denied or unmodelled."""
        self.decisions.append((attempt, sqlstate))

    def succeeded(self, attempt: int) -> None:
        """Record a success."""
        self.successes.append(attempt)

    def attempts_for(self, sqlstate: str) -> int:
        """Return how many times *sqlstate* was met, retried or decided.

        The once-only property is ``attempts_for(code) == 1`` for every code in
        :data:`REFUSAL_SQLSTATES`.
        """
        met = [state for _, state, _ in self.retries] + [state for _, state in self.decisions]
        return met.count(sqlstate)


def _sqlstate_of(exc: BaseException) -> str | None:
    """Return the SQLSTATE carried by *exc*, or ``None`` when it carries none.

    Reads the attribute rather than matching on psycopg's exception hierarchy, so this
    works on the driver's classes, on a subclass and on a test double — the same choice
    ``trappoint_core.errors.sqlstate_of`` makes, and the reason a synthetic error is a
    legitimate way to assert the taxonomy.
    """
    state = getattr(exc, "sqlstate", None)
    return state if isinstance(state, str) and state else None


def run_transaction[T](
    operation: Callable[[], T],
    *,
    undecided: Callable[[T], bool] | None = None,
    policy: RetryPolicy = DEFAULT_POLICY,
    observer: RetryObserver | None = None,
    sleep: Callable[[float], None] = time.sleep,
    rng: random.Random | None = None,
    now: Callable[[], float] = time.monotonic,
) -> T:
    """Run *operation* under the SQLSTATE contract, retrying ``40001`` and only ``40001``.

    *operation* must be the WHOLE transaction, from ``BEGIN``: ``spec/errors.md`` §2.1
    forbids retrying a statement, because a statement replayed into a poisoned transaction
    is not a retry of anything. It must also be safe to run more than once — in this
    package that means ``gate_run``, which rolls everything back, and not a committing
    transition.

    Args:
        operation: a callable that opens a transaction, does the work, and commits or
            rolls back. Called up to ``policy.max_attempts`` times.
        undecided: an optional predicate on a RETURNED value. ``gate_run`` catches its own
            ``40001`` in order to return the beats completed so far, so on that path the
            undecided outcome arrives as a payload rather than as an exception; this is how
            such a payload is recognised without this module knowing its shape. ``None``
            means only exceptions can be undecided.
        policy: the backoff ladder and the attempt bound.
        observer: the spy. ``None`` means nobody is watching.
        sleep: injected so a test can assert the ladder without spending it.
        rng: injected so a test of the jitter is reproducible. ``None`` uses
            :class:`random.SystemRandom`.
        now: injected monotonic clock, for the elapsed time reported on exhaustion.

    Returns:
        Whatever *operation* returned. **Including a result the *undecided* predicate is
        still true of, when the budget ran out on that path** — deliberately, and this is
        the one place the two exhaustion behaviours differ. An exception has nothing to
        surface, so exhausting the budget on it raises. A payload has already recorded
        which beats completed and which SQLSTATE stopped it, and ``spec/errors.md`` §5
        wants exactly that surfaced; replacing it with an exception would discard the
        evidence in order to report the same fact less precisely.

    Raises:
        RetryBudgetExhausted: ``40001`` was raised on every attempt. The transaction is
            undecided, which is not the same thing as refused. **Chained from the last
            driver error** (``raise … from exc``), so a caller that would rather answer
            from the database's own exception than learn a second exhaustion type can
            recover it from ``__cause__`` — which is what :func:`transitions._demo_gate_run`
            does, and why the answer a judge gets is unchanged by this loop's existence.
        psycopg.Error: any decided outcome — the four refusal codes, ``42501``, or an
            unmodelled code — re-raised UNCHANGED and after exactly one attempt. This
            package diagnoses those in one place
            (:func:`mainline_demo_api.refusal.diagnose`) and this loop does not become a
            second one.
    """
    generator = rng if rng is not None else random.SystemRandom()
    started = now()
    attempt = 0
    #: The last value *operation* returned that the predicate called undecided, held as a
    #: zero-or-one-element list rather than as ``T | None``: ``T`` may legitimately BE
    #: ``None``, and a sentinel that a valid result can impersonate is the kind of
    #: cleverness that makes an exhausted budget indistinguishable from a successful run.
    pending: list[T] = []
    #: The driver error the last attempt raised, carried so the exhaustion can be chained
    #: from it. A caller with one diagnosis of driver errors then still has one.
    last_error: psycopg.Error | None = None

    while attempt < policy.max_attempts:
        if observer is not None:
            observer.attempted(attempt)
        try:
            result = operation()
        except psycopg.Error as exc:
            # `psycopg.Error`, never `Exception`. Not a style choice: a blanket catch is
            # how a refusal becomes a silence, and a defect inside `operation` — a
            # KeyError in a payload builder, a KeyboardInterrupt — must propagate as
            # itself rather than be classified as a verdict the database never gave.
            state = _sqlstate_of(exc)
            if classify_for_retry(state) != "retry":
                if observer is not None:
                    observer.decided(attempt, state or "")
                raise
            last_error = exc
            delay = full_jitter(attempt, policy, generator)
            if observer is not None:
                observer.retried(attempt, state or RETRYABLE_SQLSTATE, delay)
            attempt += 1
            pending.clear()
            if attempt < policy.max_attempts:
                sleep(delay)
            continue

        if undecided is not None and undecided(result):
            delay = full_jitter(attempt, policy, generator)
            if observer is not None:
                observer.retried(attempt, RETRYABLE_SQLSTATE, delay)
            attempt += 1
            pending[:] = [result]
            if attempt < policy.max_attempts:
                sleep(delay)
            continue

        if observer is not None:
            observer.succeeded(attempt)
        return result

    if pending:
        # The budget ran out on the payload path. Hand back the last undecided result; see
        # the Returns note above for why that beats raising over the top of it.
        return pending[0]
    raise RetryBudgetExhausted(policy.max_attempts, now() - started) from last_error
