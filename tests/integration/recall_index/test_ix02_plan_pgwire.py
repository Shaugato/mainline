# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""IX-02 — layer 1 over pgwire: every generated arm plans as a constrained vector search.

Four claims, against a real CockroachDB:

1. **every arm** — all twelve scoped arms and the coarse sweep — EXPLAINs to a ``vector
   search`` on the expected ``table@index``, with a **non-empty** ``prefix spans`` and no
   ``FULL SCAN`` anywhere in the plan;
2. the whole ``UNION ALL`` plans as *one constrained vector search per arm*, which is the
   claim that the arms are independent lookups rather than one lookup the optimizer folded;
3. **the negative control**: the same query with the prefix predicates removed must FAIL the
   assertion. Red before green, against the database rather than against a fixture — if the
   assertion cannot tell a constrained arm from an unconstrained one on *this* cluster, it is
   not evidence on this cluster;
4. **the MCP-rendering equivalence**: the compact rendering sent to the capped public endpoint
   produces the same plan skeleton and the same ``index_plan_digest`` as the rendering that
   actually executes. That equivalence is the entire licence for IX-03 to prove anything about
   the executed statement, so it is asserted here rather than assumed there.

Observed plan text is written to ``fixtures/plans/captured/`` — the difference between what
the hand-written fixtures imagine CockroachDB prints and what it actually prints should be
visible, not folklore.
"""

from __future__ import annotations

import pytest
from _support import (
    ARTEFACTS,
    CUE_SCOPED,
    CUE_SWEEP,
    FIXTURES,
    POPULATED_FACETS,
    CorpusState,
    env_int,
    grow_corpus,
    pgwire_explain_source,
    policy,
    unit_vector,
)

from trappoint_recall.arms import (
    AncestorChain,
    ArmSet,
    SqlForm,
    SweepRequest,
    assert_arm_plan,
    assert_arm_set_plan,
    explain_sql,
    explain_union_sql,
    generate_arms,
    index_plan_digest,
    parse_explain,
    plan_skeleton,
)

pytestmark = pytest.mark.plan

#: The plan lane grows the corpus to the first point of the sublinearity sequence, so the two
#: lanes share the work instead of building two corpora. On a nearly-empty table the optimizer
#: may legitimately prefer a scan, and a plan assertion run against 20 rows would be
#: characterising the cost model rather than the index.
PLAN_CORPUS_ROWS = env_int("MAINLINE_RECALL_INDEX_PLAN_ROWS", 5000)

CAPTURED = FIXTURES / "plans" / "captured"


@pytest.fixture(scope="module")
def arms(session_conn: object, corpus: CorpusState) -> ArmSet:
    grow_corpus(session_conn, corpus, target_vectors=PLAN_CORPUS_ROWS)
    chain = AncestorChain.of("permit-slice-1", corpus.taxonomy.levels)
    return generate_arms(
        site=corpus.taxonomy.site_id,
        chain=chain,
        facet_vectors={f: unit_vector(1024, f"query/{f}") for f in POPULATED_FACETS},
        policy=policy(),
        scoped_table=CUE_SCOPED,
        sweep=SweepRequest(
            tenant=corpus.taxonomy.tenant_id,
            query_vector=unit_vector(256, "query/coarse"),
            table=CUE_SWEEP,
        ),
    )


def _capture(name: str, text: str) -> None:
    CAPTURED.mkdir(parents=True, exist_ok=True)
    (CAPTURED / f"{name}.txt").write_text(
        "# CAPTURED FROM A LIVE CLUSTER by tests/integration/recall_index/"
        "test_ix02_plan_pgwire.py\n" + text + "\n",
        encoding="utf-8",
    )


def test_ix02_every_arm_plans_as_a_constrained_vector_search(
    session_conn: object, arms: ArmSet
) -> None:
    source = pgwire_explain_source(session_conn)
    failures: list[str] = []
    for arm in arms.arms:
        statement = explain_sql(arm, form=SqlForm.EXPLAIN_MCP)
        plan = parse_explain(source(statement.text))
        assertion = assert_arm_plan(
            plan,
            expected_index_ref=arm.table.index_ref,
            arm_id=arm.arm_id,
            expected_target_count=arm.k,
        )
        if not assertion.ok:
            failures.append(f"{assertion.describe()}\n--- plan ---\n{plan.raw}")
        else:
            print(f"[ix02] {assertion.describe()}")
    _capture("arm_live", parse_explain(source(explain_sql(arms.arms[0]).text)).raw)
    assert not failures, (
        f"{len(failures)} of {len(arms)} arms did not plan as a constrained vector search on "
        f"a corpus of {PLAN_CORPUS_ROWS} vectors:\n\n" + "\n\n".join(failures)
    )


def test_ix02_the_union_plans_as_one_vector_search_per_arm(
    session_conn: object, arms: ArmSet
) -> None:
    source = pgwire_explain_source(session_conn)
    statement = explain_union_sql(arms, form=SqlForm.LITERAL)
    plan = parse_explain(source(statement.text))
    _capture("union_live", plan.raw)
    assertion = assert_arm_set_plan(
        plan,
        expected_arm_count=len(arms),
        expected_index_refs=tuple({a.table.index_ref for a in arms.arms}),
    )
    assert assertion.ok, f"{assertion.failures}\n--- plan ---\n{plan.raw}"


def test_ix02_red_an_unconstrained_query_fails_the_same_assertion(
    session_conn: object, arms: ArmSet, corpus: CorpusState
) -> None:
    """The negative control. Same table, same ORDER BY, no prefix predicates.

    If this passes, the assertion is not distinguishing a constrained arm from an unindexed
    scan on this cluster, and every green result above means nothing. That is why the control
    runs here rather than in a fixture file: fixtures prove the parser, this proves the claim.
    """
    source = pgwire_explain_source(session_conn)
    arm = arms.scoped[0]
    vector = arm.query_vector
    literal = "[" + ",".join(f"{v:.6f}" for v in vector) + "]"
    unconstrained = (
        f"EXPLAIN SELECT e.cue_id\n"
        f"  FROM {CUE_SCOPED.qualified_name} AS e\n"
        f" ORDER BY e.emb <=> '{literal}'::VECTOR(1024)\n"
        f" LIMIT {arm.k}"
    )
    plan = parse_explain(source(unconstrained))
    _capture("unconstrained_live", plan.raw)
    assertion = assert_arm_plan(
        plan, expected_index_ref=CUE_SCOPED.index_ref, arm_id="negative-control"
    )
    assert not assertion.ok, (
        "an ORDER BY-distance query with NO prefix predicate passed the index-use assertion. "
        "The documented rule is that a vector index is used only if EACH prefix column is "
        "constrained to a specific value, so either that rule changed on this version or the "
        "assertion is matching text it should not.\n--- plan ---\n" + plan.raw
    )
    print(f"[ix02] negative control refused for: {assertion.failures}")


def test_ix02_partially_constrained_is_also_refused(
    session_conn: object, arms: ArmSet, corpus: CorpusState
) -> None:
    """Two of three prefix columns bound, and a range on the third. Also not an index use.

    This is the realistic mistake — not "somebody forgot the WHERE clause" but "somebody wrote
    a filter that looks like a constraint and is not one".
    """
    source = pgwire_explain_source(session_conn)
    arm = arms.scoped[0]
    literal = "[" + ",".join(f"{v:.6f}" for v in arm.query_vector) + "]"
    partial = (
        f"EXPLAIN SELECT e.cue_id\n"
        f"  FROM {CUE_SCOPED.qualified_name} AS e\n"
        f" WHERE e.site_id = '{corpus.taxonomy.site_id}'\n"
        f"   AND e.scope_id = '{corpus.taxonomy.file}'\n"
        f"   AND e.facet >= 'a'\n"
        f" ORDER BY e.emb <=> '{literal}'::VECTOR(1024)\n"
        f" LIMIT {arm.k}"
    )
    plan = parse_explain(source(partial))
    _capture("partially_constrained_live", plan.raw)
    assertion = assert_arm_plan(
        plan, expected_index_ref=CUE_SCOPED.index_ref, arm_id="partial-control"
    )
    assert not assertion.ok, (
        "a range predicate on the last prefix column still planned as a constrained vector "
        "search. The documentation is explicit that `WHERE a = 1 AND b >= 2` does not use the "
        "index; if that has changed, the arm generator's whole shape can be simplified — and "
        "this test is where that discovery is supposed to happen.\n--- plan ---\n" + plan.raw
    )


def test_ix02_the_mcp_rendering_plans_identically_to_the_executed_rendering(
    session_conn: object, arms: ArmSet
) -> None:
    """The licence for IX-03 to prove anything about the statement that actually runs.

    The compact rendering exists only because a 1024-dimension vector printed twice does not
    fit the public endpoint's 16 384-character statement cap. That elision is legitimate only
    while the two renderings plan the same way, so the equivalence is measured here on every
    arm — not asserted once and assumed forever.
    """
    source = pgwire_explain_source(session_conn)
    for arm in arms.arms:
        compact = parse_explain(source(explain_sql(arm, form=SqlForm.EXPLAIN_MCP).text))
        executed = parse_explain(source(explain_sql(arm, form=SqlForm.LITERAL).text))
        assert plan_skeleton(compact) == plan_skeleton(executed), (
            f"arm {arm.arm_id}: the compact MCP rendering and the executed rendering plan "
            "differently. The MCP proof no longer covers the executed statement and the "
            "claim must be withdrawn until it does.\n"
            f"--- compact ---\n{compact.raw}\n--- executed ---\n{executed.raw}"
        )
        assert index_plan_digest(compact) == index_plan_digest(executed)


def test_ix02_the_recorded_digest_is_stable_across_two_explains(
    session_conn: object, arms: ArmSet
) -> None:
    """``recall_run.index_plan_digest`` must not move because the same plan was asked twice."""
    source = pgwire_explain_source(session_conn)
    statements = [explain_sql(arm, form=SqlForm.EXPLAIN_MCP).text for arm in arms.arms]
    first = index_plan_digest([parse_explain(source(s)) for s in statements])
    second = index_plan_digest([parse_explain(source(s)) for s in statements])
    assert first == second
    ARTEFACTS.mkdir(parents=True, exist_ok=True)
    (ARTEFACTS / "index_plan_digest.txt").write_text(
        "# index_plan_digest observed by test_ix02_plan_pgwire.py over the full arm set.\n"
        "# This is the value a recall_run row would carry for this arm set on this cluster.\n"
        f"{first.hex()}\n",
        encoding="utf-8",
    )
    print(f"[ix02] index_plan_digest = {first.hex()}")


def test_ix02_the_vector_index_setting_was_available(schema: object) -> None:
    """Report, do not assume. `feature.vector_index.enabled` defaults true on v26.2 and is a
    day-1 check; if this cluster did not have the setting the suite says so out loud."""
    print(f"[ix02] {getattr(schema, 'vector_setting', 'unknown')}")
    assert getattr(schema, "vector_setting", None) is not None


def test_ix02_captured_plans_are_written_where_a_reviewer_will_find_them() -> None:
    if not CAPTURED.is_dir():
        pytest.skip("no plans captured: the cluster-backed tests above did not run")
    captured = sorted(p.name for p in CAPTURED.glob("*.txt"))
    assert captured, "the capture directory exists but is empty"
    print(f"[ix02] captured {len(captured)} live plans: {captured}")
