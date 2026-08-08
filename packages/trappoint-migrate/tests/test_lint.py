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

from trappoint_migrate.lint import (
    ALLOCATION_SUFFIX,
    RENDERED_BANNER,
    UP_SQL_DETAIL,
    lint_paths,
    lint_text,
    load_allocation,
)

HEADER = "-- MI02: the merge gate's obligation counter.\n"

REPO_ROOT = Path(__file__).resolve().parents[3]
MIGRATIONS = REPO_ROOT / "verticals" / "mainline" / "db" / "migrations"

# 0001-0018z rendered, 0019-0020z authored, 0021+ unallocated: the smallest tree that
# reproduces the seam the whole reconciliation turns on.
TWO_BAND_ALLOCATION = """
[[band]]
first = "0001"
last = "0018z"
owner = "kernel/render-and-foundation"
mode = "rendered"
contents = "schemas, roles, revokes, the privilege floor, the seven types"

[[band]]
first = "0019"
last = "0020z"
owner = "datamodel/dm-foundation"
mode = "authored"
contents = "retention_class, adm_decision_class, site"

[[band]]
first = "0021"
last = "9999z"
owner = "UNALLOCATED"
mode = "unallocated"
contents = "No file may use these numbers (MRR-7)."
"""


def rules(path: Path, text: str, *, require_citation: bool = True) -> set[str]:
    return {f.rule for f in lint_text(path, text, require_citation=require_citation)}


def banded_tree(tmp_path: Path) -> Path:
    """A migration directory with its sibling allocation file, as the vertical has one."""
    root = tmp_path / "migrations"
    root.mkdir()
    (tmp_path / f"migrations{ALLOCATION_SUFFIX}").write_text(TWO_BAND_ALLOCATION, encoding="utf-8")
    return root


def write(root: Path, name: str, body: str) -> Path:
    path = root / name
    path.write_text(body, encoding="utf-8")
    return path


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


# ── RULE A · the one filename convention (MR-5) ─────────────────────────────────────


@pytest.mark.parametrize(
    "name",
    [
        "0031_clause_embedding.fallback.sql",
        "0031a_clause_embedding_ann.fallback.sql",
        "0031_clause_embedding.v2.sql",
        "0031_ClauseEmbedding.sql",
        "31_clause_embedding.sql",
        "0031ab_clause_embedding.sql",
        "0031-clause-embedding.sql",
    ],
)
def test_a_filename_outside_the_convention_is_refused(tmp_path: Path, name: str) -> None:
    assert "filename-convention" in rules(tmp_path / name, HEADER + "CREATE TABLE t ();\n")


def test_the_filename_finding_names_the_file_and_the_consequence(tmp_path: Path) -> None:
    path = tmp_path / "0031_clause_embedding.fallback.sql"
    (finding,) = [
        f
        for f in lint_text(path, HEADER + "CREATE TABLE t ();\n", require_citation=True)
        if f.rule == "filename-convention"
    ]
    assert "0031_clause_embedding.fallback.sql" in finding.detail
    # The consequence is not "this file is wrong". It is "every OTHER file is now
    # unreachable", and the message has to say so or nobody prioritises the fix.
    assert "SECOND DOT" in finding.detail
    assert "undiscoverable" in finding.detail.lower()


@pytest.mark.parametrize(
    "name",
    ["0001_role_mainline_owner.sql", "0006a_role_migrator.sql", "0009x_covenant_comment.sql"],
)
def test_a_conforming_filename_passes(tmp_path: Path, name: str) -> None:
    assert "filename-convention" not in rules(tmp_path / name, HEADER + "CREATE TABLE t ();\n")


def test_a_template_name_is_not_held_to_the_migration_convention(tmp_path: Path) -> None:
    (tmp_path / "0050_permit.sql.j2").write_text("CREATE TABLE {{ s }}.permit ();\n", "utf-8")
    assert "filename-convention" not in {f.rule for f in lint_paths([tmp_path]).findings}


# ── RULE B · the allocation (MR-6 lock 1) ───────────────────────────────────────────


def test_a_hand_authored_file_in_a_rendered_band_is_refused(tmp_path: Path) -> None:
    root = banded_tree(tmp_path)
    write(root, "0006_schema_mainline_ops.sql", HEADER + "CREATE SCHEMA mainline_ops;\n")
    (finding,) = [f for f in lint_paths([root]).findings if f.rule == "allocation-mode"]
    assert "0001-0018z" in finding.detail
    assert "kernel/render-and-foundation" in finding.detail
    assert "rendered" in finding.detail


