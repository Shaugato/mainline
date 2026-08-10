# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""The pytest plugin: one cluster per session, declared on the command line.

``--crdb=auto|reuse|spawn|none``

* ``auto``  (default) — reuse a cluster that already answers; start exactly one if none does.
* ``reuse`` — reuse or nothing. Never starts a container. What CI wants when the workflow
  has already declared a service.
* ``spawn`` — always this package's own container, replacing one it left behind. What a
  bisect wants when it must not inherit yesterday's schema.
* ``none``  — do not look, and make sure nothing else does either. Every cluster-backed test
  **skips with the reason its own fixture writes**, in seconds, instead of hanging.

The mode is resolved once, in ``pytest_configure``, which runs **before collection** — this
matters, because thirty-three modules read ``MAINLINE_CRDB_IMAGE`` at import time and would
otherwise have already fallen back to their hard-coded floating tag by the time a fixture ran.

WHAT THIS PLUGIN DOES NOT DO. It does not edit, wrap, monkeypatch or replace a single domain
fixture. Every one of them already prefers an environment DSN, so publishing one is enough.
The only patching it performs is :class:`~trappoint_testkit.cluster.ProcessGuard`, and only
when there is no cluster at all — which is the one case where those fixtures' own fallback
path is the thing that wedges the machine.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from typing import Any

import pytest

from . import cluster as _cluster
from . import image as _image
from .cluster import Database, ProcessGuard, SharedCluster

__all__ = ["State", "pytest_addoption", "pytest_configure"]

#: The libpq connect timeout, in seconds, applied when the environment does not set one.
#: Measured on this machine: a connect to a black-holed address raised ``ConnectionTimeout``
#: after **130.1 s** unset and after **3.1 s** at 3. A test that waits 130 s for a node that
#: is never coming back has stopped asserting anything.
DEFAULT_PGCONNECT_TIMEOUT = "5"

_MODE_ENV = "TRAPPOINT_CRDB_MODE"
_TEARDOWN_ENV = "TRAPPOINT_TESTKIT_TEARDOWN"


class State:
    """What the session decided about the cluster, and how to undo it."""

    def __init__(self, mode: str) -> None:
        """Record the resolved mode; everything else is filled in by ``pytest_configure``."""
        self.mode = mode
        self.cluster: SharedCluster | None = None
        self.image: str | None = None
        self.image_error: str | None = None
        self.gc_ttl_note: str | None = None
        self.skip_reason: str | None = None
        self.guard: ProcessGuard | None = None
        self._restore_env: dict[str, str | None] = {}

    # -- environment bookkeeping ---------------------------------------------------------

    def set_env(self, name: str, value: str | None) -> None:
        """Set or clear an environment variable, remembering what was there."""
        if name not in self._restore_env:
            self._restore_env[name] = os.environ.get(name)
        if value is None:
            os.environ.pop(name, None)
        else:
            os.environ[name] = value

    def restore_env(self) -> None:
        """Put every variable this session changed back the way it found it."""
        for name, previous in self._restore_env.items():
            if previous is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = previous
        self._restore_env.clear()

    @property
    def available(self) -> bool:
        """True when this session has a cluster to hand out."""
        return self.cluster is not None


STATE_KEY: pytest.StashKey[State] = pytest.StashKey()


def pytest_addoption(parser: pytest.Parser) -> None:
    """Declare ``--crdb``. Must run before argument parsing, so the plugin loads early."""
    parser.addoption(
        "--crdb",
        action="store",
        default=os.environ.get(_MODE_ENV, "auto"),
        choices=list(_cluster.MODES),
        help=(
            "how this session obtains its ONE CockroachDB: auto (reuse, else start one), "
            "reuse (never start), spawn (always this package's container), none (do not "
            "look — cluster tests skip with a reason instead of starting thirteen nodes)"
        ),
    )


def pytest_configure(config: pytest.Config) -> None:
    """Resolve the mode and obtain the session's one cluster, BEFORE collection begins."""
    config.addinivalue_line(
        "markers",
        "requires_cluster: needs a live CockroachDB; skips with a reason when none is shared",
    )
    state = State(str(config.getoption("--crdb")))
    config.stash[STATE_KEY] = state

    # 1. The image pin, before anything imports a module that reads it.
    try:
        state.image, _ = _image.export_pin(start=config.rootpath)
    except _image.PinNotFound as exc:
        state.image_error = str(exc)

    # 2. A connect timeout, before anything connects. Set for the whole process, including
    #    the twenty-three fixtures that pass no `connect_timeout` of their own.
    if not os.environ.get("PGCONNECT_TIMEOUT"):
        state.set_env("PGCONNECT_TIMEOUT", DEFAULT_PGCONNECT_TIMEOUT)

    # 3. Collection starts no cluster. `--collect-only` must cost a second, not a container.
    if config.getoption("collectonly"):
        state.skip_reason = "collection only: no cluster was obtained"
        _no_cluster(state)
        return

    if state.mode == "none":
        state.skip_reason = (
            "--crdb=none: this session declined to obtain a CockroachDB, so every test that "
            "needs one is skipped rather than allowed to start a private container"
        )
        _no_cluster(state)
        return

    found = _cluster.ensure(state.mode, image=state.image)
    if found is None:
        state.skip_reason = _unavailable_reason(state)
        _no_cluster(state)
        return

    state.cluster = found
    _cluster.export_dsn(found)
    # Publishing the DSN under four names is a process-wide change; record it so an
    # `--crdb=none` run in the same process afterwards is not poisoned by it.
    for name in _cluster.DSN_ENV_NAMES:
        state._restore_env.setdefault(name, None)
    if found.owned:
        # Only a node this package started may be reconfigured cluster-wide. A borrowed node
        # belongs to whoever started it, and every database we create is pinned anyway.
        state.gc_ttl_note = _cluster.pin_gc_ttl(found.dsn)
    else:
        state.gc_ttl_note = (
            f"gc.ttlseconds left alone cluster-wide (node not started by this package); "
            f"every database created here is pinned to {_cluster.CLOUD_GC_TTL_SECONDS}"
        )


