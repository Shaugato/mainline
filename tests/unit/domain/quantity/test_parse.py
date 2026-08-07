# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""Reading setpoints out of canonical clause text.

The parser's job is narrow and its failure mode is chosen: when it cannot read a
unit it produces a *bare number*, never a guessed quantity.  Several tests below
exist only to hold that choice in place, because "the parameter is called
max_operating_pressure so 50 probably means kPa" is the most tempting and most
dangerous line of code anyone could add to this module.
"""

from __future__ import annotations

from decimal import Decimal

from mainline_domain.canon import canonicalise
from mainline_domain.quantity import parse_measurements, parse_one


def only(text: str):
    measurements = parse_measurements(text)
    assert len(measurements) == 1, f"expected one measurement in {text!r}, got {measurements}"
    return measurements[0]


def test_the_six_shapes() -> None:
    m = only("The vessel shall not exceed 50 psig during the intervention.")
    assert m.comparator == "le"
    assert m.value is not None and m.value.unit == "psi_gauge"
    assert m.value.value == Decimal("50")

    m = only("At least 2 points must be proved dead before entry.")
    assert m.comparator == "ge"
    assert m.value is not None and m.value.unit == "tally"

    m = only("Oxygen content >= 19.5 %vol before entry is permitted.")
    assert m.comparator == "ge"
    assert m.value is not None and m.value.unit == "percent_volume"

    m = only("Set the regulator to 50 +/- 2 kPa.")
    assert m.value is not None and m.value.value == Decimal("50")
    assert m.tolerance is not None and m.tolerance.value == Decimal("2")
    assert m.tolerance.unit == "kilopascal"

    m = only("Set the regulator to 50 kPa +/- 5 %.")
    assert m.tolerance is None
    assert m.tolerance_relative == Decimal("0.05")

    m = only("Maintain between 40 and 60 degC.")
    assert m.comparator == "between"
    assert m.value is not None and m.value.value == Decimal("40")
    assert m.upper is not None and m.upper.value == Decimal("60")


def test_a_number_with_no_unit_stays_a_number() -> None:
    """The one thing the parser must never do is invent a unit.

    ``max_operating_pressure: 50`` is psig or bar or kPa, and those are a factor
    of fourteen apart in the direction of the failure nobody survives.  The
    measurement records the digits and the comparator and leaves ``value``
    empty; W3's extractor turns that into ``cat_confidence='low'``.
    """
    m = only("The working pressure shall not exceed 50.")
    assert m.value is None
    assert m.bare_number == Decimal("50")
    assert m.comparator == "le"


def test_an_ambiguous_unit_degrades_to_a_bare_number_rather_than_guessing() -> None:
    """``50 C`` could be coulombs.  It is not silently made Celsius."""
    m = only("Do not exceed 50 C at the seal face.")
    assert m.value is None
    assert m.bare_number == Decimal("50")

    m = only("Do not exceed 50 degC at the seal face.")
    assert m.value is not None and m.value.unit == "degree_Celsius"


def test_the_tolerance_number_is_not_a_second_setpoint() -> None:
    """``50 +/- 2 kPa`` is one control with a band, not a 50 and a 2.

    A spurious second measurement here would appear in the CAT as a control that
    the descendant clause dropped — a manufactured weakening, which is the
    failure direction W10's SURVIVE catalogue exists to catch.
    """
    assert len(parse_measurements("Set the regulator to 50 +/- 2 kPa.")) == 1
    assert len(parse_measurements("Set the regulator to 50 kPa +/- 5 %.")) == 1


def test_comparators_are_taken_from_the_nearest_governing_phrase() -> None:
    cases = {
        "shall not exceed 50 kPa": "le",
        "must not exceed 50 kPa": "le",
        "no more than 50 kPa": "le",
        "at most 50 kPa": "le",
        "a maximum of 50 kPa": "le",
        "<= 50 kPa": "le",
        "at least 50 kPa": "ge",
        "not less than 50 kPa": "ge",
        "a minimum of 50 kPa": "ge",
        ">= 50 kPa": "ge",
        "less than 50 kPa": "lt",
        "below 50 kPa": "lt",
        "greater than 50 kPa": "gt",
        "above 50 kPa": "gt",
        "approximately 50 kPa": "approx",
        "exactly 50 kPa": "eq",
    }
    for text, expected in cases.items():
        assert only(f"The value is {text} at all times.").comparator == expected, text


def test_an_unqualified_value_is_not_promoted_to_equality() -> None:
    """``none`` is a real comparator value and rule R3 reads the difference.

    A clause that states a value without stating a bound has said something
    weaker than ``=``, and turning it into ``=`` would fabricate the field the
    comparator-loosening rule compares.
    """
    assert only("The regulator is set to 50 kPa.").comparator == "none"


def test_an_intervening_noun_phrase_breaks_the_comparator_attachment() -> None:
    """``not exceed the design pressure of 50 kPa`` does not attach ``not exceed``.

    The noun phrase in between can carry its own bound, and a comparator lifted
    across it is a comparator attributed to the wrong number.  Failing to attach
    costs a ``none`` — weaker, and adjudicable.  Attaching wrongly costs a
    verdict.
    """
    assert only("It shall not exceed the design pressure of 50 kPa.").comparator == "none"


def test_multiple_setpoints_in_one_clause_are_all_returned() -> None:
    text = "Test at 50 kPa and stop work above 5 %LEL."
    measurements = parse_measurements(text)
    assert len(measurements) == 2
    assert [m.comparator for m in measurements] == ["none", "gt"]
    assert parse_one(text) is None, (
        "parse_one must refuse a clause with two setpoints rather than picking one; "
        "the discarded one may be the one that moved"
    )


def test_spans_are_offsets_into_the_text_that_was_parsed() -> None:
    text = "The vessel shall not exceed 50 psig during the intervention."
    m = only(text)
    start, end = m.span
    assert text[start:end] == m.raw
    assert "50 psig" in m.raw


def test_it_reads_canonicalised_text_unchanged() -> None:
    """Canon output is the input contract, so a canon round trip must not move a span."""
    raw = "7.3.2 (b)  The vessel shall not exceed 50 psig  during the intervention."
    canon = canonicalise(raw)
    m = only(canon.canon_text)
    start, end = m.span
    assert canon.canon_text[start:end] == m.raw
    assert m.value is not None and m.value.unit == "psi_gauge"


def test_the_unit_must_be_adjacent_and_a_separated_one_is_not_reached_for() -> None:
    """``2 isolation points`` reads as a bare 2, and that limitation is deliberate.

    The unit token has to follow the number with nothing but separators between
    them.  Relaxing that — "allow one intervening word when the unit is a
    counting noun" — would read ``2 isolation points`` correctly and would also
    read ``50 metre levels`` and ``3 shift hours`` as things they are not, at a
    false-positive rate nobody has measured.

    The cost of the strict rule is bounded and points the right way: the
    measurement degrades to a bare number, W3 marks the clause
    ``cat_confidence='low'``, and a low-confidence control over blood-written
    ancestry defaults to ``weaken``.  Under-reading costs adjudication.
    Over-reading would cost a wrong comparison, which costs a verdict.  This is
    recorded as an open limitation in ``novelty/directrix.yaml``.
    """
    m = only("At least 2 isolation points must be proved dead.")
    assert m.value is None
    assert m.bare_number == Decimal("2")
    assert m.comparator == "ge"


def test_spelled_out_numbers_are_not_read() -> None:
    """``two isolation points`` yields no measurement at all — a stated gap.

    Fails towards silence rather than towards a number, and silence in a clause
    that should carry a setpoint is what the CAT extractor turns into low
    confidence.
    """
    assert parse_measurements("At least two points must be proved dead.") == ()


def test_thousands_separators_survive_and_exponents_do_not_appear() -> None:
    m = only("The ventilation quantity shall be at least 1,200 m3/h.")
    assert m.value is not None
    assert m.value.value == Decimal("1200")
