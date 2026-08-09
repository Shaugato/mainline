# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""Layer 5: capability starvation, checked against the register rather than the caller.

The structural version of this control is that the process simply does not hold the
credential - IAM permissions boundary, no VPC endpoint, no grant. Those are the
determinism boundary's four enforcements (8.2 E1-E4) and they are another worker's.
**This is the in-process guard that runs before the process reads a single byte of
hostile text**, and it exists for the case the infrastructure controls cannot cover: a
correct deployment in which someone has widened a grant, or a task that assumed a role it
should not have.

Two properties make it a control rather than a comment.

*The register is the authority, and the caller's opinion of itself is not.* The guard is
given what the process actually holds - the roles its connection reports, the tools its
runtime was given - and compares them against ``spec/agents/fleet.yaml``. A process
declaring itself trustworthy is the thing being checked, not the check.

*A gate-writing role is refused from the authoritative list, not from the register's own
boolean.* :data:`GATE_WRITING_ROLES` comes from the SQL role matrix in 11.2. If a
register entry ever said ``may_write_gate_field: false`` while granting ``agent_gate``,
the register would be wrong and the guard would still refuse - which is the P2 rule
("projections are enforced, never trusted") applied to a YAML file.

*Not listed means no grant.* An agent the register does not contain is refused, never
treated as unconstrained.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

from .classes import Layer, Outcome
from .errors import CapabilityRefused, QuarantineError, UnknownAgent

__all__ = [
    "DEFAULT_FLEET_PATH",
    "GATE_WRITING_ROLES",
    "AgentGrant",
    "CapabilityVerdict",
    "FleetRegister",
    "RegisterUnavailable",
    "require_capability",
]

DEFAULT_FLEET_PATH: Final[str] = "spec/agents/fleet.yaml"

#: From the SQL role matrix, ARCHITECTURE.md 11.2: the two roles that can write a field
#: the merge gate reads. Held here as data so the guard does not have to believe a
#: register that says otherwise.
GATE_WRITING_ROLES: Final[frozenset[str]] = frozenset({"agent_gate", "svc_disposition"})


class RegisterUnavailable(QuarantineError):
    """The fleet register could not be read or parsed.

    A refusal rather than an empty register: an empty register grants nothing, which
    would make every call fail in a way indistinguishable from a real capability
    violation, and a register that failed to load must not look like a register that
    said no.
    """


@dataclass(frozen=True, slots=True)
class AgentGrant:
    """One agent's entry, reduced to what layer 5 enforces."""

    agent: str
    tier: str
    sql_roles: frozenset[str]
    tools: frozenset[str]
    may_write_gate_field: bool


@dataclass(frozen=True, slots=True)
class CapabilityVerdict:
    """What layer 5 decided about one process."""

    outcome: Outcome
    layer: Layer
    agent: str
    refusals: tuple[str, ...]

    @property
    def starved(self) -> bool:
        """Whether the process holds only what the register grants."""
        return self.outcome is Outcome.CLEAN


