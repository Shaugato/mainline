# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""The case registry, the profile resolution, and CF-01.

This module is the **skeleton** the conformance corpus is built into. It ships exactly
one case — ``CF-01`` — and that case **must fail** against an empty database. That is not
a caveat; it is the deliverable. ``PL-2``:

    For a product whose deliverable is a refusal, a suite that has never been red
    asserts nothing.

Five result states, and the distinctions between them are the whole reporting contract:

``PASSED``
    the database refused exactly as the manifest says it must.
``FAILED``
    it did not. Includes the ordinary pre-migration state, where the relation the case
    needs does not exist — reported as a failure naming the missing object, never as a
    harness error, because a red case and a broken runner must not look alike.
``SKIPPED``
    the case declares a ``requires`` capability this profile does not supply. Printed,
    counted, and never mistaken for a pass.
``PENDING``
    the manifest declares the case and no implementation exists yet. Counted and
    printed. It is *not* fatal today and it is *not* meant to stay that way: the
    conformance-corpus worker owns ``test_manifest_totality``, which is bidirectional
    and turns every PENDING into a failure once the corpus exists.
``ERROR``
    the runner itself could not run the case — no connection, unreadable manifest.
    Always fatal.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

import psycopg
from psycopg import sql as pgsql

from .harness import (
    ConformanceFailure,
    Harness,
    HistoryOutcome,
    Step,
    assert_admitted,
    assert_refusal,
)
from .manifest import Case, Manifest
from .site import SiteScope, new_run_id, scope_for
from .sqlstate import is_schema_absent

__all__ = [
    "PROFILE_SCHEMA",
    "CaseFn",
    "CaseResult",
    "RunReport",
    "Status",
    "implemented_case_ids",
    "register",
    "resolve_schema",
    "run",
]

# Which SQL schema a profile's objects live in. `trappoint-ref` is the reference vertical
# shipped with the substrate (kernel plan §1.1); it is what makes K1 independent of the
# ancestry milestone. Once the bindings land, `--schema` or the binding's own
# `vertical.schema` overrides this map; it is a default, not a second source of truth.
PROFILE_SCHEMA: dict[str, str] = {
    "trappoint-ref": "trappoint_ref",
    "mainline": "mainline",
}

CaseFn = Callable[[Harness, SiteScope, str], HistoryOutcome]

_REGISTRY: dict[str, CaseFn] = {}


def register(case_id: str) -> Callable[[CaseFn], CaseFn]:
    """Register the implementation of *case_id*.

    Registration is by id and duplicates are refused: two implementations of one case is
    a merge accident, and the one that silently wins would be decided by import order.
    """

    def decorate(fn: CaseFn) -> CaseFn:
        if case_id in _REGISTRY:
            raise ValueError(f"case {case_id} already has an implementation")
        _REGISTRY[case_id] = fn
        return fn

    return decorate


def implemented_case_ids() -> frozenset[str]:
    """Every case id with an implementation. Consumed by the totality test."""
    return frozenset(_REGISTRY)


def resolve_schema(profile: str, override: str | None = None) -> str:
    """Return the SQL schema *profile* maps to."""
    if override:
        return override
    try:
        return PROFILE_SCHEMA[profile]
    except KeyError:
        raise ValueError(
            f"unknown profile {profile!r}; known profiles are "
            f"{', '.join(sorted(PROFILE_SCHEMA))}. Pass --schema to run a binding whose "
            "profile is not registered."
        ) from None


class Status(Enum):
    """The five result states."""

    PASSED = "passed"
    FAILED = "failed"
    SKIPPED = "skipped"
    PENDING = "pending"
    ERROR = "error"


@dataclass(frozen=True, slots=True)
class CaseResult:
    """What happened to one case."""

    case: Case
    status: Status
    detail: str = ""
    observed: HistoryOutcome | None = None

    def render(self) -> str:
        """One line for the console."""
        mark = {
            Status.PASSED: "PASS",
            Status.FAILED: "FAIL",
            Status.SKIPPED: "SKIP",
            Status.PENDING: "PEND",
            Status.ERROR: "ERR ",
        }[self.status]
        line = f"{mark}  {self.case.id}  {self.case.title}"
        if self.detail:
            line += f"\n        {self.detail}"
        return line


@dataclass(slots=True)
class RunReport:
    """The outcome of a whole run."""

    profile: str
    schema: str
    spec_version: str
    run_id: str
    results: list[CaseResult] = field(default_factory=list)

    def count(self, status: Status) -> int:
        """How many results carry *status*."""
        return sum(1 for r in self.results if r.status is status)

    @property
    def selected(self) -> int:
        """Cases selected for the profile."""
        return len(self.results)

    @property
    def is_green(self) -> bool:
        """A run is green only when nothing failed and nothing errored.

        PENDING does not make a run red — there is no implementation to be wrong yet —
        and it does not make it green either, which is why the summary always prints the
        count. SKIPPED never makes a run green: a skipped case is not a passed case.
        """
        return self.count(Status.FAILED) == 0 and self.count(Status.ERROR) == 0

    def summary(self) -> str:
        """Render the line quoted in claims of conformance: version and profile, always."""
        parts = [
            f"{self.count(Status.PASSED)}/{self.selected}",
            f"spec {self.spec_version}",
            f"profile {self.profile}",
        ]
        for status in (Status.FAILED, Status.SKIPPED, Status.PENDING, Status.ERROR):
            n = self.count(status)
            if n:
                parts.append(f"{status.value} {n}")
        return " · ".join(parts)


