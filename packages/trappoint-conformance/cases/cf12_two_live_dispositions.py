# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""CF-12 — two live dispositions against one blocking check.

Manifest: ``23505`` on ``one_live_disposition``, ``MI08``, anomaly ``A6``.

An obligation is cleared once. Two live verdicts on one obligation is not a redundancy, it
is an ambiguity: the gate's re-derivation asks whether *a* live disposition covers the
check, so a second one changes nothing about the count and everything about which
signature is the one that answered for it.

The mechanism is a partial unique index — ``UNIQUE (check_id) WHERE retracted_by IS
NULL`` — which is the shape that permits the legal sequence (retract, then re-sign) while
refusing the illegal one (sign twice). Verified available on this platform: partial unique
indexes are ``PASS`` on v26.2.5.
"""

from __future__ import annotations

from trappoint_conformance.harness import Harness, HistoryOutcome
from trappoint_conformance.runner import register
from trappoint_conformance.site import SiteScope

from ._world import Disposition, World, refusal


@register("CF-12")
def cf_12_two_live_dispositions(harness: Harness, scope: SiteScope, schema: str) -> HistoryOutcome:
    """Sign the same obligation twice without retracting the first verdict."""
    world = World(harness, scope, schema)
    world.site_row()
    built = world.cleared_permit(tag="cf12")
    second_signer = world.person(world.actor("second"), rank=4)
    second_key = world.credential(second_signer, tag="second")
    receipt_id = world.receipt(
        actor_sub=second_signer, permit_id=built["permit_id"], tag="cf12-second"
    )
    world.line(receipt_id, built["check_id"])
    return refusal(
        harness,
        "CF-12",
        (
            Disposition(
                disposition_id=world.uid("cf12:second-disposition"),
                check_id=built["check_id"],
                receipt_id=receipt_id,
                signer_sub=second_signer,
                signer_credential_id=second_key,
                kind="applied",
            ).step(world, "file a second live verdict on the same obligation"),
        ),
        relation="disposition",
    )
