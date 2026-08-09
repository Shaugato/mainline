# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""Session fixtures: a cluster, the reference vertical applied to it, and a tenancy.

Discovery and the skip contract live in :mod:`trappoint_model.cluster`, because
``tests/concurrency/`` needs exactly the same three paths and a second copy is a second
place for the skip message to go stale. What is here is what belongs to *this* test root:
the scratch database, the schema application, and the per-test connection.

The pure tests in ``test_model_pure.py`` need none of this and always run — but they
exercise the oracle only, and an oracle that agrees with itself has proved nothing about
the gate.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any

import pytest

psycopg = pytest.importorskip(
    "psycopg", reason="psycopg 3 is required to talk to CockroachDB; `uv sync` installs it"
)

from trappoint_model.cluster import (  # noqa: E402
    SKIP_REASON,
    Cluster,
    find_cluster,
    stop_cluster,
)
from trappoint_model.profiles import active_profile, register_profiles  # noqa: E402
from trappoint_model.refschema import (  # noqa: E402
    Fixture,
    apply_reference_vertical,
    drop_database,
    scratch_database,
    seed_fixture,
)


@pytest.fixture(scope="session", autouse=True)
def _hypothesis_profiles() -> None:
    """Register and select the profile before any test draws from a strategy."""
    from hypothesis import settings

    register_profiles()
    settings.load_profile(active_profile())


@pytest.fixture(scope="session")
def cluster(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Cluster]:
    """A reachable CockroachDB v26.2, or a skip that names what is missing."""
    found = find_cluster(tmp_path_factory.mktemp("crdb"), label="differential")
    if found is None:
        pytest.skip(SKIP_REASON)
    try:
        yield found
    finally:
        stop_cluster(found)


@dataclass
class Schema:
    """A scratch database carrying the whole reference vertical."""

    dsn: str
    name: str


@pytest.fixture(scope="session")
def schema(cluster: Cluster) -> Iterator[Schema]:
    """Apply the rendered reference vertical into a fresh database, once per session.

    A fresh *database* rather than a fresh ``site_id``: the substrate isolates tenants,
    but DDL is not tenanted and this fixture applies 109 files of it.
    """
    dsn, name = scratch_database(cluster.dsn)
    apply_reference_vertical(dsn)
    print(f"\n[differential] cluster: {cluster.provenance}\n[differential] database: {name}")
    try:
        yield Schema(dsn=dsn, name=name)
    finally:
        drop_database(cluster.dsn, name)


@pytest.fixture
def conn(schema: Schema) -> Iterator[Any]:
    """One autocommit connection per test, at SERIALIZABLE, stated explicitly.

    Autocommit rather than a rolled-back transaction: a refused statement must not be able
    to hide behind a rollback that also erases the rows written before it.
    """
    connection = psycopg.connect(schema.dsn, autocommit=True)
    connection.execute("SET default_transaction_isolation = 'serializable'")
    try:
        yield connection
    finally:
        connection.close()


@pytest.fixture
def fixture(conn: Any) -> Fixture:
    """A fresh tenancy, seeded with a signer, a credential and a reading-rate policy."""
    return seed_fixture(conn, f"t{uuid.uuid4().hex[:8]}")
