# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""**The red test for W7** (``docs/leads/algorithms.md`` §3, order 7).

    a cosine-0.97 candidate with a conflicting equipment tag must be
    **rejected**, not accepted

Rejected, not down-weighted.  The distinction is the whole point.  A
down-weighted candidate is still in the pool, still assignable by W8's LAP if
nothing better turns up, and still able to carry blame onto a clause about a
different pump.  A rejected candidate is gone from the pool and its rejection
is a recorded row — so the ancestor it would have absorbed stays unmatched, and
an unmatched blood-written ancestor is a blocking residue row, which is a
louder gate than the wrong match would ever have been.

This suite also pins the two properties that make the veto trustworthy rather
than incidental:

* the veto fires **before** the score is consulted — an incompatible pair is
  never scored, so no threshold change can resurrect it; and
* a missing anchor set **raises** instead of defaulting to compatible.  P2: a
  projection is enforced, never trusted, and a veto that fails open is not a
  veto.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence

import pytest
from mainline_domain.anchors import extract_anchors
from mainline_domain.contracts import AnchorSet, Candidate
from mainline_domain.identity.candidates.records import ClauseRef, StageResult
from mainline_domain.identity.candidates.semantic import (
    Arm,
    MissingAnchorSetError,
    arms_for,
    semantic_stage,
)

SITE = uuid.UUID("11111111-1111-4111-8111-111111111111")
ACTIVITY = "maintenance/mechanical-isolation"

# The descendant under test: a clause about pump P-101A.
DESCENDANT_TEXT = (
    "Before breaking containment the authorised person shall isolate pump P-101A "
    "at ISOL-4471 and verify zero energy at PIT-1204."
)

# The trap: near-identical prose about a DIFFERENT pump.  Any embedding model
# worth using scores this pair very high, because structurally it is the same
# sentence.  That is precisely the dominant failure mode anchors exist to kill.
CONFLICTING_ANCESTOR_TEXT = (
    "Before breaking containment the authorised person shall isolate pump P-101B "
    "at ISOL-4471 and verify zero energy at PIT-1204."
)

# The control: the same pump, genuinely paraphrased.
COMPATIBLE_ANCESTOR_TEXT = (
    "Prior to breaking containment the authorised person must isolate pump P-101A "
    "at ISOL-4471 and confirm zero energy at PIT-1204."
)

CONFLICTING = ClauseRef(uuid.UUID("22222222-2222-4222-8222-222222222222"), b"\xaa" * 32)
COMPATIBLE = ClauseRef(uuid.UUID("33333333-3333-4333-8333-333333333333"), b"\xbb" * 32)


class _FixedRunner:
    """A :class:`PrefixArmRunner` that returns committed scores.

    No model call, no cluster: the cosines are the fixture.  What is under test
    is what the stage *does* with a 0.97, not whether an embedding produces one.
    """

    def __init__(self, hits: Sequence[Candidate]) -> None:
        self._hits = tuple(hits)
        self.calls: list[tuple[uuid.UUID, str, int, int]] = []

    def ann(
        self,
        site_id: uuid.UUID,
        activity_root: str,
        q: Sequence[float],
        k: int,
    ) -> Sequence[Candidate]:
        self.calls.append((site_id, activity_root, len(q), k))
        return self._hits[:k]


def _hit(ref: ClauseRef, cosine: float) -> Candidate:
    return Candidate(
        ancestor_clause_uuid=ref.clause_uuid,
        ancestor_commit=ref.commit_id,
        stage="S4",
        score=cosine,
        features={"cosine": cosine},
    )


@pytest.fixture
def anchors() -> dict[tuple[uuid.UUID, bytes], AnchorSet]:
    return {
        (CONFLICTING.clause_uuid, CONFLICTING.commit_id): extract_anchors(
            CONFLICTING_ANCESTOR_TEXT
        ),
        (COMPATIBLE.clause_uuid, COMPATIBLE.commit_id): extract_anchors(COMPATIBLE_ANCESTOR_TEXT),
    }


def _run(
    hits: Sequence[Candidate],
    anchors: dict[tuple[uuid.UUID, bytes], AnchorSet],
) -> tuple[_FixedRunner, StageResult]:
    runner = _FixedRunner(hits)
    result = semantic_stage(
        query_anchors=extract_anchors(DESCENDANT_TEXT),
        query_embedding=[0.0] * 8,
        arms=arms_for(SITE, [ACTIVITY]),
        runner=runner,
        k=16,
        anchors_of=lambda cu, ci: anchors[(cu, ci)],
    )
    return runner, result


def test_the_fixture_really_is_an_anchor_conflict(
    anchors: dict[tuple[uuid.UUID, bytes], AnchorSet],
) -> None:
    """Guard the guard: if extraction stopped seeing the tags this suite is theatre."""
    query = extract_anchors(DESCENDANT_TEXT)
    conflicting = anchors[(CONFLICTING.clause_uuid, CONFLICTING.commit_id)]
    compatible = anchors[(COMPATIBLE.clause_uuid, COMPATIBLE.commit_id)]

    assert "P-101A" in {a.norm for a in query.items}
    assert "P-101B" in {a.norm for a in conflicting.items}
    assert not query.compatible_with(conflicting)
    assert query.compatible_with(compatible)


