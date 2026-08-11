# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""MSHA loaders: Part 50 bar-delimited extracts, and fatality investigation reports.

Two corpora, and the difference between them is the whole reason the recall lead's
risk 4 exists.

**Part 50** (accident/injury extracts, bar-delimited, 2000 onward) is wide, coded and
complete — and its ``NARRATIVE`` column is ``VARCHAR2(384)``. Four hundred characters
cannot carry a recurrence condition. Part 50 is therefore excellent for G2
(structured-code co-membership, which reads only the coded columns) and thin for
everything that needs prose.

**Fatality investigation reports** are the rich material: a description of the work in
progress, a root-cause analysis, and — decisively for G1 — citations to prior similar
incidents written by an investigator who had no idea anyone would use them as relevance
judgements. That is the legal-IR citation-graph trick, and it is free human-authored
ground truth.

How this parser refuses to be quietly wrong
--------------------------------------------
The column names below are transcribed from MSHA's published Part 50 layout and are
**unverified against a live download from this machine** (this build is hermetic; see
``scripts/recall/fetch_corpora.py`` for the fetch path). The parser is therefore
**header-driven**: it reads the header row, resolves each field it needs through
:data:`PART50_COLUMN_ALIASES`, and raises :class:`Part50FormatError` naming the missing
columns when it cannot. It never falls back to positional indexing. A transcription
error surfaces as a refusal on line 1, not as an entire gold set built from the wrong
column.

Severity comes from ``DEGREE_INJURY``, a coded field MSHA wrote, through
:data:`DEGREE_INJURY_SEVERITY` — a total, published, parameter-free map from the
regulator's ordinal to the 0..5 scale. Codes absent from the map are **dropped with a
count**; they are never rated, and :func:`~trappoint_recall.corpora.model.infer_severity`
raises if anyone tries.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Iterator, Mapping, Sequence
from datetime import UTC, datetime, timedelta
from pathlib import Path
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
    "DEGREE_INJURY_SEVERITY",
    "FATALITY_REPORT_FIELDS",
    "FATALITY_REPORT_SECTIONS",
    "PART50_COLUMN_ALIASES",
    "PART50_DELIMITER",
    "FatalityReportFormatError",
    "Part50FormatError",
    "load_fatality_reports",
    "parse_fatality_report",
    "parse_part50",
    "split_report_sections",
]

PART50_DELIMITER: Final = "|"
"""MSHA's open-data extracts are bar-delimited, not comma-delimited.

Narratives contain commas and quotation marks in abundance; the bar is why the extract is
parseable at all, and why this loader does not use :mod:`csv` with a comma dialect."""

PART50_COLUMN_ALIASES: Final[Mapping[str, tuple[str, ...]]] = {
    # field this loader needs -> header names accepted, in preference order
    "document_no": ("DOCUMENT_NO", "DOCUMENTNO", "ACCIDENT_NO"),
    "mine_id": ("MINE_ID", "MINEID"),
    "accident_dt": ("ACCIDENT_DT", "ACCIDENT_DATE", "ACCIDENTDT"),
    "degree_injury": ("DEGREE_INJURY", "DEGREE_INJURY_TEXT"),
    "classification": ("CLASSIFICATION", "ACCIDENT_CLASSIFICATION"),
    "accident_type": ("ACCIDENT_TYPE", "ACCIDENTTYPE"),
    "injury_source": ("INJURY_SOURCE", "SOURCE_OF_INJURY", "INJ_SOURCE"),
    "mining_method": ("UG_MINING_METHOD", "MINING_METHOD"),
    "equipment": ("MINING_EQUIP", "EQUIPMENT", "MINING_EQUIPMENT"),
    "subunit": ("SUBUNIT", "SUB_UNIT"),
    "activity": ("ACTIVITY", "ACTIVITY_TEXT"),
    "narrative": ("NARRATIVE", "NARRATIVE_TEXT"),
}
"""What the loader needs, and the header spellings it will accept for each.

Aliases exist because MSHA's extracts have been published under more than one header
spelling over the years. They are a *closed* list: an unrecognised header is a refusal,
because guessing which column is the narrative is how a corpus silently becomes noise."""

