# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""The plan assertion itself, proven offline against committed plan text.

A plan assertion that has only ever been run against a passing plan asserts
nothing — it might be returning ``True`` unconditionally.  So each of the four
checks is exercised **in its failing direction** here, on plan text constructed
by hand, with no cluster involved.

The plan fragments below follow the shape CockroachDB's ``EXPLAIN`` prints for
a prefix-constrained vector search.  They are fixtures, not captures: no cluster
is reachable from the build machine, and that is recorded honestly rather than
papered over.  ``tests/integration/algorithms/candidates/`` runs the same
assertion against a real plan the moment a cluster exists — which is also the
test that would catch these fixtures being the wrong shape.
"""

from __future__ import annotations

import pytest
from mainline_domain.identity.candidates.explain import (
    assert_arm_plan,
    assert_arm_set_plans,
    parse_plan,
)

GOOD = """
distribution: local
vectorized: true

• vector search
  table: clause_embedding@ce_ann
  target count: 8
  prefix spans: [/1/'maintenance' - /1/'maintenance']
"""

NO_VECTOR_SEARCH = """
distribution: local

• sort
  order: +cosine_similarity
  │
  └── • filter
        filter: activity_root = 'maintenance'
        │
        └── • scan
              table: clause_embedding@primary
              spans: FULL SCAN
"""

EMPTY_PREFIX_SPANS = """
• vector search
  table: clause_embedding@ce_ann
  target count: 8
  prefix spans: []
"""

MISSING_PREFIX_SPANS = """
• vector search
  table: clause_embedding@ce_ann
  target count: 8
"""

WRONG_INDEX = """
• vector search
  table: event_cue_embedding@cue_scoped_idx
  target count: 8
  prefix spans: [/1/'maintenance' - /1/'maintenance']
"""

VECTOR_SEARCH_BESIDE_A_FULL_SCAN = """
• lookup join
  │
  ├── • vector search
  │     table: clause_embedding@ce_ann
  │     target count: 8
  │     prefix spans: [/1/'maintenance' - /1/'maintenance']
  │
  └── • scan
        table: clause_version@primary
        spans: FULL SCAN
"""


def test_a_good_plan_passes_all_four_checks() -> None:
    result = assert_arm_plan(GOOD)
    assert result.ok
    assert result.has_vector_search
    assert result.reads_expected_index
    assert result.prefix_constrained
    assert result.no_full_scan
    assert result.failures == ()


def test_a_plan_with_no_vector_search_is_refused() -> None:
    with pytest.raises(AssertionError, match="no `vector search` node"):
        assert_arm_plan(NO_VECTOR_SEARCH)


def test_empty_prefix_spans_are_refused() -> None:
    """The documented condition under which the vector index is NOT used."""
    with pytest.raises(AssertionError, match="not constrained to specific values"):
        assert_arm_plan(EMPTY_PREFIX_SPANS)


def test_absent_prefix_spans_are_refused() -> None:
    with pytest.raises(AssertionError, match="prefix spans are None"):
        assert_arm_plan(MISSING_PREFIX_SPANS)


def test_the_wrong_index_is_refused() -> None:
    """An arm that reads the recall domain's cue index is not this arm."""
    with pytest.raises(AssertionError, match="ce_ann"):
        assert_arm_plan(WRONG_INDEX)


def test_a_full_scan_beside_a_vector_search_is_refused() -> None:
    """The check that is easy to forget: the plan can look right and read everything."""
    result = assert_arm_plan(VECTOR_SEARCH_BESIDE_A_FULL_SCAN, raises=False)
    assert result.has_vector_search
    assert result.prefix_constrained
    assert not result.no_full_scan
    assert not result.ok
    with pytest.raises(AssertionError, match="FULL SCAN"):
        assert_arm_plan(VECTOR_SEARCH_BESIDE_A_FULL_SCAN)


def test_every_failure_is_reported_not_just_the_first() -> None:
    both_wrong = """
• vector search
  table: event_cue_embedding@cue_scoped_idx
  prefix spans: []
"""
    result = assert_arm_plan(both_wrong, raises=False)
    assert len(result.failures) == 2


def test_tree_glyphs_and_preamble_do_not_confuse_the_parser() -> None:
    nodes = parse_plan(VECTOR_SEARCH_BESIDE_A_FULL_SCAN)
    assert [n.node_type for n in nodes] == ["lookup join", "vector search", "scan"]
    assert nodes[1].table_ref == "clause_embedding@ce_ann"
    assert nodes[2].is_full_scan


def test_the_arm_set_assertion_names_every_bad_arm() -> None:
    with pytest.raises(AssertionError) as excinfo:
        assert_arm_set_plans([GOOD, EMPTY_PREFIX_SPANS, GOOD, NO_VECTOR_SEARCH])
    message = str(excinfo.value)
    assert "2 of 4 arms refused" in message
    assert "arm 1:" in message
    assert "arm 3:" in message


def test_a_healthy_arm_set_returns_one_result_per_arm() -> None:
    results = assert_arm_set_plans([GOOD, GOOD, GOOD])
    assert len(results) == 3
    assert all(r.ok for r in results)


def test_the_message_says_which_check_failed() -> None:
    result = assert_arm_plan(EMPTY_PREFIX_SPANS, raises=False)
    assert "arm plan REFUSED" in result.message()
    assert "prefix spans" in result.message()
