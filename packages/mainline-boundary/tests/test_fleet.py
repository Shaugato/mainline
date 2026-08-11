# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""Unit tests for the fleet register parser and the plane derivation.

The parser accepts two register shapes on purpose — a mapping of name → spec and
a list of specs carrying ``name``/``id`` — because pinning the shape would make
this check hostage to a formatting decision in a file another worker owns.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from mainline_boundary.errors import FleetParseError
from mainline_boundary.fleet import (
    COGNITION,
    CONTROL,
    CUSTODY,
    KERNEL,
    check_fleet,
    load_fleet,
    parse_fleet,
    resolve_plane,
)

REFERENCE = Path(__file__).resolve().parent / "fixtures" / "fleet_reference.yaml"


def test_reference_register_is_clean() -> None:
    report = check_fleet(load_fleet(REFERENCE), source=str(REFERENCE))
    assert report.ok, report.summary()
    assert report.examined == 10


def test_mapping_and_list_shapes_parse_identically() -> None:
    mapping = parse_fleet(
        yaml.safe_load(
            "agents:\n  recall:\n    tier: T1\n    sql_role: agent_recaller\n"
            "    tools: []\n    call_profiles: [p]\n"
        )
    )
    listed = parse_fleet(
        yaml.safe_load(
            "agents:\n  - name: recall\n    tier: T1\n    sql_role: agent_recaller\n"
            "    tools: []\n    call_profiles: [p]\n"
        )
    )
    assert mapping[0].name == listed[0].name == "recall"
    assert mapping[0].sql_roles == listed[0].sql_roles == ("agent_recaller",)


def test_a_bare_top_level_mapping_is_accepted() -> None:
    agents = parse_fleet(
        yaml.safe_load("recall:\n  tier: T1\n  sql_role: agent_recaller\n  no_model: true\n")
    )
    assert agents[0].name == "recall"


def test_an_entry_without_a_name_is_an_error() -> None:
    with pytest.raises(FleetParseError, match="no name/id"):
        parse_fleet(yaml.safe_load("agents:\n  - tier: T1\n"))


def test_an_empty_register_is_an_error() -> None:
    with pytest.raises(FleetParseError, match="declares no agents"):
        parse_fleet({"agents": {}})


@pytest.mark.parametrize(
    ("sql_role", "expected"),
    [
        ("agent_gate", KERNEL),
        ("svc_disposition", KERNEL),
        ("agent_recaller", COGNITION),
        ("agent_relay", CUSTODY),
        ("mainline_auditor", CONTROL),
    ],
)
def test_plane_is_derived_from_the_sql_role(sql_role: str, expected: str) -> None:
    agents = parse_fleet({"agents": {"x": {"tier": "T1", "sql_role": sql_role, "no_model": True}}})
    plane, how = resolve_plane(agents[0])
    assert plane == expected
    assert "§8.1" in how


def test_plane_falls_back_to_the_agent_name() -> None:
    agents = parse_fleet(
        {"agents": {"disposition_assistant": {"tier": "T2", "call_profiles": ["p"]}}}
    )
    plane, how = resolve_plane(agents[0])
    assert plane == COGNITION
    assert "§8.4" in how


def test_a_declared_plane_must_be_a_legal_plane() -> None:
    agents = parse_fleet({"agents": {"x": {"tier": "T1", "plane": "middleware", "no_model": True}}})
    plane, how = resolve_plane(agents[0])
    assert plane is None
    assert "middleware" in how


def test_sql_roles_spanning_two_planes_do_not_resolve() -> None:
    agents = parse_fleet(
        {
            "agents": {
                "x": {"tier": "T1", "sql_role": ["agent_gate", "agent_recaller"], "no_model": True}
            }
        }
    )
    plane, how = resolve_plane(agents[0])
    assert plane is None
    assert "multiple planes" in how


def test_no_model_and_call_profiles_are_distinguished() -> None:
    silent, declared, none = parse_fleet(
        {
            "agents": {
                "a": {"tier": "T1", "sql_role": "agent_recaller"},
                "b": {"tier": "T1", "sql_role": "agent_recaller", "call_profiles": ["p"]},
                "c": {"tier": "T1", "sql_role": "agent_recaller", "no_model": True},
            }
        }
    )
    assert not silent.declares_model_intent
    assert declared.has_model
    assert none.declares_model_intent and not none.has_model
