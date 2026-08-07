# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""``K-401`` is the whole job.

Channel D exists because dense embeddings systematically lose plant identifiers.  If this file
passes and every other file in the domain fails, the channel is still worth having; if this
file fails, nothing else in the channel matters.

The load-bearing assertions:

* ``K-401`` reaches the index as ``k-401`` — case-folded, **not stemmed**, **not split on the
  letter/digit boundary**;
* a query for ``K-401`` reaches a document containing ``K-401`` and does **not** reach one
  containing ``K402``;
* ``H2S`` stays ``h2s``: it has no separator, so there is nothing to decompose, and
  decomposing it would produce three tokens that mean nothing;
* the document side and the query side are the *same function*, so nothing can drift between
  them.
"""

from __future__ import annotations

import pytest
from trappoint_recall.lexical.analyser import (
    TokenClass,
    analyse,
    analyse_query,
)
from trappoint_recall.lexical.porter import stem


def terms(text: str) -> list[str]:
    return [token.text for token in analyse(text)]


def classes(text: str) -> dict[str, TokenClass]:
    return {token.text: token.token_class for token in analyse(text)}


# ── the headline ─────────────────────────────────────────────────────────────────────────────


def test_k401_survives_whole() -> None:
    assert "k-401" in terms("Vessel K-401 overpressured.")


def test_k401_is_classified_as_an_identifier() -> None:
    assert classes("Vessel K-401 overpressured.")["k-401"] is TokenClass.IDENTIFIER


def test_k401_is_not_stemmed() -> None:
    produced = terms("Vessel K-401 overpressured.")
    assert stem("k-401") not in produced or stem("k-401") == "k-401"
    assert "k-401" in produced
    # And the stemmer is not even consulted for it: the identifier path never calls `stem`.
    assert all(t != "k-40" for t in produced)


def test_k401_is_not_split_on_the_letter_digit_boundary() -> None:
    produced = terms("Vessel K-401 overpressured.")
    assert "k" not in produced, (
        "single-character components are dropped; if `k` appears, the component rule changed"
    )


def test_k401_query_reaches_a_k401_document() -> None:
    document = set(terms("Vessel K-401 overpressured after the PSV lifted."))
    query = set(analyse_query("K-401").terms)
    assert query & document
    assert "k-401" in query & document


def test_k401_query_does_not_reach_a_k402_document() -> None:
    document = set(terms("Pump K402 tripped on high vibration."))
    query = set(analyse_query("K-401").terms)
    assert not (query & document), (
        f"K-401 and K402 share terms {sorted(query & document)}; the channel that exists to "
        "distinguish two vessels has conflated them"
    )


def test_k402_query_does_not_reach_a_k401_document() -> None:
    document = set(terms("Vessel K-401 overpressured."))
    query = set(analyse_query("K402").terms)
    assert not (query & document)


def test_hyphenated_siblings_meet_only_on_the_shared_component() -> None:
    """``K-401`` and ``K-402`` share ``k``… which is dropped, so they share nothing.

    They are still both reachable from a query for ``401`` or ``402`` respectively, which is
    the behaviour a permit that names only the unit number needs.
    """
    a = set(terms("Vessel K-401"))
    b = set(terms("Vessel K-402"))
    assert (a & b) - {"vessel"} == set()
    assert "401" in a and "402" in b


# ── decomposition rules ──────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("K-401", {"k-401", "401"}),
        ("TK-12", {"tk-12", "tk", "12"}),
        ("CC-07", {"cc-07", "cc", "07"}),
        ("TK-012", {"tk-012", "tk", "012", "12"}),
        ("FT_1042A", {"ft_1042a", "ft", "1042a"}),
        ("4C/9911-B", {"4c/9911-b", "4c", "9911"}),
        ("H2S", {"h2s"}),
        ("N2", {"n2"}),
    ],
)
def test_component_decomposition(text: str, expected: set[str]) -> None:
    assert set(terms(text)) == expected


def test_h2s_is_not_decomposed() -> None:
    produced = terms("H2S was detected.")
    assert "h2s" in produced
    assert "2" not in produced and "h" not in produced and "s" not in produced


def test_leading_zero_variants_meet() -> None:
    """``TK-012`` and ``TK-12`` are one vessel written two ways."""
    a = set(terms("Vessel TK-012 was drained."))
    b = set(terms("Vessel TK-12 was drained."))
    assert "12" in a & b
    assert "tk" in a & b


def test_single_character_components_are_dropped_from_every_branch() -> None:
    """``CC-07`` and ``CC-7`` meet on the family prefix, not on a one-character term.

    The zero-stripping rule and the minimum-component rule have to agree; a term that a
    document emits and an otherwise-identical query does not is a silent recall hole.
    """
    a = set(terms("Control loop CC-07 was bypassed."))
    b = set(terms("Control loop CC-7 was bypassed."))
    assert "cc" in a & b
    assert "7" not in a and "7" not in b


def test_identifiers_are_case_folded_not_case_sensitive() -> None:
    assert terms("k-401") == terms("K-401") == terms("K-401".upper())


# ── the symmetry that makes any of this work ────────────────────────────────────────────────


@pytest.mark.parametrize(
    "text",
    [
        "K-401",
        "H2S at 10 ppm",
        "30 CFR 57.22239",
        "CAS 7783-06-4",
        "the isolation valve was not closed",
    ],
)
def test_query_side_and_document_side_are_the_same_function(text: str) -> None:
    assert set(analyse_query(text).terms) == set(terms(text))


def test_query_terms_are_deduplicated_and_sorted() -> None:
    query = analyse_query("K-401 K-401 K-401")
    assert query.terms == ("401", "k-401")
    assert set(query.weights.values()) == {1.0}


def test_class_weights_are_applied_by_token_class() -> None:
    query = analyse_query(
        "K-401 valve failed", class_weights={TokenClass.IDENTIFIER: 3.0}
    )
    assert query.weights["k-401"] == 3.0
    assert query.weights[stem("valve")] == 1.0
