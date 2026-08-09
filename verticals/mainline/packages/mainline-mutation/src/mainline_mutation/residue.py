# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""Which residue rows this edit would raise — a STAND-IN, and labelled as one.

WHAT THIS IS
------------
Worker W8 (``margin-assignment``) owns residue emission, and W9
(``cbm-enforcement``) owns the accounting that refuses a merge when it is
incomplete.  Neither has landed at the time this harness was written.  The
mutation ratchet needs *some* answer to "would this edit raise a blocking row",
because the KILL catalogue's success condition is a weakening verdict **or** a
residue row, and a harness that could only see the verdict would report the
lattice's kill rate wearing the whole pipeline's name.

So this module derives the five residue reasons from the same authoritative
facts W8 will derive them from — the anchor sets, the CAT confidence and the
cascade outcome — and every result row records ``residue_source =
"mutation-harness-local/v1"`` so that no published number can be mistaken for a
measurement of W8's implementation.

WHEN W8 LANDS
-------------
:func:`derive_residue` is the seam.  The runner takes an optional judge, so
swapping in ``mainline_domain.identity.assignment`` is one argument and the
``residue_source`` string on every row changes with it — which means the change
is visible in a diff of two artefacts rather than being an invisible improvement.

THE FIVE REASONS ARE THE FIVE IN THE DDL AND THERE IS NO SIXTH
---------------------------------------------------------------
``unmatched``, ``ambiguous``, ``anchor_drop``, ``opaque_control``,
``citation_unresolved`` — the ``CHECK`` on ``mainline.identity_residue`` and the
boundary note in ``docs/leads/algorithms.md`` §4.  A citation drop is routed to
``citation_unresolved`` rather than to ``anchor_drop`` because it is the more
specific of the two and because the person holding the permit needs to know that
what went missing was a legal reference.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Final

from mainline_domain.anchors.drop import uncompensated_drops
from mainline_domain.contracts import AnchorClass, ResidueReason

if TYPE_CHECKING:  # pragma: no cover - import cycle broken for typing only
    from .pipeline import ClauseView

__all__ = ["RESIDUE_SOURCE", "ResidueJudgement", "derive_residue"]

#: Stamped on every result row and every SQL row.  Changes when the derivation
#: does, which is the whole reason it is a string and not a boolean.
RESIDUE_SOURCE: Final[str] = "mutation-harness-local/v1"


@dataclass(frozen=True, slots=True)
class ResidueJudgement:
    """The residue reasons this edit would raise, and who decided."""

    reasons: tuple[ResidueReason, ...]
    source: str


def derive_residue(
    *,
    ancestor: ClauseView,
    descendant: ClauseView,
    recovered: bool,
) -> ResidueJudgement:
    """Derive the residue rows from the authoritative facts.  Never from the caller.

    ``opaque_control`` fires when **either** side is opaque, which is the
    fail-closed reading of risk R-A3 ("any edit to an opaque clause with
    severity >= 4 ancestry defaults to weaken").  Firing only on the descendant
    would let an adversary hide an edit behind an ancestor the extractor already
    could not read, which is the exact shape R-A3 names.
    """
    reasons: list[ResidueReason] = []

    if not recovered:
        reasons.append("unmatched")

    if "opaque" in (ancestor.cat_result.confidence, descendant.cat_result.confidence):
        reasons.append("opaque_control")

    dropped = tuple(uncompensated_drops(ancestor.anchors, descendant.anchors))
    if any(drop.cls is AnchorClass.REGULATORY_CITATION for drop in dropped):
        reasons.append("citation_unresolved")
    if any(drop.cls is not AnchorClass.REGULATORY_CITATION for drop in dropped):
        reasons.append("anchor_drop")

    # `ambiguous` is deliberately never emitted here. It is degeneracy in the
    # LAP optimum (decision D4) and this harness runs a one-member corpus, in
    # which no optimum can be degenerate. Emitting it would be inventing a
    # blocking row the matcher never produced.
    return ResidueJudgement(reasons=tuple(reasons), source=RESIDUE_SOURCE)
