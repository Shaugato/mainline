# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""The auditor persona: the questions a general counsel actually asks, deterministically routed.

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
  question to a :class:`~mainline_mcp.catalogue.ViewSpec` or to the single
  :class:`PlanProbe`, and then sends *that target's* generated statement. There is no
  path from question text into a statement. An unroutable question is a refusal
  (:class:`UnroutableQuestion`), never a guess — a wrong view answered confidently is
  worse than no answer.

* **Every rendered answer states its completeness.** Not only when it is truncated: one
  of the :class:`Completeness` states appears on every answer. An aggregate that silently
  truncated is a safety defect here, so "the flag was absent" has to be visible in the
  answer rather than inferable from its absence.

WHAT THE 2026-08-16 LIVE RUN CHANGED, AND WHY
----------------------------------------------
Until 2026-08-16 this module had never been run against ``cockroachlabs.cloud/mcp``; the
package README said so. The first live run corrected three things, each of them a case of
the endpoint proving the code wrong rather than the code being tidied:

1. **``select_query`` and ``explain_query`` require ``database``.** Neither
   :class:`AuditorPersona` nor :class:`~mainline_mcp.budget.BudgetProber` sent one, so
   neither could have answered a single question live. ``database`` is now a keyword
   argument on both, defaulting to ``None`` so the offline suites are unaffected.

2. **A zero-row answer used to render "COMPLETE — every row reports ``x`` = true".**
   That is a claim about rows that do not exist, and it fired on the flagship question:
   ``v_weakenings_without_disposition`` returns **zero rows** on the live demo cluster.
   :attr:`Completeness.VACUOUS` exists because of that measurement. Zero rows and zero
   findings-verified-complete are different facts and only one of them was observed.

3. **The vector-index plan is a routed question, not a side errand.** ``Q10`` asks *did
   the search actually use the index* and resolves to :data:`VECTOR_PLAN_PROBE`, whose
   ``EXPLAIN`` is generated here exactly as a view's ``SELECT`` is. It is the one target
   in the table that is a tool rather than a view, and it is in the table because it is
   the third of the three questions the plan's ruling R6 names.
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
    """How complete an answer is known to be.

    :attr:`VACUOUS` is the sixth state and the newest. It was added on 2026-08-16 because
    the live surface produced a case the other five described dishonestly: a view that
    contracts a completeness flag and returns **no rows** was rendering ``COMPLETE —
    every row reports ancestry_complete = true``, which is a statement about rows that do
    not exist. The flag was never observed, so no state that claims to have observed it
    may be written.
    """

    COMPLETE = "complete"
    INCOMPLETE = "incomplete"
    FLAG_MISSING = "flag_missing"
    NO_FLAG = "no_flag"
    VACUOUS = "vacuous"
    UNKNOWN = "unknown"


class UnroutableQuestion(McpClientError):
    """No contracted view answers this question, and guessing one would be worse."""


