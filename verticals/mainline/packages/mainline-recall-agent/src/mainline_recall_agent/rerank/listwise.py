# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
"""The listwise judge leg: one call, one validated answer, or a degraded record.

The reranker's contract with the orchestrator is the important part of this module, and it
is a **return type, not an exception**. When the judge leg fails as a whole — a refusal on a
cyanide narrative, a guardrail block, a throttle, two schema violations in a row — this
function returns a :class:`~mainline_recall_agent.rerank.schema.DegradedRerank` listing every
candidate the model never ranked. The orchestrator then completes the run on channels A and
B, sets ``recall_run.arms_degraded``, writes one silence row per unranked candidate, and
**still blocks the merge**.

That asymmetry is the spine of the product. Channels A and B bypass the model entirely, so a
model outage is a degradation in the *quality of the explanation*, never in whether the gate
holds. If this function raised instead of returning, the natural caller would end up with an
empty candidate list and a permit that merged — the exact failure the architecture spends a
chapter preventing. So the failure has a type, and the type carries the candidates.

Defects are different and are re-raised. ``ProviderError`` subclasses declare a
``silence_reason`` when they are facts about the world (a refusal, a truncation, a dead
letter, an unavailable provider) and leave it ``None`` when they are bugs in our code (a
malformed prefix, a tampered cassette, a bad call). Only the former become degradation; a
bug that quietly became "the model declined" would be a silent memory gap wearing a ledger
row.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, Final, Protocol

from mainline_recall_agent.providers.errors import ProviderError
from mainline_recall_agent.providers.system_blocks import SystemPrefix, build_user_turn
from mainline_recall_agent.providers.types import JudgeResult, Usage
from mainline_recall_agent.rerank.payload import (
    TOP_K_RERANK,
    ExposureCue,
    RerankCandidate,
    build_payload,
    candidate_ref_for,
    take_top_k,
)
from mainline_recall_agent.rerank.rubric import PROMPT_VERSION, build_rerank_prefix
from mainline_recall_agent.rerank.schema import (
    DegradedRerank,
    ListwiseVerdict,
    RerankOutcome,
    enforce_citation_rule,
)

__all__ = ["OVERFLOW_SILENCE_REASON", "ListwiseReranker", "RerankJudge"]

OVERFLOW_SILENCE_REASON: Final[str] = "cap_exceeded"
"""Candidates past the top-40 rerank depth. Not judged, but not forgotten either."""

_UNRANKED_SILENCE_REASON: Final[str] = "abstained"
"""A candidate the model was shown and returned no verdict for. Distinct from a refusal:
the call succeeded and this one record fell out of it, which is a fact about the answer."""


class RerankJudge(Protocol):
    """The slice of ``JudgeProvider`` this module uses.

    ``judge_detailed`` is optional; when a provider offers it the request digest, the token
    usage and the attempt count reach the record without a second call. When it does not,
    the reranker falls back to ``judge`` and records what it can.
    """

    def judge(
        self,
        system_blocks: Sequence[Any],
        user_payload: dict[str, Any],
        schema: type[ListwiseVerdict],
    ) -> ListwiseVerdict: ...


class ListwiseReranker:
    """Rerank the top-K fused candidates with the in-region Claude listwise judge."""

    def __init__(
        self,
        *,
        judge: Any,
        prompt_version: str = PROMPT_VERSION,
        top_k: int = TOP_K_RERANK,
        prefix: SystemPrefix | None = None,
    ) -> None:
        self._judge = judge
        self._prompt_version = prompt_version
        self._top_k = top_k
        self._prefix = prefix or build_rerank_prefix(prompt_version)

    @property
    def prefix(self) -> SystemPrefix:
        return self._prefix

    @property
    def prompt_version(self) -> str:
        return self._prompt_version

    @property
    def top_k(self) -> int:
        return self._top_k

    def _model_id(self) -> str:
        resolved = getattr(self._judge, "resolved_model", None)
        return str(getattr(resolved, "profile_id", "")) if resolved is not None else ""

    def _usage(self) -> dict[str, int]:
        usage = getattr(self._judge, "last_usage", None)
        if isinstance(usage, Usage):
            return dict(usage.model_dump())
        return {}

    def rerank(
        self, exposure: ExposureCue, candidates: Sequence[RerankCandidate]
    ) -> RerankOutcome | DegradedRerank:
        """Judge ``candidates`` against ``exposure``.

        Args:
            exposure: The permit-side cue, in the same facets as the event side.
            candidates: The fused, deduplicated candidate set. Only the top
                :attr:`top_k` by fused rank are judged; the overflow is returned in the
                outcome's silence records as ``cap_exceeded``.

        Returns:
            A :class:`RerankOutcome` on success, or a :class:`DegradedRerank` when the judge
            leg failed as a whole. Never raises for a model-side failure.

        Raises:
            ProviderError: for defects — a malformed payload, a contract violation, a
                tampered cassette. These are bugs in our code and must crash the run rather
                than be recorded as the model's silence.
        """
        kept, overflow = take_top_k(candidates, self._top_k)
        payload, ref_to_doc = build_payload(exposure, kept)
        sent_refs = tuple(ref_to_doc)

        overflow_records: list[dict[str, Any]] = [
            {
                "source": "recall",
                "reason": OVERFLOW_SILENCE_REASON,
                "subject_kind": "event",
                "subject_id": candidate.doc_id,
                "score": None,
                "threshold": None,
                "arithmetic": {
                    "stage": "listwise_rerank_depth",
                    "rerank_depth": self._top_k,
                    "fused_rank": candidate.fused_rank,
                    "rule": "only the top-K fused candidates are judged; the remainder are "
                    "recorded rather than ranked",
                },
            }
            for candidate in overflow
        ]

        try:
            result = self._call(payload)
        except ProviderError as exc:
            reason = exc.silence_reason
            if reason is None:
                # A defect in our own code. Never silence.
                raise
            return DegradedRerank(
                silence_reason=reason,
                detail=str(exc),
                candidate_refs=sent_refs,
                doc_ids=tuple(ref_to_doc[ref] for ref in sent_refs),
                prompt_version=self._prompt_version,
                model_id=self._model_id(),
                request_digest=str(exc.context.get("request_digest", "")),
                usage=self._usage(),
                extra_silence_records=tuple(overflow_records),
            )

        verdict, request_digest, attempts = result
        reranked, unknown = enforce_citation_rule(verdict.verdicts, ref_to_doc=ref_to_doc)
        ranked_refs = {item.candidate_ref for item in reranked}
        unranked = tuple(ref for ref in sent_refs if ref not in ranked_refs)

        records: list[Mapping[str, Any]] = list(overflow_records)
        records.extend(
            {
                "source": "recall",
                "reason": _UNRANKED_SILENCE_REASON,
                "subject_kind": "event",
                "subject_id": ref_to_doc[ref],
                "score": None,
                "threshold": None,
                "arithmetic": {
                    "stage": "listwise_rerank",
                    "candidate_ref": ref,
                    "rule": "the candidate was presented to the judge and no verdict came "
                    "back for it; a precursor the model declined to rank is recorded, never "
                    "dropped",
                    "prompt_version": self._prompt_version,
                    "request_digest": request_digest,
                },
            }
            for ref in unranked
        )

        return RerankOutcome(
            reranked=reranked,
            unranked_refs=unranked,
            unknown_refs=unknown,
            request_digest=request_digest,
            prompt_version=self._prompt_version,
            prefix_digest=self._prefix.prefix_digest(),
            model_id=self._model_id(),
            attempts=attempts,
            usage=self._usage(),
            silence_records=tuple(records),
            # Overflow past the rerank depth is designed behaviour and does not degrade the
            # run. A candidate the judge was *shown* and returned nothing for does: the
            # answer is incomplete, and the record has to say so.
            arms_degraded=bool(unranked),
        )

    def _call(self, payload: dict[str, Any]) -> tuple[ListwiseVerdict, str, int]:
        detailed = getattr(self._judge, "judge_detailed", None)
        if callable(detailed):
            result: JudgeResult = detailed(self._prefix, payload, ListwiseVerdict)
            value = result.value
            if not isinstance(value, ListwiseVerdict):  # pragma: no cover - provider contract
                raise ProviderError(
                    "the judge returned a validated model of the wrong type",
                    got=type(value).__name__,
                )
            return value, result.request_digest, result.attempts
        verdict = self._judge.judge(self._prefix, payload, ListwiseVerdict)
        return verdict, "", 1

    def expected_refs(self, count: int) -> tuple[str, ...]:
        """Return the references a payload of ``count`` candidates will use, for fixtures."""
        return tuple(candidate_ref_for(position) for position in range(1, count + 1))


def build_user_turn_for(payload: dict[str, Any]) -> dict[str, Any]:
    """Expose the quarantined user turn, for cassette generators and prompt-shape tests."""
    return build_user_turn(payload)
