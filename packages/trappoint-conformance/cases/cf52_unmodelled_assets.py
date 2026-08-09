# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""CF-52 — merge a permit whose boundary certificate reports unmodelled assets.

Manifest: ``23514`` on ``boundary_certified_when_issued``, ``MI06``, depth >= 2; profile
``mainline`` only; milestone
``K5``; ``requires = ['mainline.boundary_certificate']``.

An asset with no modelled energy edges is **UNKNOWN, not SAFE**, and unknown
blocks. The canonical multi-source-isolation fatality is electrical locked out while
trapped hydraulic pressure remains: every source anybody had modelled was dead, and the one
nobody had modelled was not.

The certificate is what turns *"we walked the boundary"* into a checkable count.

**Gated, and honestly so.** The relation this history writes is ``mainline.boundary_certificate``,
owned by the boundary milestone. Until the
capability token above is declared satisfied the runner **skips** this case with a printed
reason, and a skipped case is never counted as a passed one. That is the difference between
a suite that is honest about its coverage and one that grows green by omission.
"""

from __future__ import annotations

from trappoint_conformance.harness import Harness, HistoryOutcome
from trappoint_conformance.runner import register
from trappoint_conformance.site import SiteScope

from ._world import World, refusal


@register("CF-52")
def cf_52_unmodelled_assets(harness: Harness, scope: SiteScope, schema: str) -> HistoryOutcome:
    """Certify a boundary that contains something nobody has modelled."""
    world = World(harness, scope, schema)
    world.site_row()
    built = world.cleared_permit(tag="cf52")
    world.run(
        "certify a boundary with two unmodelled assets",
        "INSERT INTO {s}.boundary_certificate "
        "(site_id, permit_id, asset_count, unmodelled_count, certified_by) "
        "VALUES (%s, %s, 12, 2, 'conformance')",
        (world.site_id, built["permit_id"]),
    )
    return refusal(harness, "CF-52", (world.merge_step(built["permit_id"]),), relation="permit")
