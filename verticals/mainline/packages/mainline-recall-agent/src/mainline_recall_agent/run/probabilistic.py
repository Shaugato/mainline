# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
"""Channels C and D, and everything between them and a calibrated probability.

::

    C (ANN arms) + C' (coarse sweep) + D (BM25)
        -> RRF                     rank-based, so no cross-distribution normalisation
        -> MMR                     siblings suppressed, attached as also_matched, ledgered
        -> listwise rerank         in-region Claude, mechanism-and-precondition citation rule
        -> feature vector          the frozen spec; severity has no slot in it
        -> isotonic calibration    p_relevant, the only number a human is shown
        -> (admission happens in the orchestrator, over A + B + C + D together)

**Every failure in this module is a degradation, never a refusal.** Bedrock throttled, a model
refusal, a guardrail block, a dead-lettered structured output: each raises
:class:`~mainline_recall_agent.run.errors.ProbabilisticChannelUnavailable`, the orchestrator
catches it, records ``arms_degraded = true``, writes the silence rows, and completes on
channels A and B — which still block the merge. The one thing that must never happen is a
probabilistic failure turning into a permit with no obligations.

Retrieval itself is behind two protocols (:class:`ArmRunner`, :class:`LexicalRunner`) rather
than inlined. The arm generator and the BM25 statement builder are owned by other workers in
this domain and already carry their own ``EXPLAIN`` assertions; re-implementing either here
would create a second thing to keep honest. What this module owns is the *composition*, and
the composition is where the arithmetic that reaches a supervisor is decided.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Final, Protocol
from uuid import UUID

from trappoint_recall.fusion.calibration import IsotonicCalibrator
from trappoint_recall.fusion.featurespec import (
    FEATURE_NAMES,
    FeatureVector,
    build_features,
    raw_score,
)
from trappoint_recall.fusion.mmr import (
    DEFAULT_LAMBDA,
    DEFAULT_REDUNDANCY_THRESHOLD,
    MmrCandidate,
    maximal_marginal_relevance,
)
from trappoint_recall.fusion.rrf import RRF_K, ArmRanking, reciprocal_rank_fusion
from trappoint_recall.horizon.certificate import ArmCoverage
from trappoint_recall.horizon.fingerprint import PrefixTree

from mainline_recall_agent.providers.errors import ProviderError
from mainline_recall_agent.rerank.schema import DegradedRerank, RerankOutcome
from mainline_recall_agent.run.errors import ProbabilisticChannelUnavailable

__all__ = [
    "DEFAULT_FEATURE_WEIGHTS",
    "FACET_VOCABULARY",
    "ArmRunner",
    "ChannelCOutcome",
    "DedupedCandidate",
    "LexicalRunner",
    "ProbabilisticOutcome",
    "RetrievedHit",
    "ScoredCandidate",
    "SilenceRow",
    "run_probabilistic",
]

#: The facet one-hot ordering. Frozen with the feature spec: reordering it silently
#: reinterprets every stored feature vector and every fitted calibrator.
FACET_VOCABULARY: Final[tuple[str, ...]] = (
    "mechanism",
    "precondition",
    "control_failure",
    "recurrence_test",
    "narrative",
)

#: **Preliminary.** These are the weights that collapse the frozen feature vector to the
#: scalar the isotonic calibrator is fitted on. They are shipped as a starting point and are
#: overridden by ``recall_policy.arms['feature_weights']`` whenever the policy carries them —
#: which it will, because a weight vector that was not fitted alongside the calibrator it
#: feeds is a number with no provenance. The calibrator is what makes ``p_relevant`` mean
#: something; these decide only the order in which candidates arrive at it.
DEFAULT_FEATURE_WEIGHTS: Final[Mapping[str, float]] = {
    "rrf_score": 1.0,
    "best_arm_rank": -0.01,
    "scope_level": 0.08,
    "facet_onehot_0": 0.05,
    "facet_onehot_1": 0.03,
    "facet_onehot_2": 0.06,
    "facet_onehot_3": 0.10,
    "facet_onehot_4": 0.00,
    "rerank_verdict": 0.45,
    "rerank_confidence": 0.30,
    "control_class_overlap": 0.25,
    "asset_class_match": 0.04,
    "channel_mask": 0.01,
    "coarse_only": -0.08,
}

#: Channel bit positions, matching ``featurespec``'s documented mask (C=1, C_sweep=2, D=4).
_CHANNEL_BIT: Final[Mapping[str, int]] = {"C": 1, "C_sweep": 2, "D": 4}


@dataclass(frozen=True, slots=True)
class RetrievedHit:
    """One hit from one arm of one probabilistic channel."""

    event_id: UUID
    channel: str
    arm_id: str
    rank: int
    facet: str
    scope_level: int
    weight: float = 1.0
    embedding: tuple[float, ...] = ()

    def __post_init__(self) -> None:
        """Refuse a hit that could not have come from an arm."""
        if self.channel not in _CHANNEL_BIT:
            raise ProbabilisticChannelUnavailable(
                f"{self.arm_id}: unknown probabilistic channel {self.channel!r}",
                silence_reason="unreachable",
            )
        if self.rank < 1:
            raise ProbabilisticChannelUnavailable(
                f"{self.arm_id}: rank is 1-based, got {self.rank}",
                silence_reason="unreachable",
            )


@dataclass(frozen=True, slots=True)
class ChannelCOutcome:
    """What the ANN arms did, as observed. Feeds the CUE HORIZON certificate directly."""

    hits: tuple[RetrievedHit, ...]
    arm_coverage: tuple[ArmCoverage, ...]
    prefix_trees: tuple[PrefixTree, ...]
    index_generation_at_start: str
    index_generation_at_end: str
    index_plan_digest: bytes
    arm_set_digest: str
    sweep_ran: bool = False
    cap_exceeded: Mapping[str, Any] | None = None


class ArmRunner(Protocol):
    """Runs the prefix-constrained ANN arm set and reports what the index actually did."""

    def run(self) -> ChannelCOutcome:
        """Execute every arm and the coarse sweep, returning hits and coverage evidence."""
        ...


class LexicalRunner(Protocol):
    """Runs channel D — explicit BM25 over identifier-preserving tokens."""

    def run(self) -> Sequence[RetrievedHit]:
        """Execute the BM25 statement and return its ranked hits."""
        ...


class Reranker(Protocol):
    """The listwise judge. Returns an outcome or a degraded marker; may also raise."""

    def rerank(self, doc_ids: Sequence[str]) -> RerankOutcome | DegradedRerank:
        """Judge the shortlist under the mechanism-and-precondition citation rule."""
        ...


@dataclass(frozen=True, slots=True)
class SilenceRow:
    """A ``mainline_meas.silence_ledger`` row, before it is bound to a run."""

    subject_kind: str
    subject_id: UUID
    reason: str
    severity: int
    score: float | None
    threshold: float | None
    arithmetic: Mapping[str, Any]
    source: str = "recall"


@dataclass(frozen=True, slots=True)
class DedupedCandidate:
    """An MMR-suppressed sibling. Counted in the conserved partition as ``deduped``."""

    event_id: UUID
    representative_id: UUID
    similarity: float
    relevance: float


@dataclass(frozen=True, slots=True)
class ScoredCandidate:
    """A probabilistic candidate carrying its calibrated probability and its arithmetic."""

    event_id: UUID
    p_relevant: float
    rank: int
    channels: tuple[str, ...]
    features: FeatureVector
    raw: float
    evidence_summary: str
    also_matched: tuple[UUID, ...] = ()
    coarse_only: bool = False
    facet: str = "narrative"
    scope_level: int = 1


@dataclass(frozen=True, slots=True)
class ProbabilisticOutcome:
    """Everything channels C and D produced, including the reasons they produced less."""

    scored: tuple[ScoredCandidate, ...]
    deduped: tuple[DedupedCandidate, ...]
    silence: tuple[SilenceRow, ...]
    coverage: ChannelCOutcome
    rerank_degraded: bool = False
    notes: tuple[str, ...] = field(default_factory=tuple)


def _rankings(hits: Sequence[RetrievedHit]) -> tuple[ArmRanking, ...]:
    """Group hits into one :class:`ArmRanking` per arm, in rank order."""
    by_arm: dict[tuple[str, str, float], list[RetrievedHit]] = {}
    for hit in hits:
        by_arm.setdefault((hit.arm_id, hit.channel, hit.weight), []).append(hit)
    rankings: list[ArmRanking] = []
    for (arm_id, channel, weight), arm_hits in sorted(by_arm.items()):
        ordered = sorted(arm_hits, key=lambda hit: (hit.rank, str(hit.event_id)))
        rankings.append(
            ArmRanking(
                arm_id=arm_id,
                channel=channel,
                weight=weight,
                doc_ids=tuple(str(hit.event_id) for hit in ordered),
            )
        )
    return tuple(rankings)


def _channel_mask(channels: Sequence[str]) -> int:
    """Bitwise OR over the channels that returned a candidate."""
    mask = 0
    for channel in channels:
        mask |= _CHANNEL_BIT.get(channel, 0)
    return mask


def _weights(policy_arms: Mapping[str, Any]) -> Mapping[str, float]:
    """Feature weights from the policy, falling back to the documented preliminary set."""
    declared = policy_arms.get("feature_weights")
    if not isinstance(declared, Mapping):
        return DEFAULT_FEATURE_WEIGHTS
    weights = dict(DEFAULT_FEATURE_WEIGHTS)
    for name, value in declared.items():
        if name in FEATURE_NAMES:
            weights[name] = float(value)
    return weights


def run_probabilistic(  # noqa: PLR0912, PLR0915
    # PLR0912/PLR0915: this is the fusion pipeline written as one straight line — arms, sweep,
    # lexical, RRF, MMR, rerank, feature assembly, calibration — and every branch in it is a
    # degradation the caller must be able to absorb without losing the stage it happened at.
    # Cutting it into stage functions would move the branch count into an orchestration layer
    # that had to thread the same eleven locals through it, which is more surface, not less.
    *,
    arm_runner: ArmRunner,
    lexical_runner: LexicalRunner,
    reranker: Reranker | None,
    calibrator: IsotonicCalibrator,
    policy_arms: Mapping[str, Any],
    permit_control_classes: frozenset[str],
    control_class_resolver: Callable[[Sequence[UUID]], Mapping[UUID, frozenset[str]]],
    asset_match_resolver: Callable[[Sequence[UUID]], Mapping[UUID, bool]],
    rerank_top_k: int = 40,
    mmr_lambda: float = DEFAULT_LAMBDA,
    redundancy_threshold: float = DEFAULT_REDUNDANCY_THRESHOLD,
) -> ProbabilisticOutcome:
    """Run C, C', D and the fusion stack, or raise a degradation the caller absorbs.

    Raises:
        ProbabilisticChannelUnavailable: any failure of the ANN arms, the lexical channel or
            the judge. The caller records ``arms_degraded`` and completes on A + B.
    """
    try:
        coverage = arm_runner.run()
    except ProviderError as exc:
        raise ProbabilisticChannelUnavailable(
            f"the ANN arms could not run: {exc}",
            silence_reason=getattr(exc, "silence_reason", None) or "unreachable",
        ) from exc
    except (OSError, TimeoutError) as exc:
        raise ProbabilisticChannelUnavailable(
            f"the ANN arms could not reach the cluster: {exc}", silence_reason="unreachable"
        ) from exc

    try:
        lexical_hits = tuple(lexical_runner.run())
    except (OSError, TimeoutError) as exc:
        raise ProbabilisticChannelUnavailable(
            f"channel D (BM25) could not reach the cluster: {exc}",
            silence_reason="unreachable",
        ) from exc

    hits = (*coverage.hits, *lexical_hits)
    silence: list[SilenceRow] = []
    notes: list[str] = []

    if coverage.cap_exceeded is not None:
        notes.append(
            "the arm set exceeded its cap and was truncated; see the cap_exceeded arithmetic"
        )

    if not hits:
        return ProbabilisticOutcome(
            scored=(),
            deduped=(),
            silence=(),
            coverage=coverage,
            notes=("no probabilistic channel returned a candidate",),
        )

    fused = reciprocal_rank_fusion(_rankings(hits), k=RRF_K)

    # ── MMR. Siblings are suppressed as representatives' `also_matched`, never dropped. ──
    embeddings: dict[str, tuple[float, ...]] = {}
    facets: dict[str, str] = {}
    levels: dict[str, int] = {}
    channels_of: dict[str, set[str]] = {}
    for hit in hits:
        key = str(hit.event_id)
        channels_of.setdefault(key, set()).add(hit.channel)
        if hit.embedding and key not in embeddings:
            embeddings[key] = hit.embedding
        facets.setdefault(key, hit.facet)
        levels[key] = max(levels.get(key, 0), hit.scope_level)

    width = max((len(vector) for vector in embeddings.values()), default=0)
    mmr_input = [
        MmrCandidate(
            doc_id=candidate.doc_id,
            relevance=candidate.rrf_score,
            embedding=embeddings.get(candidate.doc_id, (0.0,) * width) or (0.0,),
        )
        for candidate in fused
    ]
    selection = maximal_marginal_relevance(
        mmr_input,
        lambda_value=mmr_lambda,
        redundancy_threshold=redundancy_threshold,
    )

    deduped = tuple(
        DedupedCandidate(
            event_id=UUID(sibling.doc_id),
            representative_id=UUID(sibling.representative_id),
            similarity=sibling.similarity,
            relevance=sibling.relevance,
        )
        for sibling in selection.suppressed
    )
    for sibling in selection.suppressed:
        silence.append(
            SilenceRow(
                subject_kind="event",
                subject_id=UUID(sibling.doc_id),
                reason="dedup_sibling",
                severity=0,
                score=sibling.relevance,
                threshold=redundancy_threshold,
                arithmetic={
                    "representative": sibling.representative_id,
                    "cosine": sibling.similarity,
                    "lambda": mmr_lambda,
                    "redundancy_threshold": redundancy_threshold,
                    "note": (
                        "suppressed as a near-duplicate of its representative and attached "
                        "to it as also_matched; visible, not hidden"
                    ),
                },
                source="dedup",
            )
        )

    # ── Listwise rerank. Any failure here degrades; it never stops the run. ──
    shortlist = [rep.doc_id for rep in selection.representatives[:rerank_top_k]]
    rerank_by_doc: dict[str, tuple[float, float, str]] = {}
    rerank_degraded = False
    if reranker is not None and shortlist:
        try:
            verdict = reranker.rerank(shortlist)
        except ProviderError as exc:
            raise ProbabilisticChannelUnavailable(
                f"the listwise judge did not return a verdict: {exc}",
                silence_reason=getattr(exc, "silence_reason", None) or "model_refusal",
            ) from exc
        if isinstance(verdict, DegradedRerank):
            rerank_degraded = True
            notes.append(f"listwise rerank degraded: {verdict.detail}")
            for record in verdict.silence_records():
                silence.append(
                    SilenceRow(
                        subject_kind="event",
                        subject_id=UUID(str(record["subject_id"])),
                        reason=str(record.get("reason", verdict.silence_reason)),
                        severity=int(record.get("severity", 0)),
                        score=None,
                        threshold=None,
                        arithmetic=dict(record.get("arithmetic", {})) or dict(record),
                    )
                )
        else:
            for reranked in verdict.reranked:
                # `verdict_code` and `confidence` are PROPERTIES on RerankedCandidate, not
                # methods. Reading them as attributes is not a style choice: calling them
                # would raise `TypeError: 'float' object is not callable` at the exact moment
                # a judge verdict arrives, and the caller's `except ProviderError` would not
                # catch it — a TypeError here would abort the run instead of degrading it,
                # turning a healthy rerank into a permit with no obligations.
                rerank_by_doc[reranked.doc_id] = (
                    reranked.verdict_code,
                    reranked.confidence,
                    reranked.justification,
                )
            # `abstention`, NOT `record`. The degraded branch above binds `record` to the
            # `dict[str, Any]` payloads `DegradedRerank.silence_records()` BUILDS; this
            # branch reads the `Mapping[str, Any]` payloads `RerankVerdict.silence_records`
            # OWNS. Python scopes both to the function, so one name asserted the two were
            # the same type, and they are not — the healthy verdict's records are read-only
            # by design (a caller that mutated one would be editing the judge's own answer
            # after the fact). Two payload shapes, two names.
            for abstention in verdict.silence_records:
                silence.append(
                    SilenceRow(
                        subject_kind="event",
                        subject_id=UUID(str(abstention["subject_id"])),
                        reason=str(abstention.get("reason", "abstained")),
                        severity=int(abstention.get("severity", 0)),
                        score=None,
                        threshold=None,
                        arithmetic=dict(abstention.get("arithmetic", {})) or dict(abstention),
                    )
                )

    # ── Features, raw score, calibration. p_relevant is the only number a human sees. ──
    weights = _weights(policy_arms)
    scored: list[ScoredCandidate] = []
    by_doc = {candidate.doc_id: candidate for candidate in fused}
    representative_ids = [UUID(rep.doc_id) for rep in selection.representatives]
    event_control_classes = control_class_resolver(representative_ids)
    event_asset_match = asset_match_resolver(representative_ids)
    for position, representative in enumerate(selection.representatives, start=1):
        doc_id = representative.doc_id
        fused_candidate = by_doc[doc_id]
        event_id = UUID(doc_id)
        channels = tuple(sorted(channels_of.get(doc_id, set())))
        coarse_only = channels == ("C_sweep",)
        verdict_code, confidence, justification = rerank_by_doc.get(doc_id, (-1.0, 0.0, ""))
        event_classes = event_control_classes.get(event_id, frozenset())
        union = permit_control_classes | event_classes
        overlap = len(permit_control_classes & event_classes) / len(union) if union else 0.0
        vector = build_features(
            rrf_score=fused_candidate.rrf_score,
            best_arm_rank=fused_candidate.best_arm_rank,
            scope_level=levels.get(doc_id, 1),
            facet=facets.get(doc_id, "narrative"),
            facet_vocabulary=FACET_VOCABULARY,
            rerank_verdict=verdict_code,
            rerank_confidence=confidence,
            control_class_overlap=overlap,
            asset_class_match=event_asset_match.get(event_id, False),
            channel_mask=_channel_mask(channels),
            coarse_only=coarse_only,
        )
        raw = raw_score(vector, weights)
        p_relevant = calibrator.predict_one(raw)
        scored.append(
            ScoredCandidate(
                event_id=event_id,
                p_relevant=p_relevant,
                rank=position,
                channels=channels,
                features=vector,
                raw=raw,
                evidence_summary=justification,
                also_matched=tuple(UUID(sibling) for sibling in selection.also_matched_for(doc_id)),
                coarse_only=coarse_only,
                facet=facets.get(doc_id, "narrative"),
                scope_level=levels.get(doc_id, 1),
            )
        )

    return ProbabilisticOutcome(
        scored=tuple(scored),
        deduped=deduped,
        silence=tuple(silence),
        coverage=coverage,
        rerank_degraded=rerank_degraded,
        notes=tuple(notes),
    )
