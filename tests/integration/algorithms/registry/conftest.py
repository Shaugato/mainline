# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""Cluster and schema fixtures for the DIRECTRIX integration suite.

The suite needs a real CockroachDB v26.2.  It finds one in this order and SKIPS
WITH A REASON rather than faking anything if it cannot:

1. ``MAINLINE_TEST_DSN`` (or ``COCKROACH_URL`` / ``CRDB_URL``) — a running cluster;
2. a ``cockroach`` binary on ``PATH`` — an in-memory single node for the session;
3. a running Docker daemon — the image ``compose.yaml`` pins.

Nothing in this worker is done on the basis of a skipped run, and the skip
message says which of the three is missing.  AWS credentials are not valid on the
build machine and CockroachDB Cloud is not assumed either; a local binary or a
container is the intended path.
"""

from __future__ import annotations

import os
import shutil
import socket
import subprocess
import sys
import time
import uuid
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path

import pytest
from trappoint_testkit import pinned_image

_REPO_ROOT = Path(__file__).resolve().parents[4]
_SRC = _REPO_ROOT / "verticals" / "mainline" / "packages" / "mainline-domain" / "src"
if _SRC.is_dir() and str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from _directrix_support import (  # noqa: E402  (after the sys.path fix-up, deliberately)
    PREREQ_DIR,
    owned_migration_file,
    spine_migrations,
    split_statements,
)

try:  # soft, NOT `importorskip`
    import psycopg
except ImportError:  # pragma: no cover - depends on which extras are installed
    psycopg = None  # type: ignore[assignment]

#: `pytest.importorskip` at conftest scope would skip the WHOLE directory,
#: including `test_0207_shape.py`, which needs no driver and no cluster and is
#: the only check of migration 0207 that runs everywhere.  A missing driver must
#: cost the cluster-backed tests and nothing else.
PSYCOPG_MISSING_REASON = (
    "psycopg 3 is required to talk to CockroachDB; `uv sync --extra db` installs it"
)

CRDB_IMAGE = os.environ.get("MAINLINE_CRDB_IMAGE") or pinned_image(Path(__file__))
CONTAINER_NAME = "mainline-directrix-test"
READY_TIMEOUT_S = 120.0
DOCKER_PROBE_TIMEOUT_S = 10.0
DOCKER_RUN_TIMEOUT_S = 600.0


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line("markers", "schema: exercises DDL against a real cluster")


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def _wait_until_ready(dsn: str, deadline: float) -> bool:
    last: Exception | None = None
    while time.monotonic() < deadline:
        try:
            with psycopg.connect(dsn, connect_timeout=3) as conn:
                conn.execute("SELECT 1")
            return True
        except Exception as exc:  # noqa: BLE001 - any failure means "not yet"
            last = exc
            time.sleep(1.0)
    if last is not None:
        print(f"cluster never became ready: {last}")
    return False


@dataclass
class Cluster:
    dsn: str
    provenance: str
    process: subprocess.Popen[bytes] | None = field(default=None, repr=False)


def _dsn_from_env() -> Cluster | None:
    for name in ("MAINLINE_TEST_DSN", "COCKROACH_URL", "CRDB_URL"):
        value = os.environ.get(name)
        if value:
            return Cluster(dsn=value, provenance=f"${name}")
    return None


def _start_local_binary(tmp: Path) -> Cluster | None:
    binary = shutil.which("cockroach")
    if binary is None:
        return None
    port = _free_port()
    http_port = _free_port()
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
        return Cluster(
            dsn=dsn,
            provenance=f"local `cockroach` binary on port {port}",
            process=proc,
        )
    proc.terminate()
    return None


def _docker(args: list[str], *, timeout: float) -> subprocess.CompletedProcess[str] | None:
    """Run a docker command; return ``None`` if it hangs, dies, or is not there.

    A dead Docker daemon does not make ``docker info`` fail — it makes it BLOCK,
    and an uncaught ``TimeoutExpired`` would turn every cluster-backed test into
    an ERROR instead of the skip the situation calls for.
    """
    try:
        return subprocess.run(
            ["docker", *args], capture_output=True, text=True, timeout=timeout, check=False
        )
    except (subprocess.TimeoutExpired, OSError):
        return None


def _docker_available() -> bool:
    if shutil.which("docker") is None:
        return False
    probe = _docker(["info", "--format", "{{.ServerVersion}}"], timeout=DOCKER_PROBE_TIMEOUT_S)
    return probe is not None and probe.returncode == 0


def _start_docker() -> Cluster | None:
    if not _docker_available():
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
        detail = "hung or could not be executed" if started is None else started.stderr.strip()
        print(f"`docker run {CRDB_IMAGE}` failed: {detail}")
        return None
    dsn = f"postgresql://root@127.0.0.1:{port}/defaultdb?sslmode=disable"
    if _wait_until_ready(dsn, time.monotonic() + READY_TIMEOUT_S):
        return Cluster(dsn=dsn, provenance=f"docker {CRDB_IMAGE} on port {port}")
    _docker(["rm", "-f", CONTAINER_NAME], timeout=DOCKER_PROBE_TIMEOUT_S)
    return None


@pytest.fixture(scope="session")
def cluster(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Cluster]:
    if psycopg is None:
        pytest.skip(PSYCOPG_MISSING_REASON)
    found = _dsn_from_env()
    owns_docker = False
    if found is None:
        found = _start_local_binary(tmp_path_factory.mktemp("crdb"))
    if found is None:
        found = _start_docker()
        owns_docker = found is not None
    if found is None:
        pytest.skip(
            "no CockroachDB v26.2 reachable: set MAINLINE_TEST_DSN, or put `cockroach` "
            "on PATH, or start the Docker daemon so the suite can run "
            f"`docker run {CRDB_IMAGE} start-single-node --insecure`. "
            "Migration 0207 is NOT verified by a skipped run."
        )
    try:
        yield found
    finally:
        if found.process is not None:
            found.process.terminate()
        if owns_docker:
            _docker(["rm", "-f", CONTAINER_NAME], timeout=DOCKER_PROBE_TIMEOUT_S)


def _apply(conn, path: Path) -> int:
    statements = split_statements(path.read_text(encoding="utf-8"))
    if not statements:
        raise RuntimeError(f"{path.name} contains no SQL statement")
    for statement in statements:
        try:
            conn.execute(statement)
        except psycopg.Error as exc:
            raise RuntimeError(
                f"{path.name} failed to apply.\n"
                f"  sqlstate: {exc.sqlstate}\n"
                f"  error:    {exc}\n"
                f"  statement:\n{statement.strip()[:2000]}"
            ) from exc
    return len(statements)


@dataclass
class Schema:
    dsn: str
    database: str
    applied: list[str]
    spine_is_standin: bool

    def connect(self):
        return psycopg.connect(self.dsn, autocommit=True)


@pytest.fixture(scope="session")
def schema(cluster: Cluster) -> Iterator[Schema]:
    """Apply the spine (real migrations if they exist, stand-in otherwise) then 0207."""
    database = f"mainline_directrix_{uuid.uuid4().hex[:10]}"
    with psycopg.connect(cluster.dsn, autocommit=True) as admin:
        admin.execute(f"CREATE DATABASE {database}")

    from psycopg.conninfo import conninfo_to_dict, make_conninfo

    parts = conninfo_to_dict(cluster.dsn)
    parts["dbname"] = database
    dsn = make_conninfo(**parts)

    applied: list[str] = []
    statements = 0
    real_spine = spine_migrations()
    standin = not real_spine

    with psycopg.connect(dsn, autocommit=True) as conn:
        if standin:
            statements += _apply(conn, PREREQ_DIR / "00_spine_tables.sql")
            applied.append("prereq/00_spine_tables.sql")
        else:
            for path in real_spine:
                statements += _apply(conn, path)
                applied.append(path.name)
        owned = owned_migration_file()
        statements += _apply(conn, owned)
        applied.append(owned.name)

    print(
        f"\n[directrix] cluster:  {cluster.provenance}\n"
        f"[directrix] database: {database}\n"
        f"[directrix] spine:    {'STAND-IN (schema lead migrations not landed)' if standin else 'real migrations'}\n"
        f"[directrix] applied {len(applied)} files ({statements} statements) forward from clean"
    )
    try:
        yield Schema(dsn=dsn, database=database, applied=applied, spine_is_standin=standin)
    finally:
        with psycopg.connect(cluster.dsn, autocommit=True) as admin:
            admin.execute(f"DROP DATABASE IF EXISTS {database} CASCADE")


@pytest.fixture
def conn(schema: Schema):
    """One autocommit connection per test.

    Autocommit, not a rolled-back transaction: a refused statement must not be
    able to hide behind a rollback that also erases the rows written before it.
    """
    connection = schema.connect()
    try:
        yield connection
    finally:
        connection.close()


@pytest.fixture
def site_id(conn) -> uuid.UUID:
    """A fresh site per test, so the tests share a database and not a history."""
    return uuid.uuid4()
