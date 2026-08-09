# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""The typed shape of a refusal payload: the reason set, the alternative, the context.

Five atom families and five alternative kinds, one frozen dataclass each, because the
wire schema closes every one of them with ``additionalProperties: false`` and a
dictionary would let a caller add a sixteenth key that the validator then refuses at the
last possible moment. A dataclass refuses it at the first.

**Invariant I15 is a property of these types, not of a check somewhere downstream.**
There is no field on any atom where a score, rating, threshold or ranking of a named
human could be placed. ``Obligation.origin`` is a closed vocabulary, ``severity`` is a
property of an EVENT, and ``signer_sub`` does not appear at all — a signature is a fact
that belongs in the disposition record, not a measurement that belongs in a diagnosis.
Adding such a field here would be a MAJOR bump with that consequence in the changelog.

Every ``to_wire()`` omits a key whose value is ``None``. A JSON ``null`` in an atom is
not the same as an absent key: ``event_id: null`` fails the UUID pattern, while an absent
``event_id`` is an obligation that names no precursor event, which is a real and common
shape.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Literal, Protocol, runtime_checkable

__all__ = [
    "REFUSE_SQLSTATES",
    "AuthorityGap",
    "CapabilityGap",
    "ClauseAtom",
    "DisposeObligations",
    "EventAtom",
    "EvidenceItem",
    "ForkSubject",
    "MaterialiseAuthority",
    "MusAtom",
    "Naa",
    "Obligation",
    "RefusalContext",
    "RefusalLike",
    "RefusalPayload",
    "SubstituteKind",
    "SupplyEvidence",
    "atom_sort_key",
]

# The four REFUSE-class codes (spec/errors.md section 1). 40001 is absent because an
# undecided transaction has no reason set; 42501 is absent because a DENY is a fact
# about the writer, not a diagnosis of the subject.
REFUSE_SQLSTATES: frozenset[str] = frozenset({"23514", "23503", "23505", "P0001"})

_NAA_REASONS: frozenset[str] = frozenset(
    {
        "probe_budget_exhausted",
        "no_legal_verdict_exists",
        "requires_human_authority",
        "not_computable",
    }
)


