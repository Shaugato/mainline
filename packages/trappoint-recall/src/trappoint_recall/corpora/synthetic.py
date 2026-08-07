# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""The synthetic replica corpus that makes CI hermetic — and why it is not the real thing.

CI has no network. The real corpora — MSHA Part 50, 30 000-odd fatality investigation
reports, CSB reports, Australian state-regulator alerts — are fetched by
``scripts/recall/fetch_corpora.py`` into a gitignored cache, and none of them may be
committed to this repository: some of it for licence reasons, all of it because a
repository is a copy and every copy of a fatality report is another place a family's worst
day can be mishandled.

So the committed fixtures are a **synthetic replica**: invented records, shaped exactly
like the real ones, generated deterministically from a seed. They are labelled
``corpus_class='synthetic_replica'`` and they are labelled ``tenant_use='harness_only'``
anyway, because a synthetic corpus that models real fatalities has no business in a demo
either.

What the replica is for, and what it is not for
------------------------------------------------
**For:** exercising the real parsers. The Part 50 fixture is bar-delimited with the real
header spelling; the fatality reports carry the real section headings and the real
labelled fields; the citations are embedded in the report prose where a real one would be.
:mod:`trappoint_recall.corpora.msha` is genuinely run against them, so a change that
breaks the parser fails CI rather than waiting for a download.

**Not for:** any claim about retrieval quality. A number measured on invented text is a
number about the generator. Every artefact built from this corpus carries
``preliminary: true`` and ``synthetic: true``, and the harness stamps both on every report
it renders.

Determinism
-----------
Every draw comes from :class:`~trappoint_recall.corpora.rng.DeterministicRandom`, a
counter-based blake2b stream, so the fixtures are byte-identical across interpreters and
years. The build script's ``--check`` mode rebuilds into a temporary directory and diffs.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Final

from trappoint_recall.corpora.rng import DeterministicRandom

__all__ = [
    "DEFAULT_SEED",
    "FAMILIES",
    "SyntheticCorpus",
    "generate",
]

DEFAULT_SEED: Final = "mainline-recall-corpora-v1"

CORPUS_GENESIS: Final = datetime(2005, 1, 1, tzinfo=UTC)
"""Earliest instant any record can belong to the corpus. Far enough back that every
record's ``corpus_commit_at`` is its own ingest instant rather than a global stamp that
would put every document on the wrong side of every wall."""

TIMELINE_START: Final = datetime(2010, 1, 11, tzinfo=UTC)
FAMILY_STRIDE_DAYS: Final = 240
"""Days between consecutive fatalities inside one family.

Comfortably larger than the 120-day investigation-report lag, so a family's earlier report
has been *published* before the next fatality happens. Without that, no fatality would
ever have an admissible precursor and G4 would be empty for a reason that looks like a
retrieval failure and is actually a fixture arithmetic error."""

REPORTS_PER_FAMILY: Final = 12
PART50_ROWS: Final = 900
CSB_REPORTS: Final = 24
AU_ALERTS: Final = 60


@dataclass(frozen=True, slots=True)
class Family:
    """One hazard-energy scenario family: the shape a whole cluster of records shares."""

    hazard: str
    classification: str
    injury_source: str
    mining_method: str
    equipment: str
    subunit: str
    activity: str
    operation: str
    mine_id: str
    work: tuple[str, ...]
    outcome: str
    control_failure: str
    root_cause: str
    recurrence: str