@dataclass(frozen=True, slots=True)
class FleetRegister:
    """``spec/agents/fleet.yaml``, reduced to grants."""

    grants: Mapping[str, AgentGrant]
    source: str

    @classmethod
    def from_mapping(cls, document: Any, *, source: str = "<memory>") -> FleetRegister:
        """Build a register from an already-parsed document.

        This is the primary constructor, and it takes a mapping rather than a path
        because this package holds no dependency: parsing YAML is the caller's business
        and stays out of the import graph of the component that reads hostile text.

        Both register shapes are accepted - ``agents:`` as a mapping of name to spec, and
        as a list of specs carrying ``name``/``id`` - because pinning the shape here
        would make this guard hostage to a formatting decision in another worker's file.
        """
        block = document.get("agents", document) if isinstance(document, Mapping) else document
        entries: list[tuple[str, Mapping[str, Any]]] = []
        if isinstance(block, Mapping):
            entries = [
                (str(key), value) for key, value in block.items() if isinstance(value, Mapping)
            ]
        elif isinstance(block, Sequence) and not isinstance(block, (str, bytes)):
            for item in block:
                if not isinstance(item, Mapping):
                    continue
                name = str(item.get("name") or item.get("id") or item.get("agent") or "")
                if not name:
                    raise RegisterUnavailable(f"{source}: an agent entry has no name/id field")
                entries.append((name, item))
        else:
            raise RegisterUnavailable(
                f"{source}: expected a mapping or a list of agents, got {type(block).__name__}"
            )
        if not entries:
            raise RegisterUnavailable(f"{source}: register declares no agents")

        grants = {
            name: AgentGrant(
                agent=name,
                tier=str(spec.get("tier", "")).strip().upper(),
                sql_roles=frozenset(_as_strings(spec.get("sql_role") or spec.get("sql_roles"))),
                tools=frozenset(_as_strings(spec.get("tools"))),
                may_write_gate_field=bool(spec.get("may_write_gate_field", False)),
            )
            for name, spec in entries
        }
        return cls(grants=grants, source=source)

    @classmethod
    def from_yaml_path(cls, path: Path) -> FleetRegister:
        """Load the register from YAML.

        Raises:
            RegisterUnavailable: the file is missing, unreadable, invalid YAML, or
                ``PyYAML`` is not installed. Loading YAML needs a third-party parser, so
                the import is inside this function and the package's import graph stays
                standard-library-only.
        """
        try:
            import yaml
        except ImportError as exc:  # pragma: no cover - PyYAML is present in the workspace
            raise RegisterUnavailable(
                "PyYAML is not installed; pass an already-parsed document to "
                "FleetRegister.from_mapping instead"
            ) from exc
        try:
            raw = path.read_text(encoding="utf-8")
        except OSError as exc:
            raise RegisterUnavailable(f"cannot read {path}: {exc}") from exc
        try:
            document = yaml.safe_load(raw)
        except yaml.YAMLError as exc:
            raise RegisterUnavailable(f"{path} is not valid YAML: {exc}") from exc
        return cls.from_mapping(document, source=str(path))

    def grant(self, agent: str) -> AgentGrant:
        """Return the grant for one agent.

        Raises:
            UnknownAgent: the register does not list it. Fails closed.
        """
        found = self.grants.get(agent)
        if found is None:
            raise UnknownAgent(agent, tuple(self.grants))
        return found


def require_capability(
    agent: str,
    register: FleetRegister,
    *,
    sql_roles: Sequence[str] = (),
    tools: Sequence[str] = (),
    raising: bool = True,
) -> CapabilityVerdict:
    """Refuse a process that holds more than the register grants this agent.

    Args:
        agent: the agent name as it appears in the register.
        register: the parsed fleet register.
        sql_roles: the roles the process actually holds. Empty means "holds none", which
            is the normal case for the disposition assistant.
        tools: the tools the runtime actually gave it.
        raising: ``True`` raises on the first refusal, which is what a start-up guard
            wants. ``False`` returns the full list, which is what a report wants.

    Returns:
        A verdict listing every refusal.

    Raises:
        UnknownAgent: the agent is not in the register.
        CapabilityRefused: ``raising`` and the process holds an ungranted role.
    """
    grant = register.grant(agent)
    refusals: list[str] = []

    for role in sql_roles:
        if role not in grant.sql_roles:
            if raising:
                raise CapabilityRefused(agent, role, sorted(grant.sql_roles))
            refusals.append(f"sql_role {role!r} is not granted to {agent!r}")
        if role in GATE_WRITING_ROLES and not grant.may_write_gate_field:
            message = (
                f"sql_role {role!r} writes a gate-visible field (ARCHITECTURE.md 11.2) "
                f"and {agent!r} is not a gate-writing agent"
            )
            if raising:
                raise CapabilityRefused(agent, role, sorted(grant.sql_roles - GATE_WRITING_ROLES))
            refusals.append(message)

    for tool in tools:
        if tool not in grant.tools:
            message = (
                f"tool {tool!r} is not declared for {agent!r}; the register lists "
                f"{sorted(grant.tools)}"
            )
            if raising:
                raise CapabilityRefused(agent, tool, sorted(grant.tools))
            refusals.append(message)

    return CapabilityVerdict(
        outcome=Outcome.CAPABILITY_REFUSED if refusals else Outcome.CLEAN,
        layer=Layer.L5_CAPABILITY_STARVATION,
        agent=agent,
        refusals=tuple(refusals),
    )


def _as_strings(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        return (value,) if value else ()
    if isinstance(value, Mapping):
        return tuple(str(key) for key in value)
    if isinstance(value, Sequence):
        return tuple(str(item) for item in value if item is not None)
    return (str(value),)
