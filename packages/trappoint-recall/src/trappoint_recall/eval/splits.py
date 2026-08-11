# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""Temporally-blocked splits, and the refusal to reach them with ``AS OF SYSTEM TIME``.

The money metric is Retro-Recall: for a severity-5 event at time *t*, synthesise the
permit that would have preceded it and ask whether the true precursor surfaces. That
question is only meaningful if **nothing the retriever can see post-dates t**. Three
predicates, all of them required (recall lead, D12):

    occurred_at   < t     -- the event had happened
    ingested_at   < t     -- and we had it
    corpus_commit <= t    -- under a corpus state that existed then

Random splits are refused outright. A random split over an incident corpus leaks the
future through vocabulary drift, equipment model names and investigator style, and it
is exactly how retrieval papers report numbers nobody can reproduce in service.

Why not ``AS OF SYSTEM TIME``
------------------------------
CockroachDB's default ``gc.ttlseconds`` is 4 hours. An AOST query aimed months back
either errors with a "batch timestamp must be after replica GC threshold" style
failure or, in a configuration where the horizon was extended just enough, silently
evaluates over a window nobody intended. Both outcomes are worse than a refusal, so
:func:`refuse_as_of_system_time` and :func:`assert_no_as_of_system_time` make the
mistake impossible to make quietly.

*Unverified on the target platform:* the exact SQLSTATE CockroachDB v26.2 returns for
an out-of-horizon AOST read has not been observed by this package, which is precisely
why the harness never issues one.
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Final, Literal

__all__ = [
    "GC_TTL_SECONDS_DEFAULT",
    "AsOfSystemTimeRefused",
    "RandomSplitRefused",
    "SplitPolicy",
    "SplitRecord",
    "TemporalSplit",
    "assert_no_as_of_system_time",
    "derive_split_policy_id",
    "refuse_as_of_system_time",
    "temporally_blocked_split",
]

GC_TTL_SECONDS_DEFAULT: Final = 4 * 60 * 60
"""CockroachDB Cloud default garbage-collection TTL, in seconds. Verified: 4 hours."""

SplitKind = Literal["temporally_blocked"]

_AOST_PATTERN: Final = re.compile(r"\bas\s+of\s+system\s+time\b", re.IGNORECASE)


class AsOfSystemTimeRefused(RuntimeError):
    """Raised when anything tries to reach evaluation history through AOST."""


class RandomSplitRefused(RuntimeError):
    """Raised when a random or stratified-random split is requested for a recall metric."""


def refuse_as_of_system_time(
    context: str, *, horizon_seconds: int = GC_TTL_SECONDS_DEFAULT
) -> None:
    """Always raises. There is no argument that makes AOST an acceptable time wall.

    Args:
        context: What was attempted, quoted back in the message so the refusal names
            the caller rather than the mechanism.
        horizon_seconds: The GC horizon being asserted against, for the message.

    Raises:
        AsOfSystemTimeRefused: unconditionally.
    """
    hours = horizon_seconds / 3600.0
    raise AsOfSystemTimeRefused(
        f"AS OF SYSTEM TIME refused for {context!r}: gc.ttlseconds is {horizon_seconds} "
        f"({hours:.1f}h), so an AOST read cannot reach a time wall months in the past. "
        "The evaluation time wall is enforced by the predicates "
        "occurred_at < t AND ingested_at < t AND corpus_commit <= t "
        "(recall lead decision D12). Use SplitPolicy.admits()."
    )


def assert_no_as_of_system_time(sql: str, *, context: str = "evaluation query") -> None:
    """Refuse a SQL string that contains ``AS OF SYSTEM TIME``.

    Provided so that any worker who later wires a live corpus into the harness gets a
    refusal at the point of writing the query rather than a plausible-looking number.
    """
    if _AOST_PATTERN.search(sql):
        refuse_as_of_system_time(context)


def refuse_random_split(context: str) -> None:
    """Always raises. Random splits leak the future into a diachronic metric.

    Raises:
        RandomSplitRefused: unconditionally.
    """
    raise RandomSplitRefused(
        f"random split refused for {context!r}: recall gates run on temporally-blocked "
        "splits, never random ones (BUILD_PLAN.md G4-beta). A random split over an "
        "incident corpus leaks the future through vocabulary and equipment drift."
    )


@dataclass(frozen=True, slots=True)
class SplitRecord:
    """The three timestamps a candidate must present to be admitted before the wall."""

    doc_id: str
    occurred_at: datetime
    ingested_at: datetime
    corpus_commit_at: datetime

    def __post_init__(self) -> None:
        for name in ("occurred_at", "ingested_at", "corpus_commit_at"):
            value: datetime = getattr(self, name)
            if value.tzinfo is None:
                raise ValueError(
                    f"{self.doc_id}: {name} must be timezone-aware; a naive timestamp in a "
                    "time-wall predicate is an undetectable off-by-one-timezone leak"
                )


