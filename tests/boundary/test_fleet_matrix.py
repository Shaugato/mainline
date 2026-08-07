# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""The fleet capability matrix.

E1–E4 prove no model reaches the gate through IAM, the network, the image or the
protocol set. This module proves the fifth thing, about the register rather than
the infrastructure: that the fleet we *declare* is one in which the components
reading hostile text hold nothing to act with.

Three assertions, one per agent (ARCHITECTURE.md §8.2/§8.4, decision A1):

1. ``tools`` is empty for every T1/T2 **Cognition** agent;
2. ``may_write_gate_field`` is true only for the kernel;
3. no agent declares both ``svc_disposition`` and a model profile.

The plane an agent belongs to is **derived from its SQL role via §8.1's plane
table**, not taken from the register's own say-so, which is P2 applied to a YAML
file: the field a gate reads is projected from an authoritative source, never
supplied by the writer. An agent whose plane cannot be resolved is a violation.

``spec/agents/fleet.yaml`` belongs to the agent-contracts-red worker. While it is
absent this module runs against the reference register committed with the
boundary package, and :func:`test_shipped_fleet_register_exists` **skips with its
reason** rather than passing. The day the real file lands, everything here
retargets it with no edit.
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest
from mainline_boundary.fleet import (
    COGNITION,
    KERNEL,
    PLANE_BY_SQL_ROLE,
    AgentSpec,
    check_agent,
    check_fleet,
    load_fleet,
    resolve_plane,
)
from mainline_boundary.testkit import assert_enforced, assert_violates

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SHIPPED_REGISTER = _REPO_ROOT / "spec" / "agents" / "fleet.yaml"
REFERENCE_REGISTER = (
    _REPO_ROOT
    / "packages"
    / "mainline-boundary"
    / "tests"
    / "fixtures"
    / "fleet_reference.yaml"
)


def _active_register() -> tuple[Path, bool]:
    """``(path, is_shipped)``. Prefer the real register the moment it exists."""
    if SHIPPED_REGISTER.is_file():
        return SHIPPED_REGISTER, True
    return REFERENCE_REGISTER, False


REGISTER_PATH, REGISTER_IS_SHIPPED = _active_register()
AGENTS: tuple[AgentSpec, ...] = load_fleet(REGISTER_PATH)


def _ids() -> list[str]:
    return [a.name for a in AGENTS]


def test_shipped_fleet_register_exists() -> None:
    """Never a pass by absence: while spec/agents/fleet.yaml is missing, this skips."""
    if not REGISTER_IS_SHIPPED:
        pytest.skip(
            f"{SHIPPED_REGISTER.relative_to(_REPO_ROOT).as_posix()} does not exist yet "
            "(owned by the agent-contracts-red worker), so the matrix below is asserted "
            f"against the reference register at "
            f"{REFERENCE_REGISTER.relative_to(_REPO_ROOT).as_posix()}. NOT A PASS for the "
            "shipped fleet."
        )
    assert AGENTS, "the shipped register parsed to zero agents"


def test_the_register_parses_and_is_not_empty() -> None:
    assert AGENTS, f"{REGISTER_PATH} declares no agents; the matrix would assert nothing"


@pytest.mark.parametrize("agent", AGENTS, ids=_ids())
def test_agent_satisfies_the_capability_matrix(agent: AgentSpec) -> None:
    violations = check_agent(agent)
    assert not violations, (
        f"{agent.name} violates {list(violations)}\n" + check_fleet([agent]).summary()
    )


@pytest.mark.parametrize("agent", AGENTS, ids=_ids())
def test_agent_plane_resolves_from_an_authoritative_source(agent: AgentSpec) -> None:
    plane, how = resolve_plane(agent)
    assert plane is not None, f"{agent.name}: {how}"
    if agent.declared_plane is None and agent.sql_roles:
        assert "§8.1" in how or "§8.4" in how, how


def test_whole_register_is_clean() -> None:
    assert_enforced(check_fleet(AGENTS, source=str(REGISTER_PATH)))


def test_no_cognition_t1_or_t2_agent_holds_a_tool() -> None:
    offenders = []
    examined = 0
    for agent in AGENTS:
        plane, _ = resolve_plane(agent)
        if plane == COGNITION and agent.tier in {"T1", "T2"}:
            examined += 1
            if agent.tools:
                offenders.append((agent.name, list(agent.tools)))
    assert examined, (
        "the register contains no T1/T2 Cognition agent, so decision A1's central "
        "property is not being asserted about anything"
    )
    assert not offenders, offenders


