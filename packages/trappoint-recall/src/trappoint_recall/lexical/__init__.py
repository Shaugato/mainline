# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""Channel D — explicit BM25 over identifier-preserving tokens, in SQL.

CockroachDB has no BM25, and PostgreSQL's ``ts_rank`` — which its full-text search is
compatible with — has neither IDF nor length normalisation.  For a recall channel whose whole
job is ``K-401``, ``TK-12``, ``H2S``, ``%LEL``, ``30 CFR 57.22239`` and OEM part numbers, that
is disqualifying: without IDF the rare identifier that carries the hazard scores like "the".

So this package does four things and nothing else:

:mod:`~trappoint_recall.lexical.analyser`
    A deterministic, versioned analyser that preserves identifier structure, SI-normalises
    quantities, keeps citations and CAS numbers whole, and stems only prose — with a token
    class on every term and a golden digest so a change to it cannot be silent.
:mod:`~trappoint_recall.lexical.postings`
    Idempotent, site-scoped writers for ``lex_posting`` / ``lex_stats`` / ``lex_doclen``, in
    both an incremental and a full-rebuild flavour, driven by that same analyser.
:mod:`~trappoint_recall.lexical.bm25`
    One parameterised statement implementing BM25 (k1 = 1.2, b = 0.75) with correct IDF and
    length normalisation, constrained to ``lex_posting``'s primary-key prefix.
:mod:`~trappoint_recall.lexical.reference` and :mod:`~trappoint_recall.lexical.plan`
    The oracle the SQL is differentially tested against, and the ``EXPLAIN`` assertion that
    refuses a silently-correct full scan.

There is no database driver here.  Everything takes an
:class:`~trappoint_recall.lexical.executor.Executor` callable, which is what lets the
arithmetic be checked against a second SQL engine on a laptop with no cluster.
"""

from __future__ import annotations

from trappoint_recall.lexical.analyser import (
    ANALYSER_VERSION,
    Token,
    TokenClass,
    analyse,
    analyse_query,
    is_well_formed_term,
    rule_fingerprint,
)
from trappoint_recall.lexical.bm25 import (
    DEFAULT_BM25,
    Bm25Params,
    CorpusStats,
    bm25_search,
    build_bm25_statement,
    corpus_stats_statement,
    explain_of,
    fetch_corpus_stats,
    orphan_postings_statement,
    stats_drift_statement,
)
from trappoint_recall.lexical.digest import corpus_digest, document_digest
from trappoint_recall.lexical.executor import (
    Executor,
    ParamStyle,
    Statement,
    UnsafeLiteralError,
    normalise_placeholders,
)
from trappoint_recall.lexical.plan import (
    PlanAssertionError,
    ScanNode,
    assert_constrained_lex_scan,
    parse_plan,
    plan_digest,
    plan_text_from_rows,
)
from trappoint_recall.lexical.postings import (
    DocumentPostings,
    WriteReport,
    build_document_postings,
    content_digest,
    delete_document,
    rebuild_site,
    snapshot_tables,
    upsert_document,
)
from trappoint_recall.lexical.reference import (
    LexicalTables,
    reference_bm25,
    reference_corpus_stats,
)

__all__ = [
    "ANALYSER_VERSION",
    "DEFAULT_BM25",
    "Bm25Params",
    "CorpusStats",
    "DocumentPostings",
    "Executor",
    "LexicalTables",
    "ParamStyle",
    "PlanAssertionError",
    "ScanNode",
    "Statement",
    "Token",
    "TokenClass",
    "UnsafeLiteralError",
    "WriteReport",
    "analyse",
    "analyse_query",
    "assert_constrained_lex_scan",
    "bm25_search",
    "build_bm25_statement",
    "build_document_postings",
    "content_digest",
    "corpus_digest",
    "corpus_stats_statement",
    "delete_document",
    "document_digest",
    "explain_of",
    "fetch_corpus_stats",
    "is_well_formed_term",
    "normalise_placeholders",
    "orphan_postings_statement",
    "parse_plan",
    "plan_digest",
    "plan_text_from_rows",
    "rebuild_site",
    "reference_bm25",
    "reference_corpus_stats",
    "rule_fingerprint",
    "snapshot_tables",
    "stats_drift_statement",
    "upsert_document",
]
