# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""The unwelding suite — drop one mechanism at a time and ask what still refuses.

TRAPPOINT claims that refusal is STRUCTURALLY REDUNDANT: disable the trigger, drop the
constraint, one at a time, and the write still fails. At runtime the deterministic RAISE fires
first, so that claim cannot be observed from ordinary behaviour; this file is the only place it
is made, and it is made by machine.

It is also the only place where the claim is REFUSED. Two of the three recall welds are depth 1,
and this module asserts that fact as a characterisation test rather than leaving a reader to
assume otherwise. A structural-redundancy claim that is not true everywhere is worth exactly as
much as the list of places where it is.
"""

from __future__ import annotations

import pytest

from _schema_support import (
    INSERT_RUN_SQL,
    assert_check_refusal,
    capture_refusal,
    cosign_checkpoint,
    insert_activity_node,
    insert_cue,
    insert_embedding,
    insert_event,
    insert_policy,
    new_uuid,
    rows,
    run_values,
)

pytestmark = [pytest.mark.schema, pytest.mark.unweld]


class _Unwelded:
    """Drop a trigger for the duration of a test and put it back, whatever happens."""

    def __init__(self, conn, *, trigger: str, table: str, function: str, timing: str):
        self.conn = conn
        self.trigger = trigger
        self.table = table
        self.function = function
        self.timing = timing

    def __enter__(self):
        self.conn.execute(f"DROP TRIGGER {self.trigger} ON {self.table}")
        return self

    def __exit__(self, *exc):
        self.conn.execute(
            f"CREATE TRIGGER {self.trigger} {self.timing} ON {self.table} "
            f"FOR EACH ROW EXECUTE FUNCTION {self.function}()"
        )
        return False


def test_uw01_mi16_survives_the_loss_of_its_counter_trigger(conn) -> None:
    """DEPTH 2. Drop `bonded_sev5` and the CHECK still refuses the lying run row.

    This is the unwelding case that matters, because MI16 is the invariant the product is sold
    on. With the counter trigger gone the database can no longer MAINTAIN the arithmetic — but
    an agent that writes a run row claiming a bonded fatality it never made blocking is still
    refused, by a plain-column CHECK, for every writer, forever.
    """
    site_id = new_uuid()
    cosign_checkpoint(conn, site_id=site_id, tree_size=4096)
    policy = insert_policy(conn, anchored_tree_size=1024)

    with _Unwelded(
        conn,
        trigger="bonded_sev5",
        table="mainline.blocking_check",
        function="mainline.fn_bonded_sev5",
        timing="AFTER INSERT",
    ):
        refusal = capture_refusal(
            conn.execute,
            INSERT_RUN_SQL,
            run_values(
                run_id=new_uuid(),
                permit_id=new_uuid(),
                site_id=site_id,
                policy_version=policy,
                n_bonded_sev5=1,
                n_bonded_sev5_blocking=0,
            ),
        )
        assert_check_refusal(
            conn,
            refusal,
            schema="mainline_meas",
            table="recall_run",
            constraint="bonded_fatalities_all_blocking",
        )


def test_uw02_prefix_projection_depth_is_one(conn) -> None:
    """DEPTH 1 — asserted, not hidden.

    With `cue_prefix_project_embedding` dropped, a forged prefix is ACCEPTED: nothing else in
    §5.4's shape constrains those three columns, so the vector lands in a tree of the inserter's
    choosing and the cue becomes unreachable with no refusal anywhere.

    The available strengthening, deliberately not applied by this worker because §5.4's shape is
    shared with `dm-recall-tables` and an unrequested FK change is a cross-domain break:

        ALTER TABLE mainline.event_cue
          ADD CONSTRAINT cue_prefix_identity UNIQUE (cue_id, site_id, scope_id, facet);
        ALTER TABLE mainline.event_cue_embedding
          ADD CONSTRAINT fk_cue_prefix FOREIGN KEY (cue_id, site_id, scope_id, facet)
          REFERENCES mainline.event_cue (cue_id, site_id, scope_id, facet) ON UPDATE RESTRICT;

    which would make the forgery `23503` with no trigger in the database at all — PROJECT, PIN
    and REFUSE on the index partition rather than PROJECT alone. This test is the evidence for
    that proposal and it is expected to be INVERTED (into a refusal assertion) if it is adopted.
    """
    event = insert_event(conn, severity_gate=5)
    scope = insert_activity_node(conn, site_id=event.site_id)
    cue = insert_cue(conn, event=event, scope_id=scope, facet="recurrence_test")
    forged_scope = new_uuid()

    with _Unwelded(
        conn,
        trigger="cue_prefix_project_embedding",
        table="mainline.event_cue_embedding",
        function="mainline.fn_cue_prefix_project",
        timing="BEFORE INSERT",
    ):
        insert_embedding(
            conn,
            cue_id=cue.cue_id,
            site_id=event.site_id,
            scope_id=forged_scope,
            facet="recurrence_test",
        )
        placed = rows(
            conn,
            "SELECT scope_id FROM mainline.event_cue_embedding WHERE cue_id = %s",
            (cue.cue_id,),
        )
        assert placed == [(forged_scope,)], (
            "the forged prefix was refused after all — this weld is deeper than depth 1 and "
            "the claim in 0041/0114 must be upgraded"
        )
        conn.execute(
            "DELETE FROM mainline.event_cue_embedding WHERE cue_id = %s", (cue.cue_id,)
        )

    # Re-welded: the same forgery is rewritten again.
    insert_embedding(
        conn,
        cue_id=cue.cue_id,
        site_id=event.site_id,
        scope_id=forged_scope,
        facet="recurrence_test",
    )
    assert rows(
        conn,
        "SELECT scope_id FROM mainline.event_cue_embedding WHERE cue_id = %s",
        (cue.cue_id,),
    ) == [(scope,)]


def test_uw03_mi18_depth_is_one_but_the_foreign_key_is_structural(conn) -> None:
    """DEPTH 1 for anchoring; the FK residual is real and is asserted separately.

    `fn_recall_policy_anchored` cannot be a CHECK — the condition is a join across three tables
    and no CHECK expression may contain a subquery. So dropping it lets a run cite an unanchored
    policy. What survives is `recall_run.policy_version`'s foreign key: a run still cannot cite
    a policy that does not exist, which is `23503` with no trigger at all.
    """
    site_id = new_uuid()
    cosign_checkpoint(conn, site_id=site_id, tree_size=4096)
    unanchored = insert_policy(conn, anchored_tree_size=None)
    run_id = new_uuid()

    with _Unwelded(
        conn,
        trigger="recall_policy_anchored",
        table="mainline_meas.recall_run",
        function="mainline.fn_recall_policy_anchored",
        timing="BEFORE INSERT",
    ):
        conn.execute(
            INSERT_RUN_SQL,
            run_values(
                run_id=run_id,
                permit_id=new_uuid(),
                site_id=site_id,
                policy_version=unanchored,
            ),
        )
        assert rows(
            conn, "SELECT count(*) FROM mainline_meas.recall_run WHERE run_id = %s", (run_id,)
        ) == [(1,)], "MI18 held without its trigger — the depth claim must be upgraded"

        refusal = capture_refusal(
            conn.execute,
            INSERT_RUN_SQL,
            run_values(
                run_id=new_uuid(),
                permit_id=new_uuid(),
                site_id=site_id,
                policy_version="rp-does-not-exist",
            ),
        )
        assert refusal.sqlstate == "23503", (
            f"the FK residual is gone too: {refusal.sqlstate} {refusal.message}"
        )

    # Re-welded: the unanchored policy is refused again.
    refusal = capture_refusal(
        conn.execute,
        INSERT_RUN_SQL,
        run_values(
            run_id=new_uuid(),
            permit_id=new_uuid(),
            site_id=site_id,
            policy_version=unanchored,
        ),
    )
    assert refusal.sqlstate == "P0001"
    assert "is not anchored" in refusal.message


def test_uw04_candidate_projection_depth_is_one(conn) -> None:
    """DEPTH 1. With `candidate_project` dropped, a forged severity stands.

    Recorded for the same reason as UW-02: the structural-redundancy claim is made only where
    it is true. The residual here is `candidate_sev_range` (0-5), which refuses nonsense but not
    a plausible lie — and a plausible lie is the whole threat model.
    """
    site_id = new_uuid()
    cosign_checkpoint(conn, site_id=site_id, tree_size=4096)
    policy = insert_policy(conn, anchored_tree_size=1024)
    run_id = new_uuid()
    conn.execute(
        INSERT_RUN_SQL,
        run_values(
            run_id=run_id,
            permit_id=new_uuid(),
            site_id=site_id,
            policy_version=policy,
            n_candidates=1,
            n_advisory=1,
        ),
    )
    fatality = insert_event(conn, site_id=site_id, severity_gate=5)

    with _Unwelded(
        conn,
        trigger="candidate_project",
        table="mainline_meas.recall_candidate",
        function="mainline.fn_candidate_project",
        timing="BEFORE INSERT",
    ):
        conn.execute(
            """
            INSERT INTO mainline_meas.recall_candidate
              (run_id, event_id, rank, severity, features, p_relevant, tau_applied, outcome)
            VALUES (%s, %s, 1, 1, '{}'::JSONB, 0.42, 0.85, 'silenced')
            """,
            (run_id, fatality.event_id),
        )
        assert rows(
            conn,
            "SELECT severity FROM mainline_meas.recall_candidate WHERE run_id = %s",
            (run_id,),
        ) == [(1,)]

        refusal = capture_refusal(
            conn.execute,
            """
            INSERT INTO mainline_meas.recall_candidate
              (run_id, event_id, rank, severity, features, p_relevant, tau_applied, outcome)
            VALUES (%s, %s, 2, 9, '{}'::JSONB, 0.42, 0.85, 'silenced')
            """,
            (run_id, new_uuid()),
        )
        assert_check_refusal(
            conn,
            refusal,
            schema="mainline_meas",
            table="recall_candidate",
            constraint="candidate_sev_range",
        )
    # The forged row is left in place deliberately: `recall_candidate` is append-only in the
    # deployed schema (§5.11 #9), so a test that tidied up after itself would only pass while
    # that mechanism is absent. The run_id is unique to this test.
