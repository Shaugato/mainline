# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""E2 — *no model network path*.

ARCHITECTURE.md §8.2: "Kernel subnets contain **no ``bedrock-runtime`` interface
endpoint**; the kernel SG permits TCP/443 **only** to the interface-endpoint SG.
Bedrock is HTTPS — with no endpoint and no 443-to-internet rule there is no
*route*, not merely no permission." §10.3's endpoint matrix says the same thing
in one cell: ``bedrock-runtime`` is ✘ for the kernel row, and *that absence is the
boundary*.

E2 is the enforcement a security reviewer believes, because it does not depend on
our code being correct. So it is asserted twice, in two languages, over the same
plan: once here in Python, and once in Rego under ``tests/boundary/policy/`` run
by conftest/OPA. The Python and the Rego share only the input document.

The reachability argument is made on the security-group graph, not on tags, and
then re-made on tags. Tags are cheap and a human can read them; the SG graph is
what actually decides whether a packet can leave. A resource carrying **no**
``Plane`` tag is a violation, not an exemption — an untagged subnet could be a
kernel subnet, and a checker that skips what it cannot classify is a checker that
passes by absence.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Any

from .findings import Enforcement, Report
from .planfacts import PLANE_TAG, PlanFacts, Resource

AUTHORITY = "ARCHITECTURE.md §8.2 E2 / §10.3 endpoint matrix"

#: Service-name fragments that identify a model-plane VPC endpoint.
MODEL_ENDPOINT_FRAGMENTS: tuple[str, ...] = (
    "bedrock-runtime",
    "bedrock-agentcore",
    "bedrock-mantle",
    "bedrock",
)

INTERNET_CIDRS: frozenset[str] = frozenset({"0.0.0.0/0", "::/0"})

KERNEL = "kernel"
ENDPOINT = "endpoint"

#: Resource types that must carry a Plane tag for the boundary to be readable.
PLANE_TAGGED_TYPES: tuple[str, ...] = (
    "aws_subnet",
    "aws_security_group",
    "aws_vpc_endpoint",
)


@dataclass(frozen=True, slots=True)
class Destination:
    """Where an egress rule is allowed to send packets."""

    kind: str  # "sg" | "cidr" | "prefix_list" | "unresolved"
    value: str
    resource: Resource | None = None

    def __str__(self) -> str:
        return f"{self.kind}:{self.value}"


@dataclass(frozen=True, slots=True)
class EgressRule:
    """One normalised egress permission out of a security group."""

    address: str
    source_sg: Resource
    protocol: str
    from_port: int | None
    to_port: int | None
    destination: Destination

    def covers_port(self, port: int) -> bool:
        if self.protocol in {"-1", "all"}:
            return True
        if self.from_port is None or self.to_port is None:
            return True  # a rule with no port bounds is a rule that covers everything
        return self.from_port <= port <= self.to_port

    @property
    def port_span(self) -> int:
        if self.from_port is None or self.to_port is None:
            return 65536
        return max(0, self.to_port - self.from_port) + 1

    def __str__(self) -> str:
        ports = (
            "all"
            if self.from_port is None or self.to_port is None
            else (
                str(self.from_port)
                if self.from_port == self.to_port
                else f"{self.from_port}-{self.to_port}"
            )
        )
        return f"{self.address} {self.protocol}/{ports} -> {self.destination}"


# ---------------------------------------------------------------------------
# Normalisation
# ---------------------------------------------------------------------------


def _as_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.strip().lstrip("-").isdigit():
        return int(value)
    return None


