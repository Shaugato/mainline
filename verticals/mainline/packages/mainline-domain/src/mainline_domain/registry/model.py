# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""The DIRECTRIX types: direction, status, abstention, entry, registry.

``SafeDirection.ABSTAIN`` is a member of the direction enum rather than a
separate sentinel, and that is a deliberate, slightly uncomfortable choice.  The
comfortable design has three directions and returns ``None`` for "don't know",
and it is wrong here for one reason: ``None`` is falsy, and somewhere in a
codebase this size a caller writes ``if direction:`` and an unknown parameter
becomes a silently skipped check.  ``SafeDirection.ABSTAIN`` is truthy, has to
be matched explicitly, and cannot be confused with a direction because
:data:`RATIFIABLE_DIRECTIONS` excludes it and the clause encoder refuses to
write it.

The registry object is immutable and carries the commit it was read at.  Two
registries read at two commits are two different objects with two different
answers, which is what makes the verdict on last March's permit re-derivable
under last March's registry.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum
from types import MappingProxyType
from typing import Final
from uuid import UUID

__all__ = [
    "RATIFIABLE_DIRECTIONS",
    "AbstentionReason",
    "EntryStatus",
    "RegistryEntry",
    "Resolution",
    "SafeDirection",
    "SafeDirectionRegistry",
]


class SafeDirection(Enum):
    """Which way a move in a parameter is *dangerous*.

    Three ratifiable values and one that can only ever be computed:

    ``LOWER_IS_SAFER``
        A decrease is a tightening.  ``max_operating_pressure``,
        ``LEL_test_threshold``, ``test_interval``.
    ``HIGHER_IS_SAFER``
        An increase is a tightening.  ``min_ppe_level``,
        ``isolation_point_count``, ``min_oxygen_concentration``.
    ``TIGHTER_TOLERANCE_IS_SAFER``
        The value is a target and the *band* is the control.  Narrowing the band
        is a tightening; the setpoint itself moving either way is not by itself a
        weakening.  Torque specifications and calibration windows behave this
        way, and treating them as ``LOWER_IS_SAFER`` would report every
        legitimate re-centring as a weakening.
    ``ABSTAIN``
        The registry declines to answer.  Never ratifiable, never written to a
        clause, and resolved to ``ControlDelta.weaken`` by
        :mod:`mainline_domain.registry.resolve`.
    """

    LOWER_IS_SAFER = "LOWER_IS_SAFER"
    HIGHER_IS_SAFER = "HIGHER_IS_SAFER"
    TIGHTER_TOLERANCE_IS_SAFER = "TIGHTER_TOLERANCE_IS_SAFER"
    ABSTAIN = "ABSTAIN"


RATIFIABLE_DIRECTIONS: Final[frozenset[SafeDirection]] = frozenset(
    {
        SafeDirection.LOWER_IS_SAFER,
        SafeDirection.HIGHER_IS_SAFER,
        SafeDirection.TIGHTER_TOLERANCE_IS_SAFER,
    }
)
"""The directions a human may sign.  ``ABSTAIN`` is computed and never written."""


class EntryStatus(Enum):
    """The lifecycle of one registry entry, as written in its clause.

    Status is only half of ratification.  The other half is that the commit
    carrying the clause is **signed** — see
    :attr:`RegistryEntry.ratification_signed`.  Both are required, and they fail
    independently: a ``PROPOSED`` entry on a signed commit is a proposal
    somebody merged, and a ``RATIFIED`` entry on an unsigned commit is a
    direction nobody put their name to.  Neither answers.
    """

    RATIFIED = "RATIFIED"
    PROPOSED = "PROPOSED"
    WITHDRAWN = "WITHDRAWN"


class AbstentionReason(Enum):
    """Why the registry declined, in the words the refusal will be explained in.

    Every one of these ends the same way — ``weaken``, then a blocking check —
    so the reason is not a severity.  It is what tells the person holding the
    permit whether they are looking at a coverage gap they can close by
    ratifying a parameter, or at a broken document they need to fix, or at a
    genuine ambiguity in the history that somebody has to resolve.
    """

    NOT_IN_REGISTRY = "not_in_registry"
    DOCUMENT_ABSENT = "document_absent"
    NOT_RATIFIED = "not_ratified"
    UNSIGNED_RATIFICATION = "unsigned_ratification"
    WITHDRAWN = "withdrawn"
    RETIRED = "retired"
    AMBIGUOUS_AT_COMMIT = "ambiguous_at_commit"
    DUPLICATE_PARAMETER = "duplicate_parameter"
    MALFORMED_CLAUSE = "malformed_clause"
    DIMENSION_MISMATCH = "dimension_mismatch"


@dataclass(frozen=True, slots=True)
class RegistryEntry:
    """One ratified parameter, with the clause row that ratified it.

    ``ratification_commit`` is the commit of the ``clause_version`` in force at
    ``as_of_commit`` — the registry does not carry a separate "ratified in
    commit X" field, because a field can disagree with the row it sits on.  The
    commit that wrote the entry **is** the ratification, and ``ratified_by_sub``
    is that commit's author.  Making these derived rather than declared is the
    same discipline P2 applies to a projected column: the value a gate reads
    comes from the authoritative row, never from the writer's assertion about it.
    """

    parameter: str
    dimension_label: str
    dimensionality: str
    direction: SafeDirection
    status: EntryStatus
    rationale: str
    clause_uuid: UUID
    ratification_commit: bytes
    ratified_by_sub: str
    ratification_signed: bool
    gen: int
    canon_sha256: bytes


