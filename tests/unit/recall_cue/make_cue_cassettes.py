# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
"""Regenerate the cue-synthesis cassettes.  Not a test — run it by hand after a prompt change.

    python tests/unit/recall_cue/make_cue_cassettes.py

The requests are never typed out.  Each scenario drives the **real** entry point with a
scripted transport that captures exactly the request the judge built, so a committed cassette
always carries the digest that replay will recompute.  Hand-editing a cassette breaks its
self-digest and ``CassetteStore`` refuses to load it.

Every cassette written here is ``provenance: "handwritten"``.  AWS credentials are not valid
on this machine, so there is no live Claude response to record; these are authored contract
fixtures and they are evidence about our pipeline only.

A prompt change moves ``SystemPrefix.prefix_digest()``, which moves every request digest,
which misses every cassette.  That is the intended cost of a prompt change: a commit that
regenerates the fixtures, not a silent deploy (ARCHITECTURE §8.2).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

from fixtures import (  # noqa: E402
    ACTIVITY_PATH,
    ASSET_CLASS_TYRE,
    BODY_EVENT_ANCHOR_FABRICATION,
    BODY_EVENT_FULL,
    BODY_EVENT_INSUFFICIENT,
    BODY_EXPOSURE_EXPOSED,
    BODY_EXPOSURE_ROUTINE,
    BODY_INVALID_EXTRA_FIELD,
    BODY_INVALID_NO_QUOTE,
    CASSETTE_MODEL,
    CASSETTE_ROOT,
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
from mainline_recall_agent.cue.prompts import PROMPT_VERSION  # noqa: E402
from mainline_recall_agent.cue.synthesise import (  # noqa: E402
    synthesise_event_cue,
    synthesise_exposure_cue,
)
from mainline_recall_agent.providers.cassette import CassetteStore  # noqa: E402
from mainline_recall_agent.providers.judge import BedrockClaudeJudge, TransportReply  # noqa: E402
from mainline_recall_agent.providers.types import Usage  # noqa: E402


class ScriptedTransport:
    """Returns scripted replies and captures the exact requests the judge built."""

    def __init__(self, replies: list[TransportReply]) -> None:
        self._replies = list(replies)
        self.exchanges: list[tuple[dict[str, Any], TransportReply]] = []

    def send(self, request: dict[str, Any]) -> TransportReply:
        if not self._replies:
            raise AssertionError("scripted transport exhausted: the judge called too often")
        reply = self._replies.pop(0)
        self.exchanges.append((json.loads(json.dumps(request)), reply))
        return reply


def make_judge(transport: ScriptedTransport) -> BedrockClaudeJudge:
    return BedrockClaudeJudge(
        resolved_model=CASSETTE_MODEL,
        transport=transport,
        prompt_version=PROMPT_VERSION,
        max_tokens=4096,
    )


def ok(text: str, *, cache_read: int = 0, cache_write: int = 0) -> TransportReply:
    return TransportReply(
        stop_reason="end_turn",
        text=text,
        usage=Usage(
            input_tokens=2400,
            output_tokens=320,
            cache_creation_input_tokens=cache_write,
            cache_read_input_tokens=cache_read,
        ),
    )


def _save(store: CassetteStore, transport: ScriptedTransport, note: str) -> int:
    for request, reply in transport.exchanges:
        store.save(
            "judge",
            request,
            reply.model_dump(mode="json"),
            provenance="handwritten",
            note=note,
            recorder="make_cue_cassettes.py",
        )
    return len(transport.exchanges)


def write_all(store: CassetteStore) -> int:
    total = 0

    scenarios: list[tuple[str, list[TransportReply], Any]] = [
        (
            "event, four populated facets, all anchors present in the source",
            [ok(BODY_EVENT_FULL, cache_write=2100)],
            lambda judge: synthesise_event_cue(
                EVENT_FULL, ACTIVITY_PATH, ASSET_CLASS_TYRE, judge=judge
            ),
        ),
        (
            "event, two facets take the per-facet insufficient_evidence escape",
            [ok(BODY_EVENT_INSUFFICIENT, cache_read=2100)],
            lambda judge: synthesise_event_cue(
                EVENT_INSUFFICIENT, ACTIVITY_PATH, ASSET_CLASS_TYRE, judge=judge
            ),
        ),
        (
            "event, a cue names an equipment tag absent from its source: anchor rejection",
            [ok(BODY_EVENT_ANCHOR_FABRICATION, cache_read=2100)],
            lambda judge: synthesise_event_cue(
                EVENT_ANCHOR_FABRICATION, ACTIVITY_PATH, ASSET_CLASS_TYRE, judge=judge
            ),
        ),
        (
            "event, the model refuses: silence_ledger(reason='model_refusal')",
            [TransportReply(stop_reason="refusal", text="", usage=Usage(input_tokens=2400))],
            lambda judge: synthesise_event_cue(
                EVENT_REFUSAL, ACTIVITY_PATH, ASSET_CLASS_TYRE, judge=judge
            ),
        ),
        (
            "event, schema invalid twice: dead letter, silence_ledger(reason='abstained')",
            [ok(BODY_INVALID_EXTRA_FIELD), ok(BODY_INVALID_NO_QUOTE)],
            lambda judge: synthesise_event_cue(
                EVENT_DEADLETTER, ACTIVITY_PATH, ASSET_CLASS_TYRE, judge=judge
            ),
        ),
        (
            "permit, four populated facets derived from scope, isolation plan and diff",
            [ok(BODY_EXPOSURE_EXPOSED, cache_write=2100)],
            lambda judge: synthesise_exposure_cue(
                PERMIT_EXPOSED, ISOLATION_EXPOSED, DIFF_EXPOSED, judge=judge
            ),
        ),
        (
            "permit, routine work: one mechanism and three honest escapes",
            [ok(BODY_EXPOSURE_ROUTINE, cache_read=2100)],
            lambda judge: synthesise_exposure_cue(
                PERMIT_ROUTINE, ISOLATION_ROUTINE, DIFF_ROUTINE, judge=judge
            ),
        ),
    ]

    for note, replies, run in scenarios:
        transport = ScriptedTransport(replies)
        judge = make_judge(transport)
        outcome = run(judge)
        print(f"  {note}\n    -> status={outcome.status} rows={len(outcome.rows)}")
        total += _save(store, transport, note)
    return total


def main() -> int:
    store = CassetteStore(CASSETTE_ROOT)
    written = write_all(store)
    print(f"wrote {written} judge cassettes under {store.root}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
