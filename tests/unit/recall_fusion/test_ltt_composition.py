# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""Learn-then-Test, the precision floor, and the composition that keeps them honest.

``tau = max(LTT_tau, precision_floor_tau)``. The recall side wants tau low; the alarm budget
wants it high; taking the maximum means a recall-driven threshold can never breach the
nuisance ceiling. *"A rule that breaches the ceiling is rejected rather than tuned"* stops
being a promise and becomes arithmetic, and this file is where that arithmetic is checked.
"""

from __future__ import annotations

import math

import pytest

from trappoint_recall.fusion.sga import (
    EXCHANGEABILITY_ASSUMPTION,
    AdmissionRefused,
    compose_tau,
    compose_tau_table,
    default_tau_grid,
    hoeffding_bentkus_pvalue,
    learn_then_test_tau,
    precision_floor_tau,
)

# --------------------------------------------------------------------------------------
# The p-value
# --------------------------------------------------------------------------------------


def test_an_observed_risk_at_or_above_alpha_is_never_evidence_against_the_null() -> None:
    assert hoeffding_bentkus_pvalue(0.10, 200, 0.10) == 1.0
    assert hoeffding_bentkus_pvalue(0.30, 200, 0.10) == 1.0


def test_the_p_value_falls_as_the_observed_risk_falls() -> None:
    high = hoeffding_bentkus_pvalue(0.09, 300, 0.10)
    low = hoeffding_bentkus_pvalue(0.01, 300, 0.10)
    assert 0.0 < low < high <= 1.0


def test_the_p_value_falls_as_the_sample_grows() -> None:
    small = hoeffding_bentkus_pvalue(0.02, 50, 0.10)
    large = hoeffding_bentkus_pvalue(0.02, 500, 0.10)
    assert large < small


def test_zero_observed_risk_matches_the_closed_form_hoeffding_term() -> None:
    """With no observed misses the Hoeffding term reduces to ``(1 - alpha) ** n``."""
    n, alpha = 40, 0.10
    assert hoeffding_bentkus_pvalue(0.0, n, alpha) <= (1.0 - alpha) ** n + 1e-12


def test_the_p_value_is_always_a_probability() -> None:
    for risk in (0.0, 0.01, 0.05, 0.099):
        value = hoeffding_bentkus_pvalue(risk, 120, 0.10)
        assert 0.0 <= value <= 1.0 and math.isfinite(value)


@pytest.mark.parametrize(
    ("risk", "n", "alpha"), [(0.5, 0, 0.1), (-0.1, 10, 0.1), (0.5, 10, 0.0), (0.5, 10, 1.0)]
)
def test_malformed_p_value_inputs_are_refused(risk: float, n: int, alpha: float) -> None:
    with pytest.raises(AdmissionRefused):
        hoeffding_bentkus_pvalue(risk, n, alpha)


# --------------------------------------------------------------------------------------
# Learn-then-Test
# --------------------------------------------------------------------------------------


def _precursors(n: int, low: float, high: float) -> list[float]:
    return [low + (high - low) * index / max(1, n - 1) for index in range(n)]


def test_the_selected_threshold_keeps_the_observed_miss_rate_at_or_below_alpha() -> None:
    scores = _precursors(400, 0.30, 0.99)
    result = learn_then_test_tau(scores, alpha=0.10, delta=0.05)
    assert result.certified
    assert result.risk_at_tau <= 0.10
    assert result.p_value_at_tau <= 0.05
    misses = sum(1 for score in scores if score < result.tau)
    assert misses / len(scores) == pytest.approx(result.risk_at_tau)


def test_a_stricter_alpha_yields_a_lower_or_equal_threshold() -> None:
    scores = _precursors(400, 0.30, 0.99)
    lenient = learn_then_test_tau(scores, alpha=0.20, delta=0.05)
    strict = learn_then_test_tau(scores, alpha=0.02, delta=0.05)
    assert strict.tau <= lenient.tau


def test_a_stricter_delta_yields_a_lower_or_equal_threshold() -> None:
    scores = _precursors(120, 0.30, 0.99)
    loose = learn_then_test_tau(scores, alpha=0.10, delta=0.20)
    tight = learn_then_test_tau(scores, alpha=0.10, delta=0.001)
    assert tight.tau <= loose.tau


def test_an_uncertifiable_sample_returns_zero_and_says_it_is_uncertified() -> None:
    """The safe direction. A threshold nobody could certify must not wear a guarantee."""
    result = learn_then_test_tau([0.9, 0.1, 0.2], alpha=0.01, delta=0.001)
    assert result.certified is False
    assert result.tau == 0.0


def test_the_record_carries_the_exchangeability_assumption() -> None:
    result = learn_then_test_tau(_precursors(200, 0.4, 0.95), alpha=0.10, delta=0.05)
    payload = result.to_json()
    assert payload["assumption"] == EXCHANGEABILITY_ASSUMPTION
    assert "exchangeable" in payload["assumption"]
    assert "drift" in payload["assumption"]
    assert payload["method"].startswith("learn_then_test")


def test_an_empty_precursor_set_is_refused() -> None:
    with pytest.raises(AdmissionRefused, match="certificate of nothing"):
        learn_then_test_tau([], alpha=0.1, delta=0.05)


def test_a_raw_score_instead_of_a_calibrated_probability_is_refused() -> None:
    with pytest.raises(AdmissionRefused, match="calibrated probability"):
        learn_then_test_tau([3.4], alpha=0.1, delta=0.05)


def test_a_shuffled_grid_is_refused_because_the_guarantee_depends_on_the_order() -> None:
    with pytest.raises(AdmissionRefused, match="strictly ascending"):
        learn_then_test_tau([0.9], alpha=0.1, delta=0.05, grid=(0.5, 0.2, 0.8))


def test_the_default_grid_spans_the_unit_interval() -> None:
    grid = default_tau_grid()
    assert grid[0] == 0.0 and grid[-1] == 1.0
    assert all(grid[i] < grid[i + 1] for i in range(len(grid) - 1))


# --------------------------------------------------------------------------------------
# The precision floor
# --------------------------------------------------------------------------------------


def test_the_floor_is_the_smallest_threshold_the_alarm_budget_tolerates() -> None:
    routine = [0.02] * 400 + [0.72] * 8
    result = precision_floor_tau(routine, ceiling=0.03)
    assert result.feasible
    assert result.tau > 0.72
    assert result.nuisance_upper <= 0.03


def test_the_bound_is_used_rather_than_the_point_estimate_by_default() -> None:
    """A ceiling cleared only by a point estimate is a ceiling cleared by sampling luck."""
    routine = [0.9] * 1 + [0.1] * 60
    bounded = precision_floor_tau(routine, ceiling=0.03)
    unbounded = precision_floor_tau(routine, ceiling=0.03, bounded=False)
    assert bounded.tau >= unbounded.tau
    assert bounded.bounded is True


def test_a_corpus_that_cannot_clear_the_ceiling_rejects_the_rule_rather_than_tuning_it() -> None:
    routine = [1.0] * 100
    result = precision_floor_tau(routine, ceiling=0.03)
    assert result.feasible is False
    assert result.tau == 1.0


def test_an_empty_negative_control_is_refused() -> None:
    with pytest.raises(AdmissionRefused, match="routine-permit replay"):
        precision_floor_tau([])


# --------------------------------------------------------------------------------------
# The composition
# --------------------------------------------------------------------------------------


def test_the_composed_threshold_is_never_below_either_input() -> None:
    ltt = learn_then_test_tau(_precursors(300, 0.35, 0.99), alpha=0.10, delta=0.05)
    floor = precision_floor_tau([0.05] * 300 + [0.80] * 4, ceiling=0.03)
    composed = compose_tau(ltt, floor, severity=5)
    assert composed.tau >= ltt.tau
    assert composed.tau >= floor.tau
    assert composed.tau == max(ltt.tau, floor.tau)


def test_the_record_names_which_side_bound() -> None:
    ltt = learn_then_test_tau(_precursors(300, 0.35, 0.99), alpha=0.10, delta=0.05)
    quiet_floor = precision_floor_tau([0.01] * 500, ceiling=0.03)
    noisy_floor = precision_floor_tau([0.05] * 300 + [0.95] * 30, ceiling=0.03)
    assert compose_tau(ltt, quiet_floor, severity=5).binding == "learn_then_test"
    assert compose_tau(ltt, noisy_floor, severity=5).binding == "precision_floor"


def test_a_recall_driven_threshold_can_never_breach_the_nuisance_ceiling() -> None:
    """The whole point of the composition, stated as the failure it prevents."""
    permissive_ltt = learn_then_test_tau([0.99] * 200, alpha=0.30, delta=0.20)
    demanding_floor = precision_floor_tau([0.05] * 200 + [0.90] * 20, ceiling=0.03)
    composed = compose_tau(permissive_ltt, demanding_floor, severity=3)
    assert composed.tau >= demanding_floor.tau


def test_a_full_table_composes_and_validates_its_own_monotonicity() -> None:
    per_severity = {}
    for severity, span in ((5, (0.30, 0.99)), (4, (0.40, 0.99)), (3, (0.55, 0.99)),
                           (2, (0.70, 0.99)), (1, (0.80, 0.99))):
        per_severity[severity] = (
            learn_then_test_tau(
                _precursors(300, *span), alpha=0.10, delta=0.05, severity=severity
            ),
            precision_floor_tau([0.01] * 500, ceiling=0.03, severity=severity),
        )
    table, composition = compose_tau_table(per_severity, policy_version="p-1")
    assert table.tau_for(5) <= table.tau_for(4) <= table.tau_for(3)
    assert table.tau_for(3) <= table.tau_for(2) <= table.tau_for(1)
    assert len(composition) == 5
    assert table.to_json()["provenance"]["assumption"] == EXCHANGEABILITY_ASSUMPTION


def test_a_composition_that_slopes_the_wrong_way_is_refused_not_reordered() -> None:
    """A table that had to be sorted into shape measured something other than it claims."""
    per_severity = {
        5: (
            learn_then_test_tau(_precursors(300, 0.90, 0.99), alpha=0.10, delta=0.05),
            precision_floor_tau([0.01] * 500, ceiling=0.03),
        ),
        4: (
            learn_then_test_tau(_precursors(300, 0.20, 0.99), alpha=0.10, delta=0.05),
            precision_floor_tau([0.01] * 500, ceiling=0.03),
        ),
        3: (
            learn_then_test_tau(_precursors(300, 0.20, 0.99), alpha=0.10, delta=0.05),
            precision_floor_tau([0.01] * 500, ceiling=0.03),
        ),
        2: (
            learn_then_test_tau(_precursors(300, 0.20, 0.99), alpha=0.10, delta=0.05),
            precision_floor_tau([0.01] * 500, ceiling=0.03),
        ),
        1: (
            learn_then_test_tau(_precursors(300, 0.20, 0.99), alpha=0.10, delta=0.05),
            precision_floor_tau([0.01] * 500, ceiling=0.03),
        ),
    }
    with pytest.raises(AdmissionRefused, match="LOWERS the evidence bar"):
        compose_tau_table(per_severity)
