# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
"""Three-way clause merge. Deterministic, model-free, and it never applies anything.

§8.3 states the division of labour in one line: **three-way clause merge is
deterministic; Claude explains a conflict, never resolves one.** This module is
the deterministic half, and it holds the whole of it — there is no model import
in this file and no code path that reaches one.

The algorithm is the classical diff3 of Khanna, Kunal and Pierce: match the base
against each side by longest common subsequence, walk the three cursors together
to find *stable* runs where all three agree, and treat everything between two
stable runs as an unstable chunk. An unstable chunk resolves cleanly in exactly
three cases — one side is unchanged from the base, or both sides made the same
change — and is a conflict otherwise.

Two decisions worth stating.

**A conflicted merge returns ``merged = None``.** Git writes conflict markers into
the working tree; we do not. A procedure containing ``<<<<<<<`` is a document a
person can commit by accident, and the whole subject of this package is a document
whose contents keep people alive. :meth:`Merge3Result.render_markers` exists for
*display* and says so; nothing in this package can write its output anywhere.

**A clean merge is still only a proposal.** §5.9: *a recorded resolution is
proposed, never auto-applied.* A clean three-way merge of safety text is not
evidence that the merged text is safe — it is evidence that the two edits did not
touch the same lines. Those are very different claims, and the second one is the
rubber-stamp accelerant this product exists not to build.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:
    from collections.abc import Sequence

__all__ = [
    "CLAUSE_DIGEST_DOMAIN",
    "ConflictRegion",
    "Merge3Result",
    "digest_lines",
    "merge3",
]

#: Domain separation for the base/ours/theirs digests stored on ``merge_conflict``.
CLAUSE_DIGEST_DOMAIN: Final[bytes] = b"mainline.clause_rendering.v1\x00"


@dataclass(frozen=True, slots=True)
class ConflictRegion:
    """One unstable chunk the two sides disagreed about.

    Line numbers are 0-based half-open starts into each of the three inputs, kept
    so a reviewer can find the region in the source rather than pattern-matching
    the text back out of it.
    """

    base: tuple[str, ...]
    ours: tuple[str, ...]
    theirs: tuple[str, ...]
    base_at: int
    ours_at: int
    theirs_at: int


@dataclass(frozen=True, slots=True)
class Merge3Result:
    """The outcome of one three-way merge.

    ``merged`` is ``None`` whenever ``conflicts`` is non-empty. There is no
    partially merged output: a document that is 90 % merged and 10 % conflict
    markers is a document somebody will commit.
    """

    merged: tuple[str, ...] | None
    conflicts: tuple[ConflictRegion, ...]

    @property
    def clean(self) -> bool:
        """True when the two edits did not touch the same region.

        Read the class docstring before treating this as approval. A clean merge
        says the edits did not collide. It does not say the result is correct, and
        nothing in this package will apply it.
        """
        return not self.conflicts

    def render_markers(
        self,
        *,
        ours_label: str = "SITE",
        theirs_label: str = "FLEET",
    ) -> str:
        """Render conflicts in git's marker format, **for a human to read**.

        For display only. This package holds no driver and no write path, so this
        string cannot reach a document from here — and it must not reach one from
        anywhere else either. It exists so a superintendent can see the
        disagreement in a shape they already know how to read.
        """
        if self.merged is not None:
            return "\n".join(self.merged)
        out: list[str] = []
        for region in self.conflicts:
            out.append(f"<<<<<<< {ours_label}")
            out.extend(region.ours)
            out.append("||||||| base")
            out.extend(region.base)
            out.append("=======")
            out.extend(region.theirs)
            out.append(f">>>>>>> {theirs_label}")
        return "\n".join(out)


def digest_lines(lines: Sequence[str]) -> bytes:
    """Return the SHA-256 of one clause rendering, over its lines joined by a newline.

    Domain-prefixed so a rendering digest can never be confused with a commit id
    or a ledger leaf that happens to hash the same bytes.
    """
    body = "\n".join(lines).encode("utf-8")
    return hashlib.sha256(CLAUSE_DIGEST_DOMAIN + body).digest()


def merge3(
    base: Sequence[str],
    ours: Sequence[str],
    theirs: Sequence[str],
) -> Merge3Result:
    """Merge ``ours`` and ``theirs`` over their common ancestor ``base``.

    Args:
        base: the merge base — the common ancestor rendering.
        ours: the receiving site's current rendering.
        theirs: the fleet-standard rendering the lesson carries.

    Returns:
        A :class:`Merge3Result`. Clean means the edits did not collide; it does
        not mean the result may be applied.
    """
    match_ours = _match_map(base, ours)
    match_theirs = _match_map(base, theirs)

    merged: list[str] = []
    conflicts: list[ConflictRegion] = []
    i = j = k = 0

    while i < len(base) or j < len(ours) or k < len(theirs):
        run = _stable_run(base, ours, theirs, match_ours, match_theirs, i, j, k)
        if run:
            merged.extend(base[i : i + run])
            i, j, k = i + run, j + run, k + run
            continue

        next_i, next_j, next_k = _next_sync(base, ours, theirs, match_ours, match_theirs, i, j, k)
        base_chunk = tuple(base[i:next_i])
        ours_chunk = tuple(ours[j:next_j])
        theirs_chunk = tuple(theirs[k:next_k])

        if ours_chunk == base_chunk:
            # We did not touch it; take theirs.
            merged.extend(theirs_chunk)
        elif theirs_chunk in (base_chunk, ours_chunk):
            # They did not touch it, or both sides made the same edit; take ours.
            merged.extend(ours_chunk)
        else:
            conflicts.append(
                ConflictRegion(
                    base=base_chunk,
                    ours=ours_chunk,
                    theirs=theirs_chunk,
                    base_at=i,
                    ours_at=j,
                    theirs_at=k,
                )
            )
        i, j, k = next_i, next_j, next_k

    if conflicts:
        return Merge3Result(merged=None, conflicts=tuple(conflicts))
    return Merge3Result(merged=tuple(merged), conflicts=())


def _stable_run(
    base: Sequence[str],
    ours: Sequence[str],
    theirs: Sequence[str],
    match_ours: dict[int, int],
    match_theirs: dict[int, int],
    i: int,
    j: int,
    k: int,
) -> int:
    """Length of the run from ``(i, j, k)`` in which all three advance together."""
    run = 0
    while (
        i + run < len(base)
        and j + run < len(ours)
        and k + run < len(theirs)
        and match_ours.get(i + run) == j + run
        and match_theirs.get(i + run) == k + run
    ):
        run += 1
    return run


def _next_sync(
    base: Sequence[str],
    ours: Sequence[str],
    theirs: Sequence[str],
    match_ours: dict[int, int],
    match_theirs: dict[int, int],
    i: int,
    j: int,
    k: int,
) -> tuple[int, int, int]:
    """Find the next point at which all three inputs re-synchronise.

    Returns the ends of the three inputs when they never do, which makes the
    remainder one unstable chunk. Scanning forward from ``i`` and taking the
    **first** re-sync gives the smallest unstable chunk, which is what keeps a
    one-line disagreement from being reported as a whole-clause conflict.
    """
    for candidate in range(i + 1, len(base) + 1):
        if candidate == len(base):
            break
        target_j = match_ours.get(candidate)
        target_k = match_theirs.get(candidate)
        if target_j is not None and target_k is not None and target_j >= j and target_k >= k:
            return candidate, target_j, target_k
    return len(base), len(ours), len(theirs)


def _match_map(base: Sequence[str], side: Sequence[str]) -> dict[int, int]:
    """Map base index → side index for one longest common subsequence.

    A plain O(n·m) dynamic program. Clause renderings are tens of lines, so the
    quadratic cost is irrelevant and the exactness is not: a heuristic matcher
    that occasionally produced a different alignment would produce a different set
    of conflicts for the same three inputs, and the conflict set is what a person
    is asked to resolve.

    Ties are broken toward the **earlier** base line, consistently, so the same
    three inputs always yield the same alignment.
    """
    n, m = len(base), len(side)
    table = [[0] * (m + 1) for _ in range(n + 1)]
    for a in range(n - 1, -1, -1):
        row, nxt = table[a], table[a + 1]
        for b in range(m - 1, -1, -1):
            row[b] = nxt[b + 1] + 1 if base[a] == side[b] else max(nxt[b], row[b + 1])

    matches: dict[int, int] = {}
    a = b = 0
    while a < n and b < m:
        if base[a] == side[b]:
            matches[a] = b
            a += 1
            b += 1
        elif table[a + 1][b] >= table[a][b + 1]:
            a += 1
        else:
            b += 1
    return matches
