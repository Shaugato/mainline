# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""CF-26 — a countersignature made with the signer's own credential.

Manifest: ``23514`` on ``distinct_credential``, invariant ``I09``.

Refuses the shared-tablet defeat. A countersignature exists to put a second, independent
person on the record; a second signature from the same key puts the same person on the
record twice and satisfies every count while defeating the purpose of all of them.

The constraint is on the **credential**, not on the subject identifier, and the choice
matters: two accounts on one authenticator is the cheap way round a rule written against
names. ``needs_second_signer`` in ``CF-27`` is the other half — it requires the
countersigner to be a different *person* — and the two together are what "a second pair of
eyes" has to mean in a schema.
"""

from __future__ import annotations

from trappoint_conformance.harness import Harness, HistoryOutcome
from trappoint_conformance.runner import register
from trappoint_conformance.site import SiteScope

from ._world import Disposition, World, refusal


@register("CF-26")
def cf_26_countersigned_with_own_key(
    harness: Harness, scope: SiteScope, schema: str
) -> HistoryOutcome:
    """Countersign with the key that already signed."""
    world = World(harness, scope, schema)
    world.site_row()
    armed = world.armed_permit(tag="cf26")
    return refusal(
        harness,
        "CF-26",
        (
            Disposition(
                check_id=armed["check_id"],
                receipt_id=armed["receipt_id"],
                signer_sub=armed["signer"],
                signer_credential_id=armed["signer_key"],
                kind="applied",
                countersigner_sub=armed["countersigner"],
                countersigner_credential_id=armed["signer_key"],
            ).step(world, "countersign with the signer's own credential"),
        ),
        relation="disposition",
    )
