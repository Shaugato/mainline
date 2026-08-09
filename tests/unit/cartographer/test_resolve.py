# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
"""Following a blame pointer, and the four ways it refuses.

Every test here is a refusal test except two. That ratio is the product: the resolver's
job is not to produce an ancestry, it is to be unable to produce a *wrong* one.
"""

from __future__ import annotations

import dataclasses
from datetime import UTC, datetime

import pytest
from corpus import CLAUSE_ISOLATION, COMMIT_HEX, FATALITY_ID, NEAR_MISS_ID, SITE
from mainline_cartographer import (
    AncestryUnresolvable,
    BlameClosureAbsent,
    BlameEdgeRow,
    ClosureInconsistent,
    ClosureMismatch,
    EventRow,
    InferenceActivated,
    StaleClosure,
    order_ancestry,
    resolve_blame_pointer,
)
from mainline_cartographer.types import BlameBasis, BlameState


def test_absent_closure_refuses_rather_than_reporting_no_ancestry(fatality, near_miss):
    """P3. 'We do not know the ancestry' and 'there is no ancestry' must not look alike."""
    with pytest.raises(BlameClosureAbsent) as caught:
        resolve_blame_pointer(
            clause_uuid=CLAUSE_ISOLATION,
            as_of_commit=COMMIT_HEX,
            closure=None,
            events=[fatality, near_miss],
        )
    # The sentence is shared with fn_check_project so one grep finds both sides.
    assert BlameClosureAbsent.SQL_MESSAGE in str(caught.value)


def test_resolves_ancestry_worst_first_then_earliest(closure, fatality, near_miss):
    resolved = resolve_blame_pointer(
        clause_uuid=CLAUSE_ISOLATION,
        as_of_commit=COMMIT_HEX,
        closure=closure,
        events=[near_miss, fatality],
    )
    assert [event.event_id for event in resolved.ancestry] == [FATALITY_ID, NEAR_MISS_ID]
    headline = resolved.headline()
    assert headline is not None
    assert headline.event_id == FATALITY_ID
    assert resolved.ancestry_complete is True
    assert resolved.over_banded is False
    # The projections are carried verbatim; nothing here re-bands them.
    assert resolved.max_severity == closure.max_severity
    assert resolved.virulence is closure.virulence


def test_truncated_closure_is_visible_in_the_result(closure, fatality, near_miss):
    """A truncated closure must never be indistinguishable from a complete one."""
    truncated = dataclasses.replace(closure, truncated=True)
    resolved = resolve_blame_pointer(
        clause_uuid=CLAUSE_ISOLATION,
        as_of_commit=COMMIT_HEX,
        closure=truncated,
        events=[fatality, near_miss],
    )
    assert resolved.ancestry_complete is False
    assert resolved.to_mapping()["ancestry_complete"] is False


def test_unresolvable_ancestor_refuses(closure, fatality):
    with pytest.raises(AncestryUnresolvable) as caught:
        resolve_blame_pointer(
            clause_uuid=CLAUSE_ISOLATION,
            as_of_commit=COMMIT_HEX,
            closure=closure,
            events=[fatality],
        )
    assert caught.value.missing == (NEAR_MISS_ID,)


def test_projection_below_observed_severity_refuses(closure, fatality, near_miss):
    """Under-banding is the unsafe direction: it would demand a weaker clearance."""
    stale = dataclasses.replace(closure, max_severity=3)
    with pytest.raises(StaleClosure) as caught:
        resolve_blame_pointer(
            clause_uuid=CLAUSE_ISOLATION,
            as_of_commit=COMMIT_HEX,
            closure=stale,
            events=[fatality, near_miss],
        )
    assert caught.value.projected == 3
    assert caught.value.observed == 5
    assert caught.value.event_id == FATALITY_ID


def test_projection_above_observed_is_flagged_not_refused(closure, near_miss):
    """Over-banding fails safe — a signed downgrade after the closure produces exactly this."""
    only_near_miss = dataclasses.replace(closure, ancestor_events=(NEAR_MISS_ID,), ancestor_count=1)
    resolved = resolve_blame_pointer(
        clause_uuid=CLAUSE_ISOLATION,
        as_of_commit=COMMIT_HEX,
        closure=only_near_miss,
        events=[near_miss],
    )
    assert resolved.over_banded is True
    assert resolved.max_severity == 5


