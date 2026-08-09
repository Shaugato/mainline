# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""CF-44 — N parallel merges of one permit yield exactly one merge record.

Manifest: ``23505`` on ``merge_record_pkey``, ``MI09``, anomaly ``A4``, depth >= 2;
``asserts_stored_row`` ``count(merge_record WHERE subject_id = $1) = 1``.

Eight connections, eight threads, one subject, one completion record. **Exactly one winner
is the assertion**; which one wins is not interesting and must not be asserted, because a
suite that expected a particular winner would be asserting a scheduling detail.

Like ``CF-09``, the completion is written straight at the table. Through the procedure the
losers would be refused earlier and by several different mechanisms depending on
interleaving — ``40001`` here, ``legal_edge`` there — and the case would be measuring the
scheduler. At the table it measures the primary key, which is the mechanism that has to
hold when the scheduler is doing something nobody anticipated.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

from trappoint_conformance.harness import Harness, HistoryOutcome
from trappoint_conformance.runner import register
from trappoint_conformance.site import SiteScope

from ._world import World, digest32, fail_stored

WRITERS = 8


@register("CF-44")
def cf_44_parallel_merges(harness: Harness, scope: SiteScope, schema: str) -> HistoryOutcome:
    """Race eight writers at one completion record."""
    import psycopg

    world = World(harness, scope, schema)
    world.site_row()
    built = world.cleared_permit(tag="cf44")
    permit_id = built["permit_id"]
    epoch = world.scalar("SELECT gate_epoch FROM {s}.permit WHERE permit_id = %s", (permit_id,))
    statement = world.sql(
        "INSERT INTO {s}.merge_record "
        "(subject_kind, subject_id, permit_id, gate_epoch, merged_by, merged_commit, "
        " clearance_digest) "
        "VALUES ('permit', %s, %s, %s, %s, %s, %s)"
    )

    def attempt(writer: int) -> tuple[str, str, str]:
        conn = world.sibling_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    statement,
                    (
                        permit_id,
                        permit_id,
                        epoch,
                        f"writer-{writer}",
                        digest32("merged"),
                        digest32("clearance"),
                    ),
                )
        except psycopg.Error as exc:
            diag = exc.diag
            return (
                (diag.sqlstate if diag is not None else None) or "XXUUU",
                (diag.constraint_name if diag is not None else None) or "",
                (diag.message_primary if diag is not None else None) or str(exc),
            )
        else:
            return ("00000", "", "")
        finally:
            conn.close()

    with ThreadPoolExecutor(max_workers=WRITERS) as pool:
        results = list(pool.map(attempt, range(WRITERS)))

    winners = [r for r in results if r[0] == "00000"]
    losers = [r for r in results if r[0] != "00000"]
    records = world.scalar(
        "SELECT count(*) FROM {s}.merge_record WHERE subject_id = %s", (permit_id,)
    )
    first_loser = losers[0] if losers else ("00000", "", "no writer was refused")
    outcome = HistoryOutcome(
        case_id="CF-44",
        completed=not losers,
        sqlstate=first_loser[0],
        constraint=first_loser[1],
        message=first_loser[2],
        failing_step="a losing writer's completion record",
    )
    outcome.stored["writers"] = WRITERS
    outcome.stored["winners"] = len(winners)
    outcome.stored["merge_record_count"] = records
    outcome.stored["loser_sqlstates"] = sorted({r[0] for r in losers})
    if records != 1 or len(winners) != 1:
        return fail_stored(
            outcome,
            f"{WRITERS} writers raced one subject: {len(winners)} committed and "
            f"merge_record holds {records} row(s) for it. Exactly one of each is the "
            f"invariant; anything else means a subject can be completed more than once.",
        )
    return outcome
