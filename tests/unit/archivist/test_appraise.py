# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
"""The decision the Archivist does not make, asserted from both directions.

Every test here is a sentence from migration 0033 or ARCHITECTURE.md §8.4 turned into an
assertion. The one that matters most is :func:`test_model_rating_of_five_lands_at_three`,
because it asserts the *exhibit*: rated 5 by a model, the event sits in the record at
``severity_gate = 3`` with ``severity_potential = 5``, and the disagreement is quotable.
"""

from __future__ import annotations

import archivist_corpus as corpus
import pytest
from mainline_archivist import (
    ARMING_THRESHOLD,
    MODEL_GATE_CEILING,
    Basis,
    ModelRatedCannotArm,
    SeverityClaim,
    SeverityOutOfRange,
    SeverityWithoutBasis,
    SeverityWithoutSpan,
    UnsignedPromotion,
    appraise,
    downgrade_silence_rows,
    promote,
)


def _model_claim(value: int, quote: str = corpus.POTENTIAL_CODE_QUOTE) -> SeverityClaim:
    return SeverityClaim.model(
        value,
        profile_id="narration",
        prompt_version="narration.v1",
        output_sha256="0" * 64,
        span=corpus.span(quote),
    )


def test_the_ceiling_is_one_below_the_arming_threshold():
    # If these two ever drift apart, a model rating could arm a blocking gate through
    # arithmetic that still looked deliberate.
    assert MODEL_GATE_CEILING == ARMING_THRESHOLD - 1
    assert ARMING_THRESHOLD == 4


def test_model_rating_of_five_lands_at_three():
    # Migration 0033, verbatim: "Rated 5 by a model, the event still sits in the record at
    # severity_gate = 3 with severity_potential = 5."
    appraisal = appraise([_model_claim(5)])

    assert appraisal.severity_potential == 5
    assert appraisal.severity_gate == 3
    assert appraisal.severity_basis is Basis.MODEL_RATED
    assert not appraisal.arms_gate
    assert appraisal.disagrees


def test_the_capped_reading_is_a_row_not_a_shrug():
    appraisal = appraise([_model_claim(5)])

    (downgrade,) = appraisal.downgrades
    assert downgrade.proposed == 5
    assert downgrade.admitted == MODEL_GATE_CEILING
    assert downgrade.reason == "cap_exceeded"

    (row,) = downgrade_silence_rows(
        appraisal, site_id=corpus.SITE_ID, subject_kind="event", subject_id="IR-2019-0117"
    )
    mapping = row.to_mapping()
    assert mapping["source"] == "severity_downgrade"
    assert mapping["reason"] == "cap_exceeded"
    assert mapping["score"] == 5.0
    assert mapping["threshold"] == float(MODEL_GATE_CEILING)
    # The row names the call whose reading was capped, not just the number.
    assert mapping["arithmetic"]["claim"]["evidence"]["profile_id"] == "narration"


def test_a_model_may_not_say_what_happened():
    with pytest.raises(ModelRatedCannotArm, match="severity_actual"):
        SeverityClaim(
            basis=Basis.MODEL_RATED,
            value=2,
            dimension="actual",
            attributed_to="triage",
            span=corpus.span(corpus.ACTUAL_CODE_QUOTE),
        )


def test_a_coded_field_arms_the_gate_and_a_model_does_not():
    coded = SeverityClaim.coded(
        5,
        field_name="consequence_class_actual",
        dimension="actual",
        span=corpus.span(corpus.ACTUAL_CODE_QUOTE),
    )
    appraisal = appraise([coded, _model_claim(5)])

    assert appraisal.severity_gate == 5
    assert appraisal.arms_gate
    assert appraisal.severity_basis is Basis.CODED_FIELD
    # The model's reading is still recorded in full, uncapped, in potential.
    assert appraisal.severity_potential == 5
    # …and the cap is still recorded, because the coded field agreeing does not make the
    # ceiling not have applied to the model's own claim.
    assert appraisal.downgrades


