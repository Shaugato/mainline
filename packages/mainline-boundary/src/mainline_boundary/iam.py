# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""E1 — *no model IAM*.

ARCHITECTURE.md §8.2: the ``mainline-kernel`` task role carries a **permissions
boundary** with an explicit ``Deny`` on ``bedrock:*``, ``bedrock-runtime:*`` and
``bedrock-agentcore:*``. §10.3 repeats it in the identity map: ``kernel_task``
(+ permissions boundary denying ``bedrock:*``).

Why a boundary rather than "we just did not grant it": a boundary is the only IAM
construct that survives a later, well-meaning ``AttachRolePolicy``. The claim
being made is not *we did not give the kernel Bedrock* — it is *nobody can*.

Four failure modes this module refuses to treat as passes:

* the kernel role is not in the plan at all (``E1-KERNEL-ROLE-ABSENT``);
* it has a boundary but the plan cannot show us the document
  (``E1-BOUNDARY-UNRESOLVED``) — at plan time the policy ARN is known-after-apply,
  so the link is followed through the configuration reference graph;
* the Deny is present but carries a ``Condition``, which is a Deny that can be
  argued with (``E1-CONDITIONAL-DENY``);
* the Deny is present but scoped to a ``Resource`` narrower than ``*``
  (``E1-NARROW-DENY``) — ``bedrock:InvokeModel`` on an unlisted profile ARN would
  slip straight through.

