# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""Driving a backend over a corpus, and computing every metric in one bundle.

The harness is intentionally boring: it awaits ``retrieve`` once per permit, records
what came back and how long it took, asks for the declared run counters, and hands the
lot to :mod:`trappoint_recall.eval.metrics`. It does not retrieve, embed, rank, fuse,
calibrate or admit. Every one of those belongs to a worker whose output this module
exists to judge, and a harness that shared code with the thing it grades would grade
its own bugs as passes.

Concurrency is bounded and deterministic in output order: results come back in corpus
order regardless of completion order, so two runs of the same corpus produce
byte-identical reports.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Final

from trappoint_recall.eval.backend import (
    QueryResult,
    RetrievalBackend,
    ScoredCandidate,
    declared_tally_of,
)
from trappoint_recall.eval.corpus import EvalCorpus, EvalQuery
from trappoint_recall.eval.measurement import Measurement
from trappoint_recall.eval.metrics import (
    BondedFatalityReport,
    ConservationReport,
    RankDistribution,
    bonded_fatalities_all_blocking,
    conservation,
    mean_blocking_checks_per_permit,
    mrr,
    ndcg_at_k,
    nuisance_rate,
    p_at_block,
    rank_distribution,
    recall_at_k,
    retro_recall_at_k,
)

__all__ = [
    "DEFAULT_K",
    "EvaluationRun",
    "MetricBundle",
    "compute_metrics",
    "run_evaluation",
    "run_evaluation_sync",
]

DEFAULT_K: Final = 10
"""Depth requested from the backend. 10 covers Recall@1/@3/@10 and nDCG@10 in one pass."""

DEFAULT_CONCURRENCY: Final = 8


@dataclass(frozen=True, slots=True)
class EvaluationRun:
    """Everything one backend produced over one corpus, plus how it was produced."""

    corpus_name: str
    backend_name: str
    split_policy_id: str
    k: int
    results: tuple[QueryResult, ...]
    started_at: datetime
    finished_at: datetime
    config_id: str = ""
    preliminary: bool = True
    synthetic: bool = False

    @property
    def wall_seconds(self) -> float:
        return (self.finished_at - self.started_at).total_seconds()

    @property
    def latencies_ms(self) -> tuple[float, ...]:
        return tuple(r.latency_ms for r in self.results if r.latency_ms is not None)

    def to_dict(self) -> dict[str, object]:
        return {
            "corpus_name": self.corpus_name,
            "backend_name": self.backend_name,
            "split_policy_id": self.split_policy_id,
            "k": self.k,
            "n_results": len(self.results),
            "started_at": self.started_at.isoformat(),
            "finished_at": self.finished_at.isoformat(),
            "wall_seconds": round(self.wall_seconds, 3),
            "config_id": self.config_id,
            "preliminary": self.preliminary,
            "synthetic": self.synthetic,
        }


@dataclass(frozen=True, slots=True)
class MetricBundle:
    """Every metric computed from one :class:`EvaluationRun`.

    Metrics are keyed by their stable metric id so a report, an ablation row and a gate
    all read the same dictionary rather than three parallel spellings of the same name.
    """

    run: EvaluationRun
    measurements: Mapping[str, Measurement]
    conservation: ConservationReport
    bonded: BondedFatalityReport
    ranks: RankDistribution
    notes: tuple[str, ...] = field(default_factory=tuple)

    def __getitem__(self, metric: str) -> Measurement:
        try:
            return self.measurements[metric]
        except KeyError as exc:
            known = ", ".join(sorted(self.measurements))
            raise KeyError(f"unknown metric {metric!r}; bundle carries: {known}") from exc

    def to_dict(self) -> dict[str, object]:
        return {
            "run": self.run.to_dict(),
            "measurements": {k: v.to_dict() for k, v in sorted(self.measurements.items())},
            "conservation": self.conservation.to_dict(),
            "bonded_fatalities": self.bonded.to_dict(),
            "rank_distribution": self.ranks.to_dict(),
            "notes": list(self.notes),
        }


async def _one(
    backend: RetrievalBackend, query: EvalQuery, k: int, semaphore: asyncio.Semaphore
) -> QueryResult:
    async with semaphore:
        start = time.perf_counter()
        candidates: Sequence[ScoredCandidate] = await backend.retrieve(query, k)
        elapsed_ms = (time.perf_counter() - start) * 1000.0
        tally = await declared_tally_of(backend, query)
    return QueryResult(
        query=query,
        candidates=tuple(candidates),
        declared_tally=tally,
        latency_ms=elapsed_ms,
        backend_name=backend.name,
    )


