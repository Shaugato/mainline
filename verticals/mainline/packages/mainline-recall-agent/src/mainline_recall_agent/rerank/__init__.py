# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
"""The listwise rerank: the one stage of recall admission that needs a model.

Everything else in the admission arithmetic is a pure function in
``trappoint_recall.fusion`` under Apache-2.0. This package is the exception, and it is here —
in the FSL vertical — for two reasons that are the same reason: it needs Claude on the
in-region ``au.*`` inference profile, and it carries MAINLINE's safety vocabulary in a rubric
that is an interface rather than a prompt.

The order of operations::

    fused + deduplicated candidates
        -> payload.take_top_k / build_payload    (top-40, opaque refs, quarantined span)
        -> rubric.build_rerank_prefix            (byte-frozen, cache breakpoint at the end)
        -> providers.JudgeProvider               (structured output, one repair, then dead letter)
        -> schema.enforce_citation_rule          (a relevant verdict must cite, or be demoted)
        -> evidence.evidence_summary             (the text blocking_check carries)

and, when the judge leg fails as a whole, ``schema.DegradedRerank`` — returned rather than
raised, so the orchestrator completes on channels A and B, sets ``arms_degraded`` and still
refuses the merge.
"""

from __future__ import annotations

from mainline_recall_agent.rerank.evidence import (
    MAX_EVIDENCE_CHARS,
    EvidenceRefused,
    evidence_summary,
)
from mainline_recall_agent.rerank.listwise import (
    OVERFLOW_SILENCE_REASON,
    ListwiseReranker,
    RerankJudge,
)
from mainline_recall_agent.rerank.payload import (
    MAX_FACET_CHARS,
    TOP_K_RERANK,
    ExposureCue,
    RerankCandidate,
    build_payload,
    candidate_ref_for,
    take_top_k,
)
from mainline_recall_agent.rerank.rubric import (
    FACET_DEFINITIONS,
    FEW_SHOTS,
    INSUFFICIENT_EVIDENCE,
    PROMPT_VERSION,
    RUBRIC,
    build_rerank_prefix,
    rubric_sha256,
)
from mainline_recall_agent.rerank.schema import (
    EVIDENCE_STRENGTH_SCORE,
    CandidateVerdict,
    DegradedRerank,
    ListwiseVerdict,
    RerankedCandidate,
    RerankOutcome,
    enforce_citation_rule,
)

__all__ = [
    "EVIDENCE_STRENGTH_SCORE",
    "FACET_DEFINITIONS",
    "FEW_SHOTS",
    "INSUFFICIENT_EVIDENCE",
    "MAX_EVIDENCE_CHARS",
    "MAX_FACET_CHARS",
    "OVERFLOW_SILENCE_REASON",
    "PROMPT_VERSION",
    "RUBRIC",
    "TOP_K_RERANK",
    "CandidateVerdict",
    "DegradedRerank",
    "EvidenceRefused",
    "ExposureCue",
    "ListwiseReranker",
    "ListwiseVerdict",
    "RerankCandidate",
    "RerankJudge",
    "RerankOutcome",
    "RerankedCandidate",
    "build_payload",
    "build_rerank_prefix",
    "candidate_ref_for",
    "enforce_citation_rule",
    "evidence_summary",
    "rubric_sha256",
    "take_top_k",
]
