# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""CF-69 — the audit identity attempts to write outside its attestation table.

Manifest: ``42501`` on ``grant:INSERT:mainline.disposition:mainline_auditor``; class ``deny``;
profile ``mainline`` only;
``requires = ["role:mainline_auditor"]``.

The role that certifies the books has no write path to them. The whole audit
surface is INSERT-ONLY and bound to a single relation — ``mainline_meas.external_attestation``
— which is also the only write the Managed MCP endpoint is permitted, and for the same
reason: an auditor who can write a disposition is not an auditor.

The attempted statement is deliberately incomplete as SQL. It names columns no valid
disposition could omit, and it does not matter: the privilege check happens before the
statement is planned against the table's constraints, so a refusal here is unambiguously
about the grant. If this case ever observes ``23502`` or ``23514`` instead, the role holds
INSERT and the finding is far more serious than a badly-formed test.

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


@register("CF-69")
def cf_69_auditor_cannot_write_the_books(
    harness: Harness, scope: SiteScope, schema: str
) -> HistoryOutcome:
    """Let the role that certifies the books try to write in them."""
    world = World(harness, scope, schema)

    outcome = refusal(
        harness,
        "CF-69",
        (
            Step(
                label="assume the role",
                sql=world.sql("SET ROLE mainline_auditor"),
            ),
            Step(
                label="file a disposition as the auditor",
                sql=world.sql(
                    "INSERT INTO {s}.disposition (check_id, receipt_id, site_id, kind, "
                    " defeater_code, rationale, signer_sub) "
                    "VALUES (gen_random_uuid(), gen_random_uuid(), %s, 'applied', "
                    "        'AUDIT', 'audit write attempt', 'auditor')"
                ),
                params=(world.site_id,),
            ),
        ),
        relation="disposition",
    )
    normalise_deny(outcome, verb="INSERT", obj="disposition", role="mainline_auditor")
    # The history's transaction aborted, which already reset the role. This is the
    # belt to that pair of braces and its failure is not a finding about anything.
    with contextlib.suppress(Exception):
        world.run("reset the role", "RESET ROLE")
    return outcome
