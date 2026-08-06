# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
"""The offline surrogate embedder — declared non-semantic, and named as such everywhere.

Why it exists.  ``LocalBGE`` needs the bge-large weights, which are a network fetch;
``BedrockTitanV2`` needs an AWS account.  Neither is available on a fresh checkout, and
the domain's stated property is that it runs with no cloud account.  So the offline
default is a real, deterministic, dependency-free embedder: feature hashing over
identifier-preserving word tokens and character trigrams, signed, L2-normalised.

What it is not.  It carries **no semantics**.  Two texts about the same hazard are near
each other only if they share surface tokens.  Its ``model_id`` is in
``NON_SEMANTIC_MODEL_IDS``, ``is_semantic`` is ``False``, and ``assert_semantic`` raises
on it — so a retrieval number computed over a surrogate corpus cannot be published by
accident.  It exists to make the *shapes*, the *plumbing* and the *refusals* testable
offline, not to retrieve anything.

It is nonetheless a genuine embedder in the ways that matter for the pipeline: unit norm,
1024-d, deterministic across processes and platforms (blake2b, integer arithmetic), and
facet-salted so that the five facets of one cue occupy five different points exactly as
they would under a real model.
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Sequence
from typing import Final

import numpy as np

from .base import validate_batch
from .errors import EmptyEmbeddingInput
from .projection import DEFAULT_PROJECTION_RESOURCE, load_projection
from .types import COARSE_DIM, EMBED_DIM, Vector256, Vector1024
from .vectors import l2_normalise, to_float32

__all__ = ["SURROGATE_MODEL_ID", "SurrogateEmbedder"]

SURROGATE_MODEL_ID: Final[str] = "mainline-surrogate-hash-v1"

#: Identifier-preserving tokeniser.  ``K-401``, ``H2S``, ``%LEL`` and OEM part numbers
#: survive as single tokens — the same rule channel D's tokeniser applies, so the two
#: channels do not disagree about what a token is.
_TOKEN_RE: Final[re.Pattern[str]] = re.compile(r"[A-Za-z0-9%]+(?:[-_/.][A-Za-z0-9%]+)*")

_TRIGRAM_WEIGHT: Final[float] = 0.35


def _hash_index(token: str, salt: bytes) -> tuple[int, float]:
    digest = hashlib.blake2b(
        token.encode("utf-8"), key=salt, person=b"mainline-emb", digest_size=8
    ).digest()
    value = int.from_bytes(digest, "big")
    index = value % EMBED_DIM
    sign = 1.0 if (value >> 63) & 1 else -1.0
    return index, sign


class SurrogateEmbedder:
    """Deterministic, non-semantic, offline embedder.  Implements ``EmbeddingProvider``."""

    def __init__(self, *, projection_resource: str = DEFAULT_PROJECTION_RESOURCE) -> None:
        self._projection = load_projection(projection_resource)
        self._index_gen = f"surrogate-1+{self._projection.projection_id}"

    @property
    def model_id(self) -> str:
        return SURROGATE_MODEL_ID

    @property
    def index_gen(self) -> str:
        return self._index_gen

    @property
    def is_semantic(self) -> bool:
        return False

    def embed(self, texts: list[str], facet: str) -> list[Vector1024]:
        prepared = validate_batch(texts, facet)
        salt = f"facet:{facet}".encode()
        out: list[Vector1024] = []
        for text in prepared:
            out.append(Vector1024(to_float32(self._embed_one(text, salt))))
        return out

    def _embed_one(self, text: str, salt: bytes) -> tuple[float, ...]:
        acc = np.zeros(EMBED_DIM, dtype=np.float64)
        counts: dict[str, int] = {}
        for token in _TOKEN_RE.findall(text):
            key = token.casefold()
            counts[key] = counts.get(key, 0) + 1
        compact = "".join(_TOKEN_RE.findall(text)).casefold()
        for i in range(max(0, len(compact) - 2)):
            key = "\x03" + compact[i : i + 3]
            counts[key] = counts.get(key, 0) + 1
        if not counts:
            raise EmptyEmbeddingInput(
                "cue contains no embeddable tokens (punctuation only)", text=text[:64]
            )
        for token, term_frequency in counts.items():
            index, sign = _hash_index(token, salt)
            weight = 1.0 + np.log(term_frequency)
            if token.startswith("\x03"):
                weight *= _TRIGRAM_WEIGHT
            acc[index] += sign * weight
        return l2_normalise(acc.tolist())

    def coarse(self, vecs: Sequence[Vector1024]) -> list[Vector256]:
        """Coarse via the committed projection — the surrogate is not MRL either."""
        out: list[Vector256] = []
        for vec in vecs:
            projected = self._projection.project(vec)
            if len(projected) != COARSE_DIM:  # pragma: no cover - projection is width-checked
                raise AssertionError("projection returned the wrong width")
            out.append(projected)
        return out

    def describe(self) -> dict[str, object]:
        return {
            "model_id": self.model_id,
            "index_gen": self.index_gen,
            "is_semantic": False,
            "projection": self._projection.describe(),
        }
