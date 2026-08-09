# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
"""The rows the cherry-pick worker reads and the rows it proposes.

Mirrors ARCHITECTURE.md §5.9 field for field. Where the DDL carries a `CHECK`, the
Python type carries the same predicate at construction — so a caller learns which
of their inputs was wrong instead of reading a constraint name out of a `23514`.

Two of these types are doing structural work rather than modelling work, and they
are the ones to read first.

:class:`HumanResolution` **cannot be constructed without a signature and a human
subject.** That is the third of three independent barriers against an agent
recording a merge resolution — the other two being the ``ConflictNarration``
schema, whose ``resolution_proposed`` field accepts only ``"none"``, and the grant
matrix, which gives ``agent_fleet`` no ``UPDATE`` on ``merge_conflict`` at all. Any
one of the three would do. Having all three means the claim survives someone
changing one of them without understanding it.

:class:`ClauseDelta` is normalised on ``cat_key``, **not** on ``clause_uuid``.
A clause identifier is site-local; the control assertion is not. Hashing the
delta set on ``cat_key`` is the analogue of what ``git patch-id`` does when it
strips line numbers and whitespace — it makes *the same change* recognisable in a
document where it sits somewhere else.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import TYPE_CHECKING, Any, Final, Literal

from mainline_domain.contracts import ControlDelta, force

from .errors import AdoptionNotClean, AgentWouldResolve, WeakeningWouldTravel

if TYPE_CHECKING:
    from collections.abc import Mapping
    from uuid import UUID

__all__ = [
    "AGENT_SUBJECT_PREFIXES",
    "DECLINATION_KINDS",
    "TRAVELLING_DELTAS",
    "ClauseDelta",
    "Declination",
    "DeclinationKind",
    "HumanResolution",
    "Lesson",
    "MergeConflict",
    "PropState",
    "Propagation",
    "ResolutionMemoryRow",
    "require_aware",
]


class PropState(StrEnum):
    """``mainline.prop_state``, verbatim from migration ``0016``.

    ``already_present`` is the value that makes this a *record* rather than a
    broadcast: a site that had independently written the same control is
    convergent evidence **for** the lesson, and losing that to a generic
    "declined" would throw away the strongest datum in the propagation.
    """

    PROPOSED = "proposed"
    ALREADY_PRESENT = "already_present"
    CONFLICTED = "conflicted"
    ADOPTED = "adopted"
    DECLINED = "declined"
    REVOKED = "revoked"


DeclinationKind = Literal["mitigated", "waiver", "mechanism_absent"]

#: ``CHECK declination_kind IN (...)``, verbatim (§5.9).
DECLINATION_KINDS: Final[tuple[str, ...]] = ("mitigated", "waiver", "mechanism_absent")

#: ``CHECK only_tightenings_travel``, verbatim. Force-zero deltas, and only those.
TRAVELLING_DELTAS: Final[frozenset[ControlDelta]] = frozenset(
    {ControlDelta.INTRODUCE, ControlDelta.STRENGTHEN, ControlDelta.RESTATE}
)

#: Subject prefixes that identify a machine rather than a person. A resolution
#: signed by one of these would be an agent resolving a safety-text conflict, which
#: is the thing this package exists to make structurally impossible.
AGENT_SUBJECT_PREFIXES: Final[tuple[str, ...]] = ("agent_", "svc_", "mainline-", "system:")

#: SHA-256 is 32 bytes. Named so a length check reads as an assertion about the
#: digest algorithm rather than as an unexplained integer in a validator.
_SHA256_BYTES: Final[int] = 32

#: Scores are carried as integers in milli-units so no float reaches a NUMERIC
#: column. 1000 milli = 1.0.
_MILLI_FULL: Final[int] = 1000

#: `event.severity_gate` runs 1-5. A lesson outside that band would silently
#: change every sister site's due-by through the SLA table.
_MIN_SEVERITY: Final[int] = 1
_MAX_SEVERITY: Final[int] = 5


def require_aware(value: datetime, what: str) -> datetime:
    """Return ``value`` if it carries a timezone, else raise."""
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(
            f"{what} is a naive datetime ({value!r}). A propagation SLA clock with no "
            f"timezone cannot be compared against a site's local due-by, and 'the fleet "
            f"was served everything up to T' is only provable if T has a zone"
        )
    return value


@dataclass(frozen=True, slots=True)
class ClauseDelta:
    """One element of a lesson's normalised delta set.

    ``before`` and ``after`` are ``cat_key`` values — identity axis 2, the hash of
    the *control the clause asserts* rather than of the sentence it asserts it in.
    ``before`` is ``None`` for an introduction and ``after`` is ``None`` for a
    removal; both ``None`` is nothing at all and raises.
    """

    before: str | None
    after: str | None
    delta: ControlDelta

    def __post_init__(self) -> None:
        """Refuse an element that describes no change."""
        if self.before is None and self.after is None:
            raise ValueError(
                "a delta element with neither a before nor an after cat_key describes "
                "no change; it would contribute an empty row to a patch digest"
            )
        if self.before == self.after and self.delta is not ControlDelta.RESTATE:
            raise ValueError(
                f"delta element claims {self.delta.value!r} but before and after carry the "
                f"same cat_key ({self.before}). Identical control assertions are a restate; "
                f"labelling one a strengthening would let a no-op travel as a tightening"
            )

    def normalised(self) -> dict[str, str | None]:
        """Render the JCS-canonicalisable form; the field order is part of the digest."""
        return {"after": self.after, "before": self.before, "delta": self.delta.value}


@dataclass(frozen=True, slots=True)
class Lesson:
    """One row of ``mainline.lesson`` — a control change offered to the fleet.

    ``envelope`` is the applicability predicate: the conditions under which this
    lesson is *transportable*. It is evaluated deterministically by
    :mod:`mainline_cherrypick.travel`; no model reads it and no model writes it.
    §8.4 row 7 names applicability as the decision this agent does **not** make,
    and the envelope is where that decision actually lives — declared by the
    originating site, in data, in the record.
    """

    lesson_id: UUID
    origin_site: UUID
    origin_commit: bytes
    anchor_event: UUID
    max_severity: int
    control_delta: ControlDelta
    patch_digest: bytes
    merge_base: bytes
    envelope: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Hold ``only_tightenings_travel`` and the digest widths at construction."""
        if self.control_delta not in TRAVELLING_DELTAS:
            raise WeakeningWouldTravel(str(self.lesson_id), self.control_delta.value)
        if force(self.control_delta) != 0:  # pragma: no cover - implied by the set above
            raise WeakeningWouldTravel(str(self.lesson_id), self.control_delta.value)
        if not _MIN_SEVERITY <= self.max_severity <= _MAX_SEVERITY:
            raise ValueError(
                f"max_severity must be 1…5; got {self.max_severity}. It scales the "
                f"propagation SLA clock, so a value outside the band silently changes "
                f"every sister site's due-by"
            )
        for name, digest in (
            ("patch_digest", self.patch_digest),
            ("merge_base", self.merge_base),
            ("origin_commit", self.origin_commit),
        ):
            if len(digest) != _SHA256_BYTES:
                raise ValueError(
                    f"{name} must be {_SHA256_BYTES} bytes of SHA-256; got {len(digest)}"
                )


