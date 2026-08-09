# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""CF-38 — UPDATE a disposition column other than ``retracted_by``.

Manifest: ``P0001`` on ``mainline.fn_disposition_retract_only``, ``MI01``, invariant ``I01``.

``retracted_by`` is the **single** permitted UPDATE in the operational zone, and only from
NULL. Everything else about a signature is frozen at the moment it was made, because a
signature that can be edited afterwards is a signature about the present rather than about
the moment it claims.

The guard compares the whole row minus the one permitted column, as data
(``to_jsonb(NEW) - 'retracted_by'``). That is exhaustive by construction: a column added by
a future migration is covered the day it is added, with no list for anybody to forget to
update.
"""

from __future__ import annotations

from trappoint_conformance.harness import Harness, HistoryOutcome, Step
from trappoint_conformance.runner import register
from trappoint_conformance.site import SiteScope

from ._world import World, long_rationale, refusal


@register("CF-38")
def cf_38_disposition_is_append_only(
    harness: Harness, scope: SiteScope, schema: str
) -> HistoryOutcome:
    """Improve the rationale after the fact."""
    world = World(harness, scope, schema)
    world.site_row()
    built = world.cleared_permit(tag="cf38")
    return refusal(
        harness,
        "CF-38",
        (
            Step(
                label="rewrite the rationale of a filed signature",
                sql=world.sql(
                    "UPDATE {s}.disposition SET rationale = %s WHERE disposition_id = %s"
                ),
                params=(long_rationale("Revised on reflection."), built["disposition_id"]),
            ),
        ),
        relation="disposition",
    )
