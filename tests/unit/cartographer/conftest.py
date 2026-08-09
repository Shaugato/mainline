# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
"""Fixtures and isolation for the blame-resolver suite.

The suite must pass with **no AWS credentials and no network**, and that is enforced
rather than promised: every socket call from this directory raises. The blame-link call
is a model call, and a suite that could quietly reach Bedrock would be asserting
something about a call it might never have made.

The corpus itself lives in :mod:`corpus`, beside this file.
"""

from __future__ import annotations

import socket
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

TESTS_DIR = Path(__file__).resolve().parent
REPO_ROOT = TESTS_DIR.parents[2]
CARTOGRAPHER_SRC = (
    REPO_ROOT / "verticals" / "mainline" / "packages" / "mainline-cartographer" / "src"
)
AGENTKIT_SRC = REPO_ROOT / "packages" / "mainline-agentkit" / "src"

for path in (str(CARTOGRAPHER_SRC), str(AGENTKIT_SRC), str(TESTS_DIR)):
    if path not in sys.path:  # pragma: no cover - import-time bootstrap
        sys.path.insert(0, path)

from corpus import (  # noqa: E402  (after the sys.path bootstrap)
    CLAUSE_GAS_TEST,
    CLAUSE_ISOLATION,
    CLAUSE_POISONED,
    COMMIT_HEX,
    FATALITY_ID,
    FATALITY_NARRATIVE,
    GAS_TEST_TEXT,
    ISOLATION_TEXT,
    NEAR_MISS_ID,
    NEAR_MISS_NARRATIVE,
    POISONED_TEXT,
    SITE,
)
from mainline_cartographer import (  # noqa: E402
    BlameBasis,
    BlameEdgeRow,
    BlameState,
    ClauseCandidate,
    ClosureRow,
    EventRow,
    VirulenceClass,
)


class NetworkAccessInTest(RuntimeError):
    """Raised when a test in this directory tries to open a socket."""


@pytest.fixture(autouse=True)
def no_network(monkeypatch: pytest.MonkeyPatch) -> None:
    """The blame-link call is a model call; this suite proves it replays without one."""

    def _refuse(*_args: Any, **_kwargs: Any) -> Any:
        raise NetworkAccessInTest(
            "a test in tests/unit/cartographer attempted an outbound connection. This "
            "suite must pass with no credentials and no network: use a cassette."
        )

    monkeypatch.setattr(socket.socket, "connect", _refuse, raising=True)
    monkeypatch.setattr(socket.socket, "connect_ex", _refuse, raising=True)
    monkeypatch.setattr(socket, "create_connection", _refuse, raising=True)


@pytest.fixture(autouse=True)
def isolated_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("MAINLINE_AGENT_PROVIDER", "MAINLINE_AGENT_ALLOW_LIVE", "AWS_REGION"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("MAINLINE_AGENT_PROVIDER", "cassette")
    monkeypatch.setenv("AWS_REGION", "ap-southeast-2")


@pytest.fixture
def fatality() -> EventRow:
    return EventRow(
        event_id=FATALITY_ID,
        site_id=SITE,
        occurred_at=datetime(2019, 4, 17, 4, 10, tzinfo=UTC),
        kind="incident",
        title="Thickener underflow line release, one fatality",
        narrative=FATALITY_NARRATIVE,
        source_sha256="ab" * 32,
        severity_gate=5,
        severity_basis="coded_field",
        control_classes=("energy_isolation", "isolation_verification", "atmospheric_testing"),
    )


@pytest.fixture
def near_miss() -> EventRow:
    return EventRow(
        event_id=NEAR_MISS_ID,
        site_id=SITE,
        occurred_at=datetime(2023, 11, 2, 13, 0, tzinfo=UTC),
        kind="near_miss",
        title="Confined space permit open with no attendant",
        narrative=NEAR_MISS_NARRATIVE,
        source_sha256="cd" * 32,
        severity_gate=2,
        severity_basis="human_rated",
        control_classes=("permit_control",),
    )


@pytest.fixture
def candidates() -> tuple[ClauseCandidate, ...]:
    return (
        ClauseCandidate(
            label="C1", clause_uuid=CLAUSE_ISOLATION, site_id=SITE, canon_text=ISOLATION_TEXT
        ),
        ClauseCandidate(
            label="C2", clause_uuid=CLAUSE_GAS_TEST, site_id=SITE, canon_text=GAS_TEST_TEXT
        ),
        ClauseCandidate(
            label="C3", clause_uuid=CLAUSE_POISONED, site_id=SITE, canon_text=POISONED_TEXT
        ),
    )


@pytest.fixture
def closure() -> ClosureRow:
    return ClosureRow(
        clause_uuid=CLAUSE_ISOLATION,
        as_of_commit=COMMIT_HEX,
        closure_gen=3,
        site_id=SITE,
        ancestor_events=(FATALITY_ID, NEAR_MISS_ID),
        ancestor_count=2,
        max_severity=5,
        virulence=VirulenceClass.BLOOD_FATAL,
        depth=1,
        truncated=False,
        computed_by="agent_identity:projector:0001",
        projector_ver="projector-1.0.0",
    )


@pytest.fixture
def inferred_edge() -> BlameEdgeRow:
    return BlameEdgeRow(
        event_id="aaaaaaaa-0000-0000-0000-00000000000f",
        clause_uuid=CLAUSE_ISOLATION,
        basis=BlameBasis.INFERRED_SEMANTIC,
        state=BlameState.PROVISIONAL,
    )
