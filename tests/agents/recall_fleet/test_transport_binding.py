# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
"""The transport seam: residency, refusal translation, retry count, provenance, silence.

Every assertion here is about a *refusal* or about the record a refusal leaves, because
that is what the recall agent's degraded mode is made of: Bedrock throttled, the model
refusing, or a guardrail firing must complete on channels A+B, record `arms_degraded`,
write the silence rows and **still block the merge**.  A binding that swallowed one of
those exceptions would turn a blocked merge into a merge, silently, and it would do it in
the one direction nobody notices.
"""

from __future__ import annotations

import json
from typing import Any

import pytest
from _fleet_support import TEST_PROFILE_ARN, FakeTransport, RerankVerdict, text_response
from mainline_recall_agent.providers.errors import (
    CassetteMiss,
    DeadLetter,
    ModelRefusal,
    ModelTruncated,
    ProviderUnavailable,
    ResidencyViolation,
)
from mainline_recall_agent.providers.judge import BedrockClaudeJudge
from mainline_recall_agent.providers.system_blocks import build_system_blocks
from mainline_recall_agent.providers.types import ResolvedModel
from mainline_recall_fleet import (
    FleetContractViolation,
    FleetJudgeTransport,
    PromptVersionDrift,
    RecallLeg,
    fleet_silence_row,
)

VERDICT = {"mechanism": "sulfide gas release", "precondition": "sump not purged", "relevant": True}


# ── residency, asserted once, at start-up ───────────────────────────────────────


@pytest.mark.parametrize(
    "identifier",
    [
        "anthropic.claude-opus-5-20260101-v1:0",  # bare foundation-model id
        "global.anthropic.claude-opus-5",  # routes to every commercial Region
        "apac.anthropic.claude-opus-5",  # can take a Queensland narrative offshore
        "",
    ],
)
def test_non_australian_profile_is_refused_at_construction(identifier: str, leg: RecallLeg) -> None:
    """§10.1 layer 1. A control a caller can decline is not a control."""
    with pytest.raises(ResidencyViolation):
        FleetJudgeTransport(inner=FakeTransport([]), leg=leg, inference_profile_arn=identifier)


def test_a_non_agentkit_provider_is_refused(leg: RecallLeg) -> None:
    """The body guards live inside the agentkit transport as well as in this package."""

    class NotATransport:
        pass

    with pytest.raises(FleetContractViolation):
        FleetJudgeTransport(
            inner=NotATransport(),  # type: ignore[arg-type]
            leg=leg,
            inference_profile_arn=TEST_PROFILE_ARN,
        )


# ── the happy path, and what it records ─────────────────────────────────────────


def test_a_clean_call_returns_the_text_and_the_wire_body_conforms(
    judge_request: dict[str, Any], bound: Any
) -> None:
    """The reply the judge validates is the one the fleet body produced."""
    transport, fake = bound([text_response(json.dumps(VERDICT))])
    reply = transport.send(judge_request)
    assert reply.stop_reason == "end_turn"
    assert json.loads(reply.text) == VERDICT
    assert reply.usage.cache_read_input_tokens == 1024
    sent = fake.requests[0]
    assert sent.model_id == TEST_PROFILE_ARN
    assert sent.body["thinking"] == {"type": "adaptive"}
    assert sent.body["output_config"]["effort"] == "xhigh"


def test_provenance_carries_the_replayability_record(
    judge_request: dict[str, Any], bound: Any
) -> None:
    """§8.2: replayability is the claim, and every field of it is on the record."""
    transport, _ = bound([text_response(json.dumps(VERDICT))])
    transport.send(judge_request)
    record = transport.provenance()
    assert record["leg_id"] == "recall.rerank.listwise"
    assert record["agent_name"] == "mainline-recall"
    assert record["sql_role"] == "agent_recaller"
    assert record["inference_profile_arn"] == TEST_PROFILE_ARN
    assert record["model_id"] == "claude-opus-5"
    assert len(record["input_sha256"]) == 64
    assert len(record["output_sha256"]) == 64
    assert len(record["prefix_digest"]) == 64
    assert record["usage"]["cache_read_input_tokens"] == 1024


def test_provenance_before_any_call_is_refused(leg: RecallLeg) -> None:
    """An empty record would be a claim about a call that never happened."""
    transport = FleetJudgeTransport(
        inner=FakeTransport([]), leg=leg, inference_profile_arn=TEST_PROFILE_ARN
    )
    with pytest.raises(FleetContractViolation):
        transport.provenance()


def test_identity_components_are_the_seven_in_order(bound: Any) -> None:
    """A13's formula takes seven components; this returns them and hashes none of them."""
    transport, _ = bound([])
    components = transport.identity_components(schema_version="sha256:abc")
    assert list(components) == [
        "agent_name",
        "sql_role",
        "iam_role_arn",
        "prompt_version",
        "model_id",
        "inference_profile_arn",
        "schema_version",
    ]
    assert components["prompt_version"] == "recall-judge-1"


# ── refusal, truncation, and the unknown ────────────────────────────────────────


