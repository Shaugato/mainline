# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""RC-00 — the shape checks that need no cluster, and would have caught a real defect.

Every other module in this directory needs a running CockroachDB. This one does not, and it
exists because the machine the recall band was written on could not reach one: Docker's daemon
was down and there was no ``cockroach`` binary. A band that can only be checked by a run that
cannot happen is a band nobody has checked.

Two of these assertions are not style. They are the two platform facts that were got wrong on
the first pass and found by reading the vendor's documentation rather than by running anything:

* **`(NEW).column` for reads.** CockroachDB's Triggers page carries a known limitation — *OLD and
  NEW must be wrapped in parentheses when accessing column names* — and its own v26.2 examples
  read ``(NEW).wage`` while assigning ``NEW.wage := (NEW).wage + 5``. ARCHITECTURE §5.11's
  trigger bodies are written in the unparenthesised PostgreSQL style throughout, so this is a
  transcription trap the whole deployment walks into once per trigger.

* **A trigger function may only name columns its own table has.** CockroachDB compiles PL/pgSQL
  through the optimizer with ``NEW`` bound to the trigger table's row type, so a reference in a
  branch that can never execute is still plausibly resolved when the trigger is created. Whether
  it actually is remains UNVERIFIED here — which is exactly why the code must not depend on the
  answer, and why this test refuses the shape that would.

The third is ARCHITECTURE §18's own CI rule (every migration cites an invariant), and the fourth
proves the statement splitter that `conftest` applies migrations with never cuts a ``$$`` body.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from _schema_support import (
    PREREQ_DIR,
    RECALL_MIGRATION_NUMBERS,
    recall_migration_files,
    split_statements,
)

pytestmark = pytest.mark.shape


# ── parsing, deliberately narrow ─────────────────────────────────────────────────────────────
#
# These regexes understand the band's own files and nothing else. A general SQL parser would be
# a second implementation of CockroachDB's grammar and would fail differently from it; a narrow
# one either matches this band or fails loudly, which is the honest failure direction for a test.

_CREATE_TABLE = re.compile(
    r"CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?([A-Za-z_][\w.]*)\s*\(", re.IGNORECASE
)
_ADD_COLUMN = re.compile(
    r"ALTER\s+TABLE\s+([A-Za-z_][\w.]*)(.*)", re.IGNORECASE | re.DOTALL
)
_ADD_COLUMN_ITEM = re.compile(r"ADD\s+COLUMN\s+(\w+)", re.IGNORECASE)
_CREATE_FUNCTION = re.compile(
    r"CREATE\s+(?:OR\s+REPLACE\s+)?FUNCTION\s+([A-Za-z_][\w.]*)\s*\(\s*\)", re.IGNORECASE
)
_CREATE_TRIGGER = re.compile(
    r"CREATE\s+TRIGGER\s+(\w+)\s+(.*?)\s+ON\s+([A-Za-z_][\w.]*)\s+"
    r"FOR\s+EACH\s+ROW\s+EXECUTE\s+FUNCTION\s+([A-Za-z_][\w.]*)\s*\(\s*\)",
    re.IGNORECASE | re.DOTALL,
)
#: Non-greedy on purpose: 0114 carries two `$$` bodies and a greedy match would swallow the
#: statement boundary between them, which is precisely the mistake the splitter must not make.
_BODY = re.compile(r"\$\$(.*?)\$\$", re.DOTALL)

#: A leading token that means "this item of a CREATE TABLE body is not a column definition".
_NOT_A_COLUMN = frozenset(
    {
        "CONSTRAINT", "PRIMARY", "UNIQUE", "CHECK", "FOREIGN", "EXCLUDE",
        "INDEX", "INVERTED", "VECTOR", "FAMILY", "LIKE",
    }
)


def _strip_comments(sql: str) -> str:
    sql = re.sub(r"/\*.*?\*/", " ", sql, flags=re.DOTALL)
    return re.sub(r"--[^\n]*", " ", sql)


def _balanced_body(sql: str, open_paren: int) -> str:
    """The text between a `(` at ``open_paren`` and its matching `)`."""
    depth = 0
    for i in range(open_paren, len(sql)):
        if sql[i] == "(":
            depth += 1
        elif sql[i] == ")":
            depth -= 1
            if depth == 0:
                return sql[open_paren + 1 : i]
    raise AssertionError("unbalanced parentheses in a CREATE TABLE body")


