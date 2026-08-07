# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""RRF: scale invariance, weighting, determinism, and the refusal of channels A and B."""

from __future__ import annotations

import math

import pytest

from trappoint_recall.fusion.rrf import (
    CHANNEL_BIT,
    RRF_K,
    ArmRanking,
    ChannelBypassesFusion,
    InvalidRanking,
    rank_from_scores,
    reciprocal_rank_fusion,
)

COSINE_ARM = {"E1": 0.91, "E2": 0.88, "E3": 0.42, "E4": 0.41}
BM25_ARM = {"E3": 27.4, "E1": 11.9, "E5": 3.2}


def _arms(
    cosine: dict[str, float], bm25: dict[str, float], *, weight_c: float = 1.0
) -> list[ArmRanking]:
    return [
        ArmRanking(
            arm_id="lvl3-mechanism",
            channel="C",
            weight=weight_c,
            doc_ids=rank_from_scores(cosine),
        ),
        ArmRanking(arm_id="bm25", channel="D", weight=0.6, doc_ids=rank_from_scores(bm25)),
    ]


# --------------------------------------------------------------------------------------
# Scale invariance — the property that removes the hidden tuning knob
# --------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "transform",
    [
        pytest.param(lambda v: v * 1000.0, id="linear_gain"),
        pytest.param(lambda v: v / 137.0, id="linear_attenuation"),
        pytest.param(lambda v: v + 4.5, id="offset"),
        pytest.param(math.log1p, id="log1p"),
        pytest.param(lambda v: v**3, id="cube"),
    ],
)
def test_fusion_is_invariant_under_any_strictly_increasing_rescaling(transform) -> None:  # type: ignore[no-untyped-def]
    """A cosine arm and a BM25 arm live on different scales. RRF must not care.

    If this ever fails, some raw magnitude has leaked into the fuser and the relative
    weighting of two channels has silently become a function of their score distributions.
    """
    baseline = reciprocal_rank_fusion(_arms(COSINE_ARM, BM25_ARM))
    rescaled = reciprocal_rank_fusion(
        _arms(
            {k: transform(v) for k, v in COSINE_ARM.items()},
            {k: transform(v) for k, v in BM25_ARM.items()},
        )
    )
    assert [c.doc_id for c in baseline] == [c.doc_id for c in rescaled]
    assert [c.rrf_score for c in baseline] == [c.rrf_score for c in rescaled]


def test_rank_from_scores_orders_descending_and_breaks_ties_on_doc_id() -> None:
    assert rank_from_scores({"b": 1.0, "a": 1.0, "c": 2.0}) == ("c", "a", "b")


def test_rank_from_scores_handles_a_distance_arm() -> None:
    assert rank_from_scores({"far": 0.9, "near": 0.1}, descending=False) == ("near", "far")


def test_rank_from_scores_refuses_a_repeated_document_or_a_nan() -> None:
    with pytest.raises(InvalidRanking, match="twice"):
        rank_from_scores([("a", 1.0), ("a", 2.0)])
    with pytest.raises(InvalidRanking, match="non-finite"):
        rank_from_scores({"a": float("nan")})


# --------------------------------------------------------------------------------------
# The arithmetic
# --------------------------------------------------------------------------------------


def test_the_score_is_the_weighted_sum_of_reciprocal_ranks() -> None:
    fused = reciprocal_rank_fusion(_arms(COSINE_ARM, BM25_ARM))
    by_id = {c.doc_id: c for c in fused}
    # E1 is rank 1 on the cosine arm (weight 1.0) and rank 2 on BM25 (weight 0.6).
    expected = 1.0 / (RRF_K + 1) + 0.6 / (RRF_K + 2)
    assert by_id["E1"].rrf_score == pytest.approx(expected, abs=1e-15)
    assert by_id["E1"].best_arm_rank == 1


def test_every_contribution_is_retained_so_the_score_can_be_argued_with() -> None:
    fused = reciprocal_rank_fusion(_arms(COSINE_ARM, BM25_ARM))
    by_id = {c.doc_id: c for c in fused}
    assert {c.arm_id for c in by_id["E1"].contributions} == {"lvl3-mechanism", "bm25"}
    assert sum(c.increment for c in by_id["E1"].contributions) == pytest.approx(
        by_id["E1"].rrf_score, abs=1e-15
    )


