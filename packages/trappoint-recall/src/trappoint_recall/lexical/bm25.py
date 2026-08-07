# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""BM25 as one SQL statement, and the reasons every clause of it is shaped the way it is.

CockroachDB has no BM25.  Its full-text search is PostgreSQL-compatible, and PostgreSQL's
``ts_rank`` has **neither IDF nor length normalisation** — a semantics fact about Postgres,
not a CockroachDB gap.  For a channel whose entire job is ``K-401``, ``H2S``, ``%LEL`` and OEM
part numbers that is disqualifying: without IDF the rare identifier that carries the hazard
scores like the word "the", and without length normalisation a 40-page CSB report beats a
384-character MSHA Part 50 narrative for reasons that have nothing to do with recurrence.

So the scorer is explicit:

.. math::

    \\mathrm{score}(d, Q) = \\sum_{t \\in Q} w_q(t)
        \\cdot \\ln\\!\\left(\\frac{N - df_t + 0.5}{df_t + 0.5} + 1\\right)
        \\cdot \\frac{f_{t,d} \\cdot (k_1 + 1)}
                     {f_{t,d} + k_1 \\left(1 - b + b \\frac{|d|}{\\mathrm{avgdl}}\\right)}

with ``k1 = 1.2`` and ``b = 0.75``.  Four properties are load-bearing and each one is a
constraint on the emitted text, not a preference:

**One statement.**  The Managed MCP audit surface accepts exactly one statement per call, and
the gate path pays one round trip.  No CTE chain, no temp table, no second query for the
statistics — ``N`` and ``avgdl`` are bound parameters, produced by
:func:`corpus_stats_statement`, so the hot path stays a single constrained read.

**Weight-source agnostic.**  ``lex_posting.weight`` appears in the expression as
:math:`f_{t,d}` and nowhere else.  Nothing in this statement knows or cares whether that
number is a term frequency or a learned-sparse impact weight, so swapping the writer for a
SPLADE-style one is a change to :mod:`trappoint_recall.lexical.postings` alone, with no
schema change and no change here.

**Constrained, never a full scan.**  ``lex_posting``'s primary key is
``(site_id, term, event_id)``.  The ``WHERE p.site_id = … AND p.term IN (…)`` pair is exactly
the prefix the optimiser needs to build spans.  Under a query-weighted build the ``IN`` list
is *redundant* with the ``CASE`` — it is emitted anyway, and deliberately, because without it
channel D degrades to a full scan of every posting at the site while still returning the right
answer.  A silently-correct full scan is the worst kind of defect this design can have, so
:mod:`trappoint_recall.lexical.plan` asserts the plan and CI runs the assertion.

**Deterministic order.**  ``ORDER BY score DESC, p.event_id ASC``.  A ranked list handed to a
severity-graded admission rule must not depend on which range answered first.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Final

from trappoint_recall.lexical.analyser import is_well_formed_term
from trappoint_recall.lexical.executor import (
    MCP_MAX_SELECT_ROWS,
    Executor,
    ParamStyle,
    SqlBuilder,
    Statement,
    as_float,
    as_int,
    as_text,
    check_identifier,
)

__all__ = [
    "DEFAULT_BM25",
    "Bm25Params",
    "CorpusStats",
    "bm25_search",
    "build_bm25_statement",
    "corpus_stats_statement",
    "explain_of",
    "fetch_corpus_stats",
    "orphan_postings_statement",
    "stats_drift_statement",
]


@dataclass(frozen=True, slots=True)
class Bm25Params:
    """``k1`` and ``b``.  Pinned by ARCHITECTURE §6.4; overridable per tenant via policy."""

    k1: float = 1.2
    b: float = 0.75

    def __post_init__(self) -> None:
        if not self.k1 > 0.0:
            raise ValueError(f"k1 must be > 0, got {self.k1!r}")
        if not 0.0 <= self.b <= 1.0:
            raise ValueError(f"b must be in [0, 1], got {self.b!r}")


DEFAULT_BM25: Final[Bm25Params] = Bm25Params()


