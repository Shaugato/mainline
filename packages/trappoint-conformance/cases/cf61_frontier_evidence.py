# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""CF-61 — a weakening below the risk frontier citing evidence that predates the move.

Manifest: ``23514`` on ``frontier_evidence``, secondary ``P0001`` on ``mainline.fn_frontier_guard``,
``MI20``, depth >= 2; profile ``mainline`` only; milestone
``K7``; ``requires = ['mainline.frontier_move']``.

*"As previously approved"* is not evidence. A monotone risk frontier moves in one
direction: once an incident has established that a control class is more dangerous than the
organisation believed, a prior approval issued under the old belief is **evidentiarily
inadmissible** for weakening it.

The rule is about dates, not about judgement, which is what makes it enforceable: evidence
cited for a weakening below the frontier must post-date the move that put the frontier
there.

**Gated, and honestly so.** The relation this history writes is ``mainline.frontier_move`` and
``fn_frontier_guard``, owned by the fleet-propagation milestone. Until the
capability token above is declared satisfied the runner **skips** this case with a printed
reason, and a skipped case is never counted as a passed one. That is the difference between
a suite that is honest about its coverage and one that grows green by omission.
"""

from __future__ import annotations

from trappoint_conformance.harness import Harness, HistoryOutcome, Step
from trappoint_conformance.runner import register
from trappoint_conformance.site import SiteScope

from ._world import World, refusal


@register("CF-61")
def cf_61_frontier_evidence(harness: Harness, scope: SiteScope, schema: str) -> HistoryOutcome:
    """Weaken a control on the strength of the approval that preceded the accident."""
    world = World(harness, scope, schema)
    world.site_row()
    built = world.cleared_permit(tag="cf61")
    return refusal(
        harness,
        "CF-61",
        (
            Step(
                label="weaken below the frontier on pre-frontier evidence",
                sql=world.sql(
                    "INSERT INTO {s}.frontier_weakening "
                    "(site_id, clause_uuid, frontier_move_id, evidence_at, evidence_kind) "
                    "VALUES (%s, %s, %s, now() - INTERVAL '400 days', 'prior_approval')"
                ),
                params=(world.site_id, built["clause_uuid"], world.uid("cf61:move")),
            ),
        ),
        relation="frontier_weakening",
    )
