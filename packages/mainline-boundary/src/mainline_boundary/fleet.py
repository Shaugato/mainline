# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""The fleet capability matrix.

E1 to E4 prove no model reaches the gate through IAM, the network, the image or the
protocol set. This module proves the fifth thing, which is about the *register*
rather than the infrastructure: that the fleet we declare is a fleet in which the
components reading hostile text hold nothing to act with.

Three assertions, from this domain's brief and ARCHITECTURE.md §8.2/§8.4:

* **tools is empty for every T1/T2 Cognition agent** (decision A1: the components
  that read hostile text have no capability to act on it — not a policy, a call
  shape);
* **``may_write_gate_field`` is true only for the kernel** (§8.2's tier table:
  T0 is the only tier that may write a gate-visible field);
* **no agent declares both ``svc_disposition`` and a model profile** (§8.2's first
  hard prohibition: no T1 or T2 agent may draft a disposition rationale, and
  ``svc_disposition`` is the only SQL role that can insert one).

Plane resolution is the interesting part. The fleet register is not required to
carry a ``plane`` field, so the plane is derived from the SQL role using §8.1's
plane table — an *authoritative* source, never the register's own say-so, which
is the P2 rule applied to a YAML file. An agent whose plane cannot be resolved is
a **violation**: a check that quietly exempts what it cannot classify is a check
that passes by absence.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from .errors import FleetParseError
from .findings import Enforcement, Report

AUTHORITY = "ARCHITECTURE.md §8.1 planes / §8.2 tiers / §8.4 fleet"

DEFAULT_FLEET_PATH = "spec/agents/fleet.yaml"

KERNEL = "kernel"
COGNITION = "cognition"
CUSTODY = "custody"
CONTROL = "control"
MEMORY = "memory"

PLANES: frozenset[str] = frozenset({KERNEL, MEMORY, COGNITION, CUSTODY, CONTROL})
TIERS: frozenset[str] = frozenset({"T0", "T1", "T2"})

#: §8.1's plane table, keyed by SQL role. This is the authoritative source the
#: register is checked *against*; the register does not get to nominate its own
#: plane and be believed.
PLANE_BY_SQL_ROLE: Mapping[str, str] = {
    "agent_gate": KERNEL,
    "svc_disposition": KERNEL,
    "agent_ingestor": COGNITION,
    "agent_cartographer": COGNITION,
    "agent_recaller": COGNITION,
    "agent_patroller": COGNITION,
    "agent_projector": COGNITION,
    "agent_fleet": COGNITION,
    "agent_assay": COGNITION,
    "agent_sequencer": CUSTODY,
    "agent_relay": CUSTODY,
    "mainline_auditor": CONTROL,
    "mainline_owner": CONTROL,
    "auditor_ro": CONTROL,
    "mainline_migrator": CONTROL,
}

#: §8.4's fleet, for agents that hold no SQL role at all (the disposition
#: assistant is invoked as a pure function and has none).
PLANE_BY_AGENT_NAME: Mapping[str, str] = {
    "archivist": COGNITION,
    "cartographer": COGNITION,
    "projector": COGNITION,
    "recall": COGNITION,
    "recall_agent": COGNITION,
    "disposition_assistant": COGNITION,
    "fixity_patrol": COGNITION,
    "cherry_pick": COGNITION,
    "cherry_pick_worker": COGNITION,
    "site_adopter": COGNITION,
    "steward": CONTROL,
    "auditor": CONTROL,
    "gc_persona": CONTROL,
    "kernel": KERNEL,
    "gate": KERNEL,
    "sequencer": CUSTODY,
    "relay": CUSTODY,
}

SQL_ROLE_DISPOSITION = "svc_disposition"


@dataclass(frozen=True, slots=True)
class AgentSpec:
    """One row of ``spec/agents/fleet.yaml``, normalised."""

    name: str
    tier: str
    sql_roles: tuple[str, ...]
    iam_role: str
    tools: tuple[str, ...]
    may_write_gate_field: bool
    call_profiles: tuple[str, ...]
    no_model: bool
    declared_plane: str | None
    raw: Mapping[str, Any]

    @property
    def has_model(self) -> bool:
        """True when the register says this agent issues model calls."""
        if self.no_model:
            return False
        return bool(self.call_profiles)

    @property
    def declares_model_intent(self) -> bool:
        """True when the register said *anything* about models for this agent."""
        return self.no_model or bool(self.call_profiles)


