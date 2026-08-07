# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""``compare`` is the one function rule R2 turns into a merge refusal.

Everything here is about its sign being right, or its refusal being clean.
There is no third outcome, and these tests exist to keep it that way.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from mainline_domain.quantity import (
    DimensionMismatchError,
    GaugeReferenceError,
    ReferenceMismatchError,
    ValueParseError,
    as_decimal,
    compare,
    convert,
    quantity,
    same_frame,
    to_si,
)


def test_the_sign_convention_is_descendant_minus_ancestor() -> None:
    """``compare(a, b) > 0`` means ``a`` is above ``b``.  Rule R2 depends on it."""
    assert compare(quantity("600", "kPa"), quantity("400", "kPa")) == 1
    assert compare(quantity("400", "kPa"), quantity("600", "kPa")) == -1
    assert compare(quantity("400", "kPa"), quantity("400", "kPa")) == 0


def test_comparison_across_units_in_one_frame() -> None:
    assert compare(quantity("400", "kPa"), quantity("3", "bar")) == 1
    assert compare(quantity("400", "kPa"), quantity("4", "bar")) == 0
    assert compare(quantity("1", "bar_g"), quantity("100", "kPa_g")) == 0


def test_comparison_is_exact_and_not_tolerant() -> None:
    """No epsilon.  A tolerance here would be an unsigned policy about setpoints.

    ``0.1 + 0.2`` is the canonical demonstration that a float pipeline would get
    this wrong; the whole package is Decimal so that the answer is the one a
    person reading the printed numbers would give.
    """
    assert compare(quantity("0.3", "kPa"), quantity("0.30", "kPa")) == 0
    assert compare(quantity("0.30000000000000001", "kPa"), quantity("0.3", "kPa")) == 1


def test_a_float_magnitude_is_refused_by_type() -> None:
    with pytest.raises(ValueParseError):
        as_decimal("not a number")
    with pytest.raises(ValueParseError):
        as_decimal(True)


def test_dimension_mismatch_refuses() -> None:
    with pytest.raises(DimensionMismatchError):
        compare(quantity("12", "months"), quantity("12", "m"))
    with pytest.raises(DimensionMismatchError):
        compare(quantity("2", "points"), quantity("2", "%"))
    with pytest.raises(DimensionMismatchError):
        compare(quantity("19.5", "%vol"), quantity("19.5", "%LEL"))


def test_frame_mismatch_refuses_for_pressure_as_a_gauge_error() -> None:
    with pytest.raises(GaugeReferenceError):
        compare(quantity("400", "kPa"), quantity("400", "kPa_g"))


def test_frame_mismatch_refuses_for_temperature_as_a_reference_error() -> None:
    """A delta is not a reading, even though both are ``[temperature]``."""
    with pytest.raises(ReferenceMismatchError) as raised:
        compare(quantity("5", "delta_degC"), quantity("5", "degC"))
    assert not isinstance(raised.value, GaugeReferenceError)


def test_same_frame_is_the_precondition_and_says_so() -> None:
    assert same_frame(quantity("1", "kPa"), quantity("1", "bar"))
    assert not same_frame(quantity("1", "kPa"), quantity("1", "kPa_g"))
    assert not same_frame(quantity("1", "kPa"), quantity("1", "m"))


def test_to_si_never_leaves_the_frame() -> None:
    """``to_base_units`` on a gauge quantity would return absolute pascals.

    That is the whole reason :func:`to_si` special-cases pressure: a normaliser
    that returned 446062 Pa for 50 psig would hand every downstream comparison
    the forbidden number with the frame tag stripped off.
    """
    gauge = to_si(quantity("50", "psig"))
    assert gauge.unit == "pascal_gauge"
    assert gauge.reference == "gauge"
    assert gauge.value.quantize(Decimal("0.01")) == Decimal("344737.86")

    absolute = to_si(quantity("50", "psia"))
    assert absolute.unit == "pascal_absolute"
    assert absolute.reference == "absolute"
    assert absolute.value.quantize(Decimal("0.01")) == Decimal("344737.86")

    unstated = to_si(quantity("50", "psi"))
    assert unstated.reference == "none"

    temperature = to_si(quantity("25", "degC"))
    assert temperature.reference == "absolute"
    assert temperature.value == Decimal("298.15")


def test_to_si_is_idempotent() -> None:
    for token in ("psig", "psia", "psi", "degC", "months", "%LEL", "points", "levels"):
        once = to_si(quantity("7", token))
        twice = to_si(once)
        assert once == twice, f"to_si is not idempotent for {token}"


def test_ordinal_and_count_scales_compare_but_do_not_convert() -> None:
    """A PPE level is ordinal: comparable, never rescalable.

    Nothing else in the registry has ``[rating]`` dimensionality, so there is no
    unit to convert a rating into — which is the arithmetic expression of "level
    4 is not twice level 2".
    """
    assert compare(quantity("4", "levels"), quantity("2", "levels")) == 1
    with pytest.raises(DimensionMismatchError):
        convert(quantity("4", "levels"), "%")
    with pytest.raises(DimensionMismatchError):
        convert(quantity("4", "points"), "levels")


@settings(max_examples=400, deadline=None)
@given(
    left=st.decimals(min_value=Decimal("-1e6"), max_value=Decimal("1e6"), places=4),
    right=st.decimals(min_value=Decimal("-1e6"), max_value=Decimal("1e6"), places=4),
)
def test_comparison_is_antisymmetric_and_frame_invariant(
    left: Decimal, right: Decimal
) -> None:
    """The two properties rule R2 silently assumes.

    Antisymmetry: swapping the arguments flips the sign.  Frame invariance:
    converting both sides into another unit *of the same frame* does not change
    the answer — which is the formal content of "the offsets cancel", and the
    thing that would break first if a gauge offset were written in the wrong
    unit.
    """
    a = quantity(left, "psig")
    b = quantity(right, "psig")
    assert compare(a, b) == -compare(b, a)

    a_bar = convert(a, "bar_g")
    b_bar = convert(b, "bar_g")
    assert compare(a_bar, b_bar) == compare(a, b)
