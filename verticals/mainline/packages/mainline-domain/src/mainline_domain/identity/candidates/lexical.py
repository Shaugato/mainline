# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""S3 — the lexical near-duplicate stage: band, then rescore.

The stage is two halves that must not be confused with one another.

**Generation** is banding (:mod:`.band`).  Sixteen primary-key point lookups.
It is the reason the cascade's cost does not grow with the corpus, and it is
*lossy by design*: a pair whose true Jaccard is 0.5 shares a band about 0.6 %
of the time, and that miss is not a bug.  It is the S-curve.  It is also why
the whole design refuses to depend on the matcher succeeding — a missed pair
becomes an unmatched blood-written ancestor, which is a blocking residue row,
which is a louder gate than the match would have been.

**Adjudication** is rescoring (:mod:`.rescore`), on full text, in the
application, with one score of record.

The distinction shows up in the return value.  This stage never enumerates the
pairs banding did not produce — enumerating them would mean touching every
clause in the corpus, which is exactly the cost banding exists to avoid.  What
it *does* do is take an explicit ``required_ancestors`` set (in production, the
ancestors that carry blame edges, which W8 already has to know) and emit a
``band_miss`` drop for each one banding failed to surface.  Recall failure is
therefore recorded **per ancestor, by name**, at the moment it happens, instead
of being inferred later from an absence.  That is the CBM asymmetry in
miniature: the matcher missing is not silence, it is a row.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Final

from mainline_domain.contracts import Candidate

from .band import InMemoryBandIndex
from .minhash import MinHashParams, default_params, signature
from .records import ClauseRecord, ClauseRef, DroppedCandidate, StageResult, order_candidates
from .rescore import RESCORE_VERSION, Rescore, rescore
from .thresholds import DEFAULT_BANDS, StageBands

__all__ = ["LOCAL_SITE_ID", "LexicalCorpus", "lexical_stage", "lexical_stage_from_hits"]

LOCAL_SITE_ID: Final[uuid.UUID] = uuid.uuid5(uuid.NAMESPACE_URL, "mainline/local-lexical-corpus")
"""The ``site_id`` an in-memory corpus uses when the caller supplies none.

Fixed and derived, never random: a :class:`LexicalCorpus` can emit rows that
are insertable into ``mainline.clause_band`` verbatim, and rows whose site
changes between processes would be rows nobody could join.
"""


@dataclass(frozen=True, slots=True)
class _Indexed:
    record: ClauseRecord
    signature: tuple[int, ...]


class LexicalCorpus:
    """A signed, banded corpus: the in-process equivalent of ``mainline.clause_band``.

    Built once per document (or per site slice), probed once per query clause.
    Signatures are computed at insert and kept, so a query never re-signs a
    corpus member — which is what makes rescoring the only per-pair cost and
    banding the only per-corpus cost.
    """

    __slots__ = ("_by_ref", "_index", "_params")

    def __init__(
        self,
        site_id: uuid.UUID | None = None,
        params: MinHashParams | None = None,
    ) -> None:
        """Build an empty corpus for one site, using the committed permutation table."""
        self._params = params if params is not None else default_params()
        self._index = InMemoryBandIndex(
            site_id if site_id is not None else LOCAL_SITE_ID, self._params
        )
        self._by_ref: dict[ClauseRef, _Indexed] = {}

    @property
    def params(self) -> MinHashParams:
        """The permutation table every signature in this corpus was built with."""
        return self._params

    @property
    def size(self) -> int:
        """How many clause versions are indexed."""
        return len(self._by_ref)

    @property
    def bucket_count(self) -> int:
        """Populated ``(band_no, band_hash)`` buckets — the index's own width."""
        return self._index.bucket_count

    def add(self, record: ClauseRecord) -> tuple[int, ...]:
        """Sign and band one clause version; returns its signature."""
        sig = signature(record.canon_text, self._params)
        self._by_ref[record.ref] = _Indexed(record, sig)
        self._index.add(record.ref, sig)
        return sig

    def extend(self, records: Iterable[ClauseRecord]) -> None:
        """Sign and band every record in ``records``."""
        for record in records:
            self.add(record)

    def signature_of(self, ref: ClauseRef) -> tuple[int, ...]:
        """Return the stored signature of an indexed clause version."""
        return self._by_ref[ref].signature

    def record_of(self, ref: ClauseRef) -> ClauseRecord:
        """Return the indexed record behind a reference."""
        return self._by_ref[ref].record

    def probe(self, query_signature: tuple[int, ...]) -> Mapping[ClauseRef, int]:
        """Refs sharing at least one band, mapped to how many bands they share."""
        return self._index.probe(query_signature)


