# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""What a call profile is, and what it refuses to be at import time.

A :class:`CallProfile` is the whole of a model call except its input: the tier, the
effort, the model generation, the frozen system prefix, the token budget and the output
model. There is no other place in MAINLINE where those are chosen, which is what makes
``spec/agents/fleet.yaml``'s ``call_profiles`` column a complete statement about what an
agent may do.

**The validations below run when the module is imported, not when a call is made.**
That is the difference between a rule and a control. A profile that names a forbidden
output field, or that gives a T2 narrator the ability to write a gate-visible field, or
whose token budget cannot fit its own thinking floor, does not fail on the day it is
called — it fails on the day it is written, in CI, in the import.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel

from .._canon import sha256_hex
from ..cache import min_cacheable_tokens, place_cache_breakpoint
from ..schema import BedrockSchema, bedrock_schema

if TYPE_CHECKING:
    from collections.abc import Iterator, Mapping, Sequence

__all__ = [
    "DISPOSITION_FORBIDDEN_TOKENS",
    "CallProfile",
    "Effort",
    "Tier",
]


class Tier(StrEnum):
    """§8.2's three tiers. Only ``T0`` may write a gate-visible field, and ``T0`` has no model."""

    T0 = "T0"
    T1 = "T1"
    T2 = "T2"


class Effort(StrEnum):
    """``output_config.effort``. Decision A4 differentiates the fleet by this, not by model."""

    LOW = "low"
    HIGH = "high"
    XHIGH = "xhigh"


#: Substrings that may not appear in any output-model property name of a profile that
#: declares them forbidden. §8.2's first hard prohibition: no T1 or T2 agent may draft a
#: disposition rationale. Checking property *names* is a structural check the schema can
#: be graded against — a model cannot fill a field that does not exist.
DISPOSITION_FORBIDDEN_TOKENS: frozenset[str] = frozenset(
    {
        "defeater",
        "rationale",
        "disposition",
        "signature",
        "signed",
        "clearance",
        "severity",
        "approval",
        "approved",
        "sign_off",
    }
)


