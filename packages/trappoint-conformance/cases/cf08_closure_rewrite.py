# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""CF-08 — rewrite the blame closure, twice, two different ways.

Manifest: ``P0001`` on ``mainline.fn_refuse_mutation``; secondary ``P0001`` on
``mainline.fn_closure_guard``; ``MI26`` and ``MI01``; depth >= 2.

Both halves are required, and the second is the interesting one.

**As an UPDATE.** ``UPDATE clause_blame_closure SET max_severity = 0`` is the direct
attack. Append-only refuses it, for every role, with no exception for the migrator.

**As a new generation.** The same attack, dressed as ordinary work: the closure is
append-only, so *append* a generation that says the ancestry is milder than the last one
said. That is the attack the append-only rule alone does not stop, and it is why
``fn_closure_guard`` exists: generations are dense and monotone, and severity may fall
only in the same transaction as a signed second-rater revision.

Provenance laundering is a sequence of individually reasonable edits. Each generation is a
legitimate recomputation; the fourth one is how a control written by a death comes to look
routine. The monotone guard is what makes the sequence cost a signature.
"""

from __future__ import annotations

from trappoint_conformance.harness import Harness, HistoryOutcome, Step
from trappoint_conformance.runner import register
from trappoint_conformance.site import SiteScope

from ._exhibit import normalise
from ._world import World, fail_stored, refusal


@register("CF-08")
def cf_08_closure_rewrite(harness: Harness, scope: SiteScope, schema: str) -> HistoryOutcome:
    """Lower a fatality's severity by editing it, then by appending over it."""
    world = World(harness, scope, schema)
    world.site_row()
    clause_uuid, commit_id = world.clause_version("cf08")
    world.closure(clause_uuid, commit_id, max_severity=5, virulence="blood_fatal")

    # ── the second half first, so its result can be carried on the primary outcome ──
    second = refusal(
        harness,
        "CF-08",
        (
            Step(
                label="append a milder generation",
                sql=world.sql(
                    "INSERT INTO {s}.clause_blame_closure "
                    "(clause_uuid, as_of_commit, closure_gen, site_id, ancestor_events, "
                    " ancestor_count, max_severity, virulence, depth, computed_by, "
                    " projector_ver) "
                    "VALUES (%s, %s, 1, %s, ARRAY[]::UUID[], 0, 0, 'routine', 1, "
                    "        'conformance', 'v1')"
                ),
                params=(clause_uuid, commit_id, world.site_id),
            ),
        ),
        relation="clause_blame_closure",
    )

    # ── the primary: the same rewrite as a mutation ──
    outcome = refusal(
        harness,
        "CF-08",
        (
            Step(
                label="edit the closure in place",
                sql=world.sql(
                    "UPDATE {s}.clause_blame_closure SET max_severity = 0 "
                    "WHERE clause_uuid = %s AND as_of_commit = %s"
                ),
                params=(clause_uuid, commit_id),
            ),
        ),
        relation="clause_blame_closure",
    )
    normalise(second, relation="clause_blame_closure")
    outcome.stored["secondary_sqlstate"] = second.sqlstate
    outcome.stored["secondary_constraint"] = second.constraint
    if (second.sqlstate, second.constraint) != ("P0001", "mainline.fn_closure_guard"):
        return fail_stored(
            outcome,
            f"the append-only half refused correctly, but the SAME attack as a new "
            f"generation observed {second.sqlstate} on {second.constraint or '<none>'} "
            f"rather than P0001 on mainline.fn_closure_guard. Append-only alone does not "
            f"stop provenance laundering; the monotone guard is the half that does.",
        )
    return outcome
