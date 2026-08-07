# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
"""The structured-output contracts for the two induction phases.

recall.md D6 / ARCHITECTURE §8.4: every T1 call declares ``output_config.format`` with
``json_schema``, ``additionalProperties: false`` and ``strict: true``, **and** the answer is
re-validated client-side with Pydantic.  These are the client-side halves.

``extra="forbid"`` is not decoration.  Under structural quarantine an injection's remaining
lever is to smuggle an extra field past a permissive validator, and the field it would most
like to smuggle here is one that changes where an incident gets filed.

``activity_root`` is a plain string rather than an enum on the model, and is checked against
the loaded register in :mod:`~mainline_recall_agent.taxonomy.induction` instead.  The
register is deployment data — it is the *buyer's* Material Unwanted Event list — so baking
it into a class attribute would make the schema a build-time constant of the wrong thing.
The wire schema handed to the model *does* carry the enum: see
:func:`~mainline_recall_agent.taxonomy.prompts.build_induction_prefix`, which puts the
codes in the cached system prefix, and the induction loop, which refuses an off-register
answer rather than trusting the model to have honoured it.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

__all__ = [
    "DocumentLabel",
    "LabelProposalBatch",
    "MergeDecision",
    "MergeGroup",
]


class DocumentLabel(BaseModel):
    """One document's proposed place in the taxonomy (TnT-LLM phase 1)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    doc_id: str = Field(description="Identifier of the narrative being labelled.")
    activity_root: str = Field(
        description="Level-1 code from the frozen register. Never invented."
    )
    series_label: str = Field(
        description="Level-2 activity class, naming a function performed."
    )
    file_label: str = Field(description="Level-3 activity, naming a function performed.")
    insufficient_evidence: bool = Field(
        default=False,
        description="True when the narrative does not support any activity classification.",
    )
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)


class LabelProposalBatch(BaseModel):
    """Phase 1 output for one batch of narratives."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    labels: list[DocumentLabel] = Field(default_factory=list)


class MergeGroup(BaseModel):
    """One merged label: the canonical wording plus everything folded into it."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    level: int = Field(ge=2, le=3, description="2 for a series, 3 for a file.")
    activity_root: str
    parent_label: str | None = Field(
        default=None, description="The series a file sits under; null at level 2."
    )
    canonical_label: str
    members: list[str] = Field(
        default_factory=list,
        description="Every proposed label folded into this one, canonical included.",
    )
    support: int = Field(default=0, ge=0, description="Documents backing the merged label.")


class MergeDecision(BaseModel):
    """Phase 2 output: the taxonomy after one round of merge and refine."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    groups: list[MergeGroup] = Field(default_factory=list)
