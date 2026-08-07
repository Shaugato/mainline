# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""Triage — route an ingested document, at ``effort: low``.

The Archivist's first call (§8.4 row 1). It decides which of the three ingest pipelines
a document belongs to and names the hazard classes it appears to touch, so the
downstream extraction call runs against the right rubric.

Decision A4 puts this on ``claude-opus-5`` at ``low`` effort rather than on Haiku. The
reason is measured rather than aesthetic: Opus 5's minimum cacheable prefix is 512
tokens against Haiku 4.5's 4096, so the shared rubric this profile places first
actually caches. Moving triage to Haiku is an ADR with a cost number attached, not a
default.

**Severity is absent from this schema on purpose.** §8.4: *a model-rated severity never
arms the gate.*
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from ._model import CallProfile, Effort, Tier
from ._rubric import COMMON_RUBRIC, RUBRIC_VERSION

__all__ = ["TRIAGE", "TriageVerdict"]

_TASK = """\
TASK: TRIAGE

Decide which ingest pipeline this document belongs to, and name the hazard classes it \
appears to concern. You are not reading it for content; you are reading it for kind.

route
  "incident"      an investigation, ICAM, root-cause report, near-miss record, or any \
document whose subject is something that happened.
  "procedure"     a standard operating procedure, work instruction, permit template, \
job hazard analysis, or any document whose subject is how work is to be done.
  "signal"        an as-operated export: instrument readings, alarm logs, calibration \
records, gas-detector histories, any document whose subject is what a plant did.
  "not_relevant"  correspondence, invoices, drawings without procedural text, marketing \
material, or anything with no safety-memory content at all.

Choose exactly one. A document that is genuinely two things — a procedure with an \
incident appendix — routes on its PRIMARY subject and the abstention flag is set so a \
human sees it. Do not split it yourself.

hazard_classes
  Lowercase, underscored, from the plant's own vocabulary where the document uses one: \
confined_space, hydrogen_sulfide, cyanide, working_at_height, mobile_plant, \
electrical_isolation, hot_work, pressure_systems, ground_control, tailings, \
lifting_operations, molten_material, dust_explosion, hazardous_energy. Add a term \
outside this list only when the document names it explicitly. At most eight. An empty \
list is a correct answer for a document that names no hazard.

abstained
  Set true when the route is genuinely unclear, when the extracted text is too short or \
too corrupted to judge, or when the document is two documents. When you set it, still \
give your best route and quote the span that made you hesitate.

basis_quote
  A verbatim span from the untrusted block that determines the route. A title line, a \
form number, a section heading. If the document is empty of usable text, quote the \
longest span you did receive and abstain.
"""

_SYSTEM = (COMMON_RUBRIC, _TASK)


class TriageVerdict(BaseModel):
    """Which pipeline a document belongs to, and what it appears to be about."""

    model_config = ConfigDict(extra="forbid")

    route: Literal["incident", "procedure", "signal", "not_relevant"] = Field(
        description="The ingest pipeline this document belongs to."
    )
    hazard_classes: list[str] = Field(
        default_factory=list,
        max_length=8,
        description="Lowercase underscored hazard classes the document concerns.",
    )
    abstained: bool = Field(
        description="True when the route is unclear or the document is two documents."
    )
    basis_quote: str = Field(
        min_length=1,
        max_length=280,
        description="Verbatim span from the source that determines the route.",
    )


TRIAGE: CallProfile[TriageVerdict] = CallProfile(
    profile_id="triage",
    agent="archivist",
    tier=Tier.T1,
    effort=Effort.LOW,
    model_key="claude-opus-5",
    prompt_version=f"triage.v1+{RUBRIC_VERSION}",
    system_blocks=_SYSTEM,
    # Adaptive thinking plus a short object. 3000 is the committed budget; a breach is
    # a TruncatedResponse and a change to this number, never a silent bigger retry.
    max_tokens=3000,
    thinking_floor_tokens=2000,
    output_model=TriageVerdict,
)
