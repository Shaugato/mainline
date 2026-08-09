# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
"""The propagation lifecycle — a fixed graph, and one column this agent may move.

§11.2 and ``verticals/mainline/db/GRANTS.yaml`` give ``agent_fleet`` ``UPDATE`` on
``mainline.propagation`` **scoped by trigger to ``prop_state``**. That single line
of the grant matrix decides the shape of this module:

* ``open_conflicts`` is a **projection**. It is a trigger-maintained counter over
  ``merge_conflict``, exactly as ``permit.open_blocking`` is over
  ``blocking_check``, and this agent cannot write it. A site cannot declare itself
  conflict-free.
* ``adopted_commit`` is likewise not ours. Adoption is a merge, and a merge is the
  kernel's transition; the propagation row learns about it, it does not assert it.
* what remains is ``state``, and :func:`advance` emits an ``UPDATE`` that sets
  exactly that column and no other.

So the precondition checks here read the projected values and **refuse** when they
contradict the requested state — but the statement that goes to the database never
carries them. That is P2 applied to a state machine: the agent proposes a
transition, the database keeps the counters, and the agent's belief about the
counters is checked against the row rather than written onto it.

The transition graph is fixed and enumerated. A decline that could be silently
reopened, or an adoption that could be silently undone, would make the propagation
record unciteable the next time the same lesson arrives at the same site — and
"citable the next time" is the entire content of the DEP-3 model §5.9 borrows.

There is one deliberate re-entry edge: ``declined → proposed``, reachable **only**
through :func:`reopen_expired_waiver`. MI28 says a bounded window means bounded,
not merely present, so a waiver whose expiry has passed is not a declination any
more and the site owes the fleet a fresh answer.
"""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING, Final

from .errors import AdoptionNotClean, IllegalPropagationTransition
from .types import PropState, require_aware

if TYPE_CHECKING:
    from collections.abc import Mapping
    from datetime import datetime
    from uuid import UUID

    from .merge3 import Merge3Result
    from .types import Declination, MergeConflict, Propagation

__all__ = [
    "TERMINAL_STATES",
    "TRANSITIONS",
    "advance",
    "conflicts_from_merge",
    "decline",
    "reopen_expired_waiver",
]

#: The lifecycle, written out. Every edge here is one somebody can defend; every
#: edge absent is one somebody would have had to.
TRANSITIONS: Final[Mapping[PropState, frozenset[PropState]]] = {
    PropState.PROPOSED: frozenset(
        {
            PropState.ALREADY_PRESENT,
            PropState.CONFLICTED,
            PropState.ADOPTED,
            PropState.DECLINED,
            PropState.REVOKED,
        }
    ),
    PropState.CONFLICTED: frozenset(
        {PropState.CONFLICTED, PropState.ADOPTED, PropState.DECLINED, PropState.REVOKED}
    ),
    PropState.ALREADY_PRESENT: frozenset({PropState.ADOPTED, PropState.REVOKED}),
    # `declined -> proposed` exists only through reopen_expired_waiver(), which
    # checks the expiry. Listing it here without that check would let any caller
    # reopen any decline.
    PropState.DECLINED: frozenset({PropState.PROPOSED, PropState.REVOKED}),
    PropState.ADOPTED: frozenset({PropState.REVOKED}),
    PropState.REVOKED: frozenset(),
}

#: States with no outgoing edge. ``revoked`` is terminal because a lesson the fleet
#: withdrew is not a lesson a site can go on adopting.
TERMINAL_STATES: Final[frozenset[PropState]] = frozenset({PropState.REVOKED})


