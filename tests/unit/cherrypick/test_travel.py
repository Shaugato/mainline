# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
"""Only tightenings travel; the envelope decides where; the score decides nothing."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from cherrypick_corpus import (
    APPLIES_FACTS,
    LESSON_FACTS,
    NO_MECHANISM_FACTS,
    PROPOSED_AT,
    lesson,
)
from mainline_cherrypick import (
    DEFAULT_SLA_DAYS,
    SCORE_WEIGHTS,
    SCORER_VERSION,
    WeakeningWouldTravel,
    applicability_score,
    due_by,
    evaluate_envelope,
    may_travel,
)
from mainline_domain.contracts import ControlDelta

# ── eligibility ──────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "delta",
    [ControlDelta.INTRODUCE, ControlDelta.STRENGTHEN, ControlDelta.RESTATE],
)
def test_a_tightening_may_travel(delta):
    assert lesson(control_delta=delta).control_delta is delta


@pytest.mark.parametrize("delta", [ControlDelta.WEAKEN, ControlDelta.REMOVE])
def test_a_weakening_cannot_even_be_constructed(delta):
    with pytest.raises(WeakeningWouldTravel, match="re-earned locally"):
        lesson(control_delta=delta)


def test_the_refusal_names_the_lesson_and_the_delta_not_the_constraint():
    with pytest.raises(WeakeningWouldTravel) as excinfo:
        lesson(control_delta=ControlDelta.WEAKEN)
    assert excinfo.value.delta == "weaken"
    assert "only_tightenings_travel" in str(excinfo.value)


# ── the envelope ─────────────────────────────────────────────────────────────


def test_the_lesson_applies_where_the_envelope_says_it_does():
    verdict = may_travel(lesson(), APPLIES_FACTS)
    assert verdict.travels
    assert verdict.reasons == ()


def test_a_site_outside_the_envelope_gets_a_reason_not_a_boolean():
    verdict = may_travel(lesson(), NO_MECHANISM_FACTS)
    assert not verdict.travels
    assert verdict.eligible
    assert not verdict.applicable
    assert any("flammable_atmosphere" in reason for reason in verdict.reasons)


def test_an_empty_envelope_applies_everywhere_which_is_a_claim_the_origin_made():
    applies, reasons = evaluate_envelope({}, frozenset())
    assert applies
    assert reasons == ()


def test_an_unrecognised_operator_is_refused_never_assumed_to_apply():
    applies, reasons = evaluate_envelope({"sql": "1=1"}, APPLIES_FACTS)
    assert not applies
    assert "unrecognised envelope operator" in reasons[0]


def test_a_multi_key_node_is_refused_so_an_implicit_and_cannot_be_misread():
    applies, reasons = evaluate_envelope(
        {"has": "hazard_energy:flammable_atmosphere", "absent": "x"}, APPLIES_FACTS
    )
    assert not applies
    assert "exactly one operator per node" in reasons[0]


def test_any_needs_only_one_arm():
    node = {"any": [{"has": "hazard_energy:nope"}, {"has": "asset:TK-2201"}]}
    applies, _ = evaluate_envelope(node, APPLIES_FACTS)
    assert applies


def test_not_inverts():
    applies, _ = evaluate_envelope({"not": {"has": "asset:TK-9999"}}, APPLIES_FACTS)
    assert applies
    applies, reasons = evaluate_envelope({"not": {"has": "asset:TK-2201"}}, APPLIES_FACTS)
    assert not applies
    assert "excluded condition holds" in reasons[0]


def test_an_empty_all_is_refused_rather_than_vacuously_true():
    applies, reasons = evaluate_envelope({"all": []}, APPLIES_FACTS)
    assert not applies
    assert "non-empty list" in reasons[0]


def test_an_unbounded_envelope_is_a_denial_of_service_and_is_refused():
    node: dict = {"has": "x"}
    for _ in range(12):
        node = {"not": node}
    with pytest.raises(ValueError, match="denial of service"):
        evaluate_envelope(node, APPLIES_FACTS)


# ── the score ────────────────────────────────────────────────────────────────


def test_the_weights_are_published_and_sum_to_one_thousand():
    assert sum(SCORE_WEIGHTS.values()) == 1000


def test_the_score_is_deterministic_and_names_a_deterministic_scorer():
    first = applicability_score(lesson(), APPLIES_FACTS, lesson_facts=LESSON_FACTS)
    second = applicability_score(lesson(), APPLIES_FACTS, lesson_facts=LESSON_FACTS)
    assert first == second
    assert "scorer" in SCORER_VERSION


def test_a_site_that_shares_the_hazard_scores_above_one_that_does_not():
    close = applicability_score(lesson(), APPLIES_FACTS, lesson_facts=LESSON_FACTS)
    far = applicability_score(lesson(), NO_MECHANISM_FACTS, lesson_facts=LESSON_FACTS)
    assert close > far


def test_a_low_score_is_still_an_offer_that_demands_an_answer():
    # DEP-3's content is a mandated RESPONSE, not mandated conformity. A score of
    # zero does not remove the obligation to answer, and nothing in the API lets a
    # score suppress a propagation.
    score = applicability_score(lesson(max_severity=1), frozenset(), lesson_facts=LESSON_FACTS)
    assert 0 <= score <= 1000
    assert may_travel(lesson(), APPLIES_FACTS).travels


def test_the_score_never_leaves_its_range():
    everything = LESSON_FACTS | APPLIES_FACTS
    assert applicability_score(lesson(), everything, lesson_facts=LESSON_FACTS) <= 1000


# ── the SLA clock ────────────────────────────────────────────────────────────


def test_a_higher_severity_gets_a_shorter_window():
    severe = due_by(PROPOSED_AT, 5)
    mild = due_by(PROPOSED_AT, 1)
    assert severe < mild


def test_the_sla_table_is_an_argument_because_it_is_not_a_standard():
    custom = {5: 1, 4: 2, 3: 3, 2: 4, 1: 5}
    assert due_by(PROPOSED_AT, 5, sla_days=custom) == datetime(2026, 7, 2, 9, 0, tzinfo=UTC)
    assert DEFAULT_SLA_DAYS[5] == 7


def test_an_unmapped_severity_refuses_rather_than_guessing_the_loosest_window():
    with pytest.raises(KeyError):
        due_by(PROPOSED_AT, 9)


def test_a_naive_proposed_at_is_refused():
    with pytest.raises(ValueError, match="provable if T has a zone"):
        due_by(datetime(2026, 7, 1, 9, 0), 5)  # noqa: DTZ001
