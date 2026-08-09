# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""``identity_residue.max_ancestral_severity`` stops being client-supplied.

``ARCHITECTURE.md`` section 5.3 annotates the column ``PROJECTED from
clause_blame_closure (P2)``; section 5.11 lists no trigger that projects it, and
``0049_identity_residue.sql``'s own header says so plainly: *"Until band
0130-0199 lands it is client-supplied, and this file says so rather than implying
a control that does not exist yet."*  ``0140b``/``0145b`` are that band landing,
and this module is what makes the claim checkable.

WHY THE COLUMN MATTERS ENOUGH TO GUARD
--------------------------------------
It decides how hard the residue row bites.  ``mainline.clearance_legal`` has
three deliberately absent cells — ``mechanism_absent`` and ``accept_residual``
are not legal verdicts over blood-fatal ancestry — so a writer who could lower
this number could convert an undischargeable obligation into a dischargeable one
and then dispose of it.  The whole flagship claim is that a matcher failure
becomes a LOUDER gate; a self-declared severity is the one edit that makes it a
quieter one.
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest
from _cbm_sql_support import (
    NO_FIRST_PARENT_MESSAGE,
    RESIDUE_CLOSURE_MESSAGE,
    insert_clause,
    insert_clause_version,
    insert_closure,
    insert_commit,
    insert_doc,
    insert_residue,
    rows,
)

psycopg = pytest.importorskip("psycopg")

pytestmark = pytest.mark.schema


def _parent_child_clause(
    conn: Any, site_id: uuid.UUID, seed: int, *, closure_severity: int | None
) -> tuple[Any, Any, uuid.UUID]:
    """A parent commit, a child commit, and one clause versioned in both.

    ``closure_severity=None`` withholds the closure row, which is the fail-closed
    case.
    """
    parent = insert_commit(conn, site_id=site_id, label=f"res-{seed}-parent", gen=1)
    child = insert_commit(conn, site_id=site_id, label=f"res-{seed}-child", gen=2, parent=parent)
    doc_id = insert_doc(conn, site_id=site_id, doc_code=f"PROC-R{seed:05d}")
    clause_uuid = insert_clause(conn, site_id=site_id, birth=parent)
    insert_clause_version(
        conn, site_id=site_id, doc_id=doc_id, clause_uuid=clause_uuid, commit=parent
    )
    insert_clause_version(
        conn, site_id=site_id, doc_id=doc_id, clause_uuid=clause_uuid, commit=child
    )
    if closure_severity is not None:
        insert_closure(
            conn,
            site_id=site_id,
            clause_uuid=clause_uuid,
            as_of=parent,
            max_severity=closure_severity,
        )
    return parent, child, clause_uuid


def test_a_residue_whose_ancestor_has_no_closure_row_is_p0001(
    conn: Any, site_id: uuid.UUID
) -> None:
    """Fail closed.  A severity nobody has projected is not a severity of zero."""
    _, child, clause_uuid = _parent_child_clause(conn, site_id, 3001, closure_severity=None)

    with pytest.raises(psycopg.errors.RaiseException) as caught:
        insert_residue(conn, site_id=site_id, commit=child, ancestor=clause_uuid)

    assert caught.value.sqlstate == "P0001"
    assert RESIDUE_CLOSURE_MESSAGE in str(caught.value)
    assert rows(
        conn,
        "SELECT count(*) FROM mainline.identity_residue WHERE commit_id = %s",
        (child.commit_id,),
    ) == [(0,)]


def test_the_client_supplied_severity_is_overwritten_from_the_closure(
    conn: Any, site_id: uuid.UUID
) -> None:
    """The matcher declares 0; the closure says 5; the stored row says 5."""
    _, child, clause_uuid = _parent_child_clause(conn, site_id, 3002, closure_severity=5)

    insert_residue(
        conn,
        site_id=site_id,
        commit=child,
        ancestor=clause_uuid,
        max_ancestral_severity=0,
    )

    assert rows(
        conn,
        "SELECT max_ancestral_severity FROM mainline.identity_residue WHERE commit_id = %s",
        (child.commit_id,),
    ) == [(5,)]


