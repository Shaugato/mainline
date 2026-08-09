# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
"""Sequenced-ness is derived, and the source is what proves it.

The headline test in this file is not about batching at all. It reads every module in the
package and asserts that **no statement issues an UPDATE or a DELETE against any
``ledger_*`` object**. That is the mechanical form of a claim the whole custody domain
rests on: the ledger write path is ``INSERT`` + ``SELECT``, which is why the
``mainline_ledger`` role holds exactly those grants, why ``agent_relay`` holds ``INSERT``
and not even ``SELECT``, and why attack A1 (`delete_and_relink`) has no role in this
system that can already perform it.

A grep is a weak test in general and a strong one here, because the thing being asserted
is the *absence* of a capability, and absence is exactly what a behavioural test cannot
demonstrate.
"""

from __future__ import annotations

import re
from contextlib import contextmanager
from dataclasses import fields
from pathlib import Path
from uuid import uuid4

import pytest
from mainline_sequencer import append, batch, handler, lease, sink

SRC = Path(__file__).resolve().parents[1] / "src" / "mainline_sequencer"
MODULES = (append, batch, handler, lease, sink)

SITE = "blk-07"

# `UPDATE <target>` / `DELETE FROM <target>` in a STATEMENT: the target is captured
# loosely, because a statement is already known to be SQL.
_MUTATION_IN_SQL = re.compile(r"\b(UPDATE|DELETE\s+FROM)\s+(\S+)", re.IGNORECASE)

# The same over raw source, where the surrounding text is prose as often as it is SQL.
# The target must be SCHEMA-QUALIFIED, which every statement in this package's SQL is and
# which the sentence "there is no UPDATE and no DELETE against any ledger_* object" is
# not. A guard that fired on its own rationale would force the rationale out of the file.
_MUTATION_IN_SOURCE = re.compile(
    r"\b(UPDATE|DELETE\s+FROM)\s+([A-Za-z_][A-Za-z0-9_]*\.[A-Za-z0-9_.]*)"
)

# CU-2's ban, restated locally. `trappoint migrate lint` enforces it over the migration
# tree; this asserts the client never smuggles one into a statement either.
_BANNED_SEQUENCE_CONSTRUCTS = ("nextval(", "create sequence", "unique_rowid(", " serial ")


def _sources() -> dict[str, str]:
    return {path.name: path.read_text(encoding="utf-8") for path in sorted(SRC.glob("*.py"))}


def _sql_constants() -> dict[str, str]:
    """Every module-level SQL string in the package, by qualified name.

    The banned-construct check runs over these rather than over raw source, because the
    prose in `append.py` NAMES the banned constructs in order to explain why they are
    banned — and a guard that cannot tell a statement from an explanation of a statement
    would force the explanation out of the file.
    """
    found: dict[str, str] = {}
    for module in MODULES:
        for name in dir(module):
            if not name.isupper():
                continue
            value = getattr(module, name)
            if isinstance(value, str) and re.search(r"\b(SELECT|INSERT|UPDATE)\b", value):
                found[f"{module.__name__}.{name}"] = value
    return found


# ── The claim ──────────────────────────────────────────────────────────────────────────


def test_no_update_against_any_ledger_table() -> None:
    """Every mutation in this package targets ``mainline_ops.sequencer_lease``, and nothing else.

    The lease is the one genuinely mutable object in the custody plane and it holds no
    evidence: losing every row costs one sequencing cycle, because correctness lives in
    ``ledger_leaf_pkey`` and ``ledger_linear``, which hold at any isolation level and with
    no lease at all.
    """
    offenders: list[str] = []
    for name, statement in _sql_constants().items():
        for verb, target in _MUTATION_IN_SQL.findall(statement):
            if target.lower().startswith("mainline_ops.sequencer_lease"):
                continue
            offenders.append(f"{name}: {verb} {target}")
    assert not offenders, (
        "the ledger write path must be INSERT + SELECT only; found:\n  " + "\n  ".join(offenders)
    )


def test_no_ledger_table_is_ever_a_mutation_target_anywhere_in_the_source() -> None:
    """The same claim over raw source, so an inline or interpolated statement cannot hide.

    Stated the other way round from the test above as well, so that renaming the lease
    table cannot weaken the guard by widening its allowlist.
    """
    for name, text in _sources().items():
        for verb, target in _MUTATION_IN_SOURCE.findall(text):
            assert "ledger_" not in target.lower(), f"{name}: {verb} {target}"
            assert target.lower().startswith("mainline_ops."), f"{name}: {verb} {target}"


