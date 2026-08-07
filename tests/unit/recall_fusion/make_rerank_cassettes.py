# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""Regenerate the listwise-rerank cassettes. Not a test — run it after a rubric change.

    python tests/unit/recall_fusion/make_rerank_cassettes.py

**Provenance is ``handwritten``, and the distinction matters.** AWS credentials are not valid
on this build machine, so no live Claude response exists to record. These cassettes are
authored contract fixtures. They are evidence about *our client* — that a refusal returns a
degraded record rather than an empty candidate list, that the repair path fires exactly once,
that a ``relevant`` verdict without a citation is demoted, that the cache field is surfaced —
and they are evidence about nothing else. No assertion in this suite may claim anything about
the model's behaviour from them; the live claim belongs to the day-1 check against the
resolved ``au.*`` profile.

The requests are never typed out by hand. The real :class:`ListwiseReranker` is driven with a
scripted transport that captures exactly the requests it built, so a committed cassette
always carries the digest the reranker will compute at replay time. Hand-editing a cassette
breaks its self-digest and the store refuses to load it.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve().parent
_REPO_ROOT = _HERE.parents[2]
for _entry in (
    _HERE,
    _REPO_ROOT / "packages" / "trappoint-recall" / "src",
    _REPO_ROOT / "verticals" / "mainline" / "packages" / "mainline-recall-agent" / "src",
):
    if _entry.is_dir() and str(_entry) not in sys.path:
        sys.path.insert(0, str(_entry))

from mainline_recall_agent.providers.cassette import CassetteStore  # noqa: E402
from mainline_recall_agent.providers.judge import (  # noqa: E402
    BedrockClaudeJudge,
    TransportReply,
)
from mainline_recall_agent.providers.types import ResolvedModel, Usage  # noqa: E402
from mainline_recall_agent.rerank.listwise import ListwiseReranker  # noqa: E402
from mainline_recall_agent.rerank.rubric import PROMPT_VERSION  # noqa: E402
from rerank_fixture import CANDIDATES, exposure_for  # noqa: E402

CASSETTE_ROOT = _HERE / "cassettes"

CASSETTE_MODEL = ResolvedModel(
    requested_tier="claude-opus-5",
    resolved_tier="claude-opus-5",
    profile_id="cassette://au-profile-unresolved",
    profile_arn=None,
    region="ap-southeast-2",
    source="cassette",
)

_CITING_VERDICTS = [
    {
        "candidate_ref": "C01",
        "relevance": "relevant",
        "shared_mechanism": "liberation of a toxic gas when two incompatible streams meet "
        "inside a common line",
        "shared_precondition": "a shared return header with no positive isolation while the "
        "chemistry interlock is not protecting",
        "justification": "The proposed bypass removes the same interlock whose absence let "
        "acidic wash water reach cyanide-bearing solution, and the header arrangement is "
        "unchanged.",
        "evidence_strength": "decisive",
    },
    {
        "candidate_ref": "C02",
        "relevance": "not_relevant",
        "shared_mechanism": "release of stored gravitational energy inside a machine envelope",
        "shared_precondition": "insufficient_evidence",
        "justification": "The proposed work does not place anyone inside a machine envelope "
        "and creates no stored-energy condition.",
        "evidence_strength": "weak",
    },
    {
        "candidate_ref": "C03",
        "relevance": "not_relevant",
        "shared_mechanism": "loss of containment of a corrosive liquid",
        "shared_precondition": "residual pressure with no verification before breaking "
        "containment",
        "justification": "Same reagent discipline, but the proposed work does not break "
        "containment and creates no residual-pressure condition.",
        "evidence_strength": "supporting",
    },
]

VALID_BODY = json.dumps({"verdicts": _CITING_VERDICTS})

# Schema-valid, rubric-violating: 'relevant' with a mechanism that cites nothing. The client
# demotes it; the model is never given a second chance to say something it already said.
DEMOTION_BODY = json.dumps(
    {
        "verdicts": [
            {
                **_CITING_VERDICTS[0],
                "shared_mechanism": "insufficient_evidence",
                "justification": "These records both concern the leach circuit and feel "
                "related.",
            },
            _CITING_VERDICTS[1],
            _CITING_VERDICTS[2],
        ]
    }
)

# A verdict list missing C03 entirely. The candidate was shown and no verdict came back.
OMISSION_BODY = json.dumps({"verdicts": _CITING_VERDICTS[:2]})

