# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
"""The fixture DDL must not drift, and the integration lane must not pretend.

This worker CONSUMES ``mainline.activity_node`` and ``mainline.event``, reserved as
migrations 0032-0033 by the ancestry/ingest lead.  They are not in the repository yet — the
migration band jumps 0023 to 0040 — so there is nothing for an integration test of the LMB
and bond writers to run against.  The brief's instruction is explicit: run against a
committed fixture DDL and **mark the integration lane skipped, never fake the table**.

So this module does two things and no third thing:

1. It asserts the committed fixture DDL's ``event_cue`` and ``event_bond`` column sets match
   migrations 0040 and 0046 exactly, and that the writers' INSERT statements name only
   columns those tables have.  All of it is a static read; no cluster is required, so this
   check runs everywhere and cannot rot quietly.
2. It **skips**, with a reason naming the missing migrations, the lane that would exercise
   the writers against a live CockroachDB.  A skip that says why is a debt; a passing test
   over a stand-in table would be a lie with a green tick on it.
"""

from __future__ import annotations

import re

import pytest
from mainline_recall_agent.taxonomy.sql import (
    INSERT_ACTIVITY_NODE,
    INSERT_EVENT_BOND,
    INSERT_EVENT_CUE,
)

from .conftest import FIXTURES, MIGRATIONS

#: Keywords that begin a table-level constraint or index clause rather than a column.
_NOT_A_COLUMN = frozenset(
    {
        "constraint",
        "primary",
        "unique",
        "index",
        "inverted",
        "vector",
        "foreign",
        "check",
        "family",
    }
)

_CREATE_RE = re.compile(
    r"CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?([a-z_]+\.[a-z_]+)\s*\(", re.IGNORECASE
)


def _strip_comments(sql: str) -> str:
    """Remove ``--`` comments before any bracket or comma scanning.

    Not cosmetic: the §5.4 DDL carries ``-- 1 fonds, 2 series, 3 file`` and
    ``-- ONE ROW PER ARCHIVAL LEVEL (LMB)``, whose comma and parenthesis are otherwise
    indistinguishable from structure, and the parser silently produced columns named "2"
    and "3" before this existed.
    """
    return re.sub(r"--[^\n]*", "", sql)


def _table_body(sql: str, table: str) -> str:
    """Extract the parenthesised body of ``CREATE TABLE <table> ( ... )``."""
    sql = _strip_comments(sql)
    for match in _CREATE_RE.finditer(sql):
        if match.group(1).lower() != table:
            continue
        depth = 1
        start = match.end()
        for position in range(start, len(sql)):
            character = sql[position]
            if character == "(":
                depth += 1
            elif character == ")":
                depth -= 1
                if depth == 0:
                    return sql[start:position]
    raise AssertionError(f"{table} not found")


def _columns(sql: str, table: str) -> list[str]:
    body = _table_body(sql, table)
    columns: list[str] = []
    depth = 0
    current: list[str] = []
    for character in body:
        if character == "(":
            depth += 1
        elif character == ")":
            depth -= 1
        if character == "," and depth == 0:
            current, chunk = [], "".join(current)
            columns.append(chunk)
            continue
        current.append(character)
    columns.append("".join(current))

    names: list[str] = []
    for chunk in columns:
        stripped = chunk.strip()
        if not stripped:
            continue
        head = stripped.split()[0]
        if head.lower() in _NOT_A_COLUMN:
            continue
        names.append(head.lower())
    return names


def _insert_columns(statement: str) -> list[str]:
    body = statement.split("(", 1)[1].split(")", 1)[0]
    return [name.strip().lower() for name in body.split(",")]


@pytest.fixture(scope="module")
def fixture_sql() -> str:
    return (FIXTURES / "fixture_ddl.sql").read_text(encoding="utf-8")


