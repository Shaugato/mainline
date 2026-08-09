# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
"""The row shapes the blame resolver reads, and the one row shape it builds.

Every dataclass here mirrors a table in ``ARCHITECTURE.md`` §5.4 and re-imposes that
table's CHECK vocabulary **in the constructor**. That is not belt-and-braces: this
package runs in the Cognition plane, where the rows it builds are handed to a caller
that holds the SQL role, and a row that would have been refused by the database should
be refused before it travels. Where the two disagree the database wins, always — these
constructors are an early, legible failure, never the enforcement.

One shape is built rather than read: :class:`ProvisionalBlameEdge`. It is the only
output of this package that reaches a table, and it is deliberately incapable of
carrying ``state='active'`` or a basis other than ``inferred_semantic``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import TYPE_CHECKING, Any

from .errors import FloatInEvidentiaryPayload, InferenceActivated

if TYPE_CHECKING:
    from collections.abc import Mapping

__all__ = [
    "EVENT_KINDS",
    "MAX_SEVERITY",
    "MIN_SEVERITY",
    "SEVERITY_BASES",
    "BlameBasis",
    "BlameEdgeRow",
    "BlameState",
    "ClauseCandidate",
    "ClosureRow",
    "EventRow",
    "ProvisionalBlameEdge",
    "ResolvedBlame",
    "VirulenceClass",
    "assert_float_free",
]

MIN_SEVERITY = 0
MAX_SEVERITY = 5

#: Above this band a model-rated severity may not arm anything (CHECK ``model_cannot_arm``).
_MODEL_ARM_FLOOR = 4

#: ``mainline.event.kind`` CHECK vocabulary.
EVENT_KINDS: frozenset[str] = frozenset(
    {"incident", "near_miss", "regulator_notice", "oem_alert", "audit_finding", "capa"}
)

#: ``mainline.event.severity_basis`` CHECK vocabulary.
SEVERITY_BASES: frozenset[str] = frozenset(
    {"coded_field", "regulator_class", "human_rated", "model_rated"}
)

_MODEL_RATED = "model_rated"

#: Candidate labels are minted by us and are the ONLY clause handle the model ever sees.
#: A UUID in a prompt is a UUID a model can invent; ``C7`` either is in the map or is not.
_LABEL_RE = re.compile(r"^C[0-9]{1,3}$")

_HEX_RE = re.compile(r"^[0-9a-f]+$")

#: ``p_link`` is stored in the database as FLOAT8, but it is carried here — and hashed
#: into ``features`` — as an integer count of thousandths. See ADR 0042.
MIN_P_LINK_MILLI = 1
MAX_P_LINK_MILLI = 999


class BlameBasis(StrEnum):
    """``mainline.blame_basis``. Basis-graded evidential force."""

    ASSERTED_DOCUMENT = "asserted_document"
    ASSERTED_HUMAN = "asserted_human"
    DERIVED_DOCUMENTARY = "derived_documentary"
    INFERRED_SEMANTIC = "inferred_semantic"


class BlameState(StrEnum):
    """``mainline.blame_state``. Retiring an edge is a transition, never a delete."""

    ACTIVE = "active"
    PROVISIONAL = "provisional"
    DORMANT = "dormant"
    REFUTED = "refuted"


class VirulenceClass(StrEnum):
    """``mainline.virulence_class``. Banded exactly once, in the closure, never here."""

    ROUTINE = "routine"
    SERIOUS = "serious"
    BLOOD_MAJOR = "blood_major"
    BLOOD_FATAL = "blood_fatal"


def assert_float_free(payload: Any, *, path: str = "$") -> None:
    """Refuse a float anywhere in a payload that will be hashed.

    Raises:
        FloatInEvidentiaryPayload: at the first float found, naming its path.
    """
    if isinstance(payload, bool):
        return
    if isinstance(payload, float):
        raise FloatInEvidentiaryPayload(path)
    if isinstance(payload, dict):
        for key, value in payload.items():
            assert_float_free(value, path=f"{path}.{key}")
        return
    if isinstance(payload, list | tuple):
        for index, value in enumerate(payload):
            assert_float_free(value, path=f"{path}[{index}]")


def _require_aware(value: datetime, field: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(
            f"{field} is a naive datetime. A naive timestamp in an evidentiary payload is an "
            f"unanswerable question in cross-examination."
        )


@dataclass(frozen=True, slots=True)
class EventRow:
    """One ``mainline.event``, as the resolver reads it.

    ``control_classes`` is the set of ``control_failure.control_class`` values recorded
    against this event. It is **deterministic** — ICAM/bowtie normalised at ingest — and
    it is the gazetteer the semantic-anchoring layer checks a proposal against.
    """

    event_id: str
    site_id: str
    occurred_at: datetime
    kind: str
    title: str
    narrative: str
    source_sha256: str
    severity_gate: int
    severity_basis: str
    control_classes: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        """Re-impose ``mainline.event``'s CHECK vocabulary at construction."""
        _require_aware(self.occurred_at, "event.occurred_at")
        if self.kind not in EVENT_KINDS:
            raise ValueError(f"event kind {self.kind!r} is outside {sorted(EVENT_KINDS)}")
        if self.severity_basis not in SEVERITY_BASES:
            raise ValueError(
                f"severity_basis {self.severity_basis!r} is outside {sorted(SEVERITY_BASES)}"
            )
        if not MIN_SEVERITY <= self.severity_gate <= MAX_SEVERITY:
            raise ValueError(
                f"severity_gate {self.severity_gate} is outside {MIN_SEVERITY}..{MAX_SEVERITY}"
            )
        if self.severity_gate >= _MODEL_ARM_FLOOR and self.severity_basis == _MODEL_RATED:
            raise ValueError(
                f"event {self.event_id} carries severity_gate={self.severity_gate} on a "
                f"model_rated basis. A model's severity may never arm a blocking gate "
                f"(CHECK model_cannot_arm, ARCHITECTURE.md §5.4)."
            )
        if not self.narrative.strip():
            raise ValueError(f"event {self.event_id} has an empty narrative")


