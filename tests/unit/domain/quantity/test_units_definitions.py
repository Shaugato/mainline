# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""The committed definition file, held in place.

These tests are about the *bytes in the repository*, not about the algebra.  A
unit definition file that drifts silently makes every setpoint comparison in the
system unfalsifiable, so the file is treated the way the gazetteers are: as
evidence with a declared version, cross-checked against the code that reads it.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from mainline_domain.data import data_file
from mainline_domain.quantity import (
    ABSOLUTE_PRESSURE_UNITS,
    AMBIGUOUS_TOKENS,
    DIMENSION_LABELS,
    GAUGE_PRESSURE_UNITS,
    UNIT_TOKENS,
    UNITS_VERSION,
    AmbiguousUnitError,
    UnknownUnitError,
    canonical_unit,
    dimension_of,
    dimensionality_for_label,
    reference_of,
    resolve_token,
    unit_registry,
)

PRESSURE = "[mass] / [length] / [time] ** 2"


def test_the_registry_was_built_from_the_committed_file() -> None:
    """Reading the version back through the registry is the only real proof.

    A definition file that fails to load leaves a registry that still knows
    ``psi`` — because Pint's defaults do — and merely does not know ``psig``.
    The failure therefore looks like a missing unit at some later moment rather
    than like a missing file, which is why the file declares its own version as
    a dimensionless constant and the loader refuses a mismatch.
    """
    registry = unit_registry()
    declared = registry.Quantity(Decimal(1), "mainline_units_version").to("dimensionless")
    assert int(declared.magnitude) == UNITS_VERSION


def test_the_file_is_where_the_package_says_it_is() -> None:
    path = data_file("units", "mainline_units.txt")
    assert path.is_file()
    assert "offset: 101325" in path.read_text(encoding="utf-8")


def test_every_gauge_unit_is_declared_and_every_declared_gauge_unit_exists() -> None:
    """Both directions, because either gap is silent.

    A gauge unit in the file but missing from ``GAUGE_PRESSURE_UNITS`` reads as
    ``reference='none'`` and starts comparing against unstated-frame readings —
    the exact crossing D5 forbids, arrived at by omission.  A name in the set but
    not in the file raises on first use, which is loud, but is still a lie in a
    table other code reads.
    """
    registry = unit_registry()
    text = data_file("units", "mainline_units.txt").read_text(encoding="utf-8")

    for unit in GAUGE_PRESSURE_UNITS:
        assert canonical_unit(unit) == unit, f"{unit} is not a canonical registry name"
        assert dimension_of(unit) == PRESSURE
        assert reference_of(unit) == "gauge"
        assert f"{unit} =" in text, f"{unit} is claimed as gauge but is not in the file"

    declared_in_file = {
        line.split("=", 1)[0].strip()
        for line in text.splitlines()
        if "offset: 101325" in line and not line.lstrip().startswith("#")
    }
    assert declared_in_file == GAUGE_PRESSURE_UNITS, (
        "the set of units carrying the atmospheric offset in the file does not match "
        "GAUGE_PRESSURE_UNITS"
    )

    _ = registry


def test_each_gauge_unit_agrees_with_its_absolute_twin() -> None:
    """A hand-typed scale factor that drifted would show up here and nowhere else.

    The three awkward units (``psi``, ``kgf/cm²``, ``inH2O``) are written in the
    definition file as the product of their defining constants rather than as a
    copied decimal.  This asserts that the product reproduces Pint's own value:
    the same magnitude converted through the gauge unit and through the absolute
    one must agree.  Agreement is checked to 24 significant digits rather than
    bit-for-bit because the two are reached by different arithmetic paths in
    Decimal; a typo in a constant moves the fourth digit, not the twenty-fifth.
    """
    registry = unit_registry()
    pairs = (
        ("pascal_gauge", "pascal"),
        ("kilopascal_gauge", "kilopascal"),
        ("megapascal_gauge", "megapascal"),
        ("bar_gauge", "bar"),
        ("millibar_gauge", "millibar"),
        ("psi_gauge", "psi"),
        ("kilopond_per_square_centimetre_gauge", "force_kilogram / centimeter ** 2"),
        ("inch_water_gauge", "inch_H2O"),
        ("millimetre_water_gauge", "millimeter_H2O"),
    )
    sample = Decimal("37")
    for gauge, absolute in pairs:
        # Scale-only comparison: how many pascals is one unit of each worth?
        gauge_span = Decimal(
            str(registry.Quantity(sample, gauge).to("pascal_gauge").magnitude)
        )
        absolute_span = Decimal(str(registry.Quantity(sample, absolute).to("pascal").magnitude))
        difference = abs(gauge_span - absolute_span)
        assert difference <= abs(absolute_span) * Decimal("1e-24"), (
            f"{gauge} and {absolute} disagree by {difference} pascals at {sample}: "
            "the gauge scale factor has drifted from the absolute unit it mirrors"
        )


def test_the_scales_that_must_not_interconvert_do_not() -> None:
    """``%LEL``, ``%vol``, ``%``, a count and a rating are five dimensions, not one.

    Pint makes all five dimensionless, which would let ``19.5 %vol`` (an oxygen
    minimum) compare equal to ``19.5 %LEL`` (four times the usual hot-work
    ceiling).  Each therefore carries its own base dimension in the committed
    file.
    """
    distinct = {
        dimension_of(unit)
        for unit in ("percent_lel", "percent_uel", "percent_volume", "tally", "rating", "percent")
    }
    assert len(distinct) == 6

    registry = unit_registry()
    with pytest.raises(Exception):
        registry.Quantity(Decimal("19.5"), "percent_volume").to("percent_lel")


def test_every_token_in_the_vocabulary_resolves() -> None:
    """No entry in ``UNIT_TOKENS`` may point at a unit the registry does not have.

    A dead entry is worse than a missing one: the token matches in the parser,
    the resolution raises, and the measurement degrades to a bare number — so a
    setpoint quietly stops being a setpoint.
    """
    for token, target in UNIT_TOKENS.items():
        resolved = resolve_token(token)
        assert resolved, f"{token!r} -> {target!r} did not resolve"
        assert reference_of(resolved) in {"absolute", "gauge", "delta", "none"}


def test_ambiguous_tokens_are_refused_with_a_reason() -> None:
    """``C`` is coulomb here and Celsius in a procedure. Refusing beats choosing."""
    for token in AMBIGUOUS_TOKENS:
        with pytest.raises(AmbiguousUnitError) as raised:
            resolve_token(token)
        assert len(str(raised.value)) > 40, (
            f"{token!r} is refused without saying why; the message is what tells an "
            "author how to write the clause so the system can read it"
        )

    assert "C" in AMBIGUOUS_TOKENS
    assert resolve_token("degC") == "degree_Celsius"


def test_an_unknown_token_raises_rather_than_becoming_dimensionless() -> None:
    with pytest.raises(UnknownUnitError):
        resolve_token("smoots")


def test_every_dimension_label_resolves() -> None:
    for label in DIMENSION_LABELS:
        assert dimensionality_for_label(label)
    with pytest.raises(UnknownUnitError):
        dimensionality_for_label("vibes")


def test_the_seven_gauge_pressure_units_do_not_overlap_the_absolute_ones() -> None:
    assert not (GAUGE_PRESSURE_UNITS & ABSOLUTE_PRESSURE_UNITS)
    for unit in ABSOLUTE_PRESSURE_UNITS:
        assert reference_of(unit) == "absolute"
        assert dimension_of(unit) == PRESSURE
