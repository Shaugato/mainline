# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
"""Fixtures and isolation for the Archivist suite.

Three properties are enforced rather than promised.

**No network.** Every socket call from this directory raises. This package's claim about
itself is that it holds no driver and no credential and that its model calls go through a
transport the caller injects; a suite that could quietly open a socket would be asserting
that about a process that might have.

**No clock.** Every timestamp in the corpus is a fixed, timezone-aware literal. An event
is bitemporal and ``CHECK ingested_before_occurrence`` compares two columns, so a test
that passed because ``now()`` fell on the right side of a comparison is a test that will
fail on a Tuesday.

**No installed distribution required.** The workspace member is added to ``sys.path``
here, the way ``tests/unit/fixity/conftest.py`` does, so the suite runs on a clean
checkout before ``uv sync`` has ever been executed.
"""

from __future__ import annotations

import socket
import sys
from pathlib import Path
from typing import Any

import pytest

TESTS_DIR = Path(__file__).resolve().parent
REPO_ROOT = TESTS_DIR.parents[2]
VERTICAL_PACKAGES = REPO_ROOT / "verticals" / "mainline" / "packages"

SRC_PATHS = (
    VERTICAL_PACKAGES / "mainline-archivist" / "src",
    VERTICAL_PACKAGES / "mainline-quarantine" / "src",
    VERTICAL_PACKAGES / "mainline-domain" / "src",
    REPO_ROOT / "packages" / "mainline-agentkit" / "src",
)

for path in (*(str(item) for item in SRC_PATHS), str(TESTS_DIR)):
    if path not in sys.path:  # pragma: no cover - import-time bootstrap
        sys.path.insert(0, path)


class NetworkAccessInTest(RuntimeError):
    """Raised when a test in this directory tries to open a socket."""


@pytest.fixture(autouse=True)
def no_network(monkeypatch: pytest.MonkeyPatch) -> None:
    """The Archivist reaches a model through an injected transport and a database through
    statements it hands back. Nothing in this suite needs a socket.
    """

    def _refuse(*_args: Any, **_kwargs: Any) -> Any:
        raise NetworkAccessInTest(
            "a test in tests/unit/archivist attempted an outbound connection. The "
            "Archivist holds no driver and no credential, and its model transport is "
            "injected: nothing here needs a socket."
        )

    monkeypatch.setattr(socket.socket, "connect", _refuse, raising=True)
    monkeypatch.setattr(socket.socket, "connect_ex", _refuse, raising=True)
    monkeypatch.setattr(socket, "create_connection", _refuse, raising=True)
