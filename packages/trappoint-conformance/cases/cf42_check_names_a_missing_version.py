# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""CF-42 — a blocking check against a clause version that does not exist.

Manifest: ``23503`` on ``fk_check_version``, anomaly ``A5``.

Why the foreign key is onto the **pair** ``(clause_uuid, commit_id)`` and not onto the
clause: a new version of a clause is a *different* foreign-key target, so it materialises a
new obligation with a new ``check_id``, and the disposition signed against the old one
cannot reach it. Carrying a clearance forward across an edit is not forbidden by policy
here — it is unrepresentable.

**Read the observed exhibit before believing this case.** ``fn_check_project`` is a
``BEFORE INSERT`` trigger that reads the blame closure for the same pair and raises
``P0001`` when it finds nothing, and a closure row cannot exist for a clause version that
does not exist, because ``fk_closure_version`` says so. The projection therefore *pre-empts*
the foreign key on every history that reaches this constraint, and the corpus does not
paper over that: the case is written exactly as the manifest describes it, and if the
observation is ``P0001`` on ``mainline.fn_check_project`` then the manifest and the DDL
disagree about which mechanism owns this refusal.

That is not a defect in the gate — the write is refused either way, which is what matters
in the field — but it is a defect in the *exhibit*, and the exhibit is the deliverable.
``unweld/`` resolves it constructively: with ``trg_check_project`` disabled, the identical
history is refused by ``fk_check_version``, so the foreign key is proved live and this
history is proved depth 2.
"""

from __future__ import annotations

import uuid

from trappoint_conformance.harness import Harness, HistoryOutcome
from trappoint_conformance.runner import register
from trappoint_conformance.site import SiteScope

from ._world import World, digest32, refusal


@register("CF-42")
def cf_42_check_names_a_missing_version(
    harness: Harness, scope: SiteScope, schema: str
) -> HistoryOutcome:
    """Materialise an obligation against a clause version nobody ever wrote."""
    world = World(harness, scope, schema)
    world.site_row()
    permit_id = world.permit("cf42")
    ghost_clause = uuid.uuid5(world.site_id, "cf42:ghost-clause")
    ghost_commit = digest32("cf42:ghost-commit")
    return refusal(
        harness,
        "CF-42",
        (
            world.check_step(
                "materialise against a clause version that does not exist",
                clause_uuid=ghost_clause,
                commit_id=ghost_commit,
                permit_id=permit_id,
                check_id=world.uid("cf42:check"),
            ),
        ),
        relation="blocking_check",
    )
