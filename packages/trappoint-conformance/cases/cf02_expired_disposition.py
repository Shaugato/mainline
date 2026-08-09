# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""CF-02 — merge a permit whose only disposition expired before the merge.

Manifest: ``P0001`` on ``mainline.fn_permit_merge_gate``, anomaly ``A11``, depth >= 2.

``now()`` is not immutable, so no ``CHECK`` can hold this: a constraint sees only the row
being written and cannot ask what the clock says about a different table. The projected
counter reads zero — the disposition really was filed, and ``fn_disposition_close`` really
did decrement it — while the re-derivation inside the gate, which carries the time
condition ``expires_at > now()``, counts one. Disagreement between the projection and the
re-derivation is the definition of drift, and drift refuses.

That is why ``P0001`` is legitimate here rather than a lazy substitute for a constraint
(``spec/errors.md`` §2.5 case 1), and it is the whole of rule ``P2``: *projections are
enforced, never trusted*.
"""

from __future__ import annotations

from trappoint_conformance.harness import Harness, HistoryOutcome
from trappoint_conformance.runner import register
from trappoint_conformance.site import SiteScope

from ._world import Disposition, World, refusal


@register("CF-02")
def cf_02_expired_disposition(harness: Harness, scope: SiteScope, schema: str) -> HistoryOutcome:
    """Sign a verdict that has already expired, then attempt the merge."""
    world = World(harness, scope, schema)
    world.site_row()
    clause_uuid, commit_id = world.clause_version("cf02")
    world.closure(clause_uuid, commit_id, max_severity=1, virulence="routine")
    permit_id = world.permit()
    signer = world.person(world.actor("signer"), rank=4)
    credential = world.credential(signer)
    check_id = world.check(clause_uuid=clause_uuid, commit_id=commit_id, permit_id=permit_id)
    receipt_id = world.receipt(actor_sub=signer, permit_id=permit_id)
    world.line(receipt_id, check_id)
    # `applied` at `routine` carries no max_ttl_hours, so `ttl_enforced` does not object to
    # a window that has already closed. The gate does, which is the point: the constraint
    # bounds the window, and the gate is what reads the clock.
    world.sign(
        Disposition(
            check_id=check_id,
            receipt_id=receipt_id,
            signer_sub=signer,
            signer_credential_id=credential,
            kind="applied",
            expires_at=World.past(600),
        )
    )
    outcome = refusal(harness, "CF-02", (world.merge_step(permit_id),), relation="permit")
    outcome.stored["projected_open_blocking"] = world.scalar(
        "SELECT open_blocking FROM {s}.permit WHERE permit_id = %s", (permit_id,)
    )
    return outcome
