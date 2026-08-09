# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""CF-48 — the application role attempts to drop the merge-gate trigger.

Manifest: ``42501`` on ``grant:DDL:mainline.permit:agent_gate``; class ``deny``; profile
``mainline`` only;
``requires = ["role:agent_gate"]``.

The application role holds **no DDL**, and the reason is the anomaly ``A9``
residual: a compromised agent that can drop a trigger evaporates the central invariant with
no schema-change record and no refusal for anyone to find. Privilege is the only layer that
stands in front of that one — a trigger cannot defend itself against ``DROP TRIGGER`` — so
this case is the grant layer being tested from the outside, exactly as ``CF-39`` tests the
trigger layer from the inside.

The residual that remains after this case passes is stated rather than papered over: a
cluster administrator with SQL can still drop it. That is what the ``ccloud`` audit-log
ingestion in the custody ledger is for, and it is a *detection* control, not a preventive
one.

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


@register("CF-48")
def cf_48_app_role_cannot_drop_the_trigger(
    harness: Harness, scope: SiteScope, schema: str
) -> HistoryOutcome:
    """Let the gate service try to remove the gate."""
    world = World(harness, scope, schema)

    outcome = refusal(
        harness,
        "CF-48",
        (
            Step(
                label="assume the role",
                sql=world.sql("SET ROLE agent_gate"),
            ),
            Step(
                label="drop the merge-gate trigger as the application role",
                sql=world.sql("DROP TRIGGER permit_merge_gate ON {s}.permit"),
                params=(),
            ),
        ),
        relation="permit",
    )
    normalise_deny(outcome, verb="DDL", obj="permit", role="agent_gate")
    # The history's transaction aborted, which already reset the role. This is the
    # belt to that pair of braces and its failure is not a finding about anything.
    with contextlib.suppress(Exception):
        world.run("reset the role", "RESET ROLE")
    return outcome
