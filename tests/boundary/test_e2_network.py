# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""E2 — no model network path.

ARCHITECTURE.md §8.2: "Kernel subnets contain **no ``bedrock-runtime`` interface
endpoint**; the kernel SG permits TCP/443 **only** to the interface-endpoint SG.
Bedrock is HTTPS — with no endpoint and no 443-to-internet rule there is no
*route*, not merely no permission." §10.3's endpoint matrix marks the cell ✘ and
says in words: *that absence is the boundary*.

E2 is asserted twice over the same plan — once in Python here, once in Rego by
conftest/OPA — because §8.2 says E2 convinces a reviewer precisely by not
depending on our code being correct, and a checker we wrote is our code. When
neither policy engine is installed the Rego leg **skips with its reason**; CI
installs conftest, so that skip cannot happen there.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from mainline_boundary.network import (
    check_network,
    collect_egress_rules,
    kernel_reachable_security_groups,
    model_endpoints,
    security_groups_of_plane,
)
from mainline_boundary.opa import describe_missing_runner, find_policy_runner, run_rego
from mainline_boundary.planfacts import PlanFacts
from mainline_boundary.testkit import (
    assert_enforced,
    assert_violates,
    configuration_of,
    resource_of,
)

BEDROCK_ENDPOINT = "aws_vpc_endpoint.bedrock_runtime_cog"
KERNEL_443 = "aws_vpc_security_group_egress_rule.kernel_endpoints_https"


def test_the_fixture_actually_contains_a_bedrock_endpoint(plan_facts: PlanFacts) -> None:
    """Otherwise E2 would be proving nothing at all.

    A plan with no Bedrock endpoint anywhere satisfies "no Bedrock endpoint in
    the kernel subnets" trivially. The fixture models the real topology: the
    endpoint exists, in the Cognition endpoint group, and the assertion is that
    the kernel cannot get to it.
    """
    endpoints = model_endpoints(plan_facts)
    assert [e.address for e in endpoints] == [BEDROCK_ENDPOINT], (
        "the plan fixture no longer contains a bedrock-runtime endpoint, so E2 would "
        "pass by absence rather than by routing"
    )


def test_no_bedrock_endpoint_is_reachable_from_the_kernel(plan_facts: PlanFacts) -> None:
    assert_enforced(check_network(plan_facts))


def test_kernel_443_targets_only_the_endpoint_security_group(plan_facts: PlanFacts) -> None:
    rules = collect_egress_rules(plan_facts)
    kernel_443 = [r for r in rules if r.source_sg.plane == "kernel" and r.covers_port(443)]
    assert kernel_443, "the kernel has no 443 egress rule at all; E2 has no subject"
    for rule in kernel_443:
        assert rule.destination.kind == "sg", rule
        assert rule.destination.resource is not None
        assert rule.destination.resource.plane == "endpoint", rule
        assert rule.destination.resource.serves == "kernel", rule


def test_kernel_cannot_reach_the_cognition_endpoint_group(plan_facts: PlanFacts) -> None:
    """The routing fact §10.3 asks for: separate endpoint groups, separate SGs."""
    reachable = {
        sg.address for sg in kernel_reachable_security_groups(collect_egress_rules(plan_facts))
    }
    cognition_endpoint = "aws_security_group.endpoint_cognition"
    assert cognition_endpoint not in reachable
    bedrock = plan_facts.get(BEDROCK_ENDPOINT)
    assert bedrock is not None
    fronting, _ = plan_facts.resolve_attribute_resources(
        bedrock, "security_group_ids", target_types=("aws_security_group",)
    )
    assert {sg.address for sg in fronting} == {cognition_endpoint}


def test_every_network_resource_carries_a_plane_tag(plan_facts: PlanFacts) -> None:
    """Fail-closed classification. An untagged subnet could be a kernel subnet."""
    untagged = [
        r.address
        for r in plan_facts.by_type("aws_subnet", "aws_security_group", "aws_vpc_endpoint")
        if r.plane is None
    ]
    assert not untagged, f"resources with no Plane tag: {untagged}"


# ---------------------------------------------------------------------------
# PL-2: the mutations that must make E2 fail
# ---------------------------------------------------------------------------


def test_bedrock_endpoint_in_a_kernel_subnet_fails_e2(mutate_plan: Any) -> None:
    def mutation(document: dict[str, Any]) -> None:
        configuration_of(document, BEDROCK_ENDPOINT)["expressions"]["subnet_ids"] = {
            "references": ["aws_subnet.kernel_a.id", "aws_subnet.kernel_a"]
        }

    assert_violates(check_network(mutate_plan(mutation)), "E2-BEDROCK-ENDPOINT-IN-KERNEL-SUBNET")


def test_bedrock_endpoint_on_the_kernel_endpoint_sg_fails_e2(mutate_plan: Any) -> None:
    """The subtle one: right subnet group, wrong security group.

    Placing the endpoint in the Cognition subnets is not enough if the security
    group fronting it is the one the kernel is allowed to reach.
    """

    def mutation(document: dict[str, Any]) -> None:
        configuration_of(document, BEDROCK_ENDPOINT)["expressions"]["security_group_ids"] = {
            "references": [
                "aws_security_group.endpoint_kernel.id",
                "aws_security_group.endpoint_kernel",
            ]
        }

    assert_violates(check_network(mutate_plan(mutation)), "E2-BEDROCK-ENDPOINT-KERNEL-REACHABLE")


