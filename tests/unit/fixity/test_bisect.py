# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
"""PELT bracketing and the skip-aware search — and the range it refuses to name."""

from __future__ import annotations

import uuid
from decimal import Decimal
from fractions import Fraction

import pytest
from mainline_fixity import (
    BisectBracketEmpty,
    BisectOutcome,
    ProbeResult,
    bisect_culprit,
    bracket_last_regression,
    pelt,
)


def series(*values: int) -> list[Decimal]:
    return [Decimal(v) for v in values]


def elements(n: int) -> list[uuid.UUID]:
    return [uuid.uuid5(uuid.NAMESPACE_OID, f"element-{i}") for i in range(n)]


# ── PELT ─────────────────────────────────────────────────────────────────────


def test_a_sustained_regression_produces_one_changepoint():
    values = series(*([0] * 10 + [1] * 10))
    assert pelt(values) == (10,)


def test_an_isolated_flip_is_suppressed_by_the_default_penalty():
    # The derivation in DEFAULT_PENALTY's docstring: an isolated single flip has a
    # cost reduction approaching 1, and splitting it out costs 2*penalty.
    values = series(*([0] * 10 + [1] + [0] * 10))
    assert pelt(values) == ()


def test_lowering_the_penalty_admits_the_isolated_flip():
    values = series(*([0] * 10 + [1] + [0] * 10))
    assert pelt(values, penalty=Fraction(1, 8)) != ()


def test_pelt_is_bit_identical_across_runs():
    values = series(3, 3, 3, 3, 9, 9, 9, 9, 3, 3, 3, 3, 9, 9, 9, 9)
    assert pelt(values) == pelt(values) == pelt(list(values))


def test_a_flat_series_has_no_changepoint():
    assert pelt(series(*([7] * 12))) == ()


def test_an_empty_series_refuses():
    with pytest.raises(ValueError, match="at least one observation"):
        pelt([])


def test_a_zero_penalty_refuses():
    with pytest.raises(ValueError, match="positive"):
        pelt(series(1, 2, 3), penalty=Fraction(0))


# ── bracketing ───────────────────────────────────────────────────────────────


def test_the_bracket_is_the_most_recent_regression():
    # good -> bad -> good -> bad. Controls are lost and restored, so monotonicity
    # does not hold globally and the last transition is the one to search.
    values = series(*([0] * 6 + [1] * 6 + [0] * 6 + [1] * 6))
    bracket = bracket_last_regression(values, worse="higher")
    assert bracket is not None
    assert (bracket.lo, bracket.hi) == (17, 18)


def test_worse_direction_comes_from_the_registry_not_the_data():
    values = series(*([1] * 6 + [0] * 6))
    # A DECREASE is the dangerous move when higher is safer.
    assert bracket_last_regression(values, worse="lower") is not None
    # The same series, read as though higher were dangerous, brackets nothing.
    assert bracket_last_regression(values, worse="higher") is None


def test_no_regression_returns_none_which_is_not_no_drift():
    assert bracket_last_regression(series(*([0] * 12)), worse="higher") is None


# ── the search ───────────────────────────────────────────────────────────────


def probe_from(good_until: int, skips: frozenset[int] = frozenset()):
    ids = elements(9)
    index = {value: position for position, value in enumerate(ids)}

    def probe(element: uuid.UUID) -> ProbeResult:
        position = index[element]
        if position in skips:
            return ProbeResult.SKIP
        return ProbeResult.GOOD if position <= good_until else ProbeResult.BAD

    return ids, probe


def test_the_search_converges_on_the_first_bad_element():
    ids, probe = probe_from(good_until=4)
    outcome = bisect_culprit(ids, probe)
    assert outcome.culprit == ids[5]
    assert not outcome.is_range
    assert outcome.probes >= 3


def test_a_skipped_midpoint_is_walked_outward_and_the_search_still_converges():
    ids, probe = probe_from(good_until=2, skips=frozenset({4}))
    outcome = bisect_culprit(ids, probe)
    assert outcome.culprit == ids[3]
    assert outcome.skipped >= 1
    assert outcome.probes >= 5


def test_an_unobservable_deciding_element_yields_a_range_rather_than_its_neighbour():
    # 0-4 good, 5-8 bad, and element 4 cannot be probed. The culprit is 4 or 5 and
    # the archive cannot say which. Naming 5 -- the one we happen to have probed --
    # would be fabricating a culprit from an unobservable interval.
    ids, probe = probe_from(good_until=4, skips=frozenset({4}))
    outcome = bisect_culprit(ids, probe)
    assert outcome.is_range
    assert (outcome.lo, outcome.hi) == (ids[3], ids[5])


def test_an_entirely_unobservable_interval_returns_a_range_and_no_culprit():
    ids, probe = probe_from(good_until=4, skips=frozenset(range(1, 8)))
    outcome = bisect_culprit(ids, probe)
    assert outcome.is_range
    assert outcome.culprit is None
    assert (outcome.lo, outcome.hi) == (ids[0], ids[8])
    assert outcome.skipped == 7


def test_an_outcome_cannot_hold_both_a_culprit_and_a_range():
    with pytest.raises(ValueError, match="either a culprit or a range"):
        BisectOutcome(culprit=elements(1)[0], lo=elements(2)[0], hi=None, probes=1, skipped=0)


def test_endpoints_are_probed_not_assumed():
    ids = elements(9)
    # Every element is BAD: the bracket's own claim that ids[0] is good is false,
    # so a binary search over this predicate would return an arbitrary element.
    outcome_probe = dict.fromkeys(ids, ProbeResult.BAD)
    with pytest.raises(ValueError, match="contradict the bracket"):
        bisect_culprit(ids, lambda e: outcome_probe[e])


def test_a_bracket_with_fewer_than_two_candidates_refuses():
    with pytest.raises(BisectBracketEmpty):
        bisect_culprit(elements(1), lambda _e: ProbeResult.GOOD)


def test_the_probe_sequence_is_fixed():
    calls_a: list[int] = []
    calls_b: list[int] = []
    ids = elements(9)
    index = {value: position for position, value in enumerate(ids)}

    def make(sink: list[int]):
        def probe(element: uuid.UUID) -> ProbeResult:
            position = index[element]
            sink.append(position)
            if position in (3, 4, 5):
                return ProbeResult.SKIP
            return ProbeResult.GOOD if position <= 4 else ProbeResult.BAD

        return probe

    first = bisect_culprit(ids, make(calls_a))
    second = bisect_culprit(ids, make(calls_b))
    assert calls_a == calls_b
    assert first == second
