# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""One cluster for the whole session — reused if one answers, started exactly once if not.

WHY THIS EXISTS, measured on 2026-08-10 and not inferred. A full-suite run started
**thirteen** private single-node CockroachDB containers concurrently, each with
``--cache=.25 --max-sql-memory=.25``::

    mainline-cbm-test  mainline-deltalattice-test  mainline-directrix-test
    mainline-origindiff-test  mainline-late-recall-test  mainline-recall-index-test
    mainline-recall-lexical-test  mainline-blame-schema-test
    mainline-event-severity-schema-test  mainline-cbm-probe  mainline-custody-nemesis
    trappoint-model-differential  trappoint-model-concurrency

Every one exited 7 or 8. They took the real node down with them and left the Docker engine
API answering ``500``. Thirteen nodes each claiming a quarter of the machine's memory is not
a test environment; it is a fork bomb with a version tag.

THE SEAM. Every one of the twenty-three files that spawns a container checks an environment
DSN **first** and only reaches for Docker when it is unset. Four spellings are in use —
``MAINLINE_TEST_DSN``, ``COCKROACH_URL``, ``CRDB_URL``, ``TRAPPOINT_DSN``. One cluster
exported under all four collapses thirteen into one **without editing a single domain
conftest**, and this module is the thing that finds or starts that one.

ISOLATION. Sharing a node is not sharing a database. :func:`fresh_database` hands each test
module its own database and drops it afterwards, so two modules that both create
``mainline.event`` do not collide, and a module that leaves rows behind cannot be the reason
another module passes.

``gc.ttlseconds``. Local defaults to **14400**; CockroachDB Cloud Basic is **4500**. Local is
therefore MORE permissive than production, and a time-travel test that passes on a laptop at
14400 is not evidence that it passes on Cloud. Every database this module creates is pinned
to the Cloud value, and a node this module started has its default range pinned too. A node
someone else started is never reconfigured cluster-wide — it is not ours to change.

REFUSING TO HANG. The measured failure mode was not a red suite, it was a **wedged** one:
fixtures connect with no ``connect_timeout``, so a dead node is an infinite wait rather than
an error, and ``pytest-timeout``'s thread method cannot interrupt a hang inside session-scoped
fixture setup. Measured on this machine: a connect to a black-holed address returned
``ConnectionTimeout`` after **130.1 s** with no ``PGCONNECT_TIMEOUT`` and after **3.1 s** with
``PGCONNECT_TIMEOUT=3``. Every connect here carries an explicit timeout, and
:class:`ProcessGuard` makes the no-cluster case a fast, reasoned skip instead of thirteen
sequential attempts to start a container that cannot start.

LAYERING — WHY ``psycopg`` IS IMPORTED INSIDE FUNCTIONS AND NOT AT THE TOP. Measured on
2026-08-10 in GitHub Actions run 31372088311: all seven ``boundary`` jobs died before a
single assertion executed, with ``ModuleNotFoundError: No module named 'psycopg'`` raised
from line 60 of *this file* while pytest loaded the ``trappoint_testkit.plugin`` entry
point. That lane installs ``./packages/mainline-boundary pytest`` and nothing else, on
purpose: E3 asserts what a *minimal* kernel-plane environment can reach, so widening it
would destroy the thing it measures.

