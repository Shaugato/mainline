# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""The normalised event record every corpus loader produces, and the severity refusal.

One shape, four sources
-----------------------
MSHA Part 50 extracts, MSHA fatality investigation reports, CSB investigation reports
and Australian state-regulator safety alerts are four different genres with four
different field vocabularies. They land here as one :class:`EventRecord` so that the
gold-set builders never branch on where a record came from — a builder that branched
would eventually treat one corpus more generously than another, and the resulting metric
would measure the branch.

Severity is *taken*, never *inferred*
--------------------------------------
``severity_actual`` may only come from a coded field the regulator wrote
(``severity_basis='coded_field'``) or a classification the regulator published
(``'regulator_class'``). This module refuses to construct a record whose severity is
``'model_rated'``, and :func:`infer_severity` exists solely to raise.

The reason is the kernel's own: ARCHITECTURE §5.4 carries
``CHECK (severity_gate < 4 OR severity_basis <> 'model_rated')`` — *an LLM's potential
rating alone may never arm a blocking gate*. A corpus loader that quietly rated
severities would smuggle exactly that past the CHECK by making the model's opinion look
like a coded field before it ever reached the database. The refusal therefore lives one
hop upstream, in the loader, which is where P2 says an enforced projection belongs.

Hazard energy
-------------
No regulator codes "hazard energy" directly. It is derived from the regulator's own
coded accident classification through :data:`ACCIDENT_CLASS_HAZARD_ENERGY`, a lookup
table published in this file and reviewable by a stranger. Unmapped classifications are
**dropped with a count**, never bucketed into a default: a default bucket would quietly
concentrate every unrecognised classification into one hazard class and corrupt the
THYMOGATE panel's coverage claim.
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Annotated, Final, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from trappoint_recall.corpora.provenance import FixtureProvenance
from trappoint_recall.eval.splits import SplitRecord

__all__ = [
    "ACCIDENT_CLASS_HAZARD_ENERGY",
    "HAZARD_ENERGY_CLASSES",
    "PART50_NARRATIVE_MAX_CHARS",
    "CodedFields",
    "CorpusSource",
    "EventRecord",
    "EventRecordSet",
    "HazardEnergy",
    "LoadReport",
    "SeverityBasis",
    "SeverityRefused",
    "hazard_energy_for",
    "infer_severity",
]

HazardEnergy = Literal[
    "gravity",
    "pressure",
    "electrical",
    "thermal",
    "chemical",
    "kinetic",
    "biological",
    "radiation",
]
"""The eight energy classes. Identical to the vertical's ``control_failure`` CHECK list
(ARCHITECTURE §5.4) — the THYMOGATE panel must cover all eight, which is why the list is
closed and why an unmapped classification is dropped rather than defaulted."""

HAZARD_ENERGY_CLASSES: Final[tuple[HazardEnergy, ...]] = (
    "gravity",
    "pressure",
    "electrical",
    "thermal",
    "chemical",
    "kinetic",
    "biological",
    "radiation",
)

SeverityBasis = Literal["coded_field", "regulator_class", "human_rated", "model_rated"]
"""The vertical's four bases. Loaders may only produce the first two."""

_LOADER_ADMISSIBLE_BASES: Final[frozenset[str]] = frozenset({"coded_field", "regulator_class"})

CorpusSource = Literal[
    "msha_part50",
    "msha_fatality_report",
    "csb_report",
    "au_regulator_alert",
    "synthetic_permit",
]

PART50_NARRATIVE_MAX_CHARS: Final = 384
"""MSHA Part 50 ``NARRATIVE`` is ``VARCHAR2(384)``.

This is not trivia; it is the reason the recall lead's risk 4 exists. Part 50 alone
yields terse coded records that make weak ``recurrence_test`` facets, so G1 and G4 depend
on the fatality investigation reports, and G2 — which is exactly what Part 50 *is* good
for — is calibrator-only and never a headline number."""


class SeverityRefused(RuntimeError):
    """Raised when something asks this package to decide how bad an event was."""


