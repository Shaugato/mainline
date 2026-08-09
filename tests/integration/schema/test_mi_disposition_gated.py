# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""The counsel gate (G0) as an executable assertion — ``db/ext/disposition_ext`` and MI11.

``docs/adr/0001-g0-counsel.md`` records that G0 — the paid hour with an Australian
resources-sector WHS/safety lawyer — was **not sought**, and that the *pre-committed conservative
default* is executed instead. That ADR is a prose document. This file is the part of it a stranger
can run.

**What the conservative reading actually is.** It is not a flag, a policy row or a feature switch.
It is the **absence of three cells** from ``mainline.clearance_legal``:

* ``(blood_fatal, mechanism_absent)``
* ``(blood_fatal, accept_residual)``
* ``(blood_major, accept_residual)``

Absence is the mechanism. Both ``mainline.disposition`` and ``mainline.carried_disposition`` take a
composite foreign key onto ``(virulence, kind)``, so a verdict in one of those cells is ``23503``
naming the constraint — for every writer, including a DBA, including the read-mostly MCP path, and
including a future service nobody has written yet. There is no code path to audit, because there is
no code.

Absence is also the one property a schema cannot show you. ``SHOW CREATE TABLE`` will never print
the row that is not there. So the reading is asserted three ways and this file checks that all
three agree and that the mechanism actually bites:

1. ``ext/disposition_ext/disposition_ext.toml`` — machine-readable, the value a service would read;
2. ``ext/disposition_ext/clearance_legal.conservative.sql`` — executable, ``SELECT``-only, empty
   result set means intact;
3. ``ext/disposition_ext/README.md`` — the sentence a human quotes.

**Why the extension point exists at all (DM-17).** ``BUILD_PLAN.md`` §2.1 requires the
counsel-sensitive shape to be *configuration*, not variant DDL, because a DDL fork per legal answer
is two schemas to test and one to get wrong. So the DDL in ``0066``-``0070`` ships unconditionally
and this directory records which reading it is operating under, together with what flipping each
switch would cost. Two of the four switches are answered by rows in a table with a named approver
and a policy version — which is the whole reason the clearance lattice is a table rather than a
``CHECK … IN (…)``.

**Scope, stated so the coverage claim is honest.** This worker owns
``verticals/mainline/db/ext/disposition_ext/`` and this file. The migrations ``0066``-``0068`` are
RENDERED substrate (kernel, ``obligation-and-clearance``) and ``0069``-``0070`` are authored by the
sibling ``ex-dm-disposition`` worker; nothing here edits them, and the assertions below read them
as given. Two tests are **RED BY DESIGN** against the tree as it stands and each names the file
and the owner of the fix rather than being softened — see
``test_every_counsel_gated_object_declares_it`` and
``test_spec_r3_gives_the_carried_family_mirrored_exhibit_names``.

Running it
----------
The static tier needs no cluster. The cluster tier (``@pytest.mark.requires_cluster``) finds a
CockroachDB v26.2 in this order and **skips with a reason** rather than faking anything:

1. the session ``dsn`` fixture, if ``tests/integration/schema/conftest.py`` (``dm-runner``) exists;
2. ``$MAINLINE_TEST_DSN`` / ``$COCKROACH_URL`` / ``$CRDB_URL`` / ``$TRAPPOINT_DSN``;
3. a ``cockroach`` binary on ``PATH`` (in-memory single node, session-scoped);
4. a running Docker daemon (``cockroachdb/cockroach:latest-v26.2``).

Nothing here is done on the basis of a skipped run. The suite was authored and executed against
``cockroachdb/cockroach:latest-v26.2`` in local Docker; it has **not** been run against CockroachDB
Cloud, and no test here asserts anything that requires one.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import socket
import subprocess
import time
import tomllib
import uuid
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest

psycopg = pytest.importorskip(
    "psycopg", reason="psycopg 3 is required to talk to CockroachDB; `uv sync` installs it"
)

# ══════════════════════════════════════════════════════════════════════════════════════════════
# Paths and constants
# ══════════════════════════════════════════════════════════════════════════════════════════════

REPO_ROOT = Path(__file__).resolve().parents[3]
DB_DIR = REPO_ROOT / "verticals" / "mainline" / "db"
MIGRATIONS_DIR = DB_DIR / "migrations"
EXT_DIR = DB_DIR / "ext" / "disposition_ext"
ADR = REPO_ROOT / "docs" / "adr" / "0001-g0-counsel.md"
SPEC_MANIFEST = REPO_ROOT / "spec" / "conformance" / "manifest.toml"

EXT_README = EXT_DIR / "README.md"
EXT_TOML = EXT_DIR / "disposition_ext.toml"
EXT_ASSERTION = EXT_DIR / "clearance_legal.conservative.sql"

SEED_FILE = MIGRATIONS_DIR / "0018b_clearance_legal_seed.sql"

#: MR-5, the one filename convention. Used here only to prove the extension point sits OUTSIDE it.
MR5_FILENAME = re.compile(r"^\d{4}[a-z]?_[a-z0-9_]+\.sql$")

#: The conservative reading of G0, as this suite understands it. Every other copy in the tree is
#: compared against this tuple, so a drift anywhere is a named failure rather than a discovery.
ABSENT_CELLS: tuple[tuple[str, str], ...] = (
    ("blood_fatal", "mechanism_absent"),
    ("blood_fatal", "accept_residual"),
    ("blood_major", "accept_residual"),
)

VIRULENCE_BANDS: tuple[str, ...] = ("routine", "serious", "blood_major", "blood_fatal")
DISPOSITION_KINDS: tuple[str, ...] = (
    "applied",
    "mitigated",
    "mechanism_absent",
    "escalated",
    "accept_residual",
    "emergency_override",
)
#: 4 x 6 = 24 cells in the product; the conservative seed carries 21 of them.
EXPECTED_LATTICE_ROWS = len(VIRULENCE_BANDS) * len(DISPOSITION_KINDS) - len(ABSENT_CELLS)

#: The five objects ADR 0001 names as counsel-gated. `silence_ledger` is addressed by RELATION and
#: not by number: ADR 0001 and BUILD_PLAN §2.1 both cite `0086`, and the recall band actually
#: landed it at `0084`. Pinning the number here would assert the wrong thing — the gate is about
#: the object, not the slot it occupies.
COUNSEL_GATED_OBJECTS: tuple[tuple[str, str], ...] = (
    ("0066", "mainline.disposition"),
    ("0067", "mainline.disposition_citation"),
    ("0068", "mainline.override_ledger"),
    ("0069", "mainline.carried_disposition"),
    ("*", "mainline_meas.silence_ledger"),
)

