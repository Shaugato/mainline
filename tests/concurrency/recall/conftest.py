# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
"""Cluster discovery for the late-recall lane.

The lane needs a real CockroachDB v26.2 because the property under test is a *database*
property: a composite foreign key with ``ON UPDATE RESTRICT`` refusing an ``UPDATE``. No
in-process double can stand in for that, and one that tried would be asserting its own
behaviour.

A cluster is found in this order and the lane **skips with a reason** rather than faking
anything if it cannot be:

1. ``MAINLINE_TEST_DSN`` / ``COCKROACH_URL`` / ``CRDB_URL`` — an already-running cluster;
2. a ``cockroach`` binary on ``PATH`` — an in-memory single node for the session;
3. a running Docker daemon — the image ``compose.yaml`` pins, for the session.

Nothing in this domain may be considered done on the basis of a skipped run, and the skip
message names which of the three is missing. The agent-side tests in the same file need none
of this and always run.
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
from trappoint_testkit import pinned_image

psycopg = pytest.importorskip(
    "psycopg",
    reason="psycopg 3 is required to talk to CockroachDB; `uv sync` installs it",
)

from _late_recall_ddl import SCHEMA_STATEMENTS  # noqa: E402  (after importorskip, deliberately)

CRDB_IMAGE = os.environ.get("MAINLINE_CRDB_IMAGE") or pinned_image(Path(__file__))
CONTAINER_NAME = "mainline-late-recall-test"
READY_TIMEOUT_S = 120.0
DOCKER_PROBE_TIMEOUT_S = 10.0
DOCKER_RUN_TIMEOUT_S = 600.0


@dataclass
class Cluster:
    dsn: str
    provenance: str


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


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
        cluster = Cluster(dsn=dsn, provenance=f"local `cockroach` binary on port {port}")
        cluster.__dict__["_proc"] = proc
        return cluster
    proc.terminate()
    return None


def _docker(args: list[str], *, timeout: float) -> subprocess.CompletedProcess[str] | None:
    """Run one docker command; ``None`` if it hangs, dies, or is not installed.

    `docker info` against a dead daemon does not fail — it BLOCKS. An uncaught
    `TimeoutExpired` would turn a situation that calls for a skip into a suite-wide error.
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
            f"PATH, or start the Docker daemon so the lane can run `docker run {CRDB_IMAGE} "
            "start-single-node --insecure`. THE EPOCH PIN IS NOT VERIFIED BY A SKIPPED RUN — "
            "the agent-side tests in this file still ran, and they assert the client contract "
            "only."
        )
    try:
        yield found
    finally:
        proc = found.__dict__.get("_proc")
        if proc is not None:
            proc.terminate()
        if owns_docker:
            _docker(["rm", "-f", CONTAINER_NAME], timeout=DOCKER_PROBE_TIMEOUT_S)


@dataclass
class EpochPinSchema:
    dsn: str
    database: str

    def connect(self, *, autocommit: bool = True):
        """One connection. ``autocommit=False`` is for the interleaving lane, which needs two.

        The interleaving lane also sets a ``statement_timeout``: two transactions contending
        for one ``permit`` row is the whole point of that test, and a writer that blocks
        forever behind an uncommitted lock would turn an assertion about refusal into a
        hung suite.
        """
        connection = psycopg.connect(self.dsn, autocommit=autocommit)
        if not autocommit:
            connection.execute("SET statement_timeout = '5s'")
        return connection


@pytest.fixture(scope="session")
def epoch_pin(cluster: Cluster) -> Iterator[EpochPinSchema]:
    """Apply the epoch-pin reduction into a fresh database, one statement at a time."""
    from psycopg.conninfo import conninfo_to_dict, make_conninfo

    database = f"mainline_late_recall_{uuid.uuid4().hex[:10]}"
    with psycopg.connect(cluster.dsn, autocommit=True) as admin:
        admin.execute(f"CREATE DATABASE {database}")

    parts = conninfo_to_dict(cluster.dsn)
    parts["dbname"] = database
    dsn = make_conninfo(**parts)

    with psycopg.connect(dsn, autocommit=True) as conn:
        for statement in SCHEMA_STATEMENTS:
            try:
                conn.execute(statement)
            except psycopg.Error as exc:
                raise RuntimeError(
                    "the epoch-pin reduction failed to apply.\n"
                    f"  sqlstate: {exc.sqlstate}\n  error: {exc}\n"
                    f"  statement:\n{statement}"
                ) from exc

    print(f"\n[late_recall] cluster: {cluster.provenance}\n[late_recall] database: {database}")
    try:
        yield EpochPinSchema(dsn=dsn, database=database)
    finally:
        with psycopg.connect(cluster.dsn, autocommit=True) as admin:
            admin.execute(f"DROP DATABASE IF EXISTS {database} CASCADE")


@pytest.fixture
def conn(epoch_pin: EpochPinSchema):
    """One autocommit connection per test.

    Autocommit rather than a rolled-back transaction: a refused statement must not be able to
    hide behind a rollback that also erases the rows the test wrote before it.
    """
    connection = epoch_pin.connect()
    try:
        yield connection
    finally:
        connection.close()
