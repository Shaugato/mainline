# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
"""``LocalBGE`` — BAAI/bge-large-en-v1.5, pinned by revision, coarse via committed PCA.

recall.md D4.  bge-large is MIT-licensed and natively 1024-d, so ``event_cue_embedding``
needs no DDL change to run without a cloud account.

Two things are deliberately awkward:

1. **The revision sha has no default.**  ``LocalBGE(revision=...)`` is required.  A model
   id without a revision is not a pin — the same name can serve different weights on two
   machines a week apart, and every recall number would then be unattributable.  Rather
   than carry a revision string this build machine cannot verify, the constructor refuses.
   Set it from ``MAINLINE_BGE_REVISION`` or pass it explicitly.
2. **Coarse is a projection, never a truncation.**  bge is not MRL-trained; truncating it
   would produce a 256-d vector whose neighbours are not the 1024-d vector's neighbours,
   and calling that "Matryoshka" would be a false claim.  See ``projection.py``.

If ``sentence-transformers`` is not installed (it is an extra, because the weights are a
network fetch anyway) or the weights are absent, construction raises ``ProviderUnavailable``
— an honest "this cannot run here", distinct from a refusal.
"""

from __future__ import annotations

import os
from collections.abc import Sequence
from typing import Any, Final

from .base import validate_batch
from .errors import ProviderError, ProviderUnavailable, VectorShapeError
from .projection import DEFAULT_PROJECTION_RESOURCE, load_projection
from .types import EMBED_DIM, Vector256, Vector1024
from .vectors import l2_normalise, to_float32

__all__ = ["BGE_MODEL_NAME", "LocalBGE"]

#: A Hugging Face repository id, not a Bedrock model id.  MIT-licensed, 1024-d native.
BGE_MODEL_NAME: Final[str] = "BAAI/bge-large-en-v1.5"

#: bge-* asymmetric retrieval prefixes the *query* side only.  The permit side is the
#: query side; the event-cue side is the document side.  Getting this backwards costs
#: several points of recall silently, which is exactly the class of error the ablation
#: table exists to catch.
BGE_QUERY_INSTRUCTION: Final[str] = (
    "Represent this sentence for searching relevant passages: "
)


class LocalBGE:
    """Offline semantic embedder.  Implements ``EmbeddingProvider``."""

    def __init__(
        self,
        *,
        revision: str | None = None,
        device: str | None = None,
        projection_resource: str = DEFAULT_PROJECTION_RESOURCE,
        encoder: Any | None = None,
    ) -> None:
        resolved_revision = revision or os.environ.get("MAINLINE_BGE_REVISION") or ""
        if not resolved_revision.strip():
            raise ProviderError(
                "LocalBGE requires an explicit weights revision. A bare model name is not "
                "a pin: the same name can serve different weights on two machines, and "
                "every number derived from them would be unattributable. Pass "
                "revision='<git sha of the BAAI/bge-large-en-v1.5 revision you fetched>' "
                "or set MAINLINE_BGE_REVISION.",
                model=BGE_MODEL_NAME,
            )
        self._revision = resolved_revision.strip()
        self._projection = load_projection(projection_resource)
        self._encoder = encoder if encoder is not None else self._load_encoder(device)

    def _load_encoder(self, device: str | None) -> Any:
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as exc:  # pragma: no cover - depends on the extra being installed
            raise ProviderUnavailable(
                "sentence-transformers is not installed; install the 'local-embed' extra "
                "on a machine that will actually encode",
                model=BGE_MODEL_NAME,
            ) from exc
        try:
            return SentenceTransformer(
                BGE_MODEL_NAME,
                revision=self._revision,
                device=device,
                local_files_only=True,
            )
        except Exception as exc:  # pragma: no cover - depends on a local weights cache
            raise ProviderUnavailable(
                "bge-large weights are not present locally at the pinned revision "
                "(local_files_only=True, so nothing was fetched). Warm the cache on a "
                "networked machine, then re-run.",
                model=BGE_MODEL_NAME,
                revision=self._revision,
            ) from exc

    @property
    def model_id(self) -> str:
        return f"{BGE_MODEL_NAME}@{self._revision}"

    @property
    def index_gen(self) -> str:
        return f"bge-1+{self._projection.projection_id}"

    @property
    def is_semantic(self) -> bool:
        return True

    def embed(
        self, texts: list[str], facet: str, *, side: str = "document"
    ) -> list[Vector1024]:
        """Encode a batch.

        ``side='query'`` applies the bge retrieval instruction prefix (the permit side);
        ``side='document'`` does not (the event-cue side).
        """
        if side not in {"query", "document"}:
            raise ProviderError("side must be 'query' or 'document'", side=side)
        prepared = validate_batch(texts, facet)
        if side == "query":
            prepared = [BGE_QUERY_INSTRUCTION + text for text in prepared]
        raw = self._encoder.encode(
            prepared,
            batch_size=min(len(prepared), 32),
            normalize_embeddings=False,
            convert_to_numpy=True,
            show_progress_bar=False,
        )
        out: list[Vector1024] = []
        for row in raw:
            vec = tuple(float(x) for x in row)
            if len(vec) != EMBED_DIM:
                raise VectorShapeError(
                    "bge returned an unexpected width; the DDL declares VECTOR(1024)",
                    actual=len(vec),
                )
            out.append(Vector1024(to_float32(l2_normalise(vec))))
        return out

    def coarse(self, vecs: Sequence[Vector1024]) -> list[Vector256]:
        """Coarse via the committed projection — never Matryoshka truncation."""
        return [self._projection.project(vec) for vec in vecs]

    def describe(self) -> dict[str, object]:
        return {
            "model_id": self.model_id,
            "index_gen": self.index_gen,
            "is_semantic": True,
            "revision": self._revision,
            "projection": self._projection.describe(),
        }
