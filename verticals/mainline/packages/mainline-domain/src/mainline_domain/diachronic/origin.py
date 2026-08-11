# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""Blame-origin resolution: *which version did the incident write?*.

The one sentence this module exists to make true:

    **The delta is measured against the version the incident wrote, not against
    last week.**

For a clause ``C`` at commit ``c``, the ORIGIN is the earliest-generation version
of ``C`` at which a blame edge attached carrying severity equal to the clause's
current ``clause_blame_current.max_severity``.  Ties break to the earliest
generation and then to the lexicographically smallest ``commit_id`` — never to
whichever row the storage engine returned first, because "the origin" appears in
an exhibit and an exhibit that is not reproducible is not an exhibit.

If no such version exists the mechanism is **inert**: the origin is the parent,
:func:`~mainline_domain.diachronic.ancestral_diff.delta_of_record` collapses to
the ordinary parent diff, and nothing about a clause with no blood ancestry gets
noisier.

WHERE THE WORK HAPPENS, AND WHY IT IS NOT IN A TRIGGER
------------------------------------------------------
The candidate selection is ``mainline.v_blame_origin`` (migration ``0152``): one
view, one ``DISTINCT ON``, an explicit generation-distance bound of
:data:`~mainline_domain.diachronic.version.ORIGIN_DEPTH_BOUND`, and **no
recursion**.  It is driven off ``mainline.blame_edge``, whose rows for one clause
number in the single digits, rather than off the clause's version list, which can
number in the hundreds — so the fan-out is bounded by how much blood a clause
carries and not by how often it has been retypeset.

None of it runs inside a trigger.  The merge gate's p99 is a product requirement
(``ARCHITECTURE.md`` §12), a recursive ancestry walk in a ``BEFORE INSERT`` is the
classic way to lose it, and decision D10 forbids depending on trigger firing order
anyway.  The gate reads a projected scalar; this module is what the *projector*
runs, off the gate path.

THE FIRST-PARENT RULE, AND THE ATTACK IT CLOSES
-----------------------------------------------
Ancestry here means **first-parent** ancestry — ``mainline.commit_edge`` with
``parent_ord = 0``.  A merge commit has two parents; if the origin could be
resolved through the second one, an author could merge a bloodless branch and
have the clause's origin quietly re-parent onto it.  So the walk is
:data:`FIRST_PARENT_ANCESTRY_SQL`: one statement, one linear chain (``parent_ord =
0`` is functional, so the subgraph is a forest and the walk cannot fan out), and
an explicit ``depth <`` bound in the recursive term.

The view deliberately does **not** perform that walk — a recursive CTE inside a
view would enumerate the transitive closure of every commit in the database, which
is the opposite of bounded.  The view returns the *conservative* candidate: the
earliest blame-bearing version of the clause, from any branch.  This module then
verifies chain membership and records the answer in
:attr:`BlameOrigin.first_parent_verified`.

**A candidate that fails verification is kept, not dropped**, and that direction is
deliberate.  Dropping it would mean an unverifiable chain produces a *quieter*
delta, which hands the attacker exactly what the merge was for.  Keeping it can
only raise the force of the verdict (the delta of record is a join), so the worst
case is an adjudication, which is the correct direction of failure for this
product.  The flag is on the row so that the adjudicator can see *why*.

PLATFORM NOTES (measured against CockroachDB CCL v26.2.5)
---------------------------------------------------------
* ``DISTINCT ON`` is supported and is what ``mainline.clause_blame_current``
  itself is built from (``ARCHITECTURE.md`` §5.4).
* ``WITH RECURSIVE`` is supported.  :data:`FIRST_PARENT_ANCESTRY_SQL` uses
  ``UNION ALL`` rather than ``UNION`` because ``parent_ord = 0`` gives each commit
  at most one parent, so the walk is a path and cannot revisit a node; the depth
  counter is what terminates it, and it is explicit rather than implied.
* **No ``AS OF SYSTEM TIME``.**  ``gc.ttlseconds`` is 4500 on the target cluster
  (ground truth F2), so time travel reaches back about seventy-five minutes.  A
  blame origin is typically years old.  The commit DAG is the long-horizon version
  store and this module reads it directly.
* This module imports no database driver.  ``connection`` on
  :class:`SqlBlameOriginSource` is typed ``Any`` for the same reason
  :mod:`mainline_domain.registry.sql` does it: the domain distribution must stay
  importable, and its whole unit suite runnable, with no driver installed.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Any, Final, Literal, Protocol
