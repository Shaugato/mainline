# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""E4 — *no model prompt path*.

ARCHITECTURE.md §8.2: "The kernel's only outbound protocols are pgwire and HTTPS
to enumerated in-VPC endpoints." §10.3 restates it as an egress rule: "Kernel:
TCP/26257 to the database path and TCP/443 to the endpoint SG only — no 443 to
``0.0.0.0/0``."

E2 asks *can the kernel reach Bedrock*. E4 asks the stronger, dumber question:
*what is the complete set of protocols the kernel can speak, and is it exactly
two?* A boundary argued destination-by-destination is one new destination away
from being wrong; a boundary argued as a closed protocol set fails loudly when
anything is added.

**The FIS blackhole game-day is spec'd and unrun, and this module is where that
is recorded.** §8.2 lists an AWS FIS blackhole of the kernel's SQL egress as the
thing that proves the gate *refuses* rather than admits, and §19 GT-16 says
task-level FIS network actions on Fargate need the SSM agent in the task
definition — unverified. So the experiment ships as data with
``verified: false``, and :func:`check_fis_record` fails if anyone flips that flag
without an attestation, or if any camera-facing document claims the game-day ran.
Do not promise it on camera before GT-16 passes.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from importlib import resources
from pathlib import Path
from typing import Any

import yaml

from .findings import Enforcement, Report
from .network import KERNEL, EgressRule, collect_egress_rules, security_groups_of_plane
from .planfacts import PlanFacts
from .repo import iter_files

AUTHORITY = "ARCHITECTURE.md §8.2 E4 / §10.3 egress by plane"

#: pgwire and HTTPS. Exactly these two, and nothing else.
PERMITTED_KERNEL_PORTS: frozenset[int] = frozenset({443, 26257})

#: Plane tags an enumerated in-VPC destination may carry.
ENUMERATED_DESTINATION_PLANES: frozenset[str] = frozenset({"endpoint", "database"})

FIS_RESOURCE = "fis-blackhole.yaml"

#: Documents that speak to the outside world. A claim here is a claim on camera.
CLAIM_DOCUMENT_GLOBS: tuple[str, ...] = ("README.md", "VERIFY.md")
CLAIM_DOCUMENT_DIRS: tuple[str, ...] = ("docs/deck", "docs/submission")

#: Phrases that assert the blackhole experiment actually happened.
FIS_CLAIM_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(
        r"\bblackhol\w*\b[^.\n]{0,80}\b(ran|passed|verified|proved|proven|demonstrat\w+)\b",
        re.IGNORECASE,
    ),
    re.compile(r"\b(we|mainline)\s+blackholed\b", re.IGNORECASE),
    re.compile(
        r"\bgame[- ]day\b[^.\n]{0,60}\b(passed|completed|verified|proved|proven)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\bFIS\b[^.\n]{0,60}\bexperiment\b[^.\n]{0,40}\b(ran|passed|verified)\b",
        re.IGNORECASE,
    ),
)


@dataclass(frozen=True, slots=True)
class FisRecord:
    """The blackhole experiment as a data record rather than a promise."""

    experiment_id: str
    status: str
    verified: bool
    blocked_by: str
    hypothesis: str
    expected_gate_behaviour: str
    may_be_claimed: bool
    attestation_path: str
    raw: dict[str, Any]


def load_fis_record() -> FisRecord:
    text = (
        resources.files("mainline_boundary")
        .joinpath("data", FIS_RESOURCE)
        .read_text(encoding="utf-8")
    )
    raw = yaml.safe_load(text)
    if not isinstance(raw, dict):
        raise ValueError(f"{FIS_RESOURCE} did not parse to a mapping")
    return FisRecord(
        experiment_id=str(raw.get("experiment_id", "")),
        status=str(raw.get("status", "")),
        verified=bool(raw.get("verified", False)),
        blocked_by=str(raw.get("blocked_by", "")),
        hypothesis=str(raw.get("hypothesis", "")),
        expected_gate_behaviour=str(raw.get("expected_gate_behaviour", "")),
        may_be_claimed=bool(raw.get("may_be_claimed", False)),
        attestation_path=str(raw.get("attestation_path", "")),
        raw=raw,
    )


# ---------------------------------------------------------------------------
# The protocol-set assertion
# ---------------------------------------------------------------------------


def kernel_egress_rules(facts: PlanFacts) -> tuple[EgressRule, ...]:
    return tuple(r for r in collect_egress_rules(facts) if r.source_sg.plane == KERNEL)


