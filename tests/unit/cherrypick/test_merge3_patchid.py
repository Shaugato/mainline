# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
"""The deterministic merge, and the digest that recognises the same change elsewhere."""

from __future__ import annotations

import pytest
from cherrypick_corpus import BASE_TEXT, DELTA_SET, FLEET_TEXT, SITE_TEXT
from mainline_cherrypick import (
    ClauseDelta,
    digest_lines,
    merge3,
    normalise_delta_set,
    patch_digest,
)
from mainline_domain.contracts import ControlDelta

# ── three-way merge ──────────────────────────────────────────────────────────


def test_an_edit_on_one_side_only_merges_cleanly():
    result = merge3(BASE_TEXT, BASE_TEXT, FLEET_TEXT)
    assert result.clean
    assert result.merged == FLEET_TEXT


def test_the_same_edit_on_both_sides_merges_cleanly():
    result = merge3(BASE_TEXT, FLEET_TEXT, FLEET_TEXT)
    assert result.clean
    assert result.merged == FLEET_TEXT


def test_two_different_edits_to_the_same_line_conflict():
    result = merge3(BASE_TEXT, SITE_TEXT, FLEET_TEXT)
    assert not result.clean
    assert result.merged is None
    (region,) = _regions_touching_isolation(result)
    assert "tagged" in region.ours[0]
    assert "locked" in region.theirs[0]


def test_a_conflicted_merge_never_returns_partly_merged_text():
    # Git writes markers into the working tree; a procedure containing '<<<<<<<'
    # is a document a person can commit by accident.
    result = merge3(BASE_TEXT, SITE_TEXT, FLEET_TEXT)
    assert result.merged is None


def test_markers_are_available_for_display_and_are_labelled():
    result = merge3(BASE_TEXT, SITE_TEXT, FLEET_TEXT)
    rendered = result.render_markers()
    assert "<<<<<<< SITE" in rendered
    assert ">>>>>>> FLEET" in rendered
    assert "||||||| base" in rendered


def test_edits_in_different_regions_both_survive():
    base = ("a", "b", "c", "d", "e")
    ours = ("A", "b", "c", "d", "e")
    theirs = ("a", "b", "c", "d", "E")
    result = merge3(base, ours, theirs)
    assert result.clean
    assert result.merged == ("A", "b", "c", "d", "E")


def test_the_merge_is_bit_identical_across_runs():
    first = merge3(BASE_TEXT, SITE_TEXT, FLEET_TEXT)
    second = merge3(BASE_TEXT, SITE_TEXT, FLEET_TEXT)
    assert first == second


def test_an_empty_base_with_two_different_additions_conflicts():
    result = merge3((), ("ours",), ("theirs",))
    assert not result.clean


def test_identical_inputs_merge_to_themselves():
    result = merge3(BASE_TEXT, BASE_TEXT, BASE_TEXT)
    assert result.clean
    assert result.merged == BASE_TEXT


def test_a_deletion_on_one_side_only_is_applied():
    base = ("a", "b", "c")
    result = merge3(base, base, ("a", "c"))
    assert result.clean
    assert result.merged == ("a", "c")


def test_a_clean_merge_is_not_approval():
    # The API offers no `apply()` and no write path. This is the assertion that
    # keeps that true: nothing in the package turns a clean merge into a commit.
    import mainline_cherrypick

    surface = set(mainline_cherrypick.__all__)
    assert not {name for name in surface if "apply" in name.lower()}


# ── digests ──────────────────────────────────────────────────────────────────


def test_a_rendering_digest_is_domain_separated_and_32_bytes():
    digest = digest_lines(BASE_TEXT)
    assert len(digest) == 32
    assert digest != digest_lines(FLEET_TEXT)


def test_the_patch_digest_is_order_independent():
    forward = patch_digest(DELTA_SET)
    backward = patch_digest(tuple(reversed(DELTA_SET)))
    assert forward == backward


def test_the_patch_digest_absorbs_a_duplicated_element():
    assert patch_digest(DELTA_SET) == patch_digest((*DELTA_SET, DELTA_SET[0]))


def test_the_patch_digest_changes_when_the_control_changes():
    other = (
        ClauseDelta(before="cat1:9f2c1a4d", after="cat1:ffffffff", delta=ControlDelta.STRENGTHEN),
        DELTA_SET[1],
    )
    assert patch_digest(DELTA_SET) != patch_digest(other)


def test_the_normalised_form_is_sorted_and_has_a_fixed_key_set():
    rendered = normalise_delta_set(DELTA_SET)
    assert rendered == sorted(
        rendered, key=lambda row: (row["before"] or "", row["after"] or "", row["delta"])
    )
    assert all(set(row) == {"after", "before", "delta"} for row in rendered)


def test_an_empty_delta_set_refuses_rather_than_sharing_one_digest():
    with pytest.raises(ValueError, match="empty lesson"):
        patch_digest(())


def test_a_delta_element_that_changes_nothing_refuses():
    with pytest.raises(ValueError, match="describes no change"):
        ClauseDelta(before=None, after=None, delta=ControlDelta.RESTATE)


def test_a_no_op_cannot_be_labelled_a_tightening():
    with pytest.raises(ValueError, match="no-op travel as a tightening"):
        ClauseDelta(before="cat1:aa", after="cat1:aa", delta=ControlDelta.STRENGTHEN)


def _regions_touching_isolation(result):
    return [region for region in result.conflicts if region.ours or region.theirs]
