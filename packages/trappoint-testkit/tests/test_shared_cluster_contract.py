# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""The shared-cluster contract: never start two, never hang, never lie about the TTL.

Three of these tests need no cluster and assert the behaviour that matters most — that a
session with no database says so quickly instead of building thirteen. The last two need the
session's one cluster and skip with a reason when there is none, because a skipped run is not
evidence and this module will not pretend otherwise.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import time

import pytest
from trappoint_testkit import cluster

# ── the modes ────────────────────────────────────────────────────────────────────────────────


def test_none_is_a_decision_not_a_lookup() -> None:
    """`--crdb=none` must not probe, must not spawn, and must not raise."""
    assert cluster.ensure("none") is None


def test_an_unknown_mode_is_refused_by_name() -> None:
    with pytest.raises(ValueError, match="unknown crdb mode"):
        cluster.ensure("sometimes")


def test_reuse_never_starts_anything_when_nothing_answers() -> None:
    """A closed loopback port is refused in milliseconds; reuse mode reports None."""
    dead = "postgresql://root@127.0.0.1:1/defaultdb?sslmode=disable"
    started = time.monotonic()
    found = cluster.reuse(candidates=(dead,), env={})
    elapsed = time.monotonic() - started
    assert found is None
    assert elapsed < 30.0, (
        f"probing a dead port took {elapsed:.1f}s. The measured defect this package exists to "
        "remove was a 130.1s connect against a node that was never coming back."
    )


def test_a_dsn_is_repointed_without_string_surgery_on_the_url() -> None:
    """An env-supplied DSN may carry options, or no path component at all."""
    repointed = cluster.dsn_for_database(
        "postgresql://root@example.invalid:26257/defaultdb?sslmode=disable&connect_timeout=7",
        "tk_probe",
    )
    assert "dbname=tk_probe" in repointed
    assert "connect_timeout=7" in repointed
    assert "sslmode=disable" in repointed

    hostonly = cluster.dsn_for_database("postgresql://root@example.invalid:26257", "tk_probe")
    assert "dbname=tk_probe" in hostonly


# ── the guard ────────────────────────────────────────────────────────────────────────────────


def test_the_guard_cuts_the_discovery_ladder_at_its_first_rung() -> None:
    """`shutil.which` reports the cluster binaries absent, so no fixture reaches `docker run`."""
    guard = cluster.ProcessGuard("test")
    guard.install()
    try:
        assert shutil.which("docker") is None
        assert shutil.which("cockroach") is None
    finally:
        guard.uninstall()


def test_the_guard_refuses_to_launch_a_node_with_an_error_every_fixture_already_catches() -> None:
    """`FileNotFoundError` is an `OSError`, which those fixtures catch as "no Docker here"."""
    guard = cluster.ProcessGuard("no cluster for this session")
    guard.install()
    try:
        with pytest.raises(OSError, match="refuses to launch"):
            subprocess.run(["docker", "info"], capture_output=True, check=False)
        with pytest.raises(OSError, match="refuses to launch"):
            subprocess.Popen(["cockroach", "start-single-node"])
    finally:
        guard.uninstall()


def test_the_guard_is_narrow_and_leaves_every_other_executable_alone() -> None:
    guard = cluster.ProcessGuard("test")
    guard.install()
    try:
        done = subprocess.run(
            [sys.executable, "-c", "print('alive')"],
            capture_output=True,
            text=True,
            check=True,
        )
        assert done.stdout.strip() == "alive"
        assert shutil.which(sys.executable) is not None
    finally:
        guard.uninstall()


@pytest.mark.parametrize(
    ("argv", "expected"),
    [
        (["docker", "run"], "docker"),
        (["/usr/local/bin/docker", "ps"], "docker"),
        (["C:\\Program Files\\Docker\\docker.exe", "ps"], "docker.exe"),
        (["cockroach", "start-single-node"], "cockroach"),
        (["podman", "run"], "podman"),
        ([sys.executable, "-c", "pass"], None),
        (["git", "status"], None),
        ([], None),
        (None, None),
    ],
)
def test_the_guard_classifies_argv_the_way_it_claims(argv: object, expected: str | None) -> None:
    assert cluster.ProcessGuard.blocks(argv) == expected


def test_uninstall_puts_the_standard_library_back() -> None:
    before_which, before_run, before_popen = shutil.which, subprocess.run, subprocess.Popen
    guard = cluster.ProcessGuard("test")
    guard.install()
    assert shutil.which is not before_which
    guard.uninstall()
    assert shutil.which is before_which
    assert subprocess.run is before_run
    assert subprocess.Popen is before_popen
    guard.uninstall()  # idempotent


# ── the cluster itself ───────────────────────────────────────────────────────────────────────


@pytest.mark.requires_cluster
def test_each_module_gets_a_database_of_its_own(  # type: ignore[no-untyped-def]
    crdb_conn,
    crdb_database,
) -> None:
    current = crdb_conn.execute("SELECT current_database()").fetchone()[0]
    assert current == crdb_database.name, (
        "the module's connection is not pointed at the module's own database; two modules "
        "that both create `mainline.event` would collide"
    )
    crdb_conn.execute("CREATE TABLE isolation_probe (id INT PRIMARY KEY)")
    crdb_conn.execute("INSERT INTO isolation_probe VALUES (1)")
    assert crdb_conn.execute("SELECT count(*) FROM isolation_probe").fetchone()[0] == 1


@pytest.mark.requires_cluster
def test_the_database_is_pinned_to_the_cloud_gc_ttl_not_the_permissive_local_default(
    crdb_conn,  # type: ignore[no-untyped-def]
    crdb_database,  # type: ignore[no-untyped-def]
) -> None:
    """Local defaults to 14400; Cloud Basic is 4500. Local must not be the more permissive one.

    A time-travel test that passes at 14400 on a laptop is not evidence that it passes on
    Cloud, so the laptop is configured to the stricter value by construction.
    """
    row = crdb_conn.execute(
        f"SHOW ZONE CONFIGURATION FROM DATABASE {crdb_database.name}"
    ).fetchone()
    assert row is not None
    configuration = str(row[1])
    assert f"gc.ttlseconds = {cluster.CLOUD_GC_TTL_SECONDS}" in configuration, (
        f"the module database is not pinned to Cloud's GC TTL:\n{configuration}"
    )
