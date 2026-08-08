# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""The auditor persona: the questions a general counsel actually asks, routed to views.

This is the *catalogue* half of the auditor path, not an agent. The agent in this story
is the judge's own — ``ARCHITECTURE.md`` §10.3 is explicit that the auditor path
"contains none of our code", and decision A2 keeps it that way. What we own is the
mapping from a question to the one contracted view that answers it, and the guarantee
that the answer arrives with its completeness stated.

Three properties, and the third is the one that matters in this product:

* **Routing is deterministic.** Cue-phrase and token scoring, no model, no sampling. The
  same question routes to the same view on every machine, forever, and the routing table
  is data a reader can check rather than a behaviour they must trust.

* **A question can never become arbitrary SQL.** :meth:`AuditorPersona.ask` resolves a
  question to a :class:`~mainline_mcp.catalogue.ViewSpec` and then sends *that view's*
  generated statement. There is no path from question text into a statement. An
  unroutable question is a refusal (:class:`UnroutableQuestion`), never a guess — a
  wrong view answered confidently is worse than no answer.

* **Every rendered answer states its completeness.** Not only when it is truncated: the
  four completeness states are *complete*, *incomplete*, *flag missing* and *this view
  carries no flag by contract*, and one of them appears on every answer. An aggregate
  that silently truncated is a safety defect here, so "the flag was absent" has to be
  visible in the answer rather than inferable from its absence.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Final

from .catalogue import Catalogue, ViewSpec
from .client import Client
from .limits import McpClientError

_WORD: Final = re.compile(r"[a-z0-9_]+")
_STOPWORDS: Final = frozenset(
    {
        "a",
        "an",
        "and",
        "any",
        "are",
        "as",
        "at",
        "be",
        "been",
        "by",
        "did",
        "do",
        "does",
        "for",
        "from",
        "has",
        "have",
        "how",
        "in",
        "is",
        "it",
        "its",
        "me",
        "of",
        "on",
        "or",
        "show",
        "so",
        "tell",
        "that",
        "the",
        "their",
        "there",
        "these",
        "this",
        "to",
        "us",
        "was",
        "were",
        "what",
        "when",
        "which",
        "who",
        "why",
        "with",
        "you",
        "your",
    }
)
_CUE_WEIGHT: Final = 4
_TOKEN_WEIGHT: Final = 1


class Completeness(StrEnum):
    """How complete an answer is known to be."""

    COMPLETE = "complete"
    INCOMPLETE = "incomplete"
    FLAG_MISSING = "flag_missing"
    NO_FLAG = "no_flag"
    UNKNOWN = "unknown"


class UnroutableQuestion(McpClientError):
    """No contracted view answers this question, and guessing one would be worse."""


@dataclass(frozen=True, slots=True)
class Question:
    """One question the audit surface is built to answer, bound to exactly one view."""

    id: str
    canonical: str
    view: str
    cues: tuple[str, ...]
    why: str

    def score(self, normalised: str, tokens: frozenset[str]) -> int:
        """Score this question against a normalised question string and its tokens."""
        cue_hits = sum(_CUE_WEIGHT for cue in self.cues if cue in normalised)
        overlap = len(tokens & _tokenise(self.canonical)) * _TOKEN_WEIGHT
        return cue_hits + overlap


def _tokenise(text: str) -> frozenset[str]:
    """Lower-case content words, stopwords removed."""
    return frozenset(w for w in _WORD.findall(text.lower()) if w not in _STOPWORDS)


def _normalise(text: str) -> str:
    """Lower-case, whitespace-collapsed text for cue-phrase matching."""
    return " ".join(text.lower().split())


