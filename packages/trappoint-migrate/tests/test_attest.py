# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""The schema fingerprint and the chain walk.

Two claims are under test and both are load-bearing elsewhere in the repository.

**The fingerprint is stable under the platform's own non-determinism.** CockroachDB
guarantees CREATE-before-ALTER ordering in `SHOW CREATE ALL TABLES` and nothing about
intra-category ordering. A fingerprint that changed when the server happened to return
two tables in a different order would flicker, and a flickering alarm is an ignored one.

**The chain distinguishes deletion from rewriting.** A gap means a row was deleted; a
`prev_fingerprint` mismatch means a row was rewritten. They are different findings
because they are different accusations.
"""

from __future__ import annotations

from typing import Any

import pytest

from trappoint_migrate.attest import ChainHead, fingerprint, stable_fingerprint, verify_chain
from trappoint_migrate.bootstrap import GENESIS_FINGERPRINT
from trappoint_migrate.errors import AttestationDrift

TABLES = "SHOW CREATE ALL TABLES"
TYPES = "SHOW CREATE ALL TYPES"
SCHEMAS = "SHOW CREATE ALL SCHEMAS"


class FakeCursor:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self._rows = rows

    def __enter__(self) -> FakeCursor:
        return self

    def __exit__(self, *exc: object) -> bool:
        return False

    def execute(self, *_: Any, **__: Any) -> None:
        return None

    def fetchall(self) -> list[dict[str, Any]]:
        return self._rows


class FakeConn:
    """Answers `fetch_all` from a table of (substring -> rows)."""

    def __init__(self, script: dict[str, list[dict[str, Any]]]) -> None:
        self.script = script
        self._pending: list[dict[str, Any]] = []

    def cursor(self, row_factory: Any = None) -> FakeCursor:  # noqa: ARG002
        return FakeCursor(self._pending)

    def _match(self, statement: str) -> list[dict[str, Any]]:
        for key, rows in self.script.items():
            if key in statement:
                return rows
        return []


class ScriptedConn(FakeConn):
    def cursor(self, row_factory: Any = None) -> FakeCursor:  # noqa: ARG002
        return _BindingCursor(self)


class _BindingCursor(FakeCursor):
    def __init__(self, conn: ScriptedConn) -> None:
        super().__init__([])
        self.conn = conn

    def execute(self, statement: Any, params: Any = None) -> None:  # noqa: ARG002
        self._rows = self.conn._match(str(statement))


def _schema_conn(
    tables: list[str], *, triggers: bool = True, routines: bool = True
) -> ScriptedConn:
    catalogue = []
    if triggers:
        catalogue.append({"proname": "pg_get_triggerdef"})
    if routines:
        catalogue.append({"proname": "pg_get_functiondef"})
    return ScriptedConn(
        {
            SCHEMAS: [{"create_statement": "CREATE SCHEMA mainline"}],
            TYPES: [],
            TABLES: [{"create_statement": t} for t in tables],
            "pg_catalog.pg_proc\n        WHERE proname IN": catalogue,
            "pg_get_triggerdef(t.oid)": [
                {"name": "trg_permit_merge_gate", "def": "CREATE TRIGGER trg_permit_merge_gate …"}
            ],
            "pg_get_functiondef(p.oid)": [
                {"name": "fn_check_project", "def": "CREATE FUNCTION fn_check_project() …"}
            ],
        }
    )


def test_fingerprint_is_insensitive_to_row_order() -> None:
    a = fingerprint(
        _schema_conn(["CREATE TABLE a ()", "CREATE TABLE b ()"]),  # type: ignore[arg-type]
        schema_prefixes=("mainline%",),
    )
    b = fingerprint(
        _schema_conn(["CREATE TABLE b ()", "CREATE TABLE a ()"]),  # type: ignore[arg-type]
        schema_prefixes=("mainline%",),
    )
    assert a.digest == b.digest


def test_fingerprint_is_insensitive_to_whitespace_reformatting() -> None:
    a = fingerprint(
        _schema_conn(["CREATE TABLE a (x INT8)"]),  # type: ignore[arg-type]
        schema_prefixes=("mainline%",),
    )
    b = fingerprint(
        _schema_conn(["CREATE   TABLE\n  a  (x    INT8)"]),  # type: ignore[arg-type]
        schema_prefixes=("mainline%",),
    )
    assert a.digest == b.digest


def test_fingerprint_changes_when_the_schema_changes() -> None:
    a = fingerprint(
        _schema_conn(["CREATE TABLE a ()"]),  # type: ignore[arg-type]
        schema_prefixes=("mainline%",),
    )
    b = fingerprint(
        _schema_conn(["CREATE TABLE a (x INT8)"]),  # type: ignore[arg-type]
        schema_prefixes=("mainline%",),
    )
    assert a.digest != b.digest


def test_grade_is_weak_when_pg_get_triggerdef_is_absent() -> None:
    # GT-05's fallback. The claim softens IN THE DATA: a weakly-attested run must never
    # be indistinguishable from a strongly-attested one.
    weak = fingerprint(
        _schema_conn(["CREATE TABLE a ()"], triggers=False),  # type: ignore[arg-type]
        schema_prefixes=("mainline%",),
    )
    assert weak.grade == "weak"
    assert "triggers" not in weak.parts

    strong = fingerprint(
        _schema_conn(["CREATE TABLE a ()"]),  # type: ignore[arg-type]
        schema_prefixes=("mainline%",),
    )
    assert strong.grade == "strong"
    assert "triggers" in strong.parts
    assert "routines" in strong.parts


def test_the_trigger_definition_is_inside_the_hash() -> None:
    # This is the self-attesting gate. Change the trigger body, change the fingerprint.
    base = _schema_conn(["CREATE TABLE a ()"])
    altered = _schema_conn(["CREATE TABLE a ()"])
    altered.script["pg_get_triggerdef(t.oid)"] = [
        {"name": "trg_permit_merge_gate", "def": "CREATE TRIGGER trg_permit_merge_gate WEAKENED"}
    ]
    assert (
        fingerprint(base, schema_prefixes=("mainline%",)).digest  # type: ignore[arg-type]
        != fingerprint(altered, schema_prefixes=("mainline%",)).digest  # type: ignore[arg-type]
    )


def test_stable_fingerprint_accepts_a_deterministic_server() -> None:
    conn = _schema_conn(["CREATE TABLE a ()"])
    assert stable_fingerprint(conn, schema_prefixes=("mainline%",)).grade == "strong"  # type: ignore[arg-type]


def test_stable_fingerprint_refuses_a_flickering_one() -> None:
    class Flickering(ScriptedConn):
        def __init__(self) -> None:
            super().__init__({})
            self.calls = 0

        def _match(self, statement: str) -> list[dict[str, Any]]:
            if "pg_proc\n        WHERE proname IN" in statement:
                return [{"proname": "pg_get_triggerdef"}, {"proname": "pg_get_functiondef"}]
            if statement.strip() == TABLES:
                self.calls += 1
                return [{"create_statement": f"CREATE TABLE t{self.calls} ()"}]
            return []

    with pytest.raises(AttestationDrift, match="not stable"):
        stable_fingerprint(Flickering(), schema_prefixes=("mainline%",))  # type: ignore[arg-type]


def _row(ordinal: int, prev: int, fp: bytes, prev_fp: bytes) -> dict[str, Any]:
    return {
        "ordinal": ordinal,
        "prev_ordinal": prev,
        "fingerprint": fp,
        "prev_fingerprint": prev_fp,
        "kind": "apply",
        "version": f"000{ordinal}_x",
    }


def _chain_conn(rows: list[dict[str, Any]]) -> ScriptedConn:
    return ScriptedConn({"FROM trappoint.schema_attestation": rows})


def test_an_intact_chain_reports_nothing() -> None:
    rows = [
        _row(0, -1, GENESIS_FINGERPRINT, GENESIS_FINGERPRINT),
        _row(1, 0, b"\x11" * 32, GENESIS_FINGERPRINT),
        _row(2, 1, b"\x22" * 32, b"\x11" * 32),
    ]
    assert verify_chain(_chain_conn(rows)) == []  # type: ignore[arg-type]


def test_a_gap_is_reported_as_a_deletion_and_only_as_that() -> None:
    # One finding per accusation. A gap ENTAILS a fingerprint mismatch across the hole,
    # so also reporting "a row was rewritten" would put a more serious claim in a report
    # where nothing was rewritten.
    rows = [
        _row(0, -1, GENESIS_FINGERPRINT, GENESIS_FINGERPRINT),
        _row(2, 1, b"\x22" * 32, b"\x11" * 32),
    ]
    findings = verify_chain(_chain_conn(rows))  # type: ignore[arg-type]
    assert any("deleted" in f for f in findings)
    assert not any("rewritten" in f for f in findings)


def test_a_rewritten_row_is_reported_separately_from_a_gap() -> None:
    rows = [
        _row(0, -1, GENESIS_FINGERPRINT, GENESIS_FINGERPRINT),
        _row(1, 0, b"\x11" * 32, b"\xaa" * 32),
    ]
    findings = verify_chain(_chain_conn(rows))  # type: ignore[arg-type]
    assert any("rewritten" in f for f in findings)
    assert not any("deleted" in f for f in findings)


def test_an_empty_chain_is_a_deleted_genesis() -> None:
    assert verify_chain(_chain_conn([])) == [  # type: ignore[arg-type]
        "the attestation chain is empty; the genesis row was deleted"
    ]


def test_chain_head_dataclass_is_frozen() -> None:
    head = ChainHead(ordinal=3, fingerprint=b"\x00" * 32, grade="strong", kind="apply", version="x")
    with pytest.raises(AttributeError):
        head.ordinal = 4  # type: ignore[misc]
