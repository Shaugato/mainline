# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
"""The offline embedding path over the committed fixture corpus.

``done_when``: with no AWS credentials and no network, the fixture corpus yields 1024-d
unit vectors and deterministic 256-d coarse vectors.  The semantic providers are exercised
where they can be (identity, pinning, coarse arithmetic, refusals) and skipped — loudly,
with a reason — where they cannot.
"""

from __future__ import annotations

import json
import math
from typing import Any

import pytest
from mainline_recall_agent.providers.base import embed_text
from mainline_recall_agent.providers.errors import (
    EmptyEmbeddingInput,
    ProviderError,
    ProviderUnavailable,
)
from mainline_recall_agent.providers.homogeneity import assert_semantic, is_non_semantic
from mainline_recall_agent.providers.local_bge import LocalBGE
from mainline_recall_agent.providers.registry import get_embedding_provider
from mainline_recall_agent.providers.surrogate import SURROGATE_MODEL_ID, SurrogateEmbedder
from mainline_recall_agent.providers.types import COARSE_DIM, EMBED_DIM, FACETS
from mainline_recall_agent.providers.vectors import is_unit


def _corpus_texts(corpus: list[dict[str, Any]], facet: str) -> list[str]:
    return [
        embed_text(
            activity_path=entry["activity_path"],
            asset_class=entry["asset_class"],
            facet=facet,
            cue_text=entry["facets"][facet],
        )
        for entry in corpus
    ]


# --------------------------------------------------------------------------------------
# The offline path — this is the done_when assertion.
# --------------------------------------------------------------------------------------


def test_fixture_corpus_yields_unit_1024d_vectors(fixture_corpus: list[dict[str, Any]]) -> None:
    embedder = SurrogateEmbedder()
    for facet in FACETS:
        vectors = embedder.embed(_corpus_texts(fixture_corpus, facet), facet)
        assert len(vectors) == len(fixture_corpus)
        for vector in vectors:
            assert len(vector) == EMBED_DIM
            assert is_unit(vector)


def test_fixture_corpus_yields_deterministic_256d_coarse_vectors(
    fixture_corpus: list[dict[str, Any]],
) -> None:
    texts = _corpus_texts(fixture_corpus, "mechanism")
    first = SurrogateEmbedder().coarse(SurrogateEmbedder().embed(texts, "mechanism"))
    second = SurrogateEmbedder().coarse(SurrogateEmbedder().embed(texts, "mechanism"))
    assert first == second
    for vector in first:
        assert len(vector) == COARSE_DIM
        assert is_unit(vector)


def test_coarse_vectors_are_distinct_across_the_corpus(
    fixture_corpus: list[dict[str, Any]],
) -> None:
    embedder = SurrogateEmbedder()
    texts = _corpus_texts(fixture_corpus, "mechanism")
    coarse = embedder.coarse(embedder.embed(texts, "mechanism"))
    for i in range(len(coarse)):
        for j in range(i + 1, len(coarse)):
            cosine = math.fsum(a * b for a, b in zip(coarse[i], coarse[j], strict=True))
            assert cosine < 0.999, f"cues {i} and {j} collapsed onto one coarse point"


def test_the_surrogate_declares_itself_non_semantic_and_cannot_be_scored() -> None:
    """The one property that keeps an offline run from becoming a published number."""
    embedder = SurrogateEmbedder()
    assert embedder.model_id == SURROGATE_MODEL_ID
    assert embedder.is_semantic is False
    assert is_non_semantic(embedder.model_id)
    with pytest.raises(Exception, match="NON-SEMANTIC"):
        assert_semantic(embedder.model_id)


def test_facet_changes_the_vector(fixture_corpus: list[dict[str, Any]]) -> None:
    """Five facets of one cue must occupy five points, as they would under a real model."""
    entry = fixture_corpus[0]
    embedder = SurrogateEmbedder()
    vectors = {
        facet: embedder.embed(
            [
                embed_text(
                    activity_path=entry["activity_path"],
                    asset_class=entry["asset_class"],
                    facet=facet,
                    cue_text=entry["facets"][facet],
                )
            ],
            facet,
        )[0]
        for facet in FACETS
    }
    seen = {tuple(v) for v in vectors.values()}
    assert len(seen) == len(FACETS)


def test_the_same_text_under_two_facets_still_differs() -> None:
    """Facet salting, isolated from any text difference."""
    embedder = SurrogateEmbedder()
    text = "loss of containment of a corrosive liquid at a coupling"
    a = embedder.embed([text], "mechanism")[0]
    b = embedder.embed([text], "precondition")[0]
    assert a != b


def test_index_gen_pins_the_projection_identity() -> None:
    embedder = SurrogateEmbedder()
    assert embedder.index_gen.endswith("provisional-ternary.1")


# --------------------------------------------------------------------------------------
# Input discipline
# --------------------------------------------------------------------------------------


def test_blank_and_punctuation_only_cues_are_refused() -> None:
    embedder = SurrogateEmbedder()
    with pytest.raises(EmptyEmbeddingInput):
        embedder.embed(["   "], "mechanism")
    with pytest.raises(EmptyEmbeddingInput):
        embedder.embed(["--- ... ---"], "mechanism")
    with pytest.raises(EmptyEmbeddingInput):
        embedder.embed([], "mechanism")


def test_unknown_facet_is_refused() -> None:
    with pytest.raises(ProviderError):
        SurrogateEmbedder().embed(["anything"], "vibes")


def test_over_long_input_is_refused_rather_than_truncated() -> None:
    with pytest.raises(ProviderError, match="refusing rather than"):
        SurrogateEmbedder().embed(["word " * 4000], "narrative")


