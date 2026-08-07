# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""G2 — structured-code co-membership, and the flag that keeps it out of the headline.

Two records sharing an accident classification, an injury source and an equipment code
are a **weak positive**: plausibly about the same kind of thing, and certainly not
established as the precursor a supervisor needed to see. G2 is large, free and
automatable — perfect for training the isotonic calibrator, and disqualifying as a
published precision number, because a precision computed over G2 measures how well the
retriever reproduces the regulator's coding manual.

So every G2 judgement is grade **1** ("related: same equipment or site, different
recurrence condition"), which is *below* the binary relevance floor of 2. Under the
harness's own arithmetic a G2 pair is not relevant, and a system that returned nothing
but G2 pairs would score zero. That is the correct behaviour and it is not enough on its
own — a future caller could pass ``floor=1`` — so the file also carries
``calibrator_only: true`` on its ``//!meta`` line and
:func:`~trappoint_recall.corpora.emit.refuse_headline_use` raises on the gold set id.
Three independent barriers, because the failure mode is silent.

Why the pair count is capped
-----------------------------
Co-membership is quadratic in cluster size: one popular ``(classification, injury source,
equipment)`` triple over a 20 000-record corpus would produce tens of millions of pairs
and drown every other gold set. :func:`build_g2_pairs` caps pairs per query
deterministically — nearest in time first, because temporal proximity is the one tie-break
that does not smuggle a similarity model into a structured-code rule.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Final

from trappoint_recall.corpora.model import EventRecord, EventRecordSet
from trappoint_recall.eval.qrels import Judgement

__all__ = [
    "G2_GOLD_SET",
    "G2_GRADE",
    "G2Report",
    "build_g2_judgements",
    "build_g2_pairs",
    "g2_query_id",
]

G2_GOLD_SET: Final = "G2"

G2_GRADE: Final = 1
"""Below :data:`~trappoint_recall.eval.qrels.BLOCKING_RELEVANCE_FLOOR`, on purpose.

A weak positive that graded 2 would be counted as relevant by every binary metric in the
harness, and the calibrator-only flag would then be the *only* thing standing between a
coding-manual artefact and a published precision figure."""


@dataclass(frozen=True, slots=True)
class G2Report:
    """What co-membership produced, and what it refused to produce."""

    n_records: int
    n_keys: int
    n_pairs: int
    n_capped_away: int
    max_pairs_per_query: int
    largest_cluster: int

    def to_dict(self) -> dict[str, object]:
        return {
            "n_records": self.n_records,
            "n_keys": self.n_keys,
            "n_pairs": self.n_pairs,
            "n_capped_away": self.n_capped_away,
            "max_pairs_per_query": self.max_pairs_per_query,
            "largest_cluster": self.largest_cluster,
        }


def g2_query_id(ref: str) -> str:
    """``Q-G2-<ref>``. Distinct from G1's namespace so the two never collide in a merge."""
    return f"Q-G2-{ref}"


def build_g2_pairs(
    records: EventRecordSet,
    *,
    max_pairs_per_query: int = 4,
    require_prior: bool = True,
) -> tuple[tuple[tuple[str, str], ...], G2Report]:
    """Co-membership pairs, capped and deterministic.

    Args:
        records: The corpus. Only :class:`~trappoint_recall.corpora.model.CodedFields` is
            read — never the narrative. A rule that reached into the prose would stop
            being a structured-code rule and become an undeclared retrieval model whose
            errors would be correlated with the retriever's own.
        max_pairs_per_query: Cap per query record, applied after sorting candidates by
            time distance then by identifier.
        require_prior: Keep only pairs whose document pre-dates the query, so G2 can be
            used alongside a time wall without becoming the thing that leaks.

    Returns:
        ``(pairs, report)`` where ``pairs`` is ``((query_ref, doc_ref), ...)`` sorted.
    """
    clusters: dict[tuple[str, str, str], list[EventRecord]] = {}
    for record in records:
        clusters.setdefault(record.coded.comembership_key, []).append(record)

    pairs: list[tuple[str, str]] = []
    capped_away = 0
    largest = 0
    for members in clusters.values():
        largest = max(largest, len(members))
        if len(members) < 2:
            continue
        ordered = sorted(members, key=lambda r: (r.occurred_at, r.external_ref))
        for query in ordered:
            candidates = [
                other
                for other in ordered
                if other.external_ref != query.external_ref
                and (not require_prior or other.occurred_at < query.occurred_at)
            ]
            candidates.sort(
                key=lambda other: (
                    abs((query.occurred_at - other.occurred_at).total_seconds()),
                    other.external_ref,
                )
            )
            kept = candidates[:max_pairs_per_query]
            capped_away += len(candidates) - len(kept)
            pairs.extend((query.external_ref, other.external_ref) for other in kept)

    pairs.sort()
    report = G2Report(
        n_records=len(records),
        n_keys=len(clusters),
        n_pairs=len(pairs),
        n_capped_away=capped_away,
        max_pairs_per_query=max_pairs_per_query,
        largest_cluster=largest,
    )
    return tuple(pairs), report


def build_g2_judgements(
    pairs: Sequence[tuple[str, str]], records: EventRecordSet
) -> tuple[Judgement, ...]:
    """Grade-1 weak positives, tagged ``distant_supervision`` and never blinded.

    Not blinded means ``P@block`` skips them outright — a fourth barrier on top of the
    grade, the flag and :func:`~trappoint_recall.corpora.emit.refuse_headline_use`.
    """
    out: list[Judgement] = []
    for query_ref, doc_ref in pairs:
        query = records.get(query_ref)
        doc = records.get(doc_ref)
        if query is None or doc is None:
            raise ValueError(
                f"G2 pair ({query_ref}, {doc_ref}) references a record not in the corpus; "
                "a judgement about a document nobody holds cannot be scored"
            )
        key = query.coded.comembership_key
        out.append(
            Judgement(
                query_id=g2_query_id(query_ref),
                doc_id=doc_ref,
                grade=G2_GRADE,
                gold_set=G2_GOLD_SET,
                judged_by="distant_supervision",
                blinded=False,
                # The co-membership key, and nothing else. G2 is the largest gold set by
                # an order of magnitude, so a sentence of prose per judgement would make
                # the committed fixture bigger than every other artefact combined; the
                # rationale that would have been repeated 7 000 times lives once, on the
                # file's //!meta line.
                notes=f"co-membership {key[0]}|{key[1]}|{key[2]}",
            )
        )
    return tuple(out)


def comembership_summary(records: EventRecordSet) -> Mapping[str, int]:
    """Cluster-size histogram, for the build report.

    Published because a G2 dominated by one enormous cluster is a different calibration
    set from one spread evenly, and the calibrator inherits the shape either way.
    """
    sizes: dict[tuple[str, str, str], int] = {}
    for record in records:
        key = record.coded.comembership_key
        sizes[key] = sizes.get(key, 0) + 1
    histogram: dict[str, int] = {}
    for size in sizes.values():
        bucket = "1" if size == 1 else "2-4" if size <= 4 else "5-16" if size <= 16 else "17+"
        histogram[bucket] = histogram.get(bucket, 0) + 1
    return dict(sorted(histogram.items()))
