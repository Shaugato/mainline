# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""CF-32 — a clearance kind requiring reassertion, supplied with no ``reassert_by``.

Manifest: ``23514`` on ``needs_reassert``, ``MI11``, invariants ``I10`` and ``I12``.

``(serious, mechanism_absent)`` requires a date on which the claim must be made again. A
claim about the physical world decays: the plant is modified, the crew changes, the
temporary becomes permanent. A dismissal with no reassertion date is a claim that the world
has stopped moving, which is the assumption every one of these incidents was written by.
"""

from __future__ import annotations

from trappoint_conformance.harness import Harness, HistoryOutcome
from trappoint_conformance.runner import register
from trappoint_conformance.site import SiteScope

from ._world import Disposition, World, refusal


@register("CF-32")
def cf_32_needs_reassert(harness: Harness, scope: SiteScope, schema: str) -> HistoryOutcome:
    """Dismiss a serious mechanism forever."""
    world = World(harness, scope, schema)
    world.site_row()
    armed = world.armed_permit(tag="cf32", max_severity=3, virulence="serious", signer_rank=5)
    return refusal(
        harness,
        "CF-32",
        (
            Disposition(
                check_id=armed["check_id"],
                receipt_id=armed["receipt_id"],
                signer_sub=armed["signer"],
                signer_credential_id=armed["signer_key"],
                kind="mechanism_absent",
                predicate_id=world.uid("cf32:predicate"),
            ).step(world, "declare a serious mechanism absent, permanently"),
        ),
        relation="disposition",
    )
