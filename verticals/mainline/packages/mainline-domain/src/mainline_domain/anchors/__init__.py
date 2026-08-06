# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""ANCHORLOCK — the seven hard-anchor classes and what they refuse.

Public surface::

    from mainline_domain.anchors import extract_anchors, uncompensated_drops

    reference  = extract_anchors(origin_canon_text)
    descendant = extract_anchors(new_canon_text)

    reference.compatible_with(descendant)     # False vetoes a semantic match
    uncompensated_drops(reference, descendant)  # each one is a weaken candidate

**Honest position (see ``novelty/anchorlock.yaml``): the gazetteer NER is old;
the coupling is what is unclaimed.**  Using an anchor set as a *veto over
cosine* — so a 0.97 semantic match with a different equipment tag is rejected
rather than accepted — and simultaneously as an *independent weakening signal*
whose absence writes a blocking residue row, is not something the surveyed
document-control systems express.
"""

from __future__ import annotations

from ..contracts import IDENTITY_ANCHOR_CLASSES, Anchor, AnchorClass, AnchorSet
from .cas import cas_check_digit, is_valid_cas
from .drop import AnchorDrop, analyse_drops, has_uncompensated_drop, uncompensated_drops
from .extract import extract_anchors, iter_anchors
from .gazetteer import Gazetteers, load_gazetteers

__all__ = [
    "IDENTITY_ANCHOR_CLASSES",
    "Anchor",
    "AnchorClass",
    "AnchorDrop",
    "AnchorSet",
    "Gazetteers",
    "analyse_drops",
    "cas_check_digit",
    "extract_anchors",
    "has_uncompensated_drop",
    "is_valid_cas",
    "iter_anchors",
    "load_gazetteers",
    "uncompensated_drops",
]
