# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
"""The lifecycle, the falsifiable no, and the column git's rerere does not have."""

from __future__ import annotations

import dataclasses
import uuid
from datetime import UTC, datetime

import pytest
from cherrypick_corpus import (
    BASE_TEXT,
    CONFLICT_ID,
    FLEET_TEXT,
    LOCAL_CLAUSE,
    SITE_TEXT,
    WAIVER_EXPIRY,
    conflict,
    mechanism_absent,
    mitigated,
    propagation,
    waiver,
)
from mainline_cherrypick import (
    AdoptionNotClean,
    AgentWouldResolve,
    Declination,
    DeclinationNotFalsifiable,
    HumanResolution,
    IllegalPropagationTransition,
    PropState,
    RecalledResolution,
    RecalledResolutionOffered,
    ResolutionMemoryRow,
    advance,
    conflicts_from_merge,
    decline,
    merge3,
    recall,
    remember,
    reopen_expired_waiver,
)

ADOPT_COMMIT = bytes.fromhex("c3" * 32)
AFTER_EXPIRY = datetime(2026, 10, 1, tzinfo=UTC)
BEFORE_EXPIRY = datetime(2026, 8, 1, tzinfo=UTC)


# ── the lifecycle ────────────────────────────────────────────────────────────


def test_a_clean_proposal_can_be_adopted():
    result = advance(propagation(), PropState.ADOPTED, adopted_commit=ADOPT_COMMIT)
    assert result.state is PropState.ADOPTED
    assert result.adopted_commit == ADOPT_COMMIT


def test_adoption_with_open_conflicts_is_refused():
    with pytest.raises(AdoptionNotClean, match="1 open conflict"):
        advance(propagation(open_conflicts=1), PropState.ADOPTED, adopted_commit=ADOPT_COMMIT)


def test_adoption_without_a_commit_is_refused():
    with pytest.raises(AdoptionNotClean, match="no adopted_commit"):
        advance(propagation(), PropState.ADOPTED)


def test_an_adopted_propagation_cannot_be_quietly_undone():
    adopted = advance(propagation(), PropState.ADOPTED, adopted_commit=ADOPT_COMMIT)
    with pytest.raises(IllegalPropagationTransition, match="'adopted' → 'proposed'"):
        advance(adopted, PropState.PROPOSED)


def test_revoked_is_terminal():
    revoked = advance(propagation(), PropState.REVOKED)
    with pytest.raises(IllegalPropagationTransition):
        advance(revoked, PropState.ADOPTED)


def test_already_present_must_name_the_local_clause():
    # Convergent evolution is evidence FOR the lesson, and it is only evidence if
    # it says which local clause converged.
    with pytest.raises(ValueError, match="strongest datum"):
        propagation(state=PropState.ALREADY_PRESENT)
    ok = propagation(state=PropState.ALREADY_PRESENT, already_present_clause=LOCAL_CLAUSE)
    assert ok.already_present_clause == LOCAL_CLAUSE


# ── the falsifiable no ───────────────────────────────────────────────────────


def test_declining_records_the_answer_rather_than_closing_the_item():
    declined = decline(propagation(), mechanism_absent())
    assert declined.state is PropState.DECLINED
    assert declined.declination is not None
    assert declined.declination.predicate_id is not None


def test_a_decline_with_no_declination_is_mandated_conformity_failing_quietly():
    with pytest.raises(ValueError, match="citable the next time"):
        propagation(state=PropState.DECLINED)


@pytest.mark.parametrize(
    ("kind", "missing"),
    [
        ("mitigated", "already_present_clause"),
        ("waiver", "declination_expires_at"),
        ("mechanism_absent", "declination_predicate_id"),
    ],
)
def test_every_declination_kind_carries_its_own_falsifier(kind, missing):
    with pytest.raises(DeclinationNotFalsifiable, match=missing):
        Declination(kind=kind)  # type: ignore[arg-type]


def test_the_three_well_formed_declinations_construct():
    assert mitigated().already_present_clause == LOCAL_CLAUSE
    assert waiver().expires_at == WAIVER_EXPIRY
    assert mechanism_absent().predicate_id is not None


def test_a_bounded_window_means_bounded():
    assert not waiver().expired(BEFORE_EXPIRY)
    assert waiver().expired(AFTER_EXPIRY)


def test_an_expired_waiver_reopens_the_propagation():
    declined = decline(propagation(), waiver())
    reopened = reopen_expired_waiver(declined, AFTER_EXPIRY)
    assert reopened is not None
    assert reopened.state is PropState.PROPOSED
    assert reopened.declination is None


def test_an_unexpired_waiver_is_left_alone():
    declined = decline(propagation(), waiver())
    assert reopen_expired_waiver(declined, BEFORE_EXPIRY) is None


def test_a_mechanism_absent_declination_never_expires_on_a_clock():
    # It is falsified by its predicate becoming true, not by a date passing.
    declined = decline(propagation(), mechanism_absent())
    assert reopen_expired_waiver(declined, AFTER_EXPIRY) is None


# ── conflicts ────────────────────────────────────────────────────────────────


