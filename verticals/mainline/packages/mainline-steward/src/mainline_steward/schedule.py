# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
"""``schedules.yaml`` — the calendar as declarative data, and the occurrence key.

``ARCHITECTURE.md`` §8.5: **EventBridge Scheduler is the entire calendar**, and
CockroachDB has no general-purpose SQL scheduler (``CREATE SCHEDULE`` exists only for
backups and changefeeds). So no design element here may assume in-database cron, and the
calendar has to live somewhere a human reads and a machine validates. It lives in
``verticals/mainline/apps/steward/schedules.yaml``; this module is its loader.

**This package does not create the EventBridge resources.** The infra lead owns
``infra/``. What is owned here is the *declaration* — the schedule ids, the expressions,
which skills and which views each run consumes — so that the OpenTofu that creates the
rules and the container that answers them are reading one file rather than agreeing by
coincidence.

**Idempotency, and its honest limit.** Scheduler delivery is at-least-once, so the same
``(schedule_id, occurrence_ts)`` will sometimes arrive twice. Two things make that
survivable and neither is a database constraint we own:

1. The occurrence key is carried *inside* the attestation's ``subject_ref``, so a
   duplicate is identifiable and collapsible by any reader with no join.
2. :class:`~mainline_steward.guard.OccurrenceGuard` refuses a second run of an
   occurrence it has already recorded.

What is **not** claimed: exactly-once. The writing identity (``mainline_auditor``) holds
``INSERT`` on ``mainline_meas.external_attestation`` and no ``SELECT`` anywhere, so this
package physically cannot read back to deduplicate. A ``UNIQUE (attestor, subject_kind,
subject_ref)`` on that table would turn at-least-once into exactly-once by ``23505``;
that constraint belongs to the data-model lead's migration and is recorded as a
cross-domain note rather than assumed here.
"""

from __future__ import annotations

import re
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from pathlib import Path
from typing import Any, Final

import yaml

from .errors import ScheduleRefused

__all__ = [
    "OCCURRENCE_SEPARATOR",
    "Occurrence",
    "RunKind",
    "Schedule",
    "ScheduleBook",
    "load_schedules",
    "normalise_occurrence_ts",
    "occurrence_key",
]

OCCURRENCE_SEPARATOR: Final = "@"
"""``<schedule_id>@<occurrence_ts>``. One character, and it appears in no schedule id."""

_RATE: Final = re.compile(r"\Arate\(\s*(\d+)\s+(minute|minutes|hour|hours|day|days)\s*\)\Z")
_CRON: Final = re.compile(r"\Acron\((?P<body>[^)]+)\)\Z")
_CRON_FIELDS: Final = 6
_SCHEDULE_ID: Final = re.compile(r"\A[a-z][a-z0-9-]{2,63}\Z")


class RunKind(StrEnum):
    """What a scheduled occurrence actually does.

    Two kinds, because they read different surfaces and must not be confused in the
    evidence: ``mcp_ops`` reads pre-materialised ``mainline_audit`` views over the
    Managed MCP endpoint, and ``custodian_patrol`` reads the CockroachDB Cloud API
    through the ``ccloud`` shim (§8.6 I4) *and* the ledger-health view.
    """

    MCP_OPS = "mcp_ops"
    CUSTODIAN_PATROL = "custodian_patrol"


def normalise_occurrence_ts(value: str) -> str:
    """Return ``value`` as a second-resolution UTC instant, ``YYYY-MM-DDTHH:MM:SSZ``.

    EventBridge substitutes ``<aws.scheduler.scheduled-time>`` as an ISO-8601 instant, and
    a retry of the same occurrence carries the *same* value — which is what makes it an
    idempotency key at all. It is normalised here so that ``…Z``, ``+00:00`` and a
    fractional-second variant of one occurrence cannot become three occurrence keys.

    Raises:
        ScheduleRefused: the value is not an ISO-8601 instant, or carries no timezone. A
            naive timestamp in an evidentiary key is an unanswerable question in
            cross-examination, and there is no local time it could safely be assumed to be.
    """
    text = value.strip()
    if not text:
        raise ScheduleRefused("occurrence timestamp is empty")
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ScheduleRefused(f"occurrence timestamp {value!r} is not ISO-8601: {exc}") from exc
    if parsed.tzinfo is None:
        raise ScheduleRefused(
            f"occurrence timestamp {value!r} carries no timezone. A naive instant in an "
            "idempotency key is a different instant on a different runner"
        )
    return parsed.astimezone(UTC).replace(microsecond=0).strftime("%Y-%m-%dT%H:%M:%SZ")


