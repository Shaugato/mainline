# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""CSB investigation reports and Australian state-regulator safety alerts.

Same :class:`~trappoint_recall.corpora.model.EventRecord` shape as
:mod:`trappoint_recall.corpora.msha`, two more severity bases, and one important
difference in where the number comes from.

**CSB reports** publish a casualty count — ``Fatalities: 2`` — in the incident summary.
That is a coded field: the agency counted, and counting is not rating. Severity is taken
from the count through :data:`CASUALTY_SEVERITY`, and the basis is ``coded_field``.

**State-regulator safety alerts** (NSW Resources Regulator, Queensland RSHQ, WA DMIRS)
publish a *classification* instead — "fatality", "serious injury", "high potential
incident", "dangerous incident". That is the regulator's own severity judgement, so the
basis is ``regulator_class`` and the map is :data:`AU_REGULATOR_SEVERITY`.

Neither loader will invent a number.
:func:`~trappoint_recall.corpora.model.infer_severity` raises, an unmapped classification
is dropped with a count, and an alert that carries neither a casualty count nor a
recognised classification does not become a record. A safety alert without a severity is
still useful reading; it is not usable ground truth, and the difference is the whole
point.

Licence note, which is not the same for the two corpora
--------------------------------------------------------
CSB material is US federal work product. Australian state-regulator material is Crown
copyright and is generally licensed CC-BY, but per-jurisdiction terms differ. The fetch
script records the licence per source and this package refuses to treat provenance as
optional — see :mod:`trappoint_recall.corpora.provenance`. Neither corpus may reach the
demo tenant regardless of licence, because the constraint there is not copyright.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from datetime import UTC, datetime, timedelta
from typing import Final

from trappoint_recall.corpora.model import (
    CodedFields,
    EventRecord,
    EventRecordSet,
    LoadReport,
    hazard_energy_for,
)
from trappoint_recall.corpora.provenance import FixtureProvenance

__all__ = [
    "AU_REGULATOR_SEVERITY",
    "CASUALTY_SEVERITY",
    "CSB_REPORT_FIELDS",
    "CsbFormatError",
    "RegulatorAlertFormatError",
    "load_au_regulator_alerts",
    "load_csb_reports",
    "parse_csb_report",
    "parse_regulator_alert",
]

CASUALTY_SEVERITY: Final[Mapping[str, int]] = {
    # Not a map from a code but from a count; the keys are the count buckets the CSB's own
    # incident summary distinguishes. A count is a coded field: the agency counted.
    "fatalities>=1": 5,
    "serious_injuries>=1": 4,
    "injuries>=1": 3,
    "none": 1,
}

AU_REGULATOR_SEVERITY: Final[Mapping[str, int]] = {
    # Classification vocabulary published by NSW Resources Regulator, Queensland RSHQ and
    # WA DMIRS, normalised. Transcribed from published guidance; UNVERIFIED against a live
    # download from this machine. An unrecognised classification is dropped and counted.
    "fatality": 5,
    "fatal accident": 5,
    "death": 5,
    "permanent disabling injury": 4,
    "serious injury": 4,
    "serious accident": 4,
    "high potential incident": 3,
    "significant incident": 3,
    "dangerous incident": 3,
    "notifiable incident": 2,
    "reportable incident": 2,
    "safety alert": 1,
    "safety bulletin": 1,
    "weekly incident summary": 1,
}


class CsbFormatError(ValueError):
    """Raised when a CSB report is missing a field this loader will not guess."""


class RegulatorAlertFormatError(ValueError):
    """Raised when a regulator alert carries no usable severity classification."""


CSB_REPORT_FIELDS: Final[Mapping[str, tuple[str, ...]]] = {
    "incident_date": ("Incident Date", "Date of Incident", "Accident Date"),
    "report_date": ("Report Date", "Date of Report", "Published"),
    "location": ("Location", "Facility", "Site"),
    "classification": ("Incident Type", "Accident Classification", "Classification"),
    "injury_source": ("Source", "Source of Injury", "Release Source"),
    "equipment": ("Equipment", "Unit", "Process Unit"),
    "fatalities": ("Fatalities", "Deaths"),
    "serious_injuries": ("Serious Injuries", "Severe Injuries"),
    "injuries": ("Injuries", "Injured"),
}

