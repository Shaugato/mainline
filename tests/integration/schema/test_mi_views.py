# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""Tier-3 schema suite for the view bands — migrations 0155-0172 (``dm-views-rls``).

What this band owns, and therefore what this file may honestly assert:

* the **Managed-MCP audit surface** — thirteen ``mainline_audit`` views, each aggregate-first,
  each ending ``LIMIT 25``, each depending on **no system catalog**, and each carrying a
  truncation flag. The size limits are a **functional requirement, not a style**: the Managed
  MCP caps a response at 10 KiB and a ``SELECT`` at 25 rows, and a view that exceeds either is
  silently truncated rather than refused. In this product an aggregate that quietly truncated
  would be a safety defect, because the aggregate is about how much is currently blocked;
* the two ``mainline_ops`` snapshot tables (0155, 0155a) that let the ops family answer
  questions whose real source is ``crdb_internal`` — a catalog the MCP identity may not read;
* three ``mainline_qa`` views, which **no MCP service account ever reaches, on any tier, ever**
  (S14). Their unreachability is asserted in ``test_mi_rls.py``, beside the positive assertions,
  because some of this system's guarantees are about what is NOT there.

What this file does NOT pretend to prove:

* **that the numbers are right.** These are views; their inputs are other bands' tables and
  triggers. This suite proves shape, size, catalog-independence and truncation honesty.
* **that RLS lets the views see anything.** A view evaluates RLS as its owner and every gated
  subject is ``FORCE ROW LEVEL SECURITY``, so an empty audit view can mean "nothing is wrong" or
  "the owner has no policy". That distinction is ``test_mi_rls.py``'s
  ``test_the_audit_views_can_see_through_forced_rls``.

Running it
----------
The static tier needs no cluster. The cluster tier finds a CockroachDB v26.2 in this order and
**skips with a reason** rather than faking anything: the session ``dsn`` fixture from
``tests/integration/schema/conftest.py`` (``dm-runner``), then ``$MAINLINE_TEST_DSN`` /
``$COCKROACH_URL`` / ``$CRDB_URL`` / ``$TRAPPOINT_DSN``, then a ``cockroach`` binary on ``PATH``,
then a Docker daemon.

