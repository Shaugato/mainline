# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""CF-33 — a disposition whose ``expires_at`` exceeds ``signed_at`` plus ``max_ttl_hours``.

Manifest: ``23514`` on ``ttl_enforced``, ``MI28``, invariant ``I12``.

**A bounded window means BOUNDED, not merely present.** Finding ``S12``: a constraint that
said only ``expires_at IS NOT NULL`` would admit a verdict expiring in the year 3000 and
would read, in every report and every audit, as an expiry control.

``(routine, accept_residual)`` carries six months. This case asks for a year and is refused
by arithmetic the signer does not get to supply: ``max_ttl_hours`` is projected from the
lattice, ``signed_at`` defaults to the server clock.
"""

from __future__ import annotations

from trappoint_conformance.harness import Harness, HistoryOutcome
from trappoint_conformance.runner import register
from trappoint_conformance.site import SiteScope

from ._world import Disposition, World, refusal


@register("CF-33")
def cf_33_ttl_enforced(harness: Harness, scope: SiteScope, schema: str) -> HistoryOutcome:
    """Accept a residual for twice as long as the lattice allows."""
    world = World(harness, scope, schema)
    world.site_row()
    armed = world.armed_permit(tag="cf33", countersigner_org=None, signer_rank=4)
    return refusal(
        harness,
        "CF-33",
        (
            Disposition(
                check_id=armed["check_id"],
                receipt_id=armed["receipt_id"],
                signer_sub=armed["signer"],
                signer_credential_id=armed["signer_key"],
                kind="accept_residual",
                expires_at=World.soon(365 * 24 * 3600),
            ).step(world, "set an expiry a year out against a six-month ceiling"),
        ),
        relation="disposition",
    )
