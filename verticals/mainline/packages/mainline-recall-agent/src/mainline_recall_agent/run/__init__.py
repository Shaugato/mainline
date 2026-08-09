# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
"""The recall run loop — channels, admission, the one transaction, and the kernel POST.

``mainline-recall`` turns *"which incidents wrote the controls this permit is about to
waive"* into an integer on ``permit.open_blocking``. Everything in this subpackage exists to
make that integer defensible in both directions: a miss is a fatality exhibit, a false
positive is a rubber stamp.

Read :mod:`mainline_recall_agent.run.orchestrator` first; it is the spine and every other
module here is a stage it calls.

Two boundaries this package will not cross
------------------------------------------
**It never writes ``blocking_check``.** The agent assembles a frozen
:class:`~trappoint_recall.run.contract.CandidateSet` and POSTs it to the kernel's
``/v1/permits/{id}/checks:materialise`` (ARCHITECTURE 8.3, adversarial finding S1). The
boundary is a SQL grant, not a convention — :mod:`mainline_recall_agent.run.persist` writes
only into the unprivileged ``mainline_meas`` measurement zone.

**A model failure degrades the run; it never stops it.** Bedrock throttled, a model refusal, a
guardrail block: the run completes on channels A and B, records ``arms_degraded = true``,
writes the silence rows, and **still blocks the merge**. *The gate refuses on graph truth
alone.* That is the spine and it must never regress —
``tests/integration/recall_run/test_degraded_modes.py`` injects each of the three failures
independently and asserts ``open_blocking > 0`` in every one.

Import cost
-----------
Nothing here imports ``psycopg``, ``boto3`` or ``anthropic`` at module scope. The SQL boundary
is a protocol (:class:`~mainline_recall_agent.run.session.SqlSession`) and the driver is a leaf
dependency behind :func:`~mainline_recall_agent.run.session.psycopg_session`, so
``import mainline_recall_agent.run`` works on a machine with no cluster and no AWS account —
which is the CI and demo default, not an edge case.
"""

from __future__ import annotations

from mainline_recall_agent.run.channels import (
    AncestryHit,
    BondedHit,
    ChannelAResult,
    CitedClause,
    channel_a,
    channel_b,
    cited_clauses,
)
from mainline_recall_agent.run.conservation import (
    CandidateRow,
    ConservationReport,
    enforce_conservation,
)
from mainline_recall_agent.run.errors import (
    GATE_REFUSAL_SQLSTATES,
    RETRYABLE_SQLSTATES,
    ConservationViolated,
    KernelRefused,
    LateRecall,
    PolicyRefused,
    ProbabilisticChannelUnavailable,
    RunRefused,
    ThymogateRefused,
    UnmodelledSqlstate,
)
from mainline_recall_agent.run.kernel import (
    MATERIALISE_PATH,
    KernelTransport,
    MaterialiseClient,
    MaterialiseResult,
    UrllibTransport,
)
from mainline_recall_agent.run.orchestrator import (
    RecallOrchestrator,
    RunOutcome,
    RunRequest,
)
from mainline_recall_agent.run.persist import RunRecord, insert_run, verify_projected_severity
from mainline_recall_agent.run.policy import (
    RecallPolicy,
    ThymogateCertificate,
    load_policy,
    load_thymogate,
)
from mainline_recall_agent.run.probabilistic import (
    ArmRunner,
    ChannelCOutcome,
    DedupedCandidate,
    LexicalRunner,
    ProbabilisticOutcome,
    Reranker,
    RetrievedHit,
    ScoredCandidate,
    SilenceRow,
    run_probabilistic,
)
from mainline_recall_agent.run.session import (
    SqlSession,
    Transactional,
    classify_sqlstate,
    psycopg_session,
    sqlstate_of,
)

__all__ = [
    "GATE_REFUSAL_SQLSTATES",
    "MATERIALISE_PATH",
    "RETRYABLE_SQLSTATES",
    "AncestryHit",
    "ArmRunner",
    "BondedHit",
    "CandidateRow",
    "ChannelAResult",
    "ChannelCOutcome",
    "CitedClause",
    "ConservationReport",
    "ConservationViolated",
    "DedupedCandidate",
    "KernelRefused",
    "KernelTransport",
    "LateRecall",
    "LexicalRunner",
    "MaterialiseClient",
    "MaterialiseResult",
    "PolicyRefused",
    "ProbabilisticChannelUnavailable",
    "ProbabilisticOutcome",
    "RecallOrchestrator",
    "RecallPolicy",
    "Reranker",
    "RetrievedHit",
    "RunOutcome",
    "RunRecord",
    "RunRefused",
    "RunRequest",
    "ScoredCandidate",
    "SilenceRow",
    "SqlSession",
    "ThymogateCertificate",
    "ThymogateRefused",
    "Transactional",
    "UnmodelledSqlstate",
    "UrllibTransport",
    "channel_a",
    "channel_b",
    "cited_clauses",
    "classify_sqlstate",
    "enforce_conservation",
    "insert_run",
    "load_policy",
    "load_thymogate",
    "psycopg_session",
    "run_probabilistic",
    "sqlstate_of",
    "verify_projected_severity",
]