AUDITOR_QUESTIONS: Final = (
    Question(
        id="Q1",
        canonical="which weakenings of blood-written controls have no disposition?",
        view="v_weakenings_without_disposition",
        cues=(
            "weakening",
            "weaken",
            "no disposition",
            "without disposition",
            "undispositioned",
            "blood-written",
            "blood written",
            "removed control",
        ),
        why=(
            "The flagship question. A clause that weakened or removed a control written "
            "by a severity-4-or-worse incident, with no live disposition against it."
        ),
    ),
    Question(
        id="Q2",
        canonical="what did you decline to surface, and with what arithmetic?",
        view="v_silence_summary",
        cues=(
            "decline",
            "declined",
            "silence",
            "silenced",
            "suppress",
            "not surface",
            "threshold",
            "nearest miss",
            "arithmetic",
        ),
        why=(
            "Silence is a row. The mean score, the mean threshold and the nearest miss "
            "are what turn 'we found nothing' into a checkable claim."
        ),
    ),
    Question(
        id="Q3",
        canonical="is the ledger healthy?",
        view="v_ledger_health",
        cues=(
            "ledger",
            "checkpoint",
            "custody",
            "tree size",
            "witness",
            "unwitnessed",
            "admissible",
        ),
        why="Checkpoint cadence, admissibility, and how much witness debt is open.",
    ),
    Question(
        id="Q4",
        canonical="what has the agent fleet been doing?",
        view="v_agent_actions",
        cues=("fleet", "agent", "agents", "been doing", "activity", "tool", "actions"),
        why="Which agent role used which tool, with what outcome, over the last week.",
    ),
    Question(
        id="Q5",
        canonical="what is blocking merges right now, and where?",
        view="v_open_gate_summary",
        cues=(
            "blocking",
            "blocked",
            "open permit",
            "permits",
            "merge",
            "gate",
            "right now",
            "override",
        ),
        why="Open permits by site and state, with the open blocking checks and overrides.",
    ),
    Question(
        id="Q6",
        canonical="how complete is the blame ancestry, and where is it truncated?",
        view="v_blame_coverage",
        cues=("blame", "ancestry", "closure", "truncated", "depth", "virulence", "coverage"),
        why="Closure depth, generations and truncation, per site and virulence band.",
    ),
    Question(
        id="Q7",
        canonical="are dispositions keeping up with what was surfaced?",
        view="v_disposition_coverage",
        cues=("disposition", "dispositions", "keeping up", "orphan", "signed", "quarter"),
        why="Surfaced against dispositioned by quarter, and the orphaned checks.",
    ),
    Question(
        id="Q8",
        canonical="how much of the recall was conserved, and did any arm degrade?",
        view="v_recall_conservation",
        cues=(
            "recall",
            "conservation",
            "conserved",
            "candidates",
            "deduped",
            "degraded",
            "arm",
            "arms",
        ),
        why="Candidates in, blocking and advisory out, deduped and silenced — per day.",
    ),
    Question(
        id="Q9",
        canonical="is fixity being checked, and what was never checked at all?",
        view="v_fixity_coverage",
        cues=("fixity", "patrol", "not checked", "as-operated", "drift", "last completed"),
        why="Patrol completion and the share of in-scope items never checked.",
    ),
)
"""The routing table. Nine questions, nine views, no overlap.

Every entry is a question a general counsel or a regulator asks in the first ten minutes,
and each resolves to exactly one contracted view. The four ops views in
``ARCHITECTURE.md`` §17 (``v_gate_latency_daily`` and friends) are deliberately absent:
they are the Steward's operational surface, not the auditor's, and putting them here
would invite a reader to mistake an ops metric for an evidentiary one.
"""


@dataclass(frozen=True, slots=True)
class Answer:
    """One answered question: the rows, the size, and how complete the answer is known to be."""

    question: Question
    view: ViewSpec
    statement: str
    rows: tuple[Mapping[str, Any], ...] | None
    response_bytes: int
    completeness: Completeness
    incomplete_rows: int
    elapsed_ms: float

    @property
    def row_count(self) -> int | None:
        """Number of rows, or ``None`` when the envelope could not be parsed."""
        return None if self.rows is None else len(self.rows)

    def completeness_sentence(self) -> str:
        """Return the line that appears on every rendered answer, in all five states."""
        flag = self.view.truncation_flag
        match self.completeness:
            case Completeness.COMPLETE:
                return f"COMPLETE — every row reports {flag} = true."
            case Completeness.INCOMPLETE:
                return (
                    f"INCOMPLETE — {self.incomplete_rows} of {self.row_count} rows report "
                    f"{flag} = false. Those rows summarise a TRUNCATED ancestry and the "
                    "counts beneath them are lower bounds."
                )
            case Completeness.FLAG_MISSING:
                return (
                    f"COMPLETENESS UNKNOWN — the contract says this view carries {flag!r} "
                    "and the returned rows do not. Treat every count here as unverified."
                )
            case Completeness.NO_FLAG:
                return (
                    "NO COMPLETENESS FLAG — this view carries none by contract, so it "
                    "cannot tell you whether anything was truncated."
                )
            case _:
                return (
                    "COMPLETENESS UNKNOWN — the response could not be parsed as rows, so "
                    "neither the count nor its completeness has been verified."
                )

    def render(self) -> str:
        """Render the answer. The completeness sentence is never omitted."""
        header = [
            f"Q ({self.question.id}) {self.question.canonical}",
            f"view: {self.view.qualified}   statement: {self.statement}",
            (
                f"rows: {'?' if self.row_count is None else self.row_count}"
                f"   bytes: {self.response_bytes}   {self.elapsed_ms:.0f} ms"
            ),
            self.completeness_sentence(),
        ]
        if not self.rows:
            header.append("(no rows)")
            return "\n".join(header)
        columns = list(self.rows[0].keys())
        header.append(" | ".join(columns))
        header.extend(
            " | ".join("" if row.get(col) is None else str(row.get(col)) for col in columns)
            for row in self.rows
        )
        return "\n".join(header)


