# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""CF-05 — merge with an unmet reading floor and no countersignature.

Manifest: ``23514`` on ``reading_floor_when_issued``, depth >= 2.

Finding ``S19``, and the *shape* of the rule is the argument. Signing faster than the
evidence can be read is not refused. ``reading_floor_met`` is projected with positive
polarity from the server-issued receipt — ``now() - issued_at >= tau0 + tokens/rho``, with
rho deliberately generous at four tokens a second — and a breach **prices** the
consequence rather than punishing it: ``unmet_floor_count`` rises on the subject, and the
merge then requires a countersignature from a second, differently-credentialed signer.

Fast stays legal. It just names a second person. This case supplies neither the time nor
the second person, so the constraint refuses.
"""

from __future__ import annotations

from trappoint_conformance.harness import Harness, HistoryOutcome
from trappoint_conformance.runner import register
from trappoint_conformance.site import SiteScope

from ._world import Disposition, World, refusal


@register("CF-05")
def cf_05_reading_floor(harness: Harness, scope: SiteScope, schema: str) -> HistoryOutcome:
    """Sign the instant the evidence was rendered, alone."""
    world = World(harness, scope, schema)
    world.site_row()
    clause_uuid, commit_id = world.clause_version("cf05")
    world.closure(clause_uuid, commit_id, max_severity=1, virulence="routine")
    permit_id = world.permit()
    signer = world.person(world.actor("signer"), rank=4)
    credential = world.credential(signer)
    check_id = world.check(clause_uuid=clause_uuid, commit_id=commit_id, permit_id=permit_id)
    # Issued now, four thousand tokens long: the floor is a thousand seconds away and the
    # signature is about to be a millisecond old.
    receipt_id = world.receipt(
        actor_sub=signer, permit_id=permit_id, issued_ago_seconds=0, total_tokens=4000
    )
    world.line(receipt_id, check_id, tokens=4000)
    world.sign(
        Disposition(
            check_id=check_id,
            receipt_id=receipt_id,
            signer_sub=signer,
            signer_credential_id=credential,
            kind="applied",
        )
    )
    outcome = refusal(harness, "CF-05", (world.merge_step(permit_id),), relation="permit")
    outcome.stored["unmet_floor_count"] = world.scalar(
        "SELECT unmet_floor_count FROM {s}.permit WHERE permit_id = %s", (permit_id,)
    )
    outcome.stored["countersigned_count"] = world.scalar(
        "SELECT countersigned_count FROM {s}.permit WHERE permit_id = %s", (permit_id,)
    )
    return outcome
