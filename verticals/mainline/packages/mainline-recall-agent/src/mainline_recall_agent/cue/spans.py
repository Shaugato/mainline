# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
"""``source_span`` — computed by us, from an exact unique ``find()``, never reported.

A model is perfectly capable of returning ``[412, 486]``.  It is not capable of *counting*,
and nothing downstream could ever tell the difference between an offset it counted and an
offset it guessed: both are two integers, both validate, and both look like provenance.
``event_cue.source_span`` is the field a lawyer follows from a cue back to the words that
produced it, so the offsets are arithmetic we perform on bytes we control.

The contract, in four rules:

1. The model returns an **evidence quote** — a verbatim substring of the canonical source —
   and never an offset.  We ``find()`` it.
2. The quote must occur **exactly once**.  Zero occurrences is fabrication
   (:class:`~.errors.SpanUnresolvable`); more than one is ambiguity
   (:class:`~.errors.SpanAmbiguous`), and picking the first would put a span in the record
   that points at words the cue may not have come from.
3. Quotes have a **minimum length**.  A four-character quote can be unique by accident, and
   a span that is unique by accident is not evidence.
4. Two facets may share a span exactly, or one may nest inside another — a sentence and the
   paragraph containing it are both honest delimitations.  A **partial** overlap is refused
   (:class:`~.errors.SpanOverlap`): it means the two quotes were carved out of one another,
   so neither pair of offsets delimits its own evidence.

All four failures raise.  They are not converted into silence-ledger rows, because they are
not facts about the corpus — they are our prompt or our pipeline being wrong, and a
systematically broken prompt that produced an all-``abstained`` corpus would look exactly
like a corpus with nothing in it.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Final

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .errors import SpanAmbiguous, SpanOverlap, SpanUnresolvable

__all__ = ["MAX_QUOTE_CHARS", "MIN_QUOTE_CHARS", "Span", "locate_quote", "resolve_spans"]

#: Below this, uniqueness is luck rather than evidence.
MIN_QUOTE_CHARS: Final[int] = 16

#: Above this the "quote" is the document, and the span has stopped localising anything.
MAX_QUOTE_CHARS: Final[int] = 600


class Span(BaseModel):
    """A half-open ``[start, end)`` range over the canonical source text."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    start: int = Field(ge=0)
    end: int = Field(ge=0)

    @model_validator(mode="after")
    def _non_empty(self) -> Span:
        if self.end <= self.start:
            raise ValueError(f"span [{self.start}, {self.end}) is empty or inverted")
        return self

    def as_int8_array(self) -> list[int]:
        """The ``INT8[2]`` value written to ``event_cue.source_span``."""
        return [self.start, self.end]

    def overlaps(self, other: Span) -> bool:
        return self.start < other.end and other.start < self.end

    def contains(self, other: Span) -> bool:
        return self.start <= other.start and other.end <= self.end

    def text_of(self, source: str) -> str:
        return source[self.start : self.end]


def locate_quote(source: str, quote: str, *, facet: str) -> Span:
    """Exact, unique ``find()`` of ``quote`` in ``source``.

    ``str.count`` before ``str.find`` on purpose: the cheap way to write this is
    ``source.find(quote)`` and a ``-1`` check, and that version silently accepts the
    ambiguous case, which is the one that puts a wrong span in the record.
    """
    if len(quote) < MIN_QUOTE_CHARS:
        raise SpanUnresolvable(
            "evidence quote is too short to localise; a span that is unique by accident is "
            "not evidence",
            facet=facet,
            length=len(quote),
            minimum=MIN_QUOTE_CHARS,
        )
    if len(quote) > MAX_QUOTE_CHARS:
        raise SpanUnresolvable(
            "evidence quote is longer than the bound; a quote this size has stopped "
            "localising anything",
            facet=facet,
            length=len(quote),
            maximum=MAX_QUOTE_CHARS,
        )
    occurrences = source.count(quote)
    if occurrences == 0:
        raise SpanUnresolvable(
            "evidence quote does not occur in the canonical source text; the model was "
            "shown that text verbatim, so a quote absent from it was not copied from it",
            facet=facet,
            quote_head=quote[:80],
        )
    if occurrences > 1:
        raise SpanAmbiguous(
            "evidence quote occurs more than once in the canonical source text; two "
            "candidate positions means we do not know which words the cue came from",
            facet=facet,
            occurrences=occurrences,
            quote_head=quote[:80],
        )
    start = source.find(quote)
    return Span(start=start, end=start + len(quote))


def resolve_spans(source: str, quotes: Mapping[str, str]) -> dict[str, Span]:
    """Resolve every facet's quote, then refuse a set whose spans partially overlap.

    Returns a mapping in the iteration order of ``quotes`` so a caller's logging is stable.
    """
    resolved: dict[str, Span] = {
        facet: locate_quote(source, quote, facet=facet) for facet, quote in quotes.items()
    }
    facets = list(resolved)
    for i, left_facet in enumerate(facets):
        for right_facet in facets[i + 1 :]:
            left, right = resolved[left_facet], resolved[right_facet]
            if not left.overlaps(right):
                continue
            if left.contains(right) or right.contains(left):
                continue
            raise SpanOverlap(
                "two facets resolved to partially overlapping spans; neither pair of "
                "offsets delimits its own evidence, so the set is refused rather than "
                "half-recorded",
                left_facet=left_facet,
                left_span=left.as_int8_array(),
                right_facet=right_facet,
                right_span=right.as_int8_array(),
            )
    return resolved
