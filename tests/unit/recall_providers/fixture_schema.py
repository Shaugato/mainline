# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
"""The judge schema and byte-frozen prompt text used by the provider suite.

The rubric below is a *fixture*, not the shipped rubric — the shipped one belongs to
``recall-fusion-admission``.  It is nonetheless the right shape: ARCHITECTURE §6.4 requires
the listwise judge to **name the shared mechanism and the shared precondition, or return
``not_relevant``**, because that justification becomes ``blocking_check.evidence_summary``.

These strings are byte-frozen on purpose.  ``SystemPrefix.prefix_digest()`` over them is
pinned by ``test_prompt_cache.py``; if the text moves, the committed cassettes miss and the
test says so, which is exactly what a prompt change should cost — a commit, not a deploy
(ARCHITECTURE §8.2).
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

__all__ = [
    "FACET_DEFINITIONS",
    "FEW_SHOTS",
    "PROMPT_VERSION",
    "RUBRIC",
    "CandidateVerdict",
    "RerankVerdict",
    "judge_payload",
]

PROMPT_VERSION = "recall-judge-fixture-1"

RUBRIC = """\
You are a listwise relevance judge for an industrial safety precursor-recall system.

You are given one EXPOSURE CUE describing work that is about to be authorised, and a list
of CANDIDATE CUES derived from past incidents. For each candidate you decide one thing:
could the mechanism that produced the past incident act again under the preconditions the
proposed work creates?

The bar is deliberately narrow. A candidate is relevant ONLY if you can name, in the
candidate's own terms and in the exposure's own terms:

  1. a SHARED MECHANISM  - the physical or chemical process by which harm is realised; and
  2. a SHARED PRECONDITION - the state of the plant, the isolation, the atmosphere, the
     ground or the procedure that must hold for that mechanism to act.

If you cannot name both, the verdict is not_relevant. Surface similarity is not relevance:
two records about the same commodity, the same site, the same discipline or the same
equipment vendor are not thereby about the same hazard. Neither is a shared consequence -
"someone could be injured" is true of every record in the corpus and distinguishes none of
them.

Conversely, do not require the equipment to match. A stored-energy release on a mill and a
stored-energy release on a conveyor drive share a mechanism and may share a precondition.

Your justification is read by a supervisor deciding whether to stop work, and it is
retained as evidence. Write it as one or two sentences of plain operational English. Do not
hedge, do not restate the rubric, and do not describe your own reasoning process. Name the
mechanism and name the precondition.

You never decide whether work proceeds. You produce a proposal that deterministic
arithmetic then admits or refuses against a calibrated threshold. Do not attempt to weigh
consequences, do not recommend controls, and do not rank by severity - severity is applied
downstream and is not yours to see.
"""

FACET_DEFINITIONS = """\
Every cue is decomposed into five facets. Compare like with like.

MECHANISM         The process by which harm is realised: gas liberation, stored-energy
                  release, loss of containment, liquefaction, arc, engulfment, inrush.
                  This is the strongest signal and carries the most weight.

PRECONDITION      The state that must hold for the mechanism to act: an interlock in
                  bypass, a shared header without positive isolation, a drained and closed
                  vessel, ground above a trigger level, a dual-fed bay.

CONTROL_FAILURE   The control that was defeated, absent, or defeated-by-design, expressed
                  as what it was supposed to prevent rather than as blame.

RECURRENCE_TEST   A statement, written when the past incident was appraised, of the class
                  of future work under which this incident should be recalled. When a
                  recurrence test is present, it is close to dispositive: it was written by
                  someone who had the whole investigation in front of them.

NARRATIVE         Raw description, retained as a safety net. It is dominated by names,
                  shifts, weather and investigator prose style, so treat agreement here as
                  weak evidence and disagreement here as no evidence at all.

Any facet may carry the value insufficient_evidence. Treat that as absence of information,
never as absence of the hazard, and never let it push a verdict toward not_relevant on its
own.
"""

FEW_SHOTS = """\
EXAMPLE A - relevant.
Exposure: bypassing a low-pH interlock on a barren solution circuit during calibration.
Candidate: hydrogen cyanide liberation when acidic wash water met cyanide-bearing solution
in a shared return header.
Verdict: relevant.
Shared mechanism: liberation of a toxic gas when two incompatible streams meet.
Shared precondition: a shared line without positive isolation while the chemistry interlock
is not protecting.
Justification: the proposed bypass removes the same interlock whose absence allowed the
streams to mix, and the header arrangement is unchanged.

EXAMPLE B - relevant across different equipment.
Exposure: removing liner bolts inside a crusher shell after electrical isolation.
Candidate: a mill rotated under gravity during a reline because isolation covered electrical
supply only.
Verdict: relevant.
Shared mechanism: release of stored gravitational or rotational energy with people inside
the machine envelope.
Shared precondition: an isolation whose scope names electrical supply and is silent on
stored energy.
Justification: the isolation being proposed has the same scope gap, and an unbalanced charge
can rotate the shell with the crew inside.

EXAMPLE C - not relevant despite strong surface similarity.
Exposure: replacing a pressure transmitter on a sulfuric acid unloading line, line drained
and depressurised, verified at the coupling.
Candidate: acid spray at a coupling when residual pressure was released, with no means of
verifying depressurisation.
Verdict: not_relevant.
Shared mechanism: loss of containment of a corrosive liquid - present.
Shared precondition: absent. The exposure specifies verification at the point of breaking
containment, which is precisely the precondition the candidate required.
Justification: same commodity and same equipment, but the precondition the mechanism needs
does not hold under the proposed work.
"""


class CandidateVerdict(BaseModel):
    """One candidate's verdict.  ``extra='forbid'`` mirrors ``additionalProperties: false``."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    candidate_ref: str = Field(min_length=1, max_length=64)
    relevance: Literal["relevant", "not_relevant"]
    shared_mechanism: str = Field(max_length=400)
    shared_precondition: str = Field(max_length=400)
    justification: str = Field(min_length=1, max_length=800)


class RerankVerdict(BaseModel):
    """The listwise answer."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    verdicts: list[CandidateVerdict]


def judge_payload(exposure_ref: str, candidate_refs: list[str]) -> dict[str, object]:
    """A minimal, deterministic user payload for the judge fixtures."""
    return {
        "exposure": {
            "ref": exposure_ref,
            "mechanism": "bypass of a low-pH interlock on a barren solution circuit",
            "precondition": "shared return header with no positive isolation",
        },
        "candidates": [{"ref": ref} for ref in candidate_refs],
    }
