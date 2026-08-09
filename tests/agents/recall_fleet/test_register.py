# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
"""The recall agent's half of the fleet capability matrix.

Decision A14 asks for four independent proofs that no model can reach the merge gate, and
the fourth is *a fleet capability-matrix test driven by `spec/agents/fleet.yaml`*.  That
file is the fleet-register worker's to write; these assertions are over the rows the
recall agent contributes to it, so that when the two meet there is nothing left to
discover about this half.

The load-bearing assertion in this file is
:func:`test_register_prompt_versions_match_the_recall_package`.  The register declares
prompt versions as literals *on purpose* — a mirror that imports its source can never
disagree with it, and a register that cannot disagree cannot detect the drift decision
A13 exists to detect.  This test is where the two are compared, once, in CI.
"""

from __future__ import annotations

import pytest
from mainline_agentkit import IDENTITY_COMPONENT_ORDER, SILENCE_REASONS, SILENCE_SOURCES, Effort
from mainline_recall_agent.cue.prompts import PROMPT_VERSION as CUE_PROMPT_VERSION
from mainline_recall_agent.rerank.rubric import PROMPT_VERSION as RERANK_PROMPT_VERSION
from mainline_recall_agent.taxonomy.prompts import INDUCTION_PROMPT_VERSION
from mainline_recall_fleet import (
    GATE_WRITING_ROLES,
    LEG_CHECKS,
    RECALL_LEGS,
    RECALL_SQL_ROLE,
    UnregisteredLeg,
    audit_leg,
    audit_recall_fleet,
    describe_recall_fleet,
    failures,
    fleet_yaml_fragment,
    get_leg,
    single_model_generation,
)


def test_every_leg_holds_no_tool_and_writes_no_gate_field() -> None:
    """The two structural properties of the whole domain, per leg."""
    for leg in RECALL_LEGS.values():
        assert leg.tools == ()
        assert leg.may_write_gate_field is False


def test_no_leg_runs_as_a_gate_writing_role() -> None:
    """The covenant CockroachDB already carries on the schema, in Python.

    *The role that detects a precursor may never write one: agent_recaller holds no
    INSERT on any obligation relation of this binding.*
    """
    for leg in RECALL_LEGS.values():
        assert leg.sql_role == RECALL_SQL_ROLE
        assert leg.sql_role not in GATE_WRITING_ROLES


def test_no_leg_claims_a_write_to_blocking_check() -> None:
    """ARCHITECTURE §8.3: `mainline-recall` NEVER writes `blocking_check`."""
    for leg in RECALL_LEGS.values():
        assert all("blocking_check" not in relation for relation in leg.writes)


def test_the_whole_register_passes_its_own_audit() -> None:
    """Every leg, every clause, by name."""
    assert failures(audit_recall_fleet()) == []


def test_audit_leg_emits_every_declared_check() -> None:
    """A silently deleted capability check must fail the suite rather than pass it."""
    for leg in RECALL_LEGS.values():
        assert tuple(finding.check for finding in audit_leg(leg)) == LEG_CHECKS


def test_one_model_generation_across_the_recall_fleet() -> None:
    """A4. A run record pins one ARN, so two generations cannot both be true of it."""
    assert single_model_generation() == "claude-opus-5"


def test_effort_follows_the_a4_mapping() -> None:
    """low = extraction · high = adjudication · xhigh = the listwise rerank."""
    efforts = {leg_id: str(leg.effort) for leg_id, leg in RECALL_LEGS.items()}
    assert efforts == {
        "recall.cue.event": "low",
        "recall.cue.exposure": "low",
        "recall.rerank.listwise": "xhigh",
        "recall.taxonomy.propose": "low",
        "recall.taxonomy.refine": "high",
    }
    assert set(efforts.values()) <= {str(item) for item in Effort}


def test_register_prompt_versions_match_the_recall_package() -> None:
    """A13's drift detector, evaluated once per CI run.

    If a prompt module's version moves and this register does not, the transport starts
    refusing every call through that leg — loudly, before the wire.  This test is what
    turns that refusal into a build failure at the moment of the edit instead.
    """
    assert get_leg("recall.cue.event").prompt_version == CUE_PROMPT_VERSION
    assert get_leg("recall.cue.exposure").prompt_version == CUE_PROMPT_VERSION
    assert get_leg("recall.rerank.listwise").prompt_version == RERANK_PROMPT_VERSION
    assert get_leg("recall.taxonomy.propose").prompt_version == INDUCTION_PROMPT_VERSION
    assert get_leg("recall.taxonomy.refine").prompt_version == INDUCTION_PROMPT_VERSION


def test_every_leg_declares_silence_inside_the_check_vocabularies() -> None:
    """A row the database would reject is rejected before it is built."""
    for leg in RECALL_LEGS.values():
        assert leg.silence_source in SILENCE_SOURCES
        assert leg.silence_reasons <= SILENCE_REASONS
        assert "model_refusal" in leg.silence_reasons


def test_an_unregistered_leg_is_refused() -> None:
    """A capability nobody declared is refused rather than served."""
    with pytest.raises(UnregisteredLeg) as caught:
        get_leg("recall.rerank.experimental")
    assert "recall.rerank.listwise" in caught.value.context["registered"]


def test_identity_components_are_the_seven_in_concatenation_order() -> None:
    """A13's formula takes seven components; this register supplies them and hashes none."""
    components = get_leg("recall.cue.event").identity_components(
        iam_role_arn="arn:aws:iam::000000000000:role/mainline-recall",
        model_id="claude-opus-5",
        inference_profile_arn="arn:aws:bedrock:ap-southeast-2:000000000000:"
        "inference-profile/au.anthropic.claude-opus-5",
        schema_version="sha256:deadbeef",
    )
    assert tuple(components) == IDENTITY_COMPONENT_ORDER
    assert components["sql_role"] == RECALL_SQL_ROLE
    assert components["agent_name"] == "mainline-recall"


def test_the_matrix_groups_legs_under_their_agent() -> None:
    """`spec/agents/fleet.yaml` has one row per agent and call profiles inside it."""
    matrix = describe_recall_fleet()
    names = [agent["name"] for agent in matrix["agents"]]
    assert names == ["mainline-recall", "mainline-taxonomy"]
    for agent in matrix["agents"]:
        assert agent["plane"] == "cognition"
        assert agent["tools"] == []
        assert agent["may_write_gate_field"] is False
        assert agent["reads_untrusted_text"] is True
    profiles = {
        profile["leg_id"] for agent in matrix["agents"] for profile in agent["call_profiles"]
    }
    assert profiles == set(RECALL_LEGS)


def test_the_yaml_fragment_is_deterministic_and_complete() -> None:
    """Emitted rather than written: two files claiming to be the register is the failure."""
    first = fleet_yaml_fragment()
    assert first == fleet_yaml_fragment()
    assert first.startswith("# Generated by mainline_recall_fleet.legs.fleet_yaml_fragment()")
    assert "model_generation: claude-opus-5" in first
    for leg_id in RECALL_LEGS:
        assert leg_id in first
    assert "tools: []" in first
    assert "may_write_gate_field: false" in first
    # Booleans render as YAML booleans, not as Python's capitalised repr.
    assert "True" not in first
    assert "False" not in first
