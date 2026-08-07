# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""The differential: the SQL BM25 against a pure-Python oracle, 200 queries, 2 000 documents.

BM25 written directly in SQL is exactly the kind of code that is subtly wrong and never
noticed.  Drop the ``+ 1`` from the IDF and every ranking still looks plausible.  Divide by
``|d|`` instead of ``|d|/avgdl`` and short documents still win.  Lose a row to an inner join
and the missing precursor is simply not there.  None of it raises; all of it changes which
incidents a permit approver is shown.

So the statement is measured against an independent implementation that reads the same three
tables and computes the same arithmetic in the most boring way available, over a corpus built
to reach the edges: ``df = N``, ``df = 1``, unseen terms, documents differing in length by an
order of magnitude, and every token class the analyser can produce.

Agreement is asserted to **1e-9 absolute** on every score, not merely on the ranking.  A
ranking comparison would pass on an IDF that is wrong by a constant factor.

``test_the_differential_can_fail`` is the PL-2 obligation: the comparison is re-run with the
oracle's ``b`` deliberately wrong and the disagreement is demanded.  A differential that
cannot fail measures nothing.
"""

from __future__ import annotations

import math

import pytest
from _corpus import Fixture
from conftest import Backend  # type: ignore[import-not-found]
from trappoint_recall.lexical.analyser import analyse_query
from trappoint_recall.lexical.bm25 import (
    DEFAULT_BM25,
    Bm25Params,
    CorpusStats,
    bm25_search,
    fetch_corpus_stats,
)
from trappoint_recall.lexical.postings import rebuild_site, snapshot_tables
from trappoint_recall.lexical.reference import (
    LexicalTables,
    reference_bm25,
    reference_corpus_stats,
)

#: What the module-scoped ``loaded`` fixture hands every test: the engine, the fixture, the
#: three tables read back out of it, and the statistics in force. Named so that the tests can
#: be annotated without repeating a four-element tuple type in every signature.
Loaded = tuple[Backend, Fixture, LexicalTables, CorpusStats]

TOLERANCE = 1e-9
#: Large enough that the SQL's LIMIT never truncates, so scores are compared for every
#: document a query reaches rather than only for the head of the list.
UNTRUNCATED = 100_000

pytestmark = pytest.mark.differential


@pytest.fixture(scope="module")
def loaded(backend: Backend, fixture_corpus: Fixture) -> Loaded:
    """The whole fixture, written once, then read back as the oracle's input."""
    rebuild_site(
        backend.execute,
        site_id=fixture_corpus.site_id,
        documents=fixture_corpus.documents,
        style=backend.style,
    )
    tables = snapshot_tables(
        backend.execute, site_id=fixture_corpus.site_id, style=backend.style
    )
    stats = fetch_corpus_stats(
        backend.execute, site_id=fixture_corpus.site_id, style=backend.style
    )
    return backend, fixture_corpus, tables, stats


def test_the_fixture_is_the_size_it_claims_to_be(loaded: Loaded) -> None:
    _backend, corpus, tables, stats = loaded
    assert len(corpus.documents) == 2000
    assert len(corpus.queries) >= 196
    assert stats.n_docs == 2000
    assert len(tables.posting) > 20_000
    assert len(tables.doclen) == 2000


def test_the_fixture_reaches_the_document_frequency_edges(loaded: Loaded) -> None:
    """A differential over a fixture that never reaches ``df = N`` proves less than it looks."""
    _backend, _corpus, tables, stats = loaded
    dfs = {df for _site, _term, df in tables.stats}
    assert max(dfs) == stats.n_docs, "no term appears in every document"
    assert min(dfs) == 1, "no term appears in exactly one document"


def test_the_statistics_agree_with_the_oracle(loaded: Loaded) -> None:
    _backend, corpus, tables, stats = loaded
    expected = reference_corpus_stats(tables, site_id=corpus.site_id)
    assert stats.n_docs == expected.n_docs
    assert stats.avgdl == pytest.approx(expected.avgdl, abs=1e-12)


