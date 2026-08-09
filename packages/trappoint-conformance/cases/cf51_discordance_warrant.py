# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""CF-51 — merge a permit citing a clause under an open discordance warrant.

Manifest: ``23514`` on ``no_open_warrant_when_issued``, ``MI05``, depth >= 2; profile ``mainline``
only; milestone
``K7``; ``requires = ['mainline.discordance_warrant']``.

A discordance warrant says: *two sources that should agree about this control
do not, and nobody has decided which is right yet.* Merging against a clause in that state
is choosing a side by default, which is the one thing a system that noticed the discordance
must not do silently.

**Gated, and honestly so.** The relation this history writes is ``mainline.discordance_warrant``,
owned by the fixity-drift milestone. Until the
capability token above is declared satisfied the runner **skips** this case with a printed
reason, and a skipped case is never counted as a passed one. That is the difference between
a suite that is honest about its coverage and one that grows green by omission.
"""

from __future__ import annotations

from trappoint_conformance.harness import Harness, HistoryOutcome
from trappoint_conformance.runner import register
from trappoint_conformance.site import SiteScope

from ._world import World, refusal


@register("CF-51")
def cf_51_discordance_warrant(harness: Harness, scope: SiteScope, schema: str) -> HistoryOutcome:
    """Merge while a control is under active dispute."""
    world = World(harness, scope, schema)
    world.site_row()
    built = world.cleared_permit(tag="cf51")
    world.run(
        "raise a discordance warrant over the cited clause",
        "INSERT INTO {s}.discordance_warrant (site_id, clause_uuid, state) VALUES (%s, %s, 'open')",
        (world.site_id, built["clause_uuid"]),
    )
    return refusal(harness, "CF-51", (world.merge_step(built["permit_id"]),), relation="permit")
