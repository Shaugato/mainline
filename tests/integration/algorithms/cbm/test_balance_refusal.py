# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""The exit criterion: an under-emitted residue row is ``23514`` on ``cbm_balances``.

PL-2, and what "red first" means for a conservation law
-------------------------------------------------------
The first three tests in this module were written and observed FAILING before
``0049c``, ``0140a`` and ``0145a`` existed — first because the table did not
exist (``42P01``), then because nothing corrected the counters, and only then
green for the right reason.  The permanence of that redness is the
``unguarded_schema`` fixture: it withholds ``0145a`` alone, so
``fn_cbm_account_guard`` exists and nothing calls it, and the identical INSERT
that ``guarded`` refuses is accepted there with the client's own numbers intact.

MEASURED PLATFORM DETAIL THE ASSERTIONS DEPEND ON
------------------------------------------------
On CockroachDB CCL v26.2.5 a ``23514`` MESSAGE names the CHECK EXPRESSION —
``failed to satisfy CHECK constraint (balanced)`` — where PostgreSQL names the
constraint.  The constraint NAME arrives in the error's diagnostics
(``exc.diag.constraint_name == 'cbm_balances'``).  Both are asserted: the
diagnostics because that is the exhibit, and the message because a console that
renders it must not promise a name it will not receive.
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest
from _cbm_sql_support import (
    BALANCES_CONSTRAINT,
    Commit,
    build_scene,
    insert_residue,
    rows,
)
from mainline_domain.cbm import (
    PROJECTOR_VERSION,
    derive_account,
    fetch_commit_facts,
    insert_account,
    project_commit,
    read_account,
    unaccounted_ancestors,
)

psycopg = pytest.importorskip("psycopg")

pytestmark = pytest.mark.schema


_RAW_INSERT = """
INSERT INTO mainline.cbm_account
  (site_id, commit_id, account_gen, inherited, carried, split_carried, merge_carried,
   residue_open, residue_disposed, computed_by, wrote_as, projector_ver)
VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
"""


def _raw_account(
    conn: Any,
    *,
    site_id: uuid.UUID,
    commit: Commit,
    account_gen: int,
    inherited: int,
    carried: int,
    split_carried: int = 0,
    merge_carried: int = 0,
    residue_open: int = 0,
    residue_disposed: int = 0,
) -> None:
    """Insert an account with counters chosen by the caller, bypassing the projector.

    This is the adversary's statement, written the way an adversary would write
    it: numbers that make the identity close, sent straight at the table.
    """
    conn.execute(
        _RAW_INSERT,
        (
            site_id,
            commit.commit_id,
            account_gen,
            inherited,
            carried,
            split_carried,
            merge_carried,
            residue_open,
            residue_disposed,
            "adversary",
            "-",
            PROJECTOR_VERSION,
        ),
    )


def _complete_scene(conn: Any, site_id: uuid.UUID, seed: int) -> Any:
    """Three blood-bearing ancestors, each accounted for: matched, split, open residue."""
    return build_scene(
        conn,
        site_id=site_id,
        seed=seed,
        n_ancestors=3,
        severities=[5, 5, 4],
        dispositions=["matched", "split", "residue_open"],
    )


def test_a_complete_account_is_accepted_and_balances(conn: Any, site_id: uuid.UUID) -> None:
    scene = _complete_scene(conn, site_id, seed=1001)

    account = project_commit(conn, scene.child.commit_id)
    assert account.inherited == 3
    assert account.carried == 1
    assert account.split_carried == 1
    assert account.residue_open == 1
    assert account.balanced()

    insert_account(conn, account, computed_by="agent_cartographer")

    stored = read_account(conn, scene.child.commit_id)
    assert stored is not None
    assert (stored.inherited, stored.carried, stored.split_carried, stored.residue_open) == (
        3,
        1,
        1,
        1,
    )
    assert rows(
        conn,
        "SELECT balanced FROM mainline.cbm_account WHERE commit_id = %s",
        (scene.child.commit_id,),
    ) == [(True,)]


