# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""Cluster and schema fixtures for the ORIGINDIFF SQL suite.

The suite needs a real CockroachDB v26.2.  It finds one in this order and **skips
with a reason** rather than faking anything if it cannot:

1. ``MAINLINE_TEST_DSN`` (or ``COCKROACH_URL`` / ``CRDB_URL``) — a running cluster;
2. a ``cockroach`` binary on ``PATH`` — an in-memory single node for the session;
3. a running Docker daemon — ``cockroachdb/cockroach:latest-v26.2``.

AWS credentials are not valid on the build machine and CockroachDB Cloud is not
assumed; a local binary or a container is the intended path.  **Nothing in this
worker is done on the basis of a skipped run**, and the skip message says which of
the three was missing.

The two shape suites in this directory need neither a driver nor a cluster and run
everywhere.  That is why ``pytest.importorskip`` is not called at conftest scope —
it would skip the whole directory, and a missing driver must cost the
cluster-backed tests and nothing else.
"""

from __future__ import annotations

import importlib.util
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

_REPO_ROOT = Path(__file__).resolve().parents[4]
_SRC = _REPO_ROOT / "verticals" / "mainline" / "packages" / "mainline-domain" / "src"
if importlib.util.find_spec("mainline_domain") is None and _SRC.is_dir():
    sys.path.insert(0, str(_SRC))

from _diachronic_sql_support import (  # noqa: E402  (after the sys.path fix-up, deliberately)
    origin_stack,
    split_statements,
    stood_in_for,
)

try:  # soft, NOT `importorskip`
    import psycopg
except ImportError:  # pragma: no cover - depends on which extras are installed
    psycopg = None  # type: ignore[assignment]

PSYCOPG_MISSING_REASON = (
    "psycopg 3 is required to talk to CockroachDB; `uv sync --extra db` installs it"
)

CRDB_IMAGE = os.environ.get("MAINLINE_CRDB_IMAGE", "cockroachdb/cockroach:latest-v26.2")
CONTAINER_NAME = "mainline-origindiff-test"
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
        except Exception as exc:  # noqa: BLE001 - any failure means "not yet"
            last = exc
            time.sleep(1.0)
        else:
            return True
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
        return Cluster(dsn=dsn, provenance=f"local `cockroach` binary on port {port}", process=proc)
    proc.terminate()
    return None


def _docker(args: list[str], *, timeout: float) -> subprocess.CompletedProcess[str] | None:
    """Run a docker command; return ``None`` if it hangs, dies, or is not there.

    A dead Docker daemon does not make ``docker info`` fail — it makes it BLOCK,
    and an uncaught ``TimeoutExpired`` would turn every cluster-backed test into an
    ERROR instead of the skip the situation calls for.
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
            "no CockroachDB v26.2 reachable: set MAINLINE_TEST_DSN, or put `cockroach` on "
            f"PATH, or start the Docker daemon so the suite can run `docker run {CRDB_IMAGE} "
            "start-single-node --insecure`. ORIGINDIFF's view is NOT verified by a skipped run."
        )
    try:
        yield found
    finally:
        if found.process is not None:
            found.process.terminate()
        if owns_docker:
            _docker(["rm", "-f", CONTAINER_NAME], timeout=DOCKER_PROBE_TIMEOUT_S)


def _apply_sql(conn, label: str, sql: str) -> int:
    statements = split_statements(sql)
    if not statements:
        raise RuntimeError(f"{label} contains no SQL statement")
    for statement in statements:
        try:
            conn.execute(statement)
        except psycopg.Error as exc:
            raise RuntimeError(
                f"{label} failed to apply.\n"
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
    stood_in_for: tuple[str, ...]

    def connect(self, *, autocommit: bool = True):
        return psycopg.connect(self.dsn, autocommit=autocommit)


@pytest.fixture(scope="session")
def origin_schema(cluster: Cluster) -> Iterator[Schema]:
    """The real spine, a labelled stand-in for whatever dm-blame has not shipped, then 0049b/0152.

    The stand-in list is printed on every run.  A green run that quietly stood in
    for three tables is the failure mode this print exists to prevent.
    """
    stack, standins = origin_stack()
    database = f"mainline_origindiff_{uuid.uuid4().hex[:8]}"
    with psycopg.connect(cluster.dsn, autocommit=True) as admin:
        admin.execute(f"CREATE DATABASE {database}")

    from psycopg.conninfo import conninfo_to_dict, make_conninfo

    parts = conninfo_to_dict(cluster.dsn)
    parts["dbname"] = database
    dsn = make_conninfo(**parts)

    applied: list[str] = []
    statements = 0
    invented = stood_in_for()
    with psycopg.connect(dsn, autocommit=True) as conn:
        for path in stack:
            if path.name in {"0049b_commutation_edge.sql", "0152_v_blame_origin.sql"}:
                continue
            statements += _apply_sql(conn, path.name, path.read_text(encoding="utf-8"))
            applied.append(path.name)
        for index, ddl in enumerate(standins):
            statements += _apply_sql(conn, f"<stand-in {index}>", ddl)
            applied.append(f"<stand-in {index}>")
        for name in ("0049b_commutation_edge.sql", "0152_v_blame_origin.sql"):
            path = next(p for p in stack if p.name == name)
            statements += _apply_sql(conn, name, path.read_text(encoding="utf-8"))
            applied.append(name)

    banner = (
        f"STAND-IN IN USE for {', '.join(invented)} — datamodel/dm-blame has not "
        "shipped these objects. The view is exercised against a transcription of "
        "ARCHITECTURE.md §5.4, NOT against the reviewed migration."
        if invented
        else "no stand-in: every object this suite reads comes from a real migration"
    )
    print(
        f"\n[origindiff] cluster:  {cluster.provenance}\n"
        f"[origindiff] database: {database}\n"
        f"[origindiff] applied {len(applied)} units ({statements} statements): "
        f"{', '.join(applied)}\n"
        f"[origindiff] {banner}"
    )
    try:
        yield Schema(dsn=dsn, database=database, applied=applied, stood_in_for=invented)
    finally:
        with psycopg.connect(cluster.dsn, autocommit=True) as admin:
            admin.execute(f"DROP DATABASE IF EXISTS {database} CASCADE")


@pytest.fixture
def conn(origin_schema: Schema):
    """One autocommit connection per test.

    Autocommit, not a rolled-back transaction: a refused statement must not be able
    to hide behind a rollback that also erases the rows written before it.
    """
    connection = origin_schema.connect()
    try:
        yield connection
    finally:
        connection.close()


@pytest.fixture
def site_id() -> uuid.UUID:
    """A fresh site per test, so the tests share a database and not a history."""
    return uuid.uuid4()
