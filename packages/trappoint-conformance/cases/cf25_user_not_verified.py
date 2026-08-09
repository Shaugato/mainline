# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""CF-25 — a disposition recorded with ``user_verified = false``.

Manifest: ``23514`` on ``uv_required``, invariant ``I09``.

The difference between *a token was present* and *a person authenticated*. WebAuthn's
``UV`` flag is the assertion that the authenticator verified the human — a PIN, a
biometric — rather than merely that it was plugged in. A signature without it is a
signature by whoever had the key, which is precisely the fact a shared drawer makes
uninteresting.

The constraint is a plain column ``CHECK`` and it is unconditional. There is no
configuration that relaxes it, because the population that would relax it is the
population that leaves the key in the drawer.
"""

from __future__ import annotations

from trappoint_conformance.harness import Harness, HistoryOutcome
from trappoint_conformance.runner import register
from trappoint_conformance.site import SiteScope

from ._world import Disposition, World, refusal


@register("CF-25")
def cf_25_user_not_verified(harness: Harness, scope: SiteScope, schema: str) -> HistoryOutcome:
    """Record a signature the authenticator never verified a human for."""
    world = World(harness, scope, schema)
    world.site_row()
    armed = world.armed_permit(tag="cf25", countersigner_org=None)
    return refusal(
        harness,
        "CF-25",
        (
            Disposition(
                check_id=armed["check_id"],
                receipt_id=armed["receipt_id"],
                signer_sub=armed["signer"],
                signer_credential_id=armed["signer_key"],
                kind="applied",
                user_verified=False,
            ).step(world, "sign without user verification"),
        ),
        relation="disposition",
    )
