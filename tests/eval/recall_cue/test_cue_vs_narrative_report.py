# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
"""Contract tests for the cue-vs-narrative stub.

Every assertion here is about the harness's **shape**, never about which genre wins.  A test
in this file that asserted "cue overlap exceeds narrative overlap" would be the component
under test certifying itself on seven handwritten fixtures, and it would still pass on the
day the real corpus said otherwise.  The retrieval claim is measured by
``recall-eval-harness`` against the gold sets, with intervals, or it is not made.
"""

from __future__ import annotations

from typing import Any

import pytest

from cue_vs_narrative import (
    GENRES,
    CueVsNarrativeReport,
    compare_genres,
    genre_probe,
    genre_texts,
    subject_tokens,
)
from mainline_recall_agent.cue.schema import SYNTHESISED_FACETS


class FakeArm:
    """The one field the probe reads.  Structural, so a bare checkout can run this."""

    def __init__(self, genre: str) -> None:
        self.embedding_genre = genre


def test_genre_texts_selects_the_right_facets(cue_sample: list[Any]) -> None:
    full = next(o for o in cue_sample if o.subject_ref == "FIX-EVT-0001")
    cue_texts = genre_texts(full, genre="cue")
    narrative_texts = genre_texts(full, genre="narrative")
    assert len(cue_texts) == len(SYNTHESISED_FACETS)
    assert len(narrative_texts) == 1
    assert all(" | mechanism: " in t or " | " in t for t in cue_texts)
    assert " | narrative: " in narrative_texts[0]


def test_texts_are_deduplicated_across_archival_levels(cue_sample: list[Any]) -> None:
    """The LMB writes one row per level; counting each would make coverage a depth artefact."""
    full = next(o for o in cue_sample if o.subject_ref == "FIX-EVT-0001")
    assert len(full.rows) > len(genre_texts(full, genre="cue")) + 1
    assert len(set(genre_texts(full, genre="cue"))) == len(genre_texts(full, genre="cue"))


def test_both_genres_carry_the_same_contextual_prefix(cue_sample: list[Any]) -> None:
    """Holding the D3 prefix constant is what stops its win being credited to cues."""
    full = next(o for o in cue_sample if o.subject_ref == "FIX-EVT-0001")
    prefix = full.rows[0].activity_path
    for genre in GENRES:
        for text in genre_texts(full, genre=genre):
            assert text.startswith(prefix + " | ")


def test_a_silenced_subject_contributes_no_text_under_either_genre(
    cue_sample: list[Any],
) -> None:
    silenced = next(o for o in cue_sample if o.status == "silenced")
    assert genre_texts(silenced, genre="cue") == ()
    assert genre_texts(silenced, genre="narrative") == ()


def test_an_unknown_genre_is_refused_rather_than_defaulted(cue_sample: list[Any]) -> None:
    with pytest.raises(ValueError, match="unknown embedding genre"):
        genre_texts(cue_sample[0], genre="hybrid")  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="does not implement"):
        genre_probe(FakeArm("hybrid"))


def test_the_probe_is_the_hook_a_backend_factory_calls(cue_sample: list[Any]) -> None:
    full = next(o for o in cue_sample if o.subject_ref == "FIX-EVT-0001")
    for genre in GENRES:
        select = genre_probe(FakeArm(genre))
        assert select(full) == genre_texts(full, genre=genre)


def test_the_real_ablation_arms_drive_the_probe() -> None:
    """Integration with the harness's own arm objects, skipped cleanly if it is absent."""
    ablation = pytest.importorskip(
        "trappoint_recall.eval.ablation",
        reason="trappoint-recall is not installed in this environment",
    )
    for arm in ablation.DEFAULT_MATRIX:
        assert callable(genre_probe(arm))
    narrative_arm = ablation.arm_by_id("V-narrative")
    assert narrative_arm.embedding_genre == "narrative"


def test_the_report_is_descriptive_and_carries_no_verdict(cue_sample: list[Any]) -> None:
    report = compare_genres(
        cue_sample,
        pairs=(("FIX-PTW-0001", "FIX-EVT-0001"),),
        label="committed cue cassettes (handwritten)",
    )
    assert isinstance(report, CueVsNarrativeReport)
    assert {s.genre for s in report.stats} == set(GENRES)
    assert report.stats_for("cue").subjects == len(cue_sample)
    assert report.stats_for("cue").subjects_with_no_text == 2  # refusal + dead letter
    rendered = report.to_markdown()
    assert "Report only" in rendered
    assert "No threshold" in rendered
    # No pass, no fail, no verdict vocabulary anywhere in the artefact.
    for banned in ("PASS", "FAIL", "threshold met", "wins"):
        assert banned not in rendered


def test_the_overlap_proxy_is_computed_for_named_pairs_only(cue_sample: list[Any]) -> None:
    """Which event is a precursor of which permit is gold-set knowledge, not ours to guess."""
    report = compare_genres(cue_sample, pairs=(("FIX-PTW-0001", "FIX-EVT-0001"),))
    assert len(report.pairs) == 1
    pair = report.pairs[0]
    assert 0.0 <= pair.cue_jaccard <= 1.0
    assert 0.0 <= pair.narrative_jaccard <= 1.0
    assert pair.delta == pytest.approx(pair.cue_jaccard - pair.narrative_jaccard)

    empty = compare_genres(cue_sample)
    assert empty.pairs == ()


def test_a_pair_naming_an_absent_subject_fails_loudly(cue_sample: list[Any]) -> None:
    with pytest.raises(KeyError, match="absent from the sample"):
        compare_genres(cue_sample, pairs=(("FIX-PTW-0001", "FIX-EVT-NOPE"),))


def test_tokenisation_preserves_identifiers() -> None:
    """``K-401``, ``H2S`` and ``%LEL`` are the vocabulary this domain turns on."""
    tokens = subject_tokens(["Isolation of K-401 at 10 %LEL with H2S present in the sump"])
    assert "k-401" in tokens
    assert "h2s" in tokens
    assert "%lel" not in tokens  # the leading % is not a token start; the number carries it
    assert "the" not in tokens
    assert "in" not in tokens


def test_the_report_serialises_to_stable_json(cue_sample: list[Any]) -> None:
    report = compare_genres(cue_sample, pairs=(("FIX-PTW-0002", "FIX-EVT-0002"),))
    assert report.to_json() == compare_genres(
        cue_sample, pairs=(("FIX-PTW-0002", "FIX-EVT-0002"),)
    ).to_json()
    payload = report.to_dict()
    assert set(payload) == {"label", "stats", "pairs", "notes"}
    assert any("open question" in note for note in payload["notes"])