def test_only_the_kernel_may_write_a_gate_field() -> None:
    writers = [a for a in AGENTS if a.may_write_gate_field]
    if not writers:
        pytest.skip(
            "the register declares no agent with may_write_gate_field: true, so this "
            "cell of §8.2's tier table is unproven by this register. NOT A PASS."
        )
    for agent in writers:
        plane, how = resolve_plane(agent)
        assert plane == KERNEL, f"{agent.name} may write a gate field but is {plane} ({how})"
        assert agent.tier == "T0", agent.name
        assert not agent.has_model, (
            f"{agent.name} may write a gate field AND declares model profiles "
            f"{list(agent.call_profiles)}"
        )


def test_no_agent_holds_svc_disposition_and_a_model() -> None:
    for agent in AGENTS:
        if "svc_disposition" in agent.sql_roles:
            assert not agent.has_model, (
                f"{agent.name} holds svc_disposition and declares "
                f"{list(agent.call_profiles)}. §8.2's first hard prohibition: no T1 or "
                "T2 agent may draft a disposition rationale"
            )


def test_plane_table_matches_the_architecture() -> None:
    """§8.1's plane table, spot-checked, because everything above derives from it."""
    assert PLANE_BY_SQL_ROLE["agent_gate"] == KERNEL
    assert PLANE_BY_SQL_ROLE["svc_disposition"] == KERNEL
    assert PLANE_BY_SQL_ROLE["agent_recaller"] == COGNITION
    assert PLANE_BY_SQL_ROLE["agent_relay"] == "custody"
    assert PLANE_BY_SQL_ROLE["mainline_auditor"] == "control"


# ---------------------------------------------------------------------------
# PL-2: the matrix has to be seen refusing
# ---------------------------------------------------------------------------


def _first_cognition_agent() -> AgentSpec:
    for agent in AGENTS:
        plane, _ = resolve_plane(agent)
        if plane == COGNITION and agent.tier in {"T1", "T2"}:
            return agent
    pytest.fail("the register has no T1/T2 Cognition agent to mutate")


def test_giving_a_t1_cognition_agent_a_tool_fails_the_matrix() -> None:
    """The mutation named in this worker's completion test."""
    mutated = replace(_first_cognition_agent(), tools=("bedrock:InvokeModel", "sql:insert"))
    assert_violates(check_fleet([mutated]), "FLEET-COGNITION-HOLDS-TOOLS")


def test_giving_a_t1_cognition_agent_a_gate_write_fails_the_matrix() -> None:
    mutated = replace(_first_cognition_agent(), may_write_gate_field=True)
    report = check_fleet([mutated])
    assert_violates(report, "FLEET-GATE-WRITE-OUTSIDE-KERNEL", "FLEET-GATE-WRITE-NON-T0")


def test_giving_the_kernel_a_model_profile_fails_the_matrix() -> None:
    kernel_agents = [a for a in AGENTS if a.may_write_gate_field]
    if not kernel_agents:
        pytest.skip("the register declares no gate-writing agent to mutate")
    mutated = replace(
        kernel_agents[0], no_model=False, call_profiles=("gate-adjudication-high",)
    )
    assert_violates(check_fleet([mutated]), "FLEET-GATE-WRITE-WITH-MODEL")


def test_giving_svc_disposition_a_model_profile_fails_the_matrix() -> None:
    mutated = replace(
        _first_cognition_agent(),
        sql_roles=("agent_recaller", "svc_disposition"),
        no_model=False,
        call_profiles=("disposition-drafting-high",),
    )
    report = check_fleet([mutated])
    assert_violates(report, "FLEET-DISPOSITION-WITH-MODEL")


def test_an_unclassifiable_agent_fails_the_matrix() -> None:
    """An agent whose plane cannot be derived is never quietly exempted."""
    mutated = AgentSpec(
        name="mystery_worker",
        tier="T1",
        sql_roles=("agent_unknown",),
        iam_role="mystery_fn",
        tools=("bedrock:InvokeModel",),
        may_write_gate_field=False,
        call_profiles=("some-profile",),
        no_model=False,
        declared_plane=None,
        raw={},
    )
    assert_violates(check_fleet([mutated]), "FLEET-PLANE-UNRESOLVED")


def test_an_agent_silent_about_models_fails_the_matrix() -> None:
    mutated = replace(_first_cognition_agent(), call_profiles=(), no_model=False)
    assert_violates(check_fleet([mutated]), "FLEET-MODEL-INTENT-UNDECLARED")
