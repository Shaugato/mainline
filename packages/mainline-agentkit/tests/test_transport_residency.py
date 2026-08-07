# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""Residency: ``au.*`` or refuse to serve, resolved at start-up and never hard-coded.

§10.1 and decisions A3/AR-2. No test here needs AWS: the resolver takes an injected
client, so the *logic* that decides whether a profile is Australian is covered offline
and the only thing a live credential would add is the network round trip.

The honest statement this suite protects (F5, and repeated in the README): inference
runs in Australia; on the free demo tier the database is in Singapore, so end-to-end
Australian residency is FALSE for that deployment and is never claimed.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from mainline_agentkit import (
    AgentkitSettings,
    ResidencyRefused,
    TransportUnavailable,
    assert_australian_profile,
    resolve_inference_profile,
    select_transport,
)

AU_ARN = "arn:aws:bedrock:ap-southeast-2:000000000000:inference-profile/au.anthropic.claude-opus-5"


class FakeBedrock:
    """A ``bedrock`` control-plane client that paginates, for the resolver."""

    def __init__(self, pages):
        self.pages = pages
        self.calls = []

    def list_inference_profiles(self, **kwargs):
        self.calls.append(kwargs)
        return self.pages[len(self.calls) - 1]


def _page(ids, next_token=None):
    page = {
        "inferenceProfileSummaries": [
            {
                "inferenceProfileId": profile_id,
                "inferenceProfileArn": (
                    f"arn:aws:bedrock:ap-southeast-2:000000000000:inference-profile/{profile_id}"
                ),
                "status": "ACTIVE",
            }
            for profile_id in ids
        ]
    }
    if next_token:
        page["nextToken"] = next_token
    return page


@pytest.mark.parametrize(
    "identifier",
    ["au.anthropic.claude-opus-5", AU_ARN],
)
def test_australian_identifiers_are_accepted(identifier):
    assert assert_australian_profile(identifier) == "au.anthropic.claude-opus-5"


@pytest.mark.parametrize(
    "identifier",
    [
        "global.anthropic.claude-opus-5",
        "apac.anthropic.claude-opus-5",
        "us.anthropic.claude-opus-5",
        "eu.anthropic.claude-opus-5",
        "arn:aws:bedrock:us-east-1:1:inference-profile/us.anthropic.claude-opus-5",
    ],
)
def test_cross_region_profiles_are_refused(identifier):
    with pytest.raises(ResidencyRefused) as excinfo:
        assert_australian_profile(identifier)
    assert "cross-region profile prefix" in excinfo.value.reason


def test_a_bare_foundation_model_id_is_refused():
    # Bedrock would accept it. We do not: a bare model id bypasses the inference
    # profile that the VPC-endpoint policy enumerates, so the control would still be in
    # the policy and no longer in the path.
    with pytest.raises(ResidencyRefused, match="bypasses"):
        assert_australian_profile("anthropic.claude-opus-5-v1:0")


def test_an_arn_that_is_not_an_inference_profile_is_refused():
    with pytest.raises(ResidencyRefused, match="does not name an inference profile"):
        assert_australian_profile(
            "arn:aws:bedrock:ap-southeast-2:1:foundation-model/au.anthropic.claude-opus-5"
        )


def test_an_empty_identifier_is_refused():
    with pytest.raises(ResidencyRefused, match="empty"):
        assert_australian_profile("")


def test_the_resolver_paginates_and_pins_the_australian_arn():
    client = FakeBedrock(
        [
            _page(["global.anthropic.claude-opus-5", "us.anthropic.claude-sonnet-5"], "more"),
            _page(["apac.anthropic.claude-opus-5", "au.anthropic.claude-opus-5"]),
        ]
    )
    resolved = resolve_inference_profile("claude-opus-5", client=client)
    assert resolved.profile_id == "au.anthropic.claude-opus-5"
    assert resolved.profile_arn == AU_ARN
    assert resolved.region == "ap-southeast-2"
    assert len(client.calls) == 2
    assert client.calls[1]["nextToken"] == "more"


def test_no_australian_profile_is_a_refusal_naming_ar2():
    client = FakeBedrock([_page(["global.anthropic.claude-opus-6"])])
    with pytest.raises(ResidencyRefused) as excinfo:
        resolve_inference_profile("claude-opus-6", client=client)
    assert "AR-2" in str(excinfo.value)


def test_the_live_provider_needs_two_locks_open():
    with pytest.raises(TransportUnavailable, match="MAINLINE_AGENT_ALLOW_LIVE"):
        select_transport(AgentkitSettings(provider="bedrock"))


def test_an_unknown_provider_is_refused():
    with pytest.raises(TransportUnavailable, match="unknown provider"):
        select_transport(AgentkitSettings(provider="ollama"))


def test_the_cassette_provider_refuses_to_guess_a_store():
    with pytest.raises(TransportUnavailable, match="never falls through"):
        select_transport(AgentkitSettings(provider="cassette", cassette_dir=None))


def test_replaying_a_missing_store_says_so(tmp_path: Path):
    with pytest.raises(TransportUnavailable, match="does not exist"):
        select_transport(
            AgentkitSettings(provider="cassette", cassette_dir=tmp_path / "nope"),
        )


def test_the_offline_path_imports_no_aws_sdk():
    # PL-1: every proof runs on a machine with no credential of ours. `boto3` is
    # imported inside two functions, both of which are on the live path only, so a
    # completed offline run must never have pulled the SDK into memory.
    assert "boto3" not in sys.modules, (
        "boto3 was imported during an offline test run: the lazy import that keeps the "
        "AWS SDK off the cassette path has been moved to module scope"
    )
    assert "botocore" not in sys.modules


def test_settings_default_to_the_offline_provider():
    settings = AgentkitSettings.from_env({})
    assert settings.provider == "cassette"
    assert settings.allow_live is False
    assert settings.ar1_enabled is False
    assert settings.region == "ap-southeast-2"


def test_settings_read_the_documented_environment_variables(cassette_dir):
    settings = AgentkitSettings.from_env(
        {
            "MAINLINE_AGENT_PROVIDER": "BEDROCK",
            "MAINLINE_AGENT_ALLOW_LIVE": "1",
            "MAINLINE_AR1_FALLBACK": "1",
            "MAINLINE_BEDROCK_REGION": "ap-southeast-2",
            "MAINLINE_CASSETTE_DIR": str(cassette_dir),
            "MAINLINE_WARM_TIMEOUT_S": "5",
        }
    )
    assert settings.provider == "bedrock"
    assert settings.allow_live is True
    assert settings.ar1_enabled is True
    assert settings.warm_timeout_s == 5.0
    assert settings.cassette_dir == cassette_dir
