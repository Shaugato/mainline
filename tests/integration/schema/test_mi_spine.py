# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""Tier-1 schema suite for the spine band — migrations 0024-0031 and 0047-0049 (``dm-spine``).

What this band owns, and therefore what this file may honestly assert:

* the **history DAG** — ``commit_obj``, ``commit_edge``, ``ref`` — content-addressed, generation-
  ordered, and deliberately never conflated with the blame DAG;
* ``doc``, and with it **MI19**: a document cannot be superseded while it carries a control
  series. This is the one refusal in the band that is armed on day one, because it is a
  plain-column ``CHECK`` over a projected counter rather than a trigger;
* clause identity — ``clause``, ``clause_version`` with the M2 BLOODLINE columns, ``clause_band``;
* the vector sidecar ``clause_embedding``, created **empty** with **one** inline vector index;
* the Australian series system — ``control_series`` and ``carriage``, which is the authoritative
  source MI19's counter is projected from;
* ``identity_residue`` — Conservation of Blame Mass, the reason adversarial paraphrase raises a
  stronger gate rather than evading one.

What this band does NOT own, and what this file therefore does not pretend to prove:

* **the projections.** ``commit_edge.parent_gen``, ``ref.gen_head``, ``doc.open_token_count``,
  ``clause_embedding.(site_id, activity_root)``, ``clause_version.(gen, sev_max, blood_*)`` and
  ``identity_residue.max_ancestral_severity`` are all P2 columns whose triggers land in band
  0130-0199 (``dm-functions-triggers``). Until then they are client-supplied. Every migration in
  this band says so in its own header, and the two RED tests below say so here.
* **MI03.** ``identity_conserved_when_issued`` lives on ``mainline.permit`` (band 0050-0065).
  This band ships the residue rows that constraint counts; it does not ship the constraint.
* **MI15.** The BLOODLINE monotone guard is a ``BEFORE INSERT`` trigger in band 0130-0199. Its
  test here is RED by design and ``mi_catalogue.yaml`` carries MI15 as ``pending``.

Running it
----------
The static tier needs no cluster and runs anywhere, including the machine this band was authored
on, which had neither a ``cockroach`` binary nor a live Docker daemon. The cluster tier
(``@pytest.mark.requires_cluster``) finds a CockroachDB v26.2 in this order and **skips with a
reason** rather than faking anything:

1. the session ``dsn`` fixture, if ``tests/integration/schema/conftest.py`` (owned by
   ``dm-runner``) is present — so every schema suite shares one cluster;
2. ``$MAINLINE_TEST_DSN`` / ``$COCKROACH_URL`` / ``$CRDB_URL`` / ``$TRAPPOINT_DSN``;
3. a ``cockroach`` binary on ``PATH`` (in-memory single node, session-scoped);
4. a running Docker daemon (``cockroachdb/cockroach:latest-v26.2``).

**Nothing in this band is done on the basis of a skipped run**, and the skip message says which of
the four is missing. ``requires_cluster`` is used rather than the ``schema``/``shape``/``mi``
markers of ``test_mi_foundation.py`` for one reason only: it is registered in the root
``pyproject.toml`` today, and under ``--strict-markers`` an unregistered marker turns a red test
into a collection error, which is the one failure mode a red-before-green suite must not have.
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
import uuid
from collections.abc import Iterator
from dataclasses import dataclass
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

#: The band this worker owns, exclusively. Two contiguous stretches, per docs/leads/datamodel.md §3.
SPINE_RANGES: tuple[tuple[int, int], ...] = ((24, 31), (47, 49))

#: The foundation band this one depends on (worker `dm-foundation`): schemas, roles, the seven
#: ENUM types, site/person/signing_credential. `mainline.control_delta` (0010) is the only one of
#: those the spine actually needs, but applying the band whole is what the runner does and what a
#: fresh cluster sees, so the fixture does the same.
FOUNDATION_FIRST, FOUNDATION_LAST = 1, 23

#: Applied, in this order. Written out rather than globbed so that a file appearing in the band by
#: accident — another worker's stray, a rename, a half-finished draft — is a test failure and not
#: a silent extra `CREATE TABLE` in the middle of the spine.
BAND_FILES: tuple[str, ...] = (
    "0024_commit_obj.up.sql",
    "0025_commit_edge.up.sql",
    "0026_ref.up.sql",
    "0027_doc.up.sql",
    "0028_clause.up.sql",
    "0029_clause_version.up.sql",
    "0029a_clause_version_trgm.up.sql",
    "0030_clause_band.up.sql",
    "0031_clause_embedding.up.sql",
    "0047_control_series.up.sql",
    "0048_carriage.up.sql",
    "0049_identity_residue.up.sql",
)

#: Pre-written and deliberately NOT applied. DR-1's escape hatch: if v26.2 refuses an inline
#: VECTOR INDEX, the response is renaming two files rather than redesigning a table that three
#: others take a composite foreign key onto.
FALLBACK_FILES: tuple[str, ...] = (
    "0031_clause_embedding.fallback.sql",
    "0031a_clause_embedding_ann.fallback.sql",
)

#: The tables this band creates, in dependency order.
BAND_TABLES: tuple[str, ...] = (
    "commit_obj",
    "commit_edge",
    "ref",
    "doc",
    "clause",
    "clause_version",
    "clause_band",
    "clause_embedding",
    "control_series",
    "carriage",
    "identity_residue",
)

#: The four mandatory header keys the runner's linter enforces on every migration.
REQUIRED_HEADER_KEYS = ("-- MI:", "-- I:", "-- COUNSEL-GATED:", "-- RATIONALE:")

#: MI01-MI30 (ARCHITECTURE §16) and TRAPPOINT's I01-I16. Identity check only — "the id you cited
#: is a real id". The catalogue itself is `dm-runner`'s deliverable.
VALID_MI = frozenset(f"MI{n:02d}" for n in range(1, 31))
VALID_I = frozenset(f"I{n:02d}" for n in range(1, 17))

#: DM-9: `mainline.clause_blame_current` is the ONLY read path to the blame closure. The closure
#: table itself may be named in 0038, 0039 and queries/closure_write.sql — nowhere else, and
#: certainly not in this band. Assembled at runtime so this file does not itself contain the
#: literal it forbids, which would make `scripts/grep_closure_readpath.py` fail on the test that
#: enforces the rule.
CLOSURE_TABLE = "clause_blame" + "_closure"

CRDB_IMAGE = "cockroachdb/cockroach:latest-v26.2"
CONTAINER_NAME = "mainline-spine-crdb"
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


# ══════════════════════════════════════════════════════════════════════════════════════════════
# A small SQL scanner. Same contract as the one in test_mi_foundation.py and deliberately a
# second implementation: two independent scanners agreeing that a file holds one statement is
# worth more than one scanner asserting it twice.
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


def header_value(text: str, key: str) -> str | None:
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith(key):
            return stripped[len(key) :].strip()
    return None


def foundation_files() -> list[Path]:
    """The 0001-0023 ``.up.sql`` files this band depends on, ordered."""
    found: list[tuple[str, Path]] = []
    for path in sorted(MIGRATIONS_DIR.glob("*.up.sql")):
        match = re.match(r"^(\d{4})", path.name)
        if match and FOUNDATION_FIRST <= int(match.group(1)) <= FOUNDATION_LAST:
            found.append((path.name, path))
    return [p for _, p in sorted(found)]


def band_paths() -> list[Path]:
    return [MIGRATIONS_DIR / name for name in BAND_FILES]


