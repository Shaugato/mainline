# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""Layer 1, live: ``EXPLAIN`` on every generated arm, against a real cluster.

The exit criterion this file carries is exact: *EXPLAIN on every generated arm
shows ``vector search`` with non-empty prefix spans*.  The offline suite proves
the assertion machinery has teeth (it refuses plans in four separate ways); this
file proves the statements this package generates actually produce a plan that
passes it.

Two negative controls run beside the positive one, because "the plan looked
fine" is worth very little without evidence that a bad plan would have looked
different:

* an arm whose prefix is a **range** rather than a specific value — the
  documented condition under which the vector index is not used;
* an arm with no prefix predicate at all.

If either of those still shows a prefix-constrained vector search, then the
assertion is not measuring what it claims and the positive result is worthless.

Skips with a reason when no cluster is reachable.  A skipped run does not
entitle anyone to say the plan was verified, and the skip message says so.
"""

from __future__ import annotations

from typing import Any

import pytest
from _support import (
    ACTIVITY,
    INSERT_CLAUSE_EMBEDDING,
    SITE,
    build_corpus,
    fixture_embedding,
)
from mainline_domain.identity.candidates import ARM_SQL, arms_for, vector_literal
from mainline_domain.identity.candidates.explain import (
    assert_arm_plan,
    assert_arm_set_plans,
    parse_plan,
)

pytestmark = pytest.mark.requires_cluster

ROOTS = (
    ACTIVITY,
    "operations/permit-to-work",
    "engineering/management-of-change",
)
CORPUS_SIZE = 60
QUERY_VECTOR = fixture_embedding("query probe")


@pytest.fixture
def seeded(cluster_conn: Any) -> Any:
    """Rows across three activity roots, so the arm fan-out has something to find.

    Written one statement at a time: ``IMPORT INTO`` is unsupported on
    vector-indexed tables, and the live path in ARCHITECTURE.md §5.3 is
    row-at-a-time with the index declared at ``CREATE TABLE``.  This fixture
    follows the live path rather than inventing a bulk one.
    """
    corpus = build_corpus(CORPUS_SIZE)
    rows = []
    for i, record in enumerate(corpus.records):
        rows.append(
            {
                "clause_uuid": str(record.ref.clause_uuid),
                "commit_id": record.ref.commit_id,
                "site_id": str(SITE),
                "activity_root": ROOTS[i % len(ROOTS)],
                "embedding": vector_literal(fixture_embedding(record.canon_text)),
            }
        )
    with cluster_conn.cursor() as cur:
        cur.executemany(INSERT_CLAUSE_EMBEDDING, rows)
    return cluster_conn


def _explain(conn: Any, sql: str, params: dict[str, object]) -> str:
    with conn.cursor() as cur:
        cur.execute("EXPLAIN " + sql, params)
        return "\n".join(str(row[0]) for row in cur.fetchall())


def test_every_generated_arm_plans_as_a_prefix_constrained_vector_search(
    seeded: Any,
) -> None:
    """The exit criterion, one arm at a time."""
    plans = [
        _explain(seeded, ARM_SQL, arm.params(QUERY_VECTOR, 8)) for arm in arms_for(SITE, ROOTS)
    ]
    assert_arm_set_plans(plans)


def test_the_plan_names_the_ce_ann_index(seeded: Any) -> None:
    arm = arms_for(SITE, [ACTIVITY])[0]
    plan = _explain(seeded, ARM_SQL, arm.params(QUERY_VECTOR, 8))
    result = assert_arm_plan(plan)
    node = next(n for n in result.nodes if n.node_type == "vector search")
    assert node.table_ref is not None
    assert node.table_ref.endswith("@ce_ann")
    assert node.has_constrained_prefix


def test_a_ranged_prefix_does_not_get_a_constrained_vector_search(seeded: Any) -> None:
    """Negative control: the documented failure condition, provoked on purpose."""
    ranged = ARM_SQL.replace(
        "AND activity_root = %(activity_root)s", "AND activity_root >= %(activity_root)s"
    )
    arm = arms_for(SITE, [ACTIVITY])[0]
    plan = _explain(seeded, ranged, arm.params(QUERY_VECTOR, 8))
    result = assert_arm_plan(plan, raises=False)
    assert not result.ok, (
        "a >= predicate on a prefix column still produced a fully prefix-constrained "
        "vector search; the assertion is not measuring what it claims:\n" + plan
    )


def test_an_unconstrained_prefix_does_not_get_one_either(seeded: Any) -> None:
    """Negative control 2: no prefix predicate at all."""
    unconstrained = """
    SELECT clause_uuid, commit_id, 1 - (embedding <=> %(q)s::VECTOR) AS cosine_similarity
      FROM mainline.clause_embedding
     ORDER BY embedding <=> %(q)s::VECTOR
     LIMIT %(k)s
    """.strip()
    plan = _explain(seeded, unconstrained, {"q": vector_literal(QUERY_VECTOR), "k": 8})
    result = assert_arm_plan(plan, raises=False)
    assert not result.ok, (
        "a query with NO prefix predicate produced a prefix-constrained vector "
        "search; the assertion has no teeth:\n" + plan
    )


def test_the_arm_returns_cosine_similarity_not_distance(seeded: Any) -> None:
    """``<=>`` is a distance in [0, 2]; the bands are expressed in similarity."""
    arm = arms_for(SITE, [ACTIVITY])[0]
    with seeded.cursor() as cur:
        cur.execute(ARM_SQL, arm.params(QUERY_VECTOR, 8))
        rows = cur.fetchall()
    assert rows, "the arm returned nothing; the fixture did not seed this activity root"
    scores = [float(r[2]) for r in rows]
    assert all(-1.0001 <= s <= 1.0001 for s in scores), scores
    assert scores == sorted(scores, reverse=True), "ANN results are not ordered by similarity"


def test_the_runner_captures_the_plan_it_asserted(seeded: Any) -> None:
    """``PgPrefixArmRunner.explain_arm`` keeps the text, so a failure is legible."""
    from mainline_domain.identity.candidates.pg_arm import PgPrefixArmRunner

    runner = PgPrefixArmRunner(seeded)
    result = runner.explain_arm(SITE, ACTIVITY, QUERY_VECTOR, 8)
    assert result.ok
    assert runner.last_plan is not None
    assert parse_plan(runner.last_plan)


def test_the_runner_returns_candidates_the_stage_can_consume(seeded: Any) -> None:
    from mainline_domain.identity.candidates.pg_arm import PgPrefixArmRunner

    runner = PgPrefixArmRunner(seeded)
    hits = runner.ann(SITE, ACTIVITY, QUERY_VECTOR, 5)
    assert hits
    assert all(h.stage == "S4" for h in hits)
    assert all("cosine" in h.features for h in hits)
    assert all(isinstance(h.ancestor_commit, bytes) for h in hits)
