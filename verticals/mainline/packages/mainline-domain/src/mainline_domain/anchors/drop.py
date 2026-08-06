# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""Anchor drop — an independent weakening signal that needs no model.

An anchor that was in the reference version and is not in the descendant, with
**nothing of its class added in its place**, is an *uncompensated drop*.  That
is a ``control_delta='weaken'`` candidate on its own — no embedding, no lattice
rule, no oracle — and it writes ``identity_residue.reason='anchor_drop'``, which
is what the merge gate refuses on.

The compensation rule is the whole subtlety.  Consider three edits to
"isolate P-101A":

* ``P-101A`` -> (nothing).  The pump is gone from the clause.  **Uncompensated:
  weaken candidate.**
* ``P-101A`` -> ``P-101B``.  A same-class anchor arrived.  **Compensated**, and
  it is not the drop detector's business: ``AnchorSet.compatible_with`` already
  refuses to call these the same clause, which is a louder outcome than a drop.
* ``P-101A`` -> ``P-101A, P-101B``.  Nothing dropped at all.

So "compensated" means *an anchor of the same class was added*, not "an
equivalent anchor was added" — this module does not attempt to decide
equivalence, because deciding it wrongly is how a swap gets waved through.

**Reference, not parent.**  The reference set should be the *blame-origin*
version's anchors, not the immediate parent's (ORIGINDIFF, worker W6).  Twenty
commits that each drop nothing but whose composition drops an isolation point
are only visible against the origin.  This module takes whatever reference it is
handed and does not care which; the caller chooses, and the caller is diachronic.

Only :data:`~mainline_domain.contracts.IDENTITY_ANCHOR_CLASSES` are considered.
A dropped ``setpoint`` is rule R2's business and a dropped ``named_role`` is rule
R1's; routing them here would double-count one edit as two weakenings.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..contracts import IDENTITY_ANCHOR_CLASSES, AnchorClass, AnchorSet

__all__ = ["AnchorDrop", "analyse_drops", "has_uncompensated_drop", "uncompensated_drops"]


@dataclass(frozen=True, slots=True)
class AnchorDrop:
    """One anchor present in the reference and absent from the descendant."""

    cls: AnchorClass
    norm: str
    compensated: bool
    """``True`` iff the descendant added at least one *other* anchor of this class."""

    added_in_class: tuple[str, ...]
    """The same-class norms the descendant added, sorted — the arithmetic, kept."""


def analyse_drops(reference: AnchorSet, descendant: AnchorSet) -> tuple[AnchorDrop, ...]:
    """Every identity-class drop, compensated or not, in a stable order."""
    drops: list[AnchorDrop] = []
    for cls in sorted(IDENTITY_ANCHOR_CLASSES, key=lambda c: c.value):
        before = reference.norms(cls)
        after = descendant.norms(cls)
        missing = before - after
        if not missing:
            continue
        added = tuple(sorted(after - before))
        for norm in sorted(missing):
            drops.append(
                AnchorDrop(
                    cls=cls,
                    norm=norm,
                    compensated=bool(added),
                    added_in_class=added,
                )
            )
    return tuple(drops)


def uncompensated_drops(reference: AnchorSet, descendant: AnchorSet) -> tuple[AnchorDrop, ...]:
    """The drops that raise a ``weaken`` candidate on their own."""
    return tuple(drop for drop in analyse_drops(reference, descendant) if not drop.compensated)


def has_uncompensated_drop(reference: AnchorSet, descendant: AnchorSet) -> bool:
    """``True`` when this edit is a weakening candidate on anchors alone."""
    return bool(uncompensated_drops(reference, descendant))
