# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""CF-13 — transition a permit straight from ``draft`` to ``merged``.

Manifest: ``23503`` on ``legal_edge``, ``MI10``, anomaly ``A7``.

The legal edge set is **queryable data**, not a ``switch`` in application code. An illegal
transition is a foreign key finding no row in ``subject_transition``, which means the
allowed lifecycle can be read, diffed, versioned and shown to a regulator — and cannot be
widened by a commit that adds a branch to a function nobody reviews.

``(permit, draft, merged)`` is absent from the seed for the obvious reason: a permit that
reaches ``merged`` without passing through ``checks_materialised`` and ``dispositioned``
has skipped the two states in which the gate is armed and answered.
"""

from __future__ import annotations

from trappoint_conformance.harness import Harness, HistoryOutcome
from trappoint_conformance.runner import register
from trappoint_conformance.site import SiteScope

from ._world import World, refusal


@register("CF-13")
def cf_13_illegal_transition(harness: Harness, scope: SiteScope, schema: str) -> HistoryOutcome:
    """Append the transition nobody is allowed to make."""
    world = World(harness, scope, schema)
    world.site_row()
    permit_id = world.permit("cf13")
    return refusal(
        harness,
        "CF-13",
        (
            world.event_step(
                "append draft -> merged",
                permit_id,
                seq=1,
                prev_seq=0,
                from_state="draft",
                to_state="merged",
            ),
        ),
        relation="permit_event",
    )
