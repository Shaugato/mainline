# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""CF-50 — merge a permit carrying an open fleet conflict.

Manifest: ``23514`` on ``conflicts_resolved_when_issued``, ``MI04``, depth >= 2; profile
``mainline`` only; milestone
``K7``; ``requires = ['mainline.merge_conflict']``.

A fleet of sites shares control lineage. When two sites edit the same control
in incompatible directions the conflict is a **first-class obligation on the subject**, not
a background reconciliation job, because the site merging second is the one that needs to
know.

**Gated, and honestly so.** The relation this history writes is ``mainline.merge_conflict``, which
the fleet-propagation milestone owns and which has not landed. Until the
capability token above is declared satisfied the runner **skips** this case with a printed
reason, and a skipped case is never counted as a passed one. That is the difference between
a suite that is honest about its coverage and one that grows green by omission.
"""

from __future__ import annotations

from trappoint_conformance.harness import Harness, HistoryOutcome
from trappoint_conformance.runner import register
from trappoint_conformance.site import SiteScope

from ._world import World, refusal


@register("CF-50")
def cf_50_fleet_conflict(harness: Harness, scope: SiteScope, schema: str) -> HistoryOutcome:
    """Merge while another site's version of the same control disagrees."""
    world = World(harness, scope, schema)
    world.site_row()
    built = world.cleared_permit(tag="cf50")
    world.run(
        "open a fleet conflict against the cited control",
        "INSERT INTO {s}.merge_conflict (site_id, permit_id, clause_uuid, state) "
        "VALUES (%s, %s, %s, 'open')",
        (world.site_id, built["permit_id"], built["clause_uuid"]),
    )
    return refusal(harness, "CF-50", (world.merge_step(built["permit_id"]),), relation="permit")
