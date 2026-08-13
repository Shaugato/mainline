# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""Backends for the channel-D integration suite, and what each one is allowed to prove.

Two engines, deliberately, because they answer different questions and only one of them is
available on an arbitrary machine:

**CockroachDB** (``MAINLINE_TEST_DSN``/``COCKROACH_URL``, else a local ``cockroach`` binary,
else Docker).  The only backend that can answer "does the optimiser constrain the scan?", and
the one the product actually runs on.  The three tables are created by applying the real
migrations ``0043`` to ``0045`` - not a transliteration — so the suite cannot pass against a
schema the product does not have.

**SQLite** (standard library, always present).  A *second real SQL engine* executing the
**same statement text** the gate path issues.  This is what makes the BM25 differential — 200
queries over 2 000 documents against a pure-Python oracle — run on a laptop with no cluster,
which matters because the alternative is an arithmetic oracle that is skipped by default, and
a skipped oracle is not an oracle.

What SQLite is **not** allowed to prove is stated in the tests that need CockroachDB: the plan
assertion skips with a reason on SQLite, because SQLite's query planner is not CockroachDB's
and pretending otherwise would be the exact dishonesty this band exists to prevent.

The two backends share one statement text.  ``ParamStyle`` changes only the placeholder token,
and ``tests/unit/recall_lexical/test_bm25_sql_shape.py`` asserts that the renderings are
byte-identical once placeholders are normalised — so "the SQL that was differentially tested
is the SQL that ships" is a checked claim, not a hope.
"""

from __future__ import annotations

import os
import shutil
import socket
import sqlite3
import subprocess
import sys
import time
import uuid
from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from pathlib import Path

import pytest
from trappoint_testkit import pinned_image

REPO_ROOT = Path(__file__).resolve().parents[3]
PACKAGE_SRC = REPO_ROOT / "packages" / "trappoint-recall" / "src"
MIGRATIONS = REPO_ROOT / "verticals" / "mainline" / "db" / "migrations"
LEX_MIGRATIONS = ("0043_lex_posting.sql", "0044_lex_stats.sql", "0045_lex_doclen.sql")

try:  # pragma: no cover - import-time bootstrap
    import trappoint_recall.lexical  # noqa: F401
except ImportError:  # pragma: no cover - import-time bootstrap
    sys.path.insert(0, str(PACKAGE_SRC))

from trappoint_recall.lexical.executor import ParamStyle  # noqa: E402

CRDB_IMAGE = os.environ.get("MAINLINE_CRDB_IMAGE") or pinned_image(Path(__file__))
CONTAINER_NAME = "mainline-recall-lexical-test"
READY_TIMEOUT_S = 120.0
DOCKER_PROBE_TIMEOUT_S = 10.0
DOCKER_RUN_TIMEOUT_S = 600.0

#: SQLite mirror of migrations 0043-0045.  A transliteration, and checked against the real
#: migration text by ``test_sqlite_mirror_matches_the_migrations`` so that it cannot drift
#: into agreeing with a schema the product does not have.
SQLITE_DDL = (
    """CREATE TABLE mainline.lex_posting (
         site_id  TEXT NOT NULL,
         term     TEXT NOT NULL,
         event_id TEXT NOT NULL,
         weight   REAL NOT NULL,
         CONSTRAINT lex_posting_pk PRIMARY KEY (site_id, term, event_id))""",
    """CREATE TABLE mainline.lex_stats (
         site_id TEXT    NOT NULL,
         term    TEXT    NOT NULL,
         df      INTEGER NOT NULL,
         CONSTRAINT lex_stats_pk PRIMARY KEY (site_id, term),
         CONSTRAINT df_positive CHECK (df >= 0))""",
    """CREATE TABLE mainline.lex_doclen (
         event_id TEXT    NOT NULL,
         len      INTEGER NOT NULL,
         CONSTRAINT lex_doclen_pk PRIMARY KEY (event_id),
         CONSTRAINT len_positive CHECK (len >= 0))""",
)


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line("markers", "differential: SQL against the pure-Python oracle")
    config.addinivalue_line("markers", "cockroach: needs a real CockroachDB v26.2")


@dataclass
class Backend:
    """Everything a test needs to talk to whichever engine is present."""

    engine: str  # "cockroachdb" | "sqlite"
    provenance: str
    style: ParamStyle
    execute: object  # Executor

    @property
    def is_cockroach(self) -> bool:
        return self.engine == "cockroachdb"


# ── SQLite ───────────────────────────────────────────────────────────────────────────────────


def _sqlite_backend() -> tuple[Backend, sqlite3.Connection]:
    connection = sqlite3.connect(":memory:")
    # `ATTACH ':memory:' AS mainline` gives SQLite a real schema named `mainline`, so the
    # statement text needs no rewriting at all: `mainline.lex_posting` resolves on both
    # engines. Rewriting the text would have made the differential test a different statement.
    connection.execute("ATTACH ':memory:' AS mainline")
    for ddl in SQLITE_DDL:
        connection.execute(ddl)

    def execute(sql: str, params: Sequence[object] = ()) -> list[tuple[object, ...]]:
        return connection.execute(sql, tuple(params)).fetchall()

    return (
        Backend(
            engine="sqlite",
            provenance=f"sqlite3 {sqlite3.sqlite_version} (stdlib, in-memory)",
            style=ParamStyle.QMARK,
            execute=execute,
        ),
        connection,
    )


# ── CockroachDB discovery, in the house order: env, local binary, docker ────────────────────


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def _docker(args: list[str], *, timeout: float) -> subprocess.CompletedProcess[str] | None:
    """A dead Docker daemon does not refuse ``docker info``; it blocks.  A hang means "no"."""
    try:
        return subprocess.run(  # noqa: S603
            ["docker", *args],  # noqa: S607 - `docker` is resolved via PATH by design
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except (subprocess.TimeoutExpired, OSError):
        return None


def _wait_until_ready(psycopg_module: object, dsn: str, deadline: float) -> bool:
    while time.monotonic() < deadline:
        try:
            with psycopg_module.connect(dsn, connect_timeout=3) as conn:  # type: ignore[attr-defined]
                conn.execute("SELECT 1")
            return True
        except Exception:  # noqa: BLE001 - any failure means "not yet"
            time.sleep(1.0)
    return False


def _discover_cockroach(tmp: Path) -> tuple[str, str, object] | None:
    """Return ``(dsn, provenance, psycopg_module)`` or ``None``, never raising."""
    try:
        import psycopg
    except ImportError:
        return None

    for name in ("MAINLINE_TEST_DSN", "COCKROACH_URL", "CRDB_URL"):
        value = os.environ.get(name)
        if value:
            return value, f"${name}", psycopg

    binary = shutil.which("cockroach")
    if binary is not None:
        port = _free_port()
        proc = subprocess.Popen(  # noqa: S603 - fixed argv, no shell
            [
                binary,
                "start-single-node",
                "--insecure",
                "--store=type=mem,size=2GiB",
                f"--listen-addr=127.0.0.1:{port}",
                f"--http-addr=127.0.0.1:{_free_port()}",
            ],
            cwd=str(tmp),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        dsn = f"postgresql://root@127.0.0.1:{port}/defaultdb?sslmode=disable"
        if _wait_until_ready(psycopg, dsn, time.monotonic() + READY_TIMEOUT_S):
            _OWNED["proc"] = proc
            return dsn, f"local `cockroach` binary on port {port}", psycopg
        proc.terminate()

    if shutil.which("docker") is not None:
        info = _docker(["info", "--format", "{{.ServerVersion}}"], timeout=DOCKER_PROBE_TIMEOUT_S)
        if info is not None and info.returncode == 0:
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
            if started is not None and started.returncode == 0:
                dsn = f"postgresql://root@127.0.0.1:{port}/defaultdb?sslmode=disable"
                if _wait_until_ready(psycopg, dsn, time.monotonic() + READY_TIMEOUT_S):
                    _OWNED["docker"] = True
                    return dsn, f"docker {CRDB_IMAGE} on port {port}", psycopg
                _docker(["rm", "-f", CONTAINER_NAME], timeout=DOCKER_PROBE_TIMEOUT_S)
    return None


_OWNED: dict[str, object] = {}

#: Why CockroachDB was not reached, so that a skip says something actionable.
NO_CLUSTER_REASON = (
    "no CockroachDB v26.2 reachable: set MAINLINE_TEST_DSN, or put `cockroach` on PATH, or "
    f"start the Docker daemon so the suite can run `docker run {CRDB_IMAGE} "
    "start-single-node --insecure`. Channel D's plan is NOT verified by a skipped run."
)


def _statements(text: str) -> list[str]:
    """Split a migration file on semicolons at statement level (no dollar-quoting here)."""
    return [chunk.strip() for chunk in text.split(";") if chunk.strip()]


@pytest.fixture(scope="session")
def cockroach(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Backend | None]:
    """A CockroachDB backend with migrations 0043-0045 applied, or ``None``."""
    found = _discover_cockroach(tmp_path_factory.mktemp("crdb"))
    if found is None:
        yield None
    else:
        dsn, provenance, psycopg = found
        database = f"mainline_lex_{uuid.uuid4().hex[:10]}"
        with psycopg.connect(dsn, autocommit=True) as admin:  # type: ignore[attr-defined]
            admin.execute(f"CREATE DATABASE {database}")
        from psycopg.conninfo import (  # type: ignore[import-not-found]
            conninfo_to_dict,
            make_conninfo,
        )

        parts = conninfo_to_dict(dsn)
        parts["dbname"] = database
        scoped = make_conninfo(**parts)
        connection = psycopg.connect(scoped, autocommit=True)  # type: ignore[attr-defined]
        connection.execute("CREATE SCHEMA IF NOT EXISTS mainline")
        for name in LEX_MIGRATIONS:
            for statement in _statements((MIGRATIONS / name).read_text(encoding="utf-8")):
                connection.execute(statement)

        def execute(sql: str, params: Sequence[object] = ()) -> list[tuple[object, ...]]:
            # `or None`: psycopg only treats `%` as a placeholder introducer when a params
            # argument is present, and a LITERAL-style statement carries none. Passing an
            # empty tuple would make any future `%` in the text a parse error at run time.
            cursor = connection.execute(sql, tuple(params) or None)
            return list(cursor.fetchall()) if cursor.description else []

        print(f"\n[recall_lexical] cockroachdb: {provenance}, database {database}")
        try:
            yield Backend(
                engine="cockroachdb",
                provenance=provenance,
                style=ParamStyle.PYFORMAT,
                execute=execute,
            )
        finally:
            connection.close()
            with psycopg.connect(dsn, autocommit=True) as admin:  # type: ignore[attr-defined]
                admin.execute(f"DROP DATABASE IF EXISTS {database} CASCADE")
            proc = _OWNED.get("proc")
            if proc is not None:
                proc.terminate()  # type: ignore[union-attr]
            if _OWNED.get("docker"):
                _docker(["rm", "-f", CONTAINER_NAME], timeout=DOCKER_PROBE_TIMEOUT_S)


@pytest.fixture()
def sqlite_backend() -> Iterator[Backend]:
    backend, connection = _sqlite_backend()
    try:
        yield backend
    finally:
        connection.close()


@pytest.fixture(scope="session")
def backend(request: pytest.FixtureRequest) -> Backend:
    """The engine the arithmetic suites run on: CockroachDB when present, SQLite otherwise.

    Not a skip when CockroachDB is absent.  The differential is the oracle for a BM25 written
    directly in SQL, and an oracle that only runs on fully-provisioned CI is an oracle that is
    not consulted when the code is being written.

    Session-scoped, and shared.  Isolation between tests comes from **site scoping**, not from
    a fresh database: every test in this band works under its own ``site_id`` and its own
    ``event_id`` values.  That is the stronger arrangement, because a suite that isolates by
    tearing the tables down cannot notice a statement that reaches another site's rows —
    which is the exact defect ``test_site_scoping.py`` is looking for.
    """
    crdb = request.getfixturevalue("cockroach")
    if crdb is not None:
        return crdb  # type: ignore[no-any-return]
    made, connection = _sqlite_backend()
    request.addfinalizer(connection.close)
    return made


@pytest.fixture(scope="session")
def fixture_corpus():  # noqa: ANN201 - the dataclass lives in _corpus
    from _corpus import build_fixture

    return build_fixture()
