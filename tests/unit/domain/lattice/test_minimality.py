# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""I14, as a property: the emitted reason set is irreducible.

``ARCHITECTURE.md`` §3.1 requires every refusal to carry *an irreducible reason
set and, where computable, the nearest admissible alternative*.  That is a
property, not an example, so it is proven as one — over a thousand Hypothesis
cases, which is what ``docs/leads/workers.json`` sets as this worker's exit
criterion.

The defining statement, and the reason it matters commercially: **removing any
member of the emitted set changes the verdict.**  Without it, "here is why your
merge was refused" is a dump of everything the differ noticed, a person reading
it cannot tell which item to act on, and the gate gets routed around — which
``ARCHITECTURE.md`` §3.1 says makes it not an invariant at all.
"""

from __future__ import annotations

import pytest
from _lattice_fixtures import AS_OF
from _lattice_strategies import anchor_sets, cats, registries
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st
from mainline_domain.contracts import force
from mainline_domain.lattice import (
    explain,
    is_irredundant,
    minimal_correction_set,
    minimal_unsatisfiable_subset,
    verdict_of,
)

#: A thousand cases is the exit criterion, not a taste.  ``deadline=None`` because
#: the first example pays for the lexicon load (``load_lexicons`` is ``lru_cache``d
#: and reads six committed TOML files) and Hypothesis would otherwise flag that
#: one-off cost as a flaky slow example.
_SETTINGS = settings(
    max_examples=1000,
    deadline=None,
    suppress_health_check=[HealthCheck.too_slow],
)


@_SETTINGS
@given(cats(), cats(), registries())
def test_removing_any_emitted_witness_changes_the_verdict(reference, descendant, registry) -> None:  # type: ignore[no-untyped-def]
    """The property the whole minimiser exists for."""
    decision = explain(reference, descendant, registry, AS_OF)

    assert verdict_of(decision.minimal) == decision.delta
    for i in range(len(decision.minimal)):
        without = [f for j, f in enumerate(decision.minimal) if j != i]
        assert verdict_of(without) != decision.delta, (
            f"witness {decision.minimal[i].rule_id} is redundant: dropping it still "
            f"yields {decision.delta.value}"
        )


@_SETTINGS
@given(cats(), cats(), registries())
def test_a_weaken_verdict_never_reaches_the_database_without_a_witness(
    reference,  # type: ignore[no-untyped-def]
    descendant,  # type: ignore[no-untyped-def]
    registry,  # type: ignore[no-untyped-def]
) -> None:
    """Decision D8, over the whole generated space rather than over one example.

    ``explain`` builds its verdict through
    :func:`mainline_domain.lattice.witness.verdict`, which raises on a witnessless
    lattice weaken — so an input that could produce one would fail here as an
    exception rather than as an assertion.  Both outcomes are a red test; only one
    of them would be confusing, so the invariant is also asserted directly.
    """
    decision = explain(reference, descendant, registry, AS_OF)
    if force(decision.delta) > 0:
        assert decision.verdict.witnesses, decision.delta
        assert decision.verdict.minimal is True
        assert decision.verdict.basis == "lattice"
    assert tuple(f.witness for f in decision.minimal) == decision.verdict.witnesses


@_SETTINGS
@given(cats(), cats(), registries(), anchor_sets(), anchor_sets())
def test_the_property_survives_rule_r8_joining_in(  # type: ignore[no-untyped-def]
    reference, descendant, registry, reference_anchors, descendant_anchors
) -> None:
    """R8 is the only rule whose input is not a CAT slot, so it is the one most
    likely to be wired in a way that breaks the fold.  Same property, anchors on."""
    decision = explain(
        reference,
        descendant,
        registry,
        AS_OF,
        reference_anchors=reference_anchors,
        descendant_anchors=descendant_anchors,
    )
    assert decision.anchors_considered is True
    assert is_irredundant(decision.minimal, decision.delta)


@_SETTINGS
@given(cats(), cats(), registries())
def test_the_repair_set_is_what_would_have_to_change_and_no_more(  # type: ignore[no-untyped-def]
    reference, descendant, registry
) -> None:
    """The *nearest admissible alternative* half of I14.

    Removing the repair set must leave an admissible verdict, and no proper
    subset of it may do — otherwise the list a person is handed contains work
    that would not have helped.
    """
    decision = explain(reference, descendant, registry, AS_OF)
    repair = decision.repair

    if force(decision.delta) == 0:
        assert repair == ()
        return

    removed = {id(f) for f in repair}
    remainder = [f for f in decision.findings if id(f) not in removed]
    assert force(verdict_of(remainder)) == 0

    for i in range(len(repair)):
        smaller = {id(f) for j, f in enumerate(repair) if j != i}
        rest = [f for f in decision.findings if id(f) not in smaller]
        assert force(verdict_of(rest)) > 0, (
            f"{repair[i].rule_id} is in the repair set but removing the rest already admits"
        )


@_SETTINGS
@given(cats(), cats(), registries())
def test_the_minimal_set_and_the_repair_set_answer_different_questions(  # type: ignore[no-untyped-def]
    reference, descendant, registry
) -> None:
    """Both are subsets of the findings, and the MUS is always inside the MCS
    for a refusing verdict — the one reason cited is one of the things that has
    to change.  Stated as an assertion because the two are easy to conflate and a
    refusal that cited the repair set as "the reason" would be overstating its
    case."""
    decision = explain(reference, descendant, registry, AS_OF)
    findings = {id(f) for f in decision.findings}
    assert {id(f) for f in decision.minimal} <= findings
    assert {id(f) for f in decision.repair} <= findings
    if force(decision.delta) > 0:
        assert {id(f) for f in decision.minimal} <= {id(f) for f in decision.repair}


def test_the_minimiser_is_general_and_not_a_special_case_of_the_join() -> None:
    """Hand-built findings whose forcing member is not the first one it tries.

    The greedy pass deletes in reverse declaration order, so an input whose only
    forcing finding sits at the *front* exercises the loop rather than the
    trivially-correct path.
    """
    from mainline_domain.contracts import ControlDelta, DeltaWitness
    from mainline_domain.lattice import RuleFinding

    def finding(rule_id, delta):  # type: ignore[no-untyped-def]
        return RuleFinding(
            rule_id=rule_id,
            delta=delta,
            orderable=True,
            witness=DeltaWitness(rule_id=rule_id, field="f", from_repr="a", to_repr="b", note="n"),
        )

    findings = [
        finding("R1_DEONTIC", ControlDelta.WEAKEN),
        finding("R4_EXCEPTION", ControlDelta.STRENGTHEN),
        finding("R6_VERIFICATION", ControlDelta.STRENGTHEN),
    ]
    minimal = minimal_unsatisfiable_subset(findings)
    assert [f.rule_id for f in minimal] == ["R1_DEONTIC"]
    assert is_irredundant(minimal, ControlDelta.WEAKEN)
    assert [f.rule_id for f in minimal_correction_set(findings)] == ["R1_DEONTIC"]


def test_three_independent_weakenings_cite_one_reason_and_repair_all_three() -> None:
    """The case that makes the MUS/MCS distinction concrete.

    Three rules each force ``weaken`` on their own.  The irreducible *reason* is
    any one of them — the lowest-numbered, so two runs never blame different
    rules — while the *nearest admissible alternative* is all three, because
    undoing one changes nothing.
    """
    from mainline_domain.contracts import ControlDelta, DeltaWitness
    from mainline_domain.lattice import RuleFinding

    def finding(rule_id):  # type: ignore[no-untyped-def]
        return RuleFinding(
            rule_id=rule_id,
            delta=ControlDelta.WEAKEN,
            orderable=True,
            witness=DeltaWitness(rule_id=rule_id, field="f", from_repr="a", to_repr="b", note="n"),
        )

    findings = [finding("R1_DEONTIC"), finding("R4_EXCEPTION"), finding("R7_FREQUENCY")]
    assert [f.rule_id for f in minimal_unsatisfiable_subset(findings)] == ["R1_DEONTIC"]
    assert [f.rule_id for f in minimal_correction_set(findings)] == [
        "R1_DEONTIC",
        "R4_EXCEPTION",
        "R7_FREQUENCY",
    ]


def test_the_minimiser_refuses_a_target_its_input_cannot_reach() -> None:
    from mainline_domain.contracts import ControlDelta
    from mainline_domain.lattice import LatticeError

    with pytest.raises(LatticeError):
        minimal_unsatisfiable_subset([], ControlDelta.WEAKEN)


@given(empty=st.lists(st.sampled_from(("R1_DEONTIC", "R5_QUANTIFIER")), max_size=0))
def test_an_empty_finding_set_is_trivially_minimal(empty: list[str]) -> None:
    from mainline_domain.contracts import ControlDelta

    assert empty == [], "the strategy is max_size=0; a non-empty draw is a Hypothesis bug"
    assert minimal_unsatisfiable_subset(empty) == ()
    assert is_irredundant((), ControlDelta.RESTATE)
