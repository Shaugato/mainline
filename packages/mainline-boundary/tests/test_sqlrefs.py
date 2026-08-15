# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""Unit tests for the Leg A census scanner.

This scanner is the leg most likely to rot into a no-op, for the reason
``test_astscan_sbom.py`` states about E3 and which is worse here: a scan that finds
nothing looks exactly like an application that demands nothing, and an application that
demands nothing needs no grants, so a broken scanner CERTIFIES a clean privilege surface.
Every test below therefore checks that something specific was **found**, and the two that
matter most check that something specific was **refused**: a file that will not parse, and
a name one extraction leg can see and the other cannot.

The floors are asserted against the real tree, not against a fixture. Fixtures below pass
explicit ``minimum_*`` arguments because a three-file synthetic tree cannot carry 39
relations; that is a parameter of the fixture and never a relaxation of the shipped
default, which :func:`test_the_real_demo_api_tree_clears_its_floors` asserts at its
committed value.
"""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from mainline_boundary.repo import find_repo_root
from mainline_boundary.sqlrefs import (
    DEMO_API_ROOTS,
    DYNAMIC_RELATION,
    MINIMUM_LITERAL_RELATIONS,
    MINIMUM_RESOLVED_RELATIONS,
    MINIMUM_ROUTINE_DEMANDS,
    NOT_PRIVILEGE_DEMANDS,
    PRAGMA_NOT_SQL,
    PRIVILEGED_SCHEMAS,
    RULE_LITERAL_FLOOR,
    RULE_PATHS_DISAGREE,
    RULE_ROUTINE_FLOOR,
    RULE_UNPARSEABLE,
    RULE_UNRESOLVED_DYNAMIC,
    RULE_UNRULED_SCHEMA,
    check_sql_reference_census,
    declared_relations,
    scan_source,
)

REPO_ROOT = find_repo_root(Path(__file__))
DEMO_API_SRC = REPO_ROOT / DEMO_API_ROOTS[0]


def _pairs(source: str) -> set[tuple[str, str]]:
    scan = scan_source("m.py", source)
    return {d.pair for d in scan.ast_demands}


def _tiny_repo(tmp_path: Path, *, module: str, migration: str = "") -> Path:
    """A repository shaped like this one, with one demo-api module and one migration."""
    src = tmp_path / DEMO_API_ROOTS[0]
    src.mkdir(parents=True)
    (src / "app.py").write_text(module, encoding="utf-8")
    migrations = tmp_path / "verticals/mainline/db/migrations"
    migrations.mkdir(parents=True)
    (migrations / "0001_x.sql").write_text(migration, encoding="utf-8")
    return tmp_path


def _check_fixture(root: Path, **floors: int):
    """Run the census over a SYNTHETIC tree with the floors switched off by default.

    A two-line fixture cannot carry 39 relations, and asserting that it does not would be
    asserting nothing about the shipped default. The floors are parameters here and are
    checked at their committed values against the real tree by
    :func:`test_the_real_demo_api_tree_clears_its_floors`. Nothing in this file may pass a
    lowered floor to ``REPO_ROOT``.
    """
    assert root != REPO_ROOT, "the real tree is checked at the shipped floors, never lowered"
    return check_sql_reference_census(
        root,
        minimum_literal=floors.get("minimum_literal", 0),
        minimum_resolved=floors.get("minimum_resolved", 0),
        minimum_routines=floors.get("minimum_routines", 0),
    )


# ── the verb, which is the whole reason the unit is a pair and not a name ────────────


@pytest.mark.parametrize(
    ("statement", "expected"),
    [
        ("SELECT * FROM mainline.permit", {("mainline.permit", "SELECT")}),
        ("JOIN mainline.site s ON s.id = p.id", {("mainline.site", "SELECT")}),
        (
            "INSERT INTO mainline.exposure_line (a) VALUES (1)",
            {("mainline.exposure_line", "INSERT")},
        ),
        ("UPDATE mainline.permit SET head_seq = 2", {("mainline.permit", "UPDATE")}),
        ("CALL mainline.merge_permit(%s)", {("mainline.merge_permit", "EXECUTE")}),
        (
            "DELETE FROM mainline.blocking_check WHERE false",
            {("mainline.blocking_check", "DELETE")},
        ),
        (
            "UPSERT INTO mainline_ops.outbox (a) VALUES (1)",
            {("mainline_ops.outbox", "INSERT"), ("mainline_ops.outbox", "UPDATE")},
        ),
    ],
)
def test_each_keyword_is_classified_as_the_privilege_its_statement_needs(
    statement: str, expected: set[tuple[str, str]]
) -> None:
    assert _pairs(f'SQL = """{statement}"""') == expected


def test_a_delete_is_never_read_as_a_select() -> None:
    """``DELETE FROM x`` contains ``FROM x``. MI01 says no role in this system holds DELETE.

    If the alternation ever stops preferring the longer form, the one privilege nobody
    holds becomes the one privilege everybody appears to hold, silently.
    """
    assert _pairs('SQL = "DELETE FROM mainline.permit"') == {("mainline.permit", "DELETE")}


def test_a_routine_invoked_inside_a_select_is_an_execute_demand() -> None:
    """``refusal.py:141``'s shape: a routine no statement keyword precedes.

    ``SELECT trappoint.explain_refusal(%s, %s, %s, %s)`` needs EXECUTE exactly as much as
    ``CALL mainline.merge_permit(…)`` does, and the keyword list the brief enumerates does
    not reach it. It was found by measuring the tree, not by reading the specification.
    """
    assert _pairs('SQL = "SELECT trappoint.explain_refusal(%s, %s)"') == {
        ("trappoint.explain_refusal", "EXECUTE")
    }


def test_an_insert_column_list_is_not_mistaken_for_a_routine_call() -> None:
    """Why the routine rule requires ``SELECT`` in front and is not simply ``<name>(``.

    ``INSERT INTO mainline.disposition (disposition_id, …)`` matches the general shape
    ``<schema>.<relation>(``. A looser rule would turn every insert in this application
    into an EXECUTE demand on a table, and EXECUTE on a table is not a privilege anybody
    can grant.
    """
    assert _pairs('SQL = "INSERT INTO mainline.disposition (disposition_id) VALUES (%s)"') == {
        ("mainline.disposition", "INSERT")
    }


def test_a_relation_written_under_two_verbs_is_two_demands() -> None:
    source = textwrap.dedent(
        '''
        READ = """SELECT * FROM mainline.exposure_receipt"""
        WRITE = """INSERT INTO mainline.exposure_receipt (a) VALUES (1)"""
        '''
    )
    assert _pairs(source) == {
        ("mainline.exposure_receipt", "SELECT"),
        ("mainline.exposure_receipt", "INSERT"),
    }


# ── the scanner catches a name added to demo-api SQL ─────────────────────────────────


def test_a_name_added_to_a_real_demo_api_sql_string_is_caught() -> None:
    """The mutation is applied to the SHIPPING file, not to a fixture that resembles it.

    A fixture proves the regex works on the fixture. This proves it works on
    ``reads.py`` — 99 KB of real SQL, real f-strings, real prose — which is the file the
    census actually reads.
    """
    reads = DEMO_API_SRC / "reads.py"
    assert reads.is_file(), f"{reads} is the file this census reads; it is not there"
    original = reads.read_text(encoding="utf-8")

    before = {d.pair for d in scan_source("reads.py", original).ast_demands}
    mutated = original + '\n_SMUGGLED = """SELECT x FROM mainline.brand_new_relation"""\n'
    after = {d.pair for d in scan_source("reads.py", mutated).ast_demands}

    assert before, "reads.py demanded nothing at all, which cannot be right"
    assert after - before == {("mainline.brand_new_relation", "SELECT")}


def test_a_write_added_to_a_relation_already_read_is_caught_as_a_new_demand() -> None:
    """R4b's shape: the NAME was already there and the VERB is what changed."""
    reads = (DEMO_API_SRC / "reads.py").read_text(encoding="utf-8")
    before = {d.pair for d in scan_source("reads.py", reads).ast_demands}
    assert ("mainline.permit", "SELECT") in before
    assert ("mainline.permit", "INSERT") not in before

    mutated = reads + '\n_SMUGGLED = """INSERT INTO mainline.permit (a) VALUES (1)"""\n'
    after = {d.pair for d in scan_source("reads.py", mutated).ast_demands}
    assert after - before == {("mainline.permit", "INSERT")}


# ── unparseable is a violation, not a skip ───────────────────────────────────────────


def test_a_malformed_file_is_returned_as_a_syntax_error_not_raised() -> None:
    scan = scan_source("broken.py", "def f(:\n    pass\n")
    assert scan.syntax_error is not None
    assert scan.ast_demands == () and scan.raw_demands == ()


def test_a_malformed_file_makes_the_census_red_rather_than_short(tmp_path: Path) -> None:
    """The failure mode this refuses: a file that will not parse contributing zero demands.

    An unparseable module scans as an application that issues no SQL. Its grants then look
    like over-grants and its missing grants look like nothing at all, and the report is
    clean. "Not cleared" is not "clean" — the same sentence E3 makes about the kernel.
    """
    root = _tiny_repo(
        tmp_path,
        module='SQL = """SELECT * FROM mainline.permit"""\ndef broken(:\n    pass\n',
    )
    _scan, report = _check_fixture(root)
    assert RULE_UNPARSEABLE in report.rules_violated(), report.summary()
    assert "has not been cleared" in report.violations[0].detail


# ── the two extraction legs, and why disagreement is red ─────────────────────────────


def test_the_two_legs_agree_on_the_real_tree() -> None:
    scan, _report = check_sql_reference_census(REPO_ROOT)
    ast_only, raw_only = scan.disagreement()
    assert (ast_only, raw_only) == (frozenset(), frozenset()), (
        f"AST leg only: {sorted(ast_only)}; raw-byte leg only: {sorted(raw_only)}"
    )
    assert scan.ast_pairs(), "both legs found nothing, which agrees vacuously"


def test_a_name_split_across_an_implicit_concatenation_makes_the_legs_disagree(
    tmp_path: Path,
) -> None:
    """The evasion the second leg exists to catch, and the proof it is not a rubber stamp.

    Python folds ``"FROM mainline.expo" "sure_line"`` into one constant before the AST leg
    ever sees it, so that leg reports ``mainline.exposure_line``. The raw sweep reads
    bytes and sees two fragments, neither of which carries the name. Taking the union
    would hide the divergence; the census refuses instead, and names the pair.
    """
    root = _tiny_repo(
        tmp_path,
        module='SQL = ("SELECT a FROM mainline.expo"\n       "sure_line")\n',
    )
    _scan, report = _check_fixture(root)
    assert RULE_PATHS_DISAGREE in report.rules_violated(), report.summary()
    assert any("mainline.exposure_line" in v.subject for v in report.violations)
    assert any("do not take the union" in v.detail for v in report.violations)


def test_an_f_string_hole_is_seen_identically_by_both_legs(tmp_path: Path) -> None:
    root = _tiny_repo(
        tmp_path,
        module='def q(name):\n    return f"SELECT * FROM mainline_audit.{name} LIMIT 25"\n',
        migration="CREATE VIEW mainline_audit.v_one AS SELECT 1;\n",
    )
    scan, report = _check_fixture(root, minimum_resolved=1)
    assert report.ok, report.summary()
    assert scan.disagreement() == (frozenset(), frozenset())
    assert any(d.relation == DYNAMIC_RELATION for d in scan.ast_demands)


# ── the catalogs, excluded by name and recorded ──────────────────────────────────────


@pytest.mark.parametrize("schema", sorted(NOT_PRIVILEGE_DEMANDS))
def test_a_catalog_read_is_an_exemption_with_a_reason_and_not_a_demand(
    schema: str, tmp_path: Path
) -> None:
    root = _tiny_repo(tmp_path, module=f'SQL = "SELECT * FROM {schema}.some_table"\n')
    scan, report = _check_fixture(root)
    assert report.ok, report.summary()
    assert scan.pairs() == frozenset()
    assert [e.rule for e in report.exemptions] == [RULE_UNRULED_SCHEMA]
    assert "readable by every login" in report.exemptions[0].reason


def test_the_real_tree_s_catalog_reads_are_recorded_rather_than_silent() -> None:
    """``reads.py`` really does read all three catalogs; the report must say so out loud."""
    _scan, report = check_sql_reference_census(REPO_ROOT)
    named = {e.reason.split()[0] for e in report.exemptions if e.rule == RULE_UNRULED_SCHEMA}
    assert "information_schema.views" in named, report.summary()
    assert any(name.startswith("pg_catalog.") for name in named), sorted(named)


# ── the visible escape hatch, and the schema this census has no ruling for ───────────


def test_an_unruled_schema_in_a_string_is_a_violation(tmp_path: Path) -> None:
    root = _tiny_repo(tmp_path, module='SQL = "SELECT * FROM public.legacy_table"\n')
    _scan, report = _check_fixture(root)
    assert RULE_UNRULED_SCHEMA in report.rules_violated(), report.summary()


def test_the_pragma_turns_that_violation_into_a_recorded_exemption(tmp_path: Path) -> None:
    root = _tiny_repo(
        tmp_path,
        module=f'SQL = "SELECT * FROM public.legacy_table"  # {PRAGMA_NOT_SQL} prose, not SQL\n',
    )
    _scan, report = _check_fixture(root)
    assert report.ok, report.summary()
    assert [e.rule for e in report.exemptions] == [RULE_UNRULED_SCHEMA]
    assert PRAGMA_NOT_SQL in report.exemptions[0].reason


def test_a_python_import_is_not_mistaken_for_a_table_by_the_ast_leg(tmp_path: Path) -> None:
    """``from collections.abc import Iterator`` is ``FROM collections.abc`` to a byte sweep.

    Five such lines exist in the shipping tree. They are code, not string constants, so the
    AST leg cannot see them and the raw leg is filtered to the ruled schemas — which is why
    the unruled-schema rule is applied on the AST leg only, and why the two legs agree.
    """
    root = _tiny_repo(
        tmp_path,
        module="from collections.abc import Iterator\nfrom urllib.parse import urlsplit\n",
    )
    scan, report = _check_fixture(root)
    assert report.ok, report.summary()
    assert scan.disagreement() == (frozenset(), frozenset())


# ── resolving the dynamic reference against the migration set ────────────────────────


def test_the_migration_set_is_the_authority_for_what_a_schema_contains() -> None:
    declared = declared_relations(REPO_ROOT)
    audit = declared.get("mainline_audit", ())
    assert len(audit) >= MINIMUM_RESOLVED_RELATIONS, sorted(audit)
    assert "v_open_gate_summary" in audit
    assert all(name.startswith("v_") for name in audit), sorted(audit)


def test_a_dynamic_reference_into_an_undeclarable_schema_is_a_violation(tmp_path: Path) -> None:
    """A demand the census cannot measure has not been measured, so it may not be dropped."""
    root = _tiny_repo(
        tmp_path,
        module='def q(n):\n    return f"SELECT * FROM mainline_ops.{n}"\n',
        migration="-- no CREATE statements at all\n",
    )
    _scan, report = _check_fixture(root)
    assert RULE_UNRESOLVED_DYNAMIC in report.rules_violated(), report.summary()


def test_the_real_tree_resolves_its_one_dynamic_reference_to_the_audit_views() -> None:
    scan, _report = check_sql_reference_census(REPO_ROOT)
    resolved = scan.resolved_relations()
    assert len(resolved) >= MINIMUM_RESOLVED_RELATIONS, sorted(resolved)
    assert all(name.startswith("mainline_audit.v_") for name in resolved), sorted(resolved)
    assert all(d.verb == "SELECT" for d in scan.resolved)
    assert all("reads.py" in d.path for d in scan.resolved), "the site must stay printable"


# ── the floors ───────────────────────────────────────────────────────────────────────


def test_a_scanner_that_finds_three_fails_rather_than_passes(tmp_path: Path) -> None:
    """The whole point of the file, stated as a test: a short list must be red."""
    root = _tiny_repo(
        tmp_path,
        module=textwrap.dedent(
            '''
            A = """SELECT * FROM mainline.permit"""
            B = """SELECT * FROM mainline.disposition"""
            C = """SELECT * FROM mainline.merge_record"""
            '''
        ),
    )
    scan, report = _check_fixture(root, minimum_literal=MINIMUM_LITERAL_RELATIONS)
    assert len(scan.literal_relations()) == 3
    assert RULE_LITERAL_FLOOR in report.rules_violated(), report.summary()
    assert any("never lower it" in v.detail for v in report.violations_for(RULE_LITERAL_FLOOR))


def test_a_tree_that_stops_invoking_a_routine_trips_the_routine_floor(tmp_path: Path) -> None:
    """The routine leg has its own floor because it has its own regex, which can rot alone."""
    root = _tiny_repo(tmp_path, module='A = """CALL mainline.merge_permit(%s)"""\n')
    scan, report = _check_fixture(root, minimum_routines=MINIMUM_ROUTINE_DEMANDS)
    assert scan.routines() == frozenset({"mainline.merge_permit"})
    assert RULE_ROUTINE_FLOOR in report.rules_violated(), report.summary()
    assert any("explain_refusal" in v.detail for v in report.violations_for(RULE_ROUTINE_FLOOR))


def test_the_real_demo_api_tree_clears_its_floors() -> None:
    """39 keyword-reached names, 14 resolved views, 2 routines. Floors, never ceilings.

    The scan finds 40 names today rather than 39: the plan's R4 count was taken with the
    statement-keyword rule alone, and the routine rule adds ``trappoint.explain_refusal``.
    A floor is a minimum, so 39 stays the committed value and the extra name is a wider
    net, not a moved goalpost.
    """
    scan, report = check_sql_reference_census(REPO_ROOT)
    assert report.ok, report.summary()
    assert report.examined >= 1, "a clean census over zero files is not a clean census"
    assert not scan.parse_failures, [f.path for f in scan.parse_failures]
    assert len(scan.literal_relations()) >= MINIMUM_LITERAL_RELATIONS
    assert len(scan.resolved_relations()) >= MINIMUM_RESOLVED_RELATIONS
    assert len(scan.routines()) >= MINIMUM_ROUTINE_DEMANDS
    assert MINIMUM_LITERAL_RELATIONS == 39
    assert MINIMUM_RESOLVED_RELATIONS == 14
    assert MINIMUM_ROUTINE_DEMANDS == 2


def test_the_real_tree_names_both_routines_the_matrix_must_account_for() -> None:
    scan, _report = check_sql_reference_census(REPO_ROOT)
    assert scan.routines() == frozenset({"mainline.merge_permit", "trappoint.explain_refusal"}), (
        sorted(scan.routines())
    )
    assert any("gate_run.py" in s for s in scan.sites_for("mainline.merge_permit", "EXECUTE"))
    assert any("refusal.py" in s for s in scan.sites_for("trappoint.explain_refusal", "EXECUTE"))


def test_an_absent_source_root_is_a_skip_with_a_reason_and_not_a_pass(tmp_path: Path) -> None:
    _scan, report = _check_fixture(tmp_path)
    assert report.skips, report.summary()
    assert "NOT a pass" in report.skips[0].reason
    assert report.examined == 0


# ── provenance, which is what makes a failure actionable ─────────────────────────────


def test_every_demand_carries_a_file_and_a_line_an_operator_can_open() -> None:
    scan, _report = check_sql_reference_census(REPO_ROOT)
    for demand in scan.demands:
        assert demand.path.startswith("verticals/mainline/apps/demo-api/"), demand
        assert demand.lineno >= 1, demand
        assert demand.schema in PRIVILEGED_SCHEMAS, demand
    assert scan.sites_for("mainline.permit", "UPDATE"), "the UPDATE site must be printable"
    assert any("gate_run.py" in site for site in scan.sites_for("mainline.permit"))