The live ``iam simulate-principal-policy`` equivalent is in this module too, and
it is off unless credentials genuinely resolve. It never runs in the default CI
lane.
"""

from __future__ import annotations

import fnmatch
import json
import os
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from .findings import Enforcement, Report
from .planfacts import PlanFacts, Resource

AUTHORITY = "ARCHITECTURE.md §8.2 E1 / §10.3 identity map"

#: The actions the boundary must deny outright.
DENIED_ACTIONS: tuple[str, ...] = ("bedrock:*", "bedrock-runtime:*", "bedrock-agentcore:*")

#: How the kernel task role is recognised in a plan. Tag first (authoritative,
#: because §8.1 makes the plane the organising fact), then name.
KERNEL_ROLE_NAMES: frozenset[str] = frozenset(
    {"mainline-kernel", "mainline-kernel-task", "kernel_task", "kernel-task"}
)
KERNEL_PLANE = "kernel"

LIVE_ENV_FLAG = "MAINLINE_BOUNDARY_LIVE_AWS"


@dataclass(frozen=True, slots=True)
class PolicyStatement:
    sid: str
    effect: str
    actions: tuple[str, ...]
    not_actions: tuple[str, ...]
    resources: tuple[str, ...]
    has_condition: bool

    def denies(self, action: str) -> bool:
        if self.effect.lower() != "deny":
            return False
        if self.not_actions:
            # A Deny on NotAction is a deny-everything-except; it covers `action`
            # only when `action` is not in the exception list.
            return not any(fnmatch.fnmatch(action, pattern) for pattern in self.not_actions)
        return any(fnmatch.fnmatch(action, pattern) for pattern in self.actions)

    def allows(self, action: str) -> bool:
        """True when this Allow covers ``action``.

        Matched in **both** directions on purpose. The denied-action list is
        written as wildcards (``bedrock:*``) while a real policy grants concrete
        actions (``bedrock:InvokeModel``); ``fnmatch`` one way round would miss
        exactly the grant we are hunting.
        """
        if self.effect.lower() != "allow":
            return False
        return any(
            fnmatch.fnmatch(action, pattern) or fnmatch.fnmatch(pattern, action)
            for pattern in self.actions
        )

    def allows_service(self, service_prefix: str) -> bool:
        """True when this Allow grants any action in a service whose name starts thus."""
        if self.effect.lower() != "allow":
            return False
        for pattern in self.actions:
            if pattern == "*":
                return True
            service = pattern.split(":", 1)[0].rstrip("*")
            if service and (
                service.startswith(service_prefix) or service_prefix.startswith(service)
            ):
                return True
        return False

    @property
    def is_global_resource(self) -> bool:
        return "*" in self.resources or not self.resources


def parse_policy_document(document: str | Mapping[str, Any]) -> tuple[PolicyStatement, ...]:
    """Parse an IAM policy document (JSON string or already-decoded object)."""
    obj = json.loads(document) if isinstance(document, str) else document
    if not isinstance(obj, Mapping):
        raise ValueError("IAM policy document is not an object")
    raw_statements = obj.get("Statement")
    if isinstance(raw_statements, Mapping):
        raw_statements = [raw_statements]
    if not isinstance(raw_statements, list):
        return ()
    out: list[PolicyStatement] = []
    for entry in raw_statements:
        if not isinstance(entry, Mapping):
            continue
        out.append(
            PolicyStatement(
                sid=str(entry.get("Sid", "")),
                effect=str(entry.get("Effect", "")),
                actions=_as_tuple(entry.get("Action")),
                not_actions=_as_tuple(entry.get("NotAction")),
                resources=_as_tuple(entry.get("Resource")),
                has_condition=bool(entry.get("Condition")),
            )
        )
    return tuple(out)


def _as_tuple(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        return (value,)
    if isinstance(value, list):
        return tuple(str(v) for v in value)
    return ()


# ---------------------------------------------------------------------------
# Plan-time enforcement
# ---------------------------------------------------------------------------


def find_kernel_roles(facts: PlanFacts) -> tuple[Resource, ...]:
    roles = facts.by_type("aws_iam_role")
    tagged = tuple(r for r in roles if r.plane == KERNEL_PLANE)
    if tagged:
        return tagged
    return tuple(
        r
        for r in roles
        if str(r.get("name", "")).lower() in KERNEL_ROLE_NAMES
        or r.name.lower() in KERNEL_ROLE_NAMES
    )


def check_iam(facts: PlanFacts) -> Report:
    """Run E1 over a plan."""
    report = Report(enforcement=Enforcement.E1_IAM)
    roles = find_kernel_roles(facts)

    if not roles:
        report.violate(
            rule="E1-KERNEL-ROLE-ABSENT",
            subject="aws_iam_role[Plane=kernel]",
            detail=(
                "the plan contains no IAM role tagged Plane=kernel and none named "
                f"{sorted(KERNEL_ROLE_NAMES)}. E1 cannot be satisfied by a plan that "
                "does not contain the subject of the claim"
            ),
            authority=AUTHORITY,
        )
        return report

    for role in roles:
        report.examine()
        _check_role(facts, role, report)

    _check_no_bedrock_allow(facts, roles, report)
    return report


def _check_role(facts: PlanFacts, role: Resource, report: Report) -> None:
    policies, problems = facts.resolve_attribute_resources(
        role, "permissions_boundary", target_types=("aws_iam_policy",)
    )
    if not policies:
        report.violate(
            rule="E1-BOUNDARY-UNRESOLVED",
            subject=role.address,
            detail=(
                "the kernel task role's permissions_boundary could not be resolved to a "
                "policy document in this plan ("
                + "; ".join(problems or ("no value and no reference",))
                + "). A boundary we cannot read is a boundary we cannot rely on"
            ),
            authority=AUTHORITY,
        )
        return

    for policy in policies:
        document = policy.get("policy")
        if document is None:
            report.violate(
                rule="E1-BOUNDARY-DOCUMENT-UNKNOWN",
                subject=policy.address,
                detail=(
                    "the boundary policy document is known-after-apply, so the plan "
                    "cannot show that it denies Bedrock. Render the document from a "
                    "data.aws_iam_policy_document so it is literal at plan time"
                ),
                authority=AUTHORITY,
            )
            continue
        try:
            statements = parse_policy_document(document)
        except (ValueError, json.JSONDecodeError) as exc:
            report.violate(
                rule="E1-BOUNDARY-UNPARSEABLE",
                subject=policy.address,
                detail=f"boundary policy document did not parse as IAM JSON: {exc}",
                authority=AUTHORITY,
            )
            continue
        _check_denies(policy.address, statements, report)


def _check_denies(subject: str, statements: Sequence[PolicyStatement], report: Report) -> None:
    for action in DENIED_ACTIONS:
        covering = [s for s in statements if s.denies(action)]
        if not covering:
            report.violate(
                rule="E1-DENY-MISSING",
                subject=subject,
                detail=f"no Deny statement covers {action!r}",
                authority=AUTHORITY,
            )
            continue
        if all(s.has_condition for s in covering):
            report.violate(
                rule="E1-CONDITIONAL-DENY",
                subject=subject,
                detail=(
                    f"every Deny covering {action!r} carries a Condition; a conditional "
                    "Deny is a Deny somebody can argue with in front of a regulator"
                ),
                authority=AUTHORITY,
            )
            continue
        if not any(s.is_global_resource and not s.has_condition for s in covering):
            report.violate(
                rule="E1-NARROW-DENY",
                subject=subject,
                detail=(
                    f"the unconditional Deny covering {action!r} is scoped to specific "
                    "resources; an unlisted inference-profile ARN would pass straight "
                    'through. Use Resource: "*"'
                ),
                authority=AUTHORITY,
            )


def _check_no_bedrock_allow(facts: PlanFacts, roles: Sequence[Resource], report: Report) -> None:
    """A boundary makes an Allow inert, but an Allow on the kernel is still a defect.

    It means somebody believed the kernel needed Bedrock, and the next person to
    remove the boundary gets a working model call rather than an error.
    """
    role_addresses = {r.address for r in roles}
    inline = facts.by_type("aws_iam_role_policy")
    for policy in inline:
        targets, _ = facts.resolve_attribute_resources(
            policy, "role", target_types=("aws_iam_role",)
        )
        if not any(t.address in role_addresses for t in targets):
            continue
        document = policy.get("policy")
        if not isinstance(document, str):
            continue
        try:
            statements = parse_policy_document(document)
        except (ValueError, json.JSONDecodeError):
            continue
        for service in ("bedrock", "bedrock-runtime", "bedrock-agentcore"):
            offending = [s for s in statements if s.allows_service(service)]
            if offending:
                actions = sorted({a for s in offending for a in s.actions})
                report.violate(
                    rule="E1-KERNEL-ALLOWS-BEDROCK",
                    subject=policy.address,
                    detail=(
                        f"an inline policy on the kernel role Allows {service} actions "
                        f"{actions}; the boundary makes that inert today and a defect "
                        "tomorrow"
                    ),
                    authority=AUTHORITY,
                )
                break


# ---------------------------------------------------------------------------
# The live equivalent — off by default
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class LiveAvailability:
    available: bool
    reason: str


def live_simulation_available() -> LiveAvailability:
    """Is the live ``iam simulate-principal-policy`` leg runnable right now?

    Three gates, all of which must open: the operator asked for it, boto3 is
    installed, and STS actually answers. As of 2026-08 the third gate is shut on
    the build machine, and PL-3 forbids putting an unproven capability on a dated
    path — so this returns ``False`` with the reason rather than failing a suite.
    """
    if os.environ.get(LIVE_ENV_FLAG) != "1":
        return LiveAvailability(False, f"{LIVE_ENV_FLAG} is not set to 1")
    try:  # pragma: no cover - depends on the optional extra
        # Lazy and optional by design: this package must be runnable, and every
        # plan-time enforcement must pass, with no AWS SDK installed at all.
        import boto3
    except ImportError:
        return LiveAvailability(
            False, "boto3 is not installed (install the 'aws' extra of mainline-boundary)"
        )
    try:  # pragma: no cover - depends on live credentials
        boto3.client("sts").get_caller_identity()
    except Exception as exc:
        return LiveAvailability(False, f"AWS credentials did not resolve: {type(exc).__name__}")
    return LiveAvailability(True, "credentials resolved")


def simulate_kernel_denies(
    role_arn: str,
    *,
    actions: Sequence[str] = DENIED_ACTIONS,
    region: str = "ap-southeast-2",
) -> Report:
    """``aws iam simulate-principal-policy`` over the kernel role.

    Every action must evaluate to ``explicitDeny``. ``implicitDeny`` is *not*
    acceptable: an implicit deny is the absence of a grant, which the next
    ``AttachRolePolicy`` removes, and the claim in §8.2 is that the boundary makes
    the grant impossible.
    """
    report = Report(enforcement=Enforcement.E1_IAM)
    availability = live_simulation_available()
    if not availability.available:
        report.skip(
            rule="E1-LIVE-SIMULATION",
            subject=role_arn,
            reason=(
                f"live IAM simulation not attempted: {availability.reason}. "
                "The plan-time assertion above still stands; this leg does not."
            ),
        )
        return report

    import boto3

    client = boto3.client("iam", region_name=region)
    # simulate-principal-policy wants concrete action names, not wildcards.
    concrete = [_concrete_action(a) for a in actions]
    response = client.simulate_principal_policy(
        PolicySourceArn=role_arn, ActionNames=concrete, ResourceArns=["*"]
    )
    for result in response.get("EvaluationResults", []):
        report.examine()
        decision = str(result.get("EvalDecision", ""))
        name = str(result.get("EvalActionName", ""))
        if decision != "explicitDeny":
            report.violate(
                rule="E1-LIVE-NOT-EXPLICIT-DENY",
                subject=f"{role_arn}:{name}",
                detail=(
                    f"simulate-principal-policy returned {decision!r}; §8.2 E1 requires "
                    "explicitDeny, because an implicit deny is removed by the next "
                    "AttachRolePolicy"
                ),
                authority=AUTHORITY,
            )
    if report.examined == 0:
        report.violate(
            rule="E1-LIVE-NO-RESULTS",
            subject=role_arn,
            detail="simulate-principal-policy returned no evaluation results",
            authority=AUTHORITY,
        )
    return report


def _concrete_action(wildcard: str) -> str:
    """``bedrock-runtime:*`` → ``bedrock-runtime:InvokeModel``.

    The simulator rejects wildcard action names, so each denied service is probed
    with the one action that would actually matter if it were permitted.
    """
    mapping = {
        "bedrock:*": "bedrock:InvokeModel",
        "bedrock-runtime:*": "bedrock-runtime:InvokeModel",
        "bedrock-agentcore:*": "bedrock-agentcore:InvokeAgentRuntime",
    }
    return mapping.get(wildcard, wildcard.replace(":*", ":*"))
