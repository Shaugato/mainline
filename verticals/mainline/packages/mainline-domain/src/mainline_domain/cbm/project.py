# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
"""The projector: read the three relations, propose an account, compare.

WHAT THIS PROCESS IS ALLOWED TO DECIDE: NOTHING
-----------------------------------------------
``mainline.fn_cbm_account_guard`` (migration ``0140a``) overwrites all six
counters this module computes.  The values sent by :func:`insert_account` are
therefore *discarded unread by the gate*, and that is not a wasted round trip —
it is the mechanism.  Sending numbers that the database then replaces is what
turns "the projector says the account balances" into "the account balances".

The differential in
``tests/integration/algorithms/cbm/test_differential_200.py`` is the point of the
module: it inserts the client's proposal, reads back what the trigger stored, and
requires the two to be equal on 200 fixture commits.  They are computed by
different code along different paths — the database classifies each ancestor with
five mutually exclusive SQL ``FILTER`` predicates in one aggregate, this module
classifies with :func:`mainline_domain.cbm.account.classify`'s ``if``/``elif``
chain over rows — so agreement is evidence and not tautology.

WHY THE CLIENT QUERY DOES NOT FILTER ON SEVERITY
------------------------------------------------
``0140a``'s ``anc`` CTE carries ``AND c.max_severity >= 4``.  :data:`ANCESTOR_SQL`
deliberately does NOT: it returns every first-parent clause version in a touched
document together with its severity, and
:meth:`~mainline_domain.cbm.account.AncestorFacts.is_blood_bearing` applies the
threshold in Python.  Putting the same literal in both places would make the
differential test unable to see a disagreement about the threshold, which is one
of the two things most worth catching (the other being the bucket precedence).

NO DRIVER IMPORT, ON PURPOSE
----------------------------
``psycopg`` is an optional extra of this distribution (``[db]``).  Everything
here is typed against a small structural :class:`Connection` protocol, so
importing :mod:`mainline_domain.cbm` never requires a driver and the pure
arithmetic stays testable with no cluster.
"""

from __future__ import annotations

from typing import Any, Final, Protocol
from uuid import UUID

from mainline_domain.contracts import CBMAccount

from .account import AncestorFacts, CommitFacts, derive_account
from .errors import CommitUnknown, GenerationNotDense
from .version import PROJECTOR_VERSION

__all__ = [
    "ANCESTOR_SQL",
    "CLOSURE_MISSING_SQL",
    "COMMIT_SQL",
    "Connection",
    "fetch_commit_facts",
    "insert_account",
    "next_account_gen",
    "project_commit",
    "read_account",
]


class Connection(Protocol):
    """The three-method surface this module needs from a DB-API connection."""

    def execute(self, query: str, params: Any = None, /) -> Any: ...


# --------------------------------------------------------------------------- #
# The queries.  Each one mirrors a fragment of 0140a and says which fragment.  #
# --------------------------------------------------------------------------- #

#: ``site_id`` and the FIRST PARENT, in one round trip.
#:
#: Mirrors steps 1 and 2 of ``0140a``.  ``site_id`` is read from
#: ``commit_obj`` and never from the caller for the same reason the trigger
#: re-derives it: a writer who chose the site could file a commit's accounting
#: where its auditors do not look, and RLS would then hide the account from the
#: people it indicts.
COMMIT_SQL: Final[str] = """
SELECT c.site_id,
       (SELECT e.parent_id
          FROM mainline.commit_edge e
         WHERE e.child_id = c.commit_id
           AND e.parent_ord = 0)
  FROM mainline.commit_obj c
 WHERE c.commit_id = %s
"""

#: How many first-parent clause versions in a touched document have NO closure.
#:
#: Mirrors step 4 of ``0140a``.  The count is over EVERY clause version, not
#: only the blood-bearing ones, because which ones are blood-bearing is exactly
#: what a missing closure row prevents anyone from knowing.
CLOSURE_MISSING_SQL: Final[str] = """
SELECT count(*)
  FROM mainline.clause_version pv
 WHERE pv.commit_id = %s
   AND pv.doc_id IN (SELECT DISTINCT tv.doc_id
                       FROM mainline.clause_version tv
                      WHERE tv.commit_id = %s)
   AND NOT EXISTS (SELECT 1
                     FROM mainline.clause_blame_current c
                    WHERE c.clause_uuid = pv.clause_uuid
                      AND c.as_of_commit = %s)
"""

