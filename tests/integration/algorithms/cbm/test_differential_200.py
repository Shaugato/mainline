# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""The differential: the client projector and the trigger must agree, 200 times.

WHY THIS IS EVIDENCE AND NOT A TAUTOLOGY
----------------------------------------
The two derivations are different code along different paths:

* the DATABASE classifies every ancestor with five mutually exclusive SQL
  ``FILTER`` predicates inside ONE aggregate over three ``LEFT JOIN``-ed CTEs
  (``0140a``), and applies the severity threshold in the ``anc`` CTE;
* this PACKAGE fetches one row per candidate ancestor WITHOUT a severity filter
  (:data:`mainline_domain.cbm.project.ANCESTOR_SQL` deliberately omits it) and
  classifies each one with an ``if``/``elif`` chain
  (:func:`mainline_domain.cbm.account.classify`), applying the threshold in
  Python.

So the two can disagree about the threshold, about the bucket precedence, about
whether one ancestor with two residue reasons counts once or twice, and about
whether a split that wrote two assignment rows counts once or twice.  Each of
those is a real defect that has a real consequence — three of them make a gate
that opens — and each is exactly what this test would catch.

WHAT AGREEMENT PROVES, AND WHAT IT DOES NOT
-------------------------------------------
It proves the projector can predict the database.  It does NOT prove either one
is *right* about the world: both read the same three relations, and if the
matcher never wrote an assignment row for an ancestor, both will agree that the
ancestor is unaccounted.  That agreement is the account failing to balance, which
is the product working.  What CBM cannot see is blame landing on the WRONG clause
(risk R-A2), and ``novelty/cbm-ledger.yaml`` records that under ``unverified``.
"""

from __future__ import annotations

import random
import uuid
from typing import Any

import pytest
from _cbm_sql_support import SCENE_DISPOSITIONS, build_scene, insert_residue, rows
from mainline_domain.cbm import (
    fetch_commit_facts,
    insert_account,
    project_commit,
    read_account,
    unaccounted_ancestors,
)

psycopg = pytest.importorskip("psycopg")

pytestmark = [pytest.mark.schema, pytest.mark.slow]

#: 200 commits, as the exit criterion requires.  Fixed seed: a differential that
#: draws different scenes on every run cannot be argued about after it fails.
N_COMMITS = 200
SEED = 20260809

#: Severities are drawn so that both sides of the blood threshold appear often.
#: A corpus entirely at severity 5 would never exercise the ``>= 4`` filter, and
#: a corpus entirely below it would make every account trivially balanced.
SEVERITIES = (0, 2, 3, 4, 5, 5)


def _scene_plan(rng: random.Random) -> tuple[list[int], list[str]]:
    n = rng.randint(1, 5)
    severities = [rng.choice(SEVERITIES) for _ in range(n)]
    dispositions = [rng.choice(SCENE_DISPOSITIONS) for _ in range(n)]
    return severities, dispositions


@pytest.mark.timeout(600)
def test_the_client_and_the_trigger_agree_on_200_fixture_commits(
    conn: Any, site_id: uuid.UUID
) -> None:
    rng = random.Random(SEED)
    compared = 0
    predicate_agreements = 0
    repaired = 0
    balanced_first_time = 0

    for index in range(N_COMMITS):
        severities, dispositions = _scene_plan(rng)
        scene = build_scene(
            conn,
            site_id=site_id,
            seed=90_000 + index,
            n_ancestors=len(severities),
            severities=severities,
            dispositions=dispositions,
        )
        commit_id = scene.child.commit_id

        proposed = project_commit(conn, commit_id)

        if proposed.balanced():
            balanced_first_time += 1
        else:
            # The client predicts a refusal.  Perform it, so the prediction is
            # tested and not merely recorded, then repair the scene the way the
            # conservation law says it must be repaired — by writing the residue
            # row that records the missing obligation — and compare on the
            # repaired facts.
            with pytest.raises(psycopg.errors.CheckViolation) as caught:
                insert_account(conn, proposed, computed_by="agent_cartographer")
            assert caught.value.diag.constraint_name == "cbm_balances"
            predicate_agreements += 1

            for orphan in unaccounted_ancestors(fetch_commit_facts(conn, commit_id)):
                insert_residue(
                    conn,
                    site_id=site_id,
                    commit=scene.child,
                    ancestor=orphan,
                    reason="unmatched",
                )
            repaired += 1
            proposed = project_commit(conn, commit_id)
            assert proposed.balanced(), (
                "writing a residue row for every unaccounted ancestor must close the account; "
                "if it does not, the buckets do not partition the ancestor set"
            )

        insert_account(conn, proposed, computed_by="agent_cartographer")
        stored = read_account(conn, commit_id)
        assert stored is not None

        assert (
            stored.inherited,
            stored.carried,
            stored.split_carried,
            stored.merge_carried,
            stored.residue_open,
            stored.residue_disposed,
        ) == (
            proposed.inherited,
            proposed.carried,
            proposed.split_carried,
            proposed.merge_carried,
            proposed.residue_open,
            proposed.residue_disposed,
        ), (
            f"client and trigger disagree on commit {commit_id.hex()[:16]} "
            f"(scene {index}, severities={severities}, dispositions={dispositions}): "
            f"client={proposed}, database={stored}"
        )
        assert stored.site_id == site_id, "site_id is projected from commit_obj, never supplied"
        compared += 1

    assert compared == N_COMMITS
    assert balanced_first_time > 0, "the corpus must contain accounts that balance as generated"
    assert predicate_agreements > 0, (
        "the corpus must contain accounts that do NOT balance — a differential over 200 "
        "always-balanced scenes never exercises the refusal at all"
    )
    assert repaired == predicate_agreements


@pytest.mark.timeout(300)
def test_re_accounting_the_same_commit_is_idempotent_and_generation_dense(
    conn: Any, site_id: uuid.UUID
) -> None:
    """MI26.  A correction is a new generation; the numbers do not drift.

    Running the projector twice over an unchanged commit must produce identical
    counters at ``account_gen`` 0 and 1.  If they differed, "the accounting
    balanced" would be a statement about when it ran.
    """
    scene = build_scene(
        conn,
        site_id=site_id,
        seed=95_001,
        n_ancestors=4,
        severities=[5, 5, 4, 2],
        dispositions=["matched", "split", "residue_disposed", "nothing"],
    )
    first = project_commit(conn, scene.child.commit_id)
    assert insert_account(conn, first, computed_by="agent_cartographer") == 0
    second = project_commit(conn, scene.child.commit_id)
    assert insert_account(conn, second, computed_by="agent_cartographer") == 1
    assert first == second

    stored = rows(
        conn,
        "SELECT account_gen, inherited, carried, split_carried, merge_carried, residue_open, "
        "residue_disposed FROM mainline.cbm_account WHERE commit_id = %s ORDER BY account_gen",
        (scene.child.commit_id,),
    )
    assert len(stored) == 2
    assert stored[0][1:] == stored[1][1:]
    assert [row[0] for row in stored] == [0, 1]


@pytest.mark.timeout(300)
def test_a_non_dense_generation_is_refused(conn: Any, site_id: uuid.UUID) -> None:
    """A projector cannot re-file an old, favourable generation over a newer one.

    The newest generation is what ``z_cbm_gate`` and ``mainline_audit.v_cbm_ledger``
    read, so a writer who could choose ``account_gen`` could choose which account
    is authoritative.
    """
    from _cbm_sql_support import GENERATION_MESSAGE
    from mainline_domain.cbm import PROJECTOR_VERSION

    scene = build_scene(
        conn,
        site_id=site_id,
        seed=95_002,
        n_ancestors=1,
        severities=[5],
        dispositions=["matched"],
    )
    insert_account(
        conn, project_commit(conn, scene.child.commit_id), computed_by="agent_cartographer"
    )

    with pytest.raises(psycopg.errors.RaiseException) as caught:
        conn.execute(
            """
            INSERT INTO mainline.cbm_account
              (site_id, commit_id, account_gen, inherited, carried, split_carried,
               merge_carried, residue_open, residue_disposed, computed_by, wrote_as,
               projector_ver)
            VALUES (%s, %s, 7, 1, 1, 0, 0, 0, 0, 'adversary', '-', %s)
            """,
            (site_id, scene.child.commit_id, PROJECTOR_VERSION),
        )
    assert caught.value.sqlstate == "P0001"
    assert GENERATION_MESSAGE in str(caught.value)
