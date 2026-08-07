# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""``mainline-boundary`` — the determinism boundary, asserted four ways.

*A regulator must be able to read the merge gate in ten minutes and see no model
in it.* A comment saying so is worth nothing under cross-examination, so
ARCHITECTURE.md §8.2 draws the boundary physically, with four independent
enforcements. This package implements all four, plus the fleet capability matrix
and this domain's CI greps.

===  ==============================  ==========================================
E1   no model IAM                    :mod:`mainline_boundary.iam`
E2   no model network path           :mod:`mainline_boundary.network`
E3   no model code path              :mod:`mainline_boundary.astscan`,
                                     :mod:`mainline_boundary.sbom`
E4   no model prompt path            :mod:`mainline_boundary.egress`
===  ==============================  ==========================================

They are separate modules, separate test files and separate CI jobs on purpose:
the value of four enforcements is that they do not share a failure mode. Where
they cannot help but share something — E2 and E4 both read the same plan through
:mod:`mainline_boundary.planfacts` — the shared component is re-stated in Rego
and evaluated by conftest/OPA, an engine we did not write.

Nothing here needs a live AWS account or a live cluster. E1/E2/E4 read a
committed OpenTofu plan JSON; the live ``iam simulate-principal-policy`` leg is
behind :data:`mainline_boundary.iam.LIVE_ENV_FLAG` and skips with a reason when
credentials do not resolve.
"""

from __future__ import annotations

from .astscan import ImportGraph, ModuleIndex, scan_kernel_code_boundary
from .egress import check_egress, check_fis_record, check_kernel_protocol_set, load_fis_record
from .errors import (
    BoundaryError,
    FleetParseError,
    PlanParseError,
    SbomParseError,
    VacuousCheck,
)
from .findings import Enforcement, Exemption, Finding, Report, Skip
from .fleet import AgentSpec, check_fleet, check_fleet_file, load_fleet, resolve_plane
from .greps import (
    run_all_greps,
    scan_metric_labels,
    scan_must_not_claim,
    scan_retry_dependencies,
    scan_retry_imports,
    scan_sampling_params,
)
from .iam import check_iam, live_simulation_available, simulate_kernel_denies
from .network import check_network
from .planfacts import PlanFacts, Resource
from .repo import find_repo_root
from .sbom import check_sbom_pair, diff_sboms, load_sbom
from .testkit import assert_enforced, assert_violates

__version__ = "0.1.0"

__all__ = [
    "AgentSpec",
    "BoundaryError",
    "Enforcement",
    "Exemption",
    "Finding",
    "FleetParseError",
    "ImportGraph",
    "ModuleIndex",
    "PlanFacts",
    "PlanParseError",
    "Report",
    "Resource",
    "SbomParseError",
    "Skip",
    "VacuousCheck",
    "__version__",
    "assert_enforced",
    "assert_violates",
    "check_egress",
    "check_fis_record",
    "check_fleet",
    "check_fleet_file",
    "check_iam",
    "check_kernel_protocol_set",
    "check_network",
    "check_sbom_pair",
    "diff_sboms",
    "find_repo_root",
    "live_simulation_available",
    "load_fis_record",
    "load_fleet",
    "load_sbom",
    "resolve_plane",
    "run_all_greps",
    "scan_kernel_code_boundary",
    "scan_metric_labels",
    "scan_must_not_claim",
    "scan_retry_dependencies",
    "scan_retry_imports",
    "scan_sampling_params",
    "simulate_kernel_denies",
]
