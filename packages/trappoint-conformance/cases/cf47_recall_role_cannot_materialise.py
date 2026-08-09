# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""CF-47 — the recall role attempts to insert a blocking check.

Manifest: ``42501`` on ``grant:INSERT:mainline.blocking_check:agent_recaller``; class ``deny``;
profile ``mainline`` only;
``requires = ["role:agent_recaller"]``.

**That single grant is what makes the flagship claim true.** The role that
materialises an obligation is the KERNEL; the recall agent proposes candidates into its own
measurement schema and the kernel decides what becomes binding. Without the separation,
"the role that detects a precursor cannot dispose of it" is a sentence about intent rather
than about privilege, and an agent that can both raise and clear an obligation is an agent
that can quietly do neither.

``42501`` is a **DENY**, not a gate refusal, and the distinction is not pedantry: no gate
condition was evaluated, so classifying it with the ``23xxx`` family would say the gate
refused something the gate never saw. It has its own class and its own exhibit shape,
``grant:<verb>:<object>:<role>``, synthesised in :mod:`cases._privilege` from what this
case declares it attempted.
"""

from __future__ import annotations

import contextlib

from trappoint_conformance.harness import Harness, HistoryOutcome, Step
from trappoint_conformance.runner import register
from trappoint_conformance.site import SiteScope

from ._privilege import normalise_deny
from ._world import World, refusal


@register("CF-47")
def cf_47_recall_role_cannot_materialise(
    harness: Harness, scope: SiteScope, schema: str
) -> HistoryOutcome:
    """Let the role that finds the precursor try to file the obligation."""
    world = World(harness, scope, schema)
    world.site_row()
    clause_uuid, commit_id = world.clause_version("cf47")
    world.closure(clause_uuid, commit_id, max_severity=1, virulence="routine")
    permit_id = world.permit("cf47")

    outcome = refusal(
        harness,
        "CF-47",
        (
            Step(
                label="assume the role",
                sql=world.sql("SET ROLE agent_recaller"),
            ),
            Step(
                label="materialise an obligation as the recall agent",
                sql=world.sql(
                    "INSERT INTO {s}.blocking_check "
                    "(subject_kind, permit_id, site_id, clause_uuid, commit_id, "
                    " origin, severity, virulence, closure_gen, evidence_summary) "
                    "VALUES ('permit', %s, %s, %s, %s, 'blame_ancestry', 0, "
                    "        'routine', 0, 'recall agent attempt')"
                ),
                params=(permit_id, world.site_id, clause_uuid, commit_id),
            ),
        ),
        relation="blocking_check",
    )
    normalise_deny(outcome, verb="INSERT", obj="blocking_check", role="agent_recaller")
    # The history's transaction aborted, which already reset the role. This is the
    # belt to that pair of braces and its failure is not a finding about anything.
    with contextlib.suppress(Exception):
        world.run("reset the role", "RESET ROLE")
    return outcome
