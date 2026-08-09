# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""Fixtures, markers, and the one import that makes the corpus exist.

**The loader call is the whole point of this file.** ``cases.load_all()`` imports every case
module, and importing a case module is what registers it with
``trappoint_conformance.runner``. Without it the registry holds one case — ``CF-01``, which
the runner registers itself — and every totality assertion below would be measuring an empty
corpus and passing.

**Anomaly markers are applied from the manifest, not typed by hand.** ``testing-invariants``
§2 asks for ``@pytest.mark.anomaly("A2")`` on every test so a generator can emit
``ANOMALY_COVERAGE.md`` from collected markers. Typing them into the case modules would put
the anomaly mapping in two places — the manifest and the decorators — and two places is one
too many for the thing CI fails on. So the marker is *applied* at collection from
``manifest.toml``, which means the coverage report is still generated from collected markers
exactly as asked, and the mapping still has one owner. A statically decorated test keeps its
own marker as well; both are collected.
"""

from __future__ import annotations

import os
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

_PACKAGE_ROOT = Path(__file__).resolve().parents[1]
for candidate in (_PACKAGE_ROOT, _PACKAGE_ROOT / "src"):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

import cases  # noqa: E402

from trappoint_conformance.manifest import Manifest, find_manifest, load_manifest  # noqa: E402

CASE_ID_KEY = "conformance_case_id"


def pytest_configure(config: pytest.Config) -> None:
    """Register markers, and load the corpus before anything is collected."""
    config.addinivalue_line("markers", "anomaly(id): the merge-gate anomaly A1-A14 covered")
    config.addinivalue_line("markers", "schema: mutates schema; run serially, -p no:xdist")
    config.addinivalue_line("markers", "db: needs a migrated cluster")
    cases.load_all()


def pytest_collection_modifyitems(
    config: pytest.Config,  # noqa: ARG001 - pytest fixes this signature
    items: list[pytest.Item],
) -> None:
    """Attach each case's manifest anomaly to the test that runs it."""
    try:
        manifest = load_manifest()
    except Exception:  # noqa: BLE001 — no manifest is its own failure elsewhere
        return
    by_id = {case.id: case for case in manifest.cases}
    for item in items:
        case_id = _case_id_of(item)
        if case_id is None:
            continue
        case = by_id.get(case_id)
        if case is None or case.anomaly == "none":
            continue
        item.add_marker(pytest.mark.anomaly(case.anomaly))


def _case_id_of(item: pytest.Item) -> str | None:
    """Recover the ``CF-*`` id a parametrised test is running, from its own id."""
    name = item.name
    start = name.find("CF-")
    if start < 0:
        return None
    tail = name[start : start + 5]
    return tail if len(tail) == 5 and tail[3:].isdigit() else None


@pytest.fixture(scope="session")
def manifest() -> Manifest:
    """Load the specification the whole suite asserts against."""
    return load_manifest()


@pytest.fixture(scope="session")
def repo_root() -> Path:
    """Return the checkout root, located from the manifest rather than from ``__file__``."""
    return find_manifest().parents[2]


@pytest.fixture(scope="session")
def dsn() -> str | None:
    """The cluster to assert against, or ``None``.

    ``TRAPPOINT_DSN`` / ``LOCAL_DSN``, exactly as ``trappoint-conform`` reads them, so a
    developer who can run the CLI can run the suite with no second thing to configure.
    """
    for key in ("TRAPPOINT_DSN", "LOCAL_DSN"):
        value = os.environ.get(key)
        if value:
            return value
    return None


@pytest.fixture(scope="session")
def profile() -> str:
    """Which binding to assert. ``trappoint-ref`` is the one that is green at K1."""
    return os.environ.get("TRAPPOINT_PROFILE", "trappoint-ref")


@pytest.fixture(scope="session")
def conn(dsn: str | None) -> Iterator[Any]:
    """A connection to the cluster, or a skip naming what is missing."""
    if dsn is None:
        pytest.skip(
            "SKIP WITH REASON: no TRAPPOINT_DSN or LOCAL_DSN. These assertions are about "
            "what a database does; without one there is nothing to assert and pretending "
            "otherwise would be a suite that passes by absence. `just up && just migrate`."
        )
    import psycopg

    try:
        connection = psycopg.connect(
            dsn, autocommit=True, application_name="trappoint-conform:pytest"
        )
    except psycopg.Error as exc:
        pytest.skip(f"SKIP WITH REASON: cannot connect to the cluster: {exc}")
    try:
        yield connection
    finally:
        connection.close()


@pytest.fixture(scope="session")
def report(manifest: Manifest, conn: Any, profile: str) -> dict[str, Any]:
    """Run the whole suite once and index the results by case id.

    Session-scoped and shared, for two reasons. Each case builds a world of a dozen rows,
    so re-running the suite per assertion would multiply the wall clock for no additional
    information — the three assertions in ``test_conformance_cases`` read three fields of
    one observation. And it lives *here*, in the conftest, rather than beside those
    assertions, because ``test_taxonomy_totality`` needs the same observations to make the
    dynamic half of the totality claim: what the run actually saw, not a list somebody
    maintained.
    """
    import os as _os

    from trappoint_conformance.runner import resolve_schema, run

    cases.load_all()
    satisfied = tuple(
        token.strip()
        for token in _os.environ.get("TRAPPOINT_REQUIRES", "").split(",")
        if token.strip()
    )
    outcome = run(
        manifest,
        profile=profile,
        conn=conn,
        schema=resolve_schema(profile),
        satisfied_requirements=satisfied,
    )
    return {result.case.id: result for result in outcome.results}


@pytest.fixture(scope="session")
def observations(report: dict[str, Any]) -> tuple[tuple[str, str, str], ...]:
    """Every ``(case_id, sqlstate, message)`` the run observed."""
    return tuple(
        (case_id, result.observed.sqlstate, result.observed.message)
        for case_id, result in report.items()
        if result.observed is not None
    )