def infer_severity(narrative: str, *, context: str = "corpus load") -> int:
    """Always raises. There is no acceptable way for this package to rate severity.

    Present as a named function precisely so that the refusal is discoverable by anyone
    who goes looking for the inference that "must be in here somewhere".

    Raises:
        SeverityRefused: unconditionally.
    """
    del narrative
    raise SeverityRefused(
        f"{context}: severity inference is refused. severity_actual comes from a coded "
        "field the regulator wrote (severity_basis='coded_field') or a classification "
        "the regulator published ('regulator_class'), and from nowhere else. A model's "
        "rating may never arm a blocking gate (ARCHITECTURE 5.4, "
        "CHECK model_cannot_arm), and a loader that rated severities would launder the "
        "model's opinion into a coded field before the CHECK ever saw it. If the source "
        "record carries no severity, drop it and count the drop."
    )


# --------------------------------------------------------------------------------------
# Hazard energy, derived from the regulator's own coded classification
# --------------------------------------------------------------------------------------

ACCIDENT_CLASS_HAZARD_ENERGY: Final[Mapping[str, HazardEnergy]] = {
    # MSHA Part 50 ACCIDENT_TYPE / classification vocabulary, normalised to lower case
    # with runs of non-alphanumerics collapsed to a single space. Transcribed from the
    # published Part 50 data dictionary; UNVERIFIED against a live download from this
    # machine. A classification absent from this table is dropped with a count, so a
    # transcription error shows up as a coverage shortfall rather than as a wrong label.
    "fall of roof or back": "gravity",
    "fall of face rib pillar or highwall": "gravity",
    "fall of person from elevation": "gravity",
    "falling rolling or sliding rock or material of any kind": "gravity",
    "slip or fall of person from same level": "gravity",
    "caught in under or between": "kinetic",
    "powered haulage": "kinetic",
    "machinery": "kinetic",
    "hand tools": "kinetic",
    "handling material": "kinetic",
    "struck by or against": "kinetic",
    "nonpowered haulage": "kinetic",
    "entrapment": "kinetic",
    "electrical": "electrical",
    "explosives and breaking agents": "pressure",
    "ignition or explosion of gas or dust": "pressure",
    "inundation": "pressure",
    "impoundment failure": "gravity",
    "fire": "thermal",
    "exposure to thermal extremes": "thermal",
    "exposure to chemicals or toxic substances": "chemical",
    "exposure to irrespirable atmosphere": "chemical",
    "exposure to biological agents": "biological",
    "exposure to ionising radiation": "radiation",
    "exposure to radon daughters": "radiation",
    "stored pressure release": "pressure",
    "loss of containment": "chemical",
    "vapour cloud explosion": "pressure",
    "runaway reaction": "thermal",
    "arc flash": "electrical",
    "unknown": "kinetic",
}
"""Coded accident classification → hazard energy class.

``unknown`` is present only because MSHA itself uses it as a coded value; it is mapped
rather than dropped so the drop count means "we do not recognise this code", not "the
regulator did not know"."""


def _normalise_code(text: str) -> str:
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


def hazard_energy_for(accident_classification: str) -> HazardEnergy | None:
    """Map a coded accident classification to a hazard energy class, or ``None``.

    ``None`` means *unmapped*, and every caller must count it. Returning a default would
    silently concentrate unrecognised classifications into one class and would make the
    panel's eight-class coverage claim false while it still looked true.
    """
    return ACCIDENT_CLASS_HAZARD_ENERGY.get(_normalise_code(accident_classification))


# --------------------------------------------------------------------------------------
# The record
# --------------------------------------------------------------------------------------


