# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""The declarative decomposition, including the two scenarios `done_when` names by hand.

Every test here runs with no database. That is the point of having a pure form of the
decomposition at all: the minimality claim is asserted before any schema exists, which is
what `PL-2` demands of a product whose deliverable is a refusal.

Two of these mirror, exactly, the shapes proved against the live v26.2.5 node by the SQL
form of the same algorithm:

* a permit refused by ``gate_closed_when_issued`` with three obligations of which two are
  already dispositioned names EXACTLY the third, and the alternative is to dispose of
  exactly it;
* an ``fk_clearance`` refusal at ``blood_fatal`` / ``mechanism_absent`` lists EXACTLY the
  kinds present in the clearance table at ``blood_fatal``.
"""

from __future__ import annotations

import pytest

from trappoint_diagnose.binding import (
    CounterBinding,
    GateBinding,
    SubjectBinding,
    load_gate_binding,
)
from trappoint_diagnose.decompose import OpenObligation, Witnesses, decompose
from trappoint_diagnose.errors import NotDiagnosable

PERMIT = "6f1c7f0e-2b7c-4c0e-9f1b-77a1f0d3c2aa"
OPEN_CHECK = "3d0b6b17-6c3a-4d6b-a0f4-8e5b0a9d1c22"
BLOOD_FATAL_KINDS = ("applied", "mitigated", "escalated", "emergency_override")


def binding() -> GateBinding:
    """A two-subject binding shaped exactly like MAINLINE's, built in memory."""
    permit = SubjectBinding(
        kind="permit",
        table="permit",
        id_column="permit_id",
        epoch_column="gate_epoch",
        state_column="state",
        completing_state="merged",
        counters=(
            CounterBinding(
                "open_blocking",
                "gate_closed_when_issued",
                "zero_when_complete",
                source="mainline.blocking_check",
            ),
            CounterBinding(
                "open_residue",
                "identity_conserved_when_issued",
                "zero_when_complete",
                source="mainline.identity_residue",
            ),
            CounterBinding(
                "unmet_floor_count",
                "reading_floor_when_issued",
                "offset_allowed",
                offset_column="countersigned_count",
            ),
        ),
    )
    return GateBinding(
        name="MAINLINE",
        schema="mainline",
        spec_version="1.0.0-rc.1",
        profile="mainline",
        subjects=(permit,),
        obligation_relations={
            "open_blocking": "mainline.blocking_check",
            "open_residue": "mainline.identity_residue",
        },
    )


def run(constraint: str, witnesses: Witnesses, **kwargs):
    return decompose(
        binding(),
        subject_kind="permit",
        subject_id=PERMIT,
        gate_epoch=7,
        constraint=constraint,
        witnesses=witnesses,
        **kwargs,
    )


def test_three_obligations_two_dispositioned_names_exactly_the_third():
    # The done_when case. The witness query already excluded the two that carry a live
    # disposition, so what arrives here is the one that does not.
    witnesses = Witnesses(
        counter_values={"open_blocking": 1},
        open_obligations=[
            OpenObligation(
                obligation_id=OPEN_CHECK,
                origin="weaken_over_blood",
                clause_id="b21e9a7c-5d4e-4a3b-9c2d-1e0f8a7b6c5d",
                severity=5,
                virulence="blood_fatal",
            )
        ],
        legal_kinds=BLOOD_FATAL_KINDS,
    )
    result = run("gate_closed_when_issued", witnesses)

    assert result.covered
    assert [atom.kind for atom in result.mus] == ["obligation"]
    assert result.mus[0].obligation_id == OPEN_CHECK
    assert result.naa is not None
    assert result.naa.kind == "dispose_obligations"
    assert list(result.naa.obligation_ids) == [OPEN_CHECK]
    assert result.naa.cardinality == 1
    assert tuple(result.naa.legal_kinds or ()) == BLOOD_FATAL_KINDS
    assert result.naa_reason is None


def test_two_open_obligations_produce_a_two_atom_reason_set():
    witnesses = Witnesses(
        counter_values={"open_blocking": 2},
        open_obligations=[
            OpenObligation(obligation_id="00000000-0000-0000-0000-00000000000a"),
            OpenObligation(obligation_id="00000000-0000-0000-0000-00000000000b"),
        ],
        legal_kinds=("applied",),
    )
    result = run("gate_closed_when_issued", witnesses)
    assert len(result.mus) == 2
    assert result.naa.cardinality == 2


def test_a_counter_that_says_one_with_no_witness_row_is_drift_and_refuses():
    # P2: a projection is enforced, never trusted. If the counter and its source disagree,
    # the honest answer is that they disagree — not a plausible reason set.
    witnesses = Witnesses(counter_values={"open_blocking": 1}, open_obligations=[])
    with pytest.raises(NotDiagnosable, match="refusing on drift"):
        run("gate_closed_when_issued", witnesses)


def test_a_counter_of_zero_means_the_refusal_is_no_longer_reproducible():
    witnesses = Witnesses(counter_values={"open_blocking": 0}, open_obligations=[])
    with pytest.raises(NotDiagnosable, match="not reproducible"):
        run("gate_closed_when_issued", witnesses)


def test_a_vertical_counter_names_the_counter_rather_than_inventing_witness_rows():
    witnesses = Witnesses(counter_values={"open_residue": 3})
    result = run("identity_conserved_when_issued", witnesses)
    assert result.covered
    assert [atom.kind for atom in result.mus] == ["capability_gap"]
    assert result.mus[0].capability == "mainline.permit.open_residue"
    assert result.mus[0].required_value == 0
    assert result.mus[0].observed_value == 3
    assert "mainline.identity_residue" in (result.mus[0].detail or "")
    assert result.naa.kind == "supply_evidence"
    assert result.naa.cardinality == 3


