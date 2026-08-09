# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""A cluster this suite is allowed to break.

The unwelding suite **mutates schema**. It must never run against the cluster the
conformance suite parallelises over, and it must never run against the named Compose volume
— ``compose.yaml`` says so in a comment for the same reason this module exists.

Two ways to get a cluster, in order:

``TRAPPOINT_UNWELD_DSN``
    CI supplies one: ``schema.yml`` starts a throwaway single-node container per job and
    destroys it after. The environment variable is the contract, and it is checked against
    the *forbidden* DSNs so a copy-pasted local DSN cannot quietly point the mutation suite
    at the developer's data volume.

a disposable container this module starts
    Locally, an in-memory single-node CockroachDB on its own port, created here and removed
    in the same ``finally``. In-memory because it must not survive a crash: a container that
    outlived a failed run and was later reused would be a cluster with one mechanism
    missing and no record of which.

If neither is available the fixture **skips with a printed reason**. It does not fall back
to the ordinary DSN. There is no configuration in which "I could not get a disposable
cluster" is answered by "then use the real one".
"""

from __future__ import annotations

import os
import shutil
import subprocess
import time
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

__all__ = [
    "CRDB_IMAGE",
    "REF_TREE",
    "apply_tree",
    "disposable_cluster",
    "is_forbidden_dsn",
]

# Kept in step with compose.yaml's `trappoint:crdb-image-pin` line. A version skew between
# the mutation suite and the cluster the conformance suite runs on would make the matrix a
# measurement of a database nobody ships.
CRDB_IMAGE = "cockroachdb/cockroach:v26.2.5"

REF_TREE = Path("packages/trappoint-sql/refvertical/sql")
MAINLINE_TREE = Path("verticals/mainline/db/migrations")

# The two clusters the mutation suite must never touch: the developer's Compose volume and
# anything on the default local port.
_FORBIDDEN_PORTS = ("26257",)
_FORBIDDEN_HOSTS = ("trappoint-crdb", "mainline-crdb")


def is_forbidden_dsn(dsn: str) -> bool:
    """Whether *dsn* points at a cluster this suite may not break."""
    lowered = dsn.lower()
    if any(f":{port}" in lowered for port in _FORBIDDEN_PORTS):
        return True
    return any(host in lowered for host in _FORBIDDEN_HOSTS)


def apply_tree(dsn: str, tree: Path) -> tuple[int, list[tuple[str, str]]]:
    """Apply a migration tree file by file, in lexicographic order.

    Returns ``(applied, failures)``.

    **This is not the authoritative applier and does not claim to be.** ``trappoint migrate
    up`` owns the migration stream, the lock table, the dirty marker and the attestation
    chain. What is needed here is narrower and must hold no dependency on the migrator's
    package: put a schema on a container that is about to be destroyed. Ordering is
    lexicographic on the full filename, which is exactly what MR-5's naming convention was
    designed to make sufficient (``0006a < 0006b < 0007``).

    Failures are **returned rather than raised**, because a tree that does not fully apply
    is a finding about the tree — see the fixture, which reports it as a skip naming the
    missing relations rather than as a mysterious error inside a mutation.
    """
    import psycopg

    applied = 0
    failures: list[tuple[str, str]] = []
    with psycopg.connect(dsn, autocommit=True) as conn:
        for path in sorted(p for p in tree.iterdir() if p.suffix == ".sql"):
            try:
                conn.execute(path.read_text(encoding="utf-8"))  # type: ignore[arg-type]
                applied += 1
            except psycopg.Error as exc:
                state = exc.diag.sqlstate if exc.diag is not None else "?"
                message = " ".join(str(exc).split())[:160]
                failures.append((path.name, f"{state} {message}"))
    return applied, failures


@contextmanager
def disposable_cluster() -> Iterator[str]:
    """Yield a DSN for a cluster this suite may break, or raise ``RuntimeError``.

    The caller turns the ``RuntimeError`` into a skip with the reason printed. Raising
    rather than returning ``None`` keeps the "no cluster" path from being confusable with
    the "cluster with no schema" path, which are different findings.
    """
    supplied = os.environ.get("TRAPPOINT_UNWELD_DSN")
    if supplied:
        if is_forbidden_dsn(supplied):
            raise RuntimeError(
                f"TRAPPOINT_UNWELD_DSN points at a protected cluster ({supplied!r}). The "
                f"unwelding suite drops constraints and disables triggers; it runs on a "
                f"container it can destroy, never on the Compose volume or the default "
                f"local port."
            )
        yield supplied
        return

    docker = shutil.which("docker")
    if docker is None:
        raise RuntimeError(
            "no TRAPPOINT_UNWELD_DSN and no docker on PATH. The unwelding suite needs a "
            "cluster it is allowed to break; it will not borrow the one the conformance "
            "suite runs on."
        )

    name = f"trappoint-unweld-{uuid.uuid4().hex[:8]}"
    port = os.environ.get("TRAPPOINT_UNWELD_PORT", "26399")
    started = subprocess.run(  # noqa: S603
        [
            docker,
            "run",
            "-d",
            "--name",
            name,
            "-p",
            f"127.0.0.1:{port}:26257",
            CRDB_IMAGE,
            "start-single-node",
            "--insecure",
            "--store=type=mem,size=2GiB",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if started.returncode != 0:
        raise RuntimeError(f"could not start a disposable cluster: {started.stderr.strip()}")

    dsn = f"postgresql://root@127.0.0.1:{port}/defaultdb?sslmode=disable"
    try:
        _wait_for_sql(dsn)
        yield dsn
    finally:
        subprocess.run(  # noqa: S603
            [docker, "rm", "-f", name], capture_output=True, text=True, check=False
        )


def _wait_for_sql(dsn: str, *, attempts: int = 40, delay: float = 2.0) -> None:
    import psycopg

    last: Exception | None = None
    for _ in range(attempts):
        try:
            with psycopg.connect(dsn, connect_timeout=5) as conn:
                conn.execute("SELECT 1")
        except psycopg.Error as exc:
            last = exc
            time.sleep(delay)
        else:
            return
    raise RuntimeError(f"the disposable cluster never answered SQL: {last}")