def _compare(
    loaded: Loaded, query_text: str, params: Bm25Params = DEFAULT_BM25
) -> tuple[list[tuple[str, float]], list[tuple[str, float]]]:
    backend, corpus, tables, stats = loaded
    terms = analyse_query(query_text).terms
    sql = bm25_search(
        backend.execute,
        site_id=corpus.site_id,
        terms=terms,
        limit=UNTRUNCATED,
        stats=stats,
        params=params,
        style=backend.style,
    )
    oracle = reference_bm25(
        tables,
        site_id=corpus.site_id,
        terms=terms,
        stats=stats,
        limit=UNTRUNCATED,
        params=params,
    )
    return sql, oracle


def test_every_query_agrees_to_1e_9(loaded: Loaded, fixture_corpus: Fixture) -> None:
    """The headline assertion of this worker."""
    worst = 0.0
    worst_query = ""
    compared = 0
    for kind, query_text in fixture_corpus.queries:
        sql, oracle = _compare(loaded, query_text)
        assert [event for event, _ in sql] == [event for event, _ in oracle], (
            f"[{kind}] {query_text!r}: the SQL and the oracle returned different documents "
            f"or a different order"
        )
        for (event, sql_score), (_event, oracle_score) in zip(sql, oracle, strict=True):
            delta = abs(sql_score - oracle_score)
            compared += 1
            if delta > worst:
                worst, worst_query = delta, f"[{kind}] {query_text!r} on {event}"
        assert worst <= TOLERANCE, f"{worst_query}: |SQL - oracle| = {worst}"
    assert compared > 10_000, "the differential compared suspiciously few scores"
    print(f"\n[recall_lexical] worst |SQL - oracle| = {worst:.3e} over {compared} scores")


@pytest.mark.parametrize(
    "kind", ["single", "multi", "rare-identifier", "edge"]
)
def test_each_query_kind_is_actually_represented(
    fixture_corpus: Fixture, kind: str
) -> None:
    """The differential is only as good as its query mix; assert the mix exists."""
    assert sum(1 for k, _ in fixture_corpus.queries if k == kind) >= 20


def test_rare_identifier_queries_return_exactly_their_document(
    loaded: Loaded, fixture_corpus: Fixture
) -> None:
    """Channel D's reason for existing, measured rather than asserted in prose."""
    _backend, corpus, _tables, _stats = loaded
    hits = 0
    for kind, query_text in fixture_corpus.queries:
        if kind != "rare-identifier":
            continue
        sql, _oracle = _compare(loaded, query_text)
        assert sql, f"{query_text!r} returned nothing"
        top_text = corpus.texts[sql[0][0]]
        assert query_text.lower() in top_text.lower(), (
            f"the top hit for the unique tag {query_text!r} does not contain it"
        )
        hits += 1
    assert hits >= 20


def test_a_term_in_every_document_still_scores_positively(loaded: Loaded) -> None:
    """``df = N`` is where the textbook IDF goes negative and this one does not."""
    sql, oracle = _compare(loaded, "%LEL")
    assert len(sql) == 2000
    assert all(score > 0.0 for _event, score in sql)
    assert all(abs(a[1] - b[1]) <= TOLERANCE for a, b in zip(sql, oracle, strict=True))


def test_an_unseen_term_changes_nothing(loaded: Loaded, fixture_corpus: Fixture) -> None:
    """An unseen term must contribute nothing rather than a default IDF or an error."""
    present = fixture_corpus.unique_tags[0]
    without, _ = _compare(loaded, present)
    assert without, "premise: the tag is in the corpus"
    with_unseen, _ = _compare(loaded, f"{present} qqqqzzzz")
    assert with_unseen == without


@pytest.mark.parametrize(
    "params",
    [
        Bm25Params(k1=1.2, b=0.75),
        Bm25Params(k1=0.9, b=0.4),
        Bm25Params(k1=2.0, b=1.0),
        Bm25Params(k1=1.2, b=0.0),
        Bm25Params(k1=0.05, b=0.99),
    ],
)
def test_agreement_holds_across_the_parameter_space(
    loaded: Loaded, fixture_corpus: Fixture, params: Bm25Params
) -> None:
    """``k1`` and ``b`` are per-tenant policy; agreement at the default is not enough."""
    for _kind, query_text in fixture_corpus.queries[:40]:
        sql, oracle = _compare(loaded, query_text, params)
        for (_e, a), (_f, b) in zip(sql, oracle, strict=True):
            assert abs(a - b) <= TOLERANCE


