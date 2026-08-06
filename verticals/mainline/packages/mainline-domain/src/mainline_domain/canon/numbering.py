# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""Numbering-prefix excision — the move that makes renumbering a non-event.

Akoma Ntoso separates ``@eId`` (expression level, *changes* when a document is
renumbered) from ``@wId`` (work level, never changes).  ``printed_label`` is our
``@eId``; ``clause_uuid`` is our ``@wId``.  This module is the mechanical part
of that separation: the printed label is lifted out of the text **before** the
digest is taken, so ``7.3.2(b)`` becoming ``4.1.1`` moves no bytes that identity
depends on.

Excision loops to a fixpoint.  Two reasons: a prefix can genuinely be layered
(``7.3.2 (b) (ii)``), and a fixpoint is what makes the whole canonicaliser
idempotent — after one pass the text provably does not begin with a numbering
prefix, so a second pass excises nothing.

What is deliberately **not** matched:

* a bare number with no punctuation (``50 psig is the limit``) — a setpoint is
  not a label;
* a bare letter with a full stop (``I. ``, ``i.e.``) — the false-positive rate
  against prose is unacceptable, so letter labels must be parenthesised or
  closed with ``)``;
* anything not at the very start of the text.
"""

from __future__ import annotations

import re
from typing import Final

__all__ = ["excise_numbering", "normalise_label"]

_KEYWORD: Final[str] = r"(?:section|clause|cl\.|item|para(?:graph)?|art(?:icle)?|step|§)\s*"

_PREFIX_PATTERNS: Final[tuple[re.Pattern[str], ...]] = (
    # 7.3.2, 7.3.2., 7.3.2), optionally with '(b)' / '(ii)' sub-parts, optionally
    # introduced by 'Section'/'Clause'/'§'.
    re.compile(
        r"^(?:" + _KEYWORD + r")?"
        r"\d+(?:\.\d+)+\s*"
        r"(?:\((?:[A-Za-z]{1,4}|\d{1,3})\)\s*)*"
        r"[.):\-]?\s+",
        re.IGNORECASE,
    ),
    # 1. / 1) / 1: with mandatory punctuation, optionally with sub-parts.
    re.compile(
        r"^(?:" + _KEYWORD + r")?"
        r"\d{1,3}\s*(?:\((?:[A-Za-z]{1,4}|\d{1,3})\)\s*)*"
        r"[.):]\s+",
        re.IGNORECASE,
    ),
    # (a) / (iv) / (12) / a) / iv) — letter labels must be bracketed.
    re.compile(r"^\((?:[A-Za-z]{1,4}|\d{1,3})\)\s*", re.IGNORECASE),
    re.compile(r"^(?:[A-Za-z]{1,4}|\d{1,3})\)\s+", re.IGNORECASE),
    # bullets that carry no meaning at all
    re.compile(r"^[•·▪●‣∙◦]\s*"),
)

_LABEL_JUNK: Final[re.Pattern[str]] = re.compile(r"\s+")
_LABEL_KEYWORD: Final[re.Pattern[str]] = re.compile(r"^" + _KEYWORD, re.IGNORECASE)
_BULLETS: Final[str] = "•·▪●‣∙◦"


def normalise_label(prefix: str) -> str | None:
    """Turn an excised prefix into its printed label, or ``None`` for a bullet.

    ``'7.3.2 (b)   '`` -> ``'7.3.2(b)'``; ``'Section 4.1.1 '`` -> ``'4.1.1'``;
    ``'\\u2022 '`` -> ``None``.  The label is presentation and is stored as
    ``clause_version.printed_label``; nothing may key on it.
    """
    label = _LABEL_KEYWORD.sub("", prefix.strip())
    label = _LABEL_JUNK.sub("", label).strip(" .:-")
    label = label.strip(_BULLETS).strip()
    if label.endswith(")") and "(" not in label:
        # 'iv)' is a label; '7.3.2(b)' keeps its bracket because it has both.
        label = label[:-1]
    return label or None


def excise_numbering(text: str) -> tuple[str, str | None, str | None]:
    """Return ``(body, numbering_prefix, printed_label)``.

    ``numbering_prefix`` is the exact excised substring including its trailing
    whitespace (so ``prefix + body == text``); ``printed_label`` is its
    normalised form.  Both are ``None`` when the text carries no prefix.
    """
    body = text
    consumed = 0

    while True:
        for pattern in _PREFIX_PATTERNS:
            match = pattern.match(body)
            if match is not None and match.end() > 0 and match.end() < len(body):
                consumed += match.end()
                body = body[match.end() :]
                break
        else:
            break

    if consumed == 0:
        return text, None, None
    return body, text[:consumed], normalise_label(text[:consumed])
