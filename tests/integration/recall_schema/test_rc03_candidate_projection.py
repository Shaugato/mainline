# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""RC-03 — `recall_candidate.severity` is a projection of `event.severity_gate`, never an input.

Severity is not a label on a candidate. Under Severity-Graded Admission it IS the threshold the
candidate is judged against — τ(5)=0.35 up to τ(1)=0.85 — so an agent able to write
``severity = 1`` on a fatality moves that fatality's evidence bar to 0.85, watches it fall
below, and produces a silence-ledger row that reads as a careful calibrated judgement with
arithmetic attached. Every downstream artefact would corroborate it.
"""

from __future__ import annotations

import json

import pytest

from _schema_support import (
    INSERT_RUN_SQL,
    assert_trigger_refusal,
    capture_refusal,
    cosign_checkpoint,
    insert_event,
    insert_policy,
    new_uuid,
    rows,
    run_values,
)

pytestmark = pytest.mark.schema


def _anchored_run(conn):
    site_id = new_uuid()
    cosign_checkpoint(conn, site_id=site_id, tree_size=4096)
    policy = insert_policy(conn, anchored_tree_size=1024)
    run_id, permit_id = new_uuid(), new_uuid()
    conn.execute(
        INSERT_RUN_SQL,
        run_values(
            run_id=run_id,
            permit_id=permit_id,
            site_id=site_id,
            policy_version=policy,
            n_candidates=1,
            n_advisory=1,
        ),
    )
    return run_id, site_id


def _insert_candidate(conn, *, run_id, event_id, severity: int) -> None:
    conn.execute(
        """
        INSERT INTO mainline_meas.recall_candidate
          (run_id, event_id, rank, severity, features, p_relevant, tau_applied, outcome)
        VALUES (%s, %s, 1, %s, %s, 0.81, 0.35, 'advisory')
        """,
        (
            run_id,
            event_id,
            severity,
            json.dumps({"rrf": 0.031, "bm25": 7.2, "cos_max": 0.71, "level": 3}),
        ),
    )


def test_rc03_a_candidate_claiming_severity_1_for_a_fatality_is_rewritten(conn) -> None:
    run_id, site_id = _anchored_run(conn)
    event = insert_event(conn, site_id=site_id, severity_gate=5)

    _insert_candidate(conn, run_id=run_id, event_id=event.event_id, severity=1)

    stored = rows(
        conn,
        "SELECT severity FROM mainline_meas.recall_candidate WHERE run_id = %s AND event_id = %s",
        (run_id, event.event_id),
    )
    assert stored == [(5,)], (
        "the candidate kept the severity the inserter supplied; τ would have been 0.85 on a "
        "fatality and the miss would have looked like calibration"
    )


def test_rc03b_a_candidate_naming_no_event_cannot_be_typed(conn) -> None:
    run_id, _ = _anchored_run(conn)
    refusal = capture_refusal(
        _insert_candidate, conn, run_id=run_id, event_id=new_uuid(), severity=5
    )
    assert_trigger_refusal(
        conn,
        refusal,
        message="MAINLINE: no such event — a recall candidate cannot be typed",
        schema="mainline_meas",
        table="recall_candidate",
        trigger="candidate_project",
    )


def test_rc03c_the_projection_survives_a_severity_the_check_would_have_allowed(conn) -> None:
    """`candidate_sev_range` allows 0-5; the projection is what makes 3 wrong, not the range."""
    run_id, site_id = _anchored_run(conn)
    event = insert_event(conn, site_id=site_id, severity_gate=4)
    _insert_candidate(conn, run_id=run_id, event_id=event.event_id, severity=3)
    stored = rows(
        conn,
        "SELECT severity FROM mainline_meas.recall_candidate WHERE run_id = %s AND event_id = %s",
        (run_id, event.event_id),
    )
    assert stored == [(4,)]
