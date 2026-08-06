# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
"""Model providers for the MAINLINE recall agent.

The only code in the repository that talks to Bedrock, and the reason the rest of the
recall domain runs with no AWS account.

Two contracts (``providers.types``):

``EmbeddingProvider``
    ``embed(texts, facet) -> list[Vector1024]`` and ``coarse(vecs) -> list[Vector256]``,
    plus a stable ``model_id`` and ``index_gen`` written verbatim into
    ``mainline.event_cue_embedding``.  Implementations: ``BedrockTitanV2`` (Matryoshka
    truncation, renormalised client-side), ``LocalBGE`` (committed projection, never
    truncation), ``SurrogateEmbedder`` (declared non-semantic, offline).

``JudgeProvider``
    ``judge(system_blocks, user_payload, schema) -> ValidatedModel``.  Implementation
    ``BedrockClaudeJudge`` against a Claude ``au.*`` inference profile whose identity is
    resolved at runtime and never hard-coded.

Read ``errors.py`` first if you are writing a caller: every failure that must become a
``silence_ledger`` row carries its ``silence_reason``.
"""

from __future__ import annotations

from .base import EMBED_TEMPLATE, embed_text, normalise_text, template_sha256, validate_batch
from .bedrock_titan import TITAN_EMBED_MODEL_ID, BedrockTitanV2
from .canonical import canonical_json, request_digest, sha256_hex
from .cassette import (
    CASSETTE_SCHEMA,
    CassetteJudgeTransport,
    CassetteStore,
    RecordingEmbeddingProvider,
    RecordingJudgeTransport,
    ReplayEmbeddingProvider,
    assert_recording_permitted,
    default_cassette_root,
    embed_request,
)
from .errors import (
    CANONICAL_SILENCE_REASONS,
    CanonicalisationError,
    CassetteMiss,
    CassetteRecordingNotPermitted,
    CassetteTampered,
    DeadLetter,
    EmptyEmbeddingInput,
    HeterogeneousCorpus,
    ModelRefusal,
    ModelTruncated,
    ProfileResolutionFailed,
    ProjectionError,
    ProviderError,
    ProviderUnavailable,
    ResidencyViolation,
    SystemBlockContract,
    VectorShapeError,
)
from .homogeneity import (
    NON_SEMANTIC_MODEL_IDS,
    assert_homogeneous,
    assert_semantic,
    corpus_identity,
    is_non_semantic,
)
from .judge import BedrockClaudeJudge, BedrockTransport, JudgeTransport, TransportReply
from .local_bge import BGE_MODEL_NAME, LocalBGE
from .projection import CommittedProjection, load_projection
from .registry import (
    current_mode,
    describe_providers,
    get_embedding_provider,
    get_judge_provider,
)
from .resolve import (
    AU_PROFILE_PREFIX,
    DEFAULT_TIER,
    TIER_LADDER,
    pinned_model,
    resolve_inference_profile,
    select_profile,
)
from .schema import output_config, to_strict_json_schema
from .surrogate import SURROGATE_MODEL_ID, SurrogateEmbedder
from .system_blocks import (
    SystemBlock,
    SystemPrefix,
    build_system_blocks,
    build_user_turn,
    payload_sentinel,
)
from .types import (
    COARSE_DIM,
    EMBED_DIM,
    FACETS,
    EmbeddedBatch,
    EmbeddingProvider,
    JudgeProvider,
    JudgeResult,
    ResolvedModel,
    Usage,
    ValidatedModelT,
    Vector256,
    Vector1024,
)
from .vectors import b64_to_vector, is_unit, l2_normalise, matryoshka_coarse, vector_to_b64

__all__ = [
    "AU_PROFILE_PREFIX",
    "BGE_MODEL_NAME",
    "CANONICAL_SILENCE_REASONS",
    "CASSETTE_SCHEMA",
    "COARSE_DIM",
    "DEFAULT_TIER",
    "EMBED_DIM",
    "EMBED_TEMPLATE",
    "FACETS",
    "NON_SEMANTIC_MODEL_IDS",
    "SURROGATE_MODEL_ID",
    "TIER_LADDER",
    "TITAN_EMBED_MODEL_ID",
    "BedrockClaudeJudge",
    "BedrockTitanV2",
    "BedrockTransport",
    "CanonicalisationError",
    "CassetteJudgeTransport",
    "CassetteMiss",
    "CassetteRecordingNotPermitted",
    "CassetteStore",
    "CassetteTampered",
    "CommittedProjection",
    "DeadLetter",
    "EmbeddedBatch",
    "EmbeddingProvider",
    "EmptyEmbeddingInput",
    "HeterogeneousCorpus",
    "JudgeProvider",
    "JudgeResult",
    "JudgeTransport",
    "LocalBGE",
    "ModelRefusal",
    "ModelTruncated",
    "ProfileResolutionFailed",
    "ProjectionError",
    "ProviderError",
    "ProviderUnavailable",
    "RecordingEmbeddingProvider",
    "RecordingJudgeTransport",
    "ReplayEmbeddingProvider",
    "ResidencyViolation",
    "ResolvedModel",
    "SurrogateEmbedder",
    "SystemBlock",
    "SystemBlockContract",
    "SystemPrefix",
    "TransportReply",
    "Usage",
    "ValidatedModelT",
    "Vector256",
    "Vector1024",
    "VectorShapeError",
    "assert_homogeneous",
    "assert_recording_permitted",
    "assert_semantic",
    "b64_to_vector",
    "build_system_blocks",
    "build_user_turn",
    "canonical_json",
    "corpus_identity",
    "current_mode",
    "default_cassette_root",
    "describe_providers",
    "embed_request",
    "embed_text",
    "get_embedding_provider",
    "get_judge_provider",
    "is_non_semantic",
    "is_unit",
    "l2_normalise",
    "load_projection",
    "matryoshka_coarse",
    "normalise_text",
    "output_config",
    "payload_sentinel",
    "pinned_model",
    "request_digest",
    "resolve_inference_profile",
    "select_profile",
    "sha256_hex",
    "template_sha256",
    "to_strict_json_schema",
    "validate_batch",
    "vector_to_b64",
]