@dataclass(frozen=True, slots=True)
class ClauseCandidate:
    """One clause offered to the proposer, behind an opaque label.

    Attributes:
        label: ``C1``..``C999``. Minted by the caller; the only clause handle the model
            is shown, so a hallucinated handle is a lookup miss rather than a wrong row.
        canon_text: the canonicalised clause text. Quotes are bound into **this** string
            by exact search, so it must be the same bytes the clause version stores.
    """

    label: str
    clause_uuid: str
    site_id: str
    canon_text: str

    def __post_init__(self) -> None:
        """Refuse a label shape the verifier could confuse with a UUID."""
        if not _LABEL_RE.match(self.label):
            raise ValueError(
                f"candidate label {self.label!r} must match {_LABEL_RE.pattern}. Labels are "
                f"minted by us so that a model cannot name a clause we did not offer."
            )
        if not self.canon_text.strip():
            raise ValueError(f"candidate {self.label} has empty canon_text")


@dataclass(frozen=True, slots=True)
class ClosureRow:
    """One row of ``mainline.clause_blame_current`` — the projection the gate reads.

    Nothing in this package recomputes ``max_severity`` or ``virulence``. They are
    projections written by the Projector from ``blame_edge``; a second implementation of
    the banding here would be a second answer to a question that must have exactly one
    (P2). What the resolver *does* is refuse the projection when it contradicts the
    ancestry it was handed in the unsafe direction.
    """

    clause_uuid: str
    as_of_commit: str
    closure_gen: int
    site_id: str
    ancestor_events: tuple[str, ...]
    ancestor_count: int
    max_severity: int
    virulence: VirulenceClass
    depth: int
    truncated: bool
    computed_by: str
    projector_ver: str

    def __post_init__(self) -> None:
        """Re-impose ``clause_blame_closure``'s CHECK vocabulary."""
        if self.closure_gen < 0:
            raise ValueError(f"closure_gen {self.closure_gen} is negative (CHECK gen_positive)")
        if not MIN_SEVERITY <= self.max_severity <= MAX_SEVERITY:
            raise ValueError(
                f"max_severity {self.max_severity} is outside {MIN_SEVERITY}..{MAX_SEVERITY} "
                f"(CHECK sev_range)"
            )
        if self.depth < 0:
            raise ValueError(f"closure depth {self.depth} is negative")


@dataclass(frozen=True, slots=True)
class BlameEdgeRow:
    """One ``mainline.blame_edge``, as the resolver reads it."""

    event_id: str
    clause_uuid: str
    basis: BlameBasis
    state: BlameState


