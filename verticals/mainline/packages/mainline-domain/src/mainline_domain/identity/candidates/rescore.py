# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""Rescoring band survivors — in the **application**, and with one score of record.

Banding says *which pairs to look at*.  It says nothing about how alike they
are: the estimator behind it has a standard error of about 0.088 at 128
permutations, and a number with that much noise must never decide whether an
obligation carries.  So every survivor is rescored on the full text.

**In the application, not in SQL** (risk R-A6).  CockroachDB's ``levenshtein()``
caps its input at 255 characters ([cockroach#56820]) and most clauses are
longer; the bound on the truncated behaviour is unpublished.  A score computed
by a function that silently changes meaning above a length threshold is a score
that will be wrong exactly on the long, dense clauses that carry the controls.
``rapidfuzz`` runs here, on the whole string, with no cap.

**One score of record, several recorded features.**  The score is
``Indel.normalized_similarity`` over the **token** sequences — that is,
``2·LCS(tokens) / (|a| + |b|)``.  Three reasons, and the third is the one that
was measured rather than reasoned:

* it is derived from a metric (indel distance), so it is symmetric and obeys
  the triangle inequality before normalisation;
* it is normalised by ``|a| + |b|``, so it is bounded in ``[0, 1]`` and cannot
  be gamed by padding one side;
* **it uses the whole of its range on this data.**  The character-level variant
  does not.  Two unrelated English sentences of similar length score about 0.40
  on characters, because English shares its alphabet with itself — so a 0.30
  auto-reject band over character indel would never fire, and S3 would refuse
  nothing.  On tokens the same pairs score 0.07 and 0.15, and a genuine
  two-word paraphrase scores 0.92.  The bands in ``clause-identity.md`` §4
  (accept ≥ 0.90, reject < 0.30) are only *meaningful* against a token-level
  quantity, which is also what "rescored by … token-level Myers/histogram diff"
  says.

The character-level indel and Levenshtein similarities, the trigram similarity,
the patience token agreement, the MinHash estimate and the true Jaccard are all
computed and all **kept as features** — but none of them is blended into the
score.  A weighted blend of correlated similarities needs weights, and this
package has no corpus with which to calibrate weights.  Inventing them and
writing them down as if they were measured is exactly the move
``novelty/minhash-band.yaml`` exists to prevent; the open calibration question
is recorded there under ``unverified``.

**Why the patience diff is computed even though it does not score.**  It
produces the *witness*: which blocks moved, which were deleted, which were
inserted, in text an adjudicator can read before signing.  ``matched_tokens``
from the patience anchoring is always ≤ the LCS behind the score, and the gap
between them is a reordering signature rather than a disagreement.

[cockroach#56820]: https://github.com/cockroachdb/cockroach/issues/56820
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from rapidfuzz.distance import Indel, Levenshtein

from . import trigram
from .minhash import (
    MinHashParams,
    default_params,
    exact_jaccard,
    jaccard_estimate,
    signature,
)
from .patience_diff import matched_token_count, moved_blocks, patience_diff, tokenise

__all__ = ["RESCORE_VERSION", "Rescore", "rescore"]

RESCORE_VERSION: Final[str] = "rescore-v1"
"""Stamped onto every feature map so a re-scored corpus is distinguishable from a stale one."""


@dataclass(frozen=True, slots=True)
class Rescore:
    """Every number the S3 stage computed for one pair.

    ``score`` is the one that decides; the rest are what an adjudicator reads
    when they want to know *why* two clauses that look alike scored 0.41.
    """

    score: float
    token_indel_similarity: float
    char_indel_similarity: float
    char_levenshtein_similarity: float
    trigram_similarity: float
    patience_similarity: float
    minhash_jaccard: float
    true_jaccard: float
    band_hits: int
    moved_token_count: int
    matched_tokens: int

    def features(self) -> dict[str, float]:
        """Build the feature map carried on the emitted candidate.

        Flat ``str -> float`` because that is what
        :class:`~mainline_domain.contracts.Candidate` declares and what
        ``identity_residue.features`` (JSONB) stores.  Integers are widened to
        float here rather than at the call site so the map has one type.
        """
        return {
            "token_indel_similarity": self.token_indel_similarity,
            "char_indel_similarity": self.char_indel_similarity,
            "char_levenshtein_similarity": self.char_levenshtein_similarity,
            "trigram_similarity": self.trigram_similarity,
            "patience_similarity": self.patience_similarity,
            "minhash_jaccard": self.minhash_jaccard,
            "true_jaccard": self.true_jaccard,
            "band_hits": float(self.band_hits),
            "moved_token_count": float(self.moved_token_count),
            "matched_tokens": float(self.matched_tokens),
        }


def rescore(
    query_text: str,
    candidate_text: str,
    *,
    query_signature: tuple[int, ...] | None = None,
    candidate_signature: tuple[int, ...] | None = None,
    band_hits: int = 0,
    params: MinHashParams | None = None,
) -> Rescore:
    """Score one band survivor on its full text.

    ``query_signature``/``candidate_signature`` are optional: when the caller
    already has them (it does, on the hot path — banding just used them) the
    MinHash estimate is free, and when it does not, the estimate is reported as
    the true Jaccard's own value would not be, i.e. it is computed rather than
    faked.  ``band_hits`` is passed through as a feature because "shared 14 of
    16 bands" and "shared 1 of 16" are very different provenance for the same
    final score.
    """
    p = params if params is not None else default_params()

    a_tokens = tokenise(query_text)
    b_tokens = tokenise(candidate_text)
    ops = patience_diff(a_tokens, b_tokens)
    matched = matched_token_count(ops)
    token_total = len(a_tokens) + len(b_tokens)

    left_sig = query_signature if query_signature is not None else signature(query_text, p)
    right_sig = (
        candidate_signature if candidate_signature is not None else signature(candidate_text, p)
    )
    estimate = jaccard_estimate(left_sig, right_sig)

    token_indel = Indel.normalized_similarity(a_tokens, b_tokens)
    return Rescore(
        score=token_indel,
        token_indel_similarity=token_indel,
        char_indel_similarity=Indel.normalized_similarity(query_text, candidate_text),
        char_levenshtein_similarity=Levenshtein.normalized_similarity(query_text, candidate_text),
        trigram_similarity=trigram.similarity(query_text, candidate_text),
        patience_similarity=(2 * matched / token_total) if token_total else 0.0,
        minhash_jaccard=estimate,
        true_jaccard=exact_jaccard(query_text, candidate_text, p.shingle_size),
        band_hits=band_hits,
        moved_token_count=len(moved_blocks(a_tokens, b_tokens)),
        matched_tokens=matched,
    )
