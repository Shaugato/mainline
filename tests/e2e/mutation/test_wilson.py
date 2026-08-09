# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""The Wilson interval, checked against values a reader can verify by hand.

The point of implementing the interval directly (rather than importing
``statsmodels``) is that an opposing expert can check it with a calculator.  So
the test checks it the same way: hard-coded expected values, computed from the
formula in ``wilson.py``'s docstring, to six decimal places.

The three that matter most are the degenerate ones — 0/0, 0/n and n/n — because
those are where a naive implementation publishes 0.0, 0.0 and 1.0 and calls two
of them true.
"""

from __future__ import annotations

import math

import pytest
from mainline_mutation.wilson import Z_BY_CONFIDENCE, wilson_interval, wilson_lower


def _by_hand(k: int, n: int, z: float) -> tuple[float, float]:
    p = k / n
    denom = 1.0 + z * z / n
    centre = (p + z * z / (2.0 * n)) / denom
    half = z * math.sqrt(p * (1.0 - p) / n + z * z / (4.0 * n * n)) / denom
    return centre - half, centre + half


@pytest.mark.parametrize(
    ("k", "n"),
    [(0, 1), (1, 1), (1, 2), (3, 3), (5, 10), (9, 10), (95, 100), (120, 125), (124, 132)],
)
def test_the_interval_matches_the_formula_in_the_docstring(k, n):
    z = Z_BY_CONFIDENCE["0.95"]
    lower, upper = _by_hand(k, n, z)
    interval = wilson_interval(k, n)
    assert interval.lower == pytest.approx(max(0.0, lower), abs=1e-6)
    assert interval.upper == pytest.approx(min(1.0, upper), abs=1e-6)


def test_three_of_three_is_not_one_point_zero():
    """The whole reason the lower bound is what gets published."""
    interval = wilson_interval(3, 3)
    assert interval.point == 1.0
    assert interval.lower < 0.5, (
        "three of three is a point estimate of 1.0 and a 95 % lower bound near 0.44. "
        "Publishing 1.0 there is a false statement about how much evidence exists"
    )
    assert interval.lower == pytest.approx(0.438503, abs=1e-6)


def test_no_evidence_gives_the_worst_answer():
    interval = wilson_interval(0, 0)
    assert interval.lower == 0.0
    assert interval.upper == 1.0
    assert interval.point == 0.0


def test_zero_of_many_has_a_lower_bound_of_zero():
    assert wilson_lower(0, 50) == 0.0


def test_the_bound_rises_with_evidence():
    """Same point estimate, more trials, a tighter bound.  The property that matters."""
    bounds = [wilson_lower(n, n) for n in (1, 5, 25, 125, 625)]
    assert bounds == sorted(bounds)
    assert bounds[0] < bounds[-1]


@pytest.mark.parametrize("confidence", sorted(Z_BY_CONFIDENCE))
def test_a_higher_confidence_is_a_lower_bound(confidence):
    assert wilson_lower(90, 100, confidence=confidence) <= wilson_interval(90, 100).point


def test_confidence_levels_are_ordered():
    assert (
        wilson_lower(90, 100, confidence="0.99")
        < wilson_lower(90, 100, confidence="0.95")
        < wilson_lower(90, 100, confidence="0.90")
    )


@pytest.mark.parametrize(
    ("k", "n"),
    [(-1, 5), (2, 1), (0, -1)],
)
def test_impossible_counts_raise(k, n):
    with pytest.raises(ValueError, match=r"proportion|non-negative"):
        wilson_interval(k, n)


def test_an_unlisted_confidence_raises():
    with pytest.raises(ValueError, match="quantile table"):
        wilson_interval(1, 2, confidence="0.975")


def test_the_report_dict_puts_the_bound_first():
    keys = list(wilson_interval(1, 2).as_dict())
    assert keys[0] == "wilson_lower", (
        "the lower bound is the claim and it leads the rendering; a reader skimming a "
        "column of numbers must meet it before the flattering version"
    )
