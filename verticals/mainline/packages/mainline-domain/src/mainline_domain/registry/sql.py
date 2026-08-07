# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""A :class:`~mainline_domain.registry.source.ClauseVersionSource` over CockroachDB.

Two queries, deliberately dumb, because the resolution algorithm belongs to the
loader and not to SQL:

``ancestry(as_of)``
    a ``WITH RECURSIVE`` over ``mainline.commit_edge`` returning every reachable
    commit, including the starting one.

``registry_versions(site, doc_code)``
    every ``clause_version`` of that document joined to its ``commit_obj`` for
    the author and the signature, and to ``clause`` for the retirement pointer.

Neither query filters versions by reachability, and that is on purpose.  Pushing
the reachability join into SQL would move the decision about *which version is
in force* into a place that only runs against a live cluster, and that decision
— including its refusal to break a same-generation tie — is the part that has to
be tested exhaustively without one.  The registry document is a few hundred
clauses; the cost of reading it whole is not the constraint.

PLATFORM NOTES (v26.2)
----------------------
* ``WITH RECURSIVE`` is supported.  ``UNION`` (not ``UNION ALL``) is used so the
  walk terminates on a diamond merge without a visited-set in the query.
* No ``AS OF SYSTEM TIME``.  ``gc.ttlseconds`` is four hours on this deployment,
  so time travel cannot reach a commit from last month; the *commit DAG* is the
  long-horizon version store, which is exactly what this source reads.  A source
  built on ``AS OF SYSTEM TIME`` would work in a demo and fail in an audit.
* This module is behind the ``db`` extra and imports ``psycopg`` lazily, so the
  domain package remains importable — and the whole unit suite remains runnable
  — with no database driver installed.

UNVERIFIED ON A LIVE CLUSTER at the time of writing: the migration that creates
``mainline.commit_obj`` / ``commit_edge`` / ``clause`` / ``clause_version`` is
owned by the schema lead and had not landed.  The integration suite for this
worker applies a stand-in DDL of exactly those columns and says so in its
report; these queries are shaped against ARCHITECTURE.md §5.2 and §5.3 and have
been run against that stand-in, not against the production schema.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from .doc import DOC_CODE
from .errors import RegistrySourceError
from .source import ClauseVersionRow

__all__ = ["ANCESTRY_SQL", "REGISTRY_VERSIONS_SQL", "SqlClauseVersionSource"]

ANCESTRY_SQL = """
WITH RECURSIVE reachable(commit_id) AS (
    SELECT %(as_of)s::BYTES
  UNION
    SELECT e.parent_id
      FROM mainline.commit_edge e
      JOIN reachable r ON e.child_id = r.commit_id
)
SELECT commit_id FROM reachable
"""

REGISTRY_VERSIONS_SQL = """
SELECT cv.clause_uuid,
       cv.commit_id,
       cv.gen,
       cv.canon_text,
       cv.canon_sha256,
       co.author_sub,
       co.sig IS NOT NULL AS ratification_signed,
       c.retired_commit
  FROM mainline.clause_version cv
  JOIN mainline.doc        d  ON d.doc_id     = cv.doc_id
  JOIN mainline.commit_obj co ON co.commit_id = cv.commit_id
  JOIN mainline.clause     c  ON c.clause_uuid = cv.clause_uuid
 WHERE cv.site_id = %(site_id)s
   AND d.doc_code = %(doc_code)s
"""


@dataclass
class SqlClauseVersionSource:
    """Reads the registry document out of a live cluster.

    ``connection`` is any DB-API connection whose cursors accept ``%(name)s``
    parameters — psycopg 3 in this deployment.  It is typed loosely on purpose:
    the domain package must not import ``psycopg`` at module scope, and a
    Protocol narrow enough to be useful here would be wider than the two methods
    actually called.
    """

    connection: Any

    def ancestry(self, as_of_commit: bytes) -> frozenset[bytes]:
        """Every commit reachable from ``as_of_commit``, including it.

        Raises rather than returning an empty set when the starting commit does
        not come back, because an empty ancestry produces an empty registry,
        which abstains on everything, which blocks everything — an
        infrastructure failure wearing the costume of a policy decision.
        """
        with self.connection.cursor() as cursor:
            cursor.execute(ANCESTRY_SQL, {"as_of": as_of_commit})
            found = frozenset(bytes(row[0]) for row in cursor.fetchall())
        if as_of_commit not in found:
            # The recursive seed always yields the starting commit, so an empty
            # result means the query did not run the way this code believes it
            # did. Reporting that as "no ancestry" would produce an empty
            # registry, which abstains on everything, which blocks everything —
            # an infrastructure failure wearing the costume of a policy decision.
            raise RegistrySourceError(
                f"the ancestry walk from {as_of_commit.hex()[:12]} did not return the "
                "starting commit; the commit DAG could not be read"
            )
        return found

    def registry_versions(
        self, *, site_id: UUID, doc_code: str = DOC_CODE
    ) -> Sequence[ClauseVersionRow]:
        """Every clause version of the registry document for one site, any commit."""
        with self.connection.cursor() as cursor:
            cursor.execute(
                REGISTRY_VERSIONS_SQL,
                {"site_id": str(site_id), "doc_code": doc_code},
            )
            rows = cursor.fetchall()
        return tuple(
            ClauseVersionRow(
                clause_uuid=row[0] if isinstance(row[0], UUID) else UUID(str(row[0])),
                commit_id=bytes(row[1]),
                gen=int(row[2]),
                canon_text=str(row[3]),
                canon_sha256=bytes(row[4]),
                ratified_by_sub=str(row[5]),
                ratification_signed=bool(row[6]),
                retired_commit=None if row[7] is None else bytes(row[7]),
            )
            for row in rows
        )
