# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""THE MINIMALITY PROPERTY, proved against a pure-Python oracle. No database needed.

This is the file the whole package rests on. Everything else can be checked by reading;
"the returned set is irreducible" cannot, because irreducibility is a statement about
every subset of the answer.

The oracle is a synthetic constraint system: a universe of facts and a family of CONFLICT
CORES, where a state is admissible exactly when it contains no core. That predicate is
monotone — adding a fact can only take an admissible state to an inadmissible one — which
is the same shape every gate condition in this substrate has (a counter that counts
obligations, a foreign key whose target is absent, a pin that refuses a change). So the
synthetic oracle is not a toy standing in for the database; it is the same algebra with
the round trips removed.

The assertion is stronger than "QuickXplain returned something plausible":

* the answer is REFUSED (it contains a core), and
* removing ANY ONE element makes it admissible, checked element by element, and
* the answer is EXACTLY one of the inclusion-minimal cores — which follows from the two
  above and is asserted separately, because a proof that is also a test catches the case
  where the two above are checked with the same helper that produced the answer.

`is_minimal_conflict` is deliberately not implemented in terms of QuickXplain. A test that
checked an algorithm against itself would assert nothing.
"""

from __future__ import annotations

import random

import pytest

from trappoint_diagnose.errors import ProbeBudgetExhausted
from trappoint_diagnose.quickxplain import (
    BudgetedOracle,
    is_minimal_conflict,
    quickxplain,
)

TRIALS = 1000
SEED = 20260809


class SyntheticOracle:
    """Admissible exactly when no conflict core is fully present. Monotone by construction."""

    def __init__(self, cores):
        self.cores = [frozenset(core) for core in cores]
        self.calls = 0

    def admissible(self, facts):
        self.calls += 1
        present = frozenset(facts)
        return not any(core <= present for core in self.cores)


def minimal_cores(cores):
    """Cores no other core is a subset of. QuickXplain can only ever return one of these."""
    frozen = {frozenset(core) for core in cores}
    return {c for c in frozen if not any(other < c for other in frozen)}


def random_system(rng):
    """A universe of 2..14 facts and 0..4 cores drawn from it."""
    size = rng.randint(2, 14)
    universe = [f"f{i}" for i in range(size)]
    core_count = rng.randint(0, 4)
    cores = []
    for _ in range(core_count):
        width = rng.randint(1, min(4, size))
        cores.append(frozenset(rng.sample(universe, width)))
    return universe, cores


def test_quickxplain_returns_a_minimal_conflict_on_1000_synthetic_systems():
    rng = random.Random(SEED)
    conflicts = 0
    admissible = 0
    for trial in range(TRIALS):
        universe, cores = random_system(rng)
        oracle = SyntheticOracle(cores)
        answer = quickxplain(universe, oracle)

        if answer is None:
            admissible += 1
            assert oracle.admissible(universe), f"trial {trial}: None claimed for a refused set"
            continue

        conflicts += 1
        verifier = SyntheticOracle(cores)
        shown = sorted(map(sorted, cores))
        assert is_minimal_conflict(answer, verifier), (
            f"trial {trial}: {sorted(answer)} is not irreducible against {shown}"
        )
        assert frozenset(answer) in minimal_cores(cores), (
            f"trial {trial}: {sorted(answer)} is not an inclusion-minimal core"
        )
        assert set(answer) <= set(universe), f"trial {trial}: answer left the universe"

    # Both outcomes must actually occur, or the run proved one branch a thousand times.
    assert conflicts > 0
    assert admissible > 0


def test_a_consistent_system_yields_none_not_an_empty_set():
    # `None` and `()` are different answers and a consumer must be able to tell them
    # apart: nothing explains this refusal, versus the background alone explains it.
    oracle = SyntheticOracle(cores=[])
    assert quickxplain(["a", "b", "c"], oracle) is None


def test_background_alone_inconsistent_yields_the_empty_conflict():
    oracle = SyntheticOracle(cores=[{"bg"}])
    assert quickxplain([], oracle, background=["bg"]) == ()


def test_single_candidate_is_returned_whole():
    oracle = SyntheticOracle(cores=[{"only"}])
    assert quickxplain(["only"], oracle) == ("only",)


def test_the_recursion_prunes_a_branch_it_does_not_need():
    # `a` and `b` conflict; `c`..`h` are irrelevant. The answer must be exactly {a, b},
    # and reaching it must cost fewer calls than examining every candidate one at a time.
    universe = ["a", "b", "c", "d", "e", "f", "g", "h"]
    oracle = SyntheticOracle(cores=[{"a", "b"}])
    answer = quickxplain(universe, oracle)
    assert set(answer) == {"a", "b"}
    assert oracle.calls < len(universe) * 2


def test_duplicate_candidates_do_not_appear_twice_in_the_answer():
    oracle = SyntheticOracle(cores=[{"a"}])
    assert quickxplain(["a", "a", "b", "a"], oracle) == ("a",)


def test_background_facts_are_never_reported_as_candidates():
    # The background is what is already true. A reason set that named it would be telling
    # the reader to remove something they did not add.
    oracle = SyntheticOracle(cores=[{"bg", "x"}])
    answer = quickxplain(["x", "y"], oracle, background=["bg"])
    assert answer == ("x",)


def test_budget_exhaustion_raises_rather_than_returning_a_superset():
    # The core is inside the universe, so the recursion genuinely has work to do; a
    # budget of two calls cannot finish it, and the alternative to raising would be
    # returning an unproven superset labelled as a minimal unsatisfiable subset.
    universe = [f"f{i}" for i in range(12)]
    oracle = BudgetedOracle(SyntheticOracle(cores=[{"f3", "f9"}]), budget=2)
    with pytest.raises(ProbeBudgetExhausted):
        quickxplain(universe, oracle)


def test_a_generous_budget_completes_the_same_answer():
    universe = [f"f{i}" for i in range(12)]
    oracle = BudgetedOracle(SyntheticOracle(cores=[{"f3", "f9"}]), budget=64)
    assert set(quickxplain(universe, oracle) or ()) == {"f3", "f9"}
    assert 0 < oracle.calls <= 64


def test_budget_of_zero_is_refused_at_construction():
    with pytest.raises(ValueError, match="cannot answer any question"):
        BudgetedOracle(SyntheticOracle(cores=[]), budget=0)


def test_budgeted_oracle_reports_what_it_spent():
    inner = SyntheticOracle(cores=[{"a", "b"}])
    oracle = BudgetedOracle(inner, budget=64)
    quickxplain(["a", "b", "c", "d"], oracle)
    assert oracle.calls == inner.calls
    assert oracle.budget == 64


def test_is_minimal_conflict_rejects_a_superset():
    oracle = SyntheticOracle(cores=[{"a"}])
    assert is_minimal_conflict(["a"], oracle)
    assert not is_minimal_conflict(["a", "b"], oracle)


def test_is_minimal_conflict_rejects_an_admissible_set():
    oracle = SyntheticOracle(cores=[{"a"}])
    assert not is_minimal_conflict(["b", "c"], oracle)
