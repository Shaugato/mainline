# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""RC-04 — MI18: a recall runs only under an anchored, cosigned policy version.

τ decides which precursors a supervisor is shown and which become silence-ledger rows. A policy
row that can be authored, edited or back-dated after a run retro-justifies every silence in that
run with a threshold chosen in full knowledge of the outcome — with no code change, and leaving
a database that looks entirely consistent.

So the policy's commitment must have left the trust boundary before any run may cite it.
"""

from __future__ import annotations

import pytest
from _schema_support import (
    INSERT_RUN_SQL,
    assert_trigger_refusal,
    capture_refusal,
    cosign_checkpoint,
    insert_policy,
    new_uuid,
    rows,
    run_values,
)

pytestmark = pytest.mark.schema


def _insert_run(conn, *, site_id, policy_version, run_id=None):
    conn.execute(
        INSERT_RUN_SQL,
        run_values(
            run_id=run_id or new_uuid(),
            permit_id=new_uuid(),
            site_id=site_id,
            policy_version=policy_version,
        ),
    )


def test_rc04_a_run_under_an_unanchored_policy_is_refused(conn) -> None:
    site_id = new_uuid()
    cosign_checkpoint(conn, site_id=site_id, tree_size=4096)
    policy = insert_policy(conn, anchored_tree_size=None)

    refusal = capture_refusal(_insert_run, conn, site_id=site_id, policy_version=policy)
    assert_trigger_refusal(
        conn,
        refusal,
        message="MAINLINE: recall policy is not anchored — a run may not cite an unanchored τ",
        schema="mainline_meas",
        table="recall_run",
        trigger="recall_policy_anchored",
    )


def test_rc04b_an_anchor_outside_any_cosigned_checkpoint_is_refused(conn) -> None:
    """Anchored is not enough: the anchor must be INSIDE a checkpoint a witness has signed."""
    site_id = new_uuid()
    cosign_checkpoint(conn, site_id=site_id, tree_size=1000)
    policy = insert_policy(conn, anchored_tree_size=9_999_999)

    refusal = capture_refusal(_insert_run, conn, site_id=site_id, policy_version=policy)
    assert_trigger_refusal(
        conn,
        refusal,
        message="MAINLINE: recall policy anchor is not inside a cosigned checkpoint",
        schema="mainline_meas",
        table="recall_run",
        trigger="recall_policy_anchored",
    )


def test_rc04c_an_uncosigned_checkpoint_does_not_discharge_the_anchor(conn) -> None:
    """A checkpoint we signed ourselves is a checksum in a database the adversary owns."""
    site_id = new_uuid()
    conn.execute(
        """
        INSERT INTO mainline.ledger_checkpoint
          (site_code, tree_size, root_hash, body, beacon, log_sig, canon_src_sha256, admissible)
        VALUES (%s, 4096, x'00', 'body', '{}'::JSONB, x'00', x'00', true)
        """,
        (str(site_id),),
    )
    policy = insert_policy(conn, anchored_tree_size=1024)

    refusal = capture_refusal(_insert_run, conn, site_id=site_id, policy_version=policy)
    assert refusal.sqlstate == "P0001"
    assert "not inside a cosigned checkpoint" in refusal.message


def test_rc04d_an_anchored_cosigned_policy_admits_the_run(conn) -> None:
    """The positive case, because a gate that refuses everything is not a gate."""
    site_id = new_uuid()
    cosign_checkpoint(conn, site_id=site_id, tree_size=4096)
    policy = insert_policy(conn, anchored_tree_size=1024)
    run_id = new_uuid()

    _insert_run(conn, site_id=site_id, policy_version=policy, run_id=run_id)

    assert rows(
        conn,
        "SELECT count(*) FROM mainline_meas.recall_run WHERE run_id = %s",
        (run_id,),
    ) == [(1,)]
