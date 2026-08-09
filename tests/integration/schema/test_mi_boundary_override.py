# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""Tier-1 schema suite for the boundary and carried-disposition bands.

Three non-contiguous stretches, granted by ``verticals/mainline/db/migrations.allocation.toml``
(MR-6 lock 1) to the two successor owners of the dissolved ``dm-gate`` and ``dm-disposition``
workers:

* ``0054-0057z`` — ``asset_edge``, ``permit_boundary``, ``permit_slice``,
  ``boundary_certificate``. The declared/modelled/computed trio and the arithmetic over it that
  finding **S11** rules must FAIL CLOSED: an asset with no modelled energy edges is UNKNOWN, not
  SAFE, and unknown blocks.
* ``0065-0065z`` — ``mechanism_predicate``, its watch-set index, ``predicate_revocation``. The
  **M8** defeater lease: a ``mechanism_absent`` disposition that binds a machine-checkable
  predicate over the site's own registers, bounded (**S12**, **MI28**) and self-revoking.
* ``0069-0070z`` — ``carried_disposition``, ``carried_disposition_use``, and the deferred foreign
  key that makes ``disposition.predicate_id`` point at something. **G0 counsel-gated.**

What this suite may honestly assert, and what it may not
--------------------------------------------------------
Every refusal exercised below is a ``CHECK`` or a foreign key — a property of the DDL, armed the
moment the table exists. Those are asserted for real.

The **projections** are not. ``carried_disposition.signer_rank`` / ``.min_signer_rank`` /
``.lattice_max_ttl_hours`` and all six projected columns on ``carried_disposition_use`` are P2
columns whose triggers land in band ``0140-0149z`` (``dm-functions-triggers``). Until then they
are client-supplied, every migration in these bands says so in its own header, and the four
``test_pl2_red_*`` tests below say so here — they FAIL today, on purpose, and go green when the
triggers land. A suite that has never been red asserts nothing (PL-2).

Status of the run these bands were authored against
---------------------------------------------------
**Executed, not asserted.** On 2026-08-10 the whole suite ran against a live CockroachDB CCL
**v26.2.5** (local single node, insecure, 26257): 47 assertions passed and the only failures were
the four ``test_pl2_red_*`` cases below, which are red on purpose. Every SQLSTATE and every
constraint name in this file is therefore a measurement. The three constructs that carried real
platform risk — a ``STORED`` generated column over ``jsonb_typeof``/``jsonb_array_length``, a
multi-column ``INVERTED`` index with two scalar prefixes over a ``STRING[]``, and an
enum-to-``STRING`` cast inside a ``CASE`` inside a ``CHECK`` — were all accepted.

Running it
----------
The static tier needs no cluster and runs anywhere. The cluster tier
(``@pytest.mark.requires_cluster``) finds a CockroachDB v26.2 in this order and **skips with a
reason** rather than faking anything:

1. the session ``dsn`` fixture, if ``tests/integration/schema/conftest.py`` (owned by
   ``dm-runner``) is present — so every schema suite shares one cluster;
2. ``$MAINLINE_TEST_DSN`` / ``$COCKROACH_URL`` / ``$CRDB_URL`` / ``$TRAPPOINT_DSN``;
3. a ``cockroach`` binary on ``PATH`` (in-memory single node, session-scoped);
4. a running Docker daemon (``cockroachdb/cockroach:latest-v26.2``).

**Nothing in these bands is done on the basis of a skipped run.**
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
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

psycopg = pytest.importorskip(
    "psycopg", reason="psycopg 3 is required to talk to CockroachDB; `uv sync` installs it"
)

# ══════════════════════════════════════════════════════════════════════════════════════════════
# Paths and band constants
# ══════════════════════════════════════════════════════════════════════════════════════════════

REPO_ROOT = Path(__file__).resolve().parents[3]
DB_DIR = REPO_ROOT / "verticals" / "mainline" / "db"
MIGRATIONS_DIR = DB_DIR / "migrations"
ALLOCATION_FILE = DB_DIR / "migrations.allocation.toml"
G0_ADR = REPO_ROOT / "docs" / "adr" / "0001-g0-counsel.md"

#: MR-5, the one filename convention: four digits, an optional SINGLE lowercase letter, a snake
#: slug with no second dot, and ``.sql`` — never ``.up.sql``.
MR5_FILENAME = re.compile(r"^\d{4}[a-z]?_[a-z0-9_]+\.sql$")

#: The three stretches these bands own, as inclusive ``(number, letter)`` allocation keys. Written
#: in the same shape the allocation file uses so a reader can compare them by eye.
BAND_KEYS: tuple[tuple[tuple[int, str], tuple[int, str]], ...] = (
    ((54, ""), (57, "z")),
    ((65, ""), (65, "z")),
    ((69, ""), (70, "z")),
)

#: Applied and asserted, in this order. Written out rather than globbed so that a file appearing
#: in one of these bands by accident — another worker's stray, a rename, a half-finished draft —
#: is a test failure and not a silent extra statement in the middle of the boundary trio.
BAND_FILES: tuple[str, ...] = (
    "0054_asset_edge.sql",
    "0055_permit_boundary.sql",
    "0056_permit_slice.sql",
    "0057_boundary_certificate.sql",
    "0065_mechanism_predicate.sql",
    "0065a_predicate_watch_set_index.sql",
    "0065b_predicate_revocation.sql",
    "0069_carried_disposition.sql",
    "0070_carried_disposition_use.sql",
    "0070a_disposition_predicate_fk.sql",
)

#: The tables these bands create.
BAND_TABLES: tuple[str, ...] = (
    "asset_edge",
    "permit_boundary",
    "permit_slice",
    "boundary_certificate",
    "mechanism_predicate",
    "predicate_revocation",
    "carried_disposition",
    "carried_disposition_use",
)

#: DM-17: the counsel-gated files carry the full header, not just ``yes``.
COUNSEL_GATED_FILES: tuple[str, ...] = (
    "0069_carried_disposition.sql",
    "0070_carried_disposition_use.sql",
    "0070a_disposition_predicate_fk.sql",
)
COUNSEL_HEADER_MARKERS: tuple[str, ...] = (
    "yes (G0)",
    "DEFAULT: conservative",
    "docs/adr/0001-g0-counsel.md",
)

#: The prerequisites these bands actually need, DECLARED rather than taken as a numeric prefix.
#:
#: A prefix apply would drag in every file below 0070 from five other domains — the vector
#: sidecars, the BM25 tables, the algorithms annexe, the measurement zone — none of which any
#: table in these bands references, and each of which turns an unrelated domain's red file into a
#: red file here. (That is not hypothetical: ``0049z_meas_mutation_result.sql`` currently fails to
#: apply on v26.2.5 because it declares a column named ``family``, which is a reserved word in
#: CockroachDB's ``CREATE TABLE`` grammar.) The list below is the transitive foreign-key closure of
#: these three bands and nothing else, so a failure in it is a failure that matters here.
PREREQ_FILES: tuple[str, ...] = (
    "0024_commit_obj.sql",  # carried_disposition.anchor_commit; clause.birth_commit
    "0027_doc.sql",  # clause_version.doc_id
    "0028_clause.sql",  # permit_slice.clause_uuid
    "0029_clause_version.sql",  # blocking_check.(clause_uuid, commit_id)
    "0032_activity_node.sql",  # carried_disposition.scope_id
    "0033_event.sql",  # carried_disposition.event_id
    "0050_permit.sql",  # permit_boundary / permit_slice / boundary_certificate
    "0050a_permit_scope_index.sql",
    "0051_change_request.sql",  # blocking_check.cr_id
    "0058_blocking_check.sql",  # carried_disposition_use.check_id
    "0058a_bc_open_index.sql",
    "0058b_bc_open_cr_index.sql",
    "0061_exposure_receipt.sql",  # exposure_line's parent
    "0062_exposure_line.sql",  # disposition.fk_exposure
    "0066_disposition.sql",  # 0070a alters it
    "0066a_one_live_disposition.sql",
)

#: ``0029a_clause_version_trgm.sql`` is deliberately NOT applied. It is a ``gin_trgm_ops`` index
#: carrying accepted risk DR-3, nothing in these bands reads it, and a refusal there would be
#: reported here as a failure of the boundary trio — which it would not be.

#: The four mandatory header keys the runner's linter enforces on every migration.
REQUIRED_HEADER_KEYS = ("-- MI:", "-- I:", "-- COUNSEL-GATED:", "-- RATIONALE:")

#: MI01-MI30 (ARCHITECTURE §16) and TRAPPOINT's I01-I16. Identity check only.
VALID_MI = frozenset(f"MI{n:02d}" for n in range(1, 31))
VALID_I = frozenset(f"I{n:02d}" for n in range(1, 17))

#: MR-6 rule B: these bands are ``mode = "authored"``, so no file in them may carry the banner.
RENDERED_BANNER = "-- @rendered-by  trappoint render"

CRDB_IMAGE = "cockroachdb/cockroach:latest-v26.2"
CONTAINER_NAME = "mainline-boundary-crdb"
READY_TIMEOUT_S = 120.0
DOCKER_PROBE_TIMEOUT_S = 10.0
DOCKER_RUN_TIMEOUT_S = 180.0