def test_refusal_becomes_a_recall_model_refusal(judge_request: dict[str, Any], bound: Any) -> None:
    """A8. The orchestrator's degraded path catches the recall class, not agentkit's."""
    transport, _ = bound([text_response("", stop_reason="refusal")])
    with pytest.raises(ModelRefusal) as caught:
        transport.send(judge_request)
    assert caught.value.silence_reason == "model_refusal"
    assert caught.value.context["category"] == "model_refusal"
    assert caught.value.context["leg_id"] == "recall.rerank.listwise"


def test_a_guardrail_intervention_is_a_refusal_the_judge_could_not_have_seen(
    judge_request: dict[str, Any], bound: Any
) -> None:
    """Bedrock reports a Guardrail block out of band from `stop_reason`.

    The recall judge branches on `stop_reason` alone, so an intervened response with
    `end_turn` would have been read as a clean completion with empty content.  The fleet
    classifier sees it, and a guardrail that fires and is then ignored is not a guardrail.
    """
    intervened = text_response("", **{"amazon-bedrock-guardrailAction": "INTERVENED"})
    transport, _ = bound([intervened])
    with pytest.raises(ModelRefusal) as caught:
        transport.send(judge_request)
    assert caught.value.context["category"] == "guardrail_intervention"


def test_max_tokens_becomes_model_truncated(judge_request: dict[str, Any], bound: Any) -> None:
    """A5. A cut-off answer is not an answer, so it is fatal rather than absorbed."""
    transport, _ = bound([text_response('{"mech', stop_reason="max_tokens")])
    with pytest.raises(ModelTruncated) as caught:
        transport.send(judge_request)
    assert caught.value.silence_reason == "truncated"


def test_an_unrecognised_stop_reason_fails_closed(
    judge_request: dict[str, Any], bound: Any
) -> None:
    """A stop reason nobody has classified is not evidence that the model answered."""
    transport, _ = bound([text_response(json.dumps(VERDICT), stop_reason="thermal_shutdown")])
    with pytest.raises(ModelRefusal) as caught:
        transport.send(judge_request)
    assert caught.value.context["category"] == "unknown_stop_reason"


def test_the_unbound_judge_would_have_accepted_that_stop_reason(leg: RecallLeg) -> None:
    """The hardening is real, and this is the measurement rather than the claim.

    `BedrockClaudeJudge._check_stop_reason` branches on `refusal` and `max_tokens` and
    treats everything else as a normal completion.  Driven by a transport that returns an
    unknown stop reason with valid content, the un-bound judge returns a verdict.
    """

    class UnknownStopTransport:
        def send(self, request: dict[str, Any]) -> Any:  # noqa: ARG002 - protocol shape
            from mainline_recall_agent.providers.judge import TransportReply

            return TransportReply(stop_reason="thermal_shutdown", text=json.dumps(VERDICT))

    judge = _judge(leg, UnknownStopTransport())
    verdict = judge.judge(_prefix(leg), {"candidates": []}, RerankVerdict)
    assert verdict.relevant is True, (
        "if this ever raises instead, the recall judge has learned to fail closed and the "
        "fleet binding's unknown-stop-reason translation is no longer load-bearing"
    )


def test_provider_unavailable_is_distinct_from_a_refusal(
    judge_request: dict[str, Any], leg: RecallLeg
) -> None:
    """Nothing was asked and nothing was declined, so the candidate is unreachable."""
    from mainline_agentkit import TransportUnavailable

    class DeadTransport(FakeTransport):
        def invoke(self, request: Any) -> Any:  # noqa: ARG002 - protocol shape
            raise TransportUnavailable("no route to bedrock-runtime")

    transport = FleetJudgeTransport(
        inner=DeadTransport([]), leg=leg, inference_profile_arn=TEST_PROFILE_ARN
    )
    with pytest.raises(ProviderUnavailable) as caught:
        transport.send(judge_request)
    assert caught.value.silence_reason == "unreachable"


def test_a_cassette_miss_is_a_defect_not_silence(
    judge_request: dict[str, Any], leg: RecallLeg
) -> None:
    """Replay never falls through to a live call, and a miss is nobody's silence."""
    from mainline_agentkit import CassetteMiss as AgentkitCassetteMiss

    class MissingTransport(FakeTransport):
        def invoke(self, request: Any) -> Any:
            raise AgentkitCassetteMiss(request.cassette_key, "tests/fixtures/cassettes/recall")

    transport = FleetJudgeTransport(
        inner=MissingTransport([]), leg=leg, inference_profile_arn=TEST_PROFILE_ARN
    )
    with pytest.raises(CassetteMiss) as caught:
        transport.send(judge_request)
    assert caught.value.silence_reason is None


# ── the retry rule stays where it belongs ───────────────────────────────────────


