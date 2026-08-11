# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""The frozen feature spec: pinned order, pinned digest, and no slot for severity."""

from __future__ import annotations

import json

import pytest

from trappoint_recall.fusion.featurespec import (
    FACET_SLOT_COUNT,
    FEATURE_NAMES,
    FEATURE_SPEC,
    FEATURE_SPEC_SHA256,
    FEATURE_SPEC_VERSION,
    FEATURE_WIDTH,
    RERANK_NOT_RANKED,
    RERANK_RELEVANT,
    FeatureVector,
    InvalidFeatureVector,
    build_features,
    facet_onehot,
    raw_score,
)

FACETS = ("mechanism", "precondition", "control_failure", "recurrence_test", "narrative")

#: The digest committed on the day the spec was frozen. A change to the slot order, the slot
#: names or the arity moves it, every stored feature vector stops being comparable, and every
#: fitted calibrator is void. That is the intended cost, and this is where it is paid.
PINNED_FEATURE_SPEC_SHA256 = "9fa06c7afa0326d81c3b2b75f15e48adf014dec519f592ff2563c6ffb2328eb5"


def _vector(**overrides: object) -> FeatureVector:
    kwargs: dict[str, object] = {
        "rrf_score": 0.0246,
        "best_arm_rank": 1,
        "scope_level": 3,
        "facet": "mechanism",
        "facet_vocabulary": FACETS,
        "rerank_verdict": RERANK_RELEVANT,
        "rerank_confidence": 1.0,
        "control_class_overlap": 0.5,
        "asset_class_match": True,
        "channel_mask": 5,
        "coarse_only": False,
    }
    kwargs.update(overrides)
    return build_features(**kwargs)  # type: ignore[arg-type]


# --------------------------------------------------------------------------------------
# Frozen
# --------------------------------------------------------------------------------------


@pytest.mark.frozen
def test_the_slot_order_is_the_one_the_architecture_specifies() -> None:
    assert FEATURE_NAMES == (
        "rrf_score",
        "best_arm_rank",
        "scope_level",
        "facet_onehot_0",
        "facet_onehot_1",
        "facet_onehot_2",
        "facet_onehot_3",
        "facet_onehot_4",
        "rerank_verdict",
        "rerank_confidence",
        "control_class_overlap",
        "asset_class_match",
        "channel_mask",
        "coarse_only",
    )
    assert FEATURE_WIDTH == 14
    assert FACET_SLOT_COUNT == 5


@pytest.mark.frozen
def test_the_spec_digest_is_pinned() -> None:
    assert FEATURE_SPEC_SHA256 == PINNED_FEATURE_SPEC_SHA256


def test_the_digest_covers_the_slot_names_and_not_the_prose() -> None:
    """The notes are documentation. Making them part of the digest would void every stored
    vector on a typo fix, which trains people to stop fixing typos."""
    assert all("note" not in slot.spec_entry() for slot in FEATURE_SPEC)
    assert {"name", "kind"} == set(FEATURE_SPEC[0].spec_entry())


# --------------------------------------------------------------------------------------
# Severity has no slot. This is the load-bearing assertion of the module.
# --------------------------------------------------------------------------------------


def test_no_feature_slot_mentions_severity() -> None:
    """Severity lowers the evidence bar downstream. If it were a feature it would flow
    through the calibrator and come out as an inflated probability shown to a supervisor."""
    assert not any("severity" in name.lower() for name in FEATURE_NAMES)


def test_a_severity_weight_cannot_be_smuggled_into_the_raw_score() -> None:
    with pytest.raises(InvalidFeatureVector, match="severity"):
        raw_score(_vector(), {"rrf_score": 1.0, "severity": 0.5})


def test_any_unknown_weight_is_refused_not_ignored() -> None:
    with pytest.raises(InvalidFeatureVector, match="unknown feature weight"):
        raw_score(_vector(), {"recency_boost": 1.0})