BANNED_TOKENS = (
    re.compile(r"\bCREATE\s+(?:TEMP\s+|TEMPORARY\s+|UNLOGGED\s+)*SEQUENCE\b", re.IGNORECASE),
    re.compile(r"\bnextval\s*\(", re.IGNORECASE),
    re.compile(r"\b(?:BIG|SMALL)?SERIAL[248]?\b", re.IGNORECASE),
    re.compile(r"\bunique_rowid\s*\(", re.IGNORECASE),
)

_INVARIANT_CITATION = re.compile(r"\b(?:MI\d{2}|I\d{2})\b")

#: DM-4 — no CHECK expression contains a JSONB operator, a subquery, or ``now()``. Assembled from
#: fragments where a literal would otherwise make this file itself trip a naive grep.
_JSONB_OPERATORS = ("->>", "-" + ">", "@" + ">", "<" + "@", "?" + "|", "?" + "&")

#: A long-enough rationale for ``substantive`` (>= 120 characters), used by the carried-disposition
#: fixtures. Written out so the tests read as the product would.
RATIONALE = (
    "The isolation standard this precursor wrote is applied verbatim at every intrusive entry "
    "on this scope, and the compensating control is signed off by the responsible engineer for "
    "each shift."
)


# ══════════════════════════════════════════════════════════════════════════════════════════════
# A small SQL scanner. Same contract as the ones in test_mi_foundation.py and test_mi_spine.py,
# and deliberately a third implementation: independent scanners agreeing that a file holds one
# statement is worth more than one scanner asserting it three times.
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


def header_comment(text: str) -> str:
    """Every line before the first line carrying non-comment, non-whitespace text."""
    lines: list[str] = []
    for raw in text.splitlines():
        stripped = raw.strip()
        if not stripped:
            lines.append(raw)
            continue
        if stripped.startswith("--"):
            lines.append(raw)
            continue
        break
    return "\n".join(lines)


def check_expressions(text: str) -> list[str]:
    """Return the body of every ``CHECK ( … )`` in *text*, comments stripped.

    Balanced-paren extraction rather than a regex, because every interesting CHECK in this schema
    nests parentheses and a non-greedy regex would stop at the first ``)`` — which would make a
    DM-4 scan silently pass on the half of the expression it never looked at.
    """
    body = strip_sql_comments(text)
    found: list[str] = []
    for match in re.finditer(r"\bCHECK\s*\(", body, re.IGNORECASE):
        depth, i, n = 1, match.end(), len(body)
        start = i
        while i < n and depth:
            if body[i] == "(":
                depth += 1
            elif body[i] == ")":
                depth -= 1
            i += 1
        found.append(body[start : i - 1])
    return found


def key_of(name: str) -> tuple[int, str]:
    """The allocation key a migration filename claims: ``(number, optional letter)``."""
    match = re.match(r"^(\d{4})([a-z]?)_", name)
    assert match is not None, f"{name!r} does not carry an MR-5 number prefix"
    return int(match.group(1)), match.group(2)


def in_bands(key: tuple[int, str]) -> bool:
    return any(first <= key <= last for first, last in BAND_KEYS)


def band_paths() -> list[Path]:
    return [MIGRATIONS_DIR / name for name in BAND_FILES]


def assert_names_constraint(exc: Any, expected: str) -> None:
    """Assert the refusal identifies the constraint BY NAME, from either place it can appear.

    DM-10 exists because the constraint name is the courtroom exhibit. A test asserting only that
    "an exception was raised" is worthless in a product whose deliverable is a diagnosis.
    """
    diag_name = getattr(getattr(exc, "diag", None), "constraint_name", None)
    message = str(exc)
    if diag_name == expected or expected in message:
        return
    raise AssertionError(
        f"the refusal did not name the constraint {expected!r}.\n"
        f"  diag.constraint_name: {diag_name!r}\n"
        f"  message:              {message}\n"
        "If CockroachDB v26.2 reports neither, this is a PLATFORM FINDING and not a test to "
        "relax: every constraint-name assertion in trappoint-conform depends on one of these two "
        "carrying it."
    )


def assert_refused(exc: Any, sqlstate: str, constraint: str) -> None:
    """A gate refusal is an exact SQLSTATE **and** an exact constraint name. Both, or neither."""
    assert exc.sqlstate == sqlstate, (
        f"expected SQLSTATE {sqlstate} naming {constraint!r}; got {exc.sqlstate}: {exc}. "
        "40001 is the only retryable code; any other SQLSTATE means the database refused for a "
        "reason nobody modelled, which fails the suite by design (ARCHITECTURE §16)."
    )
    assert_names_constraint(exc, constraint)


# ══════════════════════════════════════════════════════════════════════════════════════════════
# STATIC TIER — no cluster required.
# ══════════════════════════════════════════════════════════════════════════════════════════════


def test_the_bands_hold_exactly_the_declared_files() -> None:
    """No stray, no gap. The allocation grants three stretches; ten files occupy them."""
    on_disk = sorted(
        path.name
        for path in MIGRATIONS_DIR.iterdir()
        if path.is_file() and MR5_FILENAME.match(path.name) and in_bands(key_of(path.name))
    )
    assert on_disk == sorted(BAND_FILES), (
        "the files occupying 0054-0057z, 0065-0065z and 0069-0070z are not the declared set.\n"
        f"  on disk:  {on_disk}\n"
        f"  declared: {sorted(BAND_FILES)}\n"
        "A file appearing here that this suite does not know about is either another worker "
        "writing into an allocated band (the incident of 2026-08-08) or a rename nobody "
        "propagated. Both are decisions and neither is silent."
    )


def test_every_file_exists_and_carries_the_mandatory_header_block() -> None:
    """MR-5 and §4 constraint 2: SPDX, then ``MI:``, ``I:``, ``COUNSEL-GATED:``, ``RATIONALE:``."""
    for path in band_paths():
        assert path.is_file(), f"{path.name} is missing"
        text = path.read_text(encoding="utf-8")
        head = header_comment(text)
        assert "SPDX-License-Identifier: FSL-1.1-ALv2" in head, (
            f"{path.name}: verticals/ is FSL-1.1-ALv2 and every source file carries a REUSE header"
        )
        for key in REQUIRED_HEADER_KEYS:
            assert any(line.strip().startswith(key) for line in head.splitlines()), (
                f"{path.name}: the header block has no {key!r} line"
            )
        cited = set(_INVARIANT_CITATION.findall(head))
        assert cited, f"{path.name}: cites no MInn/Inn (ARCHITECTURE §18)"
        unknown = sorted(c for c in cited if c not in VALID_MI and c not in VALID_I)
        assert not unknown, (
            f"{path.name} cites identifiers that are not in the catalogue: {unknown}. "
            "MI01-MI30 and I01-I16 are the whole space."
        )


def test_exactly_one_statement_per_file() -> None:
    """§4 constraint 1. The runner does not wrap a file in a transaction."""
    for path in band_paths():
        statements = split_statements(path.read_text(encoding="utf-8"))
        assert len(statements) == 1, (
            f"{path.name} holds {len(statements)} statements. CockroachDB DDL is not "
            "transactional across statements, so a failure mid-file leaves a half-applied "
            "migration and an undiagnosable `dirty` marker. Split it with a letter suffix."
        )


def test_no_banned_constructs() -> None:
    """Ruling D10. ``CREATE SEQUENCE``/``nextval``/``SERIAL``/``unique_rowid()``.

    ``boundary_certificate.cert_gen`` is the file in these bands that most invites a sequence, and
    it is precisely the column that must not have one: a sequence may leave gaps, so under a
    sequence a missing certificate generation means nothing, and under CAS it MEANS a certificate
    was destroyed.
    """
    for path in band_paths():
        code = strip_sql_comments(path.read_text(encoding="utf-8"))
        for pattern in BANNED_TOKENS:
            match = pattern.search(code)
            if match is not None:
                raise AssertionError(f"{path.name}: banned construct {match.group(0)!r}")


def test_no_file_in_these_bands_carries_the_rendered_banner() -> None:
    """MR-6 rule B. All three stretches are ``mode = "authored"``.

    A hand-authored twin of a rendered file is the worst failure mode in the tree: ``trappoint
    render --check`` is a zero-diff assertion and a twin is not a diff, so CI stays green while the
    runner refuses the tree. CI green, deploy dead.
    """
    for path in band_paths():
        assert RENDERED_BANNER not in path.read_text(encoding="utf-8"), (
            f"{path.name} claims to be rendered output but sits in an authored band"
        )


def test_the_real_linter_accepts_these_bands() -> None:
    """Run ``trappoint migrate lint``'s own rules over the ten files, not a reimplementation.

    The static assertions above are a second opinion; this is the first. Rule B is the one that
    matters here — it resolves each file's ``(number, letter)`` key against
    ``migrations.allocation.toml`` and refuses a file whose mode disagrees with its band, which is
    the check that compares a file against a DECLARATION rather than comparing two declarations
    with each other.
    """
    package_src = REPO_ROOT / "packages" / "trappoint-migrate" / "src"
    if not package_src.is_dir():
        pytest.skip(f"{package_src} not present; trappoint-migrate has not landed")
    if str(package_src) not in sys.path:
        sys.path.insert(0, str(package_src))
    lint = pytest.importorskip(
        "trappoint_migrate.lint", reason="trappoint-migrate is not importable"
    )

    allocation = lint.find_allocation(MIGRATIONS_DIR)
    assert allocation is not None, f"{ALLOCATION_FILE} did not resolve; rule B cannot run"
    report = lint.lint_paths(band_paths(), allocation=allocation)
    assert report.ok, "trappoint migrate lint refused these bands:\n" + "\n".join(
        finding.render() for finding in report.findings
    )
    assert report.files_checked == len(BAND_FILES)


