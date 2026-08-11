# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
"""Runtime inference-profile resolution: residency, degradation, and refusal to guess.

``select_profile`` is pure, so the whole policy is testable against synthetic
``ListInferenceProfiles`` payloads with no AWS account.  The profile ids below are
fixtures, not constants: nothing in the package may contain one.
"""

from __future__ import annotations

import pytest
from mainline_recall_agent.providers.errors import (
    ProfileResolutionFailed,
    ProviderUnavailable,
    ResidencyViolation,
)
from mainline_recall_agent.providers.resolve import (
    pinned_model,
    resolve_inference_profile,
    select_profile,
)

# Built by concatenation so that no complete Bedrock model identifier appears as a literal
# anywhere in the tree — the same discipline the package itself is held to.
_VENDOR = "anthropic"


def _summary(prefix: str, tier: str, *, status: str = "ACTIVE") -> dict[str, object]:
    profile_id = f"{prefix}{_VENDOR}.{tier}-20260115-v1:0"
    return {
        "inferenceProfileId": profile_id,
        "inferenceProfileArn": f"arn:aws:bedrock:ap-southeast-2:111122223333:"
        f"inference-profile/{profile_id}",
        "inferenceProfileName": f"{tier} (Australia)",
        "status": status,
        "type": "SYSTEM_DEFINED",
    }


def test_the_requested_tier_is_selected_when_an_au_profile_exists() -> None:
    resolved = select_profile(
        [
            _summary("au.", "claude-sonnet-4-5"),
            _summary("au.", "claude-opus-5"),
        ],
        requested_tier="claude-opus-5",
    )
    assert resolved.resolved_tier == "claude-opus-5"
    assert resolved.profile_id.startswith("au.")
    assert resolved.degraded is False
    assert resolved.source == "bedrock:ListInferenceProfiles"
    assert resolved.resolved_at is not None


def test_a_missing_tier_degrades_down_the_ladder_and_says_so() -> None:
    """ARCHITECTURE §10.1: ship the previous generation and say so — as a field."""
    resolved = select_profile(
        [_summary("au.", "claude-sonnet-4-5")], requested_tier="claude-opus-5"
    )
    assert resolved.requested_tier == "claude-opus-5"
    assert resolved.resolved_tier == "claude-sonnet-4-5"
    assert resolved.degraded is True


def test_non_au_profiles_are_never_selected_even_when_they_are_the_only_match() -> None:
    """A global.* or apac.* profile is a residency failure, not a fallback."""
    with pytest.raises(ProfileResolutionFailed):
        select_profile(
            [_summary("global.", "claude-opus-5"), _summary("apac.", "claude-opus-5")],
            requested_tier="claude-opus-5",
        )


def test_inactive_profiles_are_ignored() -> None:
    with pytest.raises(ProfileResolutionFailed):
        select_profile(
            [_summary("au.", "claude-opus-5", status="INACTIVE")],
            requested_tier="claude-opus-5",
        )


def test_no_visible_profile_fails_loudly_rather_than_falling_back_to_a_constant() -> None:
    with pytest.raises(ProfileResolutionFailed, match="degrade to channels A"):
        select_profile([], requested_tier="claude-opus-5")


def test_an_unknown_tier_with_no_ladder_match_refuses_to_guess() -> None:
    with pytest.raises(ProfileResolutionFailed, match="refusing to guess"):
        select_profile([_summary("au.", "some-other-vendor-model")], requested_tier="claude-opus-5")


def test_name_matching_tolerates_bedrock_id_punctuation() -> None:
    """`claude-sonnet-4-5` must match a profile id spelling it any of the usual ways."""
    resolved = select_profile(
        [
            {
                "inferenceProfileId": f"au.{_VENDOR}.claude-sonnet-4-5-20260115-v1:0",
                "inferenceProfileName": "Claude Sonnet 4.5",
                "status": "ACTIVE",
            }
        ],
        requested_tier="claude-sonnet-4-5",
    )
    assert resolved.resolved_tier == "claude-sonnet-4-5"


def test_a_pinned_policy_row_is_re_asserted_for_residency() -> None:
    """A recall_policy row is not a bypass."""
    with pytest.raises(ResidencyViolation, match="non-Australian"):
        pinned_model(
            profile_id=f"global.{_VENDOR}.claude-opus-5-20260115-v1:0",
            profile_arn=None,
            requested_tier="claude-opus-5",
            resolved_tier="claude-opus-5",
        )


def test_a_pinned_au_profile_is_accepted_and_marked_pinned() -> None:
    resolved = pinned_model(
        profile_id=f"au.{_VENDOR}.claude-opus-5-20260115-v1:0",
        profile_arn="arn:aws:bedrock:ap-southeast-2:111122223333:inference-profile/x",
        requested_tier="claude-opus-5",
        resolved_tier="claude-opus-5",
    )
    assert resolved.source == "pinned"
    assert resolved.agent_identity_fields()["model_id"].startswith("au.")


def test_resolution_paginates() -> None:
    class _Client:
        def __init__(self) -> None:
            self.calls = 0

        def list_inference_profiles(self, **kwargs: object) -> dict[str, object]:
            self.calls += 1
            if "nextToken" not in kwargs:
                return {
                    "inferenceProfileSummaries": [_summary("au.", "claude-haiku-4-5")],
                    "nextToken": "page-2",
                }
            return {"inferenceProfileSummaries": [_summary("au.", "claude-opus-5")]}

    client = _Client()
    resolved = resolve_inference_profile(client=client, requested_tier="claude-opus-5")
    assert client.calls == 2
    assert resolved.resolved_tier == "claude-opus-5"


def test_a_failing_control_plane_call_is_unavailable_not_a_silent_default() -> None:
    class _Client:
        def list_inference_profiles(self, **_: object) -> dict[str, object]:
            raise RuntimeError("no credentials")

    with pytest.raises(ProviderUnavailable) as excinfo:
        resolve_inference_profile(client=_Client())
    assert "no hard-coded fallback exists by design" in str(excinfo.value)
    assert excinfo.value.silence_reason == "unreachable"
