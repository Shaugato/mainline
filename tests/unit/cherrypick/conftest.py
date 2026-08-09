# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
"""Fixtures and isolation for the cherry-pick suite.

The one model call in this package is a T2 narration, and the suite proves it
replays without a network: every socket call from this directory raises, so
anything green here is green against a recorded interaction and nothing else.

The recorded responses are **hand-written**. That is the only honest provenance
available — AWS credentials are not valid on this build machine as of 2026-08-09.
They exercise the code path; they are not evidence of how the model behaves.
"""

from __future__ import annotations

import socket
import sys
from pathlib import Path
from typing import Any

import pytest

TESTS_DIR = Path(__file__).resolve().parent
REPO_ROOT = TESTS_DIR.parents[2]
CHERRYPICK_SRC = REPO_ROOT / "verticals" / "mainline" / "packages" / "mainline-cherrypick" / "src"
DOMAIN_SRC = REPO_ROOT / "verticals" / "mainline" / "packages" / "mainline-domain" / "src"
AGENTKIT_SRC = REPO_ROOT / "packages" / "mainline-agentkit" / "src"
JCS_SRC = REPO_ROOT / "packages" / "trappoint-jcs" / "src"

for path in (
    str(CHERRYPICK_SRC),
    str(DOMAIN_SRC),
    str(AGENTKIT_SRC),
    str(JCS_SRC),
    str(TESTS_DIR),
):
    if path not in sys.path:  # pragma: no cover - import-time bootstrap
        sys.path.insert(0, path)


class NetworkAccessInTest(RuntimeError):
    """Raised when a test in this directory tries to open a socket."""


@pytest.fixture(autouse=True)
def no_network(monkeypatch: pytest.MonkeyPatch) -> None:
    """The narration is a model call; this suite proves it replays without one."""

    def _refuse(*_args: Any, **_kwargs: Any) -> Any:
        raise NetworkAccessInTest(
            "a test in tests/unit/cherrypick attempted an outbound connection. "
            "The suite must pass with no credentials and no network: use a cassette."
        )

    monkeypatch.setattr(socket.socket, "connect", _refuse, raising=True)
    monkeypatch.setattr(socket.socket, "connect_ex", _refuse, raising=True)
    monkeypatch.setattr(socket, "create_connection", _refuse, raising=True)


@pytest.fixture(autouse=True)
def isolated_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Pin the offline provider so a stray live call fails loudly rather than costing money."""
    for name in ("MAINLINE_AGENT_PROVIDER", "MAINLINE_AGENT_ALLOW_LIVE", "AWS_REGION"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("MAINLINE_AGENT_PROVIDER", "cassette")
    monkeypatch.setenv("AWS_REGION", "ap-southeast-2")
