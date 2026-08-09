# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""CF-21 — a disposition against an exposure receipt that has already expired.

Manifest: ``P0001`` on ``mainline.fn_disposition_project``, invariant ``I09``.

A receipt is a statement about what was rendered *at a moment*. Once it has expired, the
corpus behind it may have moved: a precursor may have been added, a severity revised, a
document superseded. Signing against it is signing against a screen that is no longer what
the substrate would show.

``now()`` is not immutable, so this cannot be a ``CHECK`` — a constraint may not read the
clock — and it is a trigger comparison instead. That is the same reasoning as ``CF-02``,
one table earlier.
"""

from __future__ import annotations

from trappoint_conformance.harness import Harness, HistoryOutcome
from trappoint_conformance.runner import register
from trappoint_conformance.site import SiteScope

from ._world import Disposition, World, refusal


@register("CF-21")
def cf_21_expired_receipt(harness: Harness, scope: SiteScope, schema: str) -> HistoryOutcome:
    """Sign against a receipt whose window closed a minute ago."""
    world = World(harness, scope, schema)
    world.site_row()
    armed = world.armed_permit(
        tag="cf21",
        countersigner_org=None,
        receipt_kwargs={"issued_ago_seconds": 3600, "expires_in_seconds": -60},
    )
    return refusal(
        harness,
        "CF-21",
        (
            Disposition(
                check_id=armed["check_id"],
                receipt_id=armed["receipt_id"],
                signer_sub=armed["signer"],
                signer_credential_id=armed["signer_key"],
                kind="applied",
            ).step(world, "sign against an expired exposure receipt"),
        ),
        relation="disposition",
    )
