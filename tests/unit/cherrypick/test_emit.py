# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
"""Statements: what they say, what they refuse to say, and the compare-and-set."""

from __future__ import annotations

import uuid

import pytest
from cherrypick_corpus import (
    CONFLICT_ID,
    DELTA_SET,
    LOCAL_CLAUSE,
    conflict,
    lesson,
    mitigated,
    propagation,
)
from mainline_cherrypick import (
    SCORER_VERSION,
    AgentWouldResolve,
    ForbiddenWriteTarget,
    HumanResolution,
    PropState,
    Statement,
    assert_fleet_safe,
    insert_lesson,
    insert_merge_conflict,
    insert_propagation,
    insert_resolution_memory,
    remember,
    statements_for_offer,
    update_propagation_state,
)

SIGNATURE = b"\x01" * 64
COMMIT = bytes.fromhex("c3" * 32)


def test_the_lesson_insert_carries_the_patch_digest_and_the_envelope():
    statement = insert_lesson(lesson(), delta_set_size=len(DELTA_SET))
    assert statement.params[5] == "strengthen"
    assert statement.params[6] == lesson().patch_digest
    assert statement.params[8]["delta_set_size"] == 2
    assert statement.params[8]["predicate"] == lesson().envelope


def test_the_propagation_insert_omits_both_projections():
    statement = insert_propagation(propagation())
    assert "open_conflicts" not in statement.sql
    assert "adopted_commit" not in statement.sql


def test_the_propagation_insert_absorbs_redelivery_on_the_primary_key():
    statement = insert_propagation(propagation())
    assert "ON CONFLICT (lesson_id, site_id) DO NOTHING" in statement.sql


def test_the_score_is_rendered_as_a_decimal_string_not_a_float():
    statement = insert_propagation(propagation(score_milli=850))
    assert statement.params[3] == "0.850"
    assert not isinstance(statement.params[3], float)
    assert statement.params[4] == SCORER_VERSION


def test_a_declination_rides_along_in_its_own_columns():
    declined = propagation(state=PropState.DECLINED, declination=mitigated())
    statement = insert_propagation(declined)
    assert statement.params[7] == LOCAL_CLAUSE
    assert statement.params[8] == "mitigated"


def test_the_state_update_is_a_compare_and_set():
    # CockroachDB has no advisory locks, so the compare has to be in the predicate:
    # two workers handed the same at-least-once delivery must not both advance.
    statement = update_propagation_state(
        propagation(state=PropState.CONFLICTED), PropState.PROPOSED
    )
    assert "AND state = %s" in statement.sql
    assert statement.params == (
        "conflicted",
        propagation().lesson_id,
        propagation().site_id,
        "proposed",
    )


def test_the_state_update_sets_exactly_one_column():
    statement = update_propagation_state(propagation(), PropState.PROPOSED)
    body = statement.sql.upper().split("WHERE")[0]
    assert body.count("=") == 1


def test_statements_for_an_offer_are_in_execution_order():
    statements = statements_for_offer(lesson(), [propagation()], delta_set_size=2)
    assert "INSERT INTO mainline.lesson" in statements[0].sql
    assert "INSERT INTO mainline.propagation" in statements[1].sql


# ── the two impossible writes ────────────────────────────────────────────────


@pytest.mark.parametrize(
    "sql",
    [
        "INSERT INTO mainline.disposition (disposition_id) VALUES (%s)",
        "SELECT * FROM mainline.blocking_check",
        "UPDATE mainline.permit SET state = 'merged'",
        "INSERT INTO mainline.merge_record (permit_id) VALUES (%s)",
    ],
)
def test_a_statement_reaching_a_forbidden_object_is_refused(sql):
    with pytest.raises(ForbiddenWriteTarget):
        assert_fleet_safe(Statement(sql=sql))


@pytest.mark.parametrize(
    "sql",
    [
        "UPDATE mainline.merge_conflict SET resolved_commit = %s",
        "DELETE FROM mainline.merge_conflict WHERE conflict_id = %s",
    ],
)
def test_a_statement_mutating_merge_conflict_is_refused(sql):
    with pytest.raises(AgentWouldResolve):
        assert_fleet_safe(Statement(sql=sql))


def test_a_statement_assigning_a_resolution_column_is_refused():
    with pytest.raises(AgentWouldResolve, match="human-authenticated pgwire path"):
        assert_fleet_safe(
            Statement(sql="INSERT INTO mainline.resolution_log (resolution_sig) VALUES (%s)")
        )


def test_the_conflict_insert_names_no_resolution_column():
    statement = insert_merge_conflict(conflict())
    for column in ("resolved_commit", "resolved_by", "resolution_sig"):
        assert column not in statement.sql


# ── the memory needs a signature to have existed ─────────────────────────────


def test_remembering_a_resolution_requires_a_signed_one():
    origin = uuid.uuid5(uuid.NAMESPACE_OID, "origin")
    row = remember(conflict(), "the merged text a person approved", origin)
    signed = HumanResolution(
        conflict_id=origin,
        resolved_commit=COMMIT,
        resolved_by="person:site-superintendent",
        resolution_sig=SIGNATURE,
    )
    statement = insert_resolution_memory(row, signed)
    assert statement.params[4] == "the merged text a person approved"


def test_a_signature_for_a_different_conflict_is_refused():
    origin = uuid.uuid5(uuid.NAMESPACE_OID, "origin")
    row = remember(conflict(), "text", origin)
    wrong = HumanResolution(
        conflict_id=CONFLICT_ID,
        resolved_commit=COMMIT,
        resolved_by="person:site-superintendent",
        resolution_sig=SIGNATURE,
    )
    with pytest.raises(AgentWouldResolve, match="points at a different conflict"):
        insert_resolution_memory(row, wrong)


def test_a_weakening_is_refused_at_the_statement_boundary_too():
    # `Lesson` already refuses one, so this asserts the SECOND check: the one that
    # runs against the object about to be written rather than the object once built.
    import dataclasses

    from mainline_cherrypick import WeakeningWouldTravel
    from mainline_domain.contracts import ControlDelta

    smuggled = lesson()
    object.__setattr__(smuggled, "control_delta", ControlDelta.WEAKEN)
    with pytest.raises(WeakeningWouldTravel):
        insert_lesson(smuggled, delta_set_size=2)
    assert dataclasses.is_dataclass(smuggled)
