# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
"""``assert_homogeneous`` — the refusal that makes two embedding spaces safe to have.

recall.md D4 ships two real embedding providers (Titan v2 and bge-large) plus, for the
offline path, a declared non-semantic surrogate.  Three spaces in one deployment is fine.
Three spaces in one *corpus* is a category error: cosine between vectors from different
models is a number with no meaning, and it is a number that reaches a supervisor as
``p_relevant``.

So the mixing is not prevented by convention.  ``event_cue_embedding.embed_model`` and
``index_gen`` are columns; this function reads them off whatever row shape the caller has
(dict, Pydantic model, or plain object) and raises.  The harness calls it before scoring;
the orchestrator calls it before fusing.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any, Final

from .errors import HeterogeneousCorpus

__all__ = [
    "NON_SEMANTIC_MODEL_IDS",
    "assert_homogeneous",
    "assert_semantic",
    "corpus_identity",
    "is_non_semantic",
]

#: Model ids whose vectors are structurally valid and semantically meaningless.
#:
#: The offline surrogate exists so the pipeline is runnable with no network and no AWS
#: account.  Its vectors have the right width and the right norm and carry no meaning
#: whatsoever.  Naming it here — rather than hoping nobody forgets — is what stops a
#: recall number ever being computed over it.
NON_SEMANTIC_MODEL_IDS: Final[frozenset[str]] = frozenset(
    {"mainline-surrogate-hash-v1"},
)

_MODEL_KEYS: Final[tuple[str, ...]] = ("embed_model", "model_id")
_GEN_KEYS: Final[tuple[str, ...]] = ("index_gen", "index_generation")


def _read(row: Any, keys: tuple[str, ...]) -> str | None:
    if isinstance(row, dict):
        for key in keys:
            if key in row and row[key] is not None:
                return str(row[key])
        return None
    for key in keys:
        value = getattr(row, key, None)
        if value is not None:
            return str(value)
    return None


def corpus_identity(rows: Iterable[Any]) -> tuple[frozenset[str], frozenset[str]]:
    """Return ``(distinct embed_model, distinct index_gen)`` over ``rows``."""
    models: set[str] = set()
    generations: set[str] = set()
    for index, row in enumerate(rows):
        model = _read(row, _MODEL_KEYS)
        if model is None:
            raise HeterogeneousCorpus(
                "row carries no embed_model; an unlabelled vector cannot be scored",
                row_index=index,
            )
        models.add(model)
        generation = _read(row, _GEN_KEYS)
        if generation is not None:
            generations.add(generation)
    return frozenset(models), frozenset(generations)


def assert_homogeneous(rows: Iterable[Any], *, require_index_gen: bool = False) -> str:
    """Raise ``HeterogeneousCorpus`` unless every row shares one ``embed_model``.

    Returns the single ``embed_model`` on success so the caller can record it.
    With ``require_index_gen`` the same is demanded of ``index_gen`` — two generations of
    the same model are a re-index in flight, and an ANN result set spanning both has no
    single ``index_generation`` to put in the PER receipt.
    """
    materialised = list(rows)
    if not materialised:
        raise HeterogeneousCorpus("empty corpus: nothing to assert homogeneity over")
    models, generations = corpus_identity(materialised)
    if len(models) != 1:
        raise HeterogeneousCorpus(
            "corpus mixes embedding models; cosine across spaces is meaningless",
            embed_models=sorted(models),
            row_count=len(materialised),
        )
    if require_index_gen and len(generations) != 1:
        raise HeterogeneousCorpus(
            "corpus spans more than one index generation",
            index_gens=sorted(generations),
            row_count=len(materialised),
        )
    return next(iter(models))


def is_non_semantic(model_id: str) -> bool:
    return model_id in NON_SEMANTIC_MODEL_IDS


def assert_semantic(model_id: str) -> None:
    """Refuse to score a corpus embedded by a declared non-semantic provider."""
    if is_non_semantic(model_id):
        raise HeterogeneousCorpus(
            "this corpus was embedded by a declared NON-SEMANTIC provider; retrieval "
            "quality measured over it means nothing and must not be published",
            embed_model=model_id,
        )