def test_kernel_443_to_the_internet_fails_e2(mutate_plan: Any) -> None:
    def mutation(document: dict[str, Any]) -> None:
        resource_of(document, KERNEL_443)["values"]["cidr_ipv4"] = "0.0.0.0/0"
        expressions = configuration_of(document, KERNEL_443)["expressions"]
        expressions.pop("referenced_security_group_id")
        expressions["cidr_ipv4"] = {"constant_value": "0.0.0.0/0"}

    assert_violates(check_network(mutate_plan(mutation)), "E2-KERNEL-443-TO-INTERNET")


def test_kernel_443_to_the_cognition_endpoint_group_fails_e2(mutate_plan: Any) -> None:
    def mutation(document: dict[str, Any]) -> None:
        configuration_of(document, KERNEL_443)["expressions"]["referenced_security_group_id"] = {
            "references": [
                "aws_security_group.endpoint_cognition.id",
                "aws_security_group.endpoint_cognition",
            ]
        }

    report = check_network(mutate_plan(mutation))
    assert_violates(report, "E2-ENDPOINT-SERVES-MISMATCH", "E2-BEDROCK-ENDPOINT-KERNEL-REACHABLE")


def test_untagged_subnet_fails_e2(mutate_plan: Any) -> None:
    def mutation(document: dict[str, Any]) -> None:
        entry = resource_of(document, "aws_subnet.kernel_a")
        entry["values"]["tags"] = {}
        entry["values"]["tags_all"] = {}

    assert_violates(check_network(mutate_plan(mutation)), "E2-PLANE-UNTAGGED")


def test_inline_kernel_egress_block_fails_e2(mutate_plan: Any) -> None:
    def mutation(document: dict[str, Any]) -> None:
        resource_of(document, "aws_security_group.kernel")["values"]["egress"] = [
            {
                "from_port": 443,
                "to_port": 443,
                "protocol": "tcp",
                "cidr_blocks": ["0.0.0.0/0"],
            }
        ]

    assert_violates(check_network(mutate_plan(mutation)), "E2-KERNEL-INLINE-EGRESS")


def test_removing_the_kernel_security_group_fails_e2(mutate_plan: Any) -> None:
    def mutation(document: dict[str, Any]) -> None:
        module = document["planned_values"]["root_module"]
        module["resources"] = [
            r for r in module["resources"] if r["address"] != "aws_security_group.kernel"
        ]

    assert_violates(check_network(mutate_plan(mutation)), "E2-KERNEL-SG-ABSENT")


# ---------------------------------------------------------------------------
# The independent second opinion
# ---------------------------------------------------------------------------


def test_rego_agrees_with_python(policy_dir: Path, plan_path: Path) -> None:
    runner = find_policy_runner()
    if runner is None:
        pytest.skip(describe_missing_runner())
    result = run_rego(policy_dir, plan_path, runner=runner)
    assert result is not None
    assert not result.failures, (
        "the Rego re-statement of E1/E2/E4 denied the plan that the Python checkers "
        "passed. One of the two is wrong, and that is exactly what this test exists to "
        "surface:\n  " + "\n  ".join(result.failures)
    )


def test_rego_policies_are_present_and_named() -> None:
    """A missing policy file is a silently-disabled control."""
    expected = {"plan.rego", "e1_iam.rego", "e2_network.rego", "e4_egress.rego"}
    here = Path(__file__).resolve().parent / "policy"
    assert expected <= {p.name for p in here.glob("*.rego")}


def test_rego_denies_a_mutated_plan(policy_dir: Path, tmp_path: Path, plan_document: Any) -> None:
    """PL-2 for the Rego leg: it has to be seen refusing, not just passing."""
    runner = find_policy_runner()
    if runner is None:
        pytest.skip(describe_missing_runner())
    import copy
    import json

    document = copy.deepcopy(dict(plan_document))
    for entry in document["configuration"]["root_module"]["resources"]:
        if entry["address"] == BEDROCK_ENDPOINT:
            entry["expressions"]["subnet_ids"] = {
                "references": ["aws_subnet.kernel_a.id", "aws_subnet.kernel_a"]
            }
    mutated = tmp_path / "plan.json"
    mutated.write_text(json.dumps(document, indent=2), encoding="utf-8")
    result = run_rego(policy_dir, mutated, runner=runner)
    assert result is not None
    assert any("E2-BEDROCK-ENDPOINT-IN-KERNEL-SUBNET" in f for f in result.failures), (
        "the Rego policy did not deny a plan that places the bedrock-runtime endpoint "
        f"in a kernel subnet. Failures reported: {result.failures}"
    )


def test_kernel_and_cognition_have_separate_security_groups(plan_facts: PlanFacts) -> None:
    kernel = security_groups_of_plane(plan_facts, "kernel")
    cognition = security_groups_of_plane(plan_facts, "cognition")
    assert kernel and cognition
    assert not {sg.address for sg in kernel} & {sg.address for sg in cognition}
