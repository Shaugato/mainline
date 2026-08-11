# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""The canonical migration-ID selector: the cases that broke the three parsers it replaces.

Every test below is a measured failure, not a hypothetical:

* ``0114a`` crashed ``tests/integration/recall_schema/test_rc00_migration_shape.py`` with
  ``ValueError: invalid literal for int() with base 10: '0114a'`` in run 31388699452;
* ``0138a`` was *silently dropped* by ``head.isdigit()`` in the same directory's support
  module, taking the duplicate-number guard with it;
* ``0049a``-``0049z`` were *silently swallowed* by ``int(name[:4])`` in
  ``tests/integration/schema/test_mi_spine.py``, which declared a band of twelve files and
  selected eighteen — six of them belonging to ``algorithms``, not ``datamodel/dm-spine``.

The last one is the case this file exists for. A parser that raises on a name it cannot
order is only half the repair; the other half is that a *directory* containing such a name
must refuse rather than return a shorter list.
``test_a_directory_with_an_unnameable_file_raises_rather_than_skipping`` is that half, and
it is the one an ``|| true``-shaped fix would delete first.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from trappoint_migrate.ids import (
    MigrationId,
    MigrationIdInvalid,
    MigrationTreeMismatch,
    ScannedMigration,
    assert_declared_band_matches_tree,
    id_of_filename,
    parse_id,
    scan_tree,
    select_band,
)


def write(root: Path, name: str) -> Path:
    path = root / name
    path.write_text("-- MI: MI01\nCREATE TABLE t ();\n", encoding="utf-8")
    return path


# ── the parser ────────────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("0000", MigrationId(0, "")),
        ("0024", MigrationId(24, "")),
        ("0049z", MigrationId(49, "z")),
        ("0114a", MigrationId(114, "a")),
        ("0138", MigrationId(138, "")),
        ("0138a", MigrationId(138, "a")),
        ("0199z", MigrationId(199, "z")),
    ],
)
def test_the_shapes_mr5_allows_parse_to_a_pair(text: str, expected: MigrationId) -> None:
    """Four digits and at most one lowercase letter. `0000` is a key, not a falsy nothing."""
    assert parse_id(text) == expected


def test_zero_is_a_key_and_not_a_falsy_absence() -> None:
    """`MigrationId(0, "")` is falsy under no rule this module writes, and that is deliberate.

    A selector that tested `if key:` rather than `if key is None:` would drop `0000`, and a
    parser that returned `0` as its "not found" sentinel would make `0000` indistinguishable
    from a failure. This module has no sentinel at all, which is why neither is possible.
    """
    key = parse_id("0000")
    assert key.number == 0
    assert key.suffix == ""
    assert str(key) == "0000"


@pytest.mark.parametrize(
    ("text", "because"),
    [
        ("0138A", "an uppercase letter"),
        ("0138ab", "more than one lowercase letter"),
        ("12345", "more than four digits"),
        ("138", "fewer than four digits"),
        ("138a", "fewer than four digits"),
        ("", "not four digits"),
        ("0138_slug", "not four digits"),
        ("0138a_trg_cue_prefix_project_coarse.sql", "not four digits"),
        ("abcd", "not four digits"),
        ("0138-a", "not four digits"),
    ],
)
def test_a_name_this_parser_cannot_order_raises_and_says_why(text: str, because: str) -> None:
    """RAISES. Not None, not False, not -1, not a skip — the sentinel IS the defect."""
    with pytest.raises(MigrationIdInvalid) as excinfo:
        parse_id(text)
    message = str(excinfo.value)
    assert repr(text) in message, "the failure must quote the name it refused"
    assert because in message, f"the failure must diagnose {because!r}, not merely say 'invalid'"
    assert "MR-5" in message


def test_the_failure_carries_the_caller_supplied_context() -> None:
    with pytest.raises(MigrationIdInvalid, match="SPINE_BANDS"):
        parse_id("0031zz", where="SPINE_BANDS")


# ── ordering ──────────────────────────────────────────────────────────────────────────────────


def test_the_suffix_sorts_between_its_number_and_the_next() -> None:
    """`0138 < 0138a < 0139` — the whole mechanism behind MR-5's band overflow (ruling D7)."""
    assert parse_id("0138") < parse_id("0138a") < parse_id("0139")