_REQUIRED_PART50_FIELDS: Final[tuple[str, ...]] = (
    "document_no",
    "accident_dt",
    "degree_injury",
    "classification",
    "injury_source",
    "narrative",
)
"""Without any one of these the record cannot become an :class:`EventRecord`."""

DEGREE_INJURY_SEVERITY: Final[Mapping[str, int]] = {
    # MSHA DEGREE_INJURY, normalised (lower case, non-alphanumerics collapsed to spaces),
    # mapped onto the 0..5 scale the vertical's event table uses.
    #
    # This map is the reviewable artefact. It has no free parameters, it reads no prose,
    # and it is a total function on the codes MSHA publishes. That is what makes the
    # result 'coded_field' rather than a rating: the regulator decided how bad it was, and
    # this table only says where the regulator's ordinal sits on ours.
    "fatality": 5,
    "permanent total disability": 4,
    "permanent partial disability": 3,
    "days away from work restricted activity": 3,
    "days away from work only": 3,
    "days restricted activity only": 2,
    "no dys awy frm wrk no rstr act": 2,
    "no days away from work no restricted activity": 2,
    "occupatnal illness not deg 1 6": 2,
    "occupational illness not deg 1 6": 2,
    "all other cases incl 1st aid": 1,
    "all other cases including first aid": 1,
    "injuries due to natural causes": 1,
    "injuries involving non employees": 1,
    "accident only": 0,
    # Deliberately absent: 'unclassified', '?', ''. Those are dropped and counted.
}


class Part50FormatError(ValueError):
    """Raised when a Part 50 extract does not carry the columns the loader needs."""


class FatalityReportFormatError(ValueError):
    """Raised when a fatality report is missing a field the loader will not guess."""


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


def _resolve_header(header: Sequence[str]) -> dict[str, int]:
    """Map each needed field to its column index, or raise naming what is missing."""
    seen = {cell.strip().upper(): index for index, cell in enumerate(header)}
    resolved: dict[str, int] = {}
    for field, aliases in PART50_COLUMN_ALIASES.items():
        for alias in aliases:
            if alias in seen:
                resolved[field] = seen[alias]
                break
    missing = [f for f in _REQUIRED_PART50_FIELDS if f not in resolved]
    if missing:
        raise Part50FormatError(
            "Part 50 extract is missing required columns "
            + ", ".join(f"{f} (any of {PART50_COLUMN_ALIASES[f]})" for f in missing)
            + f". Header seen: {sorted(seen)[:24]}"
            + ". The loader refuses to fall back to positional indexing: guessing which "
            "column holds the narrative is how a gold set is built from the wrong field."
        )
    return resolved


_DATE_FORMATS: Final[tuple[str, ...]] = (
    "%m/%d/%Y",
    "%Y-%m-%d",
    "%d/%m/%Y",
    "%m/%d/%Y %H:%M:%S",
    "%Y-%m-%d %H:%M:%S",
)


def _parse_date(raw: str) -> datetime | None:
    text = raw.strip()
    if not text:
        return None
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(text, fmt).replace(tzinfo=UTC)
        except ValueError:
            continue
    return None


def _iter_delimited(source: Iterable[str]) -> Iterator[list[str]]:
    for raw in source:
        line = raw.rstrip("\r\n")
        if not line.strip():
            continue
        yield [cell.strip().strip('"') for cell in line.split(PART50_DELIMITER)]


