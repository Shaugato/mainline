# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""Injector 6 — decoy events.  Sixty pairs that look right and are wrong.

**Proves:** the linker matches mechanisms, not vocabulary.

A decoy is an event that shares everything a bag of words can see with a *true* precursor — the
same asset, a date in the same window, the same era's vocabulary because the corpus's surface
language is era-banded — and differs in the two things that decide whether a lesson transfers:
the **hazard energy** released, and the **class of control that failed**.  A retriever scoring on
text similarity ranks the decoy alongside the true precursor.  A retriever that joins on
``control_failure.control_class`` does not.  That difference is the entire argument for the
Recurrence-Condition Cue over narrative embedding (ARCHITECTURE.md §5.4), and this set is where
it becomes a measured number instead of a design claim.

**Decoys are selected, never injected.**  ``mainline.event`` has exactly one writer — stage 1 —
and a second generator appending rows would silently invalidate the severity histogram, the
Poisson intensity and the self-excitation term.  So the predicate above is evaluated against the
timeline the sampler already produced, and the schedule records which rows satisfied it.  A
decoy the corpus already contained is a better decoy than one written to be found: it was not
built to be hard, it merely is.

The date window widens through a fixed ladder until sixty pairs exist, and the window that was
actually used is recorded on every row, so nobody has to guess how adversarial the set is.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from .. import gazetteer as gaz
from ..blame import params
from ..blame.eventindex import EventFacts, EventIndex

__all__ = ["Decoy", "schedule_rows", "select"]


@dataclass(frozen=True, slots=True)
class Decoy:
    """One (decoy event, clause) pair and the true pair it shadows."""

    decoy_event_ref: str
    decoy_event_id: str
    twin_event_ref: str
    clause_key: str
    clause_uuid: str
    site_code: str
    site_id: str
    shared_assets: tuple[str, ...]
    window_days: float
    separation_days: float
    era: str
    decoy_hazard_energy: str
    twin_hazard_energy: str
    decoy_control_classes: tuple[str, ...]
    twin_control_classes: tuple[str, ...]
    severity_gate: int


def _era_of(year: int) -> str:
    for entry in gaz.as_sequence(gaz.load("phrases"), "eras", origin="phrases.yaml"):
        if int(entry["from"]) <= year <= int(entry["to"]):
            return str(entry["key"])
    return "e4"


def _is_decoy(candidate: EventFacts, twin: EventFacts, clause_control_class: str) -> bool:
    """Decide whether ``candidate`` is a decoy for ``twin`` — the predicate, stated once.

    Same asset, same era, different hazard energy, and a failed-control set that is disjoint
    from the twin's AND does not contain the clause's own control class.  That last conjunct is
    what makes the pair a genuine negative: an event that failed the very control the clause
    asserts would be a plausible cause, not a decoy.
    """
    if candidate.external_ref == twin.external_ref:
        return False
    if not (candidate.assets & twin.assets):
        return False
    if candidate.event.hazard_energy == twin.event.hazard_energy:
        return False
    if candidate.control_classes & twin.control_classes:
        return False
    if clause_control_class in candidate.control_classes:
        return False
    return _era_of(candidate.occurred_at.year) == _era_of(twin.occurred_at.year)


def select(index: EventIndex, true_pairs: Sequence[Mapping[str, Any]]) -> tuple[Decoy, ...]:
    """Find sixty decoys against the true edges, widening the window only as far as needed.

    ``true_pairs`` carries ``event_ref``, ``clause_key``, ``clause_uuid``, ``site_code``,
    ``site_id`` and ``control_class`` for every authored true edge.  Pairs are considered in a
    stable order, so the set is a function of the corpus and not of dictionary iteration.
    """
    ordered = sorted(true_pairs, key=lambda pair: (str(pair["event_ref"]), str(pair["clause_key"])))
    chosen: list[Decoy] = []
    used_pairs: set[tuple[str, str]] = set()

    for window in params.DECOY_WINDOW_DAYS_LADDER:
        for pair in ordered:
            if len(chosen) >= params.DECOY_TARGET:
                break
            twin = index.get(str(pair["event_ref"]))
            clause_key = str(pair["clause_key"])
            neighbourhood = index.sharing_asset(
                str(pair["site_code"]),
                sorted(twin.assets),
                twin.day - window,
                twin.day + window,
            )
            for candidate in neighbourhood:
                key = (candidate.external_ref, clause_key)
                if key in used_pairs:
                    continue
                if not _is_decoy(candidate, twin, str(pair["control_class"])):
                    continue
                used_pairs.add(key)
                chosen.append(
                    Decoy(
                        decoy_event_ref=candidate.external_ref,
                        decoy_event_id=candidate.event.event_id,
                        twin_event_ref=twin.external_ref,
                        clause_key=clause_key,
                        clause_uuid=str(pair["clause_uuid"]),
                        site_code=str(pair["site_code"]),
                        site_id=str(pair["site_id"]),
                        shared_assets=tuple(sorted(candidate.assets & twin.assets)),
                        window_days=window,
                        separation_days=round(candidate.day - twin.day, 2),
                        era=_era_of(candidate.occurred_at.year),
                        decoy_hazard_energy=candidate.event.hazard_energy,
                        twin_hazard_energy=twin.event.hazard_energy,
                        decoy_control_classes=tuple(sorted(candidate.control_classes)),
                        twin_control_classes=tuple(sorted(twin.control_classes)),
                        severity_gate=candidate.severity_gate,
                    )
                )
                break
        if len(chosen) >= params.DECOY_TARGET:
            break

    if len(chosen) != params.DECOY_TARGET:
        raise RuntimeError(
            f"found {len(chosen)} decoy pairs, needed {params.DECOY_TARGET}, having widened the "
            f"window to {params.DECOY_WINDOW_DAYS_LADDER[-1]:.0f} days. Extend the ladder or "
            "loosen the era requirement — but never loosen the hazard-energy or control-class "
            "conjuncts, because those two are the whole measurement."
        )
    return tuple(sorted(chosen, key=lambda item: (item.decoy_event_ref, item.clause_key)))


def schedule_rows(decoys: Sequence[Decoy]) -> list[dict[str, Any]]:
    return [
        {
            "clause_key": item.clause_key,
            "clause_uuid": item.clause_uuid,
            "decoy_control_classes": list(item.decoy_control_classes),
            "decoy_event_ref": item.decoy_event_ref,
            "decoy_hazard_energy": item.decoy_hazard_energy,
            "era": item.era,
            "separation_days": item.separation_days,
            "severity_gate": item.severity_gate,
            "shared_assets": list(item.shared_assets),
            "site_code": item.site_code,
            "twin_control_classes": list(item.twin_control_classes),
            "twin_event_ref": item.twin_event_ref,
            "twin_hazard_energy": item.twin_hazard_energy,
            "window_days": item.window_days,
        }
        for item in decoys
    ]
