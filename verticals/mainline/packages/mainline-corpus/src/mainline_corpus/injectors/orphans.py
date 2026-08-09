# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""Injector 3 — orphan clauses.  Twelve obligations with no recorded origin.

**Proves:** the beat.  *This clause has no recorded origin; MAINLINE believes a fatality wrote
it; the engineer weakening it must say yes or no, on the record, under signature.*

An orphan is not a clause with a missing row.  It is a clause that an event genuinely generated
and that the archive never says so about: no revision-history line, no CAPA action, no MOC
citing the event, and — the second half, which is what makes it an orphan rather than merely
untraced — the change landed far enough after the event that the co-location test in
``incident-ingestion.md`` §6 cannot reach it either.  Both documentary channels come up empty.

The only edge the system can offer is therefore ``inferred_semantic``, and by
``inference_never_blocks`` that edge can never be ``active``.  It blocks exactly one thing: a
commit whose ``control_delta = 'weaken'`` lands on the clause it points at.  That is the entire
argument for basis-graded force, and these twelve clauses are what makes it demonstrable instead
of a paragraph in a design document.

At least one orphan is bound to a fatality, because the casualty map needs a red node that
nobody wrote down.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from .. import rng
from ..blame import params
from ..blame.eventindex import EventIndex
from ..skeleton import clock

__all__ = ["Orphan", "schedule_rows", "select"]

#: Drivers under which a clause can appear with the record saying nothing about why.  A revision
#: stage 1 already marked ``incident`` names its event in the revision history, so a clause born
#: there is not an orphan however little else is recorded.
_SILENT_DRIVERS: frozenset[str] = frozenset({"routine_review", "introduce", "retypeset"})


@dataclass(frozen=True, slots=True)
class Orphan:
    """One clause the archive never explains, and the event that actually generated it."""

    clause_key: str
    clause_uuid: str
    site_code: str
    doc_code: str
    revision_key: str
    hidden_cause_ref: str
    hidden_cause_severity: int
    control_class: str
    hazard_energy: str
    lag_days: float


def select(universe: Any, walk: Any, index: EventIndex) -> tuple[Orphan, ...]:
    """Choose the twelve, deliberately spread and with at least one fatality among them."""
    by_clause = walk.by_clause()
    stream = rng.stream("injector.orphans")

    candidates: list[Orphan] = []
    for clause in sorted(universe.clauses, key=lambda c: c.clause_key):
        if clause.is_spine:
            continue
        revisions = by_clause.get(clause.clause_key)
        if not revisions:
            continue
        birth = revisions[0]
        if birth.driver not in _SILENT_DRIVERS:
            continue
        # The cause must sit OUTSIDE the derived window, or the co-location test would find it
        # and the clause would not be an orphan.
        window = index.preceding(
            clause.site_code,
            birth.effective_on,
            window_days=params.ORPHAN_MAX_LAG_DAYS,
            control_class=clause.control_class,
            min_severity=3,
        )
        birth_day = clock.days_between(
            clock.EPOCH,
            clock.coerce_datetime(birth.effective_on, origin="orphan/birth"),
        )
        reachable = [
            fact
            for fact in window
            if params.ORPHAN_MIN_LAG_DAYS <= (birth_day - fact.day) <= params.ORPHAN_MAX_LAG_DAYS
        ]
        if not reachable:
            continue
        best = max(reachable, key=lambda fact: (fact.severity_gate, fact.day))
        candidates.append(
            Orphan(
                clause_key=clause.clause_key,
                clause_uuid=clause.clause_uuid,
                site_code=clause.site_code,
                doc_code=birth.doc_code,
                revision_key=birth.revision_key,
                hidden_cause_ref=best.external_ref,
                hidden_cause_severity=best.severity_gate,
                control_class=clause.control_class,
                hazard_energy=best.event.hazard_energy,
                lag_days=round(birth_day - best.day, 2),
            )
        )

    if len(candidates) < params.ORPHAN_TARGET:
        raise RuntimeError(
            f"only {len(candidates)} clauses qualify as orphans, needed {params.ORPHAN_TARGET}. "
            "An orphan needs a mechanism-matching event between "
            f"{params.ORPHAN_MIN_LAG_DAYS:.0f} and {params.ORPHAN_MAX_LAG_DAYS:.0f} days before "
            "the clause appeared. Widen the lag band rather than shipping fewer: the count is "
            "quoted and the beat is built on it."
        )

    # One fatality first, then spread across sites and documents.  Twelve orphans concentrated in
    # one operation would read as one badly-run site, and the claim is the opposite: an archive
    # that loses the origin of an obligation is the ordinary condition of a twenty-two-year
    # record everywhere, which is why nobody notices it.
    sites = sorted({item.site_code for item in candidates})
    per_site_cap = max(1, -(-params.ORPHAN_TARGET // max(1, len(sites))))
    fatal = [item for item in candidates if item.hidden_cause_severity >= 5]
    chosen: list[Orphan] = []
    seen_docs: set[str] = set()
    per_site: dict[str, int] = {}
    if fatal:
        first = min(fatal, key=lambda item: item.clause_key)
        chosen.append(first)
        seen_docs.add(f"{first.site_code}/{first.doc_code}")
        per_site[first.site_code] = 1

    pool = rng.shuffled(stream, [item for item in candidates if item not in chosen])
    for item in sorted(pool, key=lambda o: (-o.hidden_cause_severity, o.clause_key)):
        if len(chosen) >= params.ORPHAN_TARGET:
            break
        doc_key = f"{item.site_code}/{item.doc_code}"
        if doc_key in seen_docs or per_site.get(item.site_code, 0) >= per_site_cap:
            continue
        seen_docs.add(doc_key)
        per_site[item.site_code] = per_site.get(item.site_code, 0) + 1
        chosen.append(item)
    # The cap is a preference and the count is not: if a site simply has no more candidates, the
    # remainder is filled without it rather than shipping eleven orphans.
    for item in pool:
        if len(chosen) >= params.ORPHAN_TARGET:
            break
        if item not in chosen:
            chosen.append(item)

    if len(chosen) != params.ORPHAN_TARGET:  # pragma: no cover - the floor check above precedes it
        raise RuntimeError(f"selected {len(chosen)} orphans, needed {params.ORPHAN_TARGET}")
    if not any(item.hidden_cause_severity >= 5 for item in chosen):
        raise RuntimeError(
            "no orphan is bound to a fatality. The casualty map needs one true red node that "
            "the archive never wrote down; without it beat 3 is about a paperwork gap."
        )
    return tuple(sorted(chosen, key=lambda item: item.clause_key))


def schedule_rows(orphans: Sequence[Orphan]) -> list[dict[str, Any]]:
    return [
        {
            "clause_key": item.clause_key,
            "clause_uuid": item.clause_uuid,
            "control_class": item.control_class,
            "doc_code": item.doc_code,
            "hazard_energy": item.hazard_energy,
            "hidden_cause_ref": item.hidden_cause_ref,
            "hidden_cause_severity": item.hidden_cause_severity,
            "lag_days": item.lag_days,
            "only_available_basis": "inferred_semantic",
            "revision_key": item.revision_key,
            "site_code": item.site_code,
        }
        for item in sorted(orphans, key=lambda o: o.clause_key)
    ]