def test_the_letter_space_of_a_number_sorts_in_alphabetical_order() -> None:
    keys = [parse_id(t) for t in ("0049z", "0049", "0049d", "0049a", "0050", "0049y")]
    assert [str(k) for k in sorted(keys)] == [
        "0049",
        "0049a",
        "0049d",
        "0049y",
        "0049z",
        "0050",
    ]


def test_sorting_by_key_is_not_sorting_by_number() -> None:
    """The regression this ordering replaces: `int(name[:4])` makes 0049 and 0049a equal.

    Under an integer key the six algorithms files and dm-spine's `0049_identity_residue`
    are one indistinguishable bucket, which is exactly how a band declared as twelve files
    came to select eighteen.
    """
    names = ["0049_identity_residue", "0049a_delta_witness", "0049z_meas_mutation_result"]
    numbers = {int(name[:4]) for name in names}
    assert len(numbers) == 1, "the integer key collapses all three — this is the defect"
    keys = {parse_id(name.split("_", 1)[0]) for name in names}
    assert len(keys) == 3, "the pair key keeps them distinct"


# ── filenames ─────────────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("0024_commit_obj.sql", MigrationId(24, "")),
        ("0029a_clause_version_trgm.sql", MigrationId(29, "a")),
        ("0049z_meas_mutation_result.sql", MigrationId(49, "z")),
        ("0114a_fn_cue_coarse_project.sql", MigrationId(114, "a")),
        ("0138a_trg_cue_prefix_project_coarse.sql", MigrationId(138, "a")),
    ],
)
def test_a_real_filename_from_this_tree_yields_its_key(name: str, expected: MigrationId) -> None:
    assert id_of_filename(name) == expected
    assert id_of_filename(Path("/anywhere") / name) == expected


@pytest.mark.parametrize(
    "name",
    [
        "0031_clause_embedding.fallback.sql",  # the second dot that killed 121 files
        "0031a_clause_embedding_ann.fallback.sql",
        "0019_retention_class.up.sql",  # the twin that claims its sibling's version
        "0024_commit_obj.down.sql",  # forward-only, by construction
        "0024_CommitObj.sql",  # not a lower-snake slug
        "0024-commit-obj.sql",
        "commit_obj.sql",  # no key at all
        "README.md",
        "0138ab_two_letters.sql",
        "0138a_trg.sql.bak",
    ],
)
def test_a_filename_outside_mr5_raises_rather_than_being_skipped(name: str) -> None:
    with pytest.raises(MigrationIdInvalid) as excinfo:
        id_of_filename(name)
    assert repr(name) in str(excinfo.value)
    assert "NO SECOND DOT" in str(excinfo.value)


# ── the directory scanner ─────────────────────────────────────────────────────────────────────


def test_scan_tree_returns_every_file_keyed_and_ordered(tmp_path: Path) -> None:
    for name in (
        "0050_permit.sql",
        "0049a_delta_witness.sql",
        "0049_identity_residue.sql",
        "0049z_meas_mutation_result.sql",
    ):
        write(tmp_path, name)
    assert [str(entry.id) for entry in scan_tree(tmp_path)] == [
        "0049",
        "0049a",
        "0049z",
        "0050",
    ]


def test_an_empty_tree_is_an_empty_list_and_not_an_error(tmp_path: Path) -> None:
    """A binding whose SQL has not been rendered yet is a normal state on the way to K1."""
    assert scan_tree(tmp_path) == []


def test_a_missing_tree_is_reported_rather_than_treated_as_empty(tmp_path: Path) -> None:
    """ "There is no directory" and "the directory is empty" are different sentences."""
    with pytest.raises(MigrationTreeMismatch, match="is not a directory"):
        scan_tree(tmp_path / "nope")


def test_a_directory_with_an_unnameable_file_raises_rather_than_skipping(tmp_path: Path) -> None:
    """THE test. A shorter list is how a migration leaves the apply set without a word.

    ``0138a.isdigit()`` returning False, ``key_of_filename()`` returning None and
    ``int(name[:4])`` raising are three spellings of one question — what does the selector
    do with a name it cannot place? — and only one answer is safe. The scanner must name
    the file, and the count it would otherwise have returned must never be returned at all.
    """
    write(tmp_path, "0049_identity_residue.sql")
    write(tmp_path, "0050_permit.sql")
    stray = write(tmp_path, "0031_clause_embedding.fallback.sql")

    with pytest.raises(MigrationTreeMismatch) as excinfo:
        scan_tree(tmp_path)

    message = str(excinfo.value)
    assert stray.name in message, "the refusal must name the file it could not order"
    assert "cannot order them" in message
    assert "silently pretend they are absent" in message