#: The relations in schema `mainline` that the G0 decision covers, plus the lattice they all key
#: onto. Row-level TTL on any of them would be a background job deleting the record of who cleared
#: what.
COUNSEL_GATED_FAMILY: tuple[str, ...] = (
    "clearance_legal",
    "disposition",
    "disposition_citation",
    "override_ledger",
    "carried_disposition",
    "carried_disposition_use",
)

#: spec/TRAPPOINT-SPEC.md R-3 — Exhibit Uniqueness. A refusal-bearing name must be unique across
#: the whole schema, and the spec names these two mirrors explicitly (`spec/CHANGELOG.md`, R-3:
#: "`substantive` / `carried_substantive`, `bounded` / `carried_bounded` / `predicate_bounded`").
#: `spec/conformance/manifest.toml` CF-66 asserts `carried_bounded` by string.
R3_MIRRORED_NAMES: tuple[tuple[str, str], ...] = (
    ("carried_bounded", "the bounded-window refusal on mainline.carried_disposition (MI28)"),
    ("carried_substantive", "the rationale-length refusal on mainline.carried_disposition"),
)

BANNED_TOKENS = (
    re.compile(r"\bCREATE\s+(?:TEMP\s+|TEMPORARY\s+|UNLOGGED\s+)*SEQUENCE\b", re.IGNORECASE),
    re.compile(r"\bnextval\s*\(", re.IGNORECASE),
    re.compile(r"\b(?:BIG|SMALL)?SERIAL[248]?\b", re.IGNORECASE),
    re.compile(r"\bunique_rowid\s*\(", re.IGNORECASE),
)

#: A statement that writes. The conservative assertion must contain none of these outside comments,
#: because "safe to run against production" is a claim this suite has to be able to check.
WRITE_TOKENS = (
    re.compile(r"\bINSERT\s+INTO\b", re.IGNORECASE),
    re.compile(r"\bUPDATE\s+\w", re.IGNORECASE),
    re.compile(r"\bDELETE\s+FROM\b", re.IGNORECASE),
    re.compile(r"\bUPSERT\b", re.IGNORECASE),
    re.compile(r"\bTRUNCATE\b", re.IGNORECASE),
    re.compile(r"\b(?:CREATE|ALTER|DROP|GRANT|REVOKE)\b", re.IGNORECASE),
)

CRDB_IMAGE = "cockroachdb/cockroach:latest-v26.2"
CONTAINER_NAME = "mainline-dispositiongated-crdb"
READY_TIMEOUT_S = 120.0
DOCKER_PROBE_TIMEOUT_S = 10.0
DOCKER_RUN_TIMEOUT_S = 180.0

#: Everything at or below this number is applied by the fixture, in lexicographic order on the
#: whole stem — which is the order `discovery.discover()` applies in (ruling D7). 0070 is the last
#: file of the counsel-gated family; nothing above it is needed to prove a lattice refusal, and
#: applying less is applying something a fresh cluster never sees.
APPLY_THROUGH = 70

#: The relations the cluster tier genuinely needs. If one is missing after the chain has been
#: applied, the suite SKIPS with the prerequisite failures printed — it does not pass, and it does
#: not claim this worker's deliverable is broken when a neighbour's file is.
REQUIRED_RELATIONS: tuple[str, ...] = (
    "clearance_legal",
    "carried_disposition",
    "disposition",
    "exposure_line",
    "blocking_check",
)


# ══════════════════════════════════════════════════════════════════════════════════════════════
# A small SQL scanner. Third independent implementation in this directory, deliberately: the
# statement-count and comment-stripping contract is load-bearing for every schema suite, and
# three implementations agreeing is worth more than one asserting three times.
# ══════════════════════════════════════════════════════════════════════════════════════════════


def strip_sql_comments(text: str) -> str:
    """Remove ``--`` and ``/* */`` comments, preserving string literals and quoted identifiers."""
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
    """Split into statements on ``;``, ignoring semicolons inside literals and comments."""
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


def header_value(text: str, key: str) -> str | None:
    """Return the value of a ``-- KEY: value`` header line, or None when it is absent."""
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith(key):
            return stripped[len(key) :].strip()
    return None


def migration_for_relation(relation: str) -> Path | None:
    """Find the migration that creates *relation*, by reading the tree rather than a hardcoded map.

    ADR 0001 cites `0086` for the silence ledger and the recall band landed it at `0084`. A test
    that pinned the number would fail for the wrong reason and would go on failing after somebody
    "fixed" it by renumbering. The gate is about the OBJECT.
    """
    pattern = re.compile(rf"CREATE\s+TABLE\s+{re.escape(relation)}\b", re.IGNORECASE)
    for path in sorted(MIGRATIONS_DIR.iterdir()):
        if not path.is_file() or MR5_FILENAME.match(path.name) is None:
            continue
        if pattern.search(strip_sql_comments(path.read_text(encoding="utf-8"))):
            return path
    return None


def migration_by_number(number: str) -> Path | None:
    for path in sorted(MIGRATIONS_DIR.iterdir()):
        if path.is_file() and MR5_FILENAME.match(path.name) and path.name.startswith(number):
            return path
    return None


def load_ext_toml() -> dict[str, Any]:
    return tomllib.loads(EXT_TOML.read_text(encoding="utf-8"))


def cells_declared_in_toml() -> tuple[tuple[str, str], ...]:
    raw = load_ext_toml()["disposition"]["absent_cells"]
    return tuple((str(pair[0]), str(pair[1])) for pair in raw)


def cells_named_in_assertion_sql() -> tuple[tuple[str, str], ...]:
    """Extract the ``VALUES`` pairs from the executable assertion, casts and all."""
    code = strip_sql_comments(EXT_ASSERTION.read_text(encoding="utf-8"))
    pairs = re.findall(
        r"'([a-z_]+)'::mainline\.virulence_class\s*,\s*'([a-z_]+)'::mainline\.disposition_kind",
        code,
    )
    return tuple((v, k) for v, k in pairs)


def cells_named_in_readme() -> set[tuple[str, str]]:
    """Extract ``(virulence, kind)`` pairs written in prose/table form in the README."""
    text = EXT_README.read_text(encoding="utf-8")
    found = set()
    for virulence, kind in re.findall(r"\(`?([a-z_]+)`?,\s*`?([a-z_]+)`?\)", text):
        if virulence in VIRULENCE_BANDS and kind in DISPOSITION_KINDS:
            found.add((virulence, kind))
    return found


def cells_seeded() -> set[tuple[str, str]]:
    """Parse ``0018b_clearance_legal_seed.sql`` for the ``(virulence, kind)`` of every row."""
    code = strip_sql_comments(SEED_FILE.read_text(encoding="utf-8"))
    return {
        (virulence, kind)
        for virulence, kind in re.findall(r"\(\s*'([a-z_]+)'\s*,\s*'([a-z_]+)'\s*,", code)
    }


