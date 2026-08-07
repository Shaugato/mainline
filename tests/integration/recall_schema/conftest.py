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
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

import pytest

psycopg = pytest.importorskip(
    "psycopg",
    reason="psycopg 3 is required to talk to CockroachDB; `uv sync` installs it",
)

from _support import (  # noqa: E402  (import after importorskip, deliberately)
    PREREQ_DIR,
    recall_migration_files,
    split_statements,
    trigger_names,
)

CRDB_IMAGE = os.environ.get("MAINLINE_CRDB_IMAGE", "cockroachdb/cockroach:latest-v26.2")
CONTAINER_NAME = "mainline-recall-schema-test"
READY_TIMEOUT_S = 120.0
#: A dead Docker daemon does not refuse `docker info`; it blocks. Short, because the only
#: information wanted from it is "is there a daemon", and the answer to a hang is "no".
DOCKER_PROBE_TIMEOUT_S = 10.0
#: Long enough to include an image pull on a cold machine.
DOCKER_RUN_TIMEOUT_S = 600.0


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line("markers", "schema: exercises DDL against a real cluster")
    config.addinivalue_line("markers", "unweld: drops a mechanism and re-asserts the refusal")
    config.addinivalue_line("markers", "shape: static checks over the band; needs no cluster")


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
    probe = _docker(["info", "--format", "{{.ServerVersion}}"], timeout=DOCKER_PROBE_TIMEOUT_S)
    return probe is not None and probe.returncode == 0


def _docker(args: list[str], *, timeout: float) -> subprocess.CompletedProcess[str] | None:
    """Run a docker command; return None if it hangs, dies, or is not there.

    A hung probe must never become a test ERROR. The Docker CLI ships with Docker Desktop and
    stays on PATH after the daemon stops, and `docker info` against a dead daemon does not fail —
    it BLOCKS. `subprocess.run(timeout=…)` then raises `TimeoutExpired`, which `check=False` does
    not cover, so the uncaught exception took down every cluster-backed test in this suite with
    an error instead of the skip the situation actually calls for. That is the machine this band
    was written on, so it is not a hypothetical: a discoverable-by-running-it defect in the one
    code path whose whole job is to fail gracefully.
    """
    try:
        return subprocess.run(  # noqa: S603, S607
            ["docker", *args],
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except (subprocess.TimeoutExpired, OSError):
        return None


def _start_docker() -> Cluster | None:
    if not _docker_available():
        return None
    _docker(["rm", "-f", CONTAINER_NAME], timeout=DOCKER_PROBE_TIMEOUT_S)
    port = _free_port()
    started = _docker(
        [
            "run", "-d", "--name", CONTAINER_NAME,
            "-p", f"{port}:26257",
            CRDB_IMAGE,
            "start-single-node", "--insecure", "--store=type=mem,size=2GiB",
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


def _apply(conn, path: Path) -> int:
    """Apply a migration file ONE STATEMENT AT A TIME, and say how many there were.

    Not whole-file: on an autocommit connection a multi-statement send is one implicit
    transaction, and a DDL transaction is not the same thing as a sequence of schema changes on
    CockroachDB. `_support.split_statements` is dollar-quote aware so a `$$` body is never cut in
    half; `test_rc00_migration_shape.py` proves that on every file in the band, with no cluster.
    """
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


#: SQLSTATEs that mean "this cluster does not have that cluster setting", as opposed to
#: "this cluster refused to change it". v26.2 may have retired `feature.vector_index.enabled`
#: on the way to GA, and a suite that SKIPS on an unknown setting would report a green-by-absence
#: result on exactly the cluster the band is meant to run on.
_UNKNOWN_SETTING = frozenset({"42704", "22023", "42601"})


def _enable_vector_indexes(admin) -> str:
    """Best-effort. Report what happened; never decide the suite's fate from this alone."""
    try:
        admin.execute("SET CLUSTER SETTING feature.vector_index.enabled = true")
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
        vector_setting = _enable_vector_indexes(admin)
        admin.execute(f"CREATE DATABASE {database}")

    # Re-point at the fresh database without string surgery on the URL: an env-supplied DSN may
    # carry options (`--cluster=`), a sslrootcert path, or no path component at all.
    from psycopg.conninfo import conninfo_to_dict, make_conninfo

    parts = conninfo_to_dict(cluster.dsn)
    parts["dbname"] = database
    dsn = make_conninfo(**parts)

    applied: list[str] = []
    n_statements = 0
    with psycopg.connect(dsn, autocommit=True) as conn:
        n_statements += _apply(conn, PREREQ_DIR / "00_consumed_tables.sql")
        applied.append("prereq/00_consumed_tables.sql")
        for path in recall_migration_files():
            n_statements += _apply(conn, path)
            applied.append(path.name)

        standin = not trigger_names(conn, "mainline_meas", "silence_ledger")
        if standin:
            n_statements += _apply(conn, PREREQ_DIR / "90_append_only_standin.sql")
            applied.append("prereq/90_append_only_standin.sql")

    print(
        f"\n[recall_schema] cluster:  {cluster.provenance}\n"
        f"[recall_schema] vectors:  {vector_setting}\n"
        f"[recall_schema] database: {database}\n"
        f"[recall_schema] applied {len(applied)} files "
        f"({n_statements} statements) forward from clean"
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
