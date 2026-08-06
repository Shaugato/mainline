# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""Recall metrics. Every one of them returns a :class:`Measurement`, never a float.

The metric set is chosen to answer, in order, the four questions that decide whether
the gate ships:

* **Does it find the precursor?**   ``recall_at_k``, ``retro_recall_at_k``, ``mrr``,
  ``ndcg_at_k``, ``rank_distribution``
* **Is what it blocks on real?**    ``p_at_block``
* **Does it cry wolf?**             ``nuisance_rate``, ``mean_blocking_checks_per_permit``
* **Did it account for everything it saw?**  ``conservation``

Two conventions, stated because they move the numbers:

1. **Unjudged is non-relevant** (the TREC convention) *and* the judgement coverage is
   reported alongside. Excluding unjudged candidates from a precision denominator
   inflates precision by exactly the amount nobody adjudicated. Where coverage over
   the blocking set falls below :data:`MIN_JUDGEMENT_COVERAGE` the measurement is
   returned **undefined** rather than optimistic.
2. **Relevance floor is grade >= 2** (:data:`~trappoint_recall.eval.qrels.BLOCKING_RELEVANCE_FLOOR`).
   One constant, one place, under review.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Final

import numpy as np

from trappoint_recall.eval.backend import (
    BLOCKING_CAP_PROBABILISTIC,
    QueryResult,
    RunTally,
)
from trappoint_recall.eval.measurement import (
    DEFAULT_CONFIDENCE,
    Measurement,
    undefined_measurement,
)
from trappoint_recall.eval.qrels import BLOCKING_RELEVANCE_FLOOR, QrelSet

__all__ = [
    "MIN_JUDGEMENT_COVERAGE",
    "BondedFatalityReport",
    "ConservationReport",
    "ConservationViolation",
    "RankDistribution",
    "bonded_fatalities_all_blocking",
    "conservation",
    "dcg",
    "mean_blocking_checks_per_permit",
    "mrr",
    "ndcg_at_k",
    "nuisance_rate",
    "p_at_block",
    "rank_distribution",
    "recall_at_k",
    "retro_recall_at_k",
]

MIN_JUDGEMENT_COVERAGE: Final = 0.90
"""Minimum share of blocking candidates that must carry a judgement for ``P@block`` to
be considered defined. Below this the precision number is mostly assumption."""


# --------------------------------------------------------------------------------------
# Recall family
# --------------------------------------------------------------------------------------


def _hit_at_k(result: QueryResult, qrels: QrelSet, k: int, floor: int) -> bool:
    relevant = qrels.relevant_docs(result.query.query_id, floor=floor)
    if not relevant:
        return False
    return any(doc in relevant for doc in result.ranked_doc_ids()[:k])


def recall_at_k(
    results: Sequence[QueryResult],
    qrels: QrelSet,
    k: int,
    *,
    split_policy_id: str,
    metric_name: str | None = None,
    relevance_floor: int = BLOCKING_RELEVANCE_FLOOR,
    confidence: float = DEFAULT_CONFIDENCE,
) -> Measurement:
    """Share of queries with at least one relevant document in the top ``k``.

    This is *set* recall at k in the binary sense used by the release gates: a permit
    either surfaced a precursor a supervisor should see, or it did not. Queries with no
    relevant document at all are excluded from the denominator, because a query nobody
    can answer measures the corpus, not the retriever.
    """
    if k < 1:
        raise ValueError(f"k must be >= 1, got {k}")
    name = metric_name or f"recall_at_{k}"
    scorable = [
        r for r in results if qrels.relevant_docs(r.query.query_id, floor=relevance_floor)
    ]
    if not scorable:
        return undefined_measurement(
            name,
            split_policy_id=split_policy_id,
            reason=(
                "no query in this subset has a relevant document at grade "
                f">= {relevance_floor}; recall is undefined over an unanswerable set"
            ),
            confidence=confidence,
            detail={"n_results": len(results)},
        )
    hits = sum(1 for r in scorable if _hit_at_k(r, qrels, k, relevance_floor))
    return Measurement.proportion(
        name,
        hits,
        len(scorable),
        split_policy_id=split_policy_id,
        confidence=confidence,
        detail={
            "k": k,
            "relevance_floor": relevance_floor,
            "n_excluded_unanswerable": len(results) - len(scorable),
        },
    )


