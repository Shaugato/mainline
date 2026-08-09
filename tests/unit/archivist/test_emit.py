# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
"""Statements, parameters, and the eleven tables this role may write.

Two classes of assertion:

* the statements match the DDL — column order, placeholder count, the closed vocabularies
  migrations 0033 and 0035 declare, and the ``ON CONFLICT`` that makes a redelivery a
  no-op rather than a second version of an incident;
* the statements cannot be anything else — no ``UPDATE``, no ``DELETE``, no table outside
  ``agent_ingestor``'s grant, and no severity that did not come out of the appraisal.
"""

from __future__ import annotations

import re

import archivist_corpus as corpus
import pytest
from mainline_archivist import (
    CONTROL_FAILURE_COLUMNS,
    EVENT_COLUMNS,
    INGEST_INSERTABLE_TABLES,
    ControlFailureDraft,
    EventDraft,
    EventKindNotCoded,
    SpanNotVerbatim,
    Statement,
    WriteOutsideGrant,
    appraise,
    assert_ingest_safe,
    insert_control_failure,
    insert_event,
    insert_intake_finding,
)
from mainline_archivist.emit import INSERT_CONTROL_FAILURE_SQL, INSERT_EVENT_SQL, SQL_CONSTANTS

TEXT = corpus.DOCUMENT_TEXT
EVENT_ID = "1f0b8cbe-2f11-4e15-9f2a-7bd1c2a41f30"


def _draft(**overrides):
    appraisal = appraise(list(corpus.coded_claims()))
    fields = {
        "site_id": corpus.SITE_ID,
        "occurred_at": corpus.OCCURRED_AT,
        "kind": "incident",
        "title": corpus.span(corpus.TITLE_QUOTE),
        "narrative": corpus.span(corpus.NARRATIVE_QUOTE),
        "source_object_key": "incidents/IR-2019-0117.txt",
        "source_sha256": corpus.fetched().sha256_bytes,
        "severity": appraisal,
        "external_ref": "IR-2019-0117",
    }
    fields.update(overrides)
    return EventDraft(**fields)


def test_the_event_statement_matches_the_ddl_shape():
    statement = insert_event(_draft(), source_text=TEXT)

    assert statement.table == "mainline.event"
    assert len(statement.params) == len(EVENT_COLUMNS)
    assert INSERT_EVENT_SQL.count("%s") == len(EVENT_COLUMNS)
    # event_id and ingested_at are the table's to supply. A client-supplied ingested_at is
    # a client-supplied answer to "when did this system learn".
    assert "event_id," not in INSERT_EVENT_SQL.split("VALUES")[0]
    assert "ingested_at" not in INSERT_EVENT_SQL


def test_a_redelivery_is_a_no_op_rather_than_a_second_version():
    # At-least-once delivery is the normal case. An upsert here would let a redelivery
    # quietly change a severity.
    assert "ON CONFLICT (site_id, external_ref) DO NOTHING" in INSERT_EVENT_SQL
    assert "DO UPDATE" not in INSERT_EVENT_SQL


def test_severity_parameters_come_from_the_appraisal_and_nowhere_else():
    statement = insert_event(_draft(), source_text=TEXT)
    columns = dict(zip(EVENT_COLUMNS, statement.params, strict=True))

    appraisal = appraise(list(corpus.coded_claims()))
    assert columns["severity_actual"] == appraisal.severity_actual
    assert columns["severity_potential"] == appraisal.severity_potential
    assert columns["severity_gate"] == appraisal.severity_gate
    assert columns["severity_basis"] == str(appraisal.severity_basis)
    assert columns["severity_span"] == list(appraisal.severity_span)

    # There is no constructor here that takes an integer severity at all.
    with pytest.raises(TypeError):
        EventDraft(  # type: ignore[call-arg]
            site_id=corpus.SITE_ID,
            occurred_at=corpus.OCCURRED_AT,
            kind="incident",
            title=corpus.span(corpus.TITLE_QUOTE),
            narrative=corpus.span(corpus.NARRATIVE_QUOTE),
            source_object_key="k",
            source_sha256=b"0" * 32,
            severity_gate=5,
        )


def test_title_and_narrative_are_the_documents_own_bytes():
    statement = insert_event(_draft(), source_text=TEXT)
    columns = dict(zip(EVENT_COLUMNS, statement.params, strict=True))

    assert columns["title"] in TEXT
    assert columns["narrative"] in TEXT


def test_a_span_from_another_document_never_reaches_the_parameter_list():
    other = TEXT.replace("17.4 %", "19.9 %")
    with pytest.raises(SpanNotVerbatim):
        insert_event(_draft(), source_text=other)


def test_a_kind_outside_the_closed_vocabulary_is_refused():
    with pytest.raises(EventKindNotCoded, match="kind_closed"):
        _draft(kind="investigation")
    with pytest.raises(EventKindNotCoded, match="closed vocabulary"):
        _draft(kind="")


def test_a_naive_occurred_at_is_refused():
    from datetime import datetime

    with pytest.raises(ValueError, match="naive"):
        _draft(occurred_at=datetime(2019, 3, 14, 6, 20))  # noqa: DTZ001 - that is the point