def assert_names_constraint(exc: Any, expected: str) -> None:
    """Assert the refusal identifies the constraint BY NAME, from either place it can appear.

    DM-10 exists because the constraint name is the courtroom exhibit. A test asserting only that
    "an exception was raised" is worthless in a product whose deliverable is a diagnosis, so both
    the structured diagnostic field and the message text are checked, and the failure prints
    exactly what the server did say.
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


def test_band_is_exactly_the_declared_files() -> None:
    """0024-0031 and 0047-0049, no gaps, no strays, nothing from another worker's band."""
    on_disk = sorted(
        p.name
        for p in MIGRATIONS_DIR.glob("*.up.sql")
        if any(lo <= int(p.name[:4]) <= hi for lo, hi in SPINE_RANGES)
    )
    assert on_disk == sorted(BAND_FILES), (
        "the spine band on disk does not match the declared file list.\n"
        f"  on disk:  {on_disk}\n"
        f"  declared: {sorted(BAND_FILES)}\n"
        "File ownership is exclusive: an unexpected file inside 0024-0031 or 0047-0049 is another "
        "worker writing into this band, which corrupts the applied order."
    )
    for name in BAND_FILES:
        assert re.match(r"^\d{4}[a-z]*_[a-z0-9_]+\.up\.sql$", name), (
            f"{name} does not match NNNN[a-z]*_snake_name.up.sql (ruling D7). Ordering is "
            "lexicographic on the whole stem, so a filename outside that shape has no defined "
            "position in the applied sequence."
        )


def test_the_declared_order_is_the_lexicographic_order() -> None:
    """`0029` < `0029a` < `0030` is the whole mechanism behind the letter suffix (ruling D7)."""
    stems = [name.removesuffix(".up.sql") for name in BAND_FILES]
    assert stems == sorted(stems), (
        f"BAND_FILES is not in lexicographic order: {stems}. The runner applies in that order, "
        "so a list that disagrees with it applies a table before its dependency."
    )


@pytest.mark.parametrize(
    "path", band_paths() + [MIGRATIONS_DIR / n for n in FALLBACK_FILES], ids=lambda p: p.name
)
def test_every_file_carries_the_mandatory_header_block(path: Path) -> None:
    """MI / I / COUNSEL-GATED / RATIONALE, and every cited identifier is a real one."""
    text = path.read_text(encoding="utf-8")
    for key in REQUIRED_HEADER_KEYS:
        assert header_value(text, key) is not None, f"{path.name} has no `{key}` header line"

    cited = set(_INVARIANT_CITATION.findall(header_comment(text)))
    assert cited, f"{path.name} cites no invariant (ARCHITECTURE §18)"
    unknown = {c for c in cited if c not in VALID_MI and c not in VALID_I}
    assert not unknown, f"{path.name} cites identifiers that do not exist: {sorted(unknown)}"

    counsel = header_value(text, "-- COUNSEL-GATED:")
    assert counsel == "no", (
        f"{path.name} declares COUNSEL-GATED: {counsel!r}. Migrations 0001-0065 are "
        "counsel-independent by construction (BUILD_PLAN §2.1); the counsel-gated five are "
        "0066-0069 and 0086, and none of them is in this band."
    )


@pytest.mark.parametrize(
    "path", band_paths() + [MIGRATIONS_DIR / n for n in FALLBACK_FILES], ids=lambda p: p.name
)
def test_exactly_one_statement_per_file(path: Path) -> None:
    """The runner does not wrap a body in a transaction, so two statements is not atomic."""
    statements = split_statements(path.read_text(encoding="utf-8"))
    assert len(statements) == 1, (
        f"{path.name} holds {len(statements)} statements. CockroachDB DDL is not transactional "
        "across statements, so a failure leaves a half-applied file and an undiagnosable dirty "
        "marker. Split it with a lower-case letter suffix (ruling D7)."
    )


@pytest.mark.parametrize(
    "path", band_paths() + [MIGRATIONS_DIR / n for n in FALLBACK_FILES], ids=lambda p: p.name
)
def test_no_banned_constructs(path: Path) -> None:
    """Sequences are banned so that a gap in the ledger MEANS tampering. G1 GT-12 measured that
    `CREATE SEQUENCE` succeeds on this cluster, which makes the lint load-bearing rather than
    decorative — the platform will not stop us, so the tree has to."""
    code = strip_sql_comments(path.read_text(encoding="utf-8"))
    for pattern in BANNED_TOKENS:
        match = pattern.search(code)
        assert match is None, f"{path.name} contains the banned token {match.group(0)!r}"


@pytest.mark.parametrize(
    "path", band_paths() + [MIGRATIONS_DIR / n for n in FALLBACK_FILES], ids=lambda p: p.name
)
def test_no_file_in_this_band_names_the_closure_table(path: Path) -> None:
    """DM-9: `mainline.clause_blame_current` is the ONLY read path to the blame closure.

    Not a style rule. `max(closure_gen)` discipline has to be structural, because one forgotten
    call site silently reads a SUPERSEDED generation of the closure — and a superseded generation
    carries a LOWER maximum severity, which is a gate that opens. The comments are checked as well
    as the code, because `scripts/grep_closure_readpath.py` (dm-blame) greps text.
    """
    text = path.read_text(encoding="utf-8")
    assert CLOSURE_TABLE not in text, (
        f"{path.name} names {CLOSURE_TABLE} directly. DM-9 permits that only in 0038, 0039 and "
        "queries/closure_write.sql. Read the closure through mainline.clause_blame_current."
    )


@pytest.mark.parametrize("path", band_paths(), ids=lambda p: p.name)
def test_no_storing_clause_names_a_primary_key_column(path: Path) -> None:
    """CockroachDB refuses a PRIMARY KEY column inside STORING, and §5.2/§5.3 print two that do.

    Both are corrected in this band (0024's `by_branch_gen`, 0029's `by_commit`). This test is the
    guard that keeps the correction from being un-corrected by someone diffing against the
    architecture document and "restoring" it. Secondary indexes carry the primary key columns
    implicitly, so nothing is lost by the removal — but a table that fails to create is lost
    entirely.
    """
    code = strip_sql_comments(path.read_text(encoding="utf-8"))
    pk_match = re.search(r"PRIMARY\s+KEY\s*\(([^)]*)\)", code, re.IGNORECASE)
    if pk_match is None:
        return
    pk_columns = {c.strip().lower() for c in pk_match.group(1).split(",") if c.strip()}
    for storing in re.finditer(r"STORING\s*\(([^)]*)\)", code, re.IGNORECASE):
        stored = {c.strip().lower() for c in storing.group(1).split(",") if c.strip()}
        overlap = stored & pk_columns
        assert not overlap, (
            f"{path.name}: STORING names the primary-key column(s) {sorted(overlap)}. "
            "CockroachDB refuses this, and the column is in the secondary index anyway."
        )


def test_clause_version_declares_gen_before_commit_id_in_its_primary_key() -> None:
    """The single most consequential column ordering in the schema, asserted at the file level.

    `PRIMARY KEY (clause_uuid, gen, commit_id)` makes "what did this clause say at generation N" a
    PK-ordered RANGE SCAN and bisect a binary search over it. Swap the last two and the same
    question becomes one lookup into mainline.commit_obj per version, then a sort — which on a
    clause with hundreds of versions is the difference between a bisect that fits the gate's
    latency budget and one nobody runs. Asserted here as well as against the live cluster because
    the file is what a reviewer reads.
    """
    code = strip_sql_comments(
        (MIGRATIONS_DIR / "0029_clause_version.up.sql").read_text(encoding="utf-8")
    )
    match = re.search(
        r"CONSTRAINT\s+clause_version_pk\s+PRIMARY\s+KEY\s*\(([^)]*)\)", code, re.IGNORECASE
    )
    assert match is not None, "0029 does not declare a named primary key `clause_version_pk`"
    columns = [c.strip().lower() for c in match.group(1).split(",")]
    assert columns == ["clause_uuid", "gen", "commit_id"], (
        f"clause_version's primary key is {columns}; it must be "
        "['clause_uuid', 'gen', 'commit_id'] — gen BEFORE commit_id."
    )