def _no_cluster(state: State) -> None:
    """Publish "there is none" honestly: clear stale DSNs, then stop anything from spawning."""
    for name in _cluster.DSN_ENV_NAMES:
        state.set_env(name, None)
    state.guard = ProcessGuard(state.skip_reason or "no cluster for this session")
    state.guard.install()


def _unavailable_reason(state: State) -> str:
    if state.image_error is not None:
        return (
            f"--crdb={state.mode}: nothing answered, and no container could be started "
            f"because the image pin could not be read ({state.image_error})"
        )
    if state.mode == "reuse":
        return (
            "--crdb=reuse: no CockroachDB answered on $MAINLINE_TEST_DSN, $COCKROACH_URL, "
            "$CRDB_URL, $TRAPPOINT_DSN or 127.0.0.1:26257, and reuse mode will not start one"
        )
    return (
        f"--crdb={state.mode}: no CockroachDB answered and none could be started — docker is "
        f"absent, its daemon is not running, or `docker run {state.image}` did not become "
        "ready. Start the compose node (`docker compose up -d crdb`) or export "
        "MAINLINE_TEST_DSN."
    )


def pytest_report_header(config: pytest.Config) -> list[str]:
    """Say what happened, every run: mode, image, provenance, DSN, GC TTL."""
    state = config.stash.get(STATE_KEY, None)
    if state is None:
        return []
    lines = [f"trappoint-testkit: --crdb={state.mode}, image={state.image or state.image_error}"]
    if state.cluster is not None:
        version = state.cluster.version.split(" (", 1)[0]
        lines.append(f"trappoint-testkit: {state.cluster.provenance} — {version}")
        lines.append(f"trappoint-testkit: {state.cluster.dsn}")
        if state.gc_ttl_note:
            lines.append(f"trappoint-testkit: {state.gc_ttl_note}")
    else:
        lines.append(f"trappoint-testkit: NO CLUSTER — {state.skip_reason}")
    return lines


def pytest_unconfigure(config: pytest.Config) -> None:
    """Uninstall the guard, restore the environment, and tear the container down if asked."""
    state = config.stash.get(STATE_KEY, None)
    if state is None:
        return
    if state.guard is not None:
        state.guard.uninstall()
        state.guard = None
    if (
        state.cluster is not None
        and state.cluster.container is not None
        and os.environ.get(_TEARDOWN_ENV) == "1"
    ):
        _cluster.remove_container(state.cluster.container)
    state.restore_env()


# ── fixtures ─────────────────────────────────────────────────────────────────────────────────


@pytest.fixture(scope="session")
def crdb_state(request: pytest.FixtureRequest) -> State:
    """Expose what the session decided. Available even when there is no cluster."""
    state = request.config.stash.get(STATE_KEY, None)
    if state is None:  # pragma: no cover - only reachable if the plugin was not configured
        pytest.skip("trappoint-testkit plugin was not configured for this session")
    return state


@pytest.fixture(scope="session")
def shared_cluster(crdb_state: State) -> SharedCluster:
    """Return the session's ONE cluster, or skip with the reason there is none."""
    if crdb_state.cluster is None:
        pytest.skip(crdb_state.skip_reason or "no CockroachDB for this session")
    return crdb_state.cluster


@pytest.fixture(scope="module")
def crdb_database(
    shared_cluster: SharedCluster, request: pytest.FixtureRequest
) -> Iterator[Database]:
    """Yield a database of this module's own, pinned to the Cloud GC TTL, dropped after."""
    label = request.module.__name__.rsplit(".", 1)[-1] if request.module else "module"
    with _cluster.fresh_database(shared_cluster, label) as database:
        yield database


@pytest.fixture(scope="module")
def crdb_dsn(crdb_database: Database) -> str:
    """Return the DSN of this module's own database."""
    return crdb_database.dsn


@pytest.fixture
def crdb_conn(crdb_dsn: str) -> Iterator[Any]:
    """One autocommit connection per test, into this module's own database.

    Autocommit rather than a rolled-back transaction: a refused statement must not be able to
    hide behind a rollback that also erases the rows the test wrote before it.
    """
    conn = _cluster.connect(crdb_dsn)
    try:
        yield conn
    finally:
        conn.close()
