# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
"""A recorded cluster and recorded providers, so the *shipped* run loop is what runs.

Why a recorded session rather than a live one
---------------------------------------------
The kernel band that owns ``permit``, ``blocking_check`` and ``merge_record`` is not on disk
yet, so a run loop exercised end to end against a real cluster would be exercised against
half a schema. More decisively, the shipped code already draws the boundary here: everything
in :mod:`mainline_recall_agent.run` talks to CockroachDB through
:class:`~mainline_recall_agent.run.session.SqlSession`, a protocol, precisely so the whole
loop — channels, fusion, admission, conservation, persistence, the kernel POST — can be run
with no cluster and **without a second implementation of any of it**.

So this module is a recorded database, not a reimplementation of the run:

* every statement is matched against the SQL constant the shipped module actually issues, by
  string identity. A statement this file does not recognise is an :class:`UnknownStatement`
  failure, never an empty result — a silent empty result is how a query that stopped matching
  reality passes a test suite;
* the write side is **transactional**: rows become visible only on a clean exit, so
  "one transaction" is a property the tests can assert rather than a comment;
* ``fn_candidate_project`` is simulated by projecting ``severity`` from the corpus's
  ``event.severity_gate`` on read-back — which is what makes
  :func:`~mainline_recall_agent.run.persist.verify_projected_severity` a real check here and
  lets a projection disagreement be injected on purpose.

What it deliberately does **not** stand in for: the database's own CHECK constraints and
triggers. ``candidates_conserved``, ``bonded_fatalities_all_blocking``,
``fn_recall_policy_anchored`` and ``fn_candidate_project`` are exercised against a live
cluster by ``tests/integration/recall_schema``. This suite asserts that the agent never
*presents* a violating write in the first place, which is a different claim and needs both.
"""

from __future__ import annotations

import json
from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

from _run_corpus import (
    ANCESTRY_ROWS,
    BONDED_ROWS,
    CITED_CLAUSES,
    CONTAINMENT,
    E_DUP,
    E_PROB_HI,
    E_PROB_HI2,
    E_PROB_LO,
    E_PROB_SWEEP,
    E_SEV0,
    EVENTS,
    POLICY_ROW,
    SITE_ID,
    THYMOGATE_ROW,
)
from mainline_recall_agent.providers.errors import ModelRefusal, ProviderUnavailable
from mainline_recall_agent.rerank.schema import (
    DegradedRerank,
    RerankedCandidate,
    RerankOutcome,
)
from mainline_recall_agent.run.channels import (
    ANCESTRY_CONTAINMENT_SQL,
    ANCESTRY_SQL,
    BONDED_SEV5_SQL,
    CITED_CLAUSES_SQL,
)
from mainline_recall_agent.run.orchestrator import (
    EVENT_CONTROL_CLASSES_SQL,
    EVENT_SEVERITY_SQL,
)
from mainline_recall_agent.run.persist import (
    INSERT_CANDIDATE_SQL,
    INSERT_CERTIFICATE_SQL,
    INSERT_RECEIPT_SQL,
    INSERT_RUN_SQL,
    INSERT_SILENCE_SQL,
    READ_PROJECTED_SEVERITY_SQL,
)
from mainline_recall_agent.run.policy import POLICY_SQL, THYMOGATE_SQL
from mainline_recall_agent.run.probabilistic import ChannelCOutcome, RetrievedHit

from trappoint_recall.horizon.certificate import ArmCoverage
from trappoint_recall.horizon.fingerprint import PrefixTree

__all__ = [
    "FailingArmRunner",
    "FakeCluster",
    "FakeKernelTransport",
    "FakeSqlError",
    "FixtureArmRunner",
    "FixtureLexicalRunner",
    "FixtureReranker",
    "GuardrailBlockedReranker",
    "RefusingReranker",
    "Statement",
    "UnknownStatement",
    "arm_outcome",
    "lexical_hits",
    "verdicts",
]


