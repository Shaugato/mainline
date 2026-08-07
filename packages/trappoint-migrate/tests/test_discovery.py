# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""Ordering, hashing, and the shapes the runner refuses to read."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from trappoint_migrate.discovery import discover, statement_count
from trappoint_migrate.errors import MigrationTreeInvalid


def write(root: Path, name: str, body: str = "-- MI01\nCREATE TABLE t ();\n") -> Path:
    path = root / name
    path.write_text(body, encoding="utf-8")
    return path


def test_absent_directory_is_an_empty_stream_not_an_error(tmp_path: Path) -> None:
    # A binding whose SQL has not been rendered yet is a normal state on the way to K1.
    assert discover(tmp_path / "nope") == []


def test_empty_directory_is_an_empty_stream(tmp_path: Path) -> None:
    assert discover(tmp_path) == []


def test_letter_suffixes_order_within_a_slot(tmp_path: Path) -> None:
    # Ruling D7: `0071a` before `0071b` before `0072`, lexicographically on the FULL
    # stem. Parsing the number and sorting on it would make 0071a and 0071b collide.
    for name in ("0072_after.sql", "0071b_second.sql", "0071a_first.sql", "0009_early.sql"):
        write(tmp_path, name)
    assert [m.version for m in discover(tmp_path)] == [
        "0009_early",
        "0071a_first",
        "0071b_second",
        "0072_after",
    ]


def test_up_sql_suffix_is_accepted_and_stripped(tmp_path: Path) -> None:
    write(tmp_path, "0001_schema.up.sql")
    (migration,) = discover(tmp_path)
    assert migration.version == "0001_schema"


def test_down_migrations_are_refused(tmp_path: Path) -> None:
    write(tmp_path, "0001_schema.up.sql")
    write(tmp_path, "0001_schema.down.sql", "DROP SCHEMA mainline;")
    with pytest.raises(MigrationTreeInvalid, match="forward-only"):
        discover(tmp_path)


def test_unparseable_filename_is_refused(tmp_path: Path) -> None:
    write(tmp_path, "create_the_thing.sql")
    with pytest.raises(MigrationTreeInvalid, match="NNNN"):
        discover(tmp_path)


def test_duplicate_version_across_suffixes_is_refused(tmp_path: Path) -> None:
    write(tmp_path, "0001_schema.sql")
    write(tmp_path, "0001_schema.up.sql")
    with pytest.raises(MigrationTreeInvalid, match="two files claim"):
        discover(tmp_path)


def test_sha256_is_over_the_file_bytes(tmp_path: Path) -> None:
    body = "-- MI03\nCREATE TABLE t ();\n"
    write(tmp_path, "0001_t.sql", body)
    (migration,) = discover(tmp_path)
    assert migration.sha256 == hashlib.sha256(body.encode("utf-8")).digest()


def test_cited_invariants_come_from_the_header_only(tmp_path: Path) -> None:
    write(
        tmp_path,
        "0001_t.sql",
        "-- MI02, I03: the gate\nCREATE TABLE t (x INT8);\n-- MI30 mentioned late\n",
    )
    (migration,) = discover(tmp_path)
    assert migration.cited_invariants == ("MI02", "I03")


@pytest.mark.parametrize(
    ("sql", "expected"),
    [
        ("CREATE TABLE t ();", 1),
        ("CREATE TABLE t ();\n", 1),
        ("CREATE TABLE t (); CREATE TABLE u ();", 2),
        ("-- comment only\n", 0),
        ("CREATE FUNCTION f() RETURNS INT8 AS $$ BEGIN RETURN 1; END; $$ LANGUAGE plpgsql;", 1),
        ("INSERT INTO t VALUES ('a;b');", 1),
    ],
)
def test_statement_count_ignores_semicolons_inside_quoted_regions(sql: str, expected: int) -> None:
    assert statement_count(sql) == expected
