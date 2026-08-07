# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""G4 — Retro-Recall with a time wall. The money metric, and the demo.

For each severity-5 event at time *t*: synthesise the permit that would have preceded it
**from the investigation's own description of the work**, wall the corpus at *t*, and ask
whether the true precursor surfaces. It is the only metric that measures what the product
claims — *would this permit have been stopped?* — and a miss in it is a fatality exhibit.

Three refusals hold it up. Remove any one and the number becomes decoration.

**1. The permit must not contain the outcome.** The section a report calls "DESCRIPTION OF
THE ACCIDENT" describes the work *and then* the death. A permit synthesised from the whole
section would carry "was fatally crushed", and retrieval over it would be trivial and
meaningless. :func:`extract_work_in_progress` cuts the description at the first sentence
that names an outcome and keeps only what came before. A report with no work described
before the outcome yields **no** retro permit — it is dropped and counted, never padded.

**2. The wall is enforced by predicates, never by ``AS OF SYSTEM TIME``.** The three
predicates are ``occurred_at < t``, ``ingested_at < t``, ``corpus_commit <= t``, applied
through :class:`~trappoint_recall.eval.splits.SplitPolicy`. ``gc.ttlseconds`` defaults to
four hours, so an AOST read cannot reach a wall months back: it would either error or,
worse, silently evaluate a four-hour window (recall lead D12). :func:`assert_no_leakage`
re-checks every emitted judgement against its own query's wall, because a wall that is
only applied at build time is a wall nobody verified.

**3. The truth precursor is human-authored.** By default the precursor is the prior
incident the investigator themselves cited (G1). A coded-field fallback exists and is
**off** by default: choosing the precursor by shared codes would make the money metric an
evaluation of the coding manual, and would correlate the ground truth with the very
signal channel D is trying to measure.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Final

from trappoint_recall.corpora.g1_citations import CitationResolution
from trappoint_recall.corpora.model import EventRecord, EventRecordSet
from trappoint_recall.eval.corpus import EvalQuery
from trappoint_recall.eval.qrels import Judgement
from trappoint_recall.eval.splits import SplitPolicy, SplitRecord

__all__ = [
    "G4_GOLD_SET",
    "OUTCOME_MARKERS",
    "G4Report",
    "G4Result",
    "RetroPermit",
    "TimeWallLeak",
    "assert_no_leakage",
    "build_g4",
    "extract_work_in_progress",
    "g4_query_id",
    "synthesise_retro_permit",
]

G4_GOLD_SET: Final = "G4"

OUTCOME_MARKERS: Final[tuple[str, ...]] = (
    "fatal",
    "fatally",
    "died",
    "death",
    "killed",
    "deceased",
    "pronounced dead",
    "was struck",
    "were struck",
    "was crushed",
    "were crushed",
    "was engulfed",
    "were engulfed",
    "was buried",
    "were buried",
    "was electrocuted",
    "were electrocuted",
    "suffered",
    "sustained fatal",
    "life-threatening",
    "unresponsive",
    "cpr",
    "airlifted",
    "pronounced",
)
"""Words whose first appearance ends the *work* and begins the *accident*.

Deliberately generous: a marker matched too early costs a retro permit (dropped and
counted), while a marker matched too late leaks the outcome into the query and inflates
every recall number in the build. The asymmetry of the two errors is the whole reason the
list leans this way, and the drop count is published so the cost is visible."""

_SENTENCE_RE: Final = re.compile(r"(?<=[.!?])\s+")
_WS_RE: Final = re.compile(r"\s+")

MIN_WORK_DESCRIPTION_CHARS: Final = 60
"""Below this a "work description" is a fragment, and a permit built from a fragment
would be measuring nothing. Dropped and counted."""


class TimeWallLeak(RuntimeError):
    """Raised when a judged document is visible from the wrong side of its query's wall."""


def g4_query_id(ref: str) -> str:
    """``Q-G4-<ref>``. Its own namespace, and legible in a gate failure message."""
    return f"Q-G4-{ref}"


def _tidy(text: str) -> str:
    return _WS_RE.sub(" ", text).strip()


def extract_work_in_progress(description: str) -> str | None:
    """Return the work described *before* the first outcome sentence, or ``None``.

    This is the single most important function in G4. Everything downstream —
    Retro-Recall, the ablation table, the demo — is measured over the text this returns,
    and if the outcome survives into it, every number in the build is inflated by an
    amount nobody can estimate afterwards.
    """
    cleaned = _tidy(description)
    if not cleaned:
        return None
    sentences = _SENTENCE_RE.split(cleaned)
    kept: list[str] = []
    for sentence in sentences:
        lowered = sentence.lower()
        if any(marker in lowered for marker in OUTCOME_MARKERS):
            break
        kept.append(sentence.strip())
    text = " ".join(s for s in kept if s).strip()
    if len(text) < MIN_WORK_DESCRIPTION_CHARS:
        return None
    return text


