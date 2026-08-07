# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""Path-A extraction: the behaviours the lattice is entitled to rely on.

Each test here is named for a claim the domain plan makes.  Where a claim is
about a *refusal to guess*, the assertion is that a slot is empty and the
confidence dropped — an extractor that fills a slot it could not read hands rule
R2 a fabricated setpoint to compare against ``safe_direction``.
"""

from __future__ import annotations

import pytest
from mainline_domain.cat import CAT_CONFIDENCES, ClauseHint, cat_key, extract_cat
from mainline_domain.contracts import CATResult


def cat_of(text: str, **kwargs: object) -> CATResult:
    return extract_cat(text, **kwargs)  # type: ignore[arg-type]


# --------------------------------------------------------------------------- #
# Deontic: the ladder rule R1 orders                                           #
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("The supervisor shall isolate the pump.", "MUST"),
        ("The supervisor must isolate the pump.", "MUST"),
        ("The supervisor is required to isolate the pump.", "MUST"),
        ("The supervisor should isolate the pump.", "SHOULD"),
        ("The supervisor is expected to isolate the pump.", "SHOULD"),
        ("The supervisor may isolate the pump.", "MAY"),
        ("The supervisor can isolate the pump.", "MAY"),
        ("The supervisor shall not isolate the pump.", "MUST_NOT"),
        ("The supervisor must not isolate the pump.", "MUST_NOT"),
        ("The supervisor may not isolate the pump.", "MUST_NOT"),
        ("The supervisor should not isolate the pump.", "SHOULD_NOT"),
        ("The supervisor isolates the pump.", "ABSENT"),
    ],
)
def test_deontic_ladder(text: str, expected: str) -> None:
    result = cat_of(text)
    assert result.cat is not None
    assert result.cat.deontic == expected


def test_longest_cue_wins_so_a_prohibition_is_never_an_obligation() -> None:
    """``'shall not'`` must beat ``'shall'``.

    This is the single worst bug available in the extractor: matching the
    shorter cue turns every prohibition in a corpus into an obligation, which
    inverts the control while leaving the CAT looking perfectly well-formed.
    """
    negative = cat_of("No person shall enter the confined space.")
    positive = cat_of("Any person shall enter the confined space.")
    assert negative.cat is not None
    assert positive.cat is not None
    assert negative.cat.deontic == "MUST_NOT"
    assert positive.cat.deontic == "MUST"
    assert cat_key(negative.cat) != cat_key(positive.cat)


# --------------------------------------------------------------------------- #
# Negation normalises into the deontic, never into the action                  #
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "text",
    [
        "The pressure shall not exceed 1750 kPa (g).",
        "The pressure shall remain below 1750 kPa (g).",
        "The pressure must not be exceeded above 1750 kPa (g).",
        "The pressure shall be kept below 1750 kPa (g).",
    ],
)
def test_negation_folds_into_the_deontic(text: str) -> None:
    """Four spellings of one control must produce one ``(deontic, action)`` pair.

    Encoding one of them as ``(MUST, not_exceed)`` and another as
    ``(MUST_NOT, exceed)`` would give a single control two identities.  An
    identity split is worse than a missed weakening: the blame edge detaches and
    nothing anywhere goes red.
    """
    result = cat_of(text)
    assert result.cat is not None
    assert (result.cat.deontic, result.cat.action) == ("MUST_NOT", "exceed")


def test_double_negative_returns_to_the_positive() -> None:
    result = cat_of("The pressure shall not remain below 1750 kPa (g).")
    assert result.cat is not None
    assert (result.cat.deontic, result.cat.action) == ("MUST", "exceed")


# --------------------------------------------------------------------------- #
# A unit is never guessed                                                      #
# --------------------------------------------------------------------------- #


def test_bare_number_yields_no_value_and_low_confidence() -> None:
    """``shall not exceed 50`` is not ``50 kPa``.

    A guessed unit is a fabricated setpoint, and rule R2 compares setpoints
    against ``safe_direction`` as though they were evidence.
    """
    result = cat_of("The maximum operating pressure shall not exceed 50.")
    assert result.cat is not None
    assert result.cat.value is None
    assert result.cat.parameter == "max_operating_pressure"
    assert result.cat.comparator == "<="
    assert result.confidence == "low"


def test_gauge_marker_is_read_and_absolute_is_never_assumed() -> None:
    gauge = cat_of("The pressure shall not exceed 1750 kPa (g).")
    bare = cat_of("The pressure shall not exceed 1750 kPa.")
    absolute = cat_of("The pressure shall not exceed 1750 kPa (a).")
    assert gauge.cat is not None
    assert bare.cat is not None
    assert absolute.cat is not None
    assert gauge.cat.value is not None
    assert bare.cat.value is not None
    assert gauge.cat.value.reference == "gauge"
    assert absolute.cat.value is not None
    assert absolute.cat.value.reference == "absolute"
    # 'none' means UNSTATED, not 'absolute'.  Decision D5: guessing absolute is
    # how 50 psig becomes 446 kPa(a) and a weakening reads as a strengthening.
    assert bare.cat.value.reference == "none"
    assert cat_key(gauge.cat) != cat_key(bare.cat) != cat_key(absolute.cat)


def test_unit_carrying_its_own_reference_beats_the_prose() -> None:
    result = cat_of("The pressure shall not exceed 250 psig.")
    assert result.cat is not None
    assert result.cat.value is not None
    assert (result.cat.value.unit, result.cat.value.reference) == ("psig", "gauge")


def test_spelled_out_units_are_read() -> None:
    result = cat_of("The relief valve shall be tested at intervals of 12 months.")
    assert result.cat is not None
    assert result.cat.frequency is not None
    assert result.cat.frequency.unit == "month"


# --------------------------------------------------------------------------- #
# Comparators                                                                  #
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("The level shall be at least 5 m.", ">="),
        ("The level shall be no more than 5 m.", "<="),
        ("The level shall be a maximum of 5 m.", "<="),
        ("The level shall be less than 5 m.", "<"),
        ("The level shall be greater than 5 m.", ">"),
        ("The level shall be exactly 5 m.", "="),
        ("The level shall be approximately 5 m.", "~"),
        ("The level shall be between 5 m and 9 m.", "range"),
    ],
)
def test_comparators(text: str, expected: str) -> None:
    result = cat_of(text)
    assert result.cat is not None
    assert result.cat.comparator == expected


def test_longest_comparator_wins_over_the_nearest() -> None:
    """``'a maximum of 50 kPa'`` contains both ``'maximum of'`` and ``'of'``.

    Nearest-wins would pick ``'of'`` and encode ``'='`` — turning a ceiling into
    a target, which rule R3 would then read as a tightening rather than see the
    ceiling at all.
    """
    result = cat_of("The pressure shall be a maximum of 50 kPa.")
    assert result.cat is not None
    assert result.cat.comparator == "<="


def test_range_is_lossy_and_says_so() -> None:
    result = cat_of("The oxygen concentration shall be between 19.5 % and 23.5 %.")
    assert result.cat is not None
    assert result.cat.value is not None
    assert result.cat.comparator == "range"
    assert str(result.cat.value.value) == "19.5", "the LOWER bound is kept (spec §10)"
    assert result.confidence == "low"


# --------------------------------------------------------------------------- #
# Hedges land in exceptions, where rule R4 can see one enter                   #
# --------------------------------------------------------------------------- #


def test_whs_hedge_is_an_exception_not_a_deontic() -> None:
    plain = cat_of("The vessel shall be isolated.")
    hedged = cat_of("The vessel shall be isolated so far as is reasonably practicable.")
    assert plain.cat is not None
    assert hedged.cat is not None
    assert plain.cat.deontic == hedged.cat.deontic == "MUST"
    assert plain.cat.exceptions == ()
    assert "so far as is reasonably practicable" in hedged.cat.exceptions
    # The whole point: the hedge moves the identity, so the lattice sees an edit.
    assert cat_key(plain.cat) != cat_key(hedged.cat)


def test_discretionary_hedge_forces_low_confidence() -> None:
    result = cat_of("Valves may be tested quarterly at the supervisor's discretion.")
    assert result.confidence == "low"
    assert result.cat is not None
    assert "at the supervisor's discretion" in result.cat.exceptions


def test_hedge_does_not_double_count_as_a_condition() -> None:
    """``'where practicable'`` is both a subordinator and a hedge; it counts once."""
    result = cat_of("All personnel shall wear hearing protection where practicable.")
    assert result.cat is not None
    assert result.cat.exceptions == ("where practicable",)
    assert result.cat.conditions == ()


def test_exception_subordinator_is_stripped_so_rewording_is_not_a_change() -> None:
    """``unless X`` and ``except where X`` must yield the same exception element.

    A rule that fires on rewordings gets switched off, and R4 is the rule that
    catches the commonest real weakening in the corpus.
    """
    unless = cat_of("The vessel shall be entered, unless the atmosphere is untested.")
    except_where = cat_of("The vessel shall be entered, except where the atmosphere is untested.")
    assert unless.cat is not None
    assert except_where.cat is not None
    assert unless.cat.exceptions == except_where.cat.exceptions == ("the atmosphere is untested",)


# --------------------------------------------------------------------------- #
# Verification collapses to keys, so R6 sees deletions and not rewordings      #
# --------------------------------------------------------------------------- #


def test_verification_cues_collapse_to_keys() -> None:
    result = cat_of(
        "A hold point and a second signature are required, "
        "and the permit to work shall be signed off."
    )
    assert result.cat is not None
    assert "hold_point" in result.cat.verification
    assert "second_signature" in result.cat.verification
    assert "permit_to_work" in result.cat.verification


def test_deleting_a_verification_step_moves_the_key() -> None:
    with_check = cat_of("The supervisor shall verify the isolation with an independent check.")
    without = cat_of("The supervisor shall verify the isolation.")
    assert with_check.cat is not None
    assert without.cat is not None
    assert "independent_check" in with_check.cat.verification
    assert without.cat.verification == ()
    assert cat_key(with_check.cat) != cat_key(without.cat)


# --------------------------------------------------------------------------- #
# Coverage quantifier: R5's slot                                               #
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("All valves shall be tested.", "all"),
        ("Every valve shall be tested.", "all"),
        ("Selected valves shall be tested.", "selected"),
        ("A representative sample of valves shall be tested.", "typical"),
        ("The valve shall be tested.", "unspecified"),
    ],
)
def test_coverage_quantifier(text: str, expected: str) -> None:
    result = cat_of(text)
    assert result.cat is not None
    assert result.cat.coverage_quantifier == expected


def test_narrowing_wins_by_declared_precedence_not_by_position() -> None:
    """Position is not evidence: a narrowing cue anywhere narrows the coverage."""
    result = cat_of("All valves shall be tested, with a representative sample witnessed.")
    assert result.cat is not None
    assert result.cat.coverage_quantifier == "typical"


# --------------------------------------------------------------------------- #
# Actor is a role, or it is unspecified                                        #
# --------------------------------------------------------------------------- #


def test_actor_comes_from_a_role_not_from_arbitrary_prose() -> None:
    """A closed actor slot is what keeps a reworded subject from re-keying a control."""
    stative = cat_of("The operating pressure of vessel V-201 shall not exceed 1750 kPa (g).")
    assert stative.cat is not None
    assert stative.cat.actor == "unspecified", "a controlled quantity is not an actor"

    named = cat_of("The supervisor shall verify the isolation.")
    assert named.cat is not None
    assert named.cat.actor == "supervisor"


def test_passive_by_agent_is_found() -> None:
    result = cat_of("The relief valve shall be inspected annually by a competent person.")
    assert result.cat is not None
    assert result.cat.actor == "competent person"


def test_nominalised_predicate_is_recovered_from_the_subject() -> None:
    """``'gas testing shall be carried out'`` is an obligation to test, not to carry out."""
    result = cat_of("Gas testing shall be carried out at intervals not exceeding 30 minutes.")
    assert result.cat is not None
    assert result.cat.action == "test"


# --------------------------------------------------------------------------- #
# Determinism                                                                  #
# --------------------------------------------------------------------------- #

_CORPUS = (
    "The authorised person shall isolate the pressure vessel before entry.",
    "The pressure shall not exceed 1750 kPa (g).",
    "No person shall enter a confined space unless the atmosphere has been tested.",
    "Gas testing shall be carried out at intervals not exceeding 30 minutes.",
    "The relief valve shall be inspected annually by a competent person.",
)


def test_extraction_is_deterministic() -> None:
    first = [extract_cat(text) for text in _CORPUS]
    second = [extract_cat(text) for text in _CORPUS]
    assert first == second


def test_confidence_is_exactly_the_three_values_the_sql_check_permits() -> None:
    """``cat_confidence CHECK (cat_confidence IN ('ok','low','opaque'))``."""
    assert CAT_CONFIDENCES == ("ok", "low", "opaque")
    corpus = (*_CORPUS, "See clause 7.3.2.", "A | B | C", "")
    for text in corpus:
        assert extract_cat(text).confidence in CAT_CONFIDENCES


def test_evidence_spans_are_offsets_into_canon_text() -> None:
    text = "The supervisor shall verify all isolation points."
    result = extract_cat(text)
    assert result.evidence_spans
    for start, end in result.evidence_spans:
        assert 0 <= start < end <= len(text)


def test_extractor_version_records_the_lexicon_bytes() -> None:
    """A stored CAT must record WHICH word lists decided it, or R4 is unfalsifiable."""
    result = extract_cat("The supervisor shall verify the isolation.")
    assert result.extractor_version.startswith("catseal/1+lex.")
    assert len(result.extractor_version.rsplit(".", 1)[-1]) == 16


def test_empty_text_has_no_cat_at_all() -> None:
    """``cat=None`` is 'nothing to read'; ``opaque`` is 'we looked and could not'."""
    result = extract_cat("   ")
    assert result.cat is None
    assert result.confidence == "opaque"


def test_hint_is_accepted_and_paragraph_is_the_default() -> None:
    text = "The supervisor shall verify the isolation."
    assert extract_cat(text) == extract_cat(text, hint=ClauseHint(layout_kind="paragraph"))
