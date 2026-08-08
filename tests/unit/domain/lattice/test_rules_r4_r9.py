# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""R4 exception, R5 quantifier, R6 verification, R7 frequency, R8 anchor, R9 coverage.

Same shape as ``test_rules_r1_r3.py``: every rule gets an edit it must fire on
and an edit it must stay silent on.
"""

from __future__ import annotations

import pytest
from _lattice_fixtures import anchors, cat, empty_registry, qty

from mainline_domain.cat.schema import COVERAGE_QUANTIFIERS
from mainline_domain.contracts import AnchorClass, ControlDelta
from mainline_domain.lattice import (
    COVERAGE_RANK,
    RuleInput,
    r4_exception,
    r5_quantifier,
    r6_verification,
    r7_frequency,
    r8_anchor,
    r9_coverage,
)


def _inp(reference, descendant, *, ref_anchors=None, desc_anchors=None):  # type: ignore[no-untyped-def]
    return RuleInput(
        reference=reference,
        descendant=descendant,
        registry=empty_registry(),
        reference_anchors=ref_anchors,
        descendant_anchors=desc_anchors,
    )


# ── R4 ────────────────────────────────────────────────────────────────────────


def test_r4_positive_a_hedge_entering_is_a_weakening_and_the_note_names_it() -> None:
    """The commonest real weakening in a mining corpus, precisely because it does
    not look like one: the deontic is untouched and the sentence still says
    "shall"."""
    before = cat(deontic="MUST", action="isolate")
    after = cat(deontic="MUST", action="isolate", exceptions=("so far as is reasonably practicable",))
    findings = r4_exception(_inp(before, after))
    assert [f.delta for f in findings] == [ControlDelta.WEAKEN]
    assert "hedge" in findings[0].witness.note
    assert "reasonably practicable" in findings[0].witness.note


def test_r4_positive_an_ordinary_exception_entering_also_weakens_without_claiming_a_hedge() -> None:
    before = cat(exceptions=())
    after = cat(exceptions=("the vessel is already under nitrogen",))
    findings = r4_exception(_inp(before, after))
    assert [f.delta for f in findings] == [ControlDelta.WEAKEN]
    assert "hedge" not in findings[0].witness.note


def test_r4_two_exceptions_added_produce_two_findings_because_the_list_is_the_evidence() -> None:
    before = cat(exceptions=())
    after = cat(exceptions=("where practicable", "at the discretion of management"))
    findings = r4_exception(_inp(before, after))
    assert len(findings) == 2
    assert {f.delta for f in findings} == {ControlDelta.WEAKEN}


def test_r4_a_removed_exception_strengthens() -> None:
    before = cat(exceptions=("where practicable",))
    after = cat(exceptions=())
    assert [f.delta for f in r4_exception(_inp(before, after))] == [ControlDelta.STRENGTHEN]


def test_r4_negative_an_exception_present_on_both_sides_cancels() -> None:
    """A hedge already in the ancestor is in the descendant too, so it appears on
    both sides of the diff and costs nothing.  Only a hedge that ENTERS counts —
    which is why ``hedge.toml`` can afford to be generous."""
    both = ("so far as is reasonably practicable",)
    assert r4_exception(_inp(cat(exceptions=both), cat(exceptions=both))) == ()


def test_r4_negative_reordering_the_same_exceptions_is_not_a_change() -> None:
    before = cat(exceptions=("where practicable", "unless isolated"))
    after = cat(exceptions=("unless isolated", "where practicable"))
    assert r4_exception(_inp(before, after)) == ()


# ── R5 ────────────────────────────────────────────────────────────────────────


def test_r5_positive_all_to_selected_narrows() -> None:
    findings = r5_quantifier(_inp(cat(coverage_quantifier="all"), cat(coverage_quantifier="selected")))
    assert [f.delta for f in findings] == [ControlDelta.WEAKEN]
    assert findings[0].witness.field == "coverage_quantifier"


def test_r5_positive_all_to_typical_narrows_further() -> None:
    findings = r5_quantifier(_inp(cat(coverage_quantifier="all"), cat(coverage_quantifier="typical")))
    assert [f.delta for f in findings] == [ControlDelta.WEAKEN]


def test_r5_dropping_the_word_all_entirely_is_the_cheapest_weakening_and_is_caught() -> None:
    """``unspecified`` is the bottom of the rank, not a neutral middle."""
    findings = r5_quantifier(
        _inp(cat(coverage_quantifier="all"), cat(coverage_quantifier="unspecified"))
    )
    assert [f.delta for f in findings] == [ControlDelta.WEAKEN]


def test_r5_widening_strengthens() -> None:
    findings = r5_quantifier(_inp(cat(coverage_quantifier="typical"), cat(coverage_quantifier="all")))
    assert [f.delta for f in findings] == [ControlDelta.STRENGTHEN]


def test_r5_negative_an_unchanged_quantifier_is_silent() -> None:
    assert r5_quantifier(_inp(cat(coverage_quantifier="all"), cat(coverage_quantifier="all"))) == ()


def test_r5_ranks_exactly_the_vocabulary_cat_schema_closes() -> None:
    """A sixth quantifier cannot enter the lexicon without entering the rank table.

    If it could, the new value would land in the ``unknown`` branch and every
    clause carrying it would fail closed — correct, but silently and at corpus
    scale, which is indistinguishable from the rule being broken.
    """
    assert set(COVERAGE_RANK) == set(COVERAGE_QUANTIFIERS)
    assert len(set(COVERAGE_RANK.values())) == len(COVERAGE_RANK)


# ── R6 ────────────────────────────────────────────────────────────────────────


def test_r6_positive_a_deleted_hold_point_weakens_and_the_witness_names_it() -> None:
    before = cat(verification=("hold_point", "second_signature"))
    after = cat(verification=("second_signature",))
    findings = r6_verification(_inp(before, after))
    assert [f.delta for f in findings] == [ControlDelta.WEAKEN]
    assert "hold_point" in findings[0].witness.note


def test_r6_an_added_check_strengthens() -> None:
    before = cat(verification=())
    after = cat(verification=("independent_check",))
    assert [f.delta for f in r6_verification(_inp(before, after))] == [ControlDelta.STRENGTHEN]


def test_r6_negative_an_unchanged_verification_list_is_silent() -> None:
    both = ("independent_check", "hold_point")
    assert r6_verification(_inp(cat(verification=both), cat(verification=both))) == ()


def test_r6_a_swap_is_one_deletion_and_one_addition_not_a_silent_wash() -> None:
    """Replacing a hold point with a countersignature is two facts, not zero.

    The join makes the verdict ``weaken`` — force 2 beats force 0 — and both
    findings are written, so the repair set tells a person that restoring the hold
    point is what would clear the block.
    """
    before = cat(verification=("hold_point",))
    after = cat(verification=("second_signature",))
    findings = r6_verification(_inp(before, after))
    assert {f.delta for f in findings} == {ControlDelta.WEAKEN, ControlDelta.STRENGTHEN}


# ── R7 ────────────────────────────────────────────────────────────────────────


def test_r7_positive_a_longer_interval_weakens() -> None:
    before = cat(frequency=qty("7", "day"))
    after = cat(frequency=qty("30", "day"))
    findings = r7_frequency(_inp(before, after))
    assert [f.delta for f in findings] == [ControlDelta.WEAKEN]
    assert findings[0].witness.field == "frequency"


def test_r7_a_shorter_interval_strengthens() -> None:
    before = cat(frequency=qty("30", "day"))
    after = cat(frequency=qty("7", "day"))
    assert [f.delta for f in r7_frequency(_inp(before, after))] == [ControlDelta.STRENGTHEN]


def test_r7_the_interval_vanishing_weakens_because_an_unstated_interval_is_unbounded() -> None:
    findings = r7_frequency(_inp(cat(frequency=qty("7", "day")), cat(frequency=None)))
    assert [f.delta for f in findings] == [ControlDelta.WEAKEN]


def test_r7_negative_the_same_interval_in_different_units_is_not_a_change() -> None:
    """``168 hours`` is ``7 days`` exactly; the comparison is on magnitudes, not
    on spellings."""
    assert r7_frequency(_inp(cat(frequency=qty("7", "day")), cat(frequency=qty("168", "hour")))) == ()


def test_r7_negative_no_frequency_on_either_side_is_silent() -> None:
    assert r7_frequency(_inp(cat(), cat())) == ()


def test_r7_an_event_anchored_frequency_against_a_duration_fails_closed() -> None:
    """"before each use" is not a duration; the comparison is refused, not guessed."""
    from decimal import Decimal

    from mainline_domain.contracts import Quantity

    per_use = Quantity(value=Decimal("1"), unit="use", dimension="event", reference="none")
    findings = r7_frequency(_inp(cat(frequency=per_use), cat(frequency=qty("30", "day"))))
    assert [f.delta for f in findings] == [ControlDelta.WEAKEN]
    assert findings[0].orderable is False


# ── R8 ────────────────────────────────────────────────────────────────────────


def test_r8_positive_an_uncompensated_equipment_tag_drop_weakens() -> None:
    findings = r8_anchor(
        _inp(
            cat(),
            cat(),
            ref_anchors=anchors((AnchorClass.EQUIPMENT_TAG, "P-101A")),
            desc_anchors=anchors(),
        )
    )
    assert [f.delta for f in findings] == [ControlDelta.WEAKEN]
    assert findings[0].witness.field == "anchor:equipment_tag"


def test_r8_negative_a_compensated_drop_is_the_matchers_problem_not_this_rules() -> None:
    """``P-101A`` → ``P-101B`` is a *swap*.  ``AnchorSet.compatible_with`` already
    refuses to call those the same clause, which is louder than a drop, and firing
    here as well would double-count one edit."""
    findings = r8_anchor(
        _inp(
            cat(),
            cat(),
            ref_anchors=anchors((AnchorClass.EQUIPMENT_TAG, "P-101A")),
            desc_anchors=anchors((AnchorClass.EQUIPMENT_TAG, "P-101B")),
        )
    )
    assert findings == ()


def test_r8_negative_a_dropped_setpoint_anchor_belongs_to_r2() -> None:
    """``setpoint`` is deliberately not an identity anchor class."""
    findings = r8_anchor(
        _inp(
            cat(),
            cat(),
            ref_anchors=anchors((AnchorClass.SETPOINT, "1750 kpa")),
            desc_anchors=anchors(),
        )
    )
    assert findings == ()


def test_r8_an_added_anchor_strengthens() -> None:
    findings = r8_anchor(
        _inp(
            cat(),
            cat(),
            ref_anchors=anchors(),
            desc_anchors=anchors((AnchorClass.ISOLATION_POINT_ID, "ISO-44")),
        )
    )
    assert [f.delta for f in findings] == [ControlDelta.STRENGTHEN]


def test_r8_negative_absent_anchor_sets_mean_the_rule_did_not_run() -> None:
    """It does NOT fail closed on missing anchors — that would make every
    CAT-only comparison a weakening, including the two-tuple comparison this
    lattice is specified in terms of.  The omission is reported instead."""
    assert r8_anchor(_inp(cat(), cat())) == ()


# ── R9 ────────────────────────────────────────────────────────────────────────


def test_r9_positive_a_cat_present_in_the_reference_and_absent_after_is_remove() -> None:
    findings = r9_coverage(_inp(cat(deontic="MUST"), None))
    assert [f.delta for f in findings] == [ControlDelta.REMOVE]
    assert findings[0].witness.from_repr == "present"


def test_r9_the_dual_is_introduce_and_it_is_force_zero() -> None:
    """Adding a control is safe; deleting one is not.  The asymmetry is the product."""
    from mainline_domain.contracts import force

    findings = r9_coverage(_inp(None, cat(deontic="MUST")))
    assert [f.delta for f in findings] == [ControlDelta.INTRODUCE]
    assert force(findings[0].delta) == 0
    assert force(ControlDelta.REMOVE) == 3


def test_r9_negative_two_present_cats_are_silent() -> None:
    assert r9_coverage(_inp(cat(), cat())) == ()


@pytest.mark.parametrize(
    "rule",
    [r4_exception, r5_quantifier, r6_verification, r7_frequency],
)
def test_the_cat_slot_rules_stand_down_when_one_side_is_absent(rule) -> None:  # type: ignore[no-untyped-def]
    """Only R9 speaks about a missing CAT.  A rule that read ``None.exceptions``
    would raise; a rule that treated absence as an empty tuple would report the
    deletion of a whole control as four separate slot weakenings."""
    assert rule(_inp(cat(exceptions=("x",), verification=("y",), frequency=qty("7", "day")), None)) == ()
    assert rule(_inp(None, cat(exceptions=("x",), verification=("y",)))) == ()
