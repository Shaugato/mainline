# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""The lexer the sequence ban depends on.

These are the tests that decide whether ruling D10 is enforced or merely written down.
Both failure directions are covered, because both kill the rule: a false positive on a
comment makes the guard annoying enough to be weakened, and a false negative inside a
dollar-quoted body is precisely where a trigger function would reintroduce a sequence.
"""

from __future__ import annotations

from trappoint_migrate.sqltext import collapse_whitespace, header_comment, strip_sql_comments


def test_line_comment_is_removed_but_line_numbers_survive() -> None:
    sql = "SELECT 1;\n-- CREATE SEQUENCE explained here\nSELECT 2;\n"
    out = strip_sql_comments(sql)
    assert "CREATE SEQUENCE" not in out
    assert out.count("\n") == sql.count("\n")


def test_block_comment_is_removed_and_nests() -> None:
    sql = "SELECT /* outer /* inner nextval( */ still outer */ 1;"
    out = strip_sql_comments(sql)
    assert "nextval(" not in out
    assert "SELECT" in out
    assert out.rstrip().endswith("1;")


def test_block_comment_replacement_preserves_token_boundaries() -> None:
    # The whole reason a removed comment becomes a space rather than nothing.
    assert "CREATESEQUENCE" not in strip_sql_comments("CREATE/**/SEQUENCE foo")
    assert "CREATE SEQUENCE" in strip_sql_comments("CREATE/**/SEQUENCE foo").replace("  ", " ")


def test_string_literal_is_preserved_including_doubled_quotes() -> None:
    sql = "SELECT 'it''s -- not a comment', 2;"
    out = strip_sql_comments(sql)
    assert "it''s -- not a comment" in out


def test_quoted_identifier_is_preserved() -> None:
    sql = 'SELECT "weird -- name" FROM t;'
    assert '"weird -- name"' in strip_sql_comments(sql)


def test_comments_inside_a_dollar_quoted_body_are_still_comments() -> None:
    sql = (
        "CREATE FUNCTION f() RETURNS INT8 AS $$\n"
        "BEGIN\n"
        "  -- nextval( would be banned even here\n"
        "  RETURN 1;\n"
        "END;\n"
        "$$ LANGUAGE plpgsql;"
    )
    out = strip_sql_comments(sql)
    assert "nextval(" not in out
    assert "RETURN 1;" in out


def test_code_inside_a_dollar_quoted_body_is_kept() -> None:
    sql = "CREATE FUNCTION f() RETURNS INT8 AS $tag$ SELECT nextval('s'); $tag$ LANGUAGE sql;"
    out = strip_sql_comments(sql)
    assert "nextval('s')" in out, "a banned token in a routine body must remain visible to the lint"


def test_dollar_placeholder_is_not_a_quote_opener() -> None:
    sql = "SELECT $1, $2 -- comment\n, 3;"
    out = strip_sql_comments(sql)
    assert "comment" not in out
    assert "$1" in out
    assert "$2" in out


def test_unterminated_line_comment_at_eof() -> None:
    assert "x" not in strip_sql_comments("SELECT 1; -- x")


def test_header_comment_stops_at_the_first_statement() -> None:
    sql = "-- MI02 gate\n-- second line\n\nCREATE TABLE t ();\n-- trailing MI09\n"
    header = header_comment(sql)
    assert "MI02" in header
    assert "second line" in header
    assert "MI09" not in header


def test_header_comment_of_a_file_with_no_header() -> None:
    assert header_comment("CREATE TABLE t ();") == ""


def test_collapse_whitespace() -> None:
    assert collapse_whitespace("  a\n\tb   c ") == "a b c"