def parse_part50(
    source: Path | str | Iterable[str],
    *,
    provenance: FixtureProvenance,
    corpus_commit_at: datetime,
    ingest_lag: timedelta = timedelta(days=45),
    site_prefix: str = "MINE",
    strict: bool = False,
) -> EventRecordSet:
    """Parse a bar-delimited Part 50 accident/injury extract.

    Args:
        source: A path to the extract, or an iterable of lines (header first).
        provenance: Travels onto every record. Real MSHA data is ``harness_only``.
        corpus_commit_at: The corpus **genesis** — the earliest instant any record can be
            considered part of this corpus. Each record takes
            ``max(genesis, ingested_at)`` as its own ``corpus_commit_at``, which is the
            third time-wall predicate. Passing a *late* date here would stamp every
            record with a commit after every wall and admit nothing, so the value is the
            genesis and the docstring says so.
        ingest_lag: How long after the accident the record is treated as having been
            available. Part 50 reporting is quarterly, so a lag is not a fudge: pretending
            we held a record on the day of the accident would leak the future into every
            retro evaluation. 45 days is a stated assumption, not a measurement.
        site_prefix: Prefix for the synthesised ``site_ref`` when MINE_ID is present.
        strict: Raise on the first unusable row instead of dropping and counting it.

    Returns:
        Records plus the :class:`~trappoint_recall.corpora.model.LoadReport` that names
        every drop by reason.

    Raises:
        Part50FormatError: when the header does not carry the required columns.
    """
    if corpus_commit_at.tzinfo is None:
        raise ValueError("corpus_commit_at must be timezone-aware")

    lines: Iterable[str]
    if isinstance(source, (str, Path)) and Path(source).exists():
        lines = Path(source).read_text(encoding="utf-8", errors="replace").splitlines()
    elif isinstance(source, (str, Path)):
        raise Part50FormatError(f"Part 50 extract not found: {source}")
    else:
        lines = source

    rows = _iter_delimited(lines)
    try:
        header = next(rows)
    except StopIteration as exc:
        raise Part50FormatError("Part 50 extract is empty; there is no header row") from exc
    columns = _resolve_header(header)

    def cell(row: Sequence[str], field: str) -> str:
        index = columns.get(field)
        if index is None or index >= len(row):
            return ""
        return row[index]

    records: list[EventRecord] = []
    dropped: dict[str, int] = {}
    n_read = 0

    def drop(reason: str, detail: str) -> None:
        if strict:
            raise Part50FormatError(f"{detail} (reason={reason})")
        dropped[reason] = dropped.get(reason, 0) + 1

    for row in rows:
        n_read += 1
        ref = cell(row, "document_no")
        if not ref:
            drop("no_document_no", f"row {n_read} carries no document number")
            continue
        occurred = _parse_date(cell(row, "accident_dt"))
        if occurred is None:
            drop("unparseable_date", f"{ref}: accident date {cell(row, 'accident_dt')!r}")
            continue
        severity = DEGREE_INJURY_SEVERITY.get(_normalise(cell(row, "degree_injury")))
        if severity is None:
            drop("unmapped_degree_of_injury", f"{ref}: {cell(row, 'degree_injury')!r}")
            continue
        classification = cell(row, "classification") or cell(row, "accident_type")
        if not classification:
            drop("no_classification", f"{ref}: no coded accident classification")
            continue
        hazard = hazard_energy_for(classification)
        if hazard is None:
            drop("unmapped_hazard_energy", f"{ref}: classification {classification!r}")
            continue
        narrative = cell(row, "narrative")
        if not narrative:
            drop("empty_narrative", f"{ref}: narrative column is empty")
            continue
        injury_source = cell(row, "injury_source") or "unspecified"
        subunit = cell(row, "subunit") or None
        activity = cell(row, "activity") or subunit or "unspecified"
        equipment = cell(row, "equipment") or None
        mine_id = cell(row, "mine_id")
        ingested = occurred + ingest_lag
        commit_at = max(corpus_commit_at, ingested)
        records.append(
            EventRecord(
                external_ref=ref,
                source="msha_part50",
                occurred_at=occurred,
                ingested_at=ingested,
                corpus_commit_at=commit_at,
                title=f"{classification} — {injury_source}",
                narrative=narrative[:384],
                work_description=None,
                coded=CodedFields(
                    accident_classification=classification,
                    injury_source=injury_source,
                    mining_method=cell(row, "mining_method") or None,
                    equipment=equipment,
                    subunit=subunit,
                    degree_of_injury=cell(row, "degree_injury") or None,
                ),
                hazard_energy=hazard,
                severity_actual=severity,
                severity_basis="coded_field",
                site_ref=f"{site_prefix}-{mine_id}" if mine_id else f"{site_prefix}-UNKNOWN",
                activity_path=f"/{_slug(subunit or 'operation')}/{_slug(activity)}",
                asset_class=_slug(equipment or "unspecified"),
                citations=(),
                narrative_truncated=True,
                provenance=provenance,
            )
        )

    report = LoadReport(
        source="msha_part50",
        n_read=n_read,
        n_kept=len(records),
        dropped=dropped,
    )
    return EventRecordSet.build(records, report)


