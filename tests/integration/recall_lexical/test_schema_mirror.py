# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""The SQLite mirror must be a mirror.

The differential runs on SQLite when no cluster is reachable.  That is only worth anything if
the tables it runs against are the tables migrations ``0043`` to ``0045`` create.  A mirror that
had quietly gained a column, lost a ``NOT NULL`` or renamed a primary key would let the
differential pass against a schema the product does not have — which is the failure mode of
every "we test against a lightweight stand-in" arrangement, and the reason this file exists.

The check reads the **real migration files** (owned by ``recall-ddl-triggers``, consumed here)
and compares them to what SQLite actually built.  It compares structure, not text: the types
necessarily differ (``UUID``/``STRING``/``FLOAT8``/``INT8`` versus ``TEXT``/``REAL``/
``INTEGER``), and pretending otherwise would be a check that fails for the wrong reason.
"""

from __future__ import annotations

import re
import sqlite3
from pathlib import Path

import pytest
from conftest import LEX_MIGRATIONS, MIGRATIONS, SQLITE_DDL  # type: ignore[import-not-found]

TABLES = ("lex_posting", "lex_stats", "lex_doclen")


def migration_text(name: str) -> str:
    path: Path = MIGRATIONS / name
    return path.read_text(encoding="utf-8")


def columns_from_migration(name: str) -> list[str]:
    """Column names in declaration order, from the real migration file."""
    text = migration_text(name)
    body = text[text.index("(", text.index("CREATE TABLE")) :]
    columns: list[str] = []
    for line in body.splitlines():
        stripped = line.strip().lstrip("(")
        match = re.match(r"^([a-z_][a-z0-9_]*)\s+(UUID|STRING|FLOAT8|INT8)\b", stripped)
        if match is not None:
            columns.append(match.group(1))
    return columns


@pytest.fixture(scope="module")
def mirror() -> sqlite3.Connection:
    connection = sqlite3.connect(":memory:")
    connection.execute("ATTACH ':memory:' AS mainline")
    for ddl in SQLITE_DDL:
        connection.execute(ddl)
    return connection


@pytest.mark.parametrize(("table", "migration"), list(zip(TABLES, LEX_MIGRATIONS, strict=True)))
def test_the_mirror_has_the_migrations_columns(
    mirror: sqlite3.Connection, table: str, migration: str
) -> None:
    expected = columns_from_migration(migration)
    assert expected, f"could not parse any column out of {migration}"
    actual = [row[1] for row in mirror.execute(f"PRAGMA mainline.table_info({table})")]
    assert actual == expected


@pytest.mark.parametrize(("table", "migration"), list(zip(TABLES, LEX_MIGRATIONS, strict=True)))
def test_the_mirror_has_the_migrations_primary_key(
    mirror: sqlite3.Connection, table: str, migration: str
) -> None:
    text = migration_text(migration)
    match = re.search(r"PRIMARY KEY \(([^)]*)\)", text)
    assert match is not None, f"{migration} declares no PRIMARY KEY"
    expected = [part.strip() for part in match.group(1).split(",")]
    rows = list(mirror.execute(f"PRAGMA mainline.table_info({table})"))
    actual = [row[1] for row in sorted((r for r in rows if r[5]), key=lambda r: r[5])]
    assert actual == expected


@pytest.mark.parametrize(("table", "migration"), list(zip(TABLES, LEX_MIGRATIONS, strict=True)))
def test_every_column_is_not_null_in_both(
    mirror: sqlite3.Connection, table: str, migration: str
) -> None:
    """All three tables are wholly NOT NULL; a nullable ``weight`` would be a silent zero."""
    assert "NULL," not in migration_text(migration).replace("NOT NULL,", "")
    rows = list(mirror.execute(f"PRAGMA mainline.table_info({table})"))
    assert all(row[3] == 1 for row in rows), "a column in the mirror is nullable"


def test_the_migration_files_are_where_this_suite_thinks_they_are() -> None:
    for name in LEX_MIGRATIONS:
        assert (MIGRATIONS / name).is_file(), (
            f"{name} is missing. This band consumes the recall DDL band's migrations rather "
            "than restating them; if they moved, this suite is testing nothing."
        )


def test_the_lex_posting_key_order_is_the_one_the_query_depends_on() -> None:
    """``(site_id, term, event_id)``.

    The BM25 statement's ``WHERE site_id = … AND term IN (…)`` is written to match this key's
    prefix. If the DDL ever reorders it, the predicate stops building spans and channel D
    becomes a full scan with no test failing anywhere except the plan assertion.
    """
    text = migration_text("0043_lex_posting.sql")
    match = re.search(r"PRIMARY KEY \(([^)]*)\)", text)
    assert match is not None
    assert [p.strip() for p in match.group(1).split(",")] == ["site_id", "term", "event_id"]
