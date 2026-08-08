# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""``--check`` refuses a tree the migration runner cannot discover (MR-6 lock 3).

``stem_collisions()`` was written before the incident of 2026-08-08, it was correct
throughout it, and it caught nothing — because its result was printed to stderr and
returned to nobody, and ``--check``'s exit code was decided only by ``check_units()``.
Seven duplicate stems, ``0010``-``0016``, each a rendered ``.sql`` beside a
hand-authored ``.up.sql``, sat in the output directory while ``--check`` said "zero
diff" and meant it: an extra file is not a diff.

The lesson is not about that function. It is that **a check whose finding does not reach
an exit code is not a check**, so these tests assert the exit-code path, not the
printing.

Every fixture is written through ``put()``, which writes BYTES. The render engine
compares bytes, and on Windows the default text mode would translate the newlines and
turn every fixture into a ``diff`` finding for a reason that has nothing to do with the
SQL — the same trap ``write_units()`` documents.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import cast

import pytest

from trappoint_sql.render import (
    RENDERED_BANNER,
    RenderResult,
    Unit,
    check_units,
    collision_findings,
    stem_collisions,
    version_stem,
)

THE_SEVEN = (
    "0010_type_control_delta",
    "0011_type_subject_state",
    "0012_type_disposition_kind",
    "0013_type_virulence_class",
    "0014_type_blame_basis",
    "0015_type_blame_state",
    "0016_type_prop_state",
)


def result_over(directory: Path, units: tuple[Unit, ...] = ()) -> RenderResult:
    """A ``RenderResult`` stand-in carrying exactly what ``check_units`` reads."""
    binding = SimpleNamespace(output_dir=directory, source=directory / "vertical.toml")
    return cast(RenderResult, SimpleNamespace(binding=binding, units=units))


def rendered() -> str:
    return f"{RENDERED_BANNER}\n-- MI01: the seven types.\nCREATE TYPE t AS ENUM ('a');\n"


def authored() -> str:
    return "-- MI01: the seven types.\nCREATE TYPE t AS ENUM ('a');\n"


def put(directory: Path, name: str, text: str) -> Path:
    path = directory / name
    path.write_bytes(text.encode("utf-8"))
    return path


def seed_the_incident(directory: Path) -> None:
    """Reproduce numbers 0010-0016 exactly as they sat on disk on 2026-08-08."""
    for stem in THE_SEVEN:
        put(directory, f"{stem}.sql", rendered())
        put(directory, f"{stem}.up.sql", authored())


# -- the function itself ------------------------------------------------------------


def test_a_clean_directory_has_no_collisions(tmp_path: Path) -> None:
    put(tmp_path, "0010_type_control_delta.sql", rendered())
    put(tmp_path, "0011_type_subject_state.sql", rendered())
    assert stem_collisions(tmp_path) == []


def test_an_absent_directory_has_no_collisions(tmp_path: Path) -> None:
    assert stem_collisions(tmp_path / "not-rendered-yet") == []


def test_a_letter_suffix_is_not_a_collision(tmp_path: Path) -> None:
    # Ruling D7's letter suffix is the mechanism, not the fault. `0029` and `0029a` have
    # one owner and two versions; the report that grouped on the leading four digits
    # called them a collision and was wrong twice over.
    put(tmp_path, "0029_clause_version.sql", rendered())
    put(tmp_path, "0029a_clause_version_trgm.sql", rendered())
    assert stem_collisions(tmp_path) == []


def test_the_seven_type_stems_are_reported(tmp_path: Path) -> None:
    seed_the_incident(tmp_path)
    reported = stem_collisions(tmp_path)
    assert [stem for stem, _ in reported] == list(THE_SEVEN)
    for stem, names in reported:
        assert set(names) == {f"{stem}.sql", f"{stem}.up.sql"}


def test_the_stem_is_what_the_runner_would_order_on() -> None:
    assert version_stem("0010_type_control_delta.up.sql") == "0010_type_control_delta"
    assert version_stem("0010_type_control_delta.sql") == "0010_type_control_delta"


# -- the promotion: it now decides an exit code -------------------------------------


def test_collisions_become_check_findings(tmp_path: Path) -> None:
    seed_the_incident(tmp_path)
    findings = collision_findings(tmp_path)
    assert len(findings) == len(THE_SEVEN)
    assert {f.kind for f in findings} == {"collision"}


def test_check_units_refuses_the_incident_tree(tmp_path: Path) -> None:
    # THE REGRESSION TEST FOR THE INCIDENT. Every rendered unit is byte-identical to
    # what is committed, so `missing`, `diff` and `stale` all find nothing - this is a
    # zero-diff tree by the old contract. It must still be refused.
    seed_the_incident(tmp_path)
    units = tuple(
        Unit(name=f"{stem}.sql", template="0010_types.sql.j2", text=rendered())
        for stem in THE_SEVEN
    )
    findings = check_units(result_over(tmp_path, units))
    assert [f.kind for f in findings] == ["collision"] * len(THE_SEVEN)
    assert findings, "a zero-diff tree the runner refuses to discover is not a passing check"


def test_a_collision_finding_names_both_files_and_who_removes_which(tmp_path: Path) -> None:
    seed_the_incident(tmp_path)
    (finding,) = [f for f in collision_findings(tmp_path) if "0010" in f.name]
    assert "0010_type_control_delta.sql" in finding.detail
    assert "0010_type_control_delta.up.sql" in finding.detail
    # Deleting the rendered twin is the intuitive fix and it is the wrong one: the next
    # `trappoint render` recreates it. The message has to say so where it is read.
    assert "next render" in finding.detail
    assert "refuses to discover" in finding.detail


def test_check_units_is_silent_on_a_clean_tree(tmp_path: Path) -> None:
    unit = Unit(name="0010_type_control_delta.sql", template="t.j2", text=rendered())
    (tmp_path / unit.name).write_bytes(unit.data)
    assert check_units(result_over(tmp_path, (unit,))) == []


@pytest.mark.parametrize("suffix", [".sql", ".up.sql"])
def test_both_suffixes_are_counted_into_the_same_stem(tmp_path: Path, suffix: str) -> None:
    put(tmp_path, f"0010_type_control_delta{suffix}", rendered())
    put(tmp_path, "0010_type_control_delta.up.sql", authored())
    expected = 0 if suffix == ".up.sql" else 1
    assert len(stem_collisions(tmp_path)) == expected