def test_a_subdirectory_is_named_rather_than_walked_past(tmp_path: Path) -> None:
    write(tmp_path, "0049_identity_residue.sql")
    (tmp_path / "ext").mkdir()
    with pytest.raises(MigrationTreeMismatch, match="ext — is not a file"):
        scan_tree(tmp_path)


def test_two_files_claiming_one_key_is_a_refusal_naming_both(tmp_path: Path) -> None:
    write(tmp_path, "0049a_delta_witness.sql")
    write(tmp_path, "0049a_delta_witness_again.sql")
    with pytest.raises(MigrationTreeMismatch) as excinfo:
        scan_tree(tmp_path)
    message = str(excinfo.value)
    assert "0049a_delta_witness.sql" in message
    assert "0049a_delta_witness_again.sql" in message


# ── band selection: the endpoint rule that gave the letter space away ──────────────────────────


def _tree(tmp_path: Path) -> list[ScannedMigration]:
    for name in (
        "0047_control_series.sql",
        "0048_carriage.sql",
        "0049_identity_residue.sql",
        "0049a_delta_witness.sql",
        "0049b_commutation_edge.sql",
        "0049z_meas_mutation_result.sql",
        "0050_permit.sql",
    ):
        write(tmp_path, name)
    return scan_tree(tmp_path)


def test_a_band_ending_at_a_bare_number_stops_before_its_letter_space(tmp_path: Path) -> None:
    """``0047``-``0049`` is dm-spine's; ``0049a``-``0049z`` is the algorithms annexe.

    ``migrations.allocation.toml`` states the rule in its own header: *a `last` WITHOUT a
    letter closes at the bare number and hands that number's letter space to the next band*.
    ``int(name[:4]) <= 49`` cannot express that, which is why it took six files that were
    never dm-spine's.
    """
    selected = [entry.name for entry in select_band(_tree(tmp_path), "0047", "0049")]
    assert selected == ["0047_control_series.sql", "0048_carriage.sql", "0049_identity_residue.sql"]


def test_a_band_ending_at_z_owns_the_whole_of_its_final_number(tmp_path: Path) -> None:
    selected = [entry.name for entry in select_band(_tree(tmp_path), "0049a", "0049z")]
    assert selected == [
        "0049a_delta_witness.sql",
        "0049b_commutation_edge.sql",
        "0049z_meas_mutation_result.sql",
    ]


def test_the_two_bands_are_disjoint_and_together_cover_the_number(tmp_path: Path) -> None:
    files = _tree(tmp_path)
    spine = {e.name for e in select_band(files, "0047", "0049")}
    annexe = {e.name for e in select_band(files, "0049a", "0049z")}
    assert spine & annexe == set()
    assert len(spine | annexe) == 6  # everything but 0050


def test_a_band_that_ends_before_it_begins_is_refused_not_reported_as_empty(
    tmp_path: Path,
) -> None:
    with pytest.raises(MigrationTreeMismatch, match="ends before it begins"):
        select_band(_tree(tmp_path), "0049", "0047")


def test_a_band_endpoint_that_is_not_a_key_raises(tmp_path: Path) -> None:
    with pytest.raises(MigrationIdInvalid, match="band last"):
        select_band(_tree(tmp_path), "0047", "0049zz")


# ── the declaration check ─────────────────────────────────────────────────────────────────────


DECLARED = ("0047_control_series.sql", "0048_carriage.sql", "0049_identity_residue.sql")


def test_a_declaration_that_matches_the_tree_returns_the_paths_in_order(tmp_path: Path) -> None:
    _tree(tmp_path)
    paths = assert_declared_band_matches_tree(
        tmp_path, DECLARED, first="0047", last="0049", label="spine 0047-0049"
    )
    assert [p.name for p in paths] == list(DECLARED)
    assert all(p.is_file() for p in paths)


