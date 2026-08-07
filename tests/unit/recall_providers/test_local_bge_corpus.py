# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
"""``LocalBGE`` driven over the committed fixture corpus, and the anti-truncation proof.

**What this file proves, and what it deliberately does not.**  The bge-large weights are a
network fetch and are absent here, so the encoder is a declared stub.  Every assertion
below is therefore about *our* code — input validation, L2 normalisation, float32
rounding, and the committed 1024 -> 256 projection — and about nothing whatsoever
concerning bge's semantics.  ``test_embedding_offline.py::test_local_bge_with_real_weights``
is the one test that would speak for the model, and it skips loudly rather than pretending.

The load-bearing test here is
``test_local_bge_coarse_is_a_projection_and_provably_not_a_truncation``.  recall.md **D4**
says bge is not MRL-trained, so its coarse vector must come from the committed projection
and never from a Matryoshka prefix.  That is a claim about the code, and a claim about the
code that nothing can falsify is a comment.  The test computes what truncation *would* have
produced and requires the shipped result to be materially different — so if someone later
"simplifies" ``LocalBGE.coarse`` to ``matryoshka_coarse``, this goes red, which is the only
form in which D4 survives contact with a refactor.
"""

from __future__ import annotations

import hashlib
import math
from typing import Any

import pytest

from mainline_recall_agent.providers.base import embed_text
from mainline_recall_agent.providers.errors import HeterogeneousCorpus
from mainline_recall_agent.providers.homogeneity import assert_homogeneous
from mainline_recall_agent.providers.local_bge import BGE_MODEL_NAME, LocalBGE
from mainline_recall_agent.providers.surrogate import SURROGATE_MODEL_ID, SurrogateEmbedder
from mainline_recall_agent.providers.types import COARSE_DIM, EMBED_DIM
from mainline_recall_agent.providers.vectors import is_unit, matryoshka_coarse

#: A revision string standing in for the git sha of a fetched weights revision.  It is
#: nonsense on purpose: a test must never look like it pinned real weights.
STUB_REVISION = "stub0000000000000000000000000000000000000"

#: The pair of facets the fixture corpus is richest in.  Two, not five, so the test is
#: about the arithmetic rather than about how long a loop can be.
FACETS_UNDER_TEST = ("mechanism", "recurrence_test")

#: Two independent 256-d directions should be nowhere near parallel.  0.9 is generous by an
#: order of magnitude and is here to catch collapse, not to measure separation.
_COLLAPSE_COSINE = 0.9

#: If ``coarse`` were truncation, this cosine would be 1.0 to float32.  Anything at or above
#: this is truncation-shaped and the projection claim is false.
_TRUNCATION_COSINE = 0.99


class _DeterministicStubEncoder:
    """Stands in for ``SentenceTransformer``.  A stub, and never anything more.

    Produces an unnormalised, text-dependent, platform-independent 1024-d vector.  It is
    unnormalised on purpose: ``LocalBGE`` is constructed with
    ``normalize_embeddings=False`` and must do the normalisation itself, so an encoder that
    returned unit vectors would make that step untestable.
    """

    def __init__(self) -> None:
        self.seen: list[str] = []

    def encode(self, texts: list[str], **_: Any) -> list[list[float]]:
        rows: list[list[float]] = []
        for text in texts:
            self.seen.append(text)
            row: list[float] = []
            counter = 0
            while len(row) < EMBED_DIM:
                block = hashlib.blake2b(
                    counter.to_bytes(4, "big"),
                    key=text.encode("utf-8")[:64],
                    person=b"bge-test-stub",
                    digest_size=64,
                ).digest()
                # Centre on zero so the vector has a direction rather than a bias, and
                # scale away from unit norm so normalisation has something to do.
                row.extend((byte - 127.5) / 6.0 for byte in block)
                counter += 1
            rows.append(row[:EMBED_DIM])
        return rows


def _provider() -> LocalBGE:
    return LocalBGE(revision=STUB_REVISION, encoder=_DeterministicStubEncoder())


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


def _cosine(a: tuple[float, ...], b: tuple[float, ...]) -> float:
    return math.fsum(x * y for x, y in zip(a, b, strict=True))


# --------------------------------------------------------------------------------------
# 1024-d: width, unit norm, determinism
# --------------------------------------------------------------------------------------


@pytest.mark.parametrize("facet", FACETS_UNDER_TEST)
def test_local_bge_yields_unit_1024d_vectors_for_the_fixture_corpus(
    fixture_corpus: list[dict[str, Any]], facet: str
) -> None:
    vectors = _provider().embed(_corpus_texts(fixture_corpus, facet), facet)
    assert len(vectors) == len(fixture_corpus)
    for vector in vectors:
        assert len(vector) == EMBED_DIM
        assert is_unit(vector)


