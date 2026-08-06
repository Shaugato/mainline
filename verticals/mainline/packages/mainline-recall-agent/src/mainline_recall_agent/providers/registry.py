# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
"""One switch — ``MAINLINE_RECALL_PROVIDER`` — and an explicit ladder behind it.

``cassette`` (default)
    Replay.  CI and the demo run here.  Judge calls come from committed cassettes;
    embeddings come from committed cassettes when the caller names a recorded space
    (``MAINLINE_RECALL_EMBED_MODEL``), and otherwise from the declared non-semantic
    surrogate so the pipeline still runs on a machine with no weights and no account.

``bedrock``
    Live: Titan v2 in-region for embeddings, Claude on the runtime-resolved ``au.*``
    inference profile for the judge.

``local``
    bge-large from a local weights cache, no network at call time, no AWS.

The ladder is explicit rather than automatic because the failure it guards against is a
run that silently used the wrong space.  ``describe()`` returns exactly what was selected,
and the orchestrator writes it into ``recall_run`` — a degraded provider must look
different in the record from a healthy one.
"""

from __future__ import annotations

import os
from typing import Any, Final

from .bedrock_titan import BedrockTitanV2
from .cassette import CassetteJudgeTransport, CassetteStore, ReplayEmbeddingProvider
from .errors import ProviderError
from .homogeneity import is_non_semantic
from .judge import BedrockClaudeJudge, BedrockTransport
from .local_bge import BGE_MODEL_NAME, LocalBGE
from .projection import load_projection
from .resolve import DEFAULT_TIER, REQUIRED_REGION, resolve_inference_profile
from .surrogate import SURROGATE_MODEL_ID, SurrogateEmbedder
from .types import ResolvedModel
from .vectors import matryoshka_coarse

__all__ = [
    "CASSETTE_PROFILE_ID",
    "PROVIDER_MODES",
    "cassette_resolved_model",
    "current_mode",
    "describe_providers",
    "get_embedding_provider",
    "get_judge_provider",
]

PROVIDER_MODES: Final[tuple[str, ...]] = ("cassette", "bedrock", "local")

#: Deliberately not an ARN.  In replay there is no resolved profile, and pretending there
#: is one would put a fictional identity into ``recall_run.gen_model``.
CASSETTE_PROFILE_ID: Final[str] = "cassette://au-profile-unresolved"


def current_mode() -> str:
    mode = (os.environ.get("MAINLINE_RECALL_PROVIDER") or "cassette").strip().lower()
    if mode not in PROVIDER_MODES:
        raise ProviderError(
            "unknown MAINLINE_RECALL_PROVIDER", mode=mode, allowed=list(PROVIDER_MODES)
        )
    return mode


def cassette_resolved_model(requested_tier: str = DEFAULT_TIER) -> ResolvedModel:
    """The identity a replayed judge reports — visibly unresolved, by construction."""
    return ResolvedModel(
        requested_tier=requested_tier,
        resolved_tier=requested_tier,
        profile_id=CASSETTE_PROFILE_ID,
        profile_arn=None,
        region=os.environ.get("AWS_REGION") or REQUIRED_REGION,
        source="cassette",
        resolved_at=None,
        degraded=False,
    )


def _replay_embedder(store: CassetteStore | None) -> Any:
    """Replay a recorded embedding space, or fall back to the surrogate — explicitly."""
    recorded = (os.environ.get("MAINLINE_RECALL_EMBED_MODEL") or "").strip()
    if not recorded:
        return SurrogateEmbedder()
    semantic = not is_non_semantic(recorded)
    if recorded.startswith(BGE_MODEL_NAME) or recorded == SURROGATE_MODEL_ID:
        # Neither space is Matryoshka-trained: coarse goes through the committed
        # projection.  The surrogate is replayable too, so a fixture corpus recorded
        # offline exercises exactly the same replay path a Titan corpus would.
        projection = load_projection()
        prefix = "bge-1" if semantic else "surrogate-1"
        return ReplayEmbeddingProvider(
            model_id=recorded,
            index_gen=f"{prefix}+{projection.projection_id}",
            is_semantic=semantic,
            coarse_impl=projection.project,
            store=store,
        )
    # Titan and anything else MRL-trained: coarse is truncation plus renormalisation.
    return ReplayEmbeddingProvider(
        model_id=recorded,
        index_gen=os.environ.get("MAINLINE_RECALL_INDEX_GEN") or "titan2-1",
        is_semantic=semantic,
        coarse_impl=matryoshka_coarse,
        store=store,
    )


def get_embedding_provider(*, store: CassetteStore | None = None) -> Any:
    """Return the embedding provider selected by the environment."""
    mode = current_mode()
    if mode == "bedrock":
        return BedrockTitanV2()
    if mode == "local":
        return LocalBGE()
    return _replay_embedder(store)


def get_judge_provider(
    *,
    store: CassetteStore | None = None,
    requested_tier: str = DEFAULT_TIER,
    prompt_version: str = "recall-judge-1",
    max_tokens: int = 4096,
) -> BedrockClaudeJudge:
    """Return the judge selected by the environment.

    In ``bedrock`` mode the inference profile is resolved *now*, at construction, so a
    residency failure or a missing profile surfaces at start-up rather than in the middle
    of a permit's recall run.
    """
    mode = current_mode()
    if mode == "bedrock":
        resolved = resolve_inference_profile(requested_tier=requested_tier)
        return BedrockClaudeJudge(
            resolved_model=resolved,
            transport=BedrockTransport(resolved_model=resolved),
            prompt_version=prompt_version,
            max_tokens=max_tokens,
        )
    resolved = cassette_resolved_model(requested_tier)
    return BedrockClaudeJudge(
        resolved_model=resolved,
        transport=CassetteJudgeTransport(store),
        prompt_version=prompt_version,
        max_tokens=max_tokens,
    )


def describe_providers(*, store: CassetteStore | None = None) -> dict[str, Any]:
    """What was actually selected — written into ``recall_run`` by the orchestrator."""
    mode = current_mode()
    embedder = get_embedding_provider(store=store)
    describe = getattr(embedder, "describe", None)
    return {
        "mode": mode,
        "embedding": describe() if callable(describe) else {"model_id": embedder.model_id},
        "judge_tier_requested": DEFAULT_TIER,
        "judge_identity_resolution": "runtime" if mode == "bedrock" else "cassette",
    }