def test_a_rendered_file_in_an_authored_band_is_refused(tmp_path: Path) -> None:
    root = banded_tree(tmp_path)
    body = RENDERED_BANNER + "\n" + HEADER + "CREATE TABLE t ();\n"
    write(root, "0019_retention_class.sql", body)
    (finding,) = [f for f in lint_paths([root]).findings if f.rule == "allocation-mode"]
    assert "0019-0020z" in finding.detail
    assert "datamodel/dm-foundation" in finding.detail
    assert "authored" in finding.detail


def test_a_file_in_its_own_band_passes_in_both_modes(tmp_path: Path) -> None:
    root = banded_tree(tmp_path)
    write(root, "0006a_role_migrator.sql", RENDERED_BANNER + "\n" + HEADER + "CREATE ROLE r;\n")
    write(root, "0020a_site.sql", HEADER + "CREATE TABLE mainline.site ();\n")
    assert lint_paths([root]).ok


def test_a_file_in_the_unallocated_band_is_refused(tmp_path: Path) -> None:
    # MRR-7 in one test: 0200+ has no owner, so nothing may be written there. The
    # algorithms 0205/0207/0211 annexe is the population this refuses.
    root = banded_tree(tmp_path)
    write(root, "0205_delta_witness.sql", HEADER + "CREATE TABLE mainline.delta_witness ();\n")
    (finding,) = [f for f in lint_paths([root]).findings if f.rule == "allocation-unallocated"]
    assert "UNALLOCATED" in finding.detail


def test_rule_b_is_silent_where_no_allocation_governs_the_tree(tmp_path: Path) -> None:
    # Template directories and the reference vertical declare no bands. Silence there is
    # the correct answer; inventing one would be a guess with the authority of a lint.
    root = tmp_path / "templates_out"
    root.mkdir()
    write(root, "0006_schema.sql", HEADER + "CREATE SCHEMA s;\n")
    assert lint_paths([root]).ok


def test_the_committed_allocation_governs_the_committed_tree() -> None:
    if not MIGRATIONS.is_dir():
        pytest.skip("the vertical's migration tree is absent from this checkout")
    allocation = load_allocation(MIGRATIONS.parent / f"{MIGRATIONS.name}{ALLOCATION_SUFFIX}")
    report = lint_paths([MIGRATIONS], allocation=allocation)
    # Every rendered file must sit in a rendered band and every authored file in an
    # authored one. A mode mismatch here means the seam moved without the ruling moving.
    mismatches = [f.render() for f in report.findings if f.rule == "allocation-mode"]
    assert mismatches == []


# ── RULE C · `.up.sql` is a failure, and it is red on purpose ───────────────────────


def test_up_sql_is_refused_with_the_ruling_s_own_sentence(tmp_path: Path) -> None:
    findings = lint_text(
        tmp_path / "0001_role_mainline_owner.up.sql",
        HEADER + "CREATE ROLE mainline_owner;\n",
        require_citation=True,
    )
    (finding,) = [f for f in findings if f.rule == "up-sql-suffix"]
    assert finding.detail == UP_SQL_DETAIL


def test_a_condemned_up_sql_file_is_not_also_reported_by_rules_a_and_b(tmp_path: Path) -> None:
    # One file, one refusal, one fix. `0001_..._owner.up.sql` is in a RENDERED band and
    # carries no banner, so rule B would have plenty to say; saying it would bury the
    # finding whose remedy actually comes first.
    root = banded_tree(tmp_path)
    write(root, "0001_role_mainline_owner.up.sql", HEADER + "CREATE ROLE mainline_owner;\n")
    found = {f.rule for f in lint_paths([root]).findings}
    assert found == {"up-sql-suffix"}


def test_the_committed_tree_carries_no_up_sql_file() -> None:
    """RED BY DESIGN until reconciliation workers 3, 4 and 5 land their renames.

    This is the PL-2 artefact of the migration reconciliation of 2026-08-08. A guard
    that was *observed* red is a guard that asserts something; a guard that only ever
    ran green is a guard nobody has evidence works. Do not xfail it, do not skip it, do
    not soften rule C to make it pass. It goes green when the last `.up.sql` is renamed
    to `.sql`, and the red run before that is the evidence the rule was ever live.
    """
    if not MIGRATIONS.is_dir():
        pytest.skip("the vertical's migration tree is absent from this checkout")
    offenders = sorted(p.name for p in MIGRATIONS.glob("*.up.sql"))
    assert offenders == [], (
        f"{len(offenders)} file(s) still carry `.up.sql`. {UP_SQL_DETAIL}. "
        "This assertion is the reconciliation's PL-2 artefact and is red on purpose "
        "until workers 3, 4 and 5 finish: " + ", ".join(offenders[:5]) + " ..."
    )