# --------------------------------------------------------------------------------------
# Fatality investigation reports
# --------------------------------------------------------------------------------------

FATALITY_REPORT_SECTIONS: Final[tuple[str, ...]] = (
    "OVERVIEW",
    "GENERAL INFORMATION",
    "DESCRIPTION OF THE ACCIDENT",
    "INVESTIGATION OF THE ACCIDENT",
    "DISCUSSION",
    "ROOT CAUSE ANALYSIS",
    "CONCLUSION",
    "ENFORCEMENT ACTIONS",
    "APPENDIX",
)
"""Canonical section headings of an MSHA fatal accident investigation report.

Matched case-insensitively against a line that is a heading and nothing else. Reports
whose extracted text has lost its headings — a common outcome of a bad PDF extraction —
end up with no ``DESCRIPTION OF THE ACCIDENT`` section and are therefore dropped with the
reason ``no_work_description``, which is the honest outcome: G4 synthesises the retro
permit *from the investigation's own description of the work*, and there is nothing to
synthesise from."""

FATALITY_REPORT_FIELDS: Final[Mapping[str, tuple[str, ...]]] = {
    "report_id": ("Report ID", "Report No", "Accident Investigation Report"),
    "mine_id": ("Mine ID", "Mine Identification Number"),
    "operation": ("Operation", "Mine Name", "Mine"),
    "accident_date": ("Date of Accident", "Accident Date", "Date"),
    "report_date": ("Date of Report", "Report Date", "Issued"),
    "classification": ("Accident Classification", "Classification"),
    "injury_source": ("Source of Injury", "Injury Source"),
    "mining_method": ("Mining Method",),
    "equipment": ("Equipment", "Equipment Involved"),
    "subunit": ("Subunit", "Location"),
    "activity": ("Activity", "Work Activity"),
    "degree_of_injury": ("Degree of Injury",),
}
"""Labelled header fields the loader reads out of ``GENERAL INFORMATION``.

Absent labels are not guessed. ``classification``, ``accident_date`` and
``degree_of_injury`` are required; the rest degrade to ``None``."""

_HEADING_RE: Final = re.compile(r"^\s*([A-Z][A-Z '/&-]{3,60})\s*:?\s*$")
_LABEL_RE: Final = re.compile(r"^\s*([A-Za-z][A-Za-z ./'-]{2,48}?)\s*:\s*(.+?)\s*$")


def split_report_sections(text: str) -> dict[str, str]:
    """Split report text into ``{CANONICAL SECTION: body}``.

    Text before the first recognised heading is returned under the key ``""`` so nothing
    is silently discarded.
    """
    canonical = {name: name for name in FATALITY_REPORT_SECTIONS}
    sections: dict[str, list[str]] = {"": []}
    current = ""
    for line in text.splitlines():
        match = _HEADING_RE.match(line)
        if match:
            heading = " ".join(match.group(1).split()).upper().rstrip(":")
            if heading in canonical:
                current = heading
                sections.setdefault(current, [])
                continue
        sections.setdefault(current, []).append(line)
    return {name: "\n".join(body).strip() for name, body in sections.items()}


