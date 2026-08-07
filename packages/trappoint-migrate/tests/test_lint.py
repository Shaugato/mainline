# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""Ruling D10 and the §18 citation rule, tested in both directions.

The rule this file defends is not "sequences are unfashionable". It is:

    the event ledger is gap-free by compare-and-swap, so **a gap MEANS tampering**

and that sentence has to be withdrawn the moment one migration anywhere reintroduces a
sequence, because a sequence is permitted to leave gaps. A test suite that only checked
the happy direction would let the rule rot into a comment.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from trappoint_migrate.lint import lint_paths, lint_text

HEADER = "-- MI02: the merge gate's obligation counter.\n"


def rules(path: Path, text: str, *, require_citation: bool = True) -> set[str]:
    return {f.rule for f in lint_text(path, text, require_citation=require_citation)}


def test_empty_tree_passes_and_says_it_checked_nothing(tmp_path: Path) -> None:
    report = lint_paths([tmp_path])
    assert report.ok
    assert report.files_checked == 0


def test_absent_tree_passes(tmp_path: Path) -> None:
    assert lint_paths([tmp_path / "not-rendered-yet"]).ok


@pytest.mark.parametrize(
    "statement",
    [
        "CREATE SEQUENCE mainline.permit_seq;",
        "create sequence mainline.permit_seq;",
        "CREATE TEMPORARY SEQUENCE s;",
        "ALTER TABLE t ALTER COLUMN i SET DEFAULT nextval('s');",
        "CREATE TABLE t (id SERIAL PRIMARY KEY);",
        "CREATE TABLE t (id BIGSERIAL PRIMARY KEY);",
        "CREATE TABLE t (id SERIAL8 PRIMARY KEY);",
        "CREATE TABLE t (id INT8 DEFAULT unique_rowid());",
    ],
)
def test_banned_tokens_are_refused(tmp_path: Path, statement: str) -> None:
    found = rules(tmp_path / "0001_x.sql", HEADER + statement)
    assert any(r.startswith("banned-token:") for r in found), statement


def test_serializable_is_not_serial(tmp_path: Path) -> None:
    # `\bSERIAL\b` must not fire on SERIALIZABLE, which appears in every gate transaction.
    text = HEADER + "SET TRANSACTION ISOLATION LEVEL SERIALIZABLE;"
    assert not any(r.startswith("banned-token") for r in rules(tmp_path / "0001_x.sql", text))


def test_a_comment_explaining_the_ban_does_not_trip_it(tmp_path: Path) -> None:
    text = (
        "-- MI01: gap-free by CAS. No CREATE SEQUENCE, no nextval(, no SERIAL,\n"
        "-- no unique_rowid() -- a sequence would make a gap mean nothing.\n"
        "CREATE TABLE t (x INT8);\n"
    )
    assert rules(tmp_path / "0001_x.sql", text) == set()


def test_a_banned_token_inside_a_routine_body_is_still_refused(tmp_path: Path) -> None:
    text = (
        HEADER
        + "CREATE FUNCTION mainline.f() RETURNS INT8 AS $$\n"
        + "BEGIN RETURN nextval('mainline.s'); END;\n"
        + "$$ LANGUAGE plpgsql;\n"
    )
    assert "banned-token:nextval" in rules(tmp_path / "0100_f.sql", text)


def test_missing_invariant_citation_is_refused(tmp_path: Path) -> None:
    assert "missing-invariant-citation" in rules(
        tmp_path / "0001_x.sql", "-- creates the table\nCREATE TABLE t ();\n"
    )


def test_citation_must_be_in_the_header_not_the_body(tmp_path: Path) -> None:
    text = "-- creates the table\nCREATE TABLE t (); -- MI02\n"
    assert "missing-invariant-citation" in rules(tmp_path / "0001_x.sql", text)


@pytest.mark.parametrize("citation", ["MI02", "I14"])
def test_either_identifier_namespace_satisfies_the_rule(tmp_path: Path, citation: str) -> None:
    text = f"-- {citation}: why this file exists.\nCREATE TABLE t ();\n"
    assert "missing-invariant-citation" not in rules(tmp_path / "0001_x.sql", text)


def test_two_statements_in_one_file_are_refused(tmp_path: Path) -> None:
    text = HEADER + "CREATE TABLE t (); CREATE TABLE u ();"
    assert "multiple-statements" in rules(tmp_path / "0001_x.sql", text)


def test_templates_are_scanned_for_tokens_but_not_for_citations(tmp_path: Path) -> None:
    template = tmp_path / "0050_permit.sql.j2"
    template.write_text("CREATE TABLE {{ schema }}.permit (id SERIAL);\n", encoding="utf-8")
    report = lint_paths([tmp_path])
    found = {f.rule for f in report.findings}
    assert "banned-token:serial" in found
    assert "missing-invariant-citation" not in found


def test_findings_carry_a_usable_location(tmp_path: Path) -> None:
    path = tmp_path / "0001_x.sql"
    path.write_text(HEADER + "SELECT 1;\nSELECT nextval('s');\n", encoding="utf-8")
    report = lint_paths([tmp_path])
    (finding,) = [f for f in report.findings if f.rule == "banned-token:nextval"]
    assert finding.line == 3
    assert "0001_x.sql:3:" in finding.render()


def test_a_clean_tree_passes_and_counts_its_files(tmp_path: Path) -> None:
    (tmp_path / "0001_x.sql").write_text(HEADER + "CREATE TABLE t ();\n", encoding="utf-8")
    (tmp_path / "0002_y.sql").write_text(HEADER + "CREATE TABLE u ();\n", encoding="utf-8")
    report = lint_paths([tmp_path])
    assert report.ok
    assert report.files_checked == 2
