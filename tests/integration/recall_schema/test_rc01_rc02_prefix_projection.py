# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""RC-01 and RC-02 — the vector-index prefix is not writable, and a parentless vector is refused.

This is the headline of the recall domain, and the failure it prevents leaves no trace anywhere
else. C-SPANN keeps a separate K-means tree per distinct prefix value, so ``(site_id, scope_id,
facet)`` chooses which tree is searched, not which rows come back. A cue filed under the wrong
prefix is not ranked lower; it is never compared against anything, by any arm, forever — and no
query errors, no constraint trips, no silence-ledger row is written, because the candidate never
existed to be silenced.

RC-01 therefore asserts more than "the trigger ran": it asserts TREE PLACEMENT, by running the
arm shape the retriever actually runs (all three prefix columns bound to literals, ORDER BY
cosine distance, LIMIT k) against both the forged prefix and the true one.
"""

from __future__ import annotations

import pytest
from _schema_support import (
    assert_trigger_refusal,
    capture_refusal,
    insert_activity_node,
    insert_coarse,
    insert_cue,
    insert_embedding,
    insert_event,
    new_uuid,
    rows,
    vector_literal,
)

pytestmark = pytest.mark.schema


def test_rc01_forged_prefix_is_rewritten_and_the_tree_placement_proves_it(conn) -> None:
    event = insert_event(conn, severity_gate=5)
    true_scope = insert_activity_node(conn, site_id=event.site_id)
    cue = insert_cue(conn, event=event, scope_id=true_scope, facet="recurrence_test")

    forged_site, forged_scope, forged_facet = new_uuid(), new_uuid(), "narrative"
    insert_embedding(
        conn,
        cue_id=cue.cue_id,
        site_id=forged_site,
        scope_id=forged_scope,
        facet=forged_facet,
    )

    stored = rows(
        conn,
        "SELECT site_id, scope_id, facet FROM mainline.event_cue_embedding WHERE cue_id = %s",
        (cue.cue_id,),
    )
    assert stored == [(cue.site_id, cue.scope_id, cue.facet)], (
        "the inserter chose the prefix; fn_cue_prefix_project did not overwrite it"
    )
    assert (forged_site, forged_scope, forged_facet) != stored[0]

    # The arm shape the retriever runs. Under the forged prefix the row is unreachable...
    query = vector_literal(1024, 1)
    unreachable = rows(
        conn,
        """
        SELECT cue_id FROM mainline.event_cue_embedding
         WHERE site_id = %s AND scope_id = %s AND facet = %s
         ORDER BY emb <=> %s::VECTOR(1024) LIMIT 12
        """,
        (forged_site, forged_scope, forged_facet, query),
    )
    assert unreachable == [], "the forged tree must be empty"

    # ...and under the prefix its parent cue names, it is the nearest neighbour of itself.
    reachable = rows(
        conn,
        """
        SELECT cue_id FROM mainline.event_cue_embedding
         WHERE site_id = %s AND scope_id = %s AND facet = %s
         ORDER BY emb <=> %s::VECTOR(1024) LIMIT 12
        """,
        (cue.site_id, cue.scope_id, cue.facet, query),
    )
    assert [r[0] for r in reachable] == [cue.cue_id], (
        "the cue is not reachable from the tree its parent names"
    )


def test_rc01b_coarse_severity_gate_is_projected_from_the_event(conn) -> None:
    """The sweep's blocking rule reads `severity_gate`; an inserter may not lower it."""
    event = insert_event(conn, severity_gate=5)
    scope = insert_activity_node(conn, site_id=event.site_id)
    cue = insert_cue(conn, event=event, scope_id=scope, facet="mechanism")
    tenant = new_uuid()

    insert_coarse(conn, cue_id=cue.cue_id, tenant_id=tenant, severity_gate=0)

    stored = rows(
        conn,
        "SELECT severity_gate FROM mainline.event_cue_coarse WHERE cue_id = %s",
        (cue.cue_id,),
    )
    assert stored == [(5,)], (
        "a fatality was downgraded to 0 by the inserter — the sweep would never block on it"
    )


def test_rc02_embedding_with_no_parent_cue_is_refused(conn) -> None:
    orphan = new_uuid()
    refusal = capture_refusal(
        insert_embedding,
        conn,
        cue_id=orphan,
        site_id=new_uuid(),
        scope_id=new_uuid(),
        facet="mechanism",
    )
    assert_trigger_refusal(
        conn,
        refusal,
        message="MAINLINE: no parent cue — cannot place a vector in a prefix tree",
        schema="mainline",
        table="event_cue_embedding",
        trigger="cue_prefix_project_embedding",
    )


def test_rc02b_coarse_with_no_parent_cue_is_refused(conn) -> None:
    orphan = new_uuid()
    refusal = capture_refusal(
        insert_coarse, conn, cue_id=orphan, tenant_id=new_uuid(), severity_gate=5
    )
    assert_trigger_refusal(
        conn,
        refusal,
        message="MAINLINE: no parent cue — cannot place a vector in a prefix tree",
        schema="mainline",
        table="event_cue_coarse",
        trigger="cue_prefix_project_coarse",
    )


def test_rc02c_the_raise_beats_the_foreign_key_deterministically(conn) -> None:
    """Both mechanisms would refuse; the observable SQLSTATE must not be a race.

    `event_cue_embedding.cue_id` is a foreign key, so a parentless row is refused twice over.
    The BEFORE INSERT trigger fires first, by construction, and that ordering is deliberate
    (ARCHITECTURE §5.11, S4): a refusal whose SQLSTATE depends on which mechanism the optimiser
    reached first is unassertable, and "no parent cue" is the better diagnosis anyway.
    """
    refusal = capture_refusal(
        insert_embedding,
        conn,
        cue_id=new_uuid(),
        site_id=new_uuid(),
        scope_id=new_uuid(),
        facet="mechanism",
    )
    assert refusal.sqlstate == "P0001", (
        f"the FK won the race and returned {refusal.sqlstate}; the refusal is no longer "
        "deterministic and the exhibit is no longer filmable"
    )
