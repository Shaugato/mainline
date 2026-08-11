# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""The commutation footprint: what it includes, what it refuses to include, and why."""

from __future__ import annotations

from _diachronic_fixtures import anchors, cat, pressure_cat
from mainline_domain.cat.schema import EMPTY_CAT
from mainline_domain.contracts import AnchorClass
from mainline_domain.diachronic.footprint import (
    FOOTPRINT_ANCHOR_CLASSES,
    Footprint,
    anchor_tokens,
    changed_tokens,
    control_class_key,
    footprint_from_tokens,
    footprint_of_edit,
    parameter_tokens,
)


def test_a_footprint_is_the_union_over_both_versions_not_the_difference():
    """ "In scope of", not "changed by" — the decision the module docstring defends.

    An edit that adjusts the deontic of a clause about ``P-101A`` did not change
    the tag, but it is an edit about that pump, and a second edit about the same
    pump is not independent of it.
    """
    tag = anchors((AnchorClass.EQUIPMENT_TAG, "P-101A"))
    footprint = footprint_of_edit(
        reference=pressure_cat("<=", "350", deontic="MUST"),
        descendant=pressure_cat("<=", "350", deontic="SHOULD"),
        reference_anchors=tag,
        descendant_anchors=tag,
    )
    assert "anchor:equipment_tag:P-101A" in footprint.tokens
    assert "param:max_operating_pressure" in footprint.tokens
    assert "control:pressure|pressure vessel|operate" in footprint.tokens
    assert (
        changed_tokens(
            reference=pressure_cat("<=", "350", deontic="MUST"),
            descendant=pressure_cat("<=", "350", deontic="SHOULD"),
            reference_anchors=tag,
            descendant_anchors=tag,
        )
        == ()
    )


def test_an_anchor_that_only_appears_on_one_side_is_still_in_the_footprint():
    footprint = footprint_of_edit(
        reference=EMPTY_CAT,
        descendant=EMPTY_CAT,
        reference_anchors=anchors((AnchorClass.EQUIPMENT_TAG, "P-101A")),
        descendant_anchors=anchors((AnchorClass.EQUIPMENT_TAG, "P-101B")),
    )
    assert footprint.sorted_tokens() == (
        "anchor:equipment_tag:P-101A",
        "anchor:equipment_tag:P-101B",
    )


def test_setpoint_and_named_role_anchors_are_deliberately_absent():
    """Two exclusions, each with a reason, each asserted rather than left to a comment.

    A ``setpoint`` token would put every clause carrying a number in one dependency
    clique; ``named_role`` is a poor discriminator and I15 makes a role-keyed
    dependency edge something to be careful with.
    """
    assert AnchorClass.SETPOINT not in FOOTPRINT_ANCHOR_CLASSES
    assert AnchorClass.NAMED_ROLE not in FOOTPRINT_ANCHOR_CLASSES

    tokens = anchor_tokens(
        anchors(
            (AnchorClass.SETPOINT, "350 kPa"),
            (AnchorClass.NAMED_ROLE, "Authorised Gas Tester"),
            (AnchorClass.EQUIPMENT_TAG, "P-101A"),
        )
    )
    assert tokens == frozenset({"anchor:equipment_tag:P-101A"})


def test_the_five_identity_classes_that_do_count_all_produce_tokens():
    for cls in FOOTPRINT_ANCHOR_CLASSES:
        tokens = anchor_tokens(anchors((cls, "X-1")))
        assert tokens == frozenset({f"anchor:{cls.value}:X-1"})


def test_an_empty_cat_implies_no_control_class():
    """A universal token would make the whole corpus one dependency clique."""
    assert control_class_key(EMPTY_CAT) is None
    assert footprint_of_edit(reference=EMPTY_CAT, descendant=EMPTY_CAT).tokens == frozenset()


def test_a_partially_filled_cat_still_implies_one_and_renders_the_gaps():
    key = control_class_key(cat(hazard_energy="Gravity"))
    assert key == "gravity|-|-"


def test_the_control_class_key_is_casefolded_and_whitespace_collapsed():
    a = control_class_key(cat(hazard_energy="Pressure", object_class="Pressure   Vessel"))
    b = control_class_key(cat(hazard_energy="pressure", object_class="pressure vessel"))
    assert a == b == "pressure|pressure vessel|-"


def test_a_cat_with_no_parameter_contributes_no_param_token():
    assert parameter_tokens(EMPTY_CAT) == frozenset()
    assert parameter_tokens(None) == frozenset()


def test_overlap_is_sorted_and_symmetric():
    left = Footprint(frozenset({"param:a", "param:b", "control:x"}))
    right = Footprint(frozenset({"param:b", "param:a", "control:y"}))
    assert left.overlap(right) == ("param:a", "param:b")
    assert left.overlap(right) == right.overlap(left)


def test_disjointness_is_reflexively_false_for_a_nonempty_footprint():
    """An edit always overlaps itself, which is what makes commutation irreflexive."""
    footprint = Footprint(frozenset({"param:a"}))
    assert footprint.is_disjoint(footprint) is False


def test_an_empty_footprint_is_disjoint_from_everything_which_is_why_it_is_refused():
    """The arithmetic is correct and the *answer* would be wrong, so `commutes` raises.

    This test pins the arithmetic here so that ``test_commutation.py``'s refusal is
    visibly a policy decision rather than a workaround for a set-theory surprise.
    """
    empty = Footprint(frozenset())
    assert empty.is_disjoint(Footprint(frozenset({"param:a"}))) is True
    assert bool(empty) is False


def test_a_footprint_round_trips_through_a_stored_overlap_array():
    original = Footprint(frozenset({"param:a", "anchor:cas:7664-93-9"}))
    assert footprint_from_tokens(original.sorted_tokens()) == original


def test_union_is_the_footprint_of_the_two_edits_taken_together():
    a = Footprint(frozenset({"param:a"}))
    b = Footprint(frozenset({"param:b"}))
    assert a.union(b).sorted_tokens() == ("param:a", "param:b")