@dataclass(frozen=True, slots=True)
class PlanProbe:
    """The one routing target that is not a view: a query plan, proved by ``EXPLAIN``.

    Every other question in this module asks the memory layer *what it remembers*. This
    one asks *how it went and got it* — and it is the only question whose answer a judge
    can check without trusting a single row of our data, because the plan is rendered by
    CockroachDB's own optimizer and returned over CockroachDB's own endpoint.

    Three things about it are deliberate:

    * **The statement is generated here, from these fields.** Exactly as
      :attr:`~mainline_mcp.catalogue.ViewSpec.statement` is generated from the contract.
      No caller text reaches it, so the persona's "a question can never become arbitrary
      SQL" property is unchanged by adding a tool target to the table.

    * **The index hint is mandatory and that is a recorded weakness, not a flourish.**
      ADR 0002 GT-06/GT-06b: at demo corpus scale the optimizer does *not* choose the
      vector index unhinted — the unhinted plan is top-k, render, filter, scan. The index
      is traversed **when named**. Asserting traversal of the *named* index is therefore
      the assertion that is true; an unhinted assertion would fail here, and would be
      failing correctly.

    * **The probe vector's contents are meaningless and that is safe.** ``EXPLAIN``
      without ``ANALYZE`` does not execute, so the plan is a property of the query's
      shape, not of the vector's values. A zero vector keeps the statement deterministic
      and keeps this module free of a sampled literal.
    """

    tool: str
    table: str
    index_name: str
    projection: str
    prefix_predicates: tuple[tuple[str, str], ...]
    vector_column: str
    vector_dimension: int
    row_limit: int
    required_substrings: tuple[str, ...]
    defined_in: str

    @property
    def index(self) -> str:
        """The index as a plan names it: ``schema.table@index``."""
        return f"{self.table}@{self.index_name}"

    @property
    def truncation_flag(self) -> str | None:
        """``None``: a query plan carries no completeness flag.

        Its truncation risk is real but differently shaped — the server's 10 240-byte
        response cap silently truncates a long plan — and that risk is measured by
        :attr:`Answer.response_bytes` against the cap, not by a column.
        """
        return None

    @property
    def name(self) -> str:
        """A stable identifier for this target, used where a view name would be."""
        return f"{self.tool}:{self.index}"

    @property
    def qualified(self) -> str:
        """How the target is named on a rendered answer."""
        return f"{self.index} via {self.tool}"

    @property
    def probe_vector(self) -> str:
        """The deterministic placeholder vector literal."""
        return "[" + ",".join("0" for _ in range(self.vector_dimension)) + "]"

    @property
    def statement(self) -> str:
        """The exact statement sent for this probe, generated and never caller-supplied.

        The leading ``EXPLAIN`` is **omitted on purpose**: the Managed MCP
        ``explain_query`` tool prepends its own, and a statement that already carries one
        comes back ``EXPLAIN is not allowed for EXPLAIN statements``. Measured
        2026-08-16 against the live endpoint.
        """
        where = "\n   AND ".join(
            f"{column} = {literal}" for column, literal in self.prefix_predicates
        )
        # S608: every interpolated value on this path is a field of a module-level
        # constant — a table name, an index name, a column name, a generated numeric
        # literal. No caller-supplied text reaches here; that is the property the
        # persona's routing guarantee rests on.
        return (
            f"SELECT {self.projection}\n"  # noqa: S608
            f"  FROM {self.index}\n"
            f" WHERE {where}\n"
            f" ORDER BY {self.vector_column_expr}\n"
            f" LIMIT {self.row_limit}"
        )

    @property
    def vector_column_expr(self) -> str:
        """The ANN ordering term: the vector column against the placeholder literal."""
        return f"{self.vector_column} <=> '{self.probe_vector}'::VECTOR({self.vector_dimension})"

    def missing_substrings(self, plan_text: str) -> tuple[str, ...]:
        """Return the required plan fragments the returned plan does **not** contain."""
        lowered = plan_text.lower()
        return tuple(s for s in self.required_substrings if s.lower() not in lowered)

    def names_the_index(self, plan_text: str) -> bool:
        """Whether the returned plan names the index this probe pinned."""
        return self.index.rsplit(".", 1)[-1] in plan_text


VECTOR_PLAN_PROBE: Final = PlanProbe(
    tool="explain_query",
    table="mainline.event_cue_embedding",
    index_name="cue_scoped_idx",
    projection="cue_id",
    prefix_predicates=(
        ("site_id", "'00000000-0000-0000-0000-000000000000'::UUID"),
        ("scope_id", "'00000000-0000-0000-0000-000000000000'::UUID"),
        ("facet", "'cue'"),
    ),
    vector_column="emb",
    vector_dimension=1024,
    row_limit=10,
    required_substrings=("vector search", "prefix spans"),
    defined_in="verticals/mainline/db/migrations/0041_event_cue_embedding.sql:46-56",
)
"""The vector-index plan probe, every field transcribed from the migration that defines it.

``site_id`` and ``scope_id`` are ``UUID`` and ``facet`` is ``STRING`` in that migration,
which is why the literals are shaped as they are. The types are not a guess: sending
``site_id = 'KAL'`` to the live endpoint on 2026-08-16 returned ``could not parse "KAL" as
type uuid``, so a wrong type here is a refusal rather than a quiet mis-plan. The two
required substrings are ``verticals/mainline/demo/REFUSAL-STRINGS.yaml``
``explain_fragment.required_substrings``.
"""


