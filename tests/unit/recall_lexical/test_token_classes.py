# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""Token classes, citations, CAS checksums, and the prose rules that only apply to prose.

The class on a token is not decoration.  It is what decides whether the token is stemmed,
whether it is tested against the stopword list, and whether a downstream weighting may treat
identifier evidence differently from narrative evidence.  A term that drifts from
``identifier`` to ``prose`` starts being stemmed, and ``K-401`` becomes something else.
"""

from __future__ import annotations

import pytest

from trappoint_recall.lexical.analyser import (
    IDENTIFIER_CLASSES,
    TokenClass,
    analyse,
    is_well_formed_term,
)
from trappoint_recall.lexical.stopwords import STOPWORDS


def classed(text: str) -> list[tuple[str, TokenClass]]:
    return [(t.text, t.token_class) for t in analyse(text)]


def only(text: str, cls: TokenClass) -> list[str]:
    return [t for t, c in classed(text) if c is cls]


# ── class assignment ─────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("text", "term", "expected"),
    [
        ("Vessel K-401 failed", "k-401", TokenClass.IDENTIFIER),
        ("H2S detected", "h2s", TokenClass.IDENTIFIER),
        ("reached 10 ppm", "q:ratio:1e-05", TokenClass.QUANTITY),
        ("reached 10 ppm", "frac", TokenClass.IDENTIFIER),
        ("under 30 CFR 57.22239", "cfr:30:57.22239", TokenClass.CITATION),
        ("under 30 CFR 57.22239", "57.22239", TokenClass.IDENTIFIER),
        ("CAS 7783-06-4", "cas:7783-06-4", TokenClass.CAS),
        ("the valve failed", "valv", TokenClass.PROSE),
    ],
)
def test_token_class_assignment(text: str, term: str, expected: TokenClass) -> None:
    assert (term, expected) in classed(text)


def test_every_token_carries_a_class() -> None:
    tokens = analyse("Vessel K-401 at 25 %LEL, cited 30 CFR 57.22239, CAS 7783-06-4, valve failed.")
    assert tokens
    assert all(isinstance(t.token_class, TokenClass) for t in tokens)
    assert {t.token_class for t in tokens} == {
        TokenClass.IDENTIFIER,
        TokenClass.QUANTITY,
        TokenClass.CITATION,
        TokenClass.CAS,
        TokenClass.PROSE,
    }


def test_positions_are_monotone_and_dense() -> None:
    tokens = analyse("Vessel K-401 overpressured at 100 psi.")
    assert [t.position for t in tokens] == list(range(len(tokens)))


def test_every_emitted_term_is_well_formed() -> None:
    """Whatever the analyser emits must be renderable as a SQL literal and storable as a key."""
    corpus = (
        "Vessel K-401 at 25 %LEL and 3 mg/m³; §57.22239(a); CAS 7783-06-4; "
        "AS/NZS 3000; Straße; 4C/9911-B; FT_1042A; -5 °C; 1.2e-3 m3/h"
    )
    for token in analyse(corpus):
        assert is_well_formed_term(token.text), token


# ── citations ────────────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("30 CFR 57.22239", "cfr:30:57.22239"),
        ("29 C.F.R. 1910.146", "cfr:29:1910.146"),
        ("§ 57.22239(a)", "sec:57.22239.a"),
        ("AS/NZS 3000", "asnzs:3000"),
        ("AS 2865", "as:2865"),
        ("ISO 45001", "iso:45001"),
        ("IEC 61511-1", "iec:61511-1"),
        ("ASME B31.3", "asme:b31.3"),
        ("API RP 754", "api:754"),
        ("NFPA 70E", "nfpa:70e"),
        ("WHS Regulation 2011 r 341", "whsreg:341"),
    ],
)
def test_citation_canonical_forms(text: str, expected: str) -> None:
    assert expected in only(text, TokenClass.CITATION)


def test_a_citation_is_never_stemmed_or_split_into_prose() -> None:
    tokens = classed("Cited under 30 CFR 57.22239.")
    assert ("cfr", TokenClass.PROSE) not in tokens
    assert ("cfr:30:57.22239", TokenClass.CITATION) in tokens


def test_the_designator_alone_is_reachable() -> None:
    """A permit that names only ``57.22239`` must still meet the incident that cites the rule."""
    document = {t for t, _ in classed("Cited under 30 CFR 57.22239.")}
    query = {t for t, _ in classed("57.22239")}
    assert query & document


def test_a_citation_consumes_its_number_rather_than_leaving_a_quantity() -> None:
    """``30 CFR 57.22239`` must not be read as the quantity ``30`` plus a stray tag."""
    assert only("Cited under 30 CFR 57.22239.", TokenClass.QUANTITY) == []


# ── CAS numbers ──────────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("number", "valid"),
    [
        ("7783-06-4", True),  # hydrogen sulfide
        ("71-43-2", True),  # benzene
        ("1333-74-0", True),  # hydrogen
        ("74-82-8", True),  # methane
        ("7783-06-9", False),  # wrong check digit
        ("71-43-9", False),
    ],
)
def test_cas_checksum_decides_the_class(number: str, valid: bool) -> None:
    produced = classed(f"Substance {number} was released.")
    if valid:
        assert (f"cas:{number}", TokenClass.CAS) in produced
    else:
        assert all(c is not TokenClass.CAS for _, c in produced)
        assert (number, TokenClass.IDENTIFIER) in produced, (
            "a hyphenated number that fails the CAS checksum must still be kept as an "
            "identifier: it is a real string in the record, it is simply not a registry number"
        )


# ── prose rules apply to prose only ──────────────────────────────────────────────────────────


def test_stemming_applies_to_prose() -> None:
    a = {t for t, c in classed("Operators were operating the valve") if c is TokenClass.PROSE}
    b = {t for t, c in classed("The operator operated the valve") if c is TokenClass.PROSE}
    assert "oper" in a & b


def test_stopwords_are_removed_from_prose() -> None:
    produced = {t for t, _ in classed("It was on the deck and under the grating.")}
    assert "the" not in produced and "and" not in produced and "was" not in produced


def test_negations_and_spatial_prepositions_are_never_stopped() -> None:
    """ "valve not closed" and "valve closed" must not become the same document."""
    with_negation = {t for t, _ in classed("The isolation valve was not closed.")}
    without = {t for t, _ in classed("The isolation valve was closed.")}
    assert "not" in with_negation
    assert with_negation - without == {"not"}


@pytest.mark.parametrize("word", ["no", "not", "off", "on", "over", "under", "out", "without"])
def test_hazard_bearing_words_are_not_in_the_stopword_list(word: str) -> None:
    assert word not in STOPWORDS


def test_identifier_classes_are_exactly_the_unstemmed_ones() -> None:
    assert {
        TokenClass.IDENTIFIER,
        TokenClass.QUANTITY,
        TokenClass.CITATION,
        TokenClass.CAS,
    } == IDENTIFIER_CLASSES
    assert TokenClass.PROSE not in IDENTIFIER_CLASSES


def test_hyphenated_prose_is_kept_whole_and_split() -> None:
    produced = classed("The lock-out procedure was signed.")
    assert ("lock-out", TokenClass.IDENTIFIER) in produced
    assert ("lock", TokenClass.PROSE) in produced
    assert ("out", TokenClass.PROSE) in produced


# ── normalisation ────────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "variant",
    # RUF001: the non-ASCII dashes are the point of the test, not typos for ASCII "-".
    ["K-401", "K–401", "K‑401", "K—401", "k-401"],  # noqa: RUF001
)
def test_typographic_dashes_do_not_fragment_an_identifier(variant: str) -> None:
    assert "k-401" in {t for t, _ in classed(f"Vessel {variant} failed.")}


def test_case_folding_is_aggressive_enough_for_the_german_sharp_s() -> None:
    assert {t for t, _ in classed("STRASSE")} == {t for t, _ in classed("Straße")}


def test_micro_sign_and_superscripts_are_flattened() -> None:
    assert "q:massconc:4e-08" in only("40 µg/m³", TokenClass.QUANTITY)
