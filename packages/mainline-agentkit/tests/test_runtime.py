# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""The process-start bootstrap: resolve, assert `au.*`, pin, and only then serve.

ARCHITECTURE.md §10.1 states the residency control in three layers, and the **first**
one is *"an `au.*`-prefix assertion at process start-up"*. Before this module existed the
assertion lived only inside :class:`BedrockTransport`, which means it ran per call, on
the live path only, and a caller who passed `model_id=` by hand chose whether it ran at
all. A control a caller can decline is not a control.

What these tests pin down:

* boot resolves the profile ARN from ``bedrock:ListInferenceProfiles`` and never from a
  literal in our source;
* a non-Australian profile, a generation mismatch, or a replay claiming an ARN the
  cassettes were never recorded against, all **refuse to serve**;
* a boot that refused **latches** — a second boot in the same process is refused rather
  than retried, because a retry loop around a residency refusal is how a residency
  refusal becomes a warning;
* every served call carries the pinned ARN and the run id into its provenance, and no
  call may go through a profile the run record did not pin.
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Any

import make_cassettes as recipes
import pytest
from mainline_agentkit import (
    EXTRACTION,
    PROFILES,
    TRIAGE,
    AgentkitSettings,
    ConfigurationRefused,
    FanoutInput,
    ModelRefused,
    ResidencyRefused,
)
from mainline_agentkit import runtime as runtime_module
from mainline_agentkit.errors import (
    ProfileNotPinned,
    RuntimeAlreadyBooted,
    RuntimeNotBooted,
    RuntimeRefusing,
)
from mainline_agentkit.runtime import (
    IDENTITY_COMPONENT_ORDER,
    AgentkitRuntime,
    boot_runtime,
    current_runtime,
    is_serving,
    shutdown_runtime,
)

AU_ARN = recipes.MODEL_ID
GLOBAL_ARN = (
    "arn:aws:bedrock:ap-southeast-2:000000000000:inference-profile/global.anthropic.claude-opus-5"
)
FOREIGN_ACCOUNT_ARN = (
    "arn:aws:bedrock:ap-southeast-2:999999999999:inference-profile/au.anthropic.claude-opus-5"
)
SONNET_ARN = (
    "arn:aws:bedrock:ap-southeast-2:000000000000:inference-profile/au.anthropic.claude-sonnet-5"
)