FAMILIES: Final[tuple[Family, ...]] = (
    Family(
        hazard="gravity",
        classification="Fall of roof or back",
        injury_source="Roof or back",
        mining_method="Room and pillar",
        equipment="Roof bolter",
        subunit="Underground",
        activity="Ground support installation",
        operation="Kestrel Ridge Mine",
        mine_id="4601731",
        work=(
            ("The crew was installing secondary ground support along the number four entry "
            "after a routine inspection identified a change in the immediate roof"),
            ("The bolter operator was advancing the machine under a section of back that had "
            "been supported on the previous shift"),
            ("Two miners were extending the supported line towards the face in order to "
            "recover a stalled continuous miner"),
        ),
        outcome="A section of the immediate roof detached and the bolter operator was struck.",
        control_failure=(
            "The exclusion zone under unsupported back was reduced by verbal agreement "
            "rather than by a revision to the ground control plan"
        ),
        root_cause=(
            "Management policies and procedures did not require a geotechnical assessment "
            "before the supported line was advanced under changed roof conditions"
        ),
        recurrence=(
            "recurs wherever a person can occupy ground under a back whose support standard "
            "has been varied without a geotechnical assessment"
        ),
    ),
    Family(
        hazard="kinetic",
        classification="Powered haulage",
        injury_source="Haulage truck",
        mining_method="Open pit",
        equipment="Haul truck",
        subunit="Surface",
        activity="Haul road operations",
        operation="Bellbird Creek Pit",
        mine_id="2200418",
        work=(
            ("A haul truck was descending the main ramp with a loaded tray toward the primary "
            "crusher at the end of the night shift"),
            ("The operator was reversing to a tip head that had been re-established after "
            "wet weather"),
            ("A light vehicle was travelling the ramp to deliver a fuel sample to the "
            "workshop"),
        ),
        outcome="Retardation was lost on the grade and the truck was struck by the trailing unit.",
        control_failure=(
            "A defect deferral was applied to a service brake circuit without an "
            "engineering assessment of the residual retardation"
        ),
        root_cause=(
            "The defect management standard permitted deferral of a braking defect on the "
            "authority of a supervisor with no engineering review"
        ),
        recurrence=(
            "recurs wherever a deferral is applied to any element of a braking or "
            "retardation system on a graded haul route"
        ),
    ),
    Family(
        hazard="electrical",
        classification="Electrical",
        injury_source="Electric current",
        mining_method="Surface",
        equipment="Switchgear",
        subunit="Surface",
        activity="Electrical maintenance",
        operation="Wandoo Processing Facility",
        mine_id="0501992",
        work=(
            ("An electrician was fault-finding on an eleven kilovolt feeder that had tripped "
            "twice during the preceding shift"),
            ("The crew was replacing a current transformer in a switchroom cubicle adjacent "
            "to a live section of busbar"),
            ("A tradesperson was proving a circuit dead before terminating a new cable into "
            "the distribution board"),
        ),
        outcome="An arc was initiated across the open cubicle and the electrician was electrocuted.",
        control_failure=(
            "Isolation was verified by indication at the panel rather than by testing at "
            "the point of work"
        ),
        root_cause=(
            "The electrical safety rules permitted verification by remote indication where "
            "the point of work was inside the arc flash boundary"
        ),
        recurrence=(
            "recurs wherever an isolation is proved by indication rather than by test at "
            "the point of work inside an arc flash boundary"
        ),
    ),
    Family(
        hazard="pressure",
        classification="Ignition or explosion of gas or dust",
        injury_source="Gas or vapour",
        mining_method="Longwall",
        equipment="Auxiliary fan",
        subunit="Underground",
        activity="Ventilation control",
        operation="Moonta Deeps Colliery",
        mine_id="1103377",
        work=(
            ("Deputies were restoring auxiliary ventilation to a development panel after a "
            "planned power outage"),
            ("The crew was recovering equipment from a sealed area that had been re-entered "
            "under a written procedure"),
            ("A fitter was replacing ducting on the auxiliary circuit while the panel was "
            "idle"),
        ),
        outcome="An accumulation ignited at the face and two miners were fatally injured.",
        control_failure=(
            "The gas monitoring action level was raised to reduce nuisance trips without a "
            "change to the ventilation management plan"
        ),
        root_cause=(
            "The ventilation management plan did not require re-validation when an alarm "
            "setpoint was altered"
        ),
        recurrence=(
            "recurs wherever a gas alarm setpoint is raised on a circuit whose ventilation "
            "management plan is not re-validated"
        ),
    ),
    Family(
        hazard="thermal",
        classification="Fire",
        injury_source="Flame",
        mining_method="Open pit",
        equipment="Excavator",
        subunit="Surface",
        activity="Mobile plant maintenance",
        operation="Nardoo Iron Operations",
        mine_id="3300514",
        work=(
            ("A maintenance crew was replacing a hydraulic hose on the boom of an excavator "
            "parked on the pit floor"),
            ("A serviceperson was refuelling a unit at the end of the shift at the field "
            "service point"),
            ("Two fitters were performing hot work on a bucket lip adjacent to the machine "
            "house"),
        ),
        outcome="Fluid contacted a hot surface, a fire developed and the serviceperson died.",
        control_failure=(
            "The fire suppression system was isolated for maintenance and the isolation was "
            "not registered against the permit"
        ),
        root_cause=(
            "The permit system did not require suppression status to be confirmed before "
            "hot work was authorised on a machine"
        ),
        recurrence=(
            "recurs wherever hot work is authorised on a machine whose fire suppression "
            "status is not confirmed on the permit"
        ),
    ),
    Family(
        hazard="chemical",
        classification="Exposure to irrespirable atmosphere",
        injury_source="Gas or vapour",
        mining_method="Underground",
        equipment="Pump",
        subunit="Underground",
        activity="Sump and drainage work",
        operation="Cobar Extension Mine",
        mine_id="6600239",
        work=(
            ("A pump attendant was clearing a blocked suction line in a drainage sump at the "
            "base of the decline"),
            ("The crew was recovering a submersible pump from a sump that had been standing "
            "for several weeks"),
            "A fitter entered the sump enclosure to reconnect the level instrument",
        ),
        outcome="The atmosphere was irrespirable and the attendant was fatally overcome.",
        control_failure=(
            "The confined space classification of the sump was removed following a change "
            "of contractor without reassessment"
        ),
        root_cause=(
            "The confined space register was maintained by the contractor and was not "
            "reconciled at handover"
        ),
        recurrence=(
            "recurs wherever a confined space classification is removed at a contractor "
            "handover without reassessment"
        ),
    ),
    Family(
        hazard="biological",
        classification="Exposure to biological agents",
        injury_source="Contaminated water",
        mining_method="Surface",
        equipment="Water treatment plant",
        subunit="Surface",
        activity="Water services maintenance",
        operation="Yallourn Tailings Facility",
        mine_id="1500803",
        work=(
            ("A services crew was cleaning a cooling tower basin that had been off line for "
            "eleven weeks"),
            ("An operator was taking a routine sample from the raw water line at the "
            "treatment plant"),
            "A contractor was replacing drift eliminators in the tower cell",
        ),
        outcome="A worker contracted a fatal infection traced to the aerosol from the basin.",
        control_failure=(
            "The biocide dosing regime was suspended during the outage and was not "
            "reinstated before the cell was disturbed"
        ),
        root_cause=(
            "The outage procedure had no step for reinstating water treatment before "
            "intrusive work on a cooling system"
        ),
        recurrence=(
            "recurs wherever intrusive work is performed on a water system whose treatment "
            "regime was suspended during an outage"
        ),
    ),
    Family(
        hazard="radiation",
        classification="Exposure to ionising radiation",
        injury_source="Radioactive source",
        mining_method="Surface",
        equipment="Density gauge",
        subunit="Mill",
        activity="Instrument maintenance",
        operation="Ranger Sands Concentrator",
        mine_id="7700645",
        work=(
            ("An instrument technician was removing a nucleonic density gauge from a slurry "
            "line during a plant shutdown"),
            ("A boilermaker was cutting a section of pipe adjacent to a gauge housing that "
            "had been tagged for removal"),
            ("The crew was relocating a source holder to a new position on the thickener "
            "underflow"),
        ),
        outcome="The shutter was open and the technician received a fatal dose.",
        control_failure=(
            "The source shutter lock was defeated to allow a calibration and the defeat was "
            "not restored before the housing was opened"
        ),
        root_cause=(
            "The radiation management plan permitted a shutter defeat without a hold point "
            "for restoration"
        ),
        recurrence=(
            "recurs wherever a source shutter interlock is defeated without a hold point "
            "requiring its restoration before intrusive work"
        ),
    ),
)