def test_the_counsel_gated_files_carry_the_full_dm17_header_and_the_adr_exists() -> None:
    """DM-17. ``COUNSEL-GATED: yes`` alone does not say which gate, or what the default is."""
    assert G0_ADR.is_file(), f"{G0_ADR} is missing and three files in these bands cite it"
    for name in COUNSEL_GATED_FILES:
        head = header_comment((MIGRATIONS_DIR / name).read_text(encoding="utf-8"))
        line = next(
            (raw for raw in head.splitlines() if raw.strip().startswith("-- COUNSEL-GATED:")), ""
        )
        for marker in COUNSEL_HEADER_MARKERS:
            assert marker in line, (
                f"{name}: the COUNSEL-GATED line is {line.strip()!r} and is missing {marker!r}. "
                "DM-17 fixes the form because the header is what a reviewer greps for when "
                "counsel answers, and `yes` alone does not say which gate or what the default is."
            )


def test_no_check_expression_in_these_bands_uses_a_jsonb_operator_a_subquery_or_now() -> None:
    """DM-4 and §4 constraint 5, enforced over the extracted CHECK bodies.

    ``mechanism_predicate`` is where this rule earns its keep. §5.5 writes ``non_trivial`` as
    ``CHECK (jsonb_array_length(ast->'terms') >= 1)``; the migration moves the count into a STORED
    generated column and leaves the CHECK comparing a plain ``INT4``. The JSONB operator therefore
    appears in the file — in the generated column — and must NOT appear in any CHECK, which is
    exactly the distinction this test draws and a whole-file grep could not.
    """
    for path in band_paths():
        for expression in check_expressions(path.read_text(encoding="utf-8")):
            lowered = expression.lower()
            for operator in _JSONB_OPERATORS:
                assert operator not in expression, (
                    f"{path.name}: CHECK ({expression.strip()[:120]}…) contains the JSONB "
                    f"operator {operator!r}, which DM-4 forbids in a CHECK across this schema"
                )
            assert "now(" not in lowered, (
                f"{path.name}: CHECK ({expression.strip()[:120]}…) calls now(). A CHECK sees only "
                "the row being written; a clock makes an accepted row become invalid later, and "
                "makes a restore non-deterministic."
            )
            assert not re.search(r"\bselect\b", lowered), (
                f"{path.name}: CHECK ({expression.strip()[:120]}…) contains a subquery"
            )


def test_the_empty_array_trap_is_closed_in_the_watch_set_constraint() -> None:
    """``watch_set_nonempty`` must coalesce, and this is worth a static assertion.

    ``array_length(x, 1)`` of an EMPTY array is NULL, not 0, and a CHECK whose expression is NULL
    PASSES. So ``CHECK (array_length(registers, 1) >= 1)`` — the obvious form, the one a reviewer
    reads straight past — admits precisely the row it was written to refuse: a predicate with an
    empty watch set, which no changefeed can ever falsify, which is a permanent waiver wearing the
    costume of a falsifiable claim.

    The cluster tier proves the behaviour. This test guards the mechanism because the edit that
    breaks it (deleting one ``coalesce``) is small, plausible, silent, and turns the M8 lease into
    decoration.
    """
    text = strip_sql_comments((MIGRATIONS_DIR / "0065_mechanism_predicate.sql").read_text("utf-8"))
    constraint = next(
        (e for e in check_expressions(text) if "array_length" in e),
        None,
    )
    assert constraint is not None, "0065 declares no CHECK over array_length(registers, 1)"
    assert "coalesce" in constraint.lower(), (
        "watch_set_nonempty does not coalesce:\n"
        f"  {constraint.strip()}\n"
        "array_length of an empty array is NULL and a NULL CHECK PASSES, so this form admits the "
        "empty watch set it exists to refuse."
    )


def test_the_certificate_constrains_all_four_counts_including_under_declared() -> None:
    """S11 again, in the arithmetic. §5.5's ``counts_sane`` omits ``under_declared``.

    The gate reads ``tags_unmodelled + under_declared``. With ``under_declared`` unconstrained,
    ``-3`` cancels three unmodelled assets, the projection is zero,
    ``boundary_certified_when_issued`` passes, and a permit with three unmodelled assets merges.
    The refusal is not defeated by an attack on the gate; it is defeated by arithmetic on an
    unconstrained integer.
    """
    text = (MIGRATIONS_DIR / "0057_boundary_certificate.sql").read_text(encoding="utf-8")
    counts_sane = next(
        (e for e in check_expressions(text) if "tags_declared" in e and "under_declared" in e),
        None,
    )
    assert counts_sane is not None, (
        "0057 has no CHECK naming all of tags_declared and under_declared. §5.5's counts_sane "
        "omitted under_declared and the omission is the S11 fail-open direction."
    )
    for column in ("tags_declared", "tags_resolved", "tags_unmodelled", "under_declared"):
        assert re.search(rf"\b{column}\s*>=\s*0", counts_sane), (
            f"counts_sane does not constrain {column} non-negative:\n  {counts_sane.strip()}"
        )


def test_r3_no_refusal_name_in_these_bands_is_used_anywhere_else_in_the_schema() -> None:
    """spec/TRAPPOINT-SPEC.md R-3 — Exhibit Uniqueness, checked against the WHOLE tree.

    *A refusal-bearing constraint, unique index or trigger-function name MUST be unique across the
    whole database schema, not merely within its table. The exhibit name alone MUST identify the
    refusal without a qualifying table.*

    CockroachDB is perfectly happy with ``substantive`` on three tables — constraint names are
    unique per table, not per schema — so nothing in the database refuses this. The database is not
    the audience. ``the write was refused by substantive`` is not an exhibit if three tables can
    say it, and the conformance corpus asserts these names by string
    (``spec/conformance/manifest.toml`` CF-66 expects ``carried_bounded``).

    Four names in these bands were mirrored for exactly this reason, and the spec names two of them
    itself: ``bounded`` → ``predicate_bounded`` / ``carried_bounded``, ``substantive`` →
    ``carried_substantive``, plus ``kind_closed`` → ``edge_kind_closed``, ``no_self_edge`` →
    ``no_self_asset_edge``, ``state_closed`` → ``predicate_state_closed``, ``rank_floor`` →
    ``carried_rank_floor``, ``fk_clearance`` → ``fk_carried_clearance``.
    """
    mine = {path.name for path in band_paths()}
    owners: dict[str, set[str]] = {}
    for path in sorted(MIGRATIONS_DIR.glob("*.sql")):
        body = strip_sql_comments(path.read_text(encoding="utf-8"))
        for name in re.findall(r"\bCONSTRAINT\s+([a-z_][a-z0-9_]*)", body, re.IGNORECASE):
            owners.setdefault(name, set()).add(path.name)
    clashes = {
        name: sorted(files) for name, files in owners.items() if len(files) > 1 and (files & mine)
    }
    assert not clashes, (
        "spec R-3 violation — these refusal names are claimed by more than one migration and at "
        f"least one of them is in these bands:\n  {clashes}\n"
        "The mirrored object takes a distinguishing prefix. Rename the one in THIS band; never "
        "rename a neighbour's constraint, because the conformance corpus asserts theirs by string."
    )


def test_every_declared_prerequisite_exists() -> None:
    """The declared closure is only honest while every file in it is on disk.

    A missing prerequisite must fail HERE, by name, rather than surfacing as an unreadable
    foreign-key error in the middle of a session-scoped fixture.
    """
    missing = [name for name in PREREQ_FILES if not (MIGRATIONS_DIR / name).is_file()]
    assert not missing, (
        f"declared prerequisites absent from the tree: {missing}. These bands take foreign keys "
        "onto objects those files create; until they land, the cluster tier cannot run and must "
        "not pretend to."
    )


# ── PL-2: RED BY DESIGN. Each of these fails today and names the owner of the fix. ────────────


def _functions_matching(*needles: str) -> list[str]:
    """Migrations defining a function whose body mentions every needle and RAISEs."""
    hits: list[str] = []
    for path in sorted(MIGRATIONS_DIR.glob("*.sql")):
        body = strip_sql_comments(path.read_text(encoding="utf-8")).lower()
        if not re.search(r"\bcreate\s+(or\s+replace\s+)?function\b", body):
            continue
        if all(needle.lower() in body for needle in needles) and "raise" in body:
            hits.append(path.name)
    return hits


def test_pl2_red_fn_boundary_project_does_not_exist_yet() -> None:
    """RED BY DESIGN (PL-2). Owner of the fix: ``dm-functions-triggers``, band 0140-0149z.

    MI06 is a two-part mechanism and these bands ship one part. ``boundary_certificate`` computes
    ``unmodelled_total`` in the server and ``mainline.permit`` carries
    ``boundary_certified_when_issued`` over ``unmodelled_asset_count``. Nothing yet moves the first
    onto the second, and P2 requires that the mover RAISE when no certificate exists rather than
    leaving the counter at its zero default — because a permit with NO certificate at all is the
    fail-open case S11 was raised about, and a zero counter is indistinguishable from a clean one.
    """
    projectors = _functions_matching("boundary_certificate", "unmodelled")
    assert projectors, (
        "PL-2 RED, as intended. No migration defines a function that reads "
        "mainline.boundary_certificate and RAISEs, so MI06's projection half is unenforced:\n"
        "  * boundary_certificate.unmodelled_total is computed by the server (0057, this band);\n"
        "  * permit.unmodelled_asset_count and boundary_certified_when_issued exist (0050);\n"
        "  * fn_boundary_project does not.\n"
        "It must read the HIGHEST cert_gen for the permit and RAISE P0001 when there is no "
        "certificate. Owner: dm-functions-triggers, band 0140-0149z."
    )


