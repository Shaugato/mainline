# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""CF-20 — a disposition signed by a subject with no ``person`` row.

Manifest: ``P0001`` on ``mainline.fn_disposition_project``, ``MI27``.

Fail closed on identity. A missing competency record is not a competency of unknown value
and it is certainly not a competency of zero cost: it is the state in which the substrate
cannot say who signed, and the only safe reading of that is refusal.

The credential exists and is enrolled, which is the point. Holding a key is not the same as
being a person the organisation has a competency record for, and the two are separable
exactly when it matters — a contractor's token that outlived their engagement.
"""

from __future__ import annotations

from trappoint_conformance.harness import Harness, HistoryOutcome
from trappoint_conformance.runner import register
from trappoint_conformance.site import SiteScope

from ._world import Disposition, World, refusal


@register("CF-20")
def cf_20_no_person_row(harness: Harness, scope: SiteScope, schema: str) -> HistoryOutcome:
    """Sign with a credential whose holder has no competency record."""
    world = World(harness, scope, schema)
    world.site_row()
    armed = world.armed_permit(tag="cf20", countersigner_org=None)
    ghost = world.actor("ghost")
    ghost_key = world.credential(ghost, tag="ghost")  # enrolled, but no person row
    return refusal(
        harness,
        "CF-20",
        (
            Disposition(
                check_id=armed["check_id"],
                receipt_id=armed["receipt_id"],
                signer_sub=ghost,
                signer_credential_id=ghost_key,
                kind="applied",
            ).step(world, "sign as somebody the competency record has never heard of"),
        ),
        relation="disposition",
    )
