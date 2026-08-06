# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""The two things an anchor set is *for*: vetoing a match, and raising a weaken.

Both are asymmetric, and the asymmetry is the product:

* a **conflict** in an identity class refuses a match that cosine would have
  accepted;
* an **uncompensated drop** raises ``control_delta='weaken'`` with no model in
  the loop and writes ``identity_residue.reason='anchor_drop'``.

A dodge therefore has nowhere to go.  Keep the tag and the match holds; change
the tag and the match is refused; delete the tag and the drop fires.
"""

from __future__ import annotations

from mainline_domain.anchors import (
    analyse_drops,
    extract_anchors,
    has_uncompensated_drop,
    uncompensated_drops,
)
from mainline_domain.contracts import IDENTITY_ANCHOR_CLASSES, AnchorClass

ORIGIN = (
    "Before entry to P-101A the Authorised Gas Tester shall verify the "
    "atmosphere is below 10 % LEL and that LOTO-4471 is locked, per AS 2865."
)


def test_setpoint_is_not_an_identity_class() -> None:
    """A moved setpoint must reach the lattice, not hide behind a non-match."""
    assert AnchorClass.SETPOINT not in IDENTITY_ANCHOR_CLASSES
    assert AnchorClass.NAMED_ROLE not in IDENTITY_ANCHOR_CLASSES
    assert IDENTITY_ANCHOR_CLASSES == {
        AnchorClass.EQUIPMENT_TAG,
        AnchorClass.ISOLATION_POINT_ID,
        AnchorClass.CAS,
        AnchorClass.REGULATORY_CITATION,
        AnchorClass.INSTRUMENT_LOOP,
    }


def test_a_setpoint_change_does_not_break_identity() -> None:
    origin = extract_anchors(ORIGIN)
    loosened = extract_anchors(ORIGIN.replace("10 % LEL", "25 % LEL"))
    assert origin.compatible_with(loosened)
    assert not has_uncompensated_drop(origin, loosened)


def test_a_role_change_does_not_break_identity() -> None:
    origin = extract_anchors(ORIGIN)
    swapped = extract_anchors(ORIGIN.replace("Authorised Gas Tester", "competent person"))
    assert origin.compatible_with(swapped)


def test_a_tag_swap_is_a_conflict_not_a_drop() -> None:
    origin = extract_anchors(ORIGIN)
    swapped = extract_anchors(ORIGIN.replace("P-101A", "P-101B"))

    assert not origin.compatible_with(swapped)
    assert origin.conflicting_classes(swapped) == {AnchorClass.EQUIPMENT_TAG}
    # The drop is compensated: a same-class anchor arrived in its place.
    drops = analyse_drops(origin, swapped)
    assert [(d.cls, d.norm, d.compensated) for d in drops] == [
        (AnchorClass.EQUIPMENT_TAG, "P-101A", True)
    ]
    assert uncompensated_drops(origin, swapped) == ()


def test_adding_a_tag_is_not_a_conflict() -> None:
    origin = extract_anchors(ORIGIN)
    extended = extract_anchors(ORIGIN.replace("P-101A", "P-101A and P-101B"))
    assert origin.compatible_with(extended)
    assert uncompensated_drops(origin, extended) == ()


def test_deleting_an_isolation_point_is_an_uncompensated_drop() -> None:
    origin = extract_anchors(ORIGIN)
    weakened = extract_anchors(
        "Before entry to P-101A the Authorised Gas Tester shall verify the "
        "atmosphere is below 10 % LEL, per AS 2865."
    )

    # Compatible -- nothing conflicts, so a matcher would happily pair these.
    assert origin.compatible_with(weakened)
    # And that is exactly why the drop signal exists.
    drops = uncompensated_drops(origin, weakened)
    assert [(d.cls, d.norm) for d in drops] == [(AnchorClass.ISOLATION_POINT_ID, "LOTO-4471")]
    assert drops[0].added_in_class == ()
    assert has_uncompensated_drop(origin, weakened)


def test_deleting_a_citation_is_an_uncompensated_drop() -> None:
    origin = extract_anchors(ORIGIN)
    weakened = extract_anchors(ORIGIN.replace(", per AS 2865", ""))
    assert [(d.cls, d.norm) for d in uncompensated_drops(origin, weakened)] == [
        (AnchorClass.REGULATORY_CITATION, "AS 2865")
    ]


def test_replacing_a_citation_is_compensated_and_therefore_adjudicated() -> None:
    """A citation swap is a conflict, which is louder than a drop; not both."""
    origin = extract_anchors(ORIGIN)
    swapped = extract_anchors(ORIGIN.replace("AS 2865", "AS 1234"))

    assert not origin.compatible_with(swapped)
    assert uncompensated_drops(origin, swapped) == ()
    assert analyse_drops(origin, swapped)[0].added_in_class == ("AS 1234",)


def test_compatibility_is_symmetric_and_reflexive() -> None:
    origin = extract_anchors(ORIGIN)
    other = extract_anchors(ORIGIN.replace("P-101A", "P-101B"))

    assert origin.compatible_with(origin)
    assert origin.compatible_with(other) == other.compatible_with(origin)


def test_an_empty_set_conflicts_with_nothing() -> None:
    """Absence is a drop, never a conflict: a conflict needs two populated sides."""
    origin = extract_anchors(ORIGIN)
    empty = extract_anchors("Work shall be performed carefully.")

    assert origin.compatible_with(empty)
    assert empty.compatible_with(origin)
    assert len(uncompensated_drops(origin, empty)) == 3  # tag, isolation point, citation


def test_by_class_always_has_all_seven_keys() -> None:
    grouped = extract_anchors("Work shall be performed carefully.").by_class()
    assert set(grouped) == set(AnchorClass)
    assert all(value == frozenset() for value in grouped.values())


def test_identity_norms_excludes_setpoints_and_roles() -> None:
    anchors = extract_anchors(ORIGIN)
    assert anchors.identity_norms() == {"P-101A", "LOTO-4471", "AS 2865"}


def test_drop_order_is_stable() -> None:
    origin = extract_anchors(ORIGIN)
    empty = extract_anchors("Work shall be performed carefully.")
    first = [(d.cls.value, d.norm) for d in uncompensated_drops(origin, empty)]
    assert first == sorted(first)
