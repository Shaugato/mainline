# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
"""The recall judge's canonical request → the one legal Bedrock body.

`BedrockClaudeJudge.build_request` produces a *canonical identity* dictionary — the thing
the request digest and the cassette key are computed over — and the recall package's own
transport then picks fields out of it and hands them to the Anthropic SDK.  That is a
sound design, and it leaves exactly one seam where the fleet's model-call contract can be
imposed on the recall agent without editing a line of its code: **the transport**.

This module is that seam's arithmetic.  It takes the canonical request and a registered
:class:`~mainline_recall_fleet.legs.RecallLeg`, and returns the Anthropic *native* body
that decision A3 pins for `bedrock-runtime` `InvokeModel`.

**Two gaps it closes, both measured rather than assumed** (see `conformance.py`, which
turns each into a named check, and `tests/agents/recall_fleet/test_body_contract.py`,
which asserts the raw request fails and the bound body passes):

1. **`thinking` is absent from the recall judge's request.**  Decision A5 requires
   `{"type": "adaptive"}` written explicitly on *every* call, never omitted and never
   `disabled` — omission is not neutral, because `disabled` is a 400 above `high` effort
   and it causes two silent failures (a tool call written into visible text, and
   `<thinking>` tag leakage).  The bound body writes it.
2. **`output_config.effort` is absent.**  Decision A4 ships one model generation
   fleet-wide *differentiated by effort*; a body that never sends `effort` runs every leg
   at the endpoint default, which makes the whole differentiation a comment.  The bound
   body writes the leg's effort, and refuses a request that already carries a different
   one rather than silently overriding it.

**What it does not touch.**  The system array and the messages array are copied through
byte-for-byte.  The frozen prefix, its single cache breakpoint, the sentinel-delimited
untrusted span and the schema all belong to the recall package, and a binding that
rewrote any of them would invalidate the request digest the cassettes and the ledger are
keyed on.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Final

from mainline_agentkit import (
    ANTHROPIC_VERSION,
    BANNED_SAMPLING_KEYS,
    BANNED_TOOL_KEYS,
    assert_no_sampling_params,
    assert_no_tool_surface,
)

from .errors import BudgetDrift, FleetContractViolation, PromptVersionDrift

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    from .legs import RecallLeg

__all__ = [
    "FLEET_BODY_KEYS",
    "THINKING_ADAPTIVE",
    "assert_fleet_body",
    "assert_single_cache_breakpoint",
    "build_fleet_body",
]

#: Decision A5, written out rather than omitted, on every call this binding sends.
THINKING_ADAPTIVE: Final[dict[str, str]] = {"type": "adaptive"}

#: The exact top-level keys of a legal body, in the order they are written.  A body that
#: grows a key is a body whose shape changed, and a test reads this tuple.
FLEET_BODY_KEYS: Final[tuple[str, ...]] = (
    "anthropic_version",
    "max_tokens",
    "system",
    "messages",
    "thinking",
    "output_config",
)

_REQUIRED_REQUEST_KEYS: Final[tuple[str, ...]] = (
    "prompt_version",
    "max_tokens",
    "system",
    "messages",
    "output_config",
)


def build_fleet_body(request: Mapping[str, Any], leg: RecallLeg) -> dict[str, Any]:
    """Build the Anthropic native body for one recall judge request.

    Args:
        request: the canonical request from `BedrockClaudeJudge.build_request`.
        leg: the registered leg this call runs as.

    Returns:
        A body carrying, in this order and no other: ``anthropic_version``,
        ``max_tokens``, the ``system`` array with its single cache breakpoint,
        ``messages``, ``thinking`` written explicitly as adaptive, and ``output_config``
        with the leg's effort beside the recall package's own schema.

    Raises:
        FleetContractViolation: the request is missing a required key, its system array
            is not a frozen text prefix, its cache breakpoint is misplaced, or its
            ``output_config`` declares an effort the register does not pin.
        PromptVersionDrift: the request's ``prompt_version`` is not the registered one.
        BudgetDrift: the request's ``max_tokens`` is not the registered one.
        ForbiddenRequestField: a sampling parameter survived into the body (A6).
        ToolSurfaceConstructed: a tool key survived into the body (layer 1).
    """
    _assert_request_shape(request, leg)
    system = list(request["system"])
    assert_single_cache_breakpoint(system)
    body: dict[str, Any] = {
        "anthropic_version": ANTHROPIC_VERSION,
        "max_tokens": int(request["max_tokens"]),
        "system": system,
        "messages": list(request["messages"]),
        # Decision A5.  The one line this binding exists to add.
        "thinking": dict(THINKING_ADAPTIVE),
        "output_config": _output_config(request["output_config"], leg),
    }
    assert_fleet_body(body)
    return body


def assert_fleet_body(body: Mapping[str, Any]) -> None:
    """Refuse a body that breaks the model-call contract, before it reaches a wire.

    Runs the two agentkit guards — the ones that also run inside
    `BedrockTransport._guard`, deliberately, because *a guard that only runs in a test is
    a guard that runs on a different body than the one that ships* — plus the shape
    checks that are specific to this binding.

    Raises:
        FleetContractViolation: on a missing or extra top-level key, a missing
            ``thinking`` block, a ``thinking`` block that is not adaptive, or an absent
            ``output_config.effort``.
        ForbiddenRequestField: on any sampling parameter, at any depth (A6).
        ToolSurfaceConstructed: on any tool key, at any depth (layer 1).
    """
    keys = tuple(body)
    if keys != FLEET_BODY_KEYS:
        raise FleetContractViolation(
            "the body's top-level keys are not the contract's keys",
            observed=list(keys),
            expected=list(FLEET_BODY_KEYS),
            decision="A3",
        )
    if body["anthropic_version"] != ANTHROPIC_VERSION:
        raise FleetContractViolation(
            "the body declares a different anthropic_version; decision A3 pins the native "
            "Bedrock body and one version string",
            observed=body["anthropic_version"],
            expected=ANTHROPIC_VERSION,
            decision="A3",
        )
    thinking = body["thinking"]
    if not isinstance(thinking, dict) or thinking.get("type") != "adaptive":
        raise FleetContractViolation(
            "thinking is not written as adaptive; A5 requires it explicitly on every call "
            "because `disabled` is a 400 above high effort and it leaks thinking tags",
            observed=thinking,
            decision="A5",
        )
    output_config = body["output_config"]
    if not isinstance(output_config, dict) or "effort" not in output_config:
        raise FleetContractViolation(
            "output_config carries no effort; A4 differentiates the whole fleet by effort, "
            "so a body without one runs at the endpoint default and the differentiation is "
            "a comment",
            observed=output_config,
            decision="A4",
        )
    if "format" not in output_config:
        raise FleetContractViolation(
            "output_config carries no format; structured output is the mechanism by which a "
            "T1 proposal is schema-constrained",
            observed=output_config,
            decision="A3/A7",
        )
    # Both of these walk the body to any depth and treat a JSON Schema as opaque data —
    # a mining procedure genuinely has a `temperature` setpoint, and an extraction schema
    # with such a field must not be mistaken for a sampling parameter.
    assert_no_sampling_params(body)
    assert_no_tool_surface(body)


def assert_single_cache_breakpoint(system: Sequence[Mapping[str, Any]]) -> int:
    """Assert exactly one ``cache_control`` breakpoint, on the last system block.

    Decision A9: automatic caching does not exist on Bedrock, and *an un-asserted cache
    is usually a broken cache*.  The recall package's `SystemPrefix.wire()` already places
    the breakpoint correctly; this asserts it on the body that is about to be sent, which
    is a different statement from asserting it on the builder that usually produces it.

    Returns:
        The index of the block carrying the breakpoint.

    Raises:
        FleetContractViolation: on an empty prefix, a non-text block, no breakpoint, more
            than one breakpoint, or a breakpoint anywhere but the last block.
    """
    if not system:
        raise FleetContractViolation(
            "the system prefix is empty; there is nothing to cache and nothing to freeze",
            decision="A9",
        )
    marked: list[int] = []
    for index, block in enumerate(system):
        if block.get("type") != "text" or not isinstance(block.get("text"), str):
            raise FleetContractViolation(
                "a system block is not a plain text block; the prefix digest covers text "
                "blocks only, so a non-text block is a prefix nobody can pin",
                index=index,
                observed=dict(block),
                decision="A9",
            )
        if "cache_control" in block:
            marked.append(index)
    last = len(system) - 1
    if marked != [last]:
        raise FleetContractViolation(
            "the cache breakpoint is not the single last block; A9 places exactly one "
            "ephemeral breakpoint at the end of the frozen prefix, with every volatile "
            "byte after it in the user turn",
            marked=marked,
            last_index=last,
            decision="A9",
        )
    return last


# ── internals ───────────────────────────────────────────────────────────────────


def _assert_request_shape(request: Mapping[str, Any], leg: RecallLeg) -> None:
    missing = [key for key in _REQUIRED_REQUEST_KEYS if key not in request]
    if missing:
        raise FleetContractViolation(
            "the recall request is missing keys the fleet body is built from",
            missing=missing,
            leg_id=leg.leg_id,
            decision="A3",
        )
    if request["prompt_version"] != leg.prompt_version:
        raise PromptVersionDrift(
            "the request carries a prompt version the recall fleet register does not pin; "
            "a prompt edit is a commit, not a deploy",
            leg_id=leg.leg_id,
            registered=leg.prompt_version,
            observed=request["prompt_version"],
            decision="A13",
        )
    if int(request["max_tokens"]) != leg.max_tokens:
        raise BudgetDrift(
            "the request carries a token budget the register does not pin; max_tokens caps "
            "thinking PLUS text, so a run record that pins one number while the wire "
            "carries another cannot explain a truncation",
            leg_id=leg.leg_id,
            registered=leg.max_tokens,
            observed=int(request["max_tokens"]),
            decision="A5",
        )
    messages = request["messages"]
    if not isinstance(messages, list) or not messages:
        raise FleetContractViolation(
            "the request carries no user turn; the volatile payload lives there, after the "
            "cache breakpoint, and a body without one asks the model nothing",
            leg_id=leg.leg_id,
            decision="A9",
        )
    for key in (*BANNED_SAMPLING_KEYS, *BANNED_TOOL_KEYS):
        if key in request:
            raise FleetContractViolation(
                "the recall request carries a banned top-level key",
                leg_id=leg.leg_id,
                key=key,
                decision="A6" if key in BANNED_SAMPLING_KEYS else "A1",
            )


def _output_config(declared: Any, leg: RecallLeg) -> dict[str, Any]:
    """Merge the leg's effort into the recall package's own ``output_config``.

    A declared effort that agrees is kept; one that disagrees is refused rather than
    overridden, because silently replacing a caller's effort would make the register's
    claim about what ran untrue in exactly the case where it matters.
    """
    if not isinstance(declared, dict) or "format" not in declared:
        raise FleetContractViolation(
            "the request's output_config carries no format; recall's own "
            "`providers.schema.output_config` always emits one, so this request was not "
            "built by it",
            leg_id=leg.leg_id,
            observed=declared,
            decision="A3/A7",
        )
    effort = str(leg.effort)
    existing = declared.get("effort")
    if existing is not None and str(existing) != effort:
        raise FleetContractViolation(
            "the request declares an effort the register does not pin for this leg",
            leg_id=leg.leg_id,
            registered=effort,
            observed=existing,
            decision="A4",
        )
    merged = dict(declared)
    merged["effort"] = effort
    return merged
