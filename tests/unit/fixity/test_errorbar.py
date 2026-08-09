# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
"""The compression corridor: what an archived value can and cannot establish."""

from __future__ import annotations

from decimal import Decimal

import pytest
from fixity_corpus import HISTORIAN_BAR
from mainline_domain.contracts import Quantity
from mainline_domain.registry.model import SafeDirection
from mainline_fixity import CorridorVerdict, ErrorBar, read_against_corridor


def pct(value: str) -> Quantity:
    return Quantity(
        value=Decimal(value), unit="percent", dimension="dimensionless", reference="none"
    )


def test_corridor_sums_rather_than_root_sum_squares():
    # 0.25 and 0.5 compose in series: the archive step operates on the collector's
    # output. RSS would give 0.559, which is narrower and therefore more confident
    # than the data supports.
    assert HISTORIAN_BAR.corridor() == Decimal("0.75")


def test_difference_inside_the_corridor_is_indistinguishable_not_compliant():
    reading = read_against_corridor(
        pct("10"),
        pct("10.5"),
        SafeDirection.LOWER_IS_SAFER,
        parameter="lel_test_threshold",
        err_bar=HISTORIAN_BAR,
    )
    assert reading.verdict is CorridorVerdict.INDISTINGUISHABLE
    assert not reading.settles
    assert reading.bounded_negative is not None


def test_bounded_negative_states_what_it_does_not_establish():
    reading = read_against_corridor(
        pct("10"),
        pct("10.5"),
        SafeDirection.LOWER_IS_SAFER,
        parameter="lel_test_threshold",
        err_bar=HISTORIAN_BAR,
    )
    assert reading.bounded_negative is not None
    sentence = reading.bounded_negative.statement()
    # The whole point of the record: it carries its own arithmetic AND its own
    # disclaimer. A sentence that said only the first would be read as the second.
    assert "0.75" in sentence
    assert "does not say that no excursion occurred" in sentence
    assert reading.bounded_negative.to_json()["claim"] == "bounded_negative"


def test_a_difference_beyond_the_corridor_in_the_unsafe_direction_exceeds():
    reading = read_against_corridor(
        pct("10"),
        pct("14"),
        SafeDirection.LOWER_IS_SAFER,
        parameter="lel_test_threshold",
        err_bar=HISTORIAN_BAR,
    )
    assert reading.verdict is CorridorVerdict.EXCEEDS
    assert reading.settles
    assert reading.bounded_negative is None


def test_a_difference_beyond_the_corridor_in_the_safe_direction_is_within_safe():
    reading = read_against_corridor(
        pct("10"),
        pct("4"),
        SafeDirection.LOWER_IS_SAFER,
        parameter="lel_test_threshold",
        err_bar=HISTORIAN_BAR,
    )
    assert reading.verdict is CorridorVerdict.WITHIN_SAFE


def test_higher_is_safer_inverts_which_direction_exceeds():
    # min_oxygen_concentration: a DECREASE is the dangerous move.
    down = read_against_corridor(
        pct("19.5"),
        pct("17"),
        SafeDirection.HIGHER_IS_SAFER,
        parameter="min_oxygen_concentration",
        err_bar=HISTORIAN_BAR,
    )
    up = read_against_corridor(
        pct("19.5"),
        pct("21"),
        SafeDirection.HIGHER_IS_SAFER,
        parameter="min_oxygen_concentration",
        err_bar=HISTORIAN_BAR,
    )
    assert down.verdict is CorridorVerdict.EXCEEDS
    assert up.verdict is CorridorVerdict.WITHIN_SAFE


def test_a_tolerance_band_is_not_observable_from_one_archived_vertex():
    reading = read_against_corridor(
        pct("140"),
        pct("152"),
        SafeDirection.TIGHTER_TOLERANCE_IS_SAFER,
        parameter="flange_torque_target",
        err_bar=HISTORIAN_BAR,
    )
    assert reading.verdict is CorridorVerdict.BAND_NOT_OBSERVABLE
    assert not reading.settles


def test_an_abstaining_direction_does_not_get_a_direction_from_the_data():
    reading = read_against_corridor(
        pct("10"),
        pct("14"),
        SafeDirection.ABSTAIN,
        parameter="mystery_parameter",
        err_bar=HISTORIAN_BAR,
    )
    assert reading.verdict is CorridorVerdict.DIRECTION_UNKNOWN
    assert not reading.settles


def test_no_error_bar_means_a_zero_corridor_not_a_skipped_comparison():
    # Correct for a discrete assertion by a person: an inspection record has no
    # compression corridor, and giving it one would suppress real findings.
    reading = read_against_corridor(
        pct("10"), pct("10.1"), SafeDirection.LOWER_IS_SAFER, parameter="lel_test_threshold"
    )
    assert reading.corridor == Decimal(0)
    assert reading.verdict is CorridorVerdict.EXCEEDS


def test_a_negative_deviation_is_refused():
    with pytest.raises(ValueError, match="non-negative"):
        ErrorBar(exc_dev=Decimal("-0.1"), comp_dev=Decimal("0.5"), unit="percent")


def test_a_corridor_in_a_different_reference_frame_is_refused_not_converted():
    gauge = Quantity(
        value=Decimal("50"),
        unit="psi_gauge",
        dimension="[mass] / [length] / [time] ** 2",
        reference="gauge",
    )
    absolute = Quantity(
        value=Decimal("446"),
        unit="kilopascal",
        dimension="[mass] / [length] / [time] ** 2",
        reference="absolute",
    )
    # 50 psig IS 344.7 kPa_g and is NOT 446 kPa(a). Converting one to the other can
    # invert the direction of a setpoint change, so the algebra raises.
    with pytest.raises(Exception, match="reference frame"):
        read_against_corridor(
            gauge, absolute, SafeDirection.LOWER_IS_SAFER, parameter="max_operating_pressure"
        )
