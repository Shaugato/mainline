# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""Refusals raised by ORIGINDIFF.  Each one is a fail-closed path, not an accident.

The naming follows the repository rule recorded in ``ruff.toml``: ``N818`` is off
because the refusal vocabulary is a product surface, and these words appear in
operator-facing messages.
"""

from __future__ import annotations

__all__ = [
    "BlameClosureAbsent",
    "DiachronicError",
    "FootprintError",
    "OriginUnresolvedError",
]


class DiachronicError(Exception):
    """Base class for every refusal this package raises."""


class BlameClosureAbsent(DiachronicError):
    """No ``clause_blame_current`` row exists for the subject version.

    This is **not** the same as "the clause has no blood ancestry".  A clause with
    a clean history has a closure row saying ``max_severity = 0``; a clause with
    *no closure row at all* is a clause whose projection has not run, and P2 is
    explicit that a gate reading an absent projection must refuse rather than
    assume.  Treating a missing closure as "no blood" would make *deleting the
    projection* the cheapest way to move a blame origin out of the gate's reach,
    which is the attack this whole package exists to close.

    The same ruling is enforced one layer down by worker W9's ``fn_residue_project``,
    which ``RAISE``s ``P0001`` when it cannot find the closure row it must project
    ``max_ancestral_severity`` from.
    """


class OriginUnresolvedError(DiachronicError):
    """The blame origin could not be resolved and the caller asked for a verdict.

    Raised by :func:`~mainline_domain.diachronic.ancestral_diff.delta_of_record`
    when the origin is neither *resolved* nor *inert* — the two states in which a
    delta of record is computable.  Answering with the parent diff alone would be
    a quieter verdict produced by an infrastructure failure, and a quieter verdict
    is exactly what an adversary is buying.
    """


class FootprintError(DiachronicError):
    """A commutation footprint could not be computed, or two edits were compared wrongly.

    The common case is a caller asking whether an edit commutes with *itself*.
    Commutation is irreflexive here by construction — an edit's footprint always
    overlaps its own — so the question is a caller bug rather than a state the
    data can be in, and answering ``False`` would put a self-edge in
    ``mainline.commutation_edge`` that the table's ``canonical_direction`` CHECK
    refuses anyway.
    """
