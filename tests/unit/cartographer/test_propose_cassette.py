# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
"""End to end over a cassette: one proposal, one poisoned clause, one refusal.

No AWS account, no network — the autouse fixture in ``conftest`` makes an outbound
socket raise, so anything green here is green against a recorded interaction and nothing
else. The cassettes are built in-process rather than committed: they are keyed on the
frozen prompt digest, and decision A13 makes a prompt edit a commit, so a committed
cassette would break every time the shared rubric moves and would teach a reader to
regenerate it without reading why.

The synthetic responses are **hand-written**, which is the only honest provenance
available: AWS credentials are not valid on this build machine as of 2026-08-09. They
exercise the code path; they are not evidence of how the model behaves.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest
from corpus import CLAUSE_ISOLATION, COMMIT_HEX, FABRICATED_QUOTE
from mainline_agentkit import (
    CassetteStore,
    CassetteTransport,
    ModelRefused,
    build_request,
)
from mainline_cartographer import (
    BLAME_LINK,
    BLAME_SILENCE_SOURCE,
    BlameBasis,
    BlameState,
    blame_silence_row,
    compose_untrusted,
    mint_candidates,
    propose_and_verify,
    propose_blame_links,
    trusted_context_for,
)

MODEL_ID = "arn:aws:bedrock:ap-southeast-2::inference-profile/au.anthropic.claude-opus-5"
UNTIL = datetime(2026, 12, 1, tzinfo=UTC)
_FIXED_SENTINEL = "MAINLINE-UNTRUSTED-0000000000000000"

GOOD_NARRATIVE_QUOTE = "the upstream isolation point was not locked"
GOOD_EVIDENCE_QUOTE = "isolation shall be applied at every upstream isolation point and locked"

#: One well-supported link (C1), one link whose evidence quote was fabricated after the
#: poisoned clause tried to instruct the reader (C3). The model is *not* expected to
#: have resisted; the verifier is expected to make the fabrication worthless.
PROPOSAL_PAYLOAD = {
    "abstained": False,
    "abstain_reason": "none",
    "links": [
        {
            "candidate_label": "C1",
            "link_kind": "control_named",
            "control_class": "energy_isolation",
            "narrative_quote": GOOD_NARRATIVE_QUOTE,
            "evidence_quote": GOOD_EVIDENCE_QUOTE,
            "confidence_band": "high",
        },
        {
            "candidate_label": "C3",
            "link_kind": "control_named",
            "control_class": "energy_isolation",
            "narrative_quote": GOOD_NARRATIVE_QUOTE,
            "evidence_quote": FABRICATED_QUOTE,
            "confidence_band": "high",
        },
    ],
    "injection_noted": True,
    "injection_note": "clause C3 contains a line addressed to the reader claiming a mode change",
}


def _record(store_dir, event, candidates, body):
    """Record one synthetic interaction against the identity this call will have."""
    request = build_request(
        BLAME_LINK,
        compose_untrusted(event, candidates),
        trusted_context_for(event, candidates),
        model_id=MODEL_ID,
        sentinel=_FIXED_SENTINEL,
    )
    CassetteStore(store_dir, mode="record").record(request, body)
    return CassetteTransport(CassetteStore(store_dir))


def _ok_body(payload):
    return {
        "stop_reason": "end_turn",
        "model": "claude-opus-5",
        "content": [
            {"type": "thinking", "thinking": "elided"},
            {"type": "text", "text": json.dumps(payload)},
        ],
        "usage": {
            "input_tokens": 4200,
            "output_tokens": 380,
            "cache_creation_input_tokens": 1800,
            "cache_read_input_tokens": 0,
        },
    }


def test_one_call_yields_one_row_and_one_recorded_drop(tmp_path, fatality, candidates):
    transport = _record(tmp_path, fatality, candidates, _ok_body(PROPOSAL_PAYLOAD))
    verified, validated = propose_and_verify(
        fatality,
        candidates,
        commit_id=COMMIT_HEX,
        provisional_until=UNTIL,
        transport=transport,
        model_id=MODEL_ID,
    )

    (edge,) = verified.edges
    assert edge.clause_uuid == CLAUSE_ISOLATION
    assert edge.basis is BlameBasis.INFERRED_SEMANTIC
    assert edge.state is BlameState.PROVISIONAL

    (drop,) = verified.dropped
    assert drop.candidate_label == "C3"
    assert drop.reason == "evidence_quote_unbound"

    # The injection is evidence, and it travelled.
    assert verified.injection_noted is True

    # The replayability quad rode along and reached the row.
    assert validated.model_id == MODEL_ID
    assert validated.prompt_version == BLAME_LINK.prompt_version
    assert edge.features["provenance"]["output_sha256"] == validated.output_sha256


def test_the_untrusted_block_never_reaches_a_system_prompt(fatality, candidates):
    request = build_request(
        BLAME_LINK,
        compose_untrusted(fatality, candidates),
        trusted_context_for(fatality, candidates),
        model_id=MODEL_ID,
        sentinel=_FIXED_SENTINEL,
    )
    system_text = "".join(str(block.get("text", "")) for block in request.body["system"])
    assert fatality.narrative not in system_text
    assert "tools" not in request.body
    assert "temperature" not in request.body
    # The failed control classes are trusted context, and they are what the verifier
    # checks a proposal against.
    user_text = json.dumps(request.body["messages"])
    assert "energy_isolation" in user_text


def test_a_refusal_is_a_row_not_an_empty_result(tmp_path, near_miss, candidates):
    """A precursor the model declined to reason about must still block the merge."""
    transport = _record(
        tmp_path,
        near_miss,
        candidates,
        {"stop_reason": "refusal", "model": "claude-opus-5", "content": [], "usage": {}},
    )
    with pytest.raises(ModelRefused) as caught:
        propose_blame_links(near_miss, candidates, transport=transport, model_id=MODEL_ID)

    row = blame_silence_row(
        caught.value,
        event=near_miss,
        input_sha256="0" * 64,
        model_id=MODEL_ID,
        inference_profile_arn=MODEL_ID,
    )
    mapping = row.to_mapping()
    assert mapping["source"] == BLAME_SILENCE_SOURCE == "blame_lapse"
    assert mapping["reason"] == "model_refusal"
    assert mapping["subject_id"] == near_miss.event_id
    # The severity is the event's own — a refusal over a fatality must not sort with a
    # refusal over a near miss.
    assert mapping["severity"] == near_miss.severity_gate
    assert mapping["arithmetic"]["fallback"] == "deterministic_channel"


def test_an_empty_candidate_set_is_a_recall_failure_not_an_abstention(fatality):
    with pytest.raises(ValueError, match="no candidate clauses"):
        propose_blame_links(fatality, [])


def test_minted_labels_are_positional_and_hide_every_uuid(fatality):
    minted = mint_candidates(
        [
            (CLAUSE_ISOLATION, fatality.site_id, "text one"),
            ("bbbbbbbb-0000-0000-0000-00000000000a", fatality.site_id, "text two"),
        ]
    )
    assert [candidate.label for candidate in minted] == ["C1", "C2"]
    untrusted = compose_untrusted(fatality, minted)
    assert CLAUSE_ISOLATION not in untrusted.text
    context = trusted_context_for(fatality, minted)
    assert context["candidate_labels"] == ["C1", "C2"]
    assert CLAUSE_ISOLATION not in json.dumps(context)
