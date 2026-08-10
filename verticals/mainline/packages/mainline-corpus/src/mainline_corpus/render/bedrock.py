# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""The ``bedrock`` tier: Claude on an ``au.*`` inference profile, strict tool use, T=0.

**This tier is never exercised on a dated path.**  AWS credentials are not valid on the
founder's machine, ``--offline`` is the default (D2), and reaching this code requires
``--allow-live`` *and* the ``model-rendered`` policy.  It exists so that "the corpus can be
model-rendered" is a reviewable implementation rather than a claim, and so that if credentials
land before D-5 the change is a flag and a cache rebuild rather than a design.

Everything below is written from the Bedrock Converse API contract.  **None of it has been
executed against the service from this repository** — say so in the ADR, say so on the honesty
card, and do not let the renderer census say otherwise: the census counts what is in the cache,
and today the cache contains zero ``bedrock`` entries.

------------------------------------------------------------------------------------------
Five constraints, each from a specific finding
------------------------------------------------------------------------------------------
1. **``au.*``, never ``apac.*``, never ``global.*``.**  §2.2 S26 moved the corpus generator off
   ``apac.*`` because it can route an Australian fatality narrative offshore; §19 GT-11 forbids
   ``global.*`` outright because it routes to every commercial region.  ``_check_profile``
   enforces the prefix at call time, not at review time.
2. **boto3 directly, never the Claude Agent SDK.**  The SDK rejects ``au.*`` inference-profile
   ids; a corpus generator that could not name its own inference profile would be forced onto a
   non-compliant one.
3. **Strict tool use, one tool, forced.**  ``toolChoice={"tool": …}`` with a schema that is
   ``additionalProperties: false`` and all-required (checked when the prompt is parsed).  Text
   output is not accepted and is not parsed as a fallback — a fallback parser is how malformed
   output becomes plausible output.
4. **No Citations.**  Anthropic's citations feature and schema-bound tool output are mutually
   exclusive and return 400 together.  This tier binds quotes itself, deterministically, in
   :mod:`mainline_corpus.render.spans`, which is stronger anyway: we compute offsets, we never
   trust a model-reported one.
5. **No retry, no jitter, ever.**  A retry loop in a hashed path is a machine for producing two
   different responses under one cache key.  A failure here is a failure; the operator re-runs
   the command and the cache makes the successful part free.

Temperature 0 and ``topP`` 1 are asked for because they are the right ask.  They do **not**
make the service deterministic — batching and hardware can still move a token — which is
exactly why the response is cached the first time and never re-derived.

------------------------------------------------------------------------------------------
Scan exemption — read this before deleting the tool surface below
------------------------------------------------------------------------------------------
``scripts/agents/assert_no_tool_construction.py`` reported this module three times, and the
detection was correct: :meth:`BedrockRenderer._tool_config` really does build
``"tools": [{"toolSpec": …}]``, and that is a tool surface by any reading.  What did **not**
apply was the sentence the finding cited.  ARCHITECTURE.md 8.4 layer 1 says *document text
never enters a turn belonging to a tool-holding agent; the extraction call has zero tools*,
and this module is not the extraction call.  It is the corpus **generator**: its input is
:attr:`RenderNode.facts`, assembled by :mod:`mainline_corpus.render.nodes` out of stage-1
world data this repository authored, and no untrusted document reaches it.  The extraction
call is :func:`mainline_agentkit.call.quarantined_call`, which has no ``tools`` parameter at
all — a property a test asserts by signature, not by convention.

So the exemption is granted here, by exact path, scoped to ``tools`` / ``toolChoice`` /
``toolConfig`` only — an ``mcp_servers`` key added to this file is still a finding — and it
rests on the same doctrine as AR-1's in
:mod:`mainline_agentkit.fallback_toolform`: **one tool, forced by name, no implementation,
no ``toolResult`` ever returned, one turn.**  That is a *format* mechanism, not a
capability: the model cannot select a tool, cannot decline to call it, cannot call anything
else, and is never handed a result to act on.  Those four properties are no longer a
promise in this docstring — the scanner's ``forced_single_turn_format_tool`` condition
re-proves all four on every run, and the day one of them stops holding the scan is red
again.

Deleting the surface was the other candidate repair and it is the worse one: without a
schema-bound tool call this tier would have to parse free text, which constraint 3 above
names as how malformed output becomes plausible output.  Marker for the scan:

    mainline-scan-exemption: corpus-render-format-tool
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Final

from ..prompts import Prompt
from . import netguard
from .params import AWS_REGION, BEDROCK_MODEL_ID, TIERS
from .protocol import RenderNode, RenderRefusal

__all__ = ["BedrockRenderer", "check_profile_id"]

#: This tier's census heading, checked against ``params.TIERS`` at import.
TIER_NAME: Final[str] = "bedrock"
if TIER_NAME not in TIERS:  # pragma: no cover - import-time invariant
    raise ImportError(f"{TIER_NAME!r} is not one of params.TIERS")


class BedrockUnavailable(RenderRefusal):
    """The bedrock tier was asked for and cannot be reached."""