def test_the_client_supplied_severity_survives_when_0145b_is_withheld(
    unprojected_schema: Any, site_id: uuid.UUID
) -> None:
    """The permanent red half, and the state ``0049``'s header objected to.

    ``0145b`` is the only difference between this schema and ``guarded``.  Here
    the matcher's ``0`` is stored beside a closure that says ``5``, which is
    exactly the laundering path the projection closes.
    """
    with unprojected_schema.connect() as conn:
        _, child, clause_uuid = _parent_child_clause(conn, site_id, 3003, closure_severity=5)
        insert_residue(
            conn,
            site_id=site_id,
            commit=child,
            ancestor=clause_uuid,
            max_ancestral_severity=0,
        )
        assert rows(
            conn,
            "SELECT max_ancestral_severity FROM mainline.identity_residue WHERE commit_id = %s",
            (child.commit_id,),
        ) == [(0,)], (
            "with 0145b withheld the matcher's own number must survive — if it does not, "
            "something OTHER than the projection is writing it and the guarded test proves "
            "nothing"
        )


def test_a_residue_against_a_root_commit_is_a_different_p0001(
    conn: Any, site_id: uuid.UUID
) -> None:
    """A commit with no first parent inherits nothing, so nothing can be missing.

    A distinct message rather than "no closure row", because a refusal that tells
    the writer the wrong thing costs an hour.
    """
    root = insert_commit(conn, site_id=site_id, label="res-3004-root", gen=0)
    doc_id = insert_doc(conn, site_id=site_id, doc_code="PROC-R03004")
    clause_uuid = insert_clause(conn, site_id=site_id, birth=root)
    insert_clause_version(
        conn, site_id=site_id, doc_id=doc_id, clause_uuid=clause_uuid, commit=root
    )

    with pytest.raises(psycopg.errors.RaiseException) as caught:
        insert_residue(conn, site_id=site_id, commit=root, ancestor=clause_uuid)
    assert caught.value.sqlstate == "P0001"
    assert NO_FIRST_PARENT_MESSAGE in str(caught.value)


def test_the_projection_reads_the_newest_closure_generation(conn: Any, site_id: uuid.UUID) -> None:
    """DM-9: ``mainline.clause_blame_current`` is the sole read path, and it takes
    ``max(closure_gen)``.

    One forgotten call site reads a superseded generation, and a superseded
    generation is a LOWER severity, which is a gate that opens.  Here generation 0
    says 2 and generation 1 says 5; the residue row must say 5.
    """
    parent, child, clause_uuid = _parent_child_clause(conn, site_id, 3005, closure_severity=2)
    insert_closure(
        conn,
        site_id=site_id,
        clause_uuid=clause_uuid,
        as_of=parent,
        max_severity=5,
        closure_gen=1,
    )

    insert_residue(conn, site_id=site_id, commit=child, ancestor=clause_uuid)
    assert rows(
        conn,
        "SELECT max_ancestral_severity FROM mainline.identity_residue WHERE commit_id = %s",
        (child.commit_id,),
    ) == [(5,)]


def test_a_below_blood_severity_is_projected_faithfully_and_not_rounded_up(
    conn: Any, site_id: uuid.UUID
) -> None:
    """The projection reports what the closure says; it does not editorialise.

    A residue row over routine ancestry is a housekeeping item and must be
    recorded as one.  A trigger that quietly raised every severity to 4 would make
    the gate louder, which sounds safe and is not: it would put a fatality-grade
    obligation in front of an adjudicator who then learns to click through them.
    """
    _, child, clause_uuid = _parent_child_clause(conn, site_id, 3006, closure_severity=1)
    insert_residue(
        conn, site_id=site_id, commit=child, ancestor=clause_uuid, max_ancestral_severity=5
    )
    assert rows(
        conn,
        "SELECT max_ancestral_severity FROM mainline.identity_residue WHERE commit_id = %s",
        (child.commit_id,),
    ) == [(1,)]