def test_cosine_097_with_a_conflicting_equipment_tag_is_rejected(
    anchors: dict[tuple[uuid.UUID, bytes], AnchorSet],
) -> None:
    """The exit criterion.  0.97 is not enough, and it is not *nearly* enough."""
    _, result = _run([_hit(CONFLICTING, 0.97), _hit(COMPATIBLE, 0.71)], anchors)

    emitted = {c.ancestor_clause_uuid for c in result.candidates}
    assert CONFLICTING.clause_uuid not in emitted, (
        "a candidate whose equipment tag conflicts with the query was emitted at "
        "cosine 0.97 — the anchor veto did not fire, so a clause about P-101B is "
        "in the pool for a clause about P-101A"
    )


def test_the_rejection_is_recorded_with_its_arithmetic(
    anchors: dict[tuple[uuid.UUID, bytes], AnchorSet],
) -> None:
    """Dropped, not disappeared.  W8 cannot account for what it cannot see."""
    _, result = _run([_hit(CONFLICTING, 0.97), _hit(COMPATIBLE, 0.71)], anchors)

    dropped = [d for d in result.dropped if d.ancestor_clause_uuid == CONFLICTING.clause_uuid]
    assert len(dropped) == 1, "the conflicting candidate left no record of its rejection"
    record = dropped[0]
    assert record.reason == "anchor_conflict"
    assert record.stage == "S4"
    assert record.detail["cosine"] == pytest.approx(0.97)
    assert record.detail["conflicting_class_count"] >= 1.0
    assert "equipment_tag" in record.note


def test_an_incompatible_candidate_is_never_scored(
    anchors: dict[tuple[uuid.UUID, bytes], AnchorSet],
) -> None:
    """The veto runs before the band, so no threshold move can resurrect the pair.

    Proven by construction: a cosine *below* the auto-reject band is dropped
    for ``anchor_conflict``, not for ``auto_reject``.  If the stage had scored
    first, this pair would have been dropped for the score.
    """
    _, result = _run([_hit(CONFLICTING, 0.10)], anchors)

    reasons = {d.reason for d in result.dropped}
    assert reasons == {"anchor_conflict"}


def test_a_compatible_candidate_below_the_band_is_dropped_as_auto_reject(
    anchors: dict[tuple[uuid.UUID, bytes], AnchorSet],
) -> None:
    """The other half of the same proof: compatible pairs *are* judged on score."""
    _, result = _run([_hit(COMPATIBLE, 0.42)], anchors)

    assert result.candidates == ()
    assert [d.reason for d in result.dropped] == ["auto_reject"]


def test_a_compatible_candidate_above_the_band_survives(
    anchors: dict[tuple[uuid.UUID, bytes], AnchorSet],
) -> None:
    _, result = _run([_hit(COMPATIBLE, 0.94)], anchors)

    assert [c.ancestor_clause_uuid for c in result.candidates] == [COMPATIBLE.clause_uuid]


def test_a_missing_anchor_set_raises_rather_than_defaulting_to_compatible() -> None:
    """P2.  A veto that fails open when its input is absent is not a veto."""
    runner = _FixedRunner([_hit(CONFLICTING, 0.97)])

    def _no_anchors(clause_uuid: uuid.UUID, commit_id: bytes) -> AnchorSet:
        raise KeyError((clause_uuid, commit_id))

    with pytest.raises(MissingAnchorSetError) as excinfo:
        semantic_stage(
            query_anchors=extract_anchors(DESCENDANT_TEXT),
            query_embedding=[0.0] * 8,
            arms=arms_for(SITE, [ACTIVITY]),
            runner=runner,
            k=16,
            anchors_of=_no_anchors,
        )
    assert str(CONFLICTING.clause_uuid) in str(excinfo.value)


def test_one_arm_per_activity_root_and_every_arm_fully_constrained(
    anchors: dict[tuple[uuid.UUID, bytes], AnchorSet],
) -> None:
    """C-SPANN's prefix rule, expressed in the call pattern rather than in a comment."""
    roots = ["maintenance/mechanical-isolation", "operations/permit-to-work"]
    runner = _FixedRunner([_hit(COMPATIBLE, 0.95)])
    semantic_stage(
        query_anchors=extract_anchors(DESCENDANT_TEXT),
        query_embedding=[0.0] * 8,
        arms=arms_for(SITE, roots),
        runner=runner,
        k=8,
        anchors_of=lambda cu, ci: anchors[(cu, ci)],
    )
    assert [call[1] for call in runner.calls] == roots
    assert all(isinstance(call[1], str) and call[1] for call in runner.calls)


def test_arms_for_deduplicates_and_refuses_an_empty_root() -> None:
    arms = arms_for(SITE, ["a", "b", "a"])
    assert arms == (Arm(SITE, "a"), Arm(SITE, "b"))
    with pytest.raises(ValueError, match="activity_root"):
        arms_for(SITE, ["a", ""])