def test_clause_embedding_declares_exactly_one_vector_index_inline() -> None:
    """One vector index per table (§4.1 law 7), declared inline so the table is created empty."""
    code = strip_sql_comments(
        (MIGRATIONS_DIR / "0031_clause_embedding.up.sql").read_text(encoding="utf-8")
    )
    declarations = re.findall(r"VECTOR\s+INDEX\s+(\w+)\s*\(([^)]*)\)", code, re.IGNORECASE)
    assert len(declarations) == 1, (
        f"0031 declares {len(declarations)} vector indexes; the platform supports one per table "
        "and the sidecar shape exists precisely so that one is enough."
    )
    name, columns = declarations[0]
    assert name == "ce_ann", (
        f"the vector index is named {name!r}. G1's GT-06 measured that the optimizer does NOT "
        "choose a vector index unhinted at demo scale, so every ANN arm pins it by name "
        "(`FROM mainline.clause_embedding@ce_ann`). The name is part of the query contract."
    )
    parts = [c.strip().lower() for c in columns.split(",")]
    assert parts[:2] == ["site_id", "activity_root"], (
        f"prefix columns are {parts[:2]}; they must be (site_id, activity_root). C-SPANN keeps "
        "one k-means tree per distinct prefix VALUE, so the prefix selects the tree that is "
        "searched — it is not a filter."
    )
    assert parts[-1].endswith("vector_cosine_ops"), (
        f"the vector column element is {parts[-1]!r}. CockroachDB's default opclass is "
        "vector_l2_ops (`<->`); the arms use cosine (`<=>`), so omitting the opclass builds an "
        "index the queries cannot use — which presents as 'the index exists and it is still slow'."
    )


def test_the_fallback_pair_exists_and_matches_the_live_table_column_for_column() -> None:
    """DR-1 is a file swap, and a swap is only a swap if the two variants are interchangeable.

    If the fallback declared even one column differently, taking it under pressure would change
    the shape of a table that three others hold a composite foreign key onto — which is a redesign
    wearing a fallback's name.
    """
    for name in FALLBACK_FILES:
        assert (MIGRATIONS_DIR / name).is_file(), f"{name} is missing; DR-1 has no escape hatch"

    def columns_of(path: Path) -> list[str]:
        code = strip_sql_comments(path.read_text(encoding="utf-8"))
        body = code[code.index("(") + 1 : code.rindex(")")]
        out: list[str] = []
        depth = 0
        current: list[str] = []
        for ch in body:
            if ch == "(":
                depth += 1
            elif ch == ")":
                depth -= 1
            if ch == "," and depth == 0:
                out.append("".join(current).strip())
                current = []
                continue
            current.append(ch)
        out.append("".join(current).strip())
        return [
            " ".join(item.split())
            for item in out
            if item and not re.match(r"^(VECTOR\s+INDEX|INDEX|INVERTED\s+INDEX)\b", item, re.I)
        ]

    live = columns_of(MIGRATIONS_DIR / "0031_clause_embedding.up.sql")
    fallback = columns_of(MIGRATIONS_DIR / "0031_clause_embedding.fallback.sql")
    assert live == fallback, (
        "the live and fallback variants of mainline.clause_embedding disagree.\n"
        f"  only in live:     {[c for c in live if c not in fallback]}\n"
        f"  only in fallback: {[c for c in fallback if c not in live]}\n"
        "They must differ by exactly one thing: the inline `VECTOR INDEX ce_ann (…)` line."
    )

    ann = (MIGRATIONS_DIR / "0031a_clause_embedding_ann.fallback.sql").read_text(encoding="utf-8")
    missing = [token for token in ("ce_ann", "vector_cosine_ops") if token not in ann]
    assert not missing, (
        f"the fallback ANN file does not mention {missing}. It must create the index under the "
        "same name and opclass as the live variant, or the swap changes the query contract."
    )


def test_the_fallback_files_are_not_in_the_applied_band() -> None:
    """They are inert until someone renames them. Applying both variants creates the table twice."""
    for name in FALLBACK_FILES:
        assert name not in BAND_FILES
        assert not name.endswith(".up.sql"), (
            f"{name} ends in .up.sql, which makes it part of the applied sequence. The fallback "
            "must stay inert until GT-06 actually fails."
        )


def _load_discovery() -> Any:
    """Import ``trappoint_migrate.discovery``, from the installed workspace or from source.

    The source-tree fallback is here so that the blocker this test reports is visible in a plain
    checkout, not only after ``uv sync``. A cross-domain blocker that only shows up in a fully
    provisioned environment is a blocker that gets found late.
    """
    import importlib
    import sys

    try:
        return importlib.import_module("trappoint_migrate.discovery")
    except ImportError:
        pass
    src = REPO_ROOT / "packages" / "trappoint-migrate" / "src"
    if not src.is_dir():
        return None
    if str(src) not in sys.path:
        sys.path.insert(0, str(src))
    try:
        return importlib.import_module("trappoint_migrate.discovery")
    except ImportError:
        return None


def test_runner_must_exclude_fallback_files_from_discovery() -> None:
    """RED BY DESIGN. Owner of the fix: ``dm-runner``, ``trappoint_migrate.discovery``.

    ``discover()`` computes a version stem by stripping ``.sql``/``.up.sql`` and then requires it
    to match ``^\\d{4}[a-z]*_[a-z0-9_]+$``. ``0031_clause_embedding.fallback.sql`` yields
    ``0031_clause_embedding.fallback`` — a dot in the slug — so discovery RAISES
    ``MigrationTreeInvalid`` and **the whole migration tree becomes unappliable while a fallback
    file sits beside it**. That blocks this band's completion test (``apply`` succeeding through
    0049) and ``dm-recall-tables``' too, which ships two fallback files for the same reason.

    The fix is three lines in ``discovery.discover()`` — skip any name ending ``.fallback.sql``
    before the version check, exactly as ``.down.sql`` is special-cased — plus the matching skip
    in ``lint._iter_files`` if fallbacks should not be citation-linted (they are today, and they
    pass, so leaving them linted is also fine).

    This test fails until that lands. It is not ``xfail``: an ``xfail`` that passes when it fails
    is exactly the accounting the red-before-green ratchet has to be able to see through.
    """
    discovery = _load_discovery()
    if discovery is None:
        pytest.skip(
            "trappoint_migrate.discovery is neither installed nor present at "
            "packages/trappoint-migrate/src; `uv sync` installs the workspace"
        )
    try:
        found = discovery.discover(MIGRATIONS_DIR)
    except Exception as exc:  # the exception type is dm-runner's, not ours to import
        raise AssertionError(
            "PL-2 RED, as intended. `discover()` refuses the migration tree because a "
            f"`.fallback.sql` sibling is present:\n    {exc}\n"
            "Owner of the fix: dm-runner. Skip `*.fallback.sql` in "
            "trappoint_migrate.discovery.discover() the same way `.down.sql` is special-cased. "
            "Until then `trappoint-migrate apply` cannot reach 0049 on this tree."
        ) from exc

    leaked = [m.path.name for m in found if m.path.name.endswith(".fallback.sql")]
    assert not leaked, (
        f"discovery included the inert fallback files {leaked}. Applying them alongside the live "
        "0031 would create mainline.clause_embedding twice."
    )