@dataclass(frozen=True, slots=True)
class Question:
    """One question the audit surface is built to answer, bound to exactly one target.

    ``view`` names a contracted ``mainline_audit`` view; ``probe`` names the single
    :class:`PlanProbe`. Exactly one of the two is set — :func:`_validate_questions`
    asserts it at import time, because a question with neither target routes to nothing
    and a question with both is ambiguous about what it actually asked.
    """

    id: str
    canonical: str
    cues: tuple[str, ...]
    why: str
    view: str | None = None
    probe: PlanProbe | None = None

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
    Question(
        id="Q10",
        canonical="did the vector search actually use an index? show me the plan.",
        probe=VECTOR_PLAN_PROBE,
        cues=(
            "plan",
            "index",
            "vector",
            "vector search",
            "traversed",
            "ann",
            "explain",
            "actually use",
            "nearest neighbour",
            "nearest neighbor",
        ),
        why=(
            "The retrieval half of store-retrieve-act, and the only question whose answer "
            "is rendered by CockroachDB's optimizer rather than by our data. A recall "
            "claim that never proves the index was traversed is a claim about a scan."
        ),
    ),
)
"""The routing table. Ten questions, ten targets, no overlap.

Nine resolve to exactly one contracted ``mainline_audit`` view; the tenth resolves to
:data:`VECTOR_PLAN_PROBE`. Every entry is a question a general counsel or a regulator
asks in the first ten minutes.

The four ops views in ``ARCHITECTURE.md`` §17 (``v_gate_latency_daily`` and friends) are
deliberately absent: they are the Steward's operational surface, not the auditor's, and
putting them here would invite a reader to mistake an ops metric for an evidentiary one.
"""


def _validate_questions(questions: Sequence[Question]) -> None:
    """Refuse a routing table whose entries do not each name exactly one target."""
    for question in questions:
        if (question.view is None) == (question.probe is None):
            raise ValueError(
                f"{question.id} must name exactly one target: it has "
                f"view={question.view!r} and probe={question.probe!r}"
            )


_validate_questions(AUDITOR_QUESTIONS)


