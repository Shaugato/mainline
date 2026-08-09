# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
"""Resolving a blame pointer — the deterministic half of the Cartographer.

MAINLINE's product sentence is *every clause of a procedure, setpoint or critical
control carries a blame pointer to the incident that wrote it*. This module is the code
that follows that pointer, and it holds **no model, no driver and no credential**: it is
handed the closure row, the ancestor event rows and the edge rows, and it returns the
resolved ancestry or it refuses.

Four refusals, and each one is a distinct failure a reviewer can name:

1. **No closure row** ⇒ :class:`~mainline_cartographer.errors.BlameClosureAbsent`. P3.
   *We do not know the ancestry* and *there is no ancestry* must never look alike.
2. **An ancestor id with no event row** ⇒
   :class:`~mainline_cartographer.errors.AncestryUnresolvable`. A pointer we cannot
   follow is a precursor we cannot show a signer.
3. **The projection is below an observed severity** ⇒
   :class:`~mainline_cartographer.errors.StaleClosure`. Under-banding would let the gate
   demand a weaker clearance than the ancestry justifies. The opposite direction —
   projection above observed — fails safe, so it is reported as ``over_banded`` rather
   than refused; a signed severity downgrade recorded after the closure was computed
   produces exactly that shape.
4. **An ``inferred_semantic`` edge that is active, or that reached the closure** ⇒
   :class:`~mainline_cartographer.errors.InferenceActivated`. The DDL forbids the first
   and the Projector forbids the second; this is the read-side assertion that still
   fires if either is dropped.

**What this module deliberately does not do is band.** ``max_severity`` and
``virulence`` are projections written by the Projector from ``clause_blame_closure``. A
second banding implementation here would be a second answer to a question that must have
exactly one, and the moment two answers exist the interesting question stops being
"what is the ancestry" and becomes "which of our two programs is right".
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from .errors import (
    AncestryUnresolvable,
    BlameClosureAbsent,
    ClosureInconsistent,
    ClosureMismatch,
    InferenceActivated,
    StaleClosure,
)
from .types import BlameBasis, BlameState, ResolvedBlame

if TYPE_CHECKING:
    from collections.abc import Iterable, Sequence

    from .types import BlameEdgeRow, ClosureRow, EventRow

__all__ = ["order_ancestry", "resolve_blame_pointer"]


def order_ancestry(events: Iterable[EventRow]) -> tuple[EventRow, ...]:
    """Order ancestors for display: worst first, then earliest, then by id.

    ``occurred_at`` ascending inside a severity band is deliberate. Where two fatalities
    wrote the same clause, the one a reader is shown second is the *later* one — the
    recurrence — and a recurrence reads correctly only after its precursor.
    """
    return tuple(
        sorted(events, key=lambda event: (-event.severity_gate, event.occurred_at, event.event_id))
    )


def resolve_blame_pointer(
    *,
    clause_uuid: str,
    as_of_commit: str,
    closure: ClosureRow | None,
    events: Sequence[EventRow],
    edges: Sequence[BlameEdgeRow] = (),
) -> ResolvedBlame:
    """Follow one clause version's blame pointer, or refuse.

    Args:
        clause_uuid: the clause whose pointer is being followed.
        as_of_commit: the commit that pins the clause version, hex-encoded.
        closure: the ``clause_blame_current`` row, or ``None`` when the read found none.
        events: event rows for the closure's ``ancestor_events``. Extras are ignored;
            a shortfall is a refusal.
        edges: the clause's ``blame_edge`` rows. Optional, and used only to assert the
            inference law and to report what was correctly excluded.

    Returns:
        The resolved ancestry, its completeness, and the projections read verbatim.

    Raises:
        BlameClosureAbsent: no closure row exists for this clause version.
        ClosureMismatch: the closure row is for a different clause version.
        ClosureInconsistent: the closure row disagrees with itself.
        AncestryUnresolvable: an ancestor id has no event row.
        StaleClosure: the projection is below an observed ancestor severity.
        InferenceActivated: an inferred edge is active, or reached the closure.
    """
    if closure is None:
        raise BlameClosureAbsent(clause_uuid, as_of_commit)
    if closure.clause_uuid != clause_uuid or closure.as_of_commit != as_of_commit:
        raise ClosureMismatch(
            (clause_uuid, as_of_commit), (closure.clause_uuid, closure.as_of_commit)
        )

    ancestor_ids = tuple(closure.ancestor_events)
    distinct = frozenset(ancestor_ids)
    if len(distinct) != len(ancestor_ids):
        raise ClosureInconsistent(
            clause_uuid,
            f"ancestor_events holds {len(ancestor_ids)} entries but only {len(distinct)} are "
            f"distinct; the closure writer dedupes with UNION for exactly this reason",
        )
    if closure.ancestor_count != len(distinct):
        raise ClosureInconsistent(
            clause_uuid,
            f"ancestor_count={closure.ancestor_count} but ancestor_events holds "
            f"{len(distinct)} ids",
        )

    _assert_inference_never_blocks(clause_uuid, edges, distinct)

    by_id = {event.event_id: event for event in events}
    missing = tuple(sorted(event_id for event_id in distinct if event_id not in by_id))
    if missing:
        raise AncestryUnresolvable(clause_uuid, missing)

    ancestry = order_ancestry(by_id[event_id] for event_id in distinct)
    observed = max((event.severity_gate for event in ancestry), default=0)
    if observed > closure.max_severity:
        worst = next(event for event in ancestry if event.severity_gate == observed)
        raise StaleClosure(clause_uuid, closure.max_severity, observed, worst.event_id)

    return ResolvedBlame(
        clause_uuid=clause_uuid,
        as_of_commit=as_of_commit,
        closure_gen=closure.closure_gen,
        ancestry=ancestry,
        max_severity=closure.max_severity,
        virulence=closure.virulence,
        # The closure's own flag, never inferred from a count: a closure capped at 512
        # ancestors reports itself, and an aggregate that hid that would be a safety
        # defect in this product rather than a rounding error.
        ancestry_complete=not closure.truncated,
        depth=closure.depth,
        over_banded=closure.max_severity > observed,
        excluded_inferred=_excluded_inferred(edges, distinct),
    )


def _assert_inference_never_blocks(
    clause_uuid: str,
    edges: Sequence[BlameEdgeRow],
    ancestor_ids: frozenset[str],
) -> None:
    """Restate ``inference_never_blocks`` on the read path."""
    for edge in edges:
        if edge.basis is not BlameBasis.INFERRED_SEMANTIC:
            continue
        if edge.state is BlameState.ACTIVE:
            raise InferenceActivated(
                f"blame_edge(clause_uuid={clause_uuid}, event_id={edge.event_id}) was read with "
                f"basis=inferred_semantic and state=active"
            )
        if edge.event_id in ancestor_ids:
            raise InferenceActivated(
                f"event {edge.event_id} reaches clause {clause_uuid} only through an "
                f"inferred_semantic edge, yet it appears in the closure's ancestor_events. An "
                f"inferred edge may never raise clause_blame_closure.max_severity"
            )


def _excluded_inferred(
    edges: Sequence[BlameEdgeRow], ancestor_ids: frozenset[str]
) -> tuple[str, ...]:
    """Report the inferred links that were correctly left out of the closure."""
    return tuple(
        sorted(
            {
                edge.event_id
                for edge in edges
                if edge.basis is BlameBasis.INFERRED_SEMANTIC and edge.event_id not in ancestor_ids
            }
        )
    )
