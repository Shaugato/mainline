# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""CF-24 — a disposition with a rationale shorter than the substantive floor.

Manifest: ``23514`` on ``substantive``, anomaly ``A14``; profile ``mainline`` only.

**Vertical policy, not a kernel property**, and the corpus is careful to say so: the floor
is a number the customer signs, one hundred and twenty characters in this binding, and a
different vertical may choose differently without ceasing to be TRAPPOINT-compliant. That
is why the case does not run on the reference profile.

It is also the case that must never be over-claimed. ``A14`` — the rubber stamp — **cannot
be retired** by a character count, by a dwell timer, or by anything else in this schema. A
long rationale is not a considered one. What the constraint buys is that the box cannot be
left effectively empty, and what the substrate buys is that the text is dated, attributed
and immutable. The rest is a human problem and the corpus does not pretend otherwise.
"""

from __future__ import annotations

from trappoint_conformance.harness import Harness, HistoryOutcome
from trappoint_conformance.runner import register
from trappoint_conformance.site import SiteScope

from ._world import Disposition, World, refusal


@register("CF-24")
def cf_24_rationale_floor(harness: Harness, scope: SiteScope, schema: str) -> HistoryOutcome:
    """Sign with the shortest thing anyone actually types."""
    world = World(harness, scope, schema)
    world.site_row()
    armed = world.armed_permit(tag="cf24", countersigner_org=None)
    return refusal(
        harness,
        "CF-24",
        (
            Disposition(
                check_id=armed["check_id"],
                receipt_id=armed["receipt_id"],
                signer_sub=armed["signer"],
                signer_credential_id=armed["signer_key"],
                kind="applied",
                rationale="ok, reviewed",
            ).step(world, "sign with a two-word rationale"),
        ),
        relation="disposition",
    )