def retro_recall_at_k(
    results: Sequence[QueryResult],
    qrels: QrelSet,
    k: int,
    *,
    split_policy_id: str,
    severity: int = 5,
    confidence: float = DEFAULT_CONFIDENCE,
) -> Measurement:
    """Retro-Recall@k restricted to retro permits whose precursor had ``severity``.

    The money metric. For each severity-5 event at time *t*, the permit that would have
    preceded it is presented against a corpus walled at *t*; the question is whether the
    true precursor comes back in the top k. Restricting to the *authored* truth
    precursor rather than to any relevant document is deliberate: this metric answers
    "would the system have caught **this** one", which is the question a coroner asks.
    """
    subset = [
        r
        for r in results
        if r.query.kind == "retro" and r.query.severity == severity and r.query.truth_doc_id
    ]
    name = f"retro_recall_at_{k}_sev{severity}"
    if not subset:
        return undefined_measurement(
            name,
            split_policy_id=split_policy_id,
            reason=f"corpus contains no retro permits at severity {severity}",
            confidence=confidence,
            detail={"n_results": len(results)},
        )
    hits = 0
    for r in subset:
        truth = r.query.truth_doc_id
        if truth is not None and truth in r.ranked_doc_ids()[:k]:
            hits += 1
    return Measurement.proportion(
        name,
        hits,
        len(subset),
        split_policy_id=split_policy_id,
        confidence=confidence,
        detail={"k": k, "severity": severity, "criterion": "authored truth precursor in top-k"},
    )


def mrr(
    results: Sequence[QueryResult],
    qrels: QrelSet,
    *,
    split_policy_id: str,
    relevance_floor: int = BLOCKING_RELEVANCE_FLOOR,
    confidence: float = DEFAULT_CONFIDENCE,
) -> Measurement:
    """Mean reciprocal rank of the first relevant document.

    Bootstrap interval, not Wilson: MRR is a mean of per-query reciprocals, not a
    proportion, and a Wilson interval on it would be a category error.
    """
    scorable = [
        r for r in results if qrels.relevant_docs(r.query.query_id, floor=relevance_floor)
    ]
    if not scorable:
        return undefined_measurement(
            "mrr",
            split_policy_id=split_policy_id,
            reason="no query in this subset has a relevant document",
            confidence=confidence,
        )
    reciprocals: list[float] = []
    for r in scorable:
        relevant = qrels.relevant_docs(r.query.query_id, floor=relevance_floor)
        rr = 0.0
        for position, doc in enumerate(r.ranked_doc_ids(), start=1):
            if doc in relevant:
                rr = 1.0 / position
                break
        reciprocals.append(rr)
    return Measurement.mean(
        "mrr",
        reciprocals,
        split_policy_id=split_policy_id,
        confidence=confidence,
        detail={"relevance_floor": relevance_floor},
    )


def dcg(gains: Sequence[float]) -> float:
    """Discounted cumulative gain: ``sum(gain_i / log2(i + 1))``, 1-based ``i``."""
    if not gains:
        return 0.0
    arr = np.asarray(gains, dtype=np.float64)
    discounts = 1.0 / np.log2(np.arange(2, arr.size + 2, dtype=np.float64))
    return float(np.dot(arr, discounts))


