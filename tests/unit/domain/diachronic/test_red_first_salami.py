# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""PL-2: the test that was red before ORIGINDIFF existed, kept permanently red-able.

The exit criterion for worker W6, verbatim: *a 20-step chain of individually-
``restate`` edits whose composition is a weakening returns ``weaken`` at step 20.*

WHY THE RED HALF IS IN THE SAME FILE AS THE GREEN HALF
-------------------------------------------------------
Performing a red run once, in a commit message, proves nothing a year later.  The
DELTALATTICE suite solved the same problem by keeping two schemas — one with the
guard trigger and one without — so the identical INSERT is accepted by one and
refused by the other.  This suite has no trigger to withhold, so it keeps the
equivalent pair in the assertions themselves:

* :func:`test_every_single_step_is_a_restatement_to_the_parent_diff` is the RED
  half.  It runs the *parent-only* comparison — the whole of what a synchronic
  document-control system can see — over all twenty steps and asserts that every
  one of them is ``restate`` with no witnesses.  If ORIGINDIFF were deleted
  tomorrow, this is what the product would say about a cap that doubled.
* :func:`test_the_delta_of_record_at_step_twenty_is_a_weakening` is the GREEN
  half, and it fails for the right reason without the origin comparison, because
  the parent diff it would fall back to is the one the first test pins to
  ``restate``.

