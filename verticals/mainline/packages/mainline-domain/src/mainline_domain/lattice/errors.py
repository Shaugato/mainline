# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""The two things DELTALATTICE refuses to do, as exceptions.

There are deliberately only two, and neither of them is "I could not decide".
An undecidable comparison is not an error in this package — it is a
``ControlDelta.WEAKEN`` finding carrying its own witness, because principle P3
says the failure mode of a safety gate is a block, not a stack trace.  An
exception here always means the **caller** handed the lattice something it must
not silently accept.
"""

from __future__ import annotations

__all__ = ["LatticeError", "WitnesslessWeakenError"]


class LatticeError(Exception):
    """A caller error: an input the lattice must not paper over.

    Raised in exactly three places, all of them in
    :mod:`mainline_domain.lattice.decide`:

    * both sides of the comparison are ``None``, so there is no edit to judge;
    * the registry handed in was read at a commit other than the one under test,
      which would let a verdict be re-derived under a registry that has since
      moved — the retro-tuning hazard ``0150_v_safe_direction_current.sql``'s
      header names;
    * the emitted witness set failed its own minimality post-condition, which is
      an internal contradiction rather than a document state.
    """


class WitnesslessWeakenError(LatticeError, ValueError):
    """Decision D8, in Python: a lattice ``weaken``/``remove`` with no witnesses.

    Also a :class:`ValueError`, because a caller catching ``ValueError`` around
    verdict construction is doing something reasonable and should not have to
    know this package's exception tree.

    **This is not the gate.**  ``contracts.DeltaVerdict`` is a plain frozen
    dataclass owned by worker W1 and can hold the forbidden shape; the refusal
    that matters is ``mainline.fn_delta_witness_guard`` (migration ``0140``,
    attached to ``mainline.clause_version`` by ``0145``), which raises ``P0001``
    for every writer, forever, including one that has never imported this
    package.  This exception exists so the projector fails at the point the
    mistake was made rather than one round trip later.
    """
