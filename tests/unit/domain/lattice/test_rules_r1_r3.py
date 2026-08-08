# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""R1 deontic, R2 setpoint, R3 comparator — a positive and a negative each.

"Negative" here means *the rule stays silent on an edit it must not fire on*.
That direction is the one that gets a rule switched off in production: risk R-A7
says a rule which breaches the nuisance ceiling is rejected, not tuned, so a rule
with only positive tests is a rule nobody can defend when it starts blocking
everything.
"""

from __future__ import annotations

import pytest
from _lattice_fixtures import AS_OF, anchors, cat, empty_registry, qty, registry

from mainline_domain.contracts import AnchorClass, ControlDelta
from mainline_domain.lattice import (
    RuleInput,
    r1_deontic,
    r2_setpoint,
    r3_comparator,
)
from mainline_domain.registry.model import SafeDirection


def _inp(reference, descendant, reg=None):  # type: ignore[no-untyped-def]
    return RuleInput(
        reference=reference,
        descendant=descendant,
        registry=reg if reg is not None else empty_registry(),
        reference_anchors=None,
        descendant_anchors=None,
    )


# ── R1 ────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("before", "after"),
    [("MUST", "SHOULD"), ("MUST", "MAY"), ("SHOULD", "MAY"), ("MAY", "ABSENT"), ("MUST", "ABSENT")],
)
def test_r1_positive_every_step_down_the_ladder_weakens(before: str, after: str) -> None:
    findings = r1_deontic(_inp(cat(deontic=before), cat(deontic=after)))
    assert [f.delta for f in findings] == [ControlDelta.WEAKEN]
    assert findings[0].orderable is True
    assert findings[0].witness.from_repr == before
    assert findings[0].witness.to_repr == after


@pytest.mark.parametrize(("before", "after"), [("SHOULD", "MUST"), ("ABSENT", "MAY")])
def test_r1_the_same_step_upwards_strengthens(before: str, after: str) -> None:
    findings = r1_deontic(_inp(cat(deontic=before), cat(deontic=after)))
    assert [f.delta for f in findings] == [ControlDelta.STRENGTHEN]


@pytest.mark.parametrize(("before", "after"), [("MUST", "MUST_NOT"), ("SHOULD_NOT", "SHOULD")])
def test_r1_a_polarity_inversion_weakens_in_both_directions_and_is_not_orderable(
    before: str, after: str
) -> None:
    """One of exactly two non-dual cells in the lattice.  See rules.py on R1."""
    findings = r1_deontic(_inp(cat(deontic=before), cat(deontic=after)))
    assert [f.delta for f in findings] == [ControlDelta.WEAKEN]
    assert findings[0].orderable is False
    assert "polarity" in findings[0].witness.note


def test_r1_negative_a_prohibition_restated_at_the_same_rung_is_silent() -> None:
    """``MUST_NOT`` → ``MUST_NOT``: same rung, same polarity, nothing to say."""
    assert r1_deontic(_inp(cat(deontic="MUST_NOT"), cat(deontic="MUST_NOT"))) == ()


def test_r1_negative_a_reword_that_leaves_the_deontic_alone_is_silent() -> None:
    """Every other slot moves; R1 owns one slot and must not react to the others."""
    before = cat(deontic="MUST", action="isolate", object_class="vessel", actor="operator")
    after = cat(deontic="MUST", action="de-energise", object_class="switchboard", actor="fitter")
    assert r1_deontic(_inp(before, after)) == ()


def test_r1_an_unknown_label_fails_closed_rather_than_raising() -> None:
    """A broken extractor must not be able to produce a quiet ``restate``.

    Constructed by hand rather than through the fixture, because ``validate_cat``
    correctly refuses this tuple — which is the point: the only way to reach this
    branch is for something upstream to have skipped validation, and that is
    exactly when a fail-closed default earns its keep.
    """
    from mainline_domain.cat.schema import EMPTY_CAT
    from dataclasses import replace

    broken = replace(EMPTY_CAT, deontic="OUGHT")
    findings = r1_deontic(_inp(cat(deontic="MUST"), broken))
    assert [f.delta for f in findings] == [ControlDelta.WEAKEN]
    assert findings[0].orderable is False


# ── R2 ────────────────────────────────────────────────────────────────────────

_PRESSURE = registry(("max_operating_pressure", SafeDirection.LOWER_IS_SAFER, "kPa"))
_PPE = registry(("min_ppe_level", SafeDirection.HIGHER_IS_SAFER, "dimensionless"))


def test_r2_positive_a_pressure_cap_raised_on_a_lower_is_safer_parameter_weakens() -> None:
    before = cat(parameter="max_operating_pressure", comparator="<=", value=qty("1750", "kPa"))
    after = cat(parameter="max_operating_pressure", comparator="<=", value=qty("2100", "kPa"))
    findings = r2_setpoint(_inp(before, after, _PRESSURE))
    assert [f.delta for f in findings] == [ControlDelta.WEAKEN]
    assert findings[0].orderable is True
    assert findings[0].witness.field == "value"
    assert "1750" in findings[0].witness.from_repr


def test_r2_the_same_move_downwards_strengthens() -> None:
    before = cat(parameter="max_operating_pressure", comparator="<=", value=qty("2100", "kPa"))
    after = cat(parameter="max_operating_pressure", comparator="<=", value=qty("1750", "kPa"))
    assert [f.delta for f in r2_setpoint(_inp(before, after, _PRESSURE))] == [
        ControlDelta.STRENGTHEN
    ]


def test_r2_direction_is_read_from_the_registry_and_not_from_the_sign() -> None:
    """The identical arithmetic move gives the opposite verdict on the other direction."""
    before = cat(parameter="min_ppe_level", comparator=">=", value=qty("3", "dimensionless"))
    after = cat(parameter="min_ppe_level", comparator=">=", value=qty("2", "dimensionless"))
    assert [f.delta for f in r2_setpoint(_inp(before, after, _PPE))] == [ControlDelta.WEAKEN]


def test_r2_an_unratified_parameter_abstains_to_weaken_and_says_so() -> None:
    """Decision D6, reaching the lattice.  The finding is not orderable."""
    before = cat(parameter="vent_line_backpressure", comparator="<=", value=qty("10", "kPa"))
    after = cat(parameter="vent_line_backpressure", comparator="<=", value=qty("40", "kPa"))
    findings = r2_setpoint(_inp(before, after, empty_registry()))
    assert [f.delta for f in findings] == [ControlDelta.WEAKEN]
    assert findings[0].orderable is False
    assert "abstained" in findings[0].witness.note


def test_r2_negative_an_unratified_parameter_that_did_not_move_is_silent() -> None:
    """The guard that keeps D6 pointed at a *move* rather than at mere existence.

    Without it, re-typesetting any clause whose parameter is not yet in DIRECTRIX
    would report ``weaken`` on an edit in which nothing moved — the nuisance
    ceiling, breached by a bug rather than by the rule.
    """
    same = cat(parameter="vent_line_backpressure", comparator="<=", value=qty("10", "kPa"))
    reworded = cat(
        parameter="vent_line_backpressure",
        comparator="<=",
        value=qty("10", "kPa"),
        actor="fitter",
    )
    assert r2_setpoint(_inp(same, reworded, empty_registry())) == ()


def test_r2_negative_a_clause_that_asserts_no_setpoint_at_all_is_silent() -> None:
    before = cat(deontic="MUST", action="isolate")
    after = cat(deontic="SHOULD", action="isolate")
    assert r2_setpoint(_inp(before, after, empty_registry())) == ()


def test_r2_negative_a_comparator_family_change_belongs_to_r3() -> None:
    """One edit, one witness.  R2 stands down so R3 can own the relation change."""
    before = cat(parameter="max_operating_pressure", comparator="=", value=qty("1750", "kPa"))
    after = cat(parameter="max_operating_pressure", comparator="~", value=qty("1750", "kPa"))
    assert r2_setpoint(_inp(before, after, _PRESSURE)) == ()
    assert [f.delta for f in r3_comparator(_inp(before, after, _PRESSURE))] == [
        ControlDelta.WEAKEN
    ]


def test_r2_a_gauge_to_absolute_comparison_reaches_the_gate_as_a_weakening() -> None:
    """Decision D5: the conversion that would invert the verdict is never performed."""
    gauge = registry(("max_operating_pressure", SafeDirection.LOWER_IS_SAFER, "kPag"))
    before = cat(parameter="max_operating_pressure", comparator="<=", value=qty("50", "psig"))
    after = cat(parameter="max_operating_pressure", comparator="<=", value=qty("400", "kPa"))
    findings = r2_setpoint(_inp(before, after, gauge))
    assert [f.delta for f in findings] == [ControlDelta.WEAKEN]
    assert findings[0].orderable is False


def test_r2_a_replaced_parameter_is_unrankable_and_fails_closed() -> None:
    before = cat(parameter="max_operating_pressure", comparator="<=", value=qty("1750", "kPa"))
    after = cat(parameter="max_operating_temperature", comparator="<=", value=qty("80", "degC"))
    findings = r2_setpoint(_inp(before, after, _PRESSURE))
    assert [f.delta for f in findings] == [ControlDelta.WEAKEN]
    assert findings[0].orderable is False
    assert findings[0].witness.field == "parameter"


def test_r2_a_tolerance_band_that_widened_weakens_through_the_tolerance_path() -> None:
    torque = registry(("bolt_torque", SafeDirection.TIGHTER_TOLERANCE_IS_SAFER, "N*m"))
    before = cat(parameter="bolt_torque", comparator="+/-", value=qty("2", "N*m"))
    after = cat(parameter="bolt_torque", comparator="+/-", value=qty("6", "N*m"))
    findings = r2_setpoint(_inp(before, after, torque))
    assert [f.delta for f in findings] == [ControlDelta.WEAKEN]
    assert findings[0].witness.field == "value(tolerance)"


# ── R3 ────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("before", "after"),
    [("<=", ""), ("=", "~"), ("=", "+/-"), (">=", ">"), ("<=", "<"), ("range", "~")],
)
def test_r3_positive_the_transition_table_weakens_where_it_says_it_does(
    before: str, after: str
) -> None:
    findings = r3_comparator(_inp(_with_comparator(before), _with_comparator(after)))
    assert [f.delta for f in findings] == [ControlDelta.WEAKEN]
    assert findings[0].orderable is True


@pytest.mark.parametrize(
    ("before", "after"),
    [("", "<="), ("~", "="), ("+/-", "="), (">", ">="), ("<", "<="), ("~", "range")],
)
def test_r3_the_reverse_of_every_weakening_cell_strengthens(before: str, after: str) -> None:
    findings = r3_comparator(_inp(_with_comparator(before), _with_comparator(after)))
    assert [f.delta for f in findings] == [ControlDelta.STRENGTHEN]


@pytest.mark.parametrize(("before", "after"), [("<=", ">="), (">", "<"), ("<", ">=")])
def test_r3_a_bound_inversion_weakens_both_ways(before: str, after: str) -> None:
    forward = r3_comparator(_inp(_with_comparator(before), _with_comparator(after)))
    backward = r3_comparator(_inp(_with_comparator(after), _with_comparator(before)))
    assert [f.delta for f in forward] == [ControlDelta.WEAKEN]
    assert [f.delta for f in backward] == [ControlDelta.WEAKEN]
    assert forward[0].orderable is False and backward[0].orderable is False


def test_r3_negative_an_unchanged_comparator_is_silent() -> None:
    assert r3_comparator(_inp(_with_comparator("<="), _with_comparator("<="))) == ()


@pytest.mark.parametrize(("before", "after"), [("=", "<="), ("<=", "="), ("=", ">="), (">=", "=")])
def test_r3_negative_the_deliberately_silent_cells_stay_silent_in_both_directions(
    before: str, after: str
) -> None:
    """``exactly 50 kPa`` ↔ ``at most 50 kPa`` is the commonest restatement there is.

    Firing on it would breach the nuisance ceiling (risk R-A7), and the silence is
    symmetric so the duality property still holds across these cells.
    """
    assert r3_comparator(_inp(_with_comparator(before), _with_comparator(after))) == ()


def _with_comparator(token: str):  # type: ignore[no-untyped-def]
    """A CAT carrying only a comparator.  ``''`` may not carry a value (schema §)."""
    if token == "":
        return cat(parameter="max_operating_pressure", comparator="")
    return cat(parameter="max_operating_pressure", comparator=token, value=qty("1750", "kPa"))


def test_r8_needs_anchors_and_says_when_it_did_not_get_them() -> None:
    """Sanity for the shared ``_inp`` helper: R8 is silent without anchor sets."""
    from mainline_domain.lattice import r8_anchor

    assert r8_anchor(_inp(cat(), cat())) == ()
    with_anchors = RuleInput(
        reference=cat(),
        descendant=cat(),
        registry=empty_registry(),
        reference_anchors=anchors((AnchorClass.EQUIPMENT_TAG, "P-101A")),
        descendant_anchors=anchors(),
    )
    assert [f.delta for f in r8_anchor(with_anchors)] == [ControlDelta.WEAKEN]


def test_the_as_of_guard_is_not_bypassable_by_a_stale_registry() -> None:
    """A registry read at another commit is refused, not silently used."""
    from mainline_domain.lattice import LatticeError, decide

    stale = registry(
        ("max_operating_pressure", SafeDirection.LOWER_IS_SAFER, "kPa"),
        as_of=b"\x00" * 32,
    )
    with pytest.raises(LatticeError) as raised:
        decide(cat(deontic="MUST"), cat(deontic="SHOULD"), stale, AS_OF)
    assert "retro-tuning" in str(raised.value)