def test_local_bge_is_deterministic_across_independent_constructions(
    fixture_corpus: list[dict[str, Any]],
) -> None:
    """Two providers, two encoders, one answer — or the corpus is not reproducible."""
    texts = _corpus_texts(fixture_corpus, "mechanism")
    assert _provider().embed(texts, "mechanism") == _provider().embed(texts, "mechanism")


def test_local_bge_does_not_prefix_the_document_side(
    fixture_corpus: list[dict[str, Any]],
) -> None:
    """D3 symmetry: the event-cue side is the document side and takes no instruction."""
    encoder = _DeterministicStubEncoder()
    provider = LocalBGE(revision=STUB_REVISION, encoder=encoder)
    texts = _corpus_texts(fixture_corpus, "mechanism")
    provider.embed(texts, "mechanism")
    assert encoder.seen == texts


# --------------------------------------------------------------------------------------
# 256-d: the projection, and the proof that it is not a truncation
# --------------------------------------------------------------------------------------


def test_local_bge_coarse_is_unit_256d_and_deterministic(
    fixture_corpus: list[dict[str, Any]],
) -> None:
    texts = _corpus_texts(fixture_corpus, "mechanism")
    first = _provider()
    second = _provider()
    coarse_a = first.coarse(first.embed(texts, "mechanism"))
    coarse_b = second.coarse(second.embed(texts, "mechanism"))
    assert coarse_a == coarse_b
    for vector in coarse_a:
        assert len(vector) == COARSE_DIM
        assert is_unit(vector)


def test_local_bge_coarse_is_a_projection_and_provably_not_a_truncation(
    fixture_corpus: list[dict[str, Any]],
) -> None:
    """recall.md D4, as a falsifiable assertion rather than a comment.

    The counterfactual is computed in the test: ``matryoshka_coarse`` is what the shipped
    code would return if someone replaced the committed projection with a prefix.  Every
    cue must land somewhere else.
    """
    provider = _provider()
    texts = _corpus_texts(fixture_corpus, "mechanism")
    full = provider.embed(texts, "mechanism")
    projected = provider.coarse(full)
    for cue_index, (fine, coarse) in enumerate(zip(full, projected, strict=True)):
        truncated = matryoshka_coarse(fine)
        cosine = _cosine(coarse, truncated)
        assert cosine < _TRUNCATION_COSINE, (
            f"cue {cue_index}: LocalBGE.coarse agrees with Matryoshka truncation "
            f"(cos={cosine:.4f}). bge is not MRL-trained; truncating it would be a false "
            "claim (recall.md D4)."
        )


def test_local_bge_coarse_keeps_distinct_cues_distinct(
    fixture_corpus: list[dict[str, Any]],
) -> None:
    """A projection that collapsed the corpus would make the coarse sweep useless."""
    provider = _provider()
    texts = _corpus_texts(fixture_corpus, "mechanism")
    coarse = provider.coarse(provider.embed(texts, "mechanism"))
    for i in range(len(coarse)):
        for j in range(i + 1, len(coarse)):
            assert _cosine(coarse[i], coarse[j]) < _COLLAPSE_COSINE


# --------------------------------------------------------------------------------------
# Identity: two spaces, never silently one
# --------------------------------------------------------------------------------------


def test_local_bge_identity_carries_the_revision_and_the_projection() -> None:
    provider = _provider()
    assert provider.model_id == f"{BGE_MODEL_NAME}@{STUB_REVISION}"
    assert provider.is_semantic is True
    # index_gen names the projection, so a corpus coarsened under the provisional ternary
    # map can never be silently compared with one coarsened under a fitted PCA.
    assert provider.index_gen.startswith("bge-1+coarse256.")


def test_a_corpus_mixing_local_bge_and_the_surrogate_is_refused(
    fixture_corpus: list[dict[str, Any]],
) -> None:
    """The two offline providers must be distinguishable, or offline runs are meaningless."""
    bge = _provider()
    surrogate = SurrogateEmbedder()
    assert bge.model_id != surrogate.model_id
    assert surrogate.model_id == SURROGATE_MODEL_ID

    rows = [
        {"embed_model": bge.model_id, "index_gen": bge.index_gen},
        {"embed_model": surrogate.model_id, "index_gen": surrogate.index_gen},
    ]
    with pytest.raises(HeterogeneousCorpus, match="mixes embedding models"):
        assert_homogeneous(rows)
    assert len(fixture_corpus) > 0