def ndcg_at_k(
    results: Sequence[QueryResult],
    qrels: QrelSet,
    k: int = 10,
    *,
    split_policy_id: str,
    gain: str = "exponential",
    confidence: float = DEFAULT_CONFIDENCE,
) -> Measurement:
    """Mean nDCG@k over the graded judgements.

    ``gain="exponential"`` uses the TREC convention ``2**grade - 1``, which is the right
    shape for a 0-3 scale where grade 3 means "this is the precursor". ``gain="linear"``
    uses the grade itself and exists so the implementation can be cross-checked against
    scikit-learn, which offers linear gains only
    (see :mod:`trappoint_recall.eval.crosscheck`).
    """
    if k < 1:
        raise ValueError(f"k must be >= 1, got {k}")
    if gain not in ("exponential", "linear"):
        raise ValueError(f"gain must be 'exponential' or 'linear', got {gain!r}")

    def to_gain(grade: int) -> float:
        return float(2**grade - 1) if gain == "exponential" else float(grade)

    scorable = [r for r in results if qrels.graded_docs(r.query.query_id)]
    if not scorable:
        return undefined_measurement(
            f"ndcg_at_{k}",
            split_policy_id=split_policy_id,
            reason="no query in this subset carries graded judgements",
            confidence=confidence,
        )
    scores: list[float] = []
    for r in scorable:
        graded = qrels.graded_docs(r.query.query_id)
        ranked = r.ranked_doc_ids()[:k]
        actual = [to_gain(graded.get(doc, 0)) for doc in ranked]
        ideal = sorted((to_gain(g) for g in graded.values()), reverse=True)[:k]
        idcg = dcg(ideal)
        scores.append(0.0 if idcg <= 0.0 else dcg(actual) / idcg)
    return Measurement.mean(
        f"ndcg_at_{k}",
        scores,
        split_policy_id=split_policy_id,
        confidence=confidence,
        detail={"k": k, "gain": gain},
    )


@dataclass(frozen=True, slots=True)
class RankDistribution:
    """Where the truth precursor actually landed, not just whether it made a cut-off.

    Reported in full because a recall@3 of 0.90 built from ranks {1,1,1,...} and one
    built from ranks {3,3,3,...} are different products, and the second is one index
    rebuild away from being the first product's failure.
    """

    metric: str
    split_policy_id: str
    ranks: tuple[int, ...]
    not_found: int

    @property
    def n(self) -> int:
        return len(self.ranks) + self.not_found

    def histogram(self) -> Mapping[str, int]:
        buckets = {"1": 0, "2": 0, "3": 0, "4-10": 0, "11-40": 0, ">40": 0, "not_found": self.not_found}
        for rank in self.ranks:
            if rank == 1:
                buckets["1"] += 1
            elif rank == 2:
                buckets["2"] += 1
            elif rank == 3:
                buckets["3"] += 1
            elif rank <= 10:
                buckets["4-10"] += 1
            elif rank <= 40:
                buckets["11-40"] += 1
            else:
                buckets[">40"] += 1
        return buckets

    def percentile(self, q: float) -> float | None:
        """Rank at percentile ``q`` over found items only; ``None`` when nothing was found."""
        if not self.ranks:
            return None
        return float(np.percentile(np.asarray(self.ranks, dtype=np.float64), q))

    def to_dict(self) -> dict[str, object]:
        return {
            "metric": self.metric,
            "split_policy_id": self.split_policy_id,
            "n": self.n,
            "n_found": len(self.ranks),
            "not_found": self.not_found,
            "histogram": dict(self.histogram()),
            "median_rank_of_found": self.percentile(50.0),
            "p90_rank_of_found": self.percentile(90.0),
        }


def rank_distribution(
    results: Sequence[QueryResult],
    *,
    split_policy_id: str,
    severity: int | None = 5,
) -> RankDistribution:
    """Rank of the authored truth precursor for every retro permit.

    Returns a distribution rather than a :class:`Measurement`: it is not a single
    estimate and must not be reduced to one on the way to a report.
    """
    ranks: list[int] = []
    missing = 0
    label = f"truth_rank_sev{severity}" if severity is not None else "truth_rank"
    for r in results:
        if r.query.kind != "retro" or r.query.truth_doc_id is None:
            continue
        if severity is not None and r.query.severity != severity:
            continue
        ordered = r.ranked_doc_ids()
        if r.query.truth_doc_id in ordered:
            ranks.append(ordered.index(r.query.truth_doc_id) + 1)
        else:
            missing += 1
    return RankDistribution(
        metric=label,
        split_policy_id=split_policy_id,
        ranks=tuple(ranks),
        not_found=missing,
    )


# --------------------------------------------------------------------------------------
# Precision and noise
# --------------------------------------------------------------------------------------


