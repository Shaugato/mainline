# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""CF-10 — materialise a blocking check against an already-merged permit.

Manifest: ``P0001`` on ``mainline.fn_check_materialised``, ``MI07``, anomaly ``A2``,
depth >= 3.

The late-arriving recall. A fatality is ingested a week after the permit issued and the
retrieval matches a clause the permit weakened; the obligation is real, and attaching it
to an issued permit would rewrite the safety argument that was signed. The declared remedy
is a **fork** — suspend the issued permit and open a child whose gate is cleared afresh —
so the attachment itself must be impossible.

**Depth 3, and it is proved by unwelding rather than asserted here.** At runtime the
deterministic ``RAISE`` fires first and this case asserts exactly that. Remove it and the
write still fails twice more: the counter increment puts ``open_blocking`` above zero on a
row whose state is ``merged`` (``23514``), and the epoch bump mutates a value pinned by
``merge_record`` under ``ON UPDATE RESTRICT`` (``23503``). ``REFUSAL_DEPTH.md`` is where
that claim is made, because it is the only place it is measured.
"""

from __future__ import annotations

from trappoint_conformance.harness import Harness, HistoryOutcome
from trappoint_conformance.runner import register
from trappoint_conformance.site import SiteScope

from ._world import World, digest32, refusal


@register("CF-10")
def cf_10_precursor_after_issue(harness: Harness, scope: SiteScope, schema: str) -> HistoryOutcome:
    """Merge the permit, then discover the precursor."""
    world = World(harness, scope, schema)
    world.site_row()
    built = world.cleared_permit(tag="cf10")
    permit_id = built["permit_id"]
    world.run(
        "merge the permit",
        "CALL {s}.merge_permit(%s, %s, %s, 'service', '{{}}'::JSONB, %s, 1::INT2, %s)",
        (permit_id, digest32("merged"), "conformance", b"\x00", digest32("leaf")),
    )
    late_clause, late_commit = world.clause_version("cf10-late")
    world.closure(late_clause, late_commit, max_severity=5, virulence="blood_fatal")
    return refusal(
        harness,
        "CF-10",
        (
            world.check_step(
                "attach a precursor to an issued permit",
                clause_uuid=late_clause,
                commit_id=late_commit,
                permit_id=permit_id,
                check_id=world.uid("cf10:late-check"),
            ),
        ),
        relation="blocking_check",
    )