def test_deleting_one_counted_residue_row_makes_the_next_account_23514(
    conn: Any, site_id: uuid.UUID
) -> None:
    """The brief's exit criterion (a), performed exactly as it is written.

    Build a commit whose blame accounting is complete, insert the account, delete
    one ``identity_residue`` row the account counted, and re-account.  The
    ancestor that row spoke for is now in no bucket at all, so the identity is
    ``3 = 1 + 1 + 0 + 0 + 0``, and the row cannot be stored.
    """
    scene = _complete_scene(conn, site_id, seed=1002)
    insert_account(
        conn, project_commit(conn, scene.child.commit_id), computed_by="agent_cartographer"
    )

    deleted = conn.execute(
        "DELETE FROM mainline.identity_residue WHERE commit_id = %s",
        (scene.child.commit_id,),
    ).rowcount
    assert deleted == 1, "the fixture is supposed to have written exactly one residue row"

    facts = fetch_commit_facts(conn, scene.child.commit_id)
    orphaned = unaccounted_ancestors(facts)
    assert len(orphaned) == 1, "one blood-written obligation should now be accounted for by nothing"
    assert not derive_account(facts).balanced()

    with pytest.raises(psycopg.errors.CheckViolation) as caught:
        _raw_account(
            conn,
            site_id=site_id,
            commit=scene.child,
            account_gen=1,
            inherited=3,
            carried=1,
            split_carried=1,
        )

    assert caught.value.sqlstate == "23514"
    assert caught.value.diag.constraint_name == BALANCES_CONSTRAINT
    assert "balanced" in str(caught.value)


def test_the_same_re_account_is_accepted_when_0145a_is_withheld(
    unguarded_schema: Any, site_id: uuid.UUID
) -> None:
    """The permanent red half.  Without the guard, the adversary's numbers stand.

    ``0145a`` is the only difference between this schema and ``guarded``.  Here
    the same INSERT that raises ``23514`` above is ACCEPTED, because nothing
    re-derives the counters and ``1 + 1 + 0 + 0 + 0`` really does equal the
    ``inherited`` the writer chose to declare.  That is the whole of what the
    guard buys, demonstrated rather than asserted.
    """
    with unguarded_schema.connect() as conn:
        scene = _complete_scene(conn, site_id, seed=1003)
        conn.execute(
            "DELETE FROM mainline.identity_residue WHERE commit_id = %s",
            (scene.child.commit_id,),
        )
        _raw_account(
            conn,
            site_id=site_id,
            commit=scene.child,
            account_gen=0,
            inherited=2,
            carried=1,
            split_carried=1,
        )
        stored = rows(
            conn,
            "SELECT inherited, carried, split_carried, balanced FROM mainline.cbm_account "
            "WHERE commit_id = %s",
            (scene.child.commit_id,),
        )
        assert stored == [(2, 1, 1, True)], (
            "with 0145a withheld the client's own numbers must survive — if they do not, "
            "something OTHER than the guard is correcting them and the guarded test proves "
            "nothing"
        )


def test_the_two_layers_catch_two_different_lies(unguarded_schema: Any, site_id: uuid.UUID) -> None:
    """Refusal depth 2, demonstrated rather than asserted, one layer at a time.

    With ``0145a`` withheld, ``CONSTRAINT cbm_balances`` is on its own.  It still
    refuses an account whose OWN ARITHMETIC does not close — a writer cannot
    store ``inherited = 3`` beside terms summing to 2 — and that is a real,
    structural guarantee that survives ``DISABLE TRIGGER``.

    What it cannot see is an account that is arithmetically perfect and false:
    ``inherited = 2`` for a commit that really inherited 3.  Only the
    re-derivation catches that, and that is the whole of what the trigger buys.
    Both are exercised here so the depth-2 claim in ``novelty/cbm-ledger.yaml``
    names two layers that do two different things.
    """
    with unguarded_schema.connect() as conn:
        scene = _complete_scene(conn, site_id, seed=1010)
        conn.execute(
            "DELETE FROM mainline.identity_residue WHERE commit_id = %s",
            (scene.child.commit_id,),
        )

        with pytest.raises(psycopg.errors.CheckViolation) as caught:
            _raw_account(
                conn,
                site_id=site_id,
                commit=scene.child,
                account_gen=0,
                inherited=3,
                carried=1,
                split_carried=1,
            )
        assert caught.value.diag.constraint_name == BALANCES_CONSTRAINT

        # The same commit, an account that closes on its own arithmetic and lies
        # about what was inherited.  Accepted here; refused in `guarded` by
        # `test_deleting_one_counted_residue_row_makes_the_next_account_23514`.
        _raw_account(
            conn,
            site_id=site_id,
            commit=scene.child,
            account_gen=0,
            inherited=2,
            carried=1,
            split_carried=1,
        )
        assert rows(
            conn,
            "SELECT inherited FROM mainline.cbm_account WHERE commit_id = %s",
            (scene.child.commit_id,),
        ) == [(2,)]


