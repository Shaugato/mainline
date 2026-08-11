# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""Graded relevance judgements on the UMBRELA 0-3 scale.

The scale is fixed and its meanings are fixed, because a judgement whose rubric drifts
between gold sets is not a judgement. Grades follow UMBRELA (arXiv:2406.06519):

    0  irrelevant       -- shares no mechanism and no precondition with the query
    1  related          -- same equipment or same site, but the recurrence condition differs
    2  highly relevant  -- shares the mechanism *or* the precondition; a supervisor should see it
    3  perfectly relevant -- shares mechanism *and* precondition; this is the precursor

The binary metrics in this package treat grade >= 2 as relevant
(:data:`BLOCKING_RELEVANCE_FLOOR`). That threshold is a published constant, not a knob:
moving it moves ``P@block``, so it lives here, in one place, under review.

Provenance is mandatory. ``judged_by`` distinguishes ``human`` from ``llm`` because
humans grade stricter than LLMs, and an LLM-only label may never ship as the precision
headline (research/05-architecture/diachronic-recall.md, G3).
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Iterator, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Annotated, Final, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

__all__ = [
    "BLOCKING_RELEVANCE_FLOOR",
    "GRADE_MEANINGS",
    "Judgement",
    "JudgementSource",
    "QrelError",
    "QrelSet",
    "load_qrels_jsonl",
    "qrels_json_schema",
    "write_qrels_json_schema",
]

BLOCKING_RELEVANCE_FLOOR: Final = 2
"""Grade at or above which a candidate counts as relevant for the binary metrics."""

GRADE_MEANINGS: Final[Mapping[int, str]] = {
    0: "irrelevant: shares no mechanism and no precondition",
    1: "related: same equipment or site, different recurrence condition",
    2: "highly relevant: shares the mechanism or the precondition",
    3: "perfectly relevant: shares mechanism and precondition; this is the precursor",
}

JudgementSource = Literal["human", "llm", "distant_supervision", "authored"]
"""``authored`` is for synthetic corpora where the blame edge was written, not judged."""

RelevanceScale = Literal["umbrela-0-3"]


class QrelError(ValueError):
    """Raised when a judgement file is malformed or internally inconsistent."""


