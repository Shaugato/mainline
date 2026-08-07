# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
"""Fixtures and environment isolation for the recall provider suite.

The suite must pass with **no AWS credentials and no network**, so every fixture here
either uses the committed cassettes or pure client-side arithmetic.  Nothing in this
directory may open a socket.
"""

from __future__ import annotations

import os
import socket
import sys
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
PACKAGE_SRC = (
    REPO_ROOT / "verticals" / "mainline" / "packages" / "mainline-recall-agent" / "src"
)
CASSETTE_ROOT = REPO_ROOT / "tests" / "fixtures" / "cassettes" / "recall"

# Work whether or not the uv workspace has been synced: an editable install wins, and a
# bare checkout still runs.
try:  # pragma: no cover - import-time bootstrap
    import mainline_recall_agent  # noqa: F401
except ImportError:  # pragma: no cover - import-time bootstrap
    sys.path.insert(0, str(PACKAGE_SRC))

#: Every environment variable this package reads.  Cleared before each test so a developer
#: shell that has `MAINLINE_RECALL_PROVIDER=bedrock` set cannot make CI pass for the wrong
#: reason — or fail for one.
_OWNED_ENV = (
    "MAINLINE_RECALL_PROVIDER",
    "MAINLINE_RECALL_CASSETTE_MODE",
    "MAINLINE_RECALL_ALLOW_NETWORK",
    "MAINLINE_RECALL_CASSETTE_DIR",
    "MAINLINE_RECALL_EMBED_MODEL",
    "MAINLINE_RECALL_INDEX_GEN",
    "MAINLINE_RECALL_REQUIRE_FITTED_PROJECTION",
    "MAINLINE_BGE_REVISION",
    "AWS_REGION",
)


class NetworkAccessInTest(RuntimeError):
    """Raised when a test in this directory tries to open a socket.

    The suite's stated property is that it passes with no AWS credentials and no network.
    A docstring claiming that is worth nothing: a provider could acquire a lazy boto3
    session, time out after 60 s, fall back to something plausible, and the suite would go
    green while the offline guarantee quietly died.  So the guarantee is enforced.
    """


@pytest.fixture(autouse=True)
def no_network(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make the 'runs with no network' claim structural rather than aspirational.

    Only outbound connection establishment is blocked, which is the operation that would
    reach Bedrock or Hugging Face.  Socket construction itself is left alone so that
    anything merely inspecting the module keeps working.
    """

    def _refuse(*args: Any, **kwargs: Any) -> Any:
        raise NetworkAccessInTest(
            "a test in tests/unit/recall_providers attempted an outbound connection. "
            "This suite must pass with no credentials and no network: use a cassette, a "
            "stub client, or an explicit skip with a reason."
        )

    monkeypatch.setattr(socket.socket, "connect", _refuse, raising=True)
    monkeypatch.setattr(socket.socket, "connect_ex", _refuse, raising=True)
    monkeypatch.setattr(socket, "create_connection", _refuse, raising=True)


@pytest.fixture(autouse=True)
def isolated_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in _OWNED_ENV:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("MAINLINE_RECALL_PROVIDER", "cassette")
    monkeypatch.setenv("MAINLINE_RECALL_CASSETTE_DIR", str(CASSETTE_ROOT))
    monkeypatch.setenv("AWS_REGION", "ap-southeast-2")
    from mainline_recall_agent.providers.projection import load_projection

    load_projection.cache_clear()


@pytest.fixture
def cassette_root() -> Path:
    return CASSETTE_ROOT


@pytest.fixture
def store():  # type: ignore[no-untyped-def]
    from mainline_recall_agent.providers.cassette import CassetteStore

    return CassetteStore(CASSETTE_ROOT)


@pytest.fixture
def package_src() -> Path:
    return PACKAGE_SRC


@pytest.fixture
def fixture_corpus() -> list[dict[str, object]]:
    from mainline_recall_agent.providers.cassette import CassetteStore
    from mainline_recall_agent.providers.record import load_fixture_corpus

    os.environ.setdefault("MAINLINE_RECALL_CASSETTE_DIR", str(CASSETTE_ROOT))
    return load_fixture_corpus(CassetteStore(CASSETTE_ROOT))