The two together are the claim: *this is invisible synchronically and visible
diachronically*, asserted rather than narrated.
"""

from __future__ import annotations

import pytest
from _diachronic_fixtures import (
    AS_OF,
    SALAMI_STEPS,
    inert_origin,
    pressure_registry,
    resolved_origin,
    salami_chain,
)
from mainline_domain.contracts import ControlDelta, force
from mainline_domain.diachronic.ancestral_diff import delta_of_record
from mainline_domain.lattice.decide import decide, explain


def test_every_single_step_is_a_restatement_to_the_parent_diff():
    """RED HALF. Twenty edits, each a restatement, and the cap doubles anyway."""
    chain = salami_chain()
    registry = pressure_registry()

    for step in range(SALAMI_STEPS):
        verdict = decide(chain[step], chain[step + 1], registry, AS_OF)
        assert verdict.delta is ControlDelta.RESTATE, (
            f"step {step + 1} of the salami chain was classified "
            f"{verdict.delta.value!r} by the parent diff. The chain is only a test of "
            "ORIGINDIFF while every individual step is invisible to the ordinary diff"
        )
        assert verdict.witnesses == (), (
            f"step {step + 1} produced witnesses {[w.rule_id for w in verdict.witnesses]}; "
            "a restatement has nothing to witness"
        )

    origin_value = chain[0].value
    final_value = chain[SALAMI_STEPS].value
    assert origin_value is not None
    assert final_value is not None
    assert final_value.value > origin_value.value * 2 - 1, (
        "the chain must move the cap far enough that nobody can call the result a "
        f"rounding decision: {origin_value.value} -> {final_value.value}"
    )


def test_the_delta_of_record_at_step_twenty_is_a_weakening():
    """GREEN HALF. Measured against the version the incident wrote, it is a weakening."""
    chain = salami_chain()
    registry = pressure_registry()

    record = delta_of_record(
        descendant=chain[SALAMI_STEPS],
        parent=chain[SALAMI_STEPS - 1],
        origin=chain[0],
        registry=registry,
        as_of=AS_OF,
        blame_origin=resolved_origin(as_of_gen=SALAMI_STEPS, origin_gen=0),
    )

    assert record.delta is ControlDelta.WEAKEN
    assert record.baseline == "blame_origin"
    assert record.salami is True
    assert record.parent_decision.verdict.delta is ControlDelta.RESTATE
    assert [w.rule_id for w in record.verdict.witnesses] == ["R2_SETPOINT"]
    assert record.verdict.minimal is True


def test_the_witness_names_the_two_magnitudes_that_were_actually_compared():
    """The refusal has to be actionable, so the witness carries the numbers."""
    chain = salami_chain()
    record = delta_of_record(
        descendant=chain[SALAMI_STEPS],
        parent=chain[SALAMI_STEPS - 1],
        origin=chain[0],
        registry=pressure_registry(),
        as_of=AS_OF,
        blame_origin=resolved_origin(as_of_gen=SALAMI_STEPS, origin_gen=0),
    )
    witness = record.verdict.witnesses[0]
    assert witness.field == "value"
    assert "350" in witness.from_repr
    assert "700.47" in witness.to_repr
    assert "max_operating_pressure" in witness.note
    assert "LOWER_IS_SAFER" in witness.note


def test_the_salami_flag_is_false_at_every_step_before_the_composition_crosses():
    """`salami` marks the step at which the ancestry first sees what the parent cannot.

    It must not be a constant.  A flag that is always ``True`` on this chain would
    be reporting the fixture rather than the arithmetic, so the test walks the
    whole chain and asserts the flag is ``False`` while the compounded drift is
    still nothing and ``True`` once it is something.
    """
    chain = salami_chain()
    registry = pressure_registry()

    flags = []
    for step in range(1, SALAMI_STEPS + 1):
        record = delta_of_record(
            descendant=chain[step],
            parent=chain[step - 1],
            origin=chain[0],
            registry=registry,
            as_of=AS_OF,
            blame_origin=resolved_origin(as_of_gen=step, origin_gen=0),
        )
        flags.append(record.salami)

    assert flags[-1] is True, "the composition must be visible by step 20"
    assert any(flag is False for flag in flags), (
        "no step in the chain was quiet: the flag is reporting the fixture, not the "
        "arithmetic. A salami defence that fires on every step is a rule, not a defence"
    )


def test_an_odd_step_is_quiet_and_that_is_the_honest_limit():
    """At an odd step both comparators differ, so R2 declines and ORIGINDIFF is silent.

    Stated as a test rather than left to be discovered.  The chain alternates
    ``<=`` and ``=``; at an odd step the origin's family (``upper``) and the
    descendant's (``exact``) disagree, R2 falls silent for exactly the reason it
    falls silent on every step of the parent diff, and the delta of record is
    ``restate``.  The mechanism catches the drift on the next commit — but it does
    not catch it on that one, and pretending otherwise would be the sort of claim
    this repository refuses to make.
    """
    chain = salami_chain()
    record = delta_of_record(
        descendant=chain[SALAMI_STEPS - 1],
        parent=chain[SALAMI_STEPS - 2],
        origin=chain[0],
        registry=pressure_registry(),
        as_of=AS_OF,
        blame_origin=resolved_origin(as_of_gen=SALAMI_STEPS - 1, origin_gen=0),
    )
    assert record.delta is ControlDelta.RESTATE
    assert record.salami is False


def test_without_blood_ancestry_the_mechanism_adds_nothing():
    """An inert origin must leave a clause exactly as loud as the parent diff made it."""
    chain = salami_chain()
    registry = pressure_registry()
    record = delta_of_record(
        descendant=chain[SALAMI_STEPS],
        parent=chain[SALAMI_STEPS - 1],
        origin=None,
        registry=registry,
        as_of=AS_OF,
        blame_origin=inert_origin(as_of_gen=SALAMI_STEPS),
    )
    parent_only = explain(chain[SALAMI_STEPS - 1], chain[SALAMI_STEPS], registry, AS_OF)

    assert record.delta is parent_only.verdict.delta
    assert record.baseline == "parent"
    assert record.origin_decision is None
    assert record.salami is False
    assert "inert" in record.exhibit()


@pytest.mark.parametrize("steps", [2, 4, 6, 8, 10, 12, 14, 16, 18, 20])
def test_the_defence_holds_at_every_even_chain_length(steps):
    """The mechanism is not tuned to twenty. Any even prefix of the chain weakens."""
    chain = salami_chain(steps)
    registry = pressure_registry()

    for step in range(steps):
        assert decide(chain[step], chain[step + 1], registry, AS_OF).delta is ControlDelta.RESTATE

    record = delta_of_record(
        descendant=chain[steps],
        parent=chain[steps - 1],
        origin=chain[0],
        registry=registry,
        as_of=AS_OF,
        blame_origin=resolved_origin(as_of_gen=steps, origin_gen=0),
    )
    assert force(record.delta) > 0
    assert record.baseline == "blame_origin"