_LABEL_RE: Final = re.compile(r"^\s*([A-Za-z][A-Za-z ./'-]{2,48}?)\s*:\s*(.+?)\s*$")
_SECTION_RE: Final = re.compile(r"^\s*([A-Z][A-Z '/&-]{3,60})\s*:?\s*$")
_WORK_SECTIONS: Final[tuple[str, ...]] = (
    "INCIDENT DESCRIPTION",
    "DESCRIPTION OF THE INCIDENT",
    "WHAT HAPPENED",
    "THE INCIDENT",
)
_DATE_FORMATS: Final[tuple[str, ...]] = ("%Y-%m-%d", "%m/%d/%Y", "%d/%m/%Y", "%d %B %Y")


def _normalise(text: str) -> str:
    out: list[str] = []
    previous_space = False
    for char in text.strip().lower():
        if char.isalnum():
            out.append(char)
            previous_space = False
        elif not previous_space:
            out.append(" ")
            previous_space = True
    return "".join(out).strip()


def _slug(text: str) -> str:
    normalised = _normalise(text)
    return normalised.replace(" ", "-") if normalised else "unspecified"


def _parse_date(raw: str | None) -> datetime | None:
    if not raw:
        return None
    text = raw.strip()
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(text, fmt).replace(tzinfo=UTC)
        except ValueError:
            continue
    return None


def _labels(text: str) -> dict[str, str]:
    found: dict[str, str] = {}
    for line in text.splitlines():
        match = _LABEL_RE.match(line)
        if match:
            found[_normalise(match.group(1))] = match.group(2).strip()
    return found


def _field(found: Mapping[str, str], spec: Mapping[str, tuple[str, ...]], key: str) -> str | None:
    for label in spec[key]:
        value = found.get(_normalise(label))
        if value:
            return value
    return None


def _int_field(found: Mapping[str, str], key: str) -> int | None:
    raw = _field(found, CSB_REPORT_FIELDS, key)
    if raw is None:
        return None
    digits = re.sub(r"[^0-9]", "", raw)
    return int(digits) if digits else None


def _section(text: str, names: Iterable[str]) -> str:
    wanted = {n.upper() for n in names}
    body: list[str] = []
    capturing = False
    for line in text.splitlines():
        match = _SECTION_RE.match(line)
        if match:
            heading = " ".join(match.group(1).split()).upper().rstrip(":")
            capturing = heading in wanted
            continue
        if capturing:
            body.append(line)
    return "\n".join(body).strip()


def parse_csb_report(
    text: str,
    *,
    external_ref: str,
    provenance: FixtureProvenance,
    corpus_commit_at: datetime,
    default_report_lag: timedelta = timedelta(days=365),
) -> EventRecord:
    """Parse a CSB investigation report's extracted text.

    Severity is taken from the casualty counts in the incident summary — a count the
    agency published — through :data:`CASUALTY_SEVERITY`, basis ``coded_field``.

    Raises:
        CsbFormatError: when the classification, the date or the casualty counts are
            absent. A report with no casualty line and no classification carries no
            severity anyone wrote down, and this loader will not supply one.
    """
    if corpus_commit_at.tzinfo is None:
        raise ValueError("corpus_commit_at must be timezone-aware")
    found = _labels(text)
    classification = _field(found, CSB_REPORT_FIELDS, "classification")
    if not classification:
        raise CsbFormatError(f"{external_ref}: no incident type / classification label")
    hazard = hazard_energy_for(classification)
    if hazard is None:
        raise CsbFormatError(
            f"{external_ref}: classification {classification!r} is not in "
            "ACCIDENT_CLASS_HAZARD_ENERGY; add it to the published table or drop the record"
        )
    occurred = _parse_date(_field(found, CSB_REPORT_FIELDS, "incident_date"))
    if occurred is None:
        raise CsbFormatError(f"{external_ref}: unparseable or absent incident date")
    reported = _parse_date(_field(found, CSB_REPORT_FIELDS, "report_date"))
    if reported is None or reported < occurred:
        reported = occurred + default_report_lag

    fatalities = _int_field(found, "fatalities")
    serious = _int_field(found, "serious_injuries")
    injuries = _int_field(found, "injuries")
    if fatalities is None and serious is None and injuries is None:
        raise CsbFormatError(
            f"{external_ref}: no casualty counts. Severity would have to be inferred from "
            "the prose, which is refused (ARCHITECTURE 5.4 CHECK model_cannot_arm)."
        )
    if fatalities:
        severity = CASUALTY_SEVERITY["fatalities>=1"]
    elif serious:
        severity = CASUALTY_SEVERITY["serious_injuries>=1"]
    elif injuries:
        severity = CASUALTY_SEVERITY["injuries>=1"]
    else:
        severity = CASUALTY_SEVERITY["none"]

    description = _section(text, _WORK_SECTIONS)
    location = _field(found, CSB_REPORT_FIELDS, "location")
    equipment = _field(found, CSB_REPORT_FIELDS, "equipment")

    return EventRecord(
        external_ref=external_ref,
        source="csb_report",
        occurred_at=occurred,
        ingested_at=reported,
        corpus_commit_at=max(corpus_commit_at, reported),
        title=f"{classification} — {location or external_ref}",
        narrative=text.strip(),
        work_description=description or None,
        coded=CodedFields(
            accident_classification=classification,
            injury_source=_field(found, CSB_REPORT_FIELDS, "injury_source") or "unspecified",
            mining_method=None,
            equipment=equipment,
            subunit=location,
            degree_of_injury=(
                f"fatalities={fatalities or 0};serious={serious or 0};injuries={injuries or 0}"
            ),
        ),
        hazard_energy=hazard,
        severity_actual=severity,
        severity_basis="coded_field",
        site_ref=f"PLANT-{_slug(location or external_ref)}",
        activity_path=f"/process/{_slug(equipment or 'unit')}/{_slug(classification)}",
        asset_class=_slug(equipment or "unspecified"),
        citations=(),
        narrative_truncated=False,
        provenance=provenance,
    )


