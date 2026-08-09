# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""Finding a CockroachDB v26.2 to run against, and refusing to fake one.

Every property this package tests is a *database* property — a CHECK over a projected
scalar, a composite foreign key with ``ON UPDATE RESTRICT``, a partial unique index. No
in-process double can stand in for any of them, and one that tried would be asserting its
own behaviour. So a lane with no cluster **skips with a reason that names what is
missing**, and nothing in this domain is considered done on a skipped run.

Discovery order, cheapest first:

1. ``TRAPPOINT_DSN`` / ``MAINLINE_TEST_DSN`` / ``COCKROACH_URL`` / ``CRDB_URL``;
2. a ``cockroach`` binary on ``PATH`` — an in-memory single node for the session;
3. a running Docker daemon — ``cockroachdb/cockroach:v26.2.5``, the exact Cloud version.

Lives in the package rather than in a ``conftest.py`` because two test roots need it —
``packages/trappoint-model/tests/`` and ``tests/concurrency/`` — and a second copy of
cluster discovery is a second place for the skip message to go stale.

**``gc.ttlseconds`` is set to the Cloud value on a node this module started.** The local
default is 14400 and Cloud Basic is 4500, so local is *more permissive than production*
and a time-travel test that passed locally would fail on Cloud. Where the two differ,
local is configured to the stricter value — by construction, not by remembering.
"""

from __future__ import annotations

import os
import shutil
import socket
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import psycopg

__all__ = [
    "CLOUD_GC_TTL_SECONDS",
    "CRDB_IMAGE",
    "SKIP_REASON",
    "Cluster",
    "find_cluster",
    "stop_cluster",
]

CRDB_IMAGE = os.environ.get("MAINLINE_CRDB_IMAGE", "cockroachdb/cockroach:v26.2.5")
_CONTAINER_PREFIX = "trappoint-model"
_READY_TIMEOUT_S = 120.0
_DOCKER_PROBE_TIMEOUT_S = 10.0
_DOCKER_RUN_TIMEOUT_S = 600.0

#: Cloud Basic's value. Local defaults to 14400, which is more permissive than production.
CLOUD_GC_TTL_SECONDS = 4500

SKIP_REASON = (
    "no CockroachDB v26.2 reachable: set TRAPPOINT_DSN, or put `cockroach` on PATH, or "
    f"start the Docker daemon so the lane can run `docker run {CRDB_IMAGE} "
    "start-single-node --insecure`. A SKIPPED RUN IS NOT EVIDENCE: the gate is a database "
    "mechanism and nothing in this package can stand in for it."
)


@dataclass
class Cluster:
    """A reachable CockroachDB, how it was found, and how to stop it."""

    dsn: str
    provenance: str
    process: subprocess.Popen[bytes] | None = field(default=None, repr=False)
    container: str | None = None

    @property
    def owned(self) -> bool:
        """Did this module start it? Only an owned node may be reconfigured or stopped."""
        return self.process is not None or self.container is not None


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _ready(dsn: str, deadline: float) -> bool:
    last: Exception | None = None
    while time.monotonic() < deadline:
        try:
            with psycopg.connect(dsn, connect_timeout=3) as conn:
                conn.execute("SELECT 1")
        except Exception as exc:  # noqa: BLE001 - anything at all means "not yet"
            last = exc
            time.sleep(1.0)
        else:
            return True
    if last is not None:
        # T201: pytest captures stdout and shows it on failure. A cluster that never
        # came up is exactly the diagnosis a reader needs beside the skip.
        print(f"cluster never became ready: {last}")  # noqa: T201
    return False


def _from_env() -> Cluster | None:
    for name in ("TRAPPOINT_DSN", "MAINLINE_TEST_DSN", "COCKROACH_URL", "CRDB_URL"):
        value = os.environ.get(name)
        if value:
            return Cluster(dsn=value, provenance=f"${name}")
    return None


def _from_binary(workdir: Path) -> Cluster | None:
    binary = shutil.which("cockroach")
    if binary is None:
        return None
    port, http = _free_port(), _free_port()
    # S603/S607: a fixed argv, and the binary is the one `shutil.which` just resolved.
    # Nothing here comes from a payload, a test parameter or an environment string.
    proc = subprocess.Popen(  # noqa: S603
        [
            binary,
            "start-single-node",
            "--insecure",
            "--store=type=mem,size=2GiB",
            f"--listen-addr=127.0.0.1:{port}",
            f"--http-addr=127.0.0.1:{http}",
        ],
        cwd=str(workdir),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    dsn = f"postgresql://root@127.0.0.1:{port}/defaultdb?sslmode=disable"
    if _ready(dsn, time.monotonic() + _READY_TIMEOUT_S):
        return Cluster(dsn=dsn, provenance=f"local `cockroach` binary on {port}", process=proc)
    proc.terminate()
    return None


def _docker(args: list[str], *, timeout: float) -> subprocess.CompletedProcess[str] | None:
    """One docker command. ``None`` when docker hangs, dies, or is not installed.

    ``docker info`` against a dead daemon does not fail — it BLOCKS — and an uncaught
    ``TimeoutExpired`` would turn a situation that calls for a skip into a suite error.
    """
    try:
        # S603/S607: `docker` is resolved on PATH deliberately — a hard-coded absolute
        # path is wrong on macOS, Linux and every CI image at once. The arguments are
        # built in this module and never from input.
        return subprocess.run(  # noqa: S603
            ["docker", *args],  # noqa: S607
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except (subprocess.TimeoutExpired, OSError):
        return None


def _from_docker(label: str) -> Cluster | None:
    if shutil.which("docker") is None:
        return None
    probe = _docker(["info", "--format", "{{.ServerVersion}}"], timeout=_DOCKER_PROBE_TIMEOUT_S)
    if probe is None or probe.returncode != 0:
        return None
    name = f"{_CONTAINER_PREFIX}-{label}"
    _docker(["rm", "-f", name], timeout=_DOCKER_PROBE_TIMEOUT_S)
    port = _free_port()
    started = _docker(
        [
            "run",
            "-d",
            "--name",
            name,
            "-p",
            f"{port}:26257",
            CRDB_IMAGE,
            "start-single-node",
            "--insecure",
            "--store=type=mem,size=2GiB",
        ],
        timeout=_DOCKER_RUN_TIMEOUT_S,
    )
    if started is None or started.returncode != 0:
        detail = "hung" if started is None else started.stderr.strip()
        print(f"`docker run {CRDB_IMAGE}` failed: {detail}")  # noqa: T201
        return None
    dsn = f"postgresql://root@127.0.0.1:{port}/defaultdb?sslmode=disable"
    if _ready(dsn, time.monotonic() + _READY_TIMEOUT_S):
        return Cluster(dsn=dsn, provenance=f"docker {CRDB_IMAGE} on {port}", container=name)
    _docker(["rm", "-f", name], timeout=_DOCKER_PROBE_TIMEOUT_S)
    return None


def find_cluster(workdir: Path, label: str = "lane") -> Cluster | None:
    """Return a reachable cluster, or ``None`` so the caller can skip with :data:`SKIP_REASON`.

    Args:
        workdir: a scratch directory for a locally-started node's files.
        label: distinguishes containers when two lanes each start one.
    """
    found = _from_env() or _from_binary(workdir) or _from_docker(label)
    if found is not None and found.owned:
        with psycopg.connect(found.dsn, autocommit=True) as conn:
            conn.execute(
                f"ALTER RANGE default CONFIGURE ZONE USING gc.ttlseconds = {CLOUD_GC_TTL_SECONDS}"
            )
    return found


def stop_cluster(cluster: Cluster | None) -> None:
    """Stop a cluster this module started. A cluster found in the environment is left alone."""
    if cluster is None:
        return
    if cluster.process is not None:
        cluster.process.terminate()
    if cluster.container is not None:
        _docker(["rm", "-f", cluster.container], timeout=_DOCKER_PROBE_TIMEOUT_S)


def connect(dsn: str, *, isolation: str = "serializable") -> psycopg.Connection[Any]:
    """One autocommit connection with the isolation level stated explicitly.

    Never inherited from a pool default: ``spec/errors.md`` §2.1 requires the level to be
    set on every attempt, and a differential whose isolation level is implicit is a
    differential that cannot say what it tested.
    """
    conn = psycopg.connect(dsn, autocommit=True)
    conn.execute(f"SET default_transaction_isolation = '{isolation}'")
    return conn