def test_an_offset_allowed_constraint_yields_two_atoms_and_names_the_companion():
    # The CHECK is `unmet_floor_count = 0 OR countersigned_count > 0`, so BOTH facts are
    # needed to refuse and removing EITHER restores admissibility. A one-atom answer would
    # be a subset that is not unsatisfiable.
    witnesses = Witnesses(counter_values={"unmet_floor_count": 2, "countersigned_count": 0})
    result = run("reading_floor_when_issued", witnesses)
    capabilities = [atom.capability for atom in result.mus]
    assert capabilities == [
        "mainline.permit.unmet_floor_count",
        "mainline.permit.countersigned_count",
    ]
    assert result.naa.kind == "supply_evidence"
    assert list(result.naa.required) == ["mainline.permit.countersigned_count"]
    assert result.naa.cardinality == 1


def test_clearance_lattice_lists_exactly_the_kinds_present_at_that_classification():
    # The done_when case: blood_fatal / mechanism_absent. The clearance table holds four
    # kinds at blood_fatal and `mechanism_absent` is not one of them.
    witnesses = Witnesses(
        open_obligations=[
            OpenObligation(obligation_id=OPEN_CHECK, severity=5, virulence="blood_fatal")
        ],
        legal_kinds=BLOOD_FATAL_KINDS,
    )
    result = run("fk_clearance", witnesses, attempt={"kind": "mechanism_absent"})

    assert result.covered
    assert result.naa.kind == "substitute_kind"
    assert tuple(result.naa.legal_kinds) == BLOOD_FATAL_KINDS
    assert result.naa_reason is None
    kinds = [atom.kind for atom in result.mus]
    assert kinds == ["capability_gap", "obligation"]
    assert result.mus[0].capability == "mainline.clearance_legal.mechanism_absent"
    assert result.mus[0].required_value == "blood_fatal"
    # Removing EITHER element restores admissibility — a different classification, or a
    # clearance table that admits the verdict — so both belong in an irreducible set.
    assert len(result.mus) == 2


def test_an_empty_verdict_set_is_the_product_working_not_a_diagnoser_failure():
    witnesses = Witnesses(
        open_obligations=[OpenObligation(obligation_id=OPEN_CHECK, virulence="blood_fatal")],
        legal_kinds=(),
    )
    result = run("fk_clearance", witnesses, attempt={"kind": "accept_residual"})
    assert result.naa is None
    assert result.naa_reason == "no_legal_verdict_exists"
    assert result.covered, "no_legal_verdict_exists is a proven answer, not an unproven one"


def test_a_clearance_refusal_with_no_open_obligation_is_not_computable():
    result = run("fk_clearance", Witnesses(open_obligations=[]))
    assert not result.covered
    assert result.naa is None
    assert result.naa_reason == "not_computable"
    assert result.mus[0].capability == "mainline.clearance_legal"


def test_an_epoch_pin_on_a_completed_subject_offers_a_child():
    witnesses = Witnesses(subject_state="merged")
    result = run("epoch_pin_permit", witnesses, attempt={"gate_epoch": 6})
    assert result.naa.kind == "fork_subject"
    assert result.naa.parent_subject_id == PERMIT
    assert result.mus[0].required_value == 7
    assert result.mus[0].observed_value == 6


def test_an_epoch_pin_on_a_live_subject_says_the_epoch_moved():
    result = run("epoch_pin_permit", Witnesses(subject_state="draft"), attempt={"gate_epoch": 6})
    assert result.naa.kind == "supply_evidence"
    assert list(result.naa.required) == ["gate_epoch"]


def test_an_unknown_constraint_hands_off_rather_than_guessing():
    result = run("some_constraint_nobody_declared", Witnesses())
    assert not result.covered
    assert result.naa is None
    assert result.naa_reason == "not_computable"
    assert "QuickXplain" in (result.mus[0].detail or "")


def test_an_unknown_subject_kind_falls_through_to_the_uncovered_answer():
    result = decompose(
        binding(),
        subject_kind="not_a_subject",
        subject_id=PERMIT,
        gate_epoch=1,
        constraint="gate_closed_when_issued",
        witnesses=Witnesses(),
    )
    assert not result.covered
    assert result.naa_reason == "not_computable"


def test_the_shipped_mainline_binding_loads_and_declares_what_the_gate_needs():
    from pathlib import Path

    root = next(
        (
            p
            for p in Path(__file__).resolve().parents
            if (p / "verticals" / "mainline" / "vertical.toml").is_file()
        ),
        None,
    )
    if root is None:
        pytest.skip("verticals/mainline/vertical.toml is not in this checkout")
    loaded = load_gate_binding(root / "verticals" / "mainline" / "vertical.toml")
    assert loaded.schema == "mainline"
    assert loaded.subject_kinds == ("permit", "change_request")
    counter = loaded.counter_for("permit", "gate_closed_when_issued")
    assert counter is not None
    assert counter.column == "open_blocking"
    floor = loaded.counter_for("permit", "reading_floor_when_issued")
    assert floor is not None
    # The value the SQL render context cannot carry, read straight from the binding.
    assert floor.offset_column == "countersigned_count"
    assert loaded.relation_for("open_blocking") == "mainline.blocking_check"