@dataclass(frozen=True, slots=True)
class Declination:
    """A site's *falsifiable* answer of no.

    §5.9 borrows Debian's DEP-3 model, whose machine-readable ``Forwarded:
    not-needed`` has been in production since 2009: **a mandated response beats
    mandated conformity.** Each kind carries the evidence that makes it checkable
    later, and the three `CHECK`s that enforce that are mirrored here.
    """

    kind: DeclinationKind
    already_present_clause: UUID | None = None
    predicate_id: UUID | None = None
    expires_at: datetime | None = None

    def __post_init__(self) -> None:
        """Mirror ``mitigated_names_local_clause`` / ``waiver_expires`` / ``na_is_falsifiable``."""
        from .errors import DeclinationNotFalsifiable

        if self.kind not in DECLINATION_KINDS:
            raise ValueError(f"declination kind {self.kind!r} is not one of {DECLINATION_KINDS}")
        if self.kind == "mitigated" and self.already_present_clause is None:
            raise DeclinationNotFalsifiable("mitigated", "already_present_clause")
        if self.kind == "waiver" and self.expires_at is None:
            raise DeclinationNotFalsifiable("waiver", "declination_expires_at")
        if self.kind == "mechanism_absent" and self.predicate_id is None:
            raise DeclinationNotFalsifiable("mechanism_absent", "declination_predicate_id")
        if self.expires_at is not None:
            require_aware(self.expires_at, "declination.expires_at")

    def expired(self, at: datetime) -> bool:
        """Report whether a waiver's window has closed.

        MI28: *a bounded window means bounded, not merely present.* An expired
        waiver is not a declination any more — the site owes the fleet a fresh
        answer, and the caller is expected to reopen the propagation rather than
        let the record show a decline that no longer holds.
        """
        if self.expires_at is None:
            return False
        return require_aware(at, "expired(at)") >= self.expires_at