class UnknownStatement(AssertionError):
    """The run loop issued SQL this recorded cluster does not know.

    Raised rather than returning no rows. A recorded database that answered an unrecognised
    query with ``[]`` would let a statement drift away from the schema while every test stayed
    green, which is the failure mode a fixture is supposed to prevent, not cause.
    """


class FakeSqlError(Exception):
    """A driver error carrying a SQLSTATE, shaped the way ``psycopg`` exposes one."""

    def __init__(self, sqlstate: str, message: str) -> None:
        super().__init__(f"{sqlstate}: {message}")
        self.sqlstate = sqlstate


@dataclass(frozen=True, slots=True)
class Statement:
    """One statement the run loop issued, as recorded."""

    sql: str
    params: tuple[Any, ...]


def _event_ids(payload: object) -> list[str]:
    """Read the JSON array of event ids the orchestrator binds for an ``IN`` lookup."""
    return [str(item) for item in json.loads(str(payload))]


class _ReadSession:
    """The read half: the eight statements a run issues before it writes anything."""

    def __init__(self, cluster: FakeCluster) -> None:
        self._cluster = cluster

    def query(  # noqa: PLR0911 - one return per recognised statement; see the docstring
        self, sql: str, params: Sequence[object] = ()
    ) -> Sequence[Sequence[Any]]:
        self._cluster.reads.append(Statement(sql=sql, params=tuple(params)))
        cluster = self._cluster

        if sql == POLICY_SQL:
            return [] if cluster.policy_row is None else [cluster.policy_row]
        if sql == THYMOGATE_SQL:
            return [] if cluster.thymogate_row is None else [cluster.thymogate_row]
        if sql == CITED_CLAUSES_SQL:
            return [tuple(row) for row in CITED_CLAUSES]
        if sql == ANCESTRY_SQL:
            return list(cluster.ancestry_rows)
        if sql == ANCESTRY_CONTAINMENT_SQL:
            event_id = UUID(str(params[1]))
            return [(clause, commit) for clause, commit in cluster.containment.get(event_id, ())]
        if sql == BONDED_SEV5_SQL:
            return list(cluster.bonded_rows)
        if sql == EVENT_SEVERITY_SQL:
            wanted = set(_event_ids(params[1]))
            return [
                (event.event_id, event.severity_gate, event.title)
                for event in EVENTS
                if str(event.event_id) in wanted
            ]
        if sql == EVENT_CONTROL_CLASSES_SQL:
            wanted = set(_event_ids(params[0]))
            return [
                (event.event_id, list(event.control_classes))
                for event in EVENTS
                if str(event.event_id) in wanted and event.control_classes
            ]
        raise UnknownStatement(f"the run loop issued an unrecognised statement:\n{sql}")

    def execute(self, sql: str, params: Sequence[object] = ()) -> None:
        raise UnknownStatement(
            f"a write was issued outside the run transaction:\n{sql}\nparams={params!r}"
        )


_TABLE_OF_INSERT: Mapping[str, str] = {
    INSERT_RUN_SQL: "recall_run",
    INSERT_CANDIDATE_SQL: "recall_candidate",
    INSERT_CERTIFICATE_SQL: "recall_certificate",
    INSERT_RECEIPT_SQL: "silence_receipt",
    INSERT_SILENCE_SQL: "silence_ledger",
}

_EMPTY_TABLES: tuple[str, ...] = (
    "recall_run",
    "recall_candidate",
    "recall_certificate",
    "silence_receipt",
    "silence_ledger",
)


