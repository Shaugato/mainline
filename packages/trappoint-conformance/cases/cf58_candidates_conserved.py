# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""CF-58 — a recall run whose candidate set is not exactly partitioned.

Manifest: ``23514`` on ``candidates_conserved``, ``MI17``, invariant ``I13``; profile ``mainline``
only; milestone
``K4``; ``requires = ['mainline.recall_run']``.

Conservation law ``L3`` as a constraint: ``candidates = blocking + advisory +
silenced + deduped``, **exactly**. Every candidate the retrieval generated has a recorded
fate, and the arithmetic is checked by the database rather than by whoever writes the
report.

A candidate that is generated and then quietly dropped is the single most expensive bug
this system could have, because it is invisible in every metric that matters and it is
indistinguishable from the retrieval simply not finding it.

**Gated, and honestly so.** The relation this history writes is ``mainline_meas.recall_run``
(migration 0081). Until the
capability token above is declared satisfied the runner **skips** this case with a printed
reason, and a skipped case is never counted as a passed one. That is the difference between
a suite that is honest about its coverage and one that grows green by omission.
"""

from __future__ import annotations

from trappoint_conformance.harness import Harness, HistoryOutcome, Step
from trappoint_conformance.runner import register
from trappoint_conformance.site import SiteScope

from ._world import World, refusal


@register("CF-58")
def cf_58_candidates_conserved(harness: Harness, scope: SiteScope, schema: str) -> HistoryOutcome:
    """Lose a candidate between the retrieval and the report."""
    world = World(harness, scope, schema)
    world.site_row()
    permit_id = world.permit("cf58")
    return refusal(
        harness,
        "CF-58",
        (
            Step(
                label="close a run whose partition loses one candidate",
                sql=world.sql(
                    "INSERT INTO {s}_meas.recall_run "
                    "(permit_id, site_id, corpus_commit, policy_version, index_plan_digest, "
                    " index_generation, n_candidates, n_blocking, n_advisory, n_silenced, "
                    " n_deduped) "
                    "VALUES (%s, %s, %s, 'rp-1.0', %s, 'g1', 9, 2, 3, 2, 1)"
                ),
                params=(
                    permit_id,
                    world.site_id,
                    __import__("hashlib").sha256(b"cf58-corpus").digest(),
                    __import__("hashlib").sha256(b"cf58-plan").digest(),
                ),
            ),
        ),
        relation="recall_run",
    )