@dataclass(frozen=True, slots=True)
class Propagation:
    """One row of ``mainline.propagation``.

    The primary key ``(lesson_id, site_id)`` **is** the idempotency key for
    at-least-once delivery. §8.5: *the real idempotency is always a database
    primary key* — not a dedupe table, not a message id.

    ``score_milli`` is an integer in milli-units and ``model_version`` names the
    scorer. Read :mod:`mainline_cherrypick.travel` before assuming what that means:
    **no model produces this score.** The column is named ``model_version`` in the
    DDL and this package fills it with the version of a deterministic scorer,
    because a column named for a model that holds a deterministic value is a
    smaller lie than a model in the propagation path.
    """

    lesson_id: UUID
    site_id: UUID
    state: PropState
    score_milli: int
    model_version: str
    proposed_at: datetime
    due_by: datetime
    open_conflicts: int = 0
    adopted_commit: bytes | None = None
    already_present_clause: UUID | None = None
    declination: Declination | None = None

    def __post_init__(self) -> None:
        """Mirror ``adopt_needs_commit`` and ``adopt_needs_clean``."""
        require_aware(self.proposed_at, "propagation.proposed_at")
        require_aware(self.due_by, "propagation.due_by")
        if not 0 <= self.score_milli <= _MILLI_FULL:
            raise ValueError(f"score_milli must be 0…{_MILLI_FULL}; got {self.score_milli}")
        if self.open_conflicts < 0:
            raise ValueError(f"open_conflicts is negative ({self.open_conflicts})")
        if self.state is PropState.ADOPTED and (
            self.adopted_commit is None or self.open_conflicts != 0
        ):
            raise AdoptionNotClean(
                str(self.lesson_id),
                str(self.site_id),
                self.open_conflicts,
                self.adopted_commit is not None,
            )
        if self.state is PropState.ALREADY_PRESENT and self.already_present_clause is None:
            raise ValueError(
                "state 'already_present' with no already_present_clause throws away the "
                "strongest datum in the propagation: convergent evolution is evidence FOR "
                "the lesson, and it is only evidence if it names the local clause"
            )
        if self.state is PropState.DECLINED and self.declination is None:
            raise ValueError(
                "state 'declined' with no declination is mandated conformity failing "
                "quietly. DEP-3's whole content is that the answer of no is recorded and "
                "citable the next time this lesson arrives"
            )


@dataclass(frozen=True, slots=True)
class MergeConflict:
    """One row of ``mainline.merge_conflict``, **open** by construction.

    There is no ``resolved_commit`` field on this type, and that is deliberate:
    ``agent_fleet`` holds ``INSERT`` on this table and no ``UPDATE``, so the
    resolution columns are physically unreachable from this package. A Python
    object able to carry a resolution would model a state this component can never
    produce, and someone would eventually write code assuming it could.

    ``resolution_source`` is the rerere-with-recall back-pointer: the
    ``resolution_memory`` row this conflict *looked like*. It is a pointer to a
    proposal, never an application.
    """

    conflict_id: UUID
    lesson_id: UUID
    site_id: UUID
    clause_uuid: UUID
    base_digest: bytes
    ours_digest: bytes
    theirs_digest: bytes
    opened_at: datetime
    resolution_source: UUID | None = None

    def __post_init__(self) -> None:
        """Refuse a malformed digest and a conflict between identical renderings."""
        require_aware(self.opened_at, "merge_conflict.opened_at")
        for name, digest in (
            ("base_digest", self.base_digest),
            ("ours_digest", self.ours_digest),
            ("theirs_digest", self.theirs_digest),
        ):
            if len(digest) != _SHA256_BYTES:
                raise ValueError(
                    f"{name} must be {_SHA256_BYTES} bytes of SHA-256; got {len(digest)}"
                )
        if self.ours_digest == self.theirs_digest:
            raise ValueError(
                "ours and theirs carry the same digest: there is no conflict here. "
                "Opening one would put an item in a superintendent's queue that cannot "
                "be resolved because nothing disagrees"
            )


