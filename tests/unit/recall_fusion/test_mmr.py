# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""MMR dedup: nothing is dropped, and every suppressed sibling names its representative."""

from __future__ import annotations

import math

import pytest

from trappoint_recall.fusion.mmr import (
    DEFAULT_LAMBDA,
    DEFAULT_REDUNDANCY_THRESHOLD,
    InvalidMmrInput,
    MmrCandidate,
    cosine_similarity,
    maximal_marginal_relevance,
)


def _unit(angle: float) -> tuple[float, ...]:
    return (math.cos(angle), math.sin(angle), 0.0)


def _cluster(prefix: str, base_angle: float, count: int, spread: float, top: float):  # type: ignore[no-untyped-def]
    """A tight cluster: ``count`` near-identical cues around ``base_angle``."""
    return [
        MmrCandidate(
            doc_id=f"{prefix}{index}",
            relevance=top - 0.001 * index,
            embedding=_unit(base_angle + spread * index),
        )
        for index in range(count)
    ]


def _fleet_duplicate_corpus() -> list[MmrCandidate]:
    """One OEM alert landing on six sites, plus two genuinely distinct precursors."""
    return [
        *_cluster("OEM", 0.0, 6, 0.004, 0.90),
        MmrCandidate(doc_id="DISTINCT-A", relevance=0.70, embedding=_unit(1.2)),
        MmrCandidate(doc_id="DISTINCT-B", relevance=0.55, embedding=_unit(2.4)),
    ]


# --------------------------------------------------------------------------------------
# Conservation: the property the whole return type exists for
# --------------------------------------------------------------------------------------


def test_every_input_lands_in_exactly_one_of_the_two_partitions() -> None:
    candidates = _fleet_duplicate_corpus()
    selection = maximal_marginal_relevance(candidates)
    assert selection.conserved
    assert len(selection.representatives) + len(selection.suppressed) == len(candidates)
    landed = {r.doc_id for r in selection.representatives} | {
        s.doc_id for s in selection.suppressed
    }
    assert landed == {c.doc_id for c in candidates}


def test_every_suppressed_sibling_is_reachable_from_its_representative() -> None:
    """The list is ``also_matched`` on the check: visible, not hidden."""
    selection = maximal_marginal_relevance(_fleet_duplicate_corpus())
    assert selection.suppressed, "the fleet-duplicate corpus must produce siblings"
    attached: list[str] = []
    for representative in selection.representatives:
        attached.extend(representative.also_matched)
    assert sorted(attached) == sorted(s.doc_id for s in selection.suppressed)
    for sibling in selection.suppressed:
        assert sibling.doc_id in selection.also_matched_for(sibling.representative_id)


def test_a_sibling_carries_the_arithmetic_its_silence_row_needs() -> None:
    selection = maximal_marginal_relevance(_fleet_duplicate_corpus())
    record = selection.suppressed[0].to_silence_record()
    assert record["reason"] == "dedup_sibling"
    assert record["subject_id"] == selection.suppressed[0].doc_id
    assert isinstance(record["arithmetic"], dict)
    assert record["arithmetic"]["representative_id"]
    assert record["threshold"] == pytest.approx(selection.suppressed[0].similarity)


def test_the_six_site_alert_collapses_to_one_representative_with_five_siblings() -> None:
    selection = maximal_marginal_relevance(_fleet_duplicate_corpus())
    oem = [r for r in selection.representatives if r.doc_id.startswith("OEM")]
    assert len(oem) == 1
    assert len(oem[0].also_matched) == 5
    assert {r.doc_id for r in selection.representatives} >= {"DISTINCT-A", "DISTINCT-B"}


def test_split_at_returns_the_overflow_rather_than_forgetting_it() -> None:
    selection = maximal_marginal_relevance(_fleet_duplicate_corpus())
    kept, overflow = selection.split_at(1)
    assert len(kept) == 1
    assert len(kept) + len(overflow) == len(selection.representatives)


# --------------------------------------------------------------------------------------
# The trade-off actually trades
# --------------------------------------------------------------------------------------


