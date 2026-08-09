# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""Injector 4 — slow weakening.  Four chains, three MOCs each, roughly six years.

**Proves:** fixity patrol and bisect.  No single step in one of these chains looks like much —
an alarm threshold moved one notch, approved by a change record, with a plausible operational
reason.  Three steps later the control is materially weaker than the one an incident wrote, and
nobody decided that.  This is the shape a diff between two adjacent revisions cannot see and a
bisect over a version chain can, which is why ``clause_version``'s primary key puts ``gen``
before ``commit_id``.

Each chain is built on a clause that asserts a **setpoint**, because a setpoint is what makes
``control_delta`` decidable without prose judgement: ``setpoints.yaml`` records which direction
strengthens each parameter, so a step in the other direction is a weakening as a matter of
arithmetic and not of opinion.  A chain built on a reworded sentence would need a classifier to
notice, and a corpus that needs a classifier to establish its own ground truth has no ground
truth.

Chains never touch the spine clause.  The spine's 2026 weakening is a *proposal on a branch*
that the merge refuses, and a corpus in which the same clause was also being quietly weakened
in merged history would blur the two most important beats into one.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from .. import gazetteer as gaz
from .. import rng
from ..skeleton import clock
from ..skeleton.build import Skeleton
from ..skeleton.model import DocRevision

__all__ = ["Chain", "ChainStep", "plan", "schedule_rows"]

_MIN_GAP_YEARS: float = 1.2
_MOC_MATCH_WINDOW_DAYS: float = 240.0
#: Intents a weakening step can plausibly hide behind.  ``strengthen`` is excluded: a change
#: record that declares it strengthens a control and then weakens one is a different corpus —
#: that is fraud, not drift, and this injector is about drift.
_CHAIN_INTENTS: frozenset[str] = frozenset({"weaken", "replace", "restate", "introduce"})


@dataclass(frozen=True, slots=True)
class ChainStep:
    revision_key: str
    effective_on: dt.date
    change_ref: str
    change_intent: str
    change_lag_days: float
    step_index: int


@dataclass(frozen=True, slots=True)
class Chain:
    """One clause weakened three times, and the change records each step hid behind."""

    chain_id: str
    site_code: str
    doc_code: str
    clause_key: str
    clause_uuid: str
    setpoint_key: str
    steps: tuple[ChainStep, ...]
    span_years: float

    @property
    def revision_keys(self) -> frozenset[str]:
        return frozenset(step.revision_key for step in self.steps)


def _setpoint_values() -> Mapping[str, tuple[Sequence[float], str]]:
    out: dict[str, tuple[Sequence[float], str]] = {}
    for entry in gaz.as_sequence(gaz.load("setpoints"), "parameters", origin="setpoints.yaml"):
        out[str(entry["key"])] = (
            tuple(float(value) for value in entry["values"]),
            str(entry["strengthen_direction"]),
        )
    return out


def _revisions_by_doc(skeleton: Skeleton) -> dict[tuple[str, str], tuple[DocRevision, ...]]:
    grouped: dict[tuple[str, str], list[DocRevision]] = {}
    for revision in skeleton.documents.revisions:
        site_code = revision.revision_key.split("/", 1)[0]
        grouped.setdefault((site_code, revision.doc_code), []).append(revision)
    return {key: tuple(sorted(items, key=lambda r: r.rev_no)) for key, items in grouped.items()}


def _nearest_change(
    skeleton: Skeleton, site_code: str, on: dt.date
) -> tuple[str, str, float] | None:
    target = dt.datetime(on.year, on.month, on.day, tzinfo=clock.TZ)
    best: tuple[float, str, str] | None = None
    for cr in skeleton.mocs.change_requests:
        if cr.site_code != site_code or cr.intent not in _CHAIN_INTENTS:
            continue
        lag = abs((cr.opened_at - target).total_seconds()) / clock.SECONDS_PER_DAY
        if lag > _MOC_MATCH_WINDOW_DAYS:
            continue
        candidate = (lag, cr.external_ref, cr.intent)
        if best is None or candidate < best:
            best = candidate
    if best is None:
        return None
    lag, ref, intent = best
    return ref, intent, round(lag, 2)


def _pick_steps(
    revisions: Sequence[DocRevision], after: dt.date, span: tuple[float, float]
) -> tuple[DocRevision, ...] | None:
    """Three revisions of one document, spaced apart, spanning roughly the chain window."""
    from ..blame import params

    candidates = [r for r in revisions if r.effective_on > after]
    low, high = span
    for start in range(len(candidates)):
        picked = [candidates[start]]
        for revision in candidates[start + 1 :]:
            gap = (revision.effective_on - picked[-1].effective_on).days / 365.25
            if gap < _MIN_GAP_YEARS:
                continue
            picked.append(revision)
            if len(picked) == params.WEAKENING_CHAIN_STEPS:
                break
        if len(picked) < params.WEAKENING_CHAIN_STEPS:
            continue
        total = (picked[-1].effective_on - picked[0].effective_on).days / 365.25
        if low <= total <= high:
            return tuple(picked)
    return None


