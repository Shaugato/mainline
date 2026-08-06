# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""De-hyphenation across line wraps.

A hyphen at the end of a line is ambiguous: it is either the typesetter's
(``isola-`` / ``tion``) or the compound's (``lock-`` / ``out``).  Getting it
wrong is not cosmetic — it changes ``canon_text``, so it changes
``canon_sha256``, so the same clause typeset two ways stops matching at stage
S1 and arrives at adjudication as residue.

The decision is a four-step ladder against the committed lexicon, and the order
is chosen so that the *outcome does not depend on where the line happened to
break*:

1. ``left-right`` is a known compound  -> keep the hyphen.
2. ``leftright`` is a known closed word -> join.
3. both fragments are known words       -> keep the hyphen (a compound the
   lexicon has not enumerated; keeping it is the reversible choice).
4. otherwise                            -> join.

Step 1 precedes step 2 deliberately.  For ``lock-out``, whose closed form
``lockout`` is also a real word, checking the compound list first is what makes
the wrapped and unwrapped presentations agree.

Only hyphens **at a line break** are considered.  An in-line hyphen is left
exactly as written; the fold pass has already normalised every dash variant to
U+002D, so ``lock-out`` and ``lock<U+2010>out`` were the same string before this
module ran.
"""

from __future__ import annotations

import re
from typing import Final

from .lexicon import DomainLexicon, load_lexicon

__all__ = ["dehyphenate"]

# 'word-' at end of line, optional trailing spaces, the break, indentation,
# then the continuation fragment.  Both fragments are letters only: a hyphen
# between a letter and a digit (P-101A) is never a wrap artefact to repair.
_WRAP_HYPHEN: Final[re.Pattern[str]] = re.compile(
    r"(?P<left>[^\W\d_]{1,40})-[ \t]*\n[ \t]*(?P<right>[^\W\d_]{1,40})"
)


def dehyphenate(text: str, lexicon: DomainLexicon | None = None) -> str:
    """Resolve every line-wrap hyphen in ``text``.

    Idempotent by construction: the output contains no ``-`` immediately
    followed by a line break, so a second pass finds nothing to do.
    """
    lex = load_lexicon() if lexicon is None else lexicon

    def resolve(match: re.Match[str]) -> str:
        left = match.group("left")
        right = match.group("right")
        if lex.is_compound(left, right):
            return f"{left}-{right}"
        if lex.is_word(left + right):
            return f"{left}{right}"
        if lex.is_word(left) and lex.is_word(right):
            return f"{left}-{right}"
        return f"{left}{right}"

    # A single pass cannot handle two wrap hyphens that share a fragment
    # ('a-\nb-\nc'), because the first substitution consumes 'b'.  Iterate to a
    # fixpoint; the text strictly shortens each round, so this terminates.
    previous = text
    while True:
        current = _WRAP_HYPHEN.sub(resolve, previous)
        if current == previous:
            return current
        previous = current
