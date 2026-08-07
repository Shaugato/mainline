# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""The negative control: a 24-month replay of routine, uneventful permits.

The nuisance rate — *share of routine permits producing at least one probabilistic
blocking check* — has a ceiling of 3%, and ARCHITECTURE §6.7 says a rule that breaches it
is **rejected rather than tuned**. That ceiling is only meaningful if the denominator is
real work. Two ways to fake it, both of which this module refuses:

**Too few permits.** A nuisance rate over 20 permits has a Wilson interval wide enough to
contain almost anything. Twenty-four months at a realistic weekly volume is hundreds of
permits, and the replay is sized in months and permits-per-week rather than as a flat
count, so the number is traceable to an operating assumption instead of to a convenient
sample size.

**Permits that look nothing like the incident corpus.** If routine permits are written in
a different vocabulary, on different assets, at different sites, then no retriever will
ever match them and the nuisance rate is zero for a reason that has nothing to do with
precision. So the replay draws its sites, activity paths and asset classes **from the
incident corpus's own distribution**: same fleet, same equipment, same functional
taxonomy — different work. That makes the control adversarial in the way it needs to be.

What a routine permit is
------------------------
Inspection, lubrication, filter and lamp changes, calibration, sampling, housekeeping,
scheduled servicing. No control is waived or weakened, no isolation is downgraded, no
deferral is applied. Those are the features that *should* pull a precursor, and putting
one into the negative control would make a correct blocking check look like noise.

These permits are synthetic and say so. No real permit corpus exists to draw from, and
one would be commercially confidential if it did. ``corpus_class='synthetic_permit'``.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Final

from trappoint_recall.corpora.model import EventRecordSet
from trappoint_recall.corpora.rng import DeterministicRandom
from trappoint_recall.eval.corpus import EvalQuery

__all__ = [
    "ROUTINE_TASKS",
    "NegativeControl",
    "NegativeControlReport",
    "routine_query_id",
    "synthesise_routine_replay",
]

ROUTINE_TASKS: Final[tuple[tuple[str, str], ...]] = (
    ("scheduled visual inspection", "walk-down inspection against the standard checklist"),
    ("planned lubrication", "greasing to the OEM schedule with the unit shut down and isolated"),
    ("filter replacement", "change-out of the primary and secondary filters at the service interval"),
    ("lamp replacement", "replacement of a failed area light at ground level"),
    ("instrument calibration", "five-point calibration of a field transmitter against a certified reference"),
    ("routine sampling", "collection of a scheduled sample at the established sample point"),
    ("housekeeping", "removal of spillage and restoration of walkway access"),
    ("scheduled service", "service to the maintenance strategy, all controls in place"),
    ("condition monitoring", "vibration and thermographic survey with the unit running normally"),
    ("fluid top-up", "top-up of hydraulic fluid to the sight glass at the service point"),
    ("signage renewal", "replacement of faded statutory signage"),
    ("guard inspection", "verification that fixed guarding is in place and undamaged"),
)
"""Task, and the phrase describing it.

Every one is work that keeps its controls. Adding a task that waives, defers or downgrades
a control would put a permit that *ought* to pull a precursor into the false-alarm
denominator, and would make a correct gate look noisy."""

_TIME_OF_DAY: Final = (6, 8, 10, 13, 15, 18)


def routine_query_id(index: int) -> str:
    """``Q-NC-0001``. Zero-padded so lexical order matches numeric order in a diff."""
    return f"Q-NC-{index:04d}"


@dataclass(frozen=True, slots=True)
class NegativeControlReport:
    """The replay's shape, published with the nuisance rate it produced."""

    n_permits: int
    months: int
    permits_per_week: int
    first_at: str
    last_at: str
    n_sites: int
    n_activity_paths: int
    n_asset_classes: int
    drawn_from: str
    seed: str

    def to_dict(self) -> dict[str, object]:
        return {
            "n_permits": self.n_permits,
            "months": self.months,
            "permits_per_week": self.permits_per_week,
            "window": [self.first_at, self.last_at],
            "n_sites": self.n_sites,
            "n_activity_paths": self.n_activity_paths,
            "n_asset_classes": self.n_asset_classes,
            "drawn_from": self.drawn_from,
            "seed": self.seed,
            "note": (
                "Sites, activity paths and asset classes are drawn from the incident "
                "corpus so the control is adversarial: a nuisance rate measured on "
                "out-of-distribution text would be low for a reason unrelated to precision."
            ),
        }