def test_pl2_red_mi15_bloodline_guard_does_not_exist_yet() -> None:
    """RED BY DESIGN (PL-2). Owner of the fix: ``dm-functions-triggers``, band 0130-0199.

    MI15 — *blame ancestry never shrinks* — is the O-Ring Ratchet applied to a clause's lineage:
    a rewrite may reword an obligation, retitle it, renumber it and move it to another document;
    it may NOT reduce ``sev_max`` or ``blood_size`` below its parent version's. That is what stops
    a control written by a fatality from being quietly made to look routine.

    It cannot be a ``CHECK``: §4.1 law 1 says a CHECK sees only the row being written, and the
    parent version is another row. So it is a ``BEFORE INSERT`` trigger that reads the parent —
    reachable in one seek because of ``fk_parent_version`` on 0029 — and RAISEs ``P0001``.

    This band ships the columns and the pointer. It does not ship the guard, so today a version
    whose ancestry has shrunk is accepted. This test asserts the guard exists; it fails for that
    reason and goes green when band 0130-0199 lands, at which point MI15 is promoted from
    ``pending`` to ``enforced`` in ``mi_catalogue.yaml``.

    The cluster-tier counterpart is ``test_mi15_a_version_may_not_shrink_its_ancestry``, which
    demonstrates the same gap against a live database. This one exists so the red is visible on a
    machine with no cluster at all — a skipped test proves nothing, and a suite that has never
    been red asserts nothing.
    """
    guards: list[str] = []
    for path in sorted(MIGRATIONS_DIR.glob("*.sql")):
        body = strip_sql_comments(path.read_text(encoding="utf-8")).lower()
        if not re.search(r"\bcreate\s+(or\s+replace\s+)?function\b", body):
            continue
        if "sev_max" not in body and "blood_size" not in body:
            continue
        if "raise" in body:
            guards.append(path.name)

    assert guards, (
        "PL-2 RED, as intended. No migration defines a function that reads sev_max / blood_size "
        "and RAISEs, so MI15 is unenforced:\n"
        "  * mainline.clause_version carries blood_root, blood_peaks, blood_size and sev_max "
        "(migration 0029, this band);\n"
        "  * fk_parent_version makes the parent version reachable in one seek (0029, this band);\n"
        "  * sev_range refuses a severity outside 0-5 for every writer (0029, this band);\n"
        "  * the monotone guard itself does not exist.\n"
        "Owner of the fix: dm-functions-triggers, band 0130-0199. Promote MI15 from `pending` to "
        "`enforced` in mi_catalogue.yaml when this goes green."
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
    """A dead Docker daemon does not refuse ``docker info``; it BLOCKS.

    ``subprocess.run(timeout=…)`` then raises ``TimeoutExpired``, which ``check=False`` does not
    cover, and an uncaught exception in a fixture turns a run that should have SKIPPED into a
    suite of ERRORs. That is the machine this band was authored on, so it is not hypothetical.
    """
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
def spine_cluster(
    request: pytest.FixtureRequest, tmp_path_factory: pytest.TempPathFactory
) -> Iterator[Cluster]:
    # Cooperate with dm-runner's conftest if it is present, so the schema suites share a cluster.
    # A bare `except Exception` and not `except FixtureLookupError`: pytest does not export that
    # class publicly, and a `Skipped` raised by their fixture derives from BaseException, so it
    # propagates untouched — which is what we want, since their skip reason is better than ours.
    try:
        shared = request.getfixturevalue("dsn")
    except Exception:  # noqa: BLE001
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
            "The spine band is NOT verified by a skipped run."
        )
    try:
        yield found
    finally:
        if found.proc is not None:
            found.proc.terminate()
        if found.owns_docker:
            _docker(["rm", "-f", CONTAINER_NAME], timeout=DOCKER_PROBE_TIMEOUT_S)


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
class Spine:
    dsn: str
    database: str

    def connect(self) -> Any:
        return psycopg.connect(self.dsn, autocommit=True)


@pytest.fixture(scope="session")
def spine(spine_cluster: Cluster) -> Iterator[Spine]:
    """Apply 0001-0023 then this band forward from clean into a fresh database.

    The whole band is applied in one shot, in declared order, and a failure names the file and the
    statement. That is the completion test for this worker: `apply` reaching 0049 on v26.2.
    """
    from psycopg.conninfo import make_conninfo

    database = f"mainline_spine_{uuid.uuid4().hex[:10]}"
    with psycopg.connect(spine_cluster.dsn, autocommit=True) as admin:
        admin.execute(f"CREATE DATABASE {database}")

    # Re-point at the fresh database WITHOUT string surgery on the URL: an env-supplied DSN may
    # carry `options=--cluster=…` (CockroachDB Cloud), an sslrootcert path, or no path component
    # at all, and every one of those breaks a naive rsplit on "/".
    dsn = make_conninfo(spine_cluster.dsn, dbname=database)

    with psycopg.connect(dsn, autocommit=True) as conn:
        for path in foundation_files():
            _apply(conn, path)
        for path in band_paths():
            _apply(conn, path)

    print(
        f"\n[spine] cluster:  {spine_cluster.provenance}\n"
        f"[spine] database: {database}\n"
        f"[spine] applied {len(foundation_files())} foundation migrations "
        f"+ {len(BAND_FILES)} spine migrations"
    )
    try:
        yield Spine(dsn=dsn, database=database)
    finally:
        with psycopg.connect(spine_cluster.dsn, autocommit=True) as admin:
            admin.execute(f"DROP DATABASE IF EXISTS {database} CASCADE")


@pytest.fixture
def conn(spine: Spine) -> Iterator[Any]:
    """One autocommit connection per test.

    Autocommit rather than a rolled-back transaction: a refused statement must not be able to hide
    behind a rollback that also erases the rows the test wrote before it.
    """
    connection = spine.connect()
    try:
        yield connection
    finally:
        connection.close()


# ── fixture helpers: minting spine rows ───────────────────────────────────────────────────────


def _digest(seed: str) -> bytes:
    """A 32-byte id. Real commit ids are sha256 over JCS bytes; these are sha256 over a label,
    which is the same shape and is deterministic per test."""
    return hashlib.sha256(seed.encode("utf-8")).digest()


def _new_site() -> str:
    """A fresh site_id per test is this suite's isolation primitive (xdist-safe)."""
    return str(uuid.uuid4())


def _mint_commit(conn: Any, site_id: str, *, gen: int = 0, label: str | None = None) -> bytes:
    commit_id = _digest(label or f"{site_id}:{gen}:{uuid.uuid4()}")
    envelope = json.dumps({"gen": gen, "parents": [], "site": site_id}, sort_keys=True)
    conn.execute(
        """
        INSERT INTO mainline.commit_obj
          (commit_id, site_id, gen, ref_name, author_sub, message, envelope, envelope_bytes)
        VALUES (%s, %s::UUID, %s, %s, %s, %s, %s::JSONB, %s)
        """,
        (
            commit_id,
            site_id,
            gen,
            "site/test/main",
            "sub-test",
            "test commit",
            envelope,
            envelope.encode("utf-8"),
        ),
    )
    return commit_id


def _mint_doc(conn: Any, site_id: str, *, code: str = "PRO-001", open_tokens: int = 0) -> str:
    doc_id = str(uuid.uuid4())
    conn.execute(
        """
        INSERT INTO mainline.doc (doc_id, site_id, doc_code, title, state, open_token_count)
        VALUES (%s::UUID, %s::UUID, %s, %s, 'live', %s)
        """,
        (doc_id, site_id, code, "Test procedure", open_tokens),
    )
    return doc_id


def _mint_clause(conn: Any, site_id: str, birth: bytes, *, root: str = "isolation") -> str:
    clause_uuid = str(uuid.uuid4())
    conn.execute(
        """
        INSERT INTO mainline.clause (clause_uuid, site_id, birth_commit, activity_root)
        VALUES (%s::UUID, %s::UUID, %s, %s)
        """,
        (clause_uuid, site_id, birth, root),
    )
    return clause_uuid


def _mint_version(
    conn: Any,
    *,
    clause_uuid: str,
    commit_id: bytes,
    site_id: str,
    doc_id: str,
    gen: int,
    sev_max: int = 0,
    blood_size: int = 0,
    parent_version: bytes | None = None,
    text: str = "Isolate stored energy before intrusive work.",
) -> None:
    conn.execute(
        """
        INSERT INTO mainline.clause_version
          (clause_uuid, gen, commit_id, site_id, doc_id, activity_root, parent_version,
           ordinal, printed_label, raw_text, canon_text, canon_version, canon_sha256,
           anchor_set, cat_confidence, control_delta, delta_basis,
           blood_root, blood_peaks, blood_size, sev_max)
        VALUES
          (%s::UUID, %s, %s, %s::UUID, %s::UUID, %s, %s,
           %s, %s, %s, %s, 1, %s,
           ARRAY[]::STRING[], 'ok', %s::mainline.control_delta, 'lattice',
           %s, ARRAY[]::BYTES[], %s, %s)
        """,
        (
            clause_uuid,
            gen,
            commit_id,
            site_id,
            doc_id,
            "isolation",
            parent_version,
            gen,
            "7.3.2(b)",
            text,
            text,
            hashlib.sha256(text.encode("utf-8")).digest(),
            "restate",
            _digest(f"blood:{clause_uuid}:{gen}"),
            blood_size,
            sev_max,
        ),
    )


# ── the band applies, and the shape is what the files say ─────────────────────────────────────


@pytest.mark.requires_cluster
def test_the_whole_band_applies_and_creates_eleven_tables(conn: Any) -> None:
    """The completion test for this worker, executed rather than asserted."""
    rows = conn.execute(
        "SELECT table_name FROM information_schema.tables WHERE table_schema = 'mainline'"
    ).fetchall()
    present = {r[0] for r in rows}
    missing = [t for t in BAND_TABLES if t not in present]
    assert not missing, f"the band applied but these tables are absent: {missing}"


