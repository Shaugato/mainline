# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""CF-27 — a clearance kind requiring a second signer, supplied without one.

Manifest: ``23514`` on ``needs_second_signer``, ``MI11``, invariant ``I10``.

``(routine, escalated)`` carries ``req_second_signer``. Escalation is the verdict that says
*this is above my authority*, and a verdict about authority signed by one person is the
thing it claims not to be.

The requirement is **projected** from ``clearance_legal`` rather than supplied, which is
what stops the signer choosing the lattice row that judges their own signature.
"""

from __future__ import annotations

from trappoint_conformance.harness import Harness, HistoryOutcome
from trappoint_conformance.runner import register
from trappoint_conformance.site import SiteScope

from ._world import Disposition, World, refusal


@register("CF-27")
def cf_27_needs_second_signer(harness: Harness, scope: SiteScope, schema: str) -> HistoryOutcome:
    """Escalate alone."""
    world = World(harness, scope, schema)
    world.site_row()
    armed = world.armed_permit(tag="cf27", countersigner_org=None)
    return refusal(
        harness,
        "CF-27",
        (
            Disposition(
                check_id=armed["check_id"],
                receipt_id=armed["receipt_id"],
                signer_sub=armed["signer"],
                signer_credential_id=armed["signer_key"],
                kind="escalated",
            ).step(world, "escalate with no second signer"),
        ),
        relation="disposition",
    )
