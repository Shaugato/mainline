# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
"""Inputs to cue synthesis: the event side and the permit side.

These are the *only* things either entry point reads.  Two omissions are deliberate and
load-bearing:

* **No severity.**  ARCHITECTURE §8.4 gives the Archivist no say over severity, and
  ``mainline.event.model_cannot_arm`` refuses a gate-arming severity that a model rated.
  A synthesiser that could see ``severity_gate`` would be able to write a more alarming
  cue for a fatality than for a near miss, which is the same failure wearing a different
  hat — the cue would then encode the rating rather than the mechanism.
* **No dates.**  A cue is a proposition about a mechanism, not about a year.  Feeding
  ``occurred_at`` in invites recency language into a facet that has to stay plant-agnostic
  and time-free, and the retro-recall time wall is enforced by predicates upstream
  (recall.md D12), never by anything the model reads.

Everything here is a frozen Pydantic model: an input that can be mutated between the
payload that was hashed and the text that was searched is an input we cannot testify about.
"""

from __future__ import annotations

from typing import Any, Final, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

__all__ = [
    "MAX_ACTIVITY_LEVEL",
    "ActivityNode",
    "ActivityPath",
    "ClauseDiff",
    "ClauseDiffEntry",
    "ControlFailureHint",
    "EventInput",
    "IsolationPlan",
    "IsolationPoint",
    "PermitInput",
]

#: ``mainline.activity_node.level`` is ``CHECK (level BETWEEN 1 AND 3)`` — fonds, series,
#: file.  The path handed to a cue may not be deeper than the taxonomy allows.
MAX_ACTIVITY_LEVEL: Final[int] = 3

HazardEnergy = Literal[
    "gravity",
    "pressure",
    "electrical",
    "thermal",
    "chemical",
    "kinetic",
    "biological",
    "radiation",
]
"""Byte-identical to ``mainline.control_failure.hazard_energy``'s CHECK."""

ControlDelta = Literal["weaken", "remove", "strengthen", "neutral"]
"""The clause-level change classes.  ``weaken`` and ``remove`` are what the gate is for."""


class ActivityNode(BaseModel):
    """One level of the functional archival path (ISO 15489 / NAA, ARCHITECTURE §5.4).

    ``label`` is a **function performed**, never a thing and never a place.  That is what
    makes blame survive an asset-tag renumbering or an org-chart redraw, and it is why the
    label — not the asset — is what goes into the embedded text.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    scope_id: UUID
    level: int = Field(ge=1, le=MAX_ACTIVITY_LEVEL)
    label: str = Field(min_length=1, max_length=200)

    @model_validator(mode="after")
    def _label_is_not_blank(self) -> ActivityNode:
        if not self.label.strip():
            raise ValueError("activity label is blank")
        return self


class ActivityPath(BaseModel):
    """The ordered path from fonds to leaf.

    Contiguity from level 1 is enforced rather than assumed: the Level-Materialised Bond
    writes one cue row per level, so a path that skips level 2 would silently produce a
    cue that is unreachable from the series-level arm of the ANN search — a miss with no
    refusal anywhere.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    nodes: tuple[ActivityNode, ...]

    @model_validator(mode="after")
    def _contiguous_from_root(self) -> ActivityPath:
        if not self.nodes:
            raise ValueError("an activity path must have at least the level-1 fonds node")
        if len(self.nodes) > MAX_ACTIVITY_LEVEL:
            raise ValueError(
                f"activity path is deeper than the taxonomy: {len(self.nodes)} nodes, "
                f"maximum {MAX_ACTIVITY_LEVEL}"
            )
        for index, node in enumerate(self.nodes):
            if node.level != index + 1:
                raise ValueError(
                    "activity path levels must run 1..n without gaps; "
                    f"position {index} carries level {node.level}"
                )
        seen = {node.scope_id for node in self.nodes}
        if len(seen) != len(self.nodes):
            raise ValueError("an activity path may not repeat a scope_id")
        return self

    @property
    def leaf(self) -> ActivityNode:
        return self.nodes[-1]

    def rendered(self) -> str:
        """The path as it appears in the embedded text: labels, root first, ' / ' joined.

        Rendered from labels rather than ids because the embedding has to carry meaning; a
        UUID contributes nothing to a sentence embedding but does consume tokens.
        """
        return " / ".join(node.label.strip() for node in self.nodes)


