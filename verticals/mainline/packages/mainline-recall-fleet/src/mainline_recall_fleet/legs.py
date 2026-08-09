# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
"""The recall agent's rows in the fleet register.

`docs/leads/agents-mcp.md` §3 publishes `spec/agents/fleet.yaml` with the columns
*agent ⇄ tier ⇄ sql_role ⇄ tools ⇄ may_write_gate_field ⇄ call_profiles*, and decision
A14 requires a **fleet capability-matrix test driven by that file**.  The recall agent is
the largest model caller in the repository and it makes its calls through its own judge
rather than through `mainline_agentkit.call.quarantined_call`, so its rows cannot be
derived from `mainline_agentkit.profiles.PROFILES`.  This module is where they are
declared instead: one :class:`RecallLeg` per model call the recall agent can make, with
the same fields a `CallProfile` exposes to the matrix, so the two registers can be read
as one table.

**The validations run at import, not at call time.** That is the difference between a
rule and a control (the same reasoning `mainline_agentkit.profiles._model` gives for
`CallProfile.__post_init__`).  A leg that named a gate-writing SQL role, or declared a
tool, or claimed `may_write_gate_field`, does not fail on the day it is called — it fails
on the day it is written, in CI, in the import.

**The covenant this file makes executable** is the sentence CockroachDB already carries
on the schema (`0009x_covenant_comment.sql`):

    The role that detects a precursor may never write one: agent_recaller holds no
    INSERT on any obligation relation of this binding.

`agent_recaller` is the role every leg here runs as, and :data:`GATE_WRITING_ROLES` is
refused by construction.  ARCHITECTURE §8.3 states the same property in the other
direction — *`mainline-recall` NEVER writes `blocking_check`* — and the orchestrator
honours it by POSTing its `CandidateSet` to the kernel's
`/v1/permits/{id}/checks:materialise` instead.

**What this module does not do.** It does not hash `agent_identity`.
`mainline_agentkit.runtime.IDENTITY_COMPONENT_ORDER` documents the seven components in
concatenation order and deliberately stops there, because `mainline-provenance` owns the
formula and *two implementations of one digest is one implementation too many*.
:meth:`RecallLeg.identity_components` returns the same seven keys for a recall leg and
leaves the digest where it belongs.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Final

from mainline_agentkit import (
    IDENTITY_COMPONENT_ORDER,
    SILENCE_REASONS,
    SILENCE_SOURCES,
    Effort,
    Tier,
)

from .errors import FleetContractViolation, UnregisteredLeg

if TYPE_CHECKING:
    from collections.abc import Mapping

__all__ = [
    "GATE_WRITING_ROLES",
    "RECALL_LEGS",
    "RECALL_SQL_ROLE",
    "RecallLeg",
    "describe_recall_fleet",
    "fleet_yaml_fragment",
    "get_leg",
    "single_model_generation",
]

#: The one SQL role every model-calling leg of the recall agent runs as
#: (`verticals/mainline/db/migrations/0006e_role_recaller.sql`).  It holds no INSERT on
#: any obligation relation, which is what makes "the role that detects a precursor may
#: never write one" a grant rather than a promise.
RECALL_SQL_ROLE: Final[str] = "agent_recaller"

#: Roles that can write something the merge gate reads, directly or by materialising an
#: obligation.  A model-bearing leg naming one of these is refused at import.  Sourced
#: from the role migrations `0006b`-`0006f`, not invented here.
GATE_WRITING_ROLES: Final[frozenset[str]] = frozenset(
    {"agent_gate", "agent_projector", "svc_disposition", "mainline_owner", "mainline_migrator"}
)

#: Decision A4: one model generation across the whole fleet, differentiated by
#: `output_config.effort`.  Resolved to an `au.*` inference-profile ARN at start-up and
#: never hard-coded — this is the *generation*, which is a first-party name, not an ARN.
RECALL_MODEL_KEY: Final[str] = "claude-opus-5"


@dataclass(frozen=True, slots=True)
class RecallLeg:
    """One model call the recall agent is permitted to make.

    Attributes:
        leg_id: the `call_profiles` identifier in `spec/agents/fleet.yaml`.
        agent: the fleet agent this leg belongs to (§8.3 names `mainline-recall`).
        tier: §8.2 tier.  `T0` is refused: the kernel plane holds no model.
        effort: `output_config.effort`.  Decision A4's only differentiator.
        model_key: the model generation.  One per fleet, asserted by
            :func:`single_model_generation`.
        sql_role: the CockroachDB role the caller holds while this leg runs.
        prompt_version: the version the recall package's own prompt module declares.
            Cross-checked against every request at bind time (decision A13).
        max_tokens: the committed budget.  Caps thinking **plus** text (decision A5).
        thinking_floor_tokens: the share of the budget reserved for thinking.
        online: whether this leg runs on the permit's recall path.  An offline leg
            (taxonomy induction) still gates what the online path can recall, which is
            why it is in the register at all.
        reads_untrusted_text: whether third-party narrative reaches this call.  Every
            leg here does; the field exists so the matrix can state it rather than
            assume it.
        writes: relations the caller may INSERT into while running this leg.  Never an
            obligation relation, never `blocking_check`.
        degrades_to: what the orchestrator completes on when this leg fails.  Empty
            string for a leg whose failure is not degradable.
        silence_source: `mainline_meas.silence_ledger.source` for this leg's silence.
        silence_reasons: the closed set of reasons this leg can produce.
        may_write_gate_field: always false.  Present so the matrix reads a field rather
            than infers an absence.
        tools: always empty.  The absence is the structural quarantine, and it is a
            field here so a future edit that adds one fails a test instead of a review.
    """

    leg_id: str
    agent: str
    tier: Tier
    effort: Effort
    sql_role: str
    prompt_version: str
    max_tokens: int
    thinking_floor_tokens: int
    online: bool
    reads_untrusted_text: bool
    writes: tuple[str, ...]
    degrades_to: str
    silence_source: str
    silence_reasons: frozenset[str]
    model_key: str = RECALL_MODEL_KEY
    may_write_gate_field: bool = False
    tools: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        """Validate the leg at import time.  Every failure here is a build failure."""
        if self.tier is Tier.T0:
            raise FleetContractViolation(
                "a recall leg declares tier T0; the kernel plane holds no model at all",
                leg_id=self.leg_id,
                decision="ARCHITECTURE §8.2 E1-E4",
            )
        if self.may_write_gate_field:
            raise FleetContractViolation(
                "a model-bearing leg claims may_write_gate_field; no tier that holds a "
                "model may write a field the gate reads",
                leg_id=self.leg_id,
                decision="ARCHITECTURE §8.2",
            )
        if self.tools:
            raise FleetContractViolation(
                "a recall leg declares a tool; the components that read hostile text hold "
                "no capability to act on it, and that is a call shape rather than a policy",
                leg_id=self.leg_id,
                tools=list(self.tools),
                decision="A1 / ARCHITECTURE §8.4 layer 1",
            )
        if self.sql_role in GATE_WRITING_ROLES:
            raise FleetContractViolation(
                "a recall leg runs as a gate-writing role; the role that detects a "
                "precursor may never write one",
                leg_id=self.leg_id,
                sql_role=self.sql_role,
                decision="mainline.0009x covenant / MI25",
            )
        if self.thinking_floor_tokens >= self.max_tokens:
            raise FleetContractViolation(
                "the thinking floor consumes the whole budget; max_tokens caps thinking "
                "PLUS text, so no tokens are left for the answer",
                leg_id=self.leg_id,
                thinking_floor_tokens=self.thinking_floor_tokens,
                max_tokens=self.max_tokens,
                decision="A5",
            )
        if self.silence_source not in SILENCE_SOURCES:
            raise FleetContractViolation(
                "silence source is outside the silence_ledger CHECK vocabulary",
                leg_id=self.leg_id,
                silence_source=self.silence_source,
                allowed=sorted(SILENCE_SOURCES),
                decision="ARCHITECTURE §5.7",
            )
        unknown = sorted(self.silence_reasons - SILENCE_REASONS)
        if unknown:
            raise FleetContractViolation(
                "silence reasons outside the silence_ledger CHECK vocabulary",
                leg_id=self.leg_id,
                unknown=unknown,
                allowed=sorted(SILENCE_REASONS),
                decision="ARCHITECTURE §5.7",
            )
        for relation in self.writes:
            if "blocking_check" in relation:
                raise FleetContractViolation(
                    "a recall leg claims a write to blocking_check; the recall agent POSTs "
                    "its CandidateSet to the kernel and never materialises an obligation",
                    leg_id=self.leg_id,
                    relation=relation,
                    decision="ARCHITECTURE §8.3",
                )

    def describe(self) -> dict[str, Any]:
        """Summarise this leg the way `spec/agents/fleet.yaml` and the ledger consume it."""
        return {
            "leg_id": self.leg_id,
            "agent": self.agent,
            "tier": str(self.tier),
            "effort": str(self.effort),
            "model_key": self.model_key,
            "sql_role": self.sql_role,
            "prompt_version": self.prompt_version,
            "max_tokens": self.max_tokens,
            "thinking_floor_tokens": self.thinking_floor_tokens,
            "online": self.online,
            "reads_untrusted_text": self.reads_untrusted_text,
            "writes": list(self.writes),
            "degrades_to": self.degrades_to,
            "silence_source": self.silence_source,
            "silence_reasons": sorted(self.silence_reasons),
            "may_write_gate_field": self.may_write_gate_field,
            "tools": list(self.tools),
        }

    def identity_components(
        self,
        *,
        iam_role_arn: str,
        model_id: str,
        inference_profile_arn: str,
        schema_version: str,
    ) -> dict[str, str]:
        """Return the seven `agent_identity` components, in concatenation order.

        The four this register knows — the agent name, the SQL role, the prompt version
        and (through the caller) the schema version — are filled from the leg; the three
        that belong to the deployment are arguments.  The digest itself is
        `mainline-provenance`'s to compute: returning components rather than a hash is
        the same refusal `mainline_agentkit.runtime` makes, for the same reason.

        Args:
            iam_role_arn: the execution role the leg runs under.
            model_id: the model **generation**, e.g. ``claude-opus-5``.
            inference_profile_arn: the resolved ``au.*`` routing ARN.
            schema_version: the content address of the output schema this call
                declared, from the caller's own schema builder.

        Returns:
            A mapping whose key order is exactly
            :data:`mainline_agentkit.IDENTITY_COMPONENT_ORDER`.
        """
        components = {
            "agent_name": self.agent,
            "sql_role": self.sql_role,
            "iam_role_arn": iam_role_arn,
            "prompt_version": self.prompt_version,
            "model_id": model_id,
            "inference_profile_arn": inference_profile_arn,
            "schema_version": schema_version,
        }
        return {name: components[name] for name in IDENTITY_COMPONENT_ORDER}


# ── the register ────────────────────────────────────────────────────────────────
#
# Five legs.  Three run on the permit's recall path; two induct the taxonomy that
# decides what Channel B can bond to, which is why they are declared here rather than
# treated as a back-office script nobody registered.
#
# The prompt versions are READ FROM the recall package's own prompt modules
# (`cue.prompts.PROMPT_VERSION`, `rerank.rubric.PROMPT_VERSION`,
# `taxonomy.prompts.INDUCTION_PROMPT_VERSION`) rather than imported from them: importing
# would make this register a mirror that can never disagree, and a register that cannot
# disagree cannot detect the drift decision A13 exists to detect.  `test_register.py`
# asserts the two agree today; the transport refuses a request whose version differs.

_CUE_PROMPT_VERSION: Final[str] = "mainline-cue-1"
_RERANK_PROMPT_VERSION: Final[str] = "recall-judge-1"
_TAXONOMY_PROMPT_VERSION: Final[str] = "mainline-taxonomy-induction-1"

#: The judge's shipped budget (`providers.registry.get_judge_provider(max_tokens=4096)`).
#: Pinned per leg so a budget change is a register edit and therefore a commit.
_JUDGE_BUDGET: Final[int] = 4096

RECALL_LEGS: Final[Mapping[str, RecallLeg]] = {
    leg.leg_id: leg
    for leg in (
        RecallLeg(
            leg_id="recall.cue.event",
            agent="mainline-recall",
            tier=Tier.T1,
            effort=Effort.LOW,
            sql_role=RECALL_SQL_ROLE,
            prompt_version=_CUE_PROMPT_VERSION,
            max_tokens=_JUDGE_BUDGET,
            thinking_floor_tokens=512,
            online=False,
            reads_untrusted_text=True,
            writes=("mainline.event_cue",),
            # A facet the model declines to summarise produces no cue row and a logged
            # reason — never a placeholder string, and never a silently absent facet.
            degrades_to="narrative facet only",
            silence_source="recall",
            silence_reasons=frozenset({"model_refusal", "abstained", "truncated", "unreachable"}),
        ),
        RecallLeg(
            leg_id="recall.cue.exposure",
            agent="mainline-recall",
            tier=Tier.T1,
            effort=Effort.LOW,
            sql_role=RECALL_SQL_ROLE,
            prompt_version=_CUE_PROMPT_VERSION,
            max_tokens=_JUDGE_BUDGET,
            thinking_floor_tokens=512,
            online=True,
            reads_untrusted_text=True,
            # Nothing.  The exposure cue is derived per run and travels in the
            # `CandidateSet` wire payload; there is no `exposure_cue` relation in the
            # migration tree and this register does not invent one.
            writes=(),
            degrades_to="channels A+B",
            silence_source="recall",
            silence_reasons=frozenset({"model_refusal", "abstained", "truncated", "unreachable"}),
        ),
        RecallLeg(
            leg_id="recall.rerank.listwise",
            agent="mainline-recall",
            tier=Tier.T1,
            # Decision A4: xhigh is the listwise rerank.  It is the one leg whose output
            # becomes `blocking_check.evidence_summary`, which is why it is worth the
            # tokens — and why the rubric requires the model to name the shared mechanism
            # AND the shared precondition or return not_relevant.
            effort=Effort.XHIGH,
            sql_role=RECALL_SQL_ROLE,
            prompt_version=_RERANK_PROMPT_VERSION,
            max_tokens=_JUDGE_BUDGET,
            thinking_floor_tokens=1536,
            online=True,
            reads_untrusted_text=True,
            writes=("mainline_meas.recall_candidate", "mainline_meas.silence_ledger"),
            degrades_to="channels A+B, arms_degraded=true",
            silence_source="recall",
            silence_reasons=frozenset(
                {"model_refusal", "abstained", "truncated", "unreachable", "below_tau"}
            ),
        ),
        RecallLeg(
            leg_id="recall.taxonomy.propose",
            agent="mainline-taxonomy",
            tier=Tier.T2,
            effort=Effort.LOW,
            sql_role=RECALL_SQL_ROLE,
            prompt_version=_TAXONOMY_PROMPT_VERSION,
            max_tokens=_JUDGE_BUDGET,
            thinking_floor_tokens=512,
            online=False,
            reads_untrusted_text=True,
            writes=(),
            degrades_to="induction run aborts; the frozen taxonomy version stands",
            silence_source="recall",
            silence_reasons=frozenset({"model_refusal", "abstained", "truncated", "unreachable"}),
        ),
        RecallLeg(
            leg_id="recall.taxonomy.refine",
            agent="mainline-taxonomy",
            tier=Tier.T2,
            # Merge/refine adjudicates between proposed labels, which is decision A4's
            # `high`, not its `low`.
            effort=Effort.HIGH,
            sql_role=RECALL_SQL_ROLE,
            prompt_version=_TAXONOMY_PROMPT_VERSION,
            max_tokens=_JUDGE_BUDGET,
            thinking_floor_tokens=1024,
            online=False,
            reads_untrusted_text=True,
            writes=(),
            degrades_to="induction run aborts; the frozen taxonomy version stands",
            silence_source="recall",
            silence_reasons=frozenset({"model_refusal", "abstained", "truncated", "unreachable"}),
        ),
    )
}


def get_leg(leg_id: str) -> RecallLeg:
    """Look up a registered leg.

    Raises:
        UnregisteredLeg: when no leg of that id is declared.  A capability nobody
            declared is refused rather than served.
    """
    try:
        return RECALL_LEGS[leg_id]
    except KeyError as exc:
        raise UnregisteredLeg(
            "no recall fleet leg of that id is registered",
            leg_id=leg_id,
            registered=sorted(RECALL_LEGS),
        ) from exc


def single_model_generation() -> str:
    """Return the one model generation the recall register uses.

    Raises:
        FleetContractViolation: when the register spans more than one.  Decision A4
            ships one generation fleet-wide differentiated by effort, and a run record
            pins exactly one inference-profile ARN — two generations cannot both be true
            of one record.
    """
    generations = sorted({leg.model_key for leg in RECALL_LEGS.values()})
    if len(generations) != 1:
        raise FleetContractViolation(
            "the recall fleet register spans model generations; one run record pins one "
            "inference-profile ARN, so two generations cannot both be pinned by it",
            generations=generations,
            decision="A4",
        )
    return generations[0]


def describe_recall_fleet() -> dict[str, Any]:
    """The recall agent's contribution to the fleet capability matrix.

    Shaped as `spec/agents/fleet.yaml` consumes it: agents on the outside, call profiles
    on the inside, with `tools` and `may_write_gate_field` present on both levels so a
    reader never has to infer a capability from an absence.
    """
    agents: dict[str, dict[str, Any]] = {}
    for leg in RECALL_LEGS.values():
        entry = agents.setdefault(
            leg.agent,
            {
                "name": leg.agent,
                "plane": "cognition",
                "sql_role": leg.sql_role,
                "tools": [],
                "may_write_gate_field": False,
                "reads_untrusted_text": False,
                "call_profiles": [],
            },
        )
        if entry["sql_role"] != leg.sql_role:
            raise FleetContractViolation(
                "one fleet agent declares two SQL roles; the capability matrix has one "
                "row per agent and cannot describe two",
                agent=leg.agent,
                roles=sorted({str(entry["sql_role"]), leg.sql_role}),
                decision="A14",
            )
        entry["reads_untrusted_text"] = bool(entry["reads_untrusted_text"]) or (
            leg.reads_untrusted_text
        )
        profiles: list[dict[str, Any]] = entry["call_profiles"]
        profiles.append(leg.describe())
    for entry in agents.values():
        entry["call_profiles"].sort(key=lambda profile: str(profile["leg_id"]))
    return {
        "model_generation": single_model_generation(),
        "agents": [agents[name] for name in sorted(agents)],
    }


def fleet_yaml_fragment() -> str:
    """Render the register as the YAML block `spec/agents/fleet.yaml` merges verbatim.

    Emitted rather than written: `spec/agents/fleet.yaml` belongs to the fleet-register
    worker, and two files claiming to be the register is the failure mode this whole
    domain exists to refuse.  The fragment is deterministic — sorted agents, sorted
    profiles, sorted scalar keys — so a diff is a real change rather than dictionary
    ordering.

    The emitter handles exactly the value types :meth:`RecallLeg.describe` produces
    (str, bool, int, list-of-str).  It is not a general YAML writer and refuses anything
    else rather than emitting something that only looks like YAML.
    """
    matrix = describe_recall_fleet()
    lines: list[str] = [
        "# Generated by mainline_recall_fleet.legs.fleet_yaml_fragment().",
        "# The recall agent's rows in the fleet capability matrix (decision A14).",
        f"model_generation: {matrix['model_generation']}",
        "agents:",
    ]
    for agent in matrix["agents"]:
        lines.append(f"  - name: {agent['name']}")
        for key in ("plane", "sql_role"):
            lines.append(f"    {key}: {agent[key]}")
        for key in ("may_write_gate_field", "reads_untrusted_text"):
            lines.append(f"    {key}: {_yaml_scalar(agent[key])}")
        lines.append("    tools: []")
        lines.append("    call_profiles:")
        for profile in agent["call_profiles"]:
            first = True
            for key in sorted(profile):
                bullet = "      - " if first else "        "
                first = False
                value = profile[key]
                if isinstance(value, list):
                    lines.append(f"{bullet}{key}: [{', '.join(_yaml_scalar(v) for v in value)}]")
                else:
                    lines.append(f"{bullet}{key}: {_yaml_scalar(value)}")
    return "\n".join(lines) + "\n"


def _yaml_scalar(value: Any) -> str:
    """Render one scalar.  Booleans before integers: ``bool`` is an ``int`` subclass."""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, str):
        bare = value.replace(".", "").replace("_", "")
        return value if value and bare.isalnum() else f'"{value}"'
    raise FleetContractViolation(
        "the fleet fragment emitter refuses a value type it cannot render honestly",
        value_type=type(value).__name__,
    )
