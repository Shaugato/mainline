# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""The shape of the emitted statement — the properties that are not about the arithmetic.

The differential suite proves the numbers.  This file proves the things a correct-looking
number cannot: that it is *one* statement, that the predicate which constrains the scan is
actually in the text, that the four parameter styles emit the same statement, and that the
literal renderer used by the Managed-MCP audit surface refuses anything the analyser did not
produce.
"""

from __future__ import annotations

import re

import pytest
from trappoint_recall.lexical.bm25 import (
    CorpusStats,
    build_bm25_statement,
    corpus_stats_statement,
    explain_of,
    orphan_postings_statement,
    stats_drift_statement,
)
from trappoint_recall.lexical.executor import (
    MCP_MAX_STATEMENT_CHARS,
    ParamStyle,
    Statement,
    UnsafeLiteralError,
    normalise_placeholders,
    render_literal,
    strip_sql_noise,
)

SITE = "11111111-1111-4111-8111-111111111111"
STATS = CorpusStats(n_docs=2000, avgdl=37.5)
TERMS = ("401", "cas:7783-06-4", "cfr:30:57.22239", "k-401", "q:lel:25")


def built(style: ParamStyle = ParamStyle.NUMERIC, **kwargs: object) -> Statement:
    params = {
        "site_id": SITE,
        "terms": TERMS,
        "stats": STATS,
        "limit": 12,
        "style": style,
    }
    params.update(kwargs)
    return build_bm25_statement(**params)  # type: ignore[arg-type]


# ── one statement, and it fits the audit surface ─────────────────────────────────────────────


@pytest.mark.parametrize("style", list(ParamStyle))
def test_it_is_a_single_statement(style: ParamStyle) -> None:
    assert built(style).is_single_statement()


def test_the_semicolon_check_ignores_comments_and_literals() -> None:
    """It has to: the statement's own header comment contains prose punctuation."""
    assert ";" not in strip_sql_noise("-- a; b\nSELECT 1")
    assert ";" not in strip_sql_noise("SELECT 'a;b'")
    assert ";" in strip_sql_noise("SELECT 1; SELECT 2")


def test_the_literal_rendering_fits_the_managed_mcp_envelope() -> None:
    statement = built(ParamStyle.LITERAL)
    assert statement.fits_mcp_envelope()
    assert len(statement.sql) <= MCP_MAX_STATEMENT_CHARS


def test_a_large_query_still_fits_the_envelope() -> None:
    """The envelope is 16 KiB; a 200-term query must not silently exceed it."""
    many = tuple(f"tag-{i:04d}" for i in range(200))
    statement = build_bm25_statement(
        site_id=SITE, terms=many, stats=STATS, limit=25, style=ParamStyle.LITERAL
    )
    assert statement.fits_mcp_envelope(), len(statement.sql)


def test_the_query_weighted_form_fits_too_and_is_the_binding_case() -> None:
    """Query weighting adds a ``CASE`` arm per term, so this is the shape nearest the cliff.

    Recorded as a number rather than a boolean because the headroom is what a future term-set
    cap has to be chosen against: the audit surface rejects at 16 KiB, and finding that out
    during a demo is not a plan.
    """
    weighted = {f"tag-{i:04d}": 1.0 + (i % 3) for i in range(200)}
    statement = build_bm25_statement(
        site_id=SITE, terms=weighted, stats=STATS, limit=25, style=ParamStyle.LITERAL
    )
    assert statement.fits_mcp_envelope()
    # Headroom at 200 weighted terms. If this ever drops below ~2 000 characters the term set
    # needs a cap before the envelope finds one for us.
    assert MCP_MAX_STATEMENT_CHARS - len(statement.sql) > 2000, len(statement.sql)


# ── the predicate that makes the scan constrained ────────────────────────────────────────────


def test_the_site_predicate_is_present() -> None:
    assert re.search(r"WHERE p\.site_id = \$\d+", built().sql)


def test_the_term_in_list_is_present_and_covers_every_term() -> None:
    sql = built(ParamStyle.LITERAL).sql
    match = re.search(r"AND p\.term IN \(([^)]*)\)", sql)
    assert match is not None, "the IN list is what builds the spans; it is not optional"
    listed = {value.strip().strip("'") for value in match.group(1).split(",")}
    assert listed == set(TERMS)


def test_the_in_list_is_emitted_even_when_it_is_redundant_with_the_case() -> None:
    """Under query weighting the ``CASE`` already selects the terms.

    The ``IN`` list is kept anyway: dropping it leaves the answer correct and turns the plan
    into a full scan of every posting at the site.
    """
    weighted = built(ParamStyle.LITERAL, terms={t: 2.0 for t in TERMS})
    assert "CASE p.term WHEN" in weighted.sql
    assert re.search(r"AND p\.term IN \(", weighted.sql)


