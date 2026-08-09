# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""The tree fingerprint must be stable, and it must be sensitive — tier 0, no cluster.

The brief's requirement on the live fingerprint is that it "MUST be stable across two
consecutive computations (test it)". The live one needs a cluster; the *inputs*
fingerprint does not, and it is the half that DM-12 calls the dev/demo/prod parity gate.
Both are computed twice by construction, and this file tests the one a stranger can run.

Two failure modes, and they pull in opposite directions:

**Flicker.** A digest that moves when nothing did trains everybody to ignore the alarm.
So: CRLF versus LF, trailing whitespace, directory iteration order and a repeated root
must all leave it unchanged — or, for the repeated root, be refused outright.

**Deafness.** A digest that does not move when something did is worse than none. So: one
changed character, one moved statement, one renamed file and one *comment* edit must all
move it. The comment case is the interesting one — comments carry the ``MI:`` citation
and the ``RATIONALE:``, and a fingerprint that ignored them would report parity between
two trees that make different claims about why they exist.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from trappoint_migrate.errors import AttestationDrift, UsageError
from trappoint_migrate.fingerprint import (
    normalise,
    stable_tree_fingerprint,
    tree_fingerprint,
)

REPO_ROOT = Path(__file__).resolve().parents[3]
MAINLINE_TREE = REPO_ROOT / "verticals" / "mainline" / "db" / "migrations"

FILE_A = "-- MI: MI01\n-- I: I01\n-- COUNSEL-GATED: no\n-- RATIONALE: a.\nCREATE SCHEMA a;\n"
FILE_B = "-- MI: MI02\n-- I: I02\n-- COUNSEL-GATED: no\n-- RATIONALE: b.\nCREATE SCHEMA b;\n"


@pytest.fixture
def tree(tmp_path: Path) -> Path:
    root = tmp_path / "migrations"
    root.mkdir()
    (root / "0001_a.sql").write_text(FILE_A, encoding="utf-8")
    (root / "0002_b.sql").write_text(FILE_B, encoding="utf-8")
    return root


# ── Stability ─────────────────────────────────────────────────────────────────────────


def test_two_consecutive_computations_agree(tree: Path) -> None:
    assert tree_fingerprint([tree]).digest == tree_fingerprint([tree]).digest
    # And the stable variant, which is the one every caller should reach for, does not
    # raise — it computes it twice itself and refuses when the two disagree.
    assert stable_tree_fingerprint([tree]).digest == tree_fingerprint([tree]).digest


def test_crlf_and_lf_fingerprint_identically(tree: Path) -> None:
    """Authored on Windows, fingerprinted on Linux. A checkout must not be an alarm."""
    before = stable_tree_fingerprint([tree]).digest
    (tree / "0001_a.sql").write_bytes(FILE_A.replace("\n", "\r\n").encode("utf-8"))
    assert stable_tree_fingerprint([tree]).digest == before


def test_trailing_whitespace_is_not_a_schema_change(tree: Path) -> None:
    before = stable_tree_fingerprint([tree]).digest
    (tree / "0002_b.sql").write_text(
        FILE_B.replace("CREATE SCHEMA b;", "CREATE SCHEMA b;   ") + "\n\n\n", encoding="utf-8"
    )
    assert stable_tree_fingerprint([tree]).digest == before