class CodedFields(BaseModel):
    """The regulator's own coded columns, kept together and kept verbatim.

    These are the *only* fields G2 co-membership is allowed to look at, so they live in
    their own object: a weak-positive rule that reached into the narrative would stop
    being a structured-code rule and start being an undeclared retrieval model.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    accident_classification: Annotated[
        str, Field(min_length=1, description="Coded accident classification, verbatim.")
    ]
    injury_source: Annotated[
        str, Field(min_length=1, description="Coded source of injury, verbatim.")
    ]
    mining_method: Annotated[
        str | None, Field(description="Coded mining method. None where the source has none.")
    ] = None
    equipment: Annotated[
        str | None, Field(description="Coded equipment involved. None where absent.")
    ] = None
    subunit: Annotated[str | None, Field(description="Coded location/subunit.")] = None
    degree_of_injury: Annotated[
        str | None, Field(description="The coded field severity was taken from.")
    ] = None

    @property
    def comembership_key(self) -> tuple[str, str, str]:
        """``(classification, injury source, equipment)`` — the G2 weak-positive key.

        Equipment is normalised to ``''`` when absent so two records that both lack it
        can still co-member; treating missing equipment as a distinct value per record
        would make G2 empty on exactly the corpus slice where it is most useful.
        """
        return (
            _normalise_code(self.accident_classification),
            _normalise_code(self.injury_source),
            _normalise_code(self.equipment or ""),
        )


class EventRecord(BaseModel):
    """One normalised incident, from any of the four supported corpora."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    external_ref: Annotated[
        str,
        Field(
            min_length=1,
            description="The regulator's own identifier. Stable across rebuilds; it is "
            "what a citation resolves to.",
        ),
    ]
    source: Annotated[CorpusSource, Field(description="Which corpus produced this record.")]
    occurred_at: Annotated[datetime, Field(description="When it happened. Timezone-aware.")]
    ingested_at: Annotated[
        datetime, Field(description="When we had it. Bitemporal: both, always.")
    ]
    corpus_commit_at: Annotated[
        datetime,
        Field(
            description="Corpus state this record belongs to. The third time-wall predicate."
        ),
    ]
    title: Annotated[str, Field(min_length=1)]
    narrative: Annotated[
        str,
        Field(
            min_length=1,
            description="The source text. Terse for Part 50 (VARCHAR2(384)), rich for "
            "investigation reports.",
        ),
    ]
    work_description: Annotated[
        str | None,
        Field(
            description="The investigation's own description of the work in progress. "
            "G4 synthesises the retro permit from this and refuses the record without it."
        ),
    ] = None
    coded: CodedFields
    hazard_energy: HazardEnergy
    severity_actual: Annotated[
        int, Field(ge=0, le=5, description="0..5. 5 is a fatality. Never model-rated.")
    ]
    severity_basis: SeverityBasis
    site_ref: Annotated[
        str, Field(min_length=1, description="Operation identifier, opaque to this package.")
    ]
    activity_path: Annotated[
        str,
        Field(
            min_length=1,
            description="Functional taxonomy path, e.g. /underground/ground-support/rehab.",
        ),
    ]
    asset_class: Annotated[str, Field(min_length=1)]
    citations: Annotated[
        tuple[str, ...],
        Field(description="Raw citation strings this record makes to prior incidents."),
    ] = ()
    narrative_truncated: Annotated[
        bool,
        Field(
            description="True when the source column caps the narrative (Part 50 at 384 "
            "chars). Carried so a weak facet can be attributed to the source rather than "
            "to the cue synthesiser."
        ),
    ] = False
    provenance: FixtureProvenance

    @field_validator("occurred_at", "ingested_at", "corpus_commit_at")
    @classmethod
    def _tz_aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError(
                "timestamps must be timezone-aware; a naive timestamp in a time-wall "
                "predicate is an undetectable off-by-one-timezone leak"
            )
        return value.astimezone(UTC)

    @model_validator(mode="after")
    def _severity_is_taken_not_inferred(self) -> EventRecord:
        if self.severity_basis not in _LOADER_ADMISSIBLE_BASES:
            raise ValueError(
                f"{self.external_ref}: severity_basis={self.severity_basis!r} is refused "
                "for a corpus record. A loader may only carry a severity the regulator "
                "wrote: 'coded_field' or 'regulator_class'. 'model_rated' in particular "
                "would launder a model's opinion past ARCHITECTURE 5.4's "
                "CHECK model_cannot_arm."
            )
        if self.ingested_at < self.occurred_at:
            raise ValueError(
                f"{self.external_ref}: ingested_at precedes occurred_at, which would let "
                "a record be admitted by a time wall it should not reach"
            )
        if self.narrative_truncated and len(self.narrative) > PART50_NARRATIVE_MAX_CHARS:
            raise ValueError(
                f"{self.external_ref}: marked truncated but is "
                f"{len(self.narrative)} chars, over the {PART50_NARRATIVE_MAX_CHARS}-char "
                "Part 50 column width; one of the two facts is wrong"
            )
        return self

    @property
    def is_fatal(self) -> bool:
        return self.severity_actual == 5

    def to_split_record(self) -> SplitRecord:
        """The three timestamps a time wall tests, in the harness's own type."""
        return SplitRecord(
            doc_id=self.external_ref,
            occurred_at=self.occurred_at,
            ingested_at=self.ingested_at,
            corpus_commit_at=self.corpus_commit_at,
        )

    def to_dict(self) -> dict[str, object]:
        payload = self.model_dump(mode="json")
        return dict(payload)


