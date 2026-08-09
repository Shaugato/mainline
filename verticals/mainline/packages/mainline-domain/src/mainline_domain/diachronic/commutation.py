# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""COMMUTATION FOOTPRINT — dependency edges derived, never declared.

Two clause edits **commute** iff their footprints (:mod:`.footprint`) are
disjoint.  A non-commuting pair is a *dependency*: the two edits are about the
same equipment, the same controlled parameter or the same control class, so
neither can be read as independent of the other.  Those pairs are written to
``mainline.commutation_edge`` (migration ``0049b``) and they widen the antecedent
set the weaken gate reads.

**The refusal itself is not here.**  This module derives edges; the gate that
refuses a merge is the kernel's, unchanged.  What ``commutation_edge`` adds is
antecedents the gate would otherwise have had to be *told* about — invariant I06:
a dependency edge a gate consumes is computed, never declared.

WHY THE RELATION IS ENFORCED BY THE TABLE AND NOT BY THIS MODULE
----------------------------------------------------------------
Disjointness is symmetric and irreflexive, and both facts are load-bearing:

* **Symmetric** — if A depends on B then B depends on A, so storing the pair twice
  creates two rows that can disagree after a partial re-derivation.
* **Irreflexive** — an edit's footprint always overlaps its own, so a self-edge is
  never a derivation, only a bug.

Rather than trusting this module to hold both, ``0049b_commutation_edge.sql``
carries ``CONSTRAINT canonical_direction CHECK (from_commit < to_commit OR
(from_commit = to_commit AND from_clause_uuid < to_clause_uuid))``.  A strict
lexicographic ordering makes the *reverse* row and the *self* row un-storable for
every writer, including one that never imported this package.  :func:`canonical`
is the Python side of the same ordering, and
``tests/unit/domain/diachronic/test_commutation.py`` proves the two agree.

Byte ordering matches: CockroachDB compares ``BYTES`` lexicographically and
``UUID`` by its 128-bit value, which is the same order Python's ``bytes`` and
``uuid.UUID`` comparisons give.  That agreement is why the Python canonicaliser
and the SQL CHECK can be two statements of one rule instead of two rules.

WHAT A DERIVED EDGE MUST CARRY
------------------------------
``computed_by`` and ``footprint_ver`` are on every row and are not decoration.
After the fact, the only thing distinguishing an edge somebody *computed* from an
edge somebody *typed* is that the computed one names the code that computed it and
the encoding it computed under.  ``0049b``'s ``overlap_nonempty`` CHECK closes the
other half: a "dependency" row whose ``footprint_overlap`` is empty is a
declaration wearing a derivation's costume, and the database refuses it (23514).
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Final
from uuid import UUID

from .errors import FootprintError
from .footprint import Footprint
from .version import FOOTPRINT_VERSION, computed_by

__all__ = [
    "COMMUTATION_EDGE_INSERT_SQL",
    "ClauseEdit",
    "CommutationEdge",
    "EditRef",
    "canonical",
    "commutes",
    "derive_commutation_edges",
    "edge_for",
    "edges_for_clause",
    "unfootprintable",
]


@dataclass(frozen=True, slots=True, order=False)
class EditRef:
    """Which clause, in which commit, at which site.  The identity of one edit."""

    site_id: UUID
    commit_id: bytes
    clause_uuid: UUID

    @property
    def sort_key(self) -> tuple[bytes, UUID]:
        """The key ``0049b``'s ``canonical_direction`` CHECK orders on.

        ``site_id`` is deliberately absent: it is not in the table's primary key
        either, because a commit is already site-scoped through
        ``mainline.commit_obj`` and putting the site in the ordering would let two
        rows for one pair exist under two site values.
        """
        return (self.commit_id, self.clause_uuid)


@dataclass(frozen=True, slots=True)
class ClauseEdit:
    """One edit, with the footprint it was derived from."""

    ref: EditRef
    footprint: Footprint


@dataclass(frozen=True, slots=True)
class CommutationEdge:
    """One derived dependency edge, in the shape ``mainline.commutation_edge`` stores.

    ``footprint_overlap`` is sorted and non-empty.  Sorted so that two derivations
    of the same pair produce byte-identical arrays; non-empty because an edge with
    no overlap is not a derivation, and the table refuses one (23514 on
    ``overlap_nonempty``).
    """

    site_id: UUID
    from_commit: bytes
    from_clause_uuid: UUID
    to_commit: bytes
    to_clause_uuid: UUID
    footprint_overlap: tuple[str, ...]
    computed_by: str
    footprint_ver: str

    def as_parameters(self) -> dict[str, object]:
        """Return the bind parameters for :data:`COMMUTATION_EDGE_INSERT_SQL`."""
        return {
            "site_id": str(self.site_id),
            "from_commit": self.from_commit,
            "from_clause_uuid": str(self.from_clause_uuid),
            "to_commit": self.to_commit,
            "to_clause_uuid": str(self.to_clause_uuid),
            "footprint_overlap": list(self.footprint_overlap),
            "computed_by": self.computed_by,
            "footprint_ver": self.footprint_ver,
        }


COMMUTATION_EDGE_INSERT_SQL: Final[str] = """
INSERT INTO mainline.commutation_edge
  (site_id, from_commit, from_clause_uuid, to_commit, to_clause_uuid,
   footprint_overlap, computed_by, footprint_ver)
VALUES
  (%(site_id)s, %(from_commit)s, %(from_clause_uuid)s, %(to_commit)s, %(to_clause_uuid)s,
   %(footprint_overlap)s, %(computed_by)s, %(footprint_ver)s)
ON CONFLICT (from_commit, from_clause_uuid, to_commit, to_clause_uuid) DO NOTHING
"""
"""Append one derived edge.

``ON CONFLICT DO NOTHING`` and never ``DO UPDATE``: the table is append-only, a
re-derivation of the same pair under the same encoding produces the same row, and
a re-derivation under a *different* encoding is a different ``footprint_ver`` and
therefore a different fact — which must not silently overwrite the one a gate has
already read.  Re-deriving after a ``FOOTPRINT_VERSION`` bump is a new derivation
pass, not an update.
"""


