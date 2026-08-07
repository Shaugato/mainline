# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""The corpus clock.  There is no other source of time in stage 1.

``datetime.now()`` does not appear anywhere in this package and must never appear: a wall clock
inside a reproducible artefact makes ``MANIFEST.sha256`` a function of when the build ran, which
falsifies the one claim a judge can check in four minutes on a laptop.

Three decisions, each with a consequence:

1. **A fixed UTC+10:00 offset, not a named zone.**  Real Australian operations straddle DST
   boundaries and ``zoneinfo``'s answers depend on the tzdata version installed.  A corpus whose
   timestamps move by an hour when a base image updates is not byte-reproducible.  Every
   timestamp in the corpus is emitted with an explicit ``+10:00`` and says so.
2. **Whole-second resolution.**  Microseconds would serialise differently for the same instant
   depending on float rounding in the sampler.  Every emitted timestamp is truncated to the
   second before it becomes a string.
3. **``NOW`` is 2026-08-04T09:14:00+10:00**, the same instant Playwright pins the browser clock
   to (decision D14).  On-screen timestamps and corpus timestamps are the same clock, so a shot
   can be re-taken without the frame changing.
"""

from __future__ import annotations

import datetime as dt
from typing import Final

__all__ = [
    "EPOCH",
    "NOW",
    "SECONDS_PER_DAY",
    "TZ",
    "coerce_date",
    "coerce_datetime",
    "days_between",
    "from_days",
    "iso",
    "iso_date",
    "year_fraction",
]

#: Fixed offset.  Not ``ZoneInfo("Australia/Brisbane")`` — see the module docstring.
TZ: Final[dt.timezone] = dt.timezone(dt.timedelta(hours=10), name="+10:00")

#: Start of the corpus window.  Vocabulary drift is measured 2004 -> 2026, so the window opens
#: in 2004 even though the spine's protagonist clause is introduced in 2011.
EPOCH: Final[dt.datetime] = dt.datetime(2004, 1, 1, 0, 0, 0, tzinfo=TZ)

#: The demo's fixed "now".
NOW: Final[dt.datetime] = dt.datetime(2026, 8, 4, 9, 14, 0, tzinfo=TZ)

SECONDS_PER_DAY: Final[int] = 86_400
_DAYS_PER_YEAR: Final[float] = 365.25


def from_days(days: float) -> dt.datetime:
    """Return ``EPOCH + days``, truncated to whole seconds."""
    seconds = round(days * SECONDS_PER_DAY)
    return EPOCH + dt.timedelta(seconds=seconds)


def days_between(start: dt.datetime, end: dt.datetime) -> float:
    """Signed interval in days."""
    return (end - start).total_seconds() / SECONDS_PER_DAY


def year_fraction(moment: dt.datetime) -> float:
    """Position within the tropical year in ``[0, 1)``, used by the seasonal intensity term."""
    day_of_year = moment.timetuple().tm_yday - 1
    seconds = moment.hour * 3600 + moment.minute * 60 + moment.second
    return ((day_of_year + seconds / SECONDS_PER_DAY) % _DAYS_PER_YEAR) / _DAYS_PER_YEAR


def iso(moment: dt.datetime) -> str:
    """Serialise to ISO-8601 with the explicit ``+10:00`` offset.

    Raises on a naive datetime.  A naive timestamp reaching the emitter would serialise without
    an offset and silently mean "UTC" to the loader, which shifts the whole corpus ten hours.
    """
    if moment.tzinfo is None:
        raise ValueError(f"refusing to serialise a naive datetime: {moment!r}")
    return moment.astimezone(TZ).replace(microsecond=0).isoformat()


def iso_date(day: dt.date) -> str:
    """Serialise a calendar date as ``YYYY-MM-DD``."""
    return day.isoformat()


def coerce_datetime(value: object, *, origin: str) -> dt.datetime:
    """Normalise whatever the YAML loader produced into a ``TZ``-aware datetime.

    PyYAML's behaviour for offset timestamps has changed across versions — older releases
    converted to UTC and returned a *naive* datetime, current releases preserve ``tzinfo``.
    Both are handled here so the corpus does not silently shift by ten hours when the pinned
    PyYAML moves.  A naive value is read as UTC, which is what the older loader meant.
    """
    if isinstance(value, dt.datetime):
        aware = value if value.tzinfo is not None else value.replace(tzinfo=dt.timezone.utc)
        return aware.astimezone(TZ).replace(microsecond=0)
    if isinstance(value, dt.date):
        return dt.datetime(value.year, value.month, value.day, tzinfo=TZ)
    if isinstance(value, str):
        parsed = dt.datetime.fromisoformat(value)
        aware = parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=TZ)
        return aware.astimezone(TZ).replace(microsecond=0)
    raise TypeError(f"{origin}: cannot read {value!r} as a datetime")


def coerce_date(value: object, *, origin: str) -> dt.date:
    """Normalise whatever the YAML loader produced into a calendar date."""
    if isinstance(value, dt.datetime):
        return coerce_datetime(value, origin=origin).date()
    if isinstance(value, dt.date):
        return value
    if isinstance(value, str):
        return dt.date.fromisoformat(value)
    raise TypeError(f"{origin}: cannot read {value!r} as a date")
