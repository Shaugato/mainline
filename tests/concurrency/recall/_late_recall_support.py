# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
"""Minimal doubles for the agent lane of the late-recall suite.

Deliberately self-contained rather than borrowed from
``tests/integration/recall_run``. What this lane asserts is the *write path's* handling of a
SQLSTATE — attempted once for a refusal, retried boundedly for ``40001``, fatal for anything
else — and that property is a property of one method over one record. Reaching across
directories for a nine-event corpus would make the failure of these tests say something about
retrieval, which is the one thing they are not about.
"""

from __future__ import annotations

import json
from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from mainline_recall_agent.run.conservation import CandidateRow, ConservationReport
from mainline_recall_agent.run.persist import READ_PROJECTED_SEVERITY_SQL, RunRecord
from mainline_recall_agent.run.probabilistic import SilenceRow

from trappoint_recall.run.contract import (
    Candidate,
    CandidateSet,
    Counts,
    ExposureCueRef,
)

__all__ = [
    "FakeSqlError",
    "RecordingWriter",
    "RefusingSession",
    "minimal_candidate_set",
    "minimal_record",
]

SITE_ID = UUID("11111111-1111-4111-8111-111111111111")
PERMIT_ID = UUID("22222222-2222-4222-8222-222222222222")
EVENT_ID = UUID("e0000000-0000-4000-8000-0000000000aa")
CLAUSE_ID = UUID("aaaaaaaa-0000-4000-8000-000000000001")
COMMIT_ID = "a1" * 32


class FakeSqlError(Exception):
    """A driver error carrying a SQLSTATE, shaped the way ``psycopg`` exposes one."""

    def __init__(self, sqlstate: str, message: str) -> None:
        super().__init__(f"{sqlstate}: {message}")
        self.sqlstate = sqlstate


@dataclass
class _Session:
    writer: RecordingWriter
    statements: list[str] = field(default_factory=list)
    candidates: list[tuple[Any, ...]] = field(default_factory=list)

    def execute(self, sql: str, params: Sequence[object] = ()) -> None:
        self.statements.append(sql)
        self.writer.statements_seen += 1
        if self.writer.failure is not None and self.writer.statements_seen <= (
            self.writer.fail_first_n
        ):
            raise self.writer.failure
        if "recall_candidate" in sql:
            self.candidates.append(tuple(params))

    def query(
        self,
        sql: str,
        params: Sequence[object] = (),  # noqa: ARG002 - the SqlSession shape is the contract
    ) -> Sequence[Sequence[Any]]:
        self.statements.append(sql)
        if sql != READ_PROJECTED_SEVERITY_SQL:
            raise AssertionError(f"unexpected in-transaction read: {sql}")
        # `fn_candidate_project` agreeing with what admission scored.
        return [(row[1], self.writer.projected_severity) for row in self.candidates]


@dataclass
class RecordingWriter:
    """A ``Transactional`` that can fail the first N statements of every attempt."""

    failure: Exception | None = None
    fail_first_n: int = 10_000
    projected_severity: int = 5

    statements_seen: int = 0
    committed: list[list[str]] = field(default_factory=list)
    rolled_back: list[list[str]] = field(default_factory=list)

    @contextmanager
    def transaction(self) -> Iterator[_Session]:
        session = _Session(writer=self)
        try:
            yield session
        except BaseException:
            self.rolled_back.append(session.statements)
            raise
        self.committed.append(session.statements)

    @property
    def attempts(self) -> int:
        """How many transactions were opened, successful or not."""
        return len(self.committed) + len(self.rolled_back)


class RefusingSession:
    """A read session that must never be consulted in this lane."""

    def query(
        self,
        sql: str,
        params: Sequence[object] = (),  # noqa: ARG002 - conforms in order to refuse
    ) -> Sequence[Sequence[Any]]:
        raise AssertionError(f"the write-path lane issued a read: {sql}")

    def execute(self, sql: str, params: Sequence[object] = ()) -> None:  # noqa: ARG002
        raise AssertionError(f"the write-path lane wrote outside its transaction: {sql}")


def minimal_record(*, silence: tuple[SilenceRow, ...] = ()) -> RunRecord:
    """One conserved, well-formed record: exactly what a healthy run hands the writer."""
    candidate = CandidateRow(
        event_id=EVENT_ID,
        rank=1,
        severity=5,
        p_relevant=1.0,
        tau_applied=0.0,
        outcome="blocking",
        origin="bonded",
        features={"channels": ["B"]},
    )
    return RunRecord(
        run_id=uuid4(),
        permit_id=PERMIT_ID,
        site_id=SITE_ID,
        policy_version="recall-policy-2026.08.01",
        corpus_commit=bytes.fromhex("c0" * 32),
        index_generation="gen-2026-08-01T00:00:00Z",
        index_plan_digest=bytes.fromhex("d0" * 32),
        arms_degraded=False,
        started_at=datetime.now(UTC),
        latency_ms=42,
        counts=ConservationReport(
            n_candidates=1, n_blocking=1, n_advisory=0, n_silenced=0, n_deduped=0
        ),
        candidates=(candidate,),
        certificate={
            "index_generation": "gen-2026-08-01T00:00:00Z",
            "index_fingerprint": bytes.fromhex("ee" * 32),
            "coverage_basis": "index_arms",
            "verdict": "partial",
        },
        receipt={
            "silence_receipt_id": uuid4(),
            "corpus_root": bytes.fromhex("c1" * 32),
            "candidate_root": bytes.fromhex("c2" * 32),
            "theta": 1.0,
            "s": 1,
            "n": 1,
            "boundary_proof": json.loads("{}"),
        },
        silence=silence,
    )


def minimal_candidate_set() -> CandidateSet:
    """A one-candidate payload, valid under the frozen wire contract."""
    candidate = Candidate(
        event_id=EVENT_ID,
        clause_uuid=CLAUSE_ID,
        commit_id=COMMIT_ID,
        origin="bonded",
        channels=("B",),
        outcome="blocking",
        rank=1,
        severity=5,
        p_relevant=1.0,
        tau_applied=0.0,
        evidence_summary="Bonded fatality: admitted unconditionally by channel B.",
        bonded_severity_5=True,
    )
    cues: Mapping[str, Any] = {
        "facet": "mechanism",
        "cue_sha256": "11" * 32,
        "template_sha256": "ff" * 32,
        "gen_model": "au.anthropic.claude-sonnet-5",
        "prompt_version": "recall.cue/1",
        "embed_model": "BAAI/bge-large-en-v1.5@fixture",
    }
    return CandidateSet(
        run_id=uuid4(),
        permit_id=PERMIT_ID,
        site_id=SITE_ID,
        policy_version="recall-policy-2026.08.01",
        taxonomy_ver=3,
        corpus_commit="c0" * 32,
        index_generation="gen-2026-08-01T00:00:00Z",
        index_plan_digest="d0" * 32,
        arms_degraded=False,
        silence_receipt_id=uuid4(),
        candidate_root="c2" * 32,
        certificate_verdict="partial",
        exposure_cues=(ExposureCueRef(**cues),),
        candidates=(candidate,),
        counts=Counts.of((candidate,)),
    )