def _top_level_items(body: str) -> list[str]:
    items, depth, start = [], 0, 0
    for i, ch in enumerate(body):
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        elif ch == "," and depth == 0:
            items.append(body[start:i])
            start = i + 1
    items.append(body[start:])
    return [item.strip() for item in items if item.strip()]


def _columns_of(statement: str) -> tuple[str, set[str]] | None:
    match = _CREATE_TABLE.search(statement)
    if match is None:
        return None
    body = _balanced_body(statement, match.end() - 1)
    columns = set()
    for item in _top_level_items(body):
        first = item.split()[0]
        if first.upper() not in _NOT_A_COLUMN:
            columns.add(first.lower())
    return match.group(1).lower(), columns


def _column_map() -> dict[str, set[str]]:
    """Every table the band creates, plus the consumed-table fixture, plus later ADD COLUMNs."""
    tables: dict[str, set[str]] = {}
    sources = [PREREQ_DIR / "00_consumed_tables.sql", *recall_migration_files()]
    for path in sources:
        for statement in split_statements(_strip_comments(path.read_text(encoding="utf-8"))):
            found = _columns_of(statement)
            if found is not None:
                name, columns = found
                tables.setdefault(name, set()).update(columns)
                continue
            altered = _ADD_COLUMN.search(statement)
            if altered is not None:
                added = _ADD_COLUMN_ITEM.findall(altered.group(2))
                if added:
                    tables.setdefault(altered.group(1).lower(), set()).update(
                        a.lower() for a in added
                    )
    return tables


def _function_bodies() -> dict[str, str]:
    bodies: dict[str, str] = {}
    for path in recall_migration_files():
        for statement in split_statements(path.read_text(encoding="utf-8")):
            named = _CREATE_FUNCTION.search(statement)
            body = _BODY.search(statement)
            if named is not None and body is not None:
                bodies[named.group(1).lower()] = body.group(1)
    return bodies


def _triggers() -> list[tuple[str, str, str, Path]]:
    """(trigger_name, table, function, file) for every CREATE TRIGGER in the band."""
    found: list[tuple[str, str, str, Path]] = []
    for path in recall_migration_files():
        for statement in split_statements(_strip_comments(path.read_text(encoding="utf-8"))):
            match = _CREATE_TRIGGER.search(statement)
            if match is not None:
                found.append(
                    (match.group(1), match.group(3).lower(), match.group(4).lower(), path)
                )
    return found


# ── the file band itself ─────────────────────────────────────────────────────────────────────


def test_rc00a_every_reserved_migration_exists_exactly_once() -> None:
    files = recall_migration_files()  # raises on a missing or duplicated number
    assert len(files) == len(RECALL_MIGRATION_NUMBERS)
    numbers = [int(p.name.split("_", 1)[0]) for p in files]
    assert numbers == sorted(numbers), "the band is not in application order"


@pytest.mark.parametrize("path", recall_migration_files(), ids=lambda p: p.name)
def test_rc00b_headers_licence_and_invariant_citation(path: Path) -> None:
    """§18: *every migration file cites at least one invariant ID*, enforced by CI."""
    text = path.read_text(encoding="utf-8")
    assert "SPDX-FileCopyrightText" in text, "no REUSE copyright header"
    assert "SPDX-License-Identifier: FSL-1.1-ALv2" in text, "wrong or missing licence header"
    assert re.search(r"\bMI\d\d\b", text), "no invariant id cited (ARCHITECTURE §18)"
    assert not (path.parent / (path.stem + ".down.sql")).exists(), "forward-only band"


@pytest.mark.parametrize("path", recall_migration_files(), ids=lambda p: p.name)
def test_rc00c_the_splitter_never_cuts_a_dollar_quoted_body(path: Path) -> None:
    """The property `conftest` relies on to apply one statement per transaction."""
    statements = split_statements(path.read_text(encoding="utf-8"))
    assert statements, f"{path.name} contains no SQL statement"
    for statement in statements:
        assert statement.count("$$") % 2 == 0, (
            f"{path.name} was split through a $$ body:\n{statement[-400:]}"
        )
    # Every function body in the file survives intact, character for character.
    whole = path.read_text(encoding="utf-8")
    for body in _BODY.findall(whole):
        assert any(body in statement for statement in statements), (
            f"{path.name}: a PL/pgSQL body did not survive splitting"
        )


