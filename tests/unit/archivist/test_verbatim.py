# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
"""A model supplies characters; this package supplies offsets.

``mainline_agentkit.profiles.extraction`` states the rule these tests enforce: *we compute
the offsets by exact string search into the source. We never trust a model-reported
offset.* The tests below are that sentence from both sides — a real quote is located, and
a fabricated one is refused, including the fabrication that is one character different
from something that is really there.
"""

from __future__ import annotations

import archivist_corpus as corpus
import pytest
from mainline_archivist import SpanNotVerbatim, VerbatimSpan, assert_verbatim, text_digest

TEXT = corpus.DOCUMENT_TEXT


def test_locate_returns_the_sources_own_characters():
    span = VerbatimSpan.locate(TEXT, corpus.OXYGEN_QUOTE)

    assert span.text == corpus.OXYGEN_QUOTE
    assert TEXT[span.start : span.end] == corpus.OXYGEN_QUOTE
    assert span.extracted_sha256 == text_digest(TEXT)


def test_a_quote_that_is_not_in_the_document_is_not_a_quote():
    with pytest.raises(SpanNotVerbatim, match="does not occur"):
        VerbatimSpan.locate(TEXT, "at least 15.0 %")


def test_a_near_miss_fabrication_is_refused():
    # One digit different from a quote that IS in the document. This is the shape of a
    # value-only distortion, and an offset computed by search cannot be talked into it.
    assert "19.5 %" in TEXT
    with pytest.raises(SpanNotVerbatim):
        VerbatimSpan.locate(TEXT, "at least 19.6 %")


def test_read_refuses_a_range_outside_the_text():
    with pytest.raises(SpanNotVerbatim, match="outside the extracted text"):
        VerbatimSpan.read(TEXT, 0, len(TEXT) + 1)
    with pytest.raises(SpanNotVerbatim):
        VerbatimSpan.read(TEXT, 10, 10)


def test_a_repeated_quote_is_ambiguous_rather_than_silently_first():
    text = "gas test\nsecond line\ngas test\n"
    first = VerbatimSpan.locate(text, "gas test")
    second = VerbatimSpan.locate(text, "gas test", occurrence=2)

    assert first.start == 0
    assert second.start == text.index("gas test", 1)
    with pytest.raises(SpanNotVerbatim, match="3 time"):
        VerbatimSpan.locate(text, "gas test", occurrence=3)


def test_normalised_locate_still_returns_source_characters():
    # A non-breaking space in the document, an ordinary space in the quote. The widened
    # search finds it; what comes back is the document's characters, not the quote's.
    # RUF001 is the point: the NO-BREAK SPACE below is what a PDF extractor emits, and
    # what an exact search must therefore refuse.
    text = "Oxygen at least 19.5 % by volume\n"  # noqa: RUF001
    with pytest.raises(SpanNotVerbatim, match="does not occur"):
        VerbatimSpan.locate(text, "at least 19.5 %")

    span = VerbatimSpan.locate_normalised(text, "at least 19.5 %")

    assert " " in span.text  # noqa: RUF001 - the span carries the document's own byte
    assert text[span.start : span.end] == span.text


def test_normalised_locate_still_refuses_a_fabrication():
    # RUF001 is the point: the NO-BREAK SPACE below is what a PDF extractor emits, and
    # what an exact search must therefore refuse.
    text = "Oxygen at least 19.5 % by volume\n"  # noqa: RUF001
    with pytest.raises(SpanNotVerbatim, match="folding"):
        VerbatimSpan.locate_normalised(text, "at least 21.0 %")


def test_a_hand_built_span_with_invented_text_is_caught_at_the_write_boundary():
    honest = VerbatimSpan.locate(TEXT, corpus.OXYGEN_QUOTE)
    forged = VerbatimSpan(
        text="at least 15.0 %",
        start=honest.start,
        end=honest.start + len("at least 15.0 %"),
        extracted_sha256=honest.extracted_sha256,
    )

    # The constructor cannot tell (the lengths happen to agree); the write boundary can.
    with pytest.raises(SpanNotVerbatim, match="but the source holds"):
        assert_verbatim(forged, TEXT)


def test_a_span_from_a_different_document_is_refused():
    span = VerbatimSpan.locate(TEXT, corpus.TITLE_QUOTE)
    other = TEXT.replace("IR-2019-0117", "IR-2019-0118")

    with pytest.raises(SpanNotVerbatim, match="index a document that is not this one"):
        assert_verbatim(span, other)


def test_offsets_and_text_must_agree():
    with pytest.raises(SpanNotVerbatim, match="disagree"):
        VerbatimSpan(text="abc", start=0, end=5, extracted_sha256=text_digest(TEXT))


def test_digest_of_a_span_is_the_digest_of_its_own_text():
    span = VerbatimSpan.locate(TEXT, corpus.OXYGEN_QUOTE)

    assert span.sha256 == text_digest(corpus.OXYGEN_QUOTE)
    assert len(span.sha256_bytes()) == 32
    assert span.pair == (span.start, span.end)
