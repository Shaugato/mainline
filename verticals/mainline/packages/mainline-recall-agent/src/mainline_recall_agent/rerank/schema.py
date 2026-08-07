# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
"""The judge's declared output schema, and the citation rule enforced client-side.

Two layers, deliberately, and the split between them is a design decision rather than
belt-and-braces reflex.

**The schema is structural.** ``output_config.format`` is a strict JSON Schema with
``additionalProperties: false``; the same model is re-validated client-side with Pydantic
(recall.md D6). It enforces shape: the fields exist, the enum is closed, the strings are
bounded. A violation here is a malformed answer, and the judge's one repair attempt is the
right response.

**The citation rule is semantic, and it demotes rather than dead-letters.** A verdict that
says ``relevant`` while leaving the mechanism blank or ``insufficient_evidence`` is
well-formed and wrong — it is the "seems related" answer the rubric forbids, dressed in
valid JSON. Dead-lettering the whole listwise call because one candidate of forty was sloppy
would discard thirty-nine good verdicts and degrade the run to A+B for no reason. So
:func:`enforce_citation_rule` demotes that one candidate to ``not_relevant``, records why,
and lets the rest through. The demotion is visible in the returned record and in the feature
vector, so a model that does this often shows up in the ablation instead of hiding in a
retry loop.

``evidence_strength`` is an **ordinal**, not a probability. Asking a model for a numeric
confidence produces a number with no referent; asking it to place a judgement in a three-way
ordinal produces something a human grader would also produce. It feeds
``rerank_confidence`` in the frozen feature vector, where the isotonic calibrator — fitted
on adjudicated labels — is the thing that turns it into a probability. That is the correct
place for an uncalibrated ordinal: an input to calibration, never an output of it.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Final, Literal

from pydantic import BaseModel, ConfigDict, Field

from mainline_recall_agent.rerank.rubric import INSUFFICIENT_EVIDENCE

__all__ = [
    "EVIDENCE_STRENGTH_SCORE",
    "MIN_CITATION_CHARS",
    "CandidateVerdict",
    "DegradedRerank",
    "ListwiseVerdict",
    "RerankOutcome",
    "RerankedCandidate",
    "enforce_citation_rule",
]

Relevance = Literal["relevant", "not_relevant"]
EvidenceStrength = Literal["decisive", "supporting", "weak"]

EVIDENCE_STRENGTH_SCORE: Final[Mapping[str, float]] = {
    "decisive": 1.0,
    "supporting": 0.6,
    "weak": 0.3,
}
"""Ordinal to ``rerank_confidence``. The spacing is a convention, not a measurement; the
calibrator is what gives these numbers meaning, and it is fitted on adjudicated labels."""

MIN_CITATION_CHARS: Final[int] = 12
"""A citation shorter than this is a label, not a mechanism. "gas" is not a mechanism;
"liberation of a toxic gas when incompatible streams meet" is."""


class CandidateVerdict(BaseModel):
    """One candidate's verdict. ``extra='forbid'`` mirrors ``additionalProperties: false``."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    candidate_ref: str = Field(min_length=1, max_length=64)
    relevance: Relevance
    shared_mechanism: str = Field(min_length=1, max_length=400)
    shared_precondition: str = Field(min_length=1, max_length=400)
    justification: str = Field(min_length=1, max_length=800)
    evidence_strength: EvidenceStrength