def occurrence_key(schedule_id: str, occurrence_ts: str) -> str:
    """Return the ``(schedule_id, occurrence_ts)`` idempotency key as one string."""
    return f"{schedule_id}{OCCURRENCE_SEPARATOR}{normalise_occurrence_ts(occurrence_ts)}"


@dataclass(frozen=True, slots=True)
class Schedule:
    """One declared occurrence family."""

    schedule_id: str
    title: str
    kind: RunKind
    expression: str
    timezone: str
    prompt: str
    views: tuple[str, ...]
    skills: tuple[str, ...]
    max_turns: int
    ccloud_lookback_minutes: int
    why: str

    def occurrence(self, occurrence_ts: str) -> Occurrence:
        """Bind this schedule to one delivered occurrence."""
        return Occurrence(schedule=self, occurrence_ts=normalise_occurrence_ts(occurrence_ts))


@dataclass(frozen=True, slots=True)
class Occurrence:
    """One delivery: a schedule plus the instant EventBridge said it was for."""

    schedule: Schedule
    occurrence_ts: str

    @property
    def key(self) -> str:
        """The idempotency key, ``<schedule_id>@<occurrence_ts>``."""
        return occurrence_key(self.schedule.schedule_id, self.occurrence_ts)

    @property
    def since(self) -> str:
        """The ``--starting-from`` instant for the custodian patrol's audit read.

        Derived from the occurrence rather than from ``now()``: a retried occurrence must
        read the same window as its first attempt, or the two attestations for one
        occurrence would legitimately differ and a reader could not tell that from drift.
        """
        moment = datetime.strptime(self.occurrence_ts, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
        lookback = timedelta(minutes=self.schedule.ccloud_lookback_minutes)
        return (moment - lookback).strftime("%Y-%m-%dT%H:%M:%SZ")


@dataclass(frozen=True, slots=True)
class ScheduleBook:
    """Every declared schedule, with the file it came from."""

    schedules: tuple[Schedule, ...]
    source: Path | None
    default_timezone: str

    def __iter__(self) -> Iterator[Schedule]:
        """Iterate the schedules in declaration order."""
        return iter(self.schedules)

    def __len__(self) -> int:
        """Return the number of declared schedules."""
        return len(self.schedules)

    def ids(self) -> tuple[str, ...]:
        """Return the declared schedule ids, in declaration order."""
        return tuple(s.schedule_id for s in self.schedules)

    def by_id(self, schedule_id: str) -> Schedule:
        """Return one schedule, or refuse naming what is declared."""
        for schedule in self.schedules:
            if schedule.schedule_id == schedule_id:
                return schedule
        raise ScheduleRefused(f"{schedule_id!r} is not declared; have {list(self.ids())}")


def _validate_expression(expression: str, *, schedule_id: str) -> str:
    """Refuse an expression EventBridge Scheduler would not accept."""
    text = expression.strip()
    if _RATE.match(text):
        return text
    cron = _CRON.match(text)
    if cron:
        fields = cron.group("body").split()
        if len(fields) != _CRON_FIELDS:
            raise ScheduleRefused(
                f"{schedule_id}: cron expression has {len(fields)} fields; EventBridge "
                f"Scheduler takes {_CRON_FIELDS} "
                "(minutes hours day-of-month month day-of-week year)"
            )
        return text
    raise ScheduleRefused(
        f"{schedule_id}: {expression!r} is neither rate(...) nor cron(...). The calendar is "
        "EventBridge Scheduler's and only its expressions are accepted here"
    )


def _as_tuple(value: Any, *, field: str, schedule_id: str) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str) or not isinstance(value, Sequence):
        raise ScheduleRefused(f"{schedule_id}.{field} must be a list of strings, got {value!r}")
    return tuple(str(item) for item in value)


