# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""S1, S2 and S3 over an in-memory corpus — including everything they refuse.

The recurring assertion in this file is not "the right pair was found".  It is
**"the wrong pair was dropped, and the drop is a row with the arithmetic on
it."**  A cascade that discards silently gives W8 nothing to account for, and
the conservation identity CBM enforces is only as strong as the completeness of
what the stages hand it.
"""

from __future__ import annotations

import uuid

import pytest
from mainline_domain.anchors import extract_anchors
from mainline_domain.canon import canon_digest
from mainline_domain.identity.candidates import (
    DEFAULT_BANDS,
    ClauseRecord,
    ClauseRef,
    LexicalCorpus,
    anchor_stage,
    exact_stage,
    lexical_stage,
)

SITE = uuid.UUID("11111111-1111-4111-8111-111111111111")
ACTIVITY = "maintenance/mechanical-isolation"

BASE = (
    "The authorised person shall isolate pump P-101A at ISOL-4471 and verify zero "
    "energy at PIT-1204 before breaking containment."
)
REFLOWED = BASE  # byte-identical after canonicalisation: the S1 case
PARAPHRASE = (
    "The authorised person must isolate pump P-101A at ISOL-4471 and confirm zero "
    "energy at PIT-1204 before breaking containment."
)
DIFFERENT_PUMP = BASE.replace("P-101A", "P-101B")
ADDED_TAG = BASE.replace("pump P-101A", "pumps P-101A and P-101B")
UNRELATED = "Hot work in Zone 2 requires a gas test below 5 percent LEL recorded on the permit."
NO_ANCHORS = "The supervisor shall brief the crew before work commences."


def _record(text: str, tag: int) -> ClauseRecord:
    return ClauseRecord(
        ref=ClauseRef(uuid.UUID(int=tag, version=4), bytes([tag]) * 32),
        site_id=SITE,
        activity_root=ACTIVITY,
        canon_text=text,
        canon_sha256=canon_digest(text),
        anchors=extract_anchors(text),
    )


@pytest.fixture
def corpus() -> list[ClauseRecord]:
    return [
        _record(REFLOWED, 1),
        _record(PARAPHRASE, 2),
        _record(DIFFERENT_PUMP, 3),
        _record(ADDED_TAG, 4),
        _record(UNRELATED, 5),
        _record(NO_ANCHORS, 6),
    ]


# --------------------------------------------------------------------------- #
# S1                                                                          #
# --------------------------------------------------------------------------- #


def test_s1_matches_on_digest_and_scores_exactly_one(corpus: list[ClauseRecord]) -> None:
    result = exact_stage(canon_digest(BASE), corpus)
    assert [c.ancestor_clause_uuid for c in result.candidates] == [corpus[0].ref.clause_uuid]
    assert result.candidates[0].score == 1.0
    assert result.candidates[0].stage == "S1"


def test_s1_excludes_the_query_itself_and_records_why(corpus: list[ClauseRecord]) -> None:
    result = exact_stage(canon_digest(BASE), corpus, exclude=frozenset({corpus[0].ref}))
    assert result.candidates == ()
    assert [d.reason for d in result.dropped] == ["self_pair"]


def test_s1_refuses_a_tuned_accept_band(corpus: list[ClauseRecord]) -> None:
    """A policy file cannot ask for a digest match at less than digest equality."""
    from dataclasses import replace

    with pytest.raises(ValueError, match="definitional"):
        exact_stage(canon_digest(BASE), corpus, bands=replace(DEFAULT_BANDS, exact_accept=0.99))


def test_s1_misses_a_single_character_change(corpus: list[ClauseRecord]) -> None:
    """Which is the entire reason S2, S3 and S4 exist."""
    assert exact_stage(canon_digest(BASE + " "), corpus).candidates == ()


# --------------------------------------------------------------------------- #
# S2                                                                          #
# --------------------------------------------------------------------------- #


def test_s2_auto_accepts_the_identical_clause(corpus: list[ClauseRecord]) -> None:
    result = anchor_stage(query_anchors=extract_anchors(BASE), query_text=BASE, corpus=corpus)
    accepted = result.accepted(DEFAULT_BANDS.anchor_accept)
    assert {c.ancestor_clause_uuid for c in accepted} == {corpus[0].ref.clause_uuid}


def test_s2_emits_a_two_word_paraphrase_without_auto_accepting_it(
    corpus: list[ClauseRecord],
) -> None:
    """0.55 is where S2 stops speaking; 0.92 is where it auto-accepts.

    A two-word paraphrase of the same clause scores about 0.81: well above the
    floor, so it is emitted as a scored candidate — and below the accept band,
    so S2 declines to auto-accept it and it falls through to S3, which has
    evidence S2 does not.  The next test shows S3 finishing the job.
    """
    result = anchor_stage(query_anchors=extract_anchors(BASE), query_text=BASE, corpus=corpus)
    emitted = {c.ancestor_clause_uuid: c for c in result.candidates}
    candidate = emitted[corpus[1].ref.clause_uuid]
    assert DEFAULT_BANDS.anchor_trigram_floor <= candidate.score < DEFAULT_BANDS.anchor_accept


def test_s3_finishes_what_s2_declined_to_auto_accept(corpus: list[ClauseRecord]) -> None:
    """The cascade composing, end to end, on the pair S2 handed on."""
    index = LexicalCorpus(SITE)
    index.extend(corpus)
    result = lexical_stage(query_text=BASE, corpus=index)
    accepted = {c.ancestor_clause_uuid for c in result.accepted(DEFAULT_BANDS.lexical_accept)}
    assert corpus[1].ref.clause_uuid in accepted


def test_s2_refuses_a_conflicting_tag_as_anchor_set_differs(
    corpus: list[ClauseRecord],
) -> None:
    result = anchor_stage(query_anchors=extract_anchors(BASE), query_text=BASE, corpus=corpus)
    dropped = {d.ancestor_clause_uuid: d for d in result.dropped}
    record = dropped[corpus[2].ref.clause_uuid]
    assert record.reason == "anchor_set_differs"
    assert record.detail["compatible"] == 0.0


def test_s2_treats_an_added_tag_as_unequal_but_compatible(
    corpus: list[ClauseRecord],
) -> None:
    """The asymmetry that matters: compatible is not the same as equal.

    A descendant naming both pumps is an extension, not a swap, so it is not an
    anchor *conflict* — but it is not evidence of identity at S2's 0.92 band
    either, so it falls through to S3/S4 rather than being auto-accepted.
    """
    result = anchor_stage(query_anchors=extract_anchors(BASE), query_text=BASE, corpus=corpus)
    dropped = {d.ancestor_clause_uuid: d for d in result.dropped}
    record = dropped[corpus[3].ref.clause_uuid]
    assert record.reason == "anchor_set_differs"
    assert record.detail["compatible"] == 1.0


def test_s2_refuses_a_vacuous_match_between_anchor_free_clauses() -> None:
    """Empty-set equality is vacuously true and would auto-accept on no evidence."""
    corpus = [_record(NO_ANCHORS, 6)]
    result = anchor_stage(
        query_anchors=extract_anchors(NO_ANCHORS), query_text=NO_ANCHORS, corpus=corpus
    )
    assert result.candidates == ()
    assert [d.reason for d in result.dropped] == ["no_identity_anchors"]


def test_s2_refuses_when_the_anchors_would_be_carrying_the_whole_match() -> None:
    """Same tags, unrecognisably different prose: the floor is what catches it."""
    other = "P-101A at ISOL-4471 and PIT-1204 may be worked live under a hot work permit."
    corpus = [_record(other, 7)]
    result = anchor_stage(query_anchors=extract_anchors(BASE), query_text=BASE, corpus=corpus)
    reasons = [d.reason for d in result.dropped]
    assert reasons == ["trigram_floor"]
    assert result.dropped[0].detail["trigram_similarity"] < DEFAULT_BANDS.anchor_trigram_floor


def test_s2_scores_are_the_trigram_similarity_itself(corpus: list[ClauseRecord]) -> None:
    """No affine remapping of the floor onto the accept band."""
    from mainline_domain.identity.candidates import trigram_similarity

    result = anchor_stage(query_anchors=extract_anchors(BASE), query_text=BASE, corpus=corpus)
    for candidate in result.candidates:
        record = next(r for r in corpus if r.ref.clause_uuid == candidate.ancestor_clause_uuid)
        assert candidate.score == pytest.approx(trigram_similarity(BASE, record.canon_text))


# --------------------------------------------------------------------------- #
# S3                                                                          #
# --------------------------------------------------------------------------- #


@pytest.fixture
def banded(corpus: list[ClauseRecord]) -> LexicalCorpus:
    index = LexicalCorpus(SITE)
    index.extend(corpus)
    return index


def test_s3_surfaces_near_duplicates_and_rescoring_ranks_them(
    corpus: list[ClauseRecord], banded: LexicalCorpus
) -> None:
    result = lexical_stage(query_text=BASE, corpus=banded)
    found = [c.ancestor_clause_uuid for c in result.candidates]
    assert corpus[0].ref.clause_uuid in found
    assert corpus[1].ref.clause_uuid in found
    assert result.candidates[0].score >= result.candidates[-1].score


def test_s3_records_every_feature_it_computed(banded: LexicalCorpus) -> None:
    result = lexical_stage(query_text=BASE, corpus=banded)
    features = result.candidates[0].features
    for key in (
        "token_indel_similarity",
        "char_indel_similarity",
        "char_levenshtein_similarity",
        "trigram_similarity",
        "patience_similarity",
        "minhash_jaccard",
        "true_jaccard",
        "band_hits",
        "moved_token_count",
        "matched_tokens",
    ):
        assert key in features


def test_s3_score_of_record_is_the_token_indel_similarity(banded: LexicalCorpus) -> None:
    """Token level, not character level: see rescore.py for the measured reason."""
    result = lexical_stage(query_text=BASE, corpus=banded)
    for candidate in result.candidates:
        assert candidate.score == candidate.features["token_indel_similarity"]
        assert candidate.score != candidate.features["char_indel_similarity"] or (
            candidate.score == 1.0
        )


def test_s3_never_enumerates_the_unrelated_clause(
    corpus: list[ClauseRecord], banded: LexicalCorpus
) -> None:
    """The cost claim in one assertion: banding does not produce far pairs at all."""
    result = lexical_stage(query_text=BASE, corpus=banded)
    seen = {c.ancestor_clause_uuid for c in result.candidates} | {
        d.ancestor_clause_uuid for d in result.dropped
    }
    assert corpus[4].ref.clause_uuid not in seen
    assert corpus[5].ref.clause_uuid not in seen


def test_s3_records_a_band_miss_for_an_ancestor_it_was_told_to_account_for(
    corpus: list[ClauseRecord], banded: LexicalCorpus
) -> None:
    """Recall failure by name, at the moment it happens — the CBM asymmetry in miniature."""
    required = frozenset({corpus[4].ref})
    result = lexical_stage(query_text=BASE, corpus=banded, required_ancestors=required)
    misses = [d for d in result.dropped if d.reason == "band_miss"]
    assert [d.ancestor_clause_uuid for d in misses] == [corpus[4].ref.clause_uuid]
    assert misses[0].detail["band_hits"] == 0.0


def test_s3_ordering_is_deterministic_under_a_shuffled_corpus(
    corpus: list[ClauseRecord],
) -> None:
    forward = LexicalCorpus(SITE)
    forward.extend(corpus)
    backward = LexicalCorpus(SITE)
    backward.extend(reversed(corpus))

    a = lexical_stage(query_text=BASE, corpus=forward).candidates
    b = lexical_stage(query_text=BASE, corpus=backward).candidates
    assert [(c.ancestor_clause_uuid, c.score) for c in a] == [
        (c.ancestor_clause_uuid, c.score) for c in b
    ]


def test_s3_drops_a_survivor_that_the_text_does_not_support() -> None:
    """Banding is a generator, not a judgement.

    Driven through :func:`lexical_stage_from_hits` with a hit supplied directly,
    because the point under test is the *rescoring* half of S3.  Trying to make
    banding produce a bad pair would be testing the S-curve's tail — which is a
    probability, and a test that depends on one is a test that fails on a
    Tuesday.
    """
    from mainline_domain.identity.candidates import lexical_stage_from_hits
    from mainline_domain.identity.candidates.minhash import signature

    ref = ClauseRef(uuid.UUID(int=9, version=4), b"\x09" * 32)
    query = "The authorised person shall isolate pump P-101A before breaking containment."
    far = "Hot work in Zone 2 requires a gas test below 5 percent LEL on the permit."

    result = lexical_stage_from_hits(
        query_text=query,
        query_signature=signature(query),
        hits={ref: 1},
        text_of={ref: far},
    )
    assert result.candidates == ()
    assert [d.reason for d in result.dropped] == ["auto_reject"]
    assert result.dropped[0].detail["token_indel_similarity"] < DEFAULT_BANDS.lexical_reject
    assert result.dropped[0].detail["char_indel_similarity"] > DEFAULT_BANDS.lexical_reject, (
        "this pair is exactly the case that motivates scoring on tokens: on characters "
        "two unrelated English sentences still score above the auto-reject band"
    )
    assert "rescore-v1" in result.dropped[0].note