class _TxnSession:
    """The write half of one transaction. Nothing is visible until it commits."""

    def __init__(self, cluster: FakeCluster) -> None:
        self._cluster = cluster
        self.statements: list[Statement] = []
        self.rows: dict[str, list[tuple[Any, ...]]] = {name: [] for name in _EMPTY_TABLES}

    def _maybe_fail(self) -> None:
        cluster = self._cluster
        if cluster.write_failure is None:
            return
        cluster.write_attempts_seen += 1
        if cluster.write_attempts_seen <= cluster.write_failure_times:
            raise cluster.write_failure

    def execute(self, sql: str, params: Sequence[object] = ()) -> None:
        self.statements.append(Statement(sql=sql, params=tuple(params)))
        table = _TABLE_OF_INSERT.get(sql)
        if table is None:
            raise UnknownStatement(f"the run loop wrote an unrecognised statement:\n{sql}")
        self._maybe_fail()
        self.rows[table].append(tuple(params))

    def query(self, sql: str, params: Sequence[object] = ()) -> Sequence[Sequence[Any]]:
        self.statements.append(Statement(sql=sql, params=tuple(params)))
        if sql != READ_PROJECTED_SEVERITY_SQL:
            raise UnknownStatement(f"unrecognised in-transaction read:\n{sql}")
        projection = self._cluster.severity_projection
        return [
            (row[1], projection[UUID(str(row[1]))])
            for row in self.rows["recall_candidate"]
            if UUID(str(row[1])) in projection
        ]


@dataclass
class FakeCluster:
    """A recorded CockroachDB: read statements, one transactional write path, injections."""

    policy_row: tuple[Any, ...] | None = POLICY_ROW
    thymogate_row: tuple[Any, ...] | None = THYMOGATE_ROW
    ancestry_rows: tuple[tuple[Any, ...], ...] = ANCESTRY_ROWS
    bonded_rows: tuple[tuple[Any, ...], ...] = BONDED_ROWS
    containment: Mapping[UUID, tuple[tuple[UUID, str], ...]] = field(
        default_factory=lambda: dict(CONTAINMENT)
    )
    #: What ``fn_candidate_project`` projects. Defaults to the corpus's own severity_gate;
    #: override an entry to inject the disagreement `verify_projected_severity` must refuse.
    severity_projection: dict[UUID, int] = field(
        default_factory=lambda: {event.event_id: event.severity_gate for event in EVENTS}
    )
    #: Raised by the first ``write_failure_times`` statements the write path issues.
    write_failure: Exception | None = None
    write_failure_times: int = 10_000

    reads: list[Statement] = field(default_factory=list)
    committed: dict[str, list[tuple[Any, ...]]] = field(
        default_factory=lambda: {name: [] for name in _EMPTY_TABLES}
    )
    transactions: list[list[Statement]] = field(default_factory=list)
    rolled_back: list[list[Statement]] = field(default_factory=list)
    write_attempts_seen: int = 0

    # ── the two protocols the run loop consumes ──────────────────────────────────────────

    def session(self) -> _ReadSession:
        """An ``SqlSession`` over the recorded rows."""
        return _ReadSession(self)

    @contextmanager
    def transaction(self) -> Iterator[_TxnSession]:
        """One all-or-nothing write transaction."""
        pending = _TxnSession(self)
        try:
            yield pending
        except BaseException:
            self.rolled_back.append(pending.statements)
            raise
        for table, rows in pending.rows.items():
            self.committed[table].extend(rows)
        self.transactions.append(pending.statements)

    # ── assertions the tests read ────────────────────────────────────────────────────────

    @property
    def all_sql(self) -> tuple[str, ...]:
        """Every statement the run issued, read and write, committed or rolled back."""
        return tuple(statement.sql for statement in self.reads) + tuple(
            statement.sql
            for batch in (*self.transactions, *self.rolled_back)
            for statement in batch
        )

    def committed_counts(self) -> dict[str, int]:
        """How many rows landed in each measurement table."""
        return {table: len(rows) for table, rows in self.committed.items()}


# ── providers ────────────────────────────────────────────────────────────────────────────


def _unit(*values: float) -> tuple[float, ...]:
    return tuple(float(value) for value in values)


#: Four-dimensional cue vectors. ``E_DUP`` sits at cosine ~0.999 from ``E_PROB_HI``, above the
#: 0.90 redundancy threshold, so MMR collapses it into that representative; everything else is
#: orthogonal or at 0.5, comfortably below.
_ANN_HITS: tuple[tuple[UUID, int, tuple[float, ...]], ...] = (
    (E_PROB_HI, 1, _unit(1.0, 0.0, 0.0, 0.0)),
    (E_PROB_HI2, 2, _unit(0.0, 1.0, 0.0, 0.0)),
    (E_PROB_LO, 3, _unit(0.0, 0.0, 1.0, 0.0)),
    (E_DUP, 4, _unit(0.9990, 0.0447, 0.0, 0.0)),
    (E_SEV0, 5, _unit(0.5, 0.5, 0.5, 0.5)),
)


