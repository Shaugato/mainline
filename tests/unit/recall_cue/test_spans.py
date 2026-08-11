# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
"""``source_span`` is arithmetic we perform, not a number we accept.

Every test here is really one assertion in four costumes: nothing downstream can tell a
counted offset from a guessed one, so no offset may enter the record unless we computed it
from bytes we control.
"""

from __future__ import annotations

import pytest
from mainline_recall_agent.cue.errors import SpanAmbiguous, SpanOverlap, SpanUnresolvable
from mainline_recall_agent.cue.spans import MIN_QUOTE_CHARS, Span, locate_quote, resolve_spans

SOURCE = (
    "The lock ring was displaced and the rim components separated axially. "
    "The workshop held no inflation cage and no remote inflation line. "
    "The task instruction required the fitter to observe seating during inflation."
)


def test_an_exact_unique_quote_resolves_to_its_offsets() -> None:
    quote = "The workshop held no inflation cage and no remote inflation line."
    span = locate_quote(SOURCE, quote, facet="control_failure")
    assert span.text_of(SOURCE) == quote
    assert SOURCE[span.start : span.end] == quote
    assert span.as_int8_array() == [span.start, span.end]


def test_a_quote_absent_from_the_source_fails_the_step() -> None:
    """The fabrication case.  The model was shown these exact bytes."""
    with pytest.raises(SpanUnresolvable, match="does not occur in the canonical source"):
        locate_quote(SOURCE, "the inflation cage was fitted and used", facet="mechanism")


def test_a_quote_occurring_twice_is_ambiguous_rather_than_first_wins() -> None:
    """The cheap implementation — ``find()`` plus a ``-1`` check — accepts this silently."""
    doubled = SOURCE + " " + SOURCE
    with pytest.raises(SpanAmbiguous, match="occurs more than once"):
        locate_quote(doubled, "The workshop held no inflation cage", facet="control_failure")


def test_a_quote_too_short_to_localise_is_refused() -> None:
    short = SOURCE[: MIN_QUOTE_CHARS - 1]
    with pytest.raises(SpanUnresolvable, match="too short to localise"):
        locate_quote(SOURCE, short, facet="mechanism")


def test_an_enormous_quote_is_refused() -> None:
    with pytest.raises(SpanUnresolvable, match="stopped localising"):
        locate_quote("x" * 4000, "x" * 3000, facet="narrative")


def test_two_facets_may_share_a_span_exactly() -> None:
    quote = "The workshop held no inflation cage and no remote inflation line."
    spans = resolve_spans(SOURCE, {"control_failure": quote, "recurrence_test": quote})
    assert spans["control_failure"] == spans["recurrence_test"]


def test_one_span_may_nest_inside_another() -> None:
    """A sentence inside a paragraph is two honest delimitations of the same evidence."""
    outer = (
        "The workshop held no inflation cage and no remote inflation line. "
        "The task instruction required the fitter to observe seating during inflation."
    )
    inner = "The task instruction required the fitter to observe seating during inflation."
    spans = resolve_spans(SOURCE, {"control_failure": outer, "recurrence_test": inner})
    assert spans["control_failure"].contains(spans["recurrence_test"])


def test_partially_overlapping_spans_fail_the_step() -> None:
    left = "The lock ring was displaced and the rim components"
    right = "and the rim components separated axially."
    with pytest.raises(SpanOverlap, match="partially overlapping"):
        resolve_spans(SOURCE, {"mechanism": left, "precondition": right})


def test_disjoint_spans_resolve_together() -> None:
    spans = resolve_spans(
        SOURCE,
        {
            "mechanism": "The lock ring was displaced and the rim components separated",
            "control_failure": "The workshop held no inflation cage",
        },
    )
    assert not spans["mechanism"].overlaps(spans["control_failure"])
    assert list(spans) == ["mechanism", "control_failure"]


def test_an_empty_or_inverted_span_cannot_be_constructed() -> None:
    with pytest.raises(ValueError, match="empty or inverted"):
        Span(start=10, end=10)
    with pytest.raises(ValueError, match="empty or inverted"):
        Span(start=10, end=4)
