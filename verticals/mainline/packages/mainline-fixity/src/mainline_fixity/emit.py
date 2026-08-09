# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
"""Statements and parameters. This package never holds a driver or a credential.

Everything here returns a :class:`~mainline_fixity.follower.Statement`; the caller
opens the connection, holds ``agent_patroller`` and owns the transaction boundary.
That absence is what ``mainline-boundary``'s E3 SBOM scan reads, and it is why a
compromised patrol cannot write anything the grant matrix does not already permit.

**There is no ``UPDATE`` and no ``DELETE`` in this module.** Not by convention — by
grant. ``verticals/mainline/db/GRANTS.yaml`` gives ``agent_patroller`` ``INSERT``
on five tables and nothing else, so a ``UPDATE mainline.drift_finding SET
status='withdrawn'`` would fail at the database anyway; writing it here would be a
statement that exists only to be refused. ``tests/unit/fixity/test_starvation.py``
asserts the module's SQL constants over a regex, so the day someone adds one the
test fails rather than production does.

**Two projected columns are supplied and neither is decided here.**
``drift_finding.severity_inherited`` is projected from ``clause_blame_current`` and
``gate_class`` is derived from it — principle P2, and the same shape CF-07 tests on
``blocking_check``, where a client claiming ``severity=1`` on a clause whose closure
holds ``max_severity=5`` gets rewritten by ``fn_check_project``. The columns are
``NOT NULL``, so *something* must be supplied. What is supplied is
:func:`projection_placeholder`, a pure function of ``(direction, undetermined)``
and of **nothing else** — in particular, of no severity, no blame closure and no
ancestry the patrol may have read. Two properties follow:

* the placeholder cannot smuggle a severity, because it never sees one;
* if the projection trigger were ever missing, a real weakening lands as
  ``(5, 'blocking')`` — loud and wrong in the safe direction — rather than as a
  quiet ``advisory`` that nobody would notice.

The one exception is MI21: an ``undetermined`` finding must be ``advisory``, because
``CHECK undetermined_never_blocks`` would refuse anything else with a `23514`. The
obligation an undetermined finding creates is carried by an A6 warrant instead
(see :mod:`mainline_fixity.warrant`), and that warrant is blocking under MI05.

**Deterministic identifiers.** ``run_id`` and ``finding_id`` are UUID5 values over
the schedule occurrence and the finding's subject. EventBridge Scheduler is
at-least-once, so a redelivered occurrence recomputes the same primary keys and the
inserts collide instead of doubling the record. That is a second, independent
idempotency key beside ``UNIQUE (site_id, schedule_id, occurrence_ts)`` — and
§8.5's rule is that the real one is always a database primary key.
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import TYPE_CHECKING, Any, Final

from mainline_domain.contracts import ControlDelta

from .errors import ProjectionSuppliedByClient, UndeterminedWouldBlock
from .follower import Statement, assert_patrol_safe, patrol_read
from .types import GateClass, cat_json

if TYPE_CHECKING:
    from .types import (
        DriftFinding,
        ObservedAssertion,
        PatrolRun,
        PatrolScope,
        TimeWitness,
    )
    from .warrant import DiscordanceWarrant

__all__ = [
    "FINDING_NAMESPACE",
    "INSERT_DRIFT_FINDING_SQL",
    "INSERT_OBSERVED_ASSERTION_SQL",
    "INSERT_PATROL_RUN_SQL",
    "INSERT_TIME_WITNESS_SQL",
    "INSERT_WARRANT_SQL",
    "RUN_NAMESPACE",
    "STATEMENTS",
    "bindings_in_scope",
    "finding_uuid",
    "insert_drift_finding",
    "insert_observed_assertion",
    "insert_patrol_run",
    "insert_time_witness",
    "insert_warrant",
    "observations_for",
    "projection_placeholder",
    "run_uuid",
]

#: Namespaces for the two deterministic identifiers. Fixed constants: changing one
#: would make every redelivery mint a new row, silently doubling a patrol's output.
RUN_NAMESPACE: Final[uuid.UUID] = uuid.UUID("2c1a7f04-6a3d-5e18-8b90-4f6d2e9c7a15")
FINDING_NAMESPACE: Final[uuid.UUID] = uuid.UUID("8d5e2b13-9f47-5c26-a0b8-71e3c4d90f62")

#: The severity a finding is proposed with when the patrol believes it is a real
#: weakening. Deliberately the ceiling: the projection can only ever lower it, and
#: a trigger that failed to run leaves a loud finding rather than a silent one.
_PROPOSED_BLOCKING_SEVERITY: Final[int] = 5

INSERT_PATROL_RUN_SQL: Final[str] = """
INSERT INTO mainline.patrol_run (
  run_id, site_id, patrol_class, schedule_id, occurrence_ts, scope_pred,
  n_in_scope, n_checked, n_not_checked, as_of_hlc, started_at, finished_at
) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
ON CONFLICT (site_id, schedule_id, occurrence_ts) DO NOTHING
RETURNING run_id
""".strip()

INSERT_DRIFT_FINDING_SQL: Final[str] = """
INSERT INTO mainline.drift_finding (
  finding_id, run_id, site_id, clause_uuid, asset_tag, fixity_class,
  documented_cat, observed_cat, direction, undetermined,
  severity_inherited, gate_class, confidence,
  culprit_elem, bisect_lo, bisect_hi, status
) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
ON CONFLICT (finding_id) DO NOTHING
RETURNING finding_id
""".strip()

INSERT_OBSERVED_ASSERTION_SQL: Final[str] = """
INSERT INTO mainline.observed_assertion (
  obs_id, site_id, source_kind, source_ref, asset_tag,
  observed_cat, effective_at, err_bar, leaf_hash
) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
ON CONFLICT (obs_id) DO NOTHING
RETURNING obs_id
""".strip()

INSERT_WARRANT_SQL: Final[str] = """
INSERT INTO mainline.discordance_warrant (
  warrant_id, site_id, clause_uuid, warrant_class, detail, opened_at
) VALUES (%s, %s, %s, %s, %s, %s)
ON CONFLICT (warrant_id) DO NOTHING
RETURNING warrant_id
""".strip()

INSERT_TIME_WITNESS_SQL: Final[str] = """
INSERT INTO mainline.time_witness (
  subject_kind, subject_id, kind, t, source_system, source_sig, ingest_hlc
) VALUES (%s, %s, %s, %s, %s, %s, %s)
ON CONFLICT (subject_kind, subject_id, kind, source_system) DO NOTHING
RETURNING subject_id
""".strip()

#: Every statement this package can produce, for the starvation test to walk.
STATEMENTS: Final[tuple[str, ...]] = (
    INSERT_PATROL_RUN_SQL,
    INSERT_DRIFT_FINDING_SQL,
    INSERT_OBSERVED_ASSERTION_SQL,
    INSERT_WARRANT_SQL,
    INSERT_TIME_WITNESS_SQL,
)


def run_uuid(scope: PatrolScope) -> uuid.UUID:
    """Derive the deterministic ``run_id`` for one schedule occurrence."""
    return uuid.uuid5(
        RUN_NAMESPACE,
        f"{scope.site_id}|{scope.schedule_id}|{scope.occurrence_ts.isoformat()}",
    )


def finding_uuid(run_id: uuid.UUID, clause_uuid: uuid.UUID, asset_tag: str | None) -> uuid.UUID:
    """Derive the deterministic ``finding_id`` for one clause ⇄ asset pair in one run."""
    return uuid.uuid5(FINDING_NAMESPACE, f"{run_id}|{clause_uuid}|{asset_tag or ''}")


def projection_placeholder(
    direction: ControlDelta | None,
    undetermined: bool,
) -> tuple[int, GateClass]:
    """Return the ``(severity_inherited, gate_class)`` pair to *propose*.

    A pure function of its two arguments. It cannot see a severity, a blame
    closure or an ancestry, and that is the whole design: the value the gate reads
    must come from a trigger reading an authoritative table, never from the
    inserter (P2). ``fn_check_project``'s analogue on ``drift_finding`` overwrites
    both columns; this is what is written in the meantime so the ``NOT NULL``
    holds.

    ``undetermined`` forces ``advisory`` because MI21's
    ``CHECK undetermined_never_blocks`` would otherwise refuse the row with a
    `23514` — and a client that has to be told twice is a client that will
    eventually be told by a customer.
    """
    if undetermined:
        return 0, "advisory"
    if direction in (ControlDelta.WEAKEN, ControlDelta.REMOVE):
        return _PROPOSED_BLOCKING_SEVERITY, "blocking"
    return 0, "advisory"


def insert_patrol_run(run: PatrolRun) -> Statement:
    """Build the ``patrol_run`` insert for one completed occurrence.

    The row is written **once, complete**. ``agent_patroller`` holds no ``UPDATE``,
    so there is no way to open a run and close it later, and a patrol that crashes
    mid-scan leaves no row at all — which is what makes at-least-once redelivery
    correct rather than duplicative.

    ``ON CONFLICT … DO NOTHING RETURNING run_id`` returns no row when the
    occurrence has already been recorded. An empty result is the success case for a
    redelivery, and callers must treat it as such rather than as a failed insert.
    """
    return assert_patrol_safe(
        Statement(
            sql=INSERT_PATROL_RUN_SQL,
            params=(
                run.run_id,
                run.scope.site_id,
                run.scope.patrol_class,
                run.scope.schedule_id,
                run.scope.occurrence_ts,
                dict(run.scope.scope_pred),
                run.account.n_in_scope,
                run.account.n_checked,
                run.account.n_not_checked,
                run.as_of_hlc,
                run.started_at,
                run.finished_at,
            ),
        )
    )


def insert_drift_finding(finding: DriftFinding) -> Statement:
    """Build the ``drift_finding`` insert, with the projection placeholder.

    Raises:
        ProjectionSuppliedByClient: ``documented_cat`` is ``None``. The column is
            ``NOT NULL`` in §5.8 for a reason — a finding with no documented side
            is not a *drift* finding at all, it is the plant running a control the
            document does not contain, and that is an A2 warrant with no finding
            row. Routing it here would mean inventing a documented CAT.
        UndeterminedWouldBlock: the placeholder came out ``blocking`` on an
            ``undetermined`` finding, which MI21 forbids. Unreachable through
            :func:`projection_placeholder`; asserted because the day the two
            disagree is the day the database refuses and nobody knows why.
    """
    if finding.documented_cat is None:
        raise ProjectionSuppliedByClient("documented_cat")

    severity, gate_class = projection_placeholder(finding.direction, finding.undetermined)
    if finding.undetermined and gate_class == "blocking":  # pragma: no cover - guard
        raise UndeterminedWouldBlock(str(finding.clause_uuid))

    bisect = finding.bisect
    return assert_patrol_safe(
        Statement(
            sql=INSERT_DRIFT_FINDING_SQL,
            params=(
                finding.finding_id,
                finding.run_id,
                finding.site_id,
                finding.clause_uuid,
                finding.asset_tag,
                finding.fixity_class,
                cat_json(finding.documented_cat),
                cat_json(finding.observed_cat),
                finding.direction.value if finding.direction is not None else None,
                finding.undetermined,
                severity,
                gate_class,
                _confidence(finding.confidence_milli),
                bisect.culprit if bisect else None,
                bisect.lo if bisect else None,
                bisect.hi if bisect else None,
                finding.status,
            ),
        )
    )


def insert_observed_assertion(observation: ObservedAssertion) -> Statement:
    """Build the ``observed_assertion`` insert for one plant export row."""
    return assert_patrol_safe(
        Statement(
            sql=INSERT_OBSERVED_ASSERTION_SQL,
            params=(
                observation.obs_id,
                observation.site_id,
                observation.source_kind,
                observation.source_ref,
                observation.asset_tag,
                cat_json(observation.observed_cat),
                observation.effective_at,
                observation.err_bar.to_json() if observation.err_bar else None,
                observation.leaf_hash,
            ),
        )
    )


def insert_warrant(warrant: DiscordanceWarrant) -> Statement:
    """Build the ``discordance_warrant`` insert. Opens only; never closes."""
    return assert_patrol_safe(
        Statement(
            sql=INSERT_WARRANT_SQL,
            params=(
                warrant.warrant_id,
                warrant.site_id,
                warrant.clause_uuid,
                warrant.warrant_class,
                dict(warrant.detail),
                warrant.opened_at,
            ),
        )
    )


def insert_time_witness(witness: TimeWitness) -> Statement:
    """Build the ``time_witness`` insert — the patrol's half of the SECOND CLOCK."""
    return assert_patrol_safe(
        Statement(
            sql=INSERT_TIME_WITNESS_SQL,
            params=(
                witness.subject_kind,
                witness.subject_id,
                witness.kind,
                witness.t,
                witness.source_system,
                witness.source_sig,
                witness.ingest_hlc,
            ),
        )
    )