def collect_egress_rules(facts: PlanFacts) -> tuple[EgressRule, ...]:
    """Every ``aws_vpc_security_group_egress_rule`` in the plan, normalised.

    Inline ``egress`` blocks on ``aws_security_group`` are *deliberately* not
    normalised here — they are reported as a violation on kernel security groups
    by :func:`check_network`, because an inline block has no address of its own
    and therefore cannot be cited in an audit finding.
    """
    rules: list[EgressRule] = []
    for rule in facts.by_type("aws_vpc_security_group_egress_rule"):
        source_sgs, _ = facts.resolve_attribute_resources(
            rule, "security_group_id", target_types=("aws_security_group",)
        )
        protocol = str(rule.get("ip_protocol", rule.get("protocol", ""))).lower()
        from_port = _as_int(rule.get("from_port"))
        to_port = _as_int(rule.get("to_port"))
        destination = _destination_of(facts, rule)
        if not source_sgs:
            # An egress rule whose source security group cannot be resolved is
            # reported by check_network as E2-EGRESS-SOURCE-UNRESOLVED. The rule
            # itself stands in as the source so that it still appears in the list
            # and cannot be dropped on the floor.
            rules.append(
                EgressRule(
                    address=rule.address,
                    source_sg=rule,
                    protocol=protocol,
                    from_port=from_port,
                    to_port=to_port,
                    destination=destination,
                )
            )
            continue
        for sg in source_sgs:
            rules.append(
                EgressRule(
                    address=rule.address,
                    source_sg=sg,
                    protocol=protocol,
                    from_port=from_port,
                    to_port=to_port,
                    destination=destination,
                )
            )
    return tuple(rules)


def _destination_of(facts: PlanFacts, rule: Resource) -> Destination:
    cidr4 = rule.get("cidr_ipv4")
    if isinstance(cidr4, str) and cidr4:
        return Destination(kind="cidr", value=cidr4)
    cidr6 = rule.get("cidr_ipv6")
    if isinstance(cidr6, str) and cidr6:
        return Destination(kind="cidr", value=cidr6)
    referenced, ref_problems = facts.resolve_attribute_resources(
        rule, "referenced_security_group_id", target_types=("aws_security_group",)
    )
    if referenced:
        target = referenced[0]
        return Destination(kind="sg", value=target.address, resource=target)
    prefix, prefix_problems = facts.resolve_attribute_resources(
        rule, "prefix_list_id", target_types=("aws_ec2_managed_prefix_list",)
    )
    if prefix:
        target = prefix[0]
        return Destination(kind="prefix_list", value=target.address, resource=target)
    if rule.get("referenced_security_group_id") is not None or rule.is_unknown(
        "referenced_security_group_id"
    ):
        return Destination(kind="unresolved", value="; ".join(ref_problems) or "security group")
    if rule.get("prefix_list_id") is not None or rule.is_unknown("prefix_list_id"):
        return Destination(kind="unresolved", value="; ".join(prefix_problems) or "prefix list")
    return Destination(kind="unresolved", value="rule declares no destination the plan can read")


def security_groups_of_plane(facts: PlanFacts, plane: str) -> tuple[Resource, ...]:
    return tuple(sg for sg in facts.by_type("aws_security_group") if sg.plane == plane)


def kernel_reachable_security_groups(rules: Iterable[EgressRule]) -> tuple[Resource, ...]:
    """Security groups the kernel SG is permitted to send packets to."""
    out: dict[str, Resource] = {}
    for rule in rules:
        if rule.source_sg.plane != KERNEL:
            continue
        if rule.destination.kind == "sg" and rule.destination.resource is not None:
            out[rule.destination.resource.address] = rule.destination.resource
    return tuple(out.values())


def model_endpoints(facts: PlanFacts) -> tuple[Resource, ...]:
    out: list[Resource] = []
    for endpoint in facts.by_type("aws_vpc_endpoint"):
        service = str(endpoint.get("service_name", "")).lower()
        if any(fragment in service for fragment in MODEL_ENDPOINT_FRAGMENTS):
            out.append(endpoint)
    return tuple(out)


# ---------------------------------------------------------------------------
# The enforcement
# ---------------------------------------------------------------------------


