# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""CF-34 — an emergency override signed at a rank below ``3 + prior_override_count``.

Manifest: ``23514`` on ``override_escalates``, ``MI29``, anomaly ``A10``.

Finding ``S8``. The ladder escalates against the **person**, across subjects, with **no
ceiling**. A rank-3 supervisor may declare one emergency; the second one they declare needs
a rank-4 signature, the third a rank-5, and there is deliberately no rung at which it stops
rising, because a ceiling is the rung at which the ladder stops meaning anything.

``prior_override_count`` is projected from ``override_ledger`` — it is a count of what this
person has already done, site-wide — so it cannot be supplied, cannot be reset per permit,
and cannot be avoided by moving to a different subject. That is the entire mechanism: a
per-subject counter would make "one override each" the operating procedure.

The first override in this case is **legal** and it is setup. It has to be: a ladder is only
observable from the second rung.
"""

from __future__ import annotations

from trappoint_conformance.harness import Harness, HistoryOutcome
from trappoint_conformance.runner import register
from trappoint_conformance.site import SiteScope

from ._world import Disposition, World, refusal


@register("CF-34")
def cf_34_override_escalates(harness: Harness, scope: SiteScope, schema: str) -> HistoryOutcome:
    """Declare a second emergency at the rank that carried the first."""
    world = World(harness, scope, schema)
    world.site_row()
    first = world.armed_permit(tag="cf34a", signer_rank=3)
    world.sign(
        Disposition(
            check_id=first["check_id"],
            receipt_id=first["receipt_id"],
            signer_sub=first["signer"],
            signer_credential_id=first["signer_key"],
            kind="emergency_override",
            countersigner_sub=first["countersigner"],
            countersigner_credential_id=first["counter_key"],
            expires_at=World.soon(6 * 3600),
        ),
        label="the first emergency, which is legal at rank 3",
    )
    # A different subject, the same person. The ladder does not reset.
    second = world.clause_version("cf34b")
    world.closure(second[0], second[1], max_severity=1, virulence="routine")
    permit_two = world.permit("cf34b")
    check_two = world.check(
        clause_uuid=second[0], commit_id=second[1], permit_id=permit_two, tag="cf34b"
    )
    receipt_two = world.receipt(actor_sub=first["signer"], permit_id=permit_two, tag="cf34b")
    world.line(receipt_two, check_two)
    outcome = refusal(
        harness,
        "CF-34",
        (
            Disposition(
                check_id=check_two,
                receipt_id=receipt_two,
                signer_sub=first["signer"],
                signer_credential_id=first["signer_key"],
                kind="emergency_override",
                countersigner_sub=first["countersigner"],
                countersigner_credential_id=first["counter_key"],
                expires_at=World.soon(6 * 3600),
            ).step(world, "declare a second emergency at the same rank"),
        ),
        relation="disposition",
    )
    outcome.stored["prior_overrides"] = world.scalar(
        "SELECT count(*) FROM {s}.override_ledger WHERE site_id = %s AND signer_sub = %s",
        (world.site_id, first["signer"]),
    )
    return outcome
