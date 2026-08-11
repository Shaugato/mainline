# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""``mainline.v_blame_origin`` against a real CockroachDB, on a DAG with a merge in it.

THE FIXTURE, DRAWN
------------------
::

        c0 ──► c1 ──► c2 ──┐
         │                 ├──► m          (m's first parent is c2; sb is parent_ord 1)
         └──► sb ──────────┘

Every test in this file builds that DAG for a fresh ``site_id``, so the tests share
a database and not a history.

WHAT IT IS FOR
--------------
``sb`` is the bloodless side branch, and ``m`` is the merge that would re-parent a
clause onto it.  A synchronic system diffing ``m`` against the clause's declared
``parent_version`` would compare against ``sb`` — a version with no blood — and
report a restatement.  The view resolves the origin from the clause's blood
regardless of what ``parent_version`` claims, and
``mainline_domain.diachronic.origin.FIRST_PARENT_ANCESTRY_SQL`` shows that ``sb``
is not on ``m``'s first-parent chain while ``c0`` is.

**Read the ``[origindiff]`` banner this suite prints.**  ``datamodel/dm-blame``'s
three objects had not landed when this was written, so the blame tables underneath
these assertions may be a transcription of ``ARCHITECTURE.md`` §5.4 rather than the
reviewed migration.  The banner says which, on every run.
"""

from __future__ import annotations

import pytest
from _diachronic_sql_support import (
    Commit,
    insert_blame_edge,
    insert_clause,
    insert_clause_version,
    insert_closure,
    insert_commit,
    insert_commit_edge,
    insert_doc,
    insert_event,
    plan_scans,
)
from mainline_domain.diachronic.errors import BlameClosureAbsent
from mainline_domain.diachronic.origin import (
    FIRST_PARENT_ANCESTRY_SQL,
    V_BLAME_ORIGIN_SQL,
    SqlBlameOriginSource,
    resolve_origin,
)
from mainline_domain.diachronic.version import ORIGIN_DEPTH_BOUND

pytestmark = pytest.mark.schema


class Dag:
    """The five commits above, already written, with their edges."""

    def __init__(self, conn, site_id) -> None:
        prefix = str(site_id)[:8]
        self.c0 = insert_commit(conn, site_id=site_id, label=f"{prefix}/c0", gen=0)
        self.c1 = insert_commit(conn, site_id=site_id, label=f"{prefix}/c1", gen=1)
        self.c2 = insert_commit(conn, site_id=site_id, label=f"{prefix}/c2", gen=2)
        self.sb = insert_commit(
            conn, site_id=site_id, label=f"{prefix}/sb", gen=1, ref_name="cr/MOC-9001"
        )
        self.m = insert_commit(conn, site_id=site_id, label=f"{prefix}/m", gen=3)
        insert_commit_edge(conn, child=self.c1, parent=self.c0, parent_ord=0)
        insert_commit_edge(conn, child=self.c2, parent=self.c1, parent_ord=0)
        insert_commit_edge(conn, child=self.sb, parent=self.c0, parent_ord=0)
        insert_commit_edge(conn, child=self.m, parent=self.c2, parent_ord=0)
        insert_commit_edge(conn, child=self.m, parent=self.sb, parent_ord=1)
        self.doc_id = insert_doc(conn, site_id=site_id, doc_code=f"PROC-{prefix}")


def _version(conn, *, site_id, dag: Dag, clause_uuid, commit: Commit, parent: Commit | None, sev):
    insert_clause_version(
        conn,
        site_id=site_id,
        doc_id=dag.doc_id,
        clause_uuid=clause_uuid,
        commit=commit,
        parent_version=None if parent is None else parent.commit_id,
        sev_max=sev,
    )


def _origin(conn, *, clause_uuid, as_of: Commit):
    return SqlBlameOriginSource(conn).origin_row(
        clause_uuid=clause_uuid, as_of_commit=as_of.commit_id
    )


# --------------------------------------------------------------------------- #


def test_the_origin_is_the_earliest_blood_bearing_version_not_the_declared_parent(conn, site_id):
    """The headline. ``parent_version`` points at the bloodless branch; the origin does not."""
    dag = Dag(conn, site_id)
    clause = insert_clause(conn, site_id=site_id, birth=dag.c0)
    fatality = insert_event(conn, site_id=site_id, label=f"{clause}-fatal", severity_gate=5)
    lesser = insert_event(conn, site_id=site_id, label=f"{clause}-minor", severity_gate=3)

    for commit, parent in (
        (dag.c0, None),
        (dag.c1, dag.c0),
        (dag.c2, dag.c1),
        (dag.sb, dag.c0),
        (dag.m, dag.sb),  # THE RE-PARENTING ATTEMPT
    ):
        _version(
            conn,
            site_id=site_id,
            dag=dag,
            clause_uuid=clause,
            commit=commit,
            parent=parent,
            sev=5,
        )

    insert_blame_edge(conn, site_id=site_id, clause_uuid=clause, event_id=fatality, commit=dag.c0)
    insert_blame_edge(conn, site_id=site_id, clause_uuid=clause, event_id=lesser, commit=dag.c1)
    for commit in (dag.c0, dag.c1, dag.c2, dag.sb, dag.m):
        insert_closure(
            conn,
            site_id=site_id,
            clause_uuid=clause,
            as_of=commit,
            max_severity=5,
            ancestor_events=[fatality],
        )

    row = _origin(conn, clause_uuid=clause, as_of=dag.m)
    assert row is not None
    assert row.origin_commit == dag.c0.commit_id
    assert row.origin_gen == 0
    assert row.origin_depth == 3
    assert row.origin_event == fatality
    assert row.origin_severity == 5
    assert row.origin_basis == "asserted_document"
    assert row.parent_version == dag.sb.commit_id
    assert row.origin_is_parent is False

    chain = SqlBlameOriginSource(conn).first_parent_commits(
        as_of_commit=dag.m.commit_id, depth_bound=ORIGIN_DEPTH_BOUND
    )
    assert dag.c0.commit_id in chain
    assert dag.c2.commit_id in chain
    assert dag.sb.commit_id not in chain, (
        "the second parent of a merge must not appear on the first-parent chain; if it "
        "does, a merge can re-parent a clause onto a bloodless line"
    )

    origin = resolve_origin(row, chain=chain)
    assert origin.state == "resolved"
    assert origin.first_parent_verified is True
    assert origin.baseline_commit == dag.c0.commit_id


def test_a_lower_severity_edge_never_defines_the_origin(conn, site_id):
    """The origin is where the severity that IS the maximum attached, not the first edge."""
    dag = Dag(conn, site_id)
    clause = insert_clause(conn, site_id=site_id, birth=dag.c0)
    minor = insert_event(conn, site_id=site_id, label=f"{clause}-minor", severity_gate=3)
    fatality = insert_event(conn, site_id=site_id, label=f"{clause}-fatal", severity_gate=5)

    for commit, parent in ((dag.c0, None), (dag.c1, dag.c0), (dag.c2, dag.c1)):
        _version(
            conn,
            site_id=site_id,
            dag=dag,
            clause_uuid=clause,
            commit=commit,
            parent=parent,
            sev=5,
        )
    insert_blame_edge(conn, site_id=site_id, clause_uuid=clause, event_id=minor, commit=dag.c0)
    insert_blame_edge(conn, site_id=site_id, clause_uuid=clause, event_id=fatality, commit=dag.c1)
    for commit in (dag.c0, dag.c1, dag.c2):
        insert_closure(
            conn,
            site_id=site_id,
            clause_uuid=clause,
            as_of=commit,
            max_severity=5,
            ancestor_events=[fatality],
        )

    row = _origin(conn, clause_uuid=clause, as_of=dag.c2)
    assert row is not None
    assert row.origin_commit == dag.c1.commit_id
    assert row.origin_gen == 1
    assert row.origin_event == fatality


def test_a_projected_and_clean_closure_appears_with_empty_origin_columns(conn, site_id):
    """The INERT case. Distinguishable from an absent projection, which is the point."""
    dag = Dag(conn, site_id)
    clause = insert_clause(conn, site_id=site_id, birth=dag.c0)
    for commit, parent in ((dag.c0, None), (dag.c1, dag.c0)):
        _version(
            conn,
            site_id=site_id,
            dag=dag,
            clause_uuid=clause,
            commit=commit,
            parent=parent,
            sev=0,
        )
        insert_closure(
            conn,
            site_id=site_id,
            clause_uuid=clause,
            as_of=commit,
            max_severity=0,
            virulence="routine",
        )

    row = _origin(conn, clause_uuid=clause, as_of=dag.c1)
    assert row is not None
    assert row.max_severity == 0
    assert row.origin_commit is None
    assert row.origin_gen is None
    assert row.origin_depth is None

    origin = resolve_origin(row, chain=[dag.c1.commit_id, dag.c0.commit_id])
    assert origin.inert is True
    assert origin.baseline_commit == dag.c0.commit_id


def test_an_unprojected_closure_produces_no_row_at_all_and_that_is_a_refusal(conn, site_id):
    """P2, end to end: the projection is missing, so the view is silent and Python raises.

    Reporting this as "no blood" would make DELETING THE PROJECTION the cheapest
    attack in the product — cheaper than rewording the clause, and invisible in the
    clause's own history.
    """
    dag = Dag(conn, site_id)
    clause = insert_clause(conn, site_id=site_id, birth=dag.c0)
    _version(conn, site_id=site_id, dag=dag, clause_uuid=clause, commit=dag.c0, parent=None, sev=0)

    row = _origin(conn, clause_uuid=clause, as_of=dag.c0)
    assert row is None
    with pytest.raises(BlameClosureAbsent):
        resolve_origin(row)


def test_a_same_generation_fork_resolves_the_same_way_twice(conn, site_id):
    """History forks, so (clause_uuid, gen) is not unique. The tie-break is the commit id.

    "The origin" appears in an exhibit, and an exhibit that is not reproducible is
    not an exhibit.
    """
    dag = Dag(conn, site_id)
    clause = insert_clause(conn, site_id=site_id, birth=dag.c0)
    fatality = insert_event(conn, site_id=site_id, label=f"{clause}-fatal", severity_gate=5)

    _version(conn, site_id=site_id, dag=dag, clause_uuid=clause, commit=dag.c0, parent=None, sev=5)
    for commit in (dag.c1, dag.sb):
        _version(
            conn,
            site_id=site_id,
            dag=dag,
            clause_uuid=clause,
            commit=commit,
            parent=dag.c0,
            sev=5,
        )
        insert_blame_edge(
            conn,
            site_id=site_id,
            clause_uuid=clause,
            event_id=fatality,
            commit=commit,
            basis="asserted_document" if commit is dag.c1 else "derived_documentary",
        )
    _version(
        conn, site_id=site_id, dag=dag, clause_uuid=clause, commit=dag.c2, parent=dag.c1, sev=5
    )
    for commit in (dag.c0, dag.c1, dag.sb, dag.c2):
        insert_closure(
            conn,
            site_id=site_id,
            clause_uuid=clause,
            as_of=commit,
            max_severity=5,
            ancestor_events=[fatality],
        )

    expected = min(dag.c1.commit_id, dag.sb.commit_id)
    first = _origin(conn, clause_uuid=clause, as_of=dag.c2)
    second = _origin(conn, clause_uuid=clause, as_of=dag.c2)
    assert first is not None
    assert second is not None
    assert first.origin_commit == second.origin_commit == expected
    assert first.origin_gen == 1


def test_an_origin_off_the_first_parent_chain_is_returned_and_flagged_not_dropped(conn, site_id):
    """The conservative answer, end to end.

    The clause's only severity-5 blood attached on the side branch.  The view
    returns it — dropping it would make an unverifiable chain produce a quieter
    delta, which is what the merge was for — and ``first_parent_verified`` is what
    tells the adjudicator that the chain could not be confirmed.
    """
    dag = Dag(conn, site_id)
    clause = insert_clause(conn, site_id=site_id, birth=dag.c0)
    fatality = insert_event(conn, site_id=site_id, label=f"{clause}-fatal", severity_gate=5)

    for commit, parent in (
        (dag.c0, None),
        (dag.sb, dag.c0),
        (dag.c1, dag.c0),
        (dag.c2, dag.c1),
        (dag.m, dag.c2),
    ):
        _version(
            conn,
            site_id=site_id,
            dag=dag,
            clause_uuid=clause,
            commit=commit,
            parent=parent,
            sev=5,
        )
    insert_blame_edge(conn, site_id=site_id, clause_uuid=clause, event_id=fatality, commit=dag.sb)
    for commit in (dag.c0, dag.sb, dag.c1, dag.c2, dag.m):
        insert_closure(
            conn,
            site_id=site_id,
            clause_uuid=clause,
            as_of=commit,
            max_severity=5,
            ancestor_events=[fatality],
        )

    row = _origin(conn, clause_uuid=clause, as_of=dag.m)
    assert row is not None
    assert row.origin_commit == dag.sb.commit_id

    chain = SqlBlameOriginSource(conn).first_parent_commits(
        as_of_commit=dag.m.commit_id, depth_bound=ORIGIN_DEPTH_BOUND
    )
    origin = resolve_origin(row, chain=chain)
    assert origin.state == "resolved"
    assert origin.first_parent_verified is False
    assert "NOT on the first-parent chain" in origin.reason


def test_the_first_parent_walk_is_a_path_and_the_depth_bound_truncates_it(conn, site_id):
    """``parent_ord = 0`` makes the edge relation functional, so the walk cannot fan out."""
    dag = Dag(conn, site_id)
    source = SqlBlameOriginSource(conn)

    full = source.first_parent_commits(as_of_commit=dag.m.commit_id, depth_bound=ORIGIN_DEPTH_BOUND)
    assert full == frozenset(
        {dag.m.commit_id, dag.c2.commit_id, dag.c1.commit_id, dag.c0.commit_id}
    )

    clipped = source.first_parent_commits(as_of_commit=dag.m.commit_id, depth_bound=1)
    assert clipped == frozenset({dag.m.commit_id, dag.c2.commit_id})


# --------------------------------------------------------------------------- #
# The plan                                                                     #
# --------------------------------------------------------------------------- #


def test_the_origin_query_does_not_full_scan_clause_version(conn, site_id):
    """A bounded query whose plan reads the whole version table is not a bounded query.

    The gate's p99 is a product requirement, and this is the assertion that keeps the
    view honest about it as the schema underneath moves.
    """
    dag = Dag(conn, site_id)
    clause = insert_clause(conn, site_id=site_id, birth=dag.c0)
    _version(conn, site_id=site_id, dag=dag, clause_uuid=clause, commit=dag.c0, parent=None, sev=0)
    insert_closure(
        conn,
        site_id=site_id,
        clause_uuid=clause,
        as_of=dag.c0,
        max_severity=0,
        virulence="routine",
    )

    plan = _explain(conn, clause, dag)
    scans = plan_scans(plan)
    assert scans, f"the plan named no table at all, which means it was not parsed:\n{plan}"
    offenders = [s for s in scans if s.table.endswith("clause_version") and s.full_scan]
    assert not offenders, (
        "the origin query full-scans mainline.clause_version:\n"
        + "\n".join(f"  {s.table}@{s.index} spans={s.spans}" for s in offenders)
        + f"\n\nfull plan:\n{plan}"
    )


def _explain(conn, clause_uuid, dag: Dag) -> str:
    result = conn.execute(
        "EXPLAIN " + V_BLAME_ORIGIN_SQL,
        {"clause_uuid": str(clause_uuid), "as_of_commit": dag.c0.commit_id},
    ).fetchall()
    return "\n".join(str(row[0]) for row in result)


def test_the_recursive_walk_plans_as_a_recursive_cte_and_nothing_more_is_observable(conn, site_id):
    """MEASURED, v26.2.5: ``EXPLAIN`` does not render a recursive CTE's recursive term.

    The whole plan for :data:`FIRST_PARENT_ANCESTRY_SQL` is::

        • render
        └── • recursive cte
            └── • values
                  size: 2 columns, 1 row

    The ``values`` node is the *seed*.  The recursive term — the join to
    ``mainline.commit_edge`` carrying ``parent_ord = 0`` and the depth bound — is
    opaque to ``EXPLAIN`` on this version, so **no plan assertion can prove the
    restriction is applied**.  Recording that here rather than writing an assertion
    that passes for the wrong reason: a test asserting ``"parent_ord" in plan``
    would fail on a correct query, and one asserting ``"recursive" in plan`` would
    pass on a query that had lost the restriction entirely.

    What actually holds the restriction is one layer up and one layer down:

    * BEHAVIOURALLY, ``test_the_first_parent_walk_is_a_path_and_the_depth_bound_
      truncates_it`` asserts the side branch is ABSENT from the walk on a DAG that
      contains a merge, which a walk without ``parent_ord = 0`` could not do;
    * STATICALLY, ``tests/unit/domain/diachronic/test_origin_resolution.py::
      test_the_two_statements_are_parameterised_and_name_no_table_they_do_not_read``
      asserts the predicate and the bound are both in the statement text.
    """
    dag = Dag(conn, site_id)
    result = conn.execute(
        "EXPLAIN " + FIRST_PARENT_ANCESTRY_SQL,
        {"as_of_commit": dag.m.commit_id, "depth_bound": ORIGIN_DEPTH_BOUND},
    ).fetchall()
    plan = "\n".join(str(row[0]) for row in result)
    assert "recursive cte" in plan.lower()
    assert "parent_ord" not in plan, (
        "v26.2.5 did not render the recursive term; if a later version does, replace this "
        "test with the plan assertion its absence currently forbids"
    )
