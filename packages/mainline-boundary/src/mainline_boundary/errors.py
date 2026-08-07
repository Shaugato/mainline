# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""Exceptions raised by the boundary checkers.

Every one of them means *the check could not be performed*, which is a different
outcome from *the check failed* and a very different outcome from *the check
passed*. A boundary assertion that cannot be performed must never be reported as
a pass; :class:`VacuousCheck` exists so that "we examined nothing" is a loud,
typed event rather than a green tick.
"""

from __future__ import annotations


class BoundaryError(Exception):
    """Base class for every error raised by ``mainline_boundary``."""


class VacuousCheck(BoundaryError):  # noqa: N818 - the noun IS the diagnosis
    """A check completed with zero subjects examined and no recorded reason.

    This is a failure, not a pass. The whole point of the determinism boundary is
    that its assertions are falsifiable; an assertion whose subject set is empty
    asserts nothing at all.
    """


class PlanParseError(BoundaryError):
    """The OpenTofu/Terraform plan JSON is not a shape we can reason about."""


class FleetParseError(BoundaryError):
    """``spec/agents/fleet.yaml`` is not a shape we can reason about."""


class SbomParseError(BoundaryError):
    """An SBOM document is neither CycloneDX nor SPDX in a recognised version."""
