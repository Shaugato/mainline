# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""QuickXplain — the general algorithm, with an oracle it does not get to choose.

Junker's divide-and-conquer conflict extraction, unchanged from the 2004 formulation.
What is not standard is the oracle: in this system ``admissible()`` is answered by
executing the candidate subset against the DATABASE inside a savepoint and reading
whether the constraint engine refused. Because the explanation is produced by the same
mechanism that produced the refusal, **the explanation cannot disagree with the
refusal** — which is the property that makes it evidence rather than a plausible
reconstruction.

Extracting a minimal unsatisfiable subset is a solved problem *with a SAT or SMT solver*.
Using an RDBMS's own constraint engine as the oracle is the part with no prior art I could
find, and it is also the part that removes the most reasonable objection to a solver-based
answer: that the solver's model of the constraints is not the constraints.

**Cost, stated plainly.** QuickXplain is O(k · log(n/k)) oracle calls for a conflict of
size k out of n candidates, against O(n) for a naive linear scan — but every call here is
a round trip and a set of row locks, so the budget is bounded, the caller pays it only on
the refusal path, and the payload reports what it spent in ``probe_calls``. Nothing in
this module runs on the completion path; ``oracle.py`` refuses to construct a probe on a
connection that is already inside a transaction.

Nothing in this module touches a database. The algorithm is pure over an ``Oracle``
Protocol, which is what lets the minimality property be proved against a synthetic
in-memory oracle with no schema in existence — `PL-2`, applied to the one algorithm whose
correctness is not observable from the outside.
"""

from __future__ import annotations

from collections.abc import Hashable, Sequence
from typing import Protocol, runtime_checkable

from .errors import ProbeBudgetExhausted

__all__ = [
    "BudgetedOracle",
    "Oracle",
    "is_minimal_conflict",
    "quickxplain",
]


@runtime_checkable
class Oracle(Protocol):
    """One question, one answer: are exactly these facts jointly admissible.

    The predicate MUST be monotone — adding a fact can only ever take an admissible state
    to an inadmissible one, never the reverse. Every gate condition in this substrate is
    monotone by construction (a counter that counts obligations, a foreign key whose target
    is absent, a pin that refuses a change), so this is a property of the design rather
    than an assumption about the caller. QuickXplain's minimality guarantee does not
    survive a non-monotone oracle, and neither does the meaning of the word "irreducible".
    """

    def admissible(self, facts: Sequence[Hashable]) -> bool:
        """Report whether the transition succeeds with exactly *facts* present."""


class BudgetedOracle:
    """Wraps an oracle, counts calls, and refuses past the budget.

    A separate object rather than a flag inside the algorithm, for two reasons. The count
    is what the payload reports as ``probe_calls``, so it has to survive the recursion
    unwinding. And a budget that lives outside the algorithm can wrap the synthetic
    in-memory oracle in the tests exactly as it wraps the savepoint oracle in production,
    which is how the degradation path gets tested without a database.
    """

    def __init__(self, inner: Oracle, budget: int) -> None:
        """Wrap *inner*, permitting at most *budget* calls."""
        if budget < 1:
            raise ValueError("a budget below one call cannot answer any question")
        self._inner = inner
        self._budget = budget
        self._calls = 0

    @property
    def calls(self) -> int:
        """Oracle calls consumed so far."""
        return self._calls

    @property
    def budget(self) -> int:
        """The cap this wrapper enforces."""
        return self._budget

    def admissible(self, facts: Sequence[Hashable]) -> bool:
        """Delegate to the wrapped oracle, refusing once the budget is spent.

        Raises:
            ProbeBudgetExhausted: the budget is spent. The emitter catches this and
                degrades to ``diagnosis="none"`` with ``naa_reason``
                ``probe_budget_exhausted``, rather than blocking or labelling an unproven
                superset a minimal unsatisfiable subset.
        """
        if self._calls >= self._budget:
            raise ProbeBudgetExhausted(
                f"probe budget of {self._budget} oracle call(s) is spent; the reason set "
                "was not proven minimal, so it must not be labelled one"
            )
        self._calls += 1
        return self._inner.admissible(facts)


def _dedupe[Fact: Hashable](facts: Sequence[Fact]) -> tuple[Fact, ...]:
    seen: set[Fact] = set()
    out: list[Fact] = []
    for fact in facts:
        if fact not in seen:
            seen.add(fact)
            out.append(fact)
    return tuple(out)


def _qx[Fact: Hashable](
    background: tuple[Fact, ...],
    delta_empty: bool,
    candidates: tuple[Fact, ...],
    oracle: Oracle,
) -> tuple[Fact, ...]:
    # Junker's QX(B, Δ, C), with `delta_empty` standing in for `Δ = ∅`.
    #
    # The first test is the whole trick: when the previous split ALREADY made the
    # background inconsistent, nothing in C is needed and the recursion stops without
    # examining it. That is where the log factor comes from, and it is also why the test
    # is skipped when Δ is empty — at the top of the recursion the background has not
    # changed, so asking would waste an oracle call on a question already answered.
    if not delta_empty and not oracle.admissible(background):
        return ()
    if len(candidates) == 1:
        return candidates
    split = len(candidates) // 2
    first, second = candidates[:split], candidates[split:]
    left = _qx(background + first, not first, second, oracle)
    right = _qx(background + left, not left, first, oracle)
    return _dedupe(left + right)


def quickxplain[Fact: Hashable](
    candidates: Sequence[Fact],
    oracle: Oracle,
    *,
    background: Sequence[Fact] = (),
) -> tuple[Fact, ...] | None:
    """Return a minimal subset of *candidates* that is still refused, or None.

    ``None`` means the full set is admissible: there is no conflict here, and a caller
    that received a refusal and then got ``None`` has learned something important — the
    refusal is not explained by these candidates, and emitting a reason set drawn from
    them would be a fabrication.

    An empty tuple means the BACKGROUND alone is refused, so no candidate is needed to
    explain it. That is also a real answer and it is not the same as ``None``.

    The returned tuple is minimal in the strong sense: it is refused, and removing any one
    element makes it admissible. ``is_minimal_conflict()`` re-checks that directly, at a
    cost of one oracle call per element, for a caller who would rather pay than trust.

    Raises:
        ProbeBudgetExhausted: propagated from a budgeted oracle.
    """
    ordered = _dedupe(candidates)
    prior = _dedupe(background)
    if oracle.admissible(prior + ordered):
        return None
    if not ordered:
        return ()
    return _qx(prior, True, ordered, oracle)


def is_minimal_conflict[Fact: Hashable](
    subset: Sequence[Fact],
    oracle: Oracle,
    *,
    background: Sequence[Fact] = (),
) -> bool:
    """Check the minimality property directly: refused, and admissible one element short.

    This is the definition of a minimal unsatisfiable subset written out as code, and it
    is deliberately independent of QuickXplain — a test that checked the algorithm against
    itself would assert nothing. It costs ``len(subset) + 1`` oracle calls, which is why it
    is a verifier rather than the algorithm.
    """
    prior = tuple(background)
    ordered = _dedupe(subset)
    if oracle.admissible(prior + ordered):
        return False
    return all(
        oracle.admissible(prior + tuple(f for f in ordered if f != dropped)) for dropped in ordered
    )