_FILLER: Final[tuple[str, ...]] = (
    ("The investigation reviewed the training records of every person engaged on the task "
    "and found that the required competencies had been recorded and were current at the "
    "time of the accident. The task instruction in use on the shift was the current "
    "revision and had been signed by each member of the crew before work commenced."),
    ("Investigators examined the maintenance history of the equipment involved and "
    "established that the scheduled services had been completed to the strategy. No "
    "outstanding corrective work order was identified against the components examined, "
    "and the condition monitoring results for the preceding period were within limits."),
    ("The investigation considered the adequacy of supervision on the shift. The supervisor "
    "held the statutory appointment required for the activity, had conducted the pre-shift "
    "briefing, and had visited the work area earlier in the shift. Communications equipment "
    "was tested and found to be serviceable throughout."),
    ("Environmental conditions were examined in detail. Ambient conditions were within the "
    "range recorded for the preceding weeks, the lighting at the work area met the "
    "requirement, and no factor arising from weather was found to have contributed to the "
    "sequence of events reconstructed by the investigation team."),
)
"""Date-free prose.

Every citation paragraph is preceded by one of these, so the two hundred characters before
a cited identifier contain no date and the anchor check reads the date that actually
belongs to the citation. A stray date upstream would corroborate the wrong record."""

_PART50_CLASSIFICATIONS: Final[tuple[tuple[str, str, str], ...]] = (
    ("Machinery", "Machine", "Conveyor"),
    ("Handling material", "Metal item", "Hand tools"),
    ("Slip or fall of person from same level", "Ground surface", "None"),
    ("Fall of face rib pillar or highwall", "Rock face", "Continuous miner"),
    ("Struck by or against", "Metal item", "Drill"),
    ("Caught in under or between", "Machine", "Conveyor"),
    ("Powered haulage", "Haulage truck", "Haul truck"),
    ("Fall of roof or back", "Roof or back", "Roof bolter"),
    ("Electrical", "Electric current", "Switchgear"),
    ("Fire", "Flame", "Excavator"),
    ("Explosives and breaking agents", "Explosive", "Charging unit"),
    ("Exposure to chemicals or toxic substances", "Chemical", "Pump"),
)

