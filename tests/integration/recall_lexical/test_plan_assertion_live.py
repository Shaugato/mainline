# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""``EXPLAIN`` against a real CockroachDB: the posting list is scanned constrained, or CI fails.

This is the only assertion in the band that a second SQL engine cannot stand in for.  SQLite's
planner is not CockroachDB's, and a green run against SQLite would say nothing about whether
CockroachDB's optimiser built spans on ``lex_posting_pk``.  So when no cluster is reachable
this module **skips with a reason** and says so loudly.  A skipped run verifies nothing, and
this file is the reason the worker's honesty note exists.

The defect being hunted has no symptom.  Drop the ``p.term IN (…)`` predicate and every score
in the differential still matches the oracle to 1e-9 — the statement is *correct*, it simply
reads every posting at the site on every permit gate.  On a demo corpus that is imperceptible;
on a fleet corpus it is the difference between a gate and an outage.

``test_removing_the_in_predicate_produces_a_full_scan`` is the PL-2 obligation: the predicate
is removed, the plan is re-explained, and the assertion is required to fail.  Without it, a
plan check that had stopped parsing CockroachDB's output format would pass forever.
"""

from __future__ import annotations

import re

import pytest
from _corpus import Fixture

from conftest import Backend  # type: ignore[import-not-found]
from trappoint_recall.lexical.analyser import analyse_query
from trappoint_recall.lexical.bm25 import (
    build_bm25_statement,
    explain_of,
    fetch_corpus_stats,
)
from trappoint_recall.lexical.executor import ParamStyle, Statement
from trappoint_recall.lexical.plan import (
    PlanAssertionError,
    assert_constrained_lex_scan,
    parse_plan,
    plan_digest,
    plan_text_from_rows,
)
from trappoint_recall.lexical.postings import rebuild_site

pytestmark = pytest.mark.cockroach


#: Repeated rather than imported from ``conftest`` so that the skip message is next to the
#: skip. It says what to install, because "skipped" with no reason is how a check that never
#: runs comes to look like a check that passes.
NO_CLUSTER_REASON = (
    "no CockroachDB v26.2 reachable: set MAINLINE_TEST_DSN, or put `cockroach` on PATH, or "
    "start the Docker daemon. SQLite cannot stand in here — its planner is not "
    "CockroachDB's, so a green SQLite run would say nothing about whether the optimiser "
    "constrained the scan. Channel D's PLAN is NOT verified by this skipped run."
)


@pytest.fixture(scope="module")
def crdb(cockroach, fixture_corpus: Fixture):  # noqa: ANN001, ANN201
    if cockroach is None:
        pytest.skip(NO_CLUSTER_REASON)
    rebuild_site(
        cockroach.execute,
        site_id=fixture_corpus.site_id,
        documents=fixture_corpus.documents,
        style=cockroach.style,
    )
    # Plans depend on statistics; without them CockroachDB reports "missing stats" and may
    # choose a different shape than it will in production. Requesting them is part of the
    # question being asked.
    for table in ("lex_posting", "lex_stats", "lex_doclen"):
        cockroach.execute(f"CREATE STATISTICS lex_auto FROM mainline.{table}")
    return cockroach, fixture_corpus


def explain(backend: Backend, statement: Statement) -> str:
    explained = explain_of(statement)
    return plan_text_from_rows(backend.execute(explained.sql, explained.params))


def build(
    backend: Backend, corpus: Fixture, query_text: str, style: ParamStyle | None = None
) -> Statement:
    stats = fetch_corpus_stats(backend.execute, site_id=corpus.site_id, style=backend.style)
    return build_bm25_statement(
        site_id=corpus.site_id,
        terms=analyse_query(query_text).terms,
        stats=stats,
        limit=25,
        style=style if style is not None else backend.style,
    )


def test_the_posting_list_is_scanned_constrained(crdb) -> None:  # noqa: ANN001
    backend, corpus = crdb
    plan = explain(backend, build(backend, corpus, "K-401 H2S 25 %LEL"))
    approved = assert_constrained_lex_scan(plan)
    print(f"\n[recall_lexical] lex_posting access: {approved}")


@pytest.mark.parametrize(
    "query_text",
    [
        "K-401",
        "K-401 H2S 25 %LEL 30 CFR 57.22239",
        "the isolation valve was not closed before the lock-out was removed",
        "CAS 7783-06-4",
    ],
)
def test_every_query_shape_is_constrained(crdb, query_text: str) -> None:  # noqa: ANN001
    backend, corpus = crdb
    assert_constrained_lex_scan(explain(backend, build(backend, corpus, query_text)))


def test_a_query_weighted_statement_is_also_constrained(crdb) -> None:  # noqa: ANN001
    """The ``CASE`` arm is a different statement; the ``IN`` list is why it stays constrained."""
    backend, corpus = crdb
    terms = analyse_query("K-401 H2S 25 %LEL").terms
    stats = fetch_corpus_stats(backend.execute, site_id=corpus.site_id, style=backend.style)
    statement = build_bm25_statement(
        site_id=corpus.site_id,
        terms={term: 1.0 + index for index, term in enumerate(terms)},
        stats=stats,
        limit=25,
        style=backend.style,
    )
    assert "CASE p.term WHEN" in statement.sql
    assert_constrained_lex_scan(explain(backend, statement))


def test_a_large_term_set_is_still_constrained(crdb) -> None:  # noqa: ANN001
    """``optimizer_span_limit`` is a silent cliff; a 100-term query must not walk off it."""
    backend, corpus = crdb
    terms = sorted({t for tag in corpus.unique_tags[:60] for t in analyse_query(tag).terms})
    stats = fetch_corpus_stats(backend.execute, site_id=corpus.site_id, style=backend.style)
    statement = build_bm25_statement(
        site_id=corpus.site_id, terms=terms, stats=stats, limit=25, style=backend.style
    )
    assert_constrained_lex_scan(explain(backend, statement))


def test_removing_the_in_predicate_produces_a_full_scan(crdb) -> None:  # noqa: ANN001
    """PL-2: the assertion must be able to fail, and must fail for the right reason.

    The mutated statement returns the identical ranking. That is the whole argument for
    checking the plan: correctness is not the property at risk.
    """
    backend, corpus = crdb
    assert_constrained_lex_scan(explain(backend, build(backend, corpus, "K-401 H2S 25 %LEL")))

    # Built with values inlined so that deleting a clause needs no parameter surgery: the
    # mutation is one regex over the text, and what runs is unambiguously the shipped
    # statement minus its span-building predicate.
    literal = build(backend, corpus, "K-401 H2S 25 %LEL", style=ParamStyle.LITERAL)
    mutated_sql, replaced = re.subn(r"\n   AND p\.term IN \([^)]*\)", "", literal.sql)
    assert replaced == 1, "the IN predicate was not found in the statement text"
    mutated = Statement(mutated_sql, (), ParamStyle.LITERAL)

    ranking_before = backend.execute(literal.sql, literal.params)
    ranking_after = backend.execute(mutated.sql, mutated.params)
    assert [row[0] for row in ranking_before] == [row[0] for row in ranking_after][
        : len(ranking_before)
    ], "premise: removing the predicate does not change the head of the ranking"

    with pytest.raises(PlanAssertionError, match="WITHOUT a constrained span"):
        assert_constrained_lex_scan(explain(backend, mutated))


def test_the_plan_parser_understands_this_clusters_output(crdb) -> None:  # noqa: ANN001
    """If CockroachDB's EXPLAIN format ever changes, fail here rather than pass vacuously."""
    backend, corpus = crdb
    plan = explain(backend, build(backend, corpus, "K-401"))
    nodes = parse_plan(plan)
    assert nodes, f"the plan parser found no table access in:\n{plan}"
    assert {n.bare_table for n in nodes} >= {"lex_posting"}
    assert plan_digest(plan)


def test_the_supporting_statements_run_on_the_real_schema(crdb) -> None:  # noqa: ANN001
    """The integrity and statistics statements are CockroachDB SQL, not just SQLite SQL."""
    from trappoint_recall.lexical.bm25 import (
        orphan_postings_statement,
        stats_drift_statement,
    )

    backend, corpus = crdb
    for builder in (orphan_postings_statement, stats_drift_statement):
        statement = builder(site_id=corpus.site_id, style=backend.style)
        assert backend.execute(statement.sql, statement.params) == []
