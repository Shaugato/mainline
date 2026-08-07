# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""The local vocabulary of the candidate cascade.

``contracts.py`` is frozen and owned by W1; §4 of ``docs/leads/algorithms.md``
says a worker that needs a new shared type defines it **inside its own
subpackage**.  These are those types.  They are deliberately small: a stage
reads :class:`ClauseRecord` values and emits
:class:`~mainline_domain.contracts.Candidate` values plus
:class:`DroppedCandidate` values, and nothing else crosses the boundary.

The one rule that shapes every type here: **nothing silently drops.**  A stage
that discards a pair records *why*, with the arithmetic that decided it, in a
:class:`DroppedCandidate`.  A drop with no recorded reason is indistinguishable
from a matcher bug, and a matcher bug in this system is a permit that merged.

**Boundary note — drop reasons are not residue reasons.**  :data:`DropReason`
is this package's vocabulary for *why a pair did not become a candidate*.  The
five ``identity_residue.reason`` values in the DDL ``CHECK`` are a different,
smaller vocabulary about *why an ancestor obligation was left unaccounted for*,
and the mapping between them is the assignment worker's (W8) decision, not
this package's.  No stage here ever writes a residue row.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Literal
from uuid import UUID

from mainline_domain.contracts import AnchorSet, Candidate, Stage

__all__ = [
    "ClauseRecord",
    "ClauseRef",
    "DropReason",
    "DroppedCandidate",
    "StageResult",
    "order_candidates",
]


@dataclass(frozen=True, slots=True)
class ClauseRef:
    """The primary key of one clause *version*.

    ``commit_id`` is ``BYTES`` in the DDL (a SHA-256 content address), so it is
    ``bytes`` here and never a ``UUID``.  A stage that returns a bare
    ``clause_uuid`` is ambiguous across the commit DAG, which is exactly the
    ambiguity diachronic gating exists to remove.
    """

    clause_uuid: UUID
    commit_id: bytes


@dataclass(frozen=True, slots=True)
class ClauseRecord:
    """One indexed clause version, as the cascade sees it.

    This is a *projection* of ``mainline.clause_version`` (plus the anchors that
    W1 extracts from ``canon_text``), carried in memory so that S1-S3 can run
    with no cluster at all.  ``anchors`` is not optional: a record assembled
    without its anchor set would let a semantic candidate through the veto by
    default, and a veto that fails open is not a veto.
    """

    ref: ClauseRef
    site_id: UUID
    activity_root: str
    canon_text: str
    canon_sha256: bytes
    anchors: AnchorSet


DropReason = Literal[
    "anchor_conflict",
    "no_identity_anchors",
    "anchor_set_differs",
    "trigram_floor",
    "band_miss",
    "auto_reject",
    "self_pair",
]
"""Why a pair was refused *by a stage*.

* ``anchor_conflict`` — the identity anchor sets are incompatible.  This is the
  veto over cosine (S4) and it fires **before** the score is looked at.
* ``no_identity_anchors`` — S2 only: neither side carries an identity anchor,
  so anchor-set equality is vacuous and cannot be used as evidence.
* ``anchor_set_differs`` — S2 only: both sides carry identity anchors and the
  sets are not equal.  Compatible-but-unequal (an added tag) lands here, so it
  falls through to S3/S4 rather than being auto-accepted.
* ``trigram_floor`` — S2 only: anchors agreed but the trigram similarity is
  below the floor, so the anchor agreement is carrying the whole match.
* ``band_miss`` — S3 only: the pair shared no LSH band.  Recorded per *query*,
  not per pair, because the point of banding is that unshared pairs are never
  enumerated.
* ``auto_reject`` — the stage scored the pair below its auto-reject band.
* ``self_pair`` — the candidate is the query's own row.
"""


@dataclass(frozen=True, slots=True)
class DroppedCandidate:
    """A pair a stage refused, with the arithmetic that refused it.

    ``detail`` holds every number the decision used.  It is the same shape as
    ``Candidate.features`` on purpose: an adjudicator comparing an accepted
    candidate with a rejected one is comparing two dictionaries with the same
    keys, not a dictionary against a log line.
    """

    ancestor_clause_uuid: UUID
    ancestor_commit: bytes
    stage: Stage
    reason: DropReason
    detail: Mapping[str, float]
    note: str = ""


@dataclass(frozen=True, slots=True)
class StageResult:
    """Everything one stage produced for one query clause.

    ``candidates`` is ordered: descending score, then ``(clause_uuid,
    commit_id)`` as the tie-break, so the sequence is a deterministic function
    of its inputs.  The tie-break is on identity, never on score, because a
    score tie broken by score order is a hidden decision and D4 forbids those.
    """

    stage: Stage
    candidates: tuple[Candidate, ...]
    dropped: tuple[DroppedCandidate, ...] = field(default_factory=tuple)

    def accepted(self, auto_accept: float) -> tuple[Candidate, ...]:
        """Return the candidates at or above the stage's auto-accept band."""
        return tuple(c for c in self.candidates if c.score >= auto_accept)

    def best(self) -> Candidate | None:
        """Return the highest-scoring candidate, or ``None`` when there is none."""
        return self.candidates[0] if self.candidates else None


def order_candidates(candidates: list[Candidate]) -> tuple[Candidate, ...]:
    """Sort candidates the one way this package ever sorts them.

    Descending score; ties broken by ``(clause_uuid, commit_id)``.  Exposed so
    that every stage sorts identically and a test can assert that two runs over
    a shuffled corpus produce byte-identical output.
    """
    return tuple(
        sorted(
            candidates,
            key=lambda c: (-c.score, c.ancestor_clause_uuid.bytes, c.ancestor_commit),
        )
    )