**This suite is RED until the bands it depends on land, and that is the intended state** (the
data-model lead's accepted risk DR-4). ``test_the_view_bands_apply_cleanly`` fails with the exact
list of blocked files and the relation each one is waiting for. It does not skip: a skipped run
verifies nothing, and a band whose prerequisites are absent is not a band that passed.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import socket
import subprocess
import time
import uuid
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest
from trappoint_testkit import pinned_image

psycopg = pytest.importorskip(
    "psycopg", reason="psycopg 3 is required to talk to CockroachDB; `uv sync` installs it"
)

# ══════════════════════════════════════════════════════════════════════════════════════════════
# Paths and band constants
# ══════════════════════════════════════════════════════════════════════════════════════════════

REPO_ROOT = Path(__file__).resolve().parents[3]
DB_DIR = REPO_ROOT / "verticals" / "mainline" / "db"
MIGRATIONS_DIR = DB_DIR / "migrations"

#: MR-5, the one filename convention: ``NNNN[a-z]_lower_snake_slug.sql``. Never ``.up.sql``,
#: which named a ``.down.sql`` counterpart that DM-14 makes illegal by construction.
MR5_FILENAME = re.compile(r"^\d{4}[a-z]?_[a-z0-9_]+\.sql$")

#: Written out rather than globbed, so that a file appearing in the band by accident — another
#: worker's stray, a rename, a half-finished draft — is a test failure and not a silent extra
#: object in the middle of the audit surface.
OPS_SOURCE_FILES: tuple[str, ...] = (
    "0155_ops_index_usage_snapshot.sql",
    "0155a_ops_changefeed_health_snapshot.sql",
)

AUDIT_VIEW_FILES: tuple[str, ...] = (
    "0156_v_open_gate_summary.sql",
    "0157_v_weakenings_without_disposition.sql",
    "0158_v_blame_coverage.sql",
    "0159_v_disposition_coverage.sql",
    "0160_v_silence_summary.sql",
    "0161_v_recall_conservation.sql",
    "0162_v_ledger_health.sql",
    "0163_v_fixity_coverage.sql",
    "0164_v_agent_actions.sql",
    "0165_v_gate_latency_daily.sql",
    "0166_v_txn_restart_daily.sql",
    "0167_v_unused_indexes.sql",
    "0168_v_changefeed_health.sql",
)

QA_VIEW_FILES: tuple[str, ...] = (
    "0170_v_disposition_profile.sql",
    "0171_v_standing_components.sql",
    "0172_v_my_record.sql",
)

BAND_FILES: tuple[str, ...] = OPS_SOURCE_FILES + AUDIT_VIEW_FILES + QA_VIEW_FILES

#: ARCHITECTURE.md §17, verbatim: thirteen views, nine named plus the four-strong ops family.
AUDIT_VIEWS: tuple[str, ...] = (
    "v_open_gate_summary",
    "v_weakenings_without_disposition",
    "v_blame_coverage",
    "v_disposition_coverage",
    "v_silence_summary",
    "v_recall_conservation",
    "v_ledger_health",
    "v_fixity_coverage",
    "v_agent_actions",
    "v_gate_latency_daily",
    "v_txn_restart_daily",
    "v_unused_indexes",
    "v_changefeed_health",
)

QA_VIEWS: tuple[str, ...] = (
    "v_disposition_profile",
    "v_standing_components",
    "v_my_record",
)

#: Objects in `mainline_audit` that this band does NOT own, named with the band that does.
#:
#: `mainline_audit` is granted to `mainline_auditor` by a SCHEMA-WIDE WILDCARD (GRANTS.yaml
#: `schema_wide`), which is safe "precisely because the schema is constitutionally view-only" —
#: so anything that appears here is on the Managed-MCP surface the moment it is created, whoever
#: created it. An allowlist rather than a tolerance: a foreign view is fine, an ANONYMOUS foreign
#: view is a disclosure nobody reviewed. The §17 size and catalog properties are asserted against
#: these too, because the transport's caps are a property of the schema and not of the author.
FOREIGN_AUDIT_VIEWS: dict[str, str] = {
    "v_cbm_ledger": "algorithms, band 0150-0154z, migration 0151_v_cbm_ledger.sql",
}

#: §4.1 law 12 / §9.1. The Managed MCP has NO ACCESS to any of these. A view that reached one
#: would appear to work in psql, in CI and in every test that runs as root, and would fail only
#: on the one transport it exists to serve.
FORBIDDEN_CATALOGS: tuple[str, ...] = (
    "crdb_internal",
    "pg_catalog",
    "information_schema",
    "pg_extension",
)

#: The Managed MCP's own caps (§9.1). Not tunable, not advisory.
MCP_ROW_CAP = 25
MCP_BYTE_CAP = 10 * 1024

#: The uniform truncation contract this band publishes. Every view carries both.
TRUNCATION_COLUMNS: tuple[str, ...] = ("group_count", "rows_complete")

CRDB_IMAGE = os.environ.get("MAINLINE_CRDB_IMAGE") or pinned_image(Path(__file__))
CONTAINER_NAME = "mainline-test-views"
READY_TIMEOUT_S = 120.0
DOCKER_PROBE_TIMEOUT_S = 20.0
DOCKER_RUN_TIMEOUT_S = 180.0


# ══════════════════════════════════════════════════════════════════════════════════════════════
# A small SQL scanner. Same contract as the ones in test_mi_foundation.py and test_mi_spine.py,
# and deliberately a third independent implementation: three scanners agreeing that a file holds
# one statement is worth more than one scanner asserting it three times.
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


def band_paths() -> list[Path]:
    return [MIGRATIONS_DIR / name for name in BAND_FILES]


def tree_paths() -> list[Path]:
    """Every discoverable migration, in the order the runner applies them (ruling D7)."""
    found = [p for p in MIGRATIONS_DIR.iterdir() if p.is_file() and MR5_FILENAME.match(p.name)]
    return sorted(found, key=lambda p: p.name.removesuffix(".sql"))


# ══════════════════════════════════════════════════════════════════════════════════════════════
# STATIC TIER — no cluster required. Everything here is checkable on a laptop with no Docker.
# ══════════════════════════════════════════════════════════════════════════════════════════════


def test_the_band_is_exactly_the_declared_files() -> None:
    """0155-0172 holds these eighteen files and nothing else.

    Globbing would let a stray file join the audit surface silently. The audit surface is the
    thing a regulator's agent reads; an unreviewed object appearing in it is not a merge
    conflict, it is a disclosure.
    """
    on_disk = {
        p.name
        for p in MIGRATIONS_DIR.iterdir()
        if p.is_file() and MR5_FILENAME.match(p.name) and "0155" <= p.name[:4] <= "0179"
    }
    assert on_disk == set(BAND_FILES), (
        f"band 0155-0179 does not match the declaration.\n"
        f"  unexpected on disk: {sorted(on_disk - set(BAND_FILES))}\n"
        f"  declared but absent: {sorted(set(BAND_FILES) - on_disk)}"
    )


def test_the_declared_order_is_the_lexicographic_order() -> None:
    """A view must be created after every object it reads, and the runner orders lexicographically
    on the whole version stem. If the declaration and the sort disagree, the declaration is a
    fiction and the applied order is whatever the sort happened to produce."""
    assert list(BAND_FILES) == sorted(BAND_FILES, key=lambda n: n.removesuffix(".sql"))


@pytest.mark.parametrize("path", band_paths(), ids=lambda p: p.name)
def test_every_file_carries_the_mandatory_header_block(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    head = header_comment(text)
    for key in ("MI:", "I:", "COUNSEL-GATED:", "RATIONALE:"):
        assert key in head, f"{path.name}: header comment is missing {key!r}"
    assert re.search(r"\b(MI\d\d|I\d\d)\b", head), (
        f"{path.name}: the header cites no invariant id. ARCHITECTURE.md §18 requires every "
        "migration to declare which invariant it realises, where a reviewer reads it."
    )
    assert "SPDX-License-Identifier: FSL-1.1-ALv2" in head, (
        f"{path.name}: verticals/mainline/* is FSL-1.1-ALv2; the REUSE header is not optional."
    )


@pytest.mark.parametrize("path", band_paths(), ids=lambda p: p.name)
def test_exactly_one_statement_per_file(path: Path) -> None:
    """The runner does not wrap a file body in a transaction, so a two-statement file is not
    atomic and a half-applied one leaves an undiagnosable ``dirty`` marker."""
    statements = split_statements(path.read_text(encoding="utf-8"))
    assert len(statements) == 1, (
        f"{path.name} holds {len(statements)} statements; split it with a letter suffix (MR-5)."
    )


@pytest.mark.parametrize("path", band_paths(), ids=lambda p: p.name)
def test_no_banned_constructs(path: Path) -> None:
    """Sequences are banned (§4.1 law 9). The ledger is gap-free by CAS, so a gap MEANS
    tampering — and `CREATE SEQUENCE` succeeds on this cluster (platform finding F4), which makes
    the lint load-bearing rather than decorative."""
    code = strip_sql_comments(path.read_text(encoding="utf-8"))
    for pattern, why in (
        (r"\bCREATE\s+(?:TEMP\s+|TEMPORARY\s+|UNLOGGED\s+)*SEQUENCE\b", "a sequence"),
        (r"\bnextval\s*\(", "nextval()"),
        (r"\b(?:BIG|SMALL)?SERIAL[248]?\b", "SERIAL"),
        (r"\bunique_rowid\s*\(", "unique_rowid()"),
    ):
        assert re.search(pattern, code, re.IGNORECASE) is None, f"{path.name} uses {why}"


@pytest.mark.parametrize(
    "path", [MIGRATIONS_DIR / n for n in AUDIT_VIEW_FILES + QA_VIEW_FILES], ids=lambda p: p.name
)
def test_no_view_reads_a_system_catalog(path: Path) -> None:
    """§4.1 law 12 — the Managed MCP identity has NO ACCESS to ``system``, ``crdb_internal``,
    ``pg_catalog``, ``information_schema`` or ``pg_extension``.

    This is the assertion that has to be static rather than behavioural, because a view reaching
    a system catalog works perfectly in psql, in CI and in every test that runs as ``root``. It
    fails only on the one transport the view exists to serve, and it fails there as a privilege
    error the auditor cannot interpret.
    """
    code = strip_sql_comments(path.read_text(encoding="utf-8"))
    for catalog in FORBIDDEN_CATALOGS:
        assert re.search(rf"\b{catalog}\s*\.", code, re.IGNORECASE) is None, (
            f"{path.name} reads {catalog}. The ops family answers catalog questions from the "
            "pre-materialised mainline_ops snapshot tables (0155, 0155a) precisely so that the "
            "view itself never needs one — see §9.4."
        )
    # `system.` as a schema qualifier, without catching an English word ending in "system".
    assert re.search(r"(?<![A-Za-z_])system\s*\.", code, re.IGNORECASE) is None, (
        f"{path.name} appears to qualify a relation with the `system` catalog."
    )


@pytest.mark.parametrize(
    "path", [MIGRATIONS_DIR / n for n in AUDIT_VIEW_FILES], ids=lambda p: p.name
)
def test_every_audit_view_ends_with_limit_25(path: Path) -> None:
    """The transport truncates silently at 25 rows. A view that does not bound itself hands the
    reader a partial answer with no indication that it is partial."""
    code = strip_sql_comments(path.read_text(encoding="utf-8")).strip().rstrip(";").rstrip()
    assert re.search(r"\bLIMIT\s+25\s*$", code, re.IGNORECASE), (
        f"{path.name} does not end with `LIMIT 25`. Tail was: {code[-120:]!r}"
    )


@pytest.mark.parametrize(
    "path", [MIGRATIONS_DIR / n for n in AUDIT_VIEW_FILES + QA_VIEW_FILES], ids=lambda p: p.name
)
def test_every_view_declares_the_truncation_contract(path: Path) -> None:
    """``group_count`` + ``rows_complete`` on every view, without exception.

    §17: each view carries ``ancestry_complete`` **or an equivalent truncation flag**, and §5.4
    is the rule behind it — *a truncated closure must never be indistinguishable from a complete
    one*. Over a transport that truncates silently the only way to make that true is to put the
    fact INSIDE the rows that survive.
    """
    code = strip_sql_comments(path.read_text(encoding="utf-8"))
    for column in TRUNCATION_COLUMNS:
        assert re.search(rf"\bAS\s+{column}\b", code, re.IGNORECASE), (
            f"{path.name} does not project `{column}`. Every view in this band publishes the "
            "same truncation contract so that a reader never has to know which one they hold."
        )


@pytest.mark.parametrize(
    "path",
    [
        MIGRATIONS_DIR / n
        for n in (
            "0157_v_weakenings_without_disposition.sql",
            "0158_v_blame_coverage.sql",
            "0159_v_disposition_coverage.sql",
        )
    ],
    ids=lambda p: p.name,
)
def test_closure_views_carry_ancestry_complete(path: Path) -> None:
    """The three views that read the blame closure carry ``ancestry_complete`` by that name,
    because that is the name §17 gives the flag and the name an auditor will look for."""
    code = strip_sql_comments(path.read_text(encoding="utf-8"))
    assert re.search(r"\bAS\s+ancestry_complete\b", code, re.IGNORECASE), (
        f"{path.name} reads the closure and does not publish `ancestry_complete`."
    )


def test_the_ancestry_flag_fails_closed_on_an_absent_closure() -> None:
    """PL-2, applied to a draft rather than to a mechanism.

    §17's draft writes ``bool_and(NOT cbc.truncated)``. Under the LEFT JOIN that precedes it, a
    clause version with no closure row yields ``NULL``, ``bool_and`` ignores NULLs, and a group
    in which one clause is missing its closure reports ``ancestry_complete = true``. That fails
    OPEN in the one column whose whole job is to fail closed — and absence is strictly worse than
    truncation, because truncation means we walked and stopped while absence means we never
    walked.

    This test pins the corrected expression so that a later "simplification" back to the draft is
    a red build rather than a silent regression.
    """
    for name in ("0157_v_weakenings_without_disposition.sql", "0159_v_disposition_coverage.sql"):
        code = strip_sql_comments((MIGRATIONS_DIR / name).read_text(encoding="utf-8"))
        flag = re.search(
            r"bool_and\s*\((?P<expr>[^)]*(?:\([^)]*\)[^)]*)*)\)\s+AS\s+ancestry_complete",
            code,
            re.IGNORECASE | re.DOTALL,
        )
        assert flag is not None, f"{name}: could not find the bool_and(...) AS ancestry_complete"
        expr = " ".join(flag.group("expr").split())
        assert "IS NOT NULL" in expr.upper(), (
            f"{name}: `ancestry_complete` is {expr!r}. Without an explicit `IS NOT NULL` test on "
            "the closure row, an ABSENT closure reports complete. See the header block."
        )


def test_no_up_sql_file_exists_anywhere_in_the_tree() -> None:
    """MR-5 rule C. ``.up.sql`` names a ``.down.sql`` counterpart that DM-14 makes illegal by
    construction, and a suffix chain is what let two conventions coexist invisibly."""
    strays = sorted(p.name for p in MIGRATIONS_DIR.iterdir() if p.name.endswith(".up.sql"))
    assert strays == [], f"`.up.sql` files in the migration tree: {strays}"


def test_the_ops_snapshot_tables_are_declared_before_the_views_that_read_them() -> None:
    """0155/0155a create the two ``mainline_ops`` tables; 0167/0168 read them. A view created
    before its base table is not a warning in CockroachDB, it is a refusal — which is the good
    case, and this test is here so the ordering is asserted rather than merely observed."""
    for view_file, table in (
        ("0167_v_unused_indexes.sql", "mainline_ops.index_usage_snapshot"),
        ("0168_v_changefeed_health.sql", "mainline_ops.changefeed_health_snapshot"),
    ):
        code = strip_sql_comments((MIGRATIONS_DIR / view_file).read_text(encoding="utf-8"))
        assert table in code, f"{view_file} does not read {table}"
    for source_file, table in (
        ("0155_ops_index_usage_snapshot.sql", "mainline_ops.index_usage_snapshot"),
        ("0155a_ops_changefeed_health_snapshot.sql", "mainline_ops.changefeed_health_snapshot"),
    ):
        code = strip_sql_comments((MIGRATIONS_DIR / source_file).read_text(encoding="utf-8"))
        assert f"CREATE TABLE {table}" in code, f"{source_file} does not create {table}"
        assert source_file[:5] < "0167", "the source table must be applied before its reader"


def test_the_qa_band_never_names_the_mcp_identity() -> None:
    """S14, as a static assertion over the SQL itself.

    No MCP service account is ever issued for ``mainline_qa``, on any tier, ever. A `GRANT … TO
    mainline_auditor` inside a `mainline_qa` migration would be the single worst line in this
    repository, and it would look entirely ordinary in review.
    """
    for name in QA_VIEW_FILES:
        code = strip_sql_comments((MIGRATIONS_DIR / name).read_text(encoding="utf-8"))
        assert "mainline_auditor" not in code, (
            f"{name} names mainline_auditor in executable SQL. S14 is absolute."
        )


def test_the_qa_band_uses_the_shipped_vocabulary() -> None:
    """§11.5 vocabulary hygiene, enforced by a grep-class assertion exactly as the architecture
    says it must be: ``not_applicable`` → ``mechanism_absent``; ``haste_flag`` →
    ``reading_floor_met`` at positive polarity; ``approver_id`` → ``signer_sub``; and
    ``suspected_rubber_stamp`` does not exist, in schema or telemetry, ever."""
    banned = ("not_applicable", "haste_flag", "suspected_rubber_stamp", "approver_id")
    for name in QA_VIEW_FILES + AUDIT_VIEW_FILES:
        text = (MIGRATIONS_DIR / name).read_text(encoding="utf-8")
        code = strip_sql_comments(text)
        for token in banned:
            assert token not in code, f"{name}: banned vocabulary {token!r} in executable SQL"


# ══════════════════════════════════════════════════════════════════════════════════════════════
# CLUSTER TIER — everything below needs a real CockroachDB v26.2.
# ══════════════════════════════════════════════════════════════════════════════════════════════


@dataclass
class Cluster:
    dsn: str
    provenance: str
    proc: subprocess.Popen[bytes] | None = None
    owns_docker: bool = False


@dataclass
class Applied:
    dsn: str
    database: str
    blocked: list[tuple[str, str]] = field(default_factory=list)

    def connect(self) -> Any:
        return psycopg.connect(self.dsn, autocommit=True)


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
    TimeoutExpired in a fixture turns a run that should have skipped into a suite of errors."""
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
def views_cluster(
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
            "no CockroachDB v26.2 reachable. Provide one of: tests/integration/schema/"
            "conftest.py with a session `dsn` fixture (dm-runner), $MAINLINE_TEST_DSN, a "
            f"`cockroach` binary on PATH, or a running Docker daemon for `docker run {CRDB_IMAGE}`."
            " The view band is NOT verified by a skipped run."
        )
    try:
        yield found
    finally:
        if found.proc is not None:
            found.proc.terminate()
        if found.owns_docker:
            _docker(["rm", "-f", CONTAINER_NAME], timeout=DOCKER_PROBE_TIMEOUT_S)


@pytest.fixture(scope="session")
def applied(views_cluster: Cluster) -> Iterator[Applied]:
    """Apply the WHOLE tree into a fresh database, in the order the runner applies it.

    Failures OUTSIDE this band are recorded and the run continues; failures INSIDE this band are
    recorded too, and ``test_the_view_bands_apply_cleanly`` is what turns either into a red
    build. Aborting on the first foreign failure would make this suite unrunnable whenever any
    of the other seven domains has a file in flight, which for a fleet build is every hour of
    every day; and skipping would make it green while proving nothing.
    """
    from psycopg.conninfo import make_conninfo

    database = f"mainline_views_{uuid.uuid4().hex[:10]}"
    with psycopg.connect(views_cluster.dsn, autocommit=True) as admin:
        admin.execute(f"CREATE DATABASE {database}")
    dsn = make_conninfo(views_cluster.dsn, dbname=database)

    blocked: list[tuple[str, str]] = []
    with psycopg.connect(dsn, autocommit=True) as conn:
        for path in tree_paths():
            for statement in split_statements(path.read_text(encoding="utf-8")):
                try:
                    conn.execute(statement)
                except psycopg.Error as exc:
                    blocked.append((path.name, str(exc).splitlines()[0]))

    print(
        f"\n[views] cluster:  {views_cluster.provenance}\n"
        f"[views] database: {database}\n"
        f"[views] applied {len(tree_paths())} migrations, {len(blocked)} statements blocked"
    )
    try:
        yield Applied(dsn=dsn, database=database, blocked=blocked)
    finally:
        with psycopg.connect(views_cluster.dsn, autocommit=True) as admin:
            admin.execute(f"DROP DATABASE IF EXISTS {database} CASCADE")


@pytest.fixture
def conn(applied: Applied) -> Iterator[Any]:
    connection = applied.connect()
    try:
        yield connection
    finally:
        connection.close()


def _mcp_response_bytes(rows: list[Any], columns: list[str]) -> int:
    """Approximate the byte size the Managed MCP would return for a result set.

    JSON of ``{"columns": [...], "rows": [[...]]}`` with ``default=str`` for types JSON does not
    model. This is an APPROXIMATION and it is stated as one: the transport's exact encoding is
    not published, so the cap is asserted against a representation that is at least as large as
    a compact one. Being conservative in this direction is the correct error — a view that fits
    under this measure fits under a tighter encoding too.
    """
    payload = {"columns": columns, "rows": [list(r) for r in rows]}
    return len(json.dumps(payload, default=str, separators=(",", ":")).encode("utf-8"))


# ── the band's own apply result ───────────────────────────────────────────────────────────────


@pytest.mark.requires_cluster
def test_the_view_bands_apply_cleanly(applied: Applied) -> None:
    """Every file in 0155-0172 applied. Nothing else is asserted about the rest of the tree.

    This test is RED while a band this one depends on is still in flight, and the message names
    the file and the missing relation so that the dependency is legible rather than mysterious.
    The data-model lead's accepted risk DR-4 makes that the intended state: a test that has never
    been red asserts nothing, and a suite that skips its way to green asserts less.
    """
    mine = [(name, err) for name, err in applied.blocked if name in set(BAND_FILES)]
    assert mine == [], (
        "files in band 0155-0172 did not apply:\n"
        + "\n".join(f"  {name}: {err}" for name, err in mine)
        + "\n\nOther bands' failures in the same run (informational, not this band's):\n"
        + "\n".join(
            f"  {name}: {err}" for name, err in applied.blocked if name not in set(BAND_FILES)
        )
    )


# ── existence, shape, size ────────────────────────────────────────────────────────────────────


@pytest.mark.requires_cluster
def test_every_declared_view_exists(conn: Any) -> None:
    found = {
        f"{schema}.{name}"
        for schema, name in conn.execute(
            "SELECT table_schema, table_name FROM information_schema.views "
            "WHERE table_schema IN ('mainline_audit', 'mainline_qa')"
        ).fetchall()
    }
    expected = {f"mainline_audit.{v}" for v in AUDIT_VIEWS} | {f"mainline_qa.{v}" for v in QA_VIEWS}
    allowed = expected | {f"mainline_audit.{v}" for v in FOREIGN_AUDIT_VIEWS}
    assert expected <= found, f"missing views: {sorted(expected - found)}"
    assert found <= allowed, (
        f"unenumerated objects in the audit/qa schemas: {sorted(found - allowed)}.\n"
        "mainline_audit is constitutionally view-only and every object in it is granted to "
        "mainline_auditor by a SCHEMA-WIDE WILDCARD, so a new object here reaches the "
        "Managed-MCP surface the moment it is created, whoever created it. A view owned by "
        "another band is fine and belongs in FOREIGN_AUDIT_VIEWS with its owner named; an "
        "ANONYMOUS one is a disclosure nobody reviewed.\n"
        f"Currently enumerated foreign views: {FOREIGN_AUDIT_VIEWS}"
    )
    assert not any(v.startswith("mainline_qa.") for v in found - expected), (
        "mainline_qa holds a view this band did not declare. S14: per-named-person detail lives "
        "here and nowhere else, and an unenumerated object in it is exactly the surface no MCP "
        "account may ever reach."
    )


@pytest.mark.requires_cluster
@pytest.mark.parametrize("view", AUDIT_VIEWS + tuple(FOREIGN_AUDIT_VIEWS))
def test_every_audit_view_returns_at_most_25_rows(conn: Any, view: str) -> None:
    """§9.1: the Managed MCP caps a SELECT at 25 rows and truncates rather than refusing.

    Foreign views are included: the cap is a property of the schema and of the transport, not of
    whoever wrote the object, and a 26-row view in `mainline_audit` truncates the same way
    regardless of which band owns it.
    """
    # S608 is silenced at each of the three call sites below rather than repository-wide:
    # the interpolated name comes from this module's own AUDIT_VIEWS/QA_VIEWS tuples and an
    # identifier cannot be a bind parameter in any case.
    rows = conn.execute(f"SELECT * FROM mainline_audit.{view}").fetchall()  # noqa: S608
    assert len(rows) <= MCP_ROW_CAP, (
        f"mainline_audit.{view} returned {len(rows)} rows against a hard cap of {MCP_ROW_CAP}"
    )


@pytest.mark.requires_cluster
@pytest.mark.parametrize("view", AUDIT_VIEWS + tuple(FOREIGN_AUDIT_VIEWS))
def test_every_audit_view_fits_the_10_kib_response_cap(conn: Any, view: str) -> None:
    """§9.1: the response cap is 10 KiB. Over 25 rows that is ~410 bytes per row for everything,
    which is why this band rounds its floats, truncates its error strings, and returns a digest
    where a URI would be more readable."""
    cur = conn.execute(f"SELECT * FROM mainline_audit.{view}")  # noqa: S608
    rows = cur.fetchall()
    columns = [d.name for d in (cur.description or [])]
    size = _mcp_response_bytes(rows, columns)
    assert size <= MCP_BYTE_CAP, (
        f"mainline_audit.{view} would return ~{size} bytes against a {MCP_BYTE_CAP}-byte cap "
        f"({len(rows)} rows x {len(columns)} columns). The cap is a FUNCTIONAL requirement: the "
        "transport truncates silently, and a truncated audit answer is a safety defect."
    )


@pytest.mark.requires_cluster
@pytest.mark.parametrize("view", AUDIT_VIEWS + QA_VIEWS)
def test_every_view_publishes_the_truncation_contract(conn: Any, view: str) -> None:
    schema = "mainline_audit" if view in AUDIT_VIEWS else "mainline_qa"
    cur = conn.execute(f"SELECT * FROM {schema}.{view} LIMIT 0")  # noqa: S608
    columns = {d.name for d in (cur.description or [])}
    missing = [c for c in TRUNCATION_COLUMNS if c not in columns]
    assert missing == [], f"{schema}.{view} does not publish {missing}"


@pytest.mark.requires_cluster
@pytest.mark.parametrize("view", tuple(FOREIGN_AUDIT_VIEWS))
def test_foreign_audit_views_carry_some_truncation_flag(conn: Any, view: str) -> None:
    """§17's requirement of a foreign view, stated at the level §17 states it.

    This band publishes ``group_count`` + ``rows_complete`` uniformly so a reader never has to
    know which view they hold. A view owned by another band is not bound to that naming — §17
    asks for ``ancestry_complete`` **or an equivalent truncation flag** — so the assertion here
    is the weaker, correct one: SOMETHING in the row must say whether the answer was cut off.
    A capped view with no such column is a partial answer that presents as a whole one, and that
    is a defect regardless of who wrote it.
    """
    cur = conn.execute(f"SELECT * FROM mainline_audit.{view} LIMIT 0")  # noqa: S608
    columns = [d.name for d in (cur.description or [])]
    flags = [c for c in columns if "complete" in c or "truncat" in c]
    assert flags, (
        f"mainline_audit.{view} ({FOREIGN_AUDIT_VIEWS[view]}) publishes no truncation flag. "
        f"Columns: {columns}"
    )


@pytest.mark.requires_cluster
@pytest.mark.parametrize("view", AUDIT_VIEWS + QA_VIEWS + tuple(FOREIGN_AUDIT_VIEWS))
def test_no_view_definition_names_a_system_catalog(conn: Any, view: str) -> None:
    """The behavioural twin of the static assertion. The static one reads the migration file; this
    one reads what the CLUSTER stored, which is what an MCP query actually executes. They can
    differ if a view is later replaced out of band, and that is exactly the case worth catching —
    which is also why foreign views are covered: a catalog reference in `mainline_audit` breaks
    the MCP surface whoever wrote it.
    """
    schema = "mainline_qa" if view in QA_VIEWS else "mainline_audit"
    row = conn.execute(
        "SELECT view_definition FROM information_schema.views "
        "WHERE table_schema = %s AND table_name = %s",
        (schema, view),
    ).fetchone()
    assert row is not None, f"{schema}.{view} has no stored definition"
    definition = row[0] or ""
    for catalog in FORBIDDEN_CATALOGS:
        assert re.search(rf"\b{catalog}\s*\.", definition, re.IGNORECASE) is None, (
            f"{schema}.{view}'s STORED definition reads {catalog}"
        )


# ── the truncation flag, exercised rather than merely present ─────────────────────────────────


def _sha32(seed: str) -> bytes:
    import hashlib

    return hashlib.sha256(seed.encode("utf-8")).digest()


@pytest.mark.requires_cluster
def test_the_truncation_flag_actually_flips_at_the_26th_group(conn: Any) -> None:
    """The assertion the whole band exists for, exercised end to end on ``v_ledger_health``.

    A flag that is present and never observed to change is a column, not a control. Twenty-six
    sites produce twenty-six groups; the transport shows twenty-five; and every row that survives
    says so. Without that, the 26th site's open debt is invisible and indistinguishable from
    absent — which in this product is the difference between "no site owes evidence" and "we did
    not look at the site that does".

    ``v_ledger_health`` is chosen because its two base tables — ``mainline.site`` and
    ``mainline.ledger_checkpoint`` — are the ones this band can populate without depending on a
    trigger, a projection or a band still in flight.
    """
    tag = uuid.uuid4().hex[:8]
    for i in range(26):
        site_id = str(uuid.uuid4())
        # 't' so these sort AFTER the '0'-prefixed codes the two targeted ledger tests use.
        # A capped view cannot be filtered from outside — the LIMIT is inside it, so an outer
        # `WHERE site_code = …` searches the 25 rows that survived, not the table. That is not a
        # test artefact; it is the property `rows_complete` exists to make visible, and it is
        # why every other test in this file that queries a capped view by key uses a key that
        # sorts within the cap.
        code = f"trunc{tag}{i:02d}"
        conn.execute(
            "INSERT INTO mainline.site (site_id, site_code, site_role, tenant_id, taxonomy_ver) "
            "VALUES (%s, %s, %s, %s, 1)",
            (site_id, code, f"role_{code}", str(uuid.uuid4())),
        )
        conn.execute(
            "INSERT INTO mainline.ledger_checkpoint "
            "(site_code, tree_size, root_hash, body, beacon, log_sig, canon_src_sha256, "
            " admissible) VALUES (%s, %s, %s, %s, '{}'::JSONB, %s, %s, %s)",
            (code, i, _sha32(code), f"checkpoint {code}", b"\x30\x44", _sha32("canon"), i % 2 == 0),
        )

    cur = conn.execute(
        "SELECT site_code, group_count, rows_complete, witness_complete "
        "FROM mainline_audit.v_ledger_health"
    )
    rows = cur.fetchall()

    assert len(rows) == MCP_ROW_CAP, (
        f"expected the view to hand back exactly {MCP_ROW_CAP} rows with 26 groups behind it; "
        f"got {len(rows)}"
    )
    group_counts = {r[1] for r in rows}
    assert len(group_counts) == 1, (
        f"`group_count` must be identical on every surviving row; got {group_counts}. Rows that "
        "disagree about how many groups exist cannot all be describing the same result set."
    )
    assert next(iter(group_counts)) >= 26, (
        f"`group_count` should report the TRUE number of groups; got {group_counts}. A per-row "
        "count that reported 25 would be the truncated answer describing itself as complete."
    )
    assert all(r[2] is False for r in rows), (
        "`rows_complete` must be false on every row once the group count exceeds the transport "
        "cap. A truncated aggregate that presents as complete is the defect this band exists to "
        "make impossible."
    )


@pytest.mark.requires_cluster
def test_the_truncation_flag_reports_complete_when_it_is(conn: Any) -> None:
    """PL-2's other half. A flag that is always ``false`` is as useless as one that is always
    ``true``; this asserts the honest positive on a view whose population this test controls."""
    rows = conn.execute(
        "SELECT group_count, rows_complete FROM mainline_audit.v_unused_indexes"
    ).fetchall()
    # No collector has run in a fresh database, so the snapshot table is empty and there are no
    # groups at all. Zero is <= 25, so the view must report itself complete.
    assert all(r[1] is True for r in rows), (
        "an empty ops snapshot must report `rows_complete = true`: nothing was truncated. "
        "Reporting false on an empty result would train the reader to ignore the flag."
    )
    conn.execute(
        "INSERT INTO mainline_ops.index_usage_snapshot "
        "(collector, collector_ver, schema_name, table_name, index_name, index_kind, "
        " total_reads, window_reads) "
        "VALUES ('pytest', '0', 'mainline', 'permit', 'permit_epoch_target', 'unique', 0, 0)"
    )
    rows = conn.execute(
        "SELECT schema_name, table_name, index_name, is_unique, group_count, rows_complete, "
        "       measurement_complete, snapshot_fresh "
        "FROM mainline_audit.v_unused_indexes"
    ).fetchall()
    assert len(rows) == 1, f"expected the one zero-read index to surface; got {rows}"
    (_, _, index_name, is_unique, group_count, rows_complete, measured, fresh) = rows[0]
    assert index_name == "permit_epoch_target"
    assert is_unique is True, (
        "`is_unique` must be carried so this view cannot be read as a drop list without the "
        "reader seeing that the index is a constraint. A partial UNIQUE enforcing "
        "one_live_disposition has zero reads BY CONSTRUCTION."
    )
    assert (group_count, rows_complete) == (1, True)
    assert measured is True
    assert fresh is True


@pytest.mark.requires_cluster
def test_a_counter_reset_marks_the_measurement_incomplete(conn: Any) -> None:
    """Fail-closed, in the ops channel's own terms. "Zero reads" after a node restart means
    nothing at all — the index may have been traversed a million times before the counters were
    cleared — so the row must report its measurement incomplete rather than its index unused."""
    conn.execute(
        "INSERT INTO mainline_ops.index_usage_snapshot "
        "(collector, collector_ver, schema_name, table_name, index_name, index_kind, "
        " total_reads, window_reads, counters_reset) "
        "VALUES ('pytest', '0', 'mainline', 'clause', 'by_doc', 'secondary', 0, 0, true)"
    )
    row = conn.execute(
        "SELECT measurement_complete FROM mainline_audit.v_unused_indexes "
        "WHERE index_name = 'by_doc'"
    ).fetchone()
    assert row is not None, "the reset snapshot did not surface at all"
    assert row[0] is False


@pytest.mark.requires_cluster
def test_the_changefeed_view_calls_an_absent_feed_absent_and_not_healthy(conn: Any) -> None:
    """The quietest failure this system has, made loud.

    §18 keeps changefeeds out of the migrations — they are cluster jobs, re-created on restore —
    so after a restore the schema is complete and no feed is running. The one status a feed
    cannot emit is "I am not running", which is why 0155a makes ``'absent'`` a representable
    ``job_status`` with a CHECK rather than letting absence be a missing row.
    """
    conn.execute(
        "INSERT INTO mainline_ops.changefeed_health_snapshot "
        "(collector, collector_ver, feed_name, job_status, sink_uri_sha256, sink_kind) "
        "VALUES ('pytest', '0', 'cf_outbox', 'absent', %s, 'webhook')",
        (_sha32("sink"),),
    )
    row = conn.execute(
        "SELECT feed_absent, feed_running, spine_live, rows_complete "
        "FROM mainline_audit.v_changefeed_health WHERE feed_name = 'cf_outbox'"
    ).fetchone()
    assert row is not None, "an absent feed must still produce a row"
    feed_absent, feed_running, spine_live, rows_complete = row
    assert feed_absent is True
    assert feed_running is False
    assert spine_live is False, (
        "`spine_live` is fail-closed: running, with a highwater, and no more than five minutes "
        "behind. An absent feed satisfies none of the three."
    )
    assert rows_complete is True


@pytest.mark.requires_cluster
def test_a_running_feed_with_no_resolved_timestamp_is_not_live(conn: Any) -> None:
    """A feed that has emitted no resolved span has COMMITTED TO NOTHING, and reading its
    ``running`` status as health is how a stalled spine passes an ops review."""
    conn.execute(
        "INSERT INTO mainline_ops.changefeed_health_snapshot "
        "(collector, collector_ver, feed_name, job_status, sink_uri_sha256, sink_kind, "
        " highwater, behind_seconds) "
        "VALUES ('pytest', '0', 'cf_stalled', 'running', %s, 'kafka', NULL, NULL)",
        (_sha32("sink2"),),
    )
    row = conn.execute(
        "SELECT feed_running, spine_live FROM mainline_audit.v_changefeed_health "
        "WHERE feed_name = 'cf_stalled'"
    ).fetchone()
    assert row == (True, False)


@pytest.mark.requires_cluster
def test_the_ops_views_never_leak_a_sink_uri(conn: Any) -> None:
    """A changefeed sink URI carries its credentials inline. 0155a stores SHA-256 of it, so the
    leak is unrepresentable rather than merely unlikely — a control in the schema beats a control
    in whichever collector build happens to be deployed."""
    cur = conn.execute("SELECT * FROM mainline_audit.v_changefeed_health LIMIT 0")
    columns = {d.name for d in (cur.description or [])}
    assert "sink_uri" not in columns
    assert "sink_uri_sha256_hex" in columns
    table = conn.execute(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_schema = 'mainline_ops' AND table_name = 'changefeed_health_snapshot'"
    ).fetchall()
    names = {r[0] for r in table}
    assert "sink_uri" not in names, (
        "mainline_ops.changefeed_health_snapshot must not carry a sink URI in any form; the "
        "column is sink_uri_sha256 and the redaction is structural."
    )


@pytest.mark.requires_cluster
def test_the_ledger_view_reports_length_and_not_cadence(conn: Any) -> None:
    """``tree_size`` is ``max()``, never ``count()``.

    ``ledger_checkpoint`` is keyed ``(site_code, tree_size)`` and ``tree_size`` is the RFC 6962
    tree size at issuance, so ``max()`` is the number of leaves the log has committed to.
    ``count(*)`` would be the number of checkpoints issued, which is a function of the
    60-second anchoring cadence and says nothing about the log. Reporting cadence as length is
    the kind of number that survives into a deck and gets taken apart in a deposition.
    """
    # '0a' so this site sorts inside the view's own `ORDER BY site_code … LIMIT 25`. A capped
    # view cannot be filtered from outside: the LIMIT is applied inside the view, so an outer
    # WHERE searches the surviving rows rather than the table.
    tag = uuid.uuid4().hex[:6]
    code = f"0a{tag}"
    conn.execute(
        "INSERT INTO mainline.site (site_id, site_code, site_role, tenant_id, taxonomy_ver) "
        "VALUES (%s, %s, %s, %s, 1)",
        (str(uuid.uuid4()), code, f"role_{code}", str(uuid.uuid4())),
    )
    for size in (0, 7, 41):
        conn.execute(
            "INSERT INTO mainline.ledger_checkpoint "
            "(site_code, tree_size, root_hash, body, beacon, log_sig, canon_src_sha256, "
            " admissible) VALUES (%s, %s, %s, %s, '{}'::JSONB, %s, %s, true)",
            (code, size, _sha32(f"{code}{size}"), f"cp {size}", b"\x30\x44", _sha32("canon")),
        )
    row = conn.execute(
        "SELECT tree_size, checkpoints, admissible_checkpoints, inadmissible_checkpoints, "
        "       open_debt, witness_complete "
        "FROM mainline_audit.v_ledger_health WHERE site_code = %s",
        (code,),
    ).fetchone()
    assert row is not None
    tree_size, checkpoints, admissible, inadmissible, open_debt, witness_complete = row
    assert tree_size == 41, "tree_size must be max(tree_size), the log's length"
    assert checkpoints == 3, "checkpoints must be count(*), the anchoring cadence"
    assert (admissible, inadmissible, open_debt) == (3, 0, 0)
    assert witness_complete is True


@pytest.mark.requires_cluster
def test_an_inadmissible_checkpoint_makes_the_witness_incomplete(conn: Any) -> None:
    """I16: no checkpoint is admissible unless cosigned across >= k distinct trust domains
    including >= 1 adverse. A site holding an uncosigned checkpoint has not been witnessed, and
    the view must not average that away."""
    tag = uuid.uuid4().hex[:6]
    code = f"0b{tag}"  # sorts inside the cap; see the note in the preceding test
    conn.execute(
        "INSERT INTO mainline.site (site_id, site_code, site_role, tenant_id, taxonomy_ver) "
        "VALUES (%s, %s, %s, %s, 1)",
        (str(uuid.uuid4()), code, f"role_{code}", str(uuid.uuid4())),
    )
    for size, admissible in ((0, True), (1, False)):
        conn.execute(
            "INSERT INTO mainline.ledger_checkpoint "
            "(site_code, tree_size, root_hash, body, beacon, log_sig, canon_src_sha256, "
            " admissible) VALUES (%s, %s, %s, %s, '{}'::JSONB, %s, %s, %s)",
            (
                code,
                size,
                _sha32(f"{code}{size}"),
                f"cp {size}",
                b"\x30\x44",
                _sha32("canon"),
                admissible,
            ),
        )
    row = conn.execute(
        "SELECT admissible_checkpoints, inadmissible_checkpoints, witness_complete "
        "FROM mainline_audit.v_ledger_health WHERE site_code = %s",
        (code,),
    ).fetchone()
    assert row == (1, 1, False)


@pytest.mark.requires_cluster
def test_the_qa_median_is_exact_and_needs_no_ordered_set_aggregate(conn: Any) -> None:
    """``v_disposition_profile``'s median is computed by row numbering, not by
    ``percentile_cont(0.5) WITHIN GROUP (…)``, because ordered-set aggregate support is not on
    the measured capability list for this cluster and an unverified function inside a migration
    is a migration that fails on a fresh cluster and nowhere else.

    The predicate is pure integer arithmetic — ``rn * 2 BETWEEN n AND n + 2`` — and this test
    proves it selects the right rows for both parities without touching the database's own
    percentile machinery.
    """
    for n in (1, 2, 3, 4, 5, 6, 7, 8):
        values = list(range(1, n + 1))
        chosen = [v for rn, v in enumerate(values, start=1) if n <= rn * 2 <= n + 2]
        expected = sum(chosen) / len(chosen)
        # The exact median of 1..n
        reference = values[n // 2] if n % 2 == 1 else (values[n // 2 - 1] + values[n // 2]) / 2
        assert expected == reference, (
            f"n={n}: the middle-row predicate selected {chosen}, mean {expected}, but the median "
            f"of {values} is {reference}"
        )
    # And the same arithmetic, evaluated by the server, so a dialect difference in integer
    # comparison would surface here rather than in production.
    got = conn.execute(
        "WITH v(x) AS (VALUES (1),(2),(3),(4)), "
        "     r AS (SELECT x, row_number() OVER (ORDER BY x) AS rn, count(*) OVER () AS n FROM v) "
        "SELECT avg(x) FROM r WHERE r.rn * 2 >= r.n AND r.rn * 2 <= r.n + 2"
    ).fetchone()
    assert got is not None, "the server returned no row for the middle-row median"
    assert float(got[0]) == 2.5


@pytest.mark.requires_cluster
def test_the_fixity_ratio_distinguishes_an_empty_scope_from_full_coverage(conn: Any) -> None:
    """``nullif(sum(n_in_scope), 0)`` returns NULL rather than raising, and NULL means "the
    question does not apply". Coalescing it to 0.0 would report an empty scope as perfect
    coverage, and an empty scope is usually a scope predicate that stopped matching.

    This test also pins the MEASURED type correction: ``sum()`` over INT8 returns DECIMAL on
    CockroachDB v26.2.5 and there is no ``<float> / <decimal>`` operator, so §17's ``::FLOAT8``
    numerator cast does not compile. Both sides are NUMERIC.
    """
    site_id = str(uuid.uuid4())
    conn.execute(
        "INSERT INTO mainline.site (site_id, site_code, site_role, tenant_id, taxonomy_ver) "
        "VALUES (%s, %s, %s, %s, 1)",
        (site_id, f"fx{uuid.uuid4().hex[:8]}", f"role_fx{uuid.uuid4().hex[:6]}", str(uuid.uuid4())),
    )
    conn.execute(
        "INSERT INTO mainline.patrol_run (site_id, patrol_class, schedule_id, occurrence_ts, "
        " scope_pred, n_in_scope, n_checked, n_not_checked, as_of_hlc, started_at, finished_at) "
        "VALUES (%s, 'L0', 'sched-empty', now(), '{}'::JSONB, 0, 0, 0, 1, now(), now())",
        (site_id,),
    )
    conn.execute(
        "INSERT INTO mainline.patrol_run (site_id, patrol_class, schedule_id, occurrence_ts, "
        " scope_pred, n_in_scope, n_checked, n_not_checked, as_of_hlc, started_at, finished_at) "
        "VALUES (%s, 'L1', 'sched-full', now(), '{}'::JSONB, 10, 10, 0, 1, now(), now())",
        (site_id,),
    )
    rows = {
        r[0]: (r[1], r[2])
        for r in conn.execute(
            "SELECT patrol_class, not_checked_ratio, coverage_complete "
            "FROM mainline_audit.v_fixity_coverage WHERE site_id = %s",
            (site_id,),
        ).fetchall()
    }
    assert rows["L0"][0] is None, "an empty scope must report a NULL ratio, never 0.0"
    assert rows["L0"][1] is False, "an empty scope is not complete coverage"
    assert float(rows["L1"][0]) == 0.0
    assert rows["L1"][1] is True


@pytest.mark.requires_cluster
def test_an_unfinished_patrol_is_not_complete_coverage(conn: Any) -> None:
    """MI22, in the fixity channel: a patrol that started and never finished is a projection that
    is stale, and staleness must present as staleness rather than as a clean scan."""
    site_id = str(uuid.uuid4())
    conn.execute(
        "INSERT INTO mainline.site (site_id, site_code, site_role, tenant_id, taxonomy_ver) "
        "VALUES (%s, %s, %s, %s, 1)",
        (site_id, f"un{uuid.uuid4().hex[:8]}", f"role_un{uuid.uuid4().hex[:6]}", str(uuid.uuid4())),
    )
    conn.execute(
        "INSERT INTO mainline.patrol_run (site_id, patrol_class, schedule_id, occurrence_ts, "
        " scope_pred, n_in_scope, n_checked, n_not_checked, as_of_hlc, started_at, finished_at) "
        "VALUES (%s, 'L2', 'sched-open', now(), '{}'::JSONB, 5, 5, 0, 1, now(), NULL)",
        (site_id,),
    )
    row = conn.execute(
        "SELECT unfinished_runs, last_completed, coverage_complete "
        "FROM mainline_audit.v_fixity_coverage WHERE site_id = %s",
        (site_id,),
    ).fetchone()
    assert row is not None
    assert row[0] == 1
    assert row[1] is None, "no run finished, so there is no last completed time to report"
    assert row[2] is False
