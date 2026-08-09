# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""The Managed-MCP envelope: what it refuses, and what it refuses to pretend."""

from __future__ import annotations

import pytest
from judge import envelope as env


class TestScanner:
    def test_a_semicolon_inside_a_literal_is_not_a_second_statement(self):
        scanned = env.scan("SELECT 'a;b' AS x FROM t LIMIT 1;")
        assert scanned.statement_count == 1

    def test_a_forbidden_word_inside_a_comment_is_not_an_access_attempt(self):
        scanned = env.scan("SELECT 1 -- crdb_internal is unreachable\nFROM t LIMIT 1;")
        assert scanned.forbidden_schemas == frozenset()

    def test_a_forbidden_word_inside_a_quoted_identifier_is_still_caught(self):
        scanned = env.scan('SELECT 1 FROM "crdb_internal".jobs LIMIT 1;')
        assert "crdb_internal" in scanned.forbidden_schemas

    def test_system_is_only_forbidden_as_a_qualifier(self):
        # "system" is an ordinary English word that can be a column name in a mining record.
        assert env.scan("SELECT system FROM t LIMIT 1").forbidden_schemas == frozenset()
        assert "system" in env.scan("SELECT 1 FROM system.jobs LIMIT 1").forbidden_schemas

    def test_nested_block_comments_are_skipped_whole(self):
        scanned = env.scan("SELECT 1 /* outer /* inner ; */ still ; */ FROM t LIMIT 1;")
        assert scanned.statement_count == 1


class TestRefusals:
    def test_two_statements_are_refused(self):
        with pytest.raises(env.MultipleStatements):
            env.enforce("SELECT 1 LIMIT 1; SELECT 2 LIMIT 1;", verb="select_query")

    def test_an_empty_statement_is_refused(self):
        with pytest.raises(env.EmptyStatement):
            env.enforce("   ", verb="select_query")

    def test_a_statement_over_the_character_cap_is_refused(self):
        padding = "x" * env.MAX_STATEMENT_CHARS
        with pytest.raises(env.StatementTooLong) as caught:
            env.enforce(f"SELECT '{padding}' LIMIT 1", verb="select_query")
        assert caught.value.limit_value == env.MAX_STATEMENT_CHARS

    def test_explain_analyze_is_refused(self):
        with pytest.raises(env.ExplainAnalyzeRefused):
            env.enforce("EXPLAIN ANALYZE SELECT 1 FROM t LIMIT 1", verb="explain_query")

    def test_limit_all_is_refused(self):
        with pytest.raises(env.LimitAllRefused):
            env.enforce("SELECT 1 FROM t LIMIT ALL", verb="select_query")

    def test_a_page_wider_than_the_server_default_is_refused(self):
        with pytest.raises(env.RowLimitTooHigh):
            env.enforce("SELECT 1 FROM t LIMIT 100", verb="select_query")

    def test_a_missing_limit_is_refused_because_the_server_pages_silently(self):
        # This one is ours, not the server's, and it is the point of the pack: with no
        # LIMIT the server applies 25 quietly and a truncated page reads as a complete
        # answer.
        with pytest.raises(env.LimitMissing):
            env.enforce("SELECT 1 FROM mainline_audit.v_open_gate_summary", verb="select_query")

    def test_the_qa_schema_is_refused_by_its_own_named_limit(self):
        with pytest.raises(env.QaSchemaRefused) as caught:
            env.enforce("SELECT count(*) FROM mainline_qa.v_x LIMIT 1", verb="select_query")
        assert caught.value.limit == "never_mcp_schema"

    def test_an_unknown_verb_is_refused(self):
        with pytest.raises(env.UnknownVerb):
            env.enforce("SELECT 1 LIMIT 1", verb="drop_everything")

    def test_every_named_refusal_is_reachable_by_name(self):
        for name, cls in env.REFUSAL_BY_NAME.items():
            assert cls.limit == name


class TestResponseSize:
    def test_a_response_exactly_at_the_cap_is_treated_as_truncated(self):
        # `>=` not `>`: a response that exactly fills the cap has the shape of a truncated
        # one, and a silently truncated proof is the defect this product refuses.
        with pytest.raises(env.EnvelopeRefusal):
            env.enforce_response_size(env.MAX_RESPONSE_BYTES, what="v_open_gate_summary")

    def test_a_response_under_the_cap_is_returned(self):
        assert env.enforce_response_size(10, what="anything") == 10


class TestVectorSizeModel:
    def test_the_worst_case_element_is_the_longest_a_normalised_component_can_print(self):
        assert env.worst_case_element(6) == "-0.999999"

    def test_a_1024_dimension_literal_fits_with_headroom(self):
        model = env.model_vector_statement(
            "EXPLAIN SELECT 1 FROM t ORDER BY emb <=> $1 LIMIT 10;",
            placeholder="$1",
            dimension=1024,
        )
        assert model.fits
        assert model.headroom_chars > 0

    def test_an_absurd_width_is_refused_by_the_model(self):
        model = env.model_vector_statement(
            "EXPLAIN SELECT 1 FROM t ORDER BY emb <=> $1 LIMIT 10;",
            placeholder="$1",
            dimension=4096,
        )
        assert not model.fits
        assert model.headroom_chars < 0

    def test_the_bound_statement_is_kept_so_it_can_actually_be_run(self):
        model = env.model_vector_statement(
            "EXPLAIN SELECT 1 FROM t ORDER BY emb <=> $1 LIMIT 10;",
            placeholder="$1",
            dimension=4,
        )
        assert "$1" not in model.bound_sql
        assert "::VECTOR(4)" in model.bound_sql


class TestCrossCheck:
    def test_it_distinguishes_did_not_run_from_agreed(self):
        result = env.crosscheck_with_mainline_mcp()
        if not result.ran:
            # Absence is never a pass. The result must say so in words, and `agreed` must
            # be False, so a caller cannot read a missing package as a green check.
            assert not result.agreed
            assert "NOT consulted" in result.reason
            pytest.skip(f"packages/mainline-mcp is not importable: {result.reason}")
        assert result.disagreements == (), result.disagreements
        assert result.agreed
