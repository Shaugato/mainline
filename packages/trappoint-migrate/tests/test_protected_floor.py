# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""DM-14 — a down migration at or below the protected floor is refused before the socket.

The ruling, in the lead's own words: *"down-migrating an append-only ledger is not a
rollback, it is destruction of evidence, and it must fail before it reaches the cluster,
not after."* The "before" is the testable half, and it is what these cases pin:

* the refusal is a **pure filesystem** operation — no DSN, no connection, nothing that
  could partially succeed;
* the floor is ``0149z``, the end of the trigger bands in ``migrations.allocation.toml``,
  so "everything through the last trigger file" is a number rather than a recollection;
* a view or policy above the floor may carry one, because dropping a view destroys no
  evidence;
* an *unnumbered* down migration is treated as below the floor, because a rollback with
  no position in the sequence has no number at which it is safe.

``discovery.discover()`` is stricter still — MR-5 removed ``.down.sql`` from the world
entirely — and the last case here asserts that too, so that the floor and the ban cannot
drift apart silently.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from trappoint_migrate.discovery import discover
from trappoint_migrate.errors import MigrationTreeInvalid
from trappoint_migrate.runner import (
    PROTECTED_FLOOR,
    assert_above_protected_floor,
    protected_floor_violations,
)

REPO_ROOT = Path(__file__).resolve().parents[3]
MAINLINE_TREE = REPO_ROOT / "verticals" / "mainline" / "db" / "migrations"

BODY = "-- MI: MI01\n-- I: I01\n-- COUNSEL-GATED: no\n-- RATIONALE: because.\nDROP TABLE t;\n"


@pytest.fixture
def tree(tmp_path: Path) -> Path:
    root = tmp_path / "migrations"
    root.mkdir()
    return root


def test_the_floor_is_the_end_of_the_trigger_bands() -> None:
    """0149z is `dm-functions-triggers`' last vertical trigger number in the allocation.

    Hard-coded here on purpose. If the allocation moves the trigger bands, this test is
    the thing that says so, and moving the floor is then a decision somebody makes rather
    than a constant that drifted.
    """
    assert PROTECTED_FLOOR == (149, "z")


@pytest.mark.parametrize(
    "name",
    [
        "0001_schema_mainline.down.sql",
        "0071_merge_record.down.sql",
        "0130_trg_permit_merge_gate.down.sql",
        "0149z_trg_last.down.sql",
    ],
)
def test_a_down_migration_at_or_below_the_floor_is_refused(tree: Path, name: str) -> None:
    (tree / name).write_text(BODY, encoding="utf-8")
    violations = protected_floor_violations(tree)
    assert len(violations) == 1
    assert "protected floor" in violations[0]
    with pytest.raises(MigrationTreeInvalid, match="before any connection is opened"):
        assert_above_protected_floor(tree)


@pytest.mark.parametrize(
    "name",
    [
        "0150_v_safe_direction_current.down.sql",
        "0180_disposition_rls.down.sql",
        "0199_exposure_receipt_fk_silence.down.sql",
    ],
)
def test_a_down_migration_above_the_floor_is_allowed_by_the_floor_rule(
    tree: Path, name: str
) -> None:
    """DM-14 permits one above the floor: dropping a view destroys no evidence."""
    (tree / name).write_text(BODY, encoding="utf-8")
    assert protected_floor_violations(tree) == []
    assert_above_protected_floor(tree)


def test_an_unnumbered_down_migration_is_treated_as_below_the_floor(tree: Path) -> None:
    """Defaulting the unknown case to 'allowed' is how a guard acquires a hole."""
    (tree / "rollback_everything.down.sql").write_text(BODY, encoding="utf-8")
    violations = protected_floor_violations(tree)
    assert len(violations) == 1
    assert "no position in the sequence" in violations[0]


def test_every_violation_is_named_at_once(tree: Path) -> None:
    for name in ("0001_a.down.sql", "0002_b.down.sql", "0003_c.down.sql"):
        (tree / name).write_text(BODY, encoding="utf-8")
    assert len(protected_floor_violations(tree)) == 3
    with pytest.raises(MigrationTreeInvalid) as excinfo:
        assert_above_protected_floor(tree)
    message = str(excinfo.value)
    for name in ("0001_a.down.sql", "0002_b.down.sql", "0003_c.down.sql"):
        assert name in message, "an operator must not have to re-run once per violation"


def test_the_check_never_opens_a_connection(tree: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The 'before it reaches the cluster' half of DM-14, asserted rather than asserted-to.

    `psycopg.connect` is replaced with a bomb. If the refusal path touched the network at
    all — to look up a version, to check bookkeeping, to do anything — this fails.
    """
    import psycopg

    def explode(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("the protected-floor check opened a connection")

    monkeypatch.setattr(psycopg, "connect", explode)
    (tree / "0001_schema.down.sql").write_text(BODY, encoding="utf-8")
    with pytest.raises(MigrationTreeInvalid):
        assert_above_protected_floor(tree)


def test_a_clean_tree_passes_and_an_absent_tree_is_not_an_error(tmp_path: Path) -> None:
    """An absent tree is a normal state on the way to K1, not a floor violation."""
    assert protected_floor_violations(tmp_path / "nothing-here") == []


def test_a_forward_migration_named_like_a_rollback_is_not_caught(tree: Path) -> None:
    """The rule is about the `.down.sql` SUFFIX, not about the word 'down' in a slug."""
    (tree / "0001_step_down_transformer.sql").write_text(BODY, encoding="utf-8")
    assert protected_floor_violations(tree) == []


def test_discovery_refuses_a_down_migration_anywhere_not_only_below_the_floor(
    tree: Path,
) -> None:
    """MR-5 is stricter than DM-14 and the two must not drift apart unnoticed.

    There is no down-migration counterpart and there never will be, so a `.down.sql`
    above the floor still makes the tree undiscoverable — the floor constant exists to
    be *stated and cited*, not to open a door.
    """
    (tree / "0199_above_the_floor.down.sql").write_text(BODY, encoding="utf-8")
    assert protected_floor_violations(tree) == []
    with pytest.raises(MigrationTreeInvalid, match="forward-only by design"):
        discover(tree)


@pytest.mark.skipif(not MAINLINE_TREE.is_dir(), reason="the MAINLINE migration tree is absent")
def test_the_committed_tree_carries_no_down_migration_at_all() -> None:
    assert protected_floor_violations(MAINLINE_TREE) == []
    assert list(MAINLINE_TREE.rglob("*.down.sql")) == []
