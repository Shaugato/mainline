# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
"""The run loop: from a permit in draft to an integer on ``permit.open_blocking``.

::

    load + gate the policy        MI18 anchored, M5 THYMOGATE clean, or the run refuses
      -> channel A                deterministic ancestry, GIN-confirmed, uncapped
      -> channel B                bonded severity-5, uncapped
      -> channels C, C', D        [ any failure here degrades; it never stops the run ]
      -> fusion, rerank, calibration
      -> Severity-Graded Admission + the probabilistic cap
      -> L3 conservation, in code, naming the candidate that went missing
      -> CUE HORIZON certificate  -> PER receipt  (UNDETERMINED blocks the exhaustion claim)
      -> ONE transaction: recall_run, recall_candidate, recall_certificate, silence_*
      -> POST the candidate set to the kernel     [ this agent never writes blocking_check ]

**Degraded mode is the spine.** Bedrock throttled, a model refusal, a guardrail block: the
run completes on A + B, records ``arms_degraded = true``, writes the silence rows, and still
leaves ``open_blocking > 0``. Three independent injections are asserted in
``tests/integration/recall_run/test_degraded_modes.py``, because a degradation path that is
only reasoned about is a degradation path that has never run.

Ordering that is not arbitrary
------------------------------
The policy gate fires **first**, before any retrieval and before any model call. A run that
spent twenty seconds reranking and then discovered its policy was never anchored has burned a
budget to produce a refusal that reads like a bug.

Conservation is enforced **before** the transaction opens, so the failure names the event id
rather than an integer. The database's ``candidates_conserved`` CHECK still stands behind it
and still refuses — this is defence in depth, not a replacement.

The kernel POST happens **after** the commit. If the POST fails, the measurement record
survives with its receipt and its silence rows, and the permit simply has no obligations from
this run — which the merge gate treats as fail-closed on a missing projection (MI22). The
reverse order would allow an obligation to exist with no recall record behind it, which is
the one asymmetry a plaintiff would find first.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Final
from uuid import UUID, uuid4

from trappoint_recall.fusion.calibration import CalibrationRefused, IsotonicCalibrator
from trappoint_recall.fusion.sga import (
    BLOCKING_CAP_PROBABILISTIC,
    AdmissionCandidate,
    AdmissionRefused,
    TauTable,
    admit,
)
from trappoint_recall.horizon.certificate import (
    CoverageCertificate,
    CoverageObservation,
    certify,
)
from trappoint_recall.horizon.fingerprint import IndexFingerprintInput
from trappoint_recall.per.leaf import CandidateScore
from trappoint_recall.per.receipt import SilenceReceipt, build_receipt
from trappoint_recall.run.contract import (
    Candidate,
    CandidateSet,
    Counts,
    ExposureCueRef,
)

from mainline_recall_agent.run.channels import (
    AncestryHit,
    BondedHit,
    CitedClause,
    channel_a,
    channel_b,
    cited_clauses,
)
from mainline_recall_agent.run.conservation import CandidateRow, enforce_conservation
from mainline_recall_agent.run.errors import (
    ProbabilisticChannelUnavailable,
    RunRefused,
    UnmodelledSqlstate,
)
from mainline_recall_agent.run.kernel import MaterialiseClient, MaterialiseResult
from mainline_recall_agent.run.persist import RunRecord, insert_run
from mainline_recall_agent.run.policy import load_policy, load_thymogate
from mainline_recall_agent.run.probabilistic import (
    ArmRunner,
    ChannelCOutcome,
    LexicalRunner,
    ProbabilisticOutcome,
    Reranker,
    ScoredCandidate,
    SilenceRow,
    run_probabilistic,
)
from mainline_recall_agent.run.session import SqlSession, Transactional, classify_sqlstate
from mainline_recall_agent.run.session import sqlstate_of as _sqlstate_of

__all__ = [
    "EVENT_CONTROL_CLASSES_SQL",
    "EVENT_SEVERITY_SQL",
    "MAX_WRITE_ATTEMPTS",
    "RecallOrchestrator",
    "RunOutcome",
    "RunRequest",
]

EVENT_SEVERITY_SQL: Final = """
SELECT ev.event_id, ev.severity_gate, ev.title
  FROM mainline.event ev
 WHERE ev.site_id = $1
   AND ev.event_id IN (
         SELECT value::UUID FROM jsonb_array_elements_text($2::JSONB) AS t(value))
