# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""CF-14 — two ``permit_event`` rows appended from the same head.

Manifest: ``23505`` on ``linear``, ``MI09`` and ``MI24``, anomaly ``A4``.

A chain, not a tree. ``UNIQUE (permit_id, prev_seq)`` is a **lock-free compare-and-swap**:
two writers that both believe the head is at *n* both try to claim ``prev_seq = n`` and
exactly one succeeds. No advisory lock — CockroachDB has none — and no sequence, because a
sequence gap means nothing while a CAS gap means tampering.

The genesis row and one successor are setup, and they have to be, because the chain trigger
refuses a ``prev_seq`` with no predecessor row before the index is ever consulted (that is
``CF-17``). The fork is therefore built at a head that genuinely exists, which is the only
way this case tests the CAS rather than the trigger.
"""

from __future__ import annotations

from trappoint_conformance.harness import Harness, HistoryOutcome
from trappoint_conformance.runner import register
from trappoint_conformance.site import SiteScope

from ._world import World, refusal


@register("CF-14")
def cf_14_forked_permit_chain(harness: Harness, scope: SiteScope, schema: str) -> HistoryOutcome:
    """Claim a head two writers both think is theirs."""
    world = World(harness, scope, schema)
    world.site_row()
    permit_id = world.permit("cf14")
    world.append_event(
        "genesis",
        permit_id,
        seq=1,
        prev_seq=0,
        from_state="draft",
        to_state="checks_materialised",
    )
    head = world.chain_digest(permit_id, 1)
    world.append_event(
        "the first writer claims the head",
        permit_id,
        seq=2,
        prev_seq=1,
        from_state="checks_materialised",
        to_state="checks_materialised",
        prev_digest=head,
    )
    return refusal(
        harness,
        "CF-14",
        (
            world.event_step(
                "the second writer claims the same head",
                permit_id,
                seq=3,
                prev_seq=1,
                from_state="checks_materialised",
                to_state="checks_materialised",
                prev_digest=head,
            ),
        ),
        relation="permit_event",
    )
