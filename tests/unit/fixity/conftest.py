# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
"""Fixtures and isolation for the fixity-patrol suite.

Two properties are enforced rather than promised.

**No network.** Every socket call from this directory raises. The claim this
package makes about itself is that it holds no model and no driver; a suite that
could quietly open a socket would be asserting that about a process that might
have.

**No clock.** Every timestamp in the corpus is a fixed, timezone-aware literal. A
patrol is the component most likely to be re-run over historical data during an
investigation, and a test that passed because ``now()`` happened to fall on the
right side of a comparison is a test that will fail on a Tuesday.
"""

from __future__ import annotations

import socket
import sys
from pathlib import Path
from typing import Any

import pytest

TESTS_DIR = Path(__file__).resolve().parent
REPO_ROOT = TESTS_DIR.parents[2]
FIXITY_SRC = REPO_ROOT / "verticals" / "mainline" / "packages" / "mainline-fixity" / "src"
DOMAIN_SRC = REPO_ROOT / "verticals" / "mainline" / "packages" / "mainline-domain" / "src"

for path in (str(FIXITY_SRC), str(DOMAIN_SRC), str(TESTS_DIR)):
    if path not in sys.path:  # pragma: no cover - import-time bootstrap
        sys.path.insert(0, path)


class NetworkAccessInTest(RuntimeError):
    """Raised when a test in this directory tries to open a socket."""


@pytest.fixture(autouse=True)
def no_network(monkeypatch: pytest.MonkeyPatch) -> None:
    """This package holds no model and no driver; the suite proves it needs neither."""

    def _refuse(*_args: Any, **_kwargs: Any) -> Any:
        raise NetworkAccessInTest(
            "a test in tests/unit/fixity attempted an outbound connection. The fixity "
            "patrol holds no model and no database driver: nothing here needs a socket."
        )

    monkeypatch.setattr(socket.socket, "connect", _refuse, raising=True)
    monkeypatch.setattr(socket.socket, "connect_ex", _refuse, raising=True)
    monkeypatch.setattr(socket, "create_connection", _refuse, raising=True)


@pytest.fixture
def registry() -> Any:
    """The DIRECTRIX registry the corpus is written against."""
    from fixity_corpus import build_registry

    return build_registry()