@dataclass(frozen=True, slots=True)
class RetroPermit:
    """The permit that would have preceded a fatality, and the wall it is evaluated at."""

    query_id: str
    event_ref: str
    wall: datetime
    text: str
    site_ref: str
    activity_path: str
    asset_class: str
    severity: int
    truth_doc_id: str
    truth_basis: str
    bonded_sev5: tuple[str, ...]

    def to_eval_query(self) -> EvalQuery:
        """The harness's own query type, with the raw work description as the narrative facet.

        Only the ``narrative`` facet is populated. The four Recurrence-Condition Cue facets
        are the cue synthesiser's output, and inventing them here with a template would
        pre-empt the very component the ablation is supposed to measure.
        """
        return EvalQuery(
            query_id=self.query_id,
            kind="retro",
            text=self.text,
            site_id=self.site_ref,
            activity_path=self.activity_path,
            asset_class=self.asset_class,
            severity=self.severity,
            wall=self.wall,
            truth_doc_id=self.truth_doc_id,
            bonded_sev5=self.bonded_sev5,
            facets={"narrative": self.text},
            blinded=True,
        )


def synthesise_retro_permit(
    record: EventRecord,
    *,
    truth_doc_id: str,
    truth_basis: str,
    bonded_sev5: Sequence[str] = (),
) -> RetroPermit | None:
    """Build the retro permit for one severity-5 event, or ``None`` if it cannot be built.

    ``None`` means the investigation described no work before the outcome. That is a
    property of the source document, and the honest response is to drop the event from
    G4 rather than to invent a plausible permit — an invented permit would be measuring
    the inventor.
    """
    if record.severity_actual != 5:
        return None
    source_text = record.work_description or ""
    work = extract_work_in_progress(source_text)
    if work is None:
        return None
    activity = record.activity_path.rsplit("/", 1)[-1].replace("-", " ") or "work"
    asset = record.asset_class.replace("-", " ")
    text = (
        f"Permit to work: {activity} on {asset} at {record.site_ref}. "
        f"Scope of work, as described by the investigation: {work}"
    )
    return RetroPermit(
        query_id=g4_query_id(record.external_ref),
        event_ref=record.external_ref,
        wall=record.occurred_at,
        text=text,
        site_ref=record.site_ref,
        activity_path=record.activity_path,
        asset_class=record.asset_class,
        severity=5,
        truth_doc_id=truth_doc_id,
        truth_basis=truth_basis,
        bonded_sev5=tuple(bonded_sev5),
    )


@dataclass(frozen=True, slots=True)
class G4Report:
    """What G4 built, and every severity-5 event it refused to build a permit for."""

    n_severity_5: int
    n_permits: int
    dropped: Mapping[str, int]
    n_judgements: int
    n_truth_from_citation: int
    n_truth_from_codes: int
    walls: tuple[str, ...]

    @property
    def n_dropped(self) -> int:
        return sum(self.dropped.values())

    def __post_init__(self) -> None:
        if self.n_permits + self.n_dropped != self.n_severity_5:
            raise ValueError(
                f"G4 accounting does not close: {self.n_permits} permits + "
                f"{self.n_dropped} dropped != {self.n_severity_5} severity-5 events"
            )

    def to_dict(self) -> dict[str, object]:
        return {
            "n_severity_5": self.n_severity_5,
            "n_permits": self.n_permits,
            "n_dropped": self.n_dropped,
            "dropped": dict(sorted(self.dropped.items())),
            "n_judgements": self.n_judgements,
            "truth_precursor_basis": {
                "investigator_citation": self.n_truth_from_citation,
                "coded_fields_fallback": self.n_truth_from_codes,
            },
            "n_distinct_walls": len(set(self.walls)),
            "wall_range": [min(self.walls), max(self.walls)] if self.walls else [],
            "wall_enforcement": (
                "predicates occurred_at < t AND ingested_at < t AND corpus_commit <= t; "
                "AS OF SYSTEM TIME refused (gc.ttlseconds=4h, recall lead D12)"
            ),
        }