# ══════════════════════════════════════════════════════════════════════════════════════════════
# STATIC TIER — no cluster required.
# ══════════════════════════════════════════════════════════════════════════════════════════════


def test_the_extension_point_ships_its_three_files() -> None:
    """DM-17: the counsel-gated surface is configuration, and configuration has to exist."""
    for path in (EXT_README, EXT_TOML, EXT_ASSERTION):
        assert path.is_file(), (
            f"{path.relative_to(REPO_ROOT)} is missing. BUILD_PLAN §2.1 requires the "
            "counsel-sensitive shape to be CONFIGURATION rather than variant DDL, and DM-17 puts "
            "that configuration in verticals/mainline/db/ext/disposition_ext/. Without it, "
            "'the DDL ships under the conservative reading' is a claim with nothing behind it."
        )
        assert path.read_text(encoding="utf-8").strip(), f"{path.name} is empty"


def test_the_extension_point_is_outside_the_apply_path() -> None:
    """MR-5: a capability or policy variant never sits in ``migrations/``.

    ``clearance_legal.conservative.sql`` carries a SECOND DOT, which is legal here and fatal one
    directory over: inside ``migrations/`` it yields a stem ``_VERSION_RE`` rejects, and
    ``discover()`` then refuses the ENTIRE directory — one badly-named file makes every correctly
    named migration beside it go unapplied. Measured, not theorised.
    """
    assert EXT_DIR.parent.name == "ext", f"{EXT_DIR} is not under db/ext/"
    assert MIGRATIONS_DIR not in EXT_DIR.parents, "the extension point is inside migrations/"
    for path in sorted(EXT_DIR.iterdir()):
        assert MR5_FILENAME.match(path.name) is None, (
            f"{path.name} matches the migration filename convention while living outside the "
            "migrations tree. Either it is a migration in the wrong directory or it is a variant "
            "wearing a migration's name; both are how two conventions come to coexist invisibly."
        )


def test_disposition_ext_toml_declares_the_conservative_default() -> None:
    """The machine-readable copy says which reading the shipped DDL is operating under."""
    data = load_ext_toml()

    gate = data["gate"]
    assert gate["id"] == "G0"
    assert gate["sought"] is False, (
        "disposition_ext.toml says G0 was sought. ADR 0001 records that it was NOT, and executes "
        "the pre-committed default instead. If that has changed, the ADR moves first."
    )
    assert gate["default"] == "conservative"
    assert gate["adr"] == "docs/adr/0001-g0-counsel.md"

    assert data["disposition"]["mechanism_absent_over_fatal_ancestry"] is False, (
        "switch 1 is not conservative. Under the conservative reading a mechanism_absent verdict "
        "over fatal ancestry is not merely discouraged, it is UNREPRESENTABLE: the cell is absent "
        "from mainline.clearance_legal and the composite foreign key refuses it with 23503."
    )
    assert data["citation"]["record_evidence_opened"] is True, (
        "switch 2 is not conservative. `evidence_opened = false` before a fatality is a "
        "devastating row and it ships anyway, because a system that deliberately declines to "
        "record whether the human read the warning is a WORSE exhibit — that design choice is "
        "itself discoverable, dated and authored."
    )
    assert data["silence"]["silence_ledger_zone"] == "mainline_meas", (
        "switch 3 is not conservative. The silence ledger ships in the unprivileged measurement "
        "zone and is treated as discoverable by default; behind privilege it would be the worst "
        "of both worlds — the exhibit exists and the placement looks like concealment."
    )
    assert data["silence"]["privileged"] is False
    assert data["measurement"]["per_approver_dwell_timing"] is False, (
        "switch 4 is not conservative. ADR 0001 question 4 (NSW Workplace Surveillance Act 2005 "
        "and its analogues) defaults per-approver dwell timing to OFF; deliberation is derived "
        "from the SERVER-issued exposure receipt, which is a record of what the system did."
    )

    # The advice reference is empty until G0 is genuinely answered. An invented one would be a lie
    # in the one file whose purpose is to be quoted at a lawyer.
    if gate["status"] != "answered":
        assert gate["advice_reference"] == "", (
            "gate.status is not 'answered' but an advice_reference is recorded. One of the two is "
            "wrong, and the expensive way to find out which is in discovery."
        )


def test_the_three_absent_cells_agree_across_all_three_copies() -> None:
    """Executable, machine-readable and human-readable must name the same three cells.

    Three copies is deliberate — a service reads the TOML, an operator runs the SQL, a reader
    quotes the README — so the only way that is safe is if a drift between them is a red test.
    """
    expected = set(ABSENT_CELLS)

    assert set(cells_declared_in_toml()) == expected, (
        f"disposition_ext.toml [disposition] absent_cells = {sorted(cells_declared_in_toml())}, "
        f"expected {sorted(expected)}"
    )
    assert set(cells_named_in_assertion_sql()) == expected, (
        f"clearance_legal.conservative.sql checks {sorted(cells_named_in_assertion_sql())}, "
        f"expected {sorted(expected)}. The executable copy is the one an operator actually runs, "
        "so a cell missing from it is a deviation nobody would be told about."
    )
    assert expected <= cells_named_in_readme(), (
        f"README.md names {sorted(cells_named_in_readme())} and does not cover {sorted(expected)}"
    )


def test_the_seed_omits_exactly_the_three_absent_cells() -> None:
    """The mechanism, read straight off ``0018b`` without a cluster.

    This is the assertion the whole G0 default rests on: 21 rows of a 24-cell product, and the
    three that are missing ARE the product. A missing row in a foreign-key target refuses, and the
    refusal names the constraint rather than an application rule.
    """
    seeded = cells_seeded()
    product = {(v, k) for v in VIRULENCE_BANDS for k in DISPOSITION_KINDS}
    unknown = seeded - product
    assert not unknown, f"0018b seeds cells outside the 4x6 product: {sorted(unknown)}"

    missing = product - seeded
    assert missing == set(ABSENT_CELLS), (
        f"0018b omits {sorted(missing)}; the conservative reading of G0 omits "
        f"{sorted(ABSENT_CELLS)}.\n"
        "A cell that appears here is a verdict that becomes legal for every writer with no code "
        "change anywhere — which is the correct mechanism (opening a cell should be a data "
        "amendment with a named approver and a bumped policy_version) and exactly why it must be "
        "observable. Owner: kernel/render-and-foundation, template "
        "packages/trappoint-sql/templates/0018_clearance_legal.sql.j2."
    )
    assert len(seeded) == EXPECTED_LATTICE_ROWS, (
        f"0018b seeds {len(seeded)} distinct cells, expected {EXPECTED_LATTICE_ROWS}"
    )


