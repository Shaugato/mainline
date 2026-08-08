# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""Ordering, hashing, and the shapes the runner refuses to read."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from trappoint_migrate.discovery import MIGRATION_SUFFIXES, discover, statement_count
from trappoint_migrate.errors import MigrationTreeInvalid


def write(root: Path, name: str, body: str = "-- MI01\nCREATE TABLE t ();\n") -> Path:
    path = root / name
    path.write_text(body, encoding="utf-8")
    return path


def test_absent_directory_is_an_empty_stream_not_an_error(tmp_path: Path) -> None:
    # A binding whose SQL has not been rendered yet is a normal state on the way to K1.
    assert discover(tmp_path / "nope") == []


def test_empty_directory_is_an_empty_stream(tmp_path: Path) -> None:
    assert discover(tmp_path) == []


def test_letter_suffixes_order_within_a_slot(tmp_path: Path) -> None:
    # Ruling D7: `0071a` before `0071b` before `0072`, lexicographically on the FULL
    # stem. Parsing the number and sorting on it would make 0071a and 0071b collide.
    for name in ("0072_after.sql", "0071b_second.sql", "0071a_first.sql", "0009_early.sql"):
        write(tmp_path, name)
    assert [m.version for m in discover(tmp_path)] == [
        "0009_early",
        "0071a_first",
        "0071b_second",
        "0072_after",
    ]


def test_up_sql_suffix_is_now_refused_outright(tmp_path: Path) -> None:
    # NARROWED 2026-08-08. This test previously asserted the opposite: that `.up.sql`
    # was accepted and stripped. That tolerance existed only so the 49 offending files
    # stayed DISCOVERABLE while the reconciliation renames were in flight.
    #
    # The renames landed (0 `.up.sql` on disk, 105/105 files matching the convention),
    # so the tolerance was removed. The behaviour that replaces it is strictly stronger
    # than silence: `0001_schema.up.sql` still ends in `.sql`, so discovery strips only
    # that and is left with the stem `0001_schema.up`, whose `.` fails `_VERSION_RE`.
    # The tree is REFUSED, not walked past. A banned filename that is merely ignored
    # loses a migration without saying so; one that raises cannot.
    write(tmp_path, "0001_schema.up.sql")
    with pytest.raises(MigrationTreeInvalid, match="NNNN"):
        discover(tmp_path)


def test_down_migrations_are_refused(tmp_path: Path) -> None:
    write(tmp_path, "0001_schema.sql")
    write(tmp_path, "0001_schema.down.sql", "DROP SCHEMA mainline;")
    with pytest.raises(MigrationTreeInvalid, match="forward-only"):
        discover(tmp_path)


def test_unparseable_filename_is_refused(tmp_path: Path) -> None:
    write(tmp_path, "create_the_thing.sql")
    with pytest.raises(MigrationTreeInvalid, match="NNNN"):
        discover(tmp_path)


def test_duplicate_version_across_suffixes_is_now_unreachable(tmp_path: Path) -> None:
    # NARROWED 2026-08-08. The cross-suffix duplicate — a rendered `0010_x.sql` beside
    # a hand-authored `0010_x.up.sql`, both stripping to the same version — WAS the
    # incident (numbers 0010-0016 on 2026-08-08). With one legal suffix it is no longer
    # expressible, so this asserts the refusal now happens EARLIER and for a more basic
    # reason: the filename itself is invalid, before any duplicate check runs.
    #
    # Duplicate detection is still live for genuine same-suffix clashes — see
    # `test_two_files_claiming_one_version_are_refused` — this only records that the
    # cross-suffix route into that state has been closed by construction.
    write(tmp_path, "0001_schema.sql")
    write(tmp_path, "0001_schema.up.sql")
    with pytest.raises(MigrationTreeInvalid, match="NNNN"):
        discover(tmp_path)


def test_sha256_is_over_the_file_bytes(tmp_path: Path) -> None:
    body = "-- MI03\nCREATE TABLE t ();\n"
    write(tmp_path, "0001_t.sql", body)
    (migration,) = discover(tmp_path)
    assert migration.sha256 == hashlib.sha256(body.encode("utf-8")).digest()


