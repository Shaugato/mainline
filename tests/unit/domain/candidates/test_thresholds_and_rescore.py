# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""The bands, their fingerprint, and the rescorer's feature map.

Decision D11 puts a content hash of the identity policy on every
``identity_assignment`` row so that retro-tuning the matcher to make a drop look
reasonable becomes visible.  ``StageBands.fingerprint()`` is the cascade's
contribution to that hash: it moves when any band moves, and it is reproducible
by hand from ``thresholds.py`` and nothing else.
"""

from __future__ import annotations

from dataclasses import replace

import pytest
from mainline_domain.identity.candidates import DEFAULT_BANDS, StageBands, rescore
from mainline_domain.identity.candidates.thresholds import BANDS_FINGERPRINT_DOMAIN

CLAUSE = "The authorised person shall isolate pump P-101A before breaking containment."
PARAPHRASE = "The authorised person must isolate pump P-101A before breaking containment."
UNRELATED = "Records of calibration shall be retained for seven years at the site office."


def test_the_defaults_are_the_ones_the_research_table_states() -> None:
    assert DEFAULT_BANDS.exact_accept == 1.0
    assert DEFAULT_BANDS.anchor_accept == 0.92
    assert DEFAULT_BANDS.anchor_trigram_floor == 0.55
    assert DEFAULT_BANDS.lexical_accept == 0.90
    assert DEFAULT_BANDS.lexical_reject == 0.30
    assert DEFAULT_BANDS.semantic_accept == 0.93
    assert DEFAULT_BANDS.semantic_reject == 0.70


def test_the_fingerprint_is_32_bytes_and_stable() -> None:
    first = DEFAULT_BANDS.fingerprint()
    assert len(first) == 32
    assert first == DEFAULT_BANDS.fingerprint()


def test_the_fingerprint_moves_when_any_band_moves() -> None:
    seen = {DEFAULT_BANDS.fingerprint()}
    for field_name in (
        "anchor_accept",
        "anchor_trigram_floor",
        "lexical_accept",
        "lexical_reject",
        "semantic_accept",
        "semantic_reject",
    ):
        moved = replace(DEFAULT_BANDS, **{field_name: 0.777})
        digest = moved.fingerprint()
        assert digest not in seen, f"moving {field_name} did not move the fingerprint"
        seen.add(digest)


def test_the_fingerprint_is_reproducible_by_hand() -> None:
    """The preimage is documented, so an auditor can recompute it from the file."""
    import hashlib

    bands = StageBands(
        exact_accept=1.0,
        anchor_accept=0.5,
        anchor_trigram_floor=0.25,
        lexical_accept=0.5,
        lexical_reject=0.125,
        semantic_accept=0.75,
        semantic_reject=0.375,
    )
    preimage = BANDS_FINGERPRINT_DOMAIN + (
        b"exact_accept=1.0\n"
        b"anchor_accept=0.5\n"
        b"anchor_trigram_floor=0.25\n"
        b"lexical_accept=0.5\n"
        b"lexical_reject=0.125\n"
        b"semantic_accept=0.75\n"
        b"semantic_reject=0.375\n"
    )
    assert bands.fingerprint() == hashlib.sha256(preimage).digest()


# --------------------------------------------------------------------------- #
# the rescorer                                                                #
# --------------------------------------------------------------------------- #


def test_identical_text_scores_one_on_every_measure() -> None:
    scored = rescore(CLAUSE, CLAUSE)
    assert scored.score == 1.0
    assert scored.token_indel_similarity == 1.0
    assert scored.char_indel_similarity == 1.0
    assert scored.trigram_similarity == 1.0
    assert scored.patience_similarity == 1.0
    assert scored.minhash_jaccard == 1.0
    assert scored.true_jaccard == 1.0


def test_the_score_of_record_is_the_token_level_number() -> None:
    scored = rescore(CLAUSE, PARAPHRASE)
    assert scored.score == scored.token_indel_similarity


def test_the_character_level_floor_is_real_and_is_why_tokens_won() -> None:
    """The measurement that decided the score of record.

    Two unrelated English sentences of similar length still score well above
    the 0.30 auto-reject band on characters, and well below it on tokens.  If
    this ever stops being true the choice in ``rescore.py`` should be revisited
    — which is exactly why it is asserted rather than described.
    """
    scored = rescore(CLAUSE, UNRELATED)
    assert scored.char_indel_similarity > DEFAULT_BANDS.lexical_reject
    assert scored.token_indel_similarity < DEFAULT_BANDS.lexical_reject


def test_a_two_word_paraphrase_clears_the_auto_accept_band() -> None:
    assert rescore(CLAUSE, PARAPHRASE).score >= DEFAULT_BANDS.lexical_accept


def test_every_recorded_feature_is_a_float() -> None:
    features = rescore(CLAUSE, PARAPHRASE, band_hits=9).features()
    assert all(isinstance(v, float) for v in features.values())
    assert features["band_hits"] == 9.0


def test_rescoring_is_symmetric_in_its_score() -> None:
    assert rescore(CLAUSE, PARAPHRASE).score == pytest.approx(rescore(PARAPHRASE, CLAUSE).score)


def test_supplying_signatures_does_not_change_the_estimate() -> None:
    from mainline_domain.identity.candidates import signature

    with_sigs = rescore(
        CLAUSE,
        PARAPHRASE,
        query_signature=signature(CLAUSE),
        candidate_signature=signature(PARAPHRASE),
    )
    without = rescore(CLAUSE, PARAPHRASE)
    assert with_sigs.features() == without.features()


def test_patience_matched_tokens_never_exceed_the_lcs_behind_the_score() -> None:
    """The two token numbers are commensurable; their gap is a reordering signature."""
    scored = rescore(CLAUSE, PARAPHRASE)
    assert scored.patience_similarity <= scored.token_indel_similarity + 1e-12
