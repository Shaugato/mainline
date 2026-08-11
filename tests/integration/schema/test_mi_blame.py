# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""Tier-1 schema suite for migrations 0037-0039 — the blame DAG, the closure, and the one view
that reads it (worker ``dm-blame``, band ``0032``-``0039z`` in
``verticals/mainline/db/migrations.allocation.toml``).

What this file owns and therefore may honestly assert:

* ``mainline.blame_edge`` (0037) — the blame pointer the product is named for, with **MI13**'s
  ``inference_never_blocks``: an inferred link is a claim about the past, and making it block
  converts every model error into a rubber stamp;
* ``mainline.clause_blame_closure`` (0038) — append-only, generation-versioned, monotone; the
  table under every ancestry gate, with the truncation and banding CHECKs that keep a partial
  ancestry from looking complete and a fatality from being banded ``routine``;
* ``mainline.clause_blame_current`` (0039) — **the only read path** (DM-9);
* ``verticals/mainline/db/queries/closure_write.sql`` and ``closure_read.sql`` — the committed
  writer and the containment lookup, executed here rather than admired;
* ``scripts/grep_closure_readpath.py`` — DM-9's enforcement, run as part of this suite.

What this file does NOT own and does not pretend to prove:

* **MI14** (``model_cannot_arm``) is a CHECK on ``mainline.event``, migration 0033, and is
  asserted by ``test_mi_event_severity.py``. What is asserted HERE is the consequence: a
  model-rated event cannot band a closure to ``blood_major`` or ``blood_fatal``, because MI14
  keeps its ``severity_gate`` below 4.
* **MI26**'s enforcement (``fn_closure_guard`` 0108, the ``append_only`` weld 0128j) is
  rendered from kernel templates and lives ABOVE this band. This suite proves the welds exist and
  name this relation, proves what the table refuses **on its own**, and says plainly what it does
  not refuse without them.
* **MI15**'s BLOODLINE guard is ``fn_clause_version_guard`` (0141) on ``clause_version``. The RED
  case below is not that guard; it is the hole the guard does not close.

What the ratchet should read off this file
------------------------------------------
``mi_catalogue.yaml`` names three witnesses here, and the ``mi-red`` job's rule is that every
``pending`` invariant must have at least one owning test that currently FAILS.

* ``test_mi13_*`` — one test, and it **passes**. That is deliberate and it is a PROMOTION SIGNAL,
  not a defect: MI13's mechanism is complete (``0037``'s ``inference_never_blocks`` makes an
  inferred+active edge unrepresentable, and ``closure_write.sql``'s ``state = 'active'`` filter
  carries that into the scalar the gate reads), so ``mi-red`` will correctly report *"MI13 is
  pending but its tests pass — promote it in mi_catalogue.yaml"*. Promoting it is
  ``dm-runner``'s edit, and the ratchet asking for it is the ratchet working.