def canonical(a: EditRef, b: EditRef) -> tuple[EditRef, EditRef]:
    """Order two edit refs the way ``0049b``'s ``canonical_direction`` CHECK requires.

    :raises FootprintError: when the two refs are the same edit.  Commutation is
        irreflexive here by construction, the table's strict ``<`` refuses a
        self-edge anyway, and returning ``(x, x)`` would produce a row that the
        database rejects at insert time — a refusal a long way from the mistake.
    """
    if a.sort_key == b.sort_key:
        raise FootprintError(
            f"an edit cannot commute with itself: clause {a.clause_uuid} at commit "
            f"{a.commit_id.hex()[:12]} was compared against itself. Its footprint overlaps "
            "its own by definition, so the question has no answer that is not a bug"
        )
    return (a, b) if a.sort_key < b.sort_key else (b, a)


def commutes(a: ClauseEdit, b: ClauseEdit) -> bool:
    """Report whether two edits share nothing and may be read independently.

    :raises FootprintError: when either footprint is empty.  An empty footprint is
        disjoint from everything, so answering ``True`` would report *"we know
        nothing about what this edit touched"* as *"this edit is independent of
        everything"* — a fail-open answer to a question whose whole purpose is to
        widen an antecedent set.  The caller must decide what an unfootprintable
        edit means; commonly it is ``identity_residue.reason='opaque_control'``.
    """
    for edit, side in ((a, "first"), (b, "second")):
        if not edit.footprint:
            raise FootprintError(
                f"the {side} edit (clause {edit.ref.clause_uuid} at commit "
                f"{edit.ref.commit_id.hex()[:12]}) has an EMPTY footprint: no identity "
                "anchor, no controlled parameter and no control class could be derived "
                "from either version. An empty set is disjoint from everything, so "
                "answering 'these commute' would report ignorance as independence"
            )
    return a.footprint.is_disjoint(b.footprint)


def edge_for(a: ClauseEdit, b: ClauseEdit) -> CommutationEdge | None:
    """Return the derived dependency edge for one pair, or ``None`` if they commute.

    :raises FootprintError: on a self-comparison or an empty footprint — see
        :func:`canonical` and :func:`commutes`.
    """
    if commutes(a, b):
        return None
    first, second = canonical(a.ref, b.ref)
    overlap = a.footprint.overlap(b.footprint)
    return CommutationEdge(
        site_id=first.site_id,
        from_commit=first.commit_id,
        from_clause_uuid=first.clause_uuid,
        to_commit=second.commit_id,
        to_clause_uuid=second.clause_uuid,
        footprint_overlap=overlap,
        computed_by=computed_by(),
        footprint_ver=FOOTPRINT_VERSION,
    )


def derive_commutation_edges(edits: Iterable[ClauseEdit]) -> tuple[CommutationEdge, ...]:
    """Derive every dependency edge over a set of edits.

    One row per unordered non-commuting pair, in canonical direction, sorted so
    that two runs over the same input produce byte-identical output.  Edits whose
    footprint is empty are **skipped rather than silently commuted**, and the
    caller learns of them from :func:`unfootprintable`.

    Quadratic in the number of edits, deliberately and with the bound stated: the
    input is the edits in one commit, which is tens of clauses, not the corpus.
    A caller applying this across a whole history must partition first — by site
    and by document family — and this function will not do it for them, because a
    partitioning rule chosen inside a derivation is a rule nobody reviews.
    """
    footprinted: list[ClauseEdit] = [edit for edit in edits if edit.footprint]
    ordered = sorted(footprinted, key=lambda edit: edit.ref.sort_key)
    edges: list[CommutationEdge] = []
    for i, left in enumerate(ordered):
        for right in ordered[i + 1 :]:
            if left.ref.sort_key == right.ref.sort_key:
                raise FootprintError(
                    f"two distinct edits share the identity ({left.ref.commit_id.hex()[:12]}, "
                    f"{left.ref.clause_uuid}); one commit produces at most one version of "
                    "any clause (mainline.clause_version's cv_clause_commit_unique), so this "
                    "input describes a state the database refuses to be in"
                )
            edge = edge_for(left, right)
            if edge is not None:
                edges.append(edge)
    return tuple(edges)


def unfootprintable(edits: Iterable[ClauseEdit]) -> tuple[EditRef, ...]:
    """Return the edits :func:`derive_commutation_edges` skipped for having no footprint.

    Kept as a separate call rather than as a second return value so that a caller
    cannot ignore it by unpacking only the first element of a tuple.
    """
    return tuple(edit.ref for edit in edits if not edit.footprint)


def edges_for_clause(
    edges: Sequence[CommutationEdge], *, commit_id: bytes, clause_uuid: UUID
) -> tuple[CommutationEdge, ...]:
    """Return every derived edge naming one version, from either side.

    Rows are stored in one canonical direction, so a reader asking *"what does this
    edit depend on"* must look at both ends.  This function is that lookup, and its
    SQL twin is ``0049b``'s ``by_to`` index.
    """
    return tuple(
        edge
        for edge in edges
        if (edge.from_commit == commit_id and edge.from_clause_uuid == clause_uuid)
        or (edge.to_commit == commit_id and edge.to_clause_uuid == clause_uuid)
    )