@pytest.mark.requires_cluster
def test_clause_version_primary_key_is_clause_gen_commit_in_that_order(conn: Any) -> None:
    """Asserted against the live catalogue, not just the file — the server is the authority."""
    rows = conn.execute(
        """
        SELECT kcu.column_name, kcu.ordinal_position
          FROM information_schema.table_constraints tc
          JOIN information_schema.key_column_usage kcu
            ON tc.constraint_name = kcu.constraint_name
           AND tc.table_schema = kcu.table_schema
         WHERE tc.table_schema = 'mainline'
           AND tc.table_name = 'clause_version'
           AND tc.constraint_type = 'PRIMARY KEY'
         ORDER BY kcu.ordinal_position
        """
    ).fetchall()
    columns = [r[0] for r in rows]
    assert columns == ["clause_uuid", "gen", "commit_id"], (
        f"clause_version's primary key is {columns}. `gen` must precede `commit_id` so that "
        "bisect is a PK-ordered range scan rather than a graph walk."
    )


@pytest.mark.requires_cluster
def test_clause_embedding_is_created_empty_with_exactly_one_vector_index(conn: Any) -> None:
    """Empty at t=0 is the whole reason the index can be declared inline.

    `CREATE VECTOR INDEX` against a populated table starts a backfill that blocks writes, and
    `IMPORT INTO` is unsupported on a vector-indexed table entirely. Creating the index on an
    empty table sidesteps both — but only if the table really is empty when the migration runs.
    """
    count = conn.execute("SELECT count(*) FROM mainline.clause_embedding").fetchone()[0]
    assert count == 0, f"mainline.clause_embedding holds {count} rows at creation; it must be empty"

    create = conn.execute("SHOW CREATE TABLE mainline.clause_embedding").fetchone()[1]
    vector_indexes = re.findall(r"VECTOR\s+INDEX\s+(\w+)", create, re.IGNORECASE)
    assert vector_indexes == ["ce_ann"], (
        f"expected exactly one vector index named ce_ann; SHOW CREATE reports {vector_indexes}.\n"
        f"{create}"
    )


def declared_names() -> set[str]:
    """Every constraint and index name this band writes down, harvested from the files.

    Comparing the live catalogue against THIS set rather than against a hand-maintained list is
    what makes the check self-maintaining: adding a constraint to a migration without naming it
    adds nothing here, so the live catalogue grows a name this set does not contain and the test
    fails. A hardcoded expected list would have to be edited in the same commit as the omission,
    by the same person, which is not a control.
    """
    names: set[str] = set()
    for path in band_paths():
        code = strip_sql_comments(path.read_text(encoding="utf-8"))
        names.update(re.findall(r"\bCONSTRAINT\s+(\w+)", code, re.IGNORECASE))
        names.update(
            re.findall(
                r"\b(?:UNIQUE\s+)?(?:INVERTED\s+|VECTOR\s+)?INDEX\s+(\w+)\s*\(",
                code,
                re.IGNORECASE,
            )
        )
        names.update(re.findall(r"\bCREATE\s+INDEX\s+(\w+)\s+ON\b", code, re.IGNORECASE))
    return {n.lower() for n in names}


@pytest.mark.requires_cluster
def test_every_constraint_in_the_band_is_explicitly_named(conn: Any) -> None:
    """DM-10: the constraint name is the courtroom exhibit; `check_doc_1` is not an exhibit.

    Asserted as containment — every constraint the server reports for a table in this band is a
    name one of this band's files wrote down — rather than by pattern-matching the shapes
    CockroachDB happens to synthesise today. Those shapes are a release detail; "the name came
    from our file" is the property that actually matters, and it stays true across releases.
    """
    rows = conn.execute(
        """
        SELECT table_name, constraint_name
          FROM information_schema.table_constraints
         WHERE table_schema = 'mainline'
           AND constraint_type IN ('CHECK', 'FOREIGN KEY', 'PRIMARY KEY', 'UNIQUE')
        """
    ).fetchall()
    declared = declared_names()
    unnamed: list[str] = []
    for table, name in rows:
        if table not in BAND_TABLES:
            continue
        # A NOT NULL is declared on the column and has no name to give it; CockroachDB surfaces a
        # `<column>_not_null` shadow constraint for it. `primary` is the server's own spelling of
        # a primary key in some releases even when the constraint was named. Neither is a
        # system-generated name in the sense DM-10 forbids.
        if name.endswith("_not_null") or name.lower() == "primary":
            continue
        if name.lower() not in declared:
            unnamed.append(f"{table}.{name}")
    assert not unnamed, (
        f"constraints the server reports that no file in this band names: {unnamed}. Every "
        "constraint is named explicitly (DM-10) because the name is what a refusal message "
        f"carries into evidence.\n  declared in this band: {sorted(declared)}"
    )


@pytest.mark.requires_cluster
def test_no_row_level_ttl_on_any_table_in_this_band(conn: Any) -> None:
    """§4.1 law 13: row-level TTL exists on exactly three tables, none in schema `mainline`.

    Expired rows are not filtered from query results — including from UPDATE and DELETE — so a TTL
    here would mean a control's history thinning out under a query that cannot see it happening.
    The Crimes (Document Destruction) Act 2006 (Vic) is the other half of the argument.
    """
    for table in BAND_TABLES:
        create = conn.execute(f"SHOW CREATE TABLE mainline.{table}").fetchone()[1].lower()
        markers = [token for token in ("ttl_expire", "ttl_expiration") if token in create]
        assert not markers, (
            f"mainline.{table} carries a row-level TTL ({markers}). Zero tables in schema "
            "`mainline` may."
        )


# ── MI19: the refusal this band arms on day one ───────────────────────────────────────────────


@pytest.mark.requires_cluster
def test_mi19_a_document_carrying_a_control_cannot_be_superseded(conn: Any) -> None:
    """MI19 — you cannot delete a control by deleting the document that mentions it.

    The failure mode: a procedure is rewritten, the new document does not mention the isolation
    step added after a 2019 fatality, the old document is marked superseded, and the control is
    gone. Nobody deleted it. Nobody decided anything. There is no record of a decision because no
    decision was made.

    MI19 makes the last step impossible: to supersede the document you must first close each
    carriage, and closing one is either another document taking the series or the series being
    retired with a named author. Either way the control's disappearance becomes an ACT.
    """
    site = _new_site()
    doc_id = _mint_doc(conn, site, code="PRO-MI19", open_tokens=1)

    with pytest.raises(psycopg.Error) as caught:
        conn.execute(
            "UPDATE mainline.doc SET state = 'superseded', superseded_by = ARRAY[%s::UUID] "
            "WHERE doc_id = %s::UUID",
            (str(uuid.uuid4()), doc_id),
        )
    assert_refused(caught.value, "23514", "no_orphan_controls")

    state = conn.execute(
        "SELECT state FROM mainline.doc WHERE doc_id = %s::UUID", (doc_id,)
    ).fetchone()[0]
    assert state == "live", "the refused UPDATE must leave the document exactly as it was"


@pytest.mark.requires_cluster
def test_mi19_supersession_is_allowed_once_the_last_carriage_closes(conn: Any) -> None:
    """The other half of MI19: it blocks a side effect, it does not block a decision.

    A control constraint that could never be satisfied would be a control nobody could work with,
    and controls people cannot work with get disabled. Closing the carriage is the legitimate
    path, and it must be open.
    """
    site = _new_site()
    doc_id = _mint_doc(conn, site, code="PRO-MI19-OK", open_tokens=1)
    conn.execute("UPDATE mainline.doc SET open_token_count = 0 WHERE doc_id = %s::UUID", (doc_id,))
    conn.execute(
        "UPDATE mainline.doc SET state = 'superseded', superseded_by = ARRAY[%s::UUID] "
        "WHERE doc_id = %s::UUID",
        (str(uuid.uuid4()), doc_id),
    )
    state = conn.execute(
        "SELECT state FROM mainline.doc WHERE doc_id = %s::UUID", (doc_id,)
    ).fetchone()[0]
    assert state == "superseded"