def load_csb_reports(
    rows: Iterable[Mapping[str, object]],
    *,
    provenance: FixtureProvenance,
    corpus_commit_at: datetime,
    strict: bool = False,
) -> EventRecordSet:
    """Load CSB reports from ``{external_ref, text, related?}`` envelopes."""
    records: list[EventRecord] = []
    dropped: dict[str, int] = {}
    n_read = 0
    for row in rows:
        n_read += 1
        ref = str(row.get("external_ref", "")).strip()
        text = str(row.get("text", ""))
        if not ref or not text.strip():
            dropped["empty_envelope"] = dropped.get("empty_envelope", 0) + 1
            continue
        related_raw = row.get("related", ())
        related = (
            tuple(str(x) for x in related_raw) if isinstance(related_raw, (list, tuple)) else ()
        )
        try:
            record = parse_csb_report(
                text,
                external_ref=ref,
                provenance=provenance,
                corpus_commit_at=corpus_commit_at,
            )
        except CsbFormatError as exc:
            if strict:
                raise
            reason = _csb_drop_reason(str(exc))
            dropped[reason] = dropped.get(reason, 0) + 1
            continue
        records.append(record.model_copy(update={"citations": related}))
    return EventRecordSet.build(
        records,
        LoadReport(source="csb_report", n_read=n_read, n_kept=len(records), dropped=dropped),
    )


def _csb_drop_reason(message: str) -> str:
    lowered = message.lower()
    if "casualty" in lowered:
        return "no_casualty_counts"
    if "classification" in lowered and "hazard" in lowered:
        return "unmapped_hazard_energy"
    if "classification" in lowered:
        return "no_classification"
    if "date" in lowered:
        return "unparseable_date"
    return "unparseable_report"


# --------------------------------------------------------------------------------------
# Australian state-regulator safety alerts
# --------------------------------------------------------------------------------------