""".strip()

EVENT_CONTROL_CLASSES_SQL: Final = """
SELECT cf.event_id, array_agg(DISTINCT cf.control_class)
  FROM mainline.control_failure cf
 WHERE cf.event_id IN (
         SELECT value::UUID FROM jsonb_array_elements_text($1::JSONB) AS t(value))
 GROUP BY cf.event_id
""".strip()

#: The recall write transaction is off the merge hot path, so one bounded retry allowance on
#: ``40001`` is correct. It is bounded, it is scoped to a single SQLSTATE, and it rebuilds the
#: transaction rather than replaying statements. **A blanket-retry helper is banned**: a loop
#: that could absorb a ``23514`` would launder a refusal into an apparent success.
MAX_WRITE_ATTEMPTS: Final = 3

_ORIGIN_ANCESTRY: Final = "deterministic_ancestry"
_ORIGIN_BONDED: Final = "bonded"
_ORIGIN_PROBABILISTIC: Final = "recall_probabilistic"


@dataclass(frozen=True, slots=True)
class RunRequest:
    """Everything a run needs that it cannot derive for itself."""

    permit_id: UUID
    site_id: UUID
    activity_scope_id: UUID
    policy_version: str
    corpus_commit: bytes
    corpus_root: bytes
    index_generation: str
    exposure_cues: tuple[ExposureCueRef, ...]
    clause_control_classes: Mapping[UUID, tuple[str, ...]]
    permit_control_classes: frozenset[str]
    run_id: UUID = field(default_factory=uuid4)


@dataclass(frozen=True, slots=True)
class RunOutcome:
    """What one run produced. ``open_blocking`` is the integer the whole domain exists for."""

    run_id: UUID
    permit_id: UUID
    receipt: SilenceReceipt
    certificate: CoverageCertificate
    candidate_set: CandidateSet
    candidates: tuple[CandidateRow, ...]
    silence: tuple[SilenceRow, ...]
    arms_degraded: bool
    latency_ms: int
    materialise: MaterialiseResult | None = None

    @property
    def open_blocking(self) -> int:
        """How many obligations this run asks the kernel to materialise."""
        return self.candidate_set.counts.n_blocking


def _no_asset_match(event_ids: Sequence[UUID]) -> Mapping[UUID, bool]:
    """The default asset-class resolver: no match known.

    ``asset_class_match`` is documented in the frozen feature spec as *"Weak on its own: a
    mechanism crosses equipment."* Resolving it needs the asset graph, which belongs to the
    boundary domain. Returning ``False`` everywhere is the honest default — it never inflates
    a score — and a real resolver is injected when that domain lands.
    """
    return dict.fromkeys(event_ids, False)


class RecallOrchestrator:
    """The run loop. One instance per configuration, reusable across permits."""

    def __init__(
        self,
        *,
        session: SqlSession,
        writer: Transactional,
        arm_runner_factory: Callable[[RunRequest], ArmRunner] | None = None,
        lexical_runner_factory: Callable[[RunRequest], LexicalRunner] | None = None,
        reranker_factory: Callable[[RunRequest], Reranker | None] | None = None,
        kernel: MaterialiseClient | None = None,
        asset_match_resolver: Callable[
            [Sequence[UUID]], Mapping[UUID, bool]
        ] = _no_asset_match,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
        cap: int = BLOCKING_CAP_PROBABILISTIC,
    ) -> None:
        """Wire the run loop. Every collaborator is injected so the loop is testable whole."""
        self._session = session
        self._writer = writer
        self._arm_runner_factory = arm_runner_factory
        self._lexical_runner_factory = lexical_runner_factory
        self._reranker_factory = reranker_factory
        self._kernel = kernel
        self._asset_match_resolver = asset_match_resolver
        self._clock = clock
        self._cap = cap

    # ── resolvers ────────────────────────────────────────────────────────────────────

    def _severities(self, site_id: UUID, event_ids: Sequence[UUID]) -> dict[UUID, int]:
        """Read ``event.severity_gate`` for a candidate set. Never asserted by a retriever."""
        if not event_ids:
            return {}
        payload = json.dumps(sorted({str(event_id) for event_id in event_ids}))
        rows = self._session.query(EVENT_SEVERITY_SQL, (str(site_id), payload))
        return {UUID(str(row[0])): int(row[1]) for row in rows}

    def _control_classes(
        self, event_ids: Sequence[UUID]
    ) -> dict[UUID, frozenset[str]]:
        """Read each event's recorded control-failure classes."""
        if not event_ids:
            return {}
        payload = json.dumps(sorted({str(event_id) for event_id in event_ids}))
        rows = self._session.query(EVENT_CONTROL_CLASSES_SQL, (payload,))
        return {
            UUID(str(row[0])): frozenset(str(item) for item in (row[1] or []))
            for row in rows
        }

    # ── clause binding ───────────────────────────────────────────────────────────────

    @staticmethod
    def _bind_clause(
        clauses: Sequence[CitedClause],
        event_classes: frozenset[str],
    ) -> CitedClause:
        """Bind a probabilistic candidate to the cited clause it would raise a check against.

        ``blocking_check`` foreign-keys ``(clause_uuid, commit_id)``, so every candidate must
        name one. The rule, in order, and it is recorded in ``features['clause_binding']``:

        1. the cited clause with the greatest control-class overlap with the event;
        2. ties, and the no-overlap case, broken by ``clause_uuid`` ascending.

        The tie-break is lexical rather than "most severe" on purpose: severity is what
        *lowers the evidence bar*, and letting it also choose the clause would let the same
        quantity act twice on one decision.
        """
        best = max(
            clauses,
            key=lambda clause: (
                len(frozenset(clause.control_classes) & event_classes),
                # `max` keeps the first maximum, so negate the id ordering to make ascending
                # clause_uuid the winner on a tie.
                tuple(-byte for byte in clause.clause_uuid.bytes),
            ),
        )
        return best

    # ── the loop ─────────────────────────────────────────────────────────────────────

    def run(self, request: RunRequest) -> RunOutcome:
        """Execute one recall run end to end.

        Raises:
            RunRefused: the policy gate, the conservation law, the kernel, or the database
                refused. No candidate set is produced.
        """
        started_at = self._clock()

        policy = load_policy(self._session, request.policy_version)
        load_thymogate(self._session, policy)  # raises ThymogateRefused on an unclean panel
        try:
            calibrator = IsotonicCalibrator.from_json(policy.calibrator)
        except (CalibrationRefused, KeyError, TypeError, ValueError) as exc:
            raise RunRefused(
                f"{policy.policy_version}: the stored calibrator will not load ({exc}). "
                "p_relevant is an exhibit and must be re-evaluable by a stranger from the "
                "knots; a run cannot fall back to an uncalibrated score."
            ) from exc
        tau_table = TauTable(
            thresholds=policy.tau_thresholds(),
            policy_version=policy.policy_version,
            provenance={"source": "mainline_meas.recall_policy", "gate": "MI18 anchored"},
        )

        clauses = cited_clauses(
            self._session, request.permit_id, request.clause_control_classes
        )
        if not clauses:
            raise RunRefused(
                f"permit {request.permit_id} cites no clause versions. A permit that declares "
                "no scope has nothing to gate, and a recall run over an empty citation set "
                "would produce a receipt asserting that nothing was relevant to nothing."
            )

        silence: list[SilenceRow] = []
        ancestry = channel_a(self._session, request.site_id, clauses)
        bonded = channel_b(
            self._session,
            request.site_id,
            request.activity_scope_id,
            policy.taxonomy_ver,
        )
        silence.extend(self._channel_a_silence(ancestry.unresolved_clauses, ancestry.unconfirmed))

        probabilistic, arms_degraded, degradation = self._probabilistic(
            request, policy.arms, calibrator
        )
        silence.extend(degradation)
        if probabilistic is not None:
            silence.extend(probabilistic.silence)

        rows, receipt_scores, bonded_ids, cap_rows = self._admit(
            request=request,
            ancestry=ancestry.hits,
            bonded=bonded,
            probabilistic=probabilistic,
            tau_table=tau_table,
            policy_version=policy.policy_version,
        )
        silence.extend(cap_rows)

        counts = enforce_conservation(rows, bonded_event_ids=bonded_ids, cap=self._cap)

        observation = self._observation(request, probabilistic, policy, arms_degraded)
        certificate = certify(observation)

        receipt, _leaves = build_receipt(
            receipt_scores,
            run_id=str(request.run_id),
            permit_id=str(request.permit_id),
            policy_version=policy.policy_version,
            index_generation=certificate.index_generation,
            corpus_root=request.corpus_root,
            certificate_verdict=certificate.verdict,
            not_exhaustive=not certificate.permits_exhaustion_claim,
        )

        finished_at = self._clock()
        latency_ms = max(0, int((finished_at - started_at).total_seconds() * 1000))
        plan_digest = (
            probabilistic.coverage.index_plan_digest
            if probabilistic is not None
            else bytes(32)
        )

        record = RunRecord(
            run_id=request.run_id,
            permit_id=request.permit_id,
            site_id=request.site_id,
            policy_version=policy.policy_version,
            corpus_commit=request.corpus_commit,
            index_generation=certificate.index_generation,
            index_plan_digest=plan_digest,
            arms_degraded=arms_degraded,
            started_at=started_at,
            latency_ms=latency_ms,
            counts=counts,
            candidates=rows,
            certificate=certificate.to_row(),
            receipt={
                "silence_receipt_id": uuid4(),
                "corpus_root": receipt.corpus_root,
                "candidate_root": receipt.candidate_root,
                "theta": receipt.theta,
                "s": receipt.s,
                "n": receipt.n,
                "boundary_proof": receipt.boundary.to_json(),
            },
            silence=tuple(silence),
        )
        self._write(record)

        candidate_set = self._candidate_set(
            request=request,
            policy_version=policy.policy_version,
            taxonomy_ver=policy.taxonomy_ver,
            rows=rows,
            clauses=clauses,
            ancestry=ancestry.hits,
            bonded=bonded,
            probabilistic=probabilistic,
            receipt=receipt,
            certificate=certificate,
            silence_receipt_id=UUID(str(record.receipt["silence_receipt_id"])),
            plan_digest=plan_digest,
            arms_degraded=arms_degraded,
        )

        materialised = None
        if self._kernel is not None:
            materialised = self._kernel.materialise(candidate_set)

        return RunOutcome(
            run_id=request.run_id,
            permit_id=request.permit_id,
            receipt=receipt,
            certificate=certificate,
            candidate_set=candidate_set,
            candidates=rows,
            silence=tuple(silence),
            arms_degraded=arms_degraded,
            latency_ms=latency_ms,
            materialise=materialised,
        )

    # ── stages ───────────────────────────────────────────────────────────────────────

    @staticmethod
    def _channel_a_silence(
        unresolved: Sequence[CitedClause],
        unconfirmed: Sequence[AncestryHit],
    ) -> list[SilenceRow]:
        """Record what channel A could not do, rather than letting it vanish."""
        rows: list[SilenceRow] = []
        for clause in unresolved:
            rows.append(
                SilenceRow(
                    subject_kind="clause",
                    subject_id=clause.clause_uuid,
                    reason="unreachable",
                    severity=0,
                    score=None,
                    threshold=None,
                    arithmetic={
                        "commit_id": clause.commit_id,
                        "relation": clause.relation,
                        "note": (
                            "the clause version asserts no CAT control class, so channel A "
                            "has no join key and this clause contributed no deterministic "
                            "ancestry. Retrieval was not attempted for it; it was not "
                            "attempted and found nothing."
                        ),
                    },
                )
            )
        for hit in unconfirmed:
            rows.append(
                SilenceRow(
                    subject_kind="event",
                    subject_id=hit.event_id,
                    reason="unreachable",
                    severity=hit.severity_gate,
                    score=None,
                    threshold=None,
                    arithmetic={
                        "clause_uuid": str(hit.clause_uuid),
                        "commit_id": hit.commit_id,
                        "closure_gen": hit.closure_gen,
                        "note": (
                            "the closure row listed this event as an ancestor but the "
                            "inverted index @> probe did not confirm the containment. A fact "
                            "the gate depends on is enforced, never trusted, so it was not "
                            "admitted."
                        ),
                    },
                )
            )
        return rows

    def _probabilistic(
        self,
        request: RunRequest,
        policy_arms: Mapping[str, Any],
        calibrator: IsotonicCalibrator,
    ) -> tuple[ProbabilisticOutcome | None, bool, list[SilenceRow]]:
        """Run C, C' and D behind the one boundary that is allowed to fail."""
        if self._arm_runner_factory is None or self._lexical_runner_factory is None:
            return (
                None,
                True,
                [
                    SilenceRow(
                        subject_kind="permit",
                        subject_id=request.permit_id,
                        reason="unreachable",
                        severity=0,
                        score=None,
                        threshold=None,
                        arithmetic={
                            "note": (
                                "no probabilistic channel is configured for this run; it "
                                "completed on channels A and B alone"
                            )
                        },
                    )
                ],
            )
        reranker = (
            None if self._reranker_factory is None else self._reranker_factory(request)
        )
        try:
            outcome = run_probabilistic(
                arm_runner=self._arm_runner_factory(request),
                lexical_runner=self._lexical_runner_factory(request),
                reranker=reranker,
                calibrator=calibrator,
                policy_arms=policy_arms,
                permit_control_classes=request.permit_control_classes,
                control_class_resolver=self._control_classes,
                asset_match_resolver=self._asset_match_resolver,
            )
        except ProbabilisticChannelUnavailable as exc:
            return (
                None,
                True,
                [
                    SilenceRow(
                        subject_kind="permit",
                        subject_id=request.permit_id,
                        reason=exc.silence_reason,
                        severity=0,
                        score=None,
                        threshold=None,
                        arithmetic={
                            "detail": exc.detail,
                            "note": (
                                "channels C and D did not complete. The run completed on "
                                "channels A and B, recorded arms_degraded=true, and still "
                                "blocks the merge: the gate refuses on graph truth alone."
                            ),
                        },
                    )
                ],
            )
        return outcome, outcome.rerank_degraded, []

    def _admit(
        self,
        *,
        request: RunRequest,
        ancestry: Sequence[AncestryHit],
        bonded: Sequence[BondedHit],
        probabilistic: ProbabilisticOutcome | None,
        tau_table: TauTable,
        policy_version: str,
    ) -> tuple[
        tuple[CandidateRow, ...],
        tuple[CandidateScore, ...],
        tuple[UUID, ...],
        list[SilenceRow],
    ]:
        """Union the channels, apply Severity-Graded Admission, and build the candidate rows.

        The union is a **set** keyed by ``event_id``, with precedence A > B > probabilistic:
        ``recall_candidate`` is keyed ``(run_id, event_id)``, so an event found by three
        channels is one candidate and the strongest channel decides its origin. That is not a
        deduplication event — ``deduped`` is reserved for MMR-suppressed siblings — and the
        channels it was also found by survive in ``features['channels']``.
        """
        scored_by_id: dict[UUID, ScoredCandidate] = (
            {candidate.event_id: candidate for candidate in probabilistic.scored}
            if probabilistic is not None
            else {}
        )
        deduped = probabilistic.deduped if probabilistic is not None else ()

        origin_of: dict[UUID, str] = {}
        channels_of: dict[UUID, set[str]] = {}
        evidence_of: dict[UUID, str] = {}
        for hit in ancestry:
            origin_of[hit.event_id] = _ORIGIN_ANCESTRY
            channels_of.setdefault(hit.event_id, set()).add("A")
            evidence_of[hit.event_id] = hit.evidence_summary()
        for bond in bonded:
            channels_of.setdefault(bond.event_id, set()).add("B")
            if origin_of.get(bond.event_id) != _ORIGIN_ANCESTRY:
                origin_of[bond.event_id] = _ORIGIN_BONDED
                evidence_of[bond.event_id] = bond.evidence_summary(
                    request.activity_scope_id
                )
        for event_id, candidate in scored_by_id.items():
            channels_of.setdefault(event_id, set()).update(candidate.channels)
            origin_of.setdefault(event_id, _ORIGIN_PROBABILISTIC)
            evidence_of.setdefault(event_id, candidate.evidence_summary)

        deduped_ids = {sibling.event_id for sibling in deduped} - set(origin_of)
        severities = self._severities(
            request.site_id, [*origin_of, *deduped_ids]
        )

        admission_input: list[AdmissionCandidate] = []
        pre_silenced: list[CandidateRow] = []
        rank_of: dict[UUID, int] = {}
        for position, event_id in enumerate(
            sorted(origin_of, key=lambda key: (-severities.get(key, 0), str(key))), start=1
        ):
            rank_of[event_id] = position
            severity = severities.get(event_id, 0)
            scored = scored_by_id.get(event_id)
            channels = tuple(sorted(channels_of[event_id]))
            if severity < 1:
                # Severity-Graded Admission has no threshold below severity 1: there is no
                # tau(0). A severity-0 event is recorded as a bounded negative with its
                # arithmetic, never dropped and never compared against a bar that does not
                # exist.
                pre_silenced.append(
                    CandidateRow(
                        event_id=event_id,
                        rank=position,
                        severity=severity,
                        p_relevant=scored.p_relevant if scored is not None else 0.0,
                        tau_applied=0.0,
                        outcome="silenced",
                        origin=origin_of[event_id],
                        features={
                            "channels": list(channels),
                            "reason": "no admission threshold exists below severity 1",
                        },
                    )
                )
                continue
            admission_input.append(
                AdmissionCandidate(
                    doc_id=str(event_id),
                    p_relevant=scored.p_relevant if scored is not None else 1.0,
                    severity=severity,
                    origin=origin_of[event_id],
                    channel=channels[0],
                    rank=position,
                    also_matched=tuple(
                        str(sibling) for sibling in (scored.also_matched if scored else ())
                    ),
                    coarse_only=bool(scored.coarse_only) if scored is not None else False,
                )
            )

        try:
            result = admit(
                admission_input,
                tau_table=tau_table,
                cap=self._cap,
                policy_version=policy_version,
            )
        except AdmissionRefused as exc:
            raise RunRefused(f"admission refused the candidate set: {exc}") from exc

        rows: list[CandidateRow] = list(pre_silenced)
        for check in (*result.blocking, *result.advisory, *result.silenced):
            event_id = UUID(check.doc_id)
            scored = scored_by_id.get(event_id)
            rows.append(
                CandidateRow(
                    event_id=event_id,
                    rank=rank_of[event_id],
                    severity=check.severity,
                    p_relevant=check.p_relevant,
                    tau_applied=check.tau_applied,
                    outcome=check.outcome,
                    origin=check.origin,
                    features=self._features(
                        channels=tuple(sorted(channels_of[event_id])),
                        scored=scored,
                        check_demotion=check.demotion,
                        tau_consulted=check.tau_consulted,
                    ),
                )
            )

        for sibling in deduped:
            if sibling.event_id in {row.event_id for row in rows}:
                continue
            rows.append(
                CandidateRow(
                    event_id=sibling.event_id,
                    rank=len(rows) + 1,
                    severity=severities.get(sibling.event_id, 0),
                    p_relevant=min(max(sibling.relevance, 0.0), 1.0),
                    tau_applied=0.0,
                    outcome="deduped",
                    origin=_ORIGIN_PROBABILISTIC,
                    features={
                        "representative": str(sibling.representative_id),
                        "cosine": sibling.similarity,
                        "note": "MMR-suppressed sibling, attached to its representative",
                    },
                )
            )

        cap_rows = [
            SilenceRow(
                subject_kind="event",
                subject_id=UUID(record.subject_id),
                reason=record.reason,
                severity=record.severity,
                score=record.score,
                threshold=record.threshold,
                arithmetic=record.arithmetic,
                source=record.source,
            )
            for record in result.silence_records
        ]

        receipt_scores = tuple(
            CandidateScore(
                event_id=str(row.event_id),
                p_relevant=row.p_relevant,
                tau_applied=row.tau_applied,
                outcome=row.outcome,
            )
            for row in rows
        )
        bonded_ids = tuple(sorted({bond.event_id for bond in bonded}, key=str))
        # Evidence summaries are carried on the wire, not in recall_candidate: the wire is
        # what becomes blocking_check.evidence_summary.
        self._evidence = evidence_of
        return tuple(rows), receipt_scores, bonded_ids, cap_rows

    @staticmethod
    def _features(
        *,
        channels: tuple[str, ...],
        scored: ScoredCandidate | None,
        check_demotion: str,
        tau_consulted: bool,
    ) -> dict[str, Any]:
        """The ``recall_candidate.features`` JSONB — the arithmetic, kept with the row."""
        payload: dict[str, Any] = {
            "channels": list(channels),
            "tau_consulted": tau_consulted,
        }
        if check_demotion:
            payload["demotion"] = check_demotion
        if scored is not None:
            payload["feature_vector"] = scored.features.to_json()
            payload["raw_score"] = scored.raw
            payload["facet"] = scored.facet
            payload["scope_level"] = scored.scope_level
            payload["coarse_only"] = scored.coarse_only
            payload["also_matched"] = [str(item) for item in scored.also_matched]
        return payload

    def _observation(
        self,
        request: RunRequest,
        probabilistic: ProbabilisticOutcome | None,
        policy: Any,
        arms_degraded: bool,
    ) -> CoverageObservation:
        """Build the CUE HORIZON observation, including for a run that never searched."""
        if probabilistic is None:
            return CoverageObservation(
                fingerprint_input=IndexFingerprintInput(
                    index_generation=request.index_generation,
                    embed_model=policy.embed_model,
                    taxonomy_ver=policy.taxonomy_ver,
                    arm_set_digest="none:degraded",
                    prefix_trees=(),
                ),
                index_generation_at_start=request.index_generation,
                index_generation_at_end=request.index_generation,
                arms=(),
                sweep_ran=False,
                degraded=True,
                notes=(
                    "the probabilistic channels did not run, so no prefix tree was searched "
                    "and the reach of this retrieval is unknown",
                ),
            )
        coverage: ChannelCOutcome = probabilistic.coverage
        return CoverageObservation(
            fingerprint_input=IndexFingerprintInput(
                index_generation=coverage.index_generation_at_end,
                embed_model=policy.embed_model,
                taxonomy_ver=policy.taxonomy_ver,
                arm_set_digest=coverage.arm_set_digest,
                prefix_trees=coverage.prefix_trees,
            ),
            index_generation_at_start=coverage.index_generation_at_start,
            index_generation_at_end=coverage.index_generation_at_end,
            arms=coverage.arm_coverage,
            sweep_ran=coverage.sweep_ran,
            degraded=arms_degraded,
            notes=probabilistic.notes,
        )

    def _candidate_set(
        self,
        *,
        request: RunRequest,
        policy_version: str,
        taxonomy_ver: int,
        rows: Sequence[CandidateRow],
        clauses: Sequence[CitedClause],
        ancestry: Sequence[AncestryHit],
        bonded: Sequence[BondedHit],
        probabilistic: ProbabilisticOutcome | None,
        receipt: SilenceReceipt,
        certificate: CoverageCertificate,
        silence_receipt_id: UUID,
        plan_digest: bytes,
        arms_degraded: bool,
    ) -> CandidateSet:
        """Assemble the frozen wire payload. Every law is re-enforced by its validators."""
        clause_of_ancestry = {hit.event_id: hit for hit in ancestry}
        bonded_ids = {bond.event_id for bond in bonded}
        event_classes = self._control_classes([row.event_id for row in rows])
        scored_by_id = (
            {candidate.event_id: candidate for candidate in probabilistic.scored}
            if probabilistic is not None
            else {}
        )

        candidates: list[Candidate] = []
        for row in rows:
            hit = clause_of_ancestry.get(row.event_id)
            if hit is not None:
                clause_uuid, commit_id = hit.clause_uuid, hit.commit_id
                binding = "channel_a_join"
            else:
                bound = self._bind_clause(
                    clauses, event_classes.get(row.event_id, frozenset())
                )
                clause_uuid, commit_id = bound.clause_uuid, bound.commit_id
                binding = "control_class_overlap"
            scored = scored_by_id.get(row.event_id)
            features = dict(row.features)
            features["clause_binding"] = binding
            candidates.append(
                Candidate(
                    event_id=row.event_id,
                    clause_uuid=clause_uuid,
                    commit_id=commit_id,
                    origin=row.origin,  # type: ignore[arg-type]
                    channels=tuple(row.features.get("channels", ["C"])),  # type: ignore[arg-type]
                    outcome=row.outcome,  # type: ignore[arg-type]
                    rank=row.rank,
                    severity=row.severity,
                    p_relevant=row.p_relevant,
                    tau_applied=row.tau_applied,
                    features=features,
                    evidence_summary=self._evidence.get(row.event_id, "")
                    if row.outcome in {"blocking", "advisory"}
                    else "",
                    also_matched=tuple(scored.also_matched) if scored is not None else (),
                    bonded_severity_5=row.event_id in bonded_ids,
                )
            )

        return CandidateSet(
            run_id=request.run_id,
            permit_id=request.permit_id,
            site_id=request.site_id,
            policy_version=policy_version,
            taxonomy_ver=taxonomy_ver,
            corpus_commit=request.corpus_commit.hex(),
            index_generation=certificate.index_generation,
            index_plan_digest=plan_digest.hex(),
            arms_degraded=arms_degraded,
            silence_receipt_id=silence_receipt_id,
            candidate_root=receipt.candidate_root.hex(),
            certificate_verdict=certificate.verdict,
            not_exhaustive=receipt.not_exhaustive,
            exposure_cues=request.exposure_cues,
            candidates=tuple(candidates),
            counts=Counts.of(tuple(candidates)),
        )

    def _write(self, record: RunRecord) -> None:
        """Commit the record, allowing exactly the retries ARCHITECTURE 16 permits.

        ``40001`` is the only retryable SQLSTATE and this is the only place this domain
        retries. A refusal (``23514`` / ``23503`` / ``23505`` / ``P0001``) is attempted once
        and re-raised with its SQLSTATE intact; anything else is
        :class:`~mainline_recall_agent.run.errors.UnmodelledSqlstate`, because a database that
        refused for an unmodelled reason has told us an assumption is wrong.
        """
        last: Exception | None = None
        for attempt in range(1, MAX_WRITE_ATTEMPTS + 1):
            try:
                with self._writer.transaction() as session:
                    insert_run(session, record)
            except Exception as exc:  # noqa: BLE001 - immediately classified and re-raised
                sqlstate = _sqlstate_of(exc)
                if sqlstate is None:
                    raise
                kind = classify_sqlstate(sqlstate)
                if kind == "retryable" and attempt < MAX_WRITE_ATTEMPTS:
                    last = exc
                    continue
                if kind == "unmodelled":
                    raise UnmodelledSqlstate(
                        f"the recall write transaction failed with SQLSTATE {sqlstate}, "
                        "which is neither retryable (40001) nor a modelled gate refusal "
                        "(23514/23503/23505/P0001). The schema moved or an assumption is "
                        f"wrong: {exc}"
                    ) from exc
                raise
            else:
                return
        raise RunRefused(
            f"the recall write transaction retried {MAX_WRITE_ATTEMPTS} times on 40001 and "
            f"did not commit: {last}"
        )