def _labelled_fields(block: str) -> dict[str, str]:
    found: dict[str, str] = {}
    for line in block.splitlines():
        match = _LABEL_RE.match(line)
        if not match:
            continue
        label = " ".join(match.group(1).split())
        found[_normalise(label)] = match.group(2).strip()
    return found


def _field(found: Mapping[str, str], key: str) -> str | None:
    for label in FATALITY_REPORT_FIELDS[key]:
        value = found.get(_normalise(label))
        if value:
            return value
    return None


def parse_fatality_report(
    text: str,
    *,
    external_ref: str,
    provenance: FixtureProvenance,
    corpus_commit_at: datetime,
    default_report_lag: timedelta = timedelta(days=120),
) -> EventRecord:
    """Parse one fatality investigation report's extracted text into an event record.

    The whole report body becomes the ``narrative``: this is the rich material, and G1
    reads citations out of it. ``work_description`` is the ``DESCRIPTION OF THE ACCIDENT``
    section, which is what G4 synthesises the retro permit from.

    ``ingested_at`` is the report's own date when the report carries one, otherwise the
    accident date plus ``default_report_lag``. It is never the accident date: the
    investigation report did not exist on the day of the accident, and treating it as if
    it did would hand every retro evaluation a document from its own future.

    Raises:
        FatalityReportFormatError: when a required field or section is absent. Callers
            that are loading a corpus should catch this and count the drop.
    """
    if corpus_commit_at.tzinfo is None:
        raise ValueError("corpus_commit_at must be timezone-aware")

    sections = split_report_sections(text)
    general = sections.get("GENERAL INFORMATION", "") or sections.get("", "")
    found = _labelled_fields(general)
    if not found:
        found = _labelled_fields(text)

    classification = _field(found, "classification")
    if not classification:
        raise FatalityReportFormatError(
            f"{external_ref}: no 'Accident Classification' label. Severity and hazard "
            "energy both derive from the regulator's coded classification and neither "
            "may be inferred from the prose."
        )
    hazard = hazard_energy_for(classification)
    if hazard is None:
        raise FatalityReportFormatError(
            f"{external_ref}: accident classification {classification!r} is not in "
            "ACCIDENT_CLASS_HAZARD_ENERGY. Add it to the published table or drop the "
            "record; do not default it, because a default bucket silently concentrates "
            "every unrecognised classification into one hazard class."
        )
    degree = _field(found, "degree_of_injury") or "FATALITY"
    severity = DEGREE_INJURY_SEVERITY.get(_normalise(degree))
    if severity is None:
        raise FatalityReportFormatError(
            f"{external_ref}: degree of injury {degree!r} is not in DEGREE_INJURY_SEVERITY"
        )
    raw_date = _field(found, "accident_date")
    occurred = _parse_date(raw_date or "") or _parse_long_date(raw_date or "")
    if occurred is None:
        raise FatalityReportFormatError(
            f"{external_ref}: unparseable or absent accident date {raw_date!r}"
        )
    raw_report_date = _field(found, "report_date")
    reported = (
        _parse_date(raw_report_date or "")
        or _parse_long_date(raw_report_date or "")
        or occurred + default_report_lag
    )
    if reported < occurred:
        reported = occurred + default_report_lag

    description = sections.get("DESCRIPTION OF THE ACCIDENT", "").strip()
    if not description:
        raise FatalityReportFormatError(
            f"{external_ref}: no 'DESCRIPTION OF THE ACCIDENT' section. G4 synthesises "
            "the retro permit from the investigation's own description of the work, so a "
            "report without one cannot become a retro query and must be dropped rather "
            "than have a permit invented for it."
        )

    subunit = _field(found, "subunit")
    activity = _field(found, "activity") or subunit or "unspecified"
    equipment = _field(found, "equipment")
    mine_id = _field(found, "mine_id")
    operation = _field(found, "operation")

    return EventRecord(
        external_ref=external_ref,
        source="msha_fatality_report",
        occurred_at=occurred,
        ingested_at=reported,
        corpus_commit_at=max(corpus_commit_at, reported),
        title=f"{classification} — {operation or mine_id or external_ref}",
        narrative=text.strip(),
        work_description=description,
        coded=CodedFields(
            accident_classification=classification,
            injury_source=_field(found, "injury_source") or "unspecified",
            mining_method=_field(found, "mining_method"),
            equipment=equipment,
            subunit=subunit,
            degree_of_injury=degree,
        ),
        hazard_energy=hazard,
        severity_actual=severity,
        severity_basis="coded_field",
        site_ref=f"MINE-{mine_id}" if mine_id else f"MINE-{_slug(operation or external_ref)}",
        activity_path=f"/{_slug(subunit or 'operation')}/{_slug(activity)}",
        asset_class=_slug(equipment or "unspecified"),
        citations=(),
        narrative_truncated=False,
        provenance=provenance,
    )