The defect was ours, not the lane's. Three things this module owns need no database at all
— :data:`MODES` (four strings, which ``--crdb`` validates against), :data:`DSN_ENV_NAMES`
(four more strings) and :class:`ProcessGuard` (``shutil`` and ``subprocess``) — and a
module-scope ``import psycopg`` made every one of them cost a PostgreSQL driver. So the
driver is imported by the functions that open a socket, and by nothing else. Importing this
module is stdlib-only; :class:`DriverMissing` names the driver, the action and the fix when
something that genuinely needs it is called without it.
"""

from __future__ import annotations

import os
import re
import shutil
import socket
import subprocess
import time
import uuid
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, cast

if TYPE_CHECKING:  # pragma: no cover - types only; never imported at runtime
    import psycopg

__all__ = [
    "CLOUD_GC_TTL_SECONDS",
    "DEFAULT_CONTAINER_NAME",
    "DEFAULT_DSNS",
    "DSN_ENV_NAMES",
    "Database",
    "DriverMissing",
    "ProcessGuard",
    "SharedCluster",
    "connect",
    "driver_error",
    "dsn_for_database",
    "ensure",
    "export_dsn",
    "fresh_database",
    "pin_gc_ttl",
    "probe",
    "reuse",
    "spawn",
]

#: Every spelling a fixture in this repository reads a DSN from, in the order the majority of
#: them check. Counted across ``*.py`` on 2026-08-10: 28 / 19 / 17 / 3 occurrences.
DSN_ENV_NAMES: tuple[str, ...] = (
    "MAINLINE_TEST_DSN",
    "COCKROACH_URL",
    "CRDB_URL",
    "TRAPPOINT_DSN",
)

#: Tried when no environment DSN is set. The compose file publishes 26257 on loopback.
DEFAULT_DSNS: tuple[str, ...] = ("postgresql://root@127.0.0.1:26257/defaultdb?sslmode=disable",)

#: The ONE container this package may create. Named for the package so that
#: ``docker ps -a`` after a run says who to blame.
DEFAULT_CONTAINER_NAME = "trappoint-testkit-crdb"

#: CockroachDB Cloud Basic's value. Local defaults to 14400, which is more permissive.
CLOUD_GC_TTL_SECONDS = 4500

#: A probe is a question, not a wait. Three seconds is longer than a loopback answer and
#: shorter than a human's patience.
PROBE_TIMEOUT_S = 3.0

#: A cold `docker run` may include an image pull.
DOCKER_RUN_TIMEOUT_S = 600.0

#: `docker info` against a DEAD daemon does not fail — it BLOCKS. The only fact wanted from
#: it is "is there a daemon", and the answer to a hang is "no".
DOCKER_PROBE_TIMEOUT_S = 10.0

#: How long a freshly started node may take to answer SQL.
READY_TIMEOUT_S = 120.0

_SAFE_LABEL = re.compile(r"[^a-z0-9_]+")
_PORT_TAIL = re.compile(r":(?P<port>\d+)\s*$")
#: Both path separators, so the guard behaves identically on Windows and on a Linux runner.
_PATH_SEPARATORS = re.compile(r"[\\/]")


# ── the driver ───────────────────────────────────────────────────────────────────────────────


#: What to install, spelled exactly as `packages/trappoint-testkit/pyproject.toml` declares it,
#: so a reader can paste the line rather than go looking for the version floor.
DRIVER_REQUIREMENT = "psycopg[binary,pool]>=3.3.4"


class DriverMissing(RuntimeError):
    """The PostgreSQL driver is absent and the operation asked for needs a live socket.

    Raised instead of letting a bare ``ModuleNotFoundError`` escape, because the two say
    very different things to whoever reads the log. ``No module named 'psycopg'`` on line 60
    of a module that was imported for its four-string ``MODES`` tuple is a puzzle; *this*
    names the driver, the action that wanted it, and the command that supplies it.
    """


def _driver_missing(action: str, cause: ImportError) -> DriverMissing:
    """Build the refusal for *action*, naming the fix rather than only the symptom."""
    return DriverMissing(
        f"trappoint-testkit cannot {action}: the PostgreSQL driver is not importable in "
        f"this environment ({cause}). Install it with "
        f'`python -m pip install "{DRIVER_REQUIREMENT}"`. Nothing else in this module '
        "needs it — MODES, DSN_ENV_NAMES, ProcessGuard and the image pin are stdlib-only "
        "and import without a driver, which is what lets a minimal lane load this plugin "
        "at all."
    )


def driver_error() -> str | None:
    """``None`` when the driver imports; otherwise the one-line reason it does not.

    A question, not an assertion: a caller that has no use for a cluster — the boundary
    lanes, which install ``mainline-boundary`` and ``pytest`` and nothing else — asks this
    once and reports "no cluster, and here is why" instead of spending two minutes starting
    a container whose readiness it could never observe.
    """
    try:
        import psycopg  # noqa: F401 - imported for the side effect of finding out
    except ImportError as exc:
        return str(exc)
    return None


# ── the cluster ──────────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class SharedCluster:
    """A reachable CockroachDB, how it was found, and whether we may reconfigure it."""

    dsn: str
    provenance: str
    version: str
    #: The container this package started, if it started one. ``None`` when reusing.
    container: str | None = None

    @property
    def owned(self) -> bool:
        """Did this package start it? Only an owned node may be reconfigured cluster-wide."""
        return self.container is not None


@dataclass(frozen=True)
class Database:
    """A database created for one test module, and the DSN that reaches it."""

    name: str
    dsn: str
    admin_dsn: str


def connect(dsn: str, *, timeout: float = PROBE_TIMEOUT_S) -> psycopg.Connection[Any]:
    """Open an autocommit connection with an explicit connect timeout.

    Autocommit because DDL on CockroachDB is a background job and a multi-statement DDL
    transaction is a different animal from a sequence of schema changes. Explicit timeout
    because the default is 130 seconds of silence, measured.

    Raises:
        DriverMissing: psycopg is not importable here. See the module's LAYERING note.
    """
    try:
        import psycopg
    except ImportError as exc:
        raise _driver_missing("open a connection", exc) from exc
    return psycopg.connect(dsn, autocommit=True, connect_timeout=int(max(1, round(timeout))))


def probe(dsn: str, *, timeout: float = PROBE_TIMEOUT_S) -> str | None:
    """``version()`` if something answers SQL on *dsn*, otherwise ``None``.

    Never raises *for a connection failure*: "is there a cluster there" must not be able to
    fail the run. :class:`DriverMissing` is deliberately NOT swallowed, because it is not an
    answer to that question — it is this process being unable to ask it, and reporting
    "nothing answered" when nobody was able to speak is the kind of quiet lie that later
    shows up as a container nobody can explain.
    """
    try:
        with connect(dsn, timeout=timeout) as conn:
            row = conn.execute("SELECT version()").fetchone()
    except DriverMissing:
        raise
    except Exception:  # noqa: BLE001 - any failure at all means "nothing is there"
        return None
    return None if row is None else str(row[0])


def _wait_ready(dsn: str, deadline: float) -> str | None:
    while True:
        version = probe(dsn)
        if version is not None:
            return version
        if time.monotonic() >= deadline:
            return None
        time.sleep(1.0)


def _env_dsns(env: dict[str, str] | None = None) -> list[tuple[str, str]]:
    source = os.environ if env is None else env
    found: list[tuple[str, str]] = []
    for name in DSN_ENV_NAMES:
        value = source.get(name)
        if value:
            found.append((f"${name}", value))
    return found


def reuse(
    *,
    candidates: Sequence[str] = (),
    env: dict[str, str] | None = None,
    timeout: float = PROBE_TIMEOUT_S,
) -> SharedCluster | None:
    """Return the first cluster that answers: an environment DSN, then the compose port.

    Costs one refused TCP connection when there is nothing there, which is why ``auto`` can
    afford to try it before considering Docker.
    """
    ordered: list[tuple[str, str]] = [*_env_dsns(env)]
    ordered.extend(("the compose port", dsn) for dsn in (candidates or DEFAULT_DSNS))
    for provenance, dsn in ordered:
        version = probe(dsn, timeout=timeout)
        if version is not None:
            return SharedCluster(dsn=dsn, provenance=f"reused, {provenance}", version=version)
    return None


# ── docker ───────────────────────────────────────────────────────────────────────────────────


def _docker(args: list[str], *, timeout: float) -> subprocess.CompletedProcess[str] | None:
    """One docker command. ``None`` when docker hangs, dies, or is not installed.

    ``TimeoutExpired`` is not covered by ``check=False``, and an uncaught one turns a
    situation that calls for a skip into a suite error. ``OSError`` covers both a missing
    binary and the :class:`ProcessGuard` refusing on purpose.
    """
    try:
        return subprocess.run(  # noqa: S603
            ["docker", *args],  # noqa: S607
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except (subprocess.TimeoutExpired, OSError):
        return None


def docker_available() -> bool:
    """Report whether a docker CLI is on PATH and a daemon answers within the probe budget."""
    if shutil.which("docker") is None:
        return False
    probed = _docker(["info", "--format", "{{.ServerVersion}}"], timeout=DOCKER_PROBE_TIMEOUT_S)
    return probed is not None and probed.returncode == 0


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _published_port(container: str) -> int | None:
    result = _docker(["port", container, "26257/tcp"], timeout=DOCKER_PROBE_TIMEOUT_S)
    if result is None or result.returncode != 0:
        return None
    for line in result.stdout.splitlines():
        match = _PORT_TAIL.search(line.strip())
        if match is not None:
            return int(match.group("port"))
    return None


def _running(container: str) -> bool:
    result = _docker(
        ["inspect", "-f", "{{.State.Running}}", container], timeout=DOCKER_PROBE_TIMEOUT_S
    )
    return result is not None and result.returncode == 0 and result.stdout.strip() == "true"


def spawn(
    *,
    image: str,
    container: str = DEFAULT_CONTAINER_NAME,
    reuse_container: bool = True,
    ready_timeout: float = READY_TIMEOUT_S,
) -> SharedCluster | None:
    """Start **exactly one** container, or adopt the one this package started earlier.

    Returns ``None`` — never raises — when Docker is absent, dead, or the node never becomes
    ready. The caller turns that into a skip with a reason.

    The port is published on ``127.0.0.1`` only: an ``--insecure`` node has no authentication
    at all and must not be reachable from the LAN.
    """
    if not docker_available():
        return None
    if reuse_container and _running(container):
        port = _published_port(container)
        if port is not None:
            dsn = f"postgresql://root@127.0.0.1:{port}/defaultdb?sslmode=disable"
            version = _wait_ready(dsn, time.monotonic() + 30.0)
            if version is not None:
                return SharedCluster(
                    dsn=dsn,
                    provenance=f"adopted container {container} on {port}",
                    version=version,
                    container=container,
                )
    _docker(["rm", "-f", container], timeout=DOCKER_PROBE_TIMEOUT_S)
    port = _free_port()
    started = _docker(
        [
            "run",
            "-d",
            "--name",
            container,
            "-p",
            f"127.0.0.1:{port}:26257",
            image,
            "start-single-node",
            "--insecure",
            "--store=type=mem,size=2GiB",
        ],
        timeout=DOCKER_RUN_TIMEOUT_S,
    )
    if started is None or started.returncode != 0:
        _docker(["rm", "-f", container], timeout=DOCKER_PROBE_TIMEOUT_S)
        return None
    dsn = f"postgresql://root@127.0.0.1:{port}/defaultdb?sslmode=disable"
    version = _wait_ready(dsn, time.monotonic() + ready_timeout)
    if version is None:
        _docker(["rm", "-f", container], timeout=DOCKER_PROBE_TIMEOUT_S)
        return None
    return SharedCluster(
        dsn=dsn,
        provenance=f"started container {container} from {image} on {port}",
        version=version,
        container=container,
    )


def remove_container(container: str) -> bool:
    """Remove a container by name. True when docker reported success."""
    result = _docker(["rm", "-f", container], timeout=DOCKER_PROBE_TIMEOUT_S)
    return result is not None and result.returncode == 0


# ── acquisition ──────────────────────────────────────────────────────────────────────────────

#: The four acquisition modes. ``none`` is not an absence of policy; it is the policy that
#: says "there is no cluster, say so quickly".
MODES: tuple[str, ...] = ("auto", "reuse", "spawn", "none")


def ensure(
    mode: str,
    *,
    image: str | None = None,
    container: str = DEFAULT_CONTAINER_NAME,
    env: dict[str, str] | None = None,
) -> SharedCluster | None:
    """Obtain the session's one cluster under *mode*, or ``None``.

    * ``reuse`` — adopt something already answering; never start anything.
    * ``spawn`` — start a container, replacing one this package left behind.
    * ``auto``  — ``reuse``, and if nothing answers, ``spawn``.
    * ``none``  — do not look. Always ``None``.

    Never raises for an absent cluster: "no cluster" is a result, not an error.

    Raises:
        ValueError: *mode* is not one of :data:`MODES`.
        DriverMissing: every mode but ``none`` needs a driver, and a missing driver is a
            missing prerequisite rather than an absent cluster. Refusing here is what stops
            ``auto`` from doing the measured-worst thing: ``docker run`` a node, then wait
            the full :data:`READY_TIMEOUT_S` for a readiness probe that cannot succeed
            because nothing in this process can speak pgwire, then delete the node. Callers
            that have no use for a cluster ask :func:`driver_error` first and skip with a
            reason instead — see :mod:`trappoint_testkit.plugin`.
    """
    if mode not in MODES:
        raise ValueError(f"unknown crdb mode {mode!r}; expected one of {', '.join(MODES)}")
    if mode == "none":
        return None
    try:
        import psycopg  # noqa: F401 - imported for the side effect of finding out
    except ImportError as exc:
        raise _driver_missing(f"obtain a cluster under --crdb={mode}", exc) from exc
    if mode in ("auto", "reuse"):
        found = reuse(env=env)
        if found is not None or mode == "reuse":
            return found
    if image is None:
        return None
    return spawn(image=image, container=container, reuse_container=(mode == "auto"))


def export_dsn(cluster: SharedCluster, env: dict[str, str] | None = None) -> tuple[str, ...]:
    """Publish the cluster's DSN under all four spellings; report which names were written.

    Every name is OVERWRITTEN, deliberately. A stale ``CRDB_URL`` pointing at a container
    that died last Tuesday is exactly the state that produces a 130-second hang, and the
    session has just proved that *this* DSN answers.
    """
    target = os.environ if env is None else env
    for name in DSN_ENV_NAMES:
        target[name] = cluster.dsn
    return DSN_ENV_NAMES


# ── databases ────────────────────────────────────────────────────────────────────────────────


def dsn_for_database(dsn: str, database: str) -> str:
    """Re-point a DSN at another database without string surgery on the URL.

    An environment-supplied DSN may carry ``options=--cluster=``, an ``sslrootcert`` path, or
    no path component at all, and none of those survive a naive ``rsplit('/')``.

    Raises:
        DriverMissing: psycopg is not importable here. The parser this needs lives in the
            driver, and re-implementing libpq's conninfo grammar to avoid it would be a
            second, quieter version of the bug this function exists to prevent.
    """
    try:
        from psycopg.conninfo import conninfo_to_dict, make_conninfo
    except ImportError as exc:
        raise _driver_missing("re-point a DSN at another database", exc) from exc
    parts = conninfo_to_dict(dsn)
    parts["dbname"] = database
    # `conninfo_to_dict` types its values as `str | int | None` (a port is an int), while
    # `make_conninfo` is annotated `**kwargs: str`. The round trip is exactly what psycopg
    # documents, so the cast is a statement about the stubs rather than about the data.
    return make_conninfo(**cast("dict[str, str]", parts))


def pin_gc_ttl(
    dsn: str, *, database: str | None = None, seconds: int = CLOUD_GC_TTL_SECONDS
) -> str:
    """Pin ``gc.ttlseconds`` to the Cloud value; report what happened, in one line.

    With *database*, the pin is scoped to that database — safe on a node we are only
    borrowing. Without it, the node's **default range** is reconfigured, which is only
    appropriate for a node this package started.

    Never raises *for a database that says no*: a cluster that refuses the zone change is
    still a usable cluster, and the caller needs to be told rather than stopped.

    Raises:
        DriverMissing: psycopg is not importable here. A caller holding a
            :class:`SharedCluster` has already connected once, so reaching this without a
            driver means something changed underneath the session and saying so beats
            reporting it as a cluster that declined.
    """
    try:
        import psycopg
    except ImportError as exc:
        raise _driver_missing("pin gc.ttlseconds", exc) from exc
    target = f"DATABASE {database}" if database else "RANGE default"
    try:
        with connect(dsn) as conn:
            conn.execute(f"ALTER {target} CONFIGURE ZONE USING gc.ttlseconds = {int(seconds)}")
    except psycopg.Error as exc:
        return f"gc.ttlseconds on {target} NOT pinned: {exc.sqlstate} {exc}"
    return f"gc.ttlseconds = {int(seconds)} on {target}"


def _database_name(label: str) -> str:
    safe = _SAFE_LABEL.sub("_", label.lower()).strip("_") or "module"
    return f"tk_{safe[:40]}_{uuid.uuid4().hex[:10]}"


@contextmanager
def fresh_database(cluster: SharedCluster, label: str) -> Iterator[Database]:
    """Yield a database of its own for *label*, pinned to the Cloud GC TTL, dropped on exit.

    Isolation is per module rather than per test on purpose: applying a migration band costs
    seconds and asserting against a schema built by *this* module costs nothing extra. Per
    test would be honest and unusably slow; per session would let one module's leftovers
    explain another module's pass.

    Raises:
        DriverMissing: psycopg is not importable here. See the module's LAYERING note.
    """
    try:
        import psycopg
    except ImportError as exc:
        raise _driver_missing("create a database for this module", exc) from exc
    name = _database_name(label)
    with connect(cluster.dsn) as admin:
        admin.execute(f"CREATE DATABASE {name}")
    pin_gc_ttl(cluster.dsn, database=name)
    try:
        yield Database(
            name=name,
            dsn=dsn_for_database(cluster.dsn, name),
            admin_dsn=cluster.dsn,
        )
    finally:
        try:
            with connect(cluster.dsn) as admin:
                admin.execute(f"DROP DATABASE IF EXISTS {name} CASCADE")
        except psycopg.Error:
            # A drop that fails leaves a named database behind and nothing else. Failing the
            # session here would report teardown as the defect and hide the real one.
            pass


# ── the guard ────────────────────────────────────────────────────────────────────────────────


class ProcessGuard:
    """Make "there is no cluster" a fast skip instead of thirteen attempts to build one.

    When the session has no cluster, every one of the twenty-three container-spawning files
    would otherwise walk its own discovery ladder: ``shutil.which('cockroach')``, then
    ``docker info`` (which BLOCKS for the full ten-second probe against a dead daemon), then
    ``docker run``. Thirteen times ten seconds is two wasted minutes on the good day and a
    wedged machine on the bad one.

    So the ladder is cut at the first rung. ``shutil.which`` reports the cluster binaries as
    absent and ``subprocess`` refuses to launch them with ``FileNotFoundError`` — which every
    one of those files already handles, because ``FileNotFoundError`` is an ``OSError`` and
    they all catch ``OSError`` to mean "no Docker here". Each fixture then reaches **its own**
    ``pytest.skip`` with **its own** reason, which is a better message than anything this
    package could write on its behalf.

    Narrow by construction: only the named executables are blocked, so a test that shells out
    to ``git`` or ``python`` is untouched. Patching the module attribute rather than the
    imported name is sound here because no file in this repository writes
    ``from subprocess import run`` — verified by grep over ``tests``, ``packages``,
    ``verticals`` and ``scripts``.
    """

    #: Anything that could start a database node. ``.exe`` because this repository is
    #: developed on Windows and ``shutil.which('docker')`` returns ``docker.exe`` there.
    BLOCKED: frozenset[str] = frozenset(
        {
            "docker",
            "docker.exe",
            "podman",
            "podman.exe",
            "nerdctl",
            "nerdctl.exe",
            "cockroach",
            "cockroach.exe",
            "docker-compose",
            "docker-compose.exe",
        }
    )

    def __init__(self, reason: str) -> None:
        """Build a guard that will report *reason* to anything it refuses to launch."""
        self.reason = reason
        self._installed = False
        self._which = shutil.which
        self._run = subprocess.run
        self._popen = subprocess.Popen

    @staticmethod
    def _basename(value: str | os.PathLike[str]) -> str:
        r"""Split on BOTH separators, on every platform.

        ``os.path.basename`` splits on ``\\`` only on Windows, so a guard written with it
        would let ``C:\\Program Files\\Docker\\docker.exe`` through on a Linux runner — the
        exact machine where a runaway container costs the most.
        """
        return _PATH_SEPARATORS.split(os.fspath(value))[-1].lower()

    @classmethod
    def blocks(cls, argv: object) -> str | None:
        """Report the blocked executable *argv* would launch, or ``None``."""
        if isinstance(argv, (str, os.PathLike)):
            head: object = argv
        elif isinstance(argv, Sequence) and argv:
            head = argv[0]
        else:
            return None
        if not isinstance(head, (str, os.PathLike)):
            return None
        name = cls._basename(head)
        return name if name in cls.BLOCKED else None

    def install(self) -> None:
        """Patch ``shutil.which`` and ``subprocess``. Idempotent."""
        if self._installed:
            return
        guard = self

        def which(cmd: Any, *args: Any, **kwargs: Any) -> str | None:
            if isinstance(cmd, (str, os.PathLike)) and guard._basename(cmd) in guard.BLOCKED:
                return None
            found = guard._which(cmd, *args, **kwargs)
            return None if found is None else str(found)

        def run(*args: Any, **kwargs: Any) -> Any:
            guard._refuse(args, kwargs)
            return guard._run(*args, **kwargs)

        class Popen(guard._popen):  # type: ignore[misc, name-defined]
            """The real ``Popen``, with a refusal in front of its constructor."""

            def __init__(self, *args: Any, **kwargs: Any) -> None:
                guard._refuse(args, kwargs)
                super().__init__(*args, **kwargs)

        # `setattr` rather than assignment: `shutil.which` is an overloaded function and
        # `subprocess.Popen` is a class, so a plain assignment is untypeable no matter how the
        # replacement is annotated. The indirection says "this is a monkeypatch" out loud.
        setattr(shutil, "which", which)  # noqa: B010 - see the comment above: a plain assignment is untypeable
        setattr(subprocess, "run", run)  # noqa: B010 - see the comment above: a plain assignment is untypeable
        setattr(subprocess, "Popen", Popen)  # noqa: B010 - see the comment above: a plain assignment is untypeable
        self._installed = True

    def _refuse(self, args: tuple[object, ...], kwargs: dict[str, object]) -> None:
        argv = args[0] if args else kwargs.get("args")
        blocked = self.blocks(argv)
        if blocked is not None:
            raise FileNotFoundError(
                2,
                f"trappoint-testkit refuses to launch {blocked!r}: {self.reason}",
                blocked,
            )

    def uninstall(self) -> None:
        """Put the standard library back. Idempotent."""
        if not self._installed:
            return
        setattr(shutil, "which", self._which)  # noqa: B010 - see the comment above: a plain assignment is untypeable
        setattr(subprocess, "run", self._run)  # noqa: B010 - see the comment above: a plain assignment is untypeable
        setattr(subprocess, "Popen", self._popen)  # noqa: B010 - see the comment above: a plain assignment is untypeable
        self._installed = False
