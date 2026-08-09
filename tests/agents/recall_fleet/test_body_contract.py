# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
"""The two gaps this binding closes, asserted red on the raw request and green on the body.

PL-2 is structural for a product whose deliverable is a refusal, and it applies to a
*normalisation* the same way: the red case has to be checked in, not described.  The red
case here is the body the recall package's own live transport would have sent — the
canonical request's fields handed to `client.messages.create` with no `thinking` and no
`output_config.effort` — and `test_raw_recall_body_fails_exactly_two_clauses` asserts
which clauses it breaks, by name.  If someone later adds `thinking` upstream, that test
fails and this binding's justification has to be rewritten rather than quietly kept.
"""

from __future__ import annotations

from typing import Any

import pytest
from mainline_agentkit import ForbiddenRequestField, ToolSurfaceConstructed
from mainline_recall_fleet import (
    BODY_CHECKS,
    FLEET_BODY_KEYS,
    BudgetDrift,
    FleetContractViolation,
    PromptVersionDrift,
    RecallLeg,
    assert_fleet_body,
    assert_single_cache_breakpoint,
    audit_body,
    build_fleet_body,
    failures,
)


def raw_transport_body(request: dict[str, Any]) -> dict[str, Any]:
    """Exactly what `providers.judge.BedrockTransport.send` puts on the wire.

    Reading `judge.py`: it calls ``client.messages.create(model=…, max_tokens=…,
    system=…, messages=…, output_config=…)`` and passes nothing else.  This function is
    that call's body, and it is the subject of the red assertion below.
    """
    return {
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": request["max_tokens"],
        "system": request["system"],
        "messages": request["messages"],
        "output_config": request["output_config"],
    }


def test_raw_recall_body_fails_exactly_two_clauses(judge_request: dict[str, Any]) -> None:
    """RED. The un-bound recall body breaks A5 and A4, and nothing else."""
    raw = raw_transport_body(judge_request)
    broken = sorted(finding.check for finding in failures(audit_body(raw)))
    assert broken == ["A4.effort_declared", "A5.thinking_adaptive"], (
        "the recall judge's own wire body is expected to omit `thinking` (A5) and "
        "`output_config.effort` (A4) and to be conforming in every other respect; if this "
        "list changed, the binding's justification changed with it"
    )


def test_bound_body_passes_every_clause(judge_request: dict[str, Any], leg: RecallLeg) -> None:
    """GREEN. The same request, bound to its leg, satisfies the whole contract."""
    body = build_fleet_body(judge_request, leg)
    assert failures(audit_body(body)) == []


def test_audit_body_emits_every_declared_check(
    judge_request: dict[str, Any], leg: RecallLeg
) -> None:
    """A silently deleted check must fail the suite rather than pass it."""
    body = build_fleet_body(judge_request, leg)
    assert tuple(finding.check for finding in audit_body(body)) == BODY_CHECKS


def test_bound_body_keys_are_the_contract_keys(
    judge_request: dict[str, Any], leg: RecallLeg
) -> None:
    """The body has the contract's six keys, in the contract's order, and no others."""
    body = build_fleet_body(judge_request, leg)
    assert tuple(body) == FLEET_BODY_KEYS
    assert body["thinking"] == {"type": "adaptive"}
    assert body["output_config"]["effort"] == str(leg.effort) == "xhigh"


def test_system_and_messages_pass_through_unchanged(
    judge_request: dict[str, Any], leg: RecallLeg
) -> None:
    """The binding never rewrites the bytes the request digest is computed over."""
    body = build_fleet_body(judge_request, leg)
    assert body["system"] == judge_request["system"]
    assert body["messages"] == judge_request["messages"]
    assert body["output_config"]["format"] == judge_request["output_config"]["format"]


def test_cache_breakpoint_is_single_and_last(judge_request: dict[str, Any], leg: RecallLeg) -> None:
    """A9: exactly one ephemeral breakpoint, on the last block of the frozen prefix."""
    body = build_fleet_body(judge_request, leg)
    system = body["system"]
    assert assert_single_cache_breakpoint(system) == len(system) - 1
    assert system[-1]["cache_control"] == {"type": "ephemeral"}
    assert all("cache_control" not in block for block in system[:-1])


@pytest.mark.parametrize(
    "mutation",
    [
        [
            {"type": "text", "text": "a", "cache_control": {"type": "ephemeral"}},
            {"type": "text", "text": "b"},
        ],
        [{"type": "text", "text": "a"}, {"type": "text", "text": "b"}],
        [],
    ],
    ids=["breakpoint-not-last", "no-breakpoint", "empty-prefix"],
)
def test_misplaced_cache_breakpoint_is_refused(mutation: list[dict[str, Any]]) -> None:
    """An un-asserted cache is usually a broken cache, so each shape is refused."""
    with pytest.raises(FleetContractViolation):
        assert_single_cache_breakpoint(mutation)


