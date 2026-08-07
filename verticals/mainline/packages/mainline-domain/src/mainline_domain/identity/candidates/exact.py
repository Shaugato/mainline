# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""S1 — ``canon_sha256`` equality.  The cheapest stage, and the only certain one.

There is no threshold here and no band below the accept line.  Two clause
versions whose canonical digests are equal have byte-identical ``canon_text``;
the score is ``1.0`` and it is not an estimate.  Everything the cascade does
after this point exists because this stage misses whenever a single character
moved.

**What S1 quietly buys.**  ``canon_sha256`` is computed over ``canon_text``,
which the canonicaliser has already stripped of numbering prefixes, page
furniture, OCR confusables inside numeric tokens and line-wrap hyphenation.  So
"renumbered from 7.3.2(b) to 8.1.4(a), re-typeset, re-scanned" is an S1 *hit* —
the retypeset-renumber-OCR triple collapses to one digest by construction.
That is the point of CANONHOLD being a versioned migration rather than a config
flag: the digest an S1 match is asserted on is the digest blame edges were
attached to.

**The SQL path uses the index the DDL already declares.**
``mainline.clause_version`` carries ``INDEX by_digest (site_id, canon_sha256)``,
so :data:`EXACT_SQL` is a two-column index lookup.  No new index, no new
migration; this stage costs the schema nothing.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Final

from mainline_domain.contracts import Candidate

from .records import ClauseRecord, ClauseRef, DroppedCandidate, StageResult, order_candidates
from .thresholds import DEFAULT_BANDS, StageBands

__all__ = ["EXACT_SQL", "exact_stage", "exact_stage_from_refs"]

EXACT_SQL: Final[str] = """
SELECT clause_uuid, commit_id
  FROM mainline.clause_version
 WHERE site_id = %(site_id)s
   AND canon_sha256 = %(canon_sha256)s
 ORDER BY clause_uuid, commit_id
""".strip()
"""Served by ``INDEX by_digest (site_id, canon_sha256)`` — see ARCHITECTURE.md §5.3.

Ordered so that two runs against the same data return the same sequence.  An
unordered candidate list makes an assignment result depend on scan order, and a
result that depends on scan order is a result nobody can reproduce under oath.
"""


def _candidate(ref: ClauseRef) -> Candidate:
    return Candidate(
        ancestor_clause_uuid=ref.clause_uuid,
        ancestor_commit=ref.commit_id,
        stage="S1",
        score=1.0,
        features={"canon_sha256_equal": 1.0},
    )


def exact_stage_from_refs(
    hits: Iterable[ClauseRef],
    *,
    exclude: frozenset[ClauseRef] = frozenset(),
) -> StageResult:
    """Wrap rows already fetched by :data:`EXACT_SQL` as S1 candidates.

    ``exclude`` is normally the query's own ``(clause_uuid, commit_id)``: a
    clause version is trivially digest-equal to itself and admitting that as a
    candidate would make every clause its own ancestor.
    """
    kept: list[Candidate] = []
    dropped: list[DroppedCandidate] = []
    for ref in hits:
        if ref in exclude:
            dropped.append(
                DroppedCandidate(
                    ancestor_clause_uuid=ref.clause_uuid,
                    ancestor_commit=ref.commit_id,
                    stage="S1",
                    reason="self_pair",
                    detail={"canon_sha256_equal": 1.0},
                    note="a clause version is not its own ancestor",
                )
            )
            continue
        kept.append(_candidate(ref))
    return StageResult(stage="S1", candidates=order_candidates(kept), dropped=tuple(dropped))


def exact_stage(
    query_sha256: bytes,
    corpus: Iterable[ClauseRecord],
    *,
    exclude: frozenset[ClauseRef] = frozenset(),
    bands: StageBands = DEFAULT_BANDS,
) -> StageResult:
    """Run the in-memory equivalent of :data:`EXACT_SQL`, for tests and local runs.

    ``bands`` is accepted so that every stage in this package has the same
    signature shape and W8's orchestrator can call them uniformly.  The only
    thing S1 does with it is **refuse a tuned one**: this stage's accept band is
    definitional, and a policy file that lowered it would be asking for a
    digest match at less than digest equality, which is not a thing.
    """
    if bands.exact_accept != 1.0:
        raise ValueError(
            f"S1's accept band is definitional (canon_sha256 equality) and cannot be tuned; "
            f"the supplied policy says {bands.exact_accept}"
        )
    return exact_stage_from_refs(
        (record.ref for record in corpus if record.canon_sha256 == query_sha256),
        exclude=exclude,
    )
