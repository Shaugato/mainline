# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""Invariant I15 at the emitter, and the ledger row that is derived rather than supplied.

**The allegation firewall.** No substrate artefact may carry a threshold, score or flag
characterising a named human's conduct. The wire schema already refuses an unknown key on
every atom, which closes the structural route; this module tests the other one — the same
words arriving inside a permitted free-text field. The check is deliberately narrow: it
refuses a measurement word in a KEY outright, and in a VALUE only when the value also
names a person-shaped subject, because "the reading floor was unmet" must stay sayable.

**The ledger row.** Every column is derived from the payload in one function, and the
table's own CHECKs compare the two again at write time. These tests assert the derivation;
the migration asserts the agreement. Neither is sufficient alone, and that is the point.
"""

from __future__ import annotations

import json

import pytest

from trappoint_diagnose.errors import PayloadInvalid
from trappoint_diagnose.ledger import INSERT_TEMPLATE, ledger_row, record_refusal
from trappoint_diagnose.model import (
    CapabilityGap,
    DisposeObligations,
    Obligation,
    RefusalContext,
)
from trappoint_diagnose.wire import (
    FORBIDDEN_MEASURE_WORDS,
    assert_no_person_metric,
    build_payload,
)

PERMIT = "6f1c7f0e-2b7c-4c0e-9f1b-77a1f0d3c2aa"
OPEN_CHECK = "3d0b6b17-6c3a-4d6b-a0f4-8e5b0a9d1c22"


def context() -> RefusalContext:
    return RefusalContext(
        sqlstate="23514",
        constraint="gate_closed_when_issued",
        message="MAINLINE: merge refused — undispositioned precursor in blame ancestry",
        subject_kind="permit",
        subject_id=PERMIT,
        gate_epoch=7,
    )


def payload(**overrides):
    fields = {
        "spec_version": "1.0.0-rc.1",
        "diagnosis": "declarative",
        "mus": [Obligation(obligation_id=OPEN_CHECK, severity=5, virulence="blood_fatal")],
        "naa": DisposeObligations(
            obligation_ids=[OPEN_CHECK],
            cardinality=1,
            description="one obligation remains open",
        ),
        "naa_reason": None,
        "profile": "mainline",
    }
    fields.update(overrides)
    return build_payload(context(), **fields)


# ── I15 ────────────────────────────────────────────────────────────────────────────


def test_the_word_list_is_about_measurements_and_not_about_facts():
    # `signer_sub` is a FACT — who signed — and must stay sayable. The moment a fact
    # appears in this list the firewall starts refusing evidence.
    assert "signer_sub" not in FORBIDDEN_MEASURE_WORDS
    assert "signer" not in FORBIDDEN_MEASURE_WORDS
    assert {"score", "rating", "percentile"} <= FORBIDDEN_MEASURE_WORDS


def test_a_measurement_key_is_refused_wherever_it_appears():
    with pytest.raises(PayloadInvalid, match="names a measurement"):
        assert_no_person_metric({"ext": {"signer_score": 0.4}})


def test_a_measurement_attached_to_a_person_in_free_text_is_refused():
    with pytest.raises(PayloadInvalid, match="attaches a measurement to a person"):
        assert_no_person_metric(
            {
                "mus": [
                    {
                        "kind": "capability_gap",
                        "capability": "x",
                        "detail": "the signer's attentiveness was rated low",
                    }
                ]
            }
        )


def test_a_measurement_word_about_a_thing_is_not_refused():
    # The firewall protects PEOPLE. A refusal about a reading floor, a threshold on a
    # counter, or a rating of a mechanism is exactly the evidence this system exists to
    # produce, and a check that refused it would be a check people disable.
    assert_no_person_metric(
        {
            "mus": [
                {
                    "kind": "capability_gap",
                    "capability": "permit.unmet_floor_count",
                    "detail": "the reading floor was unmet and no countersignature is present",
                }
            ]
        }
    )


def test_signer_identity_as_a_fact_survives_the_firewall():
    assert_no_person_metric(
        {
            "ext": {"signer_sub": "auth0|1234"},
            "mus": [{"kind": "obligation", "obligation_id": OPEN_CHECK}],
        }
    )


def test_the_emitter_refuses_a_payload_carrying_a_person_metric():
    with pytest.raises(PayloadInvalid):
        payload(ext={"crew_reliability_score": 0.2})


def test_an_atom_cannot_carry_an_extra_field_at_all():
    # The structural half of I15: the atom dataclasses are closed, so the field cannot
    # even be constructed, let alone emitted.
    with pytest.raises(TypeError):
        CapabilityGap(capability="x", signer_percentile=0.9)  # type: ignore[call-arg]


# ── the ledger row ─────────────────────────────────────────────────────────────────


def test_every_ledger_column_is_derived_from_the_payload():
    written = payload()
    row = ledger_row(written, recorded_by="mainline-gate-svc")
    wire = written.to_wire()

    assert row["refusal_id"] == wire["refusal_id"]
    assert row["constraint_name"] == wire["constraint"], "the exhibit is stored verbatim"
    assert row["sqlstate"] == wire["sqlstate"]
    assert row["diagnosis"] == wire["diagnosis"]
    assert row["probe_calls"] == wire["probe_calls"]
    assert row["mus_cardinality"] == len(wire["mus"])
    assert row["naa_kind"] == wire["naa"]["kind"]
    assert row["naa_reason"] is None
    assert row["subject_id"] == PERMIT
    assert row["recorded_by"] == "mainline-gate-svc"
    assert json.loads(row["payload"]) == wire


def test_a_null_alternative_stores_its_reason_and_no_kind():
    written = payload(
        diagnosis="none",
        mus=[CapabilityGap(capability="weird_constraint")],
        naa=None,
        naa_reason="probe_budget_exhausted",
        probe_calls=32,
    )
    row = ledger_row(written, recorded_by="conformance")
    assert row["naa_kind"] is None
    assert row["naa_reason"] == "probe_budget_exhausted"
    assert row["probe_calls"] == 32


def test_an_unattributed_row_is_refused():
    with pytest.raises(ValueError, match="unattributed"):
        ledger_row(payload(), recorded_by="")


def test_the_stored_payload_is_canonical_bytes():
    # Sorted keys and no incidental whitespace: the JSONB column is compared against the
    # scalar columns by CHECK, and two encodings of one payload make a diff that is not a
    # difference.
    row = ledger_row(payload(), recorded_by="x")
    assert row["payload"] == json.dumps(
        json.loads(row["payload"]), sort_keys=True, separators=(",", ":")
    )


class RecordingCursor:
    def __init__(self):
        self.statements = []
        self.closed = False

    def execute(self, query, params=None):
        self.statements.append((query, params))

    def fetchone(self):
        return None

    def close(self):
        self.closed = True


class RecordingConnection:
    def __init__(self):
        self.cursor_obj = RecordingCursor()

    def cursor(self):
        return self.cursor_obj

    def rollback(self):
        raise AssertionError("record_refusal must not manage the caller's transaction")

    def close(self):
        raise AssertionError("record_refusal must not close the caller's connection")


def test_record_refusal_writes_one_insert_and_leaves_the_transaction_to_the_caller():
    connection = RecordingConnection()
    row = record_refusal(connection, payload(), schema="mainline", recorded_by="svc")
    ((statement, params),) = connection.cursor_obj.statements
    assert statement.strip().startswith("INSERT INTO mainline.refusal_ledger")
    assert params == row
    assert connection.cursor_obj.closed
    assert "UPDATE" not in statement.upper()
    assert "UPSERT" not in statement.upper()


def test_a_schema_name_that_is_not_a_plain_identifier_is_refused():
    # The schema is interpolated because it cannot be a bind parameter. It comes from the
    # binding, and it is checked rather than trusted.
    with pytest.raises(ValueError, match="not a plain schema name"):
        record_refusal(
            RecordingConnection(), payload(), schema="a; DROP TABLE b --", recorded_by="svc"
        )


def test_the_insert_names_every_column_the_migration_declares():
    for column in (
        "refusal_id",
        "observed_at",
        "spec_version",
        "profile",
        "sqlstate",
        "constraint_name",
        "constraint_source",
        "message",
        "subject_kind",
        "subject_id",
        "gate_epoch",
        "diagnosis",
        "probe_calls",
        "mus_cardinality",
        "naa_kind",
        "naa_reason",
        "payload",
        "recorded_by",
    ):
        assert f"%({column})s" in INSERT_TEMPLATE
