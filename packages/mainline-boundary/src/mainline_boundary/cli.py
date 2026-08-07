# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""``mainline-boundary`` — run any one enforcement, or all of them.

Exit codes are part of the contract, because CI reads them:

===  =========================================================================
0    the enforcement ran and found nothing
1    the enforcement ran and found violations
3    the enforcement examined nothing and gave no reason — a VACUOUS check,
     which is a failure. This code exists so that "the check passed" and "the
     check did not happen" can never be the same exit status.
4    a skip with a stated reason, and nothing examined (the caller decides
     whether that is acceptable; ``--strict`` turns it into 1)
===  =========================================================================
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

from .astscan import DEFAULT_KERNEL_ROOTS, scan_kernel_code_boundary
from .egress import check_egress
from .findings import Enforcement, Report
from .fleet import check_fleet_file, fleet_path
from .greps import run_all_greps
from .iam import check_iam
from .network import check_network
from .planfacts import PlanFacts
from .repo import find_repo_root
from .sbom import check_sbom_pair

DEFAULT_PLAN = "tests/boundary/fixtures/plan.json"
DEFAULT_SBOM_BASELINE = "evidence/sbom/kernel/baseline.cdx.json"
DEFAULT_SBOM_CURRENT = "evidence/sbom/kernel/current.cdx.json"

EXIT_OK = 0
EXIT_VIOLATIONS = 1
EXIT_VACUOUS = 3
EXIT_SKIPPED = 4


def _plan(repo_root: Path, override: str | None) -> PlanFacts:
    path = Path(override) if override else repo_root / DEFAULT_PLAN
    if not path.is_absolute():
        path = (repo_root / path).resolve()
    return PlanFacts.from_file(path)


def _run(command: str, args: argparse.Namespace, repo_root: Path) -> Report:
    if command == "e1":
        return check_iam(_plan(repo_root, args.plan))
    if command == "e2":
        return check_network(_plan(repo_root, args.plan))
    if command == "e3":
        report = scan_kernel_code_boundary(repo_root, roots=DEFAULT_KERNEL_ROOTS)
        report.merge(
            check_sbom_pair(
                repo_root / (args.sbom_baseline or DEFAULT_SBOM_BASELINE),
                repo_root / (args.sbom_current or DEFAULT_SBOM_CURRENT),
            )
        )
        return report
    if command == "e4":
        return check_egress(_plan(repo_root, args.plan), repo_root)
    if command == "fleet":
        path = Path(args.fleet) if args.fleet else fleet_path(repo_root)
        if not path.is_absolute():
            path = (repo_root / path).resolve()
        if not path.exists():
            report = Report(enforcement=Enforcement.FLEET)
            report.skip(
                rule="FLEET-REGISTER-ABSENT",
                subject=str(path),
                reason=(
                    "spec/agents/fleet.yaml does not exist yet (owned by the "
                    "agent-contracts-red worker). Nothing was asserted about the fleet"
                ),
            )
            return report
        return check_fleet_file(path)
    if command == "greps":
        return run_all_greps(repo_root)
    raise SystemExit(f"unknown command {command!r}")


def _exit_code(report: Report, *, strict: bool) -> int:
    if report.violations:
        return EXIT_VIOLATIONS
    if report.examined == 0:
        if report.skips:
            return EXIT_VIOLATIONS if strict else EXIT_SKIPPED
        return EXIT_VACUOUS
    return EXIT_OK


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="mainline-boundary",
        description=(
            "The determinism boundary, asserted four independent ways "
            "(ARCHITECTURE.md §8.2 E1-E4) plus the fleet matrix and the CI greps."
        ),
    )
    parser.add_argument(
        "command",
        choices=("e1", "e2", "e3", "e4", "fleet", "greps", "all"),
        help="which enforcement to run",
    )
    parser.add_argument("--repo-root", default=None, help="repository root (auto-detected)")
    parser.add_argument("--plan", default=None, help=f"plan JSON (default {DEFAULT_PLAN})")
    parser.add_argument("--fleet", default=None, help="fleet register YAML")
    parser.add_argument("--sbom-baseline", default=None, help="previous-digest SBOM")
    parser.add_argument("--sbom-current", default=None, help="current-image SBOM")
    parser.add_argument("--json", action="store_true", help="emit the report as JSON")
    parser.add_argument(
        "--strict",
        action="store_true",
        help="treat a skip-with-reason that examined nothing as a failure",
    )
    args = parser.parse_args(argv)

    repo_root = Path(args.repo_root).resolve() if args.repo_root else find_repo_root(Path.cwd())

    commands = ("e1", "e2", "e3", "e4", "fleet", "greps") if args.command == "all" else (
        args.command,
    )
    # Severity order, worst last. Violations beat vacuity beats a stated skip,
    # because "we found a hole" is more actionable than "we did not look".
    severity = {EXIT_OK: 0, EXIT_SKIPPED: 1, EXIT_VACUOUS: 2, EXIT_VIOLATIONS: 3}
    worst = EXIT_OK
    for command in commands:
        report = _run(command, args, repo_root)
        if args.json:
            print(report.to_json())
        else:
            print(report.summary())
        code = _exit_code(report, strict=args.strict)
        if severity[code] > severity[worst]:
            worst = code
    return worst


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