@dataclass(frozen=True, slots=True)
class Answer:
    """One answered question: the rows, the size, and how complete the answer is known to be."""

    question: Question
    target: ViewSpec | PlanProbe
    statement: str
    rows: tuple[Mapping[str, Any], ...] | None
    response_bytes: int
    completeness: Completeness
    incomplete_rows: int
    elapsed_ms: float
    plan_text: str = ""

    @property
    def view(self) -> ViewSpec | None:
        """The contracted view this answer came from, or ``None`` for the plan probe."""
        return self.target if isinstance(self.target, ViewSpec) else None

    @property
    def plan(self) -> PlanProbe | None:
        """The plan probe this answer came from, or ``None`` for a view question."""
        return self.target if isinstance(self.target, PlanProbe) else None

    @property
    def row_count(self) -> int | None:
        """Number of rows, or ``None`` when the envelope could not be parsed."""
        return None if self.rows is None else len(self.rows)

    @property
    def missing_plan_substrings(self) -> tuple[str, ...]:
        """Required plan fragments absent from the plan, or ``()`` for a view question."""
        probe = self.plan
        return () if probe is None else probe.missing_substrings(self.plan_text)

    @property
    def plan_holds(self) -> bool | None:
        """Whether the plan named the pinned index and rendered every required fragment.

        ``None`` for a view question, which has no plan to hold or fail.
        """
        probe = self.plan
        if probe is None:
            return None
        return probe.names_the_index(self.plan_text) and not self.missing_plan_substrings

    def completeness_sentence(self) -> str:
        """Return the line that appears on every rendered answer, in every state."""
        flag = self.target.truncation_flag
        match self.completeness:
            case Completeness.COMPLETE:
                return f"COMPLETE — all {self.row_count} returned rows report {flag} = true."
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
            case Completeness.VACUOUS:
                return (
                    f"COMPLETENESS UNOBSERVED — the view returned no rows, so {flag!r} was "
                    "never observed on anything. Zero rows and zero-findings-verified-"
                    "complete are different facts, and only the first one was measured."
                )
            case Completeness.NO_FLAG:
                return self._no_flag_sentence()
            case _:
                return (
                    "COMPLETENESS UNKNOWN — the response could not be parsed as rows, so "
                    "neither the count nor its completeness has been verified."
                )

    def _no_flag_sentence(self) -> str:
        """Return the no-flag line, which differs for a plan and for a view.

        A plan is not exempt from truncation — the server's byte cap silently cuts a long
        one — so the plan wording states the number that stands in for the missing flag.
        """
        if self.plan is not None:
            return (
                "NO COMPLETENESS FLAG — a query plan carries none. The truncation risk "
                f"here is the server's byte cap, and this plan arrived at "
                f"{self.response_bytes} bytes."
            )
        return (
            "NO COMPLETENESS FLAG — this view carries none by contract, so it "
            "cannot tell you whether anything was truncated."
        )

    def plan_sentence(self) -> str | None:
        """Return the verdict line a plan answer carries beside its completeness."""
        probe = self.plan
        if probe is None:
            return None
        if self.plan_holds:
            return (
                f"PLAN PROVEN — the plan names {probe.index} and renders "
                + ", ".join(repr(s) for s in probe.required_substrings)
                + ". The index was traversed, not scanned."
            )
        missing = self.missing_plan_substrings
        return (
            "PLAN NOT PROVEN — "
            + (
                f"the plan does not name {probe.index}. "
                if not probe.names_the_index(self.plan_text)
                else ""
            )
            + (f"missing required fragments: {list(missing)}." if missing else "")
        ).strip()

    def render(self) -> str:
        """Render the answer. The completeness sentence is never omitted."""
        header = [
            f"Q ({self.question.id}) {self.question.canonical}",
            f"target: {self.target.qualified}   statement: {_abbreviate(self.statement)}",
            (
                f"rows: {'?' if self.row_count is None else self.row_count}"
                f"   bytes: {self.response_bytes}   {self.elapsed_ms:.0f} ms"
            ),
            self.completeness_sentence(),
        ]
        plan_line = self.plan_sentence()
        if plan_line is not None:
            header.append(plan_line)
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


def _abbreviate(statement: str, *, keep: int = 160) -> str:
    """Shorten a statement for rendering. The plan probe's vector literal is 2 047 chars."""
    flat = " ".join(statement.split())
    if len(flat) <= keep:
        return flat
    return f"{flat[:keep]}… ({len(statement)} chars)"


def _completeness(
    target: ViewSpec | PlanProbe, rows: Sequence[Mapping[str, Any]] | None
) -> tuple[Completeness, int]:
    """Decide the completeness state and count the rows that admit truncation.

    The empty-rows branch is the one that was measured into existence. Before
    2026-08-16 an empty result fell through to ``COMPLETE`` because ``any(...)`` and
    ``sum(...)`` over no rows are both falsey — so the flagship question, which returns
    no rows on the live cluster, answered "every row reports ancestry_complete = true"
    about a set with no rows in it.
    """
    if rows is None:
        return Completeness.UNKNOWN, 0
    if target.truncation_flag is None:
        return Completeness.NO_FLAG, 0
    if not rows:
        return Completeness.VACUOUS, 0
    flag = target.truncation_flag
    if any(flag not in row for row in rows):
        return Completeness.FLAG_MISSING, 0
    incomplete = sum(1 for row in rows if row.get(flag) is False)
    if incomplete:
        return Completeness.INCOMPLETE, incomplete
    return Completeness.COMPLETE, 0