def test_an_inflated_carried_is_silently_overwritten_and_then_refused(
    conn: Any, site_id: uuid.UUID
) -> None:
    """S1, applied to the accounting: the projector's numerator is never consulted.

    The adversary declares ``inherited = 3, carried = 3`` — an account that
    balances perfectly on its own arithmetic and asserts that every obligation was
    matched.  The trigger replaces all six counters with what the relations
    actually say (one matched, one split, one unaccounted), and the CHECK then
    refuses the corrected row.  The write is refused for the TRUE reason, not for
    the reason the writer supplied.
    """
    scene = build_scene(
        conn,
        site_id=site_id,
        seed=1004,
        n_ancestors=3,
        severities=[5, 5, 5],
        dispositions=["matched", "split", "nothing"],
    )

    with pytest.raises(psycopg.errors.CheckViolation) as caught:
        _raw_account(
            conn, site_id=site_id, commit=scene.child, account_gen=0, inherited=3, carried=3
        )
    assert caught.value.diag.constraint_name == BALANCES_CONSTRAINT

    assert rows(
        conn,
        "SELECT count(*) FROM mainline.cbm_account WHERE commit_id = %s",
        (scene.child.commit_id,),
    ) == [(0,)], "a refused account must leave no row behind"


def test_an_absent_assignment_with_no_residue_row_does_not_account_for_anything(
    conn: Any, site_id: uuid.UUID
) -> None:
    """Declaring an obligation gone is not the same as recording that it is gone.

    ``identity_assignment.relation = 'absent'`` is an assertion.  The conservation
    law says an absent ancestor must be EXPLICITLY absent *with a signed
    disposition*, and the disposition hangs off an ``identity_residue`` row.  An
    ``absent`` assignment on its own therefore classifies as nothing at all, and
    the account will not close.
    """
    scene = build_scene(
        conn,
        site_id=site_id,
        seed=1005,
        n_ancestors=2,
        severities=[5, 5],
        dispositions=["matched", "absent_only"],
    )
    account = project_commit(conn, scene.child.commit_id)
    assert account.inherited == 2
    assert account.carried == 1
    assert not account.balanced()

    with pytest.raises(psycopg.errors.CheckViolation) as caught:
        insert_account(conn, account, computed_by="agent_cartographer")
    assert caught.value.diag.constraint_name == BALANCES_CONSTRAINT

    # …and writing the residue row the law actually asks for closes it.
    insert_residue(
        conn, site_id=site_id, commit=scene.child, ancestor=scene.ancestors[1], reason="unmatched"
    )
    repaired = project_commit(conn, scene.child.commit_id)
    assert repaired.residue_open == 1
    assert repaired.balanced()
    insert_account(conn, repaired, computed_by="agent_cartographer")


def test_a_sub_blood_ancestor_is_outside_the_law_and_needs_no_account(
    conn: Any, site_id: uuid.UUID
) -> None:
    """The universe is severity >= 4.  A severity-3 ancestor is not an obligation.

    This is the boundary that decides what ``inherited`` counts, and it is worth a
    test of its own because getting it wrong in the SAFE direction (counting
    everything) would make every real commit unbalanced, and getting it wrong in
    the UNSAFE direction (counting nothing) would make every commit balance.
    """
    scene = build_scene(
        conn,
        site_id=site_id,
        seed=1006,
        n_ancestors=3,
        severities=[5, 3, 0],
        dispositions=["matched", "nothing", "nothing"],
    )
    account = project_commit(conn, scene.child.commit_id)
    assert account.inherited == 1, "only the severity-5 ancestor is blood-bearing"
    assert account.carried == 1
    assert account.balanced()
    insert_account(conn, account, computed_by="agent_cartographer")


