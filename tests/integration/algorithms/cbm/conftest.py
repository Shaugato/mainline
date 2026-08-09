# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""Cluster and schema fixtures for the CONSERVATION OF BLAME MASS SQL suite.

The suite needs a real CockroachDB v26.2.  It finds one in this order and
**skips with a reason** rather than faking anything if it cannot:

1. ``MAINLINE_TEST_DSN`` (or ``COCKROACH_URL`` / ``CRDB_URL``) — a running cluster;
2. a ``cockroach`` binary on ``PATH`` — an in-memory single node for the session;
3. a running Docker daemon — ``cockroachdb/cockroach:latest-v26.2``.

AWS credentials are not valid on the build machine and CockroachDB Cloud is not
assumed; a local binary or a container is the intended path.  **Nothing in this
worker is done on the basis of a skipped run**, and the skip message says which
of the three was missing.

FOUR SCHEMAS, AND WHY THE LAST THREE ARE THE POINT
--------------------------------------------------
``guarded`` applies the real spine and all eleven owned migrations.  The other
three withhold exactly one trigger each:

===================  ===============  ==============================================
fixture              withheld         what becomes possible, and must be observed
===================  ===============  ==============================================
``unguarded``        ``0145a``        a client's fabricated counters survive intact
``unprojected``      ``0145b``        a residue row keeps a client-chosen severity
``ungated``          ``0145c/0145d``  a merge over an unaccounted commit succeeds
===================  ===============  ==============================================

PL-2 says a suite for a product whose deliverable is a *refusal* must have been
red for the right reason.  Performing that once, in a commit message, proves
nothing a year later.  These pairs make it permanent: the identical statement is
**accepted** by the withholding schema and refused by ``guarded``.  Without the
pair, "the write was refused" is equally consistent with a ``NOT NULL``, a
foreign key, or a typo in the test's own SQL.
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
from typing import Any

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[4]
_SRC = _REPO_ROOT / "verticals" / "mainline" / "packages" / "mainline-domain" / "src"
if importlib.util.find_spec("mainline_domain") is None and _SRC.is_dir():
    sys.path.insert(0, str(_SRC))

from _cbm_sql_support import (  # noqa: E402  (after the sys.path fix-up, deliberately)
    full_stack,
    split_statements,
    stack_without,
    stood_in_objects,
)

try:  # soft, NOT `importorskip`
    import psycopg
except ImportError:  # pragma: no cover - depends on which extras are installed
    psycopg = None  # type: ignore[assignment]

#: ``pytest.importorskip`` at conftest scope would skip the WHOLE directory,
#: including the shape suites, which need no driver and no cluster and are the
#: only checks of these eleven migrations that run everywhere.
PSYCOPG_MISSING_REASON = (
    "psycopg 3 is required to talk to CockroachDB; `uv sync --extra db` installs it"
)

CRDB_IMAGE = os.environ.get("MAINLINE_CRDB_IMAGE", "cockroachdb/cockroach:latest-v26.2")
CONTAINER_NAME = "mainline-cbm-test"
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
            "no CockroachDB v26.2 reachable: set MAINLINE_TEST_DSN, or put `cockroach` on "
            f"PATH, or start the Docker daemon so the suite can run `docker run {CRDB_IMAGE} "
            "start-single-node --insecure`. CONSERVATION OF BLAME MASS is NOT verified by a "
            "skipped run."
        )
    try:
        yield found
    finally:
        if found.process is not None:
            found.process.terminate()
        if owns_docker:
            _docker(["rm", "-f", CONTAINER_NAME], timeout=DOCKER_PROBE_TIMEOUT_S)


def _apply(conn: Any, path: Path) -> int:
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
    withheld: tuple[str, ...]

    def connect(self, *, autocommit: bool = True) -> Any:
        return psycopg.connect(self.dsn, autocommit=autocommit)


