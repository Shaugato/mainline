# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""Page-furniture stripping, by pattern and by position + repetition.

Two mechanisms, deliberately separate:

**Unconditional patterns.**  Whole lines that are furniture in every document
ever printed: ``Page 4 of 31``, revision stamps, ``UNCONTROLLED WHEN PRINTED``,
copyright lines, document-number stamps.  These are line-anchored regexes and
they fire without document context, because a clause never *is* one of these
lines.

**Position + repetition.**  Everything else -- a site's own header block, a
watermark, a footer with a document title -- is only detectable across pages.
:class:`FurnitureModel` is built from the pages of one document: a line is
furniture when it appears in the top-``n`` or bottom-``n`` lines of at least
``min_ratio`` of the pages, compared after masking digit runs to ``#`` (so
``Page 4 of 31`` and ``Page 12 of 31`` are the same line) and casefolding.

**Two safety rules**, both there because the asymmetry is brutal: furniture that
survives into ``canon_text`` costs a match (loud, adjudicable), while a
clause deleted as furniture costs a *control* (silent, fatal).

1. An unconditional pattern only fires on a line of at most
   :data:`_MAX_STAMP_CHARS` characters.  A stamp is short; a sentence is not.
   Without this, ``Version 2 of the isolation procedure shall ...`` reads as a
   revision stamp.
2. If stripping would remove *everything*, nothing is stripped.  This is also
   what makes the whole pipeline idempotent: ``canon(canon(x))`` re-runs
   furniture stripping over a single collapsed line, and without the rule a text
   whose entire body matched a furniture pattern would vanish on the second pass.
