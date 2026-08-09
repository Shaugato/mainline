# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
"""The one model call: it explains, and it structurally cannot resolve.

Replayed over a cassette. The autouse fixture in ``conftest`` makes an outbound
socket raise, so anything green here is green against a recorded interaction and
nothing else. The recorded bodies are hand-written — AWS credentials are not valid
on this build machine as of 2026-08-09 — so they exercise the code path and are not
evidence of how the model behaves.
"""

from __future__ import annotations

import json

import pytest
from cherrypick_corpus import BASE_TEXT, FLEET_TEXT, SITE_TEXT, conflict
from mainline_agentkit import (
    NARRATION,
    CassetteStore,
    CassetteTransport,
    ModelRefused,
    build_request,
)
from mainline_cherrypick.narrate import (
    CONFLICT_SILENCE_SOURCE,
    compose_renderings,
    conflict_silence_row,
    narrate_conflict,
    trusted_context_for,
)

MODEL_ID = "arn:aws:bedrock:ap-southeast-2::inference-profile/au.anthropic.claude-opus-5"
_FIXED_SENTINEL = "MAINLINE-UNTRUSTED-0000000000000000"

BASE = "\n".join(BASE_TEXT)
OURS = "\n".join(SITE_TEXT)
THEIRS = "\n".join(FLEET_TEXT)

NARRATION_PAYLOAD = {
    "narrative": (
        "The two versions disagree about isolation. The site version applies isolation "
        "at the upstream isolation point and tags it; the fleet version applies it at "
        "every upstream isolation point, locks it, and adds a countersignature by the "
        "permit issuer. The site version has no countersignature step."
    ),
    "conflicting_clause_ids": ["66666666-6666-6666-6666-666666666666"],
    "resolution_proposed": "none",
}


def _record(store_dir, body):
    request = build_request(
        NARRATION,
        compose_renderings(BASE, OURS, THEIRS, source_sha256=conflict().ours_digest.hex()),
        trusted_context_for(conflict()),
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
            "input_tokens": 3100,
            "output_tokens": 210,
            "cache_creation_input_tokens": 1400,
            "cache_read_input_tokens": 0,
        },
    }


def _refusal_body():
    return {
        "stop_reason": "refusal",
        "model": "claude-opus-5",
        "content": [],
        "usage": {"input_tokens": 3100, "output_tokens": 0},
    }


def test_the_narration_describes_the_disagreement(tmp_path):
    transport = _record(tmp_path, _ok_body(NARRATION_PAYLOAD))
    validated = narrate_conflict(
        conflict(), BASE, OURS, THEIRS, transport=transport, model_id=MODEL_ID
    )
    assert "countersignature" in validated.value.narrative
    assert validated.value.resolution_proposed == "none"
    assert validated.model_id == MODEL_ID
    assert validated.prompt_version == NARRATION.prompt_version


def test_the_schema_carries_the_prohibition_not_the_prompt():
    # `resolution_proposed` is Literal["none"], so the CONSTRAINED DECODER cannot
    # emit anything else. An injection inside a procedure can at worst change a
    # field value that has exactly one legal value.
    schema = NARRATION.schema.schema
    field = schema["properties"]["resolution_proposed"]
    assert field.get("const") == "none" or field.get("enum") == ["none"]


def test_the_document_text_never_reaches_a_system_block():
    request = build_request(
        NARRATION,
        compose_renderings(BASE, OURS, THEIRS, source_sha256=conflict().ours_digest.hex()),
        trusted_context_for(conflict()),
        model_id=MODEL_ID,
        sentinel=_FIXED_SENTINEL,
    )
    system = json.dumps(request.body["system"])
    assert "countersigned by the permit issuer" not in system
    assert "upstream isolation point" not in system


def test_the_call_constructs_no_tool_surface():
    request = build_request(
        NARRATION,
        compose_renderings(BASE, OURS, THEIRS, source_sha256=conflict().ours_digest.hex()),
        trusted_context_for(conflict()),
        model_id=MODEL_ID,
        sentinel=_FIXED_SENTINEL,
    )
    body = json.dumps(request.body).lower()
    for key in ('"tools"', '"toolconfig"', '"tool_choice"', '"mcp_servers"'):
        assert key not in body
    for sampling in ('"temperature"', '"top_p"', '"top_k"'):
        assert sampling not in body


def test_the_trusted_context_withholds_the_recalled_resolution():
    # Putting a remembered resolution in front of the model would make echoing it
    # the easiest completion: a recommendation, in prose, from a component that is
    # forbidden to recommend.
    context = trusted_context_for(conflict())
    rendered = json.dumps(context).lower()
    for leak in ("resolution", "recall", "score", "severity", "due_by", "adopt"):
        assert leak not in rendered


def test_the_trusted_context_carries_only_identifiers_and_digests():
    context = trusted_context_for(conflict())
    assert set(context) == {
        "conflict_id",
        "clause_uuid",
        "labels",
        "base_digest",
        "ours_digest",
        "theirs_digest",
    }


def test_a_refusal_raises_rather_than_returning_an_empty_narrative(tmp_path):
    transport = _record(tmp_path, _refusal_body())
    with pytest.raises(ModelRefused):
        narrate_conflict(conflict(), BASE, OURS, THEIRS, transport=transport, model_id=MODEL_ID)


def test_a_refusal_becomes_a_row_this_package_deliberately_cannot_write(tmp_path):
    transport = _record(tmp_path, _refusal_body())
    try:
        narrate_conflict(conflict(), BASE, OURS, THEIRS, transport=transport, model_id=MODEL_ID)
    except ModelRefused as refusal:
        row = conflict_silence_row(
            refusal,
            conflict(),
            severity=5,
            input_sha256="ab" * 32,
            inference_profile_arn=MODEL_ID,
        )
    assert row.source == CONFLICT_SILENCE_SOURCE == "fleet_appraisal"
    assert row.reason == "model_refusal"
    assert row.subject_kind == "merge_conflict"
    # Only `agent_recaller` holds INSERT on silence_ledger. Returning the row
    # surfaces the grant boundary instead of hiding it behind a helper that would
    # fail at run time with a 42501.
    import mainline_cherrypick

    assert "silence" not in " ".join(mainline_cherrypick.STATEMENTS).lower()


def test_a_conflict_the_model_declined_to_describe_still_blocks():
    # The narration is T2 prose attached as evidence; its absence changes nothing
    # the gate reads. `open_conflicts` is a trigger-maintained projection over
    # `merge_conflict`, and adoption with a non-zero count is refused whether or not
    # anyone ever explained the disagreement.
    from cherrypick_corpus import propagation
    from mainline_cherrypick import AdoptionNotClean, PropState, advance

    with pytest.raises(AdoptionNotClean):
        advance(
            propagation(open_conflicts=1),
            PropState.ADOPTED,
            adopted_commit=bytes.fromhex("c3" * 32),
        )