class ControlFailureHint(BaseModel):
    """An ICAM/bowtie control failure already normalised by ingest.

    Optional, and *evidence rather than instruction*: when present it is placed in the
    quarantined user turn alongside the narrative so the ``control_failure`` facet can name
    the control class the corpus already uses as a join key.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    control_class: str = Field(min_length=1, max_length=120)
    barrier_role: Literal["preventive", "recovery"]
    failure_mode: Literal["absent", "ineffective", "bypassed", "degraded", "not_verified"]
    hazard_energy: HazardEnergy

    def as_payload(self) -> dict[str, Any]:
        return {
            "control_class": self.control_class,
            "barrier_role": self.barrier_role,
            "failure_mode": self.failure_mode,
            "hazard_energy": self.hazard_energy,
        }


class EventInput(BaseModel):
    """The document side: one appraised record from ``mainline.event``."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    event_id: UUID
    site_id: UUID
    taxonomy_ver: int = Field(ge=0)
    kind: Literal["incident", "near_miss", "regulator_notice", "oem_alert", "audit_finding", "capa"]
    title: str = Field(min_length=1, max_length=500)
    narrative: str = Field(min_length=1)
    external_ref: str | None = Field(default=None, max_length=120)
    control_failures: tuple[ControlFailureHint, ...] = ()

    @property
    def subject_ref(self) -> str:
        return self.external_ref or str(self.event_id)


class IsolationPoint(BaseModel):
    """One isolation point on the permit's plan.

    ``tag`` is the single richest anchor on the permit side: it is an equipment tag, it is
    checkable, and a cue that invents one is exactly what layer 4 exists to catch.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    tag: str = Field(min_length=1, max_length=64)
    energy: HazardEnergy
    method: str = Field(min_length=1, max_length=300)
    verified_by: str | None = Field(default=None, max_length=120)


class IsolationPlan(BaseModel):
    """The permit's isolation plan, as the exposure cue sees it."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    plan_ref: str = Field(min_length=1, max_length=120)
    points: tuple[IsolationPoint, ...] = ()
    residual_energy_notes: str = ""


class ClauseDiffEntry(BaseModel):
    """One clause the permit proposes to change.

    ``before_text`` and ``after_text`` are carried in full because the *diff* is where the
    exposure lives: "the clause that required a second isolation now requires a visual
    check" is a mechanism-bearing statement, and neither half of it says that alone.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    clause_uuid: UUID
    clause_ref: str = Field(min_length=1, max_length=120)
    control_delta: ControlDelta
    before_text: str = ""
    after_text: str = ""
    rationale: str = ""

    @property
    def is_waiver(self) -> bool:
        """``weaken`` or ``remove`` — the two deltas the diachronic gate exists for."""
        return self.control_delta in {"weaken", "remove"}

    @model_validator(mode="after")
    def _delta_has_text(self) -> ClauseDiffEntry:
        if self.control_delta == "remove" and not self.before_text.strip():
            raise ValueError("a removed clause must carry the text being removed")
        if self.control_delta in {"weaken", "strengthen"} and not (
            self.before_text.strip() and self.after_text.strip()
        ):
            raise ValueError(f"a {self.control_delta} diff needs both before and after text")
        return self


class ClauseDiff(BaseModel):
    """The set of clause changes this permit carries."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    entries: tuple[ClauseDiffEntry, ...] = ()

    def waived_or_weakened(self) -> tuple[ClauseDiffEntry, ...]:
        return tuple(entry for entry in self.entries if entry.is_waiver)


class PermitInput(BaseModel):
    """The query side: the permit whose merge the gate may refuse.

    Carries its own ``activity_path`` and ``asset_class`` so that
    ``synthesise_exposure_cue(permit, isolation_plan, clause_diff)`` keeps the three-argument
    shape while still being able to build the same embedded text as the event side.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    permit_id: UUID
    site_id: UUID
    taxonomy_ver: int = Field(ge=0)
    activity_path: ActivityPath
    asset_class: str = Field(min_length=1, max_length=120)
    work_type: str = Field(min_length=1, max_length=120)
    scope_of_work: str = Field(min_length=1)
    external_ref: str | None = Field(default=None, max_length=120)

    @property
    def subject_ref(self) -> str:
        return self.external_ref or str(self.permit_id)