@dataclass(frozen=True, slots=True)
class G4Result:
    """Retro permits, their judgements, and the build report."""

    permits: tuple[RetroPermit, ...]
    judgements: tuple[Judgement, ...]
    report: G4Report

    @property
    def queries(self) -> tuple[EvalQuery, ...]:
        return tuple(p.to_eval_query() for p in self.permits)


def _graded_neighbours(
    subject: EventRecord,
    admitted: Sequence[EventRecord],
    *,
    truth_ref: str,
    max_graded: int,
) -> list[tuple[EventRecord, int]]:
    """Grade the admitted prior records against the subject, deterministically.

    Grade 2 — shares the mechanism: same hazard energy **and** the same coded accident
    classification. Grade 1 — same asset class only. Everything else is left unjudged
    rather than graded 0, because "we did not look" and "we looked and it was irrelevant"
    are different facts and the harness reports judgement coverage separately.
    """
    graded: list[tuple[EventRecord, int]] = []
    subject_class = subject.coded.comembership_key[0]
    for candidate in admitted:
        if candidate.external_ref in (subject.external_ref, truth_ref):
            continue
        shares_mechanism = (
            candidate.hazard_energy == subject.hazard_energy
            and candidate.coded.comembership_key[0] == subject_class
        )
        if shares_mechanism:
            graded.append((candidate, 2))
        elif candidate.asset_class == subject.asset_class:
            graded.append((candidate, 1))
    graded.sort(key=lambda pair: (-pair[1], -pair[0].occurred_at.timestamp(), pair[0].external_ref))
    return graded[:max_graded]


def build_g4(
    records: EventRecordSet,
    resolution: CitationResolution,
    *,
    corpus_commit: str,
    max_graded_per_query: int = 12,
    max_bonded_per_query: int = 3,
    allow_coded_fallback: bool = False,
) -> G4Result:
    """Build the Retro-Recall gold set from a corpus and its resolved citations.

    Args:
        records: The full corpus.
        resolution: G1's resolved citations. Supplies the human-authored precursor.
        corpus_commit: Identifier of the corpus state, carried on every
            :class:`~trappoint_recall.eval.splits.SplitPolicy` so a wall is never quoted
            without the corpus it was taken against.
        max_graded_per_query: Cap on judged neighbours per query, for file size. Applied
            after a total ordering, so it is reproducible.
        max_bonded_per_query: Cap on channel-B bonded fatalities attached to a query.
        allow_coded_fallback: Permit a coded-field precursor when the investigator cited
            none. **Off by default**, and recorded in the report when on: a coded-field
            precursor makes the money metric partly an evaluation of the coding manual.

    Returns:
        :class:`G4Result`.

    Raises:
        TimeWallLeak: if any emitted judgement would be visible across its query's wall.
            The check is redundant with the construction, which is exactly why it is here.
    """
    citations_by_citing: dict[str, list[str]] = {}
    for item in resolution.resolved:
        citations_by_citing.setdefault(item.citing_ref, []).append(item.cited_ref)

    fatal = sorted(records.fatal(), key=lambda r: (r.occurred_at, r.external_ref))
    permits: list[RetroPermit] = []
    judgements: list[Judgement] = []
    dropped: dict[str, int] = {}
    walls: list[str] = []
    n_from_citation = 0
    n_from_codes = 0

    def drop(reason: str) -> None:
        dropped[reason] = dropped.get(reason, 0) + 1

    for subject in fatal:
        wall = subject.occurred_at
        policy = SplitPolicy(
            wall=wall,
            corpus_commit=corpus_commit,
            note=f"Retro-Recall wall immediately before {subject.external_ref}",
        )
        admitted = [
            r
            for r in records
            if r.external_ref != subject.external_ref and policy.admits(r.to_split_record())
        ]
        admitted.sort(key=lambda r: (r.occurred_at, r.external_ref))
        admitted_refs = {r.external_ref for r in admitted}

        truth_ref: str | None = None
        truth_basis = ""
        # The nearest admitted citation, not the first one in some arbitrary order. An
        # investigation that cites three prior events is asserting that all three share the
        # mechanism; the closest in time is the one a permit written the week before would
        # most plausibly have surfaced, and picking it is a stated rule rather than a
        # by-product of how a set iterates.
        cited_candidates = [
            records.get(ref)
            for ref in sorted(set(citations_by_citing.get(subject.external_ref, [])))
            if ref in admitted_refs
        ]
        nearest = sorted(
            (r for r in cited_candidates if r is not None),
            key=lambda r: (r.occurred_at, r.external_ref),
        )
        if nearest:
            truth_ref = nearest[-1].external_ref
            truth_basis = "investigator_citation"
        if truth_ref is None and allow_coded_fallback:
            same_mechanism = [
                r
                for r in reversed(admitted)
                if r.hazard_energy == subject.hazard_energy
                and r.coded.comembership_key[0] == subject.coded.comembership_key[0]
            ]
            if same_mechanism:
                truth_ref = same_mechanism[0].external_ref
                truth_basis = "coded_fields_fallback"
        if truth_ref is None:
            drop("no_precursor_before_wall")
            continue

        bonded = [
            r.external_ref
            for r in reversed(admitted)
            if r.severity_actual == 5
            and r.external_ref != truth_ref
            and r.activity_path.rsplit("/", 1)[0] == subject.activity_path.rsplit("/", 1)[0]
        ][:max_bonded_per_query]

        permit = synthesise_retro_permit(
            subject,
            truth_doc_id=truth_ref,
            truth_basis=truth_basis,
            bonded_sev5=tuple(sorted(bonded)),
        )
        if permit is None:
            drop("no_work_described_before_outcome")
            continue

        permits.append(permit)
        walls.append(wall.astimezone(UTC).isoformat())
        if truth_basis == "investigator_citation":
            n_from_citation += 1
        else:
            n_from_codes += 1

        judgements.append(
            Judgement(
                query_id=permit.query_id,
                doc_id=truth_ref,
                grade=3,
                gold_set=G4_GOLD_SET,
                judged_by=(
                    "distant_supervision"
                    if truth_basis == "investigator_citation"
                    else "authored"
                ),
                blinded=False,
                notes=(
                    f"truth precursor of {subject.external_ref} via {truth_basis}; "
                    f"wall {wall.astimezone(UTC).isoformat()}"
                ),
            )
        )
        for neighbour, grade in _graded_neighbours(
            subject, admitted, truth_ref=truth_ref, max_graded=max_graded_per_query
        ):
            judgements.append(
                Judgement(
                    query_id=permit.query_id,
                    doc_id=neighbour.external_ref,
                    grade=grade,
                    gold_set=G4_GOLD_SET,
                    judged_by="distant_supervision",
                    blinded=False,
                    notes=(
                        "shares mechanism (hazard energy + coded classification)"
                        if grade == 2
                        else "same asset class, different recurrence condition"
                    ),
                )
            )
    report = G4Report(
        n_severity_5=len(fatal),
        n_permits=len(permits),
        dropped=dropped,
        n_judgements=len(judgements),
        n_truth_from_citation=n_from_citation,
        n_truth_from_codes=n_from_codes,
        walls=tuple(walls),
    )
    result = G4Result(
        permits=tuple(permits), judgements=tuple(judgements), report=report
    )
    assert_no_leakage(result, records, corpus_commit=corpus_commit)
    return result


