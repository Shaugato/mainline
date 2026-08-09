# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""CF-54 — a semantically inferred blame edge marked active.

Manifest: ``23514`` on ``inference_never_blocks``, ``MI13``, invariant ``I11``; profile ``mainline``
only; milestone
``K3``; ``requires = ['mainline.blame_edge']``.

**An inference may accuse. It may not arm the gate.** A semantically inferred
edge — this clause looks like it descends from that incident — is a lead worth showing a
human and is not a fact worth stopping work over. The distinction lives in the ``basis``
column and is enforced by a plain ``CHECK``, so it holds for the ingestion agent, for a
backfill script, and for whoever writes the next importer.

**Gated, and honestly so.** The relation this history writes is ``mainline.blame_edge``, owned by
the ancestry milestone. Until the
capability token above is declared satisfied the runner **skips** this case with a printed
reason, and a skipped case is never counted as a passed one. That is the difference between
a suite that is honest about its coverage and one that grows green by omission.
"""

from __future__ import annotations

from trappoint_conformance.harness import Harness, HistoryOutcome, Step
from trappoint_conformance.runner import register
from trappoint_conformance.site import SiteScope

from ._world import World, refusal


@register("CF-54")
def cf_54_inference_never_blocks(harness: Harness, scope: SiteScope, schema: str) -> HistoryOutcome:
    """Let a similarity score arm the gate."""
    world = World(harness, scope, schema)
    world.site_row()
    clause_uuid, commit_id = world.clause_version("cf54")
    return refusal(
        harness,
        "CF-54",
        (
            Step(
                label="mark an inferred edge active",
                sql=world.sql(
                    "INSERT INTO {s}.blame_edge "
                    "(site_id, clause_uuid, commit_id, basis, state) "
                    "VALUES (%s, %s, %s, 'semantic_inference', 'active')"
                ),
                params=(world.site_id, clause_uuid, commit_id),
            ),
        ),
        relation="blame_edge",
    )