def plan(skeleton: Skeleton, universe: Any) -> tuple[Chain, ...]:
    """Choose the four chains: one per site, on four different documents."""
    from ..blame import params

    values = _setpoint_values()
    revisions = _revisions_by_doc(skeleton)
    stream = rng.stream("injector.weakening")

    candidates = [
        clause
        for clause in universe.clauses
        if clause.setpoint_key is not None
        and not clause.is_spine
        and clause.clause_key not in universe.migrations
        and len(values[clause.setpoint_key][0]) >= params.WEAKENING_CHAIN_STEPS + 1
    ]
    candidates.sort(key=lambda c: c.clause_key)
    ordered = rng.shuffled(stream, candidates)

    chains: list[Chain] = []
    used_sites: set[str] = set()
    used_docs: set[str] = set()
    for clause in ordered:
        if len(chains) >= params.WEAKENING_CHAIN_TARGET:
            break
        if clause.site_code in used_sites or clause.origin_doc_code in used_docs:
            continue
        doc_revisions = revisions.get((clause.site_code, clause.origin_doc_code))
        if not doc_revisions:
            continue
        picked = _pick_steps(doc_revisions, clause.birth_on, params.WEAKENING_CHAIN_SPAN_YEARS)
        if picked is None:
            continue
        steps: list[ChainStep] = []
        for index, revision in enumerate(picked, start=1):
            change = _nearest_change(skeleton, clause.site_code, revision.effective_on)
            if change is None:
                break
            ref, intent, lag = change
            steps.append(
                ChainStep(
                    revision_key=revision.revision_key,
                    effective_on=revision.effective_on,
                    change_ref=ref,
                    change_intent=intent,
                    change_lag_days=lag,
                    step_index=index,
                )
            )
        if len(steps) != params.WEAKENING_CHAIN_STEPS:
            continue
        used_sites.add(clause.site_code)
        used_docs.add(clause.origin_doc_code)
        chains.append(
            Chain(
                chain_id=f"chain-{len(chains) + 1:02d}",
                site_code=clause.site_code,
                doc_code=clause.origin_doc_code,
                clause_key=clause.clause_key,
                clause_uuid=clause.clause_uuid,
                setpoint_key=clause.setpoint_key or "",
                steps=tuple(steps),
                span_years=round((steps[-1].effective_on - steps[0].effective_on).days / 365.25, 2),
            )
        )

    if len(chains) != params.WEAKENING_CHAIN_TARGET:
        raise RuntimeError(
            f"planned {len(chains)} weakening chains, needed {params.WEAKENING_CHAIN_TARGET}. "
            "A chain needs a setpoint-bearing clause whose document was reissued three times "
            "across the span window with a change record near each issue; relax "
            "WEAKENING_CHAIN_SPAN_YEARS or the site/document uniqueness rule rather than "
            "shipping fewer, because the count is quoted."
        )
    return tuple(sorted(chains, key=lambda item: item.chain_id))


def schedule_rows(
    chains: Sequence[Chain], applied: Mapping[str, Sequence[dict[str, Any]]]
) -> list[dict[str, Any]]:
    """One row per chain step, carrying the setpoint value on both sides of the step."""
    rows: list[dict[str, Any]] = []
    for chain in chains:
        moves = list(applied.get(chain.chain_id, ()))
        by_revision = {str(move["revision_key"]): move for move in moves}
        for step in chain.steps:
            move = by_revision.get(step.revision_key, {})
            rows.append(
                {
                    "chain_id": chain.chain_id,
                    "change_intent": step.change_intent,
                    "change_lag_days": step.change_lag_days,
                    "change_ref": step.change_ref,
                    "clause_key": chain.clause_key,
                    "clause_uuid": chain.clause_uuid,
                    "doc_code": chain.doc_code,
                    "effective_on": clock.iso_date(step.effective_on),
                    "revision_key": step.revision_key,
                    "setpoint_from": move.get("setpoint_from"),
                    "setpoint_key": chain.setpoint_key,
                    "setpoint_to": move.get("setpoint_to"),
                    "site_code": chain.site_code,
                    "span_years": chain.span_years,
                    "step_index": step.step_index,
                    "steps_in_chain": len(chain.steps),
                }
            )
    rows.sort(key=lambda row: (row["chain_id"], row["step_index"]))
    return rows