def test_a_file_on_disk_the_declaration_does_not_carry_is_named(tmp_path: Path) -> None:
    _tree(tmp_path)
    with pytest.raises(MigrationTreeMismatch) as excinfo:
        assert_declared_band_matches_tree(
            tmp_path,
            DECLARED,
            first="0047",
            last="0049z",  # the WRONG endpoint: it claims the algorithms annexe
            label="spine 0047-0049",
            owner="datamodel/dm-spine",
        )
    message = str(excinfo.value)
    assert "on disk, not declared" in message
    assert "0049a_delta_witness.sql" in message
    assert "0049z_meas_mutation_result.sql" in message
    assert "datamodel/dm-spine" in message
    assert "hands that number's letter space to the next band" in message


def test_a_declared_file_that_is_not_on_disk_is_named(tmp_path: Path) -> None:
    _tree(tmp_path)
    with pytest.raises(MigrationTreeMismatch) as excinfo:
        assert_declared_band_matches_tree(
            tmp_path,
            (*DECLARED, "0049c_cbm_account.sql"),
            first="0047",
            last="0049z",
            label="spine",
        )
    assert "declared, not on disk" in str(excinfo.value)
    assert "0049c_cbm_account.sql" in str(excinfo.value)


def test_a_declaration_out_of_applied_order_is_refused(tmp_path: Path) -> None:
    """Correct as a set, wrong as a sequence — which applies a consumer before its producer."""
    _tree(tmp_path)
    with pytest.raises(MigrationTreeMismatch, match="not in applied order"):
        assert_declared_band_matches_tree(
            tmp_path,
            ("0048_carriage.sql", "0047_control_series.sql", "0049_identity_residue.sql"),
            first="0047",
            last="0049",
            label="spine",
        )


def test_a_declaration_naming_one_migration_twice_is_refused(tmp_path: Path) -> None:
    _tree(tmp_path)
    with pytest.raises(MigrationTreeMismatch, match="twice"):
        assert_declared_band_matches_tree(
            tmp_path,
            ("0047_control_series.sql", "0047_control_series_again.sql"),
            first="0047",
            last="0049",
            label="spine",
        )


def test_a_declaration_entry_outside_mr5_raises_before_the_tree_is_read(tmp_path: Path) -> None:
    with pytest.raises(MigrationIdInvalid, match="declaration"):
        assert_declared_band_matches_tree(
            tmp_path / "does-not-exist",
            ("0047_control_series.fallback.sql",),
            first="0047",
            last="0049",
            label="spine",
        )


# ── the real tree ─────────────────────────────────────────────────────────────────────────────

REPO_ROOT = Path(__file__).resolve().parents[3]
MAINLINE_MIGRATIONS = REPO_ROOT / "verticals" / "mainline" / "db" / "migrations"


def test_every_file_in_the_mainline_tree_is_nameable_by_this_selector() -> None:
    """The selector and the tree agree today, and the count is stated rather than implied.

    This is the assertion that would have failed on 2026-08-08, when
    ``0031_clause_embedding.fallback.sql`` sat in the apply path — and it fails *by naming
    the file*, which the ``MigrationTreeInvalid`` raised for the whole directory did not.

    Deliberately NOT guarded by ``skipif``. A guard here would make "the vertical is not
    beside this package" and "the selector is broken" the same green, and this whole module
    is about the difference between a checker that answered and a checker that walked past.
    """
    assert MAINLINE_MIGRATIONS.is_dir(), (
        f"{MAINLINE_MIGRATIONS} is absent. This test reads the real tree on purpose: a "
        "parser proved only against tmp_path fixtures is a parser proved against names its "
        "own author chose."
    )
    entries = scan_tree(MAINLINE_MIGRATIONS)
    assert entries, "the MAINLINE migration tree is empty"
    assert [e.id for e in entries] == sorted(e.id for e in entries)
    assert len({e.id for e in entries}) == len(entries), "two files claim one key"
    suffixed = sorted(str(e.id) for e in entries if e.id.suffix)
    for expected in ("0049b", "0049z", "0114a", "0138a", "0155a", "0180a"):
        assert expected in suffixed, (
            f"{expected} is in the tree and this selector did not report it — which is the "
            "silent-drop failure this module exists to make impossible"
        )
