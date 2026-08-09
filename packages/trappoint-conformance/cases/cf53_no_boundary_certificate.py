# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""CF-53 — merge a permit with no boundary certificate at all.

Manifest: ``P0001`` on ``mainline.fn_permit_merge_gate``, ``MI06``, depth >= 2; profile ``mainline``
only; milestone
``K5``; ``requires = ['mainline.boundary_certificate']``.

The counterpart to ``CF-52`` and the more dangerous of the two. A certificate
reporting two unmodelled assets is refused by a counter; **no certificate at all** is
refused by the gate reading its own authority source and finding nothing. Same asymmetry as
``CF-06``: the missing case is the one with physical consequences, so it must not be the
one that admits.

**Gated, and honestly so.** The relation this history writes is ``mainline.boundary_certificate``,
and this case's gate arm is rendered only for the MAINLINE binding — the reference vertical's
``fn_permit_merge_gate`` carries a committed comment where this arm would be, because procedures
bind early on v26.2 and naming an absent relation would make the migration un-appliable rather than
degrade it (ruling D5). Until the
capability token above is declared satisfied the runner **skips** this case with a printed
reason, and a skipped case is never counted as a passed one. That is the difference between
a suite that is honest about its coverage and one that grows green by omission.
"""

from __future__ import annotations

from trappoint_conformance.harness import Harness, HistoryOutcome
from trappoint_conformance.runner import register
from trappoint_conformance.site import SiteScope

from ._world import World, refusal


@register("CF-53")
def cf_53_no_boundary_certificate(
    harness: Harness, scope: SiteScope, schema: str
) -> HistoryOutcome:
    """Merge without walking the boundary at all."""
    world = World(harness, scope, schema)
    world.site_row()
    built = world.cleared_permit(tag="cf53")
    # DELIBERATELY NO boundary certificate.
    return refusal(harness, "CF-53", (world.merge_step(built["permit_id"]),), relation="permit")
