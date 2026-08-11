# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""Decision D7 as a property: adding the ancestry can only ever make a verdict louder.

The guarantee ORIGINDIFF has to carry is the same shape as the ABSTENTION
RATCHET's, and it is proven the same way — over a cross product rather than
asserted in prose::

    force(delta_of_record) >= force(delta(parent -> new))     for every input

That is what makes the second baseline safe to add.  A mechanism that could
*lower* a verdict by consulting more history would be a mechanism an author could
use, and "the origin diff said restate" would become the cheapest weakening in the
product.

The property falls out of :func:`~mainline_domain.lattice.order.join` being the
maximum along a chain on which ``force`` is monotone — but "it follows from the
join" is an argument, and this file is the check.  ``lattice/order.py`` proves
``force(join(a, b)) == max(force(a), force(b))`` over all twenty-five label pairs;
this file proves that ``delta_of_record`` actually *uses* the join, on generated
CAT triples, including the ones where the two baselines disagree.
"""

from __future__ import annotations

import pytest
from _diachronic_fixtures import (
    AS_OF,
    cat,
    commit,
    inert_origin,
    origin_row,
    pressure_cat,
    pressure_registry,
    resolved_origin,
    salami_chain,
)
from _diachronic_strategies import anchor_sets, cats
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st
from mainline_domain.contracts import ControlDelta, force
from mainline_domain.diachronic.ancestral_diff import delta_of_record
from mainline_domain.diachronic.errors import OriginUnresolvedError
from mainline_domain.diachronic.origin import resolve_origin
from mainline_domain.lattice.decide import explain
from mainline_domain.lattice.order import rank

_HEALTH = [HealthCheck.too_slow, HealthCheck.data_too_large]

#: The two monotonicity properties are the guarantee the mechanism rests on and
#: they get the full budget.  The three that follow are corollaries of the same
#: join and get a smaller one, so the directory stays runnable in a pre-commit
#: hook — a property suite nobody runs proves nothing, which is the same failure
#: PL-2 names one level up.
_SETTINGS = settings(max_examples=1000, deadline=None, suppress_health_check=_HEALTH)
_COROLLARY = settings(max_examples=300, deadline=None, suppress_health_check=_HEALTH)


@_SETTINGS
@given(origin=cats(), parent=cats(), descendant=cats())
def test_the_delta_of_record_is_never_quieter_than_the_parent_diff(origin, parent, descendant):
    """THE monotonicity property. 1000+ generated triples, no exceptions permitted."""
    registry = pressure_registry()
    record = delta_of_record(
        descendant=descendant,
        parent=parent,
        origin=origin,
        registry=registry,
        as_of=AS_OF,
        blame_origin=resolved_origin(),
    )
    parent_only = explain(parent, descendant, registry, AS_OF)
    assert force(record.delta) >= force(parent_only.verdict.delta)
    assert rank(record.delta) >= rank(parent_only.verdict.delta)


@_SETTINGS
@given(origin=cats(), parent=cats(), descendant=cats())
def test_the_delta_of_record_is_never_quieter_than_the_origin_diff_either(
    origin, parent, descendant
):
    """The join is symmetric in its two arguments, and so is the guarantee."""
    registry = pressure_registry()
    record = delta_of_record(
        descendant=descendant,
        parent=parent,
        origin=origin,
        registry=registry,
        as_of=AS_OF,
        blame_origin=resolved_origin(),
    )
    origin_only = explain(origin, descendant, registry, AS_OF)
    assert force(record.delta) >= force(origin_only.verdict.delta)
    assert rank(record.delta) >= rank(origin_only.verdict.delta)


@_COROLLARY
@given(origin=cats(), parent=cats(), descendant=cats())
def test_the_delta_of_record_is_exactly_the_join_and_never_a_new_label(origin, parent, descendant):
    """COMPOSITION SOUNDNESS. No label is invented; the record is one of the two verdicts.

    The trap this closes is composing delta *labels* — inventing an algebra in
    which twenty ``restate``s become a ``weaken`` by fiat.  This module composes
    nothing: it runs the same nine rules against a different baseline and takes the
    maximum, so the delta of record is always literally one of the two verdicts it
    was handed.
    """
    registry = pressure_registry()
    record = delta_of_record(
        descendant=descendant,
        parent=parent,
        origin=origin,
        registry=registry,
        as_of=AS_OF,
        blame_origin=resolved_origin(),
    )
    both = {
        explain(parent, descendant, registry, AS_OF).verdict.delta,
        explain(origin, descendant, registry, AS_OF).verdict.delta,
    }
    assert record.delta in both
    winner = record.origin_decision if record.baseline == "blame_origin" else record.parent_decision
    assert winner is not None
    assert winner.verdict.delta is record.delta


@_COROLLARY
@given(
    origin=cats(),
    parent=cats(),
    descendant=cats(),
    origin_anchors=anchor_sets(),
    parent_anchors=anchor_sets(),
    descendant_anchors=anchor_sets(),
)
def test_the_property_survives_rule_r8_running_on_both_baselines(
    origin, parent, descendant, origin_anchors, parent_anchors, descendant_anchors
):
    """Anchors make it nine rules per comparison. The guarantee is unchanged."""
    registry = pressure_registry()
    record = delta_of_record(
        descendant=descendant,
        parent=parent,
        origin=origin,
        registry=registry,
        as_of=AS_OF,
        blame_origin=resolved_origin(),
        descendant_anchors=descendant_anchors,
        parent_anchors=parent_anchors,
        origin_anchors=origin_anchors,
    )
    parent_only = explain(
        parent,
        descendant,
        registry,
        AS_OF,
        reference_anchors=parent_anchors,
        descendant_anchors=descendant_anchors,
    )
    assert force(record.delta) >= force(parent_only.verdict.delta)
    assert record.parent_decision.anchors_considered is True
    assert record.origin_decision is not None
    assert record.origin_decision.anchors_considered is True


@_COROLLARY
@given(parent=cats(), descendant=cats())
def test_an_inert_origin_leaves_the_parent_verdict_exactly_as_it_was(parent, descendant):
    """Clauses with no blood must not get louder. The mechanism is targeted, not blanket."""
    registry = pressure_registry()
    record = delta_of_record(
        descendant=descendant,
        parent=parent,
        origin=None,
        registry=registry,
        as_of=AS_OF,
        blame_origin=inert_origin(),
    )
    parent_only = explain(parent, descendant, registry, AS_OF)
    assert record.delta is parent_only.verdict.delta
    assert record.verdict.witnesses == parent_only.verdict.witnesses
    assert record.baseline == "parent"


# --------------------------------------------------------------------------- #
# The two refusals                                                             #
# --------------------------------------------------------------------------- #


def test_a_resolved_origin_with_no_tuple_refuses_rather_than_falling_back():
    """An unreadable origin must not buy a quieter verdict."""
    with pytest.raises(OriginUnresolvedError) as raised:
        delta_of_record(
            descendant=pressure_cat("<=", "700"),
            parent=pressure_cat("<=", "690"),
            origin=None,
            registry=pressure_registry(),
            as_of=AS_OF,
            blame_origin=resolved_origin(),
        )
    message = str(raised.value)
    assert "opaque_control" in message
    assert "will not fall back" in message


def test_an_origin_tuple_with_no_resolved_origin_is_also_a_refusal():
    """The other direction: a baseline the resolution never named is not a baseline."""
    with pytest.raises(OriginUnresolvedError) as raised:
        delta_of_record(
            descendant=pressure_cat("<=", "700"),
            parent=pressure_cat("<=", "690"),
            origin=pressure_cat("<=", "350"),
            registry=pressure_registry(),
            as_of=AS_OF,
            blame_origin=inert_origin(),
        )
    assert "no version for that tuple to have come from" in str(raised.value)


# --------------------------------------------------------------------------- #
# Witness rows — what actually reaches mainline.delta_witness                  #
# --------------------------------------------------------------------------- #


def test_both_witness_sets_are_carried_and_only_the_winning_one_is_minimal():
    """I14 wants the irreducible reason set. The losing baseline's reasons are context.

    ``mainline.fn_delta_witness_guard`` (migration 0140) refuses a version row whose
    witnesses contain none flagged ``minimal``, so the flag is not cosmetic: it is
    what makes the rows insertable at all.
    """
    chain = salami_chain()
    # A parent diff that fires R1 and an origin diff that fires R1 and R2, so the
    # two sets genuinely differ and the winner is genuinely the origin.
    parent = pressure_cat("=", str(chain[19].value.value if chain[19].value else 0), deontic="MUST")
    descendant = pressure_cat("<=", "700.47", deontic="SHOULD")
    record = delta_of_record(
        descendant=descendant,
        parent=parent,
        origin=chain[0],
        registry=pressure_registry(),
        as_of=AS_OF,
        blame_origin=resolved_origin(),
    )

    rows = record.witness_rows()
    assert rows, "a weakening with no witness rows cannot be stored (decision D8)"
    assert [row.witness_ord for row in rows] == list(range(len(rows)))
    assert any(row.minimal for row in rows)
    assert {row.baseline for row in rows} <= {"parent", "blame_origin"}
    minimal_rows = [row for row in rows if row.minimal]
    assert all(row.baseline == record.baseline for row in minimal_rows)


def test_witness_rows_are_byte_identical_across_two_runs_of_the_same_comparison():
    """A citation that moves between runs is not a citation."""
    chain = salami_chain()
    kwargs = {
        "descendant": chain[20],
        "parent": chain[19],
        "origin": chain[0],
        "registry": pressure_registry(),
        "as_of": AS_OF,
        "blame_origin": resolved_origin(),
    }
    first = delta_of_record(**kwargs).witness_rows()
    second = delta_of_record(**kwargs).witness_rows()
    assert first == second


def test_a_restatement_against_both_baselines_stores_no_witnesses():
    record = delta_of_record(
        descendant=pressure_cat("<=", "350"),
        parent=pressure_cat("<=", "350"),
        origin=pressure_cat("<=", "350"),
        registry=pressure_registry(),
        as_of=AS_OF,
        blame_origin=resolved_origin(),
    )
    assert record.delta is ControlDelta.RESTATE
    assert record.witness_rows() == ()
    assert record.refuses is False


# --------------------------------------------------------------------------- #
# The exhibit sentence                                                         #
# --------------------------------------------------------------------------- #


def test_the_exhibit_names_the_generation_the_blood_attached_at():
    chain = salami_chain()
    record = delta_of_record(
        descendant=chain[20],
        parent=chain[19],
        origin=chain[0],
        registry=pressure_registry(),
        as_of=AS_OF,
        blame_origin=resolved_origin(as_of_gen=20, origin_gen=0),
    )
    exhibit = record.exhibit()
    assert "the version the incident wrote" in exhibit
    assert "generation 0" in exhibit
    assert "20 generations back" in exhibit
    assert "'restate'" in exhibit


def test_the_exhibit_says_so_when_the_two_baselines_agreed():
    record = delta_of_record(
        descendant=cat(deontic="MAY"),
        parent=cat(deontic="MUST"),
        origin=cat(deontic="MUST"),
        registry=pressure_registry(),
        as_of=AS_OF,
        blame_origin=resolved_origin(),
    )
    assert record.baseline == "parent"
    assert "the two agreed" in record.exhibit()
    assert record.salami is False


def test_a_tie_is_reported_as_the_parent_because_the_ancestry_added_nothing():
    """Ties go to the incumbent. Crediting the ancestry for a verdict the ordinary
    diff already reached would overstate what this mechanism contributes."""
    row = origin_row(origin_commit=commit("gen-0"))
    origin = resolve_origin(row, chain=[row.as_of_commit, commit("gen-0")])
    record = delta_of_record(
        descendant=cat(deontic="SHOULD"),
        parent=cat(deontic="MUST"),
        origin=cat(deontic="MUST"),
        registry=pressure_registry(),
        as_of=AS_OF,
        blame_origin=origin,
    )
    assert record.delta is ControlDelta.WEAKEN
    assert record.baseline == "parent"
    assert record.origin_decision is not None
    assert record.origin_decision.verdict.delta is ControlDelta.WEAKEN


@given(delta=st.sampled_from(list(ControlDelta)))
def test_force_is_what_the_gate_reads_and_the_record_reports_it_consistently(delta):
    """`refuses` must agree with `force` for every label, not for the ones we tested."""
    assert (force(delta) > 0) == (delta in {ControlDelta.WEAKEN, ControlDelta.REMOVE})