def check_kernel_protocol_set(facts: PlanFacts) -> Report:
    """Assert the kernel's outbound protocol set is exactly pgwire + in-VPC HTTPS."""
    report = Report(enforcement=Enforcement.E4_EGRESS)

    kernel_sgs = security_groups_of_plane(facts, KERNEL)
    if not kernel_sgs:
        report.violate(
            rule="E4-KERNEL-SG-ABSENT",
            subject="aws_security_group[Plane=kernel]",
            detail=(
                "no kernel security group in the plan; the outbound protocol set of a "
                "security group that does not exist is not 'empty', it is 'unknown'"
            ),
            authority=AUTHORITY,
        )
        return report

    rules = kernel_egress_rules(facts)
    if not rules:
        report.violate(
            rule="E4-KERNEL-EGRESS-ABSENT",
            subject=", ".join(sg.address for sg in kernel_sgs),
            detail=(
                "a kernel security group exists but the plan shows no egress rule for "
                "it, so the protocol set cannot be enumerated"
            ),
            authority=AUTHORITY,
        )
        return report

    observed_ports: set[int] = set()
    for rule in rules:
        report.examine()
        _check_rule(rule, report, observed_ports)

    missing = PERMITTED_KERNEL_PORTS - observed_ports
    if missing:
        report.violate(
            rule="E4-PROTOCOL-SET-INCOMPLETE",
            subject="kernel egress",
            detail=(
                f"the kernel cannot reach {sorted(missing)}; §8.2 E4 states the outbound "
                "protocol set is pgwire (26257) plus HTTPS (443) to enumerated in-VPC "
                "endpoints, and a kernel that cannot open a pgwire session cannot refuse "
                "a merge either — it fails to start"
            ),
            authority=AUTHORITY,
        )
    extra = observed_ports - PERMITTED_KERNEL_PORTS
    if extra:
        report.violate(
            rule="E4-PROTOCOL-SET-EXCEEDED",
            subject="kernel egress",
            detail=(
                f"the kernel can additionally reach {sorted(extra)}; the protocol set is "
                f"closed at exactly {sorted(PERMITTED_KERNEL_PORTS)}"
            ),
            authority=AUTHORITY,
        )
    report.note(f"kernel outbound protocol set observed: {sorted(observed_ports)}")
    return report


def _check_rule(rule: EgressRule, report: Report, observed_ports: set[int]) -> None:
    if rule.protocol not in {"tcp"}:
        report.violate(
            rule="E4-PROTOCOL-NOT-TCP",
            subject=str(rule),
            detail=(
                f"kernel egress rule uses ip_protocol {rule.protocol!r}; '-1'/'all' "
                "makes the protocol set unbounded and UDP is not one of the two "
                "protocols §8.2 E4 permits"
            ),
            authority=AUTHORITY,
        )
        return
    if rule.from_port is None or rule.to_port is None:
        report.violate(
            rule="E4-PORT-RANGE-UNBOUNDED",
            subject=str(rule),
            detail="kernel egress rule declares no port bounds",
            authority=AUTHORITY,
        )
        return
    if rule.from_port != rule.to_port:
        report.violate(
            rule="E4-PORT-RANGE-WIDE",
            subject=str(rule),
            detail=(
                f"kernel egress rule spans {rule.port_span} ports "
                f"({rule.from_port}-{rule.to_port}); each permitted protocol must be its "
                "own single-port rule so the set can be read off the plan"
            ),
            authority=AUTHORITY,
        )
        return

    port = rule.from_port
    observed_ports.add(port)
    if port not in PERMITTED_KERNEL_PORTS:
        report.violate(
            rule="E4-PORT-NOT-PERMITTED",
            subject=str(rule),
            detail=(
                f"kernel egress to TCP/{port} is outside the closed set "
                f"{sorted(PERMITTED_KERNEL_PORTS)}"
            ),
            authority=AUTHORITY,
        )
        return

    destination = rule.destination
    if destination.kind == "unresolved":
        report.violate(
            rule="E4-DESTINATION-UNRESOLVED",
            subject=str(rule),
            detail=(
                f"kernel TCP/{port} destination cannot be resolved from this plan "
                f"({destination.value}); an unenumerable destination is not an "
                "enumerated one"
            ),
            authority=AUTHORITY,
        )
        return
    if destination.kind == "cidr":
        report.violate(
            rule="E4-DESTINATION-NOT-ENUMERATED",
            subject=str(rule),
            detail=(
                f"kernel TCP/{port} egress targets the raw CIDR {destination.value}; "
                "§10.3 requires an enumerated destination — an interface-endpoint "
                "security group, or a managed prefix list carrying the database path"
            ),
            authority=AUTHORITY,
        )
        return
    target = destination.resource
    plane = target.plane if target is not None else None
    if plane not in ENUMERATED_DESTINATION_PLANES:
        report.violate(
            rule="E4-DESTINATION-NOT-ENUMERATED",
            subject=str(rule),
            detail=(
                f"kernel TCP/{port} egress targets {destination.value} whose Plane tag "
                f"is {plane!r}; permitted destination planes are "
                f"{sorted(ENUMERATED_DESTINATION_PLANES)}"
            ),
            authority=AUTHORITY,
        )
        return
    if port == 443 and plane != "endpoint":
        report.violate(
            rule="E4-HTTPS-NOT-IN-VPC-ENDPOINT",
            subject=str(rule),
            detail=(
                f"kernel HTTPS egress targets a {plane!r}-plane destination; §8.2 E4 "
                "permits HTTPS only to enumerated in-VPC interface endpoints"
            ),
            authority=AUTHORITY,
        )