# Extra field: caught by additionalProperties:false server-side and extra='forbid' here.
INVALID_EXTRA_FIELD = json.dumps(
    {"verdicts": [{**_CITING_VERDICTS[0], "confidence": 0.91}]}
)

INVALID_BAD_ENUM = json.dumps(
    {"verdicts": [{**_CITING_VERDICTS[0], "relevance": "probably_relevant"}]}
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


def _scenario(
    store: CassetteStore, *, scenario: str, replies: list[TransportReply], note: str
) -> int:
    transport = _ScriptedTransport(replies)
    judge = BedrockClaudeJudge(
        resolved_model=CASSETTE_MODEL,
        transport=transport,
        prompt_version=PROMPT_VERSION,
        max_tokens=4096,
    )
    reranker = ListwiseReranker(judge=judge)
    outcome = reranker.rerank(exposure_for(scenario), CANDIDATES)
    print(f"  {scenario}: degraded={outcome.degraded}")
    for request, reply in transport.exchanges:
        store.save(
            "judge",
            request,
            reply.model_dump(mode="json"),
            provenance="handwritten",
            note=note,
            recorder="make_rerank_cassettes.py",
        )
    return len(transport.exchanges)


def main() -> int:
    store = CassetteStore(CASSETTE_ROOT)
    total = 0
    total += _scenario(
        store,
        scenario="cache_call_one",
        replies=[
            TransportReply(
                stop_reason="end_turn",
                text=VALID_BODY,
                usage=Usage(
                    input_tokens=210,
                    output_tokens=320,
                    cache_creation_input_tokens=2560,
                    cache_read_input_tokens=0,
                ),
            )
        ],
        note="cache scenario, call 1: the frozen rubric prefix is written to the cache",
    )
    total += _scenario(
        store,
        scenario="cache_call_two",
        replies=[
            TransportReply(
                stop_reason="end_turn",
                text=VALID_BODY,
                usage=Usage(
                    input_tokens=212,
                    output_tokens=318,
                    cache_creation_input_tokens=0,
                    cache_read_input_tokens=2560,
                ),
            )
        ],
        note="cache scenario, call 2: different user turn, byte-identical prefix, cache read",
    )
    total += _scenario(
        store,
        scenario="refusal",
        replies=[
            TransportReply(
                stop_reason="refusal", text="", usage=Usage(input_tokens=205, output_tokens=4)
            )
        ],
        note="refusal: the reranker returns DegradedRerank and the merge still blocks on A+B",
    )
    total += _scenario(
        store,
        scenario="repair",
        replies=[
            TransportReply(
                stop_reason="end_turn",
                text=INVALID_EXTRA_FIELD,
                usage=Usage(input_tokens=210, output_tokens=140),
            ),
            TransportReply(
                stop_reason="end_turn",
                text=VALID_BODY,
                usage=Usage(
                    input_tokens=480, output_tokens=320, cache_read_input_tokens=2560
                ),
            ),
        ],
        note="one repair attempt carrying the validator error, then success",
    )
    total += _scenario(
        store,
        scenario="dead_letter",
        replies=[
            TransportReply(
                stop_reason="end_turn",
                text=INVALID_BAD_ENUM,
                usage=Usage(input_tokens=210, output_tokens=130),
            ),
            TransportReply(
                stop_reason="end_turn",
                text=INVALID_EXTRA_FIELD,
                usage=Usage(
                    input_tokens=486, output_tokens=138, cache_read_input_tokens=2560
                ),
            ),
        ],
        note="two schema failures: dead letter, DegradedRerank(abstained), never a third call",
    )
    total += _scenario(
        store,
        scenario="demotion",
        replies=[
            TransportReply(
                stop_reason="end_turn",
                text=DEMOTION_BODY,
                usage=Usage(
                    input_tokens=210, output_tokens=300, cache_read_input_tokens=2560
                ),
            )
        ],
        note="schema-valid but rubric-violating: 'relevant' with no citable mechanism",
    )
    total += _scenario(
        store,
        scenario="omission",
        replies=[
            TransportReply(
                stop_reason="end_turn",
                text=OMISSION_BODY,
                usage=Usage(
                    input_tokens=210, output_tokens=240, cache_read_input_tokens=2560
                ),
            )
        ],
        note="a candidate shown to the judge with no verdict returned: abstained, not dropped",
    )
    print(f"wrote {total} judge cassettes under {store.root}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
