# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""G3 — the adjudicated set: UMBRELA pre-labelling with human confirmation.

About 200 pairs, graded 0–3 on the UMBRELA scale, and the only gold set ``P@block`` is
allowed to be computed over. The workflow has three steps and each one exists because of
a specific way the number could otherwise be wrong.

**1. Pre-label with the model.** UMBRELA (arXiv:2406.06519) shows an LLM can produce
useful graded relevance at scale. It also shows LLMs grade *more generously* than humans.
So a pre-label is a starting point, not a judgement.

**2. Emit a worksheet and have humans confirm it.** :func:`emit_worksheet` writes one
line per pair with the pre-label, the rubric and *blank* confirmation fields. Humans fill
them in. The pre-label is visible — hiding it would make the task slower without making
it better — but the confirmation is a separate field, so "the human agreed" and "the
human never looked" are distinguishable states rather than the same blank.

**3. Ingest confirmations and record disagreement.** :func:`ingest_confirmations` takes
the returned worksheet and produces judgements *plus* an agreement report: exact
agreement, adjacent agreement, Cohen's kappa between the two raters, and the
LLM-versus-human agreement that quantifies step 1's generosity. Pairs where the raters
disagree and no adjudicator broke the tie are **excluded and counted** — never averaged.
Averaging two raters who disagree produces a grade neither of them would defend, and the
whole force of ``P@block`` is that a human would defend every label in it.

The tagging rule that ``P@block`` enforces for us
--------------------------------------------------
A human-confirmed pair is written ``judged_by='human', blinded=True``. An unconfirmed
pair keeps its pre-label and is written ``judged_by='llm', blinded=False``.
:func:`~trappoint_recall.eval.metrics.p_at_block` computes only over blinded judgements,
so an LLM-only label is refused by the metric itself — no reviewer has to remember.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Annotated, Final, Literal

from pydantic import BaseModel, ConfigDict, Field

from trappoint_recall.eval.qrels import GRADE_MEANINGS, Judgement

__all__ = [
    "G3_GOLD_SET",
    "UMBRELA_RUBRIC",
    "AdjudicationItem",
    "AdjudicationReport",
    "Confirmation",
    "G3Result",
    "WorksheetError",
    "cohens_kappa",
    "emit_worksheet",
    "g3_query_id",
    "ingest_confirmations",
    "load_worksheet",
]

G3_GOLD_SET: Final = "G3"

UMBRELA_RUBRIC: Final[str] = (
    "Grade the relevance of the candidate incident to the permit, 0-3. "
    + " | ".join(f"{grade} = {meaning}" for grade, meaning in GRADE_MEANINGS.items())
    + " | A grade of 2 or 3 means a supervisor should be required to disposition this "
    "incident before the permit merges. Name the shared mechanism and the shared "
    "precondition explicitly, or grade 0."
)
"""The rubric shown to the model and to the humans. Byte-identical for both.

Two rubrics would make the LLM-versus-human agreement figure meaningless — it would be
measuring the difference between the prompts rather than between the judges."""


class WorksheetError(ValueError):
    """Raised when an adjudication worksheet is malformed or inconsistent."""


def g3_query_id(ref: str) -> str:
    """``Q-G3-<ref>``. Its own namespace, so G3 never silently merges with G1 or G2."""
    return f"Q-G3-{ref}"


