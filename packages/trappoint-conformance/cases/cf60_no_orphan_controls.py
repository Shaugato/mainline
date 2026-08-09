# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""CF-60 — supersede a document that still carries a live control series.

Manifest: ``23514`` on ``no_orphan_controls``, ``MI19``, invariant ``I06``; profile ``mainline``
only; milestone
``K3``; ``requires = ['mainline.carriage']``.

**You cannot delete a control by deleting the document that mentions it.** The
most common way a control disappears is not a decision to remove it; it is a document
supersession where one of the twelve controls the old document carried was never carried
forward, and nobody noticed because supersession is a routine act.

``open_token_count`` is projected from ``carriage`` — a control series is *carried* by a
document from an opening commit until a closing one — and ``superseded`` requires it to be
zero. ``superseded_by`` is an array because a supersession can split, and one successor is
a lie.

**Gated, and honestly so.** The relation this history writes is ``mainline.carriage`` (migration
0048) and its projection onto ``doc.open_token_count``. Until the
capability token above is declared satisfied the runner **skips** this case with a printed
reason, and a skipped case is never counted as a passed one. That is the difference between
a suite that is honest about its coverage and one that grows green by omission.
"""

from __future__ import annotations

from trappoint_conformance.harness import Harness, HistoryOutcome, Step
from trappoint_conformance.runner import register
from trappoint_conformance.site import SiteScope

from ._world import World, refusal


@register("CF-60")
def cf_60_no_orphan_controls(harness: Harness, scope: SiteScope, schema: str) -> HistoryOutcome:
    """Delete a control by superseding the document that mentions it."""
    world = World(harness, scope, schema)
    world.site_row()
    return refusal(
        harness,
        "CF-60",
        (
            Step(
                label="supersede a document still carrying controls",
                sql=world.sql(
                    "UPDATE {s}.doc SET state = 'superseded', superseded_by = ARRAY[%s]::UUID[] "
                    "WHERE doc_id = %s"
                ),
                params=(world.uid("cf60:successor"), world.uid("cf60:doc")),
            ),
        ),
        relation="doc",
    )
