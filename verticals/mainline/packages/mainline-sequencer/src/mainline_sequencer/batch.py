# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
"""Batch selection by anti-join. Sequenced-ness is derived, never written.

``spec/custody/ledger-schema.md`` §4 is normative and this module is its implementation:

.. code-block:: sql

   SELECT i.* FROM mainline.ledger_intake i
    WHERE i.site_code = $1
      AND NOT EXISTS (SELECT 1 FROM mainline.ledger_leaf l
                       WHERE l.site_code = i.site_code AND l.entry_id = i.entry_id)
    ORDER BY i.hlc, i.entry_id
    LIMIT $2;

**There is no ``sequenced`` flag and there must never be one.** The consequence is
structural rather than aesthetic: the entire ledger write path becomes ``INSERT`` +
``SELECT``, which is why the ``mainline_ledger`` role holds exactly those grants, why
``agent_relay`` holds ``INSERT`` and not even ``SELECT``, and why the Managed MCP
server's insert-only write surface is a genuine match to the ledger's shape rather than a
coincidence we oversell. A flag would need ``UPDATE`` on an append-only table, and the
first ``UPDATE`` grant is the one that makes attack A1 (``delete_and_relink``) a single
statement for the role that already has it.

**``hlc`` is an ordering HINT and this is the only query in the repository permitted to
read it.** ``crdb_internal.cluster_logical_timestamp()`` returns the transaction's
*provisional* commit timestamp, which the KV layer may push before the transaction
commits (cockroach#79591). It orders a batch pleasantly; it decides nothing. The
authoritative order is the sequencer's ``seq``, and the authoritative *time* bracket is
the beacon (lower bound) and the RFC 3161 token (upper bound) on the checkpoint. Any
other query that orders by ``hlc`` is a defect.

**The ``entry_id`` tiebreak is load-bearing.** Two intake rows can carry the same ``hlc``
— the clock is logical and its resolution is finite — and ``ORDER BY i.hlc`` alone is
therefore not a total order. An unstable batch order is not a correctness bug (the leaf
set is the same and ``seq`` is dense either way) but it makes a replay produce a
*different tree* from the same intake, which destroys the one property an evidentiary
sequencer must have: run it twice on the same input and get the same log.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any
from uuid import UUID

if TYPE_CHECKING:  # pragma: no cover - typing only
    import psycopg

__all__ = [
    "DEFAULT_BATCH_SIZE",
    "MAX_BATCH_SIZE",
    "SELECT_UNSEQUENCED",
    "BatchSizeRefused",
    "IntakeRow",
    "unsequenced",
]

#: ``spec/custody/ledger-schema.md`` §4: ``B <= 2048``. The ceiling is not tuning. One
#: batch is one transaction and one checkpoint; a batch large enough to take seconds is a
#: batch large enough to lose its lease mid-append and to widen the ~60 s window of
#: undetectable mutation that the whole design is measured against.
MAX_BATCH_SIZE = 2048

#: Four times a minute at 512 leaves is 2,048 dispositions a minute, which is far above
#: anything a mine site produces. The default is chosen so the *checkpoint cadence*, not
#: the batch, is what bounds the window.
DEFAULT_BATCH_SIZE = 512

# The column list is fixed here rather than `SELECT i.*` so that a column added to
# `ledger_intake` cannot silently change the tuple shape this module unpacks. Order
# matters and is asserted against `IntakeRow` by the package's own test.
SELECT_UNSEQUENCED = """
SELECT i.entry_id,
       i.site_code,
       i.entry_kind,
       i.leaf_hash,
       i.payload_ver,
       i.is_sandbox,
       i.actor,
       i.actor_kind
  FROM mainline.ledger_intake i
 WHERE i.site_code = %s
   AND NOT EXISTS (SELECT 1
                     FROM mainline.ledger_leaf l
                    WHERE l.site_code = i.site_code
                      AND l.entry_id = i.entry_id)
 ORDER BY i.hlc, i.entry_id
 LIMIT %s
"""


class BatchSizeRefused(ValueError):
    """A caller asked for a batch outside ``1 .. MAX_BATCH_SIZE``."""


@dataclass(frozen=True, slots=True)
class IntakeRow:
    """One unsequenced intake row, reduced to what the appender commits to.

    ``payload`` and ``canon_bytes`` are deliberately absent. The appender never re-hashes
    a payload: ``leaf_hash`` was computed by the CLIENT under RFC 8785 at intake
    (``sink.record_intake``) and is copied into ``ledger_leaf`` verbatim. A sequencer that
    recomputed it would be a second implementation of the canonicaliser sitting between
    the bytes a stranger can reproduce and the tree those bytes are committed to, and a
    disagreement between the two would surface as a proof that does not verify years
    later rather than as a refusal now.
    """

    entry_id: UUID
    site_code: str
    entry_kind: str
    leaf_hash: bytes
    payload_ver: int
    is_sandbox: bool
    actor: str
    actor_kind: str


def unsequenced(
    conn: psycopg.Connection[Any],
    *,
    site_code: str,
    limit: int = DEFAULT_BATCH_SIZE,
) -> tuple[IntakeRow, ...]:
    """Select the next batch of unsequenced intake rows for *site_code*.

    Args:
        conn: an open connection. The caller decides the transaction; when the selection
            and the append share one ``SERIALIZABLE`` transaction, a row sequenced by a
            racing appender between the two invalidates this read and the whole attempt
            is retried, which is the behaviour the CAS loop is built around.
        site_code: the log partition.
        limit: batch size, ``1 .. MAX_BATCH_SIZE``.

    Returns:
        The rows in ``(hlc, entry_id)`` order — a total order, so a replay of the same
        intake produces the same tree.

    Raises:
        BatchSizeRefused: if *limit* is outside the permitted range.
    """
    if limit < 1 or limit > MAX_BATCH_SIZE:
        raise BatchSizeRefused(
            f"batch size {limit} is outside 1..{MAX_BATCH_SIZE}. The ceiling is "
            "spec/custody/ledger-schema.md §4: one batch is one transaction and one "
            "checkpoint, and a batch big enough to outlive its lease is a batch that "
            "widens the window it exists to close."
        )
    with conn.cursor() as cur:
        cur.execute(SELECT_UNSEQUENCED, (site_code, limit))
        rows = cur.fetchall()
    return tuple(
        IntakeRow(
            entry_id=entry_id,
            site_code=str(row_site),
            entry_kind=str(entry_kind),
            leaf_hash=bytes(leaf_hash),
            payload_ver=int(payload_ver),
            is_sandbox=bool(is_sandbox),
            actor=str(actor),
            actor_kind=str(actor_kind),
        )
        for (
            entry_id,
            row_site,
            entry_kind,
            leaf_hash,
            payload_ver,
            is_sandbox,
            actor,
            actor_kind,
        ) in rows
    )