_DEGREES: Final[tuple[tuple[str, int], ...]] = (
    ("DAYS AWAY FROM WORK ONLY", 40),
    ("DAYS RESTRICTED ACTIVITY ONLY", 20),
    ("NO DYS AWY FRM WRK,NO RSTR ACT", 15),
    ("ALL OTHER CASES (INCL 1ST AID)", 12),
    ("PERMANENT PARTIAL DISABILITY", 6),
    ("ACCIDENT ONLY", 4),
    ("PERMANENT TOTAL DISABILITY", 2),
    ("UNCLASSIFIED", 1),
)
"""Degree of injury and its relative weight.

``UNCLASSIFIED`` is present deliberately: it is absent from
:data:`~trappoint_recall.corpora.msha.DEGREE_INJURY_SEVERITY`, so roughly one row in a
hundred is dropped as ``unmapped_degree_of_injury`` and the drop path is exercised by the
fixtures instead of being asserted about in a comment."""

_CSB_SCENARIOS: Final[tuple[tuple[str, str, str, str], ...]] = (
    ("Loss of containment", "Hydrocarbon", "Heat exchanger", "Hollis Bay Refinery"),
    ("Vapour cloud explosion", "Gas or vapour", "Storage sphere", "Marchmont Chemicals"),
    ("Runaway reaction", "Chemical", "Batch reactor", "Delaney Specialty Works"),
    ("Arc flash", "Electric current", "Motor control centre", "Pinewater Terminal"),
    ("Fire", "Flame", "Distillation column", "Ardmore Olefins Plant"),
)

