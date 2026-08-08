# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""Fixtures for the candidate-cascade integration suite.

**Half of this suite needs no cluster.**  The corpus-doubling measurement is a
count of rescored pairs, not a wall-clock number, so it runs anywhere Python
runs and it runs in CI today.  That matters: no AWS credential is valid on the
build machine and no CockroachDB Cloud cluster is reachable, and nothing in this
domain may be considered done because a live dependency happened to be up.

The other half needs a real CockroachDB v26.2 and **skips with a reason** when
there is not one, looking in this order:

1. ``MAINLINE_TEST_DSN`` (or ``COCKROACH_URL`` / ``CRDB_URL``) — a cluster that
   is already running;
2. a ``cockroach`` binary on ``PATH`` — a single in-memory node for the session.

Docker is deliberately **not** orchestrated here.  The recall lead's index-truth
suite already does that, well, in ~150 lines; a second copy would be a second
thing to keep working.  If neither of the two sources above is available the
skip message says exactly which, and the suite README says what a
green-with-skips run does and does not entitle anyone to claim: it entitles them
to say the statements have the right shape and the cascade has the right cost
curve.  It does not entitle them to say the plan was verified.
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
from pathlib import Path
from typing import Any

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[4]
_SRC = _REPO_ROOT / "verticals" / "mainline" / "packages" / "mainline-domain" / "src"
if str(_SRC) not in sys.path and _SRC.is_dir():
    sys.path.insert(0, str(_SRC))
# This directory goes on `sys.path` so `_w7_support` imports under pytest's
# prepend import mode.  The helper module is named `_w7_support`, not `_support`,
# ON PURPOSE: several integration suites in this repository keep a private helper
# beside their tests, none of these directories is a package, and two files with
# the same basename on `sys.path` resolve to whichever suite pytest imported
# first.  That is a collision that shows up as one worker's conftest importing
# another worker's constants, in an order that depends on collection sequence.
# A unique basename costs nothing and removes this suite from that hazard
# entirely.
if str(Path(__file__).resolve().parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent))

DSN_ENV_VARS = ("MAINLINE_TEST_DSN", "COCKROACH_URL", "CRDB_URL")
READY_TIMEOUT_S = 90.0


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _psycopg() -> Any:
    return pytest.importorskip(
        "psycopg",
        reason="psycopg 3 is required to talk to CockroachDB; `uv sync --extra db` installs it",
    )


def _reachable(dsn: str) -> bool:
    psycopg = _psycopg()
    try:
        with psycopg.connect(dsn, connect_timeout=5) as conn, conn.cursor() as cur:
            cur.execute("SELECT 1")
            return True
    except Exception:  # noqa: BLE001 - probing: any failure means "not reachable"
        return False


@pytest.fixture(scope="session")
def cluster_dsn() -> Iterator[str]:
    """A DSN for a live CockroachDB, or a skip that says what was missing."""
    for name in DSN_ENV_VARS:
        dsn = os.environ.get(name)
        if dsn:
            if _reachable(dsn):
                yield dsn
                return
            pytest.skip(f"{name} is set to {dsn!r} but the cluster did not answer SELECT 1")

    binary = shutil.which("cockroach")
    if binary is None:
        pytest.skip(
            "no live CockroachDB: none of "
            + ", ".join(DSN_ENV_VARS)
            + " is set and no `cockroach` binary is on PATH. The offline half of this "
            "suite still ran; the plan and SQL-equivalence claims are UNVERIFIED."
        )

    port = _free_port()
    http_port = _free_port()
    store = "type=mem,size=1GiB"
    proc = subprocess.Popen(
        [
            binary,
            "start-single-node",
            "--insecure",
            f"--listen-addr=127.0.0.1:{port}",
            f"--http-addr=127.0.0.1:{http_port}",
            f"--store={store}",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    dsn = f"postgresql://root@127.0.0.1:{port}/defaultdb?sslmode=disable"
    deadline = time.monotonic() + READY_TIMEOUT_S
    try:
        while time.monotonic() < deadline:
            if proc.poll() is not None:
                pytest.skip(f"`cockroach start-single-node` exited with {proc.returncode}")
            if _reachable(dsn):
                break
            time.sleep(0.5)
        else:
            pytest.skip(
                f"`cockroach start-single-node` did not become ready within {READY_TIMEOUT_S:.0f}s"
            )
        yield dsn
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=30)
        except subprocess.TimeoutExpired:  # pragma: no cover - shutdown race
            proc.kill()


@pytest.fixture
def cluster_conn(cluster_dsn: str) -> Iterator[Any]:
    """A connection to a throwaway database holding a ``mainline`` schema.

    A fresh database per test, dropped afterwards.  Nothing here ever writes to
    a real ``mainline`` schema on a shared cluster: the identifiers in the
    package's statements are production-shaped, and the only way to run them
    unchanged *and* stay out of the way is to give them their own database.
    """
    psycopg = _psycopg()
    from _w7_support import (
        CREATE_CLAUSE_BAND,
        CREATE_CLAUSE_EMBEDDING,
        CREATE_CLAUSE_VERSION,
        CREATE_SCHEMA,
    )

    name = f"mainline_w7_{uuid.uuid4().hex[:12]}"
    with psycopg.connect(cluster_dsn, autocommit=True) as admin, admin.cursor() as cur:
        cur.execute(f"CREATE DATABASE {name}")

    scoped = cluster_dsn.split("?", maxsplit=1)[0].rsplit("/", 1)[0] + f"/{name}"
    if "?" in cluster_dsn:
        scoped += "?" + cluster_dsn.split("?", 1)[1]

    try:
        with psycopg.connect(scoped, autocommit=True) as conn:
            with conn.cursor() as cur:
                cur.execute(CREATE_SCHEMA)
                cur.execute(CREATE_CLAUSE_BAND)
                cur.execute(CREATE_CLAUSE_VERSION)
                cur.execute(CREATE_CLAUSE_EMBEDDING)
            yield conn
    finally:
        with psycopg.connect(cluster_dsn, autocommit=True) as admin, admin.cursor() as cur:
            cur.execute(f"DROP DATABASE IF EXISTS {name} CASCADE")
