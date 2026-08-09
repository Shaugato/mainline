# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""CF-18 — a disposition against a (receipt, check) pair that was never materialised.

Manifest: ``23503`` on ``fk_exposure``, ``MI12``, invariant ``I09``.

*"It never showed me"* and *"I signed without looking"* are the two defences that survive
every incident, and they are both violations of one foreign key. The key is composite —
``(receipt_id, check_id)`` into ``exposure_line`` — and onto the **pair**, never onto the
obligation alone: a signature against a receipt that did not carry this obligation is a
signature about something the signer was not shown.

The receipt in this case is real, current and issued to this signer. What is missing is the
line: the substrate never rendered this obligation into it. That is the whole difference
between a session and evidence.
"""

from __future__ import annotations

from trappoint_conformance.harness import Harness, HistoryOutcome
from trappoint_conformance.runner import register
from trappoint_conformance.site import SiteScope

from ._world import Disposition, World, refusal


@register("CF-18")
def cf_18_unexposed_obligation(harness: Harness, scope: SiteScope, schema: str) -> HistoryOutcome:
    """Sign for an obligation the receipt never carried."""
    world = World(harness, scope, schema)
    world.site_row()
    clause_uuid, commit_id = world.clause_version("cf18")
    world.closure(clause_uuid, commit_id, max_severity=1, virulence="routine")
    permit_id = world.permit("cf18")
    signer = world.person(world.actor("signer"), rank=4)
    credential = world.credential(signer)
    check_id = world.check(clause_uuid=clause_uuid, commit_id=commit_id, permit_id=permit_id)
    receipt_id = world.receipt(actor_sub=signer, permit_id=permit_id)
    # DELIBERATELY NO world.line(receipt_id, check_id).
    return refusal(
        harness,
        "CF-18",
        (
            Disposition(
                check_id=check_id,
                receipt_id=receipt_id,
                signer_sub=signer,
                signer_credential_id=credential,
                kind="applied",
            ).step(world, "sign against an obligation that was never rendered"),
        ),
        relation="disposition",
    )
