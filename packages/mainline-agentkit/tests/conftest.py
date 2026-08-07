# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""Make the package importable from a bare checkout, and bind the offline provider.

Two invariants this file exists to hold.

* ``pytest packages/mainline-agentkit`` must work on a clone with no ``uv sync``. The
  Apache substrate is what a stranger forks, and a suite that needs a workspace install
  is a suite the stranger does not run.
* **No test in this package may reach the network.** The transport fixture is the
  cassette provider, bound to the committed store. There is no fixture here that builds
  a ``BedrockTransport``, and the environment fixture clears every variable that could
  select the live path.
"""

from __future__ import annotations

import sys
from collections.abc import Iterator
from pathlib import Path

import pytest

_TESTS = Path(__file__).resolve().parent
_SRC = _TESTS.parent / "src"
for candidate in (_SRC, _TESTS):
    if candidate.is_dir() and str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

import make_cassettes as recipes  # noqa: E402 - the path shim above must run first
from mainline_agentkit import (  # noqa: E402
    AgentkitSettings,
    CassetteStore,
    CassetteTransport,
)
from mainline_agentkit.call import WARM_REGISTRY  # noqa: E402

CASSETTE_DIR = _TESTS / "cassettes"

#: The environment variables that could move this suite off the offline path.
LIVE_ENV_VARS = (
    "MAINLINE_AGENT_PROVIDER",
    "MAINLINE_AGENT_ALLOW_LIVE",
    "MAINLINE_AR1_FALLBACK",
    "MAINLINE_CASSETTE_DIR",
    "MAINLINE_CASSETTE_MODE",
    "MAINLINE_BEDROCK_REGION",
    "MAINLINE_WARM_TIMEOUT_S",
)


@pytest.fixture(autouse=True)
def _offline_environment(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Strip every live-path lever, and forget which prefixes were warmed."""
    for name in LIVE_ENV_VARS:
        monkeypatch.delenv(name, raising=False)
    WARM_REGISTRY.clear()
    yield
    WARM_REGISTRY.clear()


@pytest.fixture
def cassette_dir() -> Path:
    """The committed synthetic cassette store."""
    return CASSETTE_DIR


@pytest.fixture
def store(cassette_dir: Path) -> CassetteStore:
    """A replay-mode store over the committed cassettes."""
    return CassetteStore(cassette_dir, mode="replay")


@pytest.fixture
def transport(store: CassetteStore) -> CassetteTransport:
    """The offline transport every call test uses."""
    return CassetteTransport(store)


@pytest.fixture
def settings(cassette_dir: Path) -> AgentkitSettings:
    """Offline settings pointed at the committed store, with a short warm budget."""
    return AgentkitSettings(
        provider="cassette",
        cassette_dir=cassette_dir,
        cassette_mode="replay",
        warm_timeout_s=2.0,
    )


@pytest.fixture
def model_id() -> str:
    """The ``au.*`` inference-profile ARN the cassettes were recorded against."""
    return recipes.MODEL_ID


@pytest.fixture
def sentinel() -> str:
    """A fixed sentinel, so a test can compare two bodies byte for byte."""
    return recipes.SENTINEL


@pytest.fixture
def ctx_site() -> dict[str, object]:
    """The trusted context the committed cassettes were recorded with."""
    return dict(recipes.CTX_SITE)
