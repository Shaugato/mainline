# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""Confusable-character repair, confined to numeric literals.

The confusable classes are the classic scanner failures: ``l``/``1``/``I``,
``0``/``O``, ``5``/``S``.  Repairing them in free prose is how a canonicaliser
turns ``Oil`` into ``0i1`` and quietly rewrites a procedure.  So the repair is
gated by four conditions, all of which must hold for a token's core:

1. **It begins with a digit** (optionally after a sign).  A numeric literal
   starts with a digit.  This single rule is what keeps ``SO2``, ``IS0``,
   ``Oil``, ``loss`` and ``SOLE`` out of reach — every one of them begins with a
   letter.  The cost is stated openly: damage to the *leading* character of a
   number (``lO`` for ``10``) is **not** repaired.  A missed repair costs a
   match and produces residue, which is adjudicable; a wrong repair silently
   changes a setpoint, which is not.
2. **Every character is a digit, a confusable letter, or a numeric separator**
   (``. , / - +``).  One foreign character and the token is prose.
3. **At least one character is a real ASCII digit** before repair.  ``Ill`` and
   ``IO`` are all-confusable and carry no digit; they are left alone.
4. **At least one character is a confusable letter**, or there is nothing to do.

Repair is a 1:1 character substitution, so it never changes a length and never
invalidates an offset — a property the pipeline relies on when it shifts repair
spans past the excised numbering prefix.

Known limits, stated rather than hidden:

* A number glued to its unit (``1O0kPa``) fails condition 2 and is not repaired.
* Damage inside an equipment tag (``TK-2O4``) fails condition 2 and is not
  repaired.  Tags are anchors, and a damaged anchor is better reported as an
  anchor drop than silently reconstructed.
* ``S02`` is genuinely ambiguous between ``502`` and OCR damage to ``SO2``.
  Condition 1 resolves it by leaving it alone.
"""

from __future__ import annotations

from typing import Final

from ..contracts import OcrRepair
from .tokens import iter_tokens

__all__ = ["CONFUSABLE_MAP", "repair_numeric_confusables"]

CONFUSABLE_MAP: Final[dict[str, str]] = {
    "O": "0",
    "o": "0",
    "l": "1",
    "I": "1",
    "i": "1",
    "S": "5",
    "s": "5",
}

_SEPARATORS: Final[frozenset[str]] = frozenset(".,/-+")
_DIGITS: Final[frozenset[str]] = frozenset("0123456789")
_SIGNS: Final[frozenset[str]] = frozenset("+-")
_CONFUSABLES: Final[frozenset[str]] = frozenset(CONFUSABLE_MAP)
_ALLOWED: Final[frozenset[str]] = _DIGITS | _SEPARATORS | _CONFUSABLES

_TRANSLATION: Final[dict[int, str]] = {ord(k): v for k, v in CONFUSABLE_MAP.items()}


def _is_numeric_literal_core(core: str) -> bool:
    """The four conditions from the module docstring, in order."""
    if not core:
        return False
    head = core[0]
    if head in _SIGNS:
        if len(core) < 2 or core[1] not in _DIGITS:
            return False
    elif head not in _DIGITS:
        return False
    if any(ch not in _ALLOWED and ch not in _SIGNS for ch in core):
        return False
    if not any(ch in _DIGITS for ch in core):
        return False
    return any(ch in _CONFUSABLES for ch in core)


def repair_numeric_confusables(text: str) -> tuple[str, tuple[OcrRepair, ...]]:
    """Return ``(repaired_text, repairs)``.

    ``repaired_text`` has the same length as ``text``; every span in ``repairs``
    is a half-open offset into it and is valid in ``text`` too.
    """
    repairs: list[OcrRepair] = []
    pieces: list[str] = []
    cursor = 0

    for token in iter_tokens(text):
        start, end, core = token.core()
        if not _is_numeric_literal_core(core):
            continue
        repaired = core.translate(_TRANSLATION)
        if repaired == core:
            continue
        pieces.append(text[cursor:start])
        pieces.append(repaired)
        cursor = end
        repairs.append(OcrRepair(start=start, end=end, before=core, after=repaired))

    if not repairs:
        return text, ()

    pieces.append(text[cursor:])
    return "".join(pieces), tuple(repairs)
