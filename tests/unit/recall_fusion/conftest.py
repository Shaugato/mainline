# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""Bootstrap for the fusion, calibration, admission and rerank suite.

Nothing here opens a socket, reads AWS credentials or touches a database. The suite runs on
a bare checkout, because the thing it protects — the arithmetic that decides whether a
fatality is raised — must be checkable by anyone who clones the repository, not only by a
provisioned CI.

The cassettes live beside this file rather than in the shared
``tests/fixtures/cassettes/recall`` tree. They are keyed by the digest of *this* worker's
rubric and payload shape, so they belong with the tests that pin that shape; a shared store
would couple two prompt versions that have no reason to move together.

The paths themselves live in :mod:`fusion_paths` under a unique module name — two suites in
one pytest session both have a ``conftest``, and ``from conftest import ...`` binds to
whichever was imported first.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from fusion_paths import CASSETTE_ROOT, ensure_import_paths  # noqa: E402

ensure_import_paths()

from mainline_recall_agent.providers.cassette import CassetteStore  # noqa: E402

__all__ = ["CASSETTE_ROOT"]


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers",
        "frozen: pins a serialised contract (feature spec, rubric bytes, prompt digest). A "
        "failure here is a deliberate change that must be reviewed, never a flake.",
    )


@pytest.fixture(scope="session")
def cassette_store() -> CassetteStore:
    """The suite's own digest-keyed cassette directory."""
    return CassetteStore(CASSETTE_ROOT)