# --------------------------------------------------------------------------------------
# Construction and validation
# --------------------------------------------------------------------------------------


def test_the_one_hot_lands_in_the_slot_the_vocabulary_names() -> None:
    assert facet_onehot("mechanism", FACETS) == (1.0, 0.0, 0.0, 0.0, 0.0)
    assert facet_onehot("narrative", FACETS) == (0.0, 0.0, 0.0, 0.0, 1.0)


def test_an_unknown_facet_is_refused_rather_than_encoded_as_all_zeros() -> None:
    with pytest.raises(InvalidFeatureVector, match="not in the declared vocabulary"):
        facet_onehot("thermal_runaway", FACETS)


def test_a_vocabulary_of_the_wrong_size_is_refused() -> None:
    with pytest.raises(InvalidFeatureVector, match="exactly 5 entries"):
        facet_onehot("mechanism", ("mechanism", "precondition"))


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("best_arm_rank", -1, "1-based"),
        ("scope_level", -2, "non-negative"),
        ("rerank_verdict", 0.5, "rerank_verdict"),
        ("rerank_confidence", 1.4, "rerank_confidence"),
        ("control_class_overlap", -0.1, "Jaccard"),
        ("channel_mask", 8, "3-bit mask"),
    ],
)
def test_out_of_domain_values_are_refused_never_clamped(
    field: str, value: object, message: str
) -> None:
    with pytest.raises(InvalidFeatureVector, match=message):
        _vector(**{field: value})


def test_not_ranked_is_distinct_from_not_relevant() -> None:
    """*Not asked* and *asked and refused* must not be the same number."""
    not_ranked = _vector(rerank_verdict=RERANK_NOT_RANKED, rerank_confidence=0.0)
    not_relevant = _vector(rerank_verdict=0.0, rerank_confidence=0.0)
    assert (
        not_ranked.as_mapping()["rerank_verdict"] != (not_relevant.as_mapping()["rerank_verdict"])
    )


# --------------------------------------------------------------------------------------
# The stored payload
# --------------------------------------------------------------------------------------


def test_the_stored_payload_carries_both_digests_and_round_trips() -> None:
    vector = _vector()
    payload = json.loads(json.dumps(vector.to_json()))
    assert payload["feature_spec"] == FEATURE_SPEC_VERSION
    assert payload["feature_spec_sha256"] == FEATURE_SPEC_SHA256
    assert payload["facet_vocabulary"] == list(FACETS)
    assert payload["facet_vocabulary_sha256"]
    assert payload["names"] == list(FEATURE_NAMES)
    assert FeatureVector.from_json(payload).values == vector.values


def test_a_vector_stored_under_a_different_spec_is_refused() -> None:
    payload = _vector().to_json()
    payload["feature_spec_sha256"] = "0" * 64
    with pytest.raises(InvalidFeatureVector, match="not comparable"):
        FeatureVector.from_json(payload)


# --------------------------------------------------------------------------------------
# raw_score
# --------------------------------------------------------------------------------------


def test_raw_score_is_the_plain_weighted_sum_a_reader_can_check() -> None:
    vector = _vector(rrf_score=0.02, control_class_overlap=0.5)
    weights = {"rrf_score": 10.0, "control_class_overlap": 2.0, "rerank_verdict": 1.5}
    assert raw_score(vector, weights) == pytest.approx(0.2 + 1.0 + 1.5, abs=1e-12)


def test_raw_score_is_monotone_in_the_evidence_it_is_weighted_on() -> None:
    weights = {"rrf_score": 10.0, "rerank_verdict": 1.5}
    low = raw_score(_vector(rrf_score=0.01), weights)
    high = raw_score(_vector(rrf_score=0.03), weights)
    assert high > low


def test_an_empty_weight_set_scores_zero_rather_than_guessing() -> None:
    assert raw_score(_vector(), {}) == 0.0