def lexical_stage_from_hits(
    *,
    query_text: str,
    query_signature: tuple[int, ...],
    hits: Mapping[ClauseRef, int],
    text_of: Mapping[ClauseRef, str],
    signature_of: Mapping[ClauseRef, tuple[int, ...]] | None = None,
    required_ancestors: frozenset[ClauseRef] = frozenset(),
    exclude: frozenset[ClauseRef] = frozenset(),
    bands: StageBands = DEFAULT_BANDS,
    params: MinHashParams | None = None,
) -> StageResult:
    """Rescore band survivors that somebody else fetched.

    This is the shape the SQL path uses: run :func:`~.band.band_probe_sql`, hand
    the resulting ``ref -> band_hits`` mapping here together with the survivors'
    ``canon_text``, and get candidates back.  Keeping fetch and score apart is
    what lets identical scoring code run over a live cluster and over an
    in-memory fixture, so the two cannot silently diverge.
    """
    kept: list[Candidate] = []
    dropped: list[DroppedCandidate] = []

    for ref in sorted(
        required_ancestors - set(hits), key=lambda r: (r.clause_uuid.bytes, r.commit_id)
    ):
        dropped.append(
            DroppedCandidate(
                ancestor_clause_uuid=ref.clause_uuid,
                ancestor_commit=ref.commit_id,
                stage="S3",
                reason="band_miss",
                detail={"band_hits": 0.0},
                note=(
                    "an ancestor the caller declared it must account for shared no LSH band "
                    "with the query; S3 cannot see it, and W8 must resolve it at S4 or "
                    "record it as residue"
                ),
            )
        )

    for ref, band_hits in hits.items():
        if ref in exclude:
            dropped.append(
                DroppedCandidate(
                    ancestor_clause_uuid=ref.clause_uuid,
                    ancestor_commit=ref.commit_id,
                    stage="S3",
                    reason="self_pair",
                    detail={"band_hits": float(band_hits)},
                    note="a clause version is not its own ancestor",
                )
            )
            continue
        scored: Rescore = rescore(
            query_text,
            text_of[ref],
            query_signature=query_signature,
            candidate_signature=None if signature_of is None else signature_of.get(ref),
            band_hits=band_hits,
            params=params,
        )
        if scored.score < bands.lexical_reject:
            dropped.append(
                DroppedCandidate(
                    ancestor_clause_uuid=ref.clause_uuid,
                    ancestor_commit=ref.commit_id,
                    stage="S3",
                    reason="auto_reject",
                    detail=scored.features(),
                    note=(
                        f"{RESCORE_VERSION}: score {scored.score:.4f} is below the auto-reject "
                        f"band {bands.lexical_reject}; banding produced the pair, the text "
                        f"did not support it"
                    ),
                )
            )
            continue
        kept.append(
            Candidate(
                ancestor_clause_uuid=ref.clause_uuid,
                ancestor_commit=ref.commit_id,
                stage="S3",
                score=scored.score,
                features=scored.features(),
            )
        )
    return StageResult(stage="S3", candidates=order_candidates(kept), dropped=tuple(dropped))


def lexical_stage(
    *,
    query_text: str,
    corpus: LexicalCorpus,
    query_signature: tuple[int, ...] | None = None,
    required_ancestors: frozenset[ClauseRef] = frozenset(),
    exclude: frozenset[ClauseRef] = frozenset(),
    bands: StageBands = DEFAULT_BANDS,
) -> StageResult:
    """Band and rescore against an in-memory :class:`LexicalCorpus`."""
    sig = query_signature if query_signature is not None else signature(query_text, corpus.params)
    hits = corpus.probe(sig)
    return lexical_stage_from_hits(
        query_text=query_text,
        query_signature=sig,
        hits=hits,
        text_of={ref: corpus.record_of(ref).canon_text for ref in hits},
        signature_of={ref: corpus.signature_of(ref) for ref in hits},
        required_ancestors=required_ancestors,
        exclude=exclude,
        bands=bands,
        params=corpus.params,
    )
