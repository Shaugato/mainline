# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""A psycopg implementation of :class:`~mainline_domain.contracts.PrefixArmRunner`.

The cascade depends on the ``PrefixArmRunner`` *Protocol*, never on this class.
That is what lets S4 be exercised, in full, by unit tests that hand it committed
cosines — and it is also the boundary that keeps ``packages/trappoint-recall``
out of this package.  The recall lead owns the substrate arm runner and the
event-cue arms; duplicating either here would make two implementations that can
disagree about what an arm is.  A protocol and eighty lines cannot disagree
with anything.

``psycopg`` is an **optional extra** (``mainline-domain[db]``) and is imported
inside the constructor, so the whole package imports, type-checks and unit-tests
with no database driver installed at all.  That is not tidiness: AWS credentials
and a CockroachDB Cloud cluster are both unavailable on the build machine, and
nothing in this domain may *require* either in order to be considered done.

**Verified** against a local CockroachDB **v26.2.5** single node on 2026-08-08:
:meth:`PgPrefixArmRunner.ann` returns rows a stage can consume and
:meth:`PgPrefixArmRunner.explain_arm` reports a prefix-constrained ``vector
search`` on ``clause_embedding@ce_ann``.  **Not** verified on CockroachDB Cloud
from this machine.  The live assertions live in
``tests/integration/algorithms/candidates/`` and skip, with a reason naming the
missing DSN, when no cluster is reachable — a skipped run entitles nobody to say
the plan was verified, and the skip message says so.
"""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from typing import TYPE_CHECKING, Any, Final
from uuid import UUID

from mainline_domain.contracts import Candidate

from .explain import INDEX_REFUSED_SQLSTATE, ArmPlanAssertion, assert_arm_plan
from .semantic import ARM_INDEX, ARM_SQL, ARM_TABLE, Arm

if TYPE_CHECKING:  # pragma: no cover - typing only
    from psycopg import Connection

__all__ = ["ArmIndexUnavailableError", "PgPrefixArmRunner"]

INDEX_MISSING_SQLSTATE: Final[str] = "42704"
"""``undefined_object`` — the pinned index does not exist on this cluster.

Measured on CockroachDB v26.2.5: ``index "nope" not found``.  Together with
:data:`~.explain.INDEX_REFUSED_SQLSTATE` these are the two ways a pinned arm can
fail, and both of them are *deployment* failures that must not be swallowed.
"""


class ArmIndexUnavailableError(RuntimeError):
    """The C-SPANN index an arm pins is missing or unusable for the statement.

    Raised, never absorbed, and never retried.  S4's entire cost claim is that
    the arm is served by ``ce_ann``; a runner that fell back to an unhinted
    statement here would turn a loud deployment error into a silent full scan of
    every clause embedding on the site, and would do it underneath a gate whose
    output decides whether blame lands on the right clause.

    The pin is what makes this an exception rather than a slow afternoon.
    """


class PgPrefixArmRunner:
    """Runs **one fully-constrained arm per call**, over pgwire.

    Satisfies the ``PrefixArmRunner`` protocol structurally; it does not inherit
    from it, because a runtime base class would make ``contracts.py`` an import
    of this module rather than the other way round.
    """

    __slots__ = ("_conn", "_last_plan")

    def __init__(self, conn: Connection[Any]) -> None:
        """Wrap an open psycopg connection, refusing if the extra is absent."""
        try:
            import psycopg  # noqa: F401 - optional extra, probed here
        except ModuleNotFoundError as exc:  # pragma: no cover - depends on the extra
            raise ModuleNotFoundError(
                "PgPrefixArmRunner needs the `db` extra: install mainline-domain[db]. "
                "Every stage except S4's live path runs without it."
            ) from exc
        self._conn = conn
        self._last_plan: str | None = None

    @property
    def last_plan(self) -> str | None:
        """The most recent ``EXPLAIN`` text captured by :meth:`explain_arm`."""
        return self._last_plan

    def ann(
        self,
        site_id: UUID,
        activity_root: str,
        q: Sequence[float],
        k: int,
    ) -> Sequence[Candidate]:
        """One arm: ``site_id`` and ``activity_root`` both bound to specific values.

        Returns raw ANN hits with ``stage='S4'`` and the cosine similarity as
        the score.  **No anchor filtering happens here** — the veto belongs to
        :func:`~.semantic.semantic_stage`, where it is applied to every
        candidate from every arm, and a runner that filtered would be a second
        place the veto could be forgotten.
        """
        if k < 1:
            raise ValueError(f"k must be >= 1, got {k}")
        if not activity_root:
            raise ValueError("activity_root must be a specific value, not an empty string")
        arm = Arm(site_id=site_id, activity_root=activity_root)
        with _index_must_be_usable(), self._conn.cursor() as cur:
            cur.execute(ARM_SQL, arm.params(q, k))
            rows = cur.fetchall()
        return tuple(
            Candidate(
                ancestor_clause_uuid=row[0] if isinstance(row[0], UUID) else UUID(str(row[0])),
                ancestor_commit=bytes(row[1]),
                stage="S4",
                score=float(row[2]),
                features={"cosine": float(row[2])},
            )
            for row in rows
        )

    def explain_arm(
        self,
        site_id: UUID,
        activity_root: str,
        q: Sequence[float],
        k: int,
        *,
        expected_index: str = "ce_ann",
        raises: bool = True,
    ) -> ArmPlanAssertion:
        """``EXPLAIN`` the arm and assert the plan.

        Plain ``EXPLAIN`` only.  ``EXPLAIN ANALYZE`` is unavailable through the
        Managed MCP surface, and an assertion that can only run over pgwire is
        an assertion that cannot be re-run on CockroachDB's own endpoint — so
        this deliberately uses the form both surfaces can produce.
        """
        arm = Arm(site_id=site_id, activity_root=activity_root)
        with _index_must_be_usable(), self._conn.cursor() as cur:
            cur.execute(f"EXPLAIN {ARM_SQL}", arm.params(q, k))
            plan = "\n".join(str(row[0]) for row in cur.fetchall())
        self._last_plan = plan
        return assert_arm_plan(plan, expected_index=expected_index, raises=raises)


@contextmanager
def _index_must_be_usable() -> Iterator[None]:
    """Translate the two pinned-index SQLSTATEs into one named domain failure.

    Deliberately narrow: only ``42809`` and ``42704`` are converted, and every
    other database error propagates untouched.  A broad ``except Exception``
    here would be the same mistake as a fallback — it would let an unrelated
    failure wear a message about the vector index.
    """
    try:
        yield
    except Exception as exc:
        sqlstate = getattr(exc, "sqlstate", None)
        if sqlstate == INDEX_REFUSED_SQLSTATE:
            raise ArmIndexUnavailableError(
                f"{ARM_TABLE}@{ARM_INDEX} refused this arm (SQLSTATE "
                f"{INDEX_REFUSED_SQLSTATE}): a C-SPANN prefix column was not constrained to a "
                f"specific value. The arm is NOT retried unhinted — an unhinted arm is a full "
                f"scan of every clause embedding on the site"
            ) from exc
        if sqlstate == INDEX_MISSING_SQLSTATE:
            raise ArmIndexUnavailableError(
                f"index {ARM_INDEX} does not exist on {ARM_TABLE} (SQLSTATE "
                f"{INDEX_MISSING_SQLSTATE}): the C-SPANN index this cluster was migrated to "
                f"carry is absent, so S4 has no index to be served by and must not pretend "
                f"otherwise"
            ) from exc
        raise