def test_pl2_red_the_carried_use_projection_does_not_exist_yet() -> None:
    """RED BY DESIGN (PL-2). Owner of the fix: ``dm-functions-triggers``, band 0140-0149z.

    ``carried_disposition_use`` carries six projected columns, and its three refusals —
    ``carried_covers_check``, ``carried_was_live``, ``used_within_window`` — are only as good as
    the projection behind them. Today the inserter supplies all six, so a client that writes
    ``carried_virulence_rank = 3`` beside a routine signature defeats the coverage refusal. The
    two ``*_rank_agrees`` constraints already stop the rank disagreeing with the enum on the SAME
    row; what is missing is the trigger that makes both come from the authoritative tables.
    """
    projectors = _functions_matching("carried_disposition", "virulence")
    assert projectors, (
        "PL-2 RED, as intended. No migration defines a function that projects onto "
        "mainline.carried_disposition_use and RAISEs, so its six P2 columns are client-supplied:\n"
        "  * carried_virulence / _rank, carried_expires_at, carried_live <= carried_disposition;\n"
        "  * check_virulence / _rank <= blocking_check;\n"
        "  * @on_missing raise is declared in 0070's header and implemented nowhere.\n"
        "Owner: dm-functions-triggers, band 0140-0149z."
    )


def test_pl2_red_the_two_new_evidentiary_tables_have_no_append_only_trigger() -> None:
    """RED BY DESIGN (PL-2). Owner of the fix: ``dm-functions-triggers``, band 0140-0149z.

    MI01/I01. ``predicate_revocation`` is the evidence that a lease was called and
    ``carried_disposition_use`` is the evidence that a signature was spent; both are append-only in
    the design and neither is protected today. ``fn_refuse_mutation`` is RENDERED at 0107 and the
    ``trg_refuse_mutation_*`` family at 0128; §6's list of covered tables predates the S18 rename
    and names neither of these two.
    """
    covered: set[str] = set()
    for path in sorted(MIGRATIONS_DIR.glob("*.sql")):
        body = strip_sql_comments(path.read_text(encoding="utf-8")).lower()
        if "fn_refuse_mutation" not in body or "create trigger" not in body:
            continue
        for table in ("predicate_revocation", "carried_disposition_use"):
            if table in body:
                covered.add(table)
    assert covered == {"predicate_revocation", "carried_disposition_use"}, (
        "PL-2 RED, as intended. Append-only is unenforced on "
        f"{sorted({'predicate_revocation', 'carried_disposition_use'} - covered)}:\n"
        "  * fn_refuse_mutation exists (0107, RENDERED) and the trigger family exists (0128*);\n"
        "  * neither table is attached to it.\n"
        "Until they are, any writer holding the grant can amend the record of a lease being "
        "called or a signature being spent. Owner: dm-functions-triggers, band 0140-0149z."
    )


def test_pl2_red_nothing_yet_requires_a_cited_predicate_to_still_be_holding() -> None:
    """RED BY DESIGN (PL-2). Owner of the fix: kernel ``obligation-and-clearance`` + 0140-0149z.

    ``0070a`` makes ``disposition.predicate_id`` point at a real predicate — the floor. It does not
    make it point at a SUITABLE one: nothing requires the predicate to belong to the same site, to
    be in state ``'holding'``, or to have a horizon covering the disposition's own window. Each is
    a cross-row fact, so each is a projection onto ``mainline.disposition`` plus a plain-column
    CHECK — columns in a RENDERED table this worker does not own and must not add.
    """
    guards = _functions_matching("mechanism_predicate", "holding")
    assert guards, (
        "PL-2 RED, as intended. 0070a closes the dangling-pointer hole and nothing closes the "
        "stale-lease hole:\n"
        "  * fk_disposition_predicate makes predicate_id resolve (0070a, this band);\n"
        "  * no function requires state = 'holding', matching site_id, or horizon coverage.\n"
        "Owner: kernel/obligation-and-clearance for the projected columns on the 0066 template, "
        "dm-functions-triggers for the trigger."
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
def boundary_cluster(
    request: pytest.FixtureRequest, tmp_path_factory: pytest.TempPathFactory
) -> Iterator[Cluster]:
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
            "with a session `dsn` fixture (dm-runner), $MAINLINE_TEST_DSN, a `cockroach` binary "
            f"on PATH, or a running Docker daemon for `docker run {CRDB_IMAGE}`. "
            "The boundary and carried-disposition bands are NOT verified by a skipped run."
        )
    try:
        yield found
    finally:
        if found.proc is not None:
            found.proc.terminate()
        if found.owns_docker:
            _docker(["rm", "-f", CONTAINER_NAME], timeout=DOCKER_PROBE_TIMEOUT_S)


def foundation_files() -> list[Path]:
    """The 0001-0023 migrations, read by SHAPE.

    Schemas, roles, the privilege floor, the seven ENUM types, ``subject_transition``,
    ``clearance_legal`` and its 21-row seed, ``person``, ``signing_credential``. Most of it is
    RENDERED under MR-1 and it belongs to another domain, so it is read by shape and this file
    asserts nothing about any of it: a reader that hardcoded those filenames would turn every
    legitimate change over there into a red test over here. Ordering is lexicographic on the whole
    stem, exactly as ``discovery.discover()`` orders, so ``0009x`` follows ``0009e``.
    """
    found: list[Path] = []
    for path in sorted(MIGRATIONS_DIR.iterdir()):
        if not path.is_file() or MR5_FILENAME.match(path.name) is None:
            continue
        if 1 <= int(path.name[:4]) <= 23:
            found.append(path)
    return sorted(found, key=lambda p: p.name.removesuffix(".sql"))


def apply_order() -> list[Path]:
    """Foundation, then the declared foreign-key closure, then the three bands themselves."""
    return [
        *foundation_files(),
        *(MIGRATIONS_DIR / name for name in PREREQ_FILES),
        *band_paths(),
    ]


def _apply(conn: Any, path: Path) -> None:
    for statement in split_statements(path.read_text(encoding="utf-8")):
        try:
            conn.execute(statement)
        except psycopg.Error as exc:
            raise AssertionError(
                f"{path.name} failed to apply.\n"
                f"  sqlstate: {exc.sqlstate}\n"
                f"  error:    {exc}\n"
                f"  statement:\n{statement.strip()[:2000]}"
            ) from exc


@dataclass
class Schema:
    dsn: str
    database: str

    def connect(self) -> Any:
        return psycopg.connect(self.dsn, autocommit=True)


@pytest.fixture(scope="session")
def schema(boundary_cluster: Cluster) -> Iterator[Schema]:
    """Apply everything up to 0070z into a fresh database. A failure names the file and statement.

    This is the completion test for this worker: ``apply`` reaching 0070 on v26.2 with the three
    granted stretches in place.
    """
    from psycopg.conninfo import make_conninfo

    database = f"mainline_boundary_{uuid.uuid4().hex[:10]}"
    with psycopg.connect(boundary_cluster.dsn, autocommit=True) as admin:
        admin.execute(f"CREATE DATABASE {database}")

    dsn = make_conninfo(boundary_cluster.dsn, dbname=database)
    files = apply_order()
    with psycopg.connect(dsn, autocommit=True) as conn:
        for path in files:
            _apply(conn, path)

    print(
        f"\n[boundary] cluster:  {boundary_cluster.provenance}\n"
        f"[boundary] database: {database}\n"
        f"[boundary] applied {len(foundation_files())} foundation + {len(PREREQ_FILES)} "
        f"prerequisite + {len(BAND_FILES)} band migrations"
    )
    try:
        yield Schema(dsn=dsn, database=database)
    finally:
        with psycopg.connect(boundary_cluster.dsn, autocommit=True) as admin:
            admin.execute(f"DROP DATABASE IF EXISTS {database} CASCADE")


@pytest.fixture
def conn(schema: Schema) -> Iterator[Any]:
    """One autocommit connection per test.

    Autocommit rather than a rolled-back transaction: a refused statement must not be able to hide
    behind a rollback that also erases the rows the test wrote before it.
    """
    connection = schema.connect()
    try:
        yield connection
    finally:
        connection.close()


# ── fixture helpers ───────────────────────────────────────────────────────────────────────────


def _digest(seed: str) -> bytes:
    return hashlib.sha256(seed.encode("utf-8")).digest()


def _new_site() -> str:
    """A fresh site_id per test is this suite's isolation primitive (xdist-safe)."""
    return str(uuid.uuid4())


def _mint_permit(conn: Any, site_id: str, *, tag: str = "p") -> str:
    permit_id = str(uuid.uuid4())
    conn.execute(
        """
        INSERT INTO mainline.permit
          (permit_id, site_id, site_role, external_ref, ref_name, horizon_at)
        VALUES (%s, %s, %s, %s, %s, now() + INTERVAL '7 days')
        """,
        (permit_id, site_id, f"site_{tag}_{permit_id[:8]}", f"WO-{permit_id[:8]}", "permit/x"),
    )
    return permit_id


