# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""CF-49 — merge a permit carrying un-dispositioned identity residue.

Manifest: ``23514`` on ``identity_conserved_when_issued``, ``MI03``, depth >= 2; profile
``mainline`` only; milestone
``K3``; ``requires = ['mainline.identity_residue']``.

Conservation law ``L2``: every ancestor clause with severity >= 4 is either
**matched** across the edit or has an ``identity_residue`` row. Never neither. A control
that silently stopped being tracked because a rewrite defeated the matcher is the exact
failure the blame closure exists to prevent, and it is invisible unless the unmatched case
is recorded as an obligation rather than dropped as a miss.

``reason`` is a closed vocabulary — ``unmatched``, ``ambiguous``, ``anchor_drop``,
``opaque_control``, ``citation_unresolved`` — because *why* the matcher failed determines
what a human has to do about it, and a free-text field would make that unqueryable within a
month.

**Gated, and honestly so.** The relation this history writes is ``mainline.identity_residue``
(migration 0049), whose projection trigger onto ``permit.open_residue`` belongs to the ancestry
domain. Until the
capability token above is declared satisfied the runner **skips** this case with a printed
reason, and a skipped case is never counted as a passed one. That is the difference between
a suite that is honest about its coverage and one that grows green by omission.
"""

from __future__ import annotations

from trappoint_conformance.harness import Harness, HistoryOutcome
from trappoint_conformance.runner import register
from trappoint_conformance.site import SiteScope

from ._world import World, refusal


@register("CF-49")
def cf_49_identity_residue(harness: Harness, scope: SiteScope, schema: str) -> HistoryOutcome:
    """Merge over a clause the matcher could not follow across the edit."""
    world = World(harness, scope, schema)
    world.site_row()
    built = world.cleared_permit(tag="cf49")
    world.run(
        "record an unmatched ancestor",
        "INSERT INTO {s}.identity_residue "
        "(site_id, commit_id, ancestor_clause_uuid, reason, max_ancestral_severity, features) "
        "VALUES (%s, %s, %s, 'unmatched', 5, '{{}}'::JSONB)",
        (world.site_id, built["commit_id"], built["clause_uuid"]),
    )
    return refusal(
        harness,
        "CF-49",
        (world.merge_step(built["permit_id"]),),
        relation="permit",
    )
