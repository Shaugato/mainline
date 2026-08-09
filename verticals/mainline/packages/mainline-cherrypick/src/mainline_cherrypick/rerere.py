# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
"""rerere, with recall — the one column git's version does not have.

Git's ``rerere`` (*reuse recorded resolution*) remembers **how** a conflict was
resolved, keyed on the conflict's shape, and replays that resolution when the same
conflict recurs. It is genuinely useful and it has one gap that matters enormously
here: it does not remember **where the resolution came from**. When a resolution
turns out to have been wrong, git cannot tell you which trees inherited it.

``mainline.resolution_memory.origin_conflict`` closes that gap for the price of one
column: *when a resolution is later found wrong, one query returns every site that
inherited it.* :data:`INHERITED_SITES_SQL` is that query, and it is the reason this
module exists as something other than a cache.

Two rules, both enforced here rather than described.

**A recalled resolution is never offered again.** ``recalled_at`` is set when the
originating resolution is found wrong. From that moment :func:`recall` refuses —
loudly, with the origin conflict and the recall time in the message. A memory that
kept handing out a resolution known to be wrong would be worse than no memory,
because it would carry the authority of having been used before.

**A recorded resolution is proposed, never auto-applied.** :func:`recall` returns a
:class:`RecalledResolution` whose ``applied`` is ``False`` and which has no method
that changes it. Applying a remembered resolution to safety text without a person
reading it is the rubber-stamp accelerant §5.9 names explicitly. The recall is a
suggestion in front of a human, and the human's signature is what
:class:`~mainline_cherrypick.types.HumanResolution` requires.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Final

from .errors import RecalledResolutionOffered

if TYPE_CHECKING:
    from collections.abc import Mapping
    from uuid import UUID

    from .types import MergeConflict, ResolutionMemoryRow

__all__ = [
    "INHERITED_SITES_SQL",
    "MemoryKey",
    "RecalledResolution",
    "recall",
    "remember",
]

#: The query git cannot write. Given a conflict whose resolution was found wrong,
#: return every propagation that inherited it — site, lesson and state — so a
#: recall notice goes to the sites that acted on it rather than to all of them.
#:
#: Written as a constant rather than built at call time so it can be read, reviewed
#: and EXPLAINed without running the code that produces it.
INHERITED_SITES_SQL: Final[str] = """
SELECT c.site_id, c.lesson_id, c.clause_uuid, c.conflict_id, p.state
  FROM mainline.merge_conflict AS c
  JOIN mainline.propagation AS p
    ON p.lesson_id = c.lesson_id AND p.site_id = c.site_id
 WHERE c.resolution_source IN (
         SELECT m.origin_conflict
           FROM mainline.resolution_memory AS m
          WHERE m.origin_conflict = %s
       )
 ORDER BY c.site_id, c.lesson_id
""".strip()

#: ``(clause_uuid, base_digest, ours_digest, theirs_digest)`` — the primary key of
#: ``resolution_memory`` and the shape a conflict is looked up by.
MemoryKey = tuple["UUID", bytes, bytes, bytes]


@dataclass(frozen=True, slots=True)
class RecalledResolution:
    """A remembered resolution, offered to a person. Never applied.

    ``applied`` is a field that is always ``False`` and has no setter. It is here
    so that a caller writing ``if recalled.applied:`` reads the guarantee instead
    of having to know it — and so that a future change that tried to make it
    ``True`` would be a visible diff on a frozen dataclass rather than a quiet new
    code path.
    """

    text: str
    origin_conflict: UUID
    key: MemoryKey
    applied: bool = False

    def __post_init__(self) -> None:
        """Refuse an applied recall. There is no such thing in this system."""
        if self.applied:
            from .errors import AgentWouldResolve

            raise AgentWouldResolve(
                f"a recalled resolution for origin conflict {self.origin_conflict} was "
                f"marked applied. A recorded resolution is proposed, never auto-applied"
            )


def recall(
    conflict: MergeConflict,
    memory: Mapping[MemoryKey, ResolutionMemoryRow],
) -> RecalledResolution | None:
    """Look up a remembered resolution for this conflict's exact shape.

    The key is the full four-tuple — clause, base, ours, theirs — so a resolution
    is only replayed against a conflict that is textually identical on all three
    sides. A looser key would replay a resolution written for one disagreement
    against a different one, which is precisely the failure mode a safety document
    cannot absorb.

    Returns:
        The remembered resolution, or ``None`` when nothing matches.

    Raises:
        RecalledResolutionOffered: the memory matched, and its originating
            resolution has since been found wrong. Refusing loudly rather than
            returning ``None`` is deliberate: "there is no memory" and "the memory
            is known to be wrong" are different facts, and the second one is worth
            interrupting for.
    """
    key: MemoryKey = (
        conflict.clause_uuid,
        conflict.base_digest,
        conflict.ours_digest,
        conflict.theirs_digest,
    )
    row = memory.get(key)
    if row is None:
        return None
    if row.recalled_at is not None:
        raise RecalledResolutionOffered(
            str(conflict.clause_uuid),
            str(row.origin_conflict),
            row.recalled_at.isoformat(),
        )
    return RecalledResolution(
        text=row.resolution_text,
        origin_conflict=row.origin_conflict,
        key=key,
    )


def remember(
    conflict: MergeConflict,
    resolution_text: str,
    origin_conflict: UUID,
) -> ResolutionMemoryRow:
    """Build the ``resolution_memory`` row for a resolution a person just signed.

    ``origin_conflict`` is the conflict the resolution was authored against — the
    back-pointer that makes :data:`INHERITED_SITES_SQL` answerable. It is a
    required argument with no default, because a default would be a memory with no
    provenance and this whole module is about provenance.
    """
    from .types import ResolutionMemoryRow as Row

    return Row(
        clause_uuid=conflict.clause_uuid,
        base_digest=conflict.base_digest,
        ours_digest=conflict.ours_digest,
        theirs_digest=conflict.theirs_digest,
        resolution_text=resolution_text,
        origin_conflict=origin_conflict,
        recalled_at=None,
    )