@pytest.mark.parametrize(
    ("table", "migration"),
    [
        ("mainline.event_cue", "0040_event_cue.sql"),
        ("mainline.event_bond", "0046_event_bond.sql"),
    ],
)
def test_fixture_ddl_matches_the_committed_migration(
    fixture_sql: str, table: str, migration: str
) -> None:
    """A fixture that has drifted from the migration tests a shape that is not deployed."""
    source = MIGRATIONS / migration
    assert source.exists(), f"{migration} is owned by recall-ddl-triggers and must exist"
    deployed = _columns(source.read_text(encoding="utf-8"), table)
    fixture = _columns(fixture_sql, table)
    assert fixture == deployed, (
        f"{table}: the fixture DDL and {migration} disagree on columns.\n"
        f"  migration: {deployed}\n  fixture:   {fixture}"
    )


@pytest.mark.parametrize(
    ("statement", "table"),
    [
        (INSERT_ACTIVITY_NODE, "mainline.activity_node"),
        (INSERT_EVENT_CUE, "mainline.event_cue"),
        (INSERT_EVENT_BOND, "mainline.event_bond"),
    ],
)
def test_insert_statements_name_only_columns_that_exist(
    fixture_sql: str, statement: str, table: str
) -> None:
    available = set(_columns(fixture_sql, table))
    named = _insert_columns(statement)
    assert set(named) <= available, f"{table}: {sorted(set(named) - available)}"
    assert len(named) == statement.count("%s")


def test_the_cue_insert_leaves_generated_columns_to_the_database(fixture_sql: str) -> None:
    named = set(_insert_columns(INSERT_EVENT_CUE))
    assert "cue_id" not in named, "cue_id has a gen_random_uuid() default; it is the DB's"
    assert "tsv" not in named, "tsv is a STORED computed column over cue_text"
    # Everything else on the table is written, so a new NOT NULL column breaks this loudly
    # rather than at first contact with a cluster.
    assert named == set(_columns(fixture_sql, "mainline.event_cue")) - {"cue_id", "tsv"}


def _consumed_migrations() -> list[str]:
    """Return the names of the consumed migrations that are present, if any."""
    found: list[str] = []
    for pattern in ("0032_*.sql", "0033_*.sql"):
        found.extend(path.name for path in sorted(MIGRATIONS.glob(pattern)))
    return found


@pytest.mark.integration
def test_lmb_and_bond_writers_against_a_live_cluster() -> None:
    """The lane that would prove the writers end to end. Skipped, and the reason adapts.

    Two distinct skips, because they are two distinct debts and conflating them is how a
    skip outlives its reason. Before 0032/0033 land there is nothing to write against at
    all. After they land the blocker is only that this lane has not been built yet, and the
    message says so — loudly enough to be found by grepping for it, without turning another
    worker's correct migration into a red suite here.
    """
    present = _consumed_migrations()
    if present:
        pytest.skip(
            "TAXONOMY INTEGRATION LANE OWED: migrations "
            f"{present} have landed, so mainline.activity_node and mainline.event now "
            "exist and the LMB/bond writers can be exercised against a real cluster. "
            "This lane must be built against them (apply the migrations, insert a fonds / "
            "series / file chain and an event, run LevelMaterialisedBondWriter and "
            "BondWriter, assert the row counts and the unique-constraint behaviour). "
            "Until then the writers are proven only by the unit suite."
        )
    pytest.skip(
        "taxonomy integration lane not runnable: mainline.activity_node (0032) and "
        "mainline.event (0033) are not migrated in this repository, so there is no "
        "deployed table for the LMB and bond writers to insert into. "
        "tests/fixtures/recall_taxonomy/fixture_ddl.sql carries the ARCHITECTURE 5.4 "
        "shapes so the DDL is applicable in isolation, but applying a fixture and calling "
        "the result an integration test would be faking the table."
    )


def test_the_fixture_ddl_carries_no_enforcement_of_its_own(fixture_sql: str) -> None:
    """Nothing in a taxonomy test may pass because of something the fixture did."""
    lowered = fixture_sql.lower()
    assert "create trigger" not in lowered
    assert "create function" not in lowered
    assert "create or replace" not in lowered
    # Every statement is IF NOT EXISTS, so the real migrations win when they exist.
    creates = re.findall(r"create\s+(table|schema)\s+(if\s+not\s+exists\s+)?", lowered)
    assert creates, "the fixture must actually create something"
    for _, guard in creates:
        assert guard, "every CREATE in the fixture must be IF NOT EXISTS"
