# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""``mainline.commutation_edge`` against a real CockroachDB: what it accepts and what it refuses.

PL-2 in its simplest form.  A table whose claim is *"a dependency that cannot name
its overlap is refused"* has to be shown refusing one, and the same INSERT has to
be shown succeeding when the overlap is there.  Every test in this file pairs an
accepted row with a rejected one so that "the insert failed" can never be
explained by a ``NOT NULL``, a foreign key, or a typo in the test's own SQL.

PLATFORM NOTE, MEASURED — a CockroachDB v26.2.5 ``23514`` names the **check
expression** and not the constraint::

    failed to satisfy CHECK constraint (COALESCE(array_length(footprint_overlap, 1), 0) >= 1)

where PostgreSQL names the constraint.  So these tests assert the SQLSTATE exactly
and then a distinguishing fragment of the *expression*.  Any refusal exhibit that
promises an operator a constraint NAME for a 23514 must supply the name itself;
worker W4 recorded the same measurement for ``delta_witness``.
"""

from __future__ import annotations

import uuid

import psycopg
import pytest
from _diachronic_sql_support import (
    commit_id,
    insert_clause,
    insert_clause_version,
    insert_commit,
    insert_doc,
    rows,
)
from mainline_domain.diachronic.commutation import (
    COMMUTATION_EDGE_INSERT_SQL,
    ClauseEdit,
    EditRef,
    derive_commutation_edges,
)
from mainline_domain.diachronic.footprint import Footprint
from mainline_domain.diachronic.version import FOOTPRINT_VERSION, computed_by

pytestmark = pytest.mark.schema

RAW_INSERT = """
INSERT INTO mainline.commutation_edge
  (site_id, from_commit, from_clause_uuid, to_commit, to_clause_uuid,
   footprint_overlap, computed_by, footprint_ver)
VALUES (%(site_id)s, %(from_commit)s, %(from_clause_uuid)s, %(to_commit)s, %(to_clause_uuid)s,
        %(footprint_overlap)s, %(computed_by)s, %(footprint_ver)s)