def test_schema_violation_gets_exactly_one_repair_then_dead_letters(leg: RecallLeg) -> None:
    """One call, one repair, then DeadLetter — two transport calls, never three."""
    fake = FakeTransport([text_response("not json"), text_response("still not json")])
    transport = FleetJudgeTransport(inner=fake, leg=leg, inference_profile_arn=TEST_PROFILE_ARN)
    judge = _judge(leg, transport)
    with pytest.raises(DeadLetter) as caught:
        judge.judge(_prefix(leg), {"candidates": []}, RerankVerdict)
    assert caught.value.silence_reason == "abstained"
    assert transport.call_count == 2
    assert len(fake.requests) == 2


def test_a_clean_call_through_the_judge_makes_exactly_one_transport_call(leg: RecallLeg) -> None:
    """No hidden warming call, no speculative second shot."""
    fake = FakeTransport([text_response(json.dumps(VERDICT))])
    transport = FleetJudgeTransport(inner=fake, leg=leg, inference_profile_arn=TEST_PROFILE_ARN)
    judge = _judge(leg, transport)
    verdict = judge.judge(_prefix(leg), {"candidates": []}, RerankVerdict)
    assert verdict.mechanism == "sulfide gas release"
    assert transport.call_count == 1


# ── silence is a row ────────────────────────────────────────────────────────────


def test_a_refusal_becomes_a_silence_ledger_row(judge_request: dict[str, Any], bound: Any) -> None:
    """A8. The row carries the replayability quad, because a refusal has no score."""
    transport, _ = bound([text_response("", stop_reason="refusal")])
    with pytest.raises(ModelRefusal) as caught:
        transport.send(judge_request)
    row = fleet_silence_row(
        caught.value,
        site_id="site-nw-01",
        subject_kind="event",
        subject_id="evt-1993-0042",
        severity=5,
        policy_version="recall-policy-3",
    ).to_mapping()
    assert row["source"] == "recall"
    assert row["reason"] == "model_refusal"
    assert row["severity"] == 5
    assert row["score"] is None
    assert row["threshold"] is None
    assert row["arithmetic"]["inference_profile_arn"] == TEST_PROFILE_ARN
    assert row["arithmetic"]["prompt_version"] == "recall-judge-1"
    assert row["at"] is not None
    assert row["at"].tzinfo is not None


def test_a_truncation_becomes_a_row_with_its_own_reason(
    judge_request: dict[str, Any], bound: Any
) -> None:
    """`truncated` and `model_refusal` are different facts and different rows."""
    transport, _ = bound([text_response("{", stop_reason="max_tokens")])
    with pytest.raises(ModelTruncated) as caught:
        transport.send(judge_request)
    row = fleet_silence_row(
        caught.value,
        site_id="site-nw-01",
        subject_kind="event",
        subject_id="evt-1993-0042",
        severity=4,
    ).to_mapping()
    assert row["reason"] == "truncated"
    assert row["arithmetic"]["fallback"] == "channels A+B, arms_degraded=true"


def test_a_defect_may_never_become_silence(judge_request: dict[str, Any], leg: RecallLeg) -> None:
    """A ProviderError with no silence_reason is a bug in our code, not an absence."""
    transport = FleetJudgeTransport(
        inner=FakeTransport([]), leg=leg, inference_profile_arn=TEST_PROFILE_ARN
    )
    drifted = dict(judge_request)
    drifted["prompt_version"] = "recall-judge-99"
    with pytest.raises(PromptVersionDrift) as caught:
        transport.send(drifted)
    assert caught.value.silence_reason is None
    assert transport.call_count == 0, "the contract violation never reached a wire"
    with pytest.raises(FleetContractViolation):
        fleet_silence_row(
            caught.value,
            site_id="site-nw-01",
            subject_kind="event",
            subject_id="evt-1993-0042",
            severity=5,
        )


def test_a_reason_the_leg_does_not_declare_is_refused() -> None:
    """The register is the complete statement of what a capability can fail as."""
    from mainline_recall_agent.providers.errors import ProviderError

    class Invented(ProviderError):
        silence_reason = "dedup_sibling"

    with pytest.raises(FleetContractViolation):
        fleet_silence_row(
            Invented("x", leg_id="recall.cue.event"),
            site_id="site-nw-01",
            subject_kind="event",
            subject_id="evt-1",
            severity=3,
        )


# ── helpers ─────────────────────────────────────────────────────────────────────


def _prefix(leg: RecallLeg) -> Any:
    return build_system_blocks(
        rubric="Name the shared mechanism AND the shared precondition, or return not_relevant.",
        facet_definitions="mechanism / precondition / control_failure / recurrence_test",
        few_shots="Example: a purge line left connected is a precondition, not a mechanism.",
        prompt_version=leg.prompt_version,
    )


def _judge(leg: RecallLeg, transport: Any) -> BedrockClaudeJudge:
    return BedrockClaudeJudge(
        resolved_model=ResolvedModel(
            requested_tier="claude-opus-5",
            resolved_tier="claude-opus-5",
            profile_id="au.anthropic.claude-opus-5",
            profile_arn=TEST_PROFILE_ARN,
            region="ap-southeast-2",
            source="pinned",
        ),
        transport=transport,
        prompt_version=leg.prompt_version,
        max_tokens=leg.max_tokens,
    )
