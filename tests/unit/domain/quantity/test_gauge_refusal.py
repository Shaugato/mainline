# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""RED FIRST (PL-2): ``psig`` must never become ``kPa`` absolute — decision D5.

This is the first artefact worker W2 wrote and it was red before
``mainline_domain.quantity`` existed.  It is kept in a shape that stays
meaningful after it went green, which for a product whose deliverable is a
refusal is the harder half: a test that merely asserts ``pytest.raises`` proves
nothing about whether the mistake it guards was ever reachable.

So the first test in this file does not test our code at all.  It drives the
**raw Pint registry**, built from the same committed definition file, and shows
it returning ``446.06 kPa`` for ``50 psig`` — the wrong answer, available, one
method call away, in the exact library this package is built on.  Only then does
the second test show the domain API refusing to produce it.

WHY 446 IS THE NUMBER THAT MATTERS
----------------------------------
``50 psig`` is ``344.74 kPa`` of gauge pressure and ``446.06 kPa`` absolute.  Now
take a real edit: an ancestor clause reads *"shall not exceed 400 kPa"* and its
descendant reads *"shall not exceed 50 psig"*.

* Comparing honestly: the frames differ, nobody said which frame ``400 kPa``
  meant, and the comparison is refused.
* Comparing through Pint: 446.06 > 400, so the ceiling appears to have been
  **raised** — ``weaken`` — on an edit that in fact tightened it to 344.74 kPa_g.

The error is not small and it is not signed: run the same arithmetic on a
different pair and it hides a real weakening behind an apparent tightening.
Neither direction is detectable downstream, because what arrives at the lattice
is a number, not a doubt.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from mainline_domain.quantity import (
    GaugeReferenceError,
    ReferenceMismatchError,
    compare,
    convert,
    quantity,
    reference_of,
    unit_registry,
)

ATMOSPHERE_PA = Decimal("101325")


def test_the_mistake_this_package_refuses_is_reachable_and_wrong() -> None:
    """The raw registry converts 50 psig to 446 kPa. The refusal is not theatre."""
    registry = unit_registry()
    naive = registry.Quantity(Decimal("50"), "psig").to("kPa")

    # 446.06, not 344.74: Pint added one standard atmosphere, because psig and
    # kPa are dimensionally identical and Pint has no notion of a frame.
    assert Decimal("446.0") < Decimal(str(naive.magnitude)) < Decimal("446.1")

    # And here is the sign flip, in three lines, using only Pint.
    ancestor_ceiling = Decimal("400")  # kPa, frame unstated
    through_pint = Decimal(str(naive.magnitude))
    honest = Decimal(str(registry.Quantity(Decimal("50"), "psig").to("kPa_g").magnitude))
    assert through_pint > ancestor_ceiling  # looks like a RAISED ceiling
    assert honest < ancestor_ceiling  # the ceiling actually came DOWN


def test_psig_to_kpa_raises() -> None:
    """The headline refusal.  ``50 psig`` does not become an absolute pressure."""
    fifty_psig = quantity("50", "psig")
    assert fifty_psig.reference == "gauge"

    with pytest.raises(GaugeReferenceError) as raised:
        convert(fifty_psig, "kPa")

    message = str(raised.value)
    assert "reference frames" in message
    # The diagnosis has to name both sides, because the person reading it is
    # about to go and find out which frame the clause meant.
    assert "psi_gauge" in message
    assert "kilopascal" in message


def test_psig_to_psia_raises_too() -> None:
    """Explicitly-absolute is not a loophole: gauge does not cross into it either."""
    with pytest.raises(GaugeReferenceError):
        convert(quantity("50", "psig"), "psia")


def test_bare_kpa_is_unstated_and_not_absolute() -> None:
    """A clause that wrote ``kPa`` did not say ``absolute``.  It said nothing."""
    assert reference_of("kPa") == "none"
    assert reference_of("kPa_a") == "absolute"
    assert reference_of("kPa_g") == "gauge"

    with pytest.raises(GaugeReferenceError):
        compare(quantity("400", "kPa"), quantity("50", "psig"))
    with pytest.raises(GaugeReferenceError):
        compare(quantity("400", "kPa"), quantity("400", "kPa_a"))


def test_psig_to_barg_succeeds_with_the_right_value() -> None:
    """Inside the gauge frame the conversion is a pure scale change, and exact.

    ``50 psig`` = 50 x 6894.757293168361 Pa = 344737.86… Pa_g = 3.4473786… bar_g.
    The atmospheric offsets on the two units cancel, which is why the definition
    file carries them and why they must both be measured in pascals.
    """
    result = convert(quantity("50", "psig"), "bar_g")
    assert result.unit == "bar_gauge"
    assert result.reference == "gauge"
    assert result.value.quantize(Decimal("0.0000001")) == Decimal("3.4473786")

    # Same magnitude as the absolute conversion of a bare psi, because the two
    # units differ only by the offset that just cancelled.
    absolute = convert(quantity("50", "psi"), "bar")
    assert absolute.value.quantize(Decimal("0.0000001")) == result.value.quantize(
        Decimal("0.0000001")
    )


def test_gauge_to_gauge_round_trips_exactly() -> None:
    for target in ("Pa_g", "kPa_g", "MPa_g", "mbar_g", "inWG"):
        there = convert(quantity("50", "psig"), target)
        back = convert(there, "psig")
        assert back.value == Decimal("50"), f"{target} did not round-trip"


def test_temperature_crosses_because_its_offset_is_universal() -> None:
    """Celsius to Kelvin is allowed, and that is not an inconsistency.

    The gauge refusal is not "offset units are scary".  It is that the gauge
    offset is the *ambient pressure*, which varies with weather and altitude and
    which the instrument is not measuring.  The Celsius offset is 273.15 by
    definition, everywhere, forever.  One conversion is a fact; the other is an
    assumption about the room.
    """
    kelvin = convert(quantity("25", "degC"), "K")
    assert kelvin.value == Decimal("298.15")
    assert kelvin.reference == "absolute"

    # A temperature DIFFERENCE is still a different frame from a temperature.
    with pytest.raises(ReferenceMismatchError):
        compare(quantity("5", "delta_degC"), quantity("5", "K"))


def test_one_atmosphere_is_zero_gauge_in_every_gauge_unit() -> None:
    """The committed check on the offsets themselves.

    If any gauge unit's offset were written in its own unit instead of in
    pascals, this is where it would show: one standard atmosphere would convert
    to something other than zero gauge.  Measured on pint 0.25.3, the wrong form
    (`kilopascal_gauge = 1 * kilopascal; offset: 101325`) yields -101223.675.
    """
    registry = unit_registry()
    from mainline_domain.quantity import GAUGE_PRESSURE_UNITS

    atmosphere = registry.Quantity(ATMOSPHERE_PA, "pascal")
    for unit in sorted(GAUGE_PRESSURE_UNITS):
        gauge = atmosphere.to(unit)
        assert Decimal(str(gauge.magnitude)) == Decimal(0), (
            f"{unit} does not read zero at one standard atmosphere; its offset is "
            "not 101325 pascals"
        )