_AU_SCENARIOS: Final[tuple[tuple[str, str, str, str, str], ...]] = (
    ("NSW", "Fall of roof or back", "Roof bolter", "Underground coal", "high potential incident"),
    ("QLD", "Powered haulage", "Haul truck", "Metalliferous open cut", "serious accident"),
    ("WA", "Electrical", "Switchgear", "Processing plant", "dangerous incident"),
    ("NSW", "Fire", "Excavator", "Open cut coal", "notifiable incident"),
    ("QLD", "Exposure to chemicals or toxic substances", "Pump", "Alumina refinery", "safety alert"),
    ("WA", "Caught in under or between", "Conveyor", "Iron ore plant", "fatality"),
    ("NSW", "Explosives and breaking agents", "Charging unit", "Quarry", "high potential incident"),
    ("QLD", "Machinery", "Drill", "Underground metalliferous", "significant incident"),
)


@dataclass(frozen=True, slots=True)
class SyntheticCorpus:
    """The generated inputs, in the exact on-disk shapes the loaders read."""

    part50_lines: tuple[str, ...]
    fatality_reports: tuple[dict[str, object], ...]
    csb_reports: tuple[dict[str, object], ...]
    au_alerts: tuple[dict[str, object], ...]
    seed: str

    def summary(self) -> Mapping[str, int]:
        return {
            "part50_rows": len(self.part50_lines) - 1,
            "fatality_reports": len(self.fatality_reports),
            "csb_reports": len(self.csb_reports),
            "au_alerts": len(self.au_alerts),
        }


def _long_date(moment: datetime) -> str:
    return f"{moment.strftime('%B')} {moment.day}, {moment.year}"


def _weighted_choice(rng: DeterministicRandom, options: Sequence[tuple[str, int]]) -> str:
    total = sum(weight for _, weight in options)
    draw = rng.below(total)
    running = 0
    for value, weight in options:
        running += weight
        if draw < running:
            return value
    return options[-1][0]  # pragma: no cover - unreachable while weights are positive


def _part50(rng: DeterministicRandom) -> tuple[tuple[str, ...], list[tuple[str, datetime]]]:
    header = (
        "DOCUMENT_NO|MINE_ID|ACCIDENT_DT|DEGREE_INJURY|CLASSIFICATION|ACCIDENT_TYPE|"
        "INJURY_SOURCE|UG_MINING_METHOD|MINING_EQUIP|SUBUNIT|ACTIVITY|NARRATIVE"
    )
    lines = [header]
    index: list[tuple[str, datetime]] = []
    start = TIMELINE_START - timedelta(days=900)
    for i in range(PART50_ROWS):
        moment = start + timedelta(days=(i * 3) % 3200, hours=rng.integer(5, 21))
        classification, injury_source, equipment = rng.choice(_PART50_CLASSIFICATIONS)
        family = rng.choice(FAMILIES)
        degree = _weighted_choice(rng, _DEGREES)
        document_no = f"21{i:05d}"
        narrative = (
            f"Employee was engaged in {family.activity.lower()} using a "
            f"{equipment.lower()} when the incident occurred. {classification} recorded. "
            f"Task was stopped and the area was made safe."
        )[:384]
        lines.append(
            "|".join(
                (
                    document_no,
                    family.mine_id,
                    moment.strftime("%m/%d/%Y"),
                    degree,
                    classification,
                    classification,
                    injury_source,
                    family.mining_method,
                    equipment,
                    family.subunit,
                    family.activity,
                    narrative,
                )
            )
        )
        index.append((document_no, moment))
    return tuple(lines), index


