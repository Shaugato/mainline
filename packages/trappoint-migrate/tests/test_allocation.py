# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""The allocation file is the authority, so these are the tests that make it one.

Three properties, and the third is the one the incident of 2026-08-08 would have failed:

1. it parses;
2. its bands are contiguous and non-overlapping — one number, exactly one owner;
3. **every file actually on disk lands in exactly one band.**

Property 3 is what the pre-dispatch collision check could not do. That check compared
one side's declared number *bands* with the other side's declared *file paths*, found no
literal string in common, and reported zero collisions across twenty numbers. It was
comparing two declarations with each other. This compares a declaration against the
tree, which is the only comparison that can be wrong in a way anybody notices.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from trappoint_migrate.errors import MigrationTreeInvalid
from trappoint_migrate.lint import (
    ALLOCATION_SUFFIX,
    Allocation,
    find_allocation,
    key_of_filename,
    load_allocation,
)

REPO_ROOT = Path(__file__).resolve().parents[3]
MIGRATIONS = REPO_ROOT / "verticals" / "mainline" / "db" / "migrations"
ALLOCATION_FILE = MIGRATIONS.parent / f"{MIGRATIONS.name}{ALLOCATION_SUFFIX}"

BAND = """
[[band]]
first = "{first}"
last = "{last}"
owner = "{owner}"
mode = "{mode}"
contents = "why this band exists"
"""


def write_allocation(tmp_path: Path, *rows: tuple[str, str, str, str]) -> Path:
    path = tmp_path / f"migrations{ALLOCATION_SUFFIX}"
    body = "".join(
        BAND.format(first=first, last=last, owner=owner, mode=mode)
        for first, last, owner, mode in rows
    )
    path.write_text(body, encoding="utf-8")
    return path


@pytest.fixture(scope="module")
def allocation() -> Allocation:
    if not ALLOCATION_FILE.is_file():
        pytest.skip(f"{ALLOCATION_FILE} is not present in this checkout")
    return load_allocation(ALLOCATION_FILE)


# ── the committed allocation ────────────────────────────────────────────────────────


def test_the_committed_allocation_parses(allocation: Allocation) -> None:
    assert allocation.bands
    assert allocation.source == ALLOCATION_FILE


def test_bands_are_contiguous_and_non_overlapping(allocation: Allocation) -> None:
    # `load_allocation` refuses a gap or an overlap, so parsing is already the assertion.
    # Restated here as an explicit walk so a reader of the test knows what was checked
    # rather than trusting that the parser checked it.
    for previous, band in zip(allocation.bands, allocation.bands[1:], strict=False):
        assert previous.last_key < band.first_key, f"{previous.label} overlaps {band.label}"
        number, letter = previous.last_key
        if not letter:
            expected = (number, "a")
        elif letter == "z":
            expected = (number + 1, "")
        else:
            expected = (number, chr(ord(letter) + 1))
        assert band.first_key == expected, f"gap between {previous.label} and {band.label}"


def test_the_allocation_starts_at_0001_and_runs_to_the_end_of_the_space(
    allocation: Allocation,
) -> None:
    assert allocation.bands[0].first_key == (1, "")
    assert allocation.bands[-1].last_key == (9999, "z")


def test_every_allocated_band_is_rendered_or_authored(allocation: Allocation) -> None:
    for band in allocation.bands[:-1]:
        assert band.mode in {"rendered", "authored"}, band.label
        assert band.owner != "UNALLOCATED", band.label


def test_the_terminal_band_refuses_0200_and_above(allocation: Allocation) -> None:
    # MRR-7: a number space with no owner is exactly what produced two conventions, so
    # 0200+ is refused rather than reserved. The algorithms 0200-0219 annexe is revoked.
    terminal = allocation.bands[-1]
    assert terminal.first_key == (200, "")
    assert terminal.owner == "UNALLOCATED"
    assert terminal.mode == "unallocated"
    for number in (200, 205, 207, 211, 279):
        assert allocation.band_for((number, "")) is terminal


