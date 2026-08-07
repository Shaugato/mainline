# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""S2 — identity-anchor-set equality, floored by trigram similarity.

The stage in one sentence: *if two clause versions name exactly the same
equipment tags, isolation points, CAS numbers, citations and instrument loops,
and their prose is still recognisably the same prose, they are the same clause.*

Both halves are load-bearing and neither is sufficient.

**Anchor equality alone is not enough.**  "Isolate P-101A at ISOL-4471" and
"P-101A at ISOL-4471 may be worked live" carry identical identity anchor sets
and are opposite instructions.  The trigram floor is what stops anchor equality
from becoming a licence to match anything that mentions the same equipment.

**Trigram similarity alone is not enough** either — that is S3's job, and S3
carries a lower accept band precisely because it has no anchor evidence.

**Three deliberate refusals**, each recorded rather than silent:

* ``no_identity_anchors`` — neither side names anything.  Anchor-set equality
  between two empty sets is vacuously true and would auto-accept at 0.92 any
  pair of anchor-free clauses whose prose happened to be similar.  Vacuous
  evidence is refused, and the pair falls through to S3/S4 where similarity has
  to stand on its own.
* ``anchor_set_differs`` — both sides name things and the sets are not *equal*.
  Note the asymmetry with :meth:`AnchorSet.compatible_with`: a descendant that
  adds ``P-101B`` beside ``P-101A`` is still *compatible* (it is an extension,
  not a swap) but it is not *equal*, so it does not get S2's high auto-accept.
  It falls through, which is the conservative direction.
* ``trigram_floor`` — anchors agreed, prose did not.  Refused here, not
  down-weighted, because at this stage the anchors would otherwise be carrying
  the entire match.

**The score of record is the trigram similarity itself.**  No affine remapping
of "0.55 floor onto a 0.92 accept band" — that would be an invented calibration
dressed up as arithmetic.  The stage's contract is exactly: *anchor sets equal
and non-empty*, gate; *trigram similarity*, score.  Which means S2's ≥ 0.92
auto-accept reads, in plain words, as "the identity anchors are identical and
the prose is 92 % trigram-identical", and that sentence is checkable.

**Two thresholds, one quantity, two different jobs.**  0.55 is where S2 stops
having an opinion; 0.92 is where its opinion is strong enough to auto-accept.
Between them the pair is emitted as a *scored candidate* and falls through to
S3 and S4, which score it on evidence S2 does not have.  That is deliberately
the conservative reading of the S0-S6 table: the alternative — blending anchor
agreement into the score so that anchor-equal pairs clear 0.92 on weaker prose
— would auto-accept "same three tags, 56 % similar prose", and for a matcher
whose mistakes attach a fatality's obligation to the wrong clause, falling
through to more evidence is the right direction to be wrong in.  A worked
example: a two-word paraphrase of a real clause scores about 0.81 here (not
auto-accepted) and about 0.93 at S3 on indel similarity (auto-accepted).  The
cascade resolves it; S2 declines to.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Final

from mainline_domain.contracts import AnchorSet, Candidate

from . import trigram
from .records import ClauseRecord, ClauseRef, DroppedCandidate, StageResult, order_candidates
from .thresholds import DEFAULT_BANDS, StageBands

__all__ = ["ANCHOR_STAGE_SQL", "anchor_stage", "identity_anchor_array"]

ANCHOR_STAGE_SQL: Final[str] = """
SELECT clause_uuid, commit_id, similarity(canon_text, %(canon_text)s) AS trgm
  FROM mainline.clause_version
 WHERE site_id = %(site_id)s
   AND anchor_set @> %(identity_anchors)s
   AND anchor_set <@ %(identity_anchors)s
   AND canon_text %% %(canon_text)s
 ORDER BY trgm DESC, clause_uuid, commit_id
 LIMIT %(limit)s
""".strip()
r"""Set equality via containment both ways, plus the ``%`` trigram filter.

Three platform facts are baked into this statement and none of them is
negotiable (risk R-A6, ``clause-identity.md`` §7):

* ``anchor_set`` carries ``INVERTED INDEX cv_anchors``, and ``@>`` is the
  operator that index serves.  ``a @> b AND a <@ b`` is set equality expressed
  in operators the index understands.
* the filter is ``%``, the trigram *containment* operator, which CockroachDB
  supports.  ``word_similarity()``, ``strict_word_similarity()`` and the whole
  ``<->`` trigram distance-operator family are **unsupported**.
* the ordering is by ``similarity()`` **descending** — an ordinary expression
  sort over a supported function, not a distance-operator sort.  No query in
  this domain orders by a trigram distance operator.

``%%`` in the literal is a doubled percent for the DB-API parameter style, not
a modulo.  ``identity_anchors`` binds a ``STRING[]``; the caller builds it with
:func:`identity_anchor_array` so the array's ordering and duplicate handling are
decided in one place.

**Unverified**: this statement has not been run against a CockroachDB cluster
at the time of writing (no cluster is reachable from the build machine).  What
is proven is the in-memory :func:`anchor_stage`, and
``tests/integration/algorithms/candidates/`` asserts the two agree the moment a
cluster exists.
"""