def test_a_conflicted_merge_opens_one_row_per_clause_not_one_per_region():
    result = merge3(BASE_TEXT, SITE_TEXT, FLEET_TEXT)
    rows = conflicts_from_merge(
        result,
        conflict_id=CONFLICT_ID,
        lesson_id=propagation().lesson_id,
        site_id=propagation().site_id,
        clause_uuid=conflict().clause_uuid,
        base_digest=conflict().base_digest,
        ours_digest=conflict().ours_digest,
        theirs_digest=conflict().theirs_digest,
        opened_at=conflict().opened_at,
    )
    assert len(rows) == 1


def test_a_clean_merge_opens_nothing():
    result = merge3(BASE_TEXT, BASE_TEXT, FLEET_TEXT)
    rows = conflicts_from_merge(
        result,
        conflict_id=CONFLICT_ID,
        lesson_id=propagation().lesson_id,
        site_id=propagation().site_id,
        clause_uuid=conflict().clause_uuid,
        base_digest=conflict().base_digest,
        ours_digest=conflict().ours_digest,
        theirs_digest=conflict().theirs_digest,
        opened_at=conflict().opened_at,
    )
    assert rows == ()


def test_a_conflict_between_identical_renderings_is_refused():
    with pytest.raises(ValueError, match="no conflict here"):
        conflict(ours_digest=conflict().theirs_digest)


def test_a_merge_conflict_type_cannot_carry_a_resolution():
    from mainline_cherrypick import MergeConflict

    fields = {f.name for f in dataclasses.fields(MergeConflict)}
    assert not fields & {"resolved_commit", "resolved_by", "resolution_sig"}


# ── rerere, with recall ──────────────────────────────────────────────────────


def memory_row(**overrides) -> ResolutionMemoryRow:
    base = ResolutionMemoryRow(
        clause_uuid=conflict().clause_uuid,
        base_digest=conflict().base_digest,
        ours_digest=conflict().ours_digest,
        theirs_digest=conflict().theirs_digest,
        resolution_text="Isolation shall be applied at every point, locked and countersigned.",
        origin_conflict=uuid.uuid5(uuid.NAMESPACE_OID, "origin-conflict"),
    )
    return dataclasses.replace(base, **overrides)


def test_a_remembered_resolution_is_offered_and_never_applied():
    recalled = recall(conflict(), {memory_row().key: memory_row()})
    assert recalled is not None
    assert recalled.applied is False
    assert "countersigned" in recalled.text


def test_a_recalled_resolution_is_refused_loudly_rather_than_silently_missing():
    row = memory_row(recalled_at=datetime(2026, 6, 1, tzinfo=UTC))
    with pytest.raises(RecalledResolutionOffered, match="must not be offered again"):
        recall(conflict(), {row.key: row})


def test_a_different_conflict_shape_matches_nothing():
    other = conflict(theirs_digest=bytes.fromhex("ee" * 32))
    assert recall(other, {memory_row().key: memory_row()}) is None


def test_a_recalled_resolution_cannot_be_marked_applied():
    with pytest.raises(AgentWouldResolve, match="proposed, never auto-applied"):
        RecalledResolution(
            text="x",
            origin_conflict=uuid.uuid5(uuid.NAMESPACE_OID, "origin-conflict"),
            key=memory_row().key,
            applied=True,
        )


def test_remembering_requires_the_origin_conflict():
    row = remember(conflict(), "resolved text", uuid.uuid5(uuid.NAMESPACE_OID, "origin"))
    assert row.origin_conflict == uuid.uuid5(uuid.NAMESPACE_OID, "origin")
    assert row.recalled_at is None


def test_the_inherited_sites_query_joins_conflicts_to_propagations():
    from mainline_cherrypick import INHERITED_SITES_SQL

    assert "resolution_source" in INHERITED_SITES_SQL
    assert "mainline.propagation" in INHERITED_SITES_SQL
    assert "site_id" in INHERITED_SITES_SQL


def test_an_empty_remembered_resolution_is_refused():
    with pytest.raises(ValueError, match="propose nothing"):
        memory_row(resolution_text="   ")


# ── the signature boundary ───────────────────────────────────────────────────


def test_a_resolution_needs_a_signature():
    with pytest.raises(AgentWouldResolve, match="no signature"):
        HumanResolution(
            conflict_id=CONFLICT_ID,
            resolved_commit=ADOPT_COMMIT,
            resolved_by="person:site-superintendent",
            resolution_sig=b"",
        )


@pytest.mark.parametrize(
    "subject",
    ["agent_fleet", "svc_disposition", "mainline-site-adopter", "system:automation"],
)
def test_a_service_identity_cannot_sign_a_resolution(subject):
    with pytest.raises(AgentWouldResolve, match="service identity"):
        HumanResolution(
            conflict_id=CONFLICT_ID,
            resolved_commit=ADOPT_COMMIT,
            resolved_by=subject,
            resolution_sig=b"\x01" * 64,
        )


def test_a_person_can_sign():
    signed = HumanResolution(
        conflict_id=CONFLICT_ID,
        resolved_commit=ADOPT_COMMIT,
        resolved_by="person:site-superintendent",
        resolution_sig=b"\x01" * 64,
    )
    assert signed.resolved_by.startswith("person:")