def derive_split_policy_id(
    *, wall: datetime, corpus_commit: str, kind: SplitKind = "temporally_blocked"
) -> str:
    """Deterministic, human-legible id: ``TB-<wall date>-<8 hex of the digest>``.

    The digest covers the wall to the second, the corpus commit and the split kind, so
    two evaluations quoting the same ``split_policy_id`` really did run the same
    experiment.
    """
    payload = f"{kind}|{wall.astimezone(UTC).isoformat()}|{corpus_commit}"
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:8]
    prefix = {"temporally_blocked": "TB"}[kind]
    return f"{prefix}-{wall.astimezone(UTC).date().isoformat()}-{digest}"


@dataclass(frozen=True, slots=True)
class SplitPolicy:
    """A time wall plus the corpus state it was taken against.

    ``policy_id`` travels on every :class:`~trappoint_recall.eval.measurement.Measurement`
    this package produces, so a number can always be traced to the experiment.
    """

    wall: datetime
    corpus_commit: str
    kind: SplitKind = "temporally_blocked"
    note: str = ""

    def __post_init__(self) -> None:
        if self.wall.tzinfo is None:
            raise ValueError("SplitPolicy.wall must be timezone-aware")
        if not self.corpus_commit:
            raise ValueError(
                "SplitPolicy.corpus_commit is mandatory: a time wall without a corpus "
                "state cannot exclude a document that was re-ingested after the fact"
            )

    @property
    def policy_id(self) -> str:
        return derive_split_policy_id(
            wall=self.wall, corpus_commit=self.corpus_commit, kind=self.kind
        )

    def admits(self, record: SplitRecord) -> bool:
        """All three predicates, conjunctively. Any one of them alone is a leak."""
        return (
            record.occurred_at < self.wall
            and record.ingested_at < self.wall
            and record.corpus_commit_at <= self.wall
        )

    def rejection_reason(self, record: SplitRecord) -> str | None:
        """Which predicate excluded a record, for the audit trail. ``None`` if admitted."""
        if not record.occurred_at < self.wall:
            return "occurred_at >= wall"
        if not record.ingested_at < self.wall:
            return "ingested_at >= wall"
        if not record.corpus_commit_at <= self.wall:
            return "corpus_commit > wall"
        return None

    def to_dict(self) -> dict[str, object]:
        return {
            "policy_id": self.policy_id,
            "kind": self.kind,
            "wall": self.wall.astimezone(UTC).isoformat(),
            "corpus_commit": self.corpus_commit,
            "note": self.note,
            "predicates": [
                "occurred_at < wall",
                "ingested_at < wall",
                "corpus_commit <= wall",
            ],
            "as_of_system_time": "refused (gc.ttlseconds=4h)",
        }


@dataclass(frozen=True, slots=True)
class TemporalSplit:
    """The result of applying a policy: what the retriever may index, and what it may not."""

    policy: SplitPolicy
    indexable: tuple[str, ...]
    withheld: tuple[str, ...]
    rejections: tuple[tuple[str, str], ...]

    @property
    def policy_id(self) -> str:
        return self.policy.policy_id

    def to_dict(self) -> dict[str, object]:
        return {
            "policy": self.policy.to_dict(),
            "n_indexable": len(self.indexable),
            "n_withheld": len(self.withheld),
            "rejections": [{"doc_id": d, "reason": r} for d, r in self.rejections],
        }


def temporally_blocked_split(records: Iterable[SplitRecord], policy: SplitPolicy) -> TemporalSplit:
    """Partition ``records`` into indexable and withheld under ``policy``.

    Deterministic and order-preserving: the returned tuples follow input order so that
    an ablation over the same corpus produces byte-identical split manifests.
    """
    indexable: list[str] = []
    withheld: list[str] = []
    rejections: list[tuple[str, str]] = []
    seen: set[str] = set()
    for record in records:
        if record.doc_id in seen:
            raise ValueError(
                f"duplicate doc_id {record.doc_id!r} in split input: a document admitted "
                "twice under different timestamps makes the wall unenforceable"
            )
        seen.add(record.doc_id)
        reason = policy.rejection_reason(record)
        if reason is None:
            indexable.append(record.doc_id)
        else:
            withheld.append(record.doc_id)
            rejections.append((record.doc_id, reason))
    return TemporalSplit(
        policy=policy,
        indexable=tuple(indexable),
        withheld=tuple(withheld),
        rejections=tuple(rejections),
    )


def walls_from_events(occurrences: Sequence[datetime]) -> tuple[datetime, ...]:
    """Every distinct occurrence instant, ascending — the candidate wall positions.

    Retro-Recall places one wall immediately before each severity-5 event, which is why
    the harness needs the sorted set of occurrence instants rather than a single date.
    """
    return tuple(sorted({o.astimezone(UTC) for o in occurrences}))
