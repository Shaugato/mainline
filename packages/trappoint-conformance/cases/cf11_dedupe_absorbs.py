# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""CF-11 — materialise the same ``weaken_over_blood`` check twice, precursor NULL.

Manifest: class ``admit`` (``00000``), exhibit ``blocking_check_dedupe_key_key``;
``asserts_stored_row`` ``count(blocking_check) = 1 AND permit.open_blocking = 1``.

A gate that refuses everything is not a gate, and this is one of the three cases that say
so. Two recall runs over the same corpus produce the same obligation; the second must be
**absorbed**, not refused and not counted twice, or every re-run of the recall agent
inflates the gate.

The mechanism is why the case exists. Six of the eight obligation origins leave
``precursor_event_id`` NULL, and NULLs are *distinct* in a unique index — so a composite
``UNIQUE`` over the identity columns would silently fail to dedupe exactly the origins that
matter most. ``dedupe_key`` is a ``STORED`` digest over ``coalesce`` sentinels, computed by
the server, so identity is well-defined in the presence of NULLs and the inserter cannot
choose it.

``ON CONFLICT (dedupe_key) DO NOTHING`` is the absorbing spelling, and the second statement
must leave the counter alone: the ``AFTER INSERT`` projection never runs, because no row
was inserted.
"""

from __future__ import annotations

from trappoint_conformance.harness import Harness, HistoryOutcome
from trappoint_conformance.runner import register
from trappoint_conformance.site import SiteScope

from ._world import World, fail_stored, refusal


@register("CF-11")
def cf_11_dedupe_absorbs(harness: Harness, scope: SiteScope, schema: str) -> HistoryOutcome:
    """Run the recall twice and count what landed."""
    world = World(harness, scope, schema)
    world.site_row()
    clause_uuid, commit_id = world.clause_version("cf11")
    world.closure(clause_uuid, commit_id, max_severity=5, virulence="blood_fatal")
    permit_id = world.permit()
    first = world.check_step(
        "recall run 1 materialises the obligation",
        clause_uuid=clause_uuid,
        commit_id=commit_id,
        permit_id=permit_id,
        check_id=world.uid("cf11:first"),
        on_conflict_skip=True,
    )
    second = world.check_step(
        "recall run 2 materialises the same obligation",
        clause_uuid=clause_uuid,
        commit_id=commit_id,
        permit_id=permit_id,
        check_id=world.uid("cf11:second"),
        on_conflict_skip=True,
    )
    outcome = refusal(harness, "CF-11", (first, second), relation="blocking_check")
    rows = world.scalar(
        "SELECT count(*) FROM {s}.blocking_check WHERE permit_id = %s", (permit_id,)
    )
    open_blocking = world.scalar(
        "SELECT open_blocking FROM {s}.permit WHERE permit_id = %s", (permit_id,)
    )
    outcome.stored["blocking_check_count"] = rows
    outcome.stored["open_blocking"] = open_blocking
    if outcome.completed and (rows, open_blocking) != (1, 1):
        return fail_stored(
            outcome,
            f"the duplicate was absorbed but the world is wrong: "
            f"count(blocking_check) = {rows} and open_blocking = {open_blocking}, both of "
            f"which must be 1. A dedupe that leaves the counter at two has refused nothing "
            f"and inflated the gate.",
        )
    return outcome
