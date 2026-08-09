# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""The only way text enters an event row: bytes that were read out of the source.

Every free-text column the Archivist writes — ``event.title``, ``event.narrative``,
``control_failure`` quotes, the span behind a severity — is a :class:`VerbatimSpan`, and
a :class:`VerbatimSpan` can only be minted by two constructors, both of which **read the
source text**:

* :meth:`VerbatimSpan.read` takes offsets and returns what is actually there;
* :meth:`VerbatimSpan.locate` takes a quote and finds it by exact string search.

There is no constructor that takes a string a model produced and believes it. That
absence is the mechanism, and it exists because of what these rows are: ``event`` is the
table a blame edge points at, and its narrative is read aloud when a permit is refused.
A machine paraphrase in that column would be an unattributed statement about a real
workplace death, presented in evidence as a quotation.

**Verified again at the write boundary.** Construction-time verification is not enough
on its own — a caller can always build a frozen dataclass by hand — so
:func:`assert_verbatim` re-derives every span from the source text inside the statement
builders (:mod:`mainline_archivist.emit`). Principle P2 in miniature: the field a
downstream reader trusts is checked against its authority at the moment it is written,
not at the moment it was proposed.

**Offsets are character offsets into the extracted text**, not byte offsets into the
source PDF. That is stated rather than implied because ``event.severity_span`` is an
``INT8[]`` whose meaning has to be the same for everyone who reads it: it indexes the
canonical extracted text whose digest is ``extracted_sha256``, and the object those bytes
came from is named by ``source_object_key`` and ``source_sha256`` on the same row.
"""

from __future__ import annotations

import hashlib
import unicodedata
from dataclasses import dataclass
from typing import TYPE_CHECKING

from .errors import SpanNotVerbatim

if TYPE_CHECKING:
    from collections.abc import Iterator

__all__ = [
    "VerbatimSpan",
    "assert_verbatim",
    "sha256_hex",
    "text_digest",
]

_DIGEST_HEX_LEN = 64


def sha256_hex(data: bytes) -> str:
    """Hex SHA-256 of ``data``."""
    return hashlib.sha256(data).hexdigest()


def text_digest(text: str) -> str:
    """Hex SHA-256 of ``text`` encoded UTF-8.

    The digest of the *extracted* text, which is what spans index. It is deliberately a
    different value from the source object's digest: two different extractors over one
    PDF produce two different texts, and a span is only meaningful against the one it
    was read from.
    """
    return sha256_hex(text.encode("utf-8"))


@dataclass(frozen=True, slots=True)
class VerbatimSpan:
    """A range of the extracted text, and the text that is actually in it.

    Attributes:
        text: exactly ``source[start:end]``.
        start: inclusive character offset into the extracted text.
        end: exclusive character offset.
        extracted_sha256: digest of the extracted text these offsets index.
    """

    text: str
    start: int
    end: int
    extracted_sha256: str

    def __post_init__(self) -> None:
        """Refuse a span that could not describe any range of any document."""
        if self.start < 0 or self.end <= self.start:
            raise SpanNotVerbatim(
                f"span ({self.start}, {self.end}) is not a half-open forward range; a "
                f"severity or a quote with an impossible span is not evidence"
            )
        if len(self.text) != self.end - self.start:
            raise SpanNotVerbatim(
                f"span ({self.start}, {self.end}) covers {self.end - self.start} "
                f"characters but carries {len(self.text)}; the offsets and the text "
                f"disagree, and the offsets are what a reviewer will open the document at"
            )
        if len(self.extracted_sha256) != _DIGEST_HEX_LEN:
            raise SpanNotVerbatim(
                f"extracted_sha256 {self.extracted_sha256!r} is not a 64-character hex "
                f"SHA-256; a span that cannot name the text it indexes indexes nothing"
            )

    @classmethod
    def read(cls, source_text: str, start: int, end: int) -> VerbatimSpan:
        """Return what the source actually holds at ``[start, end)``.

        This is the constructor for offsets the *deterministic* pass produced. It cannot
        be made to lie: the text is read out of the source rather than supplied.

        Raises:
            SpanNotVerbatim: the range falls outside the text or is empty.
        """
        if start < 0 or end > len(source_text) or end <= start:
            raise SpanNotVerbatim(
                f"span ({start}, {end}) is outside the extracted text of "
                f"{len(source_text)} characters"
            )
        return cls(
            text=source_text[start:end],
            start=start,
            end=end,
            extracted_sha256=text_digest(source_text),
        )

    @classmethod
    def locate(cls, source_text: str, quote: str, *, occurrence: int = 1) -> VerbatimSpan:
        """Find ``quote`` in the source by exact string search and return its span.

        This is the constructor for a quote a **model** produced. The model supplies the
        characters; this function supplies the offsets, which is the rule
        ``mainline_agentkit.profiles.extraction`` states and the reason a fabricated
        quote becomes a refusal rather than a row.

        Args:
            source_text: the extracted text the model was shown.
            quote: the span the model claims it read.
            occurrence: which occurrence to take when the quote repeats, 1-based. A
                repeated quote is ambiguous rather than wrong, and picking silently would
                put a reviewer at the wrong paragraph.

        Raises:
            SpanNotVerbatim: the quote is empty, absent, or has fewer than
                ``occurrence`` occurrences.
        """
        if not quote:
            raise SpanNotVerbatim("an empty quote locates nothing")
        if occurrence < 1:
            raise SpanNotVerbatim(f"occurrence {occurrence} is not 1-based")
        index = -1
        for _ in range(occurrence):
            index = source_text.find(quote, index + 1)
            if index < 0:
                raise SpanNotVerbatim(
                    f"quote {_elide(quote)!r} does not occur "
                    f"{occurrence} time(s) in the extracted text. A quote that is not in "
                    f"the document is not a quote, and no offset this package computes "
                    f"will make it one."
                )
        return cls.read(source_text, index, index + len(quote))

    @classmethod
    def locate_normalised(
        cls, source_text: str, quote: str, *, occurrence: int = 1
    ) -> VerbatimSpan:
        """Locate ``quote`` allowing only Unicode NFKC and whitespace-shape differences.

        Extractors differ on non-breaking spaces, soft hyphens and ligatures, so an exact
        search can fail on a quote a human would call verbatim. This constructor widens
        the search over exactly those differences and **still returns the source's own
        characters**, never the model's — the returned ``text`` is a slice of
        ``source_text``.

        Widening is opt-in at the call site, so a caller who wants byte-exactness gets it
        by default and a caller who accepts the widening has written that down.

        Raises:
            SpanNotVerbatim: no run of the source normalises to the quote.
        """
        target = _fold(quote)
        if not target:
            raise SpanNotVerbatim("an empty quote locates nothing")
        seen = 0
        for start, end in _candidate_ranges(source_text, len(quote)):
            if _fold(source_text[start:end]) != target:
                continue
            seen += 1
            if seen == occurrence:
                return cls.read(source_text, start, end)
        raise SpanNotVerbatim(
            f"quote {_elide(quote)!r} does not occur {occurrence} time(s) in the "
            f"extracted text even after NFKC and whitespace folding"
        )

    @property
    def pair(self) -> tuple[int, int]:
        """``(start, end)``, the shape ``INT8[2]`` columns take."""
        return (self.start, self.end)

    @property
    def sha256(self) -> str:
        """Hex digest of the span's own text, for ``quote_sha256`` columns."""
        return text_digest(self.text)

    def sha256_bytes(self) -> bytes:
        """Raw 32-byte digest of the span's own text, for a ``BYTES`` column."""
        return hashlib.sha256(self.text.encode("utf-8")).digest()