@dataclass(frozen=True, slots=True)
class CorpusStats:
    """``N`` and ``avgdl`` for one site.

    Bound parameters rather than a sub-select for two reasons: it keeps the scoring statement
    a single constrained read, and it makes the numbers that produced a score *storable*, so
    a candidate row in ``mainline_meas.recall_candidate`` can be recomputed years later from
    the four scalars that were in force.  A statistic recovered by re-running a query against
    a corpus that has since grown is not the statistic that produced the score.
    """

    n_docs: int
    avgdl: float

    def __post_init__(self) -> None:
        if self.n_docs < 0:
            raise ValueError(f"n_docs must be >= 0, got {self.n_docs!r}")
        if self.n_docs > 0 and not self.avgdl > 0.0:
            raise ValueError(
                f"avgdl must be > 0 when the corpus is non-empty, got {self.avgdl!r}; "
                "a zero average document length is a division by zero in the length "
                "normalisation term, not a degenerate-but-fine input"
            )


# The statement text.  Written out in full rather than assembled from fragments so that what
# ships can be read, diffed and pasted into a psql session by a reviewer who does not have
# Python.  `{…}` slots carry placeholders or validated identifiers only.
#
# Every numeric input is wrapped in `CAST(… AS FLOAT)`, and this is not decoration.
# CockroachDB does not implicitly mix DECIMAL and FLOAT8 in a binary operator — it raises
# `unsupported binary operator: <float> - <decimal>` — and an undecorated numeric constant
# such as `0.0` resolves to DECIMAL.  So `s.df + 0.0` on an INT8 column is DECIMAL-flavoured
# and meeting a FLOAT8 parameter in the next operation is a run-time type error, not a
# rounding difference.  Casting the two integer columns and the four scalars pins the whole
# expression to float64 on every engine, which is also what makes the differential against a
# float64 Python oracle mean anything.  `FLOAT` (not `FLOAT8`) is spelled deliberately: it is
# CockroachDB's alias for FLOAT8 and it is also a name SQLite's CAST gives REAL affinity, so
# one statement text runs on both.
#
# NOTE (unverified on the target platform): the DECIMAL/FLOAT strictness above is asserted
# from CockroachDB's documented operator overload set, not from a run against v26.2 — no
# cluster was reachable from the machine this was written on. The casts make the statement
# correct under either behaviour, so the uncertainty costs nothing; it is recorded because a
# claim about a platform should say how it was established.
_BM25_SQL: Final[str] = """\
-- TRAPPOINT recall channel D: BM25 over mainline.lex_posting / lex_stats / lex_doclen.
-- IDF = ln((N - df + 0.5) / (df + 0.5) + 1), length normalised against avgdl. One statement.
-- The `p.term IN (...)` predicate is what constrains the scan to lex_posting's primary key
-- prefix (site_id, term). It is NOT an optimisation: without it this is a full scan.
SELECT p.event_id AS event_id,
       sum({weight_factor}ln((((CAST({n_docs} AS FLOAT) - CAST(s.df AS FLOAT)) + 0.5)
                 / (CAST(s.df AS FLOAT) + 0.5)) + 1.0)
           * ((p.weight * (CAST({k1} AS FLOAT) + 1.0))
              / (p.weight
                 + (CAST({k1} AS FLOAT)
                    * ((1.0 - CAST({b} AS FLOAT))
                       + (CAST({b} AS FLOAT)
                          * (CAST(d.len AS FLOAT) / CAST({avgdl} AS FLOAT)))))))) AS score
  FROM {schema}.lex_posting AS p
  JOIN {schema}.lex_stats AS s
    ON s.site_id = p.site_id AND s.term = p.term
  JOIN {schema}.lex_doclen AS d
    ON d.event_id = p.event_id
 WHERE p.site_id = {site_id}
   AND p.term IN ({term_list})
 GROUP BY p.event_id
 ORDER BY score DESC, p.event_id ASC
 LIMIT {limit}"""


def _prepare_terms(
    terms: Sequence[str] | Mapping[str, float],
) -> tuple[tuple[str, ...], dict[str, float] | None]:
    """Deduplicate, sort, validate; return ``(terms, weights or None)``.

    Sorted because the statement text must be a function of the term *set*: two callers that
    analysed the same query must produce the same statement, so that a plan cache hit, an
    ``index_plan_digest`` and an audit-surface transcript all mean what they say.
    """
    weights: dict[str, float] | None
    if isinstance(terms, Mapping):
        weights = {str(k): float(v) for k, v in terms.items()}
        ordered = tuple(sorted(weights))
        if all(w == 1.0 for w in weights.values()):
            weights = None  # uniform weights are the identity; do not emit a CASE for them
    else:
        ordered = tuple(sorted(set(terms)))
        weights = None
    bad = [t for t in ordered if not is_well_formed_term(t)]
    if bad:
        raise ValueError(
            "query terms must come from the analyser and match its charset; rejected: "
            + repr(bad[:5])
        )
    return ordered, weights


