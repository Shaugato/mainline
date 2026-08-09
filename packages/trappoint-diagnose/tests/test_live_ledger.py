# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""The refusal ledger against a real cluster: append-only, and it refuses a lying row.

Migrations ``0071c`` (the table), ``0119b`` (the guard) and ``0133`` (the trigger) make
four claims. Each is asserted here by attempting the illegal write and reading back the
exact SQLSTATE and, where a constraint produced it, the exact constraint name — because a
test asserting only that "an exception was raised" is worthless in a product whose
deliverable is the diagnosis.

1. UPDATE and DELETE are refused, unconditionally, with ``P0001``.
2. A payload whose reason set is not an array of modelled facts is refused by the guard.
3. An atom carrying a key outside the closed vocabulary is refused — invariant I15
   enforced structurally at the last place the bytes pass through.
4. A row whose scalar columns disagree with its payload is refused by a plain-column
   CHECK, and the CHECK's name says which field disagreed.

Skips with a reason when ``TRAPPOINT_DSN`` is unset. A test that passes by absence is
worse than one that is missing.
"""

from __future__ import annotations

import json
import os
import uuid

import pytest

from trappoint_diagnose.ledger import ledger_row, record_refusal
from trappoint_diagnose.model import DisposeObligations, Obligation, RefusalContext
from trappoint_diagnose.wire import build_payload

pytestmark = pytest.mark.requires_cluster

DSN_VAR = "TRAPPOINT_DSN"
SCHEMA = os.environ.get("TRAPPOINT_SCHEMA", "mainline")
OPEN_CHECK = "3d0b6b17-6c3a-4d6b-a0f4-8e5b0a9d1c22"


@pytest.fixture(scope="module")
def connect():
    dsn = os.environ.get(DSN_VAR)
    if not dsn:
        pytest.skip(f"{DSN_VAR} is unset; this case needs a migrated cluster")
    psycopg = pytest.importorskip("psycopg", reason="install trappoint-diagnose[pg]")

    def factory():
        connection = psycopg.connect(dsn)
        connection.autocommit = True
        return connection

    return factory


def a_payload():
    context = RefusalContext(
        sqlstate="23514",
        constraint="gate_closed_when_issued",
        message="MAINLINE: merge refused — undispositioned precursor in blame ancestry",
        subject_kind="permit",
        subject_id=str(uuid.uuid4()),
        gate_epoch=7,
    )
    return build_payload(
        context,
        spec_version="1.0.0-rc.1",
        diagnosis="declarative",
        mus=[Obligation(obligation_id=OPEN_CHECK, severity=5, virulence="blood_fatal")],
        naa=DisposeObligations(
            obligation_ids=[OPEN_CHECK], cardinality=1, description="one obligation remains open"
        ),
        naa_reason=None,
        profile="mainline",
    )


def _sqlstate(exc) -> str:
    return getattr(exc, "sqlstate", "")


def _constraint(exc) -> str:
    diag = getattr(exc, "diag", None)
    return getattr(diag, "constraint_name", "") or ""


def _insert_raw(connection, row):
    from trappoint_diagnose.ledger import INSERT_TEMPLATE

    cursor = connection.cursor()
    try:
        cursor.execute(INSERT_TEMPLATE.format(schema=SCHEMA), row)
    finally:
        cursor.close()


def test_a_refusal_can_be_recorded(connect):
    connection = connect()
    try:
        row = record_refusal(connection, a_payload(), schema=SCHEMA, recorded_by="pytest")
        cursor = connection.cursor()
        try:
            cursor.execute(
                f"SELECT constraint_name, mus_cardinality, diagnosis FROM {SCHEMA}."  # noqa: S608
                "refusal_ledger WHERE refusal_id = %s::UUID",
                (row["refusal_id"],),
            )
            stored = cursor.fetchone()
        finally:
            cursor.close()
    finally:
        connection.close()
    assert stored == ("gate_closed_when_issued", 1, "declarative")


@pytest.mark.parametrize("verb", ["UPDATE", "DELETE"])
def test_the_ledger_is_append_only(connect, verb):
    connection = connect()
    try:
        row = record_refusal(connection, a_payload(), schema=SCHEMA, recorded_by="pytest")
        # S608: SCHEMA comes from the environment of a test run, never from a payload,
        # and the identifier it names is checked by `record_refusal` on the write path.
        statement = (
            f"UPDATE {SCHEMA}.refusal_ledger SET message = 'edited' WHERE refusal_id = %s::UUID"  # noqa: S608
            if verb == "UPDATE"
            else f"DELETE FROM {SCHEMA}.refusal_ledger WHERE refusal_id = %s::UUID"  # noqa: S608
        )
        cursor = connection.cursor()
        try:
            with pytest.raises(Exception) as caught:  # noqa: PT011 - driver type, not ours
                cursor.execute(statement, (row["refusal_id"],))
        finally:
            cursor.close()
    finally:
        connection.close()
    assert _sqlstate(caught.value) == "P0001"
    assert "append-only" in str(caught.value)


def test_a_reason_set_that_is_not_an_array_is_refused(connect):
    row = ledger_row(a_payload(), recorded_by="pytest")
    payload = json.loads(row["payload"])
    payload["mus"] = {"kind": "obligation"}
    row["payload"] = json.dumps(payload)
    connection = connect()
    try:
        with pytest.raises(Exception) as caught:  # noqa: PT011
            _insert_raw(connection, row)
    finally:
        connection.close()
    assert _sqlstate(caught.value) == "P0001"
    assert "not an array" in str(caught.value)


def test_an_atom_key_outside_the_closed_vocabulary_is_refused(connect):
    # Invariant I15 at the last place the bytes pass through: the wire schema already
    # closes every atom, and this is the same rule enforced again for a writer that never
    # read the schema.
    row = ledger_row(a_payload(), recorded_by="pytest")
    payload = json.loads(row["payload"])
    payload["mus"][0]["signer_attentiveness"] = 0.2
    row["payload"] = json.dumps(payload)
    connection = connect()
    try:
        with pytest.raises(Exception) as caught:  # noqa: PT011
            _insert_raw(connection, row)
    finally:
        connection.close()
    assert _sqlstate(caught.value) == "P0001"
    assert "closed vocabulary" in str(caught.value)


def test_an_atom_naming_no_modelled_fact_family_is_refused(connect):
    row = ledger_row(a_payload(), recorded_by="pytest")
    payload = json.loads(row["payload"])
    payload["mus"][0]["kind"] = "vibe"
    row["payload"] = json.dumps(payload)
    connection = connect()
    try:
        with pytest.raises(Exception) as caught:  # noqa: PT011
            _insert_raw(connection, row)
    finally:
        connection.close()
    assert _sqlstate(caught.value) == "P0001"
    assert "modelled fact family" in str(caught.value)


@pytest.mark.parametrize(
    ("mutate", "constraint"),
    [
        ({"constraint_name": "something_else"}, "refusal_payload_names_the_exhibit"),
        ({"sqlstate": "23503"}, "refusal_payload_names_the_code"),
        ({"diagnosis": "quickxplain"}, "refusal_payload_names_the_diagnosis"),
        ({"mus_cardinality": 4}, "refusal_mus_agrees"),
        ({"naa_kind": "substitute_kind"}, "refusal_payload_names_the_alternative"),
    ],
)
def test_a_row_that_disagrees_with_its_own_payload_is_refused(connect, mutate, constraint):
    row = ledger_row(a_payload(), recorded_by="pytest")
    row.update(mutate)
    connection = connect()
    try:
        with pytest.raises(Exception) as caught:  # noqa: PT011
            _insert_raw(connection, row)
    finally:
        connection.close()
    assert _sqlstate(caught.value) == "23514"
    assert _constraint(caught.value) == constraint


def test_a_declarative_diagnosis_that_probed_is_refused_by_the_table_too(connect):
    row = ledger_row(a_payload(), recorded_by="pytest")
    row["probe_calls"] = 9
    connection = connect()
    try:
        with pytest.raises(Exception) as caught:  # noqa: PT011
            _insert_raw(connection, row)
    finally:
        connection.close()
    assert _sqlstate(caught.value) == "23514"
    assert _constraint(caught.value) == "refusal_declarative_costs_no_probe"


def test_a_payload_carrying_a_person_metric_is_refused_by_a_plain_column_check(connect):
    row = ledger_row(a_payload(), recorded_by="pytest")
    payload = json.loads(row["payload"])
    payload["ext"] = {"risk_score": 0.9}
    row["payload"] = json.dumps(payload)
    connection = connect()
    try:
        with pytest.raises(Exception) as caught:  # noqa: PT011
            _insert_raw(connection, row)
    finally:
        connection.close()
    assert _sqlstate(caught.value) == "23514"
    assert _constraint(caught.value) == "refusal_no_person_metric"


def test_a_p0001_refusal_recorded_as_reported_is_refused(connect):
    # diag.constraint_name is empty for P0001, so a payload claiming `reported` is
    # claiming a diagnostic the driver did not supply.
    row = ledger_row(a_payload(), recorded_by="pytest")
    row["sqlstate"] = "P0001"
    payload = json.loads(row["payload"])
    payload["sqlstate"] = "P0001"
    row["payload"] = json.dumps(payload)
    connection = connect()
    try:
        with pytest.raises(Exception) as caught:  # noqa: PT011
            _insert_raw(connection, row)
    finally:
        connection.close()
    assert _sqlstate(caught.value) == "23514"
    assert _constraint(caught.value) == "refusal_p0001_exhibit_is_parsed"