#: One row per candidate ancestor, with the five existence facts.
#:
#: Mirrors step 5 of ``0140a`` up to — and deliberately NOT including — the
#: severity threshold and the classification.  Both of those happen in Python so
#: the differential test has something to compare.
#:
#: The two ``GROUP BY ancestor_clause_uuid`` sub-selects are what make the law a
#: law: one ancestor may hold several residue rows (the unique key includes
#: ``reason``) and several assignment rows (a split writes one per child), and
#: counting rows instead of ancestors would make the right-hand side exceed the
#: left on ordinary data.
ANCESTOR_SQL: Final[str] = """
WITH touched AS (
  SELECT DISTINCT tv.doc_id AS doc_id
    FROM mainline.clause_version tv
   WHERE tv.commit_id = %(cid)s
),
anc AS (
  SELECT DISTINCT pv.clause_uuid AS cu, c.max_severity AS sev
    FROM mainline.clause_version pv
    JOIN touched t ON t.doc_id = pv.doc_id
    JOIN mainline.clause_blame_current c
      ON c.clause_uuid = pv.clause_uuid
     AND c.as_of_commit = %(fp)s
   WHERE pv.commit_id = %(fp)s
),
res AS (
  SELECT r.ancestor_clause_uuid AS cu,
         bool_or(r.disposition_id IS NULL) AS r_open
    FROM mainline.identity_residue r
   WHERE r.commit_id = %(cid)s
   GROUP BY r.ancestor_clause_uuid
),
asg AS (
  SELECT g.ancestor_clause_uuid AS cu,
         bool_or(g.relation = 'split')   AS a_split,
         bool_or(g.relation = 'merge')   AS a_merge,
         bool_or(g.relation = 'matched') AS a_match
    FROM mainline.identity_assignment g
   WHERE g.commit_id = %(cid)s
   GROUP BY g.ancestor_clause_uuid
)
SELECT a.cu,
       a.sev,
       coalesce(r.r_open, false),
       (r.cu IS NOT NULL),
       coalesce(g.a_split, false),
       coalesce(g.a_merge, false),
       coalesce(g.a_match, false)
  FROM anc a
  LEFT JOIN res r ON r.cu = a.cu
  LEFT JOIN asg g ON g.cu = a.cu
 ORDER BY a.cu
"""

_INSERT_SQL: Final[str] = """
INSERT INTO mainline.cbm_account
  (site_id, commit_id, account_gen, inherited, carried, split_carried, merge_carried,
   residue_open, residue_disposed, computed_by, wrote_as, projector_ver)
VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
"""

_NEXT_GEN_SQL: Final[str] = """
SELECT coalesce(max(a.account_gen) + 1, 0)
  FROM mainline.cbm_account a
 WHERE a.commit_id = %s
"""

_READ_SQL: Final[str] = """
SELECT a.site_id, a.inherited, a.carried, a.split_carried, a.merge_carried,
       a.residue_open, a.residue_disposed
  FROM mainline.cbm_account a
 WHERE a.commit_id = %s
 ORDER BY a.account_gen DESC
 LIMIT 1
"""


