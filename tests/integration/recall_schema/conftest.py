# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""Cluster and schema fixtures for the recall-schema illegal-history suite.

The suite needs a real CockroachDB v26.2. It finds one in this order and SKIPS WITH A REASON
rather than faking anything if it cannot:

1. ``MAINLINE_TEST_DSN`` (or ``COCKROACH_URL``) — an already-running cluster;
2. a ``cockroach`` binary on ``PATH`` — an in-memory single node is started for the session;
3. a running Docker daemon — ``cockroachdb/cockroach:latest-v26.2`` is started for the session.

Nothing in this domain may be considered done on the basis of a skipped run, and the skip
message says which of the three is missing.
"""

from __future__ import annotations

import os
import shutil
import socket
import subprocess
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

import pytest

psycopg = pytest.importorskip(
    "psycopg",
    reason="psycopg 3 is required to talk to CockroachDB; `uv sync` installs it",
)

from _support import (  # noqa: E402  (import after importorskip, deliberately)
    PREREQ_DIR,
    recall_migration_files,
    trigger_names,
)

CRDB_IMAGE = os.environ.get("MAINLINE_CRDB_IMAGE", "cockroachdb/cockroach:latest-v26.2")
CONTAINER_NAME = "mainline-recall-schema-test"
READY_TIMEOUT_S = 120.0


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line("markers", "schema: exercises DDL against a real cluster")
    config.addinivalue_line("markers", "unweld: drops a mechanism and re-asserts the refusal")


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
        cluster = Cluster(dsn=dsn, provenance=f"local `cockroach` binary on port {port}")
        cluster.__dict__["_proc"] = proc
        return cluster
    proc.terminate()
    return None


def _docker_available() -> bool:
    if shutil.which("docker") is None:
        return False
    probe = subprocess.run(  # noqa: S603, S607
        ["docker", "info", "--format", "{{.ServerVersion}}"],
        capture_output=True,
        timeout=30,
        check=False,
    )
    return probe.returncode == 0


def _start_docker() -> Cluster | None:
    if not _docker_available():
        return None
    subprocess.run(  # noqa: S603, S607
        ["docker", "rm", "-f", CONTAINER_NAME], capture_output=True, check=False
    )
    port = _free_port()
    started = subprocess.run(  # noqa: S603, S607
        [
            "docker", "run", "-d", "--name", CONTAINER_NAME,
            "-p", f"{port}:26257",
            CRDB_IMAGE,
            "start-single-node", "--insecure", "--store=type=mem,size=2GiB",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if started.returncode != 0:
        print(f"docker run failed: {started.stderr.strip()}")
        return None
    dsn = f"postgresql://root@127.0.0.1:{port}/defaultdb?sslmode=disable"
    if _wait_until_ready(dsn, time.monotonic() + READY_TIMEOUT_S):
        return Cluster(dsn=dsn, provenance=f"docker {CRDB_IMAGE} on port {port}")
    subprocess.run(  # noqa: S603, S607
        ["docker", "rm", "-f", CONTAINER_NAME], capture_output=True, check=False
    )
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
            f"`docker run {CRDB_IMAGE} start-single-node --insecure`. "
            "The recall band is NOT verified by a skipped run."
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


def _apply(conn, path: Path) -> None:
    """Send a migration file as one query.

    Whole-file execution is deliberate: a client-side statement splitter would have to parse
    ``$$`` bodies, and a splitter that gets that wrong applies half a trigger.
    """
    conn.execute(path.read_text(encoding="utf-8"))


@dataclass
class Schema:
    dsn: str
    database: str
    applied: list[str]
    append_only_is_standin: bool

    def connect(self):
        conn = psycopg.connect(self.dsn, autocommit=True)
        return conn


@pytest.fixture(scope="session")
def schema(cluster: Cluster) -> Iterator[Schema]:
    """Apply the whole reserved recall band forward from clean, in one run."""
    database = f"mainline_recall_{uuid.uuid4().hex[:10]}"
    with psycopg.connect(cluster.dsn, autocommit=True) as admin:
        try:
            admin.execute("SET CLUSTER SETTING feature.vector_index.enabled = true")
        except psycopg.Error as exc:
            pytest.skip(
                "cannot enable vector indexes on this cluster "
                f"(feature.vector_index.enabled): {exc}. Migrations 0041/0042 declare inline "
                "VECTOR INDEXes and cannot be applied without it."
            )
        admin.execute(f"CREATE DATABASE {database}")

    # Re-point at the fresh database without string surgery on the URL: an env-supplied DSN may
    # carry options (`--cluster=`), a sslrootcert path, or no path component at all.
    from psycopg.conninfo import conninfo_to_dict, make_conninfo

    parts = conninfo_to_dict(cluster.dsn)
    parts["dbname"] = database
    dsn = make_conninfo(**parts)

    applied: list[str] = []
    with psycopg.connect(dsn, autocommit=True) as conn:
        _apply(conn, PREREQ_DIR / "00_consumed_tables.sql")
        applied.append("prereq/00_consumed_tables.sql")
        for path in recall_migration_files():
            _apply(conn, path)
            applied.append(path.name)

        standin = not trigger_names(conn, "mainline_meas", "silence_ledger")
        if standin:
            _apply(conn, PREREQ_DIR / "90_append_only_standin.sql")
            applied.append("prereq/90_append_only_standin.sql")

    print(
        f"\n[recall_schema] cluster: {cluster.provenance}\n"
        f"[recall_schema] database: {database}\n"
        f"[recall_schema] applied {len(applied)} files forward from clean"
    )
    try:
        yield Schema(
            dsn=dsn,
            database=database,
            applied=applied,
            append_only_is_standin=standin,
        )
    finally:
        with psycopg.connect(cluster.dsn, autocommit=True) as admin:
            admin.execute(f"DROP DATABASE IF EXISTS {database} CASCADE")


@pytest.fixture()
def conn(schema: Schema):
    """One autocommit connection per test.

    Autocommit, not a rolled-back transaction: a refused statement must not be able to hide
    behind a rollback that also erases the rows the test wrote before it.
    """
    connection = schema.connect()
    try:
        yield connection
    finally:
        connection.close()
