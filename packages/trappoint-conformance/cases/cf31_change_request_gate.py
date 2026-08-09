# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""CF-31 — merge a ``change_request`` carrying an undispositioned ``weaken_over_blood`` check.

Manifest: ``23514`` on ``cr_gate_closed_when_merged``, ``MI30``, depth >= 2.

The named case that makes the thesis *"the **repository** is a protected branch and the
permit is one of its refs"* rather than *"the permit is a protected branch"*. Without it,
the whole product is a workflow tool for one document type; with it, the same gate stands
in front of every change to the corpus the permits are written against.

``weaken_over_blood`` is the origin that matters here: a change request that softens a
clause whose blame closure holds a fatality. The obligation is materialised against the
change request exactly as it would be against a permit — ``blocking_check`` is
subject-polymorphic — and the mirrored constraint on ``change_request`` refuses the merge
with its own name, because ``cr_gate_closed_when_merged`` and ``gate_closed_when_issued``
must be distinguishable as exhibits.
"""

from __future__ import annotations

from trappoint_conformance.harness import Harness, HistoryOutcome
from trappoint_conformance.runner import register
from trappoint_conformance.site import SiteScope

from ._world import World, refusal


@register("CF-31")
def cf_31_change_request_gate(harness: Harness, scope: SiteScope, schema: str) -> HistoryOutcome:
    """Weaken a clause a death wrote, and try to land the edit."""
    world = World(harness, scope, schema)
    world.site_row()
    clause_uuid, commit_id = world.clause_version("cf31", control_delta="weaken")
    world.closure(clause_uuid, commit_id, max_severity=5, virulence="blood_fatal")
    cr_id = world.change_request("cf31")
    world.cite_cr(cr_id, clause_uuid, commit_id, relation="edits")
    world.check(
        clause_uuid=clause_uuid,
        commit_id=commit_id,
        cr_id=cr_id,
        origin="weaken_over_blood",
        tag="cf31",
    )
    outcome = refusal(harness, "CF-31", (world.merge_cr_step(cr_id),), relation="change_request")
    outcome.stored["open_blocking"] = world.scalar(
        "SELECT open_blocking FROM {s}.change_request WHERE cr_id = %s", (cr_id,)
    )
    return outcome
