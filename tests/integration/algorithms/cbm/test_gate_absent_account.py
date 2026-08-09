# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""The exit criterion: a merge citing an unaccounted commit is ``P0001``.

    MAINLINE: merge refused — blame accounting absent for a cited commit
    MAINLINE: merge refused — blame accounting is stale for a cited commit

Both messages are pinned as literals in ``_cbm_sql_support`` and compared against
the string a live cluster raises.  Reading the string out of the migration and
comparing it with itself would pass for any string, including an empty one.

PL-2's permanent red half here is ``ungated_schema``, which withholds ``0145c``
and ``0145d`` and nothing else: the identical ``UPDATE … SET state = 'merged'``
succeeds there.  Without that pair, "the merge was refused" is equally consistent
with the permit's own ``merge_evidence`` CHECK, with a state-machine constraint,
or with a typo in the test's own SQL.
"""

from __future__ import annotations

import hashlib
import uuid
from typing import Any

import pytest
from _cbm_sql_support import (
    ABSENT_ACCOUNT_MESSAGE,
    STALE_ACCOUNT_MESSAGE,
    build_scene,
    insert_cr,
    insert_cr_clause,
    insert_permit,
    insert_permit_clause,
    insert_residue,
    rows,
)
from mainline_domain.cbm import insert_account, project_commit

psycopg = pytest.importorskip("psycopg")

pytestmark = pytest.mark.schema


def _merged_commit_bytes(label: str) -> bytes:
    """32 bytes — ``permit_commit_sized`` and ``cr_commit_sized`` demand exactly that."""
    return hashlib.sha256(label.encode()).digest()


def _merge_permit(conn: Any, permit_id: uuid.UUID) -> None:
    conn.execute(
        "UPDATE mainline.permit SET state = 'merged', merged_commit = %s WHERE permit_id = %s",
        (_merged_commit_bytes(str(permit_id)), permit_id),
    )


def _merge_cr(conn: Any, cr_id: uuid.UUID) -> None:
    conn.execute(
        "UPDATE mainline.change_request SET state = 'merged', merged_commit = %s WHERE cr_id = %s",
        (_merged_commit_bytes(str(cr_id)), cr_id),
    )


def _scene_and_permit(
    conn: Any, site_id: uuid.UUID, seed: int, dispositions: list[str]
) -> tuple[Any, uuid.UUID]:
    scene = build_scene(
        conn,
        site_id=site_id,
        seed=seed,
        n_ancestors=len(dispositions),
        severities=[5] * len(dispositions),
        dispositions=dispositions,
    )
    permit_id = insert_permit(conn, site_id=site_id, external_ref=f"PTW-{seed}")
    insert_permit_clause(
        conn, permit_id=permit_id, clause_uuid=scene.ancestors[0], commit=scene.child
    )
    return scene, permit_id


def test_a_merge_citing_a_commit_with_no_account_is_p0001(conn: Any, site_id: uuid.UUID) -> None:
    """The brief's exit criterion (b), performed exactly as it is written."""
    _, permit_id = _scene_and_permit(conn, site_id, 2001, ["matched"])

    with pytest.raises(psycopg.errors.RaiseException) as caught:
        _merge_permit(conn, permit_id)

    assert caught.value.sqlstate == "P0001"
    assert ABSENT_ACCOUNT_MESSAGE in str(caught.value)
    assert rows(conn, "SELECT state FROM mainline.permit WHERE permit_id = %s", (permit_id,)) == [
        ("draft",)
    ], "a refused merge must leave the subject in its prior state"


def test_the_same_merge_succeeds_when_0145c_is_withheld(
    ungated_schema: Any, site_id: uuid.UUID
) -> None:
    """The permanent red half.  Without ``z_cbm_gate`` the unaccounted merge lands.

    ``0145c``/``0145d`` are the only difference between this schema and
    ``guarded``.  If this merge were being refused by something else — the
    permit's own CHECKs, the state machine, the test's SQL — this test would fail
    and the one above would be proving nothing.
    """
    with ungated_schema.connect() as conn:
        _, permit_id = _scene_and_permit(conn, site_id, 2002, ["matched"])
        _merge_permit(conn, permit_id)
        assert rows(
            conn, "SELECT state FROM mainline.permit WHERE permit_id = %s", (permit_id,)
        ) == [("merged",)]


def test_a_merge_whose_cited_commit_is_accounted_for_is_allowed(
    conn: Any, site_id: uuid.UUID
) -> None:
    scene, permit_id = _scene_and_permit(conn, site_id, 2003, ["matched", "matched"])
    account = project_commit(conn, scene.child.commit_id)
    assert account.balanced()
    assert account.residue_open == 0
    insert_account(conn, account, computed_by="agent_cartographer")

    _merge_permit(conn, permit_id)
    assert rows(conn, "SELECT state FROM mainline.permit WHERE permit_id = %s", (permit_id,)) == [
        ("merged",)
    ]


