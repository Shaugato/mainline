# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""The commutation footprint — what a clause edit is *about*.

An edit's footprint is a set of typed tokens in three namespaces:

===============================  =========================================
``anchor:<class>:<norm>``        every identity anchor in scope of the edit
``param:<parameter>``            every CAT parameter the edit asserts on
``control:<hazard>|<obj>|<act>`` the control class the edit implies
===============================  =========================================

Two edits **commute** iff their footprints are disjoint (:mod:`.commutation`).
Non-commuting pairs are *derived* dependency edges, which is invariant I06: a
dependency a gate consumes is computed, never declared.

"IN SCOPE OF", NOT "CHANGED BY" — THE DECISION THAT MATTERS HERE
----------------------------------------------------------------
A footprint is the **union over both versions**, not the symmetric difference.
An edit that adjusts the deontic of a clause about ``P-101A`` did not *change*
``P-101A``, but it is an edit about that pump, and a second edit about the same
pump is not independent of it.  Reading "touched" as "changed" would make two
edits to the same equipment commute whenever neither retyped the tag — which is
almost always — and the derived dependency set would be empty precisely where it
matters.

The cost of this reading is stated rather than hidden: the footprint is *wide*, so
edits commute less often, so more derived dependency edges exist, so the antecedent
set the weaken gate reads is larger.  That is the fail-closed direction (a wider
antecedent set can only make the gate louder), and the nuisance cost of it is
unmeasured — it is named in ``novelty/commutation-footprint.yaml`` under
``unverified`` and it is what worker W10's mutation ratchet is for.
:func:`changed_tokens` computes the narrow symmetric-difference view for callers
that want to *explain* an overlap; nothing decides commutation from it.

WHAT IS DELIBERATELY NOT IN A FOOTPRINT
----------------------------------------
* **``setpoint`` anchors.**  ``setpoint`` is not an identity anchor class
  (``contracts.IDENTITY_ANCHOR_CLASSES``) and it is not in a footprint either.
  Every clause carrying a number would otherwise share a token with every other,
  and the relation would degenerate to "nothing commutes".  The semantic version
  of the same fact — *which parameter* is under control — is the ``param:``
  namespace, which is specific.
* **``named_role`` anchors.**  Same reason at the other end: "Authorised Gas
  Tester" appears in a large fraction of a site's clauses, so it is a poor
  discriminator, and I15's allegation firewall makes a role-keyed dependency edge
  a thing to be careful with rather than a thing to derive by default.
* **Free text.**  ``conditions``/``exceptions``/``verification`` carry prose. A
  footprint over prose would be a similarity measure wearing a set's clothes, and
  the whole point of this construction is that it is exact, model-free and
  reproducible.

``control:`` IS A WITHIN-DOMAIN KEY AND IS NOT JOINED TO ANYTHING
------------------------------------------------------------------
``mainline.control_failure.control_class`` is described in ``ARCHITECTURE.md``
§5.4 as *the join key to a clause's CAT control class*, and no module in this
repository yet derives that key from a CAT.  :func:`control_class_key` is **this
package's** derivation and it is used **only** to decide commutation between two
edits computed by this same package.  It is not joined against
``control_failure``, and any future code that wants to join them must first prove
the two derivations agree — a claim this worker does not make.  Saying so here is
cheaper than discovering it from a blame edge that attached to the wrong clause.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Final

from ..contracts import CAT, IDENTITY_ANCHOR_CLASSES, AnchorClass, AnchorSet

__all__ = [
    "ANCHOR_NAMESPACE",
    "CONTROL_NAMESPACE",
    "FOOTPRINT_ANCHOR_CLASSES",
    "PARAMETER_NAMESPACE",
    "Footprint",
    "anchor_tokens",
    "changed_tokens",
    "control_class_key",
    "control_tokens",
    "footprint_from_tokens",
    "footprint_of_edit",
    "parameter_tokens",
]

ANCHOR_NAMESPACE: Final[str] = "anchor"
PARAMETER_NAMESPACE: Final[str] = "param"
CONTROL_NAMESPACE: Final[str] = "control"

FOOTPRINT_ANCHOR_CLASSES: Final[frozenset[AnchorClass]] = IDENTITY_ANCHOR_CLASSES - {
    AnchorClass.NAMED_ROLE
}
"""The anchor classes a footprint keys on.

``IDENTITY_ANCHOR_CLASSES`` minus ``named_role``, and written as a subtraction
rather than as a fresh literal so that a seventh identity class added by worker W1
arrives here automatically instead of being silently excluded by a hand-copied
list.  ``named_role`` is already absent from ``IDENTITY_ANCHOR_CLASSES`` today;
the subtraction is what keeps it absent if that ever changes.
"""

_WHITESPACE = re.compile(r"\s+")
_EMPTY_SLOT: Final[str] = "-"


def _norm_slot(value: str) -> str:
    """Normalise one closed-vocabulary CAT slot for use inside a token."""
    collapsed = _WHITESPACE.sub(" ", value).strip().casefold()
    return collapsed or _EMPTY_SLOT


