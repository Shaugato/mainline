# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""The measurements that turn "the reflow was real" into a number a reader can check.

Three families, and each answers a different objection a sceptic makes about decision D6.

**"You renumbered, you did not retypeset."**  :func:`kendall_tau_distance` counts the fraction of
clause pairs whose *relative order* the reflow inverted.  A renumbering — 7.3 becomes 8.3 because
a section was inserted above it — leaves every pair concordant and scores 0.0.  Only a change of
organising principle reorders, and this is the statistic that separates them.  A uniformly
random permutation scores 0.5 in expectation, so a value near 0.4 says the two schemes disagree
about the document's structure nearly as much as chance would, which is what "a chapter per
control class" versus "the order the work is done" means in one number.

**"The labels only look different."**  :func:`label_shape` erases the digits and keeps the
punctuation, so ``7.3.2(b)`` becomes ``N.N.N(b)`` and ``5.2.1`` becomes ``N.N.N``.  Two label
*grammars* that share no shape cannot be the same scheme with different numbers in it, and
:func:`schemes_are_disjoint` is that assertion.  This is a structural fact about the corpus, not
a statistic, and it is the cheapest thing in this file to falsify.

**"Nothing actually moved."**  :func:`footrule_displacement` is the mean absolute change in
ordinal, normalised by the largest displacement the document could have shown.  It is reported
alongside tau because the two fail differently: a document can be heavily reordered with small
displacements (adjacent swaps) or lightly reordered with enormous ones (one clause sent from the
front to the back), and a reader is entitled to know which happened.

Every function here is pure, takes no clock, and draws no randomness.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Sequence
from typing import Final

#: A permutation needs two elements before "relative order" means anything.  Named so the
#: guard reads as the definition it is rather than as a magic number in a comparison.
_MIN_COMPARABLE: Final[int] = 2

__all__ = [
    "footrule_displacement",
    "kendall_tau_distance",
    "label_shape",
    "scheme_shapes",
    "schemes_are_disjoint",
]

#: Every maximal digit run becomes ``N``.  Nothing else is touched, so separators, brackets and
#: any letter suffix survive and remain distinguishing.
_DIGITS: Final[re.Pattern[str]] = re.compile(r"\d+")


def label_shape(label: str) -> str:
    """``7.3.2(b)`` -> ``N.N.N(b)``; ``5.2.1`` -> ``N.N.N``.

    The *shape* is the label's grammar with its content removed.  Comparing shapes rather than
    labels is what makes "the numbering scheme changed" a checkable claim instead of an
    impression: two labels of the same shape are the same kind of address, whatever numbers are
    in them.
    """
    if not label:
        raise ValueError(
            "a printed label cannot be empty; a clause with no address is not a clause"
        )
    return _DIGITS.sub("N", label)


def scheme_shapes(labels: Iterable[str]) -> tuple[str, ...]:
    """Return the distinct label shapes present, sorted: the generation's grammar, observed."""
    return tuple(sorted({label_shape(label) for label in labels}))


def schemes_are_disjoint(
    before: Iterable[str], after: Iterable[str]
) -> tuple[bool, tuple[str, ...]]:
    """Report whether the two generations share **no** label grammar.

    Returns the verdict and the shared shapes, so a failure names what overlapped rather than
    only that something did.  Overlap is not automatically wrong — a real retypeset could keep
    one address form — but it is the difference between "a different scheme" and "the same
    scheme, renumbered", and the corpus claims the former.
    """
    shared = tuple(sorted(set(scheme_shapes(before)) & set(scheme_shapes(after))))
    return (not shared, shared)


def kendall_tau_distance(before: Sequence[int], after: Sequence[int]) -> float:
    """Fraction of clause pairs whose relative order the reflow inverted, in ``[0, 1]``.

    ``before[i]`` and ``after[i]`` are the same clause's ordinal on the two sides.  A pair is
    *discordant* when the two sides disagree about which of the two clauses comes first.  Ties on
    either side are impossible — an ordinal is a position within one document — and are refused
    rather than silently counted as concordant, because a tie would mean two clauses claiming one
    slot, which is a corpus bug wearing a statistic as a disguise.

    A document of fewer than two clauses has no pairs; it returns 0.0 and the caller is expected
    to exclude it from any mean, which :func:`mainline_corpus.reflow.build` does.
    """
    if len(before) != len(after):
        raise ValueError(
            f"a permutation needs the same clauses on both sides: {len(before)} before, "
            f"{len(after)} after"
        )
    count = len(before)
    if count < _MIN_COMPARABLE:
        return 0.0
    if len(set(before)) != count or len(set(after)) != count:
        raise ValueError(
            "ordinals are not unique within the document; two clauses cannot occupy one position, "
            "so this is a corpus defect and not a measurable reordering"
        )
    discordant = 0
    for i in range(count - 1):
        for j in range(i + 1, count):
            if (before[i] - before[j]) * (after[i] - after[j]) < 0:
                discordant += 1
    return discordant / (count * (count - 1) / 2)


def footrule_displacement(before: Sequence[int], after: Sequence[int]) -> float:
    """Mean absolute ordinal change, normalised by the maximum a document of this size allows.

    The normaliser is Diaconis and Graham's bound for Spearman's footrule: the total displacement
    of the full reversal, ``floor(n^2 / 2)``.  Dividing by it puts every document on one scale,
    so a 13-clause permit form and a 36-clause procedure are comparable in the same column.
    """
    if len(before) != len(after):
        raise ValueError(
            f"a permutation needs the same clauses on both sides: {len(before)} before, "
            f"{len(after)} after"
        )
    count = len(before)
    if count < _MIN_COMPARABLE:
        return 0.0
    total = sum(abs(a - b) for a, b in zip(before, after, strict=True))
    return total / float(count * count // 2)