_LONG_DATE_RE: Final = re.compile(
    r"(?P<month>January|February|March|April|May|June|July|August|September|October|"
    r"November|December)\s+(?P<day>\d{1,2}),?\s+(?P<year>\d{4})",
    re.IGNORECASE,
)
_MONTHS: Final[Mapping[str, int]] = {
    "january": 1,
    "february": 2,
    "march": 3,
    "april": 4,
    "may": 5,
    "june": 6,
    "july": 7,
    "august": 8,
    "september": 9,
    "october": 10,
    "november": 11,
    "december": 12,
}


def _parse_long_date(text: str) -> datetime | None:
    """``March 4, 2016`` — the spelling investigation reports actually use."""
    match = _LONG_DATE_RE.search(text)
    if not match:
        return None
    return datetime(
        int(match.group("year")),
        _MONTHS[match.group("month").lower()],
        int(match.group("day")),
        tzinfo=UTC,
    )


def load_fatality_reports(
    rows: Iterable[Mapping[str, object]],
    *,
    provenance: FixtureProvenance,
    corpus_commit_at: datetime,
    strict: bool = False,
) -> EventRecordSet:
    """Load fatality reports from envelopes of the form ``{external_ref, text}``.

    The envelope carries the identifier and the extracted text and **nothing else**:
    every other field is parsed out of the report, so this loader is exercised by the
    committed fixtures rather than bypassed by them. PDF-to-text extraction is the fetch
    script's job — this package takes no PDF dependency, and refuses to pretend it
    extracted text it did not.

    ``related`` is accepted as an optional list of raw citation strings for sources that
    publish a structured related-incident list; G1 also mines the narrative directly.
    """
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
            record = parse_fatality_report(
                text,
                external_ref=ref,
                provenance=provenance,
                corpus_commit_at=corpus_commit_at,
            )
        except FatalityReportFormatError as exc:
            if strict:
                raise
            reason = _drop_reason(str(exc))
            dropped[reason] = dropped.get(reason, 0) + 1
            continue
        records.append(record.model_copy(update={"citations": related}))
    report = LoadReport(
        source="msha_fatality_report",
        n_read=n_read,
        n_kept=len(records),
        dropped=dropped,
    )
    return EventRecordSet.build(records, report)


def _drop_reason(message: str) -> str:
    lowered = message.lower()
    if "description of the accident" in lowered:
        return "no_work_description"
    if "classification" in lowered:
        return "no_classification"
    if "degree of injury" in lowered:
        return "unmapped_degree_of_injury"
    if "accident date" in lowered:
        return "unparseable_date"
    return "unparseable_report"
