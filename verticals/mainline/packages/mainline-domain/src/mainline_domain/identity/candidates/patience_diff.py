# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""Patience diff over tokens — anchored on rare tokens, so moves stay legible.

Myers's algorithm minimises the edit script.  On a reordered procedure that is
exactly the wrong objective: the shortest script for "paragraph (c) moved above
paragraph (b)" is a shredded interleaving that reads as a rewrite, and a
rewrite is what an adversary wants a reordering to look like.  Patience diff
anchors on tokens that occur **exactly once on each side**, takes the longest
increasing subsequence of those anchors, and recurses into the gaps — so the
common structure is found first and what is left over is genuinely different
([git diffcore](https://git-scm.com/docs/gitdiffcore); Bram Cohen's patience
algorithm).

Two outputs matter to this package, and the second is the one the ANN stage
cannot produce:

* :func:`patience_similarity` — a token-level agreement fraction, recorded as a
  candidate feature beside the character-level edit distance.
* :func:`moved_blocks` — the unique-common tokens that the LIS had to *drop*.
  Those are precisely the anchors whose relative order crossed, which is to say
  the tokens that moved.  A refactor that preserves every control shows up as a
  handful of moved blocks and near-total agreement; a rewrite that quietly
  deletes a hold point shows up as a deletion.  Telling those two apart with a
  cosine is not possible, which is why this is here.

Deterministic, dependency-free, and total: every pair of token sequences
produces a complete, non-overlapping, in-order op list that reconstructs both
sides.  ``tests/unit/domain/candidates/test_patience_diff.py`` asserts that
reconstruction property over Hypothesis-generated inputs rather than over
examples, because an op list that does not tile the input is a diff that has
silently lost text.
"""

from __future__ import annotations

import re
from bisect import bisect_left
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Final, Literal

__all__ = [
    "DiffOp",
    "DiffTag",
    "MovedBlock",
    "matched_token_count",
    "moved_blocks",
    "patience_diff",
    "patience_similarity",
    "render",
    "tokenise",
]

DiffTag = Literal["equal", "delete", "insert", "replace"]

_TOKEN_RE: Final[re.Pattern[str]] = re.compile(r"\w+|[^\w\s]")


@dataclass(frozen=True, slots=True)
class DiffOp:
    """One half-open block pair.  ``a[a_start:a_end]`` became ``b[b_start:b_end]``."""

    tag: DiffTag
    a_start: int
    a_end: int
    b_start: int
    b_end: int

    @property
    def a_len(self) -> int:
        """How many ``a`` tokens this op covers."""
        return self.a_end - self.a_start

    @property
    def b_len(self) -> int:
        """How many ``b`` tokens this op covers."""
        return self.b_end - self.b_start


@dataclass(frozen=True, slots=True)
class MovedBlock:
    """A unique-common token whose position crossed another anchor's.

    ``token`` occurs exactly once in each side, so its identity is unambiguous;
    ``a_index``/``b_index`` are where it sits in each.  It is reported because
    the longest increasing subsequence of anchors could not include it without
    shrinking, which is the operational definition of "this moved".
    """

    token: str
    a_index: int
    b_index: int


def tokenise(text: str) -> tuple[str, ...]:
    """Word runs and single punctuation marks; whitespace dropped.

    Punctuation is kept as its own token rather than discarded because a comma
    that becomes a full stop can split one obligation into two, and a tokeniser
    that cannot see that is a tokeniser that reports the split as identity.
    """
    return tuple(_TOKEN_RE.findall(text))


def _unique_anchors(
    a: Sequence[str], b: Sequence[str], alo: int, ahi: int, blo: int, bhi: int
) -> list[tuple[int, int]]:
    """Tokens occurring exactly once in both windows, as ``(a_index, b_index)``.

    Sorted by ``a_index``.  This is the "patience" part: rare tokens carry far
    more information about correspondence than common ones, and restricting to
    *unique* ones makes the correspondence unambiguous instead of merely likely.
    """
    a_count: dict[str, int] = {}
    a_where: dict[str, int] = {}
    for i in range(alo, ahi):
        token = a[i]
        a_count[token] = a_count.get(token, 0) + 1
        a_where[token] = i
    b_count: dict[str, int] = {}
    b_where: dict[str, int] = {}
    for j in range(blo, bhi):
        token = b[j]
        b_count[token] = b_count.get(token, 0) + 1
        b_where[token] = j
    pairs = [(a_where[t], b_where[t]) for t, n in a_count.items() if n == 1 and b_count.get(t) == 1]
    pairs.sort()
    return pairs


def _longest_increasing(pairs: Sequence[tuple[int, int]]) -> list[tuple[int, int]]:
    """Longest strictly-increasing-in-``b`` subsequence of ``pairs`` (sorted by ``a``).

    Patience sorting itself: ``tails[k]`` is the smallest possible tail of an
    increasing subsequence of length ``k+1``, ``back`` reconstructs the chain.
    """
    if not pairs:
        return []
    tails: list[int] = []
    tail_index: list[int] = []
    back: list[int] = [-1] * len(pairs)
    for idx, (_, bj) in enumerate(pairs):
        pos = bisect_left(tails, bj)
        if pos == len(tails):
            tails.append(bj)
            tail_index.append(idx)
        else:
            tails[pos] = bj
            tail_index[pos] = idx
        back[idx] = tail_index[pos - 1] if pos else -1
    out: list[tuple[int, int]] = []
    cursor = tail_index[-1]
    while cursor != -1:
        out.append(pairs[cursor])
        cursor = back[cursor]
    out.reverse()
    return out


def _emit_gap(out: list[DiffOp], alo: int, ahi: int, blo: int, bhi: int) -> None:
    if alo < ahi and blo < bhi:
        out.append(DiffOp("replace", alo, ahi, blo, bhi))
    elif alo < ahi:
        out.append(DiffOp("delete", alo, ahi, blo, blo))
    elif blo < bhi:
        out.append(DiffOp("insert", alo, alo, blo, bhi))


def _recurse(
    a: Sequence[str],
    b: Sequence[str],
    alo: int,
    ahi: int,
    blo: int,
    bhi: int,
    out: list[DiffOp],
) -> None:
    prefix = 0
    while alo + prefix < ahi and blo + prefix < bhi and a[alo + prefix] == b[blo + prefix]:
        prefix += 1
    if prefix:
        out.append(DiffOp("equal", alo, alo + prefix, blo, blo + prefix))
        alo += prefix
        blo += prefix

    suffix = 0
    while (
        ahi - suffix - 1 >= alo
        and bhi - suffix - 1 >= blo
        and a[ahi - suffix - 1] == b[bhi - suffix - 1]
    ):
        suffix += 1
    tail = DiffOp("equal", ahi - suffix, ahi, bhi - suffix, bhi) if suffix else None
    ahi -= suffix
    bhi -= suffix

    if alo < ahi or blo < bhi:
        anchors = _longest_increasing(_unique_anchors(a, b, alo, ahi, blo, bhi))
        if not anchors:
            _emit_gap(out, alo, ahi, blo, bhi)
        else:
            ca, cb = alo, blo
            for ia, ib in anchors:
                _recurse(a, b, ca, ia, cb, ib, out)
                out.append(DiffOp("equal", ia, ia + 1, ib, ib + 1))
                ca, cb = ia + 1, ib + 1
            _recurse(a, b, ca, ahi, cb, bhi, out)

    if tail is not None:
        out.append(tail)


def _coalesce(ops: Sequence[DiffOp]) -> tuple[DiffOp, ...]:
    """Merge adjacent contiguous ops of the same tag.

    The recursion emits each anchor as its own one-token ``equal``; a reader
    (and a feature counter) wants "these 14 tokens are unchanged", not fourteen
    rows.  Merging never changes what the op list *says*, only how many rows it
    takes to say it.
    """
    merged: list[DiffOp] = []
    for op in ops:
        if op.a_len == 0 and op.b_len == 0:
            continue
        if merged:
            last = merged[-1]
            if last.tag == op.tag and last.a_end == op.a_start and last.b_end == op.b_start:
                merged[-1] = DiffOp(op.tag, last.a_start, op.a_end, last.b_start, op.b_end)
                continue
        merged.append(op)
    return tuple(merged)


def patience_diff(a: Sequence[str], b: Sequence[str]) -> tuple[DiffOp, ...]:
    """Diff ``a`` into ``b``, anchored on tokens unique to both sides.

    Total and tiling: concatenating the ``a`` ranges in order reproduces
    ``range(len(a))`` exactly, and likewise for ``b``.  Nothing is dropped and
    nothing overlaps, which is what makes :func:`matched_token_count` a count
    rather than an estimate.
    """
    out: list[DiffOp] = []
    _recurse(a, b, 0, len(a), 0, len(b), out)
    return _coalesce(out)


def matched_token_count(ops: Sequence[DiffOp]) -> int:
    """Tokens covered by ``equal`` ops."""
    return sum(op.a_len for op in ops if op.tag == "equal")


def patience_similarity(a: Sequence[str], b: Sequence[str]) -> float:
    """``2·matched / (len(a) + len(b))`` — the Dice agreement of the diff.

    In ``[0, 1]``; ``1.0`` exactly when the token sequences are equal; ``0.0``
    when both are empty (see :func:`~.trigram.similarity` for why two empty
    inputs must not score 1.0 anywhere in this cascade).

    **Not symmetric, and this is stated rather than hidden.**  Patience diff
    anchors on tokens that are unique *within a window*, and the windows the
    recursion produces differ by direction, so ``f(a, b)`` and ``f(b, a)`` can
    disagree — Hypothesis finds ``a=[b, c, a]``, ``b=[a, b, b, c]`` scoring
    0.286 one way and 0.571 the other.  git's own diff has the same property.

    The consequence is bounded on purpose: this number is a **recorded feature
    and a witness generator**, never the score of record.  S3 decides on
    token-level indel similarity, which *is* symmetric because it is derived
    from a metric — so no assignment in this system depends on which of two
    clause versions was passed first.  If this number ever becomes a score,
    that reasoning has to be redone.
    """
    total = len(a) + len(b)
    if total == 0:
        return 0.0
    return 2 * matched_token_count(patience_diff(a, b)) / total


def moved_blocks(a: Sequence[str], b: Sequence[str]) -> tuple[MovedBlock, ...]:
    """Unique-common tokens the LIS had to drop — i.e. the ones that moved.

    Computed at the top level only.  A token that is unique across the whole of
    both sides and whose order crossed another such token is a move in the
    document's own terms; recursing would report moves *within* a block that
    was itself moved, which is noise for the purpose this serves (telling a
    reflow apart from a rewrite).
    """
    pairs = _unique_anchors(a, b, 0, len(a), 0, len(b))
    kept = set(_longest_increasing(pairs))
    return tuple(
        MovedBlock(token=a[ia], a_index=ia, b_index=ib) for ia, ib in pairs if (ia, ib) not in kept
    )


def render(ops: Sequence[DiffOp], a: Sequence[str], b: Sequence[str]) -> tuple[str, ...]:
    """Render the op list as plain text, for residue features and adjudication.

    One line per op: ``"= 14 tokens"``, ``"- shall be verified"``,
    ``"+ should be verified"``.  Deliberately plain text: this string ends up
    in front of somebody signing a disposition, and a rendering that needs a
    viewer is a rendering that will be skipped.
    """
    lines: list[str] = []
    for op in ops:
        if op.tag == "equal":
            lines.append(f"= {op.a_len} token{'' if op.a_len == 1 else 's'}")
        elif op.tag == "delete":
            lines.append("- " + " ".join(a[op.a_start : op.a_end]))
        elif op.tag == "insert":
            lines.append("+ " + " ".join(b[op.b_start : op.b_end]))
        else:
            lines.append("- " + " ".join(a[op.a_start : op.a_end]))
            lines.append("+ " + " ".join(b[op.b_start : op.b_end]))
    return tuple(lines)