def _completeness(
    view: ViewSpec, rows: Sequence[Mapping[str, Any]] | None
) -> tuple[Completeness, int]:
    """Decide the completeness state and count the rows that admit truncation."""
    if rows is None:
        return Completeness.UNKNOWN, 0
    if view.truncation_flag is None:
        return Completeness.NO_FLAG, 0
    flag = view.truncation_flag
    if any(flag not in row for row in rows):
        return Completeness.FLAG_MISSING, 0
    incomplete = sum(1 for row in rows if row.get(flag) is False)
    if incomplete:
        return Completeness.INCOMPLETE, incomplete
    return Completeness.COMPLETE, 0


class AuditorPersona:
    """Routes an auditor's question to one contracted view and answers it aggregate-first."""

    def __init__(
        self,
        client: Client,
        catalogue: Catalogue,
        *,
        questions: Sequence[Question] = AUDITOR_QUESTIONS,
    ) -> None:
        """Bind a client and a catalogue. Questions naming an uncontracted view are dropped.

        Dropping rather than raising is deliberate: the contract is another worker's file
        and may legitimately land one view at a time. :meth:`unanswerable` reports which
        questions have no view, so a partial contract is a visible gap in the persona's
        coverage rather than an import-time crash.
        """
        self._client = client
        self._catalogue = catalogue
        self._all = tuple(questions)
        self._questions = tuple(q for q in self._all if catalogue.has(q.view))

    @property
    def questions(self) -> tuple[Question, ...]:
        """The questions this persona can currently answer."""
        return self._questions

    def unanswerable(self) -> tuple[Question, ...]:
        """Questions whose view is not in the contract, and therefore cannot be answered."""
        return tuple(q for q in self._all if not self._catalogue.has(q.view))

    def route(self, question: str) -> Question:
        """Resolve free text to exactly one contracted question, or refuse."""
        normalised = _normalise(question)
        tokens = _tokenise(question)
        if not tokens:
            raise UnroutableQuestion("an empty question routes to nothing")
        scored = sorted(
            ((q.score(normalised, tokens), q.id, q) for q in self._questions),
            key=lambda triple: (-triple[0], triple[1]),
        )
        if not scored or scored[0][0] == 0:
            available = ", ".join(f"{q.id}: {q.canonical}" for q in self._questions)
            raise UnroutableQuestion(
                f"no contracted audit view answers {question!r}. Guessing one would answer a "
                f"different question confidently, which is worse than refusing. Available — "
                f"{available}"
            )
        return scored[0][2]

    def answer(self, question: Question) -> Answer:
        """Run one contracted question's view and return the answer with its completeness."""
        view = self._catalogue.by_name(question.view)
        result = self._client.select_query(view.statement, max_rows=view.row_cap)
        completeness, incomplete = _completeness(view, result.rows)
        return Answer(
            question=question,
            view=view,
            statement=view.statement,
            rows=result.rows,
            response_bytes=result.byte_count,
            completeness=completeness,
            incomplete_rows=incomplete,
            elapsed_ms=self._client.last_elapsed_ms,
        )

    def ask(self, question: str) -> Answer:
        """Route free text to a view and answer it."""
        return self.answer(self.route(question))

    def brief(self) -> str:
        """Answer every question this persona can answer, in one rendered brief."""
        blocks = [answer.render() for answer in (self.answer(q) for q in self._questions)]
        missing = self.unanswerable()
        if missing:
            blocks.append(
                "NOT ANSWERABLE — the audit-surface contract does not yet carry a view for: "
                + ", ".join(f"{q.id} ({q.view})" for q in missing)
            )
        return "\n\n".join(blocks)
