# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""CF-15 — two ``cr_event`` rows appended from the same head.

Manifest: ``23505`` on ``cr_linear``, ``MI09`` and ``MI24``, anomaly ``A4``.

The change request is a gated subject in its own right, so its chain needs the same
compare-and-swap — and the mirrored constraint **name** is required by spec rule ``R-3``:
the constraint name alone must identify the refusal without a qualifying table. Two
constraints called ``linear`` on two tables would make the exhibit ambiguous in exactly the
document where ambiguity is expensive.
"""

from __future__ import annotations

from trappoint_conformance.harness import Harness, HistoryOutcome
from trappoint_conformance.runner import register
from trappoint_conformance.site import SiteScope

from ._world import World, refusal


@register("CF-15")
def cf_15_forked_cr_chain(harness: Harness, scope: SiteScope, schema: str) -> HistoryOutcome:
    """Fork the other subject kind the same way."""
    world = World(harness, scope, schema)
    world.site_row()
    cr_id = world.change_request("cf15")
    world.append_event(
        "genesis",
        cr_id,
        seq=1,
        prev_seq=0,
        from_state="draft",
        to_state="checks_materialised",
        kind="change_request",
    )
    head = world.chain_digest(cr_id, 1, kind="change_request")
    world.append_event(
        "the first writer claims the head",
        cr_id,
        seq=2,
        prev_seq=1,
        from_state="checks_materialised",
        to_state="checks_materialised",
        prev_digest=head,
        kind="change_request",
    )
    return refusal(
        harness,
        "CF-15",
        (
            world.event_step(
                "the second writer claims the same head",
                cr_id,
                seq=3,
                prev_seq=1,
                from_state="checks_materialised",
                to_state="checks_materialised",
                prev_digest=head,
                kind="change_request",
            ),
        ),
        relation="cr_event",
    )