async def run_evaluation(
    backend: RetrievalBackend,
    corpus: EvalCorpus,
    *,
    k: int = DEFAULT_K,
    concurrency: int = DEFAULT_CONCURRENCY,
    config_id: str = "",
) -> EvaluationRun:
    """Run ``backend`` over every permit in ``corpus``.

    Results preserve corpus order. Exceptions from a backend are **not** swallowed: a
    retriever that raises has not scored zero, it has failed to be measured, and the
    difference matters when the number is going into an exhibit.
    """
    if k < 1:
        raise ValueError(f"k must be >= 1, got {k}")
    semaphore = asyncio.Semaphore(max(1, concurrency))
    started = datetime.now(tz=UTC)
    results = await asyncio.gather(
        *(_one(backend, query, k, semaphore) for query in corpus.queries)
    )
    finished = datetime.now(tz=UTC)
    return EvaluationRun(
        corpus_name=corpus.name,
        backend_name=backend.name,
        split_policy_id=corpus.split_policy_id,
        k=k,
        results=tuple(results),
        started_at=started,
        finished_at=finished,
        config_id=config_id,
        preliminary=corpus.preliminary,
        synthetic=corpus.synthetic,
    )


def run_evaluation_sync(
    backend: RetrievalBackend,
    corpus: EvalCorpus,
    *,
    k: int = DEFAULT_K,
    concurrency: int = DEFAULT_CONCURRENCY,
    config_id: str = "",
) -> EvaluationRun:
    """Synchronous wrapper around :func:`run_evaluation`.

    Exists so the G4-alpha test suite needs no async pytest plugin. A release gate that
    can be skipped because a plugin is missing is not a release gate.
    """
    return asyncio.run(
        run_evaluation(backend, corpus, k=k, concurrency=concurrency, config_id=config_id)
    )


def compute_metrics(run: EvaluationRun, corpus: EvalCorpus) -> MetricBundle:
    """Compute the full metric set for a completed run."""
    if run.split_policy_id != corpus.split_policy_id:
        raise ValueError(
            f"run was produced under split {run.split_policy_id} but is being scored "
            f"against corpus split {corpus.split_policy_id}; refusing to mix experiments"
        )
    split = corpus.split_policy_id
    qrels = corpus.qrels
    results = run.results

    measurements: dict[str, Measurement] = {}
    for k in (1, 3, 10):
        measurements[f"recall_at_{k}"] = recall_at_k(results, qrels, k, split_policy_id=split)
        measurements[f"retro_recall_at_{k}_sev5"] = retro_recall_at_k(
            results, qrels, k, split_policy_id=split, severity=5
        )
    measurements["ndcg_at_10"] = ndcg_at_k(results, qrels, 10, split_policy_id=split)
    measurements["mrr"] = mrr(results, qrels, split_policy_id=split)
    measurements["p_at_block"] = p_at_block(results, qrels, split_policy_id=split)
    measurements["nuisance_rate"] = nuisance_rate(results, split_policy_id=split)
    measurements["mean_blocking_checks_per_permit"] = mean_blocking_checks_per_permit(
        results, split_policy_id=split
    )

    notes: list[str] = []
    if corpus.synthetic:
        notes.append(
            "Corpus is SYNTHETIC. These numbers characterise the harness, not the product."
        )
    if corpus.preliminary:
        notes.append(
            "PRELIMINARY: no customer-grade floor is claimed at this checkpoint "
            "(BUILD_PLAN.md G4-alpha)."
        )
    notes.append(
        "The time wall is enforced by predicates (occurred_at < t AND ingested_at < t AND "
        "corpus_commit <= t), never by AS OF SYSTEM TIME; the harness cannot enforce it "
        "inside a backend it did not write."
    )

    return MetricBundle(
        run=run,
        measurements=measurements,
        conservation=conservation(
            results, split_policy_id=split, expected_runs=len(corpus.queries)
        ),
        bonded=bonded_fatalities_all_blocking(results, split_policy_id=split),
        ranks=rank_distribution(results, split_policy_id=split, severity=5),
        notes=tuple(notes),
    )
