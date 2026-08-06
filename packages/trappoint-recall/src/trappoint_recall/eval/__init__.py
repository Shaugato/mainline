# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""The recall evaluation harness.

This subpackage settles the product's central empirical bet — whether ``P@block >=
0.75`` is reachable at ``Retro-Recall@3 >= 0.90`` on fatal precursors — and it is built
first, red, deliberately.

It implements **no retrieval**. No embedding, no SQL, no vector arm, no model call.
That is not an omission: the harness grades work it did not write, and a harness that
shared code with the retriever would grade its own bugs as passes.

Public surface::

    Measurement           a point estimate that cannot be separated from its interval
    SplitPolicy           the time wall, enforced by predicates, never by AS OF SYSTEM TIME
    QrelSet / Judgement   graded relevance on the UMBRELA 0-3 scale
    RetrievalBackend      the contract an implementation must satisfy to be measured
    run_evaluation        drive a backend over a corpus
    compute_metrics       every metric, in one bundle
    evaluate_g4alpha      the five release gates
    AblationTable         the published configuration matrix
"""

from __future__ import annotations

from trappoint_recall.eval.ablation import (
    DEFAULT_MATRIX,
    AblationArm,
    AblationRow,
    AblationTable,
    BackendFactory,
    run_ablation,
    run_ablation_sync,
)
from trappoint_recall.eval.backend import (
    BLOCKING_CAP_PROBABILISTIC,
    ConservingBackend,
    NullBackend,
    QueryResult,
    RetrievalBackend,
    RunTally,
    ScoredCandidate,
)
from trappoint_recall.eval.corpus import EvalCorpus, EvalQuery, load_corpus
from trappoint_recall.eval.gates import (
    G4ALPHA_GATE_IDS,
    GateResult,
    evaluate_g4alpha,
    load_floors,
    overall_status,
)
from trappoint_recall.eval.harness import (
    EvaluationRun,
    MetricBundle,
    compute_metrics,
    run_evaluation,
    run_evaluation_sync,
)
from trappoint_recall.eval.measurement import Measurement, wilson_interval
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
from trappoint_recall.eval.qrels import Judgement, QrelSet, load_qrels_jsonl
from trappoint_recall.eval.splits import (
    AsOfSystemTimeRefused,
    SplitPolicy,
    SplitRecord,
    refuse_as_of_system_time,
    temporally_blocked_split,
)

__all__ = [
    "BLOCKING_CAP_PROBABILISTIC",
    "DEFAULT_MATRIX",
    "G4ALPHA_GATE_IDS",
    "AblationArm",
    "AblationRow",
    "AblationTable",
    "AsOfSystemTimeRefused",
    "BackendFactory",
    "BondedFatalityReport",
    "ConservationReport",
    "ConservingBackend",
    "EvalCorpus",
    "EvalQuery",
    "EvaluationRun",
    "GateResult",
    "Judgement",
    "Measurement",
    "MetricBundle",
    "NullBackend",
    "QrelSet",
    "QueryResult",
    "RankDistribution",
    "RetrievalBackend",
    "RunTally",
    "ScoredCandidate",
    "SplitPolicy",
    "SplitRecord",
    "bonded_fatalities_all_blocking",
    "compute_metrics",
    "conservation",
    "evaluate_g4alpha",
    "load_corpus",
    "load_floors",
    "load_qrels_jsonl",
    "mean_blocking_checks_per_permit",
    "mrr",
    "ndcg_at_k",
    "nuisance_rate",
    "overall_status",
    "p_at_block",
    "rank_distribution",
    "recall_at_k",
    "refuse_as_of_system_time",
    "retro_recall_at_k",
    "run_ablation",
    "run_ablation_sync",
    "run_evaluation",
    "run_evaluation_sync",
    "temporally_blocked_split",
    "wilson_interval",
]
