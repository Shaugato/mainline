# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""``explain(refusal)`` end to end: declarative first, QuickXplain second, honest third.

Every path produces a payload that validates against the shipped wire schema, and each
test asserts what the payload SAYS rather than that it was produced — a diagnoser that
emits a well-formed payload claiming the wrong thing is worse than one that fails.

The UDF is exercised through a fake connection so the round trip, the rollback and the
translation of a ``P0001`` into ``NotDiagnosable`` are all covered without a database. The
live equivalent is ``test_live_udf.py``, which skips with a reason when no cluster is
configured.
"""

from __future__ import annotations

import json

import pytest

from trappoint_diagnose.binding import CounterBinding, GateBinding, SubjectBinding
from trappoint_diagnose.decompose import OpenObligation, Witnesses
from trappoint_diagnose.diagnose import Diagnoser, ProbeRequest, context_from_exception
from trappoint_diagnose.errors import NotDiagnosable, ProbeBudgetExhausted
from trappoint_diagnose.model import CapabilityGap, RefusalContext, SupplyEvidence
from trappoint_diagnose.quickxplain import BudgetedOracle
from trappoint_diagnose.udf import UdfSource
from trappoint_diagnose.wire import validate_payload

PERMIT = "6f1c7f0e-2b7c-4c0e-9f1b-77a1f0d3c2aa"
OPEN_CHECK = "3d0b6b17-6c3a-4d6b-a0f4-8e5b0a9d1c22"


def binding() -> GateBinding:
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
        ),
    )
    return GateBinding(
        name="MAINLINE",
        schema="mainline",
        spec_version="1.0.0-rc.1",
        profile="mainline",
        subjects=(permit,),
        obligation_relations={"open_blocking": "mainline.blocking_check"},
    )


def context(constraint: str = "gate_closed_when_issued", **overrides) -> RefusalContext:
    fields = {
        "sqlstate": "23514",
        "constraint": constraint,
        "message": "MAINLINE: merge refused — undispositioned precursor in blame ancestry",
        "subject_kind": "permit",
        "subject_id": PERMIT,
        "gate_epoch": 7,
    }
    fields.update(overrides)
    return RefusalContext(**fields)  # type: ignore[arg-type]


# ── the declarative path ───────────────────────────────────────────────────────────


def test_the_declarative_path_emits_a_valid_payload_naming_one_obligation():
    witnesses = Witnesses(
        counter_values={"open_blocking": 1},
        open_obligations=[
            OpenObligation(obligation_id=OPEN_CHECK, severity=5, virulence="blood_fatal")
        ],
        legal_kinds=("applied", "mitigated", "escalated", "emergency_override"),
    )
    payload = Diagnoser(binding()).explain(context(), witnesses=witnesses)
    wire = payload.to_wire()
    validate_payload(wire)

    assert wire["diagnosis"] == "declarative"
    assert wire["probe_calls"] == 0
    assert wire["profile"] == "mainline"
    assert wire["spec_version"] == "1.0.0-rc.1"
    assert [atom["obligation_id"] for atom in wire["mus"]] == [OPEN_CHECK]
    assert wire["naa"]["kind"] == "dispose_obligations"
    assert wire["naa"]["obligation_ids"] == [OPEN_CHECK]
    assert wire["constraint"] == "gate_closed_when_issued"
    assert wire["constraint_source"] == "reported"


def test_with_neither_witnesses_nor_a_source_the_payload_admits_it_knows_nothing():
    payload = Diagnoser(binding()).explain(context())
    wire = payload.to_wire()
    validate_payload(wire)
    assert wire["diagnosis"] == "none"
    assert wire["naa"] is None
    assert wire["naa_reason"] == "not_computable"
    assert wire["mus"][0]["capability"] == "gate_closed_when_issued"


# ── the QuickXplain path ───────────────────────────────────────────────────────────


class Cores:
    """A synthetic oracle: inadmissible exactly when a conflict core is present."""

    def __init__(self, cores):
        self.cores = [frozenset(core) for core in cores]
        self.calls = 0

    def admissible(self, facts):
        self.calls += 1
        present = frozenset(facts)
        return not any(core <= present for core in self.cores)


def probe(cores, candidates, budget=32, alternative_of=None) -> ProbeRequest:
    return ProbeRequest(
        candidates=candidates,
        oracle=BudgetedOracle(Cores(cores), budget=budget),
        atom_of=lambda fact: CapabilityGap(capability=str(fact), detail="probed"),
        alternative_of=alternative_of,
    )


def test_quickxplain_reports_the_conflict_and_what_it_spent():
    request = probe([{"x", "y"}], ["w", "x", "y", "z"])
    payload = Diagnoser(binding()).explain(context("some_composite_check"), probe=request)
    wire = payload.to_wire()
    validate_payload(wire)

    assert wire["diagnosis"] == "quickxplain"
    assert wire["probe_calls"] >= 1
    assert sorted(atom["capability"] for atom in wire["mus"]) == ["x", "y"]
    assert wire["naa"] is None
    assert wire["naa_reason"] == "not_computable"


def test_a_deployment_that_can_compute_an_alternative_gets_a_non_null_one():
    request = probe(
        [{"x"}],
        ["x", "y"],
        alternative_of=lambda conflict: SupplyEvidence(
            required=[str(f) for f in conflict],
            cardinality=len(conflict),
            description="remove the probed fact",
        ),
    )
    wire = Diagnoser(binding()).explain(context("some_composite_check"), probe=request).to_wire()
    validate_payload(wire)
    assert wire["naa"]["kind"] == "supply_evidence"
    assert wire["naa_reason"] is None


def test_budget_exhaustion_degrades_rather_than_blocking():
    request = probe([{"f3", "f9"}], [f"f{i}" for i in range(12)], budget=2)
    wire = Diagnoser(binding()).explain(context("some_composite_check"), probe=request).to_wire()
    validate_payload(wire)

    assert wire["diagnosis"] == "none"
    assert wire["probe_calls"] == 2
    assert wire["naa"] is None
    assert wire["naa_reason"] == "probe_budget_exhausted"
    assert wire["mus"], "a candidate set is still reported; it is simply not called minimal"


def test_a_probe_that_finds_no_conflict_does_not_fabricate_one():
    request = probe([], ["a", "b"])
    wire = Diagnoser(binding()).explain(context("some_composite_check"), probe=request).to_wire()
    validate_payload(wire)
    assert wire["diagnosis"] == "none"
    assert wire["naa_reason"] == "not_computable"


def test_a_covered_refusal_never_reaches_the_probe():
    witnesses = Witnesses(
        counter_values={"open_blocking": 1},
        open_obligations=[OpenObligation(obligation_id=OPEN_CHECK)],
    )
    request = probe([{"x"}], ["x"])
    payload = Diagnoser(binding()).explain(context(), witnesses=witnesses, probe=request)
    assert payload.diagnosis == "declarative"
    assert payload.probe_calls == 0
    assert request.oracle.calls == 0, "the declarative pass covered it; probing would be waste"


def test_the_budget_wrapper_raises_before_the_inner_oracle_is_touched():
    inner = Cores([{"a"}])
    oracle = BudgetedOracle(inner, budget=1)
    oracle.admissible(["a"])
    with pytest.raises(ProbeBudgetExhausted):
        oracle.admissible(["a"])
    assert inner.calls == 1


# ── the UDF client ────────────────────────────────────────────────────────────────


class UdfCursor:
    def __init__(self, answer, raiser=None):
        self.answer = answer
        self.raiser = raiser
        self.closed = False

    def execute(self, query, params=None):
        self.query = query
        self.params = params
        if self.raiser is not None:
            raise self.raiser

    def fetchone(self):
        return (self.answer,)

    def close(self):
        self.closed = True


class UdfConnection:
    def __init__(self, answer=None, raiser=None):
        self.cursor_obj = UdfCursor(answer, raiser)
        self.rolled_back = 0
        self.closed = 0

    def cursor(self):
        return self.cursor_obj

    def rollback(self):
        self.rolled_back += 1

    def close(self):
        self.closed += 1


def udf_answer(**overrides):
    answer = {
        "spec_version": "1.0.0-rc.1",
        "profile": "mainline",
        "class": "gate",
        "constraint": "gate_closed_when_issued",
        "subject_kind": "permit",
        "subject_id": PERMIT,
        "gate_epoch": 7,
        "diagnosis": "declarative",
        "probe_calls": 0,
        "mus": [
            {
                "kind": "obligation",
                "obligation_id": OPEN_CHECK,
                "severity": 5,
                "virulence": "blood_fatal",
                "detail": "open; no live disposition",
            }
        ],
        "naa": {
            "kind": "dispose_obligations",
            "cardinality": 1,
            "obligation_ids": [OPEN_CHECK],
            "legal_kinds": ["applied", "mitigated"],
            "description": "one obligation remains open",
        },
        "naa_reason": None,
    }
    answer.update(overrides)
    return answer


def test_the_udf_source_reads_once_and_rolls_back_whatever_happens():
    connection = UdfConnection(answer=udf_answer())
    payload = Diagnoser(binding()).explain(context(), source=UdfSource(lambda: connection))
    validate_payload(payload.to_wire())
    assert payload.diagnosis == "declarative"
    assert connection.rolled_back == 1, "a read-only path still opened a transaction"
    assert connection.closed == 1
    assert connection.cursor_obj.closed


def test_the_udf_source_accepts_a_json_string_as_well_as_an_object():
    connection = UdfConnection(answer=json.dumps(udf_answer()))
    payload = Diagnoser(binding()).explain(context(), source=UdfSource(lambda: connection))
    assert payload.mus[0].obligation_id == OPEN_CHECK


def test_the_udf_call_binds_its_values_and_names_the_function():
    connection = UdfConnection(answer=udf_answer())
    Diagnoser(binding()).explain(
        context(attempt={"kind": "mechanism_absent"}),
        source=UdfSource(lambda: connection),
    )
    assert "trappoint.explain_refusal" in connection.cursor_obj.query
    assert connection.cursor_obj.params[0] == "permit"
    assert connection.cursor_obj.params[1] == PERMIT
    assert connection.cursor_obj.params[2] == "gate_closed_when_issued"
    assert json.loads(connection.cursor_obj.params[3]) == {"kind": "mechanism_absent"}


def test_a_drift_raise_from_the_udf_is_propagated_verbatim_not_papered_over():
    class Raised(Exception):
        sqlstate = "P0001"

    raised = Raised(
        "TRAPPOINT: projected counter disagrees with the re-derived witness set — refusing on drift"
    )
    connection = UdfConnection(raiser=raised)
    with pytest.raises(NotDiagnosable, match="refusing on drift"):
        Diagnoser(binding()).explain(context(), source=UdfSource(lambda: connection))
    assert connection.rolled_back == 1


def test_a_udf_answer_with_an_empty_reason_set_is_refused():
    connection = UdfConnection(answer=udf_answer(mus=[]))
    with pytest.raises(NotDiagnosable, match="empty reason set"):
        Diagnoser(binding()).explain(context(), source=UdfSource(lambda: connection))


def test_a_udf_answer_carrying_diagnosis_none_degrades_honestly():
    connection = UdfConnection(
        answer=udf_answer(
            diagnosis="none",
            naa=None,
            naa_reason="not_computable",
            mus=[{"kind": "capability_gap", "capability": "weird_constraint"}],
        )
    )
    wire = Diagnoser(binding()).explain(context(), source=UdfSource(lambda: connection)).to_wire()
    validate_payload(wire)
    assert wire["diagnosis"] == "none"
    assert wire["naa_reason"] == "not_computable"


# ── building a context from whatever the caller is holding ─────────────────────────


class GateRefusedLike(Exception):
    """Shaped like `trappoint_core.GateRefused`, which this package does not import."""

    def __init__(self, sqlstate, constraint, message):
        super().__init__(message)
        self.sqlstate = sqlstate
        self.constraint = constraint
        self.message = message


class Diag:
    def __init__(self, constraint_name):
        self.constraint_name = constraint_name


class DriverError(Exception):
    def __init__(self, sqlstate, constraint_name, message):
        super().__init__(message)
        self.sqlstate = sqlstate
        self.diag = Diag(constraint_name)


def test_a_gate_refused_becomes_a_context_with_a_reported_exhibit():
    refused = GateRefusedLike("23514", "gate_closed_when_issued", "MAINLINE: merge refused")
    built = context_from_exception(refused, subject_kind="permit", subject_id=PERMIT, gate_epoch=7)
    assert built.constraint == "gate_closed_when_issued"
    assert built.constraint_source == "reported"


def test_a_driver_error_supplies_the_exhibit_from_its_diagnostics():
    built = context_from_exception(
        DriverError("23503", "fk_clearance", "violates foreign key constraint"),
        subject_kind="permit",
        subject_id=PERMIT,
        gate_epoch=7,
    )
    assert built.constraint == "fk_clearance"
    assert built.constraint_source == "reported"


def test_a_p0001_exhibit_is_parsed_and_marked_as_weakened():
    # diag.constraint_name is empty for P0001, so the exhibit is recovered from the
    # message prefix and the payload must say the diagnosis was weakened.
    built = context_from_exception(
        DriverError("P0001", None, "mainline.fn_check_project: no blame closure for this clause"),
        subject_kind="permit",
        subject_id=PERMIT,
        gate_epoch=7,
    )
    assert built.constraint == "mainline.fn_check_project"
    assert built.constraint_source == "parsed"


def test_an_exception_with_no_sqlstate_cannot_become_a_refusal():
    with pytest.raises(ValueError, match="carries no SQLSTATE"):
        context_from_exception(
            RuntimeError("something went wrong"),
            subject_kind="permit",
            subject_id=PERMIT,
            gate_epoch=1,
        )


def test_a_retry_or_a_denial_cannot_be_dressed_up_as_a_refusal():
    for code in ("40001", "42501"):
        with pytest.raises(ValueError, match="not a REFUSE-class code"):
            context_from_exception(
                GateRefusedLike(code, "whatever", "x"),
                subject_kind="permit",
                subject_id=PERMIT,
                gate_epoch=1,
            )
