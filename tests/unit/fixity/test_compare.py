# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
"""As-documented against as-operated: the six outcomes and the one that was a bug."""

from __future__ import annotations

import dataclasses
from decimal import Decimal

import pytest
from fixity_corpus import COMMIT, HISTORIAN_BAR, binding, gas_test_cat, observation
from mainline_domain.contracts import ControlDelta
from mainline_fixity import ErrorBar, MissingErrorBar, Reason, compare_fixity


def test_a_real_weakening_is_a_determinate_drift_finding(registry):
    result = compare_fixity(
        gas_test_cat("10"),
        observation(gas_test_cat("14"), err_bar=HISTORIAN_BAR),
        registry,
        COMMIT,
        binding=binding(),
    )
    assert result.reason is Reason.DRIFT
    assert result.direction is ControlDelta.WEAKEN
    assert not result.undetermined
    assert result.is_finding
    assert result.opens_warrant
    assert [w.rule_id for w in result.witnesses] == ["R2_SETPOINT"]


def test_a_difference_inside_the_corridor_is_undetermined_and_keeps_its_arithmetic(registry):
    result = compare_fixity(
        gas_test_cat("10"),
        observation(gas_test_cat("10.5"), err_bar=HISTORIAN_BAR),
        registry,
        COMMIT,
        binding=binding(),
    )
    assert result.reason is Reason.BELOW_CORRIDOR
    assert result.undetermined
    assert result.direction is None
    assert result.bounded_negative is not None
    # A bounded negative is a limitation of the instrument, not a discordance of
    # the record. It opens no warrant, or a superintendent's queue fills with the
    # historian's compression settings until they stop reading it.
    assert not result.opens_warrant


def test_the_corridor_does_not_excuse_a_verdict_that_rests_on_another_rule(registry):
    # THE REGRESSION THIS FILE EXISTS FOR. The setpoint moves half a point (inside
    # the corridor) AND the countersignature requirement vanishes. R2 and R6 each
    # independently produce `weaken`, so the MINIMAL unsatisfiable subset keeps
    # only R2 -- and a corridor test keyed on the minimal set would have discarded
    # the missing countersignature as "indistinguishable from compression".
    observed = dataclasses.replace(gas_test_cat("10.5"), verification=())
    result = compare_fixity(
        gas_test_cat("10"),
        observation(observed, err_bar=HISTORIAN_BAR),
        registry,
        COMMIT,
        binding=binding(),
    )
    assert result.reason is Reason.DRIFT
    assert result.direction is ControlDelta.WEAKEN
    assert not result.undetermined


def test_a_verification_drop_alone_is_never_excused_by_a_corridor(registry):
    observed = dataclasses.replace(gas_test_cat("10"), verification=())
    result = compare_fixity(
        gas_test_cat("10"),
        observation(observed, err_bar=HISTORIAN_BAR),
        registry,
        COMMIT,
        binding=binding(),
    )
    assert result.reason is Reason.DRIFT
    assert result.direction is ControlDelta.WEAKEN


def test_agreement_produces_no_finding(registry):
    result = compare_fixity(
        gas_test_cat("10"),
        observation(gas_test_cat("10"), err_bar=HISTORIAN_BAR),
        registry,
        COMMIT,
        binding=binding(),
    )
    assert result.reason is Reason.NO_DRIFT
    assert not result.is_finding
    assert not result.opens_warrant


def test_an_absent_observation_is_undetermined_and_opens_a_warrant(registry):
    result = compare_fixity(gas_test_cat("10"), None, registry, COMMIT, binding=binding())
    assert result.reason is Reason.EVIDENCE_ABSENT
    assert result.undetermined
    assert result.direction is None
    assert result.opens_warrant


def test_a_row_that_asserts_nothing_is_the_same_as_no_row(registry):
    result = compare_fixity(
        gas_test_cat("10"), observation(None), registry, COMMIT, binding=binding()
    )
    assert result.reason is Reason.EVIDENCE_ABSENT
    assert result.undetermined


def test_a_control_the_document_does_not_contain_is_an_introduce_by_the_plant(registry):
    result = compare_fixity(
        None,
        observation(gas_test_cat("10"), err_bar=HISTORIAN_BAR),
        registry,
        COMMIT,
        binding=binding(),
    )
    assert result.reason is Reason.UNDOCUMENTED_CONTROL
    assert result.direction is ControlDelta.INTRODUCE
    assert result.opens_warrant


def test_abstain_resolves_to_weaken(registry):
    # `mystery_parameter` carries no ratified safe-direction clause, so the
    # registry abstains and the lattice resolves that to `weaken` (§8.4 row 6).
    result = compare_fixity(
        gas_test_cat("10", parameter="mystery_parameter"),
        observation(gas_test_cat("14", parameter="mystery_parameter"), err_bar=HISTORIAN_BAR),
        registry,
        COMMIT,
        binding=binding(),
    )
    assert result.direction is ControlDelta.WEAKEN
    assert result.registry_abstained
    assert result.reason is Reason.DRIFT


def test_a_tolerance_band_is_undetermined_rather_than_a_recentring_reported_as_drift(registry):
    documented = gas_test_cat("140", parameter="flange_torque_target")
    observed = gas_test_cat("152", parameter="flange_torque_target")
    result = compare_fixity(
        documented,
        observation(observed, err_bar=HISTORIAN_BAR),
        registry,
        COMMIT,
        binding=binding(),
    )
    assert result.reason is Reason.BAND_NOT_OBSERVABLE
    assert result.undetermined


def test_a_historian_row_with_no_error_bar_refuses_rather_than_answering(registry):
    with pytest.raises(MissingErrorBar, match="vertex of a compression corridor"):
        compare_fixity(
            gas_test_cat("10"),
            observation(gas_test_cat("14"), source_kind="historian", err_bar=None),
            registry,
            COMMIT,
            binding=binding(),
        )


def test_an_inspection_record_needs_no_error_bar(registry):
    # A person writing an inspection record is not a compression corridor.
    result = compare_fixity(
        gas_test_cat("10"),
        observation(gas_test_cat("14"), source_kind="inspection", err_bar=None),
        registry,
        COMMIT,
        binding=binding(),
    )
    assert result.reason is Reason.DRIFT


def test_confidence_is_the_bindings_confidence_and_nothing_else(registry):
    for milli in (120, 940, 1000):
        result = compare_fixity(
            gas_test_cat("10"),
            observation(gas_test_cat("14"), err_bar=HISTORIAN_BAR),
            registry,
            COMMIT,
            binding=binding(confidence_milli=milli),
        )
        assert result.confidence_milli == milli


def test_an_undetermined_comparison_cannot_carry_a_direction():
    from mainline_fixity import FixityComparison

    with pytest.raises(ValueError, match="drop the caveat"):
        FixityComparison(
            direction=ControlDelta.WEAKEN,
            undetermined=True,
            reason=Reason.BELOW_CORRIDOR,
            confidence_milli=900,
            witnesses=(),
            reading=None,
            bounded_negative=None,
            registry_abstained=False,
            decision=None,
        )


def test_a_wider_corridor_swallows_a_larger_difference(registry):
    wide = ErrorBar(exc_dev=Decimal("2"), comp_dev=Decimal("3"), unit="percent")
    result = compare_fixity(
        gas_test_cat("10"),
        observation(gas_test_cat("14"), err_bar=wide),
        registry,
        COMMIT,
        binding=binding(),
    )
    assert result.reason is Reason.BELOW_CORRIDOR
    assert result.bounded_negative is not None
    assert result.bounded_negative.corridor == Decimal("5")
