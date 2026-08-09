# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""CF-39 — UPDATE and DELETE against an append-only obligation table.

Manifest: ``P0001`` on ``mainline.fn_refuse_mutation``, ``MI01``, anomaly ``A9``,
depth >= 2.

Three independent layers, in order: **grants**, **triggers**, **RLS**. No layer is
sufficient alone and each is testable alone, which is the only arrangement in which
"defence in depth" is a statement about the system rather than about the author's
confidence.

This case tests the **trigger** layer, and it tests it as the identity that has every
privilege — the migrator — which is the point: the refusal does not depend on the writer
being under-privileged. ``CF-47`` and ``CF-48`` test the grant layer from the other end,
with a role that has no privilege at all.

Both spellings are run. A guard wired only to UPDATE leaves DELETE open, and a suite that
tested only UPDATE would never notice.
"""

from __future__ import annotations

from trappoint_conformance.harness import Harness, HistoryOutcome, Step
from trappoint_conformance.runner import register
from trappoint_conformance.site import SiteScope

from ._exhibit import normalise
from ._world import World, fail_stored, refusal


@register("CF-39")
def cf_39_append_only_obligation_table(
    harness: Harness, scope: SiteScope, schema: str
) -> HistoryOutcome:
    """Edit the chain, then delete from it."""
    world = World(harness, scope, schema)
    world.site_row()
    permit_id = world.permit("cf39")
    world.append_event(
        "genesis",
        permit_id,
        seq=1,
        prev_seq=0,
        from_state="draft",
        to_state="checks_materialised",
    )
    deletion = refusal(
        harness,
        "CF-39",
        (
            Step(
                label="delete an event from the chain",
                sql=world.sql("DELETE FROM {s}.permit_event WHERE permit_id = %s"),
                params=(permit_id,),
            ),
        ),
        relation="permit_event",
    )
    normalise(deletion, relation="permit_event")
    outcome = refusal(
        harness,
        "CF-39",
        (
            Step(
                label="edit an event in the chain",
                sql=world.sql(
                    "UPDATE {s}.permit_event SET actor_sub = 'someone else' "
                    "WHERE permit_id = %s AND seq = 1"
                ),
                params=(permit_id,),
            ),
        ),
        relation="permit_event",
    )
    outcome.stored["delete_sqlstate"] = deletion.sqlstate
    outcome.stored["delete_constraint"] = deletion.constraint
    if (deletion.sqlstate, deletion.constraint) != ("P0001", "mainline.fn_refuse_mutation"):
        return fail_stored(
            outcome,
            f"UPDATE was refused correctly, but DELETE observed {deletion.sqlstate} on "
            f"{deletion.constraint or '<none>'}. A guard wired to one verb and not the "
            f"other is not append-only; it is a speed bump on one of the two roads.",
        )
    return outcome