def _drop_none(fields: Mapping[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in fields.items() if value is not None}


@dataclass(frozen=True, slots=True)
class Obligation:
    """An open obligation attached to the subject: the commonest atom by far."""

    obligation_id: str
    origin: str | None = None
    clause_id: str | None = None
    event_id: str | None = None
    severity: int | None = None
    virulence: str | None = None
    detail: str | None = None

    kind: Literal["obligation"] = "obligation"

    def to_wire(self) -> dict[str, Any]:
        """Render the atom in wire shape, omitting absent fields."""
        return _drop_none(
            {
                "kind": self.kind,
                "obligation_id": self.obligation_id,
                "origin": self.origin,
                "clause_id": self.clause_id,
                "event_id": self.event_id,
                "severity": self.severity,
                "virulence": self.virulence,
                "detail": self.detail,
            }
        )


@dataclass(frozen=True, slots=True)
class ClauseAtom:
    """A cited clause whose ancestry armed the gate."""

    clause_id: str
    commit_id: str | None = None
    relation: str | None = None
    detail: str | None = None

    kind: Literal["clause"] = "clause"

    def to_wire(self) -> dict[str, Any]:
        """Render the atom in wire shape, omitting absent fields."""
        return _drop_none(
            {
                "kind": self.kind,
                "clause_id": self.clause_id,
                "commit_id": self.commit_id,
                "relation": self.relation,
                "detail": self.detail,
            }
        )


@dataclass(frozen=True, slots=True)
class EventAtom:
    """A precursor event bonded into the ancestry."""

    event_id: str
    severity: int | None = None
    detail: str | None = None

    kind: Literal["event"] = "event"

    def to_wire(self) -> dict[str, Any]:
        """Render the atom in wire shape, omitting absent fields."""
        return _drop_none(
            {
                "kind": self.kind,
                "event_id": self.event_id,
                "severity": self.severity,
                "detail": self.detail,
            }
        )


@dataclass(frozen=True, slots=True)
class AuthorityGap:
    """The authority source holds no row for this key. The gate failed closed."""

    relation: str
    key: Mapping[str, str | int | None]
    detail: str | None = None

    kind: Literal["authority_gap"] = "authority_gap"

    def to_wire(self) -> dict[str, Any]:
        """Render the atom in wire shape, omitting absent fields."""
        return _drop_none(
            {
                "kind": self.kind,
                "relation": self.relation,
                "key": dict(self.key),
                "detail": self.detail,
            }
        )


@dataclass(frozen=True, slots=True)
class CapabilityGap:
    """A required verdict, credential, predicate, counter or anchor is absent."""

    capability: str
    required_value: str | int | bool | None = None
    observed_value: str | int | bool | None = None
    detail: str | None = None

    kind: Literal["capability_gap"] = "capability_gap"

    def to_wire(self) -> dict[str, Any]:
        """Render the atom in wire shape, omitting absent fields."""
        return _drop_none(
            {
                "kind": self.kind,
                "capability": self.capability,
                "required_value": self.required_value,
                "observed_value": self.observed_value,
                "detail": self.detail,
            }
        )


MusAtom = Obligation | ClauseAtom | EventAtom | AuthorityGap | CapabilityGap


def atom_sort_key(atom: MusAtom) -> tuple[str, str]:
    """Sort key implementing wire rule M-3: kind, then identifier.

    Atom order is not significant and consumers must not depend on it — but a payload
    that is byte-stable can be snapshotted, and a snapshot is how a conformance corpus
    notices that a diagnosis changed when nothing was supposed to change.
    """
    identifiers = {
        "obligation": getattr(atom, "obligation_id", ""),
        "clause": getattr(atom, "clause_id", ""),
        "event": getattr(atom, "event_id", ""),
        "authority_gap": getattr(atom, "relation", ""),
        "capability_gap": getattr(atom, "capability", ""),
    }
    return (atom.kind, str(identifiers.get(atom.kind, "")))


@dataclass(frozen=True, slots=True)
class DisposeObligations:
    """Dispose exactly these obligations; these verdict kinds are legal here."""

    obligation_ids: Sequence[str]
    cardinality: int
    description: str
    legal_kinds: Sequence[str] | None = None

    kind: Literal["dispose_obligations"] = "dispose_obligations"

    def to_wire(self) -> dict[str, Any]:
        """Render the alternative in wire shape, omitting absent fields."""
        return _drop_none(
            {
                "kind": self.kind,
                "obligation_ids": list(self.obligation_ids),
                "cardinality": self.cardinality,
                "legal_kinds": None if self.legal_kinds is None else list(self.legal_kinds),
                "description": self.description,
            }
        )


@dataclass(frozen=True, slots=True)
class SubstituteKind:
    """The attempted verdict is not legal at this classification; these are."""

    legal_kinds: Sequence[str]
    description: str
    cardinality: int = 1

    kind: Literal["substitute_kind"] = "substitute_kind"

    def to_wire(self) -> dict[str, Any]:
        """Render the alternative in wire shape."""
        return {
            "kind": self.kind,
            "legal_kinds": list(self.legal_kinds),
            "cardinality": self.cardinality,
            "description": self.description,
        }


@dataclass(frozen=True, slots=True)
class SupplyEvidence:
    """A required property is absent: a countersigner, a control, a predicate, an anchor."""

    required: Sequence[str]
    description: str
    cardinality: int = 1

    kind: Literal["supply_evidence"] = "supply_evidence"

    def to_wire(self) -> dict[str, Any]:
        """Render the alternative in wire shape."""
        return {
            "kind": self.kind,
            "required": list(self.required),
            "cardinality": self.cardinality,
            "description": self.description,
        }


@dataclass(frozen=True, slots=True)
class MaterialiseAuthority:
    """The authority source must hold a row for this key before the gate can evaluate."""

    relation: str
    key: Mapping[str, str | int | None]
    description: str
    cardinality: int = 1

    kind: Literal["materialise_authority"] = "materialise_authority"

    def to_wire(self) -> dict[str, Any]:
        """Render the alternative in wire shape."""
        return {
            "kind": self.kind,
            "relation": self.relation,
            "key": dict(self.key),
            "cardinality": self.cardinality,
            "description": self.description,
        }


@dataclass(frozen=True, slots=True)
class ForkSubject:
    """The subject is completed and pinned; the only admissible path is a child."""

    parent_subject_id: str
    description: str
    cardinality: int = 1

    kind: Literal["fork_subject"] = "fork_subject"

    def to_wire(self) -> dict[str, Any]:
        """Render the alternative in wire shape."""
        return {
            "kind": self.kind,
            "parent_subject_id": self.parent_subject_id,
            "cardinality": self.cardinality,
            "description": self.description,
        }


Naa = DisposeObligations | SubstituteKind | SupplyEvidence | MaterialiseAuthority | ForkSubject


@dataclass(frozen=True, slots=True)
class EvidenceItem:
    """A pointer a third party can follow without the emitter's cooperation."""

    kind: str
    ref: str
    digest: str | None = None

    def to_wire(self) -> dict[str, Any]:
        """Render the evidence item in wire shape, omitting an absent digest."""
        return _drop_none({"kind": self.kind, "ref": self.ref, "digest": self.digest})


@runtime_checkable
class RefusalLike(Protocol):
    """The structural shape of a gate refusal this package can diagnose.

    Structural rather than nominal, and that is deliberate. ``trappoint_core.GateRefused``
    is the intended input, but this distribution does not import it: the substrate's
    refusal diagnoser must be usable by a conformance runner holding a raw driver error,
    by a replay harness holding a recorded row, and by a fork whose exception type is its
    own. ``from_exception()`` in ``diagnose.py`` builds a ``RefusalContext`` from any of
    them.
    """

    @property
    def sqlstate(self) -> str:
        """The SQLSTATE the database reported."""

    @property
    def constraint(self) -> str:
        """The exhibit name, verbatim."""

    @property
    def message(self) -> str:
        """The database message, verbatim, including its prefix."""


@dataclass(frozen=True, slots=True)
class RefusalContext:
    """Everything about a refusal that is known before the reason set is computed.

    This is the emitter's input, and every field of it is a FACT the database reported or
    the caller observed. Nothing here is inferred. ``constraint_source`` records which:
    ``reported`` means the driver supplied the exhibit, ``parsed`` means it was recovered
    from the message text, and a consumer must render the second as a weakened diagnosis.
    """

    sqlstate: str
    constraint: str
    message: str
    subject_kind: str
    subject_id: str
    gate_epoch: int
    constraint_source: Literal["reported", "parsed"] = "reported"
    attempt: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Refuse a context that could not have come from a REFUSE-class outcome."""
        if self.sqlstate not in REFUSE_SQLSTATES:
            raise ValueError(
                f"{self.sqlstate!r} is not a REFUSE-class code. 40001 is undecided and has "
                "no reason set; 42501 is a fact about the writer. Only "
                f"{', '.join(sorted(REFUSE_SQLSTATES))} are payloads."
            )
        if not self.constraint:
            raise ValueError("a refusal with no exhibit is not evidence")
        if self.gate_epoch < 0:
            raise ValueError("gate_epoch is monotone and non-negative by construction")


@dataclass(frozen=True, slots=True)
class RefusalPayload:
    """The assembled payload. ``to_wire()`` is what validates and what is recorded."""

    spec_version: str
    refusal_id: str
    observed_at: str
    context: RefusalContext
    diagnosis: Literal["declarative", "quickxplain", "none"]
    probe_calls: int
    mus: Sequence[MusAtom]
    naa: Naa | None
    naa_reason: str | None
    profile: str | None = None
    evidence: Sequence[EvidenceItem] = ()
    ext: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Refuse the four ways a payload can assert two incompatible things at once."""
        if not self.mus:
            raise ValueError(
                "a refusal with no reason set is the artefact invariant I14 exists to abolish"
            )
        if (self.naa is None) == (self.naa_reason is None):
            raise ValueError(
                "exactly one of naa and naa_reason is set: a null alternative without a "
                "reason is an unexplained silence, and an alternative with a reason "
                "asserts a thing and its absence at once"
            )
        if self.naa_reason is not None and self.naa_reason not in _NAA_REASONS:
            raise ValueError(f"{self.naa_reason!r} is not one of {', '.join(sorted(_NAA_REASONS))}")
        if self.diagnosis == "declarative" and self.probe_calls != 0:
            raise ValueError(
                "a declarative decomposition consumes no oracle calls; a non-zero probe "
                "count means the emitter probed and mislabelled it"
            )
        if self.diagnosis == "none" and self.naa is not None:
            raise ValueError(
                "an emitter that could not establish minimality cannot assert a "
                "minimum-cardinality alternative"
            )
        if self.probe_calls < 0:
            raise ValueError("probe_calls counts oracle calls and cannot be negative")

    def to_wire(self) -> dict[str, Any]:
        """Render the payload exactly as ``spec/wire/refusal.schema.json`` describes it."""
        payload: dict[str, Any] = {
            "spec_version": self.spec_version,
            "refusal_id": self.refusal_id,
            "observed_at": self.observed_at,
            "class": "gate",
            "sqlstate": self.context.sqlstate,
            "constraint": self.context.constraint,
            "constraint_source": self.context.constraint_source,
            "message": self.context.message,
            "subject_kind": self.context.subject_kind,
            "subject_id": self.context.subject_id,
            "gate_epoch": self.context.gate_epoch,
            "diagnosis": self.diagnosis,
            "probe_calls": self.probe_calls,
            "mus": [atom.to_wire() for atom in sorted(self.mus, key=atom_sort_key)],
            "naa": None if self.naa is None else self.naa.to_wire(),
            "naa_reason": self.naa_reason,
            "evidence": [item.to_wire() for item in self.evidence],
            "ext": dict(self.ext),
        }
        if self.profile is not None:
            payload["profile"] = self.profile
        return payload
