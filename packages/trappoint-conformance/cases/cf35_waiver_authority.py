# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""CF-35 — a waiver at ``blood_fatal`` by a signer whose frozen competency lacks the authorisation.

Manifest: ``23514`` on ``waiver_authority``; profile ``mainline`` only; milestone ``K5``;
``requires = ["mainline.person"]``.

Authority to waive derives from a **frozen** competency snapshot and fails closed. Not a
live join to an HR system: a live join returns *today's* competency at trial, which is
useless as evidence and looks exactly like backfilling. The snapshot supports a provable
claim — at 02:14 on 14 March the system checked, the record said this, and here is the hash
of the source record.

This one is not a reference-profile case because the competency vocabulary is the
vertical's. ``ISOLATION_AUTHORITY`` means something in a mining and heavy-industry binding
and nothing in a substrate that has never heard of stored energy.
"""

from __future__ import annotations

from trappoint_conformance.harness import Harness, HistoryOutcome
from trappoint_conformance.runner import register
from trappoint_conformance.site import SiteScope

from ._world import Disposition, World, refusal


@register("CF-35")
def cf_35_waiver_authority(harness: Harness, scope: SiteScope, schema: str) -> HistoryOutcome:
    """Waive a fatality-written control without the authorisation to do it."""
    world = World(harness, scope, schema)
    world.site_row()
    armed = world.armed_permit(
        tag="cf35",
        max_severity=5,
        virulence="blood_fatal",
        signer_rank=9,
        authorisations=("PERMIT_ISSUE",),
    )
    return refusal(
        harness,
        "CF-35",
        (
            Disposition(
                check_id=armed["check_id"],
                receipt_id=armed["receipt_id"],
                signer_sub=armed["signer"],
                signer_credential_id=armed["signer_key"],
                kind="mitigated",
                countersigner_sub=armed["countersigner"],
                countersigner_credential_id=armed["counter_key"],
                compensating_clause_uuid=world.clause_row(),
            ).step(world, "waive without ISOLATION_AUTHORITY in the frozen snapshot"),
        ),
        relation="disposition",
    )
