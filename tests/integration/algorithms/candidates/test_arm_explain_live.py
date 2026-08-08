# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""Layer 1, live: ``EXPLAIN`` on every generated arm, against a real cluster.

The exit criterion this file carries is exact: *EXPLAIN on every generated arm
shows ``vector search`` with non-empty prefix spans*.  The offline suite proves
the assertion machinery has teeth (it refuses plans in four separate ways); this
file proves the statements this package generates actually produce a plan that
passes it.

Negative controls run beside the positive one, because "the plan looked fine" is
worth very little without evidence that a bad plan would have looked different.
There are two families of them and the split is the point:

**Pinned arms are refused, not mis-planned.**  Because :data:`ARM_SQL` names the
index (``FROM mainline.clause_embedding@ce_ann``, the F1 ruling), relaxing a
prefix predicate to a range — or dropping it — makes CockroachDB v26.2.5 raise
``42809 index "ce_ann" cannot be used for this query``.  The database refuses the
statement; there is no bad plan to inspect.  That is a *stronger* control than a
plan assertion and it is asserted as a refusal.

**Unhinted arms are where the plan assertion still has to work.**  The same
query without the pin is accepted and plans as a ``FULL SCAN``, so the unhinted
forms are what prove :func:`assert_arm_plan` has teeth on a live plan and not
only on the committed fixtures the unit suite feeds it.

Skips with a reason when no cluster is reachable.  A skipped run does not
entitle anyone to say the plan was verified, and the skip message says so.
"""

from __future__ import annotations

from typing import Any

import pytest
from _w7_support import (
    ACTIVITY,
    INSERT_CLAUSE_EMBEDDING,
    SITE,
    build_corpus,
    fixture_embedding,
)
from mainline_domain.identity.candidates import ARM_SQL, Arm, arms_for, vector_literal
from mainline_domain.identity.candidates.explain import (
    INDEX_REFUSED_SQLSTATE,
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


@pytest.mark.parametrize(
    ("label", "mutate"),
    [
        (
            "ranged prefix",
            lambda sql: sql.replace(
                "AND activity_root = %(activity_root)s",
                "AND activity_root >= %(activity_root)s",
            ),
        ),
        (
            "no prefix predicate",
            lambda sql: sql.replace(
                "WHERE site_id = %(site_id)s\n   AND activity_root = %(activity_root)s",
                "WHERE %(site_id)s::UUID IS NOT NULL AND %(activity_root)s::STRING IS NOT NULL",
            ),
        ),
    ],
)
def test_a_pinned_arm_that_breaks_the_prefix_rule_is_refused_by_the_database(
    seeded: Any, label: str, mutate: Any
) -> None:
    """The strongest control: the cluster will not run the statement at all.

    Both mutations keep every parameter binding, so the only thing that changed
    is whether the C-SPANN prefix columns are constrained to specific values.
    The refusal is what makes the pin worth having: an unhinted arm would have
    been accepted and would have read the whole table.
    """
    psycopg = pytest.importorskip("psycopg")
    mutated = mutate(ARM_SQL)
    assert mutated != ARM_SQL, f"the {label} mutation did not apply; ARM_SQL changed shape"
    arm = arms_for(SITE, [ACTIVITY])[0]
    with pytest.raises(psycopg.Error) as excinfo:
        _explain(seeded, mutated, arm.params(QUERY_VECTOR, 8))
    assert excinfo.value.sqlstate == INDEX_REFUSED_SQLSTATE, (
        f"a pinned arm with a {label} failed with SQLSTATE "
        f"{excinfo.value.sqlstate}, not {INDEX_REFUSED_SQLSTATE}: {excinfo.value}"
    )


def test_the_same_arm_unhinted_is_accepted_and_reads_the_whole_table(seeded: Any) -> None:
    """Why the pin exists, and the live proof that the plan assertion has teeth.

    Without ``@ce_ann`` the identical prefix-free query is *accepted* and plans
    as a full scan.  :func:`assert_arm_plan` must catch it — on a plan the
    cluster really produced, not on a committed fixture.
    """
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
    assert not result.has_vector_search, plan


def test_the_in_form_is_characterised_rather_than_assumed(seeded: Any) -> None:
    """The ``IN`` fan-in *does* use the index on v26.2.5 — and still is not used.

    The blanket claim that ``IN (...)`` defeats a C-SPANN prefix is **false on
    this version**: the plan below carries one prefix span per listed value.  The
    package keeps the single-value fan-out for the reason this test pins
    alongside it — ``LIMIT k`` on the ``IN`` form is *k rows shared between the
    roots*, where an ancestry walk needs k per ancestor partition.

    If this test ever goes red the module docstring in ``semantic.py`` is stale,
    which is the only reason it exists.
    """
    in_form = ARM_SQL.replace(
        "AND activity_root = %(activity_root)s",
        "AND activity_root IN (%(activity_root)s, %(other_root)s)",
    )
    arm = arms_for(SITE, [ACTIVITY])[0]
    params = {**arm.params(QUERY_VECTOR, 8), "other_root": ROOTS[1]}

    plan = _explain(seeded, in_form, params)
    result = assert_arm_plan(plan, raises=False)
    stale = "the IN form no longer plans as a prefix-constrained vector search; the "
    stale += "measurement recorded in semantic.py is stale:\n" + plan
    assert result.has_vector_search, stale
    assert result.prefix_constrained, stale

    with seeded.cursor() as cur:
        cur.execute(in_form, params)
        shared = cur.fetchall()
        cur.execute(ARM_SQL, arm.params(QUERY_VECTOR, 8))
        one_arm = cur.fetchall()
        cur.execute(ARM_SQL, Arm(SITE, ROOTS[1]).params(QUERY_VECTOR, 8))
        other_arm = cur.fetchall()

    assert len(shared) == 8, "LIMIT on the IN form is no longer a shared budget"
    assert len(one_arm) + len(other_arm) == 16, (
        "the fan-out no longer yields k candidates per ancestor partition, which is "
        "the reason it is preferred over the IN form"
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


def test_a_missing_ce_ann_is_an_error_and_not_a_full_scan(seeded: Any) -> None:
    """Drop the index and S4 stops, loudly.

    The failure this pins is a deployment one: a cluster that was never migrated
    to carry ``ce_ann``, or one where it was dropped.  An unhinted runner would
    keep answering — slowly, from a full scan, with no signal that the cost
    claim underneath S4 had evaporated.  The pinned runner raises.
    """
    from mainline_domain.identity.candidates.pg_arm import (
        ArmIndexUnavailableError,
        PgPrefixArmRunner,
    )

    runner = PgPrefixArmRunner(seeded)
    assert runner.ann(SITE, ACTIVITY, QUERY_VECTOR, 5), "the fixture seeded no rows"

    with seeded.cursor() as cur:
        cur.execute("DROP INDEX mainline.clause_embedding@ce_ann")

    with pytest.raises(ArmIndexUnavailableError, match="ce_ann"):
        runner.ann(SITE, ACTIVITY, QUERY_VECTOR, 5)
