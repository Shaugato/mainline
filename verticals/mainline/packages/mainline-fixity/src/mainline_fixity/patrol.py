# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
"""One scheduled occurrence, start to finish, as a pure function.

:func:`run_patrol` takes everything a patrol read and returns everything a patrol
would write. It performs no I/O, opens no connection and reads no clock: the
caller hands it the observations, the bindings, the registry and the two
timestamps, and gets back a :class:`PatrolResult` of rows plus the statements that
write them.

That shape is not fastidiousness. A patrol is the component most likely to be
re-run over historical data during an investigation, and a function whose output
depends only on its arguments can be re-run over the same data in five years and
produce the same findings. A patrol that read ``now()`` internally could not.

**The accounting closes or the run does not exist.** ``n_in_scope = n_checked +
n_not_checked`` is checked by :class:`~mainline_fixity.types.PatrolRun` at
construction, and a run that cannot state its own denominator raises rather than
writing a coverage claim nobody can bound. A ``proposed`` clause ⇄ asset binding
is counted **in scope and not checked**: it is a hypothesis about which clause
governs which asset, and patrolling it as though it were a fact would attribute a
finding to a clause a person never bound.

**Write order is a contract, not a preference.** The returned statements are in
the order they must execute inside one transaction: the run row first (the
findings carry a foreign key to it), then the delta witnesses the caller writes
through the algorithms domain, then the findings, then the warrants. Handing back
an unordered set and documenting the order in prose is how an ordering contract
gets broken by a refactor that looks harmless.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from .compare import Reason, compare_fixity
from .emit import (
    finding_uuid,
    insert_drift_finding,
    insert_patrol_run,
    insert_warrant,
    run_uuid,
)
from .types import DriftFinding, PatrolAccount, PatrolRun
from .warrant import propose_warrant

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence
    from datetime import datetime
    from decimal import Decimal
    from uuid import UUID

    from mainline_domain.contracts import CAT
    from mainline_domain.registry.model import SafeDirectionRegistry

    from .compare import FixityComparison
    from .follower import Statement
    from .types import BisectOutcome, ClauseBinding, ObservedAssertion, PatrolScope
    from .warrant import DiscordanceWarrant

__all__ = ["PatrolResult", "Subject", "run_patrol"]


@dataclass(frozen=True, slots=True)
class Subject:
    """One clause ⇄ asset pair the patrol was asked about.

    ``documented`` is the CAT of the clause version in force at ``as_of``, and
    ``observed`` is the plant's assertion or ``None``. ``bisect`` is the outcome of
    a search the caller already ran — this module never probes, because a probe is
    I/O and this module has none.
    """

    binding: ClauseBinding
    documented: CAT | None
    observed: ObservedAssertion | None
    bisect: BisectOutcome | None = None


@dataclass(frozen=True, slots=True)
class PatrolResult:
    """Everything one occurrence produced, rows and statements together.

    ``comparisons`` holds **every** subject's verdict, including the agreements
    that produce no row. That is what makes ``n_checked`` auditable: a reviewer can
    re-derive the denominator from the same object the numerator came from,
    instead of taking the count on trust.
    """

    run: PatrolRun
    findings: tuple[DriftFinding, ...]
    warrants: tuple[DiscordanceWarrant, ...]
    comparisons: Mapping[UUID, FixityComparison]
    statements: tuple[Statement, ...]

    @property
    def blocking_proposals(self) -> tuple[DriftFinding, ...]:
        """Findings the patrol proposes as blocking, before the projection runs.

        The gate's answer will be this set intersected with the clauses whose
        projected ``max_severity`` is ≥ 4. It can only ever be smaller.
        """
        return tuple(finding for finding in self.findings if finding.would_block)


def run_patrol(
    scope: PatrolScope,
    subjects: Sequence[Subject],
    registry: SafeDirectionRegistry,
    as_of: bytes,
    *,
    as_of_hlc: Decimal,
    started_at: datetime,
    finished_at: datetime,
) -> PatrolResult:
    """Run one occurrence over an already-fetched subject set.

    Args:
        scope: the occurrence — site, class, schedule id, occurrence timestamp.
        subjects: every clause ⇄ asset pair in scope, checked and unchecked alike.
        registry: the DIRECTRIX registry read at ``as_of``.
        as_of: the commit the documented side was read at.
        as_of_hlc: the follower-read timestamp the scan actually ran at, from
            ``cluster_logical_timestamp()`` inside the follower-read transaction.
        started_at: when the scan began. Aware.
        finished_at: when it ended. Aware, and not before ``started_at``.

    Returns:
        A :class:`PatrolResult` whose ``statements`` are in execution order.

    Raises:
        PatrolAccountUnbalanced: the arithmetic did not close.
        MissingErrorBar: a corridor-bearing export supplied no ExcDev/CompDev.
    """
    run_id = run_uuid(scope)
    comparisons: dict[UUID, FixityComparison] = {}
    findings: list[DriftFinding] = []
    warrants: list[DiscordanceWarrant] = []
    checked = 0

    for subject in subjects:
        binding = subject.binding
        if not binding.patrollable:
            # A `proposed` binding is inside the denominator and outside the
            # numerator. Counting it as checked would inflate coverage; dropping
            # it from scope would hide that a clause has no confirmed asset.
            continue
        checked += 1
        comparison = compare_fixity(
            subject.documented,
            subject.observed,
            registry,
            as_of,
            binding=binding,
        )
        comparisons[binding.clause_uuid] = comparison

        warrant = propose_warrant(
            comparison,
            run_id=run_id,
            site_id=scope.site_id,
            clause_uuid=binding.clause_uuid,
            asset_tag=binding.asset_tag,
            opened_at=finished_at,
        )
        if warrant is not None:
            warrants.append(warrant)

        if not comparison.is_finding:
            continue
        if comparison.reason is Reason.UNDOCUMENTED_CONTROL:
            # `drift_finding.documented_cat` is NOT NULL. A control the plant runs
            # and the document does not contain has no documented side, so it is
            # an A2 warrant and no finding row. Synthesising a documented CAT to
            # satisfy the column would be fabricating the very thing the finding
            # claims is missing.
            continue

        findings.append(
            DriftFinding(
                finding_id=finding_uuid(run_id, binding.clause_uuid, binding.asset_tag),
                run_id=run_id,
                site_id=scope.site_id,
                clause_uuid=binding.clause_uuid,
                fixity_class=scope.patrol_class,
                documented_cat=subject.documented,
                observed_cat=(
                    subject.observed.observed_cat if subject.observed is not None else None
                ),
                direction=comparison.direction,
                undetermined=comparison.undetermined,
                confidence_milli=comparison.confidence_milli,
                asset_tag=binding.asset_tag,
                bisect=subject.bisect,
            )
        )

    run = PatrolRun(
        run_id=run_id,
        scope=scope,
        account=PatrolAccount(
            n_in_scope=len(subjects),
            n_checked=checked,
            n_not_checked=len(subjects) - checked,
        ),
        as_of_hlc=as_of_hlc,
        started_at=started_at,
        finished_at=finished_at,
    )

    statements: list[Statement] = [insert_patrol_run(run)]
    statements.extend(insert_drift_finding(finding) for finding in findings)
    statements.extend(insert_warrant(warrant) for warrant in warrants)

    return PatrolResult(
        run=run,
        findings=tuple(findings),
        warrants=tuple(warrants),
        comparisons=comparisons,
        statements=tuple(statements),
    )
