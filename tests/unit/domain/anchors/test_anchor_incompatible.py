# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""ANCHORLOCK exit criterion 2 — a paraphrase that swaps the tag is a NON-match.

PL-2 RED-BEFORE-GREEN.  Committed and run before any implementation.
Recorded red run (2026-08-04, local, Python 3.14.3)::

    tests/unit/domain/anchors/test_anchor_incompatible.py::test_p101a_to_p101b_paraphrase_is_anchor_incompatible
    E   ModuleNotFoundError: No module named 'mainline_domain'

This is the dominant embedding failure mode — two structurally identical
clauses about *different equipment*.  Cosine will happily call these the same
clause; the anchor veto is what refuses.
"""

from __future__ import annotations

REFERENCE = (
    "Before any intrusive work on P-101A, the Authorised Gas Tester shall verify "
    "that the atmosphere is below 10 % LEL."
)

# Same meaning, different words, DIFFERENT PUMP.  Cosine similarity is ~0.97.
PARAPHRASE_DIFFERENT_TAG = (
    "Prior to any intrusive activity on P-101B, an Authorised Gas Tester must "
    "confirm the atmosphere reads under 10 % LEL."
)

# Same meaning, different words, SAME pump.
PARAPHRASE_SAME_TAG = (
    "Prior to any intrusive activity on P-101A, an Authorised Gas Tester must "
    "confirm the atmosphere reads under 10 % LEL."
)


def test_p101a_to_p101b_paraphrase_is_anchor_incompatible() -> None:
    from mainline_domain.anchors import extract_anchors

    reference = extract_anchors(REFERENCE)
    descendant = extract_anchors(PARAPHRASE_DIFFERENT_TAG)

    assert reference.compatible_with(descendant) is False
    assert descendant.compatible_with(reference) is False


def test_same_tag_paraphrase_stays_compatible() -> None:
    """The veto must not fire on a genuine reword — that would manufacture residue."""
    from mainline_domain.anchors import extract_anchors

    reference = extract_anchors(REFERENCE)
    descendant = extract_anchors(PARAPHRASE_SAME_TAG)

    assert reference.compatible_with(descendant) is True


def test_the_tag_is_actually_extracted() -> None:
    """Guard against a vacuous pass: an extractor that finds nothing is 'compatible'."""
    from mainline_domain.anchors import extract_anchors
    from mainline_domain.contracts import AnchorClass

    reference = extract_anchors(REFERENCE)
    tags = {a.norm for a in reference.by_class()[AnchorClass.EQUIPMENT_TAG]}
    assert tags == {"P-101A"}

    descendant = extract_anchors(PARAPHRASE_DIFFERENT_TAG)
    assert {a.norm for a in descendant.by_class()[AnchorClass.EQUIPMENT_TAG]} == {"P-101B"}
