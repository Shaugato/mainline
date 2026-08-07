# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""IX-01 — red before green: the plan assertion must fail, for the right reason, on demand.

PL-2 in one module. For a product whose deliverable is a refusal, an assertion that has never
failed asserts nothing — so every good fixture here has a bad twin, and each bad twin fails
for its **own** reason:

* ``arm_full_scan`` — no ``vector search`` node at all;
* ``arm_wrong_index`` — a vector search on a different index;
* ``arm_empty_prefix_spans`` — a vector search whose prefix was not constrained;
* ``arm_vector_search_with_full_scan_beside_it`` — a vector search that is real, next to a
  scan that reads the whole table. This is the fixture that catches the assertion everyone
  writes first: *"does the plan contain the words 'vector search'?"*

The digest tests are the other half. ``index_plan_digest`` must be stable against things that
move on their own (row counts, spans, statistics) and sensitive to the thing an auditor cares
about (which index was read). A digest that changes whenever the table grows will be ignored
the first time it changes for no reason, and an ignored tripwire is not a tripwire.

No cluster is involved. These fixtures are hand-written from the documented fragment and
prove our assertions have teeth — they are not, and are never described as, evidence about
CockroachDB's output. That claim belongs to IX-02 and IX-03.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from _support import FIXTURES
from trappoint_recall.arms import (
    assert_arm_plan,
    assert_arm_set_plan,
    index_plan_digest,
    parse_explain,
    plan_skeleton,
    skeleton_text,
)

pytestmark = pytest.mark.shape

PLANS = FIXTURES / "plans"
SCOPED_REF = "event_cue_embedding@cue_scoped_idx"
SWEEP_REF = "event_cue_coarse@cue_sweep_idx"


def _plan(name: str):
    path: Path = PLANS / f"{name}.txt"
    assert path.is_file(), f"missing plan fixture {path}"
    return parse_explain(path.read_text(encoding="utf-8"))


# ── green ────────────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("fixture", ["arm_indexed_flat", "arm_indexed_tree"])
def test_ix01_a_constrained_arm_passes_in_both_renderings(fixture: str) -> None:
    """CockroachDB prints plans flat or as a glyph tree depending on depth. Both must parse."""
    assertion = assert_arm_plan(
        _plan(fixture), expected_index_ref=SCOPED_REF, arm_id=fixture, expected_target_count=12
    )
    assert assertion.ok, assertion.failures
    assert assertion.vector_search_present
    assert assertion.index_matches
    assert assertion.target_count == 12
    assert assertion.target_count_matches
    assert assertion.prefix_spans_nonempty
    assert not assertion.full_scan_present


def test_ix01_the_sweep_passes_with_its_single_prefix_span() -> None:
    assertion = assert_arm_plan(
        _plan("sweep_indexed"),
        expected_index_ref=SWEEP_REF,
        arm_id="sweep",
        expected_target_count=24,
    )
    assert assertion.ok, assertion.failures


def test_ix01_a_union_of_three_constrained_arms_passes() -> None:
    assertion = assert_arm_set_plan(
        _plan("union_three_arms"),
        expected_arm_count=3,
        expected_index_refs=(SCOPED_REF, SWEEP_REF),
    )
    assert assertion.ok, assertion.failures
    assert assertion.vector_search_count == 3
    assert assertion.all_prefix_spans_nonempty


# ── red, one distinct reason each ────────────────────────────────────────────────────────


def test_ix01_red_no_vector_search_node_is_refused() -> None:
    assertion = assert_arm_plan(
        _plan("arm_full_scan"), expected_index_ref=SCOPED_REF, arm_id="scan"
    )
    assert not assertion.ok
    assert not assertion.vector_search_present
    assert any("no `vector search` node" in f for f in assertion.failures)
    assert assertion.full_scan_present


def test_ix01_red_a_vector_search_on_the_wrong_index_is_refused() -> None:
    assertion = assert_arm_plan(
        _plan("arm_wrong_index"), expected_index_ref=SCOPED_REF, arm_id="wrong"
    )
    assert not assertion.ok
    assert assertion.vector_search_present, "the node IS there — that is what makes it subtle"
    assert not assertion.index_matches
    assert any("expected" in f and "cue_experimental_idx" in f for f in assertion.failures)


def test_ix01_red_empty_prefix_spans_are_refused() -> None:
    assertion = assert_arm_plan(
        _plan("arm_empty_prefix_spans"), expected_index_ref=SCOPED_REF, arm_id="unconstrained"
    )
    assert not assertion.ok
    assert assertion.vector_search_present
    assert assertion.index_matches
    assert not assertion.prefix_spans_nonempty
    assert any("prefix spans" in f for f in assertion.failures)