@pytest.mark.requires_cluster
def test_mi19_does_not_constrain_withdrawal(conn: Any) -> None:
    """Withdrawal is 'this should never have been issued'; supersession claims a successor.

    A withdrawn document that still carries a series is a genuine state and the orphaned series is
    exactly the alarm the residue and fixity machinery should raise. Constraining withdrawal would
    make emergency withdrawal of a dangerous document impossible — an availability failure at the
    moment availability is the safety property.
    """
    site = _new_site()
    doc_id = _mint_doc(conn, site, code="PRO-WITHDRAW", open_tokens=3)
    conn.execute("UPDATE mainline.doc SET state = 'withdrawn' WHERE doc_id = %s::UUID", (doc_id,))
    row = conn.execute(
        "SELECT state, open_token_count FROM mainline.doc WHERE doc_id = %s::UUID", (doc_id,)
    ).fetchone()
    assert row == ("withdrawn", 3)


@pytest.mark.requires_cluster
def test_doc_refuses_a_negative_token_count(conn: Any) -> None:
    """A counter maintained by decrement triggers goes negative the first time one runs twice.

    `tokens_nonneg` turns that into a 23514 at the moment it happens rather than a silently
    unsatisfiable MI19 later.
    """
    site = _new_site()
    with pytest.raises(psycopg.Error) as caught:
        conn.execute(
            "INSERT INTO mainline.doc (site_id, doc_code, title, open_token_count) "
            "VALUES (%s::UUID, 'PRO-NEG', 'Test', -1)",
            (site,),
        )
    assert_refused(caught.value, "23514", "tokens_nonneg")


# ── the history DAG refuses what it can see from one row ───────────────────────────────────────


@pytest.mark.requires_cluster
def test_commit_obj_refuses_an_id_that_is_not_a_sha256(conn: Any) -> None:
    """Content addressing is only a Merkle property if the id really is the digest length."""
    site = _new_site()
    envelope = json.dumps({"gen": 0})
    with pytest.raises(psycopg.Error) as caught:
        conn.execute(
            """
            INSERT INTO mainline.commit_obj
              (commit_id, site_id, gen, ref_name, author_sub, message, envelope, envelope_bytes)
            VALUES (%s, %s::UUID, 0, 'site/test/main', 'sub', 'm', %s::JSONB, %s)
            """,
            (b"\x01" * 31, site, envelope, envelope.encode()),
        )
    assert_refused(caught.value, "23514", "id_is_sha256")


@pytest.mark.requires_cluster
def test_commit_edge_refuses_a_commit_that_is_its_own_parent(conn: Any) -> None:
    """The only cycle a plain CHECK can see. Longer ones need a hash preimage."""
    site = _new_site()
    commit_id = _mint_commit(conn, site, gen=0, label=f"self-parent:{uuid.uuid4()}")
    with pytest.raises(psycopg.Error) as caught:
        conn.execute(
            "INSERT INTO mainline.commit_edge (child_id, parent_ord, parent_id, parent_gen) "
            "VALUES (%s, 0, %s, 0)",
            (commit_id, commit_id),
        )
    assert_refused(caught.value, "23514", "no_self_parent")


@pytest.mark.requires_cluster
def test_commit_edge_refuses_the_same_parent_listed_twice(conn: Any) -> None:
    """A duplicated parent double-counts a subtree in any walk that does not deduplicate, and
    makes `max(parent.gen)` ambiguous about how many parents there really were."""
    site = _new_site()
    parent = _mint_commit(conn, site, gen=0, label=f"p:{uuid.uuid4()}")
    child = _mint_commit(conn, site, gen=1, label=f"c:{uuid.uuid4()}")
    conn.execute(
        "INSERT INTO mainline.commit_edge (child_id, parent_ord, parent_id, parent_gen) "
        "VALUES (%s, 0, %s, 0)",
        (child, parent),
    )
    with pytest.raises(psycopg.Error) as caught:
        conn.execute(
            "INSERT INTO mainline.commit_edge (child_id, parent_ord, parent_id, parent_gen) "
            "VALUES (%s, 1, %s, 0)",
            (child, parent),
        )
    assert_refused(caught.value, "23505", "parent_listed_once")


@pytest.mark.requires_cluster
def test_ref_refuses_a_head_that_names_no_commit(conn: Any) -> None:
    """An exhibit that names a commit nobody can produce is worthless; 23503 says so at write."""
    with pytest.raises(psycopg.Error) as caught:
        conn.execute(
            "INSERT INTO mainline.ref (ref_name, ref_kind, head_id, gen_head) "
            "VALUES (%s, 'permit', %s, 0)",
            (f"permit/WO-{uuid.uuid4().hex[:8]}", _digest("no such commit")),
        )
    assert caught.value.sqlstate == "23503", (
        f"expected 23503 on fk_head; got {caught.value.sqlstate}: {caught.value}"
    )


@pytest.mark.requires_cluster
def test_ref_refuses_an_unknown_kind(conn: Any) -> None:
    site = _new_site()
    head = _mint_commit(conn, site, gen=0, label=f"refkind:{uuid.uuid4()}")
    with pytest.raises(psycopg.Error) as caught:
        conn.execute(
            "INSERT INTO mainline.ref (ref_name, ref_kind, head_id, gen_head) "
            "VALUES (%s, 'work_order', %s, 0)",
            (f"branch/{uuid.uuid4().hex[:8]}", head),
        )
    assert_refused(caught.value, "23514", "ref_kind_closed")


# ── clause identity ───────────────────────────────────────────────────────────────────────────


@pytest.mark.requires_cluster
def test_a_version_chain_forms_and_bisect_reads_it_as_one_range(conn: Any) -> None:
    """The shape the primary key exists for: every version of one clause, already in gen order."""
    site = _new_site()
    doc_id = _mint_doc(conn, site, code=f"PRO-{uuid.uuid4().hex[:6]}")
    birth = _mint_commit(conn, site, gen=0, label=f"birth:{uuid.uuid4()}")
    clause_uuid = _mint_clause(conn, site, birth)

    previous: bytes | None = None
    for generation in range(4):
        commit_id = (
            birth
            if generation == 0
            else _mint_commit(conn, site, gen=generation, label=f"v{generation}:{clause_uuid}")
        )
        _mint_version(
            conn,
            clause_uuid=clause_uuid,
            commit_id=commit_id,
            site_id=site,
            doc_id=doc_id,
            gen=generation,
            sev_max=generation,
            blood_size=generation,
            parent_version=previous,
        )
        previous = commit_id

    rows = conn.execute(
        "SELECT gen, sev_max FROM mainline.clause_version WHERE clause_uuid = %s::UUID "
        "ORDER BY gen",
        (clause_uuid,),
    ).fetchall()
    assert [r[0] for r in rows] == [0, 1, 2, 3]
    assert [r[1] for r in rows] == [0, 1, 2, 3]


@pytest.mark.requires_cluster
def test_a_version_may_not_take_its_parent_from_another_clause(conn: Any) -> None:
    """`fk_parent_version` is composite on (clause_uuid, parent_version), so lineage cannot cross
    obligations. The MI15 guard reads this pointer; a pointer that could dangle, or point at
    someone else's history, would be a guard with a bypass."""
    site = _new_site()
    doc_id = _mint_doc(conn, site, code=f"PRO-{uuid.uuid4().hex[:6]}")
    birth_a = _mint_commit(conn, site, gen=0, label=f"a:{uuid.uuid4()}")
    birth_b = _mint_commit(conn, site, gen=0, label=f"b:{uuid.uuid4()}")
    clause_a = _mint_clause(conn, site, birth_a)
    clause_b = _mint_clause(conn, site, birth_b)

    _mint_version(conn, clause_uuid=clause_a, commit_id=birth_a, site_id=site, doc_id=doc_id, gen=0)
    with pytest.raises(psycopg.Error) as caught:
        _mint_version(
            conn,
            clause_uuid=clause_b,
            commit_id=birth_b,
            site_id=site,
            doc_id=doc_id,
            gen=0,
            parent_version=birth_a,
        )
    assert caught.value.sqlstate == "23503", (
        f"expected 23503 on fk_parent_version; got {caught.value.sqlstate}: {caught.value}"
    )