def test_the_corpus_document_appraises_to_three_actual_five_potential():
    appraisal = appraise(list(corpus.coded_claims()))

    assert appraisal.severity_actual == 3
    assert appraisal.severity_potential == 5
    # Both claims are coded, so the potential is admitted and the gate takes it.
    assert appraisal.severity_gate == 5
    assert appraisal.severity_basis is Basis.CODED_FIELD
    assert appraisal.severity_span == corpus.span(corpus.POTENTIAL_CODE_QUOTE).pair


def test_a_tie_attributes_to_the_stronger_basis():
    coded = SeverityClaim.coded(
        3, field_name="consequence_class_actual", span=corpus.span(corpus.ACTUAL_CODE_QUOTE)
    )
    appraisal = appraise([_model_claim(3), coded])

    assert appraisal.severity_gate == 3
    assert appraisal.severity_basis is Basis.CODED_FIELD


def test_a_severity_with_no_span_is_a_number_somebody_typed():
    with pytest.raises(SeverityWithoutSpan, match="no source span"):
        SeverityClaim.coded(4, field_name="consequence_class_actual")


def test_a_zero_needs_no_span():
    claim = SeverityClaim.coded(0, field_name="consequence_class_actual")
    appraisal = appraise([claim])

    assert appraisal.severity_gate == 0
    assert appraisal.severity_span is None
    assert appraisal.severity_basis is Basis.CODED_FIELD


def test_an_empty_claim_set_is_refused_rather_than_defaulted():
    with pytest.raises(SeverityWithoutBasis, match="closed vocabulary"):
        appraise([])


@pytest.mark.parametrize("value", [-1, 6, 99])
def test_out_of_range_is_refused_before_the_check_sees_it(value):
    with pytest.raises(SeverityOutOfRange):
        SeverityClaim.coded(
            value, field_name="consequence_class_actual", span=corpus.span(corpus.TITLE_QUOTE)
        )


def test_promotion_costs_a_name_and_a_credential():
    reading = _model_claim(5)

    with pytest.raises(UnsignedPromotion):
        promote(reading, person_id="", credential_id="cred-1")
    with pytest.raises(UnsignedPromotion):
        promote(reading, person_id="person-1", credential_id="  ")

    promoted = promote(reading, person_id="person-1", credential_id="cred-1")
    assert promoted.basis is Basis.HUMAN_RATED
    # The machine's involvement is kept, not laundered away.
    assert dict(promoted.evidence)["promoted_from"] == "model_rated"
    assert dict(promoted.evidence)["profile_id"] == "narration"

    appraisal = appraise([promoted])
    assert appraisal.severity_gate == 5
    assert appraisal.arms_gate


def test_promoting_a_coded_field_is_a_confusion_not_a_no_op():
    coded = SeverityClaim.coded(
        3, field_name="consequence_class_actual", span=corpus.span(corpus.ACTUAL_CODE_QUOTE)
    )
    with pytest.raises(ValueError, match="promote"):
        promote(coded, person_id="person-1", credential_id="cred-1")


def test_an_unsigned_human_rating_is_refused():
    with pytest.raises(UnsignedPromotion, match="signing credential"):
        SeverityClaim.human(
            4,
            person_id="person-1",
            credential_id="",
            span=corpus.span(corpus.ACTUAL_CODE_QUOTE),
        )


def test_columns_match_the_ddl_names():
    columns = appraise(list(corpus.coded_claims())).to_columns()

    assert set(columns) == {
        "severity_actual",
        "severity_potential",
        "severity_gate",
        "severity_basis",
        "severity_span",
    }
    assert columns["severity_basis"] in {
        "coded_field",
        "regulator_class",
        "human_rated",
        "model_rated",
    }
    # `severity_span` is an INT8[] of exactly two, per CHECK severity_span_is_a_pair.
    assert len(columns["severity_span"]) == 2


def test_regulator_classification_arms_the_gate():
    claim = SeverityClaim.regulator(
        5,
        scheme="WHS-Reg-2011",
        code="s.35-notifiable",
        span=corpus.span(corpus.POTENTIAL_CODE_QUOTE),
    )
    appraisal = appraise([claim])

    assert appraisal.severity_gate == 5
    assert appraisal.severity_basis is Basis.REGULATOR_CLASS
    assert dict(appraisal.determined_by.evidence)["scheme"] == "WHS-Reg-2011"
