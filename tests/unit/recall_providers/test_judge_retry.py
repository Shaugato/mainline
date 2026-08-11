# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
"""The judge's failure contract: one repair, then a dead letter; refusal before content."""

from __future__ import annotations

import json
from typing import Any

import pytest
from mainline_recall_agent.providers.cassette import CassetteJudgeTransport, CassetteStore
from mainline_recall_agent.providers.errors import (
    CANONICAL_SILENCE_REASONS,
    DeadLetter,
    ModelRefusal,
    ModelTruncated,
    ProviderError,
)
from mainline_recall_agent.providers.judge import BedrockClaudeJudge, TransportReply
from mainline_recall_agent.providers.registry import cassette_resolved_model, get_judge_provider
from mainline_recall_agent.providers.system_blocks import build_system_blocks
from mainline_recall_agent.providers.types import Usage

from .fixture_schema import (
    FACET_DEFINITIONS,
    FEW_SHOTS,
    PROMPT_VERSION,
    RUBRIC,
    RerankVerdict,
    judge_payload,
)


@pytest.fixture
def prefix():  # type: ignore[no-untyped-def]
    return build_system_blocks(
        rubric=RUBRIC,
        facet_definitions=FACET_DEFINITIONS,
        few_shots=FEW_SHOTS,
        prompt_version=PROMPT_VERSION,
    )


def _judge(store: CassetteStore) -> BedrockClaudeJudge:
    return BedrockClaudeJudge(
        resolved_model=cassette_resolved_model(),
        transport=CassetteJudgeTransport(store),
        prompt_version=PROMPT_VERSION,
        max_tokens=4096,
    )


def _payload(ref: str) -> dict[str, Any]:
    return judge_payload(ref, ["FX-001", "FX-010"])


# --------------------------------------------------------------------------------------
# Happy path
# --------------------------------------------------------------------------------------


def test_a_valid_response_validates_in_one_call(store: CassetteStore, prefix: Any) -> None:
    judge = _judge(store)
    verdict = judge.judge(prefix, _payload("FX-EXP-CACHE-1"), RerankVerdict)
    assert isinstance(verdict, RerankVerdict)
    assert judge.call_count == 1
    assert verdict.verdicts[0].relevance == "relevant"
    assert verdict.verdicts[0].shared_mechanism
    assert verdict.verdicts[0].shared_precondition


def test_the_result_carries_the_evidence_needed_to_reproduce_it(
    store: CassetteStore, prefix: Any
) -> None:
    result = _judge(store).judge_detailed(prefix, _payload("FX-EXP-CACHE-1"), RerankVerdict)
    assert len(result.request_digest) == 64
    assert result.attempts == 1
    assert result.model.source == "cassette"
    assert result.stop_reason == "end_turn"


# --------------------------------------------------------------------------------------
# Exactly one repair
# --------------------------------------------------------------------------------------


def test_one_repair_attempt_recovers_a_schema_violation(store: CassetteStore, prefix: Any) -> None:
    judge = _judge(store)
    result = judge.judge_detailed(prefix, _payload("FX-EXP-REPAIR"), RerankVerdict)
    assert result.attempts == 2
    assert judge.call_count == 2


def test_two_failures_dead_letter_and_never_make_a_third_call(
    store: CassetteStore, prefix: Any
) -> None:
    judge = _judge(store)
    with pytest.raises(DeadLetter):
        judge.judge(prefix, _payload("FX-EXP-DEADLETTER"), RerankVerdict)
    assert judge.call_count == 2, "the judge retried more than once"
    assert judge.MAX_ATTEMPTS == 2


def test_the_dead_letter_carries_what_the_caller_needs_for_the_silence_ledger(
    store: CassetteStore, prefix: Any
) -> None:
    with pytest.raises(DeadLetter) as excinfo:
        _judge(store).judge(prefix, _payload("FX-EXP-DEADLETTER"), RerankVerdict)
    error = excinfo.value
    assert error.silence_reason == "abstained"
    assert error.silence_reason in CANONICAL_SILENCE_REASONS
    assert len(error.request_digest) == 64
    assert len(error.attempts) == 2
    assert error.attempts[0]["error"] and error.attempts[1]["error"]
    assert error.attempts[0]["raw"]
    assert error.model["requested_tier"] == "claude-opus-5"