@pytest.mark.parametrize("path", recall_migration_files(), ids=lambda p: p.name)
def test_rc00d_banned_platform_constructs_are_absent(path: Path) -> None:
    """No sequences anywhere: the ledger is gap-free by CAS, so a gap MEANS tampering."""
    code = _strip_comments(path.read_text(encoding="utf-8"))
    for banned in ("CREATE SEQUENCE", "nextval", "unique_rowid"):
        assert banned.lower() not in code.lower(), f"{banned} is banned in this deployment"
    assert not re.search(r"\bSERIAL\b", code, re.IGNORECASE), "SERIAL is banned"
    assert not re.search(r"\bCREATE\s+VECTOR\s+INDEX\b", code, re.IGNORECASE), (
        "vector indexes are declared INLINE at CREATE TABLE on an EMPTY table; a standalone "
        "CREATE VECTOR INDEX backfills and blocks writes"
    )


# ── §5.11 trigger style, and the two platform rules ──────────────────────────────────────────


@pytest.mark.parametrize("function", sorted(_function_bodies()), ids=lambda f: f)
def test_rc00e_trigger_style_rules(function: str) -> None:
    """§5.11: no `FOR … IN`, no FOREACH, no EXECUTE, no PERFORM, no CASE.

    Not house style — CockroachDB's PL/pgSQL does not implement FOR cursor loops, FOREACH,
    PERFORM, EXECUTE, GET DIAGNOSTICS or CASE statements at all.
    """
    body = _strip_comments(_function_bodies()[function])
    for banned in (
        r"\bFOR\b[^;]*\bIN\b", r"\bFOREACH\b", r"\bPERFORM\b",
        r"\bEXECUTE\b", r"\bCASE\b", r"\bGET\s+DIAGNOSTICS\b",
    ):
        assert not re.search(banned, body, re.IGNORECASE), (
            f"{function} uses a construct §5.11 forbids and CockroachDB lacks: {banned}"
        )


@pytest.mark.parametrize("function", sorted(_function_bodies()), ids=lambda f: f)
def test_rc00f_new_and_old_columns_are_parenthesised_for_reads(function: str) -> None:
    """The known limitation, as a machine check. This is the bug this file was written for.

    Reads must be ``(NEW).col``. Assignment targets must be bare ``NEW.col :=`` — that is the
    form CockroachDB's own example uses, so both halves are asserted rather than one.
    """
    body = _strip_comments(_function_bodies()[function])
    offenders = [
        match.group(0)
        for match in re.finditer(r"(?<![.\w)])(NEW|OLD)\.(\w+)(\s*:?=?)", body)
        if not match.group(3).strip().startswith(":=")
    ]
    assert not offenders, (
        f"{function} reads {offenders} unparenthesised. CockroachDB requires `(NEW).col` when "
        "ACCESSING a column; only an assignment target may be bare."
    )
    assert not re.search(r"\(\s*(NEW|OLD)\s*\)\.\w+\s*:=", body, re.IGNORECASE), (
        f"{function} parenthesises an assignment TARGET; the platform's example does not"
    )


def test_rc00g_a_trigger_function_only_names_columns_its_own_table_has() -> None:
    """PLATFORM NOTE 2 (0114), as a machine check rather than a comment.

    CockroachDB binds ``NEW`` to the trigger table's row type when it compiles the body, so a
    function shared across tables with different columns is a migration that may simply refuse to
    apply. This test is what stops the two cue projectors being helpfully merged back into one.
    """
    tables = _column_map()
    bodies = _function_bodies()
    welds = _triggers()
    assert welds, "no CREATE TRIGGER found in the band — the parser or the band is wrong"

    for trigger, table, function, path in welds:
        assert table in tables, f"{trigger} is welded to unknown table {table}"
        assert function in bodies, (
            f"{trigger} in {path.name} calls {function}, which the band never creates"
        )
        body = _strip_comments(bodies[function])
        referenced = {
            match.group(1).lower()
            for match in re.finditer(
                r"(?:\(\s*(?:NEW|OLD)\s*\)|(?<![.\w])(?:NEW|OLD))\.(\w+)", body, re.IGNORECASE
            )
        }
        unknown = sorted(referenced - tables[table])
        assert not unknown, (
            f"{function} names {unknown} on NEW/OLD, but {table} has no such column. "
            f"Welded by {trigger} in {path.name}. Split the function per table."
        )


def test_rc00h_every_function_in_the_band_is_welded_to_something() -> None:
    """A projector nobody calls is a comment with a syntax highlighter."""
    welded = {function for _, _, function, _ in _triggers()}
    orphans = sorted(set(_function_bodies()) - welded)
    assert not orphans, f"created but never welded to a trigger: {orphans}"
