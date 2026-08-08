# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""The order on ``control_delta``: the join W6 composes with, and the involution.

Two different structures live on the same five labels and conflating them is the
easiest mistake in this domain, so they are separated here and each is named.

THE CHAIN — a total order used for the JOIN
-------------------------------------------
::

    introduce  ≺  restate  ≺  strengthen  ≺  weaken  ≺  remove
    force  0        0            0             2         3

:func:`join` is the maximum along that chain.  It is what ORIGINDIFF (worker W6)
uses to implement decision D7 — *the ``control_delta`` of record is the more
forceful of ``delta(parent→new)`` and ``delta(blame_origin→new)``* — and what
this module's own :func:`~mainline_domain.lattice.decide.decide` uses to fold
nine independent rule findings into one verdict.

Why the three force-0 labels sit in *that* order, since force alone does not
separate them:

* ``introduce`` is a claim that **the control did not exist at the baseline**.
  Every other label presupposes that it did.  So any other label defeats it: if
  one baseline had the control, the edit is not an introduction.  That makes
  ``introduce`` the bottom of the chain and the identity of the join.
* ``restate`` is the null edit among labels that presuppose existence.
* ``strengthen`` is a real move, in the safe direction.  It defeats ``restate``
  because "something moved" is strictly more than "nothing moved".

The property that is actually load-bearing — and that
``tests/unit/domain/lattice/test_order.py`` proves over the full 5×5 product — is
that **force is monotone non-decreasing along the chain**, hence::

    force(join(a, b)) == max(force(a), force(b))

That equation is what the ABSTENTION RATCHET (worker W5) needs: composing
verdicts can raise the force the gate reacts with and can never lower it.  The
tie-break among the three force-0 labels is a *reporting* decision and changes
nothing a gate reads.

THE INVOLUTION — used only for testing, never for deciding
----------------------------------------------------------
::

    dual(weaken)    = strengthen        dual(strengthen) = weaken
    dual(remove)    = introduce         dual(introduce)  = remove
    dual(restate)   = restate

:func:`dual` is the semantic inverse of an edit: what the same pair of clause
versions would be called if you read the diff backwards.  It is **not** an order
automorphism and it does not preserve force — ``force(introduce) = 0`` while
``force(remove) = 3`` — and that asymmetry is the entire product.  Adding a
control is safe; deleting one is not.  Nothing in the decision path calls
:func:`dual`; it exists so the duality property test can state "a strengthen is
the exact dual of a weaken under field inversion" as an equation rather than as
a paragraph.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Final

from ..contracts import ControlDelta, force

__all__ = [
    "CHAIN",
    "NEUTRAL",
    "dual",
    "is_weakening",
    "join",
    "rank",
]

CHAIN: Final[tuple[ControlDelta, ...]] = (
    ControlDelta.INTRODUCE,
    ControlDelta.RESTATE,
    ControlDelta.STRENGTHEN,
    ControlDelta.WEAKEN,
    ControlDelta.REMOVE,
)
"""The total order the join maximises over, weakest first."""

#: The verdict of an edit with no findings at all.  Deliberately ``restate`` and
#: not ``CHAIN[0]``: an edit that produced no finding is a **restatement of an
#: existing control**, and calling it ``introduce`` would assert something about
#: the baseline that no rule established.  The bottom of the chain and the empty
#: verdict are different questions and this constant keeps them apart.
NEUTRAL: Final[ControlDelta] = ControlDelta.RESTATE

_RANK: Final[dict[ControlDelta, int]] = {delta: i for i, delta in enumerate(CHAIN)}

_DUAL: Final[dict[ControlDelta, ControlDelta]] = {
    ControlDelta.WEAKEN: ControlDelta.STRENGTHEN,
    ControlDelta.STRENGTHEN: ControlDelta.WEAKEN,
    ControlDelta.REMOVE: ControlDelta.INTRODUCE,
    ControlDelta.INTRODUCE: ControlDelta.REMOVE,
    ControlDelta.RESTATE: ControlDelta.RESTATE,
}


def rank(delta: ControlDelta) -> int:
    """Position along :data:`CHAIN`.  ``0`` is ``introduce``, ``4`` is ``remove``."""
    return _RANK[delta]


def join(deltas: Iterable[ControlDelta]) -> ControlDelta:
    """The least upper bound along :data:`CHAIN`.  Empty input is :data:`NEUTRAL`.

    Takes an iterable rather than varargs because every caller in this domain has
    a sequence in hand, and ``join(*findings)`` invites a caller to write
    ``join(a, b)`` on two *iterables* by mistake.
    """
    best = None
    for delta in deltas:
        if best is None or _RANK[delta] > _RANK[best]:
            best = delta
    return NEUTRAL if best is None else best


def dual(delta: ControlDelta) -> ControlDelta:
    """The semantic inverse of an edit: what the reversed diff would be called."""
    return _DUAL[delta]


def is_weakening(delta: ControlDelta) -> bool:
    """``True`` for the two labels the merge gate reacts to: ``weaken``, ``remove``.

    Written as ``force(delta) > 0`` rather than as membership in a set, because
    ``force`` is worker W1's frozen definition of *how loudly the gate must
    react* and a second, independently-maintained list of "the bad ones" is
    exactly the sort of duplicate that drifts.
    """
    return force(delta) > 0