def test_no_banned_sequence_construct_appears_in_any_statement() -> None:
    """CU-2: a gap MEANS tampering only while nothing in the path can produce a legitimate one.

    ``CREATE SEQUENCE`` **succeeds** on the target cluster (``docs/adr/0002`` F4), so the
    ban is load-bearing rather than decorative — nothing but a lint and this assertion
    stands between the ledger and a numbering whose gaps mean nothing.
    """
    statements = _sql_constants()
    assert statements, "the SQL constants are the interface; finding none means this guard is dead"
    for name, statement in statements.items():
        lowered = f" {statement.lower()} "
        for banned in _BANNED_SEQUENCE_CONSTRUCTS:
            assert banned not in lowered, f"{name} contains the banned construct {banned!r}"


def test_seq_is_derived_in_transaction_and_never_read_from_a_generator() -> None:
    """The head read IS ``COALESCE(max(seq), -1) + 1``, with the predecessor from the same row."""
    normalised = " ".join(append.READ_HEAD_SQL.split())
    assert "SELECT seq, link_hash FROM mainline.ledger_leaf" in normalised
    assert "ORDER BY seq DESC LIMIT 1" in normalised


# ── The anti-join ──────────────────────────────────────────────────────────────────────


def test_selection_is_an_anti_join_with_a_total_order() -> None:
    normalised = " ".join(batch.SELECT_UNSEQUENCED.split())
    assert "NOT EXISTS (SELECT 1 FROM mainline.ledger_leaf l" in normalised
    assert "WHERE l.site_code = i.site_code AND l.entry_id = i.entry_id" in normalised
    # `hlc` alone is not a total order — the clock is logical and its resolution is
    # finite — and an unstable batch order makes a replay produce a different tree from
    # the same intake.
    assert "ORDER BY i.hlc, i.entry_id" in normalised
    assert "LIMIT %s" in normalised
    assert "sequenced" not in normalised.replace("ledger_leaf", ""), (
        "there is no `sequenced` flag and there must never be one"
    )


def test_the_projected_columns_match_the_row_in_order() -> None:
    """``SELECT i.*`` would let a new intake column silently reshape the tuple this unpacks."""
    projected = re.findall(r"i\.([a-z_]+),?\n", batch.SELECT_UNSEQUENCED.split("FROM")[0])
    assert projected == [f.name for f in fields(batch.IntakeRow)]


def test_the_batch_carries_no_payload_and_no_canon_bytes() -> None:
    """The appender never re-hashes a payload.

    ``leaf_hash`` was computed by the CLIENT under RFC 8785 at intake and is copied into
    ``ledger_leaf`` verbatim. A sequencer that recomputed it would be a second
    implementation of the canonicaliser standing between the bytes a stranger can
    reproduce and the tree those bytes are committed to.
    """
    names = {f.name for f in fields(batch.IntakeRow)}
    assert "payload" not in names
    assert "canon_bytes" not in names


@pytest.mark.parametrize("limit", [0, -1, batch.MAX_BATCH_SIZE + 1, 100_000])
def test_batch_size_outside_the_permitted_range_is_refused(limit) -> None:
    with pytest.raises(batch.BatchSizeRefused):
        batch.unsequenced(_FakeConn([]), site_code=SITE, limit=limit)


def test_rows_are_returned_in_the_declared_shape() -> None:
    entry_id = uuid4()
    row = (entry_id, SITE, "disposition", b"\x11" * 32, 1, False, "auth0|4f2c", "human")
    rows = batch.unsequenced(_FakeConn([row]), site_code=SITE, limit=8)
    assert rows == (
        batch.IntakeRow(
            entry_id=entry_id,
            site_code=SITE,
            entry_kind="disposition",
            leaf_hash=b"\x11" * 32,
            payload_ver=1,
            is_sandbox=False,
            actor="auth0|4f2c",
            actor_kind="human",
        ),
    )


class _FakeCursor:
    def __init__(self, rows) -> None:
        self._rows = rows

    def __enter__(self) -> _FakeCursor:
        return self

    def __exit__(self, *exc: object) -> bool:
        return False

    def execute(self, sql, params=None) -> None:  # noqa: ARG002
        self.sql = sql

    def fetchall(self):
        return list(self._rows)


class _FakeConn:
    def __init__(self, rows) -> None:
        self._rows = rows

    def cursor(self) -> _FakeCursor:
        return _FakeCursor(self._rows)

    @contextmanager
    def transaction(self):
        yield self