def arm_outcome(
    *,
    index_generation: str,
    plan_digest: bytes,
    sweep_ran: bool = True,
    generation_moves_to: str | None = None,
    index_traversed: bool = True,
    prefix_tree_counted: bool = True,
) -> ChannelCOutcome:
    """The ANN arms' observed result for the fixture corpus.

    The keyword arguments are the CUE HORIZON injections: a generation that moved mid-run, an
    arm that executed without traversing its named index, and a prefix tree that could not be
    counted. Each is a separate route to ``UNDETERMINED``, and each is a thing that really
    happens to a C-SPANN tree under load.
    """
    hits = [
        RetrievedHit(
            event_id=event_id,
            channel="C",
            arm_id="arm-l2-mechanism",
            rank=rank,
            facet="mechanism",
            scope_level=2,
            weight=1.0,
            embedding=embedding,
        )
        for event_id, rank, embedding in _ANN_HITS
    ]
    coverage = [
        ArmCoverage(
            arm_id="arm-l2-mechanism",
            executed=True,
            index_traversed=index_traversed,
            k=12,
            returned=len(_ANN_HITS),
        )
    ]
    if sweep_ran:
        hits.append(
            RetrievedHit(
                event_id=E_PROB_SWEEP,
                channel="C_sweep",
                arm_id="sweep-coarse-256",
                rank=1,
                facet="narrative",
                scope_level=1,
                weight=1.0,
                embedding=_unit(0.0, 0.0, 0.0, 1.0),
            )
        )
        coverage.append(
            ArmCoverage(
                arm_id="sweep-coarse-256",
                executed=True,
                index_traversed=index_traversed,
                k=12,
                returned=1,
            )
        )

    return ChannelCOutcome(
        hits=tuple(hits),
        arm_coverage=tuple(coverage),
        prefix_trees=(
            PrefixTree(
                table="mainline.event_cue_embedding",
                prefix=(("site_id", str(SITE_ID)), ("facet", "mechanism")),
                row_count=5_200 if prefix_tree_counted else None,
            ),
        ),
        index_generation_at_start=index_generation,
        index_generation_at_end=generation_moves_to or index_generation,
        index_plan_digest=plan_digest,
        arm_set_digest="sha256:" + "ab" * 32,
        sweep_ran=sweep_ran,
    )


def lexical_hits() -> tuple[RetrievedHit, ...]:
    """Channel D. Two identifier-bearing matches, no embeddings — BM25 has no vector."""
    return (
        RetrievedHit(
            event_id=E_PROB_HI2,
            channel="D",
            arm_id="bm25-identifier",
            rank=1,
            facet="control_failure",
            scope_level=1,
        ),
        RetrievedHit(
            event_id=E_PROB_LO,
            channel="D",
            arm_id="bm25-identifier",
            rank=2,
            facet="control_failure",
            scope_level=1,
        ),
    )


def verdicts() -> dict[str, tuple[str, str]]:
    """The listwise judge's answers for the fixture shortlist.

    The judge's verdict IS the raw score in this fixture (``_run_corpus.feature_weights``),
    so this table is the admission boundary written out in full.
    """
    return {
        str(E_PROB_HI): ("relevant", "decisive"),
        str(E_PROB_HI2): ("relevant", "decisive"),
        str(E_PROB_SWEEP): ("relevant", "supporting"),
        str(E_PROB_LO): ("not_relevant", "weak"),
        str(E_SEV0): ("not_relevant", "weak"),
    }


@dataclass
class FixtureArmRunner:
    """Replays :func:`arm_outcome`."""

    outcome: ChannelCOutcome

    def run(self) -> ChannelCOutcome:
        return self.outcome


