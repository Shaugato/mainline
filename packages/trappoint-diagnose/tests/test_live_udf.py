# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""The SQL half against a real cluster. Skips with a reason when there is not one.

`done_when`, executed rather than described: a permit refused by
``gate_closed_when_issued`` with three obligations of which two carry a live disposition
must produce a payload whose reason set names EXACTLY the third, and whose alternative
names exactly that obligation; and an ``fk_clearance`` refusal at ``blood_fatal`` /
``mechanism_absent`` must list EXACTLY the kinds present in ``clearance_legal`` at
``blood_fatal``.

This module builds nothing. Fixture construction belongs to the conformance corpus, which
another worker owns; what this asserts is that the SHIPPED UDF, applied to a database that
already holds such a permit, answers correctly and that the answer validates against the
wire schema. Point ``TRAPPOINT_DSN`` at a migrated cluster and it runs; leave it unset and
it skips saying so, because a test that passes by absence is worse than one that is
missing.
"""

from __future__ import annotations

import os

import pytest

from trappoint_diagnose.diagnose import Diagnoser
from trappoint_diagnose.model import RefusalContext
from trappoint_diagnose.udf import UdfSource
from trappoint_diagnose.wire import validate_payload

pytestmark = pytest.mark.requires_cluster

DSN_VAR = "TRAPPOINT_DSN"
BINDING_VAR = "TRAPPOINT_BINDING"
SUBJECT_VAR = "TRAPPOINT_REFUSED_PERMIT"


def _require(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        pytest.skip(f"{name} is unset; this case needs a migrated cluster and a refused permit")
    return value


@pytest.fixture(scope="module")
def connect():
    dsn = _require(DSN_VAR)
    psycopg = pytest.importorskip("psycopg", reason="install trappoint-diagnose[pg]")

    def factory():
        return psycopg.connect(dsn)

    return factory


@pytest.fixture(scope="module")
def diagnoser():
    from pathlib import Path

    from trappoint_diagnose.binding import load_gate_binding

    path = os.environ.get(BINDING_VAR)
    if not path:
        root = next(
            (
                p
                for p in Path(__file__).resolve().parents
                if (p / "verticals" / "mainline" / "vertical.toml").is_file()
            ),
            None,
        )
        if root is None:
            pytest.skip("no vertical.toml found; set TRAPPOINT_BINDING")
        path = str(root / "verticals" / "mainline" / "vertical.toml")
    return Diagnoser(load_gate_binding(path))


def _epoch(connect, permit_id: str) -> int:
    connection = connect()
    try:
        cursor = connection.cursor()
        try:
            cursor.execute(
                "SELECT gate_epoch FROM mainline.permit WHERE permit_id = %s::UUID",
                (permit_id,),
            )
            row = cursor.fetchone()
        finally:
            cursor.close()
    finally:
        connection.rollback()
        connection.close()
    if row is None:
        pytest.skip(f"{SUBJECT_VAR} names a permit this cluster does not hold")
    return int(row[0])


def test_a_counter_refusal_names_exactly_the_undispositioned_obligation(connect, diagnoser):
    permit_id = _require(SUBJECT_VAR)
    context = RefusalContext(
        sqlstate="23514",
        constraint="gate_closed_when_issued",
        message="MAINLINE: merge refused — undispositioned or expired precursor in blame ancestry",
        subject_kind="permit",
        subject_id=permit_id,
        gate_epoch=_epoch(connect, permit_id),
    )
    payload = diagnoser.explain(context, source=UdfSource(connect))
    wire = payload.to_wire()
    validate_payload(wire)

    assert wire["diagnosis"] == "declarative"
    assert wire["probe_calls"] == 0
    assert len(wire["mus"]) == 1, "two of the three obligations carry a live disposition"
    assert wire["mus"][0]["kind"] == "obligation"
    assert wire["naa"]["kind"] == "dispose_obligations"
    assert wire["naa"]["cardinality"] == 1
    assert wire["naa"]["obligation_ids"] == [wire["mus"][0]["obligation_id"]]


def test_a_clearance_refusal_lists_exactly_the_kinds_present_at_that_classification(
    connect, diagnoser
):
    permit_id = _require(SUBJECT_VAR)
    context = RefusalContext(
        sqlstate="23503",
        constraint="fk_clearance",
        message='MAINLINE: insert on table "disposition" violates foreign key constraint',
        subject_kind="permit",
        subject_id=permit_id,
        gate_epoch=_epoch(connect, permit_id),
        attempt={"kind": "mechanism_absent"},
    )
    wire = diagnoser.explain(context, source=UdfSource(connect)).to_wire()
    validate_payload(wire)

    connection = connect()
    try:
        cursor = connection.cursor()
        try:
            # Row per kind rather than array_agg: an enum array comes back through the
            # driver as its text rendering, and sorting that string compares characters.
            cursor.execute(
                "SELECT kind::STRING FROM mainline.clearance_legal "
                "WHERE virulence = 'blood_fatal' ORDER BY 1"
            )
            present = [row[0] for row in cursor.fetchall()]
        finally:
            cursor.close()
    finally:
        connection.rollback()
        connection.close()

    assert wire["naa"]["kind"] == "substitute_kind"
    assert sorted(wire["naa"]["legal_kinds"]) == sorted(present)
    assert "mechanism_absent" not in wire["naa"]["legal_kinds"]


def test_the_diagnosis_writes_nothing(connect, diagnoser):
    permit_id = _require(SUBJECT_VAR)
    connection = connect()
    try:
        cursor = connection.cursor()
        try:
            cursor.execute("SELECT count(*) FROM mainline.blocking_check")
            before = cursor.fetchone()[0]
        finally:
            cursor.close()
    finally:
        connection.rollback()
        connection.close()

    diagnoser.explain(
        RefusalContext(
            sqlstate="23514",
            constraint="gate_closed_when_issued",
            message="MAINLINE: merge refused",
            subject_kind="permit",
            subject_id=permit_id,
            gate_epoch=_epoch(connect, permit_id),
        ),
        source=UdfSource(connect),
    )

    connection = connect()
    try:
        cursor = connection.cursor()
        try:
            cursor.execute("SELECT count(*) FROM mainline.blocking_check")
            after = cursor.fetchone()[0]
        finally:
            cursor.close()
    finally:
        connection.rollback()
        connection.close()
    assert before == after, "a diagnosis must leave the database exactly as it found it"
