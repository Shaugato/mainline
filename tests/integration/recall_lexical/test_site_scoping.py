# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""One site can never reach another site's postings — through any statement in this module.

``lex_posting`` and ``lex_stats`` are keyed ``(site_id, …)``.  Nothing in channel D enforces
that at the database level: there is no trigger and no policy here, only the discipline that
**every statement carries the predicate**.  So it is asserted, statement by statement, with
two sites holding deliberately colliding data — the same terms, in the same shapes, with
different weights and different document frequencies.

Colliding on purpose is the point.  A scoping bug over two sites with disjoint vocabularies
produces no visible symptom; over two sites that both index ``K-401`` it produces a permit at
one site being blocked by an incident at another, which is both a wrong answer and a
confidentiality breach.

RLS is the kernel domain's mechanism and is not duplicated here.  This band proves that the
lexical statements are correct *before* any policy is applied, which is what makes a later RLS
failure a defence-in-depth failure rather than the only thing standing between two tenants.
"""

from __future__ import annotations

import uuid

import pytest
from trappoint_recall.lexical.analyser import analyse_query
from trappoint_recall.lexical.bm25 import (
    bm25_search,
    fetch_corpus_stats,
    orphan_postings_statement,
    stats_drift_statement,
)
from trappoint_recall.lexical.postings import (
    build_document_postings,
    rebuild_site,
    snapshot_tables,
    upsert_document,
)

OURS = "Vessel K-401 overpressured; H2S reached 10 ppm at 25 %LEL."
THEIRS = (
    "Vessel K-401 overpressured; H2S reached 10 ppm at 25 %LEL. "
    "Vessel K-401 again. Vessel K-401 a third time. Confidential to the other site."
)


@pytest.fixture()
def two_sites(backend):  # noqa: ANN001, ANN201
    """Two sites whose documents share every term and differ in weight and length."""
    ours, theirs = str(uuid.uuid4()), str(uuid.uuid4())
    mine = build_document_postings(str(uuid.uuid4()), OURS)
    yours = build_document_postings(str(uuid.uuid4()), THEIRS)
    rebuild_site(backend.execute, site_id=ours, documents=[mine], style=backend.style)
    rebuild_site(backend.execute, site_id=theirs, documents=[yours], style=backend.style)
    return backend, ours, theirs, mine, yours


def test_the_two_sites_really_do_collide(two_sites) -> None:  # noqa: ANN001
    """Premise. A scoping test over disjoint vocabularies asserts nothing."""
    _backend, _ours, _theirs, mine, yours = two_sites
    assert set(mine.weights) & set(yours.weights)
    assert "k-401" in mine.weights and "k-401" in yours.weights
    assert mine.weights["k-401"] != yours.weights["k-401"]
    assert mine.length != yours.length


def test_a_search_never_returns_another_sites_document(two_sites) -> None:  # noqa: ANN001
    backend, ours, theirs, mine, yours = two_sites
    terms = analyse_query("K-401 H2S 25 %LEL").terms
    for site, expected in ((ours, mine.event_id), (theirs, yours.event_id)):
        hits = bm25_search(
            backend.execute,
            site_id=site,
            terms=terms,
            limit=100,
            style=backend.style,
        )
        assert [event for event, _ in hits] == [expected]


def test_the_other_sites_term_weights_do_not_leak_into_our_scores(two_sites) -> None:  # noqa: ANN001
    """The subtler failure: right documents, wrong numbers.

    If the join to ``lex_stats`` lost its ``site_id`` predicate the correct document would
    still be returned — scored with the *other* site's document frequency.
    """
    backend, ours, theirs, _mine, _yours = two_sites
    terms = analyse_query("K-401").terms
    alone_stats = fetch_corpus_stats(backend.execute, site_id=ours, style=backend.style)
    ours_hits = bm25_search(
        backend.execute, site_id=ours, terms=terms, limit=10,
        stats=alone_stats, style=backend.style,
    )
    theirs_hits = bm25_search(
        backend.execute, site_id=theirs, terms=terms, limit=10, style=backend.style
    )
    assert ours_hits and theirs_hits
    assert ours_hits[0][1] != theirs_hits[0][1]


def test_the_statistics_statement_is_site_scoped(two_sites) -> None:  # noqa: ANN001
    backend, ours, theirs, mine, yours = two_sites
    assert fetch_corpus_stats(backend.execute, site_id=ours, style=backend.style) != (
        fetch_corpus_stats(backend.execute, site_id=theirs, style=backend.style)
    )
    stats = fetch_corpus_stats(backend.execute, site_id=ours, style=backend.style)
    assert stats.n_docs == 1
    assert stats.avgdl == float(mine.length)
    assert stats.avgdl != float(yours.length)


def test_the_snapshot_is_site_scoped(two_sites) -> None:  # noqa: ANN001
    backend, ours, theirs, mine, yours = two_sites
    snapshot = snapshot_tables(backend.execute, site_id=ours, style=backend.style)
    assert {site for site, _t, _e, _w in snapshot.posting} == {ours}
    assert {event for _s, _t, event, _w in snapshot.posting} == {mine.event_id}
    assert dict(snapshot.doclen) == {mine.event_id: mine.length}
    assert yours.event_id not in dict(snapshot.doclen)
    assert theirs not in {site for site, _t, _df in snapshot.stats}


def test_a_rebuild_does_not_touch_the_other_site(two_sites) -> None:  # noqa: ANN001
    """A maintenance job that reached across tenants would be discovered late and badly."""
    backend, ours, theirs, mine, _yours = two_sites
    before = snapshot_tables(backend.execute, site_id=theirs, style=backend.style)
    rebuild_site(backend.execute, site_id=ours, documents=[mine], style=backend.style)
    rebuild_site(backend.execute, site_id=ours, documents=[], style=backend.style)
    after = snapshot_tables(backend.execute, site_id=theirs, style=backend.style)
    assert after == before
    assert after.posting, "premise: the other site still has postings"


def test_an_upsert_does_not_touch_the_other_site(two_sites) -> None:  # noqa: ANN001
    backend, ours, theirs, mine, _yours = two_sites
    before = snapshot_tables(backend.execute, site_id=theirs, style=backend.style)
    upsert_document(backend.execute, site_id=ours, document=mine, style=backend.style)
    assert snapshot_tables(backend.execute, site_id=theirs, style=backend.style) == before


def test_the_integrity_statements_are_site_scoped(two_sites) -> None:  # noqa: ANN001
    """Both report clean here; the assertion is that they report on ONE site."""
    backend, ours, _theirs, _mine, _yours = two_sites
    for builder in (orphan_postings_statement, stats_drift_statement):
        statement = builder(site_id=ours, style=backend.style)
        assert backend.execute(statement.sql, statement.params) == []


def test_an_orphan_posting_is_reported_rather_than_silently_dropped(backend) -> None:  # noqa: ANN001
    """PL-2 for the integrity statement: manufacture the defect and demand the report.

    A posting whose document has no length is invisible to BM25 because the join to
    ``lex_doclen`` is inner. That is the right arithmetic and the wrong silence, so it is
    audited.
    """
    site = str(uuid.uuid4())
    document = build_document_postings(str(uuid.uuid4()), OURS)
    rebuild_site(backend.execute, site_id=site, documents=[document], style=backend.style)
    statement = orphan_postings_statement(site_id=site, style=backend.style)
    assert backend.execute(statement.sql, statement.params) == []

    from trappoint_recall.lexical.executor import SqlBuilder, Statement

    builder = SqlBuilder(backend.style)
    sql = "DELETE FROM mainline.lex_doclen WHERE event_id = " + builder.bind(
        document.event_id
    )
    deletion = Statement(sql, builder.params, backend.style)
    backend.execute(deletion.sql, deletion.params)

    rows = backend.execute(statement.sql, statement.params)
    assert [str(row[0]) for row in rows] == [document.event_id]
    assert (
        bm25_search(
            backend.execute,
            site_id=site,
            terms=analyse_query("K-401").terms,
            limit=10,
            stats=None,
            style=backend.style,
        )
        == []
    ), "premise: without a length row the document is unreachable"