def test_a_threshold_of_one_suppresses_nothing() -> None:
    selection = maximal_marginal_relevance(_fleet_duplicate_corpus(), redundancy_threshold=1.0)
    assert selection.suppressed == ()
    assert len(selection.representatives) == 8


def test_a_loose_threshold_suppresses_more() -> None:
    tight = maximal_marginal_relevance(_fleet_duplicate_corpus(), redundancy_threshold=0.99)
    loose = maximal_marginal_relevance(_fleet_duplicate_corpus(), redundancy_threshold=0.20)
    assert len(loose.suppressed) > len(tight.suppressed)


def test_the_defaults_are_the_documented_ones() -> None:
    selection = maximal_marginal_relevance(_fleet_duplicate_corpus())
    assert selection.lambda_value == DEFAULT_LAMBDA == 0.7
    assert selection.redundancy_threshold == DEFAULT_REDUNDANCY_THRESHOLD


def test_the_most_relevant_candidate_is_always_a_representative() -> None:
    """The first pick has nothing to be redundant with, so the top hit can never be a sibling."""
    selection = maximal_marginal_relevance(_fleet_duplicate_corpus())
    assert selection.representatives[0].doc_id == "OEM0"
    assert selection.representatives[0].order == 1


def test_the_selection_is_deterministic_under_input_reordering() -> None:
    candidates = _fleet_duplicate_corpus()
    forward = maximal_marginal_relevance(candidates)
    backward = maximal_marginal_relevance(list(reversed(candidates)))
    assert [r.doc_id for r in forward.representatives] == [
        r.doc_id for r in backward.representatives
    ]
    assert [s.doc_id for s in forward.suppressed] == [s.doc_id for s in backward.suppressed]


# --------------------------------------------------------------------------------------
# Cosine, and the inputs it refuses
# --------------------------------------------------------------------------------------


def test_cosine_of_a_vector_with_itself_is_one() -> None:
    assert cosine_similarity(_unit(0.3), _unit(0.3)) == pytest.approx(1.0, abs=1e-15)


def test_cosine_never_escapes_the_unit_interval() -> None:
    for angle in (0.0, 0.5, 1.0, 2.0, 3.0):
        value = cosine_similarity(_unit(angle), _unit(angle))
        assert -1.0 <= value <= 1.0


def test_a_zero_vector_is_refused_rather_than_read_as_maximally_dissimilar() -> None:
    with pytest.raises(InvalidMmrInput, match="zero vector"):
        cosine_similarity((0.0, 0.0), (1.0, 0.0))


def test_two_embedding_spaces_are_refused() -> None:
    with pytest.raises(InvalidMmrInput, match="widths differ"):
        cosine_similarity((1.0, 0.0), (1.0, 0.0, 0.0))


# --------------------------------------------------------------------------------------
# Malformed input
# --------------------------------------------------------------------------------------


def test_a_duplicate_doc_id_is_refused() -> None:
    with pytest.raises(InvalidMmrInput, match="appears twice"):
        maximal_marginal_relevance(
            [
                MmrCandidate(doc_id="A", relevance=1.0, embedding=_unit(0.0)),
                MmrCandidate(doc_id="A", relevance=0.5, embedding=_unit(1.0)),
            ]
        )


@pytest.mark.parametrize("value", [-0.1, 1.1])
def test_a_lambda_outside_the_unit_interval_is_refused(value: float) -> None:
    with pytest.raises(InvalidMmrInput, match="lambda"):
        maximal_marginal_relevance([], lambda_value=value)


def test_an_empty_candidate_set_is_an_empty_selection_not_an_error() -> None:
    selection = maximal_marginal_relevance([])
    assert selection.representatives == () and selection.suppressed == ()
    assert selection.conserved


def test_a_non_finite_relevance_or_embedding_is_refused() -> None:
    with pytest.raises(InvalidMmrInput, match="not finite"):
        MmrCandidate(doc_id="A", relevance=float("nan"), embedding=_unit(0.0))
    with pytest.raises(InvalidMmrInput, match="non-finite component"):
        MmrCandidate(doc_id="A", relevance=1.0, embedding=(float("inf"), 0.0))