def _report_text(
    *,
    family: Family,
    ref: str,
    occurred: datetime,
    reported: datetime,
    citations: Sequence[tuple[str, str]],
    work: str,
    rng: DeterministicRandom,
) -> str:
    """Assemble one fatality investigation report in MSHA's published shape."""
    blocks: list[str] = [
        "UNITED STATES DEPARTMENT OF LABOR",
        "Mine Safety and Health Administration",
        "Report of Investigation",
        "",
        "GENERAL INFORMATION",
        "",
        f"Report ID: {ref}",
        f"Mine ID: {family.mine_id}",
        f"Operation: {family.operation}",
        f"Date of Accident: {_long_date(occurred)}",
        f"Date of Report: {_long_date(reported)}",
        f"Accident Classification: {family.classification}",
        f"Source of Injury: {family.injury_source}",
        f"Mining Method: {family.mining_method}",
        f"Equipment: {family.equipment}",
        f"Subunit: {family.subunit}",
        f"Activity: {family.activity}",
        "Degree of Injury: FATALITY",
        "",
        "DESCRIPTION OF THE ACCIDENT",
        "",
        (
            f"{work}. The task had been planned at the pre-shift meeting and the crew "
            f"held a current permit for {family.activity.lower()}. "
            f"{family.control_failure}. {family.outcome}"
        ),
        "",
        "INVESTIGATION OF THE ACCIDENT",
        "",
        rng.choice(_FILLER),
        "",
        "DISCUSSION",
        "",
    ]
    for identifier, cited_date in citations:
        blocks.append(rng.choice(_FILLER))
        if cited_date:
            blocks.append(
                f"Investigators reviewed prior events of the same character at this and "
                f"other operations. See Accident Investigation Report {identifier}, "
                f"{cited_date}."
            )
        else:
            blocks.append(
                f"Investigators reviewed prior events of the same character. See "
                f"{identifier}."
            )
        blocks.append("")
    blocks.extend(
        [
            "ROOT CAUSE ANALYSIS",
            "",
            f"Root cause: {family.root_cause}. Corrective action was directed accordingly.",
            "",
            "CONCLUSION",
            "",
            (
                f"The accident occurred because {family.control_failure.lower()}. The "
                f"recurrence condition {family.recurrence}."
            ),
            "",
            "ENFORCEMENT ACTIONS",
            "",
            ("Orders and citations issued as a result of this investigation are listed in "
            "the appendix to this report."),
            "",
        ]
    )
    return "\n".join(blocks)


def _fatality_reports(
    rng: DeterministicRandom, part50_index: Sequence[tuple[str, datetime]]
) -> tuple[dict[str, object], ...]:
    """Build the fatality corpus, with the citation graph G1 is mined from.

    Roughly one in four reports cites an identifier that is not in the corpus, one in six
    corroborates a real identifier with the *wrong* date, one in three carries a citation
    phrase that names no identifier at all, and every report cites itself once through its
    own ``Report ID`` line. All four are real behaviours of real reports, and each one
    lands in the resolver's drop table under its own reason, so the drop table is exercised
    by the fixtures rather than asserted about in a comment.
    """
    planned: list[tuple[Family, int, str, datetime, datetime]] = []
    for family_index, family in enumerate(FAMILIES):
        for i in range(REPORTS_PER_FAMILY):
            occurred = TIMELINE_START + timedelta(
                days=family_index * 21 + i * FAMILY_STRIDE_DAYS, hours=7 + (i % 9)
            )
            reported = occurred + timedelta(days=120)
            ref = f"FAI-{occurred.year}-{family_index * 20 + i + 1:03d}"
            planned.append((family, i, ref, occurred, reported))

    by_family: dict[str, list[tuple[str, datetime]]] = {}
    rows: list[dict[str, object]] = []
    for family, position, ref, occurred, reported in planned:
        history = by_family.setdefault(family.hazard, [])
        citations: list[tuple[str, str]] = []

        if history:
            prior_ref, prior_when = history[-1]
            citations.append((prior_ref, _long_date(prior_when)))
        if len(history) >= 2:
            older_ref, older_when = history[-2]
            wrong_date = position % 6 == 5
            citations.append(
                (
                    older_ref,
                    _long_date(older_when + timedelta(days=11 if wrong_date else 0)),
                )
            )
        earlier_part50 = [
            (doc, when) for doc, when in part50_index if when < occurred - timedelta(days=200)
        ]
        if earlier_part50:
            doc, when = earlier_part50[rng.below(len(earlier_part50))]
            citations.append((f"Document No. {doc}", _long_date(when)))
        if position % 4 == 3:
            citations.append((f"FAI-1998-{position:03d}", _long_date(occurred - timedelta(days=4000))))
        if history and position % 5 == 4:
            repeat_ref, repeat_when = history[-1]
            citations.append((repeat_ref, _long_date(repeat_when)))

        work = family.work[position % len(family.work)]
        text = _report_text(
            family=family,
            ref=ref,
            occurred=occurred,
            reported=reported,
            citations=citations,
            work=work,
            rng=rng,
        )
        if position % 3 == 2:
            text += (
                "\n\nAPPENDIX\n\n"
                "A similar fatal accident occurred at another operation of this controller "
                "and was reviewed by the investigation team.\n"
            )
        rows.append({"external_ref": ref, "text": text})
        history.append((ref, occurred))
    return tuple(rows)


