# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""CF-56 — a clause version whose ``sev_max`` is lower than its parent's.

Manifest: ``P0001`` on ``mainline.fn_clause_version_guard``, ``MI15``, invariant ``I05``; profile
``mainline`` only; milestone
``K3``; ``requires = ['mainline.clause_version']``.

**Provenance laundering**, and it is the attack that requires no malice: reword
a control across four revisions, each individually reasonable, until nobody recalls that a
death wrote it. No single edit is the one that removes the blame; the fourth one is simply
where the trace runs out.

Blame ancestry is therefore **monotone by construction**: a version may add ancestors and
may raise ``sev_max``, and may never lower either. Tightening is free; loosening is a
different operation with a different signature on it.

**Gated, and honestly so.** The relation this history writes is ``mainline.clause_version`` with its
ancestry columns (migration 0029) and its guard (0141/0146). Until the
capability token above is declared satisfied the runner **skips** this case with a printed
reason, and a skipped case is never counted as a passed one. That is the difference between
a suite that is honest about its coverage and one that grows green by omission.
"""

from __future__ import annotations

from trappoint_conformance.harness import Harness, HistoryOutcome, Step
from trappoint_conformance.runner import register
from trappoint_conformance.site import SiteScope

from ._world import World, refusal


@register("CF-56")
def cf_56_ancestry_never_shrinks(harness: Harness, scope: SiteScope, schema: str) -> HistoryOutcome:
    """Reword a control until the death that wrote it is gone."""
    world = World(harness, scope, schema)
    world.site_row()
    parent_clause, parent_commit = world.clause_version("cf56-parent")
    return refusal(
        harness,
        "CF-56",
        (
            Step(
                label="author a milder child version",
                sql=world.sql(
                    "INSERT INTO {s}.clause_version "
                    "(clause_uuid, commit_id, site_id, control_delta, body_sha256, "
                    " parent_commit_id, sev_max, blood_size) "
                    "VALUES (%s, %s, %s, 'restate', %s, %s, 0, 0)"
                ),
                params=(
                    parent_clause,
                    __import__("hashlib").sha256(b"cf56-child").digest(),
                    world.site_id,
                    __import__("hashlib").sha256(b"cf56-body").digest(),
                    parent_commit,
                ),
            ),
        ),
        relation="clause_version",
    )