def test_the_conservative_assertion_is_read_only() -> None:
    """ "Safe to run against production" is a claim, so it is checked rather than asserted."""
    code = strip_sql_comments(EXT_ASSERTION.read_text(encoding="utf-8"))
    for pattern in WRITE_TOKENS:
        match = pattern.search(code)
        assert match is None, (
            f"clearance_legal.conservative.sql contains {match.group(0)!r}. It is documented as a "
            "read-only check that is safe to run against production and from a read-only MCP "
            "session; a write in it makes that sentence false."
        )
    assert code.lstrip().upper().startswith("SELECT")


def test_the_conservative_assertion_is_one_statement() -> None:
    """One statement, so an operator can paste it anywhere — including the MCP surface, which
    accepts exactly one statement per call and caps the response at 25 rows."""
    statements = split_statements(EXT_ASSERTION.read_text(encoding="utf-8"))
    assert len(statements) == 1, (
        f"{len(statements)} statements. The managed MCP surface takes ONE statement per call; a "
        "two-statement check cannot be run from the place an auditor is most likely to be sitting."
    )


@pytest.mark.parametrize("path", [EXT_ASSERTION], ids=lambda p: p.name)
def test_no_banned_constructs_in_the_extension_point(path: Path) -> None:
    """The sequence ban (D10) holds outside the apply path too.

    G1 measured that ``CREATE SEQUENCE`` succeeds on this cluster, which makes the lint
    load-bearing rather than decorative: the platform will not stop us, so the tree has to. A file
    that is pasted into a psql session is as capable of creating a sequence as one the runner
    applies.
    """
    code = strip_sql_comments(path.read_text(encoding="utf-8"))
    for pattern in BANNED_TOKENS:
        match = pattern.search(code)
        assert match is None, f"{path.name} contains the banned token {match.group(0)!r}"


def test_adr_0001_records_the_default_executed() -> None:
    """The extension point is downstream of a decision; the decision has to be on the record."""
    assert ADR.is_file(), f"{ADR.relative_to(REPO_ROOT)} is missing"
    text = ADR.read_text(encoding="utf-8")
    assert "G0" in text
    assert "pre-committed default is executed" in text or "default is executed" in text, (
        "ADR 0001 no longer says the pre-committed default is executed. Everything in "
        "db/ext/disposition_ext/ is downstream of that sentence."
    )
    for relation in ("disposition", "carried_disposition", "silence_ledger"):
        assert relation in text, f"ADR 0001 does not name {relation}"


@pytest.mark.parametrize(
    ("number", "relation"), COUNSEL_GATED_OBJECTS, ids=[r for _, r in COUNSEL_GATED_OBJECTS]
)
def test_every_counsel_gated_object_declares_it(number: str, relation: str) -> None:
    """ADR 0001 names five counsel-gated files; each must say so where a reviewer reads it.

    **RED BY DESIGN for ``mainline_meas.silence_ledger`` (PL-2).** The migration that creates it
    declares ``COUNSEL-GATED: no``, and ADR 0001 lists it as one of the five — "ships
    **unprivileged** — treated as discoverable by default" is a *legal* posture, not a technical
    one, and it is precisely the posture G0 question 2 was written to test. The header is where a
    reviewer of that file finds out that its placement was a decision rather than a default.

    The number is deliberately not asserted. ADR 0001 and BUILD_PLAN §2.1 both cite ``0086`` and
    the recall band landed the object at ``0084``; the gate is about the object, and pinning the
    slot would assert the wrong thing and would keep failing after somebody renumbered it.

    Owner of the fix: the recall domain, band 0080-0089z.
    """
    path = migration_for_relation(relation) if number == "*" else migration_by_number(number)
    assert path is not None, (
        f"no migration in the tree creates {relation}. ADR 0001 names it as one of the five "
        "counsel-gated objects, so its absence is either an unlanded band or a stale ADR."
    )
    declared = (header_value(path.read_text(encoding="utf-8"), "-- COUNSEL-GATED:") or "").lower()
    assert declared.startswith("yes"), (
        f"{path.name} creates {relation} and declares `COUNSEL-GATED: {declared or '(absent)'}`.\n"
        f"ADR 0001 (docs/adr/0001-g0-counsel.md) lists {relation} among the five files the G0 "
        "decision covers, and records the conservative reading applied to it. A file that does "
        "not declare the gate is a file whose next editor will not know one exists, and the cost "
        "of that is a legal posture changed by somebody who did not know they were changing one."
    )


@pytest.mark.parametrize(("name", "what"), R3_MIRRORED_NAMES, ids=[n for n, _ in R3_MIRRORED_NAMES])
def test_spec_r3_gives_the_carried_family_mirrored_exhibit_names(name: str, what: str) -> None:
    """spec R-3 — Exhibit Uniqueness — over the counsel-gated carried family.

    **RED BY DESIGN (PL-2).** ``0069_carried_disposition.sql`` names these two constraints
    ``bounded`` and ``substantive``, which ``mainline.disposition`` and
    ``mainline.mechanism_predicate`` also use. R-3 is not a style rule:

        A refusal-bearing constraint, unique index or trigger-function name MUST be unique across
        the whole database schema, not merely within its table. The exhibit name alone MUST
        identify the refusal without a qualifying table.

    The consequence is concrete and already written down. ``spec/conformance/manifest.toml`` case
    **CF-66** carries ``expect_constraint = "carried_bounded"`` as a literal string, and
    ``packages/trappoint-conformance/cases/cf66_carried_bounded.py`` asserts it. The case is
    skipped today (its capability token is undeclared), so this mismatch is currently invisible —
    which is the worst place for it to be, because it will surface as a conformance failure at the
    moment the corpus is turned on rather than now.

    Owner of the fix: ``datamodel/ex-dm-disposition``, ``verticals/mainline/db/migrations/
    0069_carried_disposition.sql``. Rename ``bounded`` -> ``carried_bounded`` and ``substantive``
    -> ``carried_substantive``; nothing else in the tree references either name.
    """
    path = MIGRATIONS_DIR / "0069_carried_disposition.sql"
    if not path.is_file():
        pytest.skip("0069_carried_disposition.sql has not landed yet (datamodel/ex-dm-disposition)")
    code = strip_sql_comments(path.read_text(encoding="utf-8"))
    assert re.search(rf"\bCONSTRAINT\s+{name}\b", code), (
        f"0069_carried_disposition.sql declares no constraint named {name!r} ({what}).\n"
        "spec/TRAPPOINT-SPEC.md R-3 requires the mirrored name, spec/CHANGELOG.md names this exact "
        "pair, and spec/conformance/manifest.toml CF-66 asserts `carried_bounded` by string. "
        "Owner of the fix: datamodel/ex-dm-disposition."
    )