@pytest.mark.requires_cluster
def test_a_birth_version_needs_no_parent(conn: Any) -> None:
    """MATCH SIMPLE is what makes the composite self-FK correct rather than merely strict: a NULL
    in any column satisfies it, so `parent_version IS NULL` is a first-class 'this is a birth
    version' claim rather than a special case somebody has to remember."""
    site = _new_site()
    doc_id = _mint_doc(conn, site, code=f"PRO-{uuid.uuid4().hex[:6]}")
    birth = _mint_commit(conn, site, gen=0, label=f"birth-only:{uuid.uuid4()}")
    clause_uuid = _mint_clause(conn, site, birth)
    _mint_version(
        conn,
        clause_uuid=clause_uuid,
        commit_id=birth,
        site_id=site,
        doc_id=doc_id,
        gen=0,
        parent_version=None,
    )
    count = conn.execute(
        "SELECT count(*) FROM mainline.clause_version WHERE clause_uuid = %s::UUID",
        (clause_uuid,),
    ).fetchone()[0]
    assert count == 1


@pytest.mark.requires_cluster
def test_clause_version_refuses_a_severity_outside_the_band(conn: Any) -> None:
    """`sev_range` is the plain-column half of MI15: it holds for every writer, triggers or not."""
    site = _new_site()
    doc_id = _mint_doc(conn, site, code=f"PRO-{uuid.uuid4().hex[:6]}")
    birth = _mint_commit(conn, site, gen=0, label=f"sev:{uuid.uuid4()}")
    clause_uuid = _mint_clause(conn, site, birth)
    with pytest.raises(psycopg.Error) as caught:
        _mint_version(
            conn,
            clause_uuid=clause_uuid,
            commit_id=birth,
            site_id=site,
            doc_id=doc_id,
            gen=0,
            sev_max=6,
        )
    assert_refused(caught.value, "23514", "sev_range")


@pytest.mark.requires_cluster
def test_clause_version_refuses_a_model_basis_with_no_model_named(conn: Any) -> None:
    """The record must always be able to say whether a machine or a person decided."""
    site = _new_site()
    doc_id = _mint_doc(conn, site, code=f"PRO-{uuid.uuid4().hex[:6]}")
    birth = _mint_commit(conn, site, gen=0, label=f"basis:{uuid.uuid4()}")
    clause_uuid = _mint_clause(conn, site, birth)
    text = "Isolate stored energy."
    with pytest.raises(psycopg.Error) as caught:
        conn.execute(
            """
            INSERT INTO mainline.clause_version
              (clause_uuid, gen, commit_id, site_id, doc_id, activity_root,
               ordinal, raw_text, canon_text, canon_version, canon_sha256,
               anchor_set, control_delta, delta_basis,
               blood_root, blood_peaks, blood_size, sev_max)
            VALUES
              (%s::UUID, 0, %s, %s::UUID, %s::UUID, 'isolation',
               0, %s, %s, 1, %s,
               ARRAY[]::STRING[], 'weaken'::mainline.control_delta, 'lattice+model',
               %s, ARRAY[]::BYTES[], 0, 0)
            """,
            (
                clause_uuid,
                birth,
                site,
                doc_id,
                text,
                text,
                hashlib.sha256(text.encode()).digest(),
                _digest("blood"),
            ),
        )
    assert_refused(caught.value, "23514", "model_named_when_model_used")


@pytest.mark.requires_cluster
def test_abstain_to_weaken_is_a_legal_basis(conn: Any) -> None:
    """THE RATCHET. When the model abstains or the text is opaque, the recorded answer is the SAFE
    one — `weaken`, which arms the gate. Abstention must cost the writer, never the reader: the
    failure mode of a classifier is silence, and silence that resolves to 'no change' is a gate
    that opens on uncertainty.
    """
    site = _new_site()
    doc_id = _mint_doc(conn, site, code=f"PRO-{uuid.uuid4().hex[:6]}")
    birth = _mint_commit(conn, site, gen=0, label=f"abstain:{uuid.uuid4()}")
    clause_uuid = _mint_clause(conn, site, birth)
    text = "Something the extractor could not read."
    conn.execute(
        """
        INSERT INTO mainline.clause_version
          (clause_uuid, gen, commit_id, site_id, doc_id, activity_root,
           ordinal, raw_text, canon_text, canon_version, canon_sha256,
           anchor_set, cat_confidence, control_delta, delta_basis,
           blood_root, blood_peaks, blood_size, sev_max)
        VALUES
          (%s::UUID, 0, %s, %s::UUID, %s::UUID, 'isolation',
           0, %s, %s, 1, %s,
           ARRAY[]::STRING[], 'opaque', 'weaken'::mainline.control_delta, 'abstain_to_weaken',
           %s, ARRAY[]::BYTES[], 0, 0)
        """,
        (
            clause_uuid,
            birth,
            site,
            doc_id,
            text,
            text,
            hashlib.sha256(text.encode()).digest(),
            _digest("blood-abstain"),
        ),
    )
    row = conn.execute(
        "SELECT delta_basis, control_delta FROM mainline.clause_version "
        "WHERE clause_uuid = %s::UUID",
        (clause_uuid,),
    ).fetchone()
    assert row == ("abstain_to_weaken", "weaken")


# ── carriage and the series system ────────────────────────────────────────────────────────────


@pytest.mark.requires_cluster
def test_a_series_cannot_be_carried_twice_by_one_document_at_once(conn: Any) -> None:
    """`carriage_one_open` closes a counting hole: two open carriages for one (series, doc) pair
    make `open_token_count` read 2 when one thing is carried, and every decrement path after that
    is wrong in one direction or the other."""
    site = _new_site()
    doc_id = _mint_doc(conn, site, code=f"PRO-{uuid.uuid4().hex[:6]}")
    first = _mint_commit(conn, site, gen=0, label=f"open1:{uuid.uuid4()}")
    second = _mint_commit(conn, site, gen=1, label=f"open2:{uuid.uuid4()}")
    series_id = str(uuid.uuid4())
    conn.execute(
        "INSERT INTO mainline.control_series (series_id, site_id, activity_root, criticality, "
        "label) VALUES (%s::UUID, %s::UUID, 'isolation', 'critical', %s)",
        (series_id, site, f"CC-{uuid.uuid4().hex[:6]}"),
    )
    conn.execute(
        "INSERT INTO mainline.carriage (series_id, doc_id, opened_commit) "
        "VALUES (%s::UUID, %s::UUID, %s)",
        (series_id, doc_id, first),
    )
    with pytest.raises(psycopg.Error) as caught:
        conn.execute(
            "INSERT INTO mainline.carriage (series_id, doc_id, opened_commit) "
            "VALUES (%s::UUID, %s::UUID, %s)",
            (series_id, doc_id, second),
        )
    assert_refused(caught.value, "23505", "carriage_one_open")


@pytest.mark.requires_cluster
def test_a_document_may_carry_a_series_again_after_closing_it(conn: Any) -> None:
    """A procedure that is split and later recombined is an ordinary lifecycle, and the gap
    between the two carriages is history worth keeping — which is why `opened_commit` is in the
    primary key and the uniqueness is PARTIAL."""
    site = _new_site()
    doc_id = _mint_doc(conn, site, code=f"PRO-{uuid.uuid4().hex[:6]}")
    opened = _mint_commit(conn, site, gen=0, label=f"c-open:{uuid.uuid4()}")
    closed = _mint_commit(conn, site, gen=1, label=f"c-close:{uuid.uuid4()}")
    reopened = _mint_commit(conn, site, gen=2, label=f"c-reopen:{uuid.uuid4()}")
    series_id = str(uuid.uuid4())
    conn.execute(
        "INSERT INTO mainline.control_series (series_id, site_id, activity_root, criticality, "
        "label) VALUES (%s::UUID, %s::UUID, 'isolation', 'critical', %s)",
        (series_id, site, f"CC-{uuid.uuid4().hex[:6]}"),
    )
    conn.execute(
        "INSERT INTO mainline.carriage (series_id, doc_id, opened_commit, closed_commit) "
        "VALUES (%s::UUID, %s::UUID, %s, %s)",
        (series_id, doc_id, opened, closed),
    )
    conn.execute(
        "INSERT INTO mainline.carriage (series_id, doc_id, opened_commit) "
        "VALUES (%s::UUID, %s::UUID, %s)",
        (series_id, doc_id, reopened),
    )
    count = conn.execute(
        "SELECT count(*) FROM mainline.carriage WHERE series_id = %s::UUID", (series_id,)
    ).fetchone()[0]
    assert count == 2