# ─────────────────────────────────────────────────────────────────────────────
# CF-01 — the first case ever written, and the first observed RED.
# ─────────────────────────────────────────────────────────────────────────────


@register("CF-01")
def cf_01_merge_with_an_open_blocking_check(
    harness: Harness, scope: SiteScope, schema: str
) -> HistoryOutcome:
    """Merge a permit carrying one open blocking check → ``23514`` on ``gate_closed_when_issued``.

    The product, in four statements. A permit is opened; an obligation is materialised
    against it; the merge is attempted; the **database** refuses it. Not the application,
    not a validator, not a workflow rule — the ``CHECK`` constraint, whose name is the
    exhibit.

    Two things about the shape are deliberate and both come from the manifest's own note
    on this case.

    **The trigger must not pre-empt the CHECK.** ``spec/errors.md`` §3.3 corollary: where
    a condition is expressible as a ``CHECK`` over a projected scalar, procedural code
    must not raise first. The counter's own constraint produces the refusal, and
    *"refused by ``gate_closed_when_issued``"* is the sentence that matters.

    **The counter is not written by this history.** ``open_blocking`` is a PROJECTION —
    a trigger writes it from ``blocking_check``, the authoritative table — so the case
    inserts an obligation and lets the projection do its work. A case that set the
    counter directly would be testing that ``CHECK`` constraints work, which nobody
    doubts, rather than that the gate is welded to the obligation, which is the claim.

    Against an empty database, the first statement fails with ``42P01`` naming
    ``<schema>.permit``. That is the PL-2 red state: a missing relation, reported as a
    case failure with the object named, never as a harness error.
    """
    site = str(scope.site_id)
    permit_ref = scope.external_ref
    check_ref = f"{permit_ref}-obligation"

    # The schema name is interpolated as a quoted IDENTIFIER, never as text. It can
    # arrive from `--schema`, so it is input; every VALUE below is a bound parameter.
    steps = (
        Step(
            label="open the permit",
            sql=pgsql.SQL(
                """
                INSERT INTO {schema}.permit (site_id, external_ref, state, horizon_at)
                VALUES (%s, %s, 'draft', now() + INTERVAL '7 days')
                """
            ).format(schema=pgsql.Identifier(schema)),
            params=(site, permit_ref),
        ),
        Step(
            label="materialise one blocking obligation against it",
            sql=pgsql.SQL(
                """
                INSERT INTO {schema}.blocking_check (site_id, permit_id, external_ref, state)
                SELECT %s, p.permit_id, %s, 'open'
                FROM {schema}.permit p
                WHERE p.site_id = %s AND p.external_ref = %s
                """
            ).format(schema=pgsql.Identifier(schema)),
            params=(site, check_ref, site, permit_ref),
        ),
        Step(
            label="attempt the merge",
            sql=pgsql.SQL(
                """
                UPDATE {schema}.permit
                   SET state = 'merged', merged_commit = sha256('conformance'::BYTES)
                 WHERE site_id = %s AND external_ref = %s
                """
            ).format(schema=pgsql.Identifier(schema)),
            params=(site, permit_ref),
        ),
    )
    return harness.run_history("CF-01", steps)


# ─────────────────────────────────────────────────────────────────────────────


def _requirements_met(case: Case, satisfied: Iterable[str]) -> tuple[bool, str]:
    available = set(satisfied)
    missing = [token for token in case.requires if token not in available]
    if missing:
        return False, "requires " + ", ".join(sorted(missing))
    return True, ""


def run(
    manifest: Manifest,
    *,
    profile: str,
    conn: psycopg.Connection[Any],
    schema: str | None = None,
    only: frozenset[str] | None = None,
    satisfied_requirements: Iterable[str] = (),
    run_id: str | None = None,
) -> RunReport:
    """Run every implemented case selected for *profile*."""
    resolved_schema = resolve_schema(profile, schema)
    identifier = new_run_id(run_id)
    report = RunReport(
        profile=profile,
        schema=resolved_schema,
        spec_version=manifest.spec_version,
        run_id=identifier,
    )
    harness = Harness(conn)

    for case in manifest.for_profile(profile):
        if only is not None and case.id not in only:
            continue

        met, why = _requirements_met(case, satisfied_requirements)
        if not met:
            report.results.append(CaseResult(case, Status.SKIPPED, why))
            continue

        implementation = _REGISTRY.get(case.id)
        if implementation is None:
            report.results.append(
                CaseResult(
                    case,
                    Status.PENDING,
                    "no implementation yet (the conformance corpus owns this case)",
                )
            )
            continue

        scope = scope_for(identifier, case.id)
        try:
            observed = implementation(harness, scope, resolved_schema)
        except psycopg.Error as exc:
            report.results.append(CaseResult(case, Status.ERROR, f"driver error: {exc}".strip()))
            continue

        try:
            # `admit` cases prove a legal path stays legal; every other class asserts a
            # refusal. A gate that refuses everything is not a gate, so the two
            # assertions are genuinely different and are not collapsed into one.
            if case.cls == "admit":
                assert_admitted(observed)
            else:
                assert_refusal(observed, case.expect_sqlstate, case.expect_constraint)
        except ConformanceFailure as failure:
            detail = str(failure)
            if not observed.completed and is_schema_absent(observed.sqlstate):
                detail = f"SCHEMA NOT MIGRATED — {detail}"
            report.results.append(CaseResult(case, Status.FAILED, detail, observed))
            continue

        report.results.append(CaseResult(case, Status.PASSED, observed.summary(), observed))

    return report
