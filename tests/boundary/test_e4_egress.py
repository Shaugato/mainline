# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""E4 — no model prompt path.

ARCHITECTURE.md §8.2: "The kernel's only outbound protocols are pgwire and HTTPS
to enumerated in-VPC endpoints." §10.3: "Kernel: TCP/26257 to the database path
and TCP/443 to the endpoint SG only — no 443 to ``0.0.0.0/0``."

E2 asks whether the kernel can reach Bedrock. E4 asks the stronger, duller
question — *what is the complete set of protocols the kernel can speak* — and
requires the answer to be exactly two. A boundary argued destination-by-
destination is one new destination away from being wrong.

The second half of this module is about honesty rather than networking. §8.2
names an AWS FIS blackhole of the kernel's SQL egress as E4's live assertion.
§19 GT-16 says task-level FIS network actions on Fargate need the SSM agent in
the task definition, and GT-16 is unanswered; its pre-committed fallback is one
sentence: *do not promise it on camera*. So the experiment ships as a data record
marked ``verified: false``, and these tests fail if that marker is flipped
without an attestation or if any camera-facing document says the game-day ran.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from mainline_boundary.egress import (
    PERMITTED_KERNEL_PORTS,
    check_fis_record,
    check_kernel_protocol_set,
    kernel_egress_rules,
    load_fis_record,
)
from mainline_boundary.planfacts import PlanFacts
from mainline_boundary.testkit import (
    assert_enforced,
    assert_violates,
    configuration_of,
    resource_of,
)

KERNEL_PGWIRE = "aws_vpc_security_group_egress_rule.kernel_pgwire"
KERNEL_443 = "aws_vpc_security_group_egress_rule.kernel_endpoints_https"


def test_kernel_outbound_protocol_set_is_exactly_two(plan_facts: PlanFacts) -> None:
    assert_enforced(check_kernel_protocol_set(plan_facts))
    ports = {r.from_port for r in kernel_egress_rules(plan_facts)}
    assert ports == set(PERMITTED_KERNEL_PORTS), (
        f"the kernel's outbound protocol set is {sorted(p for p in ports if p is not None)}, "
        "not exactly pgwire + HTTPS"
    )


def test_pgwire_goes_to_an_enumerated_destination(plan_facts: PlanFacts) -> None:
    """Enumeration, not PrivateLink.

    §11.7 forbids claiming PrivateLink on a checkpoint-tier cluster, so the
    database path is a managed prefix list holding the CockroachDB Cloud egress
    CIDRs. The claim is that the destination set is closed and readable — not
    that the traffic never touches the internet.
    """
    pgwire = [r for r in kernel_egress_rules(plan_facts) if r.from_port == 26257]
    assert pgwire, "the kernel has no pgwire egress rule"
    for rule in pgwire:
        assert rule.destination.kind == "prefix_list", rule
        assert rule.destination.resource is not None
        assert rule.destination.resource.plane == "database", rule


def test_https_goes_only_to_an_in_vpc_interface_endpoint(plan_facts: PlanFacts) -> None:
    https = [r for r in kernel_egress_rules(plan_facts) if r.from_port == 443]
    assert https
    for rule in https:
        assert rule.destination.kind == "sg"
        assert rule.destination.resource is not None
        assert rule.destination.resource.plane == "endpoint"


# ---------------------------------------------------------------------------
# PL-2: the mutations that must make E4 fail
# ---------------------------------------------------------------------------


