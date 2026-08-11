# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
"""The five-field contract, and the per-facet ``insufficient_evidence`` escape.

The escape is the difference between *"the record does not say how the energy got out"* and
*"the energy got out somehow"*.  The second sentence, written into a cue row, becomes a
retrievable precedent attached to a real incident, so the tests below spend most of their
effort on the ways a model can smuggle one past the schema: a placeholder string, a facet
that is both populated and insufficient, an escape with no stated reason.
"""

from __future__ import annotations

import pytest
from mainline_recall_agent.cue.schema import (
    FACETS,
    MAX_FACET_TOKENS,
    SYNTHESISED_FACETS,
    FacetAnswer,
    FacetSynthesis,
    NarrativeFacet,
    RecurrenceConditionCue,
    approx_token_count,
)
from mainline_recall_agent.cue.spans import Span
from pydantic import ValidationError

GOOD_TEXT = "Stored pneumatic energy released axially when a rim assembly separates."
GOOD_QUOTE = "the rim components separated axially, striking the fitter"


def populated(text: str = GOOD_TEXT, quote: str = GOOD_QUOTE) -> FacetAnswer:
    return FacetAnswer(
        cue_text=text, evidence_quote=quote, insufficient=False, insufficient_reason=None
    )


def escaped(reason: str = "the record does not establish how ignition occurred") -> FacetAnswer:
    return FacetAnswer(
        cue_text=None, evidence_quote=None, insufficient=True, insufficient_reason=reason
    )


def test_the_cue_has_exactly_five_facets() -> None:
    """``mainline.event_cue.facet``'s CHECK lists five values.  So does the model."""
    assert set(RecurrenceConditionCue.model_fields) == set(FACETS)
    assert len(RecurrenceConditionCue.model_fields) == 5
    assert set(FacetSynthesis.model_fields) == set(SYNTHESISED_FACETS)
    assert "narrative" not in FacetSynthesis.model_fields


def test_narrative_is_not_in_the_model_facing_schema() -> None:
    """The safety net may not be rewritable by the thing it is a safety net against.

    An injected instruction inside a narrative cannot reach a field the output schema does
    not contain; ARCHITECTURE §8.4 layer 3, applied to the one facet that is raw evidence.
    """
    schema = FacetSynthesis.model_json_schema()
    assert "narrative" not in schema["properties"]


@pytest.mark.parametrize("facet", SYNTHESISED_FACETS)
def test_each_facet_has_its_own_escape_and_round_trips(facet: str) -> None:
    """One facet may be insufficient while its siblings are populated, per facet."""
    answers = {name: populated() for name in SYNTHESISED_FACETS}
    answers[facet] = escaped(f"the source does not establish the {facet}")
    synthesis = FacetSynthesis.model_validate(
        {name: answer.model_dump() for name, answer in answers.items()}
    )
    mapping = synthesis.as_mapping()
    assert mapping[facet].insufficient is True
    assert mapping[facet].cue_text is None
    assert mapping[facet].insufficient_reason is not None
    for other in SYNTHESISED_FACETS:
        if other != facet:
            assert mapping[other].populated


@pytest.mark.parametrize(
    "placeholder",
    [
        "insufficient evidence",
        "insufficient_evidence",
        "Insufficient Evidence.",
        "N/A",
        "unknown",
        "not applicable",
        "TBD",
        "none",
        "Not specified",
    ],
)
def test_a_placeholder_string_is_refused(placeholder: str) -> None:
    """A cue row that exists and says nothing is a point in the index that gets retrieved."""
    with pytest.raises(ValidationError, match="placeholder"):
        populated(text=placeholder)


def test_a_facet_cannot_be_populated_and_insufficient_at_once() -> None:
    with pytest.raises(ValidationError, match="produces no cue row"):
        FacetAnswer(
            cue_text=GOOD_TEXT,
            evidence_quote=GOOD_QUOTE,
            insufficient=True,
            insufficient_reason="both, somehow",
        )


def test_the_escape_requires_a_reason() -> None:
    """Silence with no ledger entry is the failure mode the whole product is about."""
    with pytest.raises(ValidationError, match="silence with no ledger entry"):
        FacetAnswer(cue_text=None, evidence_quote=None, insufficient=True, insufficient_reason="  ")


def test_a_facet_that_is_neither_populated_nor_escaped_is_refused() -> None:
    with pytest.raises(ValidationError, match="use the insufficient escape"):
        FacetAnswer(cue_text="", evidence_quote=None, insufficient=False, insufficient_reason=None)


def test_a_populated_facet_must_quote_its_source() -> None:
    """No quote means no computable span, which means the cue is derived from nothing."""
    with pytest.raises(ValidationError, match="quote the source verbatim"):
        FacetAnswer(
            cue_text=GOOD_TEXT,
            evidence_quote=None,
            insufficient=False,
            insufficient_reason=None,
        )


def test_the_token_bound_is_enforced_and_conservative() -> None:
    """<= 60 tokens (ARCHITECTURE §6.2), estimated in the over-counting direction."""
    assert approx_token_count("") == 0
    # 13 characters, 3 whitespace tokens: the character estimate wins, and it over-counts.
    # That is the direction an unverified approximation has to err in when what it bounds
    # is what goes into the index.
    assert approx_token_count("one two three") == 4
    assert approx_token_count("a b c d e f g h") == 8
    assert approx_token_count("a" * 400) == 100
    over = " ".join(["mechanism"] * 40)
    assert approx_token_count(over) > MAX_FACET_TOKENS
    with pytest.raises(ValidationError, match="over the 60"):
        populated(text=over)


def test_a_one_word_facet_is_refused() -> None:
    with pytest.raises(ValidationError, match="not a proposition about a mechanism"):
        populated(text="engulfment")


def test_extra_fields_are_forbidden_on_every_model() -> None:
    """Mirrors ``additionalProperties: false``; the client-side catch runs on cassettes."""
    with pytest.raises(ValidationError):
        FacetAnswer.model_validate(
            {
                "cue_text": GOOD_TEXT,
                "evidence_quote": GOOD_QUOTE,
                "insufficient": False,
                "insufficient_reason": None,
                "confidence": 0.9,
            }
        )


def test_the_cue_assembles_from_a_synthesis_plus_a_copied_narrative() -> None:
    synthesis = FacetSynthesis(
        mechanism=populated(),
        precondition=populated(),
        control_failure=escaped(),
        recurrence_test=populated(),
    )
    narrative = NarrativeFacet(text="raw text, unchanged", span=Span(start=10, end=29))
    cue = RecurrenceConditionCue.from_synthesis(synthesis, narrative)
    assert cue.narrative.text == "raw text, unchanged"
    assert cue.control_failure.insufficient
    assert set(cue.synthesised()) == set(SYNTHESISED_FACETS)