def test_a_digest_that_is_not_thirty_two_bytes_is_refused():
    with pytest.raises(ValueError, match="32"):
        _draft(source_sha256=b"short")


def test_the_control_failure_statement_matches_the_ddl_shape():
    draft = ControlFailureDraft(
        event_id=EVENT_ID,
        control_class="atmospheric_retest_after_isolation_break",
        barrier_role="preventive",
        failure_mode="absent",
        hazard_energy="chemical",
        icam_tier="absent_or_failed_defence",
        evidence=corpus.span("The atmospheric re-test after isolation break was ABSENT."),
    )
    statement = insert_control_failure(draft, source_text=TEXT)
    columns = dict(zip(CONTROL_FAILURE_COLUMNS, statement.params, strict=True))

    assert INSERT_CONTROL_FAILURE_SQL.count("%s") == len(CONTROL_FAILURE_COLUMNS)
    assert len(columns["evidence_span"]) == 2
    # quote_sha256 is computed from the span's own bytes, never accepted.
    assert columns["quote_sha256"] == draft.evidence.sha256_bytes()
    assert len(columns["quote_sha256"]) == 32


@pytest.mark.parametrize(
    ("field_name", "value"),
    [
        ("barrier_role", "mitigating"),
        ("failure_mode", "missing"),
        ("hazard_energy", "acoustic"),
        ("icam_tier", "management_failure"),
    ],
)
def test_control_failure_vocabularies_are_closed(field_name, value):
    fields = {
        "event_id": EVENT_ID,
        "control_class": "atmospheric_retest",
        "barrier_role": "preventive",
        "failure_mode": "absent",
        "hazard_energy": "chemical",
        "evidence": corpus.span(corpus.TITLE_QUOTE),
    }
    fields[field_name] = value
    with pytest.raises(ValueError, match="closed vocabulary"):
        ControlFailureDraft(**fields)


def test_there_is_no_update_or_delete_anywhere_in_the_emitters():
    forbidden = re.compile(r"\b(UPDATE|DELETE|TRUNCATE|DROP|ALTER|GRANT|REVOKE)\b", re.IGNORECASE)
    for sql in SQL_CONSTANTS:
        assert forbidden.search(sql) is None, sql
        assert sql.lstrip().upper().startswith("INSERT")


def test_a_statement_outside_the_grant_is_refused():
    with pytest.raises(WriteOutsideGrant, match="UPDATE"):
        assert_ingest_safe(
            Statement(
                sql="INSERT INTO mainline.event (site_id) VALUES (%s); UPDATE mainline.event "
                "SET severity_gate = 5",
                params=("x",),
                table="mainline.event",
            )
        )
    with pytest.raises(WriteOutsideGrant, match="eleven tables"):
        assert_ingest_safe(
            Statement(
                sql="INSERT INTO mainline.blocking_check (check_id) VALUES (%s)",
                params=("x",),
                table="mainline.blocking_check",
            )
        )
    with pytest.raises(WriteOutsideGrant, match="INSERT"):
        assert_ingest_safe(
            Statement(sql="SELECT 1", params=(), table="mainline.event"),
        )
    with pytest.raises(WriteOutsideGrant, match="disagrees with the SQL"):
        assert_ingest_safe(
            Statement(
                sql="INSERT INTO mainline.event_cue (cue_id) VALUES (%s)",
                params=("x",),
                table="mainline.event",
            )
        )


def test_the_grant_list_is_exactly_the_eleven_tables():
    # Transcribed from verticals/mainline/db/GRANTS.yaml, agent_ingestor block. If the
    # grant matrix grows a table, this list is where the change is noticed.
    assert len(INGEST_INSERTABLE_TABLES) == 11
    assert "mainline.event" in INGEST_INSERTABLE_TABLES
    assert "mainline.blocking_check" not in INGEST_INSERTABLE_TABLES
    assert "mainline_meas.silence_ledger" not in INGEST_INSERTABLE_TABLES


def test_an_intake_finding_statement_is_derived_from_the_payload():
    from mainline_quarantine import DocumentIntakeFinding, Layer, Outcome

    finding = DocumentIntakeFinding(
        document_sha256="a" * 64,
        observed_at=corpus.OBSERVED_AT,
        layer=Layer.L2_DELIMIT_AND_DATAMARK,
        outcome=Outcome.BLOCKED_PROMPT_ATTACK,
        detector="direct-instruction-override",
        detail="an instruction addressed to the reader",
    )
    payload = finding.to_row()
    statement = insert_intake_finding(payload)

    assert statement.table == "mainline.document_intake_finding"
    assert statement.sql.count("%s") == len(payload)
    assert statement.params == tuple(payload.values())
    for column in payload:
        assert column in statement.sql


def test_an_empty_finding_payload_is_refused():
    with pytest.raises(ValueError, match="no drop path"):
        insert_intake_finding({})


def test_a_jsonb_parameter_is_canonical():
    statement = insert_event(
        _draft(consequence_proxy={"exposure_minutes": 4, "energy": "chemical"}),
        source_text=TEXT,
    )
    columns = dict(zip(EVENT_COLUMNS, statement.params, strict=True))

    assert columns["consequence_proxy"] == '{"energy":"chemical","exposure_minutes":4}'