# ---------------------------------------------------------------------------
# The FIS record
# ---------------------------------------------------------------------------


def check_fis_record(repo_root: Path, record: FisRecord | None = None) -> Report:
    """Assert the blackhole experiment is recorded as specified-and-unrun.

    Two directions, because both failures are real. If the record claims
    ``verified: true`` without an attestation on disk, that is a promise nobody
    can check. If a camera-facing document says the game-day ran while the record
    says it did not, that is the same lie told to a wider audience.
    """
    report = Report(enforcement=Enforcement.E4_EGRESS)
    fis = record if record is not None else load_fis_record()
    report.examine()

    if fis.verified:
        attestation = repo_root / fis.attestation_path if fis.attestation_path else None
        if attestation is None or not attestation.exists():
            report.violate(
                rule="E4-FIS-UNBACKED-CLAIM",
                subject=fis.experiment_id,
                detail=(
                    "the FIS blackhole record claims verified: true but no attestation "
                    f"exists at {fis.attestation_path or '<unset>'}. §19 GT-16 is "
                    "unanswered; an unanswered question is a failed one"
                ),
                authority=AUTHORITY,
            )
    else:
        if fis.status != "specified":
            report.violate(
                rule="E4-FIS-STATUS",
                subject=fis.experiment_id,
                detail=(
                    f"status is {fis.status!r}; an unverified experiment is 'specified', "
                    "and any other word invites a reader to assume it ran"
                ),
                authority=AUTHORITY,
            )
        if fis.may_be_claimed:
            report.violate(
                rule="E4-FIS-CLAIMABLE",
                subject=fis.experiment_id,
                detail=(
                    "may_be_claimed is true while verified is false; that combination is "
                    "how an unrun experiment ends up on camera"
                ),
                authority=AUTHORITY,
            )
        if not fis.blocked_by:
            report.violate(
                rule="E4-FIS-NO-BLOCKER",
                subject=fis.experiment_id,
                detail="an unverified experiment must name the check that unblocks it (GT-16)",
                authority=AUTHORITY,
            )

    for document, text in _claim_documents(repo_root):
        report.examine()
        for pattern in FIS_CLAIM_PATTERNS:
            for match in pattern.finditer(text):
                if fis.verified and fis.may_be_claimed:
                    continue
                line = text.count("\n", 0, match.start()) + 1
                report.violate(
                    rule="E4-FIS-CLAIMED-BUT-UNRUN",
                    subject=f"{document}:{line}",
                    detail=(
                        f"document asserts the blackhole experiment happened "
                        f"({match.group(0).strip()!r}) while the record says "
                        f"verified={fis.verified}"
                    ),
                    authority=AUTHORITY,
                )
    return report


def _claim_documents(repo_root: Path) -> tuple[tuple[str, str], ...]:
    out: list[tuple[str, str]] = []
    paths: list[Path] = []
    for name in CLAIM_DOCUMENT_GLOBS:
        candidate = repo_root / name
        if candidate.is_file():
            paths.append(candidate)
    for directory in CLAIM_DOCUMENT_DIRS:
        base = repo_root / directory
        if base.is_dir():
            paths.extend(iter_files(base, (".md", ".txt")))
    for path in paths:
        try:
            out.append((path.relative_to(repo_root).as_posix(), path.read_text(encoding="utf-8")))
        except (OSError, UnicodeDecodeError, ValueError):
            continue
    return tuple(out)


def check_egress(facts: PlanFacts, repo_root: Path) -> Report:
    """Both E4 legs: the closed protocol set, and the honestly-unrun FIS record."""
    report = Report(enforcement=Enforcement.E4_EGRESS)
    report.merge(check_kernel_protocol_set(facts))
    report.merge(check_fis_record(repo_root))
    return report


def permitted_ports() -> Sequence[int]:
    return sorted(PERMITTED_KERNEL_PORTS)