def check_network(facts: PlanFacts) -> Report:
    """Run E2 over a plan."""
    report = Report(enforcement=Enforcement.E2_NETWORK)

    _check_plane_tags(facts, report)

    kernel_sgs = security_groups_of_plane(facts, KERNEL)
    if not kernel_sgs:
        report.violate(
            rule="E2-KERNEL-SG-ABSENT",
            subject=f"aws_security_group[{PLANE_TAG}=kernel]",
            detail=(
                "the plan contains no security group tagged Plane=kernel, so there is "
                "nothing to assert about the kernel's egress. E2 is unproven, not clean"
            ),
            authority=AUTHORITY,
        )

    rules = collect_egress_rules(facts)
    kernel_rules = tuple(r for r in rules if r.source_sg.plane == KERNEL)
    reachable_sgs = kernel_reachable_security_groups(rules)

    _check_bedrock_endpoints(facts, reachable_sgs, report)
    _check_kernel_443(kernel_rules, report)
    _check_inline_egress(facts, report)

    for rule in rules:
        if rule.source_sg.type == "aws_vpc_security_group_egress_rule":
            report.violate(
                rule="E2-EGRESS-SOURCE-UNRESOLVED",
                subject=rule.address,
                detail=(
                    "this egress rule's security_group_id could not be resolved to a "
                    "security group in the plan, so it cannot be excluded from the "
                    "kernel security group"
                ),
                authority=AUTHORITY,
            )

    if kernel_sgs and not kernel_rules:
        report.violate(
            rule="E2-KERNEL-EGRESS-UNREADABLE",
            subject=", ".join(sg.address for sg in kernel_sgs),
            detail=(
                "a kernel security group exists but no egress rule in the plan resolves "
                "to it; the kernel's egress posture is unreadable from this plan"
            ),
            authority=AUTHORITY,
        )
    return report


def _check_plane_tags(facts: PlanFacts, report: Report) -> None:
    for resource in facts.by_type(*PLANE_TAGGED_TYPES):
        report.examine()
        if resource.plane is None:
            report.violate(
                rule="E2-PLANE-UNTAGGED",
                subject=resource.address,
                detail=(
                    f"no {PLANE_TAG} tag; an untagged {resource.type} cannot be excluded "
                    "from the kernel plane, and a check that skips what it cannot "
                    "classify passes by absence"
                ),
                authority=AUTHORITY,
            )


def _check_bedrock_endpoints(
    facts: PlanFacts, reachable_sgs: Sequence[Resource], report: Report
) -> None:
    reachable = {sg.address for sg in reachable_sgs}
    endpoints = model_endpoints(facts)
    if not endpoints:
        report.note(
            "no bedrock-* VPC endpoint appears anywhere in this plan; the kernel-row "
            "absence in the §10.3 endpoint matrix holds trivially here"
        )
    for endpoint in endpoints:
        report.examine()
        subnets, problems = facts.resolve_attribute_resources(
            endpoint, "subnet_ids", target_types=("aws_subnet",)
        )
        if not subnets:
            report.violate(
                rule="E2-ENDPOINT-SUBNETS-UNRESOLVED",
                subject=endpoint.address,
                detail=(
                    "a bedrock endpoint's subnets could not be resolved from this plan ("
                    + "; ".join(problems or ("no value and no reference",))
                    + "), so it cannot be shown to be outside the kernel subnets"
                ),
                authority=AUTHORITY,
            )
        for subnet in subnets:
            if subnet.plane == KERNEL:
                report.violate(
                    rule="E2-BEDROCK-ENDPOINT-IN-KERNEL-SUBNET",
                    subject=f"{endpoint.address} -> {subnet.address}",
                    detail=(
                        f"interface endpoint for {endpoint.get('service_name')!r} is "
                        "placed in a kernel subnet; §10.3 marks that cell ✘ and calls "
                        "the absence the boundary"
                    ),
                    authority=AUTHORITY,
                )

        endpoint_sgs, sg_problems = facts.resolve_attribute_resources(
            endpoint, "security_group_ids", target_types=("aws_security_group",)
        )
        if not endpoint_sgs:
            report.violate(
                rule="E2-ENDPOINT-SG-UNRESOLVED",
                subject=endpoint.address,
                detail=(
                    "a bedrock endpoint's security groups could not be resolved ("
                    + "; ".join(sg_problems or ("no value and no reference",))
                    + "), so kernel reachability cannot be decided"
                ),
                authority=AUTHORITY,
            )
        for sg in endpoint_sgs:
            if sg.address in reachable:
                report.violate(
                    rule="E2-BEDROCK-ENDPOINT-KERNEL-REACHABLE",
                    subject=f"{endpoint.address} via {sg.address}",
                    detail=(
                        "the kernel security group is permitted to reach the security "
                        "group attached to a bedrock endpoint; the endpoint being in "
                        "another subnet does not help if the packet can get there"
                    ),
                    authority=AUTHORITY,
                )


