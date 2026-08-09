# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""CF-43 — materialise an obligation concurrently with the merge of the same permit.

Manifest: class ``retry``, ``40001``, exhibit ``mainline.permit.open_blocking``,
``MI02``, anomaly ``A1``.

The conflict is **materialised in data**, and that is the design decision the whole
concurrency story rests on. Because ``fn_check_materialised`` writes the counter onto the
subject row, a transaction that materialises an obligation and a transaction that merges the
subject touch the *same row*. The loser gets ``40001`` — a real serialization failure, on a
real write-write conflict — rather than a phantom nobody detects.

The alternative design, where the merge asks a question about another table and nothing
writes the subject row, produces a history that SERIALIZABLE is entitled to call legal:
neither transaction wrote what the other read in a way the system can see. That is the
anomaly, and it is closed by arranging for there to be a write.

**The exhibit for a ``40001`` is the projected column that carried the conflict**
(``spec/errors.md`` §3.1), and it is the column this case names because it is the column
``fn_check_materialised`` incremented.

**No retry.** ``40001`` is the one retryable code, and this case deliberately does not
retry: a retry here would observe the *committed* obligation and be refused by
``gate_closed_when_issued`` instead, which is the correct behaviour of a client and the
wrong observation for this case. The harness's retry loop is bypassed for exactly that
reason, and the outcome is constructed from what the first attempt saw.
"""

from __future__ import annotations

from trappoint_conformance.harness import Harness, HistoryOutcome
from trappoint_conformance.runner import register
from trappoint_conformance.site import SiteScope

from ._world import World, digest32


@register("CF-43")
def cf_43_materialised_conflict(harness: Harness, scope: SiteScope, schema: str) -> HistoryOutcome:
    """Merge and materialise at the same instant, and see which one the database keeps."""
    import psycopg

    world = World(harness, scope, schema)
    world.site_row()
    clause_uuid, commit_id = world.clause_version("cf43")
    world.closure(clause_uuid, commit_id, max_severity=1, virulence="routine")
    permit_id = world.permit("cf43")

    merger = world.sibling_connection()
    merger.autocommit = False
    outcome = HistoryOutcome(
        case_id="CF-43",
        completed=False,
        sqlstate="00000",
        constraint="",
        message="",
    )
    try:
        with merger.cursor() as cur:
            # The merging transaction reads the subject it is about to complete.
            cur.execute(
                world.sql("SELECT open_blocking FROM {s}.permit WHERE permit_id = %s"),
                (permit_id,),
            )
            outcome.stored["read_open_blocking"] = cur.fetchone()[0]
            # A second writer materialises an obligation against the same subject and
            # commits. This writes the very row the merge just read.
            world.check(
                clause_uuid=clause_uuid, commit_id=commit_id, permit_id=permit_id, tag="cf43"
            )
            # The merge now writes what it read.
            cur.execute(
                world.sql(
                    "UPDATE {s}.permit SET state = 'merged', merged_commit = %s "
                    "WHERE permit_id = %s"
                ),
                (digest32("merged"), permit_id),
            )
        merger.commit()
        outcome.completed = True
        outcome.message = (
            "the merge committed while an obligation was materialised against the same "
            "subject in a concurrent transaction"
        )
    except psycopg.Error as exc:
        merger.rollback()
        diag = exc.diag
        outcome.sqlstate = (diag.sqlstate if diag is not None else None) or "XXUUU"
        outcome.message = (diag.message_primary if diag is not None else None) or str(exc)
        outcome.failing_step = "the merge writes the row the materialisation moved"
        if outcome.sqlstate == "40001":
            # The projected column that carried the materialised conflict.
            outcome.constraint = "mainline.permit.open_blocking"
        else:
            outcome.constraint = (diag.constraint_name if diag is not None else None) or ""
    finally:
        merger.close()
    return outcome