def test_a_third_protocol_fails_e4(mutate_plan: Any) -> None:
    """Adding SMTP is not a Bedrock hole, and E4 must fail on it anyway.

    That is the point of stating the protocol set as closed: the check does not
    depend on anyone anticipating which extra protocol gets added.
    """

    def mutation(document: dict[str, Any]) -> None:
        extra = {
            "address": "aws_vpc_security_group_egress_rule.kernel_smtp",
            "mode": "managed",
            "type": "aws_vpc_security_group_egress_rule",
            "name": "kernel_smtp",
            "values": {
                "security_group_id": None,
                "ip_protocol": "tcp",
                "from_port": 587,
                "to_port": 587,
                "cidr_ipv4": None,
                "referenced_security_group_id": None,
                "prefix_list_id": None,
                "tags": {"Plane": "shared", "Component": "egress-rule"},
            },
        }
        document["planned_values"]["root_module"]["resources"].append(extra)
        document["configuration"]["root_module"]["resources"].append(
            {
                "address": "aws_vpc_security_group_egress_rule.kernel_smtp",
                "mode": "managed",
                "type": "aws_vpc_security_group_egress_rule",
                "name": "kernel_smtp",
                "expressions": {
                    "security_group_id": {
                        "references": [
                            "aws_security_group.kernel.id",
                            "aws_security_group.kernel",
                        ]
                    },
                    "referenced_security_group_id": {
                        "references": [
                            "aws_security_group.endpoint_kernel.id",
                            "aws_security_group.endpoint_kernel",
                        ]
                    },
                },
            }
        )

    report = check_kernel_protocol_set(mutate_plan(mutation))
    assert_violates(report, "E4-PORT-NOT-PERMITTED", "E4-PROTOCOL-SET-EXCEEDED")


def test_an_all_protocols_rule_fails_e4(mutate_plan: Any) -> None:
    def mutation(document: dict[str, Any]) -> None:
        values = resource_of(document, KERNEL_443)["values"]
        values["ip_protocol"] = "-1"
        values["from_port"] = None
        values["to_port"] = None

    assert_violates(check_kernel_protocol_set(mutate_plan(mutation)), "E4-PROTOCOL-NOT-TCP")


def test_a_wide_port_range_fails_e4(mutate_plan: Any) -> None:
    def mutation(document: dict[str, Any]) -> None:
        values = resource_of(document, KERNEL_443)["values"]
        values["from_port"] = 1
        values["to_port"] = 65535

    assert_violates(check_kernel_protocol_set(mutate_plan(mutation)), "E4-PORT-RANGE-WIDE")


def test_a_raw_cidr_destination_fails_e4(mutate_plan: Any) -> None:
    def mutation(document: dict[str, Any]) -> None:
        resource_of(document, KERNEL_PGWIRE)["values"]["cidr_ipv4"] = "203.0.113.0/24"
        configuration_of(document, KERNEL_PGWIRE)["expressions"].pop("prefix_list_id")

    assert_violates(
        check_kernel_protocol_set(mutate_plan(mutation)), "E4-DESTINATION-NOT-ENUMERATED"
    )


def test_losing_pgwire_fails_e4(mutate_plan: Any) -> None:
    """A kernel that cannot open a database session does not refuse — it fails to start."""

    def mutation(document: dict[str, Any]) -> None:
        module = document["planned_values"]["root_module"]
        module["resources"] = [
            r for r in module["resources"] if r["address"] != KERNEL_PGWIRE
        ]

    assert_violates(
        check_kernel_protocol_set(mutate_plan(mutation)), "E4-PROTOCOL-SET-INCOMPLETE"
    )


# ---------------------------------------------------------------------------
# The FIS blackhole: specified, unrun, and said so
# ---------------------------------------------------------------------------


def test_fis_record_is_marked_unverified() -> None:
    record = load_fis_record()
    assert record.verified is False, (
        "the FIS blackhole record claims to be verified. GT-16 is unanswered and AWS "
        "credentials are not valid on the build machine; if this genuinely ran, commit "
        f"the attestation at {record.attestation_path} and this test will accept it."
    )
    assert record.status == "specified"
    assert record.may_be_claimed is False
    assert record.blocked_by == "GT-16"
    assert record.hypothesis and record.expected_gate_behaviour


def test_no_document_claims_the_blackhole_ran(repo_root: Path) -> None:
    assert_enforced(check_fis_record(repo_root))


def test_flipping_verified_without_an_attestation_fails(repo_root: Path) -> None:
    from dataclasses import replace

    record = load_fis_record()
    lying = replace(record, verified=True, may_be_claimed=True)
    report = check_fis_record(repo_root, lying)
    assert_violates(report, "E4-FIS-UNBACKED-CLAIM")


def test_a_document_claiming_the_game_day_ran_fails(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text(
        "# MAINLINE\n\nOur FIS blackhole game-day passed: we blackholed the kernel's "
        "SQL egress and the gate refused every merge.\n",
        encoding="utf-8",
    )
    report = check_fis_record(tmp_path)
    assert_violates(report, "E4-FIS-CLAIMED-BUT-UNRUN")
