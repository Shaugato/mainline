# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
"""The refusal vocabulary of a recall run.

Two families, and the difference between them is the whole operational contract.

**Refusals that stop the run** (`PolicyRefused`, `ThymogateRefused`, `ConservationViolated`,
`LateRecall`, `KernelRefused`) mean the run must not produce a candidate set. A permit whose
recall refused has no `open_blocking` written by us, which is why the kernel's merge gate
fails closed on a missing or stale projection (MI22) rather than treating our silence as an
all-clear.

**Degradation** (`ProbabilisticChannelUnavailable`) is not a refusal at all. Bedrock throttled,
a model refusal, a guardrail block: the run completes on channels A and B, records
`arms_degraded = true`, writes the silence rows, and **still blocks the merge**. That is the
spine and it must never regress — *the gate refuses on graph truth alone.* Anything that
turned a degraded run into a stopped run would convert an unavailable reranker into a silently
unguarded permit, which is the failure this product exists to make impossible.

`40001` is the only retryable SQLSTATE. `23514` / `23503` / `23505` / `P0001` are gate
refusals: attempted exactly once, ever, and reported with the constraint name. Any other
SQLSTATE is a defect, because it means the database refused for a reason nobody modelled.
"""

from __future__ import annotations

from typing import Final

__all__ = [
    "GATE_REFUSAL_SQLSTATES",
    "RETRYABLE_SQLSTATES",
    "ConservationViolated",
    "KernelRefused",
    "LateRecall",
    "PolicyRefused",
    "ProbabilisticChannelUnavailable",
    "RunRefused",
    "ThymogateRefused",
    "UnmodelledSqlstate",
]

#: The only SQLSTATE this domain retries, and only on the recall-write transaction, which is
#: off the merge hot path. Never a blanket helper: a retry loop that could absorb a `23514`
#: would launder a real refusal into an apparent success.
RETRYABLE_SQLSTATES: Final[frozenset[str]] = frozenset({"40001"})

#: Refusals. Attempted exactly once, reported with the constraint or trigger name.
GATE_REFUSAL_SQLSTATES: Final[frozenset[str]] = frozenset(
    {"23514", "23503", "23505", "P0001"}
)


class RunRefused(Exception):
    """Base: this recall run will not produce a candidate set."""


class PolicyRefused(RunRefused):
    """The cited ``recall_policy`` may not arm a run.

    Unanchored (MI18), absent, or carrying a calibrator the fusion layer will not evaluate.
    """


class ThymogateRefused(PolicyRefused):
    """M5: the policy names a THYMOGATE certificate whose verdict is not clean.

    Negative selection is an evaluation, not a retrieval feature (recall lead D14). A policy
    that was measured against the panel of the fleet's known killers and *missed one* may not
    run, and a policy pointing at a certificate we cannot read is in the same position: the
    absence of a verdict is not a pass.
    """


class ConservationViolated(RunRefused):
    """L3 failed in code, before insert.

    ``candidates_conserved`` (MI17) is a database CHECK and it will refuse a lying run row.
    But the conservation law must never be the *first* thing that notices: by the time a
    `23514` comes back, the offending candidate is no longer in hand and the diagnosis is an
    integer. This exception carries the arithmetic and the event id.
    """


class LateRecall(RunRefused):
    """The subject has already merged; its gate epoch is pinned and cannot take an obligation.

    The declared path is to suspend the issued permit and fork a child whose gate is cleared
    afresh. Never a silent no-op: a late recall that quietly did nothing is exactly the
    anomaly the epoch pin exists to make impossible (MI07).
    """


class KernelRefused(RunRefused):
    """``POST /v1/permits/{id}/checks:materialise`` refused the candidate set."""


class UnmodelledSqlstate(RunRefused):
    """The database refused for a reason this domain never modelled.

    Deliberately fatal. A SQLSTATE outside the retryable and gate-refusal sets means either
    the schema moved or an assumption was wrong, and both are worse than the write failing.
    """


class ProbabilisticChannelUnavailable(Exception):
    """Channels C and D could not complete. **Not** a run refusal — see the module docstring.

    Carries the closed-vocabulary silence reason so the ledger row can be written without a
    second mapping table: ``model_refusal``, ``abstained``, ``unreachable``, ``truncated`` or
    ``cap_exceeded``.
    """

    def __init__(self, detail: str, *, silence_reason: str = "unreachable") -> None:
        """Record what failed and which closed-vocabulary reason the ledger will carry."""
        super().__init__(detail)
        self.detail = detail
        self.silence_reason = silence_reason
