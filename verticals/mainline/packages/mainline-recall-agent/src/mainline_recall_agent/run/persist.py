# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
"""The one transaction: ``recall_run``, ``recall_candidate``, ``silence_*``, ``certificate``.

Five tables, one SERIALIZABLE transaction, and the reason it is one is not performance.

A run row that landed without its candidates would assert a partition nobody can inspect. A
silence receipt without its run would commit to a population that does not exist. A silence
ledger without its receipt is a list of withheld warnings with no proof that the list is
complete — which is the *only* property that makes the ledger a defence rather than a
confession. Splitting the write would make each of those states reachable by a crash.

Three things this module deliberately does **not** write
--------------------------------------------------------
**``blocking_check``.** The recall agent never writes it (ARCHITECTURE 8.3, finding S1). It
hands the kernel a candidate set and the kernel materialises obligations in its own
transaction. Every table touched here is in the unprivileged measurement zone, which is also
where the silence ledger's evidentiary value comes from: a contemporaneous business record
made in the ordinary course of business.

**``recall_run.n_bonded_sev5`` and ``.n_bonded_sev5_blocking``.** Both are trigger-maintained
by ``fn_bonded_sev5`` (migration 0113) as blocking checks land, and both are left at their
column defaults here. Supplying them would let an agent declare bonded fatalities it did not
materialise — which the CHECK would refuse, but only after the lie had been attempted. Not
writing them is the honest shape.

**``recall_candidate.severity``.** Projected from ``event.severity_gate`` by
``fn_candidate_project`` (0139), which RAISEs ``P0001`` when the event does not exist. The
column is supplied as ``0`` and discarded; passing the severity admission *used* would create
the impression that the inserter chose it. What this module does instead is
:func:`verify_projected_severity`: read the projection back inside the same transaction and
refuse the whole run if it disagrees with the severity admission scored against. A retriever
that thresholded a fatality as a severity-2 is a defect the database can see and we cannot,
and the correct response is to write nothing.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Final
from uuid import UUID

from mainline_recall_agent.run.conservation import CandidateRow, ConservationReport
from mainline_recall_agent.run.errors import ConservationViolated
from mainline_recall_agent.run.probabilistic import SilenceRow
from mainline_recall_agent.run.session import SqlSession

__all__ = [
    "NO_FINGERPRINT",
    "RunRecord",
    "insert_run",
    "verify_projected_severity",
]

INSERT_RUN_SQL: Final = """
INSERT INTO mainline_meas.recall_run
  (run_id, permit_id, site_id, corpus_commit, policy_version, index_plan_digest,
   index_generation, n_candidates, n_blocking, n_advisory, n_silenced, n_deduped,
   arms_degraded, started_at, latency_ms)
VALUES ($1, $2, $3, decode($4, 'hex'), $5, decode($6, 'hex'),
        $7, $8, $9, $10, $11, $12, $13, $14, $15)
""".strip()

INSERT_CANDIDATE_SQL: Final = """
INSERT INTO mainline_meas.recall_candidate
  (run_id, event_id, rank, severity, features, p_relevant, tau_applied, outcome)
VALUES ($1, $2, $3, 0, $4::JSONB, $5, $6, $7)
""".strip()

READ_PROJECTED_SEVERITY_SQL: Final = """
SELECT rc.event_id, rc.severity
  FROM mainline_meas.recall_candidate rc
 WHERE rc.run_id = $1
""".strip()

INSERT_CERTIFICATE_SQL: Final = """
INSERT INTO mainline_meas.recall_certificate
  (run_id, index_generation, index_fingerprint, coverage_basis, verdict)
VALUES ($1, $2, decode($3, 'hex'), $4, $5)
""".strip()

INSERT_RECEIPT_SQL: Final = """
INSERT INTO mainline_meas.silence_receipt
  (silence_receipt_id, run_id, permit_id, corpus_root, candidate_root, theta, s, n,
   boundary_proof, policy_version)
VALUES ($1, $2, $3, decode($4, 'hex'), decode($5, 'hex'), $6, $7, $8, $9::JSONB, $10)
""".strip()

INSERT_SILENCE_SQL: Final = """
INSERT INTO mainline_meas.silence_ledger
  (site_id, source, reason, subject_kind, subject_id, severity, score, threshold,
   arithmetic, policy_version)
VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9::JSONB, $10)
""".strip()

#: ``recall_certificate.index_fingerprint`` is ``BYTES NOT NULL``, and an ``UNDETERMINED``
#: certificate may have no fingerprint to record — the generation moved, or a tree could not
#: be counted. Thirty-two zero bytes is the sentinel, matching the custody ledger's genesis
#: convention for ``prev_link_hash``, and it is unambiguous because it can only co-occur with
#: ``coverage_basis IN ('fingerprint_mismatch', 'unavailable')``.
NO_FINGERPRINT: Final[bytes] = bytes(32)


@dataclass(frozen=True, slots=True)
class RunRecord:
    """Everything one transaction writes."""

    run_id: UUID
    permit_id: UUID
    site_id: UUID
    policy_version: str
    corpus_commit: bytes
    index_generation: str
    index_plan_digest: bytes
    arms_degraded: bool
    started_at: datetime
    latency_ms: int | None
    counts: ConservationReport
    candidates: tuple[CandidateRow, ...]
    certificate: Mapping[str, Any]
    receipt: Mapping[str, Any]
    silence: tuple[SilenceRow, ...]


def verify_projected_severity(
    session: SqlSession,
    run_id: UUID,
    scored: Sequence[CandidateRow],
) -> None:
    """Read back ``fn_candidate_project``'s severities and refuse a disagreement.

    P2, applied to ourselves. Admission chose ``tau`` by severity; the database independently
    projected that severity from ``event.severity_gate``. If the two disagree, the thresholds
    the run applied were the wrong ones and at least one candidate was measured against a bar
    it should never have been held to. Rolling back is the only fail-closed answer — a run
    that silenced a fatality at a severity-2 threshold must not leave a receipt saying so.

    Raises:
        ConservationViolated: on any mismatch, naming the event and both severities.
    """
    projected = {
        UUID(str(row[0])): int(row[1])
        for row in session.query(READ_PROJECTED_SEVERITY_SQL, (str(run_id),))
    }
    for candidate in scored:
        stored = projected.get(candidate.event_id)
        if stored is None:
            raise ConservationViolated(
                f"{candidate.event_id} was inserted as a candidate of run {run_id} and is "
                "not readable back inside the same transaction"
            )
        if stored != candidate.severity:
            raise ConservationViolated(
                f"{candidate.event_id}: admission scored it at severity "
                f"{candidate.severity} and applied tau={candidate.tau_applied}, but "
                f"fn_candidate_project projected severity {stored} from event.severity_gate. "
                "Severity-Graded Admission lowers the evidence bar by severity, so the run "
                "applied the wrong threshold. The whole run is rolled back rather than "
                "leaving a receipt that says otherwise."
            )


def insert_run(session: SqlSession, record: RunRecord) -> None:
    """Write the whole record. Call inside one SERIALIZABLE transaction.

    Insert order is load-bearing: ``recall_run`` first, because
    ``fn_recall_policy_anchored`` (0112) fires on it and refuses an unanchored policy with
    ``P0001`` before a single candidate row is written; then the candidates, whose projection
    trigger refuses an unknown event; then the certificate, the receipt and the ledger.
    """
    session.execute(
        INSERT_RUN_SQL,
        (
            str(record.run_id),
            str(record.permit_id),
            str(record.site_id),
            record.corpus_commit.hex(),
            record.policy_version,
            record.index_plan_digest.hex(),
            record.index_generation,
            record.counts.n_candidates,
            record.counts.n_blocking,
            record.counts.n_advisory,
            record.counts.n_silenced,
            record.counts.n_deduped,
            record.arms_degraded,
            record.started_at,
            record.latency_ms,
        ),
    )

    for candidate in record.candidates:
        session.execute(
            INSERT_CANDIDATE_SQL,
            (
                str(record.run_id),
                str(candidate.event_id),
                candidate.rank,
                json.dumps(dict(candidate.features), sort_keys=True, default=str),
                candidate.p_relevant,
                candidate.tau_applied,
                candidate.outcome,
            ),
        )

    verify_projected_severity(session, record.run_id, record.candidates)

    fingerprint = record.certificate.get("index_fingerprint")
    session.execute(
        INSERT_CERTIFICATE_SQL,
        (
            str(record.run_id),
            str(record.certificate["index_generation"]),
            (NO_FINGERPRINT if fingerprint is None else bytes(fingerprint)).hex(),
            str(record.certificate["coverage_basis"]),
            str(record.certificate["verdict"]),
        ),
    )

    session.execute(
        INSERT_RECEIPT_SQL,
        (
            str(record.receipt["silence_receipt_id"]),
            str(record.run_id),
            str(record.permit_id),
            bytes(record.receipt["corpus_root"]).hex(),
            bytes(record.receipt["candidate_root"]).hex(),
            float(record.receipt["theta"]),
            int(record.receipt["s"]),
            int(record.receipt["n"]),
            json.dumps(record.receipt["boundary_proof"], sort_keys=True),
            record.policy_version,
        ),
    )

    for row in record.silence:
        session.execute(
            INSERT_SILENCE_SQL,
            (
                str(record.site_id),
                row.source,
                row.reason,
                row.subject_kind,
                str(row.subject_id),
                row.severity,
                row.score,
                row.threshold,
                json.dumps(dict(row.arithmetic), sort_keys=True, default=str),
                record.policy_version,
            ),
        )
