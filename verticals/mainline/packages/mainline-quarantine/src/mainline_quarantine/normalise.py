# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
#
# ruff: noqa: RUF001, RUF002
#
# RUF001/RUF002 flag ambiguous Unicode characters in strings and docstrings. This
# is the module whose DATA IS a table of ambiguous Unicode characters: every key of
# CONFUSABLES is there precisely because it is indistinguishable from a Latin
# letter, and the docstrings have to be able to say so. The directive is file-scoped
# and appears nowhere else in the repository.
"""Unmasking: what the screen must see before it can decide anything.

An imperative written as ``ｉｇｎｏｒｅ　ａｌｌ　ｐｒｅｖｉｏｕｓ`` , as
``i<ZWSP>g<ZWSP>n<ZWSP>o<ZWSP>r<ZWSP>e``, as Cyrillic-\u0456gn\u043er\u0435, or as
``aWdub3JlIGFsbCBwcmV2aW91cw==`` is the same imperative. A screen that reads the raw
bytes sees four different documents and refuses none of them.

**Three rules this module keeps, because breaking any one of them would make the span
hash in a `document_intake_finding` row meaningless.**

1. **Folding is one character to one character.** Every transform here maps a single
   code point to a single code point or deletes it. Full ``NFKC`` is *not* applied to
   the string, because ``NFKC`` expands ligatures and some compatibility forms into
   several characters and every offset after the first one would then be a lie. Instead
   each character is normalised alone and the result is kept only when it is still one
   character.
2. **Deletions are recorded, not silently dropped.** Zero-width removal shifts every
   later offset, so :class:`Unmasked` carries an index map from folded position back to
   original position, and :meth:`Unmasked.original_span` is the only supported way to
   turn a match in the folded text into a span in the document a human will read.
3. **Decoding is once, never a loop.** A base64 run is decoded exactly one level.
   Recursive unwrapping is an unbounded amount of attacker-controlled work in the one
   component that must not be made expensive to run, and one level is what carries an
   instruction payload in practice.

Nothing here decides anything. It produces the several readings of a document that
:mod:`mainline_quarantine.screen` then applies its detectors to.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import re
import unicodedata
from dataclasses import dataclass
from typing import Final

__all__ = [
    "CONFUSABLES",
    "PUNCTUATION_FOLDS",
    "SPAN_DIGEST_DOMAIN",
    "ZERO_WIDTH",
    "DecodedRun",
    "Observation",
    "Unmasked",
    "collapse_whitespace",
    "decode_base64_runs",
    "span_sha256",
    "unmask",
]

#: Domain-separation prefix for :func:`span_sha256`. A finding row records the digest of
#: an offending span rather than the span itself, so that an operator triaging a queue of
#: findings is not re-reading the attack; the prefix keeps that digest from colliding
#: with any other sha256 in the ledger.
SPAN_DIGEST_DOMAIN: Final[bytes] = b"mainline/quarantine/span/v1"

#: Code points with no visual extent. Inside a word they are pure obfuscation: no
#: procedure, incident report or standard has ever needed a zero-width joiner between
#: the ``P`` and the ``-`` of an equipment tag.
#:
#: Written as escapes on purpose: a literal zero-width character in source is a
#: character no reviewer can see, and this is the one file where that would be a joke
#: at the reviewer's expense.
ZERO_WIDTH: Final[frozenset[str]] = frozenset(
    {
        "\u00ad",  # soft hyphen
        "\u200b",  # zero-width space
        "\u200c",  # zero-width non-joiner
        "\u200d",  # zero-width joiner
        "\u200e",  # left-to-right mark
        "\u200f",  # right-to-left mark
        "\u2060",  # word joiner
        "\u2061",  # function application
        "\u2062",  # invisible times
        "\u2063",  # invisible separator
        "\u2064",  # invisible plus
        "\u202a",  # left-to-right embedding
        "\u202b",  # right-to-left embedding
        "\u202c",  # pop directional formatting
        "\u202d",  # left-to-right override
        "\u202e",  # right-to-left override
        "\ufeff",  # zero-width no-break space / BOM
    }
)

#: Cyrillic and Greek letters that render as Latin ones. ``NFKC`` does **not** fold
#: these — they are distinct letters in distinct scripts, not compatibility forms — so
#: the map is explicit and each entry is a deliberate claim that the two are
#: indistinguishable in a sans-serif face at document size.
CONFUSABLES: Final[dict[str, str]] = {
    # Cyrillic lower case
    "а": "a",
    "е": "e",
    "о": "o",
    "р": "p",
    "с": "c",
    "у": "y",
    "х": "x",
    "ѕ": "s",
    "і": "i",
    "ј": "j",
    "һ": "h",
    "ӏ": "l",
    # Cyrillic upper case
    "А": "A",
    "В": "B",
    "Е": "E",
    "К": "K",
    "М": "M",
    "Н": "H",
    "О": "O",
    "Р": "P",
    "С": "C",
    "Т": "T",
    "У": "Y",
    "Х": "X",
    "Ѕ": "S",
    "І": "I",
    "Ј": "J",
    "Ӏ": "I",
    # Greek lower case
    "ο": "o",
    "ρ": "p",
    "ν": "v",
    "υ": "u",
    # Greek upper case
    "Α": "A",
    "Β": "B",
    "Ε": "E",
    "Ζ": "Z",
    "Η": "H",
    "Ι": "I",
    "Κ": "K",
    "Μ": "M",
    "Ν": "N",
    "Ο": "O",
    "Ρ": "P",
    "Τ": "T",
    "Υ": "Y",
    "Χ": "X",
}

#: Punctuation that folds to ASCII but is **not** evidence of anything. An en dash in a
#: procedure is typography, not an attack, and counting it as obfuscation would put
#: every professionally typeset document into the review queue — which is how a review
#: queue stops being read.
PUNCTUATION_FOLDS: Final[dict[str, str]] = {
    "‐": "-",
    "‑": "-",
    "‒": "-",
    "–": "-",
    "—": "-",
    "−": "-",
    "⁄": "/",
    "∕": "/",
}

#: A run long enough that it is base64 rather than a word. Twenty-four characters of
#: the base64 alphabet with no separator does not occur in plant prose; the shortest
#: useful instruction payload is longer than that.
_B64_RUN: Final[re.Pattern[str]] = re.compile(
    r"(?<![A-Za-z0-9+/=])[A-Za-z0-9+/]{24,}={0,2}(?![A-Za-z0-9+/=])"
)

#: A token, for the mixed-script test: the run of characters a reader sees as one word.
_TOKEN_CHARS: Final[re.Pattern[str]] = re.compile(r"[^\W_]|[-_/.]", re.UNICODE)

_WS: Final[re.Pattern[str]] = re.compile(r"\s+")

#: Below this share of printable characters, a base64 run decoded to binary rather than
#: to text and carries no instruction a language model would read.
_PRINTABLE_SHARE: Final[float] = 0.85


@dataclass(frozen=True, slots=True)
class Observation:
    """One masking artefact found in a document, with where it was and what it was."""

    kind: str
    span: tuple[int, int]
    raw: str
    folded: str


@dataclass(frozen=True, slots=True)
class DecodedRun:
    """A base64 run that decoded to text, and the text it decoded to."""

    span: tuple[int, int]
    encoded: str
    decoded: str


@dataclass(frozen=True, slots=True)
class Unmasked:
    """Every reading of one document that a detector must be applied to.

    Attributes:
        original: the document exactly as it arrived.
        folded: same length semantics minus zero-width characters, with confusables
            mapped to their Latin look-alikes.
        index_map: ``index_map[i]`` is the offset in ``original`` of ``folded[i]``.
        zero_width: every zero-width character removed, with its original span.
        confusables: every character folded, across scripts or punctuation.
        mixed_script: the subset of ``confusables`` that sat inside a token which also
            contained ASCII letters or digits. That is the signal — a Cyrillic ``е``
            inside an otherwise-Latin word is a substitution nobody makes by accident,
            whereas a wholly Cyrillic word is a language.
        decoded: every base64 run that decoded to text.
    """

    original: str
    folded: str
    index_map: tuple[int, ...]
    zero_width: tuple[Observation, ...]
    confusables: tuple[Observation, ...]
    mixed_script: tuple[Observation, ...]
    decoded: tuple[DecodedRun, ...]

    @property
    def obfuscated(self) -> bool:
        """Whether the document carried a masking artefact worth a human's time.

        Deliberately narrower than "anything was folded": punctuation folding is
        typography and does not appear here.
        """
        return bool(self.zero_width or self.mixed_script or self.decoded)

    def original_span(self, start: int, end: int) -> tuple[int, int]:
        """Map a half-open span in :attr:`folded` back onto :attr:`original`.

        The end is mapped through the last folded character in the span rather than
        through ``index_map[end]``, so a match that ends at the end of the string does
        not index past the map, and so a run of deleted characters immediately after a
        match is not silently included in the reported span.
        """
        if not self.index_map:
            return (0, 0)
        clamped_start = max(0, min(start, len(self.index_map) - 1))
        clamped_last = max(clamped_start, min(end, len(self.index_map)) - 1)
        return (self.index_map[clamped_start], self.index_map[clamped_last] + 1)


def _fold_char(char: str) -> tuple[str, str]:
    """Fold one character. Returns ``(replacement, kind)`` and never grows the string."""
    punctuation = PUNCTUATION_FOLDS.get(char)
    if punctuation is not None:
        return punctuation, "punctuation"
    mapped = CONFUSABLES.get(char)
    if mapped is not None:
        return mapped, "confusable_script"
    if char.isascii():
        return char, ""
    compatible = unicodedata.normalize("NFKC", char)
    # One-to-one only. `NFKC` of the ligature 'fi' is two characters, and accepting it
    # would shift every offset after it - see rule 1 in the module docstring.
    if len(compatible) == 1 and compatible != char:
        return compatible, "compatibility"
    return char, ""


def _token_bounds(text: str, position: int) -> tuple[int, int]:
    """Return the maximal token-character run containing ``position``."""
    start = position
    while start > 0 and _TOKEN_CHARS.fullmatch(text[start - 1]):
        start -= 1
    end = position + 1
    while end < len(text) and _TOKEN_CHARS.fullmatch(text[end]):
        end += 1
    return start, end


def _is_mixed_script(text: str, position: int) -> bool:
    """Whether the token around ``position`` also contains ASCII letters or digits."""
    start, end = _token_bounds(text, position)
    return any(char.isascii() and (char.isalpha() or char.isdigit()) for char in text[start:end])


def unmask(text: str) -> Unmasked:
    """Produce the folded, offset-preserving reading of a document plus its artefacts."""
    folded_chars: list[str] = []
    index_map: list[int] = []
    zero_width: list[Observation] = []
    confusables: list[Observation] = []
    mixed_script: list[Observation] = []

    for position, char in enumerate(text):
        if char in ZERO_WIDTH:
            zero_width.append(
                Observation(
                    kind="zero_width",
                    span=(position, position + 1),
                    raw=char,
                    folded="",
                )
            )
            continue
        replacement, kind = _fold_char(char)
        if kind:
            observation = Observation(
                kind=kind,
                span=(position, position + 1),
                raw=char,
                folded=replacement,
            )
            confusables.append(observation)
            if kind == "confusable_script" and _is_mixed_script(text, position):
                mixed_script.append(
                    Observation(
                        kind="mixed_script",
                        span=observation.span,
                        raw=char,
                        folded=replacement,
                    )
                )
        folded_chars.append(replacement)
        index_map.append(position)

    return Unmasked(
        original=text,
        folded="".join(folded_chars),
        index_map=tuple(index_map),
        zero_width=tuple(zero_width),
        confusables=tuple(confusables),
        mixed_script=tuple(mixed_script),
        decoded=decode_base64_runs(text),
    )


def decode_base64_runs(text: str) -> tuple[DecodedRun, ...]:
    """Decode every base64 run that yields text. One level, never recursive."""
    runs: list[DecodedRun] = []
    for match in _B64_RUN.finditer(text):
        encoded = match.group(0)
        decoded = _try_decode(encoded)
        if decoded is None:
            continue
        runs.append(DecodedRun(span=(match.start(), match.end()), encoded=encoded, decoded=decoded))
    return tuple(runs)


def _try_decode(encoded: str) -> str | None:
    """Return the decoded text of a base64 run, or ``None`` if it is not text."""
    stripped = encoded.rstrip("=")
    for pad in ("", "=", "=="):
        candidate = stripped + pad
        if len(candidate) % 4:
            continue
        try:
            raw = base64.b64decode(candidate, validate=True)
        except (binascii.Error, ValueError):
            continue
        if not raw:
            continue
        try:
            decoded = raw.decode("utf-8")
        except UnicodeDecodeError:
            continue
        printable = sum(1 for char in decoded if char.isprintable() or char in " \t\r\n")
        if printable / len(decoded) < _PRINTABLE_SHARE:
            continue
        return decoded
    return None


def collapse_whitespace(text: str) -> str:
    """Collapse runs of whitespace to one space and strip the ends."""
    return _WS.sub(" ", text).strip()


def span_sha256(text: str) -> str:
    """Domain-separated digest of an offending span, for a `document_intake_finding`."""
    return hashlib.sha256(SPAN_DIGEST_DOMAIN + text.encode("utf-8")).hexdigest()