def identity_anchor_array(anchors: AnchorSet) -> list[str]:
    """Build the ``STRING[]`` binding for :data:`ANCHOR_STAGE_SQL`.

    Sorted and de-duplicated, because ``@>``/``<@`` treat an array as a set but
    a *test* comparing two bindings does not, and a parameter whose byte form
    depends on iteration order over a ``frozenset`` is a parameter that changes
    between runs.
    """
    return sorted(anchors.identity_norms())


def anchor_stage(
    *,
    query_anchors: AnchorSet,
    query_text: str,
    corpus: Iterable[ClauseRecord],
    exclude: frozenset[ClauseRef] = frozenset(),
    bands: StageBands = DEFAULT_BANDS,
) -> StageResult:
    """Run S2 over an in-memory corpus.

    Returns every pair that passed the gate and the floor, ordered by score;
    the caller decides what to do with the ones below ``bands.anchor_accept``
    (they are candidates, not accepted matches).  Every refusal is in
    ``dropped`` with the arithmetic that produced it.
    """
    query_norms = query_anchors.identity_norms()
    kept: list[Candidate] = []
    dropped: list[DroppedCandidate] = []

    for record in corpus:
        if record.ref in exclude:
            continue
        record_norms = record.anchors.identity_norms()
        detail = {
            "query_identity_anchor_count": float(len(query_norms)),
            "candidate_identity_anchor_count": float(len(record_norms)),
        }
        if not query_norms or not record_norms:
            dropped.append(
                DroppedCandidate(
                    ancestor_clause_uuid=record.ref.clause_uuid,
                    ancestor_commit=record.ref.commit_id,
                    stage="S2",
                    reason="no_identity_anchors",
                    detail=detail,
                    note=(
                        "anchor-set equality between empty sets is vacuous; the pair falls "
                        "through to S3/S4 rather than being auto-accepted on no evidence"
                    ),
                )
            )
            continue
        if query_norms != record_norms:
            dropped.append(
                DroppedCandidate(
                    ancestor_clause_uuid=record.ref.clause_uuid,
                    ancestor_commit=record.ref.commit_id,
                    stage="S2",
                    reason="anchor_set_differs",
                    detail={
                        **detail,
                        "shared_identity_anchors": float(len(query_norms & record_norms)),
                        "compatible": float(query_anchors.compatible_with(record.anchors)),
                    },
                    note=(
                        "equality, not compatibility: an added anchor is compatible but is "
                        "not evidence of identity at S2's accept band"
                    ),
                )
            )
            continue

        score = trigram.similarity(query_text, record.canon_text)
        detail["trigram_similarity"] = score
        if score < bands.anchor_trigram_floor:
            dropped.append(
                DroppedCandidate(
                    ancestor_clause_uuid=record.ref.clause_uuid,
                    ancestor_commit=record.ref.commit_id,
                    stage="S2",
                    reason="trigram_floor",
                    detail=detail,
                    note=(
                        f"identity anchors agreed but trigram similarity {score:.4f} is below "
                        f"the floor {bands.anchor_trigram_floor}; the anchors would be "
                        f"carrying the whole match"
                    ),
                )
            )
            continue

        kept.append(
            Candidate(
                ancestor_clause_uuid=record.ref.clause_uuid,
                ancestor_commit=record.ref.commit_id,
                stage="S2",
                score=score,
                features={**detail, "anchor_set_equal": 1.0},
            )
        )

    return StageResult(stage="S2", candidates=order_candidates(kept), dropped=tuple(dropped))
