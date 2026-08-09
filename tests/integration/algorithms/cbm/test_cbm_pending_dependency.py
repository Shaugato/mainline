# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""The stand-in for three not-yet-landed dependencies retires itself.

``_pending_dependency.sql`` supplies ``clause_blame_closure``,
``clause_blame_current`` and ``identity_assignment`` while no migration in the
tree creates them.  Two things must be true of that arrangement or it becomes the
kind of quiet lie this project exists to refuse:

1. it must be used ONLY for objects a real migration does not create, and
2. its retirement must be automatic and noisy, not a note in somebody's head.

This module is (2).  When ``datamodel/dm-blame`` lands ``clause_blame_closure``
and worker W8 lands ``identity_assignment``, ``stood_in_objects()`` shrinks and
these tests say so; when it reaches empty, the whole file can be deleted and
:func:`test_the_stand_in_is_gone_once_every_dependency_is_real` records that it
is time.

No cluster and no driver are needed here, deliberately: this is a fact about the
repository, not about a database.
"""

from __future__ import annotations

from _cbm_sql_support import (
    PENDING_DDL,
    PENDING_OBJECTS,
    full_stack,
    stood_in_objects,
)


def test_the_stand_in_covers_exactly_the_objects_no_migration_creates() -> None:
    """Rule (1).  It never shadows a real migration.

    If a real ``clause_blame_closure`` lands and this file still creates one, the
    stack would carry two definitions of the same object and the suite would be
    exercising whichever applied last — which is the failure mode that made the
    reconciliation ruling necessary in the first place.
    """
    missing = stood_in_objects()
    stack = [p.name for p in full_stack()]

    if missing:
        assert PENDING_DDL.name in stack, (
            f"{missing} have no migration, so the stand-in must be in the stack"
        )
        text = PENDING_DDL.read_text(encoding="utf-8")
        for _pattern, human in PENDING_OBJECTS:
            noun = human.split(" ", 1)[1]
            if human in missing:
                assert noun in text, f"{human} is missing and the stand-in does not create it"
    else:
        assert PENDING_DDL.name not in stack, (
            "every dependency is now a real migration, so the stand-in must not be applied"
        )


def test_the_stand_in_is_never_inside_the_apply_path() -> None:
    """It lives under ``tests/`` and it must stay there.

    ``verticals/mainline/db/migrations/`` is governed by MR-5's filename
    convention and by ``trappoint migrate lint``.  A hand-authored twin of
    another worker's table inside that directory is MR-1 consequence 2 — a
    zero-diff ``render --check`` staying green while the runner refuses the tree,
    which is CI green and deploy dead.
    """
    assert PENDING_DDL.parent.name == "cbm"
    assert "migrations" not in PENDING_DDL.parts[-3:], (
        f"{PENDING_DDL} has moved into an apply path; it is not a migration and must never "
        "become one"
    )
    assert not PENDING_DDL.name[0].isdigit(), (
        "a leading digit would let a careless copy into the migrations directory be discovered "
        "as a migration"
    )


def test_the_stand_in_is_gone_once_every_dependency_is_real() -> None:
    """A signpost, not a gate.  It passes in both states and says which one holds.

    This test never fails on the strength of another worker's schedule — a suite
    that went red because a dependency had not landed would be a suite that
    trains people to ignore it.  It reports, and
    :func:`test_the_stand_in_covers_exactly_the_objects_no_migration_creates` is
    the one that actually refuses the dangerous combination.
    """
    missing = stood_in_objects()
    if missing:
        print(
            "\n[cbm] STILL STOOD IN, from tests/integration/algorithms/cbm/"
            f"_pending_dependency.sql: {', '.join(missing)}.\n"
            "[cbm] These belong to datamodel/dm-blame (the closure and its view, allocation "
            "band 0032-0039) and to algorithms/margin-assignment (identity_assignment, band "
            "0049a-0049z). When they land, delete _pending_dependency.sql and this module.\n"
            "[cbm] Every cluster-backed result in this suite holds for the shapes transcribed "
            "there, and is only as true of the deployment as those transcriptions are."
        )
    else:
        print("\n[cbm] every dependency is a real migration; _pending_dependency.sql is dead code")
    assert isinstance(missing, list)