def p_at_block(
    results: Sequence[QueryResult],
    qrels: QrelSet,
    *,
    split_policy_id: str,
    blinded_only: bool = True,
    relevance_floor: int = BLOCKING_RELEVANCE_FLOOR,
    confidence: float = DEFAULT_CONFIDENCE,
    min_coverage: float = MIN_JUDGEMENT_COVERAGE,
) -> Measurement:
    """Precision of *probabilistic* blocking checks on the blinded adjudicated subset.

    Only ``origin='recall_probabilistic'`` counts. Channels A and B block on graph
    truth and are not in the precision question: a bonded fatality is blocking because
    it is bonded, and scoring it as a retrieval hit would flatter the retriever with
    the ancestry engine's work (lead decision D2).

    Unjudged blocking candidates count as **not relevant**. If judgement coverage over
    the blocking set falls below ``min_coverage`` the measurement is undefined, because
    at that point the number is mostly an assumption about the unjudged remainder.
    """
    numerator = 0
    denominator = 0
    unjudged = 0
    skipped_unblinded = 0
    for r in results:
        qid = r.query.query_id
        for candidate in r.probabilistic_blocking:
            if blinded_only and not qrels.is_blinded(qid, candidate.doc_id):
                skipped_unblinded += 1
                continue
            denominator += 1
            grade = qrels.grade(qid, candidate.doc_id)
            if grade is None:
                unjudged += 1
            elif grade >= relevance_floor:
                numerator += 1
    if denominator == 0:
        return undefined_measurement(
            "p_at_block",
            split_policy_id=split_policy_id,
            reason=(
                "zero probabilistic blocking checks were produced over this corpus; "
                "a gate that never blocks has no precision, and reporting one would "
                "certify silence"
            ),
            confidence=confidence,
            detail={
                "n_results": len(results),
                "skipped_unblinded": skipped_unblinded,
                "blinded_only": blinded_only,
            },
        )
    coverage = (denominator - unjudged) / denominator
    if coverage < min_coverage:
        return undefined_measurement(
            "p_at_block",
            split_policy_id=split_policy_id,
            reason=(
                f"judgement coverage over the blocking set is {coverage:.3f}, below the "
                f"{min_coverage:.2f} floor; adjudicate the remainder before quoting precision"
            ),
            confidence=confidence,
            detail={"n_blocking": denominator, "n_unjudged": unjudged},
        )
    return Measurement.proportion(
        "p_at_block",
        numerator,
        denominator,
        split_policy_id=split_policy_id,
        confidence=confidence,
        detail={
            "origin": "recall_probabilistic",
            "relevance_floor": relevance_floor,
            "n_unjudged_counted_as_irrelevant": unjudged,
            "judgement_coverage": round(coverage, 4),
            "skipped_unblinded": skipped_unblinded,
            "blinded_only": blinded_only,
        },
    )


def nuisance_rate(
    results: Sequence[QueryResult],
    *,
    split_policy_id: str,
    confidence: float = DEFAULT_CONFIDENCE,
) -> Measurement:
    """Share of **routine** permits producing at least one probabilistic blocking check.

    The negative control. Measured by replaying uneventful permits: a routine permit
    that blocks is, by construction of the replay, a false alarm. ARCHITECTURE 6.7
    ceiling is 3%, and a rule that breaches it is rejected rather than tuned.
    """
    routine = [r for r in results if r.query.kind == "routine"]
    if not routine:
        return undefined_measurement(
            "nuisance_rate",
            split_policy_id=split_policy_id,
            reason=(
                "corpus contains no routine permits; the nuisance rate is measured on a "
                "routine-permit replay and cannot be inferred from incident permits"
            ),
            confidence=confidence,
        )
    noisy = sum(1 for r in routine if r.probabilistic_blocking)
    return Measurement.proportion(
        "nuisance_rate",
        noisy,
        len(routine),
        split_policy_id=split_policy_id,
        confidence=confidence,
        detail={
            "criterion": ">=1 probabilistic blocking check on a routine permit",
            "n_routine": len(routine),
        },
    )


