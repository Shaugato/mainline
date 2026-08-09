# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""Blame-origin resolution: the three states, the tie-break, and the fail-closed edge.

Every assertion here runs with no cluster.  ``resolve_origin`` is pure over one
view row, which is the whole reason the view returns a row rather than a verdict:
the *choice* of origin is expensive to test against a database and trivial to test
against a dataclass, so the choice lives in Python and the *candidate generation*
lives in SQL.
"""

from __future__ import annotations

import pytest
from _diachronic_fixtures import (
    AS_OF,
    commit,
    inert_origin_row,
    origin_row,
)
from mainline_domain.diachronic.errors import BlameClosureAbsent
from mainline_domain.diachronic.origin import (
    FIRST_PARENT_ANCESTRY_SQL,
    V_BLAME_ORIGIN_SQL,
    first_parent_chain,
    resolve_origin,
)
from mainline_domain.diachronic.version import ORIGIN_DEPTH_BOUND


def test_a_missing_closure_row_is_a_refusal_and_not_an_absence_of_blood():
    """P2: a gate may not read past an absent projection.

    This is the single most important assertion in the file.  If a missing
    ``clause_blame_current`` row resolved to "inert", then *deleting the
    projection* would be the cheapest way in the whole product to move a blame
    origin out of the gate's reach — cheaper than rewording the clause, and
    invisible in the clause's own history.
    """
    with pytest.raises(BlameClosureAbsent) as raised:
        resolve_origin(None)
    message = str(raised.value)
    assert "clause_blame_current" in message
    assert "max_severity = 0" in message


def test_a_closure_with_no_qualifying_blame_is_inert_and_the_origin_is_the_parent():
    row = inert_origin_row(as_of_gen=7, parent_version=commit("gen-6"))
    origin = resolve_origin(row, chain=[row.as_of_commit, commit("gen-6")])

    assert origin.state == "inert"
    assert origin.inert is True
    assert origin.origin_commit is None
    assert origin.baseline_commit == commit("gen-6")
    assert "inert" in origin.reason


def test_a_resolved_origin_carries_its_event_its_generation_and_its_depth():
    row = origin_row(as_of_gen=20, origin_gen=3)
    origin = resolve_origin(row, chain=[row.as_of_commit, commit("gen-0")])

    assert origin.state == "resolved"
    assert origin.origin_gen == 3
    assert origin.origin_depth == 17
    assert origin.origin_severity == 5
    assert origin.origin_event is not None
    assert origin.baseline_commit == commit("gen-0")
    assert origin.first_parent_verified is True
    assert origin.depth_bound_reached is False


def test_an_origin_off_the_first_parent_chain_is_kept_and_flagged():
    """The re-parenting attack, and why the conservative answer is the safe one.

    A merge commit has two parents.  If the origin could be *dropped* for failing
    chain verification, then merging a bloodless branch would produce a quieter
    delta — which is precisely what the merge would have been for.  So the
    candidate survives, the verdict can only get louder, and the flag tells the
    adjudicator why.
    """
    row = origin_row(as_of_gen=12, origin_gen=1)
    origin = resolve_origin(row, chain=[row.as_of_commit, commit("some-other-branch")])

    assert origin.state == "resolved"
    assert origin.origin_commit == commit("gen-0")
    assert origin.first_parent_verified is False
    assert "NOT on the first-parent chain" in origin.reason
    assert "quieter verdict" in origin.reason


def test_an_unwalked_chain_is_reported_unverified_rather_than_assumed_verified():
    row = origin_row()
    origin = resolve_origin(row, chain=None)

    assert origin.first_parent_verified is False
    assert "not walked" in origin.reason


def test_the_depth_bound_is_reported_when_it_is_reached():
    """Reaching the bound is fail-open, so it must be visible on the row."""
    row = origin_row(as_of_gen=ORIGIN_DEPTH_BOUND, origin_gen=0)
    origin = resolve_origin(row, chain=[row.as_of_commit, commit("gen-0")])

    assert origin.origin_depth == ORIGIN_DEPTH_BOUND
    assert origin.depth_bound_reached is True


def test_an_origin_that_is_the_parent_is_resolved_and_not_inert():
    """`resolved` and `origin_is_parent` are different facts and both are kept.

    A clause whose blood attached at the immediately preceding commit has a real
    origin — the two comparisons simply coincide today.  Reporting it as ``inert``
    would erase the blood from the record and make the next edit look like the
    first one that ever mattered.
    """
    parent = commit("gen-19")
    row = origin_row(as_of_gen=20, origin_gen=19, origin_commit=parent, parent_version=parent)
    origin = resolve_origin(row, chain=[row.as_of_commit, parent])

    assert origin.state == "resolved"
    assert origin.inert is False
    assert origin.origin_is_parent is True
    assert origin.baseline_commit == parent


def test_first_parent_chain_converts_driver_rows_without_caring_about_the_driver():
    rows = [(commit("a"), 0), (bytearray(commit("b")), 1)]
    assert first_parent_chain(rows) == frozenset({commit("a"), commit("b")})


def test_the_two_statements_are_parameterised_and_name_no_table_they_do_not_read():
    """A cheap shape check that catches the expensive mistakes.

    ``V_BLAME_ORIGIN_SQL`` must go through the view rather than re-deriving the
    join at the call site — a second copy of the origin rule is a second rule —
    and ``FIRST_PARENT_ANCESTRY_SQL`` must carry both the ``parent_ord = 0``
    restriction and the depth bound, because dropping either one turns a linear
    walk into the thing this design refused to put in a trigger.
    """
    assert "mainline.v_blame_origin" in V_BLAME_ORIGIN_SQL
    assert "%(clause_uuid)s" in V_BLAME_ORIGIN_SQL
    assert "%(as_of_commit)s" in V_BLAME_ORIGIN_SQL
    assert "JOIN" not in V_BLAME_ORIGIN_SQL.upper()

    assert "parent_ord = 0" in FIRST_PARENT_ANCESTRY_SQL
    assert "fp.depth < %(depth_bound)s" in FIRST_PARENT_ANCESTRY_SQL
    assert "UNION ALL" in FIRST_PARENT_ANCESTRY_SQL
    assert "AS OF SYSTEM TIME" not in FIRST_PARENT_ANCESTRY_SQL.upper()


def test_the_as_of_commit_round_trips_onto_the_verdict():
    row = origin_row(as_of_commit=AS_OF)
    origin = resolve_origin(row, chain=[AS_OF])
    assert origin.as_of_commit == AS_OF
    assert origin.clause_uuid == row.clause_uuid