def _as_positive_int(value: Any, *, field: str, schedule_id: str, default: int) -> int:
    if value is None:
        return default
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ScheduleRefused(f"{schedule_id}.{field} must be a positive integer, got {value!r}")
    return value


def parse_schedules(document: Mapping[str, Any], *, source: Path | None = None) -> ScheduleBook:
    """Build a :class:`ScheduleBook` from an already-parsed schedules document."""
    raw = document.get("schedules")
    if not isinstance(raw, list) or not raw:
        raise ScheduleRefused("schedules.yaml has no non-empty `schedules` list")
    default_timezone = str(document.get("timezone", "Australia/Brisbane"))
    schedules: list[Schedule] = []
    seen: set[str] = set()
    for index, entry in enumerate(raw):
        if not isinstance(entry, Mapping):
            raise ScheduleRefused(f"schedules[{index}] must be a mapping")
        schedule_id = str(entry.get("schedule_id", "")).strip()
        if not _SCHEDULE_ID.match(schedule_id):
            raise ScheduleRefused(
                f"schedules[{index}]: schedule_id {schedule_id!r} must be lowercase "
                "kebab-case, 3-64 characters. It becomes half of an idempotency key that "
                "outlives this deployment"
            )
        if schedule_id in seen:
            raise ScheduleRefused(f"schedule_id {schedule_id!r} appears twice")
        seen.add(schedule_id)
        kind_text = str(entry.get("kind", "")).strip()
        try:
            kind = RunKind(kind_text)
        except ValueError as exc:
            raise ScheduleRefused(
                f"{schedule_id}: kind {kind_text!r} is not one of {[k.value for k in RunKind]}"
            ) from exc
        views = _as_tuple(entry.get("views"), field="views", schedule_id=schedule_id)
        if not views:
            raise ScheduleRefused(
                f"{schedule_id}: declares no views. A scheduled run that reads nothing would "
                "produce an attestation with no findings, which is the shape a clean report has"
            )
        prompt = str(entry.get("prompt", "")).strip()
        if not prompt:
            raise ScheduleRefused(f"{schedule_id}: declares no prompt asset")
        schedules.append(
            Schedule(
                schedule_id=schedule_id,
                title=str(entry.get("title", schedule_id)),
                kind=kind,
                expression=_validate_expression(
                    str(entry.get("expression", "")), schedule_id=schedule_id
                ),
                timezone=str(entry.get("timezone", default_timezone)),
                prompt=prompt,
                views=views,
                skills=_as_tuple(entry.get("skills"), field="skills", schedule_id=schedule_id),
                max_turns=_as_positive_int(
                    entry.get("max_turns"), field="max_turns", schedule_id=schedule_id, default=12
                ),
                ccloud_lookback_minutes=_as_positive_int(
                    entry.get("ccloud_lookback_minutes"),
                    field="ccloud_lookback_minutes",
                    schedule_id=schedule_id,
                    default=20,
                ),
                why=str(entry.get("why", "")),
            )
        )
    return ScheduleBook(
        schedules=tuple(schedules), source=source, default_timezone=default_timezone
    )


def load_schedules(path: Path) -> ScheduleBook:
    """Load and validate ``schedules.yaml``."""
    if not path.is_file():
        raise ScheduleRefused(f"no schedules file at {path}")
    try:
        document = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise ScheduleRefused(f"{path} is not valid YAML: {exc}") from exc
    if not isinstance(document, Mapping):
        raise ScheduleRefused(f"{path} must contain a mapping at the top level")
    return parse_schedules(document, source=path)