def mean_blocking_checks_per_permit(
    results: Sequence[QueryResult],
    *,
    split_policy_id: str,
    probabilistic_only: bool = False,
    confidence: float = DEFAULT_CONFIDENCE,
) -> Measurement:
    """Mean blocking checks per permit, over **all** permits in the corpus.

    The supervisor-attention budget: ~250 permits/week at ~4 minutes per disposition.
    Counted over every permit, routine included, because the operator's week includes
    the quiet permits too.

    ``detail['n_over_cap']`` reports permits carrying more than
    :data:`~trappoint_recall.eval.backend.BLOCKING_CAP_PROBABILISTIC` probabilistic
    blocking checks — a cap breach is a defect regardless of the mean.
    """
    if not results:
        return undefined_measurement(
            "mean_blocking_checks_per_permit",
            split_policy_id=split_policy_id,
            reason="no permits were evaluated",
            confidence=confidence,
        )
    counts: list[float] = []
    over_cap = 0
    for r in results:
        blocking = r.probabilistic_blocking if probabilistic_only else r.blocking
        counts.append(float(len(blocking)))
        if len(r.probabilistic_blocking) > BLOCKING_CAP_PROBABILISTIC:
            over_cap += 1
    return Measurement.mean(
        "mean_blocking_checks_per_permit",
        counts,
        split_policy_id=split_policy_id,
        confidence=confidence,
        detail={
            "probabilistic_only": probabilistic_only,
            "cap": BLOCKING_CAP_PROBABILISTIC,
            "n_over_cap": over_cap,
            "n_permits": len(results),
            "total_blocking": int(sum(counts)),
        },
    )


# --------------------------------------------------------------------------------------
# Conservation law L3
# --------------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ConservationViolation:
    """One run whose accounting did not close, with both sides shown."""

    query_id: str
    kind: str
    declared: RunTally | None
    enumerated: RunTally
    detail: str

    def to_dict(self) -> dict[str, object]:
        return {
            "query_id": self.query_id,
            "kind": self.kind,
            "declared": self.declared.to_dict() if self.declared else None,
            "enumerated": self.enumerated.to_dict(),
            "detail": self.detail,
        }


@dataclass(frozen=True, slots=True)
class ConservationReport:
    """Result of checking ``candidates = blocking + advisory + silenced + deduped``.

    ``holds`` is not enough. A law verified over zero candidates holds vacuously, and a
    vacuous conservation law certifies exactly nothing — hence ``covered_runs``,
    ``expected_runs`` and ``total_candidates``, all of which the gate reads.
    """

    holds: bool
    expected_runs: int
    covered_runs: int
    total_candidates: int
    violations: tuple[ConservationViolation, ...]
    split_policy_id: str

    @property
    def coverage_complete(self) -> bool:
        return self.expected_runs > 0 and self.covered_runs == self.expected_runs

    @property
    def vacuous(self) -> bool:
        """True when the law was checked but had nothing to check."""
        return self.total_candidates == 0

    def to_dict(self) -> dict[str, object]:
        return {
            "law": "L3: n_candidates = n_blocking + n_advisory + n_silenced + n_deduped",
            "holds": self.holds,
            "expected_runs": self.expected_runs,
            "covered_runs": self.covered_runs,
            "coverage_complete": self.coverage_complete,
            "total_candidates": self.total_candidates,
            "vacuous": self.vacuous,
            "split_policy_id": self.split_policy_id,
            "violations": [v.to_dict() for v in self.violations],
        }


