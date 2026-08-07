# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""``pg_trgm``-compatible trigram similarity, computed in the application.

Why this module exists at all, given that CockroachDB ships ``similarity()``:
the cascade must be able to run, and be tested, with **no cluster**.  S2's floor
and S3's recorded features are decided by a number, and a number that can only
be produced by a database is a number no unit test can hold to account.  So the
function lives here and the cluster's own ``similarity()`` is checked against it
by an integration test that skips cleanly when no cluster is reachable.

**The recipe, transcribed from PostgreSQL's ``contrib/pg_trgm``** (which is what
CockroachDB's ``similarity()`` is documented as being compatible with):

1. the string is lowercased;
2. it is split into maximal runs of alphanumeric characters — with the default
   ``KEEPONLYALNUM`` build, every other character is a separator;
3. each word ``w`` is padded to ``"  " + w + " "`` and every length-3 substring
   of the padded word is a trigram, so a word of length *L* yields *L+1* of
   them;
4. ``similarity(a, b) = |T(a)  intersect  T(b)| / |T(a)  union  T(b)|`` over the **distinct**
   trigram sets.

**Traps this module exists to keep the rest of the package away from** (risk
R-A6):

* CockroachDB supports ``similarity()``, ``show_trgm()`` and ``%``.  It does
  **not** support ``word_similarity()``, ``strict_word_similarity()``, or the
  entire ``<->`` trigram distance-operator family.  No query in this package
  orders by a trigram distance operator; SQL filters with ``%`` and scores with
  ``similarity()``.  (The ``<->`` on a ``VECTOR`` column is an unrelated
  operator and is not affected — see :mod:`.semantic`.)
* Trigram matching needs at least 3 characters and does not work on collated
  strings.

**Unverified.**  Step 2's notion of "alphanumeric" is Python's Unicode-aware
``str.isalnum``; PostgreSQL's is locale-aware and, for a single-byte encoding,
ASCII-only.  On the ASCII procedure text this system handles the two agree, and
``tests/integration/algorithms/candidates/test_similarity_matches_cluster.py``
asserts it against a live cluster — but only when one is reachable.  Outside
ASCII the two may diverge and nothing here has measured it.
"""

from __future__ import annotations

from functools import lru_cache

__all__ = [
    "MIN_TRIGRAM_LENGTH",
    "similarity",
    "trigrams",
]

MIN_TRIGRAM_LENGTH = 3
"""Below this length pg_trgm produces no usable match — documented, not chosen."""


def _words(text: str) -> list[str]:
    """Maximal runs of alphanumeric characters, lowercased."""
    words: list[str] = []
    current: list[str] = []
    for ch in text.lower():
        if ch.isalnum():
            current.append(ch)
        elif current:
            words.append("".join(current))
            current = []
    if current:
        words.append("".join(current))
    return words


@lru_cache(maxsize=4096)
def trigrams(text: str) -> frozenset[str]:
    """Shred ``text`` into its distinct trigram set, as ``show_trgm()`` reports it.

    Cached because S2 compares one query against every record in a document and
    would otherwise re-shred the same query text once per record.  The cache is
    keyed on the whole string and is therefore safe: ``trigrams`` is pure.
    """
    out: set[str] = set()
    for word in _words(text):
        padded = f"  {word} "
        for i in range(len(padded) - 2):
            out.add(padded[i : i + 3])
    return frozenset(out)


def similarity(left: str, right: str) -> float:
    """``pg_trgm.similarity`` — Jaccard over distinct trigram sets.

    Two empty (or sub-trigram) inputs score ``0.0`` rather than ``1.0``.  That
    is pg_trgm's behaviour and it is also the safe one here: "these two clauses
    are identical because neither of them has any content" is not a statement
    this cascade should be able to make.
    """
    a = trigrams(left)
    b = trigrams(right)
    if not a or not b:
        return 0.0
    shared = len(a & b)
    if shared == 0:
        return 0.0
    return shared / (len(a) + len(b) - shared)