def control_class_key(cat: CAT) -> str | None:
    """Return this package's control-class key for a CAT, or ``None`` for an empty one.

    ``<hazard_energy>|<object_class>|<action>``, each slot casefolded with its
    whitespace collapsed and an empty slot rendered ``'-'``.  A CAT with all three
    slots empty yields ``None`` rather than ``'-|-|-'``: a universal token would
    overlap every other edit's footprint and make the whole corpus one dependency
    clique, which is the degenerate answer wearing a conservative one's costume.
    """
    hazard = _norm_slot(cat.hazard_energy)
    obj = _norm_slot(cat.object_class)
    action = _norm_slot(cat.action)
    if hazard == obj == action == _EMPTY_SLOT:
        return None
    return f"{hazard}|{obj}|{action}"


def anchor_tokens(anchors: AnchorSet | None) -> frozenset[str]:
    """Return the ``anchor:`` tokens of one anchor set.  ``None`` yields the empty set."""
    if anchors is None:
        return frozenset()
    return frozenset(
        f"{ANCHOR_NAMESPACE}:{anchor.cls.value}:{anchor.norm}"
        for anchor in anchors.items
        if anchor.cls in FOOTPRINT_ANCHOR_CLASSES and anchor.norm
    )


def parameter_tokens(cat: CAT | None) -> frozenset[str]:
    """Return the ``param:`` tokens of one CAT.  ``None`` or an unnamed parameter yields ``()``."""
    if cat is None or not cat.parameter:
        return frozenset()
    return frozenset({f"{PARAMETER_NAMESPACE}:{_norm_slot(cat.parameter)}"})


def control_tokens(cat: CAT | None) -> frozenset[str]:
    """Return the ``control:`` token of one CAT.  ``None`` or an empty CAT yields ``()``."""
    if cat is None:
        return frozenset()
    key = control_class_key(cat)
    return frozenset() if key is None else frozenset({f"{CONTROL_NAMESPACE}:{key}"})


@dataclass(frozen=True, slots=True)
class Footprint:
    """The set of things one clause edit is about.

    Immutable and set-valued, so :meth:`is_disjoint` is exact and symmetric by
    construction rather than by a convention two call sites have to keep.
    """

    tokens: frozenset[str]

    def __bool__(self) -> bool:
        """Report whether the footprint names anything at all."""
        return bool(self.tokens)

    def sorted_tokens(self) -> tuple[str, ...]:
        """Return the tokens in a stable order — what goes into ``footprint_overlap``."""
        return tuple(sorted(self.tokens))

    def overlap(self, other: Footprint) -> tuple[str, ...]:
        """Return the shared tokens, sorted.  Empty exactly when the two commute."""
        return tuple(sorted(self.tokens & other.tokens))

    def is_disjoint(self, other: Footprint) -> bool:
        """Report whether the two edits share nothing and therefore commute."""
        return self.tokens.isdisjoint(other.tokens)

    def union(self, other: Footprint) -> Footprint:
        """Return the footprint of the two edits considered as one."""
        return Footprint(tokens=self.tokens | other.tokens)


def footprint_of_edit(
    *,
    reference: CAT | None,
    descendant: CAT | None,
    reference_anchors: AnchorSet | None = None,
    descendant_anchors: AnchorSet | None = None,
) -> Footprint:
    """Return the footprint of one clause edit: everything in scope on either side.

    ``reference`` is whichever version the edit is measured from — the parent for
    an ordinary edit, the blame origin under ORIGINDIFF.  The union makes the
    choice immaterial for the *dependency* question: an edit is about the same
    equipment and the same parameter whichever baseline named it.

    An edit with no CAT and no anchors on either side yields an **empty**
    footprint, and an empty footprint is disjoint from everything, so such an edit
    commutes with every other.  That is the honest answer — nothing is known about
    what it touched — and it is also the fail-*open* one, which is why
    :func:`~mainline_domain.diachronic.commutation.commutes` refuses to answer for
    an empty footprint rather than reporting ``True``.
    """
    return Footprint(
        tokens=(
            anchor_tokens(reference_anchors)
            | anchor_tokens(descendant_anchors)
            | parameter_tokens(reference)
            | parameter_tokens(descendant)
            | control_tokens(reference)
            | control_tokens(descendant)
        )
    )


def changed_tokens(
    *,
    reference: CAT | None,
    descendant: CAT | None,
    reference_anchors: AnchorSet | None = None,
    descendant_anchors: AnchorSet | None = None,
) -> tuple[str, ...]:
    """Return the tokens that differ between the two versions, sorted.

    The narrow, symmetric-difference view of an edit.  **Nothing decides
    commutation from this** — see the module docstring — but it is what a person
    reading "these two edits do not commute, and here is the overlap" wants beside
    the overlap: which of the shared tokens either edit actually moved.
    """
    before = (
        anchor_tokens(reference_anchors) | parameter_tokens(reference) | control_tokens(reference)
    )
    after = (
        anchor_tokens(descendant_anchors)
        | parameter_tokens(descendant)
        | control_tokens(descendant)
    )
    return tuple(sorted(before ^ after))


def footprint_from_tokens(tokens: Iterable[str]) -> Footprint:
    """Rebuild a :class:`Footprint` from a stored ``footprint_overlap`` array."""
    return Footprint(tokens=frozenset(tokens))
