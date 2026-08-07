# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""The patience diff: total, tiling, and able to say that something *moved*.

Two properties carry the weight.

**Tiling** is asserted over Hypothesis-generated inputs rather than over
examples.  An op list that does not exactly tile both sides has silently lost
text, and lost text in a diff that an adjudicator reads before signing a
disposition is the worst kind of bug this package could ship: it is invisible
and it is exculpatory.

**Move detection** is why patience rather than Myers.  The shortest edit script
for a reordered procedure is a shredded interleaving that reads as a rewrite —
and "this looks like a rewrite" is exactly what an author reordering clauses to
hide a deletion would like it to look like.
"""

from __future__ import annotations

from hypothesis import given
from hypothesis import strategies as st
from mainline_domain.identity.candidates.patience_diff import (
    DiffOp,
    matched_token_count,
    moved_blocks,
    patience_diff,
    patience_similarity,
    render,
    tokenise,
)

WORDS = st.lists(st.sampled_from(["a", "b", "c", "d", "e", "f", "g", "."]), max_size=24)


def _tiles(ops: tuple[DiffOp, ...], a: list[str], b: list[str]) -> bool:
    ai = bi = 0
    for op in ops:
        if op.a_start != ai or op.b_start != bi:
            return False
        ai, bi = op.a_end, op.b_end
    return ai == len(a) and bi == len(b)


@given(WORDS, WORDS)
def test_the_op_list_tiles_both_sides(a: list[str], b: list[str]) -> None:
    assert _tiles(patience_diff(a, b), a, b)


@given(WORDS, WORDS)
def test_equal_ops_really_are_equal(a: list[str], b: list[str]) -> None:
    for op in patience_diff(a, b):
        if op.tag == "equal":
            assert a[op.a_start : op.a_end] == b[op.b_start : op.b_end]


@given(WORDS)
def test_a_sequence_against_itself_is_one_equal_op(a: list[str]) -> None:
    ops = patience_diff(a, a)
    if a:
        assert ops == (DiffOp("equal", 0, len(a), 0, len(a)),)
        assert patience_similarity(a, a) == 1.0
    else:
        assert ops == ()


@given(WORDS, WORDS)
def test_similarity_is_bounded(a: list[str], b: list[str]) -> None:
    assert 0.0 <= patience_similarity(a, b) <= 1.0


def test_patience_similarity_is_not_symmetric_and_that_is_documented() -> None:
    """Hypothesis found this pair; it is pinned so the property cannot be forgotten.

    Patience anchors on tokens unique *within a window*, and the recursion's
    windows differ by direction.  git's diff behaves the same way.  The reason
    this is acceptable is that the number is a witness and a feature, never the
    score of record — S3 decides on token-level indel similarity, which is
    metric-derived and symmetric, so no assignment depends on argument order.
    """
    a = ["b", "c", "a"]
    b = ["a", "b", "b", "c"]
    assert patience_similarity(a, b) != patience_similarity(b, a)

    from mainline_domain.identity.candidates import rescore

    left = rescore("shall isolate P-101A", "must isolate P-101A")
    right = rescore("must isolate P-101A", "shall isolate P-101A")
    assert left.score == right.score, "the score of record must not depend on argument order"


def test_a_deontic_downgrade_is_one_replacement_and_nothing_else() -> None:
    a = tokenise("the authorised person shall isolate pump P-101A before breaking containment")
    b = tokenise("the authorised person should isolate pump P-101A before breaking containment")
    ops = patience_diff(a, b)
    replacements = [op for op in ops if op.tag == "replace"]
    assert len(replacements) == 1
    assert a[replacements[0].a_start : replacements[0].a_end] == ("shall",)
    assert b[replacements[0].b_start : replacements[0].b_end] == ("should",)


def test_a_reorder_is_reported_as_a_move_not_as_a_rewrite() -> None:
    """The whole reason this module is not ``difflib``."""
    a = tokenise("alpha bravo charlie delta echo foxtrot")
    b = tokenise("charlie delta alpha bravo echo foxtrot")
    moves = moved_blocks(a, b)

    assert {m.token for m in moves} == {"alpha", "bravo"}
    ops = patience_diff(a, b)
    assert matched_token_count(ops) >= 3, "a pure reorder should keep most tokens matched"


def test_no_moves_when_nothing_moved() -> None:
    a = tokenise("alpha bravo charlie delta")
    b = tokenise("alpha bravo charlie delta echo")
    assert moved_blocks(a, b) == ()


def test_a_dropped_verification_sentence_is_a_deletion() -> None:
    a = tokenise("the isolation shall be verified at PIT-1204 . a second signature is required .")
    b = tokenise("the isolation shall be verified at PIT-1204 .")
    ops = patience_diff(a, b)
    deletions = [op for op in ops if op.tag == "delete"]
    assert len(deletions) == 1
    assert "signature" in a[deletions[0].a_start : deletions[0].a_end]


def test_render_is_plain_text_a_human_can_sign_against() -> None:
    a = tokenise("shall isolate pump P-101A")
    b = tokenise("should isolate pump P-101A")
    lines = render(patience_diff(a, b), a, b)
    assert lines[0] == "- shall"
    assert lines[1] == "+ should"
    assert lines[2].startswith("= ")


def test_tokenise_keeps_punctuation_as_its_own_token() -> None:
    """A comma that becomes a full stop can split one obligation into two."""
    assert tokenise("isolate, then verify.") == ("isolate", ",", "then", "verify", ".")


def test_tokenise_keeps_tag_components_addressable() -> None:
    """``P-101A`` shreds into word tokens; identity of the tag is ANCHORLOCK's job."""
    assert tokenise("pump P-101A") == ("pump", "P", "-", "101A")


def test_empty_against_empty_is_zero_not_one() -> None:
    """Two empty inputs must never score as identical anywhere in this cascade."""
    assert patience_similarity([], []) == 0.0
