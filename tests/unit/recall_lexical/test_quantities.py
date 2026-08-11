# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""SI normalisation, and the two conflations that must never happen.

``25 %LEL`` and ``25 %`` are not the same measurement.  ``%LEL`` is a fraction of the lower
explosive limit of the particular gas; for methane, 25 %LEL is 1.25 %v/v in air.  A retrieval
channel that treats them as one term will find a routine tank-gauging record when asked about
an explosive atmosphere, and will do it with a high score.

``30 psig`` and ``30 psi`` are likewise not the same: converting gauge to absolute needs an
ambient pressure the analyser does not have, so it does not guess.
"""

from __future__ import annotations

import pytest

from trappoint_recall.lexical.analyser import TokenClass, analyse
from trappoint_recall.lexical.units import DIMENSION_SYMBOL, format_magnitude


def terms(text: str) -> list[str]:
    return [token.text for token in analyse(text)]


def quantities(text: str) -> list[str]:
    return [t.text for t in analyse(text) if t.token_class is TokenClass.QUANTITY]


# ── the refusals ─────────────────────────────────────────────────────────────────────────────


def test_percent_lel_is_not_percent() -> None:
    lel = set(quantities("The atmosphere was 25 %LEL."))
    pct = set(quantities("The tank was 25 % full."))
    assert lel and pct
    assert not (lel & pct), (
        "25 %LEL and 25 % produced a shared term. For methane those differ by a factor of "
        "twenty and one of them is an explosive atmosphere."
    )


def test_gauge_pressure_is_not_absolute_pressure() -> None:
    gauge = set(quantities("Suction showed 30 psig."))
    absolute = set(quantities("Discharge was 30 psi."))
    assert gauge and absolute
    assert not (gauge & absolute)


def test_lel_and_uel_are_distinct() -> None:
    assert not set(quantities("40 %LEL")) & set(quantities("40 %UEL"))


# ── the equivalences ─────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("left", "right"),
    [
        ("0.1 %", "1000 ppm"),
        ("1 %", "10000 ppm"),
        ("50 °C", "122 degF"),
        ("0 °C", "32 degF"),
        ("1 bar", "100 kPa"),
        ("1 bar", "100000 Pa"),
        ("1 m", "1000 mm"),
        ("1 kg", "1000 g"),
        ("1 h", "60 min"),
        ("1 m3", "1000 litres"),
        ("1 ppm", "1000 ppb"),
    ],
)
def test_equivalent_quantities_produce_the_same_term(left: str, right: str) -> None:
    assert quantities(left) == quantities(right) != []


@pytest.mark.parametrize(
    ("left", "right"),
    [
        ("1000 ppm", "1001 ppm"),
        ("50 °C", "51 °C"),
        ("100 psi", "101 psi"),
    ],
)
def test_different_quantities_produce_different_terms(left: str, right: str) -> None:
    assert quantities(left) != quantities(right)


def test_six_significant_figures_absorbs_float_noise_but_not_real_differences() -> None:
    """The reason the mantissa is ``%.6g`` and not ``repr``.

    Unit conversion is a multiply and an add.  Two routes to the same physical quantity — an
    affine temperature conversion versus a direct one, a ratio reached through ``ppm`` versus
    through ``%`` — need not land on the same float64, and a term that depended on the
    seventeenth digit would simply never match.  Six significant figures absorbs the
    conversion noise and nothing else.
    """
    noisy = 323.15 + 3e-13
    assert noisy != 323.15
    assert format_magnitude(noisy) == format_magnitude(323.15) == "323.15"
    # Below six significant figures: collapsed. At six: distinguished.
    assert format_magnitude(1.0) == format_magnitude(1.0000001)
    assert format_magnitude(1.0) != format_magnitude(1.00001)


def test_negative_zero_is_zero() -> None:
    assert format_magnitude(-0.0) == format_magnitude(0.0) == "0"


# ── shape of the emitted pair ────────────────────────────────────────────────────────────────


def test_a_quantity_emits_its_dimension_symbol_as_an_identifier() -> None:
    tokens = {t.text: t.token_class for t in analyse("Discharge pressure was 100 psi.")}
    assert tokens["q:pressure:689476"] is TokenClass.QUANTITY
    assert tokens[DIMENSION_SYMBOL["pressure"]] is TokenClass.IDENTIFIER


def test_pressure_written_in_different_units_meets_on_the_dimension_symbol() -> None:
    psi = set(terms("100 psi"))
    kpa = set(terms("689 kPa"))
    assert DIMENSION_SYMBOL["pressure"] in psi & kpa


def test_scientific_notation_and_negative_values() -> None:
    assert quantities("1.2e-3 m3/h") == ["q:volflow:3.33333e-07"]
    assert quantities("-5 °C") == ["q:temperature:268.15"]


# ── boundaries: what must NOT become a quantity ──────────────────────────────────────────────


@pytest.mark.parametrize(
    "text",
    [
        "the crew went in metres of water",
        "a bar stock lever",
        "K-401",
        "2S1 was tagged out",
        "Only 3 of the 5 detectors",
    ],
)
def test_prose_and_identifiers_do_not_become_quantities(text: str) -> None:
    assert quantities(text) == []


def test_a_unit_glued_to_an_asset_tag_does_not_steal_the_tag() -> None:
    assert "2s1" in terms("2S1 was tagged out")


def test_bare_hazard_units_are_recognised_without_a_number() -> None:
    assert "lel" in terms("monitor for %LEL during entry")
    assert "ppm" not in terms("monitor for %LEL during entry")
    assert DIMENSION_SYMBOL["ratio"] not in terms("monitor for %LEL during entry")


def test_bare_ambiguous_words_are_not_treated_as_units() -> None:
    """``bar``, ``in`` and ``m`` are English before they are units."""
    assert "pa" not in terms("a bar stock lever")
    assert "m" not in terms("the valve is in the pit")
