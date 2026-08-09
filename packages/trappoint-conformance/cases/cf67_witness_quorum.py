# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""CF-67 — mark a checkpoint admissible with cosignatures from fewer than k trust domains.

Manifest: ``23514`` on ``witness_quorum``, invariant ``I16``; profile ``mainline`` only; milestone
``K9``; ``requires = ['mainline.cosignature']``.

**A ``q=1`` quorum over our own storage is not adverse in the legal sense**, and
split-view resistance MUST NOT be claimed until a genuinely adverse witness is live. A
checkpoint cosigned only by parties who share our incentives proves the log is internally
consistent and proves nothing at all about whether a different log was shown to someone
else.

This case is the guard against the most tempting shortcut in the whole custody design:
declaring the checkpoint admissible because it is cosigned, without asking by whom.

**Gated, and honestly so.** The relation this history writes is the admissibility columns on
``mainline.ledger_checkpoint`` and the quorum constraint, owned by the custody milestone. Until the
capability token above is declared satisfied the runner **skips** this case with a printed
reason, and a skipped case is never counted as a passed one. That is the difference between
a suite that is honest about its coverage and one that grows green by omission.
"""

from __future__ import annotations

from trappoint_conformance.harness import Harness, HistoryOutcome, Step
from trappoint_conformance.runner import register
from trappoint_conformance.site import SiteScope

from ._world import World, refusal


@register("CF-67")
def cf_67_witness_quorum(harness: Harness, scope: SiteScope, schema: str) -> HistoryOutcome:
    """Witness your own ledger and call it independent."""
    world = World(harness, scope, schema)
    world.site_row()
    return refusal(
        harness,
        "CF-67",
        (
            Step(
                label="admit a checkpoint witnessed only by ourselves",
                sql=world.sql(
                    "UPDATE {s}.ledger_checkpoint "
                    "SET admissible = true, cosigner_domains = 1, adverse_domains = 0 "
                    "WHERE checkpoint_id = %s"
                ),
                params=(world.uid("cf67:checkpoint"),),
            ),
        ),
        relation="ledger_checkpoint",
    )
