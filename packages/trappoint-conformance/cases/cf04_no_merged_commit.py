# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""CF-04 — merge a permit with no ``merged_commit``.

Manifest: ``23514`` on ``merge_evidence``, depth >= 2.

The gate is fully closed: one obligation, one live disposition covering it, the counter at
zero and the re-derivation agreeing. Everything in the safety argument is in order, and
the write is still refused — because a completed transition that names no commit is a
completion with nothing to point at. The permit is a *ref*; a ref with no object is not a
merge, and six months later it is indistinguishable from one.
"""

from __future__ import annotations

from trappoint_conformance.harness import Harness, HistoryOutcome
from trappoint_conformance.runner import register
from trappoint_conformance.site import SiteScope

from ._world import World, refusal


@register("CF-04")
def cf_04_no_merged_commit(harness: Harness, scope: SiteScope, schema: str) -> HistoryOutcome:
    """Complete the transition without naming what was merged."""
    world = World(harness, scope, schema)
    world.site_row()
    built = world.cleared_permit(tag="cf04")
    return refusal(
        harness,
        "CF-04",
        (world.merge_step(built["permit_id"], omit_commit=True),),
        relation="permit",
    )
