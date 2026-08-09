# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""CF-66 — a carried disposition whose expiry exceeds its declared window.

Manifest: ``23514`` on ``carried_bounded``, ``MI28``, invariant ``I12``; profile ``mainline`` only;
milestone
``K5``; ``requires = ['mainline.carried_disposition']``.

``MI28`` on a second table, and the **name is different on purpose**. Spec rule
``R-3``: the constraint name alone must identify the refusal without a qualifying table, so
``bounded`` on two tables would make the exhibit ambiguous in exactly the document where
ambiguity is expensive. ``ttl_enforced`` on ``disposition``, ``carried_bounded`` here.

**Gated, and honestly so.** The relation this history writes is ``mainline.carried_disposition``,
owned by the permit-lifecycle milestone. Until the
capability token above is declared satisfied the runner **skips** this case with a printed
reason, and a skipped case is never counted as a passed one. That is the difference between
a suite that is honest about its coverage and one that grows green by omission.
"""

from __future__ import annotations

from trappoint_conformance.harness import Harness, HistoryOutcome, Step
from trappoint_conformance.runner import register
from trappoint_conformance.site import SiteScope

from ._world import World, refusal


@register("CF-66")
def cf_66_carried_bounded(harness: Harness, scope: SiteScope, schema: str) -> HistoryOutcome:
    """Carry a verdict forward for longer than the carry allows."""
    world = World(harness, scope, schema)
    world.site_row()
    built = world.cleared_permit(tag="cf66")
    return refusal(
        harness,
        "CF-66",
        (
            Step(
                label="carry a verdict past its window",
                sql=world.sql(
                    "INSERT INTO {s}.carried_disposition "
                    "(site_id, permit_id, disposition_id, window_hours, expires_at) "
                    "VALUES (%s, %s, %s, 24, now() + INTERVAL '400 days')"
                ),
                params=(world.site_id, built["permit_id"], built["disposition_id"]),
            ),
        ),
        relation="carried_disposition",
    )