class AuditorPersona:
    """Routes an auditor's question to one contracted target and answers it aggregate-first.

    Nine of the ten targets are contracted ``mainline_audit`` views; the tenth is
    :data:`VECTOR_PLAN_PROBE`, an ``EXPLAIN`` whose index is pinned.
    """

    def __init__(
        self,
        client: Client,
        catalogue: Catalogue,
        *,
        questions: Sequence[Question] = AUDITOR_QUESTIONS,
        database: str | None = None,
    ) -> None:
        """Bind a client and a catalogue. Questions naming an uncontracted view are dropped.

        Dropping rather than raising is deliberate: the contract is another worker's file
        and may legitimately land one view at a time. :meth:`unanswerable` reports which
        questions have no view, so a partial contract is a visible gap in the persona's
        coverage rather than an import-time crash.

        Args:
            client: a connected client.
            catalogue: the loaded audit-surface contract.
            questions: the routing table; defaults to :data:`AUDITOR_QUESTIONS`.
            database: the database to send with every tool call. **Required against the
                live endpoint** — ``database`` is a required property of ``select_query``
                and ``explain_query`` in the server's own JSON Schema, measured
                2026-08-16. It defaults to ``None`` so that the offline suites, whose
                stub transport does not care, are unchanged; a live caller that omits it
                gets the server's refusal rather than a silently different answer.
        """
        self._client = client
        self._catalogue = catalogue
        self._database = database
        _validate_questions(questions)
        self._all = tuple(questions)
        self._questions = tuple(q for q in self._all if self._answerable(q))

    def _answerable(self, question: Question) -> bool:
        """Report whether a question can be answered: a plan always, a view if contracted."""
        if question.view is None:
            return True
        return self._catalogue.has(question.view)

    @property
    def database(self) -> str | None:
        """The database sent with every tool call, or ``None`` when none is sent."""
        return self._database

    @property
    def questions(self) -> tuple[Question, ...]:
        """The questions this persona can currently answer."""
        return self._questions

    def unanswerable(self) -> tuple[Question, ...]:
        """Questions whose view is not in the contract, and therefore cannot be answered."""
        return tuple(q for q in self._all if not self._answerable(q))

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
        """Run one routed question's target and return the answer with its completeness."""
        if question.probe is not None:
            return self._answer_plan(question, question.probe)
        assert question.view is not None  # noqa: S101 - _validate_questions guarantees it
        view = self._catalogue.by_name(question.view)
        result = self._client.select_query(
            view.statement, database=self._database, max_rows=view.row_cap
        )
        completeness, incomplete = _completeness(view, result.rows)
        return Answer(
            question=question,
            target=view,
            statement=view.statement,
            rows=result.rows,
            response_bytes=result.byte_count,
            completeness=completeness,
            incomplete_rows=incomplete,
            elapsed_ms=self._client.last_elapsed_ms,
        )

    def _answer_plan(self, question: Question, probe: PlanProbe) -> Answer:
        """Run the plan probe. The plan's own text is what the verdict is read from."""
        result = self._client.explain_query(probe.statement, database=self._database)
        completeness, incomplete = _completeness(probe, result.rows)
        plan_text = result.text or ""
        if result.rows:
            # CockroachDB renders a plan as one row per line under an ``info`` column.
            # Joining them back is what makes "does the plan contain 'vector search'" a
            # question about the plan rather than about the envelope that carried it.
            plan_text = "\n".join(str(row.get("info", "")) for row in result.rows)
        return Answer(
            question=question,
            target=probe,
            statement=probe.statement,
            rows=result.rows,
            response_bytes=result.byte_count,
            completeness=completeness,
            incomplete_rows=incomplete,
            elapsed_ms=self._client.last_elapsed_ms,
            plan_text=plan_text,
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

    def route_target(self, question: Question) -> str:
        """Name what a question routes to, for a transcript that has to show the routing."""
        if question.probe is not None:
            return question.probe.qualified
        assert question.view is not None  # noqa: S101 - _validate_questions guarantees it
        return self._catalogue.by_name(question.view).qualified