def test_query_weighting_agrees_too(loaded: Loaded, fixture_corpus: Fixture) -> None:
    """The ``CASE`` arm of the statement is a different text and needs its own oracle run."""
    backend, corpus, tables, stats = loaded
    for _kind, query_text in fixture_corpus.queries[:40]:
        terms = analyse_query(query_text).terms
        weights = {term: 1.0 + (index % 4) for index, term in enumerate(terms)}
        sql = bm25_search(
            backend.execute,
            site_id=corpus.site_id,
            terms=weights,
            limit=UNTRUNCATED,
            stats=stats,
            style=backend.style,
        )
        oracle = reference_bm25(
            tables, site_id=corpus.site_id, terms=weights, stats=stats, limit=UNTRUNCATED
        )
        assert [e for e, _ in sql] == [e for e, _ in oracle]
        for (_e, a), (_f, b) in zip(sql, oracle, strict=True):
            assert abs(a - b) <= TOLERANCE


def test_the_limit_truncates_the_same_head(loaded: Loaded, fixture_corpus: Fixture) -> None:
    backend, corpus, tables, stats = loaded
    for _kind, query_text in fixture_corpus.queries[:60]:
        terms = analyse_query(query_text).terms
        sql = bm25_search(
            backend.execute,
            site_id=corpus.site_id,
            terms=terms,
            limit=10,
            stats=stats,
            style=backend.style,
        )
        oracle = reference_bm25(
            tables, site_id=corpus.site_id, terms=terms, stats=stats, limit=10
        )
        assert len(sql) <= 10
        assert [e for e, _ in sql] == [e for e, _ in oracle]


# ── PL-2: the differential must be able to fail ──────────────────────────────────────────────


def test_the_differential_can_fail(loaded: Loaded, fixture_corpus: Fixture) -> None:
    """Run the oracle with the wrong ``b`` and demand disagreement.

    Without this, a differential that silently compared a list against itself — or that ran
    over a corpus where every document had the same length, so ``b`` did not matter — would be
    green forever while proving nothing.
    """
    backend, corpus, tables, stats = loaded
    disagreements = 0
    for _kind, query_text in fixture_corpus.queries[:40]:
        terms = analyse_query(query_text).terms
        sql = bm25_search(
            backend.execute,
            site_id=corpus.site_id,
            terms=terms,
            limit=UNTRUNCATED,
            stats=stats,
            style=backend.style,
        )
        wrong = reference_bm25(
            tables,
            site_id=corpus.site_id,
            terms=terms,
            stats=stats,
            limit=UNTRUNCATED,
            params=Bm25Params(k1=1.2, b=0.10),
        )
        by_event = dict(wrong)
        if any(
            abs(score - by_event.get(event, math.inf)) > TOLERANCE for event, score in sql
        ):
            disagreements += 1
    assert disagreements >= 30, (
        "a deliberately wrong oracle agreed with the SQL, so the differential is not "
        "measuring the arithmetic it claims to measure"
    )


def test_a_mutated_idf_is_caught(loaded: Loaded) -> None:
    """The specific mutation this file exists for: IDF without the ``+ 1``.

    Recomputed here by hand rather than by patching the oracle, so the assertion is about the
    arithmetic and not about monkeypatching.
    """
    _backend, corpus, tables, stats = loaded
    sql, _oracle = _compare(loaded, "%LEL")
    df_by_term = {term: df for _site, term, df in tables.stats}
    lengths = dict(tables.doclen)
    weights = {
        event: weight
        for site, term, event, weight in tables.posting
        if site == corpus.site_id and term == "lel"
    }
    textbook_idf = math.log(
        (stats.n_docs - df_by_term["lel"] + 0.5) / (df_by_term["lel"] + 0.5)
    )
    assert textbook_idf < 0.0, "premise: df = N is where the textbook IDF is negative"
    event, score = sql[0]
    weight = weights[event]
    tf_norm = (weight * 2.2) / (
        weight + 1.2 * (0.25 + 0.75 * lengths[event] / stats.avgdl)
    )
    assert abs(score - textbook_idf * tf_norm) > TOLERANCE
    assert score > 0.0 > textbook_idf * tf_norm