@dataclass(frozen=True, slots=True)
class HumanResolution:
    """A resolution a **person** signed. Unconstructible by an agent.

    Three barriers stand between model output and a recorded resolution, and this
    is the third. It refuses an empty signature, and it refuses a subject that
    looks like a machine — because the first way this guarantee would be lost is
    not an attack, it is a service account being given a friendly display name.

    §5.9: *a recorded resolution is proposed, never auto-applied* — auto-applying
    a safety-text resolution is precisely the rubber-stamp accelerant we are trying
    not to build.
    """

    conflict_id: UUID
    resolved_commit: bytes
    resolved_by: str
    resolution_sig: bytes

    def __post_init__(self) -> None:
        """Refuse an unsigned resolution and a machine subject."""
        if len(self.resolved_commit) != _SHA256_BYTES:
            raise ValueError(
                f"resolved_commit must be {_SHA256_BYTES} bytes of SHA-256; "
                f"got {len(self.resolved_commit)}"
            )
        if not self.resolution_sig:
            raise AgentWouldResolve(
                f"resolution for conflict {self.conflict_id} carries no signature"
            )
        subject = self.resolved_by.strip()
        if not subject:
            raise AgentWouldResolve(f"resolution for conflict {self.conflict_id} names no subject")
        lowered = subject.lower()
        for prefix in AGENT_SUBJECT_PREFIXES:
            if lowered.startswith(prefix):
                raise AgentWouldResolve(
                    f"resolution for conflict {self.conflict_id} is signed by {subject!r}, "
                    f"which is a service identity"
                )


@dataclass(frozen=True, slots=True)
class ResolutionMemoryRow:
    """One row of ``mainline.resolution_memory`` — rerere, with recall.

    ``origin_conflict`` is what git's ``rerere`` cannot buy. Git remembers *how*
    a conflict was resolved; it does not remember *where the resolution came
    from*, so when a resolution is later found wrong there is no way to ask which
    trees inherited it. One column, one query, and the answer is a list of sites.

    ``recalled_at`` is set when the originating resolution is found wrong. From
    that moment :mod:`mainline_cherrypick.rerere` refuses to offer it.
    """

    clause_uuid: UUID
    base_digest: bytes
    ours_digest: bytes
    theirs_digest: bytes
    resolution_text: str
    origin_conflict: UUID
    recalled_at: datetime | None = None

    def __post_init__(self) -> None:
        """Refuse a malformed digest, an empty resolution and a naive recall time."""
        for name, digest in (
            ("base_digest", self.base_digest),
            ("ours_digest", self.ours_digest),
            ("theirs_digest", self.theirs_digest),
        ):
            if len(digest) != _SHA256_BYTES:
                raise ValueError(
                    f"{name} must be {_SHA256_BYTES} bytes of SHA-256; got {len(digest)}"
                )
        if not self.resolution_text.strip():
            raise ValueError(
                "resolution_text is empty. A remembered resolution with no text is a "
                "key that will match a future conflict and then propose nothing"
            )
        if self.recalled_at is not None:
            require_aware(self.recalled_at, "resolution_memory.recalled_at")

    @property
    def key(self) -> tuple[UUID, bytes, bytes, bytes]:
        """The primary key, as the tuple :mod:`mainline_cherrypick.rerere` looks up."""
        return (self.clause_uuid, self.base_digest, self.ours_digest, self.theirs_digest)