def test_the_repair_turn_carries_the_validator_error_verbatim(prefix: Any) -> None:
    """The repair prompt restates nothing about the task — only the validator's message."""
    captured: list[dict[str, Any]] = []

    class _Transport:
        def send(self, request: dict[str, Any]) -> TransportReply:
            captured.append(request)
            return TransportReply(stop_reason="end_turn", text='{"verdicts": "not a list"}')

    judge = BedrockClaudeJudge(
        resolved_model=cassette_resolved_model(),
        transport=_Transport(),
        prompt_version=PROMPT_VERSION,
    )
    with pytest.raises(DeadLetter):
        judge.judge(prefix, _payload("X"), RerankVerdict)

    assert len(captured) == 2
    repair_messages = captured[1]["messages"]
    assert [m["role"] for m in repair_messages] == ["user", "assistant", "user"]
    repair_text = repair_messages[-1]["content"][0]["text"]
    assert "failed schema validation" in repair_text
    assert "verdicts" in repair_text


# --------------------------------------------------------------------------------------
# Refusal and truncation — read stop_reason BEFORE content
# --------------------------------------------------------------------------------------


def test_a_refusal_raises_rather_than_returning_an_empty_result(
    store: CassetteStore, prefix: Any
) -> None:
    judge = _judge(store)
    with pytest.raises(ModelRefusal) as excinfo:
        judge.judge(prefix, _payload("FX-EXP-REFUSAL"), RerankVerdict)
    assert judge.call_count == 1, "a refusal must not be retried"
    assert excinfo.value.silence_reason == "model_refusal"
    assert excinfo.value.silence_reason in CANONICAL_SILENCE_REASONS


def test_stop_reason_is_checked_before_content_is_touched(
    prefix: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The ordering guarantee, proved rather than commented.

    The scripted reply carries a refusal stop_reason *and* a body that would validate
    perfectly.  Two things are asserted: that the refusal raises, and — the part that
    actually pins the ordering — that the validator was **never called**.  Without the
    second assertion, code that parsed content first and checked ``stop_reason``
    afterwards would still pass, and the day the parse has a side effect (a token spend, a
    log line claiming a verdict, a cached partial) the refusal would already have been
    laundered into an answer.
    """
    seen: list[str] = []
    original = BedrockClaudeJudge._validate

    def _spy(text: str, schema: Any) -> Any:
        seen.append(text)
        return original(text, schema)

    monkeypatch.setattr(BedrockClaudeJudge, "_validate", staticmethod(_spy))

    perfectly_valid = json.dumps(
        {
            "verdicts": [
                {
                    "candidate_ref": "FX-001",
                    "relevance": "not_relevant",
                    "shared_mechanism": "none",
                    "shared_precondition": "none",
                    "justification": "no shared mechanism could be named",
                }
            ]
        }
    )

    class _Transport:
        def send(self, request: dict[str, Any]) -> TransportReply:
            return TransportReply(
                stop_reason="refusal",
                text=perfectly_valid,
                usage=Usage(input_tokens=10, output_tokens=1),
            )

    judge = BedrockClaudeJudge(
        resolved_model=cassette_resolved_model(),
        transport=_Transport(),
        prompt_version=PROMPT_VERSION,
    )
    with pytest.raises(ModelRefusal):
        judge.judge(prefix, _payload("X"), RerankVerdict)
    assert seen == [], "the refusal's content was parsed before stop_reason was checked"


def test_truncation_raises_and_maps_to_the_truncated_reason(
    store: CassetteStore, prefix: Any
) -> None:
    judge = _judge(store)
    with pytest.raises(ModelTruncated) as excinfo:
        judge.judge(prefix, _payload("FX-EXP-TRUNCATED"), RerankVerdict)
    assert judge.call_count == 1
    assert excinfo.value.silence_reason == "truncated"


def test_every_provider_exception_maps_into_the_closed_silence_vocabulary() -> None:
    """A new failure mode cannot quietly become "nothing happened"."""
    from mainline_recall_agent.providers import errors as error_module

    subclasses = [
        obj
        for obj in vars(error_module).values()
        if isinstance(obj, type) and issubclass(obj, ProviderError) and obj is not ProviderError
    ]
    assert subclasses
    for subclass in subclasses:
        reason = subclass.silence_reason
        assert reason is None or reason in CANONICAL_SILENCE_REASONS, subclass.__name__


# --------------------------------------------------------------------------------------
# Contract enforcement
# --------------------------------------------------------------------------------------


def test_a_raw_list_of_system_blocks_is_refused(store: CassetteStore) -> None:
    judge = _judge(store)
    with pytest.raises(ProviderError, match="stability contract"):
        judge.judge([{"type": "text", "text": "hi"}], _payload("X"), RerankVerdict)


def test_the_registry_builds_a_replay_judge_by_default(store: CassetteStore, prefix: Any) -> None:
    judge = get_judge_provider(store=store, prompt_version=PROMPT_VERSION)
    assert judge.resolved_model.source == "cassette"
    assert judge.resolved_model.profile_id.startswith("cassette://")
    verdict = judge.judge(prefix, _payload("FX-EXP-CACHE-1"), RerankVerdict)
    assert isinstance(verdict, RerankVerdict)