def test_one_ancestor_with_two_open_residue_reasons_counts_once(
    conn: Any, site_id: uuid.UUID
) -> None:
    """``residue_unique`` includes ``reason``; the law counts ANCESTORS.

    A clause can be both ``ambiguous`` and ``anchor_drop`` — ``0049``'s own header
    says so at length — and counting rows would make the right-hand side exceed
    the left on a perfectly ordinary matcher output.
    """
    scene = build_scene(
        conn,
        site_id=site_id,
        seed=1007,
        n_ancestors=1,
        severities=[5],
        dispositions=["residue_two_reasons_open"],
    )
    assert rows(
        conn,
        "SELECT count(*) FROM mainline.identity_residue WHERE commit_id = %s",
        (scene.child.commit_id,),
    ) == [(2,)]

    account = project_commit(conn, scene.child.commit_id)
    assert (account.inherited, account.residue_open) == (1, 1)
    assert account.balanced()
    insert_account(conn, account, computed_by="agent_cartographer")


def test_an_open_residue_outranks_a_claimed_match(conn: Any, site_id: uuid.UUID) -> None:
    """Precedence is fail-closed: doubt beats a claim, never the other way round.

    A matcher that emits BOTH a ``matched`` assignment and an open ``ambiguous``
    residue for one ancestor has contradicted itself.  The account records the
    obligation as OPEN, which blocks, rather than as carried, which would not.
    """
    scene = build_scene(
        conn,
        site_id=site_id,
        seed=1008,
        n_ancestors=1,
        severities=[5],
        dispositions=["residue_open_and_matched"],
    )
    account = project_commit(conn, scene.child.commit_id)
    assert (account.inherited, account.residue_open, account.carried) == (1, 1, 0)
    assert account.balanced()


def test_an_update_to_a_stored_account_is_refused_outright(conn: Any, site_id: uuid.UUID) -> None:
    """The hole an INSERT-only guard leaves open, closed by ``0145e``.

    ``fn_cbm_account_guard`` fires ``BEFORE INSERT``, so an UPDATE walks past it,
    and ``cbm_balances`` only asks whether the six numbers sum correctly — which
    ``inherited = 2, carried = 1, split_carried = 1`` does, over a stored
    ``inherited = 3``, while being false.  Without ``z_cbm_account_append_only``
    every refusal in this domain is reachable around on one statement.

    Re-deriving on UPDATE instead would be worse, not better: an in-place
    correction would then SUCCEED, quietly, leaving no trace that the earlier
    account had said something different — and "the accounting was right when it
    was written and the world moved underneath it" is precisely the history this
    table exists to keep.
    """
    scene = _complete_scene(conn, site_id, seed=1011)
    insert_account(
        conn, project_commit(conn, scene.child.commit_id), computed_by="agent_cartographer"
    )

    with pytest.raises(psycopg.errors.RaiseException) as caught:
        conn.execute(
            "UPDATE mainline.cbm_account SET inherited = 2, residue_open = 0 WHERE commit_id = %s",
            (scene.child.commit_id,),
        )
    assert caught.value.sqlstate == "P0001"
    assert "MAINLINE: this table is append-only; write a new row" in str(caught.value)

    with pytest.raises(psycopg.errors.RaiseException):
        conn.execute(
            "DELETE FROM mainline.cbm_account WHERE commit_id = %s", (scene.child.commit_id,)
        )

    assert rows(
        conn,
        "SELECT inherited, residue_open FROM mainline.cbm_account WHERE commit_id = %s",
        (scene.child.commit_id,),
    ) == [(3, 1)]


def test_a_root_commit_inherits_nothing_and_balances_trivially(
    conn: Any, site_id: uuid.UUID
) -> None:
    """No first parent, no ancestry, no obligation.  Zero is the right answer here.

    Worth pinning: the same ``NULL`` first parent that makes this correct would,
    if mishandled, make EVERY commit's ``inherited`` zero — which is the single
    most damaging way this file could be wrong, and the way that would look like
    everything working.
    """
    from _cbm_sql_support import insert_clause, insert_clause_version, insert_commit, insert_doc

    root = insert_commit(conn, site_id=site_id, label="root-1009", gen=0)
    doc_id = insert_doc(conn, site_id=site_id, doc_code="PROC-01009")
    clause_uuid = insert_clause(conn, site_id=site_id, birth=root)
    insert_clause_version(
        conn, site_id=site_id, doc_id=doc_id, clause_uuid=clause_uuid, commit=root
    )

    account = project_commit(conn, root.commit_id)
    assert account.inherited == 0
    assert account.balanced()
    insert_account(conn, account, computed_by="agent_cartographer")