def check_profile_id(model_id: str) -> None:
    """Refuse any inference profile that is not ``au.*``.

    Enforced here rather than trusted to configuration: residency is one of the arguments this
    product makes in the room, and an argument enforced by a comment is not enforced.
    """
    if model_id.startswith("global."):
        raise BedrockUnavailable(
            f"{model_id}: a `global.*` inference profile routes to every commercial region "
            "(ARCHITECTURE §19 GT-11). Refused."
        )
    if model_id.startswith("apac."):
        raise BedrockUnavailable(
            f"{model_id}: an `apac.*` profile can route Australian incident narratives offshore "
            "(§2.2 finding S26). Refused; use the `au.*` profile."
        )
    if not model_id.startswith("au."):
        raise BedrockUnavailable(
            f"{model_id}: only `au.*` inference profiles are permitted for corpus rendering."
        )


@dataclass(slots=True)
class BedrockRenderer:
    """Render one node with Claude on Bedrock, under a forced tool call."""

    prompts: Mapping[str, Prompt]
    model_id: str = BEDROCK_MODEL_ID
    region: str = AWS_REGION
    allow_live: bool = False
    #: Injected in tests.  A ``converse``-shaped callable, so the request assembly and the
    #: response handling are covered without an AWS account — which is the only way they can
    #: be covered at all right now.
    client: Any = None
    name: str = TIER_NAME

    def __post_init__(self) -> None:
        check_profile_id(self.model_id)

    def _ensure_client(self) -> Any:
        if self.client is not None:
            return self.client
        if not self.allow_live:
            raise BedrockUnavailable(
                "the bedrock tier was selected without --allow-live. --offline is the default "
                "(D2) because AWS credentials are not valid on this machine and PL-3 forbids "
                "putting an unproven capability on a dated path. Every bedrock-tier node must "
                "therefore be served from the committed cache."
            )
        try:
            import boto3
        except ImportError as exc:  # pragma: no cover - boto3 is a declared dependency
            raise BedrockUnavailable(f"boto3 is not importable: {exc}") from exc
        with netguard.allow(reason="bedrock tier under --allow-live"):
            self.client = boto3.client("bedrock-runtime", region_name=self.region)
        return self.client

    def _tool_config(self, prompt: Prompt) -> dict[str, Any]:
        return {
            "tools": [
                {
                    "toolSpec": {
                        "name": prompt.tool_name,
                        "description": (
                            f"Emit the {prompt.kind} render for one corpus node. "
                            "Every field is required and no other field is permitted."
                        ),
                        "inputSchema": {"json": dict(prompt.schema)},
                    }
                }
            ],
            # Forced, not `any`: with one tool `any` and a named tool are equivalent today and
            # would stop being so the moment a second tool were added.
            "toolChoice": {"tool": {"name": prompt.tool_name}},
        }

    def request(self, node: RenderNode, prompt: Prompt) -> dict[str, Any]:
        """Build the ``converse`` request.  Pure — assembled and testable without a client."""
        facts = json.dumps(dict(node.facts), sort_keys=True, ensure_ascii=False, indent=2)
        return {
            "modelId": self.model_id,
            "system": [{"text": prompt.system}],
            "messages": [
                {
                    "role": "user",
                    "content": [{"text": f"{prompt.user}\n{facts}\n"}],
                }
            ],
            "toolConfig": self._tool_config(prompt),
            "inferenceConfig": {
                "temperature": 0.0,
                "topP": 1.0,
                "maxTokens": prompt.max_tokens,
            },
        }

    @staticmethod
    def _extract(response: Mapping[str, Any], *, prompt: Prompt, node_id: str) -> Mapping[str, Any]:
        stop_reason = response.get("stopReason")
        if stop_reason == "max_tokens":
            raise BedrockUnavailable(
                f"{node_id}: the model hit maxTokens ({prompt.max_tokens}) before completing the "
                "tool call. A truncated tool call is not a partial answer, it is no answer; "
                "raise max_tokens in the prompt front matter and bump prompt_version."
            )
        blocks = response.get("output", {}).get("message", {}).get("content", [])
        for block in blocks:
            tool_use = block.get("toolUse")
            if tool_use is None:
                continue
            if tool_use.get("name") != prompt.tool_name:
                raise BedrockUnavailable(
                    f"{node_id}: model called {tool_use.get('name')!r}, expected "
                    f"{prompt.tool_name!r}"
                )
            payload = tool_use.get("input")
            if not isinstance(payload, Mapping):
                raise BedrockUnavailable(f"{node_id}: toolUse.input is not an object")
            return payload
        raise BedrockUnavailable(
            f"{node_id}: the response contains no toolUse block (stopReason={stop_reason!r}). "
            "Text output is not parsed as a fallback: a fallback parser is how malformed output "
            "becomes plausible output."
        )

    def render(self, node: RenderNode, prompt_version: str) -> Mapping[str, Any]:
        """Call Bedrock once and return the tool payload."""
        prompt = self.prompts[node.kind]
        if prompt.version != prompt_version:
            raise BedrockUnavailable(
                f"{node.node_id}: pinned prompt_version {prompt_version!r} but the file on disk "
                f"is {prompt.version!r}; a live call under a version the prompt is not would "
                "cache a response under a key that does not describe it."
            )
        client = self._ensure_client()
        request = self.request(node, prompt)
        with netguard.allow(reason="bedrock tier under --allow-live"):
            raw = client.converse(**request)
        return self._extract(raw, prompt=prompt, node_id=node.node_id)
