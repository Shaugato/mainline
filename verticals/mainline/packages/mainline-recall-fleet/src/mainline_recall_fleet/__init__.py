# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
"""`mainline-recall-fleet` — the recall agent's binding to the agent fleet.

MAINLINE has two model runtimes: `mainline-agentkit`, which issues every single-shot,
zero-tool, schema-constrained call in the Cognition plane, and the recall agent's own
`BedrockClaudeJudge`, which issues the listwise rerank and the cue synthesis.  The second
exists for a good reason — a listwise judge over forty candidates is not the shape
`quarantined_call` has — and it means the recall agent is the one large model caller in
the repository that the fleet's controls do not reach.

This package is the seam that makes them one fleet, and it is deliberately small:

* :mod:`~mainline_recall_fleet.legs` — the recall agent's rows in the capability matrix
  (`spec/agents/fleet.yaml`'s *agent ⇄ tier ⇄ sql_role ⇄ tools ⇄ may_write_gate_field ⇄
  call_profiles*), validated at import.
* :mod:`~mainline_recall_fleet.body` — the recall judge's canonical request rendered as
  the one legal Anthropic native Bedrock body, which is where the fleet's `thinking`
  block and its `output_config.effort` are added.
* :mod:`~mainline_recall_fleet.transport` — a recall `JudgeTransport` over an agentkit
  transport: residency asserted at start-up, refusal classified before content, silence
  built as one row by one implementation.
* :mod:`~mainline_recall_fleet.conformance` — the model-call contract as named findings,
  runnable over a conforming body and a non-conforming one alike.

Three sentences that constrain what this package may claim:

* *We claim replayability and arithmetic reproducibility, never reproducibility of model
  output.*  The model proposes; the arithmetic decides; both are on the record.
* *A precursor the model declined to summarise must still block the merge.*  Every
  translation in :mod:`~mainline_recall_fleet.transport` exists to keep the recall
  orchestrator's degraded path — complete on channels A+B, set `arms_degraded`, write the
  silence rows — firing on exactly the exception classes it already catches.
* *Inference is pinned to `au.*` inference profiles in the configured Bedrock region.
  This package pins inference only and makes no claim about database residency; on the
  free demo tier the cluster is in Singapore, so end-to-end Australian data residency is
  FALSE for that deployment and is never claimed.*

**Unverified, and stated rather than implied.**  No live Bedrock call has been made from
this machine: AWS credentials are not valid here as of 2026-08-09 (PL-3).  What is proven
by this package's tests is *our* body shape, *our* refusal translation and *our*
register — not that the endpoint accepts the body.  That is `GT-AG-01`'s job, and AR-1 is
the pre-committed answer if it says no.
"""

from __future__ import annotations

from .body import (
    FLEET_BODY_KEYS,
    THINKING_ADAPTIVE,
    assert_fleet_body,
    assert_single_cache_breakpoint,
    build_fleet_body,
)
from .conformance import (
    BODY_CHECKS,
    LEG_CHECKS,
    Finding,
    audit_body,
    audit_leg,
    audit_recall_fleet,
    failures,
    render_report,
)
from .errors import (
    BudgetDrift,
    FleetContractViolation,
    PromptVersionDrift,
    UnregisteredLeg,
)
from .legs import (
    GATE_WRITING_ROLES,
    RECALL_LEGS,
    RECALL_SQL_ROLE,
    RecallLeg,
    describe_recall_fleet,
    fleet_yaml_fragment,
    get_leg,
    single_model_generation,
)
from .transport import FleetJudgeTransport, fleet_silence_row

__version__ = "0.1.0"

__all__ = [
    "BODY_CHECKS",
    "FLEET_BODY_KEYS",
    "GATE_WRITING_ROLES",
    "LEG_CHECKS",
    "RECALL_LEGS",
    "RECALL_SQL_ROLE",
    "THINKING_ADAPTIVE",
    "BudgetDrift",
    "Finding",
    "FleetContractViolation",
    "FleetJudgeTransport",
    "PromptVersionDrift",
    "RecallLeg",
    "UnregisteredLeg",
    "__version__",
    "assert_fleet_body",
    "assert_single_cache_breakpoint",
    "audit_body",
    "audit_leg",
    "audit_recall_fleet",
    "build_fleet_body",
    "describe_recall_fleet",
    "failures",
    "fleet_silence_row",
    "fleet_yaml_fragment",
    "get_leg",
    "render_report",
    "single_model_generation",
]