def _build(
    cluster: Cluster, stack: list[Path], *, tag: str, withheld: tuple[str, ...]
) -> Iterator[Schema]:
    database = f"mainline_cbm_{tag}_{uuid.uuid4().hex[:8]}"
    with psycopg.connect(cluster.dsn, autocommit=True) as admin:
        admin.execute(f"CREATE DATABASE {database}")

    from psycopg.conninfo import conninfo_to_dict, make_conninfo

    parts = conninfo_to_dict(cluster.dsn)
    parts["dbname"] = database
    dsn = make_conninfo(**parts)

    applied: list[str] = []
    statements = 0
    with psycopg.connect(dsn, autocommit=True) as conn:
        for path in stack:
            statements += _apply(conn, path)
            applied.append(path.name)

    stood_in = stood_in_objects()
    print(
        f"\n[cbm/{tag}] cluster:  {cluster.provenance}\n"
        f"[cbm/{tag}] database: {database}\n"
        f"[cbm/{tag}] applied {len(applied)} files ({statements} statements) forward from "
        f"clean: {', '.join(applied)}\n"
        f"[cbm/{tag}] withheld: {', '.join(withheld) if withheld else '(nothing)'}\n"
        f"[cbm/{tag}] STOOD IN from _pending_dependency.sql: "
        f"{', '.join(stood_in) if stood_in else '(nothing — every dependency is a real migration)'}"
    )
    try:
        yield Schema(dsn=dsn, database=database, applied=applied, withheld=withheld)
    finally:
        with psycopg.connect(cluster.dsn, autocommit=True) as admin:
            admin.execute(f"DROP DATABASE IF EXISTS {database} CASCADE")


@pytest.fixture(scope="session")
def guarded_schema(cluster: Cluster) -> Iterator[Schema]:
    """Spine + all eleven owned migrations.  The deployment as it is meant to be."""
    yield from _build(cluster, full_stack(), tag="guarded", withheld=())


@pytest.fixture(scope="session")
def unguarded_schema(cluster: Cluster) -> Iterator[Schema]:
    """``0145a`` withheld: ``fn_cbm_account_guard`` exists, nothing calls it.

    The permanent red half of PL-2 for the account.  A client's fabricated
    counters survive here and are corrected in ``guarded``.
    """
    yield from _build(
        cluster,
        stack_without("0145a_trg_cbm_account_guard.sql"),
        tag="unguarded",
        withheld=("0145a_trg_cbm_account_guard.sql",),
    )


@pytest.fixture(scope="session")
def unprojected_schema(cluster: Cluster) -> Iterator[Schema]:
    """``0145b`` withheld: ``max_ancestral_severity`` is client-supplied again.

    This is the state ``0049_identity_residue.sql``'s own header describes and
    objects to.  Withholding one statement reproduces it exactly, which is how
    this suite proves the projection is doing something.
    """
    yield from _build(
        cluster,
        stack_without("0145b_trg_residue_project.sql"),
        tag="unprojected",
        withheld=("0145b_trg_residue_project.sql",),
    )


@pytest.fixture(scope="session")
def ungated_schema(cluster: Cluster) -> Iterator[Schema]:
    """``0145c`` and ``0145d`` withheld: a merge over an unaccounted commit succeeds."""
    yield from _build(
        cluster,
        stack_without("0145c_trg_cbm_gate_permit.sql", "0145d_trg_cbm_gate_cr.sql"),
        tag="ungated",
        withheld=("0145c_trg_cbm_gate_permit.sql", "0145d_trg_cbm_gate_cr.sql"),
    )


@pytest.fixture
def conn(guarded_schema: Schema) -> Iterator[Any]:
    """One autocommit connection per test against the guarded schema.

    Autocommit, not a rolled-back transaction: a refused statement must not be
    able to hide behind a rollback that also erases the rows written before it.
    """
    connection = guarded_schema.connect()
    try:
        yield connection
    finally:
        connection.close()


@pytest.fixture
def isolated_schema(cluster: Cluster) -> Iterator[Schema]:
    """A FRESH database per test, with the whole stack applied.

    Most tests share ``guarded_schema`` and take a fresh ``site_id`` instead,
    which is faster and models production correctly: rows for other sites exist
    and RLS keeps them out of view.

    ``mainline_audit.v_cbm_ledger`` cannot use that trick.  Its ``LIMIT 25`` and
    its ``n_accounted_commits`` total are global by construction — under RLS a
    reader sees only their own site's rows and the totals are then the totals of
    what they may see, but a superuser test connection sees everything.  So a
    test that asserts on the CAP or on the TOTALS needs a database in which its
    own rows are the only rows, and that is what this builds.
    """
    yield from _build(cluster, full_stack(), tag="isolated", withheld=())


@pytest.fixture
def isolated_conn(isolated_schema: Schema) -> Iterator[Any]:
    connection = isolated_schema.connect()
    try:
        yield connection
    finally:
        connection.close()


@pytest.fixture
def site_id() -> uuid.UUID:
    """A fresh site per test, so the tests share a database and not a history."""
    return uuid.uuid4()