def fetch_commit_facts(conn: Connection, commit_id: bytes) -> CommitFacts:
    """Resolve the three relations for one commit.

    :raises CommitUnknown: mirroring ``0140a``'s first refusal.  The trigger
        would raise it too; raising here means the projector finds out before it
        has built a proposal it cannot use.
    """
    row = conn.execute(COMMIT_SQL, (commit_id,)).fetchone()
    if row is None:
        raise CommitUnknown(f"commit {commit_id.hex()[:16]} is not in mainline.commit_obj")
    site_id: UUID = row[0] if isinstance(row[0], UUID) else UUID(str(row[0]))
    first_parent: bytes | None = row[1]

    if first_parent is None:
        # A root commit inherits nothing.  Every counter is 0 and the account
        # balances trivially — which is correct, not a special case being papered
        # over: a commit with no ancestry carries no obligation forward.
        return CommitFacts(
            site_id=site_id, commit_id=commit_id, first_parent=None, ancestors=(), closure_missing=0
        )

    missing_row = conn.execute(
        CLOSURE_MISSING_SQL, (first_parent, commit_id, first_parent)
    ).fetchone()
    closure_missing = int(missing_row[0]) if missing_row is not None else 0

    ancestors: list[AncestorFacts] = []
    for cu, sev, r_open, r_any, a_split, a_merge, a_match in conn.execute(
        ANCESTOR_SQL, {"cid": commit_id, "fp": first_parent}
    ).fetchall():
        ancestors.append(
            AncestorFacts(
                clause_uuid=cu if isinstance(cu, UUID) else UUID(str(cu)),
                max_ancestral_severity=int(sev),
                has_open_residue=bool(r_open),
                has_any_residue=bool(r_any),
                has_split=bool(a_split),
                has_merge=bool(a_merge),
                has_matched=bool(a_match),
            )
        )

    return CommitFacts(
        site_id=site_id,
        commit_id=commit_id,
        first_parent=first_parent,
        ancestors=tuple(ancestors),
        closure_missing=closure_missing,
    )


def project_commit(conn: Connection, commit_id: bytes) -> CBMAccount:
    """Read the relations and compute the account this projector would propose."""
    return derive_account(fetch_commit_facts(conn, commit_id))


def next_account_gen(conn: Connection, commit_id: bytes) -> int:
    """``0`` for the first account, ``previous + 1`` afterwards (MI26).

    Read from the database rather than counted in the process, because two
    projector instances racing on the same commit must not both believe they are
    generation 3.  The loser's INSERT is refused by the primary key, which is the
    correct outcome: gap-free by CAS, never by a generator (there are no
    sequences in this deployment and ``CREATE SEQUENCE`` is a CI lint failure).
    """
    row = conn.execute(_NEXT_GEN_SQL, (commit_id,)).fetchone()
    return int(row[0]) if row is not None else 0


def insert_account(
    conn: Connection,
    account: CBMAccount,
    *,
    computed_by: str,
    account_gen: int | None = None,
    projector_ver: str = PROJECTOR_VERSION,
) -> int:
    """Propose the account.  The database will overwrite every counter in it.

    ``wrote_as`` is sent as the empty-ish placeholder ``'-'`` because ``0140a``
    replaces it with ``current_user`` and the column is ``NOT NULL`` with a
    ``<> ''`` check.  Sending a real value would be sending a claim about who we
    are to a column whose entire purpose is to record who the CLUSTER thought we
    were.

    :raises GenerationNotDense: when an explicit ``account_gen`` is not the one
        the ledger expects.  Checked here so the projector gets a typed error
        instead of a ``P0001`` string, and checked AGAIN by the trigger because
        this check is a convenience and that one is the control.
    :returns: the ``account_gen`` actually used.
    """
    expected = next_account_gen(conn, account.commit_id)
    if account_gen is not None and account_gen != expected:
        raise GenerationNotDense(account_gen, expected)
    gen = expected if account_gen is None else account_gen

    conn.execute(
        _INSERT_SQL,
        (
            account.site_id,
            account.commit_id,
            gen,
            account.inherited,
            account.carried,
            account.split_carried,
            account.merge_carried,
            account.residue_open,
            account.residue_disposed,
            computed_by,
            "-",
            projector_ver,
        ),
    )
    return gen


def read_account(conn: Connection, commit_id: bytes) -> CBMAccount | None:
    """Return the NEWEST stored generation — what the gate and the audit view read.

    ``None`` when no account exists, which is the state
    ``z_cbm_gate`` refuses a merge over.
    """
    row = conn.execute(_READ_SQL, (commit_id,)).fetchone()
    if row is None:
        return None
    site = row[0] if isinstance(row[0], UUID) else UUID(str(row[0]))
    return CBMAccount(
        site_id=site,
        commit_id=commit_id,
        inherited=int(row[1]),
        carried=int(row[2]),
        split_carried=int(row[3]),
        merge_carried=int(row[4]),
        residue_open=int(row[5]),
        residue_disposed=int(row[6]),
    )
