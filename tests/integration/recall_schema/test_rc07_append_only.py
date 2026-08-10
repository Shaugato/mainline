# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""RC-07 — the silence ledger is append-only.

The ledger's entire evidentiary value comes from being a contemporaneous business record made
in the ordinary course of business. A mutable one is not that; it is a document the defendant
could have written last week. So an UPDATE and a DELETE are both refusals, for every writer.

HONESTY NOTE, and it is the reason this module reports rather than just asserts:
`mainline.fn_refuse_mutation` and its triggers are ARCHITECTURE §5.11 #9 and belong to the
trigger band owned by `dm-functions-triggers`, not to this worker. The suite uses the DEPLOYED
mechanism when it is present. When it is not — which is the case whenever the recall band is
applied in isolation — a stand-in with the identical body is applied from `prereq/` and this
module says so in its own assertion output. A test that silently exercises its own fixture and
reports a passing invariant is worse than a missing test.
"""

from __future__ import annotations

import json

import pytest

from _schema_support import capture_refusal, new_uuid, rows, trigger_names

pytestmark = pytest.mark.schema


def _insert_silence(conn, *, site_id, subject_id) -> None:
    conn.execute(
        """
        INSERT INTO mainline_meas.silence_ledger
          (site_id, source, reason, subject_kind, subject_id, severity, score, threshold,
           arithmetic, policy_version)
        VALUES (%s, 'recall', 'below_tau', 'event', %s, 5, 0.31, 0.45, %s, 'rp-test')
        """,
        (
            site_id,
            subject_id,
            json.dumps({"rrf": 0.019, "cos_max": 0.58, "tau": 0.45, "calibrator": "knots-v1"}),
        ),
    )


def test_rc07_update_on_the_silence_ledger_is_refused(conn, schema) -> None:
    site_id, subject_id = new_uuid(), new_uuid()
    _insert_silence(conn, site_id=site_id, subject_id=subject_id)

    present = trigger_names(conn, "mainline_meas", "silence_ledger")
    assert present, "no append-only trigger on silence_ledger at all"

    refusal = capture_refusal(
        conn.execute,
        "UPDATE mainline_meas.silence_ledger SET score = 0.99 WHERE subject_id = %s",
        (subject_id,),
    )
    assert refusal.sqlstate == "P0001", refusal.message
    assert "MAINLINE: this table is append-only; write a new row" in refusal.message, (
        refusal.message
    )
    assert "silence_ledger_append_only" in present or not schema.append_only_is_standin, (
        f"unexpected append-only trigger name: {sorted(present)}"
    )

    # The row is untouched, which is the property that matters to a court.
    assert rows(
        conn,
        "SELECT score FROM mainline_meas.silence_ledger WHERE subject_id = %s",
        (subject_id,),
    ) == [(0.31,)]


def test_rc07b_delete_on_the_silence_ledger_is_refused(conn) -> None:
    site_id, subject_id = new_uuid(), new_uuid()
    _insert_silence(conn, site_id=site_id, subject_id=subject_id)

    refusal = capture_refusal(
        conn.execute,
        "DELETE FROM mainline_meas.silence_ledger WHERE subject_id = %s",
        (subject_id,),
    )
    assert refusal.sqlstate == "P0001", refusal.message
    assert "MAINLINE: this table is append-only; write a new row" in refusal.message
    assert rows(
        conn,
        "SELECT count(*) FROM mainline_meas.silence_ledger WHERE subject_id = %s",
        (subject_id,),
    ) == [(1,)]


def test_rc07c_report_whether_the_deployed_mechanism_or_the_stand_in_ran(schema) -> None:
    """Not an assertion about the database. An assertion about what the suite just proved.

    This test always passes and always prints. If it prints `stand-in`, RC-07 above proved that
    the recall band is COMPATIBLE with the append-only mechanism, not that the deployed schema
    carries it — that proof belongs to `dm-functions-triggers` and arrives with migration band
    0130-0199.
    """
    origin = "stand-in (prereq/90)" if schema.append_only_is_standin else "deployed migration"
    print(f"\n[RC-07] append-only mechanism exercised: {origin}")
    assert origin
