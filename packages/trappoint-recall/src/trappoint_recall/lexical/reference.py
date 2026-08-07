# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""The oracle: BM25 by brute force over the three tables, in Python, deliberately naive.

BM25 written directly in SQL is exactly the kind of code that is subtly wrong and never
noticed — an ``IDF`` that forgets the ``+ 1``, a length normalisation that divides by the
document's length instead of the ratio, a ``sum`` that silently drops a term because an inner
join lost a row.  Every one of those still returns a plausible ranked list.

So this module exists to disagree.  It reads the **same three tables as rows**, joins them the
same way, and computes the same arithmetic in the most boring possible manner.  It is not an
implementation to be used in production; it is the thing the production statement is measured
against, across 200 queries on a 2 000-document fixture, to 1e-9
(``tests/integration/recall_lexical/test_sql_vs_reference.py``).

Two semantics are copied from the SQL on purpose because they are easy to get wrong in
opposite directions:

* the joins are **inner**.  A posting whose term has no ``lex_stats`` row, or whose document
  has no ``lex_doclen`` row, contributes nothing.  It does not contribute a default IDF and it
  does not raise.  ``bm25.orphan_postings_statement`` exists so that this silence is audited
  rather than assumed;
* ``N`` and ``avgdl`` are **inputs**, not recomputed here.  If the oracle derived its own
  statistics it would agree with the SQL only when both derived the same ones, which is a
  weaker test of the thing actually being tested.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from trappoint_recall.lexical.bm25 import DEFAULT_BM25, Bm25Params, CorpusStats

__all__ = ["LexicalTables", "reference_bm25", "reference_corpus_stats"]


@dataclass(frozen=True, slots=True)
class LexicalTables:
    """The three tables as row tuples, in their DDL column order."""

    posting: tuple[tuple[str, str, str, float], ...]  # (site_id, term, event_id, weight)
    stats: tuple[tuple[str, str, int], ...]  # (site_id, term, df)
    doclen: tuple[tuple[str, int], ...]  # (event_id, len)


def reference_bm25(
    tables: LexicalTables,
    *,
    site_id: str,
    terms: Sequence[str] | Mapping[str, float],
    stats: CorpusStats,
    limit: int,
    params: Bm25Params = DEFAULT_BM25,
) -> list[tuple[str, float]]:
    """Brute-force BM25.  ``O(len(posting))`` on purpose: clarity beats speed in an oracle."""
    if isinstance(terms, Mapping):
        weights: dict[str, float] = {str(k): float(v) for k, v in terms.items()}
        if all(w == 1.0 for w in weights.values()):
            weights = dict.fromkeys(weights, 1.0)
    else:
        weights = dict.fromkeys(terms, 1.0)

    df_by_term = {term: df for (site, term, df) in tables.stats if site == site_id}
    len_by_event = dict(tables.doclen)

    n_docs = float(stats.n_docs)
    avgdl = float(stats.avgdl)
    k1 = params.k1
    b = params.b

    scores: dict[str, float] = {}
    for site, term, event_id, weight in tables.posting:
        if site != site_id:
            continue
        query_weight = weights.get(term)
        if query_weight is None:
            continue
        df = df_by_term.get(term)  # INNER JOIN lex_stats
        if df is None:
            continue
        doc_len = len_by_event.get(event_id)  # INNER JOIN lex_doclen
        if doc_len is None:
            continue
        df_f = float(df)
        idf = math.log(((n_docs - df_f) + 0.5) / (df_f + 0.5) + 1.0)
        norm = weight + k1 * ((1.0 - b) + b * (float(doc_len) / avgdl))
        scores[event_id] = scores.get(event_id, 0.0) + query_weight * idf * (
            weight * (k1 + 1.0) / norm
        )

    ranked = sorted(scores.items(), key=lambda item: (-item[1], item[0]))
    return ranked[:limit]


def reference_corpus_stats(tables: LexicalTables, *, site_id: str) -> CorpusStats:
    """``N`` and ``avgdl`` the way ``bm25.corpus_stats_statement`` computes them.

    Note what "the site's documents" means here: the distinct ``event_id`` values appearing in
    ``lex_posting`` for the site, intersected with the documents that have a length.  It is
    *not* every row of ``lex_doclen``, because that table carries no ``site_id``.
    """
    events = {event_id for (site, _term, event_id, _w) in tables.posting if site == site_id}
    lengths = [length for (event_id, length) in tables.doclen if event_id in events]
    if not lengths:
        return CorpusStats(n_docs=0, avgdl=0.0)
    return CorpusStats(n_docs=len(lengths), avgdl=sum(lengths) / len(lengths))
