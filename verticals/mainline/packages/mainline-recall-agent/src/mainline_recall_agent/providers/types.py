# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
"""The provider contracts: vector aliases, identity records, and the two Protocols.

Two Protocols, deliberately narrow.  ``EmbeddingProvider`` turns text into the two vector
widths the DDL declares (``event_cue_embedding.emb VECTOR(1024)`` and
``event_cue_coarse.emb_coarse VECTOR(256)``, ARCHITECTURE §5.4).  ``JudgeProvider`` turns
a structured payload into a *validated* Pydantic model or an exception — never a dict, and
never a string, because the listwise judge's output becomes
``blocking_check.evidence_summary`` and an unvalidated field there is an unreviewed claim
about a fatality.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from typing import Any, Final, NewType, Protocol, TypeVar, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field

__all__ = [
    "COARSE_DIM",
    "EMBED_DIM",
    "FACETS",
    "EmbeddedBatch",
    "EmbeddingProvider",
    "JudgeProvider",
    "JudgeResult",
    "ResolvedModel",
    "Usage",
    "ValidatedModelT",
    "Vector256",
    "Vector1024",
]

#: Full width.  Titan v2's default output and bge-large's native width — chosen so the
#: DDL is identical for both providers (recall.md D4).
EMBED_DIM: Final[int] = 1024

#: Coarse sweep width (``event_cue_coarse``, one unpartitioned K-means tree, S20).
COARSE_DIM: Final[int] = 256

#: The closed facet vocabulary, byte-identical to the CHECK on ``mainline.event_cue``.
FACETS: Final[tuple[str, ...]] = (
    "mechanism",
    "precondition",
    "control_failure",
    "recurrence_test",
    "narrative",
)

Vector1024 = NewType("Vector1024", tuple[float, ...])
Vector256 = NewType("Vector256", tuple[float, ...])

ValidatedModelT = TypeVar("ValidatedModelT", bound=BaseModel)


class Usage(BaseModel):
    """Token accounting for one model call.

    ``cache_read_input_tokens`` is the only observable that distinguishes a working prompt
    cache from a broken one, which is why it is surfaced rather than logged (recall.md D7).
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    input_tokens: int = 0
    output_tokens: int = 0
    cache_creation_input_tokens: int = 0
    cache_read_input_tokens: int = 0


class ResolvedModel(BaseModel):
    """A model identity resolved at runtime, in the shape callers pin into ``recall_policy``.

    Nothing in this package hard-codes a Bedrock Claude model id or inference-profile ARN.
    ``requested_tier`` and ``resolved_tier`` are *first-party* names (``claude-opus-5``);
    ``profile_id`` / ``profile_arn`` come back from ``bedrock:ListInferenceProfiles`` at
    process start-up, are asserted to carry the ``au.`` prefix, and are written into
    ``mainline_meas.recall_policy.gen_model`` and ``agent_action.model_id`` so the run is
    replayable against the identity that actually served it (ARCHITECTURE §8.2, §10.1;
    recall.md D5).
    """

    model_config = ConfigDict(frozen=True, extra="forbid", protected_namespaces=())

    requested_tier: str
    resolved_tier: str
    profile_id: str
    profile_arn: str | None = None
    region: str
    source: str = Field(description="'bedrock:ListInferenceProfiles' | 'cassette' | 'pinned'")
    resolved_at: datetime | None = None
    degraded: bool = Field(
        default=False,
        description="True when the requested tier had no au.* profile and a lower tier was "
        "used.  ARCHITECTURE §10.1: ship the previous generation and say so.",
    )

    def agent_identity_fields(self) -> dict[str, Any]:
        """The subset that feeds ``sha256(agent_identity)`` in ARCHITECTURE §8.2."""
        return {
            "model_id": self.profile_id,
            "inference_profile_arn": self.profile_arn or "",
        }


class EmbeddedBatch(BaseModel):
    """Vectors plus the identity that produced them.

    The identity travels with the vectors rather than being attached later, because
    ``event_cue_embedding.embed_model`` is the column that makes a mixed corpus detectable
    at all.
    """

    model_config = ConfigDict(frozen=True, extra="forbid", protected_namespaces=())

    embed_model: str
    index_gen: str
    facet: str
    vectors: tuple[Vector1024, ...]


class JudgeResult(BaseModel):
    """A validated judge answer with the evidence needed to reproduce the call."""

    model_config = ConfigDict(frozen=True, extra="forbid", arbitrary_types_allowed=True)

    value: BaseModel
    request_digest: str
    usage: Usage
    model: ResolvedModel
    stop_reason: str
    attempts: int


@runtime_checkable
class EmbeddingProvider(Protocol):
    """Text -> vectors, for one embedding space.

    ``model_id`` and ``index_gen`` are stable strings written verbatim into
    ``event_cue_embedding``.  Two providers must never share a ``model_id``.
    """

    @property
    def model_id(self) -> str: ...

    @property
    def index_gen(self) -> str: ...

    @property
    def is_semantic(self) -> bool:
        """False for the offline surrogate.  A non-semantic space may never be scored."""
        ...

    def embed(self, texts: list[str], facet: str) -> list[Vector1024]: ...

    def coarse(self, vecs: Sequence[Vector1024]) -> list[Vector256]: ...


@runtime_checkable
class JudgeProvider(Protocol):
    """Structured payload -> validated model, or an exception that names its silence reason."""

    @property
    def resolved_model(self) -> ResolvedModel: ...

    @property
    def last_usage(self) -> Usage | None: ...

    def judge(
        self,
        system_blocks: Sequence[Any],
        user_payload: dict[str, Any],
        schema: type[ValidatedModelT],
    ) -> ValidatedModelT: ...