def test_the_digest_does_not_depend_on_directory_iteration_order(
    tree: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Filesystems differ. The fingerprint sorts, so the filesystem cannot move it."""
    before = stable_tree_fingerprint([tree]).digest
    original = Path.rglob

    def reversed_rglob(self: Path, pattern: str) -> object:
        return sorted(original(self, pattern), reverse=True)

    monkeypatch.setattr(Path, "rglob", reversed_rglob)
    assert stable_tree_fingerprint([tree]).digest == before


# ── Sensitivity ───────────────────────────────────────────────────────────────────────


def test_one_changed_character_moves_the_digest(tree: Path) -> None:
    before = stable_tree_fingerprint([tree]).digest
    (tree / "0001_a.sql").write_text(FILE_A.replace("SCHEMA a", "SCHEMA c"), encoding="utf-8")
    assert stable_tree_fingerprint([tree]).digest != before


def test_a_comment_edit_moves_the_digest(tree: Path) -> None:
    """Comments carry the MI citation and the rationale. Ignoring them would be parity
    between two trees that make different claims about why they exist."""
    before = stable_tree_fingerprint([tree]).digest
    (tree / "0001_a.sql").write_text(FILE_A.replace("MI: MI01", "MI: MI09"), encoding="utf-8")
    assert stable_tree_fingerprint([tree]).digest != before


def test_moving_a_statement_between_two_files_moves_the_digest(tree: Path) -> None:
    """The path is hashed with the content, so a swap is not invisible."""
    before = stable_tree_fingerprint([tree]).digest
    (tree / "0001_a.sql").write_text(FILE_B, encoding="utf-8")
    (tree / "0002_b.sql").write_text(FILE_A, encoding="utf-8")
    assert stable_tree_fingerprint([tree]).digest != before


def test_renaming_a_file_moves_the_digest(tree: Path) -> None:
    before = stable_tree_fingerprint([tree]).digest
    (tree / "0002_b.sql").rename(tree / "0002_renamed.sql")
    assert stable_tree_fingerprint([tree]).digest != before


def test_deleting_a_file_moves_the_digest(tree: Path) -> None:
    before = stable_tree_fingerprint([tree]).digest
    (tree / "0002_b.sql").unlink()
    assert stable_tree_fingerprint([tree]).digest != before


# ── Refusals ──────────────────────────────────────────────────────────────────────────


def test_a_repeated_root_is_refused_rather_than_double_counted(tree: Path) -> None:
    """It would change the digest without changing the tree — the definition of a lie."""
    with pytest.raises(UsageError, match="passed twice"):
        tree_fingerprint([tree, tree])


def test_a_missing_root_is_refused_not_hashed_as_empty(tmp_path: Path) -> None:
    """'the tree is absent' must not be indistinguishable from 'the tree is empty'."""
    with pytest.raises(UsageError, match="neither a file nor a directory"):
        tree_fingerprint([tmp_path / "nothing-here"])


def test_a_flickering_tree_is_refused_and_the_culprit_is_named(
    tree: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A parity gate that flickers cannot be used as a gate, so it refuses loudly."""
    calls = {"n": 0}
    original = Path.read_text

    def mutating_read(self: Path, *_args: object, **_kwargs: object) -> str:
        text = original(self, encoding="utf-8")
        if self.name == "0002_b.sql":
            calls["n"] += 1
            return text + f"-- {calls['n']}\n"
        return text

    monkeypatch.setattr(Path, "read_text", mutating_read)
    with pytest.raises(AttestationDrift, match=re.escape("0002_b.sql")):
        stable_tree_fingerprint([tree])


# ── Normalisation, stated directly ────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("a\r\nb\r\n", "a\nb\n"),
        ("a\rb\r", "a\nb\n"),
        ("a   \nb\t\n", "a\nb\n"),
        ("a\n\n\n\n", "a\n"),
        ("", ""),
        ("   \n  \n", ""),
        ("  indented\n", "  indented\n"),
    ],
)
def test_normalisation_is_exactly_what_it_claims(raw: str, expected: str) -> None:
    assert normalise(raw) == expected


# ── The repository itself ─────────────────────────────────────────────────────────────


@pytest.mark.skipif(not MAINLINE_TREE.is_dir(), reason="the MAINLINE migration tree is absent")
def test_the_committed_tree_fingerprints_stably() -> None:
    """The gate is only a gate if it holds on the real corpus, not only on two files."""
    computed = stable_tree_fingerprint([MAINLINE_TREE])
    assert len(computed.digest) == 32
    assert len(computed.files) > 100
    assert computed.digest == stable_tree_fingerprint([MAINLINE_TREE]).digest
