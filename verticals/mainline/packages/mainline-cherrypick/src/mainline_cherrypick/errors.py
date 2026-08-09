# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
"""What this package refuses, and the sentence it refuses with.

Each of these is a Python mirror of something the database would refuse anyway.
Mirroring is not redundancy: a `23514` on `only_tightenings_travel` tells an
operator which constraint fired, and :class:`WeakeningWouldTravel` tells them
which *lesson* and which *delta*, in the same words, before the transaction opens.

``N818`` is disabled repository-wide on purpose — the refusal vocabulary is a
product surface.
"""

from __future__ import annotations

__all__ = [
    "AdoptionNotClean",
    "AgentWouldResolve",
    "CherryPickError",
    "DeclinationNotFalsifiable",
    "ForbiddenWriteTarget",
    "IllegalPropagationTransition",
    "RecalledResolutionOffered",
    "WeakeningWouldTravel",
]


class CherryPickError(Exception):
    """Base for every refusal this package makes."""


class WeakeningWouldTravel(CherryPickError):
    """A lesson whose delta is a weakening was offered for propagation.

    The Python mirror of MI23 (``CHECK only_tightenings_travel``, `23514`).
    §5.9 states the reason and it is not an implementation detail: **weakenings
    are site-local trade-offs and must be re-earned locally.** A setpoint that is
    right at one plant can be an unrevealed hazard at another, so a relaxation
    that one site justified with its own evidence must not arrive at a sister site
    carrying that justification.
    """

    def __init__(self, lesson_id: str, delta: str) -> None:
        """Name the lesson and the delta that disqualified it."""
        self.lesson_id = lesson_id
        self.delta = delta
        super().__init__(
            f"lesson {lesson_id} carries control_delta={delta!r} and may not travel. "
            f"Only 'introduce', 'strengthen' and 'restate' propagate (MI23, "
            f"CHECK only_tightenings_travel, SQLSTATE 23514): a weakening is a "
            f"site-local trade-off and must be re-earned locally"
        )


class AdoptionNotClean(CherryPickError):
    """Adoption was attempted with open conflicts or with no adopted commit.

    Mirrors ``CHECK adopt_needs_clean`` and ``CHECK adopt_needs_commit``. Both are
    `23514`, and both exist because "adopted" is a claim a site makes to the rest
    of the fleet — a site that adopted a lesson it never merged has told the fleet
    something untrue about its own controls.
    """

    def __init__(self, lesson_id: str, site_id: str, open_conflicts: int, has_commit: bool) -> None:
        """Name both halves of the cleanliness condition."""
        self.lesson_id = lesson_id
        self.site_id = site_id
        self.open_conflicts = open_conflicts
        self.has_commit = has_commit
        reason = f"{open_conflicts} open conflict(s)" if open_conflicts else "no adopted_commit"
        super().__init__(
            f"propagation ({lesson_id}, {site_id}) cannot enter 'adopted': {reason}. "
            f"'Adopted' is a claim to the rest of the fleet about this site's controls "
            f"(CHECK adopt_needs_clean / adopt_needs_commit, SQLSTATE 23514)"
        )


class IllegalPropagationTransition(CherryPickError):
    """A propagation was moved between two states with no edge between them."""

    def __init__(self, lesson_id: str, site_id: str, source: str, target: str) -> None:
        """Name the transition that does not exist."""
        self.lesson_id = lesson_id
        self.site_id = site_id
        self.source = source
        self.target = target
        super().__init__(
            f"propagation ({lesson_id}, {site_id}) has no transition "
            f"{source!r} → {target!r}. The lifecycle is a fixed graph: a decline that "
            f"could be silently reopened, or an adoption that could be silently undone, "
            f"would make the propagation record unciteable the next time this lesson arrives"
        )


class DeclinationNotFalsifiable(CherryPickError):
    """A declination was recorded without the evidence its kind requires.

    Mirrors ``mitigated_names_local_clause``, ``waiver_expires`` and
    ``na_is_falsifiable``. §5.9's design is Debian's DEP-3 model: a **mandated
    response** beats mandated conformity. A response of "not applicable" with
    nothing attached is not a response, it is a way of closing a queue item.
    """

    def __init__(self, kind: str, missing: str) -> None:
        """Name the declination kind and the field it must carry."""
        self.kind = kind
        self.missing = missing
        super().__init__(
            f"a {kind!r} declination requires {missing}. A declination with no "
            f"falsifiable content is a queue item being closed, not a site answering "
            f"the fleet (SQLSTATE 23514)"
        )


class RecalledResolutionOffered(CherryPickError):
    """A resolution whose origin was later found wrong was about to be re-offered.

    ``resolution_memory.recalled_at`` is what git's ``rerere`` cannot buy: when a
    resolution is found wrong, one query returns every site that inherited it. That
    is worth nothing if the memory keeps handing the same resolution out.
    """

    def __init__(self, clause_uuid: str, origin_conflict: str, recalled_at: str) -> None:
        """Name the clause, the originating conflict and when it was recalled."""
        self.clause_uuid = clause_uuid
        self.origin_conflict = origin_conflict
        self.recalled_at = recalled_at
        super().__init__(
            f"the recorded resolution for clause {clause_uuid} was recalled at "
            f"{recalled_at} (origin conflict {origin_conflict}) and must not be offered "
            f"again. Every site that inherited it is one query away; re-offering it "
            f"would add another"
        )


class ForbiddenWriteTarget(CherryPickError):
    """A statement named an object this role holds no privilege on.

    Layer 5 of the injection posture — capability starvation — expressed against
    the statement text rather than against the connection. ``agent_fleet`` would be
    refused by the database with a `42501` anyway; refusing here means the
    diagnosis names the object and the statement instead of naming a privilege.
    """

    def __init__(self, target: str, statement: str) -> None:
        """Name the object and quote the statement that reached for it."""
        self.target = target
        self.statement = statement
        super().__init__(
            f"statement names {target!r}, which the fleet role holds no privilege on and "
            f"this package must never reach. Statement: {statement!r}"
        )


class AgentWouldResolve(CherryPickError):
    """Something tried to turn model output into a recorded resolution.

    §8.3: **Claude explains a conflict, never resolves one.** The prohibition is
    load-bearing three ways — the ``ConflictNarration`` schema's
    ``resolution_proposed`` accepts only ``"none"``, ``agent_fleet`` holds no
    ``UPDATE`` on ``merge_conflict`` so the resolution columns are unreachable by
    grant, and :class:`~mainline_cherrypick.types.HumanResolution` cannot be
    constructed without a signature and a human subject. This is the third one
    firing.
    """

    def __init__(self, detail: str) -> None:
        """Quote what was attempted."""
        self.detail = detail
        super().__init__(
            f"refusing to record a resolution that no person signed: {detail}. "
            f"Auto-applying a safety-text resolution is precisely the rubber-stamp "
            f"accelerant this product exists not to build"
        )