def _check_kernel_443(kernel_rules: Sequence[EgressRule], report: Report) -> None:
    for rule in kernel_rules:
        report.examine()
        if not rule.covers_port(443):
            continue
        destination = rule.destination
        if destination.kind == "cidr" and destination.value in INTERNET_CIDRS:
            report.violate(
                rule="E2-KERNEL-443-TO-INTERNET",
                subject=str(rule),
                detail=(
                    "the kernel security group permits TCP/443 to the internet; Bedrock "
                    "is HTTPS, so this single rule reinstates the route the whole "
                    "boundary claim rests on"
                ),
                authority=AUTHORITY,
            )
            continue
        if destination.kind == "unresolved":
            report.violate(
                rule="E2-KERNEL-443-DESTINATION-UNRESOLVED",
                subject=str(rule),
                detail=(
                    f"a kernel 443 egress rule has a destination this plan cannot "
                    f"resolve ({destination.value}); it cannot be shown to be the "
                    "interface-endpoint security group"
                ),
                authority=AUTHORITY,
            )
            continue
        if destination.kind != "sg":
            report.violate(
                rule="E2-KERNEL-443-NOT-ENDPOINT-SG",
                subject=str(rule),
                detail=(
                    f"kernel TCP/443 egress targets a {destination.kind} "
                    f"({destination.value}); §8.2 E2 permits 443 only to the "
                    "interface-endpoint security group"
                ),
                authority=AUTHORITY,
            )
            continue
        target = destination.resource
        if target is None or target.plane != ENDPOINT:
            plane = "untagged" if target is None or target.plane is None else target.plane
            report.violate(
                rule="E2-KERNEL-443-NOT-ENDPOINT-SG",
                subject=str(rule),
                detail=(
                    f"kernel TCP/443 egress targets security group {destination.value} "
                    f"whose Plane tag is {plane!r}, not 'endpoint'"
                ),
                authority=AUTHORITY,
            )
            continue
        serves = target.serves
        if serves is not None and serves != KERNEL:
            report.violate(
                rule="E2-ENDPOINT-SERVES-MISMATCH",
                subject=str(rule),
                detail=(
                    f"kernel TCP/443 egress targets endpoint security group "
                    f"{destination.value} tagged Serves={serves!r}; the kernel must "
                    "reach only its own endpoint group"
                ),
                authority=AUTHORITY,
            )


def _check_inline_egress(facts: PlanFacts, report: Report) -> None:
    for sg in facts.by_type("aws_security_group"):
        if sg.plane != KERNEL:
            continue
        inline = sg.get("egress")
        if isinstance(inline, list) and inline:
            report.violate(
                rule="E2-KERNEL-INLINE-EGRESS",
                subject=sg.address,
                detail=(
                    f"the kernel security group declares {len(inline)} inline egress "
                    "block(s); an inline block has no resource address, so a finding "
                    "against it cannot be cited. Use aws_vpc_security_group_egress_rule"
                ),
                authority=AUTHORITY,
            )
