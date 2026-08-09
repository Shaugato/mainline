# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""CF-64 — propagate a weakening across the fleet.

Manifest: ``23514`` on ``only_tightenings_travel``, ``MI23``, invariant ``I12``; profile
``mainline`` only; milestone
``K7``; ``requires = ['mainline.propagation']``.

Fleet propagation is asymmetric on purpose. A **tightening** learned at one site
travels automatically, because the cost of a redundant control is small and the cost of a
site that never heard is a fatality. A **weakening** does not travel at all: the local
argument for relaxing a control is local — this pump, this crew, this compensating
instrument — and shipping it to eleven other sites converts one considered decision into
eleven unconsidered ones.

**Gated, and honestly so.** The relation this history writes is ``mainline.propagation``, owned by
the fleet-propagation milestone. Until the
capability token above is declared satisfied the runner **skips** this case with a printed
reason, and a skipped case is never counted as a passed one. That is the difference between
a suite that is honest about its coverage and one that grows green by omission.
"""

from __future__ import annotations

from trappoint_conformance.harness import Harness, HistoryOutcome, Step
from trappoint_conformance.runner import register
from trappoint_conformance.site import SiteScope

from ._world import World, refusal


@register("CF-64")
def cf_64_only_tightenings_travel(
    harness: Harness, scope: SiteScope, schema: str
) -> HistoryOutcome:
    """Roll a relaxation out to twelve sites at once."""
    world = World(harness, scope, schema)
    world.site_row()
    clause_uuid, commit_id = world.clause_version("cf64", control_delta="weaken")
    return refusal(
        harness,
        "CF-64",
        (
            Step(
                label="propagate a weakening",
                sql=world.sql(
                    "INSERT INTO {s}.propagation "
                    "(origin_site_id, clause_uuid, commit_id, control_delta, state) "
                    "VALUES (%s, %s, %s, 'weaken', 'proposed')"
                ),
                params=(world.site_id, clause_uuid, commit_id),
            ),
        ),
        relation="propagation",
    )
