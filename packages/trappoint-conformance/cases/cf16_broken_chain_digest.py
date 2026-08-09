# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""CF-16 — append a ``permit_event`` whose ``prev_digest`` does not match.

Manifest: ``P0001`` on ``mainline.fn_permit_event_chain``, ``MI24``, anomaly ``A9``.

The difference between a comment claiming a chain and a chain. ``chain_digest`` is a
``STORED`` generated column, so the server computes each link; ``prev_digest`` is supplied
by the writer, so the *claim* about which link precedes this one is an input — and an input
is **verified**, never trusted.

The guard uses ``IS DISTINCT FROM`` rather than ``<>`` for a reason worth stating: a NULL on
either side makes ``<>`` evaluate to NULL, an ``IF`` on NULL does not execute, and the check
would pass silently on precisely the row it exists to catch.

Two objects raise this message byte for byte — the permit chain and the change-request
chain are one function rendered twice — so the case tells the resolver which relation it
wrote to. An exhibit chosen by tie-break is not an exhibit.
"""

from __future__ import annotations

from trappoint_conformance.harness import Harness, HistoryOutcome
from trappoint_conformance.runner import register
from trappoint_conformance.site import SiteScope

from ._world import World, digest32, refusal


@register("CF-16")
def cf_16_broken_chain_digest(harness: Harness, scope: SiteScope, schema: str) -> HistoryOutcome:
    """Point at a predecessor that exists, with a digest that is not its own."""
    world = World(harness, scope, schema)
    world.site_row()
    permit_id = world.permit("cf16")
    world.append_event(
        "genesis",
        permit_id,
        seq=1,
        prev_seq=0,
        from_state="draft",
        to_state="checks_materialised",
    )
    return refusal(
        harness,
        "CF-16",
        (
            world.event_step(
                "append with a forged predecessor digest",
                permit_id,
                seq=2,
                prev_seq=1,
                from_state="checks_materialised",
                to_state="dispositioned",
                prev_digest=digest32("a digest from some other chain"),
            ),
        ),
        relation="permit_event",
    )
