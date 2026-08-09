# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""CF-17 — append a ``permit_event`` declaring a ``prev_seq`` with no predecessor row.

Manifest: ``P0001`` on ``mainline.fn_permit_event_chain``, ``MI24``, anomaly ``A4``.

The gate does not invent a chain. A writer that claims to follow event 7 when the subject
has six events is either racing a writer whose transaction has not landed or fabricating a
history; both are refused identically, and neither is papered over by starting a new chain.

The genesis exemption is taken **once per subject** and only while the subject has no
events at all. A later row claiming genesis falls through to this lookup and is refused
here, with ``UNIQUE (permit_id, prev_seq)`` as the structural backstop behind it.
"""

from __future__ import annotations

from trappoint_conformance.harness import Harness, HistoryOutcome
from trappoint_conformance.runner import register
from trappoint_conformance.site import SiteScope

from ._world import World, refusal


@register("CF-17")
def cf_17_missing_predecessor(harness: Harness, scope: SiteScope, schema: str) -> HistoryOutcome:
    """Claim to follow an event that was never written."""
    world = World(harness, scope, schema)
    world.site_row()
    permit_id = world.permit("cf17")
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
        "CF-17",
        (
            world.event_step(
                "append from a head that does not exist",
                permit_id,
                seq=4,
                prev_seq=3,
                from_state="checks_materialised",
                to_state="dispositioned",
                prev_digest=world.chain_digest(permit_id, 1),
            ),
        ),
        relation="permit_event",
    )