@dataclass(frozen=True, slots=True)
class NegativeControl:
    """The routine permits and the report describing how they were built."""

    permits: tuple[EvalQuery, ...]
    report: NegativeControlReport

    def __len__(self) -> int:
        return len(self.permits)


def synthesise_routine_replay(
    records: EventRecordSet,
    *,
    end: datetime,
    months: int = 24,
    permits_per_week: int = 3,
    seed: str = "mainline-negative-control-v1",
    limit: int | None = None,
) -> NegativeControl:
    """Replay ``months`` of uneventful permits ending at ``end``.

    Args:
        records: The incident corpus, read only for its site / activity / asset
            distribution. No incident text is copied into a permit.
        end: The instant the replay ends. Timezone-aware.
        months: Length of the replay. 24 is the figure ARCHITECTURE §6.7 names.
        permits_per_week: Volume assumption. Stated here so the denominator is traceable
            to an operating assumption rather than to a convenient sample size.
        seed: Fixture seed. Same seed, same permits, forever.
        limit: Truncate to this many permits, for a committed fixture slice. Applied after
            generation so the truncated set is a prefix of the full one.

    Returns:
        :class:`NegativeControl`.

    Raises:
        ValueError: if the corpus is empty — a control drawn from nothing has no
            distribution to be adversarial against.
    """
    if end.tzinfo is None:
        raise ValueError("end must be timezone-aware")
    if not len(records):
        raise ValueError(
            "cannot build a negative control from an empty corpus: the replay draws its "
            "sites, activity paths and asset classes from the incident distribution, and "
            "without one the permits would be out-of-distribution by construction"
        )

    sites = sorted({r.site_ref for r in records})
    paths = sorted({r.activity_path for r in records})
    assets = sorted({r.asset_class for r in records})

    total = max(1, (months * 52 * permits_per_week) // 12)
    start = end - timedelta(days=int(months * 30.4375))
    span_seconds = max(1, int((end - start).total_seconds()))
    rng = DeterministicRandom(seed)

    permits: list[EvalQuery] = []
    for index in range(1, total + 1):
        offset = (index - 1) * span_seconds // total
        moment = (start + timedelta(seconds=offset)).replace(
            hour=rng.choice(_TIME_OF_DAY), minute=0, second=0, microsecond=0, tzinfo=UTC
        )
        site = rng.choice(sites)
        path = rng.choice(paths)
        asset = rng.choice(assets)
        task, phrase = rng.choice(ROUTINE_TASKS)
        activity = path.rsplit("/", 1)[-1].replace("-", " ") or "operations"
        text = (
            f"Permit to work: {task} on {asset.replace('-', ' ')} at {site}. "
            f"Scope of work: {phrase}. Activity: {activity}. "
            "No control is waived, weakened or deferred; isolation standard unchanged; "
            f"planned duration one shift commencing {moment.date().isoformat()}."
        )
        permits.append(
            EvalQuery(
                query_id=routine_query_id(index),
                kind="routine",
                text=text,
                site_id=site,
                activity_path=path,
                asset_class=asset,
                severity=None,
                wall=None,
                truth_doc_id=None,
                bonded_sev5=(),
                facets={"narrative": text},
                blinded=True,
            )
        )

    if limit is not None:
        permits = permits[:limit]

    report = NegativeControlReport(
        n_permits=len(permits),
        months=months,
        permits_per_week=permits_per_week,
        first_at=start.astimezone(UTC).isoformat(),
        last_at=end.astimezone(UTC).isoformat(),
        n_sites=len(sites),
        n_activity_paths=len(paths),
        n_asset_classes=len(assets),
        drawn_from=f"{len(records)} incident records",
        seed=seed,
    )
    return NegativeControl(permits=tuple(permits), report=report)


def distribution_summary(records: EventRecordSet) -> Mapping[str, int]:
    """Counts of the three axes the replay draws from, for the build report."""
    return {
        "sites": len({r.site_ref for r in records}),
        "activity_paths": len({r.activity_path for r in records}),
        "asset_classes": len({r.asset_class for r in records}),
    }


def as_rows(permits: Sequence[EvalQuery]) -> tuple[dict[str, object], ...]:
    """Permits as JSON rows, in the harness's ``queries.jsonl`` shape."""
    return tuple(p.to_dict() for p in permits)
