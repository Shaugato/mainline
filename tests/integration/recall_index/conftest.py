# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""Fixtures for the index-truth suite.

Two of this suite's five modules need **no cluster at all** — the arm-shape assertions and the
plan-parser assertions run anywhere Python runs, and they are the ones that prove the
assertion machinery has teeth before any cluster is involved. The remaining three need a real
CockroachDB v26.2 and **SKIP WITH A REASON** if there is not one, in this order:

1. ``MAINLINE_TEST_DSN`` (or ``COCKROACH_URL`` / ``CRDB_URL``) — an already-running cluster;
2. a ``cockroach`` binary on ``PATH`` — an in-memory single node for the session;
3. a running Docker daemon — ``cockroachdb/cockroach:latest-v26.2`` for the session.

**Nothing in this domain may be considered proven by a skipped run.** The skip message says
which of the three is missing, and the suite's README says what a green-with-skips run does
and does not entitle anybody to claim.
"""

from __future__ import annotations

import os
import shutil
import socket
import subprocess
import time
import uuid
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

import pytest

psycopg = pytest.importorskip(
    "psycopg",
    reason="psycopg 3 is required to talk to CockroachDB; `uv sync` installs it",
)

from _support import (  # noqa: E402  (import after importorskip, deliberately)
    PREREQ_CONSUMED,
    CorpusState,
    create_taxonomy,
    recall_migration_files,
    split_statements,
)

CRDB_IMAGE = os.environ.get("MAINLINE_CRDB_IMAGE", "cockroachdb/cockroach:latest-v26.2")
CONTAINER_NAME = "mainline-recall-index-test"
READY_TIMEOUT_S = 120.0
DOCKER_PROBE_TIMEOUT_S = 10.0
DOCKER_RUN_TIMEOUT_S = 600.0


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line("markers", "shape: static assertions; needs no cluster")
    config.addinivalue_line("markers", "plan: layer 1 — EXPLAIN skeleton over pgwire")
    config.addinivalue_line("markers", "mcp: layer 1 — the same claim over the public endpoint")
    config.addinivalue_line("markers", "behaviour: layer 2 — sublinearity and planted recall")
    config.addinivalue_line("markers", "nightly: layer 3 — characterisation; expected to drift")
    config.addinivalue_line("markers", "slow: builds a corpus; minutes, not seconds")


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
    proc = subprocess.Popen(  # noqa: S603 - fixed argv, no shell
        [
            binary,
            "start-single-node",
            "--insecure",
            "--store=type=mem,size=4GiB",
            f"--listen-addr=127.0.0.1:{port}",
            f"--http-addr=127.0.0.1:{http_port}",
        ],
        cwd=str(tmp),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    dsn = f"postgresql://root@127.0.0.1:{port}/defaultdb?sslmode=disable"
    if _wait_until_ready(dsn, time.monotonic() + READY_TIMEOUT_S):
        cluster = Cluster(dsn=dsn, provenance=f"local `cockroach` binary on port {port}")
        cluster.__dict__["_proc"] = proc
        return cluster
    proc.terminate()
    return None


def _docker(args: list[str], *, timeout: float) -> subprocess.CompletedProcess[str] | None:
    """Never let a hung Docker probe become a test ERROR — the answer to a hang is "no"."""
    try:
        return subprocess.run(  # noqa: S603, S607
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
            "--store=type=mem,size=4GiB",
        ],
        timeout=DOCKER_RUN_TIMEOUT_S,
    )
    if started is None:
        print(f"`docker run {CRDB_IMAGE}` hung or could not be executed")
        return None
    if started.returncode != 0:
        print(f"docker run failed: {started.stderr.strip()}")
        return None
    dsn = f"postgresql://root@127.0.0.1:{port}/defaultdb?sslmode=disable"
    if _wait_until_ready(dsn, time.monotonic() + READY_TIMEOUT_S):
        return Cluster(dsn=dsn, provenance=f"docker {CRDB_IMAGE} on port {port}")
    _docker(["rm", "-f", CONTAINER_NAME], timeout=DOCKER_PROBE_TIMEOUT_S)
    return None


@pytest.fixture(scope="session")
def cluster(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Cluster]:
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
            "PATH, or start the Docker daemon so the suite can run "
            f"`docker run {CRDB_IMAGE} start-single-node --insecure`. The claim that the "
            "vector index is used is NOT proven by a skipped run."
        )
    try:
        yield found
    finally:
        proc = found.__dict__.get("_proc")
        if proc is not None:
            proc.terminate()
        if owns_docker:
            subprocess.run(  # noqa: S603, S607
                ["docker", "rm", "-f", CONTAINER_NAME], capture_output=True, check=False
            )


def _apply(conn: object, path: Path) -> None:
    statements = split_statements(path.read_text(encoding="utf-8"))
    if not statements:
        raise RuntimeError(f"{path.name} contains no SQL statement")
    for statement in statements:
        try:
            conn.execute(statement)  # type: ignore[attr-defined]
        except psycopg.Error as exc:
            raise RuntimeError(
                f"{path.name} failed to apply.\n  sqlstate: {exc.sqlstate}\n  error: {exc}\n"
                f"  statement:\n{statement.strip()[:1500]}"
            ) from exc


_UNKNOWN_SETTING = frozenset({"42704", "22023", "42601"})


def _enable_vector_indexes(admin: object) -> str:
    try:
        admin.execute("SET CLUSTER SETTING feature.vector_index.enabled = true")  # type: ignore[attr-defined]
    except psycopg.Error as exc:
        state = exc.sqlstate or ""
        if state in _UNKNOWN_SETTING:
            return f"feature.vector_index.enabled is not a setting on this cluster ({state})"
        return f"could not set feature.vector_index.enabled: {state} {exc}"
    return "feature.vector_index.enabled = true"


@dataclass
class Schema:
    dsn: str
    database: str
    applied: tuple[str, ...]
    vector_setting: str

    def connect(self) -> object:
        return psycopg.connect(self.dsn, autocommit=True)


@pytest.fixture(scope="session")
def schema(cluster: Cluster) -> Iterator[Schema]:
    """Apply the reserved recall band forward from clean into a throwaway database."""
    if not PREREQ_CONSUMED.is_file():
        pytest.skip(
            f"the consumed-table fixture is missing: {PREREQ_CONSUMED}. It is owned by "
            "`recall-ddl-triggers`; this suite reads it rather than keeping a second copy "
            "that could drift from the real shapes."
        )
    database = f"mainline_recall_index_{uuid.uuid4().hex[:10]}"
    with psycopg.connect(cluster.dsn, autocommit=True) as admin:
        vector_setting = _enable_vector_indexes(admin)
        admin.execute(f"CREATE DATABASE {database}")

    from psycopg.conninfo import conninfo_to_dict, make_conninfo

    parts = conninfo_to_dict(cluster.dsn)
    parts["dbname"] = database
    dsn = make_conninfo(**parts)

    applied: list[str] = []
    with psycopg.connect(dsn, autocommit=True) as conn:
        _apply(conn, PREREQ_CONSUMED)
        applied.append(PREREQ_CONSUMED.name)
        for path in recall_migration_files():
            _apply(conn, path)
            applied.append(path.name)

    print(
        f"\n[recall_index] cluster:  {cluster.provenance}\n"
        f"[recall_index] vectors:  {vector_setting}\n"
        f"[recall_index] database: {database}\n"
        f"[recall_index] applied {len(applied)} files forward from clean"
    )
    try:
        yield Schema(
            dsn=dsn, database=database, applied=tuple(applied), vector_setting=vector_setting
        )
    finally:
        with psycopg.connect(cluster.dsn, autocommit=True) as admin:
            admin.execute(f"DROP DATABASE IF EXISTS {database} CASCADE")


@pytest.fixture()
def conn(schema: Schema) -> Iterator[object]:
    connection = schema.connect()
    try:
        yield connection
    finally:
        connection.close()  # type: ignore[attr-defined]


@pytest.fixture(scope="session")
def session_conn(schema: Schema) -> Iterator[object]:
    """One long-lived connection for the corpus-building lanes, so 20 000 inserts share it."""
    connection = schema.connect()
    try:
        yield connection
    finally:
        connection.close()  # type: ignore[attr-defined]


@pytest.fixture(scope="session")
def corpus(session_conn: object) -> CorpusState:
    """One site, one three-level ancestor chain, and a corpus that grows across the lane."""
    return CorpusState(taxonomy=create_taxonomy(session_conn))