def test_ix01_red_a_full_scan_beside_a_real_vector_search_is_refused() -> None:
    """The assertion everybody writes first would pass this plan. This one must not."""
    plan = _plan("arm_vector_search_with_full_scan_beside_it")
    assertion = assert_arm_plan(plan, expected_index_ref=SCOPED_REF, arm_id="mixed")
    assert assertion.vector_search_present
    assert assertion.index_matches
    assert assertion.prefix_spans_nonempty
    assert assertion.full_scan_present
    assert not assertion.ok, (
        "a plan can contain a perfectly good vector search AND read the whole table beside "
        "it; the arm that looked proven is the arm that scans"
    )
    assert any("FULL SCAN" in f for f in assertion.failures)


def test_ix01_red_a_union_missing_an_arm_is_refused() -> None:
    assertion = assert_arm_set_plan(
        _plan("union_three_arms"),
        expected_arm_count=13,
        expected_index_refs=(SCOPED_REF, SWEEP_REF),
    )
    assert not assertion.ok
    assert any("13 arms" in f for f in assertion.failures), assertion.failures


def test_ix01_red_exact_target_count_can_be_required_once_observed() -> None:
    """Off by default and honest about why; the switch itself must work."""
    plan = _plan("arm_indexed_flat")
    lenient = assert_arm_plan(plan, expected_index_ref=SCOPED_REF, expected_target_count=99)
    assert lenient.ok
    assert not lenient.target_count_matches
    strict = assert_arm_plan(
        plan,
        expected_index_ref=SCOPED_REF,
        expected_target_count=99,
        require_exact_target_count=True,
    )
    assert not strict.ok
    assert any("target count" in f for f in strict.failures)


# ── the digest ───────────────────────────────────────────────────────────────────────────


def test_ix01_skeleton_holds_node_types_and_index_names_and_nothing_else() -> None:
    skeleton = plan_skeleton(_plan("arm_indexed_tree"))
    joined = "\n".join(skeleton)
    assert "vector search" in joined
    assert "cue_scoped_idx" in joined
    for excluded in ("estimated row count", "target count", "prefix spans", "12", "equality"):
        assert excluded not in joined, (
            f"{excluded!r} leaked into the plan skeleton. The digest must be stable against "
            "statistics and against per-permit literals, or it will be ignored the first time "
            "it changes for a reason nobody cares about."
        )


def test_ix01_digest_ignores_row_counts_and_statistics() -> None:
    text = (PLANS / "arm_indexed_tree.txt").read_text(encoding="utf-8")
    grown = text.replace("estimated row count: 12", "estimated row count: 4,000,000")
    assert index_plan_digest(parse_explain(text)) == index_plan_digest(parse_explain(grown)), (
        "the corpus growing must not move the plan digest"
    )


def test_ix01_digest_ignores_the_per_permit_prefix_spans() -> None:
    text = (PLANS / "arm_indexed_flat.txt").read_text(encoding="utf-8")
    other_permit = text.replace("recurrence_test'", "mechanism'").replace("6f2c…", "0000…")
    assert index_plan_digest(parse_explain(text)) == index_plan_digest(parse_explain(other_permit))


def test_ix01_digest_moves_when_the_index_changes() -> None:
    good = index_plan_digest(_plan("arm_indexed_flat"))
    wrong = index_plan_digest(_plan("arm_wrong_index"))
    assert good != wrong, (
        "the one thing the digest exists to detect is the plan reading a different index"
    )


def test_ix01_digest_moves_when_a_node_disappears() -> None:
    assert index_plan_digest(_plan("arm_indexed_tree")) != index_plan_digest(
        _plan("arm_indexed_flat")
    )


def test_ix01_digest_covers_every_plan_in_a_per_arm_sequence() -> None:
    """A run that asserted its arms one at a time must not be able to drop one silently."""
    all_three = [_plan("arm_indexed_flat"), _plan("arm_indexed_tree"), _plan("sweep_indexed")]
    missing_one = all_three[:2]
    assert index_plan_digest(all_three) != index_plan_digest(missing_one)
    reordered = [all_three[1], all_three[0], all_three[2]]
    assert index_plan_digest(all_three) != index_plan_digest(reordered), (
        "arm order is part of what was attested; reordering must be visible"
    )


def test_ix01_digest_is_reproducible_by_a_stranger() -> None:
    """A digest nobody else can recompute is a number, not evidence."""
    import hashlib

    from trappoint_recall.arms import PLAN_DIGEST_DOMAIN

    plans = [_plan("arm_indexed_flat"), _plan("sweep_indexed")]
    by_hand = hashlib.sha256(PLAN_DIGEST_DOMAIN + skeleton_text(plans).encode("utf-8")).digest()
    assert by_hand == index_plan_digest(plans)
    assert len(by_hand) == 32


def test_ix01_refusing_to_digest_nothing() -> None:
    with pytest.raises(ValueError, match="empty plan set"):
        index_plan_digest([])
