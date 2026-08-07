# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""Unit tests for the plan reader.

The plan reader is where E1, E2 and E4 all go wrong at once if it is wrong, so it
is tested against the shapes a real ``tofu show -json`` emits rather than against
tidy invented ones: unknown-after-apply attributes, references that carry a
trailing attribute name, child modules, and ``count``-indexed addresses.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from mainline_boundary.errors import PlanParseError
from mainline_boundary.planfacts import PlanFacts

FIXTURE = (
    Path(__file__).resolve().parents[3] / "tests" / "boundary" / "fixtures" / "plan.json"
)


def _minimal(resources: list[dict[str, Any]], **extra: Any) -> dict[str, Any]:
    return {
        "format_version": "1.2",
        "terraform_version": "1.10.5",
        "planned_values": {"root_module": {"resources": resources}},
        **extra,
    }


def test_rejects_a_document_that_is_not_a_plan() -> None:
    with pytest.raises(PlanParseError, match="planned_values"):
        PlanFacts.from_dict({"format_version": "1.2"})


def test_walks_child_modules() -> None:
    document = {
        "format_version": "1.2",
        "planned_values": {
            "root_module": {
                "resources": [
                    {"address": "aws_vpc.main", "type": "aws_vpc", "name": "main", "values": {}}
                ],
                "child_modules": [
                    {
                        "address": "module.net",
                        "resources": [
                            {
                                "address": "module.net.aws_subnet.a",
                                "type": "aws_subnet",
                                "name": "a",
                                "values": {"tags": {"Plane": "kernel"}},
                            }
                        ],
                    }
                ],
            }
        },
    }
    facts = PlanFacts.from_dict(document)
    assert len(facts) == 2
    subnet = facts.get("module.net.aws_subnet.a")
    assert subnet is not None
    assert subnet.plane == "kernel"
    assert subnet.module_address == "module.net"


def test_unknown_after_apply_is_visible() -> None:
    document = _minimal(
        [{"address": "aws_iam_role.k", "type": "aws_iam_role", "name": "k", "values": {}}],
        resource_changes=[
            {
                "address": "aws_iam_role.k",
                "change": {"actions": ["create"], "after_unknown": {"permissions_boundary": True}},
            }
        ],
    )
    role = PlanFacts.from_dict(document).get("aws_iam_role.k")
    assert role is not None
    assert role.is_unknown("permissions_boundary")
    assert not role.is_unknown("name")


def test_references_drop_the_trailing_attribute() -> None:
    document = _minimal(
        [{"address": "aws_iam_role.k", "type": "aws_iam_role", "name": "k", "values": {}}],
        configuration={
            "root_module": {
                "resources": [
                    {
                        "address": "aws_iam_role.k",
                        "expressions": {
                            "permissions_boundary": {
                                "references": [
                                    "aws_iam_policy.b.arn",
                                    "aws_iam_policy.b",
                                    "var.unused",
                                ]
                            }
                        },
                    }
                ]
            }
        },
    )
    facts = PlanFacts.from_dict(document)
    assert facts.references("aws_iam_role.k", "permissions_boundary") == (
        "aws_iam_policy.b.arn",
        "aws_iam_policy.b",
        "var.unused",
    )
    resolved, unresolvable = facts.referenced_resources("aws_iam_role.k", "permissions_boundary")
    assert resolved == ()
    # The policy is not in planned_values, so both aws_ references are reported
    # unresolvable — and `var.unused` too. Nothing is silently dropped.
    assert "var.unused" in unresolvable


def test_unresolvable_reasons_are_never_empty_when_resolution_fails() -> None:
    """The invariant every caller relies on to avoid passing by absence."""
    document = _minimal(
        [{"address": "aws_iam_role.k", "type": "aws_iam_role", "name": "k", "values": {}}]
    )
    facts = PlanFacts.from_dict(document)
    role = facts.get("aws_iam_role.k")
    assert role is not None
    resolved, problems = facts.resolve_attribute_resources(
        role, "permissions_boundary", target_types=("aws_iam_policy",)
    )
    assert resolved == ()
    assert problems, "resolution failed with no stated reason"


def test_count_indexed_addresses_are_matched() -> None:
    document = _minimal(
        [
            {
                "address": "aws_subnet.k[0]",
                "type": "aws_subnet",
                "name": "k",
                "index": 0,
                "values": {"tags": {"Plane": "kernel"}},
            },
            {
                "address": "aws_subnet.k[1]",
                "type": "aws_subnet",
                "name": "k",
                "index": 1,
                "values": {"tags": {"Plane": "kernel"}},
            },
        ]
    )
    facts = PlanFacts.from_dict(document)
    assert len(facts.all_matching("aws_subnet.k")) == 2


def test_tags_all_is_used_when_tags_is_absent() -> None:
    document = _minimal(
        [
            {
                "address": "aws_subnet.k",
                "type": "aws_subnet",
                "name": "k",
                "values": {"tags_all": {"Plane": "Kernel"}},
            }
        ]
    )
    subnet = PlanFacts.from_dict(document).get("aws_subnet.k")
    assert subnet is not None
    assert subnet.plane == "kernel"


def test_committed_fixture_parses_and_has_the_shape_the_suite_assumes() -> None:
    facts = PlanFacts.from_file(FIXTURE)
    assert facts.format_version == "1.2"
    assert len(facts.by_type("aws_subnet")) >= 8
    assert len(facts.by_type("aws_security_group")) >= 4
    assert facts.by_type("aws_vpc_endpoint")
    role = facts.get("aws_iam_role.kernel_task")
    assert role is not None and role.plane == "kernel"


def test_fixture_json_is_stable_and_readable() -> None:
    """A fixture nobody can read is a fixture nobody checks."""
    text = FIXTURE.read_text(encoding="utf-8")
    assert json.loads(text)
    assert text.endswith("\n")
    assert "  " in text, "the fixture must stay indented for human review"