def test_cited_invariants_come_from_the_header_only(tmp_path: Path) -> None:
    write(
        tmp_path,
        "0001_t.sql",
        "-- MI02, I03: the gate\nCREATE TABLE t (x INT8);\n-- MI30 mentioned late\n",
    )
    (migration,) = discover(tmp_path)
    assert migration.cited_invariants == ("MI02", "I03")


# ── what the three new lint rules look like from the runner's side ──────────────────


def test_a_second_dot_makes_the_whole_directory_undiscoverable(tmp_path: Path) -> None:
    # RULE A, seen from the runner. `_VERSION_RE` does not admit '.', so the stem
    # `0031_clause_embedding.fallback` has no defined position and the runner refuses
    # the ENTIRE tree — the four well-named files beside it go unapplied too. This is
    # why the lint's message shouts about the second dot rather than about tidiness.
    for name in ("0028_clause.sql", "0029_clause_version.sql", "0030_clause_band.sql"):
        write(tmp_path, name)
    write(tmp_path, "0031_clause_embedding.fallback.sql")
    with pytest.raises(MigrationTreeInvalid, match="NNNN"):
        discover(tmp_path)


def test_the_up_sql_tolerance_is_still_in_force_and_pinned_here(tmp_path: Path) -> None:
    # RULE C's other half, now CLOSED. The tuple previously carried `.up.sql` so the
    # 49 offending files stayed discoverable while the renames were in flight; the
    # comment that shipped with it required the narrowing to be "a deliberate edit to
    # a test and not a side effect nobody reviewed". This is that edit.
    #
    # Preconditions verified before flipping, on 2026-08-08:
    #   * `find verticals packages -name '*.up.sql'` returned 0
    #   * the chain verifier independently confirmed 105/105 files matching
    #     `^\d{4}[a-z]?_[a-z0-9_]+\.sql$`, zero `.up.sql`, zero second-dot names
    #
    # `.up.sql` is now unreachable by CONSTRUCTION rather than by lint, which is the
    # stronger guarantee: the lint could be disabled, the parser cannot be talked out
    # of a `.` in the slug.
    assert MIGRATION_SUFFIXES == (".sql",)
    write(tmp_path, "0001_role_mainline_owner.up.sql")
    with pytest.raises(MigrationTreeInvalid, match="NNNN"):
        discover(tmp_path)


def test_the_up_sql_twin_of_a_rendered_file_is_the_incident_in_one_test(tmp_path: Path) -> None:
    # RULE B and RULE C's shared consequence, and the exact shape of numbers 0010-0016
    # on 2026-08-08: a rendered `.sql` beside a hand-authored `.up.sql`. Both stems
    # strip to `0010_type_control_delta`, so `trappoint render --check` sees zero diff
    # (an extra file is not a diff) while the runner refuses the tree. CI green, deploy
    # dead — which is why the collision report is now a --check failure too.
    write(tmp_path, "0010_type_control_delta.sql", "-- MI01\nCREATE TYPE d AS ENUM ('a');\n")
    write(tmp_path, "0010_type_control_delta.up.sql", "-- MI01\nCREATE TYPE d AS ENUM ('a');\n")
    with pytest.raises(MigrationTreeInvalid, match="0010_type_control_delta"):
        discover(tmp_path)


def test_the_down_sql_refusal_is_untouched_by_the_reconciliation(tmp_path: Path) -> None:
    # MR-5 removes `.up.sql` precisely BECAUSE it names this counterpart, so the
    # refusal that makes the counterpart illegal must outlive the suffix change.
    write(tmp_path, "0001_schema.sql")
    write(tmp_path, "0001_schema.down.sql", "DROP SCHEMA mainline;")
    with pytest.raises(MigrationTreeInvalid, match="forward-only"):
        discover(tmp_path)


@pytest.mark.parametrize(
    ("sql", "expected"),
    [
        ("CREATE TABLE t ();", 1),
        ("CREATE TABLE t ();\n", 1),
        ("CREATE TABLE t (); CREATE TABLE u ();", 2),
        ("-- comment only\n", 0),
        ("CREATE FUNCTION f() RETURNS INT8 AS $$ BEGIN RETURN 1; END; $$ LANGUAGE plpgsql;", 1),
        ("INSERT INTO t VALUES ('a;b');", 1),
    ],
)
def test_statement_count_ignores_semicolons_inside_quoted_regions(sql: str, expected: int) -> None:
    assert statement_count(sql) == expected
