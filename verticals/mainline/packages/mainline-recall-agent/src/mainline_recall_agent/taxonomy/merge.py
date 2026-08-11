# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
"""Deterministic label clustering — TnT-LLM phase 2, in its non-model form.

Two callers, one algorithm:

* :class:`~mainline_recall_agent.taxonomy.offline_judge.RuleBasedInductionJudge` answers the
  ``merge`` phase with this, which is what lets the whole induction run with no AWS account;
* the induction loop uses it as the **fallback** when the live judge refuses or dead-letters
  on the merge call, so a model outage degrades the taxonomy's *quality* rather than
  producing no taxonomy at all.

The algorithm is single-link agglomeration under a token-set similarity, run inside each
``(level, activity_root, parent_label)`` bucket.  It is deliberately dull:

* similarity is Jaccard over content tokens with a small stop list, so it is symmetric,
  bounded and computable by hand from the labels in a version diff;
* the canonical wording is the highest-support member, ties broken by shortest-then-
  lexicographic — a total order, so the output does not depend on dict iteration;
* clusters whose total support is below ``min_support`` are absorbed into the most similar
  surviving cluster in the same bucket, or dropped when nothing is similar enough.  They
  are not silently kept: a level-3 node backed by one document is a K-means tree with one
  vector in it, which is worse than not existing because it draws an arm.

What it is not: semantic.  ``"venting trapped compressed air"`` and ``"bleeding down
hydraulic accumulators"`` are the same activity to a reader and share no content token, so
this will keep them apart and a model would not.  That gap is the argument for running the
live judge in production, and it is stated here rather than discovered later.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Final

from .models import LEVEL_FILE, LEVEL_SERIES
from .schemas import MergeGroup

__all__ = [
    "DEFAULT_MIN_SUPPORT",
    "DEFAULT_SIMILARITY",
    "LabelCandidate",
    "cluster_labels",
    "label_tokens",
    "similarity",
]

#: A label below this support is not a class, it is an observation.
DEFAULT_MIN_SUPPORT: Final[int] = 3

#: Jaccard floor for folding two labels together.  0.6 keeps "applying personal locks to
#: isolation points" with "applying personal locks at isolation points" and keeps
#: "planning rescue before entering" apart from "planning a lift over people".
DEFAULT_SIMILARITY: Final[float] = 0.6

_TOKEN_RE: Final[re.Pattern[str]] = re.compile(r"[a-z][a-z0-9'\-]*|[0-9]+")

#: Function words only.  Removing them stops "a", "the", "before" and "and" from carrying
#: similarity between labels that share nothing else.
_STOP: Final[frozenset[str]] = frozenset(
    {
        "a",
        "after",
        "an",
        "and",
        "at",
        "before",
        "between",
        "by",
        "during",
        "for",
        "from",
        "in",
        "inside",
        "into",
        "of",
        "on",
        "onto",
        "or",
        "over",
        "the",
        "through",
        "to",
        "under",
        "with",
        "within",
    }
)


@dataclass(frozen=True, slots=True)
class LabelCandidate:
    """One proposed label with the number of documents behind it."""

    level: int
    activity_root: str
    parent_label: str | None
    label: str
    support: int = 1

    @property
    def bucket(self) -> tuple[int, str, str]:
        return (self.level, self.activity_root, self.parent_label or "")


def label_tokens(label: str) -> frozenset[str]:
    """Content tokens of a label, stop words removed."""
    return frozenset(t for t in _TOKEN_RE.findall(label.lower()) if t not in _STOP)


def similarity(left: str, right: str) -> float:
    """Jaccard over content tokens.  1.0 for identical content, 0.0 for disjoint."""
    a = label_tokens(left)
    b = label_tokens(right)
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def _canonical(members: Mapping[str, int]) -> str:
    """Highest support wins; ties go to the shortest, then to the lexicographic first."""
    return min(members.items(), key=lambda kv: (-kv[1], len(kv[0]), kv[0]))[0]


def _agglomerate(labels: Sequence[tuple[str, int]], threshold: float) -> list[dict[str, int]]:
    """Single-link clustering over ``(label, support)`` pairs, in a fixed order."""
    ordered = sorted(labels, key=lambda kv: (-kv[1], len(kv[0]), kv[0]))
    clusters: list[dict[str, int]] = []
    for label, support in ordered:
        target: dict[str, int] | None = None
        best = threshold
        for cluster in clusters:
            score = max(similarity(label, member) for member in cluster)
            if score >= best:
                best = score
                target = cluster
        if target is None:
            clusters.append({label: support})
        else:
            target[label] = target.get(label, 0) + support
    return clusters


def _absorb_small(
    clusters: list[dict[str, int]], min_support: int, threshold: float
) -> list[dict[str, int]]:
    survivors = [c for c in clusters if sum(c.values()) >= min_support]
    small = [c for c in clusters if sum(c.values()) < min_support]
    if not survivors:
        return []
    for cluster in small:
        label = _canonical(cluster)
        scored = [
            (max(similarity(label, member) for member in survivor), index)
            for index, survivor in enumerate(survivors)
        ]
        score, index = max(scored, key=lambda pair: (pair[0], -pair[1]))
        if score <= 0.0:
            continue  # nothing to attach it to: the label is dropped, not kept as a stub
        for member, support in cluster.items():
            survivors[index][member] = survivors[index].get(member, 0) + support
    return survivors


def cluster_labels(
    candidates: Iterable[LabelCandidate],
    *,
    min_support: int = DEFAULT_MIN_SUPPORT,
    threshold: float = DEFAULT_SIMILARITY,
) -> list[MergeGroup]:
    """Fold near-duplicate labels together and return the surviving groups.

    Level 2 is clustered first and level 3 second, and every level-3 group's
    ``parent_label`` is rewritten to the canonical wording of its parent's group.  Doing it
    in the other order would leave files pointing at series labels that no longer exist,
    which is exactly the shape of orphan the snapshot builder refuses.
    """
    buckets: dict[tuple[int, str, str], dict[str, int]] = {}
    for candidate in candidates:
        pool = buckets.setdefault(candidate.bucket, {})
        pool[candidate.label] = pool.get(candidate.label, 0) + max(candidate.support, 0)

    series_groups: list[MergeGroup] = []
    series_canonical: dict[tuple[str, str], str] = {}
    for bucket in sorted(k for k in buckets if k[0] == LEVEL_SERIES):
        _, activity_root, _ = bucket
        clusters = _absorb_small(
            _agglomerate(list(buckets[bucket].items()), threshold), min_support, threshold
        )
        for cluster in clusters:
            canonical = _canonical(cluster)
            for member in cluster:
                series_canonical[(activity_root, member)] = canonical
            series_groups.append(
                MergeGroup(
                    level=LEVEL_SERIES,
                    activity_root=activity_root,
                    parent_label=None,
                    canonical_label=canonical,
                    members=sorted(cluster),
                    support=sum(cluster.values()),
                )
            )

    file_pools: dict[tuple[str, str], dict[str, int]] = {}
    for bucket, pool in buckets.items():
        if bucket[0] != LEVEL_FILE:
            continue
        _, activity_root, parent = bucket
        canonical_parent = series_canonical.get((activity_root, parent))
        if canonical_parent is None:
            # The parent series did not survive its own support floor. Its files go with
            # it: attaching them to an arbitrary surviving series would file incidents
            # under work they do not describe.
            continue
        target = file_pools.setdefault((activity_root, canonical_parent), {})
        for label, support in pool.items():
            target[label] = target.get(label, 0) + support

    file_groups: list[MergeGroup] = []
    for (activity_root, parent), pool in sorted(file_pools.items()):
        clusters = _absorb_small(
            _agglomerate(list(pool.items()), threshold), min_support, threshold
        )
        for cluster in clusters:
            file_groups.append(
                MergeGroup(
                    level=LEVEL_FILE,
                    activity_root=activity_root,
                    parent_label=parent,
                    canonical_label=_canonical(cluster),
                    members=sorted(cluster),
                    support=sum(cluster.values()),
                )
            )

    ordered = sorted(
        series_groups + file_groups,
        key=lambda g: (g.level, g.activity_root, g.parent_label or "", g.canonical_label),
    )
    return ordered
