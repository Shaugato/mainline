# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""Shared text surgery.  Small, boring, and deliberately not a template engine.

Every mutation in both catalogues is a substring edit on a document.  Keeping
the primitives here means an operator is three lines and a reader can see the
whole of what it did; a mutation produced by a general rewriter would be a
mutation nobody could describe in the artefact.
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

__all__ = [
    "decimal_str",
    "find_ci",
    "hyphenate_at",
    "insert_before",
    "replace_first_ci",
]


def find_ci(haystack: str, needle: str) -> int:
    """Index of the first case-insensitive occurrence, or ``-1``.

    Case-insensitive because a procedure library capitalises the same phrase
    differently at the start of a sentence and in the middle of one, and an
    operator that only matched one casing would silently decline half the
    fixtures — which shows up as a smaller denominator and a better-looking kill
    rate.
    """
    return haystack.lower().find(needle.lower())


def replace_first_ci(text: str, needle: str, replacement: str) -> str | None:
    """Replace the first case-insensitive occurrence.  ``None`` when absent.

    ``None`` rather than an unchanged string: an operator must be able to tell
    "I changed nothing" from "I changed something into itself", and returning
    the input for both makes an inapplicable operator indistinguishable from a
    no-op one.
    """
    at = find_ci(text, needle)
    if at < 0:
        return None
    return text[:at] + replacement + text[at + len(needle) :]


def insert_before(text: str, needle: str, inserted: str) -> str | None:
    """Insert ``inserted`` immediately before the first occurrence of ``needle``."""
    at = find_ci(text, needle)
    if at < 0:
        return None
    return text[:at] + inserted + text[at:]


def decimal_str(value: Decimal) -> str:
    """Render a magnitude the way a drafter would type it.

    Quantised to three decimal places and then stripped of trailing zeros, so a
    1 % nudge of ``400`` prints ``404`` and a 1 % nudge of ``19.5`` prints
    ``19.695``.  The quantisation is :data:`~decimal.ROUND_HALF_UP` rather than
    banker's rounding because the mutant text is read by a person and half-up is
    what a person expects; nothing downstream compares two roundings, so the
    choice costs nothing and surprises nobody.
    """
    quantised = value.quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)
    text = format(quantised, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text or "0"


def hyphenate_at(word: str, position: int) -> str:
    r"""Break one word with a soft hyphen and a newline, the way a reflow does.

    ``pressure`` at position 4 becomes ``pres-\\nsure``.  CANONHOLD's
    de-hyphenator is expected to put it back together, which is the whole
    content of the ``reflow_rewrap`` SURVIVE class.
    """
    if not 0 < position < len(word):
        return word
    return f"{word[:position]}-\n{word[position:]}"
