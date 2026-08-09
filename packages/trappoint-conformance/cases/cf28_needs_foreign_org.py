# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""CF-28 — a clearance kind requiring a foreign-org countersigner, countersigned in-house.

Manifest: ``23514`` on ``needs_foreign_org``, ``MI11``, invariant ``I10``.

``(blood_major, mechanism_absent)`` requires the countersigner to be outside the signer's
organisation. Saying *the mechanism that killed someone cannot occur here* is the claim
most exposed to the pressure that produced the permit in the first place, and an
independent organisation is the cheapest available structural check on it.

The comparison is between two **projected** organisation strings. If either came from the
party the requirement constrains, the requirement is a formality — which is why
``fn_disposition_project`` reads the countersigner's org from ``person`` and not from the
row being written.
"""

from __future__ import annotations

from trappoint_conformance.harness import Harness, HistoryOutcome
from trappoint_conformance.runner import register
from trappoint_conformance.site import SiteScope

from ._world import Disposition, World, refusal


@register("CF-28")
def cf_28_needs_foreign_org(harness: Harness, scope: SiteScope, schema: str) -> HistoryOutcome:
    """Countersign a fatality-class dismissal from the same organisation."""
    world = World(harness, scope, schema)
    world.site_row()
    armed = world.armed_permit(
        tag="cf28",
        max_severity=4,
        virulence="blood_major",
        signer_rank=9,
        signer_org="alpha-operations",
        countersigner_org="alpha-operations",
    )
    return refusal(
        harness,
        "CF-28",
        (
            Disposition(
                check_id=armed["check_id"],
                receipt_id=armed["receipt_id"],
                signer_sub=armed["signer"],
                signer_credential_id=armed["signer_key"],
                kind="mechanism_absent",
                countersigner_sub=armed["countersigner"],
                countersigner_credential_id=armed["counter_key"],
                predicate_id=world.uid("cf28:predicate"),
                reassert_by=World.soon(86400),
            ).step(world, "countersign inside the same organisation"),
        ),
        relation="disposition",
    )