def bindings_in_scope(site_id: uuid.UUID, asset_tags: tuple[str, ...]) -> Statement:
    """Build the scope query: which clauses are bound to which of these assets.

    A follower read by construction. ``bind_kind`` is returned rather than
    filtered so the caller can count a ``proposed`` binding into ``n_in_scope``
    and out of ``n_checked`` — a hypothesis is inside the denominator and outside
    the numerator, which is the only way the coverage number stays honest.
    """
    return patrol_read(
        """
        SELECT b.clause_uuid, b.asset_tag, b.bind_kind, b.bound_by, b.confidence
          FROM mainline.clause_binding AS b
         WHERE b.site_id = %s AND b.asset_tag = ANY(%s)
         ORDER BY b.clause_uuid, b.asset_tag
        """.strip(),
        (site_id, list(asset_tags)),
    )


def observations_for(
    site_id: uuid.UUID,
    asset_tag: str,
    since: Any,
) -> Statement:
    """Build the per-source-kind latest-observation query, at a follower read."""
    return patrol_read(
        """
        SELECT DISTINCT ON (o.source_kind)
               o.obs_id, o.source_kind, o.source_ref, o.observed_cat,
               o.effective_at, o.err_bar, o.leaf_hash
          FROM mainline.observed_assertion AS o
         WHERE o.site_id = %s AND o.asset_tag = %s AND o.effective_at >= %s
         ORDER BY o.source_kind, o.effective_at DESC
        """.strip(),
        (site_id, asset_tag, since),
    )


def _confidence(milli: int) -> Decimal:
    """Convert milli-units to the DDL's ``FLOAT8``, once, at the boundary.

    This is the only place in the package where a confidence stops being an
    integer. Keeping it integral everywhere else means no evidentiary payload,
    digest or comparison ever contains a float.
    """
    return Decimal(milli) / Decimal(1000)
