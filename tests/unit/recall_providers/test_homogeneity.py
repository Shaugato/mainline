# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
"""``assert_homogeneous`` — the refusal that makes two embedding spaces safe to have."""

from __future__ import annotations

from dataclasses import dataclass

import pytest
from mainline_recall_agent.providers.errors import HeterogeneousCorpus
from mainline_recall_agent.providers.homogeneity import (
    assert_homogeneous,
    assert_semantic,
    corpus_identity,
)
from mainline_recall_agent.providers.surrogate import SURROGATE_MODEL_ID


@dataclass
class Row:
    embed_model: str
    index_gen: str


def test_a_single_space_passes_and_returns_its_model() -> None:
    rows = [Row("m", "g1"), Row("m", "g1")]
    assert assert_homogeneous(rows) == "m"


def test_mixed_models_are_refused() -> None:
    rows = [Row("titan", "g1"), Row("bge", "g1")]
    with pytest.raises(HeterogeneousCorpus, match="mixes embedding models"):
        assert_homogeneous(rows)


def test_mixed_index_generations_are_refused_when_required() -> None:
    rows = [Row("m", "g1"), Row("m", "g2")]
    assert_homogeneous(rows)  # models agree
    with pytest.raises(HeterogeneousCorpus, match="index generation"):
        assert_homogeneous(rows, require_index_gen=True)


def test_a_provisional_and_a_fitted_projection_are_different_spaces() -> None:
    """The projection id is folded into ``index_gen`` precisely so this is detectable."""
    rows = [
        Row("BAAI/bge-large-en-v1.5@abc", "bge-1+coarse256.provisional-ternary.1"),
        Row("BAAI/bge-large-en-v1.5@abc", "bge-1+coarse256.pca.1"),
    ]
    with pytest.raises(HeterogeneousCorpus):
        assert_homogeneous(rows, require_index_gen=True)


def test_dicts_and_objects_are_both_readable() -> None:
    rows = [{"embed_model": "m", "index_gen": "g"}, Row("m", "g")]
    assert assert_homogeneous(rows, require_index_gen=True) == "m"


def test_an_unlabelled_row_is_refused() -> None:
    with pytest.raises(HeterogeneousCorpus, match="no embed_model"):
        assert_homogeneous([{"vector": [0.1]}])


def test_an_empty_corpus_is_refused_rather_than_vacuously_homogeneous() -> None:
    with pytest.raises(HeterogeneousCorpus, match="empty corpus"):
        assert_homogeneous([])


def test_corpus_identity_reports_both_dimensions() -> None:
    models, generations = corpus_identity([Row("m", "g1"), Row("m", "g2")])
    assert models == {"m"}
    assert generations == {"g1", "g2"}


def test_the_surrogate_space_cannot_be_scored() -> None:
    with pytest.raises(HeterogeneousCorpus, match="must not be published"):
        assert_semantic(SURROGATE_MODEL_ID)


def test_a_real_space_may_be_scored() -> None:
    assert_semantic("BAAI/bge-large-en-v1.5@abc")
