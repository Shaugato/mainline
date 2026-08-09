# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
#
# ruff.toml's per-file-ignores exempt `**/tests/**` from the assert, magic-value,
# annotation and private-access rules, for the reason every test suite needs them.
# This IS a test suite; it lives in `unweld/` rather than `tests/` because the
# schema-mutating suite is invoked as its own serial job (`-m schema -p no:xdist`)
# and the matrix it drives is library code its tests import. The exemption is
# declared here rather than by widening a glob in a file this worker does not own.
"""Fixtures for the schema-mutating suite.

Everything here is **session-scoped and serial**. ``testing-invariants.md`` §1: two suites
are exempt from the parallel-against-one-cluster architecture — migrations and unwelding —
and both get a serialised job on a disposable container. The marker is ``schema`` and the
invocation is ``-p no:xdist -m schema``; ``.github/workflows/schema.yml`` is where that is
written down for CI.

The matrix is collected **once**, in a session fixture, and the individual tests assert
against slices of it. Collecting per test would re-run every history once per mechanism and
would let a mutation from one test leak into another's baseline through an ordering change
nobody intended.
"""

from __future__ import annotations

import os
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

_PACKAGE_ROOT = Path(__file__).resolve().parents[1]
if str(_PACKAGE_ROOT) not in sys.path:
    sys.path.insert(0, str(_PACKAGE_ROOT))
if str(_PACKAGE_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(_PACKAGE_ROOT / "src"))

import cases  # noqa: E402

from trappoint_conformance.manifest import Manifest, find_manifest, load_manifest  # noqa: E402
from trappoint_conformance.runner import resolve_schema  # noqa: E402

from .container import REF_TREE, apply_tree, disposable_cluster  # noqa: E402
from .harness import collect, merge_gate_case_ids  # noqa: E402

PROFILE = os.environ.get("TRAPPOINT_UNWELD_PROFILE", "trappoint-ref")


def pytest_configure(config: pytest.Config) -> None:
    """Register the markers this suite uses, so ``--strict-markers`` stays usable."""
    config.addinivalue_line("markers", "schema: mutates schema; run serially, -p no:xdist")
    config.addinivalue_line("markers", "anomaly(id): the merge-gate anomaly this covers")


@pytest.fixture(scope="session")
def manifest() -> Manifest:
    """Load the specification the suite is asserting."""
    return load_manifest()


@pytest.fixture(scope="session")
def repo_root() -> Path:
    """Return the checkout root, located from the manifest rather than from ``__file__``."""
    return find_manifest().parents[2]


@pytest.fixture(scope="session")
def mutable_cluster(repo_root: Path) -> Iterator[str]:
    """Yield a DSN for a cluster this suite may break, with the reference tree applied."""
    try:
        with disposable_cluster() as dsn:
            tree = repo_root / REF_TREE
            if not tree.is_dir():
                pytest.skip(f"SKIP WITH REASON: no migration tree at {tree}")
            applied, failures = apply_tree(dsn, tree)
            if failures:
                names = ", ".join(f"{name} ({why})" for name, why in failures[:6])
                pytest.skip(
                    "SKIP WITH REASON: the reference vertical does not fully apply, so the "
                    "unwelding matrix would measure a partial schema. "
                    f"{applied} of {applied + len(failures)} statements applied; first "
                    f"failures: {names}"
                )
            yield dsn
    except RuntimeError as exc:
        pytest.skip(f"SKIP WITH REASON: {exc}")


@pytest.fixture(scope="session")
def mutable_conn(mutable_cluster: str) -> Iterator[Any]:
    """Yield an autocommit connection to the disposable cluster."""
    import psycopg

    conn = psycopg.connect(mutable_cluster, autocommit=True, application_name="trappoint-unweld")
    try:
        yield conn
    finally:
        conn.close()


@pytest.fixture(scope="session")
def matrix(manifest: Manifest, mutable_conn: Any) -> list[Any]:
    """Collect the whole unwelding matrix, once."""
    cases.load_all()
    schema = resolve_schema(PROFILE)
    return collect(manifest, mutable_conn, profile=PROFILE, schema=schema)


@pytest.fixture(scope="session")
def gated(manifest: Manifest) -> frozenset[str]:
    """Return the histories the depth floor applies to."""
    return merge_gate_case_ids(manifest, PROFILE)