"""

from __future__ import annotations

import re
from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from typing import Final

from .fold import fold_text, normalise_newlines

__all__ = ["FurnitureModel", "iter_lines", "mask_line", "strip_furniture"]

_MAX_STAMP_CHARS: Final[int] = 80

_UNCONDITIONAL: Final[tuple[re.Pattern[str], ...]] = (
    # 'Page 4', 'Page 4 of 31', 'p. 4 of 31'
    re.compile(r"^(?:page|pg\.?|p\.)\s*\d+\s*(?:of\s*\d+)?$", re.IGNORECASE),
    # a decorated bare folio: '- 4 -', '~ 12 ~'.  An undecorated bare number is
    # NOT matched here: a wrapped table cell can be exactly '50'.
    re.compile(r"^[-=~*_]{1,4}\s*\d{1,4}\s*[-=~*_]{1,4}$"),
    # revision stamps: 'Rev. 3 - 14 Mar 2019', 'Revision B', 'Issue 2', 'Ver 1.4'.
    # The token after the keyword must contain a digit or be a single letter,
    # so 'Revision of the permit shall ...' is prose, not a stamp.
    re.compile(
        r"^(?:rev(?:ision)?|issue|version|ver)\.?\s*[:#]?\s*"
        r"(?:\d[\w.]*|[A-Za-z]\d[\w.]*|[A-Za-z])\b.*$",
        re.IGNORECASE,
    ),
    # controlled-copy watermarks
    re.compile(
        r"^(?:uncontrolled(?:\s+(?:copy|document|when\s+printed))?"
        r"|controlled\s+copy"
        r"|printed\s+copies?\s+are\s+uncontrolled"
        r"|for\s+internal\s+use\s+only"
        r"|commercial[\s-]in[\s-]confidence"
        r"|confidential"
        r"|draft(?:\s+only)?"
        r"|not\s+for\s+construction)\.?$",
        re.IGNORECASE,
    ),
    # document identity stamps ('ref' must not swallow 'reference ...')
    re.compile(r"^doc(?:ument)?\s*(?:no|number|id|ref)\b\.?\s*[:#]?\s*\S.*$", re.IGNORECASE),
    re.compile(r"^(?:\(c\)|copyright)\s.*$", re.IGNORECASE),
    re.compile(r"^printed\s+(?:on|by)\s+.*\d.*$", re.IGNORECASE),
    # bare timestamps of the kind print drivers add
    re.compile(r"^\d{1,2}[/-]\d{1,2}[/-]\d{2,4}(?:[ ,]+\d{1,2}:\d{2}(?::\d{2})?)?$"),
)

_LINE_BREAK: Final[re.Pattern[str]] = re.compile(r"\r\n|\r|\n")
_DIGIT_RUN: Final[re.Pattern[str]] = re.compile(r"\d+")
_WS_RUN: Final[re.Pattern[str]] = re.compile(r"\s+")


def iter_lines(text: str) -> Iterator[tuple[int, int, str]]:
    """Yield ``(start, end, line)`` for each line, with **offsets into ``text``**.

    The text is not modified; the line separator is matched rather than
    rewritten, so the spans yielded are true offsets into the caller's input.
    """
    pos = 0
    n = len(text)
    while pos <= n:
        match = _LINE_BREAK.search(text, pos)
        if match is None:
            if pos < n:
                yield pos, n, text[pos:n]
            return
        yield pos, match.start(), text[pos : match.start()]
        pos = match.end()


def _probe(line: str) -> str:
    """The comparison form of a line: folded, whitespace-collapsed, stripped."""
    return _WS_RUN.sub(" ", fold_text(line)).strip()


def mask_line(line: str) -> str:
    """Normalise a line for cross-page comparison: probe, mask digits, casefold."""
    return _DIGIT_RUN.sub("#", _probe(line)).casefold()


@dataclass(frozen=True, slots=True)
class FurnitureModel:
    """Repeated edge lines learned from the pages of one document."""

    masked_lines: frozenset[str]

    @classmethod
    def empty(cls) -> FurnitureModel:
        return cls(masked_lines=frozenset())

    @classmethod
    def from_pages(
        cls,
        pages: Sequence[str],
        *,
        edge_lines: int = 3,
        min_ratio: float = 0.5,
        min_pages: int = 2,
    ) -> FurnitureModel:
        """Learn furniture from page text.

        A masked line counts once per page (a header repeated twice on one page
        is still one page's worth of evidence) and must appear in the top or
        bottom ``edge_lines`` of at least ``min_ratio`` of the pages.  Below
        ``min_pages`` there is no repetition evidence at all and the model is
        empty.
        """
        if edge_lines < 1:
            raise ValueError("edge_lines must be >= 1")
        if not 0.0 < min_ratio <= 1.0:
            raise ValueError("min_ratio must be in (0, 1]")
        if len(pages) < min_pages:
            return cls.empty()

        counts: dict[str, int] = {}
        for page in pages:
            lines = [line for _, _, line in iter_lines(normalise_newlines(page)) if line.strip()]
            # The edge zone may never cover the whole page.  On a short page,
            # every line is an "edge" line, and the model would learn the BODY --
            # which, after digit masking, repeats across pages just as happily as
            # a header does.  Capping at half the page keeps the middle safe.
            zone = min(edge_lines, len(lines) // 2)
            if zone == 0:
                continue
            edge = lines[:zone] + lines[-zone:]
            seen: set[str] = set()
            for line in edge:
                masked = mask_line(line)
                if masked and masked not in seen:
                    seen.add(masked)
                    counts[masked] = counts.get(masked, 0) + 1

        threshold = min_ratio * len(pages)
        return cls(masked_lines=frozenset(m for m, c in counts.items() if c >= threshold))

    def is_furniture(self, line: str) -> bool:
        masked = mask_line(line)
        return bool(masked) and masked in self.masked_lines


def _is_unconditional_furniture(line: str) -> bool:
    probe = _probe(line)
    if not probe or len(probe) > _MAX_STAMP_CHARS:
        return False
    return any(pattern.match(probe) for pattern in _UNCONDITIONAL)


def strip_furniture(
    text: str,
    model: FurnitureModel | None = None,
) -> tuple[str, tuple[tuple[int, int], ...]]:
    """Remove furniture lines; return ``(kept_text, spans_removed_from_text)``.

    Spans are half-open offsets into ``text`` exactly as passed in.  If every
    line would be removed, nothing is removed and the span tuple is empty.
    """
    kept: list[str] = []
    removed: list[tuple[int, int]] = []
    saw_content = False

    for start, end, line in iter_lines(text):
        if line.strip():
            saw_content = True
            if _is_unconditional_furniture(line) or (
                model is not None and model.is_furniture(line)
            ):
                removed.append((start, end))
                continue
        kept.append(line)

    if not removed:
        return text, ()

    kept_text = "\n".join(kept)
    if saw_content and not kept_text.strip():
        # Stripping would empty a non-empty clause.  Refuse to strip anything.
        return text, ()
    return kept_text, tuple(removed)
