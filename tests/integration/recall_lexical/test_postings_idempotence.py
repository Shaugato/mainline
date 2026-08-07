# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""Repeated ingest must leave the index untouched, and the two write paths must agree.

Ingestion in this system is driven by a changefeed and re-run on retry, on replay and after a
partial failure.  If a second ingest of an unchanged document writes anything at all, then
every replay produces a new MVCC version, a changefeed row and an audit entry for a change
that did not happen — and if it writes anything *different*, ``df`` drifts, IDF drifts with
it, and the channel that exists to surface a fatality quietly re-ranks.

Two claims, asserted separately because they can fail independently:

1. **Zero writes on a repeat.**  Not "the same bytes again" — none.  The writer reads what is
   there, diffs, and issues nothing when the diff is empty.  A digest comparison alone cannot
   tell those apart, and the difference is exactly what shows up in a changefeed.
2. **The incremental path and the full-rebuild path produce byte-identical tables.**  They are
   different SQL; if they could disagree about what ``df`` means, a corpus built by ingest and
   the same corpus rebuilt would score differently.

Every test here works under its own ``site_id``, so it runs against a shared engine without
tearing anything down — which is deliberate, because a suite that isolates by truncating
cannot notice a statement that reaches another site's rows.
"""

from __future__ import annotations

import uuid

import pytest
from _corpus import Fixture
from trappoint_recall.lexical.bm25 import fetch_corpus_stats
from trappoint_recall.lexical.postings import (
    DocumentPostings,
    build_document_postings,
    content_digest,
    delete_document,
    rebuild_site,
    snapshot_tables,
    upsert_document,
)


def new_site() -> str:
    return str(uuid.uuid4())


def new_event() -> str:
    return str(uuid.uuid4())


DOCS = {
    "Vessel K-401 overpressured; H2S reached 10 ppm at 25 %LEL under a hot work permit.",
    "Pump K402 tripped on high vibration during maintenance. No hazardous atmosphere.",
    "Cited under 30 CFR 57.22239 after the K-401 relief valve lifted late.",
    "Substance CAS 7783-06-4 was released from the sump at 689 kPa.",
    "The isolation valve was not closed before the lock-out was removed.",
}


@pytest.fixture()
def corpus_slice() -> list[DocumentPostings]:
    return [build_document_postings(new_event(), text) for text in sorted(DOCS)]


def test_a_repeated_ingest_writes_nothing(backend, corpus_slice) -> None:  # noqa: ANN001
    site = new_site()
    first = [
        upsert_document(backend.execute, site_id=site, document=d, style=backend.style)
        for d in corpus_slice
    ]
    assert all(report.rows_written > 0 for report in first)

    before = snapshot_tables(backend.execute, site_id=site, style=backend.style)
    second = [
        upsert_document(backend.execute, site_id=site, document=d, style=backend.style)
        for d in corpus_slice
    ]
    after = snapshot_tables(backend.execute, site_id=site, style=backend.style)

    assert [report.rows_written for report in second] == [0] * len(corpus_slice), (
        "a repeated ingest issued writes. Each one is a new MVCC version and a changefeed "
        "row for a change that did not happen."
    )
    assert content_digest(after) == content_digest(before)
    assert after == before


def test_a_third_and_fourth_ingest_are_also_silent(backend, corpus_slice) -> None:  # noqa: ANN001
    site = new_site()
    for _ in range(2):
        for document in corpus_slice:
            upsert_document(
                backend.execute, site_id=site, document=document, style=backend.style
            )
    digests = []
    for _ in range(2):
        reports = [
            upsert_document(
                backend.execute, site_id=site, document=document, style=backend.style
            )
            for document in corpus_slice
        ]
        assert sum(r.rows_written for r in reports) == 0
        digests.append(
            content_digest(snapshot_tables(backend.execute, site_id=site, style=backend.style))
        )
    assert len(set(digests)) == 1


def test_incremental_and_rebuild_agree_byte_for_byte(backend, corpus_slice) -> None:  # noqa: ANN001
    incremental_site = new_site()
    rebuilt_site = new_site()
    for document in corpus_slice:
        upsert_document(
            backend.execute, site_id=incremental_site, document=document, style=backend.style
        )
    rebuild_site(
        backend.execute,
        site_id=rebuilt_site,
        documents=corpus_slice,
        style=backend.style,
    )

    a = snapshot_tables(backend.execute, site_id=incremental_site, style=backend.style)
    b = snapshot_tables(backend.execute, site_id=rebuilt_site, style=backend.style)
    # The site_id column necessarily differs; everything else must not.
    assert sorted((t, e, w) for _s, t, e, w in a.posting) == sorted(
        (t, e, w) for _s, t, e, w in b.posting
    )
    assert sorted((t, df) for _s, t, df in a.stats) == sorted(
        (t, df) for _s, t, df in b.stats
    )
    assert sorted(a.doclen) == sorted(b.doclen)


def test_a_rebuild_is_itself_idempotent(backend, corpus_slice) -> None:  # noqa: ANN001
    site = new_site()
    rebuild_site(
        backend.execute, site_id=site, documents=corpus_slice, style=backend.style
    )
    first = content_digest(snapshot_tables(backend.execute, site_id=site, style=backend.style))
    rebuild_site(
        backend.execute, site_id=site, documents=corpus_slice, style=backend.style
    )
    second = content_digest(snapshot_tables(backend.execute, site_id=site, style=backend.style))
    assert first == second


def test_document_frequency_matches_the_posting_list(backend, corpus_slice) -> None:  # noqa: ANN001
    """``df`` is the only input to IDF; drift here re-ranks silently rather than raising."""
    site = new_site()
    for document in corpus_slice:
        upsert_document(
            backend.execute, site_id=site, document=document, style=backend.style
        )
    tables = snapshot_tables(backend.execute, site_id=site, style=backend.style)
    actual: dict[str, int] = {}
    for _site, term, _event, _weight in tables.posting:
        actual[term] = actual.get(term, 0) + 1
    recorded = {term: df for _site, term, df in tables.stats}
    assert recorded == actual


def test_editing_a_document_moves_only_what_changed(backend) -> None:  # noqa: ANN001
    site = new_site()
    event = new_event()
    original = build_document_postings(event, "Vessel K-401 overpressured at 100 psi.")
    edited = build_document_postings(event, "Vessel K-401 overpressured at 200 psi.")

    upsert_document(backend.execute, site_id=site, document=original, style=backend.style)
    report = upsert_document(
        backend.execute, site_id=site, document=edited, style=backend.style
    )
    assert report.rows_written > 0

    tables = snapshot_tables(backend.execute, site_id=site, style=backend.style)
    terms = {term for _s, term, _e, _w in tables.posting}
    assert "q:pressure:1.37895e+06" in terms
    assert "q:pressure:689476" not in terms, "the superseded quantity term was left behind"
    assert "k-401" in terms

    # And the edit is itself idempotent.
    assert (
        upsert_document(
            backend.execute, site_id=site, document=edited, style=backend.style
        ).rows_written
        == 0
    )


def test_deleting_a_document_repairs_the_document_frequencies(backend) -> None:  # noqa: ANN001
    site = new_site()
    keep = build_document_postings(new_event(), "Vessel K-401 overpressured at 100 psi.")
    drop = build_document_postings(new_event(), "Vessel K-401 leaked at 100 psi.")
    for document in (keep, drop):
        upsert_document(
            backend.execute, site_id=site, document=document, style=backend.style
        )

    before = {t: df for _s, t, df in snapshot_tables(
        backend.execute, site_id=site, style=backend.style
    ).stats}
    assert before["k-401"] == 2

    delete_document(
        backend.execute, site_id=site, event_id=drop.event_id, style=backend.style
    )
    tables = snapshot_tables(backend.execute, site_id=site, style=backend.style)
    after = {t: df for _s, t, df in tables.stats}
    assert after["k-401"] == 1
    assert "leak" not in after, "a term with no remaining postings kept a lex_stats row"
    assert {event for _s, _t, event, _w in tables.posting} == {keep.event_id}
    assert dict(tables.doclen) == {keep.event_id: keep.length}


def test_the_full_fixture_rebuilds_identically(backend, fixture_corpus: Fixture) -> None:  # noqa: ANN001
    """The completion test at fixture scale rather than on five documents."""
    site = new_site()
    documents = fixture_corpus.documents[:400]
    rebuild_site(backend.execute, site_id=site, documents=documents, style=backend.style)
    first = snapshot_tables(backend.execute, site_id=site, style=backend.style)
    stats_first = fetch_corpus_stats(backend.execute, site_id=site, style=backend.style)

    reports = [
        upsert_document(backend.execute, site_id=site, document=d, style=backend.style)
        for d in documents
    ]
    assert sum(r.rows_written for r in reports) == 0, (
        "an incremental ingest over a freshly rebuilt index wanted to write. The two paths "
        "disagree about what the index should contain."
    )
    second = snapshot_tables(backend.execute, site_id=site, style=backend.style)
    assert content_digest(second) == content_digest(first)
    assert fetch_corpus_stats(backend.execute, site_id=site, style=backend.style) == stats_first


def test_the_digest_is_not_vacuous(backend, corpus_slice) -> None:  # noqa: ANN001
    """PL-2: the digest must move when the index moves."""
    site = new_site()
    rebuild_site(
        backend.execute, site_id=site, documents=corpus_slice[:-1], style=backend.style
    )
    partial = content_digest(
        snapshot_tables(backend.execute, site_id=site, style=backend.style)
    )
    rebuild_site(
        backend.execute, site_id=site, documents=corpus_slice, style=backend.style
    )
    complete = content_digest(
        snapshot_tables(backend.execute, site_id=site, style=backend.style)
    )
    assert partial != complete
