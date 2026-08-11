# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""The stopword list, and the rule about what may never be in it.

Stopwords apply to **prose tokens only**.  An identifier, quantity, citation or CAS token is
never tested against this list, so no amount of unlucky overlap can delete ``K-401``,
``A-1``, ``no.`` or a unit symbol from a posting list.  That separation is the whole reason
:class:`~trappoint_recall.lexical.analyser.TokenClass` exists.

Two things are deliberately *absent* from the list even though a generic English stopword set
would contain them:

``no``, ``not``, ``off``, ``on``, ``over``, ``under``, ``down``, ``out``
    In an incident narrative these are the difference between "isolation valve **closed**"
    and "isolation valve **not** closed".  A recall channel that drops the negation and then
    tells a supervisor the two documents match has produced a false precedent, which under
    this design is a rubber stamp rather than a missed hit — the worse of the two failures.

``a``, ``i``, ``s``, ``t``, ``m``, ``c``, ``v``
    Single letters are dropped by length, not by list, so that they cannot silently become
    unavailable as unit symbols or identifier components if the length rule is ever relaxed.

The list is frozen and its contents feed the analyser fingerprint: editing it changes
``rule_fingerprint()`` and therefore fails the golden-digest test until the change is
acknowledged as a re-index.
"""

from __future__ import annotations

from typing import Final

__all__ = ["STOPWORDS", "STOPWORD_LIST_VERSION", "is_stopword"]

STOPWORD_LIST_VERSION: Final[str] = "mainline-en-prose/1"

#: Sorted for a stable fingerprint; membership is what matters, order is what is hashed.
STOPWORDS: Final[frozenset[str]] = frozenset(
    {
        "about",
        "above",
        "after",
        "again",
        "against",
        "all",
        "also",
        "although",
        "am",
        "among",
        "an",
        "and",
        "any",
        "are",
        "as",
        "at",
        "be",
        "because",
        "been",
        "before",
        "being",
        "below",
        "between",
        "both",
        "but",
        "by",
        "can",
        "could",
        "did",
        "do",
        "does",
        "doing",
        "during",
        "each",
        "either",
        "else",
        "few",
        "for",
        "from",
        "further",
        "had",
        "has",
        "have",
        "having",
        "he",
        "her",
        "here",
        "hers",
        "herself",
        "him",
        "himself",
        "his",
        "how",
        "however",
        "if",
        "in",
        "into",
        "is",
        "it",
        "its",
        "itself",
        "just",
        "me",
        "more",
        "most",
        "my",
        "myself",
        "neither",
        "nor",
        "now",
        "of",
        "once",
        "only",
        "or",
        "other",
        "ought",
        "our",
        "ours",
        "ourselves",
        "own",
        "per",
        "same",
        "she",
        "should",
        "so",
        "some",
        "such",
        "than",
        "that",
        "the",
        "their",
        "theirs",
        "them",
        "themselves",
        "then",
        "there",
        "these",
        "they",
        "this",
        "those",
        "through",
        "to",
        "too",
        "until",
        "up",
        "upon",
        "us",
        "very",
        "was",
        "we",
        "were",
        "what",
        "when",
        "where",
        "whether",
        "which",
        "while",
        "who",
        "whom",
        "whose",
        "why",
        "will",
        "with",
        "would",
        "you",
        "your",
        "yours",
        "yourself",
        "yourselves",
    }
)

#: Guard rail, asserted at import: the negations and prepositions that carry hazard meaning
#: must never drift into the list.  A stopword list is edited casually; this is not a casual
#: list.
_MUST_NOT_BE_STOPWORDS: Final[frozenset[str]] = frozenset(
    {
        "no",
        "not",
        "off",
        "on",
        "over",
        "under",
        "down",
        "out",
        "without",
        "never",
        "always",
        "failed",
        "open",
        "closed",
        "isolated",
    }
)

_overlap = STOPWORDS & _MUST_NOT_BE_STOPWORDS
if _overlap:  # pragma: no cover - import-time guard; firing means the list was edited wrongly
    raise RuntimeError(
        "stopword list contains hazard-bearing tokens: "
        + ", ".join(sorted(_overlap))
        + ". Dropping these turns 'valve not closed' into 'valve closed'."
    )


def is_stopword(token: str) -> bool:
    """True when a **prose** token should be discarded before stemming."""
    return token in STOPWORDS
