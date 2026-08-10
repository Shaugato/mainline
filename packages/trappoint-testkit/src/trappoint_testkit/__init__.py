# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""One CockroachDB for the whole test session, and a suite that refuses to hang.

Two facts, both measured on 2026-08-10, are the entire reason this package exists.

**Thirteen clusters.** A full-suite run started thirteen private single-node CockroachDB
containers concurrently, each claiming a quarter of the machine's memory. All thirteen exited
7 or 8, took the real node down with them, and left the Docker engine API answering HTTP 500.

**A hang, not a failure.** The run did not go red; it wedged. Fixtures connect with no
``connect_timeout``, so a dead node is an infinite wait, and ``pytest-timeout``'s thread
method cannot interrupt a hang inside session-scoped fixture setup. A connect to a black-holed
address on this machine took **130.1 s** to raise unset, and **3.1 s** with
``PGCONNECT_TIMEOUT=3``.

The fix touches none of the twenty-three files that spawn containers, because every one of
them checks an environment DSN first. This package publishes one DSN under all four spellings
the tree uses, publishes the ``compose.yaml`` image pin under all three image spellings, and —
when there is genuinely no cluster — makes the discovery ladder terminate at its first rung so
each fixture reaches its own ``pytest.skip`` in milliseconds.

Public surface::

    from trappoint_testkit import pinned_image, ensure, fresh_database

and the pytest plugin, which the repository-root ``conftest.py`` installs::

    pytest --crdb=auto|reuse|spawn|none

**WHAT IMPORTING THIS PACKAGE COSTS, AND WHY IT IS A DECLARED PROPERTY.** Measured on
2026-08-10 in GitHub Actions run 31372088311: all seven ``boundary`` jobs died before a
single assertion executed, on line 34 of *this file*. It re-exported the whole of
:mod:`~trappoint_testkit.cluster` eagerly, ``cluster`` imported ``psycopg`` at module scope,
and the boundary lane installs ``mainline-boundary`` and ``pytest`` and nothing else — on
purpose, because E3 measures what a *minimal* kernel-plane environment can reach. So
registering the ``--crdb`` option required a PostgreSQL driver, and reading the compose
image pin required one too.

Both halves are fixed and both are load-bearing. :mod:`~trappoint_testkit.cluster` now
imports the driver inside the functions that open a socket, so it is stdlib-only to import;
and the cluster names below are re-exported **lazily** through :pep:`562`, so
``from trappoint_testkit import pinned_image`` never touches ``cluster`` at all. The lazy
layer is not redundant with the first fix — it is what keeps the property true if someone
later adds a top-level driver import back to ``cluster``.

:mod:`~trappoint_testkit.image` stays eager: it is one regex over one file, it has no
third-party dependency of any kind, and the root ``conftest.py`` needs it during collection.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from .image import (
    IMAGE_ENV_NAMES,
    IMAGE_PIN_MARKER,
    PinNotFound,
    export_pin,
    find_compose,
    pinned_image,
    read_pin,
)

if TYPE_CHECKING:  # pragma: no cover - resolved by type checkers, never executed
    # Declared for mypy and for editors: a module-level `__getattr__` would otherwise make
    # every attribute of this package `Any`, which is a real loss of checking paid for a
    # cost nobody asked about. At runtime these names arrive through `__getattr__` below.
    from .cluster import (
        CLOUD_GC_TTL_SECONDS,
        DEFAULT_CONTAINER_NAME,
        DSN_ENV_NAMES,
        MODES,
        Database,
        DriverMissing,
        ProcessGuard,
        SharedCluster,
        connect,
        driver_error,
        dsn_for_database,
        ensure,
        export_dsn,
        fresh_database,
        pin_gc_ttl,
        probe,
        reuse,
        spawn,
    )

__version__ = "0.1.0"

#: Everything re-exported from :mod:`~trappoint_testkit.cluster`, and therefore everything
#: that is resolved on first access rather than at import. Kept as a frozenset so an
#: attribute miss is one hash lookup and an unknown name still raises ``AttributeError``.
_LAZY_FROM_CLUSTER: frozenset[str] = frozenset(
    {
        "CLOUD_GC_TTL_SECONDS",
        "DEFAULT_CONTAINER_NAME",
        "DSN_ENV_NAMES",
        "MODES",
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
    }
)

__all__ = [
    "CLOUD_GC_TTL_SECONDS",
    "DEFAULT_CONTAINER_NAME",
    "DSN_ENV_NAMES",
    "IMAGE_ENV_NAMES",
    "IMAGE_PIN_MARKER",
    "MODES",
    "Database",
    "DriverMissing",
    "PinNotFound",
    "ProcessGuard",
    "SharedCluster",
    "__version__",
    "connect",
    "driver_error",
    "dsn_for_database",
    "ensure",
    "export_dsn",
    "export_pin",
    "find_compose",
    "fresh_database",
    "pin_gc_ttl",
    "pinned_image",
    "probe",
    "read_pin",
    "reuse",
    "spawn",
]


def __getattr__(name: str) -> Any:
    """Resolve a cluster name on first access, then cache it in the module namespace.

    :pep:`562`. The cached write into ``globals()`` matters: it means the laziness is paid
    exactly once per name per process, so nothing that uses these in a loop pays for the
    indirection, and ``trappoint_testkit.connect is trappoint_testkit.connect`` stays true.
    """
    if name in _LAZY_FROM_CLUSTER:
        from . import cluster

        value = getattr(cluster, name)
        globals()[name] = value
        return value
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__() -> list[str]:
    """Report the full public surface, lazy names included, to ``dir()`` and to tab-complete."""
    return sorted(set(__all__) | set(globals()))