def conservation(
    results: Sequence[QueryResult], *, split_policy_id: str, expected_runs: int | None = None
) -> ConservationReport:
    """Check L3 on every run, comparing the declared counters to the enumerated ones.

    Three independent things must be true, and all three are checked separately so a
    failure names which one broke:

    1. the declared counters satisfy the partition arithmetic exactly (MI17);
    2. the declared counters equal the counters enumerated from the candidate list —
       an *independent* derivation, which is what stops the check being a tautology;
    3. every run in the corpus published counters at all.
    """
    violations: list[ConservationViolation] = []
    covered = 0
    total_candidates = 0
    for r in results:
        enumerated = r.enumerated_tally
        total_candidates += enumerated.n_candidates
        declared = r.declared_tally
        if declared is None:
            violations.append(
                ConservationViolation(
                    query_id=r.query.query_id,
                    kind=r.query.kind,
                    declared=None,
                    enumerated=enumerated,
                    detail=(
                        "backend published no run counters; the conservation law is "
                        "unverifiable, which is a failure and not a pass"
                    ),
                )
            )
            continue
        covered += 1
        if not declared.conserved:
            violations.append(
                ConservationViolation(
                    query_id=r.query.query_id,
                    kind=r.query.kind,
                    declared=declared,
                    enumerated=enumerated,
                    detail=(
                        f"declared n_candidates={declared.n_candidates} != "
                        f"blocking+advisory+silenced+deduped={declared.partition_sum}"
                    ),
                )
            )
        if declared.n_candidates != enumerated.n_candidates:
            violations.append(
                ConservationViolation(
                    query_id=r.query.query_id,
                    kind=r.query.kind,
                    declared=declared,
                    enumerated=enumerated,
                    detail=(
                        f"declared n_candidates={declared.n_candidates} != enumerated "
                        f"{enumerated.n_candidates}: candidates were dropped between the "
                        "run counters and the candidate set"
                    ),
                )
            )
        for field_name in ("n_blocking", "n_advisory", "n_silenced", "n_deduped"):
            declared_value: int = getattr(declared, field_name)
            enumerated_value: int = getattr(enumerated, field_name)
            if declared_value != enumerated_value:
                violations.append(
                    ConservationViolation(
                        query_id=r.query.query_id,
                        kind=r.query.kind,
                        declared=declared,
                        enumerated=enumerated,
                        detail=(
                            f"declared {field_name}={declared_value} != enumerated "
                            f"{enumerated_value}"
                        ),
                    )
                )
    return ConservationReport(
        holds=not violations,
        expected_runs=expected_runs if expected_runs is not None else len(results),
        covered_runs=covered,
        total_candidates=total_candidates,
        violations=tuple(violations),
        split_policy_id=split_policy_id,
    )


# --------------------------------------------------------------------------------------
# MI16 — bonded fatalities, checked against corpus truth
# --------------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class BondedFatalityReport:
    """MI16 evaluated against the corpus, not against the backend's self-report.

    ``bonded_fatalities_all_blocking`` is the positive invariant that stops a silent
    system passing the noise gates: every severity-5 event bonded to the permit's
    activity node or an ancestor must come back **blocking**, unconditionally, with no
    threshold and no model in the path.
    """

    holds: bool
    expected_bonded: int
    blocking_bonded: int
    missing: tuple[tuple[str, str], ...]
    declared_mismatches: tuple[str, ...]
    split_policy_id: str

    @property
    def vacuous(self) -> bool:
        return self.expected_bonded == 0

    def to_dict(self) -> dict[str, object]:
        return {
            "invariant": "MI16 bonded_fatalities_all_blocking",
            "holds": self.holds,
            "expected_bonded": self.expected_bonded,
            "blocking_bonded": self.blocking_bonded,
            "vacuous": self.vacuous,
            "missing": [{"query_id": q, "doc_id": d} for q, d in self.missing],
            "declared_mismatches": list(self.declared_mismatches),
            "split_policy_id": self.split_policy_id,
        }


def bonded_fatalities_all_blocking(
    results: Sequence[QueryResult], *, split_policy_id: str
) -> BondedFatalityReport:
    """Every corpus-bonded severity-5 event must appear as a blocking candidate."""
    expected = 0
    blocking = 0
    missing: list[tuple[str, str]] = []
    declared_mismatches: list[str] = []
    for r in results:
        bonded_truth = set(r.query.bonded_sev5)
        expected += len(bonded_truth)
        returned_blocking = {c.doc_id for c in r.blocking}
        for doc in sorted(bonded_truth):
            if doc in returned_blocking:
                blocking += 1
            else:
                missing.append((r.query.query_id, doc))
        declared = r.declared_tally
        if declared is not None and declared.n_bonded_sev5 != len(bonded_truth):
            declared_mismatches.append(
                f"{r.query.query_id}: declared n_bonded_sev5={declared.n_bonded_sev5} but the "
                f"corpus bonds {len(bonded_truth)}"
            )
    return BondedFatalityReport(
        holds=not missing and not declared_mismatches,
        expected_bonded=expected,
        blocking_bonded=blocking,
        missing=tuple(missing),
        declared_mismatches=tuple(declared_mismatches),
        split_policy_id=split_policy_id,
    )
