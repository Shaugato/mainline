# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""Severity-Graded Admission: the bar moves, the score does not, and the cap has a scope.

Three claims are pinned here, and each one is a load-bearing sentence of the product:

* severity **lowers tau** and changes nothing else about a candidate;
* the cap of three is scoped to ``recall_probabilistic``, so five bonded fatalities produce
  five blocking checks and MI16 stays satisfiable;
* everything that does not block is *recorded* — below tau, capped, or demoted by the sweep
  rule — with the score and the threshold that produced the silence.
"""

from __future__ import annotations

import pytest

from trappoint_recall.fusion.sga import (
    BLOCKING_CAP_PROBABILISTIC,
    DEFAULT_TAU,
    AdmissionCandidate,
    AdmissionRefused,
    SilenceRecord,
    TauTable,
    admit,
)


def _probabilistic(
    doc_id: str, score: float, severity: int, rank: int = 1, channel: str = "C"
) -> AdmissionCandidate:
    return AdmissionCandidate(
        doc_id=doc_id,
        p_relevant=score,
        severity=severity,
        origin="recall_probabilistic",
        channel=channel,
        rank=rank,
    )


def _bonded(doc_id: str, rank: int) -> AdmissionCandidate:
    return AdmissionCandidate(
        doc_id=doc_id,
        p_relevant=0.02,
        severity=5,
        origin="bonded",
        channel="B",
        rank=rank,
    )


@pytest.fixture
def tau() -> TauTable:
    return TauTable.defaults("policy-under-test")


# --------------------------------------------------------------------------------------
# The table itself
# --------------------------------------------------------------------------------------


def test_the_default_table_is_the_architectures_initial_calibrated_values() -> None:
    assert DEFAULT_TAU == {5: 0.35, 4: 0.45, 3: 0.60, 2: 0.75, 1: 0.85}


def test_the_table_must_slope_downward_in_severity(tau: TauTable) -> None:
    assert tau.tau_for(5) < tau.tau_for(4) < tau.tau_for(3) < tau.tau_for(2) < tau.tau_for(1)


def test_a_table_that_demands_more_evidence_for_a_fatality_is_refused() -> None:
    with pytest.raises(AdmissionRefused, match="LOWERS the evidence bar"):
        TauTable(thresholds={5: 0.9, 4: 0.45, 3: 0.6, 2: 0.75, 1: 0.85})


def test_a_missing_severity_level_is_refused_rather_than_defaulted() -> None:
    with pytest.raises(AdmissionRefused, match="missing severity level"):
        TauTable(thresholds={5: 0.35, 4: 0.45, 3: 0.6, 2: 0.75})


# --------------------------------------------------------------------------------------
# Severity lowers the bar. It does not touch the score.
# --------------------------------------------------------------------------------------


def test_the_same_score_is_admitted_at_severity_5_and_silenced_at_severity_1(
    tau: TauTable,
) -> None:
    """The whole design in one assertion: less evidence required, not more claimed."""
    grave = admit([_probabilistic("E1", 0.40, severity=5)], tau_table=tau)
    minor = admit([_probabilistic("E1", 0.40, severity=1)], tau_table=tau)
    assert [c.doc_id for c in grave.blocking] == ["E1"]
    assert [c.doc_id for c in minor.silenced] == ["E1"]
    assert grave.blocking[0].tau_applied == 0.35
    assert minor.silenced[0].tau_applied == 0.85


@pytest.mark.parametrize("severity", [1, 2, 3, 4, 5])
def test_p_relevant_is_identical_at_every_severity(tau: TauTable, severity: int) -> None:
    """If severity ever multiplied a score, this is where it would show."""
    result = admit([_probabilistic("E1", 0.4321, severity=severity)], tau_table=tau)
    every = (*result.blocking, *result.advisory, *result.silenced)
    assert len(every) == 1
    assert every[0].p_relevant == 0.4321


def test_only_the_threshold_moves_with_severity(tau: TauTable) -> None:
    applied = []
    for severity in (1, 2, 3, 4, 5):
        result = admit([_probabilistic("E1", 0.99, severity=severity)], tau_table=tau)
        applied.append(result.blocking[0].tau_applied)
    assert applied == sorted(applied, reverse=True)
    assert applied == [0.85, 0.75, 0.60, 0.45, 0.35]


def test_the_silence_record_says_severity_selected_the_threshold(tau: TauTable) -> None:
    result = admit([_probabilistic("E1", 0.10, severity=3)], tau_table=tau)
    record = result.silence_records[0]
    assert record.reason == "below_tau"
    assert record.score == 0.10
    assert record.threshold == 0.60
    assert "did not alter the score" in str(record.arithmetic["severity_effect"])


# --------------------------------------------------------------------------------------
# The cap, and its scope
# --------------------------------------------------------------------------------------


def test_five_bonded_fatalities_produce_five_blocking_checks(tau: TauTable) -> None:
    """The completion test. A cap that could suppress a bonded fatality would contradict
    ``bonded_fatalities_all_blocking`` and make the gate unsatisfiable on a real fonds."""
    result = admit([_bonded(f"FATAL-{i}", i + 1) for i in range(5)], tau_table=tau)
    assert len(result.blocking) == 5
    assert result.n_blocking_probabilistic == 0
    assert result.advisory == () and result.silenced == ()
    assert result.silence_records == ()


def test_a_bonded_fatality_blocks_even_at_a_score_far_below_every_threshold(
    tau: TauTable,
) -> None:
    result = admit(
        [AdmissionCandidate("F1", 0.0, 5, "bonded", "B", 1)], tau_table=tau
    )
    assert result.blocking[0].outcome == "blocking"
    assert result.blocking[0].tau_consulted is False


def test_deterministic_ancestry_is_uncapped_too(tau: TauTable) -> None:
    result = admit(
        [
            AdmissionCandidate(f"A{i}", 0.01, 4, "deterministic_ancestry", "A", i + 1)
            for i in range(6)
        ],
        tau_table=tau,
    )
    assert len(result.blocking) == 6


def test_probabilistic_blocking_is_capped_at_three(tau: TauTable) -> None:
    result = admit(
        [_probabilistic(f"P{i}", 0.95, severity=3, rank=i + 1) for i in range(7)],
        tau_table=tau,
    )
    assert result.n_blocking_probabilistic == BLOCKING_CAP_PROBABILISTIC == 3
    assert len(result.advisory) == 4
    assert all(check.demotion == "cap_exceeded" for check in result.advisory)


def test_the_cap_never_reaches_the_bonded_set_even_when_both_are_present(
    tau: TauTable,
) -> None:
    candidates = [_bonded(f"FATAL-{i}", i + 1) for i in range(5)]
    candidates += [_probabilistic(f"P{i}", 0.95, severity=3, rank=i + 10) for i in range(5)]
    result = admit(candidates, tau_table=tau)
    bonded_blocking = [c for c in result.blocking if c.origin == "bonded"]
    assert len(bonded_blocking) == 5
    assert result.n_blocking_probabilistic == 3
    assert len(result.blocking) == 8


def test_the_overflow_record_carries_its_score_and_its_tau(tau: TauTable) -> None:
    result = admit(
        [_probabilistic(f"P{i}", 0.90 - 0.01 * i, severity=3, rank=i + 1) for i in range(5)],
        tau_table=tau,
    )
    overflow = [r for r in result.silence_records if r.reason == "cap_exceeded"]
    assert len(overflow) == 2
    for record in overflow:
        assert record.score is not None and record.score > 0
        assert record.threshold == 0.60
        assert record.arithmetic["cap"] == 3


def test_the_graver_precedent_takes_a_capped_slot_without_its_score_changing(
    tau: TauTable,
) -> None:
    """Severity orders a queue for scarce attention. It does not alter what was measured."""
    candidates = [
        _probabilistic("MINOR-1", 0.99, severity=1, rank=1),
        _probabilistic("MINOR-2", 0.98, severity=1, rank=2),
        _probabilistic("MINOR-3", 0.97, severity=1, rank=3),
        _probabilistic("FATAL", 0.40, severity=5, rank=9),
    ]
    result = admit(candidates, tau_table=tau)
    blocking = {c.doc_id: c for c in result.blocking}
    assert "FATAL" in blocking
    assert blocking["FATAL"].p_relevant == 0.40
    assert result.n_blocking_probabilistic == 3


def test_score_only_ordering_is_available_for_the_ablation(tau: TauTable) -> None:
    candidates = [
        _probabilistic("MINOR-1", 0.99, severity=1, rank=1),
        _probabilistic("MINOR-2", 0.98, severity=1, rank=2),
        _probabilistic("MINOR-3", 0.97, severity=1, rank=3),
        _probabilistic("FATAL", 0.40, severity=5, rank=9),
    ]
    result = admit(candidates, tau_table=tau, ordering="score_only")
    assert {c.doc_id for c in result.blocking} == {"MINOR-1", "MINOR-2", "MINOR-3"}


def test_a_cap_of_zero_blocks_nothing_probabilistic_and_still_blocks_the_bonded_set(
    tau: TauTable,
) -> None:
    result = admit(
        [_bonded("FATAL", 1), _probabilistic("P1", 0.99, severity=3, rank=2)],
        tau_table=tau,
        cap=0,
    )
    assert [c.doc_id for c in result.blocking] == ["FATAL"]
    assert [c.doc_id for c in result.advisory] == ["P1"]


# --------------------------------------------------------------------------------------
# The coarse sweep rule
# --------------------------------------------------------------------------------------


def test_a_sweep_hit_below_severity_five_is_advisory_however_high_it_scores(
    tau: TauTable,
) -> None:
    result = admit(
        [_probabilistic("S1", 0.99, severity=4, channel="C_sweep")], tau_table=tau
    )
    assert result.blocking == ()
    assert result.advisory[0].demotion == "coarse_sweep_below_severity_5"
    assert result.silence_records[0].reason == "bounded_negative"


def test_a_sweep_hit_at_severity_five_blocks_like_any_other(tau: TauTable) -> None:
    result = admit(
        [_probabilistic("S1", 0.50, severity=5, channel="C_sweep")], tau_table=tau
    )
    assert [c.doc_id for c in result.blocking] == ["S1"]


def test_coarse_only_carries_the_same_rule_as_the_sweep_channel(tau: TauTable) -> None:
    candidate = AdmissionCandidate(
        doc_id="S2",
        p_relevant=0.99,
        severity=2,
        origin="recall_probabilistic",
        channel="C",
        rank=1,
        coarse_only=True,
    )
    result = admit([candidate], tau_table=tau)
    assert result.advisory[0].demotion == "coarse_sweep_below_severity_5"


# --------------------------------------------------------------------------------------
# Conservation and refusals
# --------------------------------------------------------------------------------------


def test_every_candidate_lands_in_exactly_one_bucket(tau: TauTable) -> None:
    candidates = [
        _bonded("FATAL", 1),
        _probabilistic("HIGH", 0.95, severity=3, rank=2),
        _probabilistic("LOW", 0.05, severity=3, rank=3),
        _probabilistic("SWEEP", 0.95, severity=2, rank=4, channel="C_sweep"),
        *[_probabilistic(f"X{i}", 0.9, severity=3, rank=i + 5) for i in range(4)],
    ]
    result = admit(candidates, tau_table=tau)
    total = len(result.blocking) + len(result.advisory) + len(result.silenced)
    assert total == len(candidates)
    landed = {c.doc_id for c in (*result.blocking, *result.advisory, *result.silenced)}
    assert landed == {c.doc_id for c in candidates}


def test_a_duplicate_candidate_is_refused(tau: TauTable) -> None:
    with pytest.raises(AdmissionRefused, match="presented twice"):
        admit(
            [_probabilistic("E1", 0.9, 3, 1), _probabilistic("E1", 0.8, 3, 2)],
            tau_table=tau,
        )


def test_a_raw_cosine_masquerading_as_a_probability_is_refused() -> None:
    with pytest.raises(AdmissionRefused, match="calibrated probability"):
        AdmissionCandidate("E1", 1.4, 3, "recall_probabilistic", "C", 1)


def test_an_unknown_origin_is_refused() -> None:
    with pytest.raises(AdmissionRefused, match="unknown origin"):
        AdmissionCandidate("E1", 0.5, 3, "vibes", "C", 1)


def test_a_silence_reason_outside_the_closed_vocabulary_is_refused() -> None:
    with pytest.raises(AdmissionRefused, match="closed silence vocabulary"):
        SilenceRecord(
            subject_id="E1",
            reason="seemed_unimportant",
            severity=3,
            score=0.1,
            threshold=0.6,
            arithmetic={},
        )


def test_the_result_serialises_the_whole_arithmetic(tau: TauTable) -> None:
    result = admit(
        [_bonded("FATAL", 1), _probabilistic("LOW", 0.05, severity=3, rank=2)],
        tau_table=tau,
    )
    payload = result.to_json()
    assert payload["n_blocking"] == 1
    assert payload["n_blocking_probabilistic"] == 0
    assert payload["cap"] == 3
    assert payload["tau_table"]["tau"]["5"] == 0.35
    assert payload["silence_records"][0]["reason"] == "below_tau"
