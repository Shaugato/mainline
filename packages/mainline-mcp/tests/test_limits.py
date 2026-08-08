# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""The scanner and the refusals: every documented Managed-MCP limit, refused client-side.

The interesting tests here are the *negative* ones — the cases where a naive
implementation would refuse something legal. A semicolon inside a string literal, the
word ``pg_catalog`` inside a comment, a dollar-quoted body containing anything at all: a
client that refused those would be a client operators route around, and a control
operators route around is not a control.
"""

from __future__ import annotations

import pytest
from mainline_mcp.limits import (
    BUDGET_RESPONSE_BYTES,
    MAX_RESPONSE_BYTES,
    MAX_STATEMENT_CHARS,
    SELECT_MAX_ROWS,
    SHOW_MAX_ROWS,
    EmptyStatement,
    ExplainAnalyzeRefused,
    ForbiddenSchema,
    LimitAllRefused,
    MultipleStatements,
    QaSchemaRefused,
    ResponseTooLarge,
    RowLimitTooHigh,
    StatementTooLong,
    enforce_response_size,
    enforce_row_limit,
    enforce_statement,
    scan,
)


class TestStatementCounting:
    def test_one_statement_with_trailing_semicolon_is_one(self):
        assert scan("SELECT 1;").statement_count == 1

    def test_two_statements_are_two(self):
        assert scan("SELECT 1; SELECT 2").statement_count == 2

    def test_semicolon_inside_a_string_literal_is_not_a_separator(self):
        scanned = scan("SELECT * FROM t WHERE code = 'CY-01; CY-02'")
        assert scanned.statement_count == 1

    def test_doubled_quote_inside_a_string_literal_does_not_end_it(self):
        scanned = scan("SELECT * FROM t WHERE note = 'it''s fine; really'")
        assert scanned.statement_count == 1

    def test_semicolon_inside_a_line_comment_is_not_a_separator(self):
        scanned = scan("SELECT 1 -- ; not a statement\n")
        assert scanned.statement_count == 1

    def test_semicolon_inside_a_block_comment_is_not_a_separator(self):
        scanned = scan("SELECT /* ; still one ; */ 1")
        assert scanned.statement_count == 1

    def test_nested_block_comments_close_correctly(self):
        scanned = scan("SELECT /* outer /* inner ; */ ; */ 1 FROM crdb_x")
        assert scanned.statement_count == 1

    def test_semicolon_inside_a_dollar_quoted_body_is_not_a_separator(self):
        scanned = scan("SELECT $tag$ a ; b ; c $tag$")
        assert scanned.statement_count == 1

    def test_empty_input_refuses(self):
        with pytest.raises(EmptyStatement):
            enforce_statement("   \n  ", verb="select_query")

    def test_multiple_statements_refuse_and_name_the_count(self):
        with pytest.raises(MultipleStatements) as excinfo:
            enforce_statement("SELECT 1; SELECT 2", verb="select_query")
        assert excinfo.value.observed == 2
        assert excinfo.value.limit == "statements_per_call"


class TestLength:
    def test_at_the_limit_is_accepted(self):
        statement = "SELECT '" + "x" * (MAX_STATEMENT_CHARS - 9) + "'"
        assert len(statement) == MAX_STATEMENT_CHARS
        enforce_statement(statement, verb="select_query")

    def test_one_over_the_limit_refuses_with_both_numbers(self):
        statement = "SELECT '" + "x" * (MAX_STATEMENT_CHARS - 8) + "'"
        with pytest.raises(StatementTooLong) as excinfo:
            enforce_statement(statement, verb="select_query")
        assert excinfo.value.limit_value == MAX_STATEMENT_CHARS
        assert excinfo.value.observed == MAX_STATEMENT_CHARS + 1


class TestForbiddenSchemas:
    @pytest.mark.parametrize(
        "statement",
        [
            "SELECT * FROM crdb_internal.jobs",
            "SELECT * FROM pg_catalog.pg_class",
            "SELECT * FROM information_schema.tables",
            "SELECT * FROM system.jobs",
            "SELECT * FROM pg_extension.foo",
            "SHOW TABLES FROM information_schema",
        ],
    )
    def test_forbidden_schema_refuses(self, statement):
        with pytest.raises(ForbiddenSchema):
            enforce_statement(statement, verb="select_query")

    def test_quoted_identifier_does_not_launder_a_forbidden_schema(self):
        with pytest.raises(ForbiddenSchema):
            enforce_statement('SELECT * FROM "crdb_internal".jobs', verb="select_query")

    def test_forbidden_name_inside_a_comment_is_not_an_access_attempt(self):
        enforce_statement(
            "SELECT * FROM mainline_audit.v_ledger_health -- unlike crdb_internal.jobs\n",
            verb="select_query",
        )

    def test_forbidden_name_inside_a_string_literal_is_not_an_access_attempt(self):
        enforce_statement(
            "SELECT * FROM mainline_audit.v_agent_actions WHERE tool = 'pg_catalog'",
            verb="select_query",
        )

    def test_the_word_system_as_a_column_is_not_an_access_attempt(self):
        enforce_statement(
            "SELECT system, count(*) FROM mainline_audit.v_blame_coverage GROUP BY 1",
            verb="select_query",
        )

    def test_mainline_qa_is_refused_as_ours_not_the_servers(self):
        with pytest.raises(QaSchemaRefused) as excinfo:
            enforce_statement(
                "SELECT * FROM mainline_qa.v_disposition_profile", verb="select_query"
            )
        assert excinfo.value.limit == "never_mcp_schema"

    def test_the_screen_can_be_disabled_only_explicitly(self):
        scanned = enforce_statement(
            "SELECT * FROM crdb_internal.jobs",
            verb="select_query",
            screen_schemas=False,
        )
        assert scanned.forbidden_schemas == frozenset({"crdb_internal"})


class TestExplainAndRowLimits:
    @pytest.mark.parametrize(
        "statement",
        [
            "EXPLAIN ANALYZE SELECT 1",
            "EXPLAIN (ANALYZE) SELECT 1",
            "EXPLAIN ANALYSE SELECT 1",
            "EXPLAIN (VERBOSE, ANALYZE) SELECT 1",
        ],
    )
    def test_explain_analyze_refuses(self, statement):
        with pytest.raises(ExplainAnalyzeRefused):
            enforce_statement(statement, verb="explain_query")

    def test_plain_explain_is_accepted(self):
        enforce_statement("EXPLAIN SELECT * FROM mainline.clause LIMIT 1", verb="explain_query")

    def test_limit_all_refuses(self):
        with pytest.raises(LimitAllRefused):
            enforce_statement("SELECT * FROM mainline.clause LIMIT ALL", verb="select_query")

    def test_limit_at_the_maximum_is_accepted(self):
        enforce_statement(f"SELECT 1 LIMIT {SELECT_MAX_ROWS}", verb="select_query")

    def test_limit_above_the_maximum_refuses(self):
        with pytest.raises(RowLimitTooHigh) as excinfo:
            enforce_statement(f"SELECT 1 LIMIT {SELECT_MAX_ROWS + 1}", verb="select_query")
        assert excinfo.value.observed == SELECT_MAX_ROWS + 1

    def test_show_has_a_lower_ceiling_than_select(self):
        enforce_statement("SHOW CLUSTER SETTINGS", verb="show_statement", max_rows=SHOW_MAX_ROWS)
        with pytest.raises(RowLimitTooHigh):
            enforce_statement(
                f"SHOW CLUSTER SETTINGS LIMIT {SHOW_MAX_ROWS + 1}",
                verb="show_statement",
                max_rows=SHOW_MAX_ROWS,
            )

    def test_row_limit_argument_is_enforced_at_the_ceiling(self):
        allowed = enforce_row_limit(SHOW_MAX_ROWS, verb="show_statement", maximum=SHOW_MAX_ROWS)
        assert allowed == SHOW_MAX_ROWS
        with pytest.raises(RowLimitTooHigh):
            enforce_row_limit(SHOW_MAX_ROWS + 1, verb="show_statement", maximum=SHOW_MAX_ROWS)
        with pytest.raises(RowLimitTooHigh):
            enforce_row_limit(0, verb="show_statement", maximum=SHOW_MAX_ROWS)


class TestResponseSize:
    def test_below_the_cap_is_returned_unchanged(self):
        assert enforce_response_size(1024, tool="select_query") == 1024

    def test_at_the_cap_refuses_because_that_is_the_shape_of_a_truncation(self):
        with pytest.raises(ResponseTooLarge) as excinfo:
            enforce_response_size(MAX_RESPONSE_BYTES, tool="select_query")
        assert excinfo.value.observed == MAX_RESPONSE_BYTES

    def test_our_budget_leaves_twenty_percent_of_headroom(self):
        # AR-6: the alarm has to fire while there is still room to fix it.
        assert int(MAX_RESPONSE_BYTES * 0.8) == BUDGET_RESPONSE_BYTES