class Judgement(BaseModel):
    """One (query, document, grade) triple with its provenance."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    query_id: Annotated[str, Field(min_length=1, description="Evaluation query identifier.")]
    doc_id: Annotated[str, Field(min_length=1, description="Candidate event identifier.")]
    grade: Annotated[
        int,
        Field(ge=0, le=3, description="UMBRELA relevance grade, 0-3. See GRADE_MEANINGS."),
    ]
    scale: Annotated[RelevanceScale, Field(description="Rubric the grade was produced under.")] = (
        "umbrela-0-3"
    )
    gold_set: Annotated[
        str,
        Field(
            min_length=1,
            description="Gold set this judgement belongs to, e.g. G1, G2, G3, G4, GS0.",
        ),
    ]
    judged_by: Annotated[
        JudgementSource,
        Field(description="Provenance. LLM-only labels never ship as a precision headline."),
    ]
    judged_at: Annotated[
        datetime | None, Field(description="When the judgement was recorded, if known.")
    ] = None
    blinded: Annotated[
        bool,
        Field(
            description=(
                "True when the judge could not see which system retrieved the document. "
                "P@block is only computed over blinded judgements."
            )
        ),
    ] = False
    notes: Annotated[str | None, Field(description="Free-text rationale.")] = None

    @field_validator("query_id", "doc_id", "gold_set")
    @classmethod
    def _no_surrounding_space(cls, value: str) -> str:
        stripped = value.strip()
        if stripped != value:
            raise ValueError("identifiers must not carry leading or trailing whitespace")
        return stripped

    @property
    def relevant(self) -> bool:
        return self.grade >= BLOCKING_RELEVANCE_FLOOR


@dataclass(frozen=True, slots=True)
class QrelSet:
    """Validated judgements indexed for the metric functions.

    Two documents with the same ``(query_id, doc_id)`` and different grades is a hard
    error, not a last-writer-wins merge: silently collapsing contradictory judgements
    is how a precision number stops meaning anything.
    """

    judgements: tuple[Judgement, ...]
    _by_query: Mapping[str, Mapping[str, int]]
    _blinded: frozenset[tuple[str, str]]

    @classmethod
    def build(cls, judgements: Iterable[Judgement]) -> QrelSet:
        items = tuple(judgements)
        table: dict[str, dict[str, int]] = {}
        blinded: set[tuple[str, str]] = set()
        for j in items:
            row = table.setdefault(j.query_id, {})
            previous = row.get(j.doc_id)
            if previous is not None and previous != j.grade:
                raise QrelError(
                    f"contradictory judgements for ({j.query_id}, {j.doc_id}): "
                    f"{previous} and {j.grade}. Adjudicate the pair; do not average it."
                )
            row[j.doc_id] = j.grade
            if j.blinded:
                blinded.add((j.query_id, j.doc_id))
        frozen: dict[str, Mapping[str, int]] = {q: dict(r) for q, r in table.items()}
        return cls(judgements=items, _by_query=frozen, _blinded=frozenset(blinded))

    def __len__(self) -> int:
        return len(self.judgements)

    def __iter__(self) -> Iterator[Judgement]:
        return iter(self.judgements)

    @property
    def query_ids(self) -> frozenset[str]:
        return frozenset(self._by_query)

    def grade(self, query_id: str, doc_id: str) -> int | None:
        """Graded relevance, or ``None`` when the pair was never judged.

        ``None`` is distinct from ``0``. Unjudged pairs are counted as non-relevant by
        the binary metrics (the TREC convention) *and* reported as a coverage figure,
        because pretending an unjudged blocking check is a correct one is how a
        precision claim quietly inflates.
        """
        row = self._by_query.get(query_id)
        if row is None:
            return None
        return row.get(doc_id)

    def graded_docs(self, query_id: str) -> Mapping[str, int]:
        return self._by_query.get(query_id, {})

    def relevant_docs(
        self, query_id: str, *, floor: int = BLOCKING_RELEVANCE_FLOOR
    ) -> frozenset[str]:
        return frozenset(
            doc for doc, grade in self._by_query.get(query_id, {}).items() if grade >= floor
        )

    def is_blinded(self, query_id: str, doc_id: str) -> bool:
        return (query_id, doc_id) in self._blinded

    def coverage(self, query_id: str, doc_ids: Sequence[str]) -> float:
        """Fraction of ``doc_ids`` carrying a judgement for ``query_id``."""
        if not doc_ids:
            return 1.0
        judged = sum(1 for d in doc_ids if self.grade(query_id, d) is not None)
        return judged / len(doc_ids)

    def restrict(self, query_ids: Iterable[str]) -> QrelSet:
        keep = frozenset(query_ids)
        return QrelSet.build(j for j in self.judgements if j.query_id in keep)


def load_qrels_jsonl(path: Path | str) -> QrelSet:
    """Load and validate a JSONL judgement file.

    Every line is validated independently and the line number is reported on failure,
    because a 4 000-line qrel file with one bad grade should tell you which line.
    """
    source = Path(path)
    if not source.is_file():
        raise QrelError(f"qrels file not found: {source}")
    judgements: list[Judgement] = []
    with source.open("r", encoding="utf-8") as handle:
        for lineno, raw in enumerate(handle, start=1):
            line = raw.strip()
            if not line or line.startswith("//"):
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError as exc:
                raise QrelError(f"{source}:{lineno}: not valid JSON: {exc}") from exc
            try:
                judgements.append(Judgement.model_validate(payload))
            except Exception as exc:  # pydantic ValidationError, re-raised with position
                raise QrelError(f"{source}:{lineno}: invalid judgement: {exc}") from exc
    if not judgements:
        raise QrelError(f"{source}: contains no judgements; an empty qrel set gates nothing")
    return QrelSet.build(judgements)


def qrels_json_schema() -> dict[str, object]:
    """JSON Schema for one judgement line, with the rubric embedded in the description."""
    schema = Judgement.model_json_schema()
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    schema["$id"] = "https://mainline.dev/schema/recall/qrels-v1.schema.json"
    schema["title"] = "TRAPPOINT recall relevance judgement (UMBRELA 0-3)"
    schema["description"] = (
        "One line of a recall qrels JSONL file. Grade meanings: "
        + "; ".join(f"{k} = {v}" for k, v in GRADE_MEANINGS.items())
        + f". Grades >= {BLOCKING_RELEVANCE_FLOOR} count as relevant for binary metrics."
    )
    return schema


def write_qrels_json_schema(path: Path | str) -> Path:
    """Write the schema to ``path`` with a trailing newline. Returns the path written."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(qrels_json_schema(), indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return target


PACKAGED_SCHEMA_RELPATH: Final = "schema/qrels-v1.schema.json"
"""Location of the committed schema inside this package, checked for drift in CI."""
