# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""Fixtures for the kernel concurrency lane.

**Nothing here may run at import time, and that is not a style preference.** This
``conftest.py`` sits at the root of ``tests/concurrency/``, which also contains
``custody/`` and ``recall/`` — two lanes owned by other domains, each with its own
``conftest.py``. A module-level ``pytest.importorskip`` here raises ``Skipped`` while the
conftest is being imported, and pytest applies that to the **whole directory**: one
missing dependency of this lane would silently skip two lanes that do not depend on it.
So every import that can fail happens inside a fixture, where the skip reaches only the
tests that asked for it.

Fixture names are prefixed ``kernel_`` for the same reason. Sibling directories' fixtures
shadow these anyway — pytest applies the nearest ``conftest`` first — but a bare ``conn``
here would be one rename away from silently rebinding somebody else's.

Everything expensive is session-scoped: applying 109 migration files takes a few seconds
on a local node, which is why this lane runs against ONE database with per-test tenancies
rather than a fresh schema per test.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import pytest

if TYPE_CHECKING:  # pragma: no cover - typing only, never imported at collection
    from trappoint_model.cluster import Cluster
    from trappoint_model.refschema import Fixture

_MISSING_MODEL = (
    "the kernel concurrency lane drives the gate through `trappoint-model`, which supplies "
    "the reference-vertical applier and the operation adapter. `uv sync --package "
    "trappoint-model` installs it. NOTHING IN THIS LANE IS EVIDENCE WHEN IT SKIPS."
)
_MISSING_PSYCOPG = "psycopg 3 is required to talk to CockroachDB; `uv sync` installs it"


def _psycopg() -> Any:
    """Import psycopg, or skip only the test that asked for it."""
    return pytest.importorskip("psycopg", reason=_MISSING_PSYCOPG)


def _model() -> Any:
    """Import ``trappoint_model``, or skip only the test that asked for it."""
    return pytest.importorskip("trappoint_model", reason=_MISSING_MODEL)


@dataclass
class Schema:
    """A scratch database carrying the whole reference vertical."""

    dsn: str
    name: str


@pytest.fixture(scope="session")
def kernel_cluster(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Cluster]:
    """A reachable CockroachDB v26.2, or a skip that names what is missing."""
    _model()
    from trappoint_model.cluster import SKIP_REASON, find_cluster, stop_cluster

    found = find_cluster(tmp_path_factory.mktemp("crdb"), label="concurrency")
    if found is None:
        pytest.skip(SKIP_REASON)
    try:
        yield found
    finally:
        stop_cluster(found)


@pytest.fixture(scope="session")
def kernel_schema(kernel_cluster: Cluster) -> Iterator[Schema]:
    """The reference vertical, applied once, into a database this lane owns."""
    from trappoint_model.refschema import (
        apply_reference_vertical,
        drop_database,
        scratch_database,
    )

    dsn, name = scratch_database(kernel_cluster.dsn, prefix="trappoint_conc")
    apply_reference_vertical(dsn)
    print(f"\n[concurrency] cluster: {kernel_cluster.provenance}\n[concurrency] database: {name}")
    try:
        yield Schema(dsn=dsn, name=name)
    finally:
        drop_database(kernel_cluster.dsn, name)


@pytest.fixture
def kernel_conn(kernel_schema: Schema) -> Iterator[Any]:
    """One autocommit connection per test, at SERIALIZABLE, stated explicitly.

    Autocommit rather than a rolled-back transaction: a refused statement must not be able
    to hide behind a rollback that also erases the rows written before it.
    """
    psycopg = _psycopg()
    connection = psycopg.connect(kernel_schema.dsn, autocommit=True)
    connection.execute("SET default_transaction_isolation = 'serializable'")
    try:
        yield connection
    finally:
        connection.close()


@pytest.fixture
def kernel_fixture(kernel_conn: Any) -> Fixture:
    """A fresh tenancy: a signer, a credential and a reading-rate policy."""
    from trappoint_model.refschema import seed_fixture

    return seed_fixture(kernel_conn, f"c{uuid.uuid4().hex[:8]}")
