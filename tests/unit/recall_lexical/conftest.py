# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""Bootstrap for the channel-D analyser suite.

Nothing here opens a socket, reads an environment variable or touches a database.  The whole
unit band runs on a bare checkout with no ``uv sync``, because the thing it protects — the
analyser — is the thing whose silent change is most expensive, and a check that only runs in a
fully provisioned CI is a check that does not run when it matters.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
PACKAGE_SRC = REPO_ROOT / "packages" / "trappoint-recall" / "src"
FIXTURES = Path(__file__).resolve().parent / "fixtures"

try:  # pragma: no cover - import-time bootstrap
    import trappoint_recall.lexical  # noqa: F401
except ImportError:  # pragma: no cover - import-time bootstrap
    sys.path.insert(0, str(PACKAGE_SRC))


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers", "golden: pins committed analyser behaviour; a failure is a re-index"
    )


@pytest.fixture(scope="session")
def fixtures_dir() -> Path:
    return FIXTURES