def test_the_conformance_corpus_still_expects_the_name_this_suite_checks() -> None:
    """Guard the guard: if CF-66's expected constraint changes, R3_MIRRORED_NAMES is stale.

    A test that hardcodes a string from another file has to notice when that file moves, or it
    becomes an assertion about history.
    """
    if not SPEC_MANIFEST.is_file():
        pytest.skip("spec/conformance/manifest.toml is not present in this tree")
    manifest = tomllib.loads(SPEC_MANIFEST.read_text(encoding="utf-8"))
    cases = {case["id"]: case for case in manifest.get("case", [])}
    if "CF-66" not in cases:
        pytest.skip("CF-66 is not in the conformance manifest")
    assert cases["CF-66"]["expect_constraint"] == "carried_bounded", (
        "CF-66 no longer expects `carried_bounded`. Update R3_MIRRORED_NAMES in this file to match "
        "the manifest, which is the authority on what the corpus asserts."
    )
    assert cases["CF-66"]["expect_sqlstate"] == "23514"


# ══════════════════════════════════════════════════════════════════════════════════════════════
# CLUSTER DISCOVERY — four sources, and a skip that names which one is missing.
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


def _wait_until_ready(dsn: str, deadline: float) -> bool:
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
    """A dead Docker daemon does not refuse ``docker info``; it BLOCKS, and an uncaught
    ``TimeoutExpired`` in a fixture turns a run that should have SKIPPED into a suite of ERRORs."""
    try:
        return subprocess.run(
            ["docker", *args], capture_output=True, text=True, timeout=timeout, check=False
        )
    except (subprocess.TimeoutExpired, OSError):
        return None


def _from_env() -> Cluster | None:
    for name in ("MAINLINE_TEST_DSN", "COCKROACH_URL", "CRDB_URL", "TRAPPOINT_DSN"):
        value = os.environ.get(name)
        if value:
            return Cluster(dsn=value, provenance=f"${name}")
    return None


def _from_local_binary(tmp: Path) -> Cluster | None:
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
    if _wait_until_ready(dsn, time.monotonic() + READY_TIMEOUT_S):
        return Cluster(dsn=dsn, provenance=f"local `cockroach` binary on {port}", proc=proc)
    proc.terminate()
    return None


def _from_docker() -> Cluster | None:
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
    if _wait_until_ready(dsn, time.monotonic() + READY_TIMEOUT_S):
        return Cluster(dsn=dsn, provenance=f"docker {CRDB_IMAGE} on {port}", owns_docker=True)
    _docker(["rm", "-f", CONTAINER_NAME], timeout=DOCKER_PROBE_TIMEOUT_S)
    return None


@pytest.fixture(scope="session")
def gated_cluster(
    request: pytest.FixtureRequest, tmp_path_factory: pytest.TempPathFactory
) -> Iterator[Cluster]:
    """Cooperate with ``dm-runner``'s conftest when it exists, so schema suites share a cluster."""
    try:
        shared = request.getfixturevalue("dsn")
    except Exception:  # noqa: BLE001 — pytest does not export FixtureLookupError publicly
        shared = None
    if isinstance(shared, str) and shared:
        yield Cluster(dsn=shared, provenance="the `dsn` fixture from tests/integration/schema")
        return

    found = _from_env() or _from_local_binary(tmp_path_factory.mktemp("crdb")) or _from_docker()
    if found is None:
        pytest.skip(
            "no CockroachDB v26.2 reachable. Provide one of: tests/integration/schema/conftest.py "
            "with a session `dsn` fixture (dm-runner), $MAINLINE_TEST_DSN, a `cockroach` binary on "
            f"PATH, or a running Docker daemon for `docker run {CRDB_IMAGE}`. The G0 refusals are "
            "NOT verified by a skipped run."
        )
    try:
        yield found
    finally:
        if found.proc is not None:
            found.proc.terminate()
        if found.owns_docker:
            _docker(["rm", "-f", CONTAINER_NAME], timeout=DOCKER_PROBE_TIMEOUT_S)


def chain_files() -> list[Path]:
    """Every migration at or below ``APPLY_THROUGH``, in the order the runner applies them.

    Read by SHAPE rather than by name. Every file in this range belongs to another worker, and a
    prerequisite reader that hardcoded filenames would turn every legitimate change over there into
    a red test over here.
    """
    found = [
        path
        for path in sorted(MIGRATIONS_DIR.iterdir())
        if path.is_file()
        and MR5_FILENAME.match(path.name) is not None
        and int(path.name[:4]) <= APPLY_THROUGH
    ]
    return sorted(found, key=lambda p: p.name.removesuffix(".sql"))


@dataclass
class Lattice:
    dsn: str
    database: str
    prerequisite_failures: list[tuple[str, str, str]] = field(default_factory=list)

    def connect(self, *, autocommit: bool = True) -> Any:
        return psycopg.connect(self.dsn, autocommit=autocommit)


@pytest.fixture(scope="session")
def lattice(gated_cluster: Cluster) -> Iterator[Lattice]:
    """Apply the chain up to 0070 into a fresh database.

    A file that fails to apply is RECORDED, not raised. Every file in the range belongs to another
    worker and an unrelated failure — a reserved word in a measurement table, say — must not be
    reported as "the counsel gate is broken". What IS raised is a missing required relation, and
    the message carries the failure list so the cause is one read away.
    """
    from psycopg.conninfo import make_conninfo

    database = f"mainline_gated_{uuid.uuid4().hex[:10]}"
    with psycopg.connect(gated_cluster.dsn, autocommit=True) as admin:
        admin.execute(f"CREATE DATABASE {database}")

    # Re-point at the fresh database WITHOUT string surgery on the URL: an env-supplied DSN may
    # carry `options=--cluster=…` (CockroachDB Cloud), an sslrootcert path, or no path component
    # at all, and every one of those breaks a naive rsplit on "/".
    dsn = make_conninfo(gated_cluster.dsn, dbname=database)

    failures: list[tuple[str, str, str]] = []
    applied = 0
    files = chain_files()
    with psycopg.connect(dsn, autocommit=True) as conn:
        for path in files:
            try:
                for statement in split_statements(path.read_text(encoding="utf-8")):
                    conn.execute(statement)
            except psycopg.Error as exc:
                failures.append((path.name, str(exc.sqlstate), str(exc).splitlines()[0]))
            else:
                applied += 1

    print(
        f"\n[gated] cluster:  {gated_cluster.provenance}\n"
        f"[gated] database: {database}\n"
        f"[gated] applied {applied} of {len(files)} migrations at or below {APPLY_THROUGH:04d}"
    )
    for name, sqlstate, message in failures:
        print(f"[gated] PREREQUISITE NOT APPLIED — {name}: [{sqlstate}] {message}")

    try:
        yield Lattice(dsn=dsn, database=database, prerequisite_failures=failures)
    finally:
        with psycopg.connect(gated_cluster.dsn, autocommit=True) as admin:
            admin.execute(f"DROP DATABASE IF EXISTS {database} CASCADE")


