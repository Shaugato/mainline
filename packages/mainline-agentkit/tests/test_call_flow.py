# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""The call path end to end: quarantine, one retry, then dead letter.

The retry rule is the one worth staring at. §8.4: *a schema violation gets one retry
with the validator error appended, then dead-letters — never a free-text retry loop,
because a retry loop against an ill-posed prompt is how a silent extraction failure
becomes a silent memory gap.* Two cassette pairs cover both outcomes: one where the
second attempt validates, and one where it does not.
"""

from __future__ import annotations

import json

import make_cassettes as recipes
import pytest
from mainline_agentkit import (
    EXTRACTION,
    SENTINEL_PREFIX,
    TRIAGE,
    DeadLettered,
    UntrustedText,
    UntrustedTextInSystemPrompt,
    build_request,
    new_sentinel,
    quarantined_call,
)
from mainline_agentkit.profiles._model import CallProfile, Effort, Tier
from mainline_agentkit.profiles._rubric import COMMON_RUBRIC


def test_the_happy_path_returns_the_full_replayability_record(
    transport, model_id, sentinel, ctx_site
):
    result = quarantined_call(
        TRIAGE,
        recipes.DOC_PROCEDURE,
        ctx_site,
        transport=transport,
        model_id=model_id,
        sentinel=sentinel,
    )
    assert result.value.route == "procedure"
    assert result.attempts == 1
    assert result.stop_reason == "end_turn"

    provenance = result.provenance()
    # §8.2 claims replayability, not reproducibility. These are the fields that make
    # the weaker claim checkable.
    assert provenance["profile_id"] == "triage"
    assert provenance["prompt_version"] == TRIAGE.prompt_version
    assert provenance["prompt_sha256"] == TRIAGE.prompt_sha256()
    assert provenance["schema_version"] == TRIAGE.schema_version
    assert provenance["model_id"] == model_id
    assert len(provenance["input_sha256"]) == 64
    assert len(provenance["output_sha256"]) == 64
    assert provenance["usage"]["input_tokens"] > 0


def test_untrusted_text_lands_in_the_user_turn_and_only_there(model_id, sentinel, ctx_site):
    request = build_request(
        TRIAGE, recipes.DOC_PROCEDURE, ctx_site, model_id=model_id, sentinel=sentinel
    )
    system_text = " ".join(block["text"] for block in request.body["system"])
    assert "THICKENER 3" not in system_text
    user_text = " ".join(block["text"] for block in request.body["messages"][0]["content"])
    assert "THICKENER 3" in user_text
    assert sentinel in user_text
    assert user_text.count(sentinel) >= 3  # open, close, and the end-of-content marker


def test_the_trusted_context_precedes_the_untrusted_block(model_id, sentinel, ctx_site):
    request = build_request(
        TRIAGE, recipes.DOC_PROCEDURE, ctx_site, model_id=model_id, sentinel=sentinel
    )
    blocks = request.body["messages"][0]["content"]
    assert "<trusted_context>" in blocks[0]["text"]
    assert "THICKENER 3" not in blocks[0]["text"]
    assert blocks[1]["text"].startswith(f"<{sentinel}>")


def test_a_profile_that_puts_the_document_in_its_system_prompt_is_refused(model_id, sentinel):
    document = UntrustedText(
        text="4.2 Atmospheric testing. Oxygen shall be at least 19.5 %.",
        source_sha256="0" * 64,
    )
    leaky = CallProfile(
        profile_id="leaky_system",
        agent="archivist",
        tier=Tier.T1,
        effort=Effort.LOW,
        model_key="claude-opus-5",
        prompt_version="leaky.v1",
        system_blocks=(COMMON_RUBRIC, document.text),
        max_tokens=2000,
        thinking_floor_tokens=1000,
        output_model=TRIAGE.output_model,
    )
    with pytest.raises(UntrustedTextInSystemPrompt, match="never enters a system prompt"):
        build_request(leaky, document, {}, model_id=model_id, sentinel=sentinel)


def test_the_sentinel_is_fresh_per_request():
    sentinels = {new_sentinel() for _ in range(64)}
    assert len(sentinels) == 64
    assert all(value.startswith(SENTINEL_PREFIX) for value in sentinels)


def test_one_retry_carries_the_validator_error_and_then_succeeds(
    transport, model_id, sentinel, ctx_site
):
    result = quarantined_call(
        EXTRACTION,
        recipes.DOC_POISONED,
        ctx_site,
        transport=transport,
        model_id=model_id,
        sentinel=sentinel,
    )
    assert result.attempts == 2
    assert result.value.abstained is False
    # The second request carried the validator's own words, not a rephrased prompt.
    retry_body = transport.calls[-1].body
    retry_text = retry_body["messages"][0]["content"][-1]["text"]
    assert "did not validate against the required schema" in retry_text
    assert "Input should be a valid integer" in retry_text


def test_the_retry_budget_is_one_and_then_it_dead_letters(transport, model_id, sentinel, ctx_site):
    with pytest.raises(DeadLettered) as excinfo:
        quarantined_call(
            EXTRACTION,
            recipes.DOC_CONFLICT,
            ctx_site,
            transport=transport,
            model_id=model_id,
            sentinel=sentinel,
        )
    assert excinfo.value.attempts == 2
    assert len(transport.calls) == 2, "a third attempt was made; the retry budget is one"
    record = excinfo.value.record
    assert record["profile_id"] == "extraction"
    assert record["schema_version"] == EXTRACTION.schema_version
    assert record["untrusted_sha256"] == recipes.DOC_CONFLICT.sha256
    # The second failure was a CLIENT-SIDE constraint: `minLength` on `quote` was
    # stripped from the wire schema by decision A7 and re-imposed by the Pydantic model,
    # which is where this complaint comes from. A payload that the server considered
    # schema-conforming still did not survive.
    assert "String should have at least 1 character" in record["validator_error"]
    assert "minLength" not in json.dumps(EXTRACTION.schema.schema), (
        "the constraint that caught this must not be on the wire"
    )


def test_the_poisoned_document_produces_evidence_not_an_action(transport, model_id, sentinel):
    result = quarantined_call(
        TRIAGE,
        recipes.DOC_POISONED,
        {"site_code": "KAL-01", "corpus_commit": "0" * 64},
        transport=transport,
        model_id=model_id,
        sentinel=sentinel,
    )
    # The injection asked for a disposition and a defeater code. The schema has nowhere
    # to put either, the call had no tool to reach, and what came back is an abstention
    # that routes a human at the document.
    assert result.value.abstained is True
    assert "SUPERSEDED" not in json.dumps(result.value.model_dump())
    assert set(result.value.model_dump()) == {
        "route",
        "hazard_classes",
        "abstained",
        "basis_quote",
    }


def test_the_body_shape_is_stable_for_a_fixed_sentinel(model_id, sentinel, ctx_site):
    first = build_request(
        TRIAGE, recipes.DOC_PROCEDURE, ctx_site, model_id=model_id, sentinel=sentinel
    )
    second = build_request(
        TRIAGE, recipes.DOC_PROCEDURE, ctx_site, model_id=model_id, sentinel=sentinel
    )
    assert first.body == second.body
    assert first.body_json() == second.body_json()
    assert first.prefix_digest == second.prefix_digest