def assert_no_leakage(
    result: G4Result, records: EventRecordSet, *, corpus_commit: str
) -> None:
    """Re-check every judgement against its own query's wall.

    Redundant with :func:`build_g4`'s construction, and that is the point: a wall applied
    once at build time is a wall nobody verified, and this is the assertion the invariant
    test drives.

    Raises:
        TimeWallLeak: naming the query, the document and which predicate failed.
    """
    walls = {p.query_id: p.wall for p in result.permits}
    for judgement in result.judgements:
        wall = walls.get(judgement.query_id)
        if wall is None:
            raise TimeWallLeak(
                f"{judgement.query_id}: judgement for {judgement.doc_id} has no retro "
                "permit and therefore no wall; an unwalled judgement in G4 is a leak "
                "waiting to be scored"
            )
        record = records.get(judgement.doc_id)
        if record is None:
            raise TimeWallLeak(
                f"{judgement.query_id}: judged document {judgement.doc_id} is not in the "
                "corpus, so its timestamps cannot be checked against the wall"
            )
        policy = SplitPolicy(wall=wall, corpus_commit=corpus_commit)
        reason = policy.rejection_reason(record.to_split_record())
        if reason is not None:
            raise TimeWallLeak(
                f"{judgement.query_id}: document {judgement.doc_id} fails the time wall "
                f"{wall.astimezone(UTC).isoformat()} on {reason}. Retro-Recall measured "
                "over this pair would be scoring the retriever on its own future."
            )


def split_records_for(records: Iterable[EventRecord]) -> tuple[SplitRecord, ...]:
    """Every record's three timestamps, for a caller driving the harness's split helper."""
    return tuple(r.to_split_record() for r in records)