def test_uniform_query_weights_emit_no_case_at_all() -> None:
    """A ``CASE`` of all-1.0 is the identity; emitting it would be noise in the plan."""
    assert "CASE" not in built(ParamStyle.LITERAL, terms=dict.fromkeys(TERMS, 1.0)).sql


def test_the_ordering_is_deterministic() -> None:
    assert "ORDER BY score DESC, p.event_id ASC" in built().sql


def test_all_three_tables_are_joined() -> None:
    sql = built().sql
    for table in ("lex_posting", "lex_stats", "lex_doclen"):
        assert f"mainline.{table}" in sql


def test_the_statement_text_is_a_function_of_the_term_set_not_its_order() -> None:
    a = build_bm25_statement(
        site_id=SITE, terms=list(TERMS), stats=STATS, limit=12, style=ParamStyle.LITERAL
    )
    b = build_bm25_statement(
        site_id=SITE,
        terms=list(reversed(TERMS)),
        stats=STATS,
        limit=12,
        style=ParamStyle.LITERAL,
    )
    assert a.sql == b.sql


# ── the four parameter styles emit the same statement ────────────────────────────────────────


def test_styles_differ_only_in_placeholder_tokens() -> None:
    """"The SQL that was differentially tested is the SQL that ships", as a checked claim.

    The differential suite executes the ``QMARK`` rendering on whatever engine is available;
    the gate path issues the ``NUMERIC`` one.  If those two texts could diverge, the
    differential would be measuring something other than what runs.
    """
    numeric = normalise_placeholders(built(ParamStyle.NUMERIC).sql)
    qmark = normalise_placeholders(built(ParamStyle.QMARK).sql)
    pyformat = normalise_placeholders(built(ParamStyle.PYFORMAT).sql)
    assert numeric == qmark == pyformat


def test_numeric_reuses_a_placeholder_and_qmark_repeats_the_value() -> None:
    numeric = built(ParamStyle.NUMERIC)
    qmark = built(ParamStyle.QMARK)
    # k1 and b appear twice in the expression, and every term appears once (no CASE here).
    assert len(qmark.params) == len(numeric.params) + 2
    assert numeric.params.count(1.2) == 1
    assert qmark.params.count(1.2) == 2


def test_the_parameter_order_matches_the_text_for_qmark() -> None:
    statement = built(ParamStyle.QMARK)
    assert statement.params == (
        float(STATS.n_docs),
        1.2,
        1.2,
        0.75,
        0.75,
        STATS.avgdl,
        SITE,
        *TERMS,
        12,
    )


def test_weighted_query_parameter_order_matches_the_text_for_qmark() -> None:
    weights = {term: float(i + 2) for i, term in enumerate(TERMS)}
    statement = built(ParamStyle.QMARK, terms=weights)
    case_pairs = tuple(x for term in TERMS for x in (term, weights[term]))
    assert statement.params[: len(case_pairs)] == case_pairs


# ── the literal renderer refuses rather than escapes ─────────────────────────────────────────


@pytest.mark.parametrize(
    "value",
    ["k-401'; DROP TABLE mainline.lex_posting; --", "term\nwith newline", "back\\slash", "a" * 300],
)
def test_unsafe_strings_are_refused(value: str) -> None:
    with pytest.raises(UnsafeLiteralError):
        render_literal(value)


def test_floats_round_trip_exactly() -> None:
    assert float(render_literal(0.1 + 0.2)) == 0.1 + 0.2
    assert float(render_literal(37.5)) == 37.5


def test_non_finite_floats_are_refused() -> None:
    with pytest.raises(UnsafeLiteralError):
        render_literal(float("nan"))
    with pytest.raises(UnsafeLiteralError):
        render_literal(float("inf"))


def test_a_schema_name_that_is_not_an_identifier_is_refused() -> None:
    with pytest.raises(UnsafeLiteralError, match="not a plain lowercase SQL identifier"):
        build_bm25_statement(
            site_id=SITE, terms=TERMS, stats=STATS, limit=5, schema="mainline; DROP"
        )


# ── the supporting statements ────────────────────────────────────────────────────────────────


def test_corpus_stats_is_one_site_scoped_statement() -> None:
    statement = corpus_stats_statement(site_id=SITE, style=ParamStyle.LITERAL)
    assert statement.fits_mcp_envelope()
    assert f"p.site_id = '{SITE}'" in statement.sql


@pytest.mark.parametrize("builder", [orphan_postings_statement, stats_drift_statement])
def test_the_integrity_statements_are_single_and_site_scoped(builder: object) -> None:
    statement = builder(site_id=SITE, style=ParamStyle.LITERAL)  # type: ignore[operator]
    assert statement.fits_mcp_envelope()
    assert SITE in statement.sql


def test_explain_wraps_the_statement_without_changing_its_parameters() -> None:
    statement = built()
    explained = explain_of(statement)
    assert explained.sql.startswith("EXPLAIN -- TRAPPOINT recall channel D")
    assert explained.params == statement.params
    assert "ANALYZE" not in explained.sql
