# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""``decide`` and ``explain`` end to end: the fold, the fields, and the refusals."""

from __future__ import annotations

import pytest
from _lattice_fixtures import AS_OF, anchors, cat, empty_registry, qty, registry

from mainline_domain.contracts import AnchorClass, ControlDelta
from mainline_domain.lattice import (
    LATTICE_VERSION,
    LatticeError,
    decide,
    explain,
)
from mainline_domain.registry.model import SafeDirection

_PRESSURE = registry(("max_operating_pressure", SafeDirection.LOWER_IS_SAFER, "kPa"))


def test_an_edit_that_changes_nothing_is_a_restatement_with_no_witnesses() -> None:
    same = cat(deontic="MUST", action="isolate", coverage_quantifier="all")
    result = decide(same, same, empty_registry(), AS_OF)
    assert result.delta is ControlDelta.RESTATE
    assert result.witnesses == ()
    assert result.minimal is True


def test_a_strengthening_is_reported_with_its_reason_not_as_a_silence() -> None:
    before = cat(deontic="SHOULD")
    after = cat(deontic="MUST")
    result = decide(before, after, empty_registry(), AS_OF)
    assert result.delta is ControlDelta.STRENGTHEN
    assert [w.rule_id for w in result.witnesses] == ["R1_DEONTIC"]


def test_the_loudest_rule_sets_the_verdict_and_the_quiet_ones_stay_in_the_record() -> None:
    """A verification step added while the deontic falls is still a weakening.

    The join takes force 2 over force 0; the strengthening finding is not lost —
    it is in ``findings`` and would appear in an audit view — but it does not get
    to soften the verdict.  A lattice in which a cosmetic improvement could
    cancel a real downgrade is a lattice that can be gamed by adding a signature
    line.
    """
    before = cat(deontic="MUST", verification=())
    after = cat(deontic="SHOULD", verification=("second_signature",))
    decision = explain(before, after, empty_registry(), AS_OF)

    assert decision.delta is ControlDelta.WEAKEN
    assert {f.rule_id for f in decision.findings} == {"R1_DEONTIC", "R6_VERIFICATION"}
    assert [f.rule_id for f in decision.minimal] == ["R1_DEONTIC"]
    assert [f.rule_id for f in decision.repair] == ["R1_DEONTIC"]


def test_four_independent_weakenings_cite_one_and_repair_four() -> None:
    """The salami edit, in a single commit rather than spread over twenty.

    Deontic down, coverage narrowed, a hedge in, a hold point out.  Any one of
    them is an irreducible reason; all four are the nearest admissible
    alternative.
    """
    before = cat(
        deontic="MUST",
        coverage_quantifier="all",
        exceptions=(),
        verification=("hold_point",),
    )
    after = cat(
        deontic="SHOULD",
        coverage_quantifier="selected",
        exceptions=("where practicable",),
        verification=(),
    )
    decision = explain(before, after, empty_registry(), AS_OF)

    assert decision.delta is ControlDelta.WEAKEN
    assert [f.rule_id for f in decision.minimal] == ["R1_DEONTIC"]
    assert [f.rule_id for f in decision.repair] == [
        "R1_DEONTIC",
        "R4_EXCEPTION",
        "R5_QUANTIFIER",
        "R6_VERIFICATION",
    ]
    assert decision.verdict.witnesses == tuple(f.witness for f in decision.minimal)


def test_a_deleted_control_is_remove_and_outranks_every_weakening() -> None:
    decision = explain(cat(deontic="MUST"), None, empty_registry(), AS_OF)
    assert decision.delta is ControlDelta.REMOVE
    assert [w.rule_id for w in decision.verdict.witnesses] == ["R9_COVERAGE"]
    assert decision.refuses is True


def test_a_new_control_is_introduce_and_the_gate_does_not_react() -> None:
    decision = explain(None, cat(deontic="MUST"), empty_registry(), AS_OF)
    assert decision.delta is ControlDelta.INTRODUCE
    assert decision.refuses is False
    assert decision.repair == ()


def test_two_absent_sides_is_a_caller_bug_and_raises() -> None:
    with pytest.raises(LatticeError) as raised:
        decide(None, None, empty_registry(), AS_OF)
    assert "no edit to judge" in str(raised.value)


def test_the_decision_records_whether_rule_r8_actually_ran() -> None:
    without = explain(cat(), cat(), empty_registry(), AS_OF)
    assert without.anchors_considered is False

    with_anchors = explain(
        cat(),
        cat(),
        empty_registry(),
        AS_OF,
        reference_anchors=anchors((AnchorClass.EQUIPMENT_TAG, "P-101A")),
        descendant_anchors=anchors((AnchorClass.EQUIPMENT_TAG, "P-101A")),
    )
    assert with_anchors.anchors_considered is True


def test_the_decision_records_the_lattice_version_and_the_registry_commit() -> None:
    """Both are what makes a stored verdict re-derivable.

    The lattice version says *which tables decided*; the registry commit says
    *which directions were ratified at the time*.  Neither is reconstructible
    from the verdict alone once either has moved.
    """
    decision = explain(cat(deontic="MUST"), cat(deontic="MAY"), _PRESSURE, AS_OF)
    assert decision.lattice_version == LATTICE_VERSION
    assert decision.registry_commit == AS_OF


def test_an_anchor_drop_alone_weakens_with_no_cat_change_at_all() -> None:
    """R8 is a weakening signal in its own right — no embedding, no lattice slot,
    no oracle.  The two CATs here are identical."""
    identical = cat(deontic="MUST", action="isolate")
    decision = explain(
        identical,
        identical,
        empty_registry(),
        AS_OF,
        reference_anchors=anchors(
            (AnchorClass.EQUIPMENT_TAG, "P-101A"), (AnchorClass.ISOLATION_POINT_ID, "ISO-44")
        ),
        descendant_anchors=anchors((AnchorClass.EQUIPMENT_TAG, "P-101A")),
    )
    assert decision.delta is ControlDelta.WEAKEN
    assert [f.rule_id for f in decision.minimal] == ["R8_ANCHOR"]
    assert "ISO-44" in decision.verdict.witnesses[0].note


def test_a_setpoint_move_against_a_ratified_direction_is_the_headline_case() -> None:
    before = cat(
        deontic="MUST",
        parameter="max_operating_pressure",
        comparator="<=",
        value=qty("1750", "kPa"),
    )
    after = cat(
        deontic="MUST",
        parameter="max_operating_pressure",
        comparator="<=",
        value=qty("2100", "kPa"),
    )
    decision = explain(before, after, _PRESSURE, AS_OF)
    assert decision.delta is ControlDelta.WEAKEN
    assert [w.rule_id for w in decision.verdict.witnesses] == ["R2_SETPOINT"]
    witness = decision.verdict.witnesses[0]
    assert "1750" in witness.from_repr and "2100" in witness.to_repr
    assert "LOWER_IS_SAFER" in witness.note


def test_every_witness_names_the_rule_that_produced_it() -> None:
    """``delta_witness.rule_id`` is what an audit view groups by.  A witness whose
    ``rule_id`` disagreed with its producer would make the table unauditable, and
    ``explain`` refuses to build such a decision."""
    decision = explain(
        cat(deontic="MUST", coverage_quantifier="all", verification=("hold_point",)),
        cat(deontic="MAY", coverage_quantifier="typical", verification=()),
        empty_registry(),
        AS_OF,
    )
    for finding in decision.findings:
        assert finding.witness.rule_id == finding.rule_id
        assert finding.witness.note
        assert finding.witness.field
