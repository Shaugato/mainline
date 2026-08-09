# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
"""The projection placeholder, the follower-read weld, and the deterministic ids."""

from __future__ import annotations

import dataclasses
import uuid

import pytest
from fixity_corpus import ASSET, CLAUSE_GAS_TEST, SITE, gas_test_cat, scope
from mainline_domain.contracts import ControlDelta
from mainline_fixity import (
    DriftFinding,
    GateReadFromPatrol,
    ProjectionSuppliedByClient,
    StaleFollowerRead,
    Statement,
    UndeterminedWouldBlock,
    assert_patrol_safe,
    finding_uuid,
    insert_drift_finding,
    patrol_read,
    projection_placeholder,
    run_uuid,
)

RUN = run_uuid(scope())


def finding(**overrides) -> DriftFinding:
    base = DriftFinding(
        finding_id=finding_uuid(RUN, CLAUSE_GAS_TEST, ASSET),
        run_id=RUN,
        site_id=SITE,
        clause_uuid=CLAUSE_GAS_TEST,
        fixity_class="L2",
        documented_cat=gas_test_cat("10"),
        observed_cat=gas_test_cat("14"),
        direction=ControlDelta.WEAKEN,
        undetermined=False,
        confidence_milli=940,
        asset_tag=ASSET,
    )
    return dataclasses.replace(base, **overrides)


# ── the projection placeholder ───────────────────────────────────────────────


def test_a_proposed_weakening_is_loud_rather_than_quiet():
    # The projection trigger can only ever LOWER this. If the trigger were missing,
    # a real weakening lands blocking rather than silently advisory.
    assert projection_placeholder(ControlDelta.WEAKEN, False) == (5, "blocking")
    assert projection_placeholder(ControlDelta.REMOVE, False) == (5, "blocking")


def test_a_tightening_proposes_nothing():
    for delta in (ControlDelta.INTRODUCE, ControlDelta.STRENGTHEN, ControlDelta.RESTATE):
        assert projection_placeholder(delta, False) == (0, "advisory")


def test_undetermined_forces_advisory_because_mi21_would_refuse_otherwise():
    assert projection_placeholder(ControlDelta.WEAKEN, True) == (0, "advisory")
    assert projection_placeholder(None, True) == (0, "advisory")


def test_the_placeholder_cannot_see_a_severity():
    # Two findings differing in everything the patrol knows EXCEPT direction and
    # undetermined emit the same projected pair. That is what "the inserter did not
    # decide it" means, stated as a test rather than as a comment.
    left = insert_drift_finding(finding(confidence_milli=10))
    right = insert_drift_finding(
        finding(
            confidence_milli=1000,
            documented_cat=gas_test_cat("100"),
            observed_cat=gas_test_cat("140"),
            clause_uuid=uuid.uuid5(uuid.NAMESPACE_OID, "other-clause"),
        )
    )
    severity_index, gate_index = 10, 11
    assert left.params[severity_index] == right.params[severity_index] == 5
    assert left.params[gate_index] == right.params[gate_index] == "blocking"


def test_an_undetermined_finding_that_would_block_refuses_at_construction():
    with pytest.raises(UndeterminedWouldBlock, match="MI21"):
        finding(undetermined=True, direction=ControlDelta.WEAKEN)


def test_a_finding_with_no_documented_side_is_refused_not_invented():
    # `drift_finding.documented_cat` is NOT NULL. Synthesising one would fabricate
    # the exact thing the finding claims is missing.
    with pytest.raises(ProjectionSuppliedByClient, match="documented_cat"):
        insert_drift_finding(finding(documented_cat=None))


# ── deterministic identifiers ────────────────────────────────────────────────


def test_run_and_finding_ids_are_stable_across_processes():
    assert run_uuid(scope()) == run_uuid(scope()) == RUN
    assert finding_uuid(RUN, CLAUSE_GAS_TEST, ASSET) == finding_uuid(RUN, CLAUSE_GAS_TEST, ASSET)


def test_a_different_occurrence_is_a_different_run():
    other = dataclasses.replace(scope(), schedule_id="fixity-patrol-l0-weekly")
    assert run_uuid(other) != RUN


def test_the_finding_id_separates_two_assets_on_one_clause():
    assert finding_uuid(RUN, CLAUSE_GAS_TEST, "TK-2201") != finding_uuid(
        RUN, CLAUSE_GAS_TEST, "TK-2202"
    )


def test_redelivery_is_absorbed_by_the_primary_key():
    statement = insert_drift_finding(finding())
    assert "ON CONFLICT (finding_id) DO NOTHING" in statement.sql


# ── the follower-read weld ───────────────────────────────────────────────────


def test_every_patrol_read_carries_the_preamble():
    statement = patrol_read("SELECT 1 FROM mainline.clause_binding")
    assert statement.is_follower_read
    assert statement.preamble[1].endswith("follower_read_timestamp()")


def test_a_select_without_the_preamble_is_refused():
    with pytest.raises(StaleFollowerRead):
        assert_patrol_safe(Statement(sql="SELECT * FROM mainline.clause_binding"))


def test_a_patrol_statement_may_not_name_a_gate_table():
    with pytest.raises(GateReadFromPatrol, match="blocking_check"):
        patrol_read("SELECT * FROM mainline.blocking_check WHERE permit_id = %s", (1,))


def test_the_refusal_names_the_table_and_quotes_the_statement():
    with pytest.raises(GateReadFromPatrol) as excinfo:
        patrol_read("SELECT * FROM mainline.disposition")
    assert excinfo.value.table == "disposition"
    assert "mainline.disposition" in excinfo.value.statement


def test_a_write_does_not_need_the_preamble():
    # An INSERT at a past timestamp is not a thing, and the database would refuse a
    # write inside a follower-read transaction anyway.
    statement = insert_drift_finding(finding())
    assert statement.preamble == ()
