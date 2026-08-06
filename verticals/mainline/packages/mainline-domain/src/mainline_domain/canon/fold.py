# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""Unicode folding: NFKC, confusable punctuation, and discretionary breaks.

Order matters and is fixed:

1. **Discretionary breaks first.**  A SOFT HYPHEN (U+00AD) or ZERO WIDTH SPACE
   at a line wrap is a typesetter's suggestion, not text.  It is removed
   *together with the line break it caused*, otherwise whitespace collapse
   turns ``atmo<SHY><LF>sphere`` into ``atmo sphere`` -- a new word, a new
   digest, a lost match.  NFKC does not touch these characters, so they must go
   first.
2. **NFKC.**  Folds ligatures (U+FB01 -> ``fi``), NO-BREAK SPACE -> space,
   superscripts, fullwidth forms, and the compatibility decompositions that
   scanners and word processors emit.  NFKC is idempotent by definition.
3. **Confusable punctuation.**  NFKC deliberately does *not* fold curly quotes
   or dashes, because they are semantically distinct in general text.  In a
   procedure they are not: ``lock<U+2010>out`` and ``lock-out`` are the same
   control.  The map below is exhaustive over what the corpus's authoring tools
   actually emit and is versioned with ``canon_version``.

What this module does **not** do: it never touches letters or digits.  Every
substitution here is punctuation or whitespace.  Character-class repair for OCR
damage lives in :mod:`mainline_domain.canon.ocr` and is confined to numeric
tokens.

Every non-ASCII code point in this module is written as an escape on purpose:
an invisible character in a canonicaliser is an invisible change to every
digest the system will ever produce.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Final

__all__ = ["fold_text", "normalise_newlines"]

# Characters that exist only to suggest a break.  They carry no content.
#   U+00AD SOFT HYPHEN            U+200B ZERO WIDTH SPACE
#   U+200C ZERO WIDTH NON-JOINER  U+200D ZERO WIDTH JOINER
#   U+2060 WORD JOINER            U+FEFF ZERO WIDTH NO-BREAK SPACE (BOM)
_DISCRETIONARY: Final[str] = "­​‌‍⁠﻿"

# A discretionary break immediately followed by a line break: remove both, and
# the indentation of the continuation line with them.
_DISCRETIONARY_AT_WRAP: Final[re.Pattern[str]] = re.compile(
    "[" + _DISCRETIONARY + "][ \t]*(?:\r\n|\r|\n)[ \t]*"
)
_DISCRETIONARY_BARE: Final[re.Pattern[str]] = re.compile("[" + _DISCRETIONARY + "]")

# CRLF, CR, LINE SEPARATOR (U+2028), PARAGRAPH SEPARATOR (U+2029).
_NEWLINES: Final[re.Pattern[str]] = re.compile("\r\n|\r| | ")

# Post-NFKC punctuation folding.  Keys are single code points, values are ASCII.
_CONFUSABLE_PUNCTUATION: Final[dict[str, str]] = {
    # apostrophes and single quotes
    "‘": "'",  # LEFT SINGLE QUOTATION MARK
    "’": "'",  # RIGHT SINGLE QUOTATION MARK
    "‚": "'",  # SINGLE LOW-9 QUOTATION MARK
    "‛": "'",  # SINGLE HIGH-REVERSED-9 QUOTATION MARK
    "′": "'",  # PRIME
    "´": "'",  # ACUTE ACCENT
    "`": "'",  # GRAVE ACCENT
    # double quotes
    "“": '"',  # LEFT DOUBLE QUOTATION MARK
    "”": '"',  # RIGHT DOUBLE QUOTATION MARK
    "„": '"',  # DOUBLE LOW-9 QUOTATION MARK
    "‟": '"',  # DOUBLE HIGH-REVERSED-9 QUOTATION MARK
    "″": '"',  # DOUBLE PRIME
    "«": '"',  # LEFT-POINTING DOUBLE ANGLE QUOTATION MARK
    "»": '"',  # RIGHT-POINTING DOUBLE ANGLE QUOTATION MARK
    # dashes and minus signs
    "‐": "-",  # HYPHEN
    "‑": "-",  # NON-BREAKING HYPHEN
    "‒": "-",  # FIGURE DASH
    "–": "-",  # EN DASH
    "—": "-",  # EM DASH
    "―": "-",  # HORIZONTAL BAR
    "−": "-",  # MINUS SIGN
    "⁃": "-",  # HYPHEN BULLET
    "─": "-",  # BOX DRAWINGS LIGHT HORIZONTAL
    # slashes
    "⁄": "/",  # FRACTION SLASH
    "∕": "/",  # DIVISION SLASH
    # spaces NFKC leaves behind
    " ": " ",  # NO-BREAK SPACE (NFKC already folds this; belt and braces)
    "᠎": " ",  # MONGOLIAN VOWEL SEPARATOR
    " ": " ",  # NARROW NO-BREAK SPACE
    " ": " ",  # MEDIUM MATHEMATICAL SPACE
}

_FOLD_TABLE: Final[dict[int, str]] = {ord(k): v for k, v in _CONFUSABLE_PUNCTUATION.items()}


def normalise_newlines(text: str) -> str:
    """Collapse CRLF/CR/LS/PS to LF without changing any other character."""
    return _NEWLINES.sub("\n", text)


def fold_text(text: str) -> str:
    """Apply the full folding pipeline.  Idempotent: ``fold(fold(x)) == fold(x)``.

    Idempotence holds because (a) the output contains none of the discretionary
    characters, (b) NFKC is idempotent, and (c) every value in the confusable
    map is ASCII and is not itself a key of the map.
    """
    text = normalise_newlines(text)
    text = _DISCRETIONARY_AT_WRAP.sub("", text)
    text = _DISCRETIONARY_BARE.sub("", text)
    text = unicodedata.normalize("NFKC", text)
    return text.translate(_FOLD_TABLE)