@pytest.fixture
def conn(lattice: Lattice) -> Iterator[Any]:
    """One autocommit connection per test, with the required relations proved present first.

    Autocommit rather than a rolled-back transaction: a refused statement must not be able to hide
    behind a rollback that also erases the rows the test wrote before it. The two deviation tests
    that DO need a rollback open their own transactional connection and say why.
    """
    connection = lattice.connect()
    present = {
        row[0]
        for row in connection.execute(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema IN ('mainline', 'mainline_meas')"
        ).fetchall()
    }
    missing = [name for name in REQUIRED_RELATIONS if name not in present]
    if missing:
        connection.close()
        detail = "\n".join(f"    {n}: [{s}] {m}" for n, s, m in lattice.prerequisite_failures)
        pytest.skip(
            f"the cluster tier needs {missing} and the chain did not create them.\n"
            f"  migrations that failed to apply:\n{detail or '    (none)'}\n"
            "This is a SKIP and not a pass: the G0 refusals are unverified in this run."
        )
    try:
        yield connection
    finally:
        connection.close()


# ── fixture helpers: minting the rows a lattice refusal needs ─────────────────────────────────


def _d32(seed: str) -> bytes:
    """A 32-byte id. Real ids are sha256 over canonical bytes; these are sha256 over a label."""
    return hashlib.sha256(seed.encode("utf-8")).digest()


#: 120 characters is `substantive`'s floor on both disposition tables; every rationale in this
#: suite clears it so that the ONLY thing wrong with a refused row is the lattice cell.
RATIONALE = (
    "Standing verdict recorded for this control class after a full review of the precursor, its "
    "bonded events and the ancestry of every clause in scope."
)


@dataclass
class World:
    """The minimum set of rows a ``carried_disposition`` and a ``disposition`` insert need."""

    site_id: str
    event_id: str
    scope_id: str
    commit_id: bytes
    credential_id: bytes
    permit_id: str
    check_id: str
    receipt_id: str


def _build_world(conn: Any) -> World:
    """Mint one fresh site's worth of rows. A fresh ``site_id`` per test is the isolation
    primitive for this whole directory, and it is xdist-safe."""
    site = str(uuid.uuid4())
    tag = uuid.uuid4().hex[:10]

    conn.execute(
        "INSERT INTO mainline.site (site_id, site_code, site_role, tenant_id, taxonomy_ver) "
        "VALUES (%s, %s, %s, %s, 1)",
        (site, f"g0-{tag}".lower(), f"g0_{tag}".lower(), str(uuid.uuid4())),
    )
    commit_id = _d32(f"commit:{tag}")
    conn.execute(
        "INSERT INTO mainline.commit_obj "
        "(commit_id, site_id, gen, ref_name, author_sub, message, envelope, envelope_bytes) "
        "VALUES (%s, %s, 0, 'refs/heads/main', 'author', 'seed', '{}'::JSONB, b'envelope')",
        (commit_id, site),
    )
    scope_id = conn.execute(
        "INSERT INTO mainline.activity_node "
        "(site_id, level, label, activity_root, taxonomy_ver, induced_by, frozen) "
        "VALUES (%s, 1, %s, 'isolation', 1, 'human', true) RETURNING scope_id",
        (site, f"isolation-{tag}"),
    ).fetchone()[0]
    event_id = conn.execute(
        "INSERT INTO mainline.event "
        "(site_id, occurred_at, kind, title, narrative, source_object_key, source_sha256, "
        " severity_actual, severity_potential, severity_gate, severity_basis, canon_version) "
        "VALUES (%s, now() - INTERVAL '30 days', 'incident', 'fatality', 'narrative', "
        " 's3://evidence', %s, 5, 5, 5, 'coded_field', 1) RETURNING event_id",
        (site, _d32(f"source:{tag}")),
    ).fetchone()[0]
    credential_id = _d32(f"credential:{tag}")
    conn.execute(
        "INSERT INTO mainline.signing_credential "
        "(credential_id, signer_sub, public_key_cose, aaguid, transports, attachment, "
        " enrolment_assurance) "
        "VALUES (%s, 'signer', b'cose', b'aaguid', ARRAY['usb']::STRING[], 'cross-platform', "
        " 'hr_system_of_record')",
        (credential_id,),
    )

    # The disposition side needs an obligation and a receipt line: `fk_exposure` binds a signature
    # to an obligation the substrate actually rendered to that actor (MI12), so a lattice test on
    # `disposition` has to build a legal exposure first or it fails for the wrong reason.
    doc_id = conn.execute(
        "INSERT INTO mainline.doc (site_id, doc_code, title) VALUES (%s, %s, 'Isolation procedure')"
        " RETURNING doc_id",
        (site, f"PRO-{tag}"),
    ).fetchone()[0]
    clause_uuid = str(uuid.uuid4())
    conn.execute(
        "INSERT INTO mainline.clause (clause_uuid, site_id, birth_commit, activity_root) "
        "VALUES (%s, %s, %s, 'isolation')",
        (clause_uuid, site, commit_id),
    )
    conn.execute(
        "INSERT INTO mainline.clause_version "
        "(clause_uuid, gen, commit_id, site_id, doc_id, activity_root, ordinal, raw_text, "
        " canon_text, canon_version, canon_sha256, anchor_set, control_delta, delta_basis, "
        " blood_root, blood_peaks, blood_size, sev_max) "
        "VALUES (%s, 0, %s, %s, %s, 'isolation', 0, 'Isolate before entry.', "
        " 'isolate before entry', 1, %s, ARRAY['TAG-1']::STRING[], 'weaken', 'human', "
        " %s, ARRAY[]::BYTES[], 0, 5)",
        (clause_uuid, commit_id, site, doc_id, _d32(f"canon:{tag}"), _d32(f"blood:{tag}")),
    )
    permit_id = str(uuid.uuid4())
    conn.execute(
        "INSERT INTO mainline.permit "
        "(permit_id, site_id, site_role, external_ref, ref_name, horizon_at) "
        "VALUES (%s, %s, %s, %s, %s, now() + INTERVAL '7 days')",
        (permit_id, site, f"g0_{tag}".lower(), f"ext-{tag}", f"refs/permits/{tag}"),
    )
    check_id = str(uuid.uuid4())
    conn.execute(
        "INSERT INTO mainline.blocking_check "
        "(check_id, subject_kind, permit_id, site_id, clause_uuid, commit_id, origin, severity, "
        " virulence, closure_gen, evidence_summary) "
        "VALUES (%s, 'permit', %s, %s, %s, %s, 'blame_ancestry', 5, 'blood_fatal', 0, "
        " 'a fatality wrote this control')",
        (check_id, permit_id, site, clause_uuid, commit_id),
    )
    receipt_id = str(uuid.uuid4())
    conn.execute(
        "INSERT INTO mainline.exposure_receipt "
        "(receipt_id, subject_kind, permit_id, actor_sub, issued_hlc, expires_at, corpus_root, "
        " silence_receipt_id, policy_version, total_tokens, receipt_digest) "
        "VALUES (%s, 'permit', %s, 'signer', 1.0, now() + INTERVAL '1 hour', %s, %s, 'rp-1.0', "
        " 400, %s)",
        (receipt_id, permit_id, _d32(f"corpus:{tag}"), str(uuid.uuid4()), _d32(f"receipt:{tag}")),
    )
    conn.execute(
        "INSERT INTO mainline.exposure_line (receipt_id, check_id, payload_digest, tokens) "
        "VALUES (%s, %s, %s, 400)",
        (receipt_id, check_id, _d32(f"payload:{tag}")),
    )
    return World(
        site_id=site,
        event_id=str(event_id),
        scope_id=str(scope_id),
        commit_id=commit_id,
        credential_id=credential_id,
        permit_id=permit_id,
        check_id=check_id,
        receipt_id=receipt_id,
    )