def test_the_embedding_template_is_the_d3_template() -> None:
    composed = embed_text(
        activity_path="surface/processing/leach",
        asset_class="fixed_plant_vessel",
        facet="mechanism",
        cue_text="cyanide-bearing solution met acidic wash water",
    )
    assert composed == (
        "surface/processing/leach | fixed_plant_vessel | mechanism: "
        "cyanide-bearing solution met acidic wash water"
    )


# --------------------------------------------------------------------------------------
# LocalBGE — pinning is enforced here; encoding is skipped, with a reason.
# --------------------------------------------------------------------------------------


def test_local_bge_refuses_to_construct_without_a_pinned_revision() -> None:
    with pytest.raises(ProviderError, match="not a pin"):
        LocalBGE()


def test_local_bge_reports_a_model_id_that_carries_the_revision() -> None:
    class _FakeEncoder:
        def encode(self, texts: list[str], **_: Any) -> list[list[float]]:
            return [[0.0] * (EMBED_DIM - 1) + [1.0] for _ in texts]

    provider = LocalBGE(revision="deadbeefcafe", encoder=_FakeEncoder())
    assert provider.model_id == "BAAI/bge-large-en-v1.5@deadbeefcafe"
    assert provider.is_semantic is True
    vectors = provider.embed(["a cue about stored energy release"], "mechanism")
    assert len(vectors[0]) == EMBED_DIM
    assert is_unit(vectors[0])
    coarse = provider.coarse(vectors)
    assert len(coarse[0]) == COARSE_DIM
    assert is_unit(coarse[0])


def test_local_bge_query_side_applies_the_retrieval_instruction() -> None:
    seen: list[str] = []

    class _CapturingEncoder:
        def encode(self, texts: list[str], **_: Any) -> list[list[float]]:
            seen.extend(texts)
            return [[1.0] + [0.0] * (EMBED_DIM - 1) for _ in texts]

    provider = LocalBGE(revision="deadbeefcafe", encoder=_CapturingEncoder())
    provider.embed(["permit side cue"], "mechanism", side="query")
    provider.embed(["event side cue"], "mechanism", side="document")
    assert seen[0].startswith("Represent this sentence for searching relevant passages: ")
    assert not seen[1].startswith("Represent this sentence")


def test_local_bge_with_real_weights() -> None:
    """Skipped without the weights — never faked, because a fake would be a false number."""
    pytest.importorskip(
        "sentence_transformers",
        reason="sentence-transformers is the 'local-embed' extra and the bge-large weights "
        "are a network fetch; neither is available offline. Install the extra, warm the "
        "cache, then run with MAINLINE_BGE_REVISION set.",
    )
    import os

    revision = os.environ.get("MAINLINE_BGE_REVISION")
    if not revision:
        pytest.skip("MAINLINE_BGE_REVISION is not set: no pinned weights revision to test")
    provider = LocalBGE(revision=revision)
    vectors = provider.embed(["stored energy release during a mill reline"], "mechanism")
    assert len(vectors[0]) == EMBED_DIM
    assert is_unit(vectors[0])


# --------------------------------------------------------------------------------------
# Titan — residency and coarse arithmetic, with a stub client (no live call).
# --------------------------------------------------------------------------------------


def test_titan_refuses_a_foreign_region() -> None:
    from mainline_recall_agent.providers.bedrock_titan import BedrockTitanV2

    with pytest.raises(ProviderError, match="residency"):
        BedrockTitanV2(region="us-east-1")


def test_titan_uses_matryoshka_truncation_for_coarse() -> None:
    from mainline_recall_agent.providers.bedrock_titan import BedrockTitanV2

    class _StubClient:
        def __init__(self) -> None:
            self.calls: list[dict[str, Any]] = []

        def invoke_model(self, **kwargs: Any) -> dict[str, Any]:
            self.calls.append(kwargs)
            raw = [math.sin(i * 0.11) + 0.001 * i + 1.0 for i in range(EMBED_DIM)]
            return {"body": json.dumps({"embedding": raw}).encode("utf-8")}

    client = _StubClient()
    provider = BedrockTitanV2(client=client)
    vectors = provider.embed(["a cue about gas liberation"], "mechanism")
    assert is_unit(vectors[0])
    body = json.loads(client.calls[0]["body"])
    assert body["dimensions"] == EMBED_DIM
    assert body["normalize"] is True

    coarse = provider.coarse(vectors)
    assert len(coarse[0]) == COARSE_DIM
    assert is_unit(coarse[0])
    # Truncation preserves direction: coarse is a rescaled prefix of the full vector.
    scale = coarse[0][0] / vectors[0][0]
    for a, b in zip(coarse[0], vectors[0][:COARSE_DIM], strict=True):
        assert abs(a - b * scale) < 1e-6


def test_titan_without_a_client_reports_unavailable_not_a_refusal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from mainline_recall_agent.providers import bedrock_titan

    provider = bedrock_titan.BedrockTitanV2()
    monkeypatch.setattr(
        provider, "_bedrock", lambda: (_ for _ in ()).throw(ProviderUnavailable("no creds"))
    )
    with pytest.raises(ProviderUnavailable) as excinfo:
        provider.embed(["x y z"], "mechanism")
    assert excinfo.value.silence_reason == "unreachable"


# --------------------------------------------------------------------------------------
# Registry
# --------------------------------------------------------------------------------------


def test_registry_default_is_the_offline_surrogate() -> None:
    provider = get_embedding_provider()
    assert provider.model_id == SURROGATE_MODEL_ID
    assert provider.is_semantic is False


def test_registry_rejects_an_unknown_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MAINLINE_RECALL_PROVIDER", "whatever")
    with pytest.raises(ProviderError):
        get_embedding_provider()