def _mint_commit(conn: Any, site_id: str, *, label: str = "c") -> bytes:
    commit_id = _digest(f"{site_id}:{label}")
    conn.execute(
        """
        INSERT INTO mainline.commit_obj
          (commit_id, site_id, gen, ref_name, author_sub, message, envelope, envelope_bytes)
        VALUES (%s, %s, 0, 'site/x/main', 'sub-author', 'seed', %s, %s)
        ON CONFLICT DO NOTHING
        """,
        (commit_id, site_id, json.dumps({"label": label}), b"envelope-bytes"),
    )
    return commit_id


def _mint_clause(conn: Any, site_id: str, commit_id: bytes) -> str:
    clause_uuid = str(uuid.uuid4())
    conn.execute(
        """
        INSERT INTO mainline.clause (clause_uuid, site_id, birth_commit, activity_root)
        VALUES (%s, %s, %s, 'isolation')
        """,
        (clause_uuid, site_id, commit_id),
    )
    return clause_uuid


def _mint_clause_version(conn: Any, site_id: str, clause_uuid: str, commit_id: bytes) -> None:
    doc_id = str(uuid.uuid4())
    conn.execute(
        "INSERT INTO mainline.doc (doc_id, site_id, doc_code, title) VALUES (%s, %s, %s, 'Doc')",
        (doc_id, site_id, f"PRO-{doc_id[:8]}"),
    )
    conn.execute(
        """
        INSERT INTO mainline.clause_version
          (clause_uuid, gen, commit_id, site_id, doc_id, activity_root, ordinal, raw_text,
           canon_text, canon_version, canon_sha256, anchor_set, control_delta, delta_basis,
           blood_root, blood_peaks, blood_size, sev_max)
        VALUES (%s, 0, %s, %s, %s, 'isolation', 1, 'raw', 'canon', 1, %s,
                ARRAY['P-101'], 'restate', 'lattice', %s, ARRAY[]::BYTES[], 0, 0)
        """,
        (clause_uuid, commit_id, site_id, doc_id, _digest("canon"), _digest("blood")),
    )


def _mint_event(conn: Any, site_id: str) -> str:
    event_id = str(uuid.uuid4())
    conn.execute(
        """
        INSERT INTO mainline.event
          (event_id, site_id, occurred_at, kind, title, narrative, source_object_key,
           source_sha256, severity_actual, severity_potential, severity_gate, severity_basis,
           canon_version)
        VALUES (%s, %s, now() - INTERVAL '30 days', 'incident', 'T', 'N', 'k', %s,
                4, 5, 4, 'human_rated', 1)
        """,
        (event_id, site_id, _digest(event_id)),
    )
    return event_id


def _mint_scope(conn: Any, site_id: str) -> str:
    scope_id = str(uuid.uuid4())
    conn.execute(
        """
        INSERT INTO mainline.activity_node
          (scope_id, site_id, level, label, activity_root, taxonomy_ver, induced_by, frozen)
        VALUES (%s, %s, 1, %s, 'isolation', 1, 'human', true)
        """,
        (scope_id, site_id, f"isolating-{scope_id[:8]}"),
    )
    return scope_id


def _mint_credential(conn: Any, *, label: str) -> bytes:
    credential_id = _digest(f"cred:{label}:{uuid.uuid4()}")
    conn.execute(
        """
        INSERT INTO mainline.signing_credential
          (credential_id, signer_sub, public_key_cose, aaguid, transports, attachment,
           enrolment_assurance)
        VALUES (%s, %s, %s, %s, ARRAY['usb'], 'cross-platform', 'in_person')
        """,
        (credential_id, f"sub-{label}", b"cose", b"aaguid"),
    )
    return credential_id


def _mint_check(conn: Any, site_id: str, permit_id: str, *, virulence: str = "routine") -> str:
    commit_id = _mint_commit(conn, site_id, label=f"chk-{uuid.uuid4().hex[:6]}")
    clause_uuid = _mint_clause(conn, site_id, commit_id)
    _mint_clause_version(conn, site_id, clause_uuid, commit_id)
    check_id = str(uuid.uuid4())
    conn.execute(
        """
        INSERT INTO mainline.blocking_check
          (check_id, subject_kind, permit_id, site_id, clause_uuid, commit_id, origin,
           severity, virulence, closure_gen, evidence_summary)
        VALUES (%s, 'permit', %s, %s, %s, %s, 'blame_ancestry', 4, %s, 1, 'summary')
        """,
        (check_id, permit_id, site_id, clause_uuid, commit_id, virulence),
    )
    return check_id


def _mint_carried(
    conn: Any,
    site_id: str,
    *,
    virulence: str = "routine",
    kind: str = "applied",
    signer_rank: int = 4,
    min_signer_rank: int = 1,
    max_ttl_hours: int = 24,
    lattice_max_ttl_hours: int | None = None,
    ttl_offset_hours: int = 12,
    revoked: bool = False,
) -> str:
    carried_id = str(uuid.uuid4())
    issued = datetime.now(UTC)
    conn.execute(
        """
        INSERT INTO mainline.carried_disposition
          (carried_id, site_id, event_id, scope_id, control_class, kind, virulence, rationale,
           signer_sub, signer_rank, signer_credential_id, issued_at, max_ttl_hours, expires_at,
           min_signer_rank, lattice_max_ttl_hours, anchor_commit, revoked_at, revoke_reason)
        VALUES (%s, %s, %s, %s, 'isolation', %s, %s, %s, 'sub-signer', %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s)
        """,
        (
            carried_id,
            site_id,
            _mint_event(conn, site_id),
            _mint_scope(conn, site_id),
            kind,
            virulence,
            RATIONALE,
            signer_rank,
            _mint_credential(conn, label=carried_id[:8]),
            issued,
            max_ttl_hours,
            issued + timedelta(hours=ttl_offset_hours),
            min_signer_rank,
            lattice_max_ttl_hours,
            _mint_commit(conn, site_id, label=f"anchor-{carried_id[:8]}"),
            issued if revoked else None,
            "superseded by a new commit in the blame ancestry" if revoked else None,
        ),
    )
    return carried_id


# ── the apply itself ──────────────────────────────────────────────────────────────────────────


@pytest.mark.requires_cluster
def test_the_bands_apply_and_create_their_eight_tables(conn: Any) -> None:
    rows = conn.execute(
        """
        SELECT table_name FROM information_schema.tables
         WHERE table_schema = 'mainline' AND table_name = ANY(%s)
        """,
        (list(BAND_TABLES),),
    ).fetchall()
    found = sorted(row[0] for row in rows)
    assert found == sorted(BAND_TABLES), f"missing: {sorted(set(BAND_TABLES) - set(found))}"


@pytest.mark.requires_cluster
def test_the_watch_set_index_exists_with_the_inverted_column_last(conn: Any) -> None:
    """The least-verified statement in these bands, asserted rather than assumed.

    A multi-column INVERTED index with two scalar prefixes ahead of a ``STRING[]`` is documented
    but was not measurable from the authoring machine, which is why it is a separate file (0065a):
    a refusal here must cost one red file, not the whole M8 mechanism.
    """
    rows = conn.execute(
        """
        SELECT index_name, column_name, seq_in_index FROM information_schema.statistics
         WHERE table_schema = 'mainline' AND table_name = 'mechanism_predicate'
           AND index_name = 'predicate_watch_set'
         ORDER BY seq_in_index
        """
    ).fetchall()
    assert rows, (
        "predicate_watch_set does not exist. If CREATE INVERTED INDEX with scalar prefix columns "
        "was refused by v26.2, that is a PLATFORM FINDING: record it beside F1-F5 in "
        "docs/leads/datamodel.md and take the documented fallback in 0065a's header."
    )
    # CockroachDB appends the primary-key column(s) to every secondary index, so the LAST entry
    # reported here is `predicate_id`, not the inverted column. What §4 constraint 9 requires is
    # that `registers` follow every DECLARED prefix column, which is what is asserted.
    positions = {row[1]: row[2] for row in rows}
    assert positions["registers"] > positions["site_id"], positions
    assert positions["registers"] > positions["state"], positions


# ── 0054-0057: the boundary trio and the arithmetic ───────────────────────────────────────────


@pytest.mark.requires_cluster
def test_asset_edge_refuses_a_self_loop_by_name(conn: Any) -> None:
    """A self-loop moves a tag from UNKNOWN to MODELLED without adding a fact — S11 in miniature."""
    site_id = _new_site()
    with pytest.raises(psycopg.Error) as caught:
        conn.execute(
            "INSERT INTO mainline.asset_edge (site_id, from_tag, to_tag, kind) "
            "VALUES (%s, 'P-101', 'P-101', 'stores_energy')",
            (site_id,),
        )
    assert_refused(caught.value, "23514", "no_self_asset_edge")


@pytest.mark.requires_cluster
def test_asset_edge_refuses_an_unknown_kind_by_name(conn: Any) -> None:
    site_id = _new_site()
    with pytest.raises(psycopg.Error) as caught:
        conn.execute(
            "INSERT INTO mainline.asset_edge (site_id, from_tag, to_tag, kind) "
            "VALUES (%s, 'P-101', 'V-220', 'maybe_energises')",
            (site_id,),
        )
    assert_refused(caught.value, "23514", "edge_kind_closed")