class AdjudicationItem(BaseModel):
    """One pair presented for adjudication, with its model pre-label."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    pair_id: Annotated[str, Field(min_length=1, description="Stable id for this pair.")]
    query_id: Annotated[str, Field(min_length=1)]
    doc_id: Annotated[str, Field(min_length=1)]
    query_text: Annotated[str, Field(min_length=1, description="The permit, as shown.")]
    doc_text: Annotated[str, Field(min_length=1, description="The candidate, as shown.")]
    llm_grade: Annotated[
        int, Field(ge=0, le=3, description="UMBRELA pre-label. Never a final grade.")
    ]
    llm_rationale: Annotated[
        str,
        Field(
            min_length=1,
            description="Why the model graded it so, naming mechanism and precondition.",
        ),
    ]
    model_id: Annotated[str, Field(min_length=1, description="Which model pre-labelled.")]
    prompt_version: Annotated[str, Field(min_length=1)]

    def worksheet_row(self) -> dict[str, object]:
        """The line a human is asked to fill in. Confirmation fields start empty."""
        return {
            "pair_id": self.pair_id,
            "query_id": self.query_id,
            "doc_id": self.doc_id,
            "query_text": self.query_text,
            "doc_text": self.doc_text,
            "llm_grade": self.llm_grade,
            "llm_rationale": self.llm_rationale,
            "model_id": self.model_id,
            "prompt_version": self.prompt_version,
            "rubric": UMBRELA_RUBRIC,
            "rater_a": "",
            "grade_a": None,
            "rater_b": "",
            "grade_b": None,
            "adjudicator": "",
            "grade_final": None,
            "confirmed_at": None,
        }


class Confirmation(BaseModel):
    """A returned worksheet line."""

    model_config = ConfigDict(frozen=True, extra="ignore")

    pair_id: Annotated[str, Field(min_length=1)]
    rater_a: Annotated[str, Field(description="Identifier of the first human rater.")] = ""
    grade_a: Annotated[int | None, Field(ge=0, le=3)] = None
    rater_b: Annotated[str, Field(description="Identifier of the second human rater.")] = ""
    grade_b: Annotated[int | None, Field(ge=0, le=3)] = None
    adjudicator: Annotated[str, Field(description="Tie-breaker, when the two disagree.")] = ""
    grade_final: Annotated[
        int | None,
        Field(ge=0, le=3, description="Set by the adjudicator. Required when a and b differ."),
    ] = None
    confirmed_at: datetime | None = None

    @property
    def human_grades(self) -> tuple[int, ...]:
        return tuple(g for g in (self.grade_a, self.grade_b) if g is not None)

    @property
    def resolved_grade(self) -> int | None:
        """The grade a human would defend, or ``None``.

        ``None`` when nobody graded it, or when two raters disagreed and no adjudicator
        broke the tie. Never a mean: an averaged 1.5 is a grade neither rater would sign.
        """
        if self.grade_final is not None:
            return self.grade_final
        grades = self.human_grades
        if not grades:
            return None
        if len(grades) == 1:
            return grades[0]
        return grades[0] if grades[0] == grades[1] else None


@dataclass(frozen=True, slots=True)
class AdjudicationReport:
    """Agreement statistics, published with the gold set.

    ``kappa`` is Cohen's kappa on the raw 0–3 scale over pairs both raters graded.
    ``None`` when fewer than two pairs have two grades, or when one rater used a single
    category throughout — kappa is undefined there, and reporting 0.0 would look like
    catastrophic disagreement rather than an undefined statistic.
    """

    n_items: int
    n_confirmed: int
    n_llm_only: int
    n_unresolved: int
    n_double_graded: int
    n_exact_agreement: int
    n_adjacent_agreement: int
    kappa: float | None
    kappa_undefined_reason: str | None
    n_llm_matches_human: int
    n_llm_stricter: int
    n_llm_more_generous: int

    def __post_init__(self) -> None:
        accounted = self.n_confirmed + self.n_llm_only + self.n_unresolved
        if accounted != self.n_items:
            raise ValueError(
                f"adjudication accounting does not close: confirmed {self.n_confirmed} + "
                f"llm-only {self.n_llm_only} + unresolved {self.n_unresolved} != "
                f"{self.n_items} items"
            )

    @property
    def exact_agreement_rate_per_1000(self) -> int | None:
        if not self.n_double_graded:
            return None
        return round(1000 * self.n_exact_agreement / self.n_double_graded)

    def to_dict(self) -> dict[str, object]:
        return {
            "n_items": self.n_items,
            "n_confirmed": self.n_confirmed,
            "n_llm_only": self.n_llm_only,
            "n_unresolved": self.n_unresolved,
            "n_double_graded": self.n_double_graded,
            "n_exact_agreement": self.n_exact_agreement,
            "n_adjacent_agreement": self.n_adjacent_agreement,
            "exact_agreement_rate_per_1000": self.exact_agreement_rate_per_1000,
            "cohens_kappa": self.kappa,
            "cohens_kappa_undefined_reason": self.kappa_undefined_reason,
            "llm_vs_human": {
                "matches": self.n_llm_matches_human,
                "llm_stricter": self.n_llm_stricter,
                "llm_more_generous": self.n_llm_more_generous,
            },
            "note": (
                "LLM-only labels are tagged judged_by='llm' and blinded=False, so "
                "p_at_block skips them. Humans grade stricter than LLMs (UMBRELA), and "
                "the llm_more_generous count is the size of that effect on this set."
            ),
        }


def cohens_kappa(
    pairs: Sequence[tuple[int, int]], *, categories: Sequence[int] = (0, 1, 2, 3)
) -> tuple[float | None, str | None]:
    """Cohen's kappa, or ``(None, reason)`` when it is undefined.

    Returns ``(None, reason)`` rather than 0.0 when expected agreement is 1.0 — which
    happens when both raters used exactly one category. That is perfect agreement with an
    undefined chance correction, and reporting 0.0 would read as total disagreement.
    """
    n = len(pairs)
    if n < 2:
        return None, "fewer than two double-graded pairs"
    observed = sum(1 for a, b in pairs if a == b) / n
    marginal_a = {c: sum(1 for a, _ in pairs if a == c) / n for c in categories}
    marginal_b = {c: sum(1 for _, b in pairs if b == c) / n for c in categories}
    expected = sum(marginal_a[c] * marginal_b[c] for c in categories)
    if abs(1.0 - expected) < 1e-12:
        return None, "expected agreement is 1.0; kappa is undefined (both raters used one category)"
    return (observed - expected) / (1.0 - expected), None


def emit_worksheet(items: Sequence[AdjudicationItem], path: Path | str) -> Path:
    """Write the adjudication worksheet as JSONL, one pair per line.

    Deterministic order by ``pair_id`` so two people asked to adjudicate the same set get
    the same file, and a partially completed worksheet can be diffed against the original.
    """
    from trappoint_recall.corpora.emit import write_jsonl

    ordered = sorted(items, key=lambda i: i.pair_id)
    seen: set[str] = set()
    for item in ordered:
        if item.pair_id in seen:
            raise WorksheetError(f"duplicate pair_id {item.pair_id!r} in worksheet")
        seen.add(item.pair_id)
    return write_jsonl(path, (item.worksheet_row() for item in ordered))


def load_worksheet(path: Path | str) -> tuple[Confirmation, ...]:
    """Read a returned worksheet into confirmations, reporting the line on failure."""
    source = Path(path)
    if not source.is_file():
        raise WorksheetError(f"worksheet not found: {source}")
    out: list[Confirmation] = []
    with source.open("r", encoding="utf-8") as handle:
        for lineno, raw in enumerate(handle, start=1):
            line = raw.strip()
            if not line or line.startswith("//"):
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError as exc:
                raise WorksheetError(f"{source}:{lineno}: not valid JSON: {exc}") from exc
            try:
                out.append(Confirmation.model_validate(payload))
            except Exception as exc:
                raise WorksheetError(f"{source}:{lineno}: invalid confirmation: {exc}") from exc
    return tuple(out)


@dataclass(frozen=True, slots=True)
class G3Result:
    """Judgements plus the agreement report they must always be quoted with."""

    judgements: tuple[Judgement, ...]
    report: AdjudicationReport

    @property
    def blinded_human(self) -> tuple[Judgement, ...]:
        return tuple(j for j in self.judgements if j.judged_by == "human" and j.blinded)


AdjudicationPolicy = Literal["confirmed_only", "keep_llm_tagged"]


def ingest_confirmations(
    items: Sequence[AdjudicationItem],
    confirmations: Iterable[Confirmation],
    *,
    policy: AdjudicationPolicy = "keep_llm_tagged",
) -> G3Result:
    """Combine pre-labels with returned confirmations into judgements plus a report.

    Args:
        items: The pairs that were sent out.
        confirmations: What came back. Missing pairs are treated as unconfirmed.
        policy: ``keep_llm_tagged`` emits unconfirmed pairs as ``judged_by='llm',
            blinded=False`` so they remain available to the calibrator while being
            refused by ``P@block``. ``confirmed_only`` drops them entirely.

    Returns:
        :class:`G3Result`. Unresolved pairs — two raters, no agreement, no adjudicator —
        are never emitted under either policy, and are counted.
    """
    by_pair = {c.pair_id: c for c in confirmations}
    judgements: list[Judgement] = []
    double_graded: list[tuple[int, int]] = []
    n_confirmed = 0
    n_llm_only = 0
    n_unresolved = 0
    n_exact = 0
    n_adjacent = 0
    llm_match = 0
    llm_stricter = 0
    llm_generous = 0

    for item in sorted(items, key=lambda i: i.pair_id):
        confirmation = by_pair.get(item.pair_id)
        if confirmation is not None and len(confirmation.human_grades) == 2:
            a, b = confirmation.human_grades
            double_graded.append((a, b))
            if a == b:
                n_exact += 1
            if abs(a - b) <= 1:
                n_adjacent += 1
        resolved = confirmation.resolved_grade if confirmation else None
        if confirmation is not None and resolved is None and confirmation.human_grades:
            n_unresolved += 1
            continue
        if resolved is None:
            n_llm_only += 1
            if policy == "keep_llm_tagged":
                judgements.append(
                    Judgement(
                        query_id=item.query_id,
                        doc_id=item.doc_id,
                        grade=item.llm_grade,
                        gold_set=G3_GOLD_SET,
                        judged_by="llm",
                        blinded=False,
                        notes=(
                            f"LLM pre-label only, unconfirmed. model={item.model_id} "
                            f"prompt={item.prompt_version}. Refused by p_at_block because "
                            "it is not blinded."
                        ),
                    )
                )
            continue
        n_confirmed += 1
        if resolved == item.llm_grade:
            llm_match += 1
        elif item.llm_grade > resolved:
            llm_generous += 1
        else:
            llm_stricter += 1
        raters = ", ".join(
            r for r in (confirmation.rater_a, confirmation.rater_b, confirmation.adjudicator) if r
        ) if confirmation else ""
        judgements.append(
            Judgement(
                query_id=item.query_id,
                doc_id=item.doc_id,
                grade=resolved,
                gold_set=G3_GOLD_SET,
                judged_by="human",
                judged_at=confirmation.confirmed_at if confirmation else None,
                blinded=True,
                notes=(
                    f"human-confirmed by {raters or 'unnamed rater'}; "
                    f"llm pre-label was {item.llm_grade}"
                ),
            )
        )

    kappa, kappa_reason = cohens_kappa(double_graded)
    report = AdjudicationReport(
        n_items=len(items),
        n_confirmed=n_confirmed,
        n_llm_only=n_llm_only,
        n_unresolved=n_unresolved,
        n_double_graded=len(double_graded),
        n_exact_agreement=n_exact,
        n_adjacent_agreement=n_adjacent,
        kappa=kappa,
        kappa_undefined_reason=kappa_reason,
        n_llm_matches_human=llm_match,
        n_llm_stricter=llm_stricter,
        n_llm_more_generous=llm_generous,
    )
    return G3Result(judgements=tuple(judgements), report=report)


_ITEM_FIELDS: Final[tuple[str, ...]] = tuple(AdjudicationItem.model_fields)


def worksheet_items_from_rows(rows: Iterable[Mapping[str, object]]) -> tuple[AdjudicationItem, ...]:
    """Validate raw worksheet rows into :class:`AdjudicationItem`s.

    A returned worksheet carries the item fields *and* the confirmation fields on one
    line, so the item fields are projected out explicitly rather than by loosening the
    model to ``extra='ignore'``: a typo in an item field must still be an error, and
    ``ignore`` would swallow it.
    """
    return tuple(
        AdjudicationItem.model_validate({k: row[k] for k in _ITEM_FIELDS if k in row})
        for row in rows
    )