@dataclass(frozen=True, slots=True)
class ResolvedBlame:
    """A resolved blame pointer: the incidents a clause version is answerable to.

    Attributes:
        ancestry: the ancestor events, ordered by severity descending then by
            ``occurred_at`` ascending then by id. The order is a display order and a
            stable one; it is never an argument about which incident matters more.
        ancestry_complete: false when the closure was truncated. **A truncated closure
            must never be indistinguishable from a complete one**, which is why this is
            a field on the result rather than a footnote in a log.
        over_banded: the projection exceeds the highest severity in the resolved
            ancestry. Fails safe, so it is reported rather than refused — a downgrade
            recorded after the closure was computed produces exactly this.
        excluded_inferred: event ids reachable through ``inferred_semantic`` edges and
            correctly absent from the closure. Surfaced so a reviewer can see what the
            system declined to count, which is the honest form of "we found something
            but it does not block".
    """

    clause_uuid: str
    as_of_commit: str
    closure_gen: int
    ancestry: tuple[EventRow, ...]
    max_severity: int
    virulence: VirulenceClass
    ancestry_complete: bool
    depth: int
    over_banded: bool
    excluded_inferred: tuple[str, ...]

    def headline(self) -> EventRow | None:
        """Return the incident a reader should be shown first, or ``None`` if there is none."""
        return self.ancestry[0] if self.ancestry else None

    def to_mapping(self) -> dict[str, Any]:
        """Render for a console payload or an MCP-facing aggregate."""
        return {
            "clause_uuid": self.clause_uuid,
            "as_of_commit": self.as_of_commit,
            "closure_gen": self.closure_gen,
            "ancestor_count": len(self.ancestry),
            "ancestor_events": [event.event_id for event in self.ancestry],
            "max_severity": self.max_severity,
            "virulence": str(self.virulence),
            "ancestry_complete": self.ancestry_complete,
            "depth": self.depth,
            "over_banded": self.over_banded,
            "excluded_inferred": list(self.excluded_inferred),
        }


@dataclass(frozen=True, slots=True)
class ProvisionalBlameEdge:
    """The one row this package builds: an inferred, provisional blame edge.

    It cannot be constructed with any other basis or any other state. That is the point
    of the type: the DDL constraint ``inference_never_blocks`` refuses the write, and
    this refuses the object, so the impossible row cannot even be held in memory long
    enough to be logged as if it existed.
    """

    event_id: str
    clause_uuid: str
    site_id: str
    commit_id: str
    p_link_milli: int
    features: Mapping[str, Any]
    attribution: str
    evidence_span: tuple[int, int]
    evidence_quote_sha256: str
    provisional_until: datetime
    model_id: str
    prompt_version: str
    evidence_doc_id: str | None = None
    basis: BlameBasis = BlameBasis.INFERRED_SEMANTIC
    state: BlameState = BlameState.PROVISIONAL

    def __post_init__(self) -> None:
        """Refuse every shape the database would refuse, and one it would not."""
        if self.basis is not BlameBasis.INFERRED_SEMANTIC:
            raise InferenceActivated(
                f"ProvisionalBlameEdge built with basis={self.basis!s}; this type exists to "
                f"carry inferred_semantic and nothing else"
            )
        if self.state is not BlameState.PROVISIONAL:
            raise InferenceActivated(
                f"ProvisionalBlameEdge built with state={self.state!s} on an inferred_semantic "
                f"basis"
            )
        if not MIN_P_LINK_MILLI <= self.p_link_milli <= MAX_P_LINK_MILLI:
            raise ValueError(
                f"p_link_milli {self.p_link_milli} is outside "
                f"{MIN_P_LINK_MILLI}..{MAX_P_LINK_MILLI}; CHECK scored_needs_features requires "
                f"a score on an inferred basis, and a score of 0 or 1000 is a certainty nobody "
                f"inferred"
            )
        start, end = self.evidence_span
        if start < 0 or end <= start:
            raise ValueError(f"evidence_span {self.evidence_span} is not a forward, non-empty span")
        if not _HEX_RE.match(self.evidence_quote_sha256):
            raise ValueError(
                f"evidence_quote_sha256 {self.evidence_quote_sha256!r} is not lowercase hex"
            )
        _require_aware(self.provisional_until, "provisional_until")
        if not self.attribution.strip():
            raise ValueError(
                "attribution is empty. The DDL comment is explicit: attribution is prose a "
                "human is shown, never a bare number."
            )
        # `features` is hashed into the ledger with the rest of the row.
        assert_float_free(dict(self.features), path="$.features")
