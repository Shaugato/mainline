# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
"""Fixtures for the recall-agent ⇄ fleet binding suite.

The doubles live in `_fleet_support.py`; this file is the fixture surface.

The prefix below is built with the recall package's own `build_system_blocks` rather than
hand-rolled dicts: that builder refuses volatile content in a system prefix (UUIDs, ISO
instants, run markers, format placeholders), and a fixture that dodged the refusal would
be asserting against a prefix production could never produce.  The request is likewise
built by `BedrockClaudeJudge.build_request`, so if the recall package changes its request
shape this suite fails rather than asserting against a shape nothing emits.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest
from _fleet_support import TEST_PROFILE_ARN, FakeTransport, RerankVerdict
from mainline_recall_agent.providers.judge import BedrockClaudeJudge
from mainline_recall_agent.providers.system_blocks import build_system_blocks, build_user_turn
from mainline_recall_agent.providers.types import ResolvedModel
from mainline_recall_fleet import FleetJudgeTransport, get_leg

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    from mainline_recall_fleet import RecallLeg


@pytest.fixture
def leg() -> RecallLeg:
    """The listwise rerank leg — the one whose output becomes `evidence_summary`."""
    return get_leg("recall.rerank.listwise")


@pytest.fixture
def judge_request(leg: RecallLeg) -> dict[str, Any]:
    """A real canonical request, produced by the recall judge's own builder."""
    prefix = build_system_blocks(
        rubric=(
            "Name the shared mechanism AND the shared precondition, or return "
            "not_relevant. Do not answer with a similarity impression."
        ),
        facet_definitions=(
            "mechanism: the physical process that did the harm. "
            "precondition: the state that had to hold first. "
            "control_failure: the barrier that did not hold. "
            "recurrence_test: what would show it can happen again."
        ),
        few_shots=(
            "Example: a nitrogen purge line left connected is a precondition, not a mechanism."
        ),
        prompt_version=leg.prompt_version,
    )
    judge = BedrockClaudeJudge(
        resolved_model=ResolvedModel(
            requested_tier="claude-opus-5",
            resolved_tier="claude-opus-5",
            profile_id="au.anthropic.claude-opus-5",
            profile_arn=TEST_PROFILE_ARN,
            region="ap-southeast-2",
            source="pinned",
        ),
        prompt_version=leg.prompt_version,
        max_tokens=leg.max_tokens,
    )
    return judge.build_request(
        system=prefix,
        messages=[build_user_turn({"candidates": [{"ord": 1, "cue": "hydrogen sulfide release"}]})],
        schema=RerankVerdict,
    )


@pytest.fixture
def bound(leg: RecallLeg) -> Any:
    """A factory returning ``(bound_transport, fake_inner)`` for the rerank leg."""

    def _bind(responses: Sequence[Mapping[str, Any]]) -> tuple[FleetJudgeTransport, FakeTransport]:
        fake = FakeTransport(responses)
        return (
            FleetJudgeTransport(
                inner=fake,
                leg=leg,
                inference_profile_arn=TEST_PROFILE_ARN,
                iam_role_arn="arn:aws:iam::000000000000:role/mainline-recall",
            ),
            fake,
        )

    return _bind