def test_every_band_carries_a_prose_line_and_an_owner(allocation: Allocation) -> None:
    for band in allocation.bands:
        assert band.owner.strip(), band.label
        assert len(band.contents.strip()) > 10, band.label


@pytest.mark.parametrize(
    ("number", "letter", "owner", "mode"),
    [
        # The seam the whole ruling turns on: 0001-0018 is the substrate's, rendered.
        (6, "a", "kernel/render-and-foundation", "rendered"),
        (18, "b", "kernel/render-and-foundation", "rendered"),
        # ... 0019-0020z is all that survives of dm-foundation's revoked 0001-0023 claim.
        (19, "", "datamodel/dm-foundation", "authored"),
        (20, "a", "datamodel/dm-foundation", "authored"),
        (21, "", "kernel/render-and-foundation", "rendered"),
        # The letter-suffix carve-out: bare 0049 is datamodel's, 0049a-z is algorithms'.
        (49, "", "datamodel/dm-spine", "authored"),
        (49, "a", "algorithms", "authored"),
        # The same shape one band later in section 4.
        (119, "", "kernel/merge-gate-and-core", "rendered"),
        (119, "a", "kernel/quickrefuse", "rendered"),
        # D8's extension adopted, datamodel's 0130-0199 remap revoked (MR-7).
        (114, "a", "recall", "authored"),
        (130, "", "kernel/merge-gate-and-core+quickrefuse", "rendered"),
        (150, "", "algorithms", "authored"),
        (199, "", "datamodel/dm-views-rls", "authored"),
    ],
)
def test_the_load_bearing_numbers_resolve_to_the_ruling_owner(
    allocation: Allocation, number: int, letter: str, owner: str, mode: str
) -> None:
    band = allocation.band_for((number, letter))
    assert band is not None
    assert band.owner == owner
    assert band.mode == mode


# ── the tree on disk ────────────────────────────────────────────────────────────────


def migration_names() -> list[str]:
    if not MIGRATIONS.is_dir():
        return []
    return sorted(p.name for p in MIGRATIONS.iterdir() if p.is_file() and p.name.endswith(".sql"))


def test_every_file_on_disk_lands_in_exactly_one_band(allocation: Allocation) -> None:
    names = migration_names()
    if not names:
        pytest.skip(f"{MIGRATIONS} carries no .sql files in this checkout")
    unresolved: list[str] = []
    for name in names:
        key = key_of_filename(name)
        if key is None:
            unresolved.append(name)
            continue
        covering = [b.label for b in allocation.bands if b.covers(key)]
        assert len(covering) == 1, f"{name} -> {len(covering)} band(s): {covering}"
    assert unresolved == [], (
        "these filenames carry no NNNN[a-z]_ prefix, so no band can be resolved for "
        f"them at all: {unresolved}"
    )


def test_the_allocation_is_found_from_the_migration_root(allocation: Allocation) -> None:
    found = find_allocation(MIGRATIONS)
    assert found is not None
    assert found.source == allocation.source


def test_a_tree_without_an_allocation_resolves_to_none(tmp_path: Path) -> None:
    (tmp_path / "migrations").mkdir()
    assert find_allocation(tmp_path / "migrations") is None


# ── the parser refuses what it must ─────────────────────────────────────────────────


def test_an_overlap_is_refused(tmp_path: Path) -> None:
    path = write_allocation(
        tmp_path,
        ("0001", "0010z", "kernel", "rendered"),
        ("0010", "0020z", "datamodel", "authored"),
    )
    with pytest.raises(MigrationTreeInvalid, match="overlaps"):
        load_allocation(path)


def test_a_gap_is_refused(tmp_path: Path) -> None:
    path = write_allocation(
        tmp_path,
        ("0001", "0010z", "kernel", "rendered"),
        ("0012", "0020z", "datamodel", "authored"),
    )
    with pytest.raises(MigrationTreeInvalid, match="gap"):
        load_allocation(path)