def _csb_reports(rng: DeterministicRandom) -> tuple[dict[str, object], ...]:
    rows: list[dict[str, object]] = []
    for i in range(CSB_REPORTS):
        classification, injury_source, equipment, facility = _CSB_SCENARIOS[i % len(_CSB_SCENARIOS)]
        occurred = TIMELINE_START + timedelta(days=90 + i * 97, hours=rng.integer(4, 20))
        reported = occurred + timedelta(days=430)
        fatalities = 1 if i % 3 == 0 else 0
        serious = 0 if fatalities else (2 if i % 3 == 1 else 0)
        injuries = 0 if (fatalities or serious) else 3
        ref = f"{occurred.year}-{(i % 12) + 1:02d}-I-{['TX', 'LA', 'CA', 'OH'][i % 4]}"
        text = "\n".join(
            (
                "U.S. CHEMICAL SAFETY AND HAZARD INVESTIGATION BOARD",
                "Investigation Report",
                "",
                f"Report Number: {ref}",
                f"Incident Date: {occurred.date().isoformat()}",
                f"Report Date: {reported.date().isoformat()}",
                f"Location: {facility}",
                f"Incident Type: {classification}",
                f"Source: {injury_source}",
                f"Equipment: {equipment}",
                f"Fatalities: {fatalities}",
                f"Serious Injuries: {serious}",
                f"Injuries: {injuries}",
                "",
                "INCIDENT DESCRIPTION",
                "",
                (
                    f"Operators were preparing the {equipment.lower()} for a planned "
                    "changeover under a written procedure. The unit had been placed in a "
                    "hold state and the isolation had been established at the block valves."
                ),
                "",
                "KEY FINDINGS",
                "",
                (
                    "The management of change process did not require a hazard review when "
                    "the isolation standard was varied for a short-duration task."
                ),
                "",
            )
        )
        rows.append({"external_ref": ref, "text": text})
    return tuple(rows)


def _au_alerts(rng: DeterministicRandom) -> tuple[dict[str, object], ...]:
    rows: list[dict[str, object]] = []
    for i in range(AU_ALERTS):
        jurisdiction, incident_type, equipment, setting, classification = _AU_SCENARIOS[
            i % len(_AU_SCENARIOS)
        ]
        occurred = TIMELINE_START + timedelta(days=40 + i * 41, hours=rng.integer(5, 19))
        published = occurred + timedelta(days=21)
        ref = f"{jurisdiction}-SA-{occurred.year}-{i + 1:03d}"
        rows.append(
            {
                "external_ref": ref,
                "jurisdiction": jurisdiction,
                "classification": classification,
                "incident_type": incident_type,
                "injury_source": equipment,
                "occurred_at": occurred.date().isoformat(),
                "published_at": published.date().isoformat(),
                "title": f"{classification.title()} — {incident_type} at a {setting.lower()}",
                "equipment": equipment,
                "site": setting,
                "activity": incident_type,
                "text": (
                    f"A {classification} was reported at a {setting.lower()}. Workers were "
                    f"engaged in routine duties involving a {equipment.lower()} when the "
                    "event occurred. The regulator reminds operators to verify that the "
                    "relevant principal hazard management plan addresses the control "
                    "identified in this alert."
                ),
            }
        )
    return tuple(rows)


def generate(seed: str = DEFAULT_SEED) -> SyntheticCorpus:
    """Generate the whole replica corpus from one seed. Deterministic and total."""
    rng = DeterministicRandom(seed)
    part50_lines, part50_index = _part50(rng)
    return SyntheticCorpus(
        part50_lines=part50_lines,
        fatality_reports=_fatality_reports(rng, part50_index),
        csb_reports=_csb_reports(rng),
        au_alerts=_au_alerts(rng),
        seed=seed,
    )