@dataclass(frozen=True, slots=True)
class CallProfile[ModelT: BaseModel]:
    """One fully-specified model call shape.

    Attributes:
        profile_id: the id ``spec/agents/fleet.yaml`` references in ``call_profiles``.
        agent: the fleet agent (§8.4) this profile belongs to.
        tier: §8.2 tier. ``T0`` is rejected here: the kernel has no model.
        effort: ``output_config.effort``.
        model_key: the model generation, resolved to an ``au.*`` profile ARN at
            start-up and never hard-coded (decision A3/AR-2).
        prompt_version: bumped on any byte change to :attr:`system_blocks`.
        system_blocks: the byte-frozen system prefix, in order. The cache breakpoint
            goes on the last one.
        max_tokens: the committed budget. Caps thinking **plus** text (decision A5), so
            a breach is a change to this number, never a silent retry.
        thinking_floor_tokens: the share of :attr:`max_tokens` reserved for thinking.
        output_model: the Pydantic model the response must validate against.
        may_write_gate_field: always false for every profile in this package. Present so
            the fleet matrix test has a field to read rather than an absence to infer.
        forbidden_output_tokens: substrings refused in output-model property names.
        allow_uncacheable_prefix: permit a prefix below the generation minimum.
        require_all_properties: list every property in ``required`` (strict tool form).
    """

    profile_id: str
    agent: str
    tier: Tier
    effort: Effort
    model_key: str
    prompt_version: str
    system_blocks: tuple[str, ...]
    max_tokens: int
    thinking_floor_tokens: int
    output_model: type[ModelT]
    may_write_gate_field: bool = False
    forbidden_output_tokens: frozenset[str] = frozenset()
    allow_uncacheable_prefix: bool = False
    require_all_properties: bool = False
    _schema: BedrockSchema = field(init=False, compare=False, repr=False)

    def __post_init__(self) -> None:
        """Validate the profile and build its schema, at import time."""
        if self.tier is Tier.T0:
            raise ValueError(
                f"profile {self.profile_id!r} declares tier T0: the kernel plane holds no "
                f"model at all (ARCHITECTURE.md §8.2 E1-E4)"
            )
        if self.may_write_gate_field:
            raise ValueError(
                f"profile {self.profile_id!r} claims may_write_gate_field: no model-bearing "
                f"tier may write a field the gate reads (ARCHITECTURE.md §8.2)"
            )
        if not self.system_blocks:
            raise ValueError(f"profile {self.profile_id!r} has no system blocks")
        if self.thinking_floor_tokens >= self.max_tokens:
            raise ValueError(
                f"profile {self.profile_id!r} reserves {self.thinking_floor_tokens} thinking "
                f"tokens out of a {self.max_tokens}-token budget that caps thinking PLUS "
                f"text: no budget is left for the answer (decision A5)"
            )
        built = bedrock_schema(
            self.output_model, require_all_properties=self.require_all_properties
        )
        self._reject_forbidden_fields(built)
        object.__setattr__(self, "_schema", built)
        # Raises CachePrefixTooSmall here, at import, rather than on the first call.
        place_cache_breakpoint(
            list(self.system_blocks),
            profile_id=self.profile_id,
            model_key=self.model_key,
            allow_uncacheable_prefix=self.allow_uncacheable_prefix,
        )

    def _reject_forbidden_fields(self, built: BedrockSchema) -> None:
        if not self.forbidden_output_tokens:
            return
        for name in _property_names(built.schema):
            lowered = name.lower()
            for token in sorted(self.forbidden_output_tokens):
                if token in lowered:
                    raise ValueError(
                        f"profile {self.profile_id!r} exposes output field {name!r}, which "
                        f"contains the forbidden token {token!r}. A tier-{self.tier} agent "
                        f"may not be given a field it could fill with a disposition "
                        f"(ARCHITECTURE.md §8.2, §8.4 row 5)."
                    )

    @property
    def schema(self) -> BedrockSchema:
        """The Bedrock-legal schema, built once at import."""
        return self._schema

    @property
    def schema_version(self) -> str:
        """The ``schema_version`` component of ``agent_identity`` (§8.2)."""
        return self._schema.schema_version

    def system_text(self) -> str:
        """Join the frozen prefix into one string, for hashing and token estimation."""
        return "".join(self.system_blocks)

    def prompt_sha256(self) -> str:
        """Content address of the frozen prefix.

        This is what ``mainline_meas.prompt_asset`` registers and what makes decision
        A13 checkable: a prompt file that is not registered under this digest is a
        prompt edit that was deployed rather than committed.
        """
        return sha256_hex(self.system_text().encode("utf-8"))

    def cache_minimum(self) -> int:
        """Return the cacheable-prefix minimum for this profile's model generation."""
        return min_cacheable_tokens(self.model_key)

    def build_system(self) -> list[dict[str, Any]]:
        """Build the ``system`` array, with exactly one breakpoint on the last block."""
        return place_cache_breakpoint(
            list(self.system_blocks),
            profile_id=self.profile_id,
            model_key=self.model_key,
            allow_uncacheable_prefix=self.allow_uncacheable_prefix,
        )

    def describe(self) -> dict[str, Any]:
        """Summarise this profile as ``spec/agents/fleet.yaml`` and the ledger consume it."""
        return {
            "profile_id": self.profile_id,
            "agent": self.agent,
            "tier": str(self.tier),
            "effort": str(self.effort),
            "model_key": self.model_key,
            "prompt_version": self.prompt_version,
            "prompt_sha256": self.prompt_sha256(),
            "schema_version": self.schema_version,
            "max_tokens": self.max_tokens,
            "thinking_floor_tokens": self.thinking_floor_tokens,
            "may_write_gate_field": self.may_write_gate_field,
            "tools": [],
        }


def _property_names(schema: Mapping[str, Any]) -> Iterator[str]:
    """Every property name anywhere in a JSON Schema."""
    properties = schema.get("properties")
    if isinstance(properties, dict):
        for name, sub in properties.items():
            yield str(name)
            if isinstance(sub, dict):
                yield from _property_names(sub)
    items = schema.get("items")
    if isinstance(items, dict):
        yield from _property_names(items)
    for key in ("anyOf", "oneOf", "allOf"):
        branches: Sequence[Any] = schema.get(key) or ()
        for branch in branches:
            if isinstance(branch, dict):
                yield from _property_names(branch)
