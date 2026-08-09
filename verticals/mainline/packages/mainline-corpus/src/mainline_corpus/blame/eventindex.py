# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""The one index both the clause builder and the causality author read the timeline through.

Two questions get asked of the incident timeline several thousand times during a build:

* *which events at this site, in this window before this date, failed a control of this class?*
* *which events at this site, in this window around this date, touched this asset?*

Both are answered here, once, against a per-site time-sorted array with a bisect, rather than by
re-scanning eleven hundred events per clause revision.  Keeping them together also keeps the
**mechanism join key honest**: an event is a candidate cause because its ``control_failure``
rows name the control class the clause asserts, never because the words look similar.  That is
the whole difference the decoy set exists to measure, and it is enforced by there being no other
way to ask the question.
"""

from __future__ import annotations

import bisect
import datetime as dt
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from ..skeleton import clock
from ..skeleton.build import Skeleton
from ..skeleton.model import Event

__all__ = ["EventFacts", "EventIndex"]


@dataclass(frozen=True, slots=True)
class EventFacts:
    """One event plus the derived facts causality asks about, computed once."""

    event: Event
    control_classes: frozenset[str]
    barrier_roles: frozenset[str]
    icam_tiers: frozenset[str]
    assets: frozenset[str]
    day: float

    @property
    def external_ref(self) -> str:
        return self.event.external_ref

    @property
    def occurred_at(self) -> dt.datetime:
        return self.event.occurred_at

    @property
    def severity_gate(self) -> int:
        return self.event.severity_gate


class EventIndex:
    """Per-site, time-ordered access to the incident timeline and its control failures."""

    __slots__ = ("_by_ref", "_days", "_facts", "_site_days", "_site_facts")

    def __init__(self, skeleton: Skeleton) -> None:
        by_event: dict[str, list[str]] = {}
        roles: dict[str, set[str]] = {}
        tiers: dict[str, set[str]] = {}
        for failure in skeleton.events.control_failures:
            by_event.setdefault(failure.event_ref, []).append(failure.control_class)
            roles.setdefault(failure.event_ref, set()).add(failure.barrier_role)
            tiers.setdefault(failure.event_ref, set()).add(failure.icam_tier)

        facts: list[EventFacts] = []
        for event in skeleton.events.events:
            facts.append(
                EventFacts(
                    event=event,
                    control_classes=frozenset(by_event.get(event.external_ref, ())),
                    barrier_roles=frozenset(roles.get(event.external_ref, ())),
                    icam_tiers=frozenset(tiers.get(event.external_ref, ())),
                    assets=frozenset(event.assets),
                    day=clock.days_between(clock.EPOCH, event.occurred_at),
                )
            )
        facts.sort(key=lambda item: (item.day, item.external_ref))

        self._facts: tuple[EventFacts, ...] = tuple(facts)
        self._days: tuple[float, ...] = tuple(item.day for item in facts)
        self._by_ref: Mapping[str, EventFacts] = {item.external_ref: item for item in facts}

        site_facts: dict[str, list[EventFacts]] = {}
        for item in facts:
            site_facts.setdefault(item.event.site_code, []).append(item)
        self._site_facts: Mapping[str, tuple[EventFacts, ...]] = {
            code: tuple(items) for code, items in site_facts.items()
        }
        self._site_days: Mapping[str, tuple[float, ...]] = {
            code: tuple(item.day for item in items) for code, items in self._site_facts.items()
        }

    def __len__(self) -> int:
        return len(self._facts)

    @property
    def all_facts(self) -> tuple[EventFacts, ...]:
        return self._facts

    def get(self, external_ref: str) -> EventFacts:
        return self._by_ref[external_ref]

    def has(self, external_ref: str) -> bool:
        return external_ref in self._by_ref

    def between(self, site_code: str, low_day: float, high_day: float) -> tuple[EventFacts, ...]:
        """Events at ``site_code`` whose day is in ``[low_day, high_day]``, time-ordered."""
        days = self._site_days.get(site_code)
        if not days:
            return ()
        facts = self._site_facts[site_code]
        start = bisect.bisect_left(days, low_day)
        end = bisect.bisect_right(days, high_day)
        return facts[start:end]

    def preceding(
        self,
        site_code: str,
        moment: dt.date,
        *,
        window_days: float,
        control_class: str | None = None,
        min_severity: int = 0,
    ) -> tuple[EventFacts, ...]:
        """Candidate causes: events before ``moment``, inside the window, matching the mechanism.

        ``control_class`` is the mechanism join key.  Passing ``None`` asks the weaker question
        "what happened here recently", which is what the negative-control set needs to find the
        *most plausible distractor* — the pair a linker is most likely to get wrong.
        """
        high = clock.days_between(
            clock.EPOCH, dt.datetime(moment.year, moment.month, moment.day, tzinfo=clock.TZ)
        )
        low = high - window_days
        found = [
            item
            for item in self.between(site_code, low, high)
            if item.severity_gate >= min_severity
            and (control_class is None or control_class in item.control_classes)
        ]
        return tuple(found)

    def sharing_asset(
        self, site_code: str, assets: Sequence[str], low_day: float, high_day: float
    ) -> tuple[EventFacts, ...]:
        """Events at the site in the window that named at least one of ``assets``."""
        wanted = set(assets)
        return tuple(
            item for item in self.between(site_code, low_day, high_day) if item.assets & wanted
        )