@pytest.mark.requires_cluster
def test_control_series_refuses_a_criticality_outside_the_register(conn: Any) -> None:
    site = _new_site()
    with pytest.raises(psycopg.Error) as caught:
        conn.execute(
            "INSERT INTO mainline.control_series (site_id, activity_root, criticality, label) "
            "VALUES (%s::UUID, 'isolation', 'catastrophic', %s)",
            (site, f"CC-{uuid.uuid4().hex[:6]}"),
        )
    assert_refused(caught.value, "23514", "criticality_closed")


# ── identity residue: Conservation of Blame Mass ──────────────────────────────────────────────


@pytest.mark.requires_cluster
def test_identity_residue_refuses_an_unmodelled_reason(conn: Any) -> None:
    """Five reasons, closed set. Each names a different kind of doubt, and an unnamed doubt is a
    doubt nobody can adjudicate."""
    site = _new_site()
    commit_id = _mint_commit(conn, site, gen=0, label=f"res:{uuid.uuid4()}")
    clause_uuid = _mint_clause(conn, site, commit_id)
    with pytest.raises(psycopg.Error) as caught:
        conn.execute(
            """
            INSERT INTO mainline.identity_residue
              (site_id, commit_id, ancestor_clause_uuid, reason, max_ancestral_severity, features)
            VALUES (%s::UUID, %s, %s::UUID, 'probably_fine', 5, '{}'::JSONB)
            """,
            (site, commit_id, clause_uuid),
        )
    assert_refused(caught.value, "23514", "reason_closed")


@pytest.mark.requires_cluster
def test_rerunning_the_matcher_does_not_double_the_open_residue(conn: Any) -> None:
    """The matcher is idempotent by construction: a second run collides on 23505 rather than
    doubling the count of open residue, which is what would happen if the gate's input were a
    running total instead of a set."""
    site = _new_site()
    commit_id = _mint_commit(conn, site, gen=0, label=f"idem:{uuid.uuid4()}")
    clause_uuid = _mint_clause(conn, site, commit_id)
    statement = """
        INSERT INTO mainline.identity_residue
          (site_id, commit_id, ancestor_clause_uuid, reason, max_ancestral_severity,
           match_score, features)
        VALUES (%s::UUID, %s, %s::UUID, 'unmatched', 5, 0.41, '{"bands_hit": 0}'::JSONB)
    """
    conn.execute(statement, (site, commit_id, clause_uuid))
    with pytest.raises(psycopg.Error) as caught:
        conn.execute(statement, (site, commit_id, clause_uuid))
    assert_refused(caught.value, "23505", "residue_unique")

    open_rows = conn.execute(
        "SELECT count(*) FROM mainline.identity_residue "
        "WHERE commit_id = %s AND disposition_id IS NULL",
        (commit_id,),
    ).fetchone()[0]
    assert open_rows == 1


@pytest.mark.requires_cluster
def test_one_ancestor_may_carry_several_distinct_doubts(conn: Any) -> None:
    """`reason` is in the unique key on purpose. A clause can be both ambiguous and missing an
    anchor; collapsing those would force the matcher to rank its own doubts and discard the rest,
    and the discarded one is the one that mattered."""
    site = _new_site()
    commit_id = _mint_commit(conn, site, gen=0, label=f"multi:{uuid.uuid4()}")
    clause_uuid = _mint_clause(conn, site, commit_id)
    for reason in ("ambiguous", "anchor_drop"):
        conn.execute(
            """
            INSERT INTO mainline.identity_residue
              (site_id, commit_id, ancestor_clause_uuid, reason, max_ancestral_severity, features)
            VALUES (%s::UUID, %s, %s::UUID, %s, 4, '{}'::JSONB)
            """,
            (site, commit_id, clause_uuid, reason),
        )
    count = conn.execute(
        "SELECT count(*) FROM mainline.identity_residue WHERE commit_id = %s", (commit_id,)
    ).fetchone()[0]
    assert count == 2


# ── the red one ───────────────────────────────────────────────────────────────────────────────


@pytest.mark.requires_cluster
def test_mi15_a_version_may_not_shrink_its_ancestry(conn: Any) -> None:
    """RED BY DESIGN (PL-2). MI15. Owner of the fix: ``dm-functions-triggers``, band 0130-0199.

    A clause whose parent version accumulated a severity-5 blame ancestry (``sev_max = 5``,
    ``blood_size = 7``) is rewritten, and the rewrite declares ``sev_max = 0``, ``blood_size = 0``.
    Every column in that insert is individually legal: 0 is inside ``sev_range``, the parent
    pointer resolves, the foreign keys hold. **The database accepts it today**, and that acceptance
    is the O-Ring failure in miniature — the obligation is still there, the text may even be
    identical, and the record now says nothing wrote it.

    Downstream that is not a cosmetic loss. ``virulence`` is banded from ancestral severity, the
    clearance lattice keys on ``virulence``, and the three deliberately absent cells of
    ``mainline.clearance_legal`` are what make ``mechanism_absent`` over a fatality a ``23503``.
    A version that has shrunk its ancestry to routine has bought itself the whole disposition
    vocabulary, including the constructors that dismiss the control outright.

    The guard is a ``BEFORE INSERT`` trigger reading the parent version and RAISEing ``P0001``.
    Until it lands this test fails, ``mi_catalogue.yaml`` carries MI15 as ``pending``, and the
    ``mi-red`` job passes BECAUSE this fails. It is not ``xfail``: a suite that has never been red
    asserts nothing, and for a product whose deliverable is a refusal that is not a slogan.
    """
    site = _new_site()
    doc_id = _mint_doc(conn, site, code=f"PRO-{uuid.uuid4().hex[:6]}")
    parent_commit = _mint_commit(conn, site, gen=0, label=f"mi15-parent:{uuid.uuid4()}")
    child_commit = _mint_commit(conn, site, gen=1, label=f"mi15-child:{uuid.uuid4()}")
    clause_uuid = _mint_clause(conn, site, parent_commit)

    _mint_version(
        conn,
        clause_uuid=clause_uuid,
        commit_id=parent_commit,
        site_id=site,
        doc_id=doc_id,
        gen=0,
        sev_max=5,
        blood_size=7,
    )

    refusal: Exception | None = None
    try:
        _mint_version(
            conn,
            clause_uuid=clause_uuid,
            commit_id=child_commit,
            site_id=site,
            doc_id=doc_id,
            gen=1,
            sev_max=0,
            blood_size=0,
            parent_version=parent_commit,
            text="Isolate energy where practicable.",
        )
    except psycopg.Error as exc:
        refusal = exc

    assert refusal is not None, (
        "PL-2 RED, as intended. MI15 is NOT enforced: a clause version whose parent carried "
        "sev_max=5 / blood_size=7 was accepted with sev_max=0 / blood_size=0.\n"
        "  * the BLOODLINE columns exist (0029, this band);\n"
        "  * fk_parent_version makes the parent reachable in one seek (0029, this band);\n"
        "  * the BEFORE INSERT monotone guard does not exist.\n"
        "Owner of the fix: dm-functions-triggers, band 0130-0199, SQLSTATE P0001. Promote MI15 "
        "from `pending` to `enforced` in mi_catalogue.yaml when this goes green."
    )
    assert refusal.sqlstate == "P0001", (  # type: ignore[attr-defined]
        f"MI15 is enforced but with the wrong SQLSTATE: {refusal.sqlstate}. "  # type: ignore[attr-defined]
        "The BLOODLINE guard is a trigger RAISE, which is P0001; 23514 would mean somebody "
        "expressed it as a CHECK, and a CHECK cannot see the parent row."
    )