# --------------------------------------------------------------------------------------
# Collections and load reporting
# --------------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class LoadReport:
    """What a loader kept, what it dropped, and why — one object, always returned.

    Drops are counted by reason rather than logged and forgotten. A gold set built from a
    corpus that silently lost 40% of its records is not a smaller gold set, it is a
    different one, and the only way to notice is to make the loss a number that travels
    with the data.
    """

    source: str
    n_read: int
    n_kept: int
    dropped: Mapping[str, int]

    @property
    def n_dropped(self) -> int:
        return sum(self.dropped.values())

    def __post_init__(self) -> None:
        if self.n_kept + self.n_dropped != self.n_read:
            raise ValueError(
                f"{self.source}: load accounting does not close — read {self.n_read}, "
                f"kept {self.n_kept}, dropped {self.n_dropped}. A loader whose counts do "
                "not add up has lost records it cannot name."
            )

    def render(self) -> str:
        if not self.dropped:
            return f"{self.source}: {self.n_kept}/{self.n_read} kept, no drops"
        detail = ", ".join(f"{k}={v}" for k, v in sorted(self.dropped.items()))
        return f"{self.source}: {self.n_kept}/{self.n_read} kept; dropped {detail}"

    def to_dict(self) -> dict[str, object]:
        return {
            "source": self.source,
            "n_read": self.n_read,
            "n_kept": self.n_kept,
            "n_dropped": self.n_dropped,
            "dropped": dict(sorted(self.dropped.items())),
        }


@dataclass(frozen=True, slots=True)
class EventRecordSet:
    """Records indexed by ``external_ref``, with the load report that produced them."""

    records: tuple[EventRecord, ...]
    report: LoadReport
    _index: Mapping[str, EventRecord]

    @classmethod
    def build(cls, records: Iterable[EventRecord], report: LoadReport) -> EventRecordSet:
        items = tuple(records)
        index: dict[str, EventRecord] = {}
        for record in items:
            if record.external_ref in index:
                raise ValueError(
                    f"duplicate external_ref {record.external_ref!r}: a citation could "
                    "resolve to either record, and the gold set would depend on dict order"
                )
            index[record.external_ref] = record
        return cls(records=items, report=report, _index=index)

    def __len__(self) -> int:
        return len(self.records)

    def __iter__(self) -> Iterator[EventRecord]:
        return iter(self.records)

    def __contains__(self, external_ref: object) -> bool:
        return external_ref in self._index

    def get(self, external_ref: str) -> EventRecord | None:
        return self._index.get(external_ref)

    @property
    def refs(self) -> frozenset[str]:
        return frozenset(self._index)

    def fatal(self) -> tuple[EventRecord, ...]:
        return tuple(r for r in self.records if r.is_fatal)

    def by_hazard_energy(self, hazard: HazardEnergy) -> tuple[EventRecord, ...]:
        return tuple(r for r in self.records if r.hazard_energy == hazard)

    def before(self, wall: datetime) -> tuple[EventRecord, ...]:
        """Records admitted by all three time-wall predicates against ``wall``."""
        return tuple(
            r
            for r in self.records
            if r.occurred_at < wall and r.ingested_at < wall and r.corpus_commit_at <= wall
        )

    def merged_with(self, other: EventRecordSet, *, source: str) -> EventRecordSet:
        """Concatenate two sets, refusing an overlap of ``external_ref``."""
        combined: list[EventRecord] = [*self.records, *other.records]
        dropped: dict[str, int] = {}
        for key, value in (*self.report.dropped.items(), *other.report.dropped.items()):
            dropped[key] = dropped.get(key, 0) + value
        report = LoadReport(
            source=source,
            n_read=self.report.n_read + other.report.n_read,
            n_kept=self.report.n_kept + other.report.n_kept,
            dropped=dropped,
        )
        return EventRecordSet.build(combined, report)


def sorted_records(records: Sequence[EventRecord]) -> tuple[EventRecord, ...]:
    """Deterministic order: ``(occurred_at, external_ref)``.

    Every gold-set builder sorts before it emits, so a rebuild is byte-identical and a
    diff means the data changed rather than that a dict iterated differently.
    """
    return tuple(sorted(records, key=lambda r: (r.occurred_at, r.external_ref)))
