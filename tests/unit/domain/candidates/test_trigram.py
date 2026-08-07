# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""``pg_trgm`` compatibility, asserted against the published recipe by hand.

The values below are not "what the implementation returned"; they are what the
documented pg_trgm algorithm produces, worked out from the recipe: lowercase,
split on non-alphanumerics, pad each word to ``"  word "``, take every length-3
substring, and Jaccard the distinct sets.

That distinction matters because this function decides S2's floor.  A test that
records the implementation's own output cannot detect the implementation being
wrong; it can only detect it *changing*.
"""

from __future__ import annotations

import pytest
from mainline_domain.identity.candidates.trigram import similarity, trigrams


def test_a_three_letter_word_produces_four_trigrams() -> None:
    """``"  abc "`` has four length-3 substrings: a word of length L yields L+1."""
    assert trigrams("abc") == frozenset({"  a", " ab", "abc", "bc "})


def test_a_one_letter_word_produces_two() -> None:
    assert trigrams("a") == frozenset({"  a", " a "})


def test_non_alphanumerics_are_separators_not_characters() -> None:
    """With pg_trgm's default KEEPONLYALNUM build, punctuation splits words."""
    assert trigrams("ab-cd") == trigrams("ab cd") == trigrams("AB!!CD")


def test_case_is_folded() -> None:
    assert trigrams("Shall") == trigrams("shall")


def test_identical_strings_score_one() -> None:
    assert similarity("isolate the pump", "isolate the pump") == 1.0


def test_disjoint_strings_score_zero() -> None:
    assert similarity("aaaa", "zzzz") == 0.0


def test_two_empty_strings_score_zero_not_one() -> None:
    """pg_trgm's behaviour, and the safe one: 'identical because both are empty'
    is not a statement this cascade may make."""
    assert similarity("", "") == 0.0
    assert similarity("", "isolate") == 0.0


def test_similarity_is_symmetric() -> None:
    left = "the authorised person shall isolate pump P-101A"
    right = "the authorised person should isolate pump P-101B"
    assert similarity(left, right) == similarity(right, left)


def test_a_worked_example_matches_the_recipe() -> None:
    """``"ab cd"`` vs ``"ab ce"`` — computed by hand from the padded words.

    ``ab`` -> ``{"  a", " ab", "ab "}``; ``cd`` -> ``{"  c", " cd", "cd "}``;
    ``ce`` -> ``{"  c", " ce", "ce "}``.  Intersection is
    ``{"  a", " ab", "ab ", "  c"}`` = 4; union is 8.  So 4/8 = 0.5.
    """
    assert similarity("ab cd", "ab ce") == pytest.approx(0.5)


def test_a_deontic_downgrade_barely_moves_the_score() -> None:
    """Why trigram similarity is a *floor* and never the whole answer.

    ``shall`` -> ``should`` is the single most important weakening in the
    lattice, and it costs almost nothing in trigram terms.  S2 uses this number
    to confirm that anchor-equal clauses are still recognisably the same prose;
    deciding whether the edit weakened the control is DELTALATTICE's job.
    """
    left = "the authorised person shall isolate pump P-101A before breaking containment"
    right = "the authorised person should isolate pump P-101A before breaking containment"
    assert similarity(left, right) > 0.85


def test_a_different_equipment_tag_barely_moves_it_either() -> None:
    """And why an anchor conflict must veto rather than subtract."""
    left = "the authorised person shall isolate pump P-101A before breaking containment"
    right = "the authorised person shall isolate pump P-101B before breaking containment"
    assert similarity(left, right) > 0.85