def advance(
    propagation: Propagation,
    target: PropState,
    *,
    adopted_commit: bytes | None = None,
    already_present_clause: UUID | None = None,
    declination: Declination | None = None,
) -> Propagation:
    """Return the propagation in its new state, or refuse the transition.

    The keyword arguments are the **projected** values as they stand on the row,
    supplied so the preconditions can be checked. They are not written by
    :func:`~mainline_cherrypick.emit.update_propagation_state`, which sets
    ``state`` alone — see this module's docstring.

    Raises:
        IllegalPropagationTransition: no edge from the current state to ``target``.
        AdoptionNotClean: ``target`` is ``adopted`` with open conflicts or with no
            adopted commit. Mirrors ``adopt_needs_clean`` / ``adopt_needs_commit``.
    """
    allowed = TRANSITIONS[propagation.state]
    if target not in allowed:
        raise IllegalPropagationTransition(
            str(propagation.lesson_id),
            str(propagation.site_id),
            propagation.state.value,
            target.value,
        )
    if target is PropState.ADOPTED and (adopted_commit is None or propagation.open_conflicts != 0):
        raise AdoptionNotClean(
            str(propagation.lesson_id),
            str(propagation.site_id),
            propagation.open_conflicts,
            adopted_commit is not None,
        )
    return replace(
        propagation,
        state=target,
        adopted_commit=adopted_commit or propagation.adopted_commit,
        already_present_clause=already_present_clause or propagation.already_present_clause,
        declination=declination or propagation.declination,
    )


def decline(propagation: Propagation, declination: Declination) -> Propagation:
    """Record a site's falsifiable answer of no.

    A convenience over :func:`advance` that exists to make the declination
    argument non-optional at the call site. §5.9's model is a **mandated
    response**: a site is not required to conform, it is required to answer, and an
    answer with nothing attached is a queue item being closed.
    """
    return advance(propagation, PropState.DECLINED, declination=declination)


def reopen_expired_waiver(propagation: Propagation, at: datetime) -> Propagation | None:
    """Reopen a declination whose waiver has expired, or return ``None``.

    MI28: *a bounded window means bounded, not merely present.* A waiver with a
    past expiry is not a declination any more; the site owes the fleet a fresh
    answer, and leaving the row at ``declined`` would show a decline that no longer
    holds.

    Returns ``None`` when there is nothing to reopen — not declined, no waiver, or
    the window is still open. ``None`` here means "correct as it stands", which is
    why it is not an exception.
    """
    require_aware(at, "reopen_expired_waiver(at)")
    if propagation.state is not PropState.DECLINED:
        return None
    declination = propagation.declination
    if declination is None or declination.kind != "waiver":
        return None
    if not declination.expired(at):
        return None
    return replace(propagation, state=PropState.PROPOSED, declination=None)


def conflicts_from_merge(
    result: Merge3Result,
    *,
    conflict_id: UUID,
    lesson_id: UUID,
    site_id: UUID,
    clause_uuid: UUID,
    base_digest: bytes,
    ours_digest: bytes,
    theirs_digest: bytes,
    opened_at: datetime,
    resolution_source: UUID | None = None,
) -> tuple[MergeConflict, ...]:
    """Turn a conflicted three-way merge into the ``merge_conflict`` row it implies.

    **One row per clause, not one per region.** A clause whose fleet and site
    renderings disagree in four places is one thing a person has to decide, and
    four rows would be four queue items, four dispositions and four chances to
    resolve three of them. The regions themselves are on the
    :class:`~mainline_cherrypick.merge3.Merge3Result`, which the console renders.

    Returns an empty tuple for a clean merge. A clean merge opens no conflict — and
    still adopts nothing, because adoption is a merge and a merge is the kernel's.
    """
    from .types import MergeConflict as Conflict

    if result.clean:
        return ()
    return (
        Conflict(
            conflict_id=conflict_id,
            lesson_id=lesson_id,
            site_id=site_id,
            clause_uuid=clause_uuid,
            base_digest=base_digest,
            ours_digest=ours_digest,
            theirs_digest=theirs_digest,
            opened_at=require_aware(opened_at, "merge_conflict.opened_at"),
            resolution_source=resolution_source,
        ),
    )
