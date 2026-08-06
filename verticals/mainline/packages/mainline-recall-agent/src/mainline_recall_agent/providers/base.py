# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
"""Shared input discipline for every embedding provider.

The template in ``embed_text`` is recall.md D3, byte-identical on the event side and the
permit side::

    "{activity_path} | {asset_class} | {facet}: {cue_text}"

Query/document genre symmetry is the entire reason exposure cues exist; if the template
drifts between the two sides the design degrades silently to narrative search.  It lives
here — in the provider layer both sides call — rather than in either caller.
"""

from __future__ import annotations

import hashlib
import unicodedata
from collections.abc import Sequence
from typing import Final

from .errors import EmptyEmbeddingInput, ProviderError
from .types import FACETS

__all__ = ["EMBED_TEMPLATE", "embed_text", "normalise_text", "template_sha256", "validate_batch"]

EMBED_TEMPLATE: Final[str] = "{activity_path} | {asset_class} | {facet}: {cue_text}"

#: Hard cap on a single input.  Titan v2 accepts 8 192 tokens / 50 000 characters; a cue
#: is specified at <= 60 tokens, so anything approaching this bound is a bug upstream
#: (a whole narrative leaking into a cue field) and is refused rather than truncated —
#: truncation would quietly change what the index contains.
MAX_INPUT_CHARS: Final[int] = 8000

#: Batch cap.  Keeps one cassette and one Bedrock call bounded, and keeps the RPM-bound
#: Titan leg (ARCHITECTURE §13.1: embedding models throttle on requests, not tokens)
#: predictable.
MAX_BATCH: Final[int] = 96


def template_sha256() -> str:
    """Digest of the embedding template, pinned beside ``prompt_version`` (recall.md D3)."""
    return hashlib.sha256(EMBED_TEMPLATE.encode("utf-8")).hexdigest()


def embed_text(*, activity_path: str, asset_class: str, facet: str, cue_text: str) -> str:
    """Compose the exact string that gets embedded, on both sides."""
    if facet not in FACETS:
        raise ProviderError("unknown facet", facet=facet, allowed=list(FACETS))
    return EMBED_TEMPLATE.format(
        activity_path=activity_path.strip(),
        asset_class=asset_class.strip(),
        facet=facet,
        cue_text=cue_text.strip(),
    )


def normalise_text(text: str) -> str:
    """NFKC + whitespace collapse.  Applied identically by every provider.

    Case is NOT folded: ``K-401`` and ``H2S`` are the identifiers channel D exists to
    preserve, and the embedding side has no business disagreeing with the lexical side
    about what a token looks like.
    """
    collapsed = " ".join(unicodedata.normalize("NFKC", text).split())
    return collapsed


def validate_batch(texts: Sequence[str], facet: str) -> list[str]:
    """Validate and normalise a batch, refusing blanks and over-long inputs."""
    if facet not in FACETS:
        raise ProviderError("unknown facet", facet=facet, allowed=list(FACETS))
    if not texts:
        raise EmptyEmbeddingInput("empty batch: nothing to embed")
    if len(texts) > MAX_BATCH:
        raise ProviderError("batch too large", size=len(texts), maximum=MAX_BATCH)
    out: list[str] = []
    for index, text in enumerate(texts):
        if not isinstance(text, str):
            raise ProviderError("embedding input must be str", index=index)
        normalised = normalise_text(text)
        if not normalised:
            raise EmptyEmbeddingInput(
                "blank cue handed to an embedder; a point in the index with no content "
                "behind it is retrievable evidence of nothing",
                index=index,
            )
        if len(normalised) > MAX_INPUT_CHARS:
            raise ProviderError(
                "embedding input exceeds the cue length bound; refusing rather than "
                "truncating, because truncation silently changes what the index holds",
                index=index,
                length=len(normalised),
                maximum=MAX_INPUT_CHARS,
            )
        out.append(normalised)
    return out
