# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""The gap-free ledger append: ``seq`` is derived in-transaction, never allocated.

``ARCHITECTURE.md`` §5.6 and invariant ``MI24``. The sequence is 0-based and **dense**,
and the density is what makes the ledger evidence rather than a log::

    seq := coalesce(max(seq) + 1, 0)          -- derived INSIDE the caller's txn
    PRIMARY KEY (site_code, seq)              -- the compare-and-swap
    UNIQUE (site_code, prev_link_hash)        -- and the fork check

Two appenders that read the same ``max(seq)`` both try to write the same position and
one of them gets ``23505``. Nothing is allocated, nothing is cached, and nothing is
handed out ahead of a commit — **so a gap MEANS tampering.** That sentence is the entire
evidentiary value of the structure, and it is false the moment a sequence exists: a
sequence gap can be a crash, a rollback, a cache loss or a deletion, and a log that
cannot distinguish those four is a log that asserts nothing about any of them.

``CREATE SEQUENCE``, ``nextval(``, ``SERIAL`` and ``unique_rowid()`` are therefore
banned repository-wide, refused by ``trappoint render`` and by ``trappoint migrate lint``
(ruling D10). That lint is **load-bearing rather than decorative**: ground-truth finding
F4 measured that ``CREATE SEQUENCE`` succeeds on this cluster. :func:`assert_gap_free`
lets any caller apply the same test to a string of SQL it is about to run.

**Two append paths, one behaviour.** :func:`append_leaf` does the derivation in Python
so the link arithmetic is unit-testable without a cluster and so a caller that already
holds the canonical bytes pays no extra round trip; :func:`append_leaf_server_side`
calls migration ``0119``'s ``fn_ledger_cas_append``, which does the identical thing in
one statement. Both must be run inside a SERIALIZABLE transaction the CALLER owns —
neither commits, because the ledger row belongs to whatever transaction produced the
fact it records (``INV-3``).
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from typing import Any, Final, Protocol

from psycopg import sql as pgsql

__all__ = [
    "BANNED_SQL_TOKENS",
    "GENESIS_LINK",
    "LedgerPosition",
    "append_leaf",
    "append_leaf_server_side",
    "assert_dense",
    "assert_gap_free",
    "leaf_hash",
    "link_hash",
    "next_seq",
]

#: RFC 6962 leaf prefix. A leaf and an interior node must not be confusable, or a second
#: preimage over the tree is available for free.
_LEAF_PREFIX: Final = b"\x00"

#: Genesis predecessor: 32 zero bytes (custody ``CU-1``). Never NULL, so the link
#: function is total and no verifier ever branches on an absent predecessor.
GENESIS_LINK: Final[bytes] = bytes(32)

_SCHEMA_RE: Final = re.compile(r"^[a-z_][a-z0-9_]*$")

#: Ruling D10, as a table a caller can apply. Kept here as well as in the renderer
#: because this is the module whose docstring makes the claim the ban protects.
BANNED_SQL_TOKENS: Final[tuple[tuple[str, re.Pattern[str]], ...]] = (
    (
        "CREATE SEQUENCE",
        re.compile(r"\bCREATE\s+(?:TEMP\s+|TEMPORARY\s+|UNLOGGED\s+)*SEQUENCE\b", re.I),
    ),
    ("nextval(", re.compile(r"\bnextval\s*\(", re.I)),
    ("SERIAL", re.compile(r"\b(?:BIG|SMALL)?SERIAL[248]?\b", re.I)),
    ("unique_rowid()", re.compile(r"\bunique_rowid\s*\(", re.I)),
)


class _Cursor(Protocol):
    """The slice of a psycopg cursor this module uses."""

    def execute(self, query: Any, params: Any = None) -> Any:
        """Execute a statement."""

    def fetchone(self) -> Any:
        """Return the first row, or ``None``."""


class _Connection(Protocol):
    """The slice of a psycopg connection this module uses."""

    def cursor(self) -> Any:
        """Return a cursor."""


@dataclass(frozen=True, slots=True)
class LedgerPosition:
    """Where a leaf landed, and what it committed to.

    Attributes:
        site_code: the ledger partition.
        seq: the 0-based dense position this append took.
        leaf_hash: ``SHA-256(0x00 || canon_bytes)``.
        prev_link_hash: the predecessor's link, or :data:`GENESIS_LINK` at position 0.
        link_hash: ``SHA-256(prev_link_hash || leaf_hash)``.
    """

    site_code: str
    seq: int
    leaf_hash: bytes
    prev_link_hash: bytes
    link_hash: bytes


def leaf_hash(canon_bytes: bytes) -> bytes:
    """Return ``SHA-256(0x00 || canon_bytes)`` — RFC 6962 §2.1.

    *canon_bytes* must already be RFC 8785 JCS. Canonicalisation belongs to
    ``trappoint-jcs``, which has zero runtime dependencies precisely so an opposing
    expert can re-implement it; hashing something this function canonicalised itself
    would move that decision somewhere nobody audits.
    """
    return hashlib.sha256(_LEAF_PREFIX + canon_bytes).digest()


def link_hash(prev_link_hash: bytes, leaf: bytes) -> bytes:
    """Return ``SHA-256(prev_link_hash || leaf)``.

    Raises:
        ValueError: either argument is not 32 bytes. A short hash concatenated into a
            chain makes the chain ambiguous about where one link ends, which is a second
            preimage handed over for free.
    """
    if len(prev_link_hash) != hashlib.sha256().digest_size:
        raise ValueError(f"prev_link_hash is {len(prev_link_hash)} bytes; expected 32")
    if len(leaf) != hashlib.sha256().digest_size:
        raise ValueError(f"leaf hash is {len(leaf)} bytes; expected 32")
    return hashlib.sha256(prev_link_hash + leaf).digest()


def assert_gap_free(sql_text: str) -> None:
    """Refuse SQL that would make a gap in the ledger ambiguous.

    Raises:
        ValueError: *sql_text* contains ``CREATE SEQUENCE``, ``nextval(``, ``SERIAL`` or
            ``unique_rowid()``.
    """
    for token, pattern in BANNED_SQL_TOKENS:
        found = pattern.search(sql_text)
        if found is not None:
            raise ValueError(
                f"banned token {found.group(0)!r} (ruling D10): {token} makes a gap in "
                "the ledger ambiguous, and the whole evidentiary value of the ledger is "
                "that a gap MEANS tampering"
            )


def _relation(schema: str, table: str) -> pgsql.Identifier:
    if _SCHEMA_RE.match(schema) is None:
        raise ValueError(f"{schema!r} is not a bare lower-case SQL identifier")
    return pgsql.Identifier(schema, table)


def next_seq(cursor: _Cursor, schema: str, site_code: str) -> int:
    """Return ``coalesce(max(seq) + 1, 0)`` for *site_code*.

    Read inside the caller's SERIALIZABLE transaction, which is the whole mechanism: the
    value is a *proposal*, and the primary key is what adjudicates between two proposals
    that agree.
    """
    cursor.execute(
        pgsql.SQL("SELECT coalesce(max(seq) + 1, 0) FROM {} WHERE site_code = %s").format(
            _relation(schema, "ledger_leaf")
        ),
        (site_code,),
    )
    row = cursor.fetchone()
    return int(row[0])


def assert_dense(cursor: _Cursor, schema: str, site_code: str) -> int:
    """Refuse a ledger partition whose sequence has a hole, and return its leaf count.

    ``count(*)`` must equal ``max(seq) + 1`` for a 0-based dense sequence. Under a
    compare-and-swap ledger there is no legitimate way to reach a state where it does
    not: nothing is allocated, so nothing can be allocated and abandoned; the append is
    an ``INSERT`` in the transaction that produced the fact, so a rolled-back transaction
    leaves no position taken. **A hole therefore means rows were deleted**, and this is
    the function that says so out loud.

    NOT on the append path. It is O(partition) and belongs to the verifier, the nightly
    fixity patrol and the conformance suite — the places where the question being asked
    is "is this ledger intact", not "where does this leaf go".

    Raises:
        ValueError: the sequence is not dense.
    """
    cursor.execute(
        pgsql.SQL("SELECT count(*), coalesce(max(seq) + 1, 0) FROM {} WHERE site_code = %s").format(
            _relation(schema, "ledger_leaf")
        ),
        (site_code,),
    )
    row = cursor.fetchone()
    total, expected = int(row[0]), int(row[1])
    if total != expected:
        raise ValueError(
            f"ledger {site_code!r} holds {total} leaves but its highest position implies "
            f"{expected}: the sequence has {expected - total} hole(s). Positions are "
            "derived by compare-and-swap and never allocated, so a hole cannot be a "
            "crash, a rollback or a cache loss — the rows were tampered with"
        )
    return total


def _prev_link(cursor: _Cursor, schema: str, site_code: str, seq: int) -> bytes:
    if seq == 0:
        return GENESIS_LINK
    cursor.execute(
        pgsql.SQL("SELECT link_hash FROM {} WHERE site_code = %s AND seq = %s").format(
            _relation(schema, "ledger_leaf")
        ),
        (site_code, seq - 1),
    )
    row = cursor.fetchone()
    if row is None:
        # Defensive, and its unreachability is the assertion. `seq` came from
        # `max(seq) + 1` in the SAME transaction, so the row at `seq - 1` is the row
        # that produced that maximum. Reaching this branch means the two reads did not
        # see one snapshot — which is not a missing row, it is the isolation level not
        # being what the caller asserted it was.
        raise ValueError(
            f"ledger {site_code!r} has no leaf at position {seq - 1} while position "
            f"{seq} was derived from the maximum in the same transaction: the two reads "
            "did not see one snapshot, so this transaction is not SERIALIZABLE"
        )
    return bytes(row[0])


def append_leaf(
    connection: _Connection,
    *,
    schema: str,
    site_code: str,
    entry_id: str,
    leaf: bytes,
    batch_id: str,
) -> LedgerPosition:
    """Append one leaf, deriving its position in the caller's transaction.

    Does NOT commit: the leaf belongs to whatever transaction produced the fact it
    records.

    Args:
        connection: a connection already inside a SERIALIZABLE transaction.
        schema: the binding's business schema.
        site_code: the ledger partition.
        entry_id: the ``ledger_intake`` row this leaf sequences.
        leaf: ``SHA-256(0x00 || canon_bytes)``; see :func:`leaf_hash`.
        batch_id: which sequencer run. Commits to nothing; it is operational.

    Returns:
        Where the leaf landed and what it committed to.

    Raises:
        ValueError: the sequence is not dense, or *leaf* is not 32 bytes.
        psycopg.errors.UniqueViolation: ``23505`` on ``ledger_leaf_pkey`` (another
            appender took this position) or on ``ledger_linear`` (another appender forked
            at the same predecessor). Both are the compare-and-swap working, and neither
            is retried by this function: the caller's ``run_gate`` owns that decision.
    """
    cursor = connection.cursor()
    seq = next_seq(cursor, schema, site_code)
    previous = _prev_link(cursor, schema, site_code, seq)
    link = link_hash(previous, leaf)
    cursor.execute(
        pgsql.SQL(
            "INSERT INTO {} (site_code, seq, entry_id, leaf_hash, prev_link_hash, "
            "link_hash, batch_id) VALUES (%s, %s, %s::UUID, %s, %s, %s, %s::UUID)"
        ).format(_relation(schema, "ledger_leaf")),
        (site_code, seq, entry_id, leaf, previous, link, batch_id),
    )
    return LedgerPosition(
        site_code=site_code,
        seq=seq,
        leaf_hash=leaf,
        prev_link_hash=previous,
        link_hash=link,
    )


def append_leaf_server_side(
    connection: _Connection,
    *,
    schema: str,
    site_code: str,
    entry_id: str,
    leaf: bytes,
    batch_id: str,
) -> int:
    """Append one leaf via migration ``0119``'s ``fn_ledger_cas_append``.

    Identical semantics to :func:`append_leaf` in one round trip. Prefer this from a
    Lambda, where the round trip is the cost that matters; prefer :func:`append_leaf`
    where the caller wants the link arithmetic in a language it can test.

    Returns:
        The position the leaf took.
    """
    cursor = connection.cursor()
    cursor.execute(
        pgsql.SQL("SELECT {}(%s, %s::UUID, %s, %s::UUID)").format(
            _relation(schema, "fn_ledger_cas_append")
        ),
        (site_code, entry_id, leaf, batch_id),
    )
    row = cursor.fetchone()
    return int(row[0])