def build_bm25_statement(
    *,
    site_id: str,
    terms: Sequence[str] | Mapping[str, float],
    stats: CorpusStats,
    limit: int,
    params: Bm25Params = DEFAULT_BM25,
    style: ParamStyle = ParamStyle.NUMERIC,
    schema: str = "mainline",
) -> Statement:
    """Build the single BM25 statement.

    ``terms`` may be a sequence (uniform query weights, which is Lucene's ``k3 = 0``
    behaviour and the default) or a mapping term → query weight, which is how a learned-sparse
    query expansion or a class-weighted analyser feeds this channel.
    """
    if limit <= 0:
        raise ValueError(f"limit must be positive, got {limit!r}")
    ordered, weights = _prepare_terms(terms)
    if not ordered:
        raise ValueError(
            "no query terms survived analysis; the caller must decide what an empty query "
            "means rather than receiving an unconstrained scan"
        )
    if stats.n_docs == 0:
        raise ValueError("cannot score against an empty corpus (N = 0)")
    schema = check_identifier(schema, what="schema")

    qb = SqlBuilder(style)

    # Order of binding is the order of appearance in the text, which is what QMARK requires.
    weight_factor = ""
    if weights is not None:
        arms = " ".join(
            f"WHEN {qb.bind(t, key=f'term:{t}')} "
            f"THEN CAST({qb.bind(weights[t], key=f'qw:{t}')} AS FLOAT)"
            for t in ordered
        )
        weight_factor = f"(CASE p.term {arms} ELSE 0.0 END)\n           * "

    # `_BM25_SQL` mentions {k1} and {b} twice each, and `str.format` substitutes one value for
    # every occurrence of a name.  So each is bound TWICE here, in text order, and the first
    # token is the one written into the text:
    #   * under NUMERIC the second bind reuses the first's `$n` by key and appends no
    #     parameter, which is exactly what the text needs;
    #   * under QMARK/PYFORMAT both binds render the identical `?`/`%s` token, and the second
    #     bind is what keeps the positional parameter list aligned with the two occurrences.
    # Eliding either call, or reordering them, silently mis-binds one style or the other.
    n_docs = qb.bind(float(stats.n_docs), key="n_docs")
    k1_token = qb.bind(params.k1, key="k1")
    qb.bind(params.k1, key="k1")
    b_token = qb.bind(params.b, key="b")
    qb.bind(params.b, key="b")
    avgdl = qb.bind(float(stats.avgdl), key="avgdl")
    site = qb.bind(site_id, key="site")
    term_list = ", ".join(qb.bind(t, key=f"term:{t}") for t in ordered)
    limit_token = qb.bind(int(limit), key="limit")

    sql = _BM25_SQL.format(
        weight_factor=weight_factor,
        n_docs=n_docs,
        k1=k1_token,
        b=b_token,
        avgdl=avgdl,
        schema=schema,
        site_id=site,
        term_list=term_list,
        limit=limit_token,
    )
    return Statement(sql, qb.params, style)


_CORPUS_STATS_SQL: Final[str] = """\
-- N and avgdl for one site. Not on the gate path: the gate binds these as parameters so the
-- scoring statement stays a single constrained read and so the numbers that produced a score
-- can be stored with it. `lex_doclen` carries no site_id (ARCHITECTURE §5.4), so the site's
-- document set has to be recovered from `lex_posting`; see the note in this module's tests.
SELECT count(*) AS n_docs,
       coalesce(avg(CAST(d.len AS FLOAT)), 0.0) AS avgdl
  FROM {schema}.lex_doclen AS d
 WHERE d.event_id IN (SELECT DISTINCT p.event_id
                        FROM {schema}.lex_posting AS p
                       WHERE p.site_id = {site_id})"""


def corpus_stats_statement(
    *, site_id: str, style: ParamStyle = ParamStyle.NUMERIC, schema: str = "mainline"
) -> Statement:
    """One statement returning ``(n_docs, avgdl)`` for a site."""
    schema = check_identifier(schema, what="schema")
    qb = SqlBuilder(style)
    sql = _CORPUS_STATS_SQL.format(schema=schema, site_id=qb.bind(site_id, key="site"))
    return Statement(sql, qb.params, style)


