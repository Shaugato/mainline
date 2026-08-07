# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""Refusal is silence, silence is a row, and truncation is fatal.

Decisions A5 and A8. The subtle test in here is
``test_stop_reason_is_checked_before_content``: the refusal cassette carries content
that is perfectly readable prose and *not* JSON. If the code ever parsed content before
classifying ``stop_reason``, this suite would report a ``SchemaViolation`` instead of a
``ModelRefused`` — a difference that decides whether a refused precursor becomes a
silence-ledger row or a dead letter nobody reads.
"""

from __future__ import annotations

from datetime import datetime

import make_cassettes as recipes
import pytest
from mainline_agentkit import (
    EXTRACTION,
    KNOWN_STOP_REASONS,
    SILENCE_REASONS,
    SILENCE_SOURCES,
    ModelRefused,
    ModelResponse,
    Outcome,
    SilenceRow,
    TruncatedResponse,
    UnknownStopReason,
    Usage,
    classify,
    interpret,
    quarantined_call,
    silence_row_for_refusal,
)

REFUSAL_CTX = {"site_code": "KAL-01", "corpus_commit": "1" * 64}
TRUNCATION_CTX = {"site_code": "KAL-01", "corpus_commit": "2" * 64}
UNKNOWN_CTX = {"site_code": "KAL-01", "corpus_commit": "3" * 64}
GUARDRAIL_CTX = {"site_code": "KAL-01", "corpus_commit": "4" * 64}


def _call(context, transport, model_id, sentinel, document=None):
    return quarantined_call(
        EXTRACTION,
        document or recipes.DOC_PROCEDURE,
        context,
        transport=transport,
        model_id=model_id,
        sentinel=sentinel,
    )


class ExplodingBlock(dict):
    """A content block that refuses to be read. The trap for rule 1."""

    def get(self, *args, **kwargs):  # noqa: ARG002 - the signature must match dict.get
        raise AssertionError("content was read before stop_reason was classified")


def test_interpret_never_touches_content():
    # The sharp version of rule 1: `interpret` classifies a refusal without reading a
    # single content block, proved by a block that raises if anyone looks at it.
    response = ModelResponse(
        stop_reason="refusal",
        content=(ExplodingBlock(),),
        usage=Usage(),
        model="au.anthropic.claude-opus-5",
        raw={"stop_reason": "refusal"},
    )
    with pytest.raises(ModelRefused):
        interpret(response, max_tokens=1000)
    # And the trap is live: anything that did read content would have blown up.
    with pytest.raises(AssertionError, match="before stop_reason"):
        response.last_text_block()


def test_stop_reason_is_checked_before_content(transport, model_id, sentinel):
    with pytest.raises(ModelRefused) as excinfo:
        _call(REFUSAL_CTX, transport, model_id, sentinel)
    assert excinfo.value.category == "model_refusal"
    assert excinfo.value.stop_reason == "refusal"
    # Exactly one call: a refusal is not retried. A retry here would spend the one
    # permitted attempt on a document the model has already declined.
    assert len(transport.calls) == 1


def test_max_tokens_is_fatal_and_never_absorbed(transport, model_id, sentinel):
    with pytest.raises(TruncatedResponse) as excinfo:
        _call(TRUNCATION_CTX, transport, model_id, sentinel)
    assert excinfo.value.stop_reason == "max_tokens"
    assert excinfo.value.max_tokens == EXTRACTION.max_tokens
    assert "truncated structured output is a silent" in str(excinfo.value)


def test_an_unrecognised_stop_reason_fails_closed(transport, model_id, sentinel):
    # The response body is otherwise perfectly valid. Fail closed anyway.
    with pytest.raises(UnknownStopReason) as excinfo:
        _call(UNKNOWN_CTX, transport, model_id, sentinel)
    assert excinfo.value.stop_reason == "handed_to_operator"


def test_a_guardrail_intervention_is_a_refusal_even_on_a_clean_stop_reason(
    transport, model_id, sentinel
):
    with pytest.raises(ModelRefused) as excinfo:
        quarantined_call(
            EXTRACTION,
            recipes.DOC_POISONED,
            GUARDRAIL_CTX,
            transport=transport,
            model_id=model_id,
            sentinel=sentinel,
        )
    assert excinfo.value.category == "guardrail_intervention"


def test_classify_branches_on_stop_reason_only():
    assert classify("end_turn") is Outcome.OK
    assert classify("max_tokens") is Outcome.TRUNCATED
    assert classify("refusal") is Outcome.REFUSED
    with pytest.raises(UnknownStopReason):
        classify(None)
    with pytest.raises(UnknownStopReason):
        classify("something_new")
    assert set(KNOWN_STOP_REASONS) == {
        "end_turn",
        "max_tokens",
        "model_context_window_exceeded",
        "pause_turn",
        "refusal",
        "stop_sequence",
        "tool_use",
    }


def test_a_refusal_becomes_a_legal_silence_ledger_row():
    refusal = ModelRefused(category="model_refusal", stop_reason="refusal")
    row = silence_row_for_refusal(
        refusal,
        site_id="00000000-0000-0000-0000-000000000001",
        source="recall",
        subject_kind="event",
        subject_id="00000000-0000-0000-0000-000000000002",
        severity=5,
        profile_id="extraction",
        prompt_version=EXTRACTION.prompt_version,
        model_id="au.anthropic.claude-opus-5",
        inference_profile_arn=recipes.MODEL_ID,
        input_sha256="0" * 64,
    )
    mapping = row.to_mapping()
    assert mapping["reason"] == "model_refusal"
    assert mapping["source"] in SILENCE_SOURCES
    assert mapping["reason"] in SILENCE_REASONS
    assert mapping["arithmetic"]["fallback"] == "deterministic_channel"
    assert isinstance(mapping["at"], datetime)
    # A naive datetime in an evidentiary payload is an unanswerable question.
    assert mapping["at"].tzinfo is not None


@pytest.mark.parametrize(
    ("source", "reason"),
    [("not_a_source", "model_refusal"), ("recall", "not_a_reason")],
)
def test_the_row_refuses_a_value_the_database_would_refuse(source, reason):
    with pytest.raises(ValueError, match="CHECK vocabulary"):
        SilenceRow(
            site_id="s",
            source=source,
            reason=reason,
            subject_kind="event",
            subject_id="e",
            severity=3,
            arithmetic={},
        )


def test_a_refused_precursor_still_produces_evidence(transport, model_id, sentinel):
    # The point of A8 stated as a test: nothing here returns an empty result. The call
    # raises, and the raise carries everything the caller needs to write the row.
    with pytest.raises(ModelRefused) as excinfo:
        _call(REFUSAL_CTX, transport, model_id, sentinel)
    row = silence_row_for_refusal(
        excinfo.value,
        site_id="site",
        source="recall",
        subject_kind="clause",
        subject_id="clause-1",
        severity=4,
        profile_id=EXTRACTION.profile_id,
        prompt_version=EXTRACTION.prompt_version,
        model_id="au.anthropic.claude-opus-5",
        inference_profile_arn=recipes.MODEL_ID,
        input_sha256="0" * 64,
    )
    assert row.arithmetic["stop_reason"] == "refusal"