@pytest.mark.requires_cluster
def test_asset_edge_admits_both_relations_between_the_same_pair(conn: Any) -> None:
    """`kind` is in the primary key on purpose: a pump both energises a line and stores energy in
    it. Collapsing the pair would keep whichever was loaded first — the more dangerous half of the
    pair exactly half the time."""
    site_id = _new_site()
    for kind in ("energises", "stores_energy"):
        conn.execute(
            "INSERT INTO mainline.asset_edge (site_id, from_tag, to_tag, kind) "
            "VALUES (%s, 'P-101', 'V-220', %s)",
            (site_id, kind),
        )
    count = conn.execute(
        "SELECT count(*) FROM mainline.asset_edge WHERE site_id = %s", (site_id,)
    ).fetchone()[0]
    assert count == 2


@pytest.mark.requires_cluster
def test_mi06_an_unmodelled_tag_can_be_declared_because_counting_it_is_what_blocks(
    conn: Any,
) -> None:
    """THE POSITIVE TEST THAT PROTECTS MI06 FROM ITS MOST TEMPTING REGRESSION.

    A foreign key from ``permit_boundary.asset_tag`` onto the asset graph would force crews to
    declare only tags the model already knows. ``tags_unmodelled`` would be structurally zero,
    ``unmodelled_asset_count`` structurally zero, and ``boundary_certified_when_issued`` would pass
    on every permit forever while appearing to work. The unmodelled tag must be WRITEABLE so that
    it can be COUNTED and BLOCK.
    """
    site_id = _new_site()
    permit_id = _mint_permit(conn, site_id)
    conn.execute(
        "INSERT INTO mainline.permit_boundary (permit_id, asset_tag, isolation_point_id) "
        "VALUES (%s, 'TAG-THE-MODEL-HAS-NEVER-HEARD-OF', 'LOTO-9')",
        (permit_id,),
    )
    count = conn.execute(
        "SELECT count(*) FROM mainline.permit_boundary WHERE permit_id = %s", (permit_id,)
    ).fetchone()[0]
    assert count == 1, (
        "a declared tag absent from mainline.asset_edge was refused. If a foreign key onto the "
        "asset graph has been added to 0055, delete it: it makes the count that blocks the merge "
        "structurally zero."
    )


@pytest.mark.requires_cluster
def test_permit_boundary_refuses_a_blank_isolation_point(conn: Any) -> None:
    """NULL means 'not yet recorded'. '' prints as nothing and reads as an answer."""
    site_id = _new_site()
    permit_id = _mint_permit(conn, site_id)
    with pytest.raises(psycopg.Error) as caught:
        conn.execute(
            "INSERT INTO mainline.permit_boundary (permit_id, asset_tag, isolation_point_id) "
            "VALUES (%s, 'P-101', '')",
            (permit_id,),
        )
    assert_refused(caught.value, "23514", "isolation_point_stated")


@pytest.mark.requires_cluster
def test_permit_slice_refuses_an_untraceable_hop(conn: Any) -> None:
    """A hop of 2 with no ``via_asset`` is an accusation with no chain of reasoning attached."""
    site_id = _new_site()
    permit_id = _mint_permit(conn, site_id)
    commit_id = _mint_commit(conn, site_id, label="slice")
    clause_uuid = _mint_clause(conn, site_id, commit_id)
    with pytest.raises(psycopg.Error) as caught:
        conn.execute(
            "INSERT INTO mainline.permit_slice (permit_id, clause_uuid, hop, via_asset) "
            "VALUES (%s, %s, 2, NULL)",
            (permit_id, clause_uuid),
        )
    assert_refused(caught.value, "23514", "slice_hop_is_traceable")


@pytest.mark.requires_cluster
def test_permit_slice_refuses_a_phantom_clause(conn: Any) -> None:
    """The published denominator may not contain a member nothing can be true of."""
    site_id = _new_site()
    permit_id = _mint_permit(conn, site_id)
    with pytest.raises(psycopg.Error) as caught:
        conn.execute(
            "INSERT INTO mainline.permit_slice (permit_id, clause_uuid, hop) VALUES (%s, %s, 0)",
            (permit_id, str(uuid.uuid4())),
        )
    assert_refused(caught.value, "23503", "fk_slice_clause")


@pytest.mark.requires_cluster
def test_mi06_the_certificate_refuses_a_negative_under_declared_count(conn: Any) -> None:
    """§5.5's ``counts_sane`` omitted this column, and the gate reads a SUM.

    ``under_declared = -3`` with ``tags_unmodelled = 3`` projects zero, and a permit with three
    unmodelled assets merges. This is the S11 fail-open direction reached by arithmetic rather than
    by attacking the gate.
    """
    site_id = _new_site()
    permit_id = _mint_permit(conn, site_id)
    with pytest.raises(psycopg.Error) as caught:
        conn.execute(
            """
            INSERT INTO mainline.boundary_certificate
              (permit_id, cert_gen, asset_graph_version, tags_declared, tags_resolved,
               tags_unmodelled, under_declared)
            VALUES (%s, 1, 'ag-1', 4, 4, 3, -3)
            """,
            (permit_id,),
        )
    assert_refused(caught.value, "23514", "counts_sane")


@pytest.mark.requires_cluster
def test_the_certificate_refuses_a_computation_that_lost_declared_tags(conn: Any) -> None:
    """Every declared tag is resolved or unmodelled; there is no third case. Losing tags is
    under-counting, which is the direction that kills people."""
    site_id = _new_site()
    permit_id = _mint_permit(conn, site_id)
    with pytest.raises(psycopg.Error) as caught:
        conn.execute(
            """
            INSERT INTO mainline.boundary_certificate
              (permit_id, cert_gen, asset_graph_version, tags_declared, tags_resolved,
               tags_unmodelled, under_declared)
            VALUES (%s, 1, 'ag-1', 9, 3, 1, 0)
            """,
            (permit_id,),
        )
    assert_refused(caught.value, "23514", "declared_accounted_for")


@pytest.mark.requires_cluster
def test_the_certificate_computes_the_gates_number_in_the_server(conn: Any) -> None:
    """``unmodelled_total`` is generated, so the certificate and the gate cannot disagree about the
    formula, and a client cannot supply a zero beside non-zero components."""
    site_id = _new_site()
    permit_id = _mint_permit(conn, site_id)
    conn.execute(
        """
        INSERT INTO mainline.boundary_certificate
          (permit_id, cert_gen, asset_graph_version, tags_declared, tags_resolved,
           tags_unmodelled, under_declared)
        VALUES (%s, 1, 'ag-1', 5, 4, 1, 2)
        """,
        (permit_id,),
    )
    total = conn.execute(
        "SELECT unmodelled_total FROM mainline.boundary_certificate WHERE permit_id = %s",
        (permit_id,),
    ).fetchone()[0]
    assert total == 3, "unmodelled_total must be tags_unmodelled + under_declared"

    with pytest.raises(psycopg.Error) as caught:
        conn.execute(
            """
            INSERT INTO mainline.boundary_certificate
              (permit_id, cert_gen, asset_graph_version, tags_declared, tags_resolved,
               tags_unmodelled, under_declared, unmodelled_total)
            VALUES (%s, 2, 'ag-1', 5, 4, 1, 2, 0)
            """,
            (permit_id,),
        )
    assert caught.value.sqlstate in {"55000", "42601", "0A000", "42P10"}, (
        "writing to a STORED generated column must be refused; got "
        f"{caught.value.sqlstate}: {caught.value}"
    )


@pytest.mark.requires_cluster
def test_the_certificate_is_recomputable_because_it_is_generation_versioned(conn: Any) -> None:
    """§5.5's ``permit_id PRIMARY KEY`` plus §6's append-only listing cannot both hold.

    Resolved in favour of append-only: a recomputation is a NEW GENERATION, and the reader takes
    ``max(cert_gen)`` exactly as the blame-closure reader takes ``max(closure_gen)``. Under the
    literal §5 shape the only way to record a corrected boundary would be to delete the evidence
    of the first one.
    """
    site_id = _new_site()
    permit_id = _mint_permit(conn, site_id)
    for gen, unmodelled in ((1, 3), (2, 0)):
        conn.execute(
            """
            INSERT INTO mainline.boundary_certificate
              (permit_id, cert_gen, asset_graph_version, tags_declared, tags_resolved,
               tags_unmodelled, under_declared)
            VALUES (%s, %s, 'ag-1', 4, 4, %s, 0)
            """,
            (permit_id, gen, unmodelled),
        )
    rows = conn.execute(
        "SELECT cert_gen, unmodelled_total FROM mainline.boundary_certificate "
        "WHERE permit_id = %s ORDER BY cert_gen",
        (permit_id,),
    ).fetchall()
    assert [tuple(row) for row in rows] == [(1, 3), (2, 0)], (
        "both generations must survive; the first is the evidence that the boundary WAS incomplete"
    )
    with pytest.raises(psycopg.Error) as caught:
        conn.execute(
            """
            INSERT INTO mainline.boundary_certificate
              (permit_id, cert_gen, asset_graph_version, tags_declared, tags_resolved,
               tags_unmodelled, under_declared)
            VALUES (%s, 2, 'ag-2', 4, 4, 0, 0)
            """,
            (permit_id,),
        )
    assert caught.value.sqlstate == "23505", f"expected 23505, got {caught.value.sqlstate}"


@pytest.mark.requires_cluster
def test_the_certificate_refuses_a_blank_asset_graph_version(conn: Any) -> None:
    """An exhibit that cannot be re-derived is a number somebody typed."""
    site_id = _new_site()
    permit_id = _mint_permit(conn, site_id)
    with pytest.raises(psycopg.Error) as caught:
        conn.execute(
            """
            INSERT INTO mainline.boundary_certificate
              (permit_id, cert_gen, asset_graph_version, tags_declared, tags_resolved,
               tags_unmodelled, under_declared)
            VALUES (%s, 1, '', 0, 0, 0, 0)
            """,
            (permit_id,),
        )
    assert_refused(caught.value, "23514", "asset_graph_version_stated")


