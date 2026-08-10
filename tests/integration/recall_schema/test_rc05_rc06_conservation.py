# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""RC-05 and RC-06 — the two conservation laws on `recall_run`.

MI16 (`bonded_fatalities_all_blocking`) is the hard one, because it is POSITIVE: it asserts
that something must be there. Negative invariants are enforced by refusing a write; positive
ones cannot be, because the offending write is the one that never happens. The construction
that makes MI16 refusable is to hold both sides of the equation in columns, let a CHECK compare
them, and make certain that neither side is ever written by the party with the incentive —
`mainline.fn_bonded_sev5` moves the pair together from `event_bond` ⋈ `event`.

MI17 (`candidates_conserved`) is the silence conservation law: a candidate that was retrieved
and then vanished from the accounting has nowhere to go.
"""

from __future__ import annotations

import pytest

from _schema_support import (
    INSERT_RUN_SQL,
    assert_check_refusal,
    capture_refusal,
    cosign_checkpoint,
    insert_activity_node,
    insert_blocking_check,
    insert_bond,
    insert_event,
    insert_policy,
    new_uuid,
    rows,
    run_values,
)

pytestmark = pytest.mark.schema


def _anchored_policy(conn, site_id) -> str:
    cosign_checkpoint(conn, site_id=site_id, tree_size=4096)
    return insert_policy(conn, anchored_tree_size=1024)


def test_rc05_a_run_recognising_an_unblocked_fatality_is_refused(conn) -> None:
    site_id = new_uuid()
    policy = _anchored_policy(conn, site_id)

    refusal = capture_refusal(
        conn.execute,
        INSERT_RUN_SQL,
        run_values(
            run_id=new_uuid(),
            permit_id=new_uuid(),
            site_id=site_id,
            policy_version=policy,
            n_candidates=3,
            n_blocking=1,
            n_advisory=1,
            n_silenced=1,
            n_bonded_sev5=1,            # the run says it recognised a bonded fatality
            n_bonded_sev5_blocking=0,   # and did not make it blocking
        ),
    )
    assert_check_refusal(
        conn,
        refusal,
        schema="mainline_meas",
        table="recall_run",
        constraint="bonded_fatalities_all_blocking",
    )


def test_rc05b_the_database_moves_both_counters_when_a_bonded_fatality_blocks(conn) -> None:
    """MI16's maintenance half: the agent never writes either counter.

    The run opens at (0, 0) — the only pair an agent can legally supply — and the blocking check
    landing is what moves it to (1, 1), derived from `event_bond` ⋈ `event`.
    """
    site_id = new_uuid()
    policy = _anchored_policy(conn, site_id)
    run_id, permit_id = new_uuid(), new_uuid()
    conn.execute(
        INSERT_RUN_SQL,
        run_values(
            run_id=run_id, permit_id=permit_id, site_id=site_id, policy_version=policy
        ),
    )

    fatality = insert_event(conn, site_id=site_id, severity_gate=5)
    scope = insert_activity_node(conn, site_id=site_id)
    insert_bond(conn, event_id=fatality.event_id, scope_id=scope)

    insert_blocking_check(
        conn,
        permit_id=permit_id,
        site_id=site_id,
        precursor_event_id=fatality.event_id,
    )

    assert rows(
        conn,
        "SELECT n_bonded_sev5, n_bonded_sev5_blocking FROM mainline_meas.recall_run "
        "WHERE run_id = %s",
        (run_id,),
    ) == [(1, 1)], "fn_bonded_sev5 did not maintain MI16's arithmetic"


def test_rc05c_a_severity_4_precursor_does_not_move_the_bonded_counters(conn) -> None:
    """"Bonded severity-5" means both halves. A serious event is not a fatality."""
    site_id = new_uuid()
    policy = _anchored_policy(conn, site_id)
    run_id, permit_id = new_uuid(), new_uuid()
    conn.execute(
        INSERT_RUN_SQL,
        run_values(
            run_id=run_id, permit_id=permit_id, site_id=site_id, policy_version=policy
        ),
    )

    serious = insert_event(conn, site_id=site_id, severity_gate=4)
    scope = insert_activity_node(conn, site_id=site_id)
    insert_bond(conn, event_id=serious.event_id, scope_id=scope)
    insert_blocking_check(
        conn, permit_id=permit_id, site_id=site_id, precursor_event_id=serious.event_id
    )

    unbonded = insert_event(conn, site_id=site_id, severity_gate=5)  # sev-5 but NOT bonded
    insert_blocking_check(
        conn, permit_id=permit_id, site_id=site_id, precursor_event_id=unbonded.event_id
    )

    assert rows(
        conn,
        "SELECT n_bonded_sev5, n_bonded_sev5_blocking FROM mainline_meas.recall_run "
        "WHERE run_id = %s",
        (run_id,),
    ) == [(0, 0)]


def test_rc06_a_run_whose_candidates_do_not_partition_is_refused(conn) -> None:
    site_id = new_uuid()
    policy = _anchored_policy(conn, site_id)

    refusal = capture_refusal(
        conn.execute,
        INSERT_RUN_SQL,
        run_values(
            run_id=new_uuid(),
            permit_id=new_uuid(),
            site_id=site_id,
            policy_version=policy,
            n_candidates=5,      # five retrieved
            n_blocking=1,
            n_advisory=1,
            n_silenced=1,
            n_deduped=1,         # four accounted for; one candidate has nowhere to be
        ),
    )
    assert_check_refusal(
        conn,
        refusal,
        schema="mainline_meas",
        table="recall_run",
        constraint="candidates_conserved",
    )


def test_rc06b_the_conserved_partition_admits_the_honest_run(conn) -> None:
    site_id = new_uuid()
    policy = _anchored_policy(conn, site_id)
    run_id = new_uuid()
    conn.execute(
        INSERT_RUN_SQL,
        run_values(
            run_id=run_id,
            permit_id=new_uuid(),
            site_id=site_id,
            policy_version=policy,
            n_candidates=4,
            n_blocking=1,
            n_advisory=1,
            n_silenced=1,
            n_deduped=1,
        ),
    )
    assert rows(
        conn, "SELECT n_candidates FROM mainline_meas.recall_run WHERE run_id = %s", (run_id,)
    ) == [(4,)]