from uuid import UUID

from .errors import BlameClosureAbsent
from .version import ORIGIN_DEPTH_BOUND

__all__ = [
    "FIRST_PARENT_ANCESTRY_SQL",
    "V_BLAME_ORIGIN_SQL",
    "BlameOrigin",
    "BlameOriginRow",
    "BlameOriginSource",
    "OriginState",
    "SqlBlameOriginSource",
    "first_parent_chain",
    "resolve_origin",
]

# --------------------------------------------------------------------------- #
# SQL                                                                          #
# --------------------------------------------------------------------------- #

V_BLAME_ORIGIN_SQL: Final[str] = """
SELECT clause_uuid,
       as_of_commit,
       site_id,
       as_of_gen,
       parent_version,
       max_severity,
       closure_gen,
       closure_truncated,
       origin_commit,
       origin_gen,
       origin_depth,
       origin_event,
       origin_severity,
       origin_basis,
       origin_is_parent
  FROM mainline.v_blame_origin
 WHERE clause_uuid  = %(clause_uuid)s
   AND as_of_commit = %(as_of_commit)s
"""
"""Read the origin candidate for one subject version.  Two equality predicates, both
on the view's leading columns, so the optimiser can push them into the primary
index of every table underneath.  ``tests/integration/algorithms/diachronic/
test_origin_plan.py`` asserts the plan contains no full scan of
``mainline.clause_version``."""

FIRST_PARENT_ANCESTRY_SQL: Final[str] = """
WITH RECURSIVE first_parent(commit_id, depth) AS (
      SELECT %(as_of_commit)s::BYTES, 0::INT8
    UNION ALL
      SELECT e.parent_id, fp.depth + 1
        FROM mainline.commit_edge e
        JOIN first_parent fp ON e.child_id = fp.commit_id
       WHERE e.parent_ord = 0
         AND fp.depth < %(depth_bound)s
)
SELECT commit_id, depth FROM first_parent
"""
"""Walk the first-parent chain from one commit, depth-bounded.

``parent_ord = 0`` is the mainline parent.  Restricting to it makes the edge
relation functional, so the recursion is a *path* and terminates at the root
whether or not the bound bites; the bound is there so that a cycle introduced by a
corrupt ``commit_edge`` cannot spin, and so that the statement's cost is stated
rather than inferred.

``UNION ALL`` rather than ``UNION``: with one parent per commit there are no
duplicates to eliminate, and ``UNION`` would add a distinct over every step for
nothing.  A walk over *all* parents would need ``UNION`` to survive a diamond —
:mod:`mainline_domain.registry.sql` does exactly that and says so — but that is a
different question, and answering it here would re-admit the second parent this
walk exists to exclude."""


# --------------------------------------------------------------------------- #
# Rows and verdicts                                                            #
# --------------------------------------------------------------------------- #

OriginState = Literal["resolved", "inert"]
"""``resolved`` — a blame-origin version was found.  ``inert`` — none exists, the
origin is the parent, and ORIGINDIFF adds nothing to this clause's verdict.

There is no third value.  "The closure row is missing" is not a state of the
origin; it is :class:`~mainline_domain.diachronic.errors.BlameClosureAbsent`, and
it is raised rather than represented so that no caller can pattern-match past it.
"""


@dataclass(frozen=True, slots=True)
class BlameOriginRow:
    """One row of ``mainline.v_blame_origin``, as read.

    Every ``origin_*`` field is ``None`` together: the view LEFT JOINs the blame
    edge, so a clause with a closure row and no qualifying blood produces a row
    with the subject columns populated and the origin columns empty.  That is the
    distinction :class:`~mainline_domain.diachronic.errors.BlameClosureAbsent`
    turns on — *no row at all* means the projection did not run, and a row with
    empty origin columns means the projection ran and found nothing.
    """

    clause_uuid: UUID
    as_of_commit: bytes
    site_id: UUID
    as_of_gen: int
    parent_version: bytes | None
    max_severity: int
    closure_gen: int
    closure_truncated: bool
    origin_commit: bytes | None
    origin_gen: int | None
    origin_depth: int | None
    origin_event: UUID | None
    origin_severity: int | None
    origin_basis: str | None
    origin_is_parent: bool