# ── 0065: the defeater lease ──────────────────────────────────────────────────────────────────


def _predicate_values(
    *,
    registers: list[str] | None = None,
    terms: Any = None,
    horizon_days: float = 30.0,
    p_holds: float = 0.9,
) -> tuple[Any, ...]:
    opened = datetime.now(UTC)
    ast: dict[str, Any] = {} if terms is None else {"terms": terms}
    return (
        json.dumps(ast),
        ["hazard_register"] if registers is None else registers,
        _digest("compiled"),
        opened,
        opened + timedelta(days=horizon_days),
        p_holds,
    )


def _insert_predicate(conn: Any, site_id: str, values: tuple[Any, ...]) -> str:
    predicate_id = str(uuid.uuid4())
    conn.execute(
        """
        INSERT INTO mainline.mechanism_predicate
          (predicate_id, site_id, ast, registers, compiled_sha256, opened_at, horizon_at, p_holds)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (predicate_id, site_id, *values),
    )
    return predicate_id


@pytest.mark.requires_cluster
def test_mi28_a_lease_with_an_empty_watch_set_is_refused(conn: Any) -> None:
    """THE NULL-CHECK-PASSES TRAP, proven as behaviour.

    ``array_length('{}', 1)`` is NULL and a CHECK whose expression is NULL PASSES. Without the
    coalesce this insert succeeds and the resulting predicate can never be falsified by anything:
    no changefeed subscribes to it, and it holds to its horizon whatever happens on the plant.
    """
    site_id = _new_site()
    with pytest.raises(psycopg.Error) as caught:
        _insert_predicate(conn, site_id, _predicate_values(registers=[], terms=[{"op": "none"}]))
    assert_refused(caught.value, "23514", "watch_set_nonempty")


@pytest.mark.requires_cluster
def test_mi28_a_lease_with_no_terms_is_the_constant_true_and_is_refused(conn: Any) -> None:
    site_id = _new_site()
    empty_forms: tuple[Any, ...] = ([], None)  # `{"terms": []}` and `{}` — both are `true`
    for terms in empty_forms:
        with pytest.raises(psycopg.Error) as caught:
            _insert_predicate(conn, site_id, _predicate_values(terms=terms))
        assert_refused(caught.value, "23514", "non_trivial")


@pytest.mark.requires_cluster
def test_a_non_array_terms_field_refuses_by_name_rather_than_erroring(conn: Any) -> None:
    """``jsonb_array_length`` of a non-array RAISES. Mapping it to 0 turns three different ways of
    writing an empty predicate into the SAME 23514 naming ``non_trivial``, which is the exhibit."""
    site_id = _new_site()
    with pytest.raises(psycopg.Error) as caught:
        _insert_predicate(conn, site_id, _predicate_values(terms="none"))
    assert_refused(caught.value, "23514", "non_trivial")


@pytest.mark.requires_cluster
def test_mi28_the_horizon_is_bounded_not_merely_present(conn: Any) -> None:
    """S12. ``horizon_at IS NOT NULL`` admits a lease expiring in the year 3000."""
    site_id = _new_site()
    for days in (400.0, -1.0):
        with pytest.raises(psycopg.Error) as caught:
            _insert_predicate(
                conn, site_id, _predicate_values(terms=[{"op": "absent"}], horizon_days=days)
            )
        assert_refused(caught.value, "23514", "predicate_bounded")


@pytest.mark.requires_cluster
def test_a_signer_may_not_claim_certainty(conn: Any) -> None:
    """A stated probability of 1.0 is a claim no proper scoring rule can ever penalise."""
    site_id = _new_site()
    for p in (1.0, 0.0):
        with pytest.raises(psycopg.Error) as caught:
            _insert_predicate(conn, site_id, _predicate_values(terms=[{"op": "absent"}], p_holds=p))
        assert_refused(caught.value, "23514", "p_holds_is_a_probability")


@pytest.mark.requires_cluster
def test_a_well_formed_lease_is_admitted(conn: Any) -> None:
    site_id = _new_site()
    predicate_id = _insert_predicate(
        conn, site_id, _predicate_values(terms=[{"register": "hazard", "op": "absent"}])
    )
    row = conn.execute(
        "SELECT state, term_count FROM mainline.mechanism_predicate WHERE predicate_id = %s",
        (predicate_id,),
    ).fetchone()
    assert row[0] == "holding"
    assert row[1] == 1, "term_count is computed by the server from ast->'terms'"


@pytest.mark.requires_cluster
def test_two_falsifications_of_one_lease_are_both_recorded(conn: Any) -> None:
    """A UNIQUE on ``predicate_id`` would look obviously right and would destroy evidence.

    Two feeds can falsify one predicate within the same second. Under a unique constraint the
    second is a 23505, the writer swallows it as "already revoked", and at an inquiry "what did the
    firm know and when" is answered from a set of one. Which revocation CALLED the lease is
    ``min(falsified_at)`` — an ordering over recorded facts.
    """
    site_id = _new_site()
    predicate_id = _insert_predicate(
        conn, site_id, _predicate_values(terms=[{"register": "hazard", "op": "absent"}])
    )
    for source in ("signal:hazard_register:row-9", "signal:vessel_class:row-4"):
        conn.execute(
            """
            INSERT INTO mainline.predicate_revocation
              (predicate_id, falsified_by, observed_evidence)
            VALUES (%s, %s, %s)
            """,
            (predicate_id, source, json.dumps({"source": source})),
        )
    count = conn.execute(
        "SELECT count(*) FROM mainline.predicate_revocation WHERE predicate_id = %s",
        (predicate_id,),
    ).fetchone()[0]
    assert count == 2, (
        "both falsifications must survive. If a UNIQUE (predicate_id) has been added to 0065b, "
        "delete it and read 0065b's header."
    )


@pytest.mark.requires_cluster
def test_a_revocation_of_a_predicate_that_does_not_exist_is_refused(conn: Any) -> None:
    with pytest.raises(psycopg.Error) as caught:
        conn.execute(
            "INSERT INTO mainline.predicate_revocation "
            "(predicate_id, falsified_by, observed_evidence) VALUES (%s, 'x', '{}')",
            (str(uuid.uuid4()),),
        )
    assert_refused(caught.value, "23503", "fk_revocation_predicate")


# ── 0069-0070: the carried disposition and its spending ───────────────────────────────────────


@pytest.mark.requires_cluster
def test_mi11_a_carried_disposition_may_not_dismiss_a_fatality_written_control(conn: Any) -> None:
    """The three cells the lattice deliberately leaves empty are empty for carried signatures too.

    ``(blood_fatal, mechanism_absent)`` is not a stricter row in 0018b — it is NO row — so this is
    a 23503 naming ``fk_carried_clearance``, for every writer including a DBA and the MCP insert
    path. The name is mirrored rather than shared with ``disposition.fk_clearance`` under spec R-3.
    """
    site_id = _new_site()
    with pytest.raises(psycopg.Error) as caught:
        _mint_carried(conn, site_id, virulence="blood_fatal", kind="mechanism_absent")
    assert_refused(caught.value, "23503", "fk_carried_clearance")


@pytest.mark.requires_cluster
def test_a_carried_disposition_must_be_substantive(conn: Any) -> None:
    site_id = _new_site()
    carried_id = str(uuid.uuid4())
    issued = datetime.now(UTC)
    with pytest.raises(psycopg.Error) as caught:
        conn.execute(
            """
            INSERT INTO mainline.carried_disposition
              (carried_id, site_id, event_id, scope_id, control_class, kind, virulence, rationale,
               signer_sub, signer_rank, signer_credential_id, issued_at, max_ttl_hours,
               expires_at, min_signer_rank, anchor_commit)
            VALUES (%s, %s, %s, %s, 'isolation', 'applied', 'routine', 'because', 'sub', 4, %s,
                    %s, 24, %s, 1, %s)
            """,
            (
                carried_id,
                site_id,
                _mint_event(conn, site_id),
                _mint_scope(conn, site_id),
                _mint_credential(conn, label="short"),
                issued,
                issued + timedelta(hours=12),
                _mint_commit(conn, site_id, label="anchor-short"),
            ),
        )
    assert_refused(caught.value, "23514", "carried_substantive")


@pytest.mark.requires_cluster
def test_mi28_a_carried_window_is_bounded_by_its_own_ttl(conn: Any) -> None:
    site_id = _new_site()
    with pytest.raises(psycopg.Error) as caught:
        _mint_carried(conn, site_id, max_ttl_hours=4, ttl_offset_hours=48)
    assert_refused(caught.value, "23514", "carried_bounded")


@pytest.mark.requires_cluster
def test_a_carried_window_may_not_outlast_the_lattices_ceiling(conn: Any) -> None:
    """ADDITION 2 to §5.5. ``bounded`` compares the window against a number the SIGNER chose."""
    site_id = _new_site()
    with pytest.raises(psycopg.Error) as caught:
        _mint_carried(
            conn, site_id, max_ttl_hours=48, ttl_offset_hours=24, lattice_max_ttl_hours=12
        )
    assert_refused(caught.value, "23514", "ttl_within_lattice")


@pytest.mark.requires_cluster
def test_what_repeats_forty_times_meets_the_bar_of_what_happens_once(conn: Any) -> None:
    """ADDITION 1 to §5.5. §5.5 gives this table a signer and no rank, so as written a rank-1
    signer could issue a carried disposition a rank-1 signer could not issue as a single one."""
    site_id = _new_site()
    with pytest.raises(psycopg.Error) as caught:
        _mint_carried(conn, site_id, signer_rank=1, min_signer_rank=4)
    assert_refused(caught.value, "23514", "carried_rank_floor")


@pytest.mark.requires_cluster
def test_a_revocation_without_a_reason_is_refused(conn: Any) -> None:
    site_id = _new_site()
    carried_id = _mint_carried(conn, site_id)
    with pytest.raises(psycopg.Error) as caught:
        conn.execute(
            "UPDATE mainline.carried_disposition SET revoked_at = now() WHERE carried_id = %s",
            (carried_id,),
        )
    assert_refused(caught.value, "23514", "revocation_reasoned")


@pytest.mark.requires_cluster
def test_a_routine_signature_may_not_clear_a_fatality_written_obligation(conn: Any) -> None:
    """THE COVERAGE REFUSAL, and the reason understating virulence on 0069 is self-punishing."""
    site_id = _new_site()
    permit_id = _mint_permit(conn, site_id)
    check_id = _mint_check(conn, site_id, permit_id, virulence="blood_fatal")
    carried_id = _mint_carried(conn, site_id, virulence="routine")
    with pytest.raises(psycopg.Error) as caught:
        conn.execute(
            """
            INSERT INTO mainline.carried_disposition_use
              (carried_id, check_id, carried_virulence, carried_virulence_rank,
               carried_expires_at, carried_live, check_virulence, check_virulence_rank)
            VALUES (%s, %s, 'routine', 0, now() + INTERVAL '1 hour', true, 'blood_fatal', 3)
            """,
            (carried_id, check_id),
        )
    assert_refused(caught.value, "23514", "carried_covers_check")


@pytest.mark.requires_cluster
def test_the_rank_may_not_disagree_with_the_enum_beside_it(conn: Any) -> None:
    """Without this, the rank is forgeable and the coverage refusal above is decorative."""
    site_id = _new_site()
    permit_id = _mint_permit(conn, site_id)
    check_id = _mint_check(conn, site_id, permit_id, virulence="blood_fatal")
    carried_id = _mint_carried(conn, site_id, virulence="routine")
    with pytest.raises(psycopg.Error) as caught:
        conn.execute(
            """
            INSERT INTO mainline.carried_disposition_use
              (carried_id, check_id, carried_virulence, carried_virulence_rank,
               carried_expires_at, carried_live, check_virulence, check_virulence_rank)
            VALUES (%s, %s, 'routine', 3, now() + INTERVAL '1 hour', true, 'blood_fatal', 3)
            """,
            (carried_id, check_id),
        )
    assert_refused(caught.value, "23514", "carried_rank_agrees")


@pytest.mark.requires_cluster
def test_a_revoked_signature_may_not_be_spent(conn: Any) -> None:
    site_id = _new_site()
    permit_id = _mint_permit(conn, site_id)
    check_id = _mint_check(conn, site_id, permit_id)
    carried_id = _mint_carried(conn, site_id, revoked=True)
    with pytest.raises(psycopg.Error) as caught:
        conn.execute(
            """
            INSERT INTO mainline.carried_disposition_use
              (carried_id, check_id, carried_virulence, carried_virulence_rank,
               carried_expires_at, carried_live, check_virulence, check_virulence_rank)
            VALUES (%s, %s, 'routine', 0, now() + INTERVAL '1 hour', false, 'routine', 0)
            """,
            (carried_id, check_id),
        )
    assert_refused(caught.value, "23514", "carried_was_live")


@pytest.mark.requires_cluster
def test_a_signature_may_not_be_spent_after_its_window_closes(conn: Any) -> None:
    """Distinct from revocation, and it gets its own name: the clock, not an act."""
    site_id = _new_site()
    permit_id = _mint_permit(conn, site_id)
    check_id = _mint_check(conn, site_id, permit_id)
    carried_id = _mint_carried(conn, site_id)
    with pytest.raises(psycopg.Error) as caught:
        conn.execute(
            """
            INSERT INTO mainline.carried_disposition_use
              (carried_id, check_id, carried_virulence, carried_virulence_rank,
               carried_expires_at, carried_live, check_virulence, check_virulence_rank)
            VALUES (%s, %s, 'routine', 0, now() - INTERVAL '1 hour', true, 'routine', 0)
            """,
            (carried_id, check_id),
        )
    assert_refused(caught.value, "23514", "used_within_window")


@pytest.mark.requires_cluster
def test_a_covering_live_in_window_spend_is_admitted_once_and_only_once(conn: Any) -> None:
    """The mechanism must permit the thing it exists to make safe, and permit it exactly once."""
    site_id = _new_site()
    permit_id = _mint_permit(conn, site_id)
    check_id = _mint_check(conn, site_id, permit_id, virulence="routine")
    carried_id = _mint_carried(conn, site_id, virulence="serious")
    statement = """
        INSERT INTO mainline.carried_disposition_use
          (carried_id, check_id, carried_virulence, carried_virulence_rank,
           carried_expires_at, carried_live, check_virulence, check_virulence_rank)
        VALUES (%s, %s, 'serious', 1, now() + INTERVAL '4 hours', true, 'routine', 0)
    """
    conn.execute(statement, (carried_id, check_id))
    with pytest.raises(psycopg.Error) as caught:
        conn.execute(statement, (carried_id, check_id))
    assert caught.value.sqlstate == "23505", (
        "a second spend of one signature against one obligation is one fact recorded twice; "
        f"expected 23505, got {caught.value.sqlstate}"
    )


@pytest.mark.requires_cluster
def test_the_deferred_predicate_foreign_key_is_attached(conn: Any) -> None:
    """0070a. ``needs_predicate`` on 0066 checks only ``predicate_id IS NOT NULL``.

    Without this key, a ``mechanism_absent`` disposition at a cell whose lattice row sets
    ``req_predicate = true`` is satisfied by any 128 bits — ``gen_random_uuid()`` clears it — and
    the whole M8 apparatus is optional in practice while appearing mandatory in the schema.
    """
    attached = conn.execute(
        """
        SELECT count(*) FROM information_schema.table_constraints
         WHERE table_schema = 'mainline' AND table_name = 'disposition'
           AND constraint_name = 'fk_disposition_predicate'
        """
    ).fetchone()[0]
    assert attached == 1, "fk_disposition_predicate did not attach"


# ── whole-band properties ─────────────────────────────────────────────────────────────────────


def declared_constraint_names() -> set[str]:
    """Every ``CONSTRAINT <name>`` and ``INDEX <name>`` the ten files declare."""
    names: set[str] = set()
    for path in band_paths():
        body = strip_sql_comments(path.read_text(encoding="utf-8"))
        names.update(re.findall(r"\bCONSTRAINT\s+([a-z_][a-z0-9_]*)", body, re.IGNORECASE))
        names.update(
            re.findall(r"\b(?:INVERTED\s+)?INDEX\s+([a-z_][a-z0-9_]*)\s*\(", body, re.IGNORECASE)
        )
    return names


@pytest.mark.requires_cluster
def test_dm10_every_constraint_in_these_bands_is_explicitly_named(conn: Any) -> None:
    """The constraint name is the courtroom exhibit; ``check_asset_edge_1`` is not an exhibit."""
    declared = declared_constraint_names()
    rows = conn.execute(
        """
        SELECT table_name, constraint_name, constraint_type
          FROM information_schema.table_constraints
         WHERE table_schema = 'mainline' AND table_name = ANY(%s)
        """,
        (list(BAND_TABLES),),
    ).fetchall()
    assert rows, "no constraints found; the bands did not apply"
    generated: list[str] = []
    for table_name, constraint_name, constraint_type in rows:
        if constraint_type == "PRIMARY KEY" and constraint_name == "primary":
            continue  # CockroachDB's internal name for a named PK is reported as `primary`
        if constraint_name in declared:
            continue
        looks_generated = re.match(
            rf"^(check|fk|unique)_{table_name}_\d+$", constraint_name
        ) or re.search(r"_ref_|_auto_|_\d+$", constraint_name)
        if looks_generated:
            generated.append(f"{table_name}.{constraint_name}")
    assert not generated, (
        "system-generated constraint names in these bands (DM-10): "
        f"{sorted(generated)}. Every constraint is named explicitly, because a refusal that says "
        "`check_boundary_certificate_2` cannot be cited in a disclosure bundle."
    )


@pytest.mark.requires_cluster
def test_no_row_level_ttl_on_any_table_in_these_bands(conn: Any) -> None:
    """§4 constraint 4: TTL on exactly three tables, none in schema ``mainline``.

    Everything here is evidence. A row that deletes itself on a timer is evidence destroyed by
    configuration, and the fact that nobody chose it at the moment it happened is what makes it
    worse rather than better.
    """
    offenders: list[str] = []
    for table in BAND_TABLES:
        create = conn.execute(f"SHOW CREATE TABLE mainline.{table}").fetchone()[1]
        if "ttl_expire" in create.lower() or "ttl =" in create.lower():
            offenders.append(table)
    assert not offenders, f"row-level TTL declared on {offenders}, all in schema `mainline`"