* ``test_mi26_*`` — two tests, one passing (the boundary transcript) and one failing (the
  monotone guard's uncorrelated revision count). MI26 stays honestly ``pending``.
* ``test_mi14_*`` — the catalogue promises one here and this file does NOT supply it, on purpose.
  MI14's other witness already passes, so a *passing* ``test_mi14_*`` added here would make MI14
  green-while-pending and break ``mi-red`` for a reason that has nothing to do with MI14. The
  witness this file owes is a RED one, and it belongs to whoever closes the provenance gap under
  ``event.severity_gate``.

Running it
----------
The static tier needs nothing but the repository and runs anywhere. The cluster tier is marked
``requires_cluster`` and finds a CockroachDB v26.2 in this order, **skipping with a reason**
rather than faking anything: ``$MAINLINE_TEST_DSN`` / ``$COCKROACH_URL`` / ``$CRDB_URL``, then a
``cockroach`` binary on ``PATH``, then a running Docker daemon. Nothing in this band is done on
the basis of a skipped run.

Measured, not assumed: on 2026-08-10 the cluster tier ran against CockroachDB CCL **v26.2.5**
(`cockroachdb/cockroach:latest-v26.2`) and applied 62 prerequisites plus this band with zero
failures. The plans it observed are recorded in
``verticals/mainline/db/queries/EXPLAIN-ASSERTIONS.md``.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import time
import uuid
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

# ══════════════════════════════════════════════════════════════════════════════════════════════
# Paths and band constants
# ══════════════════════════════════════════════════════════════════════════════════════════════

REPO_ROOT = Path(__file__).resolve().parents[3]
DB_DIR = REPO_ROOT / "verticals" / "mainline" / "db"
MIGRATIONS_DIR = DB_DIR / "migrations"
QUERIES_DIR = DB_DIR / "queries"
READPATH_SCRIPT = REPO_ROOT / "scripts" / "grep_closure_readpath.py"

#: The half of band 0032-0039 this file covers. 0032-0036 are asserted by
#: ``test_mi_event_severity.py``; splitting the band across two files keeps each one readable and
#: keeps a failure in the taxonomy from reading as a failure in the closure.
BAND_FIRST, BAND_LAST = 37, 39

#: Everything numbered at or below this must exist before the band applies.
PREREQ_LAST = 36

BAND_TABLES = ("mainline.blame_edge", "mainline.clause_blame_closure")
BAND_VIEW = "mainline.clause_blame_current"

REQUIRED_HEADER_KEYS = ("-- MI:", "-- I:", "-- COUNSEL-GATED:", "-- RATIONALE:")

#: MR-5, the one filename convention: ``NNNN[a-z]_lower_snake_slug.sql``.
MR5_FILENAME = re.compile(r"^\d{4}[a-z]?_[a-z0-9_]+\.sql$")

VALID_MI = frozenset(f"MI{n:02d}" for n in range(1, 31))
VALID_I = frozenset(f"I{n:02d}" for n in range(1, 17))

#: Names quoted in ARCHITECTURE §5.4 / §16 and asserted by name in the conformance corpus.
#: Renaming one is a breaking change to an exhibit, not a refactor.
LOAD_BEARING_NAMES: dict[str, tuple[str, ...]] = {
    "0037_blame_edge.sql": (
        "inference_never_blocks",
        "asserted_needs_quote",
        "human_needs_signature",
        "scored_needs_features",
    ),
    "0038_clause_blame_closure.sql": ("sev_range", "gen_positive", "fk_version"),
    "0039_clause_blame_current.sql": (),
}

CRDB_IMAGE = os.environ.get("MAINLINE_CRDB_IMAGE", "cockroachdb/cockroach:latest-v26.2")
CONTAINER_NAME = "mainline-blame-schema-test"
READY_TIMEOUT_S = 120.0
DOCKER_PROBE_TIMEOUT_S = 10.0
DOCKER_RUN_TIMEOUT_S = 600.0


# ══════════════════════════════════════════════════════════════════════════════════════════════
# A comment-, string- and dollar-quote-aware SQL reader.
#
# Every file in this band is mostly prose, and the prose is full of apostrophes ("the operator's
# permit"). A scanner that looks for quotes before comment markers reads `operator's permit` as
# the start of a string literal and swallows the rest of the file, which would let a
# two-statement file through the one-statement lint. `test_the_scanner_survives_apostrophes_in_
# prose` is the self-test, and it runs before the scanner is trusted with anything.
# ══════════════════════════════════════════════════════════════════════════════════════════════

_DOLLAR_TAG = re.compile(r"\$[A-Za-z_]?\w*\$")


def strip_sql_comments(text: str) -> str:
    """Remove ``--`` and ``/* */`` comments, preserving string and identifier literals."""
    out: list[str] = []
    i, n = 0, len(text)
    while i < n:
        ch = text[i]
        if ch == "'":
            out.append(ch)
            i += 1
            while i < n:
                if text[i] == "'":
                    if i + 1 < n and text[i + 1] == "'":
                        out.append("''")
                        i += 2
                        continue
                    out.append("'")
                    i += 1
                    break
                out.append(text[i])
                i += 1
            continue
        if ch == '"':
            out.append(ch)
            i += 1
            while i < n and text[i] != '"':
                out.append(text[i])
                i += 1
            if i < n:
                out.append('"')
                i += 1
            continue
        if ch == "-" and i + 1 < n and text[i + 1] == "-":
            while i < n and text[i] != "\n":
                i += 1
            continue
        if ch == "/" and i + 1 < n and text[i + 1] == "*":
            i += 2
            while i + 1 < n and not (text[i] == "*" and text[i + 1] == "/"):
                i += 1
            i += 2
            continue
        out.append(ch)
        i += 1
    return "".join(out)


def split_statements(text: str) -> list[str]:
    """Split into statements on ``;``, ignoring semicolons inside literals and dollar-quoted bodies.

    Dollar quoting matters here in a way it did not for 0032-0036: this band's neighbours in the
    enforcement layer are ``CREATE FUNCTION … $$ … END $$`` bodies full of semicolons, and a
    splitter that did not know about ``$$`` would report one file as fourteen statements.
    """
    body = strip_sql_comments(text)
    statements: list[str] = []
    current: list[str] = []
    i, n = 0, len(body)
    while i < n:
        ch = body[i]
        if ch == "'":
            current.append(ch)
            i += 1
            while i < n:
                if body[i] == "'":
                    if i + 1 < n and body[i + 1] == "'":
                        current.append("''")
                        i += 2
                        continue
                    current.append("'")
                    i += 1
                    break
                current.append(body[i])
                i += 1
            continue
        if ch == "$":
            tag = _DOLLAR_TAG.match(body, i)
            if tag is not None:
                close = body.find(tag.group(0), tag.end())
                end = len(body) if close == -1 else close + len(tag.group(0))
                current.append(body[i:end])
                i = end
                continue
        if ch == ";":
            statement = "".join(current).strip()
            if statement:
                statements.append(statement)
            current = []
            i += 1
            continue
        current.append(ch)
        i += 1
    tail = "".join(current).strip()
    if tail:
        statements.append(tail)
    return statements


def table_body(create_table_sql: str) -> str:
    """Return the text between the outermost parentheses of a ``CREATE TABLE``."""
    start = create_table_sql.index("(")
    depth = 0
    for index in range(start, len(create_table_sql)):
        if create_table_sql[index] == "(":
            depth += 1
        elif create_table_sql[index] == ")":
            depth -= 1
            if depth == 0:
                return create_table_sql[start + 1 : index]
    raise AssertionError("unbalanced parentheses in CREATE TABLE")


def top_level_items(body: str) -> list[str]:
    """Split a ``CREATE TABLE`` body into its comma-separated top-level items."""
    items: list[str] = []
    current: list[str] = []
    depth = 0
    for ch in body:
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        if ch == "," and depth == 0:
            items.append("".join(current).strip())
            current = []
            continue
        current.append(ch)
    tail = "".join(current).strip()
    if tail:
        items.append(tail)
    return [item for item in items if item]


def band_files() -> list[Path]:
    """The 0037-0039 migrations, ordered by version, selected by SHAPE and never by name."""
    found: list[tuple[int, str, Path]] = []
    for path in sorted(MIGRATIONS_DIR.iterdir()):
        if not path.is_file() or MR5_FILENAME.match(path.name) is None:
            continue
        match = re.match(r"^(\d{4})([a-z]?)_", path.name)
        if match and BAND_FIRST <= int(match.group(1)) <= BAND_LAST:
            found.append((int(match.group(1)), match.group(2), path))
    return [p for _, _, p in sorted(found)]


def table_files() -> list[Path]:
    """The band's ``CREATE TABLE`` files. 0039 is a view and is excluded from table-shape lints."""
    return [p for p in band_files() if "CREATE TABLE" in strip_sql_comments(p.read_text("utf-8"))]


def prerequisite_files() -> list[Path]:
    """Every migration numbered at or below ``PREREQ_LAST`` that currently exists.

    Applied BEST-EFFORT on purpose. Bands 0001-0036 belong to other workers and to the rendered
    substrate; a half-written sibling that raised here would report as "the blame band is broken",
    which is both false and the kind of message that gets a working band reverted. This band's OWN
    files are applied strictly.
    """
    found: list[tuple[int, str, Path]] = []
    for path in sorted(MIGRATIONS_DIR.iterdir()):
        if not path.is_file() or MR5_FILENAME.match(path.name) is None:
            continue
        match = re.match(r"^(\d{4})([a-z]?)_", path.name)
        if match and int(match.group(1)) <= PREREQ_LAST:
            found.append((int(match.group(1)), match.group(2), path))
    return [p for _, _, p in sorted(found)]


def header_value(text: str, key: str) -> str | None:
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith(key):
            return stripped[len(key) :].strip()
    return None


def all_migration_text() -> dict[str, str]:
    """Every migration in the tree, comment-stripped and lower-cased, keyed by file name."""
    return {
        path.name: strip_sql_comments(path.read_text(encoding="utf-8")).lower()
        for path in sorted(MIGRATIONS_DIR.glob("*.sql"))
    }


# ══════════════════════════════════════════════════════════════════════════════════════════════
# STATIC TIER — no cluster, no driver, no network. These run everywhere.
# ══════════════════════════════════════════════════════════════════════════════════════════════


def test_the_scanner_survives_apostrophes_in_prose_and_dollar_bodies() -> None:
    """Self-test of this file's own scanner, before it is trusted to lint anything."""
    sample = (
        "-- the operator's permit, not ours; and it isn't the contractor's either\n"
        "/* a block comment with a ; and an apostrophe: don't */\n"
        "SELECT 'a;b', 'it''s fine';\n"
    )
    statements = split_statements(sample)
    assert len(statements) == 1, statements
    assert statements[0].startswith("SELECT")
    assert "a;b" in statements[0]

    body = "CREATE FUNCTION f() RETURNS TRIGGER AS $$ BEGIN a; b; RETURN NEW; END $$;\n"
    assert len(split_statements(body)) == 1, split_statements(body)


def test_band_is_dense_and_exclusive() -> None:
    """0037-0039, no gaps, no duplicates, no strays."""
    files = band_files()
    numbers = [int(p.name[:4]) for p in files]
    assert numbers == list(range(BAND_FIRST, BAND_LAST + 1)), (
        f"the blame band must be dense over {BAND_FIRST:04d}-{BAND_LAST:04d}; got {numbers}"
    )
    strays = sorted(
        p.name
        for p in MIGRATIONS_DIR.iterdir()
        if p.is_file()
        and re.match(r"^\d{4}", p.name)
        and BAND_FIRST <= int(p.name[:4]) <= BAND_LAST
        and MR5_FILENAME.match(p.name) is None
    )
    assert not strays, (
        f"files inside {BAND_FIRST:04d}-{BAND_LAST:04d} that MR-5 refuses: {strays}. `.up.sql` is "
        "banned because it names a `.down.sql` counterpart that is illegal by construction, and a "
        "twin claims the same version — `discover()` then refuses the whole tree."
    )


def test_no_down_migration_in_the_band() -> None:
    """DM-14. Down-migrating an evidentiary table is destruction of evidence, not a rollback."""
    strays = [
        p.name
        for p in MIGRATIONS_DIR.glob("*.down.sql")
        if re.match(r"^\d{4}", p.name) and BAND_FIRST <= int(p.name[:4]) <= BAND_LAST
    ]
    assert not strays, f".down.sql is illegal at or below the protected floor: {strays}"


@pytest.mark.parametrize("path", band_files(), ids=lambda p: p.name)
def test_every_file_carries_the_mandatory_header_block(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    for key in REQUIRED_HEADER_KEYS:
        assert header_value(text, key) is not None, f"{path.name} is missing `{key}`"

    cited = re.findall(r"MI\d{2}", header_value(text, "-- MI:") or "")
    assert cited, f"{path.name} cites no MI id (ARCHITECTURE §18: every migration cites one)"
    assert not set(cited) - VALID_MI, f"{path.name} cites MI ids outside MI01-MI30: {cited}"

    i_cited = re.findall(r"\bI\d{2}\b", header_value(text, "-- I:") or "")
    assert i_cited, f"{path.name} cites no TRAPPOINT invariant in `-- I:`"
    assert not set(i_cited) - VALID_I, f"{path.name} cites ids outside I01-I16: {i_cited}"

    gated = (header_value(text, "-- COUNSEL-GATED:") or "").lower()
    assert gated.startswith("no"), (
        f"{path.name} claims to be counsel-gated. The counsel-gated five are 0066-0069 and 0086 "
        f"(DM-17); 0001-0065 are counsel-independent by construction."
    )
    assert len(header_value(text, "-- RATIONALE:") or "") >= 40, (
        f"{path.name}'s RATIONALE is too short to be one"
    )


@pytest.mark.parametrize("path", band_files(), ids=lambda p: p.name)
def test_exactly_one_statement_per_file(path: Path) -> None:
    """The runner does not wrap a body in a transaction, so a two-statement file is not atomic."""
    statements = split_statements(path.read_text(encoding="utf-8"))
    assert len(statements) == 1, (
        f"{path.name} parses to {len(statements)} statements, not 1:\n"
        + "\n---\n".join(s[:200] for s in statements)
    )


@pytest.mark.parametrize("path", band_files(), ids=lambda p: p.name)
def test_no_banned_constructs(path: Path) -> None:
    """§4.1 law 9. The ledger is gap-free by CAS, so a gap must MEAN tampering.

    Platform ground truth F4 measured ``CREATE SEQUENCE`` as *succeeding* on the target cluster,
    which is exactly why this lint is load-bearing rather than decorative.
    """
    body = strip_sql_comments(path.read_text(encoding="utf-8")).lower()
    for banned in ("create sequence", "nextval", "unique_rowid", " serial", "\tserial"):
        assert banned not in body, f"{path.name} uses the banned construct {banned!r}"


@pytest.mark.parametrize("path", table_files(), ids=lambda p: p.name)
def test_no_check_reads_another_row_or_the_clock(path: Path) -> None:
    """DM-4 / constraint 5. A CHECK sees only the row being written.

    A subquery in a CHECK is a cross-row read the optimizer is under no obligation to
    re-evaluate, which is how a projection gets *trusted* instead of enforced — the exact shape of
    adversarial finding S1, and the reason this band's banding CHECKs compare two columns of the
    same row rather than looking anything up.
    """
    statement = split_statements(path.read_text(encoding="utf-8"))[0]
    for item in top_level_items(table_body(statement)):
        if not re.match(r"^CONSTRAINT\s+\w+\s+CHECK\b", item, re.IGNORECASE):
            continue
        lowered = item.lower()
        for forbidden in ("now(", "current_timestamp", "select ", "::jsonb", " ? "):
            assert forbidden not in lowered, (
                f"{path.name}: CHECK {item.split()[1]} contains {forbidden!r}. A CHECK may read "
                f"only the row being written (DM-4)."
            )


@pytest.mark.parametrize("path", table_files(), ids=lambda p: p.name)
def test_every_constraint_is_explicitly_named(path: Path) -> None:
    """DM-10, asserted against the FILE and not only against the cluster.

    ``check_clause_blame_closure_4`` is not a courtroom exhibit, and it renumbers the moment a
    column is added above it.
    """
    statement = split_statements(path.read_text(encoding="utf-8"))[0]
    anonymous: list[str] = []
    for item in top_level_items(table_body(statement)):
        if re.match(r"^CONSTRAINT\s+\w+\b", item, re.IGNORECASE):
            continue
        if re.match(r"^(INDEX|UNIQUE\s+INDEX|INVERTED\s+INDEX|FAMILY)\b", item, re.IGNORECASE):
            continue
        lowered = item.lower()
        for keyword in ("primary key", "unique", "check", "references", "foreign key"):
            if keyword in lowered:
                anonymous.append(f"{item[:120]}  ← anonymous {keyword.upper()}")
                break
    assert not anonymous, (
        f"{path.name} declares constraints CockroachDB will have to name for us (DM-10):\n  "
        + "\n  ".join(anonymous)
    )


@pytest.mark.parametrize("path", band_files(), ids=lambda p: p.name)
def test_the_load_bearing_constraint_names_are_verbatim(path: Path) -> None:
    """These names appear in ARCHITECTURE and in trappoint-conform's expected diagnoses."""
    body = strip_sql_comments(path.read_text(encoding="utf-8"))
    for name in LOAD_BEARING_NAMES[path.name]:
        assert re.search(rf"CONSTRAINT\s+{name}\b", body), (
            f"{path.name} no longer declares CONSTRAINT {name}. That name is quoted in "
            f"ARCHITECTURE §5.4/§16; renaming it is a breaking change to an exhibit."
        )


def test_inference_never_blocks_is_spelled_exactly_as_mi13_states_it() -> None:
    """MI13, read off the file rather than off the docstring.

    A CHECK named ``inference_never_blocks`` that said ``state <> 'refuted'`` would pass every
    other test in this file and would not be MI13. So the predicate itself is asserted.
    """
    body = strip_sql_comments((MIGRATIONS_DIR / "0037_blame_edge.sql").read_text("utf-8"))
    normalised = " ".join(body.split()).lower()
    expected = (
        "constraint inference_never_blocks "
        "check (basis <> 'inferred_semantic' or state <> 'active')"
    )
    assert expected in normalised, (
        "0037's inference_never_blocks is not the MI13 predicate. It must be exactly\n"
        "  CHECK (basis <> 'inferred_semantic' OR state <> 'active')\n"
        "— a model may propose a blame link and say so; it may not thereby make one BLOCK."
    )


def test_the_inverted_index_puts_its_inverted_column_last_and_carries_no_storing() -> None:
    """The two shape rules a multi-column GIN in CockroachDB actually has.

    Getting either wrong is not a performance regression: the statement does not apply at all, so
    the whole band fails on a fresh cluster and nowhere else.
    """
    statement = split_statements(
        (MIGRATIONS_DIR / "0038_clause_blame_closure.sql").read_text("utf-8")
    )[0]
    inverted = [
        item
        for item in top_level_items(table_body(statement))
        if re.match(r"^INVERTED\s+INDEX\b", item, re.IGNORECASE)
    ]
    assert len(inverted) == 1, f"0038 must declare exactly one inverted index; got {inverted}"
    declaration = " ".join(inverted[0].split())
    assert "storing" not in declaration.lower(), (
        f"CockroachDB refuses a STORING clause on an inverted index: {declaration}"
    )
    columns = [c.strip() for c in declaration[declaration.index("(") + 1 :].rstrip(")").split(",")]
    assert columns[-1] == "ancestor_events", (
        f"the inverted column must be LAST in a multi-column GIN; got {columns}"
    )
    assert columns[0] == "site_id", (
        f"`site_id` must lead `cbc_anc` — the tenancy scope every lookup constrains: {columns}"
    )


def test_no_primary_key_column_appears_in_a_storing_clause() -> None:
    """The platform correction §5.4's printed ``cbc_sev`` needs, asserted so it stays corrected.

    ``STORING (clause_uuid, virulence, closure_gen)`` is what ARCHITECTURE prints. CockroachDB
    refuses a primary-key column inside ``STORING``, and secondary indexes carry the primary key
    implicitly, so the correct list is ``STORING (virulence)`` and nothing is lost. The same
    correction is recorded by 0024 and 0029; this test stops it being un-made by someone
    transcribing §5.4 again.
    """
    for path in table_files():
        statement = split_statements(path.read_text(encoding="utf-8"))[0]
        items = top_level_items(table_body(statement))
        pk_item = next(
            (i for i in items if re.search(r"\bPRIMARY\s+KEY\b", i, re.IGNORECASE)), None
        )
        assert pk_item is not None, f"{path.name} declares no PRIMARY KEY"
        pk_columns = {
            c.strip().lower()
            for c in pk_item[pk_item.index("(") + 1 :].rstrip(")").split(",")
            if c.strip()
        }
        for item in items:
            match = re.search(r"\bSTORING\s*\(([^)]*)\)", item, re.IGNORECASE)
            if match is None:
                continue
            stored = {c.strip().lower() for c in match.group(1).split(",") if c.strip()}
            overlap = sorted(stored & pk_columns)
            assert not overlap, (
                f"{path.name}: {overlap} are PRIMARY KEY columns and appear in a STORING clause. "
                f"CockroachDB refuses that, and secondary indexes carry the primary key implicitly."
            )


# ── DM-9 — the view is the only read path, enforced over the tree ─────────────────────────────


def test_the_readpath_scanner_proves_itself_before_it_is_trusted() -> None:
    """``--selftest``. A classifier that has never been shown to separate a weld from a write is a
    classifier whose green result means nothing."""
    result = subprocess.run(
        [sys.executable, str(READPATH_SCRIPT), "--selftest"],
        capture_output=True,
        text=True,
        check=False,
        cwd=str(REPO_ROOT),
    )
    assert result.returncode == 0, (
        f"scripts/grep_closure_readpath.py --selftest failed:\n{result.stdout}\n{result.stderr}"
    )


def test_dm9_the_closure_is_read_only_through_the_view() -> None:
    """DM-9. ``mainline.clause_blame_current`` is the only read path, proved over the whole tree."""
    result = subprocess.run(
        [sys.executable, str(READPATH_SCRIPT), "--json"],
        capture_output=True,
        text=True,
        check=False,
        cwd=str(REPO_ROOT),
    )
    payload = json.loads(result.stdout) if result.stdout.strip() else {}
    violations = [o for o in payload.get("occurrences", []) if not o["allowed"]]
    assert result.returncode == 0, (
        "DM-9 violated — a file outside 0038, 0039 and queries/closure_write.sql touches "
        "mainline.clause_blame_closure in an executable position:\n"
        + "\n".join(f"  {o['kind']:<6} {o['path']}:{o['line']}  {o['excerpt']}" for o in violations)
        + f"\n{result.stderr}"
    )


def test_the_view_reads_the_closure_and_orders_by_generation_descending() -> None:
    """0039 is the ONE file allowed to read the table, and it must read it the one right way."""
    body = " ".join(
        strip_sql_comments(
            (MIGRATIONS_DIR / "0039_clause_blame_current.sql").read_text("utf-8")
        ).split()
    ).lower()
    assert "distinct on (clause_uuid, as_of_commit)" in body, (
        "the view must de-duplicate on the clause VERSION, not on the clause: two versions of one "
        "clause have two independent ancestries and both are current."
    )
    assert "order by clause_uuid, as_of_commit, closure_gen desc" in body, (
        "the ORDER BY prefix must match the DISTINCT ON list and must end `closure_gen DESC`. "
        "Ordering ascending would make the view return the FIRST generation — the one computed "
        "with the least ancestry — on every read, silently."
    )
    assert "select *" not in body, (
        "0039 must list its columns. `*` is expanded at view-creation time, so the file would "
        "stop describing the view it created the moment 0038 gains a column."
    )


# ── the committed queries ─────────────────────────────────────────────────────────────────────


def test_the_committed_queries_exist() -> None:
    for name in ("closure_write.sql", "closure_read.sql", "EXPLAIN-ASSERTIONS.md"):
        assert (QUERIES_DIR / name).is_file(), f"verticals/mainline/db/queries/{name} is missing"


def test_the_read_query_never_names_the_table() -> None:
    body = strip_sql_comments((QUERIES_DIR / "closure_read.sql").read_text("utf-8")).lower()
    assert "clause_blame_current" in body
    assert "clause_blame_closure" not in body, (
        "closure_read.sql must go through the view. Reading the table and forgetting "
        "max(closure_gen) returns a superseded generation — computed with LESS ancestry, so a "
        "LOWER max_severity — with no error anywhere."
    )
    assert "ancestor_events @> array[" in " ".join(body.split()), (
        "the containment predicate is the query. `= ANY` and `&&` are not the same question: "
        "`@>` is the one an inverted index can serve."
    )


def test_the_writer_is_one_statement_that_unions_and_bounds_its_recursion() -> None:
    """The three properties §5.4 spells out, asserted against the committed statement."""
    raw = (QUERIES_DIR / "closure_write.sql").read_text("utf-8")
    statements = split_statements(raw)
    assert len(statements) == 1, (
        f"the writer must be ONE top-level statement; got {len(statements)}"
    )
    body = " ".join(strip_sql_comments(raw).split()).lower()

    assert "with recursive anc" in body
    assert "union all" not in body, (
        "the recursion must use UNION, not UNION ALL. Diamond ancestry is the NORMAL case here — "
        "two paths to the same 2004 fatality — and UNION ALL enumerates every path, which grows "
        "combinatorially in a graph whose node count is small."
    )
    assert "depth < 64" in body, (
        "the explicit end condition is the ONLY cycle guard the walk has: CockroachDB has no "
        "CYCLE clause."
    )
    assert "b.state = 'active'" in body, (
        "the base case must filter to ACTIVE edges. That filter is the second half of MI13: "
        "0037's CHECK makes an inferred+active edge unrepresentable, and this filter is what "
        "turns that into 'an inferred edge can never raise max_severity'."
    )
    assert "512" in body, "the fan-out cap must appear in the writer"
    assert "insert into mainline.clause_blame_closure" in body


def test_the_writer_is_not_a_trigger_and_no_trigger_writes_the_closure() -> None:
    """The trap named in this band's brief, checked mechanically.

    An asynchronous projection is a deliberate design choice paid for by MI22 (the gate fails
    closed on a missing closure). A trigger that "kept it fresh" would put an unbounded recursive
    walk on the money path and would make the p99 a function of a customer's incident history.
    """
    writer = strip_sql_comments((QUERIES_DIR / "closure_write.sql").read_text("utf-8")).lower()
    assert "create trigger" not in writer, "queries/closure_write.sql must not create a trigger"

    offenders: list[str] = []
    for name, text in all_migration_text().items():
        if "insert into mainline.clause_blame_closure" not in text:
            continue
        if re.search(r"\bcreate\s+(or\s+replace\s+)?(function|procedure|trigger)\b", text):
            offenders.append(name)
    assert not offenders, (
        f"a routine in the migration set INSERTs the blame closure: {offenders}. The closure is "
        "written by a top-level application statement driven by the outbox changefeed, never by a "
        "trigger (ARCHITECTURE §5.4)."
    )


def test_no_migration_grants_update_or_delete_on_the_closure() -> None:
    """No mutating grant on the closure, anywhere — asserted rather than remembered.

    Grants are cluster state applied by the declarative matrix (DM-7), so this test is about the
    migration set: a `GRANT UPDATE` that slipped into DDL would survive every review that reads
    GRANTS.yaml.
    """
    offenders: list[str] = []
    for name, text in all_migration_text().items():
        flat = " ".join(text.split())
        for match in re.finditer(r"\bgrant\b(.{0,200}?)\bon\b(.{0,80}?)clause_blame_closure", flat):
            if re.search(r"\b(update|delete|truncate|all)\b", match.group(1)):
                offenders.append(f"{name}: …{match.group(0)[-120:]}")
    assert not offenders, (
        "a migration grants a mutating privilege on the blame closure:\n  " + "\n  ".join(offenders)
    )


def test_the_two_welds_exist_and_name_this_relation() -> None:
    """MI26's mechanism lives above this band; this band owes it a table of the right shape.

    Asserted here so that a rename of the relation, or a deletion of either weld, fails in the
    band that owns the table rather than silently in the band that owns the trigger.
    """
    text = all_migration_text()
    welds = {
        name: body
        for name, body in text.items()
        if "create trigger" in body and "on mainline.clause_blame_closure" in body
    }
    triggers = {re.search(r"create trigger\s+(\w+)", b).group(1) for b in welds.values()}  # type: ignore[union-attr]
    assert "closure_guard" in triggers, (
        f"no BEFORE INSERT closure_guard is welded to mainline.clause_blame_closure. Generations "
        f"would be neither dense nor severity-monotone. Found: {sorted(triggers)}"
    )
    # The failure message DESCRIBES the attack rather than spelling it, because a message that
    # spells `UPDATE … SET` reads to ruff's S608 heuristic as a statement being built. Suppressing
    # the rule with `noqa` would work; not tripping it is better, and CF-08 in
    # packages/trappoint-conformance carries the literal history anyway.
    assert "append_only" in triggers, (
        "no append_only weld on mainline.clause_blame_closure. A one-statement rewrite of "
        "max_severity to 0 is finding S2 — a shorter path to a laundered gate than any attack "
        f"the rest of the design defends against. Found: {sorted(triggers)}"
    )


# ── PL-2: the deliberately RED cases ──────────────────────────────────────────────────────────


@pytest.mark.pl2_red
def test_pl2_red_sev_max_is_never_projected_from_the_closure() -> None:
    """RED BY DESIGN (PL-2). Owner of the fix: ``dm-functions-triggers``, band 0140-0149.

    ``mainline.clause_version.sev_max`` is annotated in 0029 as *"PROJECTED … via
    mainline.clause_blame_current"* and it is the scalar the weaken-over-blood gate reads. What
    exists today is ``fn_clause_version_guard`` (0141), which enforces MI15's RATCHET: ``sev_max``
    may not DECREASE along the version chain. That is a real and valuable guard and it is not this.

    The hole it leaves is one INSERT wide. A BIRTH version has no parent, so the ratchet does not
    engage, and nothing compares ``sev_max`` against the ancestry that actually exists:

        insert a clause, a birth clause_version with sev_max = 0
        insert a blame_edge from a severity-5 fatality to that clause, basis asserted_document,
          state active
        the closure projects max_severity = 5, virulence = blood_fatal
        clause_version.sev_max is still 0, and every gate that reads the VERSION rather than the
          closure sees a routine clause

    The ratchet then locks that zero in as the floor for every descendant version. A projection
    that is trusted rather than enforced is adversarial finding S1, and this is its last
    unclosed instance on the blame path.

    The fix is a function that reads ``mainline.clause_blame_current`` and writes
    ``clause_version.sev_max``, RAISEing ``P0001`` when the closure row is absent (fail closed —
    MI22), plus a ``TRIGGER-MAP.yaml`` row:

        sev_max ⇄ fn_bloodline_project ⇄ mainline.clause_blame_current ⇄ P0001

    This test fails today for exactly that reason and goes green the moment the projection lands.
    It is not ``xfail``: the ``mi-red`` job needs to SEE the failure, and an xfail that passes when
    it fails is exactly the accounting PL-2 exists to prevent.
    """
    projecting: list[str] = []
    for name, text in all_migration_text().items():
        if not re.search(r"\bcreate\s+(or\s+replace\s+)?function\b", text):
            continue
        if "clause_blame_current" not in text:
            continue
        if re.search(r"\bnew\s*\)?\s*\.?\s*sev_max\s*:=", text) or re.search(
            r"\(new\)\.sev_max\s*:=", text
        ):
            projecting.append(name)

    assert projecting, (
        "PL-2 RED, as intended. No migration defines a function that reads "
        "mainline.clause_blame_current and assigns mainline.clause_version.sev_max, so:\n"
        "  * a BIRTH version may declare sev_max = 0 while its blame ancestry holds a fatality;\n"
        "  * fn_clause_version_guard (0141) then RATCHETS that zero — it refuses a DECREASE, and "
        "0 is already the floor;\n"
        "  * every reader of clause_version.sev_max sees `routine` for a blood-written control.\n"
        "Owner of the fix: dm-functions-triggers (band 0140-0149). The closure itself is correct "
        "and is not the defect: mainline.clause_blame_current already holds max_severity = 5 for "
        "that version. The defect is that nothing copies it onto the row the gate reads."
    )


@pytest.mark.pl2_red
def test_mi26_red_the_monotone_guard_accepts_an_unrelated_severity_revision() -> None:
    """RED BY DESIGN (PL-2). Owner of the fix: ``kernel/projection-triggers``.

    MI26's monotone half says a closure's ``max_severity`` may fall only against a signed
    second-rater ``event_severity_revision`` written in the same transaction. ``fn_closure_guard``
    (0108, rendered from ``packages/trappoint-sql/templates/0107_fn_closure_guard.sql.j2``)
    implements the count as::

        SELECT count(*) INTO v_revisions
          FROM mainline.event_severity_revision r
         WHERE r.at >= transaction_timestamp();

    The predicate is on TIME ALONE. It is not correlated to ``(NEW).clause_uuid``, to
    ``(NEW).ancestor_events``, or to any event in this closure's ancestry. So a signed, perfectly
    legitimate downgrade of an unrelated 2011 near-miss at another site, written in the same
    transaction, authorises lowering a fatality-written closure from 5 to 0 — and the ledger row
    the guard writes will faithfully record that it was authorised.

    This is not a hypothetical shape. It is the same class of defect as adversarial finding S1:
    a control that reads a value whose RELATIONSHIP to the thing being controlled is never
    checked. The severity revision is real; it is just about something else.

    The fix is one predicate: correlate the revision to this closure's ancestry, e.g.

        WHERE r.at >= transaction_timestamp()
          AND r.event_id = ANY ((NEW).ancestor_events)

    It is a change to the TEMPLATE followed by a re-render of both bindings (MR-1), which is why
    the owner is the kernel worker and not this band. This test fails today and goes green when
    that predicate lands.
    """
    guard = (MIGRATIONS_DIR / "0108_fn_closure_guard.sql").read_text("utf-8")
    body = " ".join(strip_sql_comments(guard).split()).lower()
    monotone = re.search(r"from mainline\.event_severity_revision.*?;", body)
    assert monotone is not None, (
        "0108 no longer counts event_severity_revision at all — MI26's monotone half has been "
        "removed rather than corrected."
    )
    clause = monotone.group(0)
    assert "ancestor_events" in clause or "event_id" in clause, (
        "PL-2 RED, as intended. fn_closure_guard's severity-monotone branch counts severity "
        "revisions by TIME alone:\n"
        f"    {clause}\n"
        "so a signed downgrade of ANY unrelated event, written in the same transaction, "
        "authorises lowering a fatality-written closure. Correlate it to this closure's ancestry "
        "— `AND r.event_id = ANY ((NEW).ancestor_events)` — in "
        "packages/trappoint-sql/templates/0107_fn_closure_guard.sql.j2, then re-render BOTH "
        "bindings (MR-1). Owner: kernel/projection-triggers."
    )


# ══════════════════════════════════════════════════════════════════════════════════════════════
# CLUSTER TIER — everything below needs a real CockroachDB v26.2.
# ══════════════════════════════════════════════════════════════════════════════════════════════


@dataclass
class Cluster:
    dsn: str
    provenance: str
    proc: subprocess.Popen[bytes] | None = None
    owns_docker: bool = False


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def _wait_until_ready(psycopg: Any, dsn: str, deadline: float) -> bool:
    while time.monotonic() < deadline:
        try:
            with psycopg.connect(dsn, connect_timeout=3) as conn:
                conn.execute("SELECT 1")
        except Exception:  # noqa: BLE001 — any failure here means "not yet"
            time.sleep(1.0)
        else:
            return True
    return False


def _docker(args: list[str], *, timeout: float) -> subprocess.CompletedProcess[str] | None:
    """A dead Docker daemon does not refuse ``docker info``; it BLOCKS."""
    try:
        return subprocess.run(
            ["docker", *args], capture_output=True, text=True, timeout=timeout, check=False
        )
    except (subprocess.TimeoutExpired, OSError):
        return None


def _from_env() -> Cluster | None:
    for name in ("MAINLINE_TEST_DSN", "COCKROACH_URL", "CRDB_URL"):
        value = os.environ.get(name)
        if value:
            return Cluster(dsn=value, provenance=f"${name}")
    return None


def _from_local_binary(psycopg: Any, tmp: Path) -> Cluster | None:
    binary = shutil.which("cockroach")
    if binary is None:
        return None
    port, http_port = _free_port(), _free_port()
    proc = subprocess.Popen(
        [
            binary,
            "start-single-node",
            "--insecure",
            "--store=type=mem,size=2GiB",
            f"--listen-addr=127.0.0.1:{port}",
            f"--http-addr=127.0.0.1:{http_port}",
        ],
        cwd=str(tmp),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    dsn = f"postgresql://root@127.0.0.1:{port}/defaultdb?sslmode=disable"
    if _wait_until_ready(psycopg, dsn, time.monotonic() + READY_TIMEOUT_S):
        return Cluster(dsn=dsn, provenance=f"local `cockroach` binary on {port}", proc=proc)
    proc.terminate()
    return None


def _from_docker(psycopg: Any) -> Cluster | None:
    if shutil.which("docker") is None:
        return None
    probe = _docker(["info", "--format", "{{.ServerVersion}}"], timeout=DOCKER_PROBE_TIMEOUT_S)
    if probe is None or probe.returncode != 0:
        return None
    _docker(["rm", "-f", CONTAINER_NAME], timeout=DOCKER_PROBE_TIMEOUT_S)
    port = _free_port()
    started = _docker(
        [
            "run",
            "-d",
            "--name",
            CONTAINER_NAME,
            "-p",
            f"{port}:26257",
            CRDB_IMAGE,
            "start-single-node",
            "--insecure",
            "--store=type=mem,size=2GiB",
        ],
        timeout=DOCKER_RUN_TIMEOUT_S,
    )
    if started is None or started.returncode != 0:
        return None
    dsn = f"postgresql://root@127.0.0.1:{port}/defaultdb?sslmode=disable"
    if _wait_until_ready(psycopg, dsn, time.monotonic() + READY_TIMEOUT_S):
        return Cluster(dsn=dsn, provenance=f"docker {CRDB_IMAGE} on {port}", owns_docker=True)
    _docker(["rm", "-f", CONTAINER_NAME], timeout=DOCKER_PROBE_TIMEOUT_S)
    return None


@pytest.fixture(scope="session")
def driver() -> Any:
    return pytest.importorskip(
        "psycopg", reason="psycopg 3 is required to talk to CockroachDB; `uv sync` installs it"
    )


@pytest.fixture(scope="session")
def cluster(driver: Any, tmp_path_factory: pytest.TempPathFactory) -> Iterator[Cluster]:
    found = (
        _from_env()
        or _from_local_binary(driver, tmp_path_factory.mktemp("crdb"))
        or _from_docker(driver)
    )
    if found is None:
        pytest.skip(
            "no CockroachDB v26.2 reachable. Provide $MAINLINE_TEST_DSN, a `cockroach` binary on "
            f"PATH, or a running Docker daemon for `docker run {CRDB_IMAGE}`. Migrations "
            "0037-0039 and queries/closure_write.sql are NOT verified by a skipped run."
        )
    try:
        yield found
    finally:
        if found.proc is not None:
            found.proc.terminate()
        if found.owns_docker:
            _docker(["rm", "-f", CONTAINER_NAME], timeout=DOCKER_PROBE_TIMEOUT_S)


@dataclass
class Applied:
    dsn: str
    database: str
    prerequisite_notes: list[str]


def _apply_file(driver: Any, conn: Any, path: Path, *, strict: bool) -> str | None:
    """Apply one migration. Return a note when it failed and ``strict`` is false."""
    for statement in split_statements(path.read_text(encoding="utf-8")):
        try:
            conn.execute(statement)
        except driver.Error as exc:
            detail = (
                f"{path.name} failed to apply.\n"
                f"  sqlstate: {exc.sqlstate}\n"
                f"  error:    {exc}\n"
                f"  statement:\n{statement.strip()[:1500]}"
            )
            if strict:
                raise AssertionError(detail) from exc
            return f"{path.name}: {exc.sqlstate} {str(exc).splitlines()[0][:160]}"
    return None


@pytest.fixture(scope="session")
def applied(driver: Any, cluster: Cluster) -> Iterator[Applied]:
    """Apply every prerequisite that exists, then the band, into a fresh database.

    The band is applied WITHOUT its enforcement layer (0107/0108/0127/0128j, which are rendered
    from kernel templates and numbered far above it). That is deliberate: this suite's job is to
    say what the TABLE refuses on its own, and a fixture that quietly pulled in four other
    domains' files would report their failures as this band's.
    """
    from psycopg.conninfo import make_conninfo

    database = f"mainline_blame_{uuid.uuid4().hex[:10]}"
    with driver.connect(cluster.dsn, autocommit=True) as admin:
        admin.execute(f"CREATE DATABASE {database}")

    dsn = make_conninfo(cluster.dsn, dbname=database)
    notes: list[str] = []
    with driver.connect(dsn, autocommit=True) as conn:
        for path in prerequisite_files():
            note = _apply_file(driver, conn, path, strict=False)
            if note is not None:
                notes.append(note)
        for path in band_files():
            _apply_file(driver, conn, path, strict=True)

    print(
        f"\n[blame] cluster:  {cluster.provenance}\n"
        f"[blame] database: {database}\n"
        f"[blame] applied {len(prerequisite_files())} prerequisites "
        f"({len(notes)} of them failed and were skipped) + {len(band_files())} band migrations"
        + ("".join(f"\n[blame] prerequisite skipped — {n}" for n in notes))
    )
    try:
        yield Applied(dsn=dsn, database=database, prerequisite_notes=notes)
    finally:
        with driver.connect(cluster.dsn, autocommit=True) as admin:
            admin.execute(f"DROP DATABASE IF EXISTS {database} CASCADE")


@pytest.fixture
def conn(driver: Any, applied: Applied) -> Iterator[Any]:
    """One autocommit connection per test.

    Autocommit and not a rolled-back transaction: a refused statement must not be able to hide
    behind a rollback that also erases the rows the test wrote before it.
    """
    connection = driver.connect(applied.dsn, autocommit=True)
    try:
        yield connection
    finally:
        connection.close()


# ── helpers that mint legal rows, so that every refusal below is about ONE column ─────────────


def _digest(label: str) -> bytes:
    return hashlib.sha256(label.encode("utf-8")).digest()


@dataclass
class World:
    """One isolated site's worth of spine, minted per test (the xdist-safe isolation primitive)."""

    site_id: uuid.UUID
    commit_id: bytes
    doc_id: uuid.UUID
    clause_uuid: uuid.UUID


def _world(conn: Any, tag: str = "w") -> World:
    site_id = uuid.uuid4()
    label = f"{tag}:{site_id}"
    commit_id = _digest(label)
    conn.execute(
        "INSERT INTO mainline.site "
        "(site_id, site_code, site_role, tenant_id, taxonomy_ver) VALUES (%s, %s, %s, %s, 1)",
        (site_id, f"s{site_id.hex[:12]}", f"r{site_id.hex[:12]}", uuid.uuid4()),
    )
    conn.execute(
        "INSERT INTO mainline.commit_obj "
        "(commit_id, site_id, gen, ref_name, author_sub, message, envelope, envelope_bytes) "
        "VALUES (%s, %s, 0, 'site/test/main', 'sub-a', %s, '{}', %s)",
        (commit_id, site_id, label, b"{}"),
    )
    doc_id = uuid.uuid4()
    conn.execute(
        "INSERT INTO mainline.doc (doc_id, site_id, doc_code, title) VALUES (%s, %s, %s, %s)",
        (doc_id, site_id, f"D-{site_id.hex[:8]}", "isolation standard"),
    )
    clause_uuid = uuid.uuid4()
    conn.execute(
        "INSERT INTO mainline.clause (clause_uuid, site_id, birth_commit, activity_root) "
        "VALUES (%s, %s, %s, 'ISOLATION-OF-STORED-ENERGY')",
        (clause_uuid, site_id, commit_id),
    )
    return World(site_id=site_id, commit_id=commit_id, doc_id=doc_id, clause_uuid=clause_uuid)


def _commit(conn: Any, world: World, label: str, gen: int = 1) -> bytes:
    commit_id = _digest(f"{world.site_id}:{label}")
    conn.execute(
        "INSERT INTO mainline.commit_obj "
        "(commit_id, site_id, gen, ref_name, author_sub, message, envelope, envelope_bytes) "
        "VALUES (%s, %s, %s, 'site/test/main', 'sub-a', %s, '{}', %s)",
        (commit_id, world.site_id, gen, label, b"{}"),
    )
    return commit_id


def _clause_version(
    conn: Any,
    world: World,
    commit_id: bytes,
    *,
    gen: int = 0,
    sev_max: int = 0,
    delta: str = "introduce",
) -> None:
    conn.execute(
        "INSERT INTO mainline.clause_version "
        "(clause_uuid, gen, commit_id, site_id, doc_id, activity_root, ordinal, raw_text, "
        " canon_text, canon_version, canon_sha256, anchor_set, control_delta, delta_basis, "
        " blood_root, blood_peaks, blood_size, sev_max) "
        "VALUES (%s, %s, %s, %s, %s, 'ISOLATION-OF-STORED-ENERGY', 1, %s, %s, 1, %s, "
        "        ARRAY[]::STRING[], %s, 'lattice', %s, ARRAY[]::BYTES[], 0, %s)",
        (
            world.clause_uuid,
            gen,
            commit_id,
            world.site_id,
            world.doc_id,
            "the energy shall be proved dead",
            "the energy shall be proved dead",
            _digest("canon"),
            delta,
            _digest("blood-root"),
            sev_max,
        ),
    )


_NUMBERED_PARAM = re.compile(r"\$(\d+)")


def _bind(query_file: str, values: dict[int, Any]) -> tuple[str, tuple[Any, ...]]:
    """Load a committed query and translate PostgreSQL ``$n`` params into psycopg's ``%s``.

    Not a ``str.replace`` loop, and the difference is the whole point. ``closure_write.sql``
    names ``$1`` FOUR times — the recursion's base case, the ``ver`` lookup, the ``nextgen``
    lookup and the INSERT's own column list — because deriving ``site_id`` and ``closure_gen``
    inside the statement is what keeps a caller from supplying either (P2). psycopg's positional
    form needs one value per OCCURRENCE, so the parameters are rebuilt in the order the
    placeholders actually appear. A naive replace passes four values to ten placeholders and
    fails with a message about counting rather than about the query.

    The committed file keeps ``$n`` because that is what the projector's driver speaks natively
    and because a query file full of ``%s`` cannot be read against ARCHITECTURE §5.4.
    """
    raw = strip_sql_comments((QUERIES_DIR / query_file).read_text(encoding="utf-8")).strip()
    params: list[Any] = []

    def substitute(match: re.Match[str]) -> str:
        params.append(values[int(match.group(1))])
        return "%s"

    return _NUMBERED_PARAM.sub(substitute, raw.rstrip(";")), tuple(params)


def _event(
    conn: Any, world: World, label: str, *, severity: int, basis: str = "coded_field"
) -> uuid.UUID:
    event_id = uuid.uuid4()
    conn.execute(
        "INSERT INTO mainline.event "
        "(event_id, site_id, external_ref, occurred_at, kind, title, narrative, "
        " source_object_key, source_sha256, severity_actual, severity_potential, severity_gate, "
        " severity_basis, canon_version) "
        "VALUES (%s, %s, %s, %s, 'incident', %s, 'narrative', 'k', %s, %s, %s, %s, %s, 1)",
        (
            event_id,
            world.site_id,
            f"INC-{event_id.hex[:8]}",
            "2019-03-14T06:20:00+00:00",
            label,
            _digest(label),
            severity,
            severity,
            severity,
            basis,
        ),
    )
    return event_id


_BLAME_COLUMNS = (
    "event_id, clause_uuid, basis, state, site_id, commit_id, p_link, features, attribution, "
    "evidence_span, evidence_quote_sha256, model_id, reviewed_by, review_sig"
)
_BLAME_PLACEHOLDERS = ", ".join(["%s"] * 14)


def _blame_edge_params(
    world: World,
    event_id: uuid.UUID,
    commit_id: bytes,
    *,
    basis: str,
    state: str,
) -> tuple[Any, ...]:
    """A legal row for every basis, so each refusal below differs in exactly one place."""
    scored = basis in ("derived_documentary", "inferred_semantic")
    return (
        event_id,
        world.clause_uuid,
        basis,
        state,
        world.site_id,
        commit_id,
        0.91 if scored else None,
        json.dumps({"fixture": True}),
        "the same control class failed in both cases",
        [1204, 1391],
        _digest("quote"),
        "au.anthropic.claude-sonnet-5" if basis == "inferred_semantic" else None,
        "sub-reviewer" if basis == "asserted_human" else None,
        _digest("review-sig") if basis == "asserted_human" else None,
    )


def _insert_blame_edge(
    conn: Any,
    world: World,
    event_id: uuid.UUID,
    commit_id: bytes,
    *,
    basis: str = "asserted_document",
    state: str = "active",
) -> None:
    conn.execute(
        f"INSERT INTO mainline.blame_edge ({_BLAME_COLUMNS}) VALUES ({_BLAME_PLACEHOLDERS})",  # noqa: S608
        _blame_edge_params(world, event_id, commit_id, basis=basis, state=state),
    )


_CLOSURE_COLUMNS = (
    "clause_uuid, as_of_commit, closure_gen, site_id, ancestor_events, ancestor_count, "
    "max_severity, virulence, depth, truncated, computed_by, projector_ver"
)


def _closure_params(
    world: World,
    commit_id: bytes,
    *,
    gen: int = 0,
    ancestors: list[uuid.UUID] | None = None,
    max_severity: int = 0,
    virulence: str = "routine",
    depth: int = 0,
    truncated: bool = False,
    ancestor_count: int | None = None,
) -> tuple[Any, ...]:
    events = ancestors or []
    return (
        world.clause_uuid,
        commit_id,
        gen,
        world.site_id,
        events,
        len(events) if ancestor_count is None else ancestor_count,
        max_severity,
        virulence,
        depth,
        truncated,
        "agent_projector",
        "test-fixture",
    )


def _insert_closure(conn: Any, params: tuple[Any, ...]) -> None:
    placeholders = ", ".join(["%s"] * len(params))
    conn.execute(
        f"INSERT INTO mainline.clause_blame_closure ({_CLOSURE_COLUMNS}) VALUES ({placeholders})",  # noqa: S608
        params,
    )


def _explain(conn: Any, statement: str, params: tuple[Any, ...]) -> str:
    """Return ``EXPLAIN``'s output as one string, joined by row and by cell.

    Deliberately un-parsed. ``packages/trappoint-recall`` owns a real plan parser and the
    diachronic suite owns a twenty-line one; a third would be two too many. What this band needs
    from a plan is three substrings — an index name, ``FULL SCAN``, and their absence — and a
    substring test that prints the whole plan on failure is more useful to the reader than a
    structured one that prints a dataclass.
    """
    return "\n".join(
        str(cell) for row in conn.execute("EXPLAIN " + statement, params).fetchall() for cell in row
    )


def _refusal(driver: Any, conn: Any, statement: str, params: tuple[Any, ...]) -> Any:
    """Execute expecting a refusal, and return the exception. Fail loudly if it succeeded."""
    try:
        conn.execute(statement, params)
    except driver.Error as exc:
        return exc
    raise AssertionError(f"the database ACCEPTED a write it must refuse:\n  {statement}")


def _closure_refusal(driver: Any, conn: Any, params: tuple[Any, ...]) -> Any:
    placeholders = ", ".join(["%s"] * len(params))
    return _refusal(
        driver,
        conn,
        f"INSERT INTO mainline.clause_blame_closure ({_CLOSURE_COLUMNS}) VALUES ({placeholders})",  # noqa: S608
        params,
    )


def _names_constraint(exc: Any, expected: str) -> None:
    """Assert the refusal identifies the constraint BY NAME, from either place it can appear."""
    diag_name = getattr(getattr(exc, "diag", None), "constraint_name", None)
    message = str(exc)
    if diag_name == expected or expected in message:
        return
    raise AssertionError(
        f"the refusal did not name the constraint {expected!r}.\n"
        f"  diag.constraint_name: {diag_name!r}\n"
        f"  message:              {message}"
    )


# ── MI13 — an inferred blame edge is never active ─────────────────────────────────────────────


@pytest.mark.requires_cluster
def test_mi13_an_inferred_edge_may_never_be_active(driver: Any, conn: Any) -> None:
    """The single line 0037 exists for.

    Three assertions, and the two positive controls matter as much as the refusal: a test that
    only ever sees 23514 passes just as happily when the INSERT is failing for an unrelated
    reason, and an MI13 that refused *every* inferred edge would be indistinguishable from MI13
    working right up until the first useful model proposal could not be recorded at all.
    """
    world = _world(conn, "mi13")
    _clause_version(conn, world, world.commit_id)
    event = _event(conn, world, "loss of isolation", severity=5)

    # 1. A model may propose a blame link and say so — provisionally.
    _insert_blame_edge(
        conn, world, event, world.commit_id, basis="inferred_semantic", state="provisional"
    )

    # 2. A re-derivable link may block.
    _insert_blame_edge(
        conn, world, event, world.commit_id, basis="derived_documentary", state="active"
    )

    # 3. An inferred one may not.
    exc = _refusal(
        driver,
        conn,
        f"INSERT INTO mainline.blame_edge ({_BLAME_COLUMNS}) VALUES ({_BLAME_PLACEHOLDERS})",  # noqa: S608
        _blame_edge_params(
            world,
            _event(conn, world, "second incident", severity=5),
            world.commit_id,
            basis="inferred_semantic",
            state="active",
        ),
    )
    assert exc.sqlstate == "23514", f"MI13 must be a CHECK refusal, got {exc.sqlstate}"
    _names_constraint(exc, "inference_never_blocks")


@pytest.mark.requires_cluster
def test_each_basis_carries_the_evidence_its_force_requires(driver: Any, conn: Any) -> None:
    """``asserted_needs_quote``, ``human_needs_signature``, ``scored_needs_features``.

    Four bases are four different CLAIMS, not four confidences of the same claim, and each is
    distinguished by what can be cross-examined about it. These three CHECKs are what make the
    distinction real rather than documentary.
    """
    world = _world(conn, "basis")
    _clause_version(conn, world, world.commit_id)

    def attempt(basis: str, **blanked: Any) -> Any:
        params = list(
            _blame_edge_params(
                world,
                _event(conn, world, f"e-{basis}-{len(blanked)}", severity=3),
                world.commit_id,
                basis=basis,
                state="provisional",
            )
        )
        index = {"quote": 10, "sig": 13, "p_link": 6, "model": 11}
        for key in blanked:
            params[index[key]] = None
        return _refusal(
            driver,
            conn,
            f"INSERT INTO mainline.blame_edge ({_BLAME_COLUMNS}) "  # noqa: S608
            f"VALUES ({_BLAME_PLACEHOLDERS})",
            tuple(params),
        )

    exc = attempt("asserted_document", quote=True)
    assert exc.sqlstate == "23514"
    _names_constraint(exc, "asserted_needs_quote")

    exc = attempt("asserted_human", sig=True)
    assert exc.sqlstate == "23514"
    _names_constraint(exc, "human_needs_signature")

    exc = attempt("derived_documentary", p_link=True)
    assert exc.sqlstate == "23514"
    _names_constraint(exc, "scored_needs_features")

    exc = attempt("inferred_semantic", model=True)
    assert exc.sqlstate == "23514"
    _names_constraint(exc, "inferred_names_its_model")


# ── the closure's plain-column refusals ───────────────────────────────────────────────────────


@pytest.mark.requires_cluster
def test_the_banding_refuses_under_banding_and_permits_over_banding(driver: Any, conn: Any) -> None:
    """``virulence`` is banded ONCE, here, and the CHECKs are one-directional on purpose.

    Banding a severity-5 ancestry as ``routine`` would make ``(blood_fatal, mechanism_absent)``'s
    deliberate absence from ``clearance_legal`` bypassable by one integer — the whole clearance
    lattice defeated from inside the projector. Banding a severity-4 ancestry as ``blood_fatal``
    raises the bar and costs a signature, so it is allowed.
    """
    world = _world(conn, "band")
    _clause_version(conn, world, world.commit_id)

    # over-banding: permitted, and it is generation 0 so nothing else can be blamed for it.
    _insert_closure(
        conn,
        _closure_params(world, world.commit_id, max_severity=4, virulence="blood_fatal"),
    )

    exc = _closure_refusal(
        driver,
        conn,
        _closure_params(world, world.commit_id, gen=1, max_severity=5, virulence="routine"),
    )
    assert exc.sqlstate == "23514"
    _names_constraint(exc, "fatal_ancestry_is_banded_fatal")

    exc = _closure_refusal(
        driver,
        conn,
        _closure_params(world, world.commit_id, gen=1, max_severity=4, virulence="serious"),
    )
    assert exc.sqlstate == "23514"
    _names_constraint(exc, "major_ancestry_is_at_least_major")

    exc = _closure_refusal(
        driver,
        conn,
        _closure_params(world, world.commit_id, gen=1, max_severity=3, virulence="blood_major"),
    )
    assert exc.sqlstate == "23514"
    _names_constraint(exc, "blood_needs_severity")


@pytest.mark.requires_cluster
def test_a_truncated_closure_cannot_look_complete(driver: Any, conn: Any) -> None:
    """``truncation_is_declared``. The most important boolean in the schema, refused for real.

    A closure that hit either bound has walked LESS ancestry than exists, so its ``max_severity``
    is a lower bound. A lower bound presented as a fact understates severity.
    """
    world = _world(conn, "trunc")
    _clause_version(conn, world, world.commit_id)

    # A walk that stopped at the depth bound must say so.
    exc = _closure_refusal(
        driver, conn, _closure_params(world, world.commit_id, depth=64, truncated=False)
    )
    assert exc.sqlstate == "23514"
    _names_constraint(exc, "truncation_is_declared")

    # Declaring it is enough; the row is then legal.
    _insert_closure(conn, _closure_params(world, world.commit_id, depth=64, truncated=True))

    # And the bounds themselves are bounds.
    exc = _closure_refusal(
        driver, conn, _closure_params(world, world.commit_id, gen=1, depth=65, truncated=True)
    )
    assert exc.sqlstate == "23514"
    _names_constraint(exc, "depth_within_cap")


@pytest.mark.requires_cluster
def test_the_count_may_not_disagree_with_the_array(driver: Any, conn: Any) -> None:
    """``count_matches_the_array``. A denormalised count that may drift is a lie with a deadline."""
    world = _world(conn, "count")
    _clause_version(conn, world, world.commit_id)
    events = [_event(conn, world, f"c{i}", severity=1) for i in range(3)]

    _insert_closure(conn, _closure_params(world, world.commit_id, ancestors=events))

    exc = _closure_refusal(
        driver,
        conn,
        _closure_params(world, world.commit_id, gen=1, ancestors=events, ancestor_count=9),
    )
    assert exc.sqlstate == "23514"
    _names_constraint(exc, "count_matches_the_array")

    # The empty closure is LEGAL and is not the same thing as an absent one (MI22).
    other = _world(conn, "empty")
    _clause_version(conn, other, other.commit_id)
    _insert_closure(conn, _closure_params(other, other.commit_id))
    row = conn.execute(
        "SELECT ancestor_count FROM mainline.clause_blame_current WHERE clause_uuid = %s",
        (other.clause_uuid,),
    ).fetchone()
    assert row is not None, "the empty closure did not land"
    assert row[0] == 0, f"an empty closure must report ancestor_count 0, not {row[0]}"


@pytest.mark.requires_cluster
def test_a_closure_needs_a_committed_clause_version(driver: Any, conn: Any) -> None:
    """``fk_version``. A closure is about a VERSION of a clause, never a clause in the abstract."""
    world = _world(conn, "fk")
    # deliberately NO clause_version row
    exc = _closure_refusal(driver, conn, _closure_params(world, world.commit_id))
    assert exc.sqlstate == "23503"
    _names_constraint(exc, "fk_version")


# ── the view ──────────────────────────────────────────────────────────────────────────────────


@pytest.mark.requires_cluster
def test_the_view_returns_the_highest_generation_only(conn: Any) -> None:
    """DM-9's whole reason: a reader that forgets ``max(closure_gen)`` reads a superseded row."""
    world = _world(conn, "gen")
    _clause_version(conn, world, world.commit_id)
    events = [_event(conn, world, f"g{i}", severity=s) for i, s in enumerate((1, 5))]

    _insert_closure(
        conn,
        _closure_params(
            world, world.commit_id, gen=0, ancestors=events[:1], max_severity=1, virulence="routine"
        ),
    )
    _insert_closure(
        conn,
        _closure_params(
            world,
            world.commit_id,
            gen=1,
            ancestors=events,
            max_severity=5,
            virulence="blood_fatal",
        ),
    )

    rows = conn.execute(
        "SELECT closure_gen, max_severity, virulence::STRING FROM mainline.clause_blame_current "
        "WHERE clause_uuid = %s",
        (world.clause_uuid,),
    ).fetchall()
    assert len(rows) == 1, f"the view must collapse generations to one row per version: {rows}"
    assert rows[0] == (1, 5, "blood_fatal"), (
        f"the view returned generation {rows[0]} — the OLDER generation is the one computed with "
        f"LESS ancestry, so reading it understates severity, which is the one error direction "
        f"with physical consequences."
    )

    raw = conn.execute(
        "SELECT count(*) FROM mainline.clause_blame_closure WHERE clause_uuid = %s",
        (world.clause_uuid,),
    ).fetchone()
    assert raw is not None, "the closure table reported nothing at all"
    assert raw[0] == 2, "the superseded generation must still be THERE"


@pytest.mark.requires_cluster
def test_the_containment_lookup_omits_a_superseded_only_match(conn: Any) -> None:
    """The correctness property any faster read path must preserve (EXPLAIN-ASSERTIONS §2.2).

    A clause whose generation 0 held incident E — because a provisional edge was later refuted —
    and whose generation 1 does not is NOT a descendant of E today. Filtering *before* the
    de-duplication would return it, which is exactly why the optimizer may not push the predicate
    below ``DISTINCT ON`` and why this test exists beside the plan file.
    """
    world = _world(conn, "supersede")
    _clause_version(conn, world, world.commit_id)
    retracted = _event(conn, world, "retracted", severity=3)
    kept = _event(conn, world, "kept", severity=3)

    _insert_closure(
        conn,
        _closure_params(world, world.commit_id, gen=0, ancestors=[retracted, kept], max_severity=3),
    )
    _insert_closure(
        conn,
        _closure_params(world, world.commit_id, gen=1, ancestors=[kept], max_severity=3),
    )

    statement, params = _bind("closure_read.sql", {1: world.site_id, 2: kept})
    hit = conn.execute(statement, params).fetchall()
    assert len(hit) == 1, f"the current generation holds `kept`; the lookup returned {hit}"
    assert hit[0][0] == world.clause_uuid

    statement, params = _bind("closure_read.sql", {1: world.site_id, 2: retracted})
    miss = conn.execute(statement, params).fetchall()
    assert miss == [], (
        "closure_read.sql returned a clause whose CURRENT generation no longer holds the event. "
        "That is a superseded-generation read wearing a containment predicate."
    )


@pytest.mark.requires_cluster
def test_the_inverted_index_is_traversable_for_a_containment_predicate(conn: Any) -> None:
    """EXPLAIN-ASSERTIONS §2.3 — asserted against the TABLE with the index pinned.

    A test may name the raw relation; a service may not (DM-9). Pinning the index follows the F1
    ruling's engineering: at CI's row counts a scan is genuinely cheaper, so an unhinted assertion
    would be asserting the optimizer's row-count estimate rather than our index.

    Three things are proved at once: a multi-column inverted index was accepted with the inverted
    column last, ``@>`` is a valid inverted-index constraint on a ``UUID[]``, and no ``STORING``
    clause crept onto it — CockroachDB refuses one, so its absence is load-bearing.
    """
    world = _world(conn, "gin")
    _clause_version(conn, world, world.commit_id)
    event = _event(conn, world, "gin", severity=1)
    _insert_closure(conn, _closure_params(world, world.commit_id, ancestors=[event]))

    plan = _explain(
        conn,
        "SELECT clause_uuid FROM mainline.clause_blame_closure@cbc_anc "
        "WHERE site_id = %s AND ancestor_events @> ARRAY[%s::UUID]",
        (world.site_id, event),
    )
    assert "cbc_anc" in plan, (
        "the plan did not traverse cbc_anc even with the index pinned, which means the inverted "
        f"index cannot serve `@>` on a UUID[] on this build:\n{plan}"
    )


@pytest.mark.requires_cluster
def test_the_severity_sweep_index_is_a_constrained_span(conn: Any) -> None:
    """EXPLAIN-ASSERTIONS §3 — ``cbc_sev`` exists, is index-only, and spans the blood band.

    Pinned for the same reason as §2.3. What is being asserted is the INDEX SHAPE — that
    ``STORING (virulence)`` survived the platform correction to §5.4's printed form, and that
    ``(site_id, max_severity)`` is a range the fleet sweep can seek rather than filter.
    """
    world = _world(conn, "sev")
    _clause_version(conn, world, world.commit_id)
    _insert_closure(
        conn,
        _closure_params(world, world.commit_id, max_severity=5, virulence="blood_fatal"),
    )
    plan = _explain(
        conn,
        "SELECT clause_uuid, virulence FROM mainline.clause_blame_closure@cbc_sev "
        "WHERE site_id = %s AND max_severity >= 4",
        (world.site_id,),
    )
    assert "cbc_sev" in plan, f"the severity sweep did not traverse cbc_sev:\n{plan}"
    assert "FULL SCAN" not in plan, (
        f"cbc_sev was named but not constrained — the sweep is reading every closure:\n{plan}"
    )


# ── the writer, executed ──────────────────────────────────────────────────────────────────────


def _run_writer(conn: Any, world: World, commit_id: bytes) -> Any:
    """Execute the COMMITTED writer verbatim. Nothing here re-types the statement."""
    statement, params = _bind(
        "closure_write.sql",
        {1: world.clause_uuid, 2: commit_id, 3: "agent_projector", 4: "test-fixture"},
    )
    return conn.execute(statement, params).fetchall()


@pytest.mark.requires_cluster
def test_the_closure_writer_seeks_its_base_case(conn: Any) -> None:
    """EXPLAIN-ASSERTIONS §1.1, §1.3 and §1.4 — the three access paths a plan CAN show.

    The recursive term is deliberately absent from this list, and the absence is recorded rather
    than papered over: CockroachDB's ``EXPLAIN`` renders a ``recursive cte`` node showing only its
    INITIAL term, so there is no fragment for the ``event_edge`` join to assert and a test that
    claimed to assert one would be asserting nothing (EXPLAIN-ASSERTIONS §1.2).

    What these three catch is DRIFT, not wrongness. Every one of them is *correct* without its
    index; each just gets quietly worse as a real customer's history accumulates, and a projection
    whose cost is unbounded is a projection that eventually stops running — at which point the
    gate fails closed on every permit in the fleet (MI22).
    """
    world = _world(conn, "plan")
    _clause_version(conn, world, world.commit_id)
    event = _event(conn, world, "plan", severity=3)
    _insert_blame_edge(conn, world, event, world.commit_id)
    _run_writer(conn, world, world.commit_id)

    base = _explain(
        conn,
        "SELECT event_id FROM mainline.blame_edge "
        "WHERE clause_uuid = %s AND commit_id = %s AND state = 'active'",
        (world.clause_uuid, world.commit_id),
    )
    assert "blame_edge@by_clause_commit" in base, (
        "the closure writer's base case no longer seeks by_clause_commit. blame_edge_pk is "
        "correct but wider — it range-scans every edge of the clause and then filters two "
        f"columns:\n{base}"
    )
    assert "FULL SCAN" not in base, f"the base case full-scans blame_edge:\n{base}"

    severity = _explain(
        conn,
        "SELECT ev.severity_gate FROM mainline.event AS ev WHERE ev.event_id IN (%s)",
        (event,),
    )
    assert "FULL SCAN" not in severity, (
        f"the writer's severity lookup full-scans mainline.event:\n{severity}"
    )

    generation = _explain(
        conn,
        "SELECT closure_gen FROM mainline.clause_blame_current "
        "WHERE clause_uuid = %s AND as_of_commit = %s",
        (world.clause_uuid, world.commit_id),
    )
    assert "FULL SCAN" not in generation, (
        "a primary-key-prefix lookup THROUGH THE VIEW full-scans the closure, which would make "
        "every projector write O(table). `closure_gen` is derived inside closure_write.sql "
        f"precisely because this is a seek:\n{generation}"
    )


@pytest.mark.requires_cluster
def test_the_writer_projects_a_real_blame_dag(conn: Any) -> None:
    """``queries/closure_write.sql``, end to end, against a three-generation event DAG.

        2004 fatality (sev 5)
              ▲ recurrence_of
        2011 incident (sev 3)
              ▲ precursor_of
        2019 near miss (sev 2) ── blame_edge (asserted_document, active) ──▶ the clause

    The clause is answerable to the 2004 fatality it has never heard of. That inheritance is the
    product, and this is the statement that computes it.
    """
    world = _world(conn, "writer")
    _clause_version(conn, world, world.commit_id)

    fatality = _event(conn, world, "2004 fatality", severity=5)
    incident = _event(conn, world, "2011 incident", severity=3)
    near_miss = _event(conn, world, "2019 near miss", severity=2)
    conn.execute(
        "INSERT INTO mainline.event_edge (child_event_id, parent_event_id, relation) "
        "VALUES (%s, %s, 'recurrence_of'), (%s, %s, 'precursor_of')",
        (incident, fatality, near_miss, incident),
    )
    _insert_blame_edge(conn, world, near_miss, world.commit_id)

    rows = _run_writer(conn, world, world.commit_id)
    assert len(rows) == 1, (
        "the writer inserted no row. An empty RETURNING means the clause VERSION does not exist "
        "— see the zero-row contract in queries/closure_write.sql."
    )

    stored = conn.execute(
        "SELECT closure_gen, ancestor_count, max_severity, virulence::STRING, depth, truncated, "
        "       ancestor_events FROM mainline.clause_blame_current WHERE clause_uuid = %s",
        (world.clause_uuid,),
    ).fetchone()
    assert stored is not None
    gen, count, max_sev, virulence, depth, truncated, ancestors = stored
    assert gen == 0, "the first generation for a clause version is zero"
    assert count == 3, f"three ancestral events were reachable; the closure recorded {count}"
    assert max_sev == 5, "the 2004 fatality is two hops away and it is the maximum"
    assert virulence == "blood_fatal", "severity 5 bands blood_fatal, once, here"
    assert depth == 2, f"the walk is two hops deep; recorded {depth}"
    assert truncated is False
    assert {uuid.UUID(str(a)) for a in ancestors} == {fatality, incident, near_miss}

    # A second run is a NEW GENERATION, never an overwrite. That is what makes the gate diachronic.
    _run_writer(conn, world, world.commit_id)
    generations = conn.execute(
        "SELECT closure_gen FROM mainline.clause_blame_closure WHERE clause_uuid = %s "
        "ORDER BY closure_gen",
        (world.clause_uuid,),
    ).fetchall()
    assert [g for (g,) in generations] == [0, 1], (
        f"recomputing the closure must append a generation, not overwrite one: {generations}"
    )


@pytest.mark.requires_cluster
def test_an_inferred_edge_cannot_raise_max_severity(conn: Any) -> None:
    """MI13's consequence, proved through the writer rather than asserted about the CHECK.

    A CI assertion that "an inferred edge can never raise ``clause_blame_closure.max_severity``"
    is worth more than the constraint alone, because it exercises the whole chain: CHECK, then the
    base case's ``state = 'active'`` filter, then the scalar the gate reads.
    """
    world = _world(conn, "inferred")
    _clause_version(conn, world, world.commit_id)

    fatality = _event(conn, world, "unseen fatality", severity=5)
    minor = _event(conn, world, "minor", severity=1)
    _insert_blame_edge(
        conn, world, fatality, world.commit_id, basis="inferred_semantic", state="provisional"
    )
    _insert_blame_edge(conn, world, minor, world.commit_id, basis="asserted_document")

    _run_writer(conn, world, world.commit_id)
    stored = conn.execute(
        "SELECT max_severity, virulence::STRING, ancestor_count "
        "FROM mainline.clause_blame_current WHERE clause_uuid = %s",
        (world.clause_uuid,),
    ).fetchone()
    assert stored is not None
    assert stored == (1, "routine", 1), (
        f"an inferred edge to a severity-5 fatality reached the closure: {stored}. MI13 says an "
        f"inferred link is a claim about the past; letting it arm a gate converts every model "
        f"error into a rubber stamp."
    )


@pytest.mark.requires_cluster
def test_a_model_rated_event_cannot_band_the_closure_to_blood(conn: Any) -> None:
    """MI14's consequence, one band down. Asserted here because 0033's CHECK is asserted there.

    ``model_cannot_arm`` keeps ``severity_gate`` below 4 for a ``model_rated`` event, so such an
    event cannot band a closure to ``blood_major`` or ``blood_fatal`` no matter how confident the
    model was. The event still SITS in the record at potential 5 — a visible, quotable
    disagreement between what the machine thought and what the gate did.
    """
    world = _world(conn, "mi14")
    _clause_version(conn, world, world.commit_id)
    rated = _event(conn, world, "model rated", severity=3, basis="model_rated")
    _insert_blame_edge(conn, world, rated, world.commit_id, basis="derived_documentary")

    _run_writer(conn, world, world.commit_id)
    stored = conn.execute(
        "SELECT max_severity, virulence::STRING FROM mainline.clause_blame_current "
        "WHERE clause_uuid = %s",
        (world.clause_uuid,),
    ).fetchone()
    assert stored is not None
    assert stored[0] < 4, (
        f"a model-rated event carried the closure to max_severity {stored[0]}. MI14 is upstream of "
        f"this and must make it unreachable."
    )
    assert stored[1] not in ("blood_major", "blood_fatal"), (
        f"a model-rated event banded the closure to {stored[1]}."
    )


@pytest.mark.requires_cluster
def test_mi26_the_band_alone_does_not_refuse_a_closure_rewrite(conn: Any) -> None:
    """The BOUNDARY of this band, executed rather than asserted — finding S2's exact shape.

    Migration 0038 is a table. A table has no opinion about ``UPDATE``. MI26's append-only,
    generation-dense and severity-monotone properties are enforced by ``fn_closure_guard`` (0108)
    welded by 0127, and by the ``append_only`` weld 0128j — all of them rendered from kernel
    templates and numbered far above this band, and none of them applied by this suite's fixture.

    So this test is not a red: it is the transcript of the boundary, and it asserts two things
    that ARE this band's business — that the rewrite is possible against the bare table, and that
    the tree contains the welds that make it impossible in a real deployment. If a future edit
    deleted 0127 or 0128j, ``test_the_two_welds_exist_and_name_this_relation`` fails and this test
    is what explains why that matters.
    """
    world = _world(conn, "s2")
    _clause_version(conn, world, world.commit_id)
    fatality = _event(conn, world, "fatality", severity=5)
    _insert_closure(
        conn,
        _closure_params(
            world,
            world.commit_id,
            ancestors=[fatality],
            max_severity=5,
            virulence="blood_fatal",
        ),
    )

    conn.execute(
        "UPDATE mainline.clause_blame_closure SET max_severity = 0, virulence = 'routine' "
        "WHERE clause_uuid = %s",
        (world.clause_uuid,),
    )
    after = conn.execute(
        "SELECT max_severity FROM mainline.clause_blame_current WHERE clause_uuid = %s",
        (world.clause_uuid,),
    ).fetchone()
    assert after is not None, "the closure row vanished, which is a different defect entirely"
    assert after[0] == 0, (
        "the bare table refused the rewrite, which means something in band 0032-0039 is enforcing "
        "MI26. That is not this band's job and it would be a duplicate of fn_refuse_mutation — "
        "if it was added deliberately, update this test and REFUSAL_DEPTH.md together."
    )

    # And a non-dense generation is equally free, for the same reason.
    _insert_closure(conn, _closure_params(world, world.commit_id, gen=7))


# ── shape assertions over the applied band ────────────────────────────────────────────────────


def _rows_by_column(conn: Any, statement: str) -> list[dict[str, Any]]:
    """Run a ``SHOW …`` and return dicts, by name and never by position."""
    with conn.cursor() as cur:
        cur.execute(statement)
        names = [d.name for d in (cur.description or [])]
        return [dict(zip(names, row, strict=False)) for row in cur.fetchall()]


#: Shapes CockroachDB synthesises when nobody named the constraint. ``^fk_.*_ref_`` is ANCHORED
#: rather than a bare ``_ref_`` substring: a bare substring also matches names a human deliberately
#: wrote, and a DM-10 probe that reports false positives is a probe somebody eventually relaxes.
_AUTO_CONSTRAINT_PATTERNS = (
    re.compile(r"_pkey$"),
    re.compile(r"^primary$"),
    re.compile(r"^check_"),
    re.compile(r"^unique_"),
    re.compile(r"^fk_.*_ref_"),
    re.compile(r"_key$"),
    re.compile(r"^\d"),
)
_NOT_NULL_NAME = re.compile(r"_not_null$")


@pytest.mark.requires_cluster
def test_every_constraint_on_the_band_tables_is_named(conn: Any) -> None:
    """DM-10, as the cluster sees it."""
    offenders: list[str] = []
    for qualified in BAND_TABLES:
        _, _, table = qualified.partition(".")
        rows = conn.execute(
            "SELECT constraint_name, constraint_type FROM information_schema.table_constraints "
            "WHERE table_schema = 'mainline' AND table_name = %s "
            "AND constraint_type IN ('PRIMARY KEY', 'UNIQUE', 'CHECK', 'FOREIGN KEY')",
            (table,),
        ).fetchall()
        assert rows, f"{qualified} reports no constraints — the band did not apply"
        for name, kind in rows:
            if _NOT_NULL_NAME.search(str(name)):
                continue
            if any(p.search(str(name)) for p in _AUTO_CONSTRAINT_PATTERNS):
                offenders.append(f"{qualified}.{name} ({kind})")
    assert not offenders, "system-generated constraint names (DM-10):\n  " + "\n  ".join(offenders)


@pytest.mark.requires_cluster
def test_every_index_on_the_band_tables_is_named(conn: Any) -> None:
    """DM-10 for indexes. A ``…_auto_index_fk_…`` name is one CockroachDB chose, not one we did."""
    offenders: list[str] = []
    for qualified in BAND_TABLES:
        for row in _rows_by_column(conn, f"SHOW INDEXES FROM {qualified}"):
            name = str(row["index_name"])
            if name.endswith("_pkey") or name == "primary":
                continue
            if "_auto_index_" in name or name.endswith("_key"):
                offenders.append(f"{qualified}.{name}")
    assert not offenders, f"system-generated index names (DM-10): {offenders}"


#: Markers CockroachDB emits in ``SHOW CREATE TABLE`` for a row-level-TTL table. NOT the bare
#: substring "ttl": a column named ``max_ttl_hours`` exists elsewhere in this schema.
_TTL_MARKERS = ("ttl_expire", "ttl_expiration_expression", "ttl_job_cron", "ttl = ", "ttl='on'")


@pytest.mark.requires_cluster
def test_no_row_level_ttl_on_any_band_table(conn: Any) -> None:
    """§4.1 law 13. Zero TTL in schema ``mainline``, forever.

    Expired rows are not filtered from query results — including from ``UPDATE`` and ``DELETE`` —
    which alone disqualifies row-level TTL for evidence. On the blame closure it would be worse
    than disqualifying: the generation that armed last year's refusal would simply stop existing.
    """
    for qualified in BAND_TABLES:
        row = conn.execute(f"SHOW CREATE TABLE {qualified}").fetchone()
        assert row is not None
        create = " ".join(str(c) for c in row).lower()
        hits = [m for m in _TTL_MARKERS if m in create]
        assert not hits, f"{qualified} carries a row-level TTL ({hits})"


@pytest.mark.requires_cluster
def test_the_view_exists_and_exposes_every_closure_column(conn: Any) -> None:
    """The view must project the closure UNCHANGED — a narrower view is a narrower gate."""
    table_columns = {
        str(r[0])
        for r in conn.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema = 'mainline' AND table_name = 'clause_blame_closure'"
        ).fetchall()
    }
    view_columns = {
        str(r[0])
        for r in conn.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema = 'mainline' AND table_name = 'clause_blame_current'"
        ).fetchall()
    }
    assert view_columns, f"{BAND_VIEW} did not apply"
    assert table_columns == view_columns, (
        f"the view and the table have diverged. Missing from the view: "
        f"{sorted(table_columns - view_columns)}; extra: {sorted(view_columns - table_columns)}. "
        f"A projection trigger rendered from a kernel template reads max_severity, virulence and "
        f"closure_gen off this relation by name."
    )
