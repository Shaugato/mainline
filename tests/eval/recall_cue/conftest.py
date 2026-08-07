# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
"""Fixtures for the cue-vs-narrative comparison harness.

The sample is built by replaying the committed cue cassettes from
``tests/unit/recall_cue``: the comparison must describe cues that came out of the real
pipeline, not hand-written strings, or it would describe the fixtures instead of the
product.  Same consequence as everywhere else in this domain — no network, no credentials.
"""

from __future__ import annotations

import socket
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[2]
PACKAGE_SRC = (
    REPO_ROOT / "verticals" / "mainline" / "packages" / "mainline-recall-agent" / "src"
)
UNIT_DIR = REPO_ROOT / "tests" / "unit" / "recall_cue"
CASSETTE_ROOT = UNIT_DIR / "cassettes"
#: The uv workspace installs ``trappoint-recall`` editable; adding its source tree as well
#: means "the ablation integration test was skipped because the package would not import"
#: can never be the reason this lane looks clean on a bare checkout.
TRAPPOINT_RECALL_SRC = REPO_ROOT / "packages" / "trappoint-recall" / "src"

for path in (str(PACKAGE_SRC), str(TRAPPOINT_RECALL_SRC), str(UNIT_DIR), str(HERE)):
    if path not in sys.path:  # pragma: no cover - import-time bootstrap
        sys.path.insert(0, path)


@pytest.fixture(autouse=True)
def no_network(monkeypatch: pytest.MonkeyPatch) -> None:
    def _refuse(*args: Any, **kwargs: Any) -> Any:
        raise RuntimeError(
            "tests/eval/recall_cue attempted an outbound connection; the comparison "
            "harness replays cassettes and must run offline"
        )

    monkeypatch.setattr(socket.socket, "connect", _refuse, raising=True)
    monkeypatch.setattr(socket.socket, "connect_ex", _refuse, raising=True)
    monkeypatch.setattr(socket, "create_connection", _refuse, raising=True)


@pytest.fixture
def replay_judge() -> Callable[[], Any]:
    from fixtures import CASSETTE_MODEL
    from mainline_recall_agent.cue.prompts import PROMPT_VERSION
    from mainline_recall_agent.providers.cassette import CassetteJudgeTransport, CassetteStore
    from mainline_recall_agent.providers.judge import BedrockClaudeJudge

    def factory() -> Any:
        return BedrockClaudeJudge(
            resolved_model=CASSETTE_MODEL,
            transport=CassetteJudgeTransport(CassetteStore(CASSETTE_ROOT)),
            prompt_version=PROMPT_VERSION,
            max_tokens=4096,
        )

    return factory


@pytest.fixture
def cue_sample(replay_judge: Callable[[], Any]) -> list[Any]:
    """Every scenario the cassettes cover, as ``CueOutcome`` objects.

    The refusal and dead-letter scenarios are deliberately included.  A comparison harness
    that quietly dropped its silenced subjects would report a corpus larger than the one the
    index actually holds, which is the same class of error the silence ledger exists to
    prevent.
    """
    from fixtures import (
        ACTIVITY_PATH,
        ASSET_CLASS_TYRE,
        DIFF_EXPOSED,
        DIFF_ROUTINE,
        EVENT_ANCHOR_FABRICATION,
        EVENT_DEADLETTER,
        EVENT_FULL,
        EVENT_INSUFFICIENT,
        EVENT_REFUSAL,
        ISOLATION_EXPOSED,
        ISOLATION_ROUTINE,
        PERMIT_EXPOSED,
        PERMIT_ROUTINE,
    )
    from mainline_recall_agent.cue.synthesise import (
        synthesise_event_cue,
        synthesise_exposure_cue,
    )

    events = (
        EVENT_FULL,
        EVENT_INSUFFICIENT,
        EVENT_ANCHOR_FABRICATION,
        EVENT_REFUSAL,
        EVENT_DEADLETTER,
    )
    outcomes = [
        synthesise_event_cue(event, ACTIVITY_PATH, ASSET_CLASS_TYRE, judge=replay_judge())
        for event in events
    ]
    outcomes.append(
        synthesise_exposure_cue(
            PERMIT_EXPOSED, ISOLATION_EXPOSED, DIFF_EXPOSED, judge=replay_judge()
        )
    )
    outcomes.append(
        synthesise_exposure_cue(
            PERMIT_ROUTINE, ISOLATION_ROUTINE, DIFF_ROUTINE, judge=replay_judge()
        )
    )
    return outcomes