def fetch_corpus_stats(
    execute: Executor,
    *,
    site_id: str,
    style: ParamStyle = ParamStyle.NUMERIC,
    schema: str = "mainline",
) -> CorpusStats:
    statement = corpus_stats_statement(site_id=site_id, style=style, schema=schema)
    rows = execute(statement.sql, statement.params)
    if not rows:
        return CorpusStats(n_docs=0, avgdl=0.0)
    n_docs, avgdl = rows[0][0], rows[0][1]
    return CorpusStats(
        n_docs=0 if n_docs is None else as_int(n_docs),
        avgdl=0.0 if avgdl is None else as_float(avgdl),
    )


def bm25_search(
    execute: Executor,
    *,
    site_id: str,
    terms: Sequence[str] | Mapping[str, float],
    limit: int,
    stats: CorpusStats | None = None,
    params: Bm25Params = DEFAULT_BM25,
    style: ParamStyle = ParamStyle.NUMERIC,
    schema: str = "mainline",
) -> list[tuple[str, float]]:
    """Run channel D and return ``[(event_id, score), …]`` in ranked order."""
    if stats is None:
        stats = fetch_corpus_stats(execute, site_id=site_id, style=style, schema=schema)
    if stats.n_docs == 0:
        return []
    statement = build_bm25_statement(
        site_id=site_id,
        terms=terms,
        stats=stats,
        limit=limit,
        params=params,
        style=style,
        schema=schema,
    )
    rows = execute(statement.sql, statement.params)
    return [(as_text(row[0]), as_float(row[1])) for row in rows]


def explain_of(statement: Statement) -> Statement:
    """``EXPLAIN`` the given statement, keeping its parameters.

    Plain ``EXPLAIN``, never ``EXPLAIN ANALYZE``: the Managed MCP surface forbids the latter,
    and the assertion this exists for is about the *plan*, which does not require execution.
    """
    return Statement("EXPLAIN " + statement.sql, statement.params, statement.style)


_ORPHAN_SQL: Final[str] = """\
-- Integrity: a posting whose document has no length is invisible to BM25, because the join to
-- lex_doclen is an INNER join. That is the correct failure (a missing length cannot be
-- normalised against) but it is a SILENT one, so it is checked rather than assumed.
SELECT DISTINCT p.event_id AS event_id
  FROM {schema}.lex_posting AS p
 WHERE p.site_id = {site_id}
   AND NOT EXISTS (SELECT 1 FROM {schema}.lex_doclen AS d WHERE d.event_id = p.event_id)
 LIMIT {limit}"""


def orphan_postings_statement(
    *,
    site_id: str,
    limit: int = MCP_MAX_SELECT_ROWS,
    style: ParamStyle = ParamStyle.NUMERIC,
    schema: str = "mainline",
) -> Statement:
    """Postings with no ``lex_doclen`` row — documents BM25 cannot see."""
    schema = check_identifier(schema, what="schema")
    qb = SqlBuilder(style)
    sql = _ORPHAN_SQL.format(
        schema=schema,
        site_id=qb.bind(site_id, key="site"),
        limit=qb.bind(int(limit), key="limit"),
    )
    return Statement(sql, qb.params, style)


_DRIFT_SQL: Final[str] = """\
-- Integrity: lex_stats.df must equal the number of postings for that term at that site. df is
-- the only input to IDF, so drift here does not raise an error, it silently re-ranks.
SELECT s.term AS term, s.df AS recorded_df, count(p.event_id) AS actual_df
  FROM {schema}.lex_stats AS s
  LEFT JOIN {schema}.lex_posting AS p
    ON p.site_id = s.site_id AND p.term = s.term
 WHERE s.site_id = {site_id}
 GROUP BY s.term, s.df
HAVING s.df <> count(p.event_id)
 LIMIT {limit}"""


def stats_drift_statement(
    *,
    site_id: str,
    limit: int = MCP_MAX_SELECT_ROWS,
    style: ParamStyle = ParamStyle.NUMERIC,
    schema: str = "mainline",
) -> Statement:
    """Terms whose recorded ``df`` disagrees with the posting list."""
    schema = check_identifier(schema, what="schema")
    qb = SqlBuilder(style)
    sql = _DRIFT_SQL.format(
        schema=schema,
        site_id=qb.bind(site_id, key="site"),
        limit=qb.bind(int(limit), key="limit"),
    )
    return Statement(sql, qb.params, style)
