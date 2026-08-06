# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""The one tokeniser.

Everything downstream that needs to talk about "a token" — OCR repair, content
defined segmentation, shingling — uses this, so that a token boundary is one
decision made once rather than three regexes that agree until they do not.

A token is a maximal run of non-whitespace characters.  That is the whole
definition, and it is deliberately dumber than a linguistic tokeniser: word
boundaries computed by a model are word boundaries that can change under a
model upgrade, and every digest in this system would move with them.

Edge punctuation is *reported*, never removed, so a caller can address the
numeric core of ``(1O0),`` without losing the offsets of the parentheses.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Final

__all__ = ["Token", "iter_tokens", "token_texts"]

_TOKEN: Final[re.Pattern[str]] = re.compile(r"\S+")

_LEAD_PUNCT: Final[str] = "([{<\"'"
_TRAIL_PUNCT: Final[str] = ")]}>\"'.,;:!?%"


@dataclass(frozen=True, slots=True)
class Token:
    """A maximal non-whitespace run, with a half-open span into its source."""

    start: int
    end: int
    text: str

    def core(self) -> tuple[int, int, str]:
        """``(start, end, text)`` of the token with edge punctuation excluded.

        Returns an empty core (``start == end``) for a token that is nothing but
        punctuation.
        """
        lead = 0
        trail = len(self.text)
        while lead < trail and self.text[lead] in _LEAD_PUNCT:
            lead += 1
        while trail > lead and self.text[trail - 1] in _TRAIL_PUNCT:
            trail -= 1
        return self.start + lead, self.start + trail, self.text[lead:trail]


def iter_tokens(text: str) -> Iterator[Token]:
    """Yield every token of ``text`` in order."""
    for match in _TOKEN.finditer(text):
        yield Token(start=match.start(), end=match.end(), text=match.group())


def token_texts(text: str) -> tuple[str, ...]:
    """Just the token strings — the shingling and segmentation view."""
    return tuple(match.group() for match in _TOKEN.finditer(text))
