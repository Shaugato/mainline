# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""CF-41 — a blocking check naming both a permit and a change request.

Manifest: ``23514`` on ``exactly_one_subject``, invariant ``I02``.

An obligation belongs to **one** subject. A row naming both would be counted twice — once
by each subject's projection — and cleared once, because a single disposition covers a
single ``check_id``. The arithmetic would be permanently wrong in the direction that opens
gates.

The polymorphism is a nullable column per kind rather than one ``subject_id``, because
CockroachDB enforces a foreign key only when every column of it is non-NULL (``MATCH
SIMPLE``). That gives exactly one *enforced* reference per row — an obligation always names
a subject that exists — where a single polymorphic column would have to give up the
reference entirely. ``exactly_one_subject`` is what closes the hole that arrangement opens.
"""

from __future__ import annotations

from trappoint_conformance.harness import Harness, HistoryOutcome
from trappoint_conformance.runner import register
from trappoint_conformance.site import SiteScope

from ._world import World, refusal


@register("CF-41")
def cf_41_exactly_one_subject(harness: Harness, scope: SiteScope, schema: str) -> HistoryOutcome:
    """Block two subjects with one obligation."""
    world = World(harness, scope, schema)
    world.site_row()
    clause_uuid, commit_id = world.clause_version("cf41")
    world.closure(clause_uuid, commit_id, max_severity=1, virulence="routine")
    permit_id = world.permit("cf41")
    cr_id = world.change_request("cf41")
    return refusal(
        harness,
        "CF-41",
        (
            world.check_step(
                "materialise one obligation against two subjects",
                clause_uuid=clause_uuid,
                commit_id=commit_id,
                permit_id=permit_id,
                cr_id=cr_id,
                subject_kind="permit",
                check_id=world.uid("cf41:check"),
            ),
        ),
        relation="blocking_check",
    )