def assert_verbatim(span: VerbatimSpan, source_text: str) -> VerbatimSpan:
    """Re-derive ``span`` from ``source_text`` and refuse any disagreement.

    Called by every statement builder in :mod:`mainline_archivist.emit`, on every span,
    every time. The cost is a string slice; what it buys is that a hand-built span with
    plausible offsets and invented text cannot reach a parameter list.

    Raises:
        SpanNotVerbatim: the digest, the offsets or the text disagree with the source.
    """
    digest = text_digest(source_text)
    if span.extracted_sha256 != digest:
        raise SpanNotVerbatim(
            f"span indexes text {span.extracted_sha256[:12]}… but the source supplied at "
            f"write time is {digest[:12]}…; the offsets index a document that is not "
            f"this one"
        )
    if span.end > len(source_text):
        raise SpanNotVerbatim(
            f"span ends at {span.end} but the extracted text is {len(source_text)} characters"
        )
    actual = source_text[span.start : span.end]
    if actual != span.text:
        raise SpanNotVerbatim(
            f"span ({span.start}, {span.end}) carries {_elide(span.text)!r} but the "
            f"source holds {_elide(actual)!r} there"
        )
    return span


def _candidate_ranges(source_text: str, quote_len: int) -> Iterator[tuple[int, int]]:
    """Yield plausible ranges for a normalised match, shortest deviation first.

    Folding can change length (a ligature becomes two characters, a run of whitespace
    becomes one), so the window is swept over a small band around the quote's length
    rather than fixed at it. The band is bounded so this stays linear in the text for a
    fixed quote.
    """
    slack = min(max(quote_len // 4, 4), 64)
    lo = max(1, quote_len - slack)
    hi = quote_len + slack
    for start in range(len(source_text)):
        for width in range(lo, hi + 1):
            end = start + width
            if end > len(source_text):
                break
            yield start, end


def _fold(text: str) -> str:
    """NFKC-normalise, collapse whitespace runs, and strip. Case is preserved."""
    normalised = unicodedata.normalize("NFKC", text)
    return " ".join(normalised.split())


def _elide(text: str, limit: int = 60) -> str:
    """Shorten a span for an error message without hiding which end was wrong."""
    if len(text) <= limit:
        return text
    half = (limit - 1) // 2
    return f"{text[:half]}…{text[-half:]}"
