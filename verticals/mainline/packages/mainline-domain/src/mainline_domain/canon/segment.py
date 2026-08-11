# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""FastCDC-style content-defined segmentation over the canonical token stream.

Ingest is layout-first: paragraph boundaries come from the layout model
(Textract ``LAYOUT_TEXT`` / ``LAYOUT_SECTION_HEADER`` / ``LAYOUT_LIST``), not
from newline guessing.  This module is the **fallback** for the documents that
give no reliable structure — a scanned typewritten procedure, a plain-text
export, a wall of prose with no numbering.

Why content-defined and not fixed-size: a local edit perturbs only local
boundaries.  Insert a sentence in clause 3 and fixed-size chunking shifts every
boundary in the document, so every downstream clause looks new; content-defined
chunking moves at most the boundaries adjacent to the edit.  That property is
precisely what clause identity needs.

Implementation notes, all of them deliberate:

* **Gear hash over tokens, not bytes.**  The unit of a clause is a word; hashing
  bytes makes a boundary sensitive to a single character of OCR noise.
* **The gear table is derived, not random.**  256 entries, each
  ``blake2b(domain || index)`` truncated to 64 bits.  It is a pure function of a
  committed constant, so an opposing expert can regenerate it in four lines.
  Python's builtin ``hash`` is salted per process and appears nowhere.
* **Normalised chunking (FastCDC NC=2).**  A hard mask before the average size
  and an easy mask after it, which pulls the chunk-size distribution towards the
  average and reduces the number of forced ``max``-size cuts.
* **min/avg/max = 40/120/400 tokens**, per the architecture.
"""

from __future__ import annotations

import hashlib
from typing import Final

__all__ = [
    "AVG_TOKENS",
    "GEAR",
    "MAX_TOKENS",
    "MIN_TOKENS",
    "gear_table",
    "segment_tokens",
]

MIN_TOKENS: Final[int] = 40
AVG_TOKENS: Final[int] = 120
MAX_TOKENS: Final[int] = 400

_GEAR_DOMAIN: Final[bytes] = b"mainline/canon/gear/v1"
_MASK64: Final[int] = (1 << 64) - 1

# Normalised-chunking masks.  MASK_HARD has more set bits than log2(avg), so a
# cut before the average size is unlikely; MASK_EASY has fewer, so a cut after it
# is likely.  Bit positions are spread rather than contiguous, which is what the
# FastCDC paper does to avoid correlating with the low bits of the rolling hash.
MASK_HARD: Final[int] = 0b0000000000000000000101010101010101010101010100000000000000000000
MASK_EASY: Final[int] = 0b0000000000000000000000000000010101010101010000000000000000000000


def gear_table() -> tuple[int, ...]:
    """The 256-entry gear table, derived from a committed domain constant."""
    entries: list[int] = []
    for index in range(256):
        digest = hashlib.blake2b(_GEAR_DOMAIN + index.to_bytes(2, "big"), digest_size=8).digest()
        entries.append(int.from_bytes(digest, "big"))
    return tuple(entries)


GEAR: Final[tuple[int, ...]] = gear_table()


def _token_byte(token: str) -> int:
    """Map a token to a gear-table index with a keyed, unsalted hash."""
    return hashlib.blake2b(token.encode("utf-8"), digest_size=1).digest()[0]


def segment_tokens(
    tokens: tuple[str, ...],
    *,
    min_tokens: int = MIN_TOKENS,
    avg_tokens: int = AVG_TOKENS,
    max_tokens: int = MAX_TOKENS,
) -> tuple[tuple[int, int], ...]:
    """Cut a token stream into segments; return half-open ``(start, end)`` token
    index ranges covering every token exactly once.

    An input shorter than ``min_tokens`` is one segment.  A final segment
    shorter than ``min_tokens`` is kept as-is rather than merged backwards:
    merging would make the last boundary depend on the document's length, which
    is exactly the non-locality content-defined chunking exists to avoid.
    """
    if not (0 < min_tokens <= avg_tokens <= max_tokens):
        raise ValueError("require 0 < min_tokens <= avg_tokens <= max_tokens")

    n = len(tokens)
    if n == 0:
        return ()
    if n <= min_tokens:
        return ((0, n),)

    cuts: list[tuple[int, int]] = []
    start = 0
    while start < n:
        remaining = n - start
        if remaining <= min_tokens:
            cuts.append((start, n))
            break

        limit = min(remaining, max_tokens)
        normal = min(remaining, avg_tokens)
        fingerprint = 0
        cut = limit

        for offset in range(min_tokens, limit):
            fingerprint = ((fingerprint << 1) + GEAR[_token_byte(tokens[start + offset])]) & _MASK64
            mask = MASK_HARD if offset < normal else MASK_EASY
            if fingerprint & mask == 0:
                cut = offset
                break

        cuts.append((start, start + cut))
        start += cut

    return tuple(cuts)
