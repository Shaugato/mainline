# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""The gap-free append, and the ban that makes a gap mean tampering. No database."""

from __future__ import annotations

import hashlib

import pytest

from trappoint_core.cas import (
    BANNED_SQL_TOKENS,
    GENESIS_LINK,
    append_leaf,
    assert_dense,
    assert_gap_free,
    leaf_hash,
    link_hash,
    next_seq,
)


class FakeCursor:
    """A cursor over an in-memory ledger: enough to exercise the derivation."""

    def __init__(self, rows: list[tuple[str, int, bytes]]) -> None:
        self.rows = rows
        self.result: list[tuple[object, ...]] = []
        self.inserts: list[tuple[object, ...]] = []

    def execute(self, query, params=None):
        text = query.as_string() if hasattr(query, "as_string") else str(query)
        if "count(*)" in text:
            site = params[0]
            seqs = [seq for code, seq, _ in self.rows if code == site]
            self.result = [(len(seqs), max(seqs) + 1 if seqs else 0)]
        elif "max(seq)" in text:
            site = params[0]
            seqs = [seq for code, seq, _ in self.rows if code == site]
            self.result = [(max(seqs) + 1 if seqs else 0,)]
        elif text.startswith("SELECT link_hash"):
            site, seq = params
            match = [link for code, position, link in self.rows if code == site and position == seq]
            self.result = [(match[0],)] if match else []
        else:
            self.inserts.append(params)
            self.result = []

    def fetchone(self):
        return self.result[0] if self.result else None


class FakeConnection:
    def __init__(self, rows: list[tuple[str, int, bytes]]) -> None:
        self.shared = FakeCursor(rows)

    def cursor(self) -> FakeCursor:
        return self.shared


def test_the_first_position_is_zero_and_its_predecessor_is_genesis():
    conn = FakeConnection([])
    landed = append_leaf(
        conn,
        schema="mainline",
        site_code="sitea",
        entry_id="00000000-0000-0000-0000-0000000000e1",
        leaf=leaf_hash(b'{"a":1}'),
        batch_id="00000000-0000-0000-0000-0000000000b1",
    )
    assert landed.seq == 0
    assert landed.prev_link_hash == GENESIS_LINK
    assert landed.link_hash == hashlib.sha256(GENESIS_LINK + landed.leaf_hash).digest()


def test_the_sequence_is_dense_and_derived_not_allocated():
    first = hashlib.sha256(b"one").digest()
    conn = FakeConnection([("sitea", 0, first), ("sitea", 1, hashlib.sha256(b"two").digest())])
    landed = append_leaf(
        conn,
        schema="mainline",
        site_code="sitea",
        entry_id="00000000-0000-0000-0000-0000000000e2",
        leaf=leaf_hash(b'{"a":2}'),
        batch_id="00000000-0000-0000-0000-0000000000b1",
    )
    assert landed.seq == 2
    assert landed.prev_link_hash == hashlib.sha256(b"two").digest()
    # A different site is a different ledger, and its positions are independent.
    assert next_seq(conn.cursor(), "mainline", "siteb") == 0


def test_a_hole_in_the_sequence_is_reported_as_tampering_not_as_a_missing_row():
    # Position 1 is absent while position 2 exists. Nothing is allocated, so the hole
    # cannot be a crash, a rollback or a cache loss: the rows were deleted, and the
    # message says exactly that rather than calling it a lookup miss.
    conn = FakeConnection([("sitea", 0, hashlib.sha256(b"one").digest()), ("sitea", 2, b"x" * 32)])
    with pytest.raises(ValueError, match="tampered with"):
        assert_dense(conn.cursor(), "mainline", "sitea")


def test_a_dense_ledger_passes_the_same_check():
    rows = [("sitea", position, bytes(32)) for position in range(4)]
    assert assert_dense(FakeConnection(rows).cursor(), "mainline", "sitea") == 4
    assert assert_dense(FakeConnection([]).cursor(), "mainline", "siteb") == 0


def test_the_leaf_prefix_is_rfc_6962_and_a_leaf_is_not_an_interior_node():
    canon = b'{"kind":"merge"}'
    assert leaf_hash(canon) == hashlib.sha256(b"\x00" + canon).digest()
    assert leaf_hash(canon) != hashlib.sha256(canon).digest()


def test_a_short_hash_is_refused_because_a_ragged_chain_is_ambiguous():
    with pytest.raises(ValueError, match="prev_link_hash is 4 bytes"):
        link_hash(b"abcd", bytes(32))
    with pytest.raises(ValueError, match="leaf hash is 4 bytes"):
        link_hash(bytes(32), b"abcd")


@pytest.mark.parametrize(
    "sql",
    [
        "CREATE SEQUENCE mainline.ledger_seq",
        "CREATE TEMPORARY SEQUENCE s",
        "INSERT INTO t (seq) VALUES (nextval('s'))",
        "CREATE TABLE t (id SERIAL PRIMARY KEY)",
        "CREATE TABLE t (id INT8 DEFAULT unique_rowid())",
    ],
)
def test_every_way_of_reintroducing_a_sequence_is_refused(sql):
    with pytest.raises(ValueError, match="banned token"):
        assert_gap_free(sql)


def test_the_word_serializable_is_not_the_word_serial():
    # A substring test would refuse `SET TRANSACTION ISOLATION LEVEL SERIALIZABLE`,
    # which is the one statement every gate transaction must issue.
    assert_gap_free("SET TRANSACTION ISOLATION LEVEL SERIALIZABLE")
    assert_gap_free("SELECT coalesce(max(seq) + 1, 0) FROM mainline.ledger_leaf")
    assert len(BANNED_SQL_TOKENS) == 4