"""


class Pair:
    """Two real clause versions in two real commits, ready to be related."""

    def __init__(self, conn, site_id) -> None:
        prefix = str(site_id)[:8]
        self.site_id = site_id
        self.c1 = insert_commit(conn, site_id=site_id, label=f"{prefix}/e1", gen=1)
        self.c2 = insert_commit(conn, site_id=site_id, label=f"{prefix}/e2", gen=2)
        doc_id = insert_doc(conn, site_id=site_id, doc_code=f"PROC-{prefix}")
        self.left = insert_clause(conn, site_id=site_id, birth=self.c1)
        self.right = insert_clause(conn, site_id=site_id, birth=self.c1)
        for clause in (self.left, self.right):
            insert_clause_version(
                conn,
                site_id=site_id,
                doc_id=doc_id,
                clause_uuid=clause,
                commit=self.c1,
                parent_version=None,
            )
            insert_clause_version(
                conn,
                site_id=site_id,
                doc_id=doc_id,
                clause_uuid=clause,
                commit=self.c2,
                parent_version=self.c1.commit_id,
            )

    def edit(self, clause, commit, *tokens: str) -> ClauseEdit:
        return ClauseEdit(
            ref=EditRef(site_id=self.site_id, commit_id=commit.commit_id, clause_uuid=clause),
            footprint=Footprint(frozenset(tokens)),
        )


def _derived(pair: Pair):
    edits = [
        pair.edit(
            pair.left, pair.c1, "anchor:equipment_tag:P-101A", "param:max_operating_pressure"
        ),
        pair.edit(pair.right, pair.c2, "anchor:equipment_tag:P-101A", "param:min_ppe_level"),
    ]
    edges = derive_commutation_edges(edits)
    assert len(edges) == 1
    return edges[0]


# --------------------------------------------------------------------------- #
# The row this package actually writes                                         #
# --------------------------------------------------------------------------- #


def test_a_derived_edge_round_trips_through_the_real_insert(conn, site_id):
    pair = Pair(conn, site_id)
    edge = _derived(pair)
    conn.execute(COMMUTATION_EDGE_INSERT_SQL, edge.as_parameters())

    stored = rows(
        conn,
        """
        SELECT footprint_overlap, computed_by, footprint_ver
          FROM mainline.commutation_edge
         WHERE from_commit = %s AND from_clause_uuid = %s
           AND to_commit = %s AND to_clause_uuid = %s
        """,
        (edge.from_commit, edge.from_clause_uuid, edge.to_commit, edge.to_clause_uuid),
    )
    assert len(stored) == 1
    overlap, by, ver = stored[0]
    assert list(overlap) == ["anchor:equipment_tag:P-101A"]
    assert by == computed_by()
    assert ver == FOOTPRINT_VERSION


def test_re_deriving_the_same_pair_is_a_no_op_and_never_an_update(conn, site_id):
    """Append-only in the write path: a second derivation must not overwrite a row a
    gate may already have read."""
    pair = Pair(conn, site_id)
    edge = _derived(pair)
    conn.execute(COMMUTATION_EDGE_INSERT_SQL, edge.as_parameters())
    conn.execute(COMMUTATION_EDGE_INSERT_SQL, edge.as_parameters())
    count = rows(
        conn,
        "SELECT count(*) FROM mainline.commutation_edge WHERE from_commit = %s",
        (edge.from_commit,),
    )
    assert count[0][0] == 1


# --------------------------------------------------------------------------- #
# The three refusals                                                           #
# --------------------------------------------------------------------------- #


def test_an_edge_with_an_empty_overlap_is_refused(conn, site_id):
    """I06, as a database refusal.

    A row here asserts that a gate should widen its antecedent set; the evidence
    for that assertion is the shared tokens.  A row with an empty array asserts the
    conclusion and withholds the evidence — a declaration wearing a derivation's
    costume — and the database will not store it.

    The accepted twin below is the same INSERT with one token in the array, so
    "the insert failed" cannot be explained by anything else in the row.
    """
    pair = Pair(conn, site_id)
    edge = _derived(pair)

    empty = edge.as_parameters()
    empty["footprint_overlap"] = []
    with pytest.raises(psycopg.errors.CheckViolation) as raised:
        conn.execute(RAW_INSERT, empty)
    assert raised.value.sqlstate == "23514"
    assert "array_length(footprint_overlap" in str(raised.value)

    conn.execute(RAW_INSERT, edge.as_parameters())  # the accepted twin


def test_the_reverse_row_is_unstorable(conn, site_id):
    """Symmetry, enforced. Two rows per pair can disagree after a partial re-derivation."""
    pair = Pair(conn, site_id)
    edge = _derived(pair)
    conn.execute(RAW_INSERT, edge.as_parameters())

    reversed_row = edge.as_parameters()
    reversed_row["from_commit"], reversed_row["to_commit"] = edge.to_commit, edge.from_commit
    reversed_row["from_clause_uuid"] = str(edge.to_clause_uuid)
    reversed_row["to_clause_uuid"] = str(edge.from_clause_uuid)
    with pytest.raises(psycopg.errors.CheckViolation) as raised:
        conn.execute(RAW_INSERT, reversed_row)
    assert raised.value.sqlstate == "23514"
    assert "from_commit" in str(raised.value)


def test_a_self_edge_is_unstorable(conn, site_id):
    """Irreflexivity falls out of the strict ``<``. An edit's footprint overlaps its own."""
    pair = Pair(conn, site_id)
    edge = _derived(pair)
    self_row = edge.as_parameters()
    self_row["to_commit"] = edge.from_commit
    self_row["to_clause_uuid"] = str(edge.from_clause_uuid)
    with pytest.raises(psycopg.errors.CheckViolation) as raised:
        conn.execute(RAW_INSERT, self_row)
    assert raised.value.sqlstate == "23514"