@dataclass(frozen=True, slots=True)
class BlameOrigin:
    """The resolved origin for one subject version, with the whole of its arithmetic.

    ``baseline_commit`` is what a caller diffs against: the origin version when one
    was resolved, the parent version when the mechanism is inert.  It is ``None``
    only for a birth version with no blood, which has nothing to be diffed against
    at all.
    """

    clause_uuid: UUID
    as_of_commit: bytes
    as_of_gen: int
    state: OriginState
    max_severity: int
    parent_version: bytes | None
    origin_commit: bytes | None
    origin_gen: int | None
    origin_depth: int | None
    origin_event: UUID | None
    origin_severity: int | None
    origin_basis: str | None
    first_parent_verified: bool
    depth_bound_reached: bool
    closure_truncated: bool
    reason: str

    @property
    def inert(self) -> bool:
        """``True`` when there is no blood-written baseline and the parent diff stands alone."""
        return self.state == "inert"

    @property
    def baseline_commit(self) -> bytes | None:
        """The commit whose version the delta of record is measured against."""
        return self.origin_commit if self.state == "resolved" else self.parent_version

    @property
    def origin_is_parent(self) -> bool:
        """``True`` when the resolved origin is the immediate parent.

        The mechanism is then *arithmetically* inert — both comparisons read the
        same baseline — while remaining ``resolved``, because the clause does carry
        blood and a later edit can move the two apart.  Reporting it as ``inert``
        would erase that distinction from the record.
        """
        return (
            self.origin_commit is not None
            and self.parent_version is not None
            and self.origin_commit == self.parent_version
        )


class BlameOriginSource(Protocol):
    """Where :func:`resolve_origin` gets its two facts.

    Two methods and no more, so the whole of ORIGINDIFF's resolution logic is
    testable with a dictionary and no cluster — which is what
    ``tests/unit/domain/diachronic`` does.
    """

    def origin_row(self, *, clause_uuid: UUID, as_of_commit: bytes) -> BlameOriginRow | None:
        """Return the ``v_blame_origin`` row for one subject, or ``None`` if absent."""
        ...

    def first_parent_commits(self, *, as_of_commit: bytes, depth_bound: int) -> frozenset[bytes]:
        """Return every commit on the first-parent chain from ``as_of_commit``, inclusive."""
        ...


# --------------------------------------------------------------------------- #
# Resolution — pure                                                            #
# --------------------------------------------------------------------------- #


def resolve_origin(
    row: BlameOriginRow | None,
    *,
    chain: Iterable[bytes] | None = None,
    depth_bound: int = ORIGIN_DEPTH_BOUND,
) -> BlameOrigin:
    """Turn one view row (or its absence) into a :class:`BlameOrigin`.

    Pure: no I/O, no clock, no randomness.  ``chain`` is the first-parent ancestry
    when the caller has walked it and ``None`` when it has not — an unwalked chain
    is reported as ``first_parent_verified=False`` and is *not* silently treated as
    verified.

    :raises BlameClosureAbsent: when ``row`` is ``None``.  A subject version with
        no ``clause_blame_current`` row has an unprojected blame closure, and P2
        forbids a gate from reading past an absent projection.
    """
    if row is None:
        raise BlameClosureAbsent(
            "no mainline.clause_blame_current row exists for this version, so its blame "
            "ancestry has not been projected. A clause with a clean history has a closure "
            "row saying max_severity = 0; a clause with no closure row at all has an "
            "unprojected one, and P2 refuses to read past that rather than reporting "
            "'no blood' — which would make deleting the projection the cheapest way to "
            "move a blame origin out of the gate's reach"
        )

    if row.origin_commit is None:
        return BlameOrigin(
            clause_uuid=row.clause_uuid,
            as_of_commit=row.as_of_commit,
            as_of_gen=row.as_of_gen,
            state="inert",
            max_severity=row.max_severity,
            parent_version=row.parent_version,
            origin_commit=None,
            origin_gen=None,
            origin_depth=None,
            origin_event=None,
            origin_severity=None,
            origin_basis=None,
            first_parent_verified=chain is not None,
            depth_bound_reached=False,
            closure_truncated=row.closure_truncated,
            reason=(
                f"max_severity = {row.max_severity} and no active blame edge at that "
                "severity attached at any version of this clause within "
                f"{depth_bound} generations; the origin is the parent and ORIGINDIFF is inert"
            ),
        )

    depth = row.origin_depth if row.origin_depth is not None else 0
    verified = chain is not None and row.origin_commit in frozenset(chain)
    unverified_note = ""
    if chain is None:
        unverified_note = (
            "; the first-parent chain was not walked, so branch membership is unverified"
        )
    elif not verified:
        unverified_note = (
            "; the origin version is NOT on the first-parent chain of this commit. It is "
            "kept anyway: dropping it would make an unverifiable chain produce a quieter "
            "verdict, which is what a merge that re-parents a clause onto a bloodless line "
            "is buying. Keeping it can only raise the force of the delta of record"
        )

    return BlameOrigin(
        clause_uuid=row.clause_uuid,
        as_of_commit=row.as_of_commit,
        as_of_gen=row.as_of_gen,
        state="resolved",
        max_severity=row.max_severity,
        parent_version=row.parent_version,
        origin_commit=row.origin_commit,
        origin_gen=row.origin_gen,
        origin_depth=depth,
        origin_event=row.origin_event,
        origin_severity=row.origin_severity,
        origin_basis=row.origin_basis,
        first_parent_verified=verified,
        depth_bound_reached=depth >= depth_bound,
        closure_truncated=row.closure_truncated,
        reason=(
            f"severity {row.origin_severity} blame attached at generation {row.origin_gen}, "
            f"{depth} generations before this edit" + unverified_note
        ),
    )


