# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""CF-09 — merge the same subject twice.

Manifest: ``23505`` on ``merge_record_pkey``, ``MI09``, anomaly ``A4``, depth >= 2.

The completion record — not the procedure — is the merge. ``PRIMARY KEY (subject_kind,
subject_id)`` on ``merge_record`` is deliberately left unnamed in the DDL so CockroachDB
derives ``merge_record_pkey``, and that derived name is the exhibit this case and ``CF-44``
both fix.

The second completion is written **straight at the table**, not through a second ``CALL``,
and that is the stronger test. A second ``CALL`` would be refused earlier, by ``legal_edge``
on the event chain, and would prove only that the procedure guards itself. Refusing the
direct insert proves the subject cannot be completed twice by *any* writer — including one
that skips the procedure entirely, which is exactly the writer a gate has to survive.
"""

from __future__ import annotations

from trappoint_conformance.harness import Harness, HistoryOutcome, Step
from trappoint_conformance.runner import register
from trappoint_conformance.site import SiteScope

from ._world import World, digest32, refusal


@register("CF-09")
def cf_09_double_merge(harness: Harness, scope: SiteScope, schema: str) -> HistoryOutcome:
    """Complete a permit, then write a second completion record for it."""
    world = World(harness, scope, schema)
    world.site_row()
    built = world.cleared_permit(tag="cf09")
    permit_id = built["permit_id"]
    world.run(
        "merge it once, legally",
        "CALL {s}.merge_permit(%s, %s, %s, 'service', '{{}}'::JSONB, %s, 1::INT2, %s)",
        (permit_id, digest32("merged"), "conformance", b"\x00", digest32("leaf")),
    )
    epoch = world.scalar(
        "SELECT gate_epoch FROM {s}.merge_record WHERE subject_id = %s", (permit_id,)
    )
    outcome = refusal(
        harness,
        "CF-09",
        (
            Step(
                label="write a second completion record for the same subject",
                sql=world.sql(
                    "INSERT INTO {s}.merge_record "
                    "(subject_kind, subject_id, permit_id, gate_epoch, merged_by, "
                    " merged_commit, clearance_digest) "
                    "VALUES ('permit', %s, %s, %s, 'conformance-second', %s, %s)"
                ),
                params=(permit_id, permit_id, epoch, digest32("merged"), digest32("clr")),
            ),
        ),
        relation="merge_record",
    )
    outcome.stored["merge_record_count"] = world.scalar(
        "SELECT count(*) FROM {s}.merge_record WHERE subject_id = %s", (permit_id,)
    )
    return outcome