class ListwiseVerdict(BaseModel):
    """The listwise answer: one verdict per supplied candidate reference."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    verdicts: list[CandidateVerdict]


@dataclass(frozen=True, slots=True)
class RerankedCandidate:
    """A verdict after the citation rule has run, joined back to the real event identity."""

    candidate_ref: str
    doc_id: str
    relevance: Relevance
    shared_mechanism: str
    shared_precondition: str
    justification: str
    evidence_strength: EvidenceStrength
    demoted: bool = False
    demotion_reason: str = ""

    @property
    def cites_mechanism_and_precondition(self) -> bool:
        """True only when both citations are substantive.

        This is the predicate the whole rerank exists to make true for admitted candidates,
        and it is a property rather than a comment so a test can assert it directly.
        """
        return _is_substantive(self.shared_mechanism) and _is_substantive(
            self.shared_precondition
        )

    @property
    def confidence(self) -> float:
        """``rerank_confidence`` for the frozen feature vector."""
        return EVIDENCE_STRENGTH_SCORE[self.evidence_strength]

    @property
    def verdict_code(self) -> float:
        """``rerank_verdict`` for the frozen feature vector: 1.0 relevant, 0.0 not."""
        return 1.0 if self.relevance == "relevant" else 0.0

    def to_json(self) -> dict[str, Any]:
        return {
            "candidate_ref": self.candidate_ref,
            "doc_id": self.doc_id,
            "relevance": self.relevance,
            "shared_mechanism": self.shared_mechanism,
            "shared_precondition": self.shared_precondition,
            "justification": self.justification,
            "evidence_strength": self.evidence_strength,
            "confidence": self.confidence,
            "demoted": self.demoted,
            "demotion_reason": self.demotion_reason,
        }


@dataclass(frozen=True, slots=True)
class RerankOutcome:
    """A completed listwise rerank."""

    reranked: tuple[RerankedCandidate, ...]
    unranked_refs: tuple[str, ...]
    request_digest: str
    prompt_version: str
    prefix_digest: str
    model_id: str
    attempts: int
    usage: Mapping[str, int] = field(default_factory=dict)
    silence_records: tuple[Mapping[str, Any], ...] = ()
    unknown_refs: tuple[str, ...] = ()
    degraded: bool = False
    arms_degraded: bool = False

    @property
    def relevant(self) -> tuple[RerankedCandidate, ...]:
        return tuple(item for item in self.reranked if item.relevance == "relevant")

    def by_ref(self, candidate_ref: str) -> RerankedCandidate:
        for item in self.reranked:
            if item.candidate_ref == candidate_ref:
                return item
        raise KeyError(f"no verdict for candidate reference {candidate_ref!r}")

    def to_json(self) -> dict[str, Any]:
        return {
            "degraded": False,
            "arms_degraded": self.arms_degraded,
            "reranked": [item.to_json() for item in self.reranked],
            "unranked_refs": list(self.unranked_refs),
            "unknown_refs": list(self.unknown_refs),
            "request_digest": self.request_digest,
            "prompt_version": self.prompt_version,
            "prefix_digest": self.prefix_digest,
            "model_id": self.model_id,
            "attempts": self.attempts,
            "usage": dict(self.usage),
            "silence_records": [dict(record) for record in self.silence_records],
        }


@dataclass(frozen=True, slots=True)
class DegradedRerank:
    """The judge leg failed as a whole. Returned, never raised past the reranker.

    The orchestrator completes the run on channels A and B, sets ``recall_run.arms_degraded``
    and writes one silence row per candidate carrying ``silence_reason``. The candidates are
    listed here in full, because *a precursor the model declined to rank must still block the
    merge* — dropping them silently is the failure this type exists to make impossible.
    """

    silence_reason: str
    detail: str
    candidate_refs: tuple[str, ...]
    doc_ids: tuple[str, ...]
    prompt_version: str
    model_id: str
    request_digest: str = ""
    usage: Mapping[str, int] = field(default_factory=dict)
    extra_silence_records: tuple[Mapping[str, Any], ...] = ()
    degraded: bool = True
    arms_degraded: bool = True

    @property
    def reranked(self) -> tuple[RerankedCandidate, ...]:
        """No verdicts. Present so a caller can treat both outcomes uniformly."""
        return ()

    def silence_records(self) -> tuple[dict[str, Any], ...]:
        """One ``mainline_meas.silence_ledger`` payload per candidate the judge never ranked.

        Records carried in ``extra_silence_records`` — candidates that never reached the
        judge because they sat past the rerank depth — keep their own reason and are
        appended verbatim. Collapsing them into the failure reason would claim the model
        refused records it was never shown.
        """
        own = tuple(
            {
                "source": "recall",
                "reason": self.silence_reason,
                "subject_kind": "event",
                "subject_id": doc_id,
                "score": None,
                "threshold": None,
                "arithmetic": {
                    "stage": "listwise_rerank",
                    "detail": self.detail,
                    "prompt_version": self.prompt_version,
                    "model_id": self.model_id,
                    "request_digest": self.request_digest,
                    "consequence": "the run completes on channels A and B and still blocks; "
                    "arms_degraded is set on the recall run",
                },
            }
            for doc_id in self.doc_ids
        )
        return own + tuple(dict(record) for record in self.extra_silence_records)

    def to_json(self) -> dict[str, Any]:
        return {
            "degraded": True,
            "arms_degraded": self.arms_degraded,
            "silence_reason": self.silence_reason,
            "detail": self.detail,
            "candidate_refs": list(self.candidate_refs),
            "doc_ids": list(self.doc_ids),
            "prompt_version": self.prompt_version,
            "model_id": self.model_id,
            "request_digest": self.request_digest,
            "usage": dict(self.usage),
            "silence_records": [dict(record) for record in self.silence_records()],
        }


def _is_substantive(text: str) -> bool:
    stripped = text.strip()
    if not stripped:
        return False
    if stripped.lower() == INSUFFICIENT_EVIDENCE:
        return False
    return len(stripped) >= MIN_CITATION_CHARS


def enforce_citation_rule(
    verdicts: Sequence[CandidateVerdict], *, ref_to_doc: Mapping[str, str]
) -> tuple[tuple[RerankedCandidate, ...], tuple[str, ...]]:
    """Join verdicts to their events, and demote any ``relevant`` that fails to cite.

    Args:
        verdicts: What the model returned, already schema-valid.
        ref_to_doc: The opaque candidate reference to event identity mapping built by
            :mod:`mainline_recall_agent.rerank.payload`.

    Returns:
        The reranked candidates in the order supplied by the model, and the tuple of
        references the model returned that name no candidate we sent. An unknown reference
        is dropped rather than trusted: it is either a hallucinated identity or an injected
        one, and in both cases it names no event we can attach a check to.
    """
    out: list[RerankedCandidate] = []
    unknown: list[str] = []
    seen: set[str] = set()
    for verdict in verdicts:
        doc_id = ref_to_doc.get(verdict.candidate_ref)
        if doc_id is None:
            unknown.append(verdict.candidate_ref)
            continue
        if verdict.candidate_ref in seen:
            # A second verdict for one reference is not a merge conflict to resolve, it is a
            # malformed answer. The first is kept and the duplicate reported as unknown, so
            # nothing about the outcome depends on which one the model happened to emit last.
            unknown.append(verdict.candidate_ref)
            continue
        seen.add(verdict.candidate_ref)

        relevance: Relevance = verdict.relevance
        demoted = False
        reason = ""
        if relevance == "relevant" and not (
            _is_substantive(verdict.shared_mechanism)
            and _is_substantive(verdict.shared_precondition)
        ):
            relevance = "not_relevant"
            demoted = True
            reason = (
                "relevant verdict without a substantive shared mechanism and shared "
                "precondition; the rubric admits no verdict that cannot cite both"
            )
        out.append(
            RerankedCandidate(
                candidate_ref=verdict.candidate_ref,
                doc_id=doc_id,
                relevance=relevance,
                shared_mechanism=verdict.shared_mechanism,
                shared_precondition=verdict.shared_precondition,
                justification=verdict.justification,
                evidence_strength=verdict.evidence_strength,
                demoted=demoted,
                demotion_reason=reason,
            )
        )
    return tuple(out), tuple(unknown)