def resolve_plane(agent: AgentSpec) -> tuple[str | None, str]:
    """``(plane, how)``. ``plane`` is ``None`` when it cannot be resolved."""
    if agent.declared_plane is not None:
        plane = agent.declared_plane.strip().lower()
        if plane in PLANES:
            return plane, "declared in the register and a legal §8.1 plane"
        return None, f"declared plane {agent.declared_plane!r} is not one of {sorted(PLANES)}"
    planes = {PLANE_BY_SQL_ROLE[r] for r in agent.sql_roles if r in PLANE_BY_SQL_ROLE}
    if len(planes) == 1:
        return planes.pop(), "derived from the SQL role via §8.1's plane table"
    if len(planes) > 1:
        return None, f"SQL roles span multiple planes: {sorted(planes)}"
    by_name = PLANE_BY_AGENT_NAME.get(agent.name.strip().lower())
    if by_name is not None:
        return by_name, "derived from the agent name via §8.4's fleet table"
    return None, "no plane field, no known SQL role, and no known agent name"


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------


def _as_str_tuple(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        return (value,) if value else ()
    if isinstance(value, (list, tuple)):
        return tuple(str(v) for v in value if v is not None)
    if isinstance(value, Mapping):
        return tuple(str(k) for k in value)
    return (str(value),)


def parse_fleet(document: Any, *, source: str = "") -> tuple[AgentSpec, ...]:
    """Accept both shapes a register can reasonably take.

    ``agents:`` may be a mapping of name → spec or a list of specs carrying
    ``name``/``id``. Both are parsed, because pinning the shape here would make
    this check hostage to a formatting decision in another worker's file.
    """
    block = document.get("agents", document) if isinstance(document, Mapping) else document
    entries: list[tuple[str, Mapping[str, Any]]] = []
    if isinstance(block, Mapping):
        for key, value in block.items():
            if isinstance(value, Mapping):
                entries.append((str(key), value))
    elif isinstance(block, list):
        for item in block:
            if not isinstance(item, Mapping):
                continue
            name = str(item.get("name") or item.get("id") or item.get("agent") or "")
            if not name:
                raise FleetParseError(
                    f"{source or '<fleet>'}: an agent entry has no name/id field"
                )
            entries.append((name, item))
    else:
        raise FleetParseError(
            f"{source or '<fleet>'}: expected a mapping or a list of agents, got "
            f"{type(block).__name__}"
        )
    if not entries:
        raise FleetParseError(f"{source or '<fleet>'}: register declares no agents")

    out: list[AgentSpec] = []
    for name, spec in entries:
        call_profiles = _as_str_tuple(spec.get("call_profiles") or spec.get("profiles"))
        out.append(
            AgentSpec(
                name=name,
                tier=str(spec.get("tier", "")).strip().upper(),
                sql_roles=_as_str_tuple(spec.get("sql_role") or spec.get("sql_roles")),
                iam_role=str(spec.get("iam_role", "")),
                tools=_as_str_tuple(spec.get("tools")),
                may_write_gate_field=bool(spec.get("may_write_gate_field", False)),
                call_profiles=call_profiles,
                no_model=bool(spec.get("no_model", False)),
                declared_plane=(
                    str(spec["plane"]) if isinstance(spec.get("plane"), str) else None
                ),
                raw=spec,
            )
        )
    return tuple(out)


def load_fleet(path: Path) -> tuple[AgentSpec, ...]:
    try:
        document = yaml.safe_load(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise FleetParseError(f"{path}: {exc}") from exc
    except yaml.YAMLError as exc:
        raise FleetParseError(f"{path}: not valid YAML: {exc}") from exc
    return parse_fleet(document, source=str(path))


def fleet_path(repo_root: Path) -> Path:
    return repo_root / DEFAULT_FLEET_PATH


# ---------------------------------------------------------------------------
# The matrix
# ---------------------------------------------------------------------------


def check_agent(agent: AgentSpec) -> tuple[str, ...]:
    """Return the rule ids this one agent violates. Empty tuple means clean."""
    return tuple(finding.rule for finding in _agent_findings(agent))


@dataclass(frozen=True, slots=True)
class _AgentFinding:
    rule: str
    detail: str


def _agent_findings(agent: AgentSpec) -> tuple[_AgentFinding, ...]:
    out: list[_AgentFinding] = []
    plane, how = resolve_plane(agent)

    if agent.tier not in TIERS:
        out.append(
            _AgentFinding(
                "FLEET-TIER-UNKNOWN",
                f"tier {agent.tier!r} is not one of {sorted(TIERS)}",
            )
        )
    if plane is None:
        out.append(
            _AgentFinding(
                "FLEET-PLANE-UNRESOLVED",
                f"the plane of this agent cannot be resolved: {how}. An agent whose "
                "plane is unknown cannot be exempted from the Cognition rules",
            )
        )

    if plane == COGNITION and agent.tier in {"T1", "T2"} and agent.tools:
        out.append(
            _AgentFinding(
                "FLEET-COGNITION-HOLDS-TOOLS",
                f"a {agent.tier} Cognition agent declares tools {list(agent.tools)}; "
                "the components that read hostile text hold no capability to act on it "
                "(§8.4 injection posture layer 1, decision A1)",
            )
        )

    if agent.may_write_gate_field:
        if plane != KERNEL:
            out.append(
                _AgentFinding(
                    "FLEET-GATE-WRITE-OUTSIDE-KERNEL",
                    f"may_write_gate_field is true on a {plane or 'unresolved'}-plane "
                    "agent; §8.2 gives that capability to T0 Kernel alone",
                )
            )
        if agent.tier != "T0":
            out.append(
                _AgentFinding(
                    "FLEET-GATE-WRITE-NON-T0",
                    f"may_write_gate_field is true on tier {agent.tier!r}; only T0 may "
                    "write a gate-visible field",
                )
            )
        if agent.has_model:
            out.append(
                _AgentFinding(
                    "FLEET-GATE-WRITE-WITH-MODEL",
                    f"may_write_gate_field is true and the agent declares call profiles "
                    f"{list(agent.call_profiles)}; the plane that decides holds no model",
                )
            )

    if SQL_ROLE_DISPOSITION in agent.sql_roles and agent.has_model:
        out.append(
            _AgentFinding(
                "FLEET-DISPOSITION-WITH-MODEL",
                "the agent holds svc_disposition and declares a model profile; §8.2's "
                "first hard prohibition is that no T1 or T2 agent may draft a "
                "disposition rationale, and svc_disposition is the only role that can "
                "insert one",
            )
        )

    if not agent.declares_model_intent:
        out.append(
            _AgentFinding(
                "FLEET-MODEL-INTENT-UNDECLARED",
                "the register says neither call_profiles nor no_model: true for this "
                "agent; silence is not a declaration that it holds no model",
            )
        )

    return tuple(out)


def check_fleet(agents: Sequence[AgentSpec], *, source: str = "") -> Report:
    report = Report(enforcement=Enforcement.FLEET)
    if not agents:
        report.violate(
            rule="FLEET-EMPTY",
            subject=source or "<fleet>",
            detail="the fleet register declares no agents; there is nothing to assert",
            authority=AUTHORITY,
        )
        return report
    for agent in agents:
        report.examine()
        plane, how = resolve_plane(agent)
        report.note(f"{agent.name}: tier={agent.tier} plane={plane or 'UNRESOLVED'} ({how})")
        for finding in _agent_findings(agent):
            report.violate(
                rule=finding.rule,
                subject=agent.name,
                detail=finding.detail,
                authority=AUTHORITY,
            )
    return report


def check_fleet_file(path: Path) -> Report:
    return check_fleet(load_fleet(path), source=str(path))