def test_a_residue_row_written_after_the_account_makes_the_merge_stale(
    conn: Any, site_id: uuid.UUID
) -> None:
    """An accounting that was true last week and is false now is worse than none.

    It looks like evidence.  The account is append-only and describes the world at
    the moment it was written; ``z_cbm_gate`` compares its ``residue_open``
    against the live count of distinct ancestors with an open residue row, and a
    difference in EITHER direction refuses the merge.
    """
    scene, permit_id = _scene_and_permit(conn, site_id, 2004, ["matched", "matched"])
    insert_account(
        conn, project_commit(conn, scene.child.commit_id), computed_by="agent_cartographer"
    )

    insert_residue(
        conn,
        site_id=site_id,
        commit=scene.child,
        ancestor=scene.ancestors[1],
        reason="anchor_drop",
    )

    with pytest.raises(psycopg.errors.RaiseException) as caught:
        _merge_permit(conn, permit_id)
    assert caught.value.sqlstate == "P0001"
    assert STALE_ACCOUNT_MESSAGE in str(caught.value)

    # The remedy is one more account generation, and nothing else.
    refreshed = project_commit(conn, scene.child.commit_id)
    assert refreshed.residue_open == 1
    insert_account(conn, refreshed, computed_by="agent_cartographer")

    # …which does NOT open the merge, because the obligation is still open — it
    # moves the refusal to MI03, where it belongs.  This suite does not apply the
    # kernel's residue counter, so the merge succeeds here; the point being made
    # is that the CBM gate is satisfied by an account that is CURRENT, not by one
    # that is convenient.
    _merge_permit(conn, permit_id)
    assert rows(conn, "SELECT state FROM mainline.permit WHERE permit_id = %s", (permit_id,)) == [
        ("merged",)
    ]


def test_a_change_request_is_gated_on_the_same_arithmetic(conn: Any, site_id: uuid.UUID) -> None:
    """Finding S16: the repository is the protected branch, not only the permit.

    A conservation law enforced over work permits and not over document merges
    would have a documented way around it — edit the procedure instead of working
    under it.
    """
    scene = build_scene(
        conn,
        site_id=site_id,
        seed=2005,
        n_ancestors=1,
        severities=[5],
        dispositions=["matched"],
    )
    cr_id = insert_cr(conn, site_id=site_id, external_ref="CR-2005")
    insert_cr_clause(conn, cr_id=cr_id, clause_uuid=scene.ancestors[0], commit=scene.child)

    with pytest.raises(psycopg.errors.RaiseException) as caught:
        _merge_cr(conn, cr_id)
    assert caught.value.sqlstate == "P0001"
    assert ABSENT_ACCOUNT_MESSAGE in str(caught.value), (
        "the permit and the change request must refuse with the SAME words — a database that "
        "says something slightly different depending on which branch you merged is an exhibit "
        "that ends a cross-examination badly"
    )

    insert_account(
        conn, project_commit(conn, scene.child.commit_id), computed_by="agent_cartographer"
    )
    _merge_cr(conn, cr_id)
    assert rows(conn, "SELECT state FROM mainline.change_request WHERE cr_id = %s", (cr_id,)) == [
        ("merged",)
    ]


def test_an_ordinary_permit_update_does_not_run_the_gate(conn: Any, site_id: uuid.UUID) -> None:
    """The ``WHEN`` clause is what keeps the gate off every non-completing write.

    A permit that is not completing a transition has no obligation to have its
    arithmetic current, and a gate that fired on every ``under_hold`` toggle would
    be both wasteful and wrong.
    """
    _, permit_id = _scene_and_permit(conn, site_id, 2006, ["matched"])
    conn.execute("UPDATE mainline.permit SET under_hold = true WHERE permit_id = %s", (permit_id,))
    conn.execute(
        "UPDATE mainline.permit SET state = 'checks_materialised' WHERE permit_id = %s",
        (permit_id,),
    )
    assert rows(
        conn, "SELECT state, under_hold FROM mainline.permit WHERE permit_id = %s", (permit_id,)
    ) == [("checks_materialised", True)]

    # …and the completing edge from that new state is still refused.
    with pytest.raises(psycopg.errors.RaiseException):
        _merge_permit(conn, permit_id)


def test_a_permit_citing_nothing_at_all_is_not_refused_by_this_gate(
    conn: Any, site_id: uuid.UUID
) -> None:
    """Honest boundary: no cited commits means no accounting to demand.

    Recorded rather than left implicit, because it IS a hole and it is not this
    trigger's to close: a permit that declares no scope is refused by the
    boundary certificate (``unmodelled_asset_count`` / ``fn_boundary_project``,
    the kernel's and ``ex-dm-gate``'s files), not by blame arithmetic.  Claiming
    otherwise here would be claiming a mechanism this file does not contain.
    """
    permit_id = insert_permit(conn, site_id=site_id, external_ref="PTW-2007")
    _merge_permit(conn, permit_id)
    assert rows(conn, "SELECT state FROM mainline.permit WHERE permit_id = %s", (permit_id,)) == [
        ("merged",)
    ]
