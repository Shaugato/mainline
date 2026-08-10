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
"""

from __future__ import annotations

from .cluster import (
    CLOUD_GC_TTL_SECONDS,
    DEFAULT_CONTAINER_NAME,
    DSN_ENV_NAMES,
    MODES,
    Database,
    ProcessGuard,
    SharedCluster,
    connect,
    dsn_for_database,
    ensure,
    export_dsn,
    fresh_database,
    pin_gc_ttl,
    probe,
    reuse,
    spawn,
)
from .image import (
    IMAGE_ENV_NAMES,
    IMAGE_PIN_MARKER,
    PinNotFound,
    export_pin,
    find_compose,
    pinned_image,
    read_pin,
)

__version__ = "0.1.0"

__all__ = [
    "CLOUD_GC_TTL_SECONDS",
    "DEFAULT_CONTAINER_NAME",
    "DSN_ENV_NAMES",
    "IMAGE_ENV_NAMES",
    "IMAGE_PIN_MARKER",
    "MODES",
    "Database",
    "PinNotFound",
    "ProcessGuard",
    "SharedCluster",
    "__version__",
    "connect",
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
