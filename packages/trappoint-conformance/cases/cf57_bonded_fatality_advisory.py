# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""CF-57 — a severity-5 event bonded to the permit's activity node, materialised as advisory.

Manifest: ``23514`` on ``bonded_fatalities_all_blocking``, ``MI16``, invariant ``I13``; profile
``mainline`` only; milestone
``K4``; ``requires = ['mainline.recall_run']``.

Finding ``S10``, stated as a **positive** invariant rather than a threshold: *a
fatality in your fonds is always recalled.* Probabilistic retrieval is allowed to be wrong
about almost everything, and it is not allowed to be wrong about a severity-5 event bonded
to the very activity the permit covers — that is not a retrieval question, it is a join.

``n_bonded_sev5`` is trigger-maintained and never an input, so the run cannot report a
smaller number than the join produces.

**Gated, and honestly so.** The relation this history writes is ``mainline_meas.recall_run``
(migration 0081) and its projection trigger (0113/0137). Until the
capability token above is declared satisfied the runner **skips** this case with a printed
reason, and a skipped case is never counted as a passed one. That is the difference between
a suite that is honest about its coverage and one that grows green by omission.
"""

from __future__ import annotations

from trappoint_conformance.harness import Harness, HistoryOutcome, Step
from trappoint_conformance.runner import register
from trappoint_conformance.site import SiteScope

from ._world import World, refusal


@register("CF-57")
def cf_57_bonded_fatality_advisory(
    harness: Harness, scope: SiteScope, schema: str
) -> HistoryOutcome:
    """Downgrade a fatality in your own fonds to a suggestion."""
    world = World(harness, scope, schema)
    world.site_row()
    permit_id = world.permit("cf57")
    return refusal(
        harness,
        "CF-57",
        (
            Step(
                label="close a run that downgraded a bonded fatality",
                sql=world.sql(
                    "INSERT INTO {s}_meas.recall_run "
                    "(permit_id, site_id, corpus_commit, policy_version, index_plan_digest, "
                    " index_generation, n_candidates, n_blocking, n_advisory, n_silenced, "
                    " n_deduped, n_bonded_sev5, n_bonded_sev5_blocking) "
                    "VALUES (%s, %s, %s, 'rp-1.0', %s, 'g1', 4, 1, 3, 0, 0, 2, 1)"
                ),
                params=(
                    permit_id,
                    world.site_id,
                    __import__("hashlib").sha256(b"cf57-corpus").digest(),
                    __import__("hashlib").sha256(b"cf57-plan").digest(),
                ),
            ),
        ),
        relation="recall_run",
    )
