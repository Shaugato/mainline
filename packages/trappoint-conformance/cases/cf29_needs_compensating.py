# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""CF-29 — a clearance kind requiring a compensating control, supplied without one.

Manifest: ``23514`` on ``needs_compensating``, ``MI11``, invariant ``I10``.

``(routine, mitigated)`` requires a compensating clause. *Mitigated* is a claim that
something else is carrying the risk; a mitigation that names nothing is a claim with no
object, and it is the single most common way a control disappears without anyone deciding
to remove it.

The column is a foreign key to a clause, not free text, so the mitigation is a **thing in
the corpus** that can itself be recalled, superseded and blamed.
"""

from __future__ import annotations

from trappoint_conformance.harness import Harness, HistoryOutcome
from trappoint_conformance.runner import register
from trappoint_conformance.site import SiteScope

from ._world import Disposition, World, refusal


@register("CF-29")
def cf_29_needs_compensating(harness: Harness, scope: SiteScope, schema: str) -> HistoryOutcome:
    """Mitigate with nothing."""
    world = World(harness, scope, schema)
    world.site_row()
    armed = world.armed_permit(tag="cf29", countersigner_org=None)
    return refusal(
        harness,
        "CF-29",
        (
            Disposition(
                check_id=armed["check_id"],
                receipt_id=armed["receipt_id"],
                signer_sub=armed["signer"],
                signer_credential_id=armed["signer_key"],
                kind="mitigated",
            ).step(world, "claim a mitigation that names no control"),
        ),
        relation="disposition",
    )
