# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""CF-06 — merge a permit citing a clause for which the authority source holds no row.

Manifest: ``P0001`` on ``mainline.fn_permit_merge_gate``, ``MI22``, depth >= 2.

**Fail closed.** The original bug — the one worth writing a substrate over — was the
asymmetry the other way: a *stale* blame closure refused the merge while a *missing* one
admitted it, so the most effective thing a caller could do to get a permit through was to
delete the evidence that it was dangerous.

Absence of evidence is not evidence of absence, and here it is not a default either. The
gate counts cited clause versions with no row in the declared authority relation and
refuses on any. Nothing about this permit's obligations is wrong; there is simply no basis
on which to say they are right.
"""

from __future__ import annotations

from trappoint_conformance.harness import Harness, HistoryOutcome
from trappoint_conformance.runner import register
from trappoint_conformance.site import SiteScope

from ._world import World, refusal


@register("CF-06")
def cf_06_absent_authority(harness: Harness, scope: SiteScope, schema: str) -> HistoryOutcome:
    """Cite a clause version whose blame closure has never been computed."""
    world = World(harness, scope, schema)
    world.site_row()
    clause_uuid, commit_id = world.clause_version("cf06")
    # DELIBERATELY NO world.closure(...). The clause version exists; what it inherited does
    # not. No obligation can be materialised against it either — fn_check_project raises
    # for the same reason — and the gate must not read that silence as safety.
    permit_id = world.permit()
    world.cite(permit_id, clause_uuid, commit_id, relation="weakens")
    return refusal(harness, "CF-06", (world.merge_step(permit_id),), relation="permit")
