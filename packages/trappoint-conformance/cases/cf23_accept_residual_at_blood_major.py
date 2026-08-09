# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""CF-23 — an ``accept_residual`` disposition at virulence ``blood_major``.

Manifest: ``23503`` on ``fk_clearance``, ``MI11``, invariant ``I10``.

One of the three deliberately absent cells. ``(blood_major, accept_residual)`` is not a
*stricter* row in the lattice; it is **no row**, so the composite foreign key refuses it
and names itself.

The absence is versioned data with a named approver and a date, not a constant in code. A
customer who thinks residual acceptance should be available at ``blood_major`` contests it
by amending ``clearance_legal`` — an amendment with a signature on it — rather than by
opening a pull request against a function. That is the difference between a safety policy
and a code path.

Like ``CF-07``, the disposition is fully equipped: a missing lattice row projects the
strictest requirements, and every ``CHECK`` is evaluated before any foreign key, so the
case would otherwise be refused for a reason it is not about.
"""

from __future__ import annotations

from trappoint_conformance.harness import Harness, HistoryOutcome
from trappoint_conformance.runner import register
from trappoint_conformance.site import SiteScope

from ._world import Disposition, World, refusal


@register("CF-23")
def cf_23_accept_residual_at_blood_major(
    harness: Harness, scope: SiteScope, schema: str
) -> HistoryOutcome:
    """Accept the residual risk of a control a major injury wrote."""
    world = World(harness, scope, schema)
    world.site_row()
    armed = world.armed_permit(tag="cf23", max_severity=4, virulence="blood_major", signer_rank=9)
    return refusal(
        harness,
        "CF-23",
        (
            Disposition(
                check_id=armed["check_id"],
                receipt_id=armed["receipt_id"],
                signer_sub=armed["signer"],
                signer_credential_id=armed["signer_key"],
                kind="accept_residual",
                countersigner_sub=armed["countersigner"],
                countersigner_credential_id=armed["counter_key"],
                compensating_clause_uuid=world.clause_row(),
                predicate_id=world.uid("cf23:predicate"),
                reassert_by=World.soon(86400),
                expires_at=World.soon(3600),
            ).step(world, "accept the residual on a blood_major control"),
        ),
        relation="disposition",
    )