def parse_regulator_alert(
    payload: Mapping[str, object],
    *,
    provenance: FixtureProvenance,
    corpus_commit_at: datetime,
    publication_lag: timedelta = timedelta(days=21),
) -> EventRecord:
    """Parse one state-regulator safety alert.

    Alerts are published as structured records rather than long documents, so the
    envelope carries the regulator's own fields verbatim:
    ``external_ref``, ``jurisdiction``, ``classification``, ``incident_type``,
    ``occurred_at``, ``published_at``, ``title``, ``text``, ``equipment``, ``site``,
    ``activity``, and optionally ``related``.

    Severity comes from ``classification`` through :data:`AU_REGULATOR_SEVERITY`, basis
    ``regulator_class``.

    Raises:
        RegulatorAlertFormatError: when the classification is absent or unrecognised, or
            when the incident type does not map to a hazard energy class.
    """
    if corpus_commit_at.tzinfo is None:
        raise ValueError("corpus_commit_at must be timezone-aware")
    ref = str(payload.get("external_ref", "")).strip()
    if not ref:
        raise RegulatorAlertFormatError("alert carries no external_ref")
    classification = str(payload.get("classification", "")).strip()
    severity = AU_REGULATOR_SEVERITY.get(_normalise(classification))
    if severity is None:
        raise RegulatorAlertFormatError(
            f"{ref}: classification {classification!r} is not in AU_REGULATOR_SEVERITY. "
            "A safety alert without a regulator classification is worth reading and is "
            "not usable ground truth; it is dropped rather than rated."
        )
    incident_type = str(payload.get("incident_type", "")).strip() or classification
    hazard = hazard_energy_for(incident_type)
    if hazard is None:
        raise RegulatorAlertFormatError(
            f"{ref}: incident type {incident_type!r} is not in ACCIDENT_CLASS_HAZARD_ENERGY"
        )
    occurred = _parse_date(str(payload.get("occurred_at", "")))
    if occurred is None:
        raise RegulatorAlertFormatError(f"{ref}: unparseable or absent occurred_at")
    published = _parse_date(str(payload.get("published_at", "")))
    if published is None or published < occurred:
        published = occurred + publication_lag
    text = str(payload.get("text", "")).strip()
    if not text:
        raise RegulatorAlertFormatError(f"{ref}: empty alert text")
    equipment = str(payload.get("equipment", "")).strip() or None
    site = str(payload.get("site", "")).strip() or ref
    activity = str(payload.get("activity", "")).strip() or incident_type
    related_raw = payload.get("related", ())
    related = tuple(str(x) for x in related_raw) if isinstance(related_raw, (list, tuple)) else ()

    return EventRecord(
        external_ref=ref,
        source="au_regulator_alert",
        occurred_at=occurred,
        ingested_at=published,
        corpus_commit_at=max(corpus_commit_at, published),
        title=str(payload.get("title", "")).strip() or f"{classification} — {incident_type}",
        narrative=text,
        work_description=text,
        coded=CodedFields(
            accident_classification=incident_type,
            injury_source=str(payload.get("injury_source", "")).strip() or "unspecified",
            mining_method=str(payload.get("mining_method", "")).strip() or None,
            equipment=equipment,
            subunit=str(payload.get("jurisdiction", "")).strip() or None,
            degree_of_injury=classification,
        ),
        hazard_energy=hazard,
        severity_actual=severity,
        severity_basis="regulator_class",
        site_ref=f"SITE-{_slug(site)}",
        activity_path=f"/{_slug(str(payload.get('jurisdiction', 'au')))}/{_slug(activity)}",
        asset_class=_slug(equipment or "unspecified"),
        citations=related,
        narrative_truncated=False,
        provenance=provenance,
    )


def load_au_regulator_alerts(
    rows: Iterable[Mapping[str, object]],
    *,
    provenance: FixtureProvenance,
    corpus_commit_at: datetime,
    strict: bool = False,
) -> EventRecordSet:
    """Load state-regulator alerts, dropping and counting anything unrated."""
    records: list[EventRecord] = []
    dropped: dict[str, int] = {}
    n_read = 0
    for row in rows:
        n_read += 1
        try:
            records.append(
                parse_regulator_alert(row, provenance=provenance, corpus_commit_at=corpus_commit_at)
            )
        except RegulatorAlertFormatError as exc:
            if strict:
                raise
            reason = _alert_drop_reason(str(exc))
            dropped[reason] = dropped.get(reason, 0) + 1
    return EventRecordSet.build(
        records,
        LoadReport(
            source="au_regulator_alert", n_read=n_read, n_kept=len(records), dropped=dropped
        ),
    )


def _alert_drop_reason(message: str) -> str:
    lowered = message.lower()
    if "au_regulator_severity" in lowered:
        return "unmapped_regulator_class"
    if "hazard" in lowered:
        return "unmapped_hazard_energy"
    if "occurred_at" in lowered:
        return "unparseable_date"
    if "empty alert text" in lowered:
        return "empty_text"
    return "unparseable_alert"
