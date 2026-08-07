# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
"""Regenerate the committed cassettes.  Not a test — run it by hand after a prompt change.

    python -m tests.unit.recall_providers.make_fixture_cassettes
    # or, from the repo root:
    python tests/unit/recall_providers/make_fixture_cassettes.py

Two families are written, and they are not the same kind of artefact:

**Judge cassettes — ``provenance: "handwritten"``.**  AWS credentials are not valid on the
build machine, so no live Claude response exists to record.  These are authored contract
fixtures.  They are evidence about *our client* — that a refusal raises before content is
touched, that the repair path fires exactly once, that the dead letter carries its context,
that the cache breakpoint sits on the last system block — and they are evidence about
nothing else.  No test may assert model behaviour from them, and
``test_cassettes.py::test_no_test_asserts_model_behaviour_from_handwritten_cassettes``
keeps that honest by requiring live provenance for any such claim.

The requests are not typed out by hand: the judge itself is driven with a scripted
transport that captures the exact requests it builds, so a committed cassette always has
the digest the judge will compute at replay time.  Hand-editing a cassette breaks its
self-digest and the store refuses to load it.

**Embed cassettes — ``provenance: "surrogate"``.**  Recorded from the offline surrogate
embedder, which is deterministic and declared non-semantic.  They exercise the replay path
end to end without claiming to be vectors from any real model.  Recording the *real* spaces
is ``record.py``, on a machine that has the weights or the account.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[3]
PACKAGE_SRC = (
    REPO_ROOT / "verticals" / "mainline" / "packages" / "mainline-recall-agent" / "src"
)
if str(PACKAGE_SRC) not in sys.path:
    sys.path.insert(0, str(PACKAGE_SRC))
if str(Path(__file__).resolve().parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent))

from fixture_schema import (  # noqa: E402
    FACET_DEFINITIONS,
    FEW_SHOTS,
    PROMPT_VERSION,
    RUBRIC,
    RerankVerdict,
    judge_payload,
)

from mainline_recall_agent.providers.base import embed_text  # noqa: E402
from mainline_recall_agent.providers.cassette import CassetteStore, embed_request  # noqa: E402
from mainline_recall_agent.providers.judge import BedrockClaudeJudge, TransportReply  # noqa: E402
from mainline_recall_agent.providers.surrogate import SurrogateEmbedder  # noqa: E402
from mainline_recall_agent.providers.system_blocks import build_system_blocks  # noqa: E402
from mainline_recall_agent.providers.types import EMBED_DIM, ResolvedModel, Usage  # noqa: E402
from mainline_recall_agent.providers.vectors import vector_to_b64  # noqa: E402

CASSETTE_ROOT = REPO_ROOT / "tests" / "fixtures" / "cassettes" / "recall"
RECORDED_FACETS = ("mechanism", "recurrence_test")

VALID_BODY = json.dumps(
    {
        "verdicts": [
            {
                "candidate_ref": "FX-001",
                "relevance": "relevant",
                "shared_mechanism": "liberation of a toxic gas when two incompatible "
                "streams meet in a shared line",
                "shared_precondition": "a shared return header with no positive isolation "
                "while the pH interlock is not protecting",
                "justification": "The proposed bypass removes the same interlock whose "
                "absence allowed acidic wash water to meet cyanide-bearing solution, and "
                "the header arrangement is unchanged.",
            },
            {
                "candidate_ref": "FX-010",
                "relevance": "not_relevant",
                "shared_mechanism": "loss of containment of a corrosive liquid",
                "shared_precondition": "insufficient_evidence",
                "justification": "Same reagent handling discipline, but the proposed work "
                "does not create the residual-pressure condition the mechanism requires.",
            },
        ]
    }
)

# Extra field: caught by additionalProperties:false server-side and by extra='forbid'
# client-side.  The client-side catch is the one that runs on a cassette.
INVALID_BODY_EXTRA_FIELD = json.dumps(
    {
        "verdicts": [
            {
                "candidate_ref": "FX-001",
                "relevance": "relevant",
                "shared_mechanism": "toxic gas liberation",
                "shared_precondition": "shared header without isolation",
                "justification": "Same interlock, same header.",
                "confidence": 0.91,
            }
        ]
    }
)

INVALID_BODY_BAD_ENUM = json.dumps(
    {
        "verdicts": [
            {
                "candidate_ref": "FX-001",
                "relevance": "probably_relevant",
                "shared_mechanism": "toxic gas liberation",
                "shared_precondition": "shared header without isolation",
                "justification": "Same interlock, same header.",
            }
        ]
    }
)


class _ScriptedTransport:
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


def _judge(transport: _ScriptedTransport) -> BedrockClaudeJudge:
    return BedrockClaudeJudge(
        resolved_model=ResolvedModel(
            requested_tier="claude-opus-5",
            resolved_tier="claude-opus-5",
            profile_id="cassette://au-profile-unresolved",
            profile_arn=None,
            region="ap-southeast-2",
            source="cassette",
        ),
        transport=transport,
        prompt_version=PROMPT_VERSION,
        max_tokens=4096,
    )


def _scenario(
    store: CassetteStore,
    *,
    exposure_ref: str,
    replies: list[TransportReply],
    note: str,
) -> int:
    prefix = build_system_blocks(
        rubric=RUBRIC,
        facet_definitions=FACET_DEFINITIONS,
        few_shots=FEW_SHOTS,
        prompt_version=PROMPT_VERSION,
    )
    transport = _ScriptedTransport(replies)
    judge = _judge(transport)
    try:
        judge.judge(prefix, judge_payload(exposure_ref, ["FX-001", "FX-010"]), RerankVerdict)
    except Exception as exc:  # expected for the refusal / truncation / dead-letter scenarios
        print(f"  {exposure_ref}: raised {type(exc).__name__} (expected for this scenario)")
    for request, reply in transport.exchanges:
        store.save(
            "judge",
            request,
            reply.model_dump(mode="json"),
            provenance="handwritten",
            note=note,
            recorder="make_fixture_cassettes.py",
        )
    return len(transport.exchanges)


def write_judge_cassettes(store: CassetteStore) -> int:
    total = 0
    total += _scenario(
        store,
        exposure_ref="FX-EXP-CACHE-1",
        replies=[
            TransportReply(
                stop_reason="end_turn",
                text=VALID_BODY,
                usage=Usage(
                    input_tokens=180,
                    output_tokens=210,
                    cache_creation_input_tokens=1420,
                    cache_read_input_tokens=0,
                ),
            )
        ],
        note="cache scenario, call 1: prefix written to the cache",
    )
    total += _scenario(
        store,
        exposure_ref="FX-EXP-CACHE-2",
        replies=[
            TransportReply(
                stop_reason="end_turn",
                text=VALID_BODY,
                usage=Usage(
                    input_tokens=180,
                    output_tokens=205,
                    cache_creation_input_tokens=0,
                    cache_read_input_tokens=1420,
                ),
            )
        ],
        note="cache scenario, call 2: same system prefix bytes, prefix read from the cache",
    )
    total += _scenario(
        store,
        exposure_ref="FX-EXP-REFUSAL",
        replies=[
            TransportReply(
                stop_reason="refusal",
                text="",
                usage=Usage(input_tokens=175, output_tokens=3),
            )
        ],
        note="refusal: must raise ModelRefusal before content is touched",
    )
    total += _scenario(
        store,
        exposure_ref="FX-EXP-TRUNCATED",
        replies=[
            TransportReply(
                stop_reason="max_tokens",
                text='{"verdicts": [{"candidate_ref": "FX-001", "relev',
                usage=Usage(input_tokens=175, output_tokens=4096),
            )
        ],
        note="truncation: a cut-off answer is not an answer",
    )
    total += _scenario(
        store,
        exposure_ref="FX-EXP-REPAIR",
        replies=[
            TransportReply(
                stop_reason="end_turn",
                text=INVALID_BODY_EXTRA_FIELD,
                usage=Usage(input_tokens=180, output_tokens=120),
            ),
            TransportReply(
                stop_reason="end_turn",
                text=VALID_BODY,
                usage=Usage(
                    input_tokens=420,
                    output_tokens=210,
                    cache_read_input_tokens=1420,
                ),
            ),
        ],
        note="one repair attempt, then success",
    )
    total += _scenario(
        store,
        exposure_ref="FX-EXP-DEADLETTER",
        replies=[
            TransportReply(
                stop_reason="end_turn",
                text=INVALID_BODY_BAD_ENUM,
                usage=Usage(input_tokens=180, output_tokens=110),
            ),
            TransportReply(
                stop_reason="end_turn",
                text=INVALID_BODY_EXTRA_FIELD,
                usage=Usage(
                    input_tokens=430,
                    output_tokens=118,
                    cache_read_input_tokens=1420,
                ),
            ),
        ],
        note="two failures: dead letter, and never a third call",
    )
    return total


def write_embed_cassettes(store: CassetteStore) -> int:
    corpus = json.loads((store.root / "fixture_corpus.json").read_text(encoding="utf-8"))
    embedder = SurrogateEmbedder()
    written = 0
    for facet in RECORDED_FACETS:
        texts = [
            embed_text(
                activity_path=entry["activity_path"],
                asset_class=entry["asset_class"],
                facet=facet,
                cue_text=entry["facets"][facet],
            )
            for entry in corpus["cues"]
        ]
        vectors = embedder.embed(texts, facet)
        for text, vector in zip(texts, vectors, strict=True):
            store.save(
                "embed",
                embed_request(embed_model=embedder.model_id, facet=facet, text=text),
                {"embedding_b64": vector_to_b64(vector), "dim": EMBED_DIM},
                provenance="surrogate",
                note="fixture corpus, offline surrogate space (declared non-semantic)",
                recorder="make_fixture_cassettes.py",
            )
            written += 1
    return written


def main() -> int:
    store = CassetteStore(CASSETTE_ROOT)
    judge_count = write_judge_cassettes(store)
    embed_count = write_embed_cassettes(store)
    print(f"wrote {judge_count} judge cassettes and {embed_count} embed cassettes")
    print(f"under {store.root}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
