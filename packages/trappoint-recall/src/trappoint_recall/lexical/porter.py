# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""The Porter (1980) stemmer, written from the published rule set.

Why a hand-written stemmer rather than a dependency: this module is part of a **versioned
analyser**.  A change in the stemmer changes every posting in ``lex_posting``, so it has to be
a migration rather than an accident (see :mod:`trappoint_recall.lexical.analyser`).  A
third-party stemmer that silently improves its rules in a patch release is precisely the
failure this design refuses to accept — the analyser fingerprint would not move, the golden
digest would go red on a machine that resolved a different wheel, and nobody would know which
of the two was right.  Vendoring the algorithm makes the analyser's behaviour a property of
this repository's own bytes.

Scope, stated honestly: this is the **original 1980 algorithm**, not Porter2/Snowball.  It is
applied to prose tokens only.  Identifier-class tokens (``K-401``, ``H2S``, ``30 cfr 57.22239``)
never reach it — stemming ``K-401`` is exactly how a channel whose job is rare identifiers
loses them.

Reference: M.F. Porter, "An algorithm for suffix stripping", *Program* 14(3), 1980.
"""

from __future__ import annotations

from typing import Final

__all__ = ["PORTER_VERSION", "stem"]

#: Bumped only when a rule changes.  It is one of the inputs to the analyser fingerprint.
PORTER_VERSION: Final[str] = "porter-1980/1"

_VOWELS: Final[frozenset[str]] = frozenset("aeiou")


def _is_consonant(word: str, i: int) -> bool:
    """``y`` is a consonant unless the letter before it is a consonant (Porter's definition)."""
    ch = word[i]
    if ch in _VOWELS:
        return False
    if ch != "y":
        return True
    return i == 0 or not _is_consonant(word, i - 1)


def _measure(word: str) -> int:
    """Porter's *m*: the number of ``VC`` sequences in ``[C](VC)^m[V]``."""
    n = 0
    i = 0
    length = len(word)
    while i < length and _is_consonant(word, i):
        i += 1
    while i < length:
        while i < length and not _is_consonant(word, i):
            i += 1
        if i >= length:
            break
        n += 1
        while i < length and _is_consonant(word, i):
            i += 1
    return n


def _has_vowel(word: str) -> bool:
    return any(not _is_consonant(word, i) for i in range(len(word)))


def _ends_double_consonant(word: str) -> bool:
    return (
        len(word) >= 2
        and word[-1] == word[-2]
        and _is_consonant(word, len(word) - 1)
    )


def _ends_cvc(word: str) -> bool:
    """``*o``: consonant-vowel-consonant where the final consonant is not ``w``, ``x`` or ``y``."""
    if len(word) < 3:
        return False
    last = len(word) - 1
    return (
        _is_consonant(word, last)
        and not _is_consonant(word, last - 1)
        and _is_consonant(word, last - 2)
        and word[last] not in "wxy"
    )


def _step1a(word: str) -> str:
    if word.endswith("sses"):
        return word[:-2]
    if word.endswith("ies"):
        return word[:-2]
    if word.endswith("ss"):
        return word
    if word.endswith("s"):
        return word[:-1]
    return word


def _step1b_tail(word: str) -> str:
    """The shared continuation of the ``ed`` / ``ing`` branches."""
    if word.endswith(("at", "bl", "iz")):
        return word + "e"
    if _ends_double_consonant(word) and word[-1] not in "lsz":
        return word[:-1]
    if _measure(word) == 1 and _ends_cvc(word):
        return word + "e"
    return word


def _step1b(word: str) -> str:
    if word.endswith("eed"):
        return word[:-1] if _measure(word[:-3]) > 0 else word
    if word.endswith("ed"):
        base = word[:-2]
        return _step1b_tail(base) if _has_vowel(base) else word
    if word.endswith("ing"):
        base = word[:-3]
        return _step1b_tail(base) if _has_vowel(base) else word
    return word


def _step1c(word: str) -> str:
    if word.endswith("y") and _has_vowel(word[:-1]):
        return word[:-1] + "i"
    return word


#: Longest suffix first within each step; the first match wins.
_STEP2: Final[tuple[tuple[str, str], ...]] = (
    ("ational", "ate"), ("tional", "tion"), ("enci", "ence"), ("anci", "ance"),
    ("izer", "ize"), ("abli", "able"), ("alli", "al"), ("entli", "ent"),
    ("eli", "e"), ("ousli", "ous"), ("ization", "ize"), ("ation", "ate"),
    ("ator", "ate"), ("alism", "al"), ("iveness", "ive"), ("fulness", "ful"),
    ("ousness", "ous"), ("aliti", "al"), ("iviti", "ive"), ("biliti", "ble"),
)

_STEP3: Final[tuple[tuple[str, str], ...]] = (
    ("icate", "ic"), ("ative", ""), ("alize", "al"), ("iciti", "ic"),
    ("ical", "ic"), ("ful", ""), ("ness", ""),
)

#: Step 4 strips a derivational suffix when ``m > 1``.  ``ational`` and ``tional`` are NOT here
#: — they belong to step 2, which has already run.  Including them made this step match
#: ``rational`` on ``ational``, fail the measure test on the one-letter stem ``r``, and return
#: without ever trying ``al``; ``rational`` stemmed to itself while ``rationally`` stemmed to
#: ``ration``, so the two forms never met in a posting list.
_STEP4: Final[tuple[str, ...]] = (
    "ement", "ance", "ence", "able", "ible", "ment",
    "ant", "ent", "ism", "ate", "iti", "ous", "ive", "ize", "al", "er",
    "ic", "ou",
)


def _longest_suffix(word: str, table: tuple[tuple[str, str], ...]) -> tuple[str, str] | None:
    best: tuple[str, str] | None = None
    for suffix, replacement in table:
        if word.endswith(suffix) and (best is None or len(suffix) > len(best[0])):
            best = (suffix, replacement)
    return best


def _step2(word: str) -> str:
    hit = _longest_suffix(word, _STEP2)
    if hit is None:
        return word
    suffix, replacement = hit
    base = word[: len(word) - len(suffix)]
    return base + replacement if _measure(base) > 0 else word


def _step3(word: str) -> str:
    hit = _longest_suffix(word, _STEP3)
    if hit is None:
        return word
    suffix, replacement = hit
    base = word[: len(word) - len(suffix)]
    return base + replacement if _measure(base) > 0 else word


def _step4(word: str) -> str:
    best: str | None = None
    for suffix in _STEP4:
        if word.endswith(suffix) and (best is None or len(suffix) > len(best)):
            best = suffix
    if best is not None:
        base = word[: len(word) - len(best)]
        return base if _measure(base) > 1 else word
    # `ion` only strips after `s` or `t`, so "nation" keeps its stem but "adoption" loses it.
    if word.endswith("ion"):
        base = word[:-3]
        if base.endswith(("s", "t")) and _measure(base) > 1:
            return base
    return word


def _step5(word: str) -> str:
    if word.endswith("e"):
        base = word[:-1]
        m = _measure(base)
        if m > 1 or (m == 1 and not _ends_cvc(base)):
            word = base
    if _measure(word) > 1 and _ends_double_consonant(word) and word.endswith("l"):
        word = word[:-1]
    return word


def stem(word: str) -> str:
    """Return the Porter stem of an already case-folded, purely alphabetic word.

    Words of two letters or fewer are returned unchanged, as in the original description.
    The caller is responsible for having decided that this token is *prose*; passing an
    identifier here is a bug in the caller, not something this function will detect.
    """
    if len(word) <= 2:
        return word
    result = _step1a(word)
    result = _step1b(result)
    result = _step1c(result)
    result = _step2(result)
    result = _step3(result)
    result = _step4(result)
    return _step5(result)
