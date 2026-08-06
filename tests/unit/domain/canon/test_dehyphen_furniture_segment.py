# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""The three context-sensitive stages: de-hyphenation, furniture, segmentation.

Each of these can delete or invent text, so each is tested for the *direction*
of its failure, not just for a happy path.
"""

from __future__ import annotations

import pytest

# --------------------------------------------------------------------------- #
# de-hyphenation                                                               #
# --------------------------------------------------------------------------- #

WRAPS = [
    # (wrapped, unwrapped) — both MUST canonicalise identically
    ("isola-\ntion point", "isolation point"),
    ("ver-\nify the result", "verify the result"),
    ("pres-\nsure vessel", "pressure vessel"),
    ("lock-\nout applied", "lock-out applied"),
    ("hot-\nwork permit", "hot-work permit"),
    ("stand-\nby person", "stand-by person"),
]


@pytest.mark.parametrize(("wrapped", "unwrapped"), WRAPS)
def test_wrapping_is_invisible_to_the_digest(wrapped: str, unwrapped: str) -> None:
    from mainline_domain.canon import canonicalise

    assert canonicalise(wrapped).canon_sha256 == canonicalise(unwrapped).canon_sha256


def test_a_compound_keeps_its_hyphen_whether_or_not_the_line_wrapped() -> None:
    """The compound list is consulted BEFORE the closed-word list, on purpose."""
    from mainline_domain.canon.dehyphen import dehyphenate

    assert dehyphenate("lock-\nout") == "lock-out"
    assert dehyphenate("shut-\ndown") == "shut-down"


def test_an_unknown_fragment_pair_joins() -> None:
    """A wrap hyphen is overwhelmingly a typesetting artefact; join is the default."""
    from mainline_domain.canon.dehyphen import dehyphenate

    assert dehyphenate("zqx-\nvvt") == "zqxvvt"


def test_two_known_words_keep_the_hyphen() -> None:
    from mainline_domain.canon.dehyphen import dehyphenate

    assert dehyphenate("pressure-\nvessel") == "pressure-vessel"


def test_a_tag_hyphen_is_not_a_wrap_hyphen() -> None:
    """``P-\\n101A`` must not be joined into a different tag."""
    from mainline_domain.canon.dehyphen import dehyphenate

    assert dehyphenate("P-\n101A") == "P-\n101A"


def test_dehyphenation_is_idempotent() -> None:
    from mainline_domain.canon.dehyphen import dehyphenate

    once = dehyphenate("isola-\ntion and lock-\nout and a-\nb-\nc")
    assert dehyphenate(once) == once


# --------------------------------------------------------------------------- #
# page furniture                                                               #
# --------------------------------------------------------------------------- #

FURNITURE_LINES = [
    "Page 4 of 31",
    "Page 12",
    "Uncontrolled when printed",
    "UNCONTROLLED COPY",
    "Rev. 3 - 14 Mar 2019",
    "Revision B",
    "Commercial-in-confidence",
    "Document No: PRO-0042",
    "Copyright 2019 Example Pty Ltd",
    "- 7 -",
]

CONTENT_LINES = [
    "Version 2 of the isolation procedure shall be used for all confined space entry work.",
    "Revision of the permit shall occur whenever the scope of work changes materially.",
    "Document reference numbers shall be recorded on the permit before work starts.",
    "50",
    "The pump shall be isolated.",
    "Page turning is not a control.",
]


@pytest.mark.parametrize("line", FURNITURE_LINES)
def test_furniture_lines_are_stripped(line: str) -> None:
    from mainline_domain.canon.furniture import strip_furniture

    kept, removed = strip_furniture(f"Isolate the pump.\n{line}\nVerify the isolation.")
    assert kept == "Isolate the pump.\nVerify the isolation."
    assert len(removed) == 1


@pytest.mark.parametrize("line", CONTENT_LINES)
def test_content_lines_survive(line: str) -> None:
    from mainline_domain.canon.furniture import strip_furniture

    body = f"Isolate the pump.\n{line}\nVerify the isolation."
    kept, removed = strip_furniture(body)
    assert kept == body
    assert removed == ()


def test_stripping_never_empties_a_clause() -> None:
    """A clause that looks like a footer is still a clause."""
    from mainline_domain.canon.furniture import strip_furniture

    kept, removed = strip_furniture("Page 4 of 31")
    assert kept == "Page 4 of 31"
    assert removed == ()


def test_repetition_model_learns_a_site_header() -> None:
    from mainline_domain.canon.furniture import FurnitureModel, strip_furniture

    pages = [
        f"EXAMPLE MINE - ISOLATION STANDARD\nClause body {index} goes here.\nPage {index} of 3"
        for index in range(1, 4)
    ]
    model = FurnitureModel.from_pages(pages)
    assert "example mine - isolation standard" in model.masked_lines
    assert "page # of #" in model.masked_lines
    # The body repeats across pages once digits are masked, exactly as a header
    # does.  It must NOT be learned: the edge zone is capped at half the page.
    assert "clause body # goes here." not in model.masked_lines

    kept, removed = strip_furniture(pages[0], model)
    assert kept.strip() == "Clause body 1 goes here."
    assert len(removed) == 2


def test_repetition_model_needs_repetition() -> None:
    from mainline_domain.canon.furniture import FurnitureModel

    assert FurnitureModel.from_pages(["one page only"]).masked_lines == frozenset()


def test_furniture_spans_point_into_the_raw_text() -> None:
    from mainline_domain.canon import canonicalise

    raw = "Page 4 of 31\nIsolate the pump.\nUncontrolled when printed"
    result = canonicalise(raw)
    assert [raw[start:end] for start, end in result.furniture_spans] == [
        "Page 4 of 31",
        "Uncontrolled when printed",
    ]


# --------------------------------------------------------------------------- #
# content-defined segmentation                                                 #
# --------------------------------------------------------------------------- #


def _tokens(count: int, *, seed: str = "t") -> tuple[str, ...]:
    return tuple(f"{seed}{index}" for index in range(count))


def test_short_input_is_one_segment() -> None:
    from mainline_domain.canon.segment import MIN_TOKENS, segment_tokens

    assert segment_tokens(_tokens(MIN_TOKENS)) == ((0, MIN_TOKENS),)


def test_segments_cover_every_token_exactly_once() -> None:
    from mainline_domain.canon.segment import segment_tokens

    tokens = _tokens(2500)
    ranges = segment_tokens(tokens)
    assert ranges[0][0] == 0
    assert ranges[-1][1] == len(tokens)
    for (_, end), (start, _) in zip(ranges, ranges[1:]):
        assert end == start


def test_segment_sizes_respect_min_and_max() -> None:
    from mainline_domain.canon.segment import MAX_TOKENS, MIN_TOKENS, segment_tokens

    tokens = _tokens(5000)
    ranges = segment_tokens(tokens)
    for index, (start, end) in enumerate(ranges):
        size = end - start
        assert size <= MAX_TOKENS
        if index < len(ranges) - 1:
            assert size >= MIN_TOKENS


def test_a_local_edit_perturbs_only_local_boundaries() -> None:
    """The whole reason for content-defined chunking.

    Insert one token near the front of a long document and the boundaries far
    from the edit must be unchanged (shifted by exactly one index).  Fixed-size
    chunking would move every boundary, and every clause after the edit would
    look new.
    """
    from mainline_domain.canon.segment import segment_tokens

    tokens = _tokens(3000)
    edited = tokens[:50] + ("inserted",) + tokens[50:]

    before = segment_tokens(tokens)
    after = segment_tokens(edited)

    tail_before = {(start, end) for start, end in before if start > 1200}
    tail_after = {(start - 1, end - 1) for start, end in after if start > 1200}
    common = tail_before & tail_after
    assert len(common) >= max(1, int(0.8 * len(tail_before))), (
        "content-defined boundaries did not re-synchronise after a local edit"
    )


def test_segmentation_is_deterministic_across_processes() -> None:
    """The gear table is derived from a committed constant, not from ``hash``."""
    from mainline_domain.canon.segment import GEAR, gear_table

    assert GEAR == gear_table()
    assert len(GEAR) == 256
    assert GEAR[0] == int.from_bytes(
        __import__("hashlib")
        .blake2b(b"mainline/canon/gear/v1" + (0).to_bytes(2, "big"), digest_size=8)
        .digest(),
        "big",
    )


def test_masks_are_ordered_hard_then_easy() -> None:
    from mainline_domain.canon.segment import MASK_EASY, MASK_HARD

    assert MASK_HARD.bit_count() > MASK_EASY.bit_count()
    assert MASK_HARD < (1 << 64) and MASK_EASY < (1 << 64)