def test_an_anonymous_derivation_is_refused(conn, site_id):
    """After the fact, an edge with no deriver is indistinguishable from a declaration."""
    pair = Pair(conn, site_id)
    edge = _derived(pair)
    for column in ("computed_by", "footprint_ver"):
        anonymous = edge.as_parameters()
        anonymous[column] = ""
        with pytest.raises(psycopg.errors.CheckViolation) as raised:
            conn.execute(RAW_INSERT, anonymous)
        assert raised.value.sqlstate == "23514"
        assert column in str(raised.value)


def test_an_edge_naming_a_version_that_does_not_exist_is_refused(conn, site_id):
    """The composite FK: a derived edge names two VERSIONS, not two clauses.

    ``0049a_delta_witness.sql`` could not take this constraint — its rows must be
    written *before* the version row and CockroachDB has no ``DEFERRABLE``.  This
    table is derived after both versions are committed, so the constraint that was
    unbuildable one file earlier is free here.
    """
    pair = Pair(conn, site_id)
    edge = _derived(pair)

    ghost = edge.as_parameters()
    ghost["to_clause_uuid"] = str(uuid.uuid4())
    with pytest.raises(psycopg.errors.ForeignKeyViolation) as raised:
        conn.execute(RAW_INSERT, ghost)
    assert raised.value.sqlstate == "23503"

    # And a clause that EXISTS but has no version at that commit is refused too,
    # which is the half a non-composite FK would have let through.
    orphan = edge.as_parameters()
    orphan["to_commit"] = commit_id(f"{site_id}/never-written")
    with pytest.raises(psycopg.errors.ForeignKeyViolation):
        conn.execute(RAW_INSERT, orphan)


def test_a_duplicate_row_without_on_conflict_is_a_primary_key_violation(conn, site_id):
    """The append-only guarantee the PK gives on its own, shown rather than assumed."""
    pair = Pair(conn, site_id)
    edge = _derived(pair)
    conn.execute(RAW_INSERT, edge.as_parameters())
    with pytest.raises(psycopg.errors.UniqueViolation) as raised:
        conn.execute(RAW_INSERT, edge.as_parameters())
    assert raised.value.sqlstate == "23505"


def test_append_only_is_not_yet_enforced_and_this_test_demonstrates_it(conn, site_id):
    """THE HONEST LIMIT, performed rather than left in a header comment.

    MI01 wants a ``BEFORE UPDATE/DELETE`` trigger calling
    ``mainline.fn_refuse_mutation``.  It belongs in the vertical trigger band
    (0145-0149), one file may carry one statement, and this worker owns neither a
    number there nor the file.  So today an owner-level UPDATE succeeds, and this
    test asserts that it does — a red test kept deliberately green-side-up, so that
    the day the trigger lands this test fails and somebody has to come and delete
    it.  That is a better reminder than a TODO.
    """
    pair = Pair(conn, site_id)
    edge = _derived(pair)
    conn.execute(RAW_INSERT, edge.as_parameters())
    conn.execute(
        """
        UPDATE mainline.commutation_edge
           SET footprint_overlap = ARRAY['param:something-else']
         WHERE from_commit = %s AND from_clause_uuid = %s
        """,
        (edge.from_commit, edge.from_clause_uuid),
    )
    stored = rows(
        conn,
        "SELECT footprint_overlap FROM mainline.commutation_edge WHERE from_commit = %s",
        (edge.from_commit,),
    )
    assert list(stored[0][0]) == ["param:something-else"], (
        "the UPDATE was refused, which means the MI01 append-only trigger has landed. "
        "Delete this test and update 0049b_commutation_edge.sql's HONEST LIMITS section "
        "and novelty/commutation-footprint.yaml's `unverified` list."
    )
