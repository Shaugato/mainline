# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""Fusion, calibration and admission — pure functions, no database, no model client.

The path from four retrieval channels to an integer on ``permit.open_blocking``::

    channels C, C_sweep, D  ->  rrf.reciprocal_rank_fusion   (A and B bypass entirely)
                            ->  mmr.maximal_marginal_relevance   (siblings kept, ledgered)
                            ->  [listwise rerank, in the vertical: it needs a model]
                            ->  featurespec.build_features / raw_score
                            ->  calibration.IsotonicCalibrator.predict  ->  p_relevant
                            ->  sga.admit  ->  blocking / advisory / silenced + silence rows

Everything in this subpackage is a pure function over value objects. There is no session, no
connection, no client and no clock on the hot path, for one reason: this is the arithmetic
that decides whether a fatality is raised, and it has to be runnable — and arguable — by a
stranger holding nothing but the policy row and the candidate set.

The vertical half of the pipeline (the listwise judge, which needs a model and therefore a
region, an account and a residency argument) lives in
``mainline_recall_agent.rerank`` under FSL-1.1-ALv2.
"""

from __future__ import annotations

from trappoint_recall.fusion.calibration import (
    CALIBRATOR_SCHEMA,
    CalibrationRefused,
    CalibrationReport,
    CalibrationSample,
    IsotonicCalibrator,
    ReliabilityBin,
    assert_disjoint_folds,
    brier_score,
    calibration_report,
    evaluate_knots,
    expected_calibration_error,
    fit_isotonic,
    maximum_calibration_error,
    reliability_diagram,
)
from trappoint_recall.fusion.featurespec import (
    FEATURE_NAMES,
    FEATURE_SPEC,
    FEATURE_SPEC_SHA256,
    FEATURE_SPEC_VERSION,
    FEATURE_WIDTH,
    FeatureSlot,
    FeatureVector,
    InvalidFeatureVector,
    build_features,
    facet_onehot,
    raw_score,
)
from trappoint_recall.fusion.mmr import (
    DEFAULT_LAMBDA,
    DEFAULT_REDUNDANCY_THRESHOLD,
    InvalidMmrInput,
    MmrCandidate,
    MmrSelection,
    Representative,
    SuppressedSibling,
    cosine_similarity,
    maximal_marginal_relevance,
)
from trappoint_recall.fusion.rrf import (
    RRF_K,
    ArmRanking,
    ChannelBypassesFusion,
    Contribution,
    FusedCandidate,
    InvalidRanking,
    rank_from_scores,
    reciprocal_rank_fusion,
)
from trappoint_recall.fusion.sga import (
    BLOCKING_CAP_PROBABILISTIC,
    DEFAULT_NUISANCE_CEILING,
    DEFAULT_TAU,
    EXCHANGEABILITY_ASSUMPTION,
    AdmissionCandidate,
    AdmissionRefused,
    AdmissionResult,
    AdmittedCheck,
    ComposedTau,
    LttResult,
    PrecisionFloorResult,
    SilenceRecord,
    TauTable,
    admit,
    compose_tau,
    compose_tau_table,
    hoeffding_bentkus_pvalue,
    learn_then_test_tau,
    precision_floor_tau,
)

__all__ = [
    "BLOCKING_CAP_PROBABILISTIC",
    "CALIBRATOR_SCHEMA",
    "DEFAULT_LAMBDA",
    "DEFAULT_NUISANCE_CEILING",
    "DEFAULT_REDUNDANCY_THRESHOLD",
    "DEFAULT_TAU",
    "EXCHANGEABILITY_ASSUMPTION",
    "FEATURE_NAMES",
    "FEATURE_SPEC",
    "FEATURE_SPEC_SHA256",
    "FEATURE_SPEC_VERSION",
    "FEATURE_WIDTH",
    "RRF_K",
    "AdmissionCandidate",
    "AdmissionRefused",
    "AdmissionResult",
    "AdmittedCheck",
    "ArmRanking",
    "CalibrationRefused",
    "CalibrationReport",
    "CalibrationSample",
    "ChannelBypassesFusion",
    "ComposedTau",
    "Contribution",
    "FeatureSlot",
    "FeatureVector",
    "FusedCandidate",
    "InvalidFeatureVector",
    "InvalidMmrInput",
    "InvalidRanking",
    "IsotonicCalibrator",
    "LttResult",
    "MmrCandidate",
    "MmrSelection",
    "PrecisionFloorResult",
    "ReliabilityBin",
    "Representative",
    "SilenceRecord",
    "SuppressedSibling",
    "TauTable",
    "admit",
    "assert_disjoint_folds",
    "brier_score",
    "build_features",
    "calibration_report",
    "compose_tau",
    "compose_tau_table",
    "cosine_similarity",
    "evaluate_knots",
    "expected_calibration_error",
    "facet_onehot",
    "fit_isotonic",
    "hoeffding_bentkus_pvalue",
    "learn_then_test_tau",
    "maximal_marginal_relevance",
    "maximum_calibration_error",
    "precision_floor_tau",
    "rank_from_scores",
    "raw_score",
    "reciprocal_rank_fusion",
    "reliability_diagram",
]