@dataclass
class FailingArmRunner:
    """Injection 1 — the ANN arms never complete (throttle, timeout, embedder outage)."""

    detail: str = "Bedrock returned ThrottlingException on the cue embedding call"

    def run(self) -> ChannelCOutcome:
        raise ProviderUnavailable(self.detail)


@dataclass
class FixtureLexicalRunner:
    """Channel D, replayed."""

    hits: tuple[RetrievedHit, ...] = ()

    def run(self) -> Sequence[RetrievedHit]:
        return self.hits


@dataclass
class FixtureReranker:
    """The listwise judge, replayed with a fixed verdict per document."""

    table: Mapping[str, tuple[str, str]]
    calls: list[tuple[str, ...]] = field(default_factory=list)

    def rerank(self, doc_ids: Sequence[str]) -> RerankOutcome:
        self.calls.append(tuple(doc_ids))
        reranked: list[RerankedCandidate] = []
        unranked: list[str] = []
        for position, doc_id in enumerate(doc_ids, start=1):
            answer = self.table.get(doc_id)
            if answer is None:
                unranked.append(doc_id)
                continue
            relevance, strength = answer
            reranked.append(
                RerankedCandidate(
                    candidate_ref=f"C{position}",
                    doc_id=doc_id,
                    relevance=relevance,  # type: ignore[arg-type]
                    shared_mechanism="loss of a positive isolation under stored pressure",
                    shared_precondition=(
                        "a live line entered while the register showed it isolated"
                    ),
                    justification=(
                        "Both the precursor and the proposed work remove a positive isolation "
                        "while the line can still be pressurised; the shared precondition is "
                        "an isolation register recording a state nobody re-verified."
                    ),
                    evidence_strength=strength,  # type: ignore[arg-type]
                )
            )
        return RerankOutcome(
            reranked=tuple(reranked),
            unranked_refs=tuple(unranked),
            request_digest="sha256:" + "cd" * 32,
            prompt_version="recall.listwise/1",
            prefix_digest="sha256:" + "ce" * 32,
            model_id="au.anthropic.claude-opus-5",
            attempts=1,
            usage={"input_tokens": 4096, "cache_read_input_tokens": 3900},
        )


@dataclass
class RefusingReranker:
    """Injection 2 — ``stop_reason: "refusal"`` on a cyanide/H2S narrative."""

    detail: str = "the model returned stop_reason='refusal' on the listwise prompt"

    def rerank(self, doc_ids: Sequence[str]) -> RerankOutcome:
        raise ModelRefusal(self.detail, doc_count=len(doc_ids))


@dataclass
class GuardrailBlockedReranker:
    """Injection 3 — Bedrock Guardrails ``PROMPT_ATTACK`` blocked the whole listwise call."""

    detail: str = "Bedrock Guardrails blocked the listwise request (PROMPT_ATTACK, BLOCK)"

    def rerank(self, doc_ids: Sequence[str]) -> DegradedRerank:
        return DegradedRerank(
            silence_reason="model_refusal",
            detail=self.detail,
            candidate_refs=tuple(f"C{index}" for index, _ in enumerate(doc_ids, start=1)),
            doc_ids=tuple(doc_ids),
            prompt_version="recall.listwise/1",
            model_id="au.anthropic.claude-opus-5",
            request_digest="sha256:" + "cf" * 32,
        )


@dataclass
class FakeKernelTransport:
    """Records the one POST the agent makes and replays a scripted answer."""

    status: int = 200
    body: Mapping[str, Any] = field(
        default_factory=lambda: {
            "receipt_id": "9f1c0c2e-0000-4000-8000-00000000abcd",
            "open_blocking": 5,
            "gate_epoch": 3,
        }
    )
    posts: list[tuple[str, bytes, dict[str, str]]] = field(default_factory=list)

    def post(
        self,
        url: str,
        body: bytes,
        headers: Mapping[str, str],
        timeout: float,  # noqa: ARG002 - KernelTransport passes it; a recorder ignores it
    ) -> tuple[int, bytes]:
        self.posts.append((url, body, dict(headers)))
        return self.status, json.dumps(dict(self.body)).encode("utf-8")