def test_a_bare_last_hands_its_letter_space_to_the_next_band(tmp_path: Path) -> None:
    # This is exactly the 0047-0049 / 0049a-0049z shape, and the reason `last` may be
    # written with or without a letter: one number split between two owners.
    path = write_allocation(
        tmp_path,
        ("0047", "0049", "datamodel/dm-spine", "authored"),
        ("0049a", "0049z", "algorithms", "authored"),
    )
    loaded = load_allocation(path)
    identity_residue = loaded.band_for((49, ""))
    delta_witness = loaded.band_for((49, "a"))
    assert identity_residue is not None
    assert delta_witness is not None
    assert identity_residue.owner == "datamodel/dm-spine"
    assert delta_witness.owner == "algorithms"


def test_an_unknown_mode_is_refused(tmp_path: Path) -> None:
    path = write_allocation(tmp_path, ("0001", "0010z", "kernel", "templated"))
    with pytest.raises(MigrationTreeInvalid, match="rendered"):
        load_allocation(path)


def test_unallocated_mode_requires_the_unallocated_owner(tmp_path: Path) -> None:
    path = write_allocation(tmp_path, ("0001", "0010z", "algorithms", "unallocated"))
    with pytest.raises(MigrationTreeInvalid, match="UNALLOCATED"):
        load_allocation(path)


def test_an_inverted_band_is_refused(tmp_path: Path) -> None:
    path = write_allocation(tmp_path, ("0020", "0010", "kernel", "rendered"))
    with pytest.raises(MigrationTreeInvalid, match="ends before it begins"):
        load_allocation(path)


def test_a_missing_key_is_refused(tmp_path: Path) -> None:
    path = tmp_path / f"migrations{ALLOCATION_SUFFIX}"
    path.write_text('[[band]]\nfirst = "0001"\nlast = "0010"\nowner = "k"\n', encoding="utf-8")
    with pytest.raises(MigrationTreeInvalid, match="missing mode, contents"):
        load_allocation(path)


def test_an_unknown_key_is_refused_so_a_typo_cannot_become_a_grant(tmp_path: Path) -> None:
    path = tmp_path / f"migrations{ALLOCATION_SUFFIX}"
    path.write_text(
        '[[band]]\nfirst = "0001"\nlast = "0010"\nowner = "k"\nmode = "rendered"\n'
        'contents = "x"\nmodes = "authored"\n',
        encoding="utf-8",
    )
    with pytest.raises(MigrationTreeInvalid, match="unknown key"):
        load_allocation(path)


def test_an_empty_allocation_authorises_nothing(tmp_path: Path) -> None:
    path = tmp_path / f"migrations{ALLOCATION_SUFFIX}"
    path.write_text("# nothing here\n", encoding="utf-8")
    with pytest.raises(MigrationTreeInvalid, match="authorises nothing"):
        load_allocation(path)


def test_broken_toml_is_refused_by_name(tmp_path: Path) -> None:
    path = tmp_path / f"migrations{ALLOCATION_SUFFIX}"
    path.write_text("[[band]\nfirst = 0001\n", encoding="utf-8")
    with pytest.raises(MigrationTreeInvalid, match="not valid TOML"):
        load_allocation(path)


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("0006a_role_migrator.sql", (6, "a")),
        ("0010_type_control_delta.sql", (10, "")),
        ("0010_type_control_delta.up.sql", (10, "")),
        ("0031_clause_embedding.fallback.sql", (31, "")),
        ("0009x_covenant_comment.sql", (9, "x")),
        ("GRANTS.yaml", None),
        ("readme.sql", None),
    ],
)
def test_key_of_filename_reads_only_the_prefix(name: str, expected: tuple[int, str] | None) -> None:
    # Deliberately answers for a badly-named file too: a file the runner refuses is
    # still a file occupying a number somebody else was granted.
    assert key_of_filename(name) == expected


def test_the_allocation_file_carries_a_reuse_header() -> None:
    if not ALLOCATION_FILE.is_file():
        pytest.skip("allocation file absent")
    head = ALLOCATION_FILE.read_text(encoding="utf-8")[:600]
    assert "SPDX-FileCopyrightText" in head
    assert "SPDX-License-Identifier" in head
    assert re.search(r"2026-08-08", head), "the header names the date the ruling was made"
