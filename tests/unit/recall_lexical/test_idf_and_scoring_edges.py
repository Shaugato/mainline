# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""IDF edge cases and the scoring guards, against the pure-Python oracle.

``ln((N - df + 0.5) / (df + 0.5) + 1)`` is the Lucene form of Robertson's IDF, and the ``+ 1``
is the whole reason it is that form: the textbook ``ln((N - df + 0.5)/(df + 0.5))`` goes
**negative** once a term appears in more than half the corpus.  A negative IDF means a document
is penalised for containing a query term, and in a two-term query it means a document
containing both terms can rank below a document containing one.  In this product that
arithmetic decides whether a fatality is surfaced to a permit approver, so the boundary is
asserted rather than assumed.

The oracle is the definition here; the SQL is checked against it in
``tests/integration/recall_lexical/test_sql_vs_reference.py``.
"""

from __future__ import annotations

import itertools
import math

import pytest
from trappoint_recall.lexical.bm25 import Bm25Params, CorpusStats, build_bm25_statement
from trappoint_recall.lexical.executor import ParamStyle, UnsafeLiteralError
from trappoint_recall.lexical.reference import LexicalTables, reference_bm25

SITE = "11111111-1111-4111-8111-111111111111"
OTHER = "22222222-2222-4222-8222-222222222222"


def idf(n_docs: int, df: int) -> float:
    return math.log((n_docs - df + 0.5) / (df + 0.5) + 1.0)


def tables(*, n_docs: int, df: int, term: str = "k-401", doc_len: int = 10) -> LexicalTables:
    posting = tuple(
        (SITE, term, f"e{i}", 1.0) for i in range(df)
    )
    doclen = tuple((f"e{i}", doc_len) for i in range(n_docs))
    return LexicalTables(
        posting=posting, stats=((SITE, term, df),), doclen=doclen
    )


# ── the boundary the `+ 1` exists for ────────────────────────────────────────────────────────


def test_idf_is_positive_when_the_term_is_in_every_document() -> None:
    assert idf(1000, 1000) > 0.0


def test_idf_is_positive_where_the_textbook_form_goes_negative() -> None:
    n = 1000
    common = 600  # a term in 60% of the corpus: `%LEL`, `valve`, `permit`
    textbook = math.log((n - common + 0.5) / (common + 0.5))
    assert textbook < 0.0, "premise: the form without the +1 is negative here"
    assert idf(n, common) > 0.0


def test_idf_is_monotonically_decreasing_in_df() -> None:
    values = [idf(1000, df) for df in range(1, 1001)]
    assert all(later < earlier for earlier, later in itertools.pairwise(values))


def test_a_rare_identifier_outscores_a_ubiquitous_one_by_orders_of_magnitude() -> None:
    """The reason channel D exists at all."""
    assert idf(2000, 1) / idf(2000, 2000) > 100.0


# ── the same edges, through the scorer ───────────────────────────────────────────────────────


def test_df_equal_to_n_still_produces_a_positive_score() -> None:
    ranked = reference_bm25(
        tables(n_docs=50, df=50),
        site_id=SITE,
        terms=["k-401"],
        stats=CorpusStats(n_docs=50, avgdl=10.0),
        limit=100,
    )
    assert len(ranked) == 50
    assert all(score > 0.0 for _event, score in ranked)


def test_df_equal_to_one() -> None:
    ranked = reference_bm25(
        tables(n_docs=2000, df=1),
        site_id=SITE,
        terms=["k-401"],
        stats=CorpusStats(n_docs=2000, avgdl=10.0),
        limit=10,
    )
    assert [event for event, _ in ranked] == ["e0"]
    expected = idf(2000, 1) * (1.0 * 2.2) / (1.0 + 1.2 * (0.25 + 0.75 * 1.0))
    assert ranked[0][1] == pytest.approx(expected, abs=1e-12)


def test_an_unseen_term_contributes_nothing_and_does_not_raise() -> None:
    ranked = reference_bm25(
        tables(n_docs=10, df=3),
        site_id=SITE,
        terms=["k-401", "never-indexed"],
        stats=CorpusStats(n_docs=10, avgdl=10.0),
        limit=10,
    )
    only_known = reference_bm25(
        tables(n_docs=10, df=3),
        site_id=SITE,
        terms=["k-401"],
        stats=CorpusStats(n_docs=10, avgdl=10.0),
        limit=10,
    )
    assert ranked == only_known


def test_a_query_of_only_unseen_terms_returns_nothing() -> None:
    assert (
        reference_bm25(
            tables(n_docs=10, df=3),
            site_id=SITE,
            terms=["never-indexed"],
            stats=CorpusStats(n_docs=10, avgdl=10.0),
            limit=10,
        )
        == []
    )


def test_length_normalisation_favours_the_shorter_document() -> None:
    """Same term, same tf, different lengths: the terse Part 50 narrative must win."""
    tbl = LexicalTables(
        posting=((SITE, "k-401", "short", 1.0), (SITE, "k-401", "long", 1.0)),
        stats=((SITE, "k-401", 2),),
        doclen=(("short", 20), ("long", 400)),
    )
    ranked = reference_bm25(
        tbl,
        site_id=SITE,
        terms=["k-401"],
        stats=CorpusStats(n_docs=2, avgdl=210.0),
        limit=10,
    )
    assert [event for event, _ in ranked] == ["short", "long"]


def test_b_zero_disables_length_normalisation() -> None:
    tbl = LexicalTables(
        posting=((SITE, "k-401", "short", 1.0), (SITE, "k-401", "long", 1.0)),
        stats=((SITE, "k-401", 2),),
        doclen=(("short", 20), ("long", 400)),
    )
    ranked = reference_bm25(
        tbl,
        site_id=SITE,
        terms=["k-401"],
        stats=CorpusStats(n_docs=2, avgdl=210.0),
        limit=10,
        params=Bm25Params(k1=1.2, b=0.0),
    )
    assert ranked[0][1] == pytest.approx(ranked[1][1], abs=1e-15)


def test_ties_break_deterministically_on_event_id() -> None:
    tbl = LexicalTables(
        posting=((SITE, "t", "zzz", 1.0), (SITE, "t", "aaa", 1.0)),
        stats=((SITE, "t", 2),),
        doclen=(("zzz", 10), ("aaa", 10)),
    )
    ranked = reference_bm25(
        tbl, site_id=SITE, terms=["t"], stats=CorpusStats(n_docs=2, avgdl=10.0), limit=10
    )
    assert [event for event, _ in ranked] == ["aaa", "zzz"]


def test_another_sites_postings_are_never_reachable() -> None:
    tbl = LexicalTables(
        posting=((OTHER, "k-401", "theirs", 1.0),),
        stats=((OTHER, "k-401", 1),),
        doclen=(("theirs", 10),),
    )
    assert (
        reference_bm25(
            tbl,
            site_id=SITE,
            terms=["k-401"],
            stats=CorpusStats(n_docs=1, avgdl=10.0),
            limit=10,
        )
        == []
    )


def test_an_inner_join_silently_drops_a_posting_with_no_document_length() -> None:
    """Documented behaviour, asserted so it cannot become accidental.

    ``bm25.orphan_postings_statement`` exists to make this auditable rather than assumed.
    """
    tbl = LexicalTables(
        posting=((SITE, "k-401", "has-len", 1.0), (SITE, "k-401", "no-len", 1.0)),
        stats=((SITE, "k-401", 2),),
        doclen=(("has-len", 10),),
    )
    ranked = reference_bm25(
        tbl, site_id=SITE, terms=["k-401"], stats=CorpusStats(n_docs=1, avgdl=10.0), limit=10
    )
    assert [event for event, _ in ranked] == ["has-len"]


# ── the guards the builder raises rather than returning something plausible ──────────────────


def test_an_empty_corpus_is_refused_rather_than_dividing_by_zero() -> None:
    with pytest.raises(ValueError, match="avgdl must be > 0"):
        CorpusStats(n_docs=5, avgdl=0.0)


def test_zero_document_corpus_is_representable_but_unscoreable() -> None:
    stats = CorpusStats(n_docs=0, avgdl=0.0)
    with pytest.raises(ValueError, match="empty corpus"):
        build_bm25_statement(site_id=SITE, terms=["k-401"], stats=stats, limit=5)


def test_an_empty_query_is_refused_rather_than_scanning_everything() -> None:
    with pytest.raises(ValueError, match="no query terms"):
        build_bm25_statement(
            site_id=SITE, terms=[], stats=CorpusStats(n_docs=10, avgdl=10.0), limit=5
        )


@pytest.mark.parametrize("k1", [0.0, -1.0])
def test_k1_must_be_positive(k1: float) -> None:
    with pytest.raises(ValueError, match="k1 must be"):
        Bm25Params(k1=k1, b=0.75)


@pytest.mark.parametrize("b", [-0.1, 1.1])
def test_b_must_be_a_fraction(b: float) -> None:
    with pytest.raises(ValueError, match="b must be"):
        Bm25Params(k1=1.2, b=b)


def test_terms_that_did_not_come_from_the_analyser_are_refused() -> None:
    stats = CorpusStats(n_docs=10, avgdl=10.0)
    with pytest.raises(ValueError, match="must come from the analyser"):
        build_bm25_statement(
            site_id=SITE, terms=["k-401'; DROP TABLE"], stats=stats, limit=5
        )


def test_a_site_id_that_is_not_a_uuid_shaped_string_is_refused_for_literal_rendering() -> None:
    stats = CorpusStats(n_docs=10, avgdl=10.0)
    with pytest.raises(UnsafeLiteralError):
        build_bm25_statement(
            site_id="'; DROP TABLE mainline.lex_posting; --",
            terms=["k-401"],
            stats=stats,
            limit=5,
            style=ParamStyle.LITERAL,
        )