def first_parent_chain(rows: Sequence[tuple[Any, Any]]) -> frozenset[bytes]:
    """Turn :data:`FIRST_PARENT_ANCESTRY_SQL`'s result rows into a commit set.

    Split out from :class:`SqlBlameOriginSource` so that a caller holding rows from
    somewhere else — a fixture, a replayed plan, another driver — converts them the
    same way.
    """
    return frozenset(bytes(row[0]) for row in rows)


# --------------------------------------------------------------------------- #
# The SQL source                                                               #
# --------------------------------------------------------------------------- #


def _as_uuid(value: Any) -> UUID:
    return value if isinstance(value, UUID) else UUID(str(value))


def _as_optional_uuid(value: Any) -> UUID | None:
    return None if value is None else _as_uuid(value)


def _as_optional_bytes(value: Any) -> bytes | None:
    return None if value is None else bytes(value)


def _as_optional_int(value: Any) -> int | None:
    return None if value is None else int(value)


@dataclass
class SqlBlameOriginSource:
    """A :class:`BlameOriginSource` over a live CockroachDB connection.

    ``connection`` is any DB-API connection whose cursors accept ``%(name)s``
    parameters — psycopg 3 in this deployment.  Typed ``Any`` deliberately: the
    domain package must not import ``psycopg`` at module scope, and a Protocol
    narrow enough to be useful here would be wider than the two calls made.
    """

    connection: Any

    def origin_row(self, *, clause_uuid: UUID, as_of_commit: bytes) -> BlameOriginRow | None:
        """Read ``mainline.v_blame_origin`` for one subject version."""
        with self.connection.cursor() as cursor:
            cursor.execute(
                V_BLAME_ORIGIN_SQL,
                {"clause_uuid": str(clause_uuid), "as_of_commit": as_of_commit},
            )
            found = cursor.fetchall()
        if not found:
            return None
        row = found[0]
        return BlameOriginRow(
            clause_uuid=_as_uuid(row[0]),
            as_of_commit=bytes(row[1]),
            site_id=_as_uuid(row[2]),
            as_of_gen=int(row[3]),
            parent_version=_as_optional_bytes(row[4]),
            max_severity=int(row[5]),
            closure_gen=int(row[6]),
            closure_truncated=bool(row[7]),
            origin_commit=_as_optional_bytes(row[8]),
            origin_gen=_as_optional_int(row[9]),
            origin_depth=_as_optional_int(row[10]),
            origin_event=_as_optional_uuid(row[11]),
            origin_severity=_as_optional_int(row[12]),
            origin_basis=None if row[13] is None else str(row[13]),
            origin_is_parent=bool(row[14]),
        )

    def first_parent_commits(
        self, *, as_of_commit: bytes, depth_bound: int = ORIGIN_DEPTH_BOUND
    ) -> frozenset[bytes]:
        """Walk the first-parent chain from ``as_of_commit``, inclusive, depth-bounded."""
        with self.connection.cursor() as cursor:
            cursor.execute(
                FIRST_PARENT_ANCESTRY_SQL,
                {"as_of_commit": as_of_commit, "depth_bound": depth_bound},
            )
            rows = cursor.fetchall()
        return first_parent_chain(rows)
