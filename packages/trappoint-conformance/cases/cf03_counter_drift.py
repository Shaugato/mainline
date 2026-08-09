# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""CF-03 — merge a permit whose ``open_blocking`` was forced to zero out of band.

Manifest: ``P0001`` on ``mainline.fn_permit_merge_gate``, anomaly ``A8``, depth >= 2.

The attack a counter invites: write the counter, not the fact. ``UPDATE permit SET
open_blocking = 0`` is one statement, nothing on the permit row refuses it, and afterwards
the ``CHECK`` the whole product rests on is satisfied by a lie.

It does not work, because the projection is **enforced, never trusted**. The gate
re-derives the count from ``blocking_check`` anti-joined against live dispositions and
refuses on disagreement. The obligation is still there; only the bookkeeping was edited,
and the bookkeeping is not what the gate reads last.

``A8`` is *detection, not prevention*, and this case says only that. The forgery is setup:
a case asserting the UPDATE itself was refused would be asserting a guarantee the
architecture explicitly declines to make.
"""

from __future__ import annotations

from trappoint_conformance.harness import Harness, HistoryOutcome
from trappoint_conformance.runner import register
from trappoint_conformance.site import SiteScope

from ._world import World, refusal


@register("CF-03")
def cf_03_counter_drift(harness: Harness, scope: SiteScope, schema: str) -> HistoryOutcome:
    """Falsify the counter out of band, then merge behind it."""
    world = World(harness, scope, schema)
    world.site_row()
    clause_uuid, commit_id = world.clause_version("cf03")
    world.closure(clause_uuid, commit_id, max_severity=5, virulence="blood_fatal")
    permit_id = world.permit()
    world.check(clause_uuid=clause_uuid, commit_id=commit_id, permit_id=permit_id)
    world.run(
        "force the counter to zero",
        "UPDATE {s}.permit SET open_blocking = 0 WHERE permit_id = %s",
        (permit_id,),
    )
    outcome = refusal(harness, "CF-03", (world.merge_step(permit_id),), relation="permit")
    outcome.stored["projected_open_blocking"] = world.scalar(
        "SELECT open_blocking FROM {s}.permit WHERE permit_id = %s", (permit_id,)
    )
    outcome.stored["derived_open_blocking"] = world.scalar(
        "SELECT count(*) FROM {s}.blocking_check WHERE permit_id = %s", (permit_id,)
    )
    return outcome
