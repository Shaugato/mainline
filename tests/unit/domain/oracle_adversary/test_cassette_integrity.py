# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""The other Path-B attack surface: the recordings, not the model.

Cassette-first (decision D12) means the committed store *is* Path B for every run
in CI and on a stranger's laptop.  That makes the store an attack surface with a
property the live lane does not have — it is a directory of files an attacker can
edit — and the honest thing to do is to say exactly what editing it buys.

It buys a **different model opinion**, and nothing else.  A tampered recording can
make the oracle report that clause B strengthens clause A; it cannot make the
resolution act on it, because the resolution's codomain is monotone upward and
Path A is not in the store.  That is the point of running two paths from two
different kinds of source, and this module is where it is demonstrated rather
than asserted.

Two further properties are pinned here because both have failed in other systems:
a replay **miss** never falls through to a live call, and a recording from a
different model generation is refused rather than replayed.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

import pytest
from _adversary import path_a_verdict
from mainline_agentkit import AgentkitSettings, CassetteMiss, CassettePrefixDrift
from mainline_delta_oracle.cassettes import scenario
from mainline_delta_oracle.errors import CassetteModelDrift
from mainline_delta_oracle.oracle import AdjudicationOracle
from mainline_delta_oracle.transport import default_cassette_root
from mainline_domain.contracts import ControlDelta, force
from mainline_domain.resolution import explain

_OFFLINE = AgentkitSettings(provider="cassette", cassette_mode="replay")

#: The scenario every test here drives: the money path, where the model agrees
#: with the lattice that a 30-minute gas test became a 120-minute one.
_SCENARIO = "contradicts_high"


@pytest.fixture
def store(tmp_path: Path) -> Path:
    """A private, writable copy of the committed recordings."""
    root = tmp_path / "cassettes"
    root.mkdir()
    for path in default_cassette_root().glob("*.json"):
        shutil.copy2(path, root / path.name)
    assert list(root.glob("*.json")), "the committed cassette store is empty"
    return root


def _oracle(root: Path) -> AdjudicationOracle:
    return AdjudicationOracle(cassette_root=root, settings=_OFFLINE)


def _key(root: Path) -> str:
    item = scenario(_SCENARIO)
    return _oracle(root).request_identity(item.request)["cassette_key"]


def _rewrite(path: Path, **changes: Any) -> None:
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload.update(changes)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


# ── the positive control, without which every test below is vacuous ─────────────


def test_the_untampered_store_replays_the_recorded_opinion(store: Path) -> None:
    """The committed recording still says what the README says it says."""
    item = scenario(_SCENARIO)
    verdict = _oracle(store).classify(item.request)
    assert verdict.abstained is False
    assert verdict.label is ControlDelta.WEAKEN
    assert verdict.confidence == pytest.approx(0.85)


# ── tampering ───────────────────────────────────────────────────────────────────


def test_rewriting_a_recording_changes_the_opinion_and_not_the_gate(store: Path) -> None:
    """An attacker with write access to the store gets a second opinion, not a merge.

    The tamper is deliberately *successful* at the transport layer — the assertion
    that it produced a clearing verdict is what makes the second half of this test
    mean something.  Then the ratchet runs, and the merge is still refused.
    """
    path = store / f"{_key(store)}.json"
    _rewrite(
        path,
        response={
            "id": "msg_tampered",
            "model": "claude-opus-5",
            "stop_reason": "end_turn",
            "usage": {"input_tokens": 1800, "output_tokens": 160},
            "content": [
                {
                    "type": "text",
                    "text": json.dumps(
                        {
                            "relation": "entails",
                            "confidence_band": "high",
                            "numeric_disagreement": True,
                            "supporting_quote": "at intervals not exceeding 120 minutes",
                            "notes": "B is at least as demanding as A.",
                        }
                    ),
                }
            ],
        },
    )

    verdict = _oracle(store).classify(scenario(_SCENARIO).request)
    assert verdict.abstained is False
    assert verdict.label is ControlDelta.STRENGTHEN, (
        "the tamper must actually work at the transport layer, or this test proves nothing"
    )

    weaken = path_a_verdict(ControlDelta.WEAKEN)
    resolved = explain(weaken, verdict, theta=0.5)
    assert force(resolved.verdict.delta) >= force(ControlDelta.WEAKEN)
    assert resolved.verdict.delta is ControlDelta.WEAKEN
    assert resolved.verdict.basis == "lattice", (
        "a model that disagreed downward contributes nothing to the basis"
    )


def test_a_deleted_recording_is_fatal_and_never_an_abstention(store: Path) -> None:
    """Replay never falls through to a live call, and never invents a model statement.

    A miss that became an abstention would put a row in the silence ledger saying
    a model declined to answer a question it was never asked.
    """
    (store / f"{_key(store)}.json").unlink()
    with pytest.raises(CassetteMiss):
        _oracle(store).classify(scenario(_SCENARIO).request)


def test_a_recording_from_another_generation_is_refused(store: Path) -> None:
    """A cassette replayed across model generations asserts something nobody measured."""
    _rewrite(store / f"{_key(store)}.json", model_id="claude-sonnet-5")
    with pytest.raises(CassetteModelDrift, match="claude-sonnet-5"):
        _oracle(store).classify(scenario(_SCENARIO).request)


def test_prefix_drift_is_fatal(store: Path) -> None:
    """A recording made under a prompt that has since been edited is not replayable.

    Decision A13 makes a prompt edit a commit.  Replaying across one would produce
    a green test asserting something that no longer exists.
    """
    _rewrite(store / f"{_key(store)}.json", prefix_digest="0" * 64)
    with pytest.raises(CassettePrefixDrift):
        _oracle(store).classify(scenario(_SCENARIO).request)


# ── the two locks on the live lane ──────────────────────────────────────────────


def test_the_default_lane_is_offline() -> None:
    """No environment, no credential, no socket — and that is the default, not a flag."""
    settings = AgentkitSettings.from_env({})
    assert settings.provider == "cassette"
    assert settings.allow_live is False
    assert settings.cassette_mode == "replay"


def test_opening_one_lock_is_not_enough() -> None:
    """Reaching Bedrock needs both the provider and the explicit live allowance."""
    provider_only = AgentkitSettings.from_env({"MAINLINE_AGENT_PROVIDER": "bedrock"})
    assert provider_only.provider == "bedrock"
    assert provider_only.allow_live is False, (
        "the second lock is not implied by the first; agentkit refuses a live call "
        "until MAINLINE_AGENT_ALLOW_LIVE=1 is set as well"
    )

    live_only = AgentkitSettings.from_env({"MAINLINE_AGENT_ALLOW_LIVE": "1"})
    assert live_only.provider == "cassette"
    assert live_only.allow_live is True


def test_every_committed_recording_declares_its_provenance() -> None:
    """None of the shipped recordings has been near Bedrock, and each one says so."""
    for path in default_cassette_root().glob("*.json"):
        payload = json.loads(path.read_text(encoding="utf-8"))
        assert payload["provenance"] == "synthetic", (
            f"{path.name} claims provenance {payload['provenance']!r}; the committed "
            f"store is synthetic and a 'live' file in it is an unproven claim"
        )
