# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""The refusal vocabulary of Proof of Exhausted Recall.

Every name here is a sentence a stranger reads in a verifier's output, so each one says what
was wrong rather than that something was. ``PerRefused`` is the single base, because a caller
that wants "did the proof hold?" should not have to enumerate the ways it can fail — while a
caller that wants to *report* which way it failed can, and the CLI does.

None of these is retryable. A proof either holds over the bytes it was given or it does not,
and a verifier that retried would be answering a different question the second time.
"""

from __future__ import annotations

__all__ = [
    "BoundaryInconsistent",
    "ExhaustionOverclaim",
    "InvalidLeaf",
    "InvalidProof",
    "NotCanonicalisable",
    "PerRefused",
    "RootMismatch",
    "UnsortedCandidates",
]


class PerRefused(ValueError):
    """Base: the commitment could not be built, or could not be verified."""


class NotCanonicalisable(PerRefused):
    """A leaf member is outside the frozen leaf profile (see :mod:`.canon`)."""


class InvalidLeaf(PerRefused):
    """A leaf field is absent, mistyped, or outside its declared range."""


class UnsortedCandidates(PerRefused):
    """The leaf sequence is not score-sorted.

    This is the one failure that voids the whole mechanism rather than one proof: the force
    of the boundary disclosure is *"no item can be hand-excluded without breaking
    sortedness"*, so an unsorted sequence proves nothing at all about what lies past ``s``.
    """


class BoundaryInconsistent(PerRefused):
    """``(theta, s, n)`` disagrees with the leaves it claims to describe."""


class InvalidProof(PerRefused):
    """An inclusion path is malformed, or the wrong length for its ``(index, n)``."""


class RootMismatch(PerRefused):
    """A recomputed root differs from the committed one.

    In the field this is what a removed, added or edited candidate looks like.
    """


class ExhaustionOverclaim(PerRefused):
    """A receipt tried to claim exhaustion under an ``UNDETERMINED`` coverage certificate.

    M4 CUE HORIZON's whole content: where coverage cannot be certified, the verdict is
    ``UNDETERMINED`` and PER **may not** claim exhaustion. The builder refuses rather than
    emitting a receipt that overclaims, because a proof that overclaims is worse than none —
    a caller that genuinely wants the weaker artefact sets ``not_exhaustive=True`` and the
    receipt says so on its face, where an opposing expert will read it.
    """