@dataclass(frozen=True, slots=True)
class Resolution:
    """The registry's answer about one parameter, with its reason.

    ``direction`` is ``SafeDirection.ABSTAIN`` exactly when ``reason`` is not
    ``None``.  Both are always populated so that a caller logging the answer
    never has to reconstruct why.
    """

    parameter: str
    direction: SafeDirection
    reason: AbstentionReason | None
    entry: RegistryEntry | None
    detail: str

    @property
    def abstained(self) -> bool:
        """True when the registry declined to answer about this parameter."""
        return self.direction is SafeDirection.ABSTAIN

    def __post_init__(self) -> None:
        """Hold the abstained-iff-has-a-reason invariant at construction."""
        abstained = self.direction is SafeDirection.ABSTAIN
        if abstained != (self.reason is not None):
            raise ValueError(
                "a Resolution abstains if and only if it carries a reason; got "
                f"direction={self.direction} reason={self.reason}"
            )


@dataclass(frozen=True, slots=True)
class SafeDirectionRegistry:
    """The registry as it stood at one commit.  Immutable, and it says which commit.

    Constructed only by :func:`mainline_domain.registry.loader.load_registry`.
    ``entries`` holds the parameters that answer; ``abstentions`` holds the ones
    that were *present in the document and refused anyway* — a proposal, a
    withdrawal, a malformed clause, a duplicate.  Keeping the refused ones is
    what lets a refusal say "that parameter is proposed but not ratified"
    instead of "unknown parameter", which is the difference between a person
    knowing what to do next and not.
    """

    site_id: UUID
    as_of_commit: bytes
    doc_code: str
    entries: Mapping[str, RegistryEntry]
    abstentions: Mapping[str, Resolution]
    encoding_version: int
    document_present: bool

    def __post_init__(self) -> None:
        """Freeze the two mappings so a loaded registry cannot be edited in place."""
        # Freeze the mappings so a caller cannot mutate a registry that another
        # caller is about to derive a merge decision from.
        object.__setattr__(self, "entries", MappingProxyType(dict(self.entries)))
        object.__setattr__(self, "abstentions", MappingProxyType(dict(self.abstentions)))

    def parameters(self) -> frozenset[str]:
        """Parameters that answer.  Not the ones that abstain."""
        return frozenset(self.entries)

    def resolve(self, parameter: str, *, dimensionality: str | None = None) -> Resolution:
        """The registry's answer, with its reason.  Never raises for an unknown key.

        ``dimensionality``, when given, is checked against the entry's declared
        dimension and a mismatch **abstains**.  That check is not pedantry: it
        catches the case where a clause's parameter name has come to mean
        something else — ``test_interval`` that used to be a time and is now a
        count of shifts — which is a change of control disguised as a change of
        units, and the one place the registry can notice it.
        """
        entry = self.entries.get(parameter)
        if entry is None:
            recorded = self.abstentions.get(parameter)
            if recorded is not None:
                return recorded
            if not self.document_present:
                return Resolution(
                    parameter=parameter,
                    direction=SafeDirection.ABSTAIN,
                    reason=AbstentionReason.DOCUMENT_ABSENT,
                    entry=None,
                    detail=(
                        f"no {self.doc_code} document is reachable from commit "
                        f"{self.as_of_commit.hex()[:12]} for this site"
                    ),
                )
            return Resolution(
                parameter=parameter,
                direction=SafeDirection.ABSTAIN,
                reason=AbstentionReason.NOT_IN_REGISTRY,
                entry=None,
                detail=(
                    f"{parameter!r} carries no ratified safe-direction clause at commit "
                    f"{self.as_of_commit.hex()[:12]}"
                ),
            )

        if dimensionality is not None and dimensionality != entry.dimensionality:
            return Resolution(
                parameter=parameter,
                direction=SafeDirection.ABSTAIN,
                reason=AbstentionReason.DIMENSION_MISMATCH,
                entry=entry,
                detail=(
                    f"{parameter!r} is ratified as {entry.dimension_label} "
                    f"({entry.dimensionality}) but the clause measures it in "
                    f"{dimensionality}"
                ),
            )

        return Resolution(
            parameter=parameter,
            direction=entry.direction,
            reason=None,
            entry=entry,
            detail=(
                f"{parameter!r} is {entry.direction.value}, ratified in commit "
                f"{entry.ratification_commit.hex()[:12]} by {entry.ratified_by_sub}"
            ),
        )

    def safe_direction(
        self, parameter: str, *, dimensionality: str | None = None
    ) -> SafeDirection:
        """The direction, or :attr:`SafeDirection.ABSTAIN`.  Never a default."""
        return self.resolve(parameter, dimensionality=dimensionality).direction