def test_closure_for_a_different_clause_version_refuses(closure, fatality, near_miss):
    with pytest.raises(ClosureMismatch):
        resolve_blame_pointer(
            clause_uuid="bbbbbbbb-0000-0000-0000-0000000000ff",
            as_of_commit=COMMIT_HEX,
            closure=closure,
            events=[fatality, near_miss],
        )


def test_ancestor_count_disagreeing_with_the_array_refuses(closure, fatality, near_miss):
    with pytest.raises(ClosureInconsistent):
        resolve_blame_pointer(
            clause_uuid=CLAUSE_ISOLATION,
            as_of_commit=COMMIT_HEX,
            closure=dataclasses.replace(closure, ancestor_count=7),
            events=[fatality, near_miss],
        )


def test_duplicate_ancestor_ids_refuse(closure, fatality, near_miss):
    with pytest.raises(ClosureInconsistent):
        resolve_blame_pointer(
            clause_uuid=CLAUSE_ISOLATION,
            as_of_commit=COMMIT_HEX,
            closure=dataclasses.replace(
                closure,
                ancestor_events=(FATALITY_ID, FATALITY_ID, NEAR_MISS_ID),
                ancestor_count=3,
            ),
            events=[fatality, near_miss],
        )


def test_active_inferred_edge_refuses_on_read(closure, fatality, near_miss):
    """The DDL forbids storing it; this is the assertion that survives a dropped constraint."""
    rogue = BlameEdgeRow(
        event_id="aaaaaaaa-0000-0000-0000-0000000000aa",
        clause_uuid=CLAUSE_ISOLATION,
        basis=BlameBasis.INFERRED_SEMANTIC,
        state=BlameState.ACTIVE,
    )
    with pytest.raises(InferenceActivated):
        resolve_blame_pointer(
            clause_uuid=CLAUSE_ISOLATION,
            as_of_commit=COMMIT_HEX,
            closure=closure,
            events=[fatality, near_miss],
            edges=[rogue],
        )


def test_inferred_edge_inside_the_closure_refuses(closure, fatality, near_miss):
    """An inferred edge may never raise clause_blame_closure.max_severity."""
    laundered = BlameEdgeRow(
        event_id=FATALITY_ID,
        clause_uuid=CLAUSE_ISOLATION,
        basis=BlameBasis.INFERRED_SEMANTIC,
        state=BlameState.PROVISIONAL,
    )
    with pytest.raises(InferenceActivated):
        resolve_blame_pointer(
            clause_uuid=CLAUSE_ISOLATION,
            as_of_commit=COMMIT_HEX,
            closure=closure,
            events=[fatality, near_miss],
            edges=[laundered],
        )


def test_excluded_inferred_links_are_reported(closure, fatality, near_miss, inferred_edge):
    """'We found something and declined to count it' is a statement, not a silence."""
    resolved = resolve_blame_pointer(
        clause_uuid=CLAUSE_ISOLATION,
        as_of_commit=COMMIT_HEX,
        closure=closure,
        events=[fatality, near_miss],
        edges=[inferred_edge],
    )
    assert resolved.excluded_inferred == (inferred_edge.event_id,)


def test_model_rated_severity_cannot_arm_the_gate():
    """CHECK model_cannot_arm, re-imposed in the constructor."""
    with pytest.raises(ValueError, match="model_rated"):
        EventRow(
            event_id=FATALITY_ID,
            site_id=SITE,
            occurred_at=datetime(2019, 4, 17, tzinfo=UTC),
            kind="incident",
            title="t",
            narrative="n",
            source_sha256="ab" * 32,
            severity_gate=5,
            severity_basis="model_rated",
        )


def test_naive_timestamps_are_refused():
    with pytest.raises(ValueError, match="naive datetime"):
        EventRow(
            event_id=FATALITY_ID,
            site_id=SITE,
            occurred_at=datetime(2019, 4, 17),  # noqa: DTZ001 - the point of the test
            kind="incident",
            title="t",
            narrative="n",
            source_sha256="ab" * 32,
            severity_gate=1,
            severity_basis="coded_field",
        )


def test_order_is_total_and_stable(fatality, near_miss):
    twice = order_ancestry([near_miss, fatality])
    again = order_ancestry([fatality, near_miss])
    assert twice == again