class FakeControlPlane:
    """A ``bedrock`` control-plane client that pages, like the real one does."""

    def __init__(self, *pages: list[dict[str, str]]) -> None:
        self.pages = list(pages)
        self.calls: list[dict[str, Any]] = []

    def list_inference_profiles(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(dict(kwargs))
        index = 0 if "nextToken" not in kwargs else int(kwargs["nextToken"])
        page = self.pages[index]
        body: dict[str, Any] = {"inferenceProfileSummaries": page}
        if index + 1 < len(self.pages):
            body["nextToken"] = str(index + 1)
        return body


def au_control_plane() -> FakeControlPlane:
    """Two pages, with the Australian profile on the second one."""
    return FakeControlPlane(
        [
            {
                "inferenceProfileId": "global.anthropic.claude-opus-5",
                "inferenceProfileArn": GLOBAL_ARN,
            }
        ],
        [
            {
                "inferenceProfileId": "au.anthropic.claude-opus-5",
                "inferenceProfileArn": AU_ARN,
            }
        ],
    )


@pytest.fixture(autouse=True)
def _no_process_runtime():
    """No test may inherit a booted process runtime, or leave one behind."""
    shutdown_runtime(force=True)
    yield
    shutdown_runtime(force=True)


@pytest.fixture
def booted(settings, transport) -> AgentkitRuntime:
    """A runtime bound to the committed cassette store and the recorded ARN."""
    return AgentkitRuntime.boot(
        settings=settings, transport=transport, inference_profile_arn=AU_ARN
    )


# ── the start-up assertion ──────────────────────────────────────────────────────


def test_boot_resolves_the_arn_from_the_control_plane(transport):
    settings = AgentkitSettings(provider="bedrock", region="ap-southeast-2", allow_live=True)
    control = au_control_plane()
    booted = AgentkitRuntime.boot(settings=settings, transport=transport, control_plane=control)
    assert booted.model_id == AU_ARN
    assert booted.run_record.inference_profile_id == "au.anthropic.claude-opus-5"
    assert booted.run_record.resolution == "bedrock:ListInferenceProfiles"
    # Both pages were read: the global profile is on page 1 and was skipped.
    assert len(control.calls) == 2


def test_boot_refuses_when_no_australian_profile_exists(transport):
    settings = AgentkitSettings(provider="bedrock", region="ap-southeast-2", allow_live=True)
    control = FakeControlPlane(
        [
            {
                "inferenceProfileId": "global.anthropic.claude-opus-5",
                "inferenceProfileArn": GLOBAL_ARN,
            }
        ]
    )
    with pytest.raises(ResidencyRefused) as excinfo:
        AgentkitRuntime.boot(settings=settings, transport=transport, control_plane=control)
    assert "AR-2" in str(excinfo.value)


def test_a_deploy_time_pin_that_disagrees_with_the_control_plane_refuses(transport):
    settings = AgentkitSettings(provider="bedrock", region="ap-southeast-2", allow_live=True)
    with pytest.raises(ConfigurationRefused) as excinfo:
        AgentkitRuntime.boot(
            settings=settings,
            transport=transport,
            control_plane=au_control_plane(),
            inference_profile_arn=FOREIGN_ACCOUNT_ARN,
        )
    assert "declared" in str(excinfo.value)


def test_boot_refuses_a_global_profile_at_process_start(settings, transport):
    with pytest.raises(ResidencyRefused) as excinfo:
        AgentkitRuntime.boot(
            settings=settings, transport=transport, inference_profile_arn=GLOBAL_ARN
        )
    assert excinfo.value.identifier == GLOBAL_ARN


def test_boot_refuses_a_bare_foundation_model_id(settings, transport):
    with pytest.raises(ResidencyRefused):
        AgentkitRuntime.boot(
            settings=settings,
            transport=transport,
            inference_profile_arn="anthropic.claude-opus-5-v1:0",
        )


def test_an_offline_run_must_still_name_the_profile_it_replays(settings, transport, monkeypatch):
    monkeypatch.delenv("MAINLINE_INFERENCE_PROFILE_ARN", raising=False)
    with pytest.raises(ConfigurationRefused) as excinfo:
        AgentkitRuntime.boot(settings=settings, transport=transport)
    assert "MAINLINE_INFERENCE_PROFILE_ARN" in str(excinfo.value)


def test_the_declared_arn_must_name_the_generation_the_register_uses(settings, transport):
    with pytest.raises(ConfigurationRefused) as excinfo:
        AgentkitRuntime.boot(
            settings=settings, transport=transport, inference_profile_arn=SONNET_ARN
        )
    assert "claude-opus-5" in str(excinfo.value)


def test_a_replay_may_not_claim_an_arn_the_cassettes_never_recorded(settings, transport):
    with pytest.raises(ConfigurationRefused) as excinfo:
        AgentkitRuntime.boot(
            settings=settings, transport=transport, inference_profile_arn=FOREIGN_ACCOUNT_ARN
        )
    message = str(excinfo.value)
    assert "cassette" in message
    assert AU_ARN in message


def test_a_fleet_spanning_two_generations_cannot_be_pinned(settings, transport):
    register = {
        "triage": TRIAGE,
        "other": replace(
            TRIAGE,
            profile_id="other",
            model_key="claude-haiku-4-5",
            allow_uncacheable_prefix=True,
        ),
    }
    with pytest.raises(ConfigurationRefused) as excinfo:
        AgentkitRuntime.boot(
            settings=settings,
            transport=transport,
            inference_profile_arn=AU_ARN,
            profiles=register,
        )
    assert "A4" in str(excinfo.value)


def test_no_inference_profile_arn_is_hard_coded_in_the_runtime_module():
    source = Path(runtime_module.__file__).read_text(encoding="utf-8")
    assert "arn:aws:bedrock" not in source, "the profile ARN must be resolved, never written down"
    assert "au.anthropic" not in source, "the model generation comes from the profile register"


# ── the run record ──────────────────────────────────────────────────────────────


def test_the_run_record_pins_every_registered_profile(booted):
    record = booted.run_record
    assert [pin.profile_id for pin in record.profiles] == sorted(PROFILES)
    for pin in record.profiles:
        profile = PROFILES[pin.profile_id]
        assert pin.prompt_version == profile.prompt_version
        assert pin.prompt_sha256 == profile.prompt_sha256()
        assert pin.schema_version == profile.schema_version
        assert pin.max_tokens == profile.max_tokens
        assert pin.may_write_gate_field is False


def test_the_configuration_digest_is_stable_and_excludes_the_run_id(settings, transport):
    first = AgentkitRuntime.boot(
        settings=settings, transport=transport, inference_profile_arn=AU_ARN
    )
    second = AgentkitRuntime.boot(
        settings=settings, transport=transport, inference_profile_arn=AU_ARN
    )
    assert first.run_record.run_id != second.run_record.run_id
    assert first.run_record.configuration_sha256() == second.run_record.configuration_sha256()
    # A prompt edit moves it. Decision A13: a prompt edit is a commit.
    edited_pin = replace(first.run_record.profiles[0], prompt_version="v99")
    edited = replace(first.run_record, profiles=(edited_pin,))
    assert edited.configuration_sha256() != first.run_record.configuration_sha256()


def test_the_run_record_states_what_transport_actually_served(booted):
    mapping = booted.run_record.to_mapping()
    assert mapping["provider"] == "cassette"
    assert mapping["transport"] == "CassetteTransport"
    assert mapping["resolution"].startswith("declared")
    assert "residency_note" in mapping


def test_identity_components_are_the_seven_the_architecture_names(booted):
    components = booted.run_record.identity_components(
        agent_name="archivist",
        sql_role="svc_archivist",
        iam_role_arn="arn:aws:iam::000000000000:role/mainline-archivist",
        profile_id="extraction",
    )
    assert tuple(components) == IDENTITY_COMPONENT_ORDER
    assert IDENTITY_COMPONENT_ORDER == (
        "agent_name",
        "sql_role",
        "iam_role_arn",
        "prompt_version",
        "model_id",
        "inference_profile_arn",
        "schema_version",
    )
    assert components["inference_profile_arn"] == AU_ARN
    assert components["prompt_version"] == EXTRACTION.prompt_version
    # `model_id` is the generation and `inference_profile_arn` the routing ARN. Read any
    # other way, the seven components would hash one fact twice.
    assert components["model_id"] == EXTRACTION.model_key
    assert components["model_id"] != components["inference_profile_arn"]
    # The hash itself belongs to `mainline-provenance`: one implementation of the
    # formula, not two.
    assert "agent_identity" not in components


def test_identity_components_refuse_an_unpinned_profile(booted):
    with pytest.raises(ProfileNotPinned):
        booted.run_record.identity_components(
            agent_name="archivist",
            sql_role="svc_archivist",
            iam_role_arn="arn:aws:iam::000000000000:role/mainline-archivist",
            profile_id="rerank",
        )


# ── serving ─────────────────────────────────────────────────────────────────────


def test_a_served_call_carries_the_pinned_arn_and_the_run_id(booted, ctx_site):
    validated = booted.call(TRIAGE, recipes.DOC_PROCEDURE, ctx_site)
    assert validated.value.route == "procedure"
    assert validated.model_id == AU_ARN
    provenance = booted.provenance(validated)
    assert provenance["run_id"] == booted.run_record.run_id
    assert provenance["inference_profile_arn"] == AU_ARN
    assert provenance["configuration_sha256"] == booted.run_record.configuration_sha256()
    assert provenance["profile_id"] == "triage"
    assert provenance["output_sha256"] == validated.output_sha256


def test_a_profile_the_record_never_pinned_cannot_be_served(booted, ctx_site):
    rogue = replace(TRIAGE, profile_id="rogue")
    with pytest.raises(ProfileNotPinned):
        booted.call(rogue, recipes.DOC_PROCEDURE, ctx_site)


def test_a_prompt_edited_at_the_call_site_cannot_be_served(booted, ctx_site):
    """Same id, different bytes. The record pinned v1; this is not v1."""
    edited = replace(TRIAGE, prompt_version="v99")
    with pytest.raises(ProfileNotPinned) as excinfo:
        booted.call(edited, recipes.DOC_PROCEDURE, ctx_site)
    assert "triage" in str(excinfo.value)


def test_fanout_through_the_runtime_reads_the_cache_on_call_two(booted, ctx_site):
    results = booted.fanout(
        EXTRACTION,
        [
            FanoutInput(untrusted=recipes.DOC_PROCEDURE, trusted_context=ctx_site),
            FanoutInput(untrusted=recipes.DOC_INCIDENT, trusted_context=ctx_site),
        ],
    )
    assert results[0].cache.warmed is True
    assert results[0].cache.read_tokens == 0
    assert results[1].cache.read_tokens > 0


def test_the_serving_surface_holds_no_tool_parameter():
    import inspect

    for method in (AgentkitRuntime.call, AgentkitRuntime.fanout):
        names = set(inspect.signature(method).parameters)
        assert not names & {"tools", "tool_choice", "toolConfig", "toolChoice"}


def test_a_refusal_becomes_a_silence_row_carrying_the_pinned_arn(booted):
    refusal = ModelRefused(category="model_refusal", stop_reason="refusal")
    row = booted.silence_row(
        refusal,
        profile_id="extraction",
        site_id="KAL-01",
        source="fleet_appraisal",
        subject_kind="event",
        subject_id="evt-2019-0417",
        severity=3,
        input_sha256="0" * 64,
    )
    assert row.reason == "model_refusal"
    assert row.arithmetic["inference_profile_arn"] == AU_ARN
    assert row.arithmetic["prompt_version"] == EXTRACTION.prompt_version
    assert row.arithmetic["fallback"] == "deterministic_channel"


# ── the process-wide latch ──────────────────────────────────────────────────────


def test_current_runtime_before_boot_is_a_refusal_not_a_none():
    assert is_serving() is False
    with pytest.raises(RuntimeNotBooted):
        current_runtime()


def test_booting_twice_is_refused(settings, transport):
    boot_runtime(settings=settings, transport=transport, inference_profile_arn=AU_ARN)
    assert is_serving() is True
    with pytest.raises(RuntimeAlreadyBooted):
        boot_runtime(settings=settings, transport=transport, inference_profile_arn=AU_ARN)


def test_a_failed_boot_latches_and_the_process_refuses_to_serve(settings, transport):
    with pytest.raises(ResidencyRefused):
        boot_runtime(settings=settings, transport=transport, inference_profile_arn=GLOBAL_ARN)

    # Every later attempt names the original refusal rather than trying again.
    with pytest.raises(RuntimeRefusing) as first:
        current_runtime()
    assert GLOBAL_ARN in str(first.value)
    with pytest.raises(RuntimeRefusing):
        boot_runtime(settings=settings, transport=transport, inference_profile_arn=AU_ARN)
    assert is_serving() is False

    # Clearing it is explicit, and nothing else clears it.
    with pytest.raises(RuntimeRefusing):
        shutdown_runtime()
    shutdown_runtime(force=True)
    booted = boot_runtime(settings=settings, transport=transport, inference_profile_arn=AU_ARN)
    assert current_runtime() is booted


def test_the_environment_can_declare_the_arn(settings, transport, monkeypatch):
    monkeypatch.setenv("MAINLINE_INFERENCE_PROFILE_ARN", AU_ARN)
    booted = AgentkitRuntime.boot(settings=settings, transport=transport)
    assert booted.model_id == AU_ARN