def test_a_heavier_arm_weight_moves_the_ranking() -> None:
    """Arm weights come from the signed policy row, so they must actually do something."""
    light = reciprocal_rank_fusion(_arms(COSINE_ARM, BM25_ARM, weight_c=0.1))
    heavy = reciprocal_rank_fusion(_arms(COSINE_ARM, BM25_ARM, weight_c=10.0))
    assert light[0].doc_id == "E3"
    assert heavy[0].doc_id == "E1"


def test_ranks_are_dense_and_one_based() -> None:
    fused = reciprocal_rank_fusion(_arms(COSINE_ARM, BM25_ARM))
    assert [c.rank for c in fused] == list(range(1, len(fused) + 1))


def test_the_order_is_deterministic_under_an_exact_score_tie() -> None:
    arms = [
        ArmRanking(arm_id="a1", channel="C", weight=1.0, doc_ids=("z", "y")),
        ArmRanking(arm_id="a2", channel="D", weight=1.0, doc_ids=("y", "z")),
    ]
    first = reciprocal_rank_fusion(arms)
    second = reciprocal_rank_fusion(list(reversed(arms)))
    assert [c.doc_id for c in first] == [c.doc_id for c in second] == ["y", "z"]


# --------------------------------------------------------------------------------------
# Channel bookkeeping
# --------------------------------------------------------------------------------------


def test_the_channel_mask_records_which_channels_agreed() -> None:
    fused = reciprocal_rank_fusion(_arms(COSINE_ARM, BM25_ARM))
    by_id = {c.doc_id: c for c in fused}
    assert by_id["E1"].channel_mask == CHANNEL_BIT["C"] | CHANNEL_BIT["D"]
    assert by_id["E5"].channel_mask == CHANNEL_BIT["D"]
    assert set(by_id["E1"].channels) == {"C", "D"}


def test_coarse_only_is_true_only_when_the_sweep_stood_alone() -> None:
    fused = reciprocal_rank_fusion(
        [
            ArmRanking(arm_id="sweep", channel="C_sweep", weight=0.3, doc_ids=("E9", "E1")),
            ArmRanking(arm_id="lvl2", channel="C", weight=1.0, doc_ids=("E1",)),
        ]
    )
    by_id = {c.doc_id: c for c in fused}
    assert by_id["E9"].coarse_only is True
    assert by_id["E1"].coarse_only is False


# --------------------------------------------------------------------------------------
# Channels A and B never enter fusion
# --------------------------------------------------------------------------------------


@pytest.mark.parametrize("channel", ["A", "B"])
def test_deterministic_and_bonded_channels_are_refused(channel: str) -> None:
    """MI16 lives in the schema, not in a weight. Fusing B would put it in a weight."""
    with pytest.raises(ChannelBypassesFusion, match="admitted unconditionally"):
        ArmRanking(arm_id="x", channel=channel, weight=1.0, doc_ids=("E1",))


def test_an_unknown_channel_is_refused_rather_than_defaulted() -> None:
    with pytest.raises(InvalidRanking, match="unknown channel"):
        ArmRanking(arm_id="x", channel="E", weight=1.0, doc_ids=("E1",))


# --------------------------------------------------------------------------------------
# Malformed input
# --------------------------------------------------------------------------------------


@pytest.mark.parametrize("weight", [0.0, -1.0, float("inf"), float("nan")])
def test_a_non_positive_or_non_finite_weight_is_refused(weight: float) -> None:
    with pytest.raises(InvalidRanking, match="weight"):
        ArmRanking(arm_id="x", channel="C", weight=weight, doc_ids=("E1",))


def test_one_arm_may_not_return_the_same_document_twice() -> None:
    with pytest.raises(InvalidRanking, match="twice"):
        ArmRanking(arm_id="x", channel="C", weight=1.0, doc_ids=("E1", "E1"))


def test_two_rankings_may_not_share_an_arm_id() -> None:
    with pytest.raises(InvalidRanking, match="appears twice"):
        reciprocal_rank_fusion(
            [
                ArmRanking(arm_id="dup", channel="C", weight=1.0, doc_ids=("E1",)),
                ArmRanking(arm_id="dup", channel="D", weight=1.0, doc_ids=("E2",)),
            ]
        )


def test_a_non_positive_k_is_refused() -> None:
    with pytest.raises(InvalidRanking, match="k must be positive"):
        reciprocal_rank_fusion(_arms(COSINE_ARM, BM25_ARM), k=0)


def test_fusing_nothing_returns_nothing_rather_than_raising() -> None:
    assert reciprocal_rank_fusion([]) == ()
