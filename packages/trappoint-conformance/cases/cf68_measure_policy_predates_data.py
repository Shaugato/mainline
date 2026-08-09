# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""CF-68 — compute a standing measurement over data predating the signed policy.

Manifest: ``23514`` on ``measure_policy_predates_data``, invariant ``I15``; profile ``mainline``
only; milestone
``K8``; ``requires = ['mainline_meas.person_measure_policy']``.

A score computed **about a person**, used **against them**, and derived from a
policy that **did not exist when the data was made** is an allegation. Not a metric, not a
finding: an allegation, and it is not insertable.

This is invariant ``I15`` — the allegation firewall — and it is the constraint that costs
the most and is worth the most. Every measurement in this system is either about the
system's own behaviour or is bound to a policy the customer signed before the data existed.
The alternative is a surveillance instrument with a safety label on it, and ADR 0001
defaults per-approver dwell timing to OFF for the same reason.

**Gated, and honestly so.** The relation this history writes is
``mainline_meas.person_measure_policy``, owned by the measurement milestone. Until the
capability token above is declared satisfied the runner **skips** this case with a printed
reason, and a skipped case is never counted as a passed one. That is the difference between
a suite that is honest about its coverage and one that grows green by omission.
"""

from __future__ import annotations

from trappoint_conformance.harness import Harness, HistoryOutcome, Step
from trappoint_conformance.runner import register
from trappoint_conformance.site import SiteScope

from ._world import World, refusal


@register("CF-68")
def cf_68_measure_policy_predates_data(
    harness: Harness, scope: SiteScope, schema: str
) -> HistoryOutcome:
    """Score a person against a rule invented after the fact."""
    world = World(harness, scope, schema)
    world.site_row()
    return refusal(
        harness,
        "CF-68",
        (
            Step(
                label="measure a person under a policy younger than the data",
                sql=world.sql(
                    "INSERT INTO {s}_meas.person_measure "
                    "(site_id, signer_sub, policy_version, policy_signed_at, "
                    " data_earliest_at, value) "
                    "VALUES (%s, %s, 'pm-1.0', now() - INTERVAL '1 day', "
                    "        now() - INTERVAL '400 days', 0.5)"
                ),
                params=(world.site_id, world.actor("measured")),
            ),
        ),
        relation="person_measure",
    )
