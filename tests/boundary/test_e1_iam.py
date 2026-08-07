# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""E1 — no model IAM.

ARCHITECTURE.md §8.2: the ``mainline-kernel`` task role carries a permissions
boundary with an explicit ``Deny`` on ``bedrock:*``, ``bedrock-runtime:*`` and
``bedrock-agentcore:*``, asserted by ``aws iam simulate-principal-policy`` in CI
and by a Rego ``deny`` if the boundary is absent from the plan.

Credentials are not valid on the build machine as of 2026-08, so the plan-time
assertion is the one that runs and the live simulation skips **with its reason
printed**. PL-3: an unproven capability does not go on a dated path.

Every positive assertion here is paired with a mutation that must make it fail.
A refusal nobody has watched refuse is not evidence.
"""

from __future__ import annotations

import json
from typing import Any

import pytest
from mainline_boundary.iam import (
    DENIED_ACTIONS,
    check_iam,
    find_kernel_roles,
    live_simulation_available,
    parse_policy_document,
    simulate_kernel_denies,
)
from mainline_boundary.planfacts import PlanFacts
from mainline_boundary.testkit import (
    assert_enforced,
    assert_violates,
    configuration_of,
    resource_of,
)

KERNEL_ROLE = "aws_iam_role.kernel_task"
BOUNDARY_POLICY = "aws_iam_policy.kernel_boundary"


def test_kernel_role_is_in_the_plan(plan_facts: PlanFacts) -> None:
    roles = find_kernel_roles(plan_facts)
    assert roles, (
        "E1 has no subject: the plan contains no IAM role tagged Plane=kernel. "
        "Every later assertion in this module would pass by absence."
    )
    assert any(r.address == KERNEL_ROLE for r in roles)


def test_kernel_boundary_denies_the_model_plane(plan_facts: PlanFacts) -> None:
    assert_enforced(check_iam(plan_facts))


def test_boundary_arn_is_unknown_at_plan_time(plan_facts: PlanFacts) -> None:
    """The trap this whole module is written around.

    At plan time ``aws_iam_policy.arn`` does not exist, so the role's
    ``permissions_boundary`` is ``null``. A checker reading ``planned_values``
    alone sees nothing and calls it clean. This test asserts the fixture really
    does have that shape, so :func:`check_iam` is being exercised on the hard
    case rather than a convenient one.
    """
    role = plan_facts.get(KERNEL_ROLE)
    assert role is not None
    assert role.get("permissions_boundary") is None
    assert role.is_unknown("permissions_boundary"), (
        "the fixture no longer marks permissions_boundary known-after-apply, so this "
        "suite is no longer testing the case that actually occurs in a plan"
    )
    resolved, problems = plan_facts.resolve_attribute_resources(
        role, "permissions_boundary", target_types=("aws_iam_policy",)
    )
    assert [r.address for r in resolved] == [BOUNDARY_POLICY], problems


def test_each_denied_action_is_covered_unconditionally(plan_facts: PlanFacts) -> None:
    policy = plan_facts.get(BOUNDARY_POLICY)
    assert policy is not None
    statements = parse_policy_document(policy.get("policy"))
    for action in DENIED_ACTIONS:
        covering = [
            s
            for s in statements
            if s.denies(action) and not s.has_condition and s.is_global_resource
        ]
        assert covering, (
            f"no unconditional Deny with Resource '*' covers {action}; a conditional or "
            "resource-scoped Deny is a Deny somebody can argue with"
        )


# ---------------------------------------------------------------------------
# PL-2: the mutations that must make E1 fail
# ---------------------------------------------------------------------------


def _rewrite_boundary(document: dict[str, Any], transform: Any) -> None:
    entry = resource_of(document, BOUNDARY_POLICY)
    policy = json.loads(entry["values"]["policy"])
    transform(policy)
    entry["values"]["policy"] = json.dumps(policy, indent=2)


def test_removing_every_deny_fails_e1(mutate_plan: Any) -> None:
    def mutation(document: dict[str, Any]) -> None:
        def drop_all_denies(policy: dict[str, Any]) -> None:
            policy["Statement"] = [
                s for s in policy["Statement"] if s.get("Effect") != "Deny"
            ]

        _rewrite_boundary(document, drop_all_denies)

    assert_violates(check_iam(mutate_plan(mutation)), "E1-DENY-MISSING")


def test_making_the_deny_conditional_fails_e1(mutate_plan: Any) -> None:
    """A Deny with a Condition is a Deny somebody can argue their way past."""

    def mutation(document: dict[str, Any]) -> None:
        def add_condition(policy: dict[str, Any]) -> None:
            for statement in policy["Statement"]:
                if statement.get("Sid") == "DenyModelPlaneEntirely":
                    statement["Condition"] = {
                        "StringNotEquals": {"aws:PrincipalTag/break-glass": "true"}
                    }

        _rewrite_boundary(document, add_condition)

    assert_violates(check_iam(mutate_plan(mutation)), "E1-CONDITIONAL-DENY")


def test_scoping_the_deny_to_named_resources_fails_e1(mutate_plan: Any) -> None:
    """An unlisted inference-profile ARN would walk straight through a scoped Deny."""

    def mutation(document: dict[str, Any]) -> None:
        def narrow(policy: dict[str, Any]) -> None:
            for statement in policy["Statement"]:
                if statement.get("Sid") == "DenyModelPlaneEntirely":
                    statement["Resource"] = [
                        "arn:aws:bedrock:ap-southeast-2:*:inference-profile/au.anthropic.*"
                    ]

        _rewrite_boundary(document, narrow)

    assert_violates(check_iam(mutate_plan(mutation)), "E1-NARROW-DENY")


def test_detaching_the_boundary_fails_e1(mutate_plan: Any) -> None:
    def mutation(document: dict[str, Any]) -> None:
        configuration_of(document, KERNEL_ROLE)["expressions"].pop("permissions_boundary")

    assert_violates(check_iam(mutate_plan(mutation)), "E1-BOUNDARY-UNRESOLVED")


def test_removing_the_kernel_role_fails_e1(mutate_plan: Any) -> None:
    """Absence of the subject is a failure, never a pass."""

    def mutation(document: dict[str, Any]) -> None:
        module = document["planned_values"]["root_module"]
        module["resources"] = [
            r for r in module["resources"] if r["address"] != KERNEL_ROLE
        ]

    assert_violates(check_iam(mutate_plan(mutation)), "E1-KERNEL-ROLE-ABSENT")


def test_granting_the_kernel_bedrock_inline_fails_e1(mutate_plan: Any) -> None:
    """The boundary makes it inert today and a defect tomorrow."""

    def mutation(document: dict[str, Any]) -> None:
        entry = resource_of(document, "aws_iam_role_policy.kernel_runtime")
        policy = json.loads(entry["values"]["policy"])
        policy["Statement"].append(
            {
                "Sid": "OopsModelPlane",
                "Effect": "Allow",
                "Action": ["bedrock:InvokeModel"],
                "Resource": "*",
            }
        )
        entry["values"]["policy"] = json.dumps(policy, indent=2)

    assert_violates(check_iam(mutate_plan(mutation)), "E1-KERNEL-ALLOWS-BEDROCK")


def test_e1_targets_the_kernel_not_every_role(plan_facts: PlanFacts) -> None:
    """The cognition role legitimately holds ``bedrock:InvokeModel``.

    If E1 flagged that, it would be asserting "nobody may use Bedrock", which is
    not the claim and would be false. The claim is about one plane.
    """
    recall = plan_facts.get("aws_iam_role_policy.recall_model")
    assert recall is not None
    statements = parse_policy_document(recall.get("policy"))
    assert any(s.allows("bedrock:InvokeModel") for s in statements)
    assert_enforced(check_iam(plan_facts))


# ---------------------------------------------------------------------------
# The live leg — off, with its reason stated
# ---------------------------------------------------------------------------


def test_live_simulation_is_reported_not_assumed() -> None:
    availability = live_simulation_available()
    assert availability.reason, "the live leg must always state why it did or did not run"
    if not availability.available:
        pytest.skip(f"live IAM simulation unavailable: {availability.reason}")


def test_live_simulation_returns_explicit_deny() -> None:
    availability = live_simulation_available()
    if not availability.available:
        pytest.skip(
            "live IAM simulation not attempted: "
            f"{availability.reason}. The plan-time assertions in this module still "
            "hold; this one does not, and is not counted as a pass."
        )
    report = simulate_kernel_denies(  # pragma: no cover - requires live credentials
        "arn:aws:iam::000000000000:role/mainline-kernel"
    )
    assert_enforced(report)