def _carry(conn: Any, world: World, *, virulence: str, kind: str, rank: int = 6) -> None:
    """Write one carried disposition. Every column but ``(virulence, kind)`` is legal by
    construction, so a refusal can only be the lattice."""
    conn.execute(
        "INSERT INTO mainline.carried_disposition "
        "(site_id, event_id, scope_id, control_class, kind, virulence, rationale, signer_sub, "
        " signer_rank, signer_credential_id, max_ttl_hours, expires_at, min_signer_rank, "
        " anchor_commit) "
        "VALUES (%s, %s, %s, 'isolation', %s, %s, %s, 'signer', %s, %s, 12, "
        " now() + INTERVAL '6 hours', 1, %s)",
        (
            world.site_id,
            world.event_id,
            world.scope_id,
            kind,
            virulence,
            RATIONALE,
            rank,
            world.credential_id,
            world.commit_id,
        ),
    )


def _sign(conn: Any, world: World, *, virulence: str, kind: str, rank: int = 6) -> None:
    """Write one disposition against the obligation ``_build_world`` materialised.

    ``waiver_authority`` reads the FROZEN competency snapshot, so the snapshot carries
    ``ISOLATION_AUTHORITY``: without it a blood_* row is refused by that constraint instead and the
    test would prove the wrong thing.
    """
    snapshot = json.dumps({"authorisations": ["ISOLATION_AUTHORITY"], "rank": rank})
    conn.execute(
        "INSERT INTO mainline.disposition "
        "(check_id, receipt_id, subject_kind, permit_id, site_id, kind, virulence, closure_gen, "
        " defeater_code, defeater_vocab_sha256, rationale, evidence_sha256, signer_sub, "
        " signer_rank, signer_org, signer_credential_id, signature_alg, authenticator_data, "
        " client_data_json, user_verified, competency_snapshot, competency_source_id, "
        " competency_sha256, req_compensating, req_second_signer, req_foreign_org, req_predicate, "
        " req_reassert, min_signer_rank, deliberation_seconds, evidence_opened, "
        " prior_override_count, severity_snapshot) "
        "VALUES (%s, %s, 'permit', %s, %s, %s, %s, 0, 'precondition_absent', %s, %s, %s, 'signer', "
        " %s, 'operator', %s, 'ES256', b'authenticator', b'clientdata', true, %s::JSONB, %s, %s, "
        " false, false, false, false, false, 1, 600, true, 0, 5)",
        (
            world.check_id,
            world.receipt_id,
            world.permit_id,
            world.site_id,
            kind,
            virulence,
            _d32("vocab"),
            RATIONALE,
            _d32("evidence"),
            rank,
            world.credential_id,
            snapshot,
            str(uuid.uuid4()),
            _d32("competency"),
        ),
    )


def assert_refused(exc: Any, sqlstate: str, constraint: str) -> None:
    """A refusal is an exact SQLSTATE **and** an exact constraint name. Both, or neither.

    DM-10 exists because the constraint name is the courtroom exhibit. Both the structured
    diagnostic field and the message text are checked, and the failure prints what the server did
    say — if v26.2 carries the name in neither, that is a PLATFORM FINDING and not a test to relax.
    """
    assert exc.sqlstate == sqlstate, (
        f"expected SQLSTATE {sqlstate} naming {constraint!r}; got {exc.sqlstate}: {exc}"
    )
    diag_name = getattr(getattr(exc, "diag", None), "constraint_name", None)
    if diag_name == constraint or constraint in str(exc):
        return
    raise AssertionError(
        f"the refusal did not name the constraint {constraint!r}.\n"
        f"  diag.constraint_name: {diag_name!r}\n"
        f"  message:              {exc}"
    )


# ══════════════════════════════════════════════════════════════════════════════════════════════
# CLUSTER TIER — the conservative reading, executed.
# ══════════════════════════════════════════════════════════════════════════════════════════════


@pytest.mark.requires_cluster
def test_the_shipped_lattice_holds_twenty_one_of_twenty_four_cells(conn: Any) -> None:
    """21 rows of a 24-cell product, and the three that are missing are the product."""
    rows = {
        (str(virulence), str(kind))
        for virulence, kind in conn.execute(
            "SELECT virulence, kind FROM mainline.clearance_legal"
        ).fetchall()
    }
    assert len(rows) == EXPECTED_LATTICE_ROWS, (
        f"the lattice holds {len(rows)} cells, expected {EXPECTED_LATTICE_ROWS}"
    )
    for cell in ABSENT_CELLS:
        assert cell not in rows, (
            f"{cell} EXISTS in the shipped lattice. Under the conservative reading of G0 it is "
            "deliberately absent, and its presence makes that verdict legal for every writer with "
            "no code change anywhere."
        )


@pytest.mark.requires_cluster
@pytest.mark.parametrize(
    ("virulence", "kind"), ABSENT_CELLS, ids=[f"{v}.{k}" for v, k in ABSENT_CELLS]
)
def test_an_absent_cell_refuses_a_disposition(conn: Any, virulence: str, kind: str) -> None:
    """MI11 on ``mainline.disposition`` — the headline claim of ADR 0001, executed.

    The row is legal in every other respect: the signature clears ``rank_floor``, the frozen
    snapshot carries ``ISOLATION_AUTHORITY`` so ``waiver_authority`` is satisfied, the rationale
    clears ``substantive``, and ``fk_exposure`` resolves because the world built a receipt line for
    this obligation. The ONLY thing wrong is the verdict, and the database says so by name.
    """
    world = _build_world(conn)
    with pytest.raises(psycopg.Error) as excinfo:
        _sign(conn, world, virulence=virulence, kind=kind)
    assert_refused(excinfo.value, "23503", "fk_clearance")