def test_sampling_parameter_in_the_request_is_refused(
    judge_request: dict[str, Any], leg: RecallLeg
) -> None:
    """A6. A parameter that cannot exist cannot be blamed for drift."""
    poisoned = dict(judge_request)
    poisoned["temperature"] = 0.0
    with pytest.raises(FleetContractViolation):
        build_fleet_body(poisoned, leg)


def test_sampling_parameter_deep_in_a_message_is_refused(
    judge_request: dict[str, Any], leg: RecallLeg
) -> None:
    """A6 holds at any depth: agentkit's guard walks the whole body."""
    poisoned = dict(judge_request)
    poisoned["messages"] = [
        *judge_request["messages"],
        {"role": "user", "content": [{"type": "text", "text": "x", "top_p": 0.9}]},
    ]
    with pytest.raises(ForbiddenRequestField):
        build_fleet_body(poisoned, leg)


def test_a_temperature_setpoint_inside_the_schema_is_not_a_sampling_parameter(
    judge_request: dict[str, Any], leg: RecallLeg
) -> None:
    """The corpus is mining chemistry: a procedure genuinely has a temperature setpoint.

    The guard treats a JSON Schema as opaque data, so an extraction schema with such a
    field is not mistaken for a request parameter.  A guard that fired on the corpus is a
    guard that gets deleted.
    """
    with_setpoint = dict(judge_request)
    output_config = dict(judge_request["output_config"])
    fmt = dict(output_config["format"])
    schema = dict(fmt["schema"])
    schema["properties"] = {**schema.get("properties", {}), "temperature": {"type": "number"}}
    fmt["schema"] = schema
    output_config["format"] = fmt
    with_setpoint["output_config"] = output_config
    body = build_fleet_body(with_setpoint, leg)
    properties = body["output_config"]["format"]["schema"]["properties"]
    assert properties["temperature"]["type"] == "number"


def test_tool_surface_in_the_request_is_refused(
    judge_request: dict[str, Any], leg: RecallLeg
) -> None:
    """Layer 1. The absence of a tool surface is the quarantine, not a convention."""
    poisoned = dict(judge_request)
    poisoned["messages"] = [
        *judge_request["messages"],
        {"role": "user", "content": [{"type": "text", "text": "x"}], "tool_choice": "any"},
    ]
    with pytest.raises(ToolSurfaceConstructed):
        build_fleet_body(poisoned, leg)


def test_prompt_version_drift_is_refused(judge_request: dict[str, Any], leg: RecallLeg) -> None:
    """A13. A prompt edit is a commit, not a deploy."""
    drifted = dict(judge_request)
    drifted["prompt_version"] = "recall-judge-2"
    with pytest.raises(PromptVersionDrift) as caught:
        build_fleet_body(drifted, leg)
    assert caught.value.context["registered"] == leg.prompt_version
    assert caught.value.silence_reason is None, (
        "a contract violation is a defect in our code, not a fact about the corpus; "
        "recording it as silence would put a false absence into the ledger"
    )


def test_budget_drift_is_refused(judge_request: dict[str, Any], leg: RecallLeg) -> None:
    """A5. max_tokens caps thinking PLUS text, so the budget identifies the call."""
    drifted = dict(judge_request)
    drifted["max_tokens"] = 1024
    with pytest.raises(BudgetDrift):
        build_fleet_body(drifted, leg)


def test_conflicting_effort_is_refused_not_overridden(
    judge_request: dict[str, Any], leg: RecallLeg
) -> None:
    """Silently replacing a caller's effort would make the register's claim untrue."""
    conflicting = dict(judge_request)
    output_config = dict(judge_request["output_config"])
    output_config["effort"] = "low"
    conflicting["output_config"] = output_config
    with pytest.raises(FleetContractViolation) as caught:
        build_fleet_body(conflicting, leg)
    assert caught.value.context["decision"] == "A4"


def test_matching_effort_is_accepted(judge_request: dict[str, Any], leg: RecallLeg) -> None:
    """A caller that already declared the registered effort is not fighting the register."""
    declared = dict(judge_request)
    output_config = dict(judge_request["output_config"])
    output_config["effort"] = str(leg.effort)
    declared["output_config"] = output_config
    assert build_fleet_body(declared, leg)["output_config"]["effort"] == str(leg.effort)


def test_assert_fleet_body_rejects_a_disabled_thinking_block(
    judge_request: dict[str, Any], leg: RecallLeg
) -> None:
    """A5 forbids `disabled` as loudly as it forbids omission."""
    body = build_fleet_body(judge_request, leg)
    body["thinking"] = {"type": "disabled"}
    with pytest.raises(FleetContractViolation) as caught:
        assert_fleet_body(body)
    assert caught.value.context["decision"] == "A5"


def test_missing_required_request_key_is_named(
    judge_request: dict[str, Any], leg: RecallLeg
) -> None:
    """The refusal names what was missing rather than raising a KeyError somewhere else."""
    incomplete = {k: v for k, v in judge_request.items() if k != "output_config"}
    with pytest.raises(FleetContractViolation) as caught:
        build_fleet_body(incomplete, leg)
    assert caught.value.context["missing"] == ["output_config"]