@pytest.mark.requires_cluster
def test_a_present_cell_accepts_a_disposition(conn: Any) -> None:
    """The control. Without it, the three refusals above are consistent with a broken fixture."""
    world = _build_world(conn)
    _sign(conn, world, virulence="blood_fatal", kind="applied")
    count = conn.execute(
        "SELECT count(*) FROM mainline.disposition WHERE check_id = %s", (world.check_id,)
    ).fetchone()[0]
    assert count == 1


@pytest.mark.requires_cluster
@pytest.mark.parametrize(
    ("virulence", "kind"), ABSENT_CELLS, ids=[f"{v}.{k}" for v, k in ABSENT_CELLS]
)
def test_an_absent_cell_refuses_a_carried_disposition(conn: Any, virulence: str, kind: str) -> None:
    """MI11 on the CARRY path, which is the one that would otherwise be the way around it.

    A carried disposition is a signature made once and reused on every materially identical permit.
    If the lattice bound signing but not carrying, the whole conservative reading would be one
    ``carried_disposition`` row away from irrelevant: sign nothing forbidden, carry something
    forbidden, and every future permit in scope is cleared by a verdict that has no legal cell.
    """
    world = _build_world(conn)
    with pytest.raises(psycopg.Error) as excinfo:
        _carry(conn, world, virulence=virulence, kind=kind)
    assert_refused(excinfo.value, "23503", "fk_clearance")


@pytest.mark.requires_cluster
def test_a_present_cell_accepts_a_carried_disposition(conn: Any) -> None:
    """The control for the carry path."""
    world = _build_world(conn)
    _carry(conn, world, virulence="blood_fatal", kind="applied")
    count = conn.execute(
        "SELECT count(*) FROM mainline.carried_disposition WHERE site_id = %s", (world.site_id,)
    ).fetchone()[0]
    assert count == 1


@pytest.mark.requires_cluster
def test_the_conservative_assertion_returns_nothing_against_the_shipped_seed(conn: Any) -> None:
    """The executable copy is executed. An empty result set IS the assertion."""
    statement = split_statements(EXT_ASSERTION.read_text(encoding="utf-8"))[0]
    rows = conn.execute(statement).fetchall()
    assert rows == [], (
        "clearance_legal.conservative.sql reported deviations against the shipped seed:\n"
        + "\n".join(f"    {row}" for row in rows)
    )


@pytest.mark.requires_cluster
def test_the_conservative_assertion_detects_an_opened_cell(lattice: Lattice) -> None:
    """A check that has never fired is a check nobody has evidence works (PL-2).

    Runs inside an explicit transaction and rolls back, so the deviation exists only for the
    lifetime of the assertion and the shared database is byte-identical afterwards. This is the one
    place in the suite where a rollback is right: the thing being proved is that the detector
    *sees* a state, not that the state survives.
    """
    statement = split_statements(EXT_ASSERTION.read_text(encoding="utf-8"))[0]
    with psycopg.connect(lattice.dsn, autocommit=False) as conn:
        conn.execute(
            "INSERT INTO mainline.clearance_legal "
            "(virulence, kind, min_signer_rank, policy_version, approved_by_sub, approved_at) "
            "VALUES ('blood_fatal', 'mechanism_absent', 9, 'cl-test', 'TEST', "
            " TIMESTAMPTZ '2026-08-05T00:00:00Z')"
        )
        rows = conn.execute(statement).fetchall()
        conn.rollback()

    findings = {(row[0], row[1], row[2]) for row in rows}
    assert ("cell_opened", "blood_fatal", "mechanism_absent") in findings, (
        "the conservative assertion did not report a cell it was written to catch. Detected: "
        f"{sorted(findings)}"
    )


@pytest.mark.requires_cluster
def test_the_conservative_assertion_detects_a_removed_cell(lattice: Lattice) -> None:
    """The other drift: a cell REMOVED. It opens no gate, but it strips a legal verdict from
    operators who need one and presents in the field as "the sign button stopped working"."""
    statement = split_statements(EXT_ASSERTION.read_text(encoding="utf-8"))[0]
    with psycopg.connect(lattice.dsn, autocommit=False) as conn:
        conn.execute(
            "DELETE FROM mainline.clearance_legal WHERE virulence = 'routine' AND kind = 'applied'"
        )
        rows = conn.execute(statement).fetchall()
        conn.rollback()

    assert any(row[0] == "cardinality" for row in rows), (
        f"the cardinality arm did not fire after a cell was removed. Reported: {rows}"
    )


@pytest.mark.requires_cluster
def test_no_row_level_ttl_on_the_disposition_family(conn: Any) -> None:
    """Law 13 / DM-17, checked where it matters most.

    Row-level TTL is a background job that DELETES. On a disposition, a carried disposition or the
    clearance lattice it would be a background job that destroys the record of who cleared what —
    and expired rows are not filtered out of ``UPDATE`` and ``DELETE`` either, so the failure is
    silent in both directions. The Crimes (Document Destruction) Act 2006 (Vic) is the reason this
    is a test rather than a note.

    Read through ``SHOW CREATE TABLE`` rather than ``crdb_internal.create_statements``: the latter
    is refused on this cluster with ``InsufficientPrivilege`` unless ``allow_unsafe_internals`` is
    set, and a schema test that needs an unsafe session variable is a schema test that will not run
    where it matters. Measured on v26.2.5, not assumed.
    """
    offenders: list[str] = []
    for relation in COUNSEL_GATED_FAMILY:
        # `SHOW CREATE TABLE` takes an identifier, not a placeholder, so the relation name is
        # interpolated — from COUNSEL_GATED_FAMILY, a module constant of literals, never from a
        # row, an argument or the environment. S608 is suppressed on that basis and no other.
        statement = f"SELECT create_statement FROM [SHOW CREATE TABLE mainline.{relation}]"  # noqa: S608
        row = conn.execute(statement).fetchone()
        if row is not None and "ttl_expiration_expression" in row[0].lower():
            offenders.append(relation)
    assert offenders == [], (
        f"row-level TTL found on {offenders}. The TTL allowlist is exactly three tables — "
        "mainline_ops.outbox, mainline_meas.model_cache, mainline_meas.receipt_render_cache — and "
        "none of them is in schema `mainline`, least of all in the disposition family."
    )
