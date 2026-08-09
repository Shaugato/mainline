# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""The typed shape of a vertical binding, and the kernel's role and schema models.

Two things live here that are *not* in ``vertical.toml``, and both are deliberate.

**The schema zone model.** A TRAPPOINT vertical occupies five schemas derived from the
one name it declares: ``<schema>`` (business records), ``<schema>_meas`` (measurement),
``<schema>_audit`` (the MCP-facing views), ``<schema>_qa`` (per-named-person views, no
MCP account ever) and ``<schema>_ops`` (infrastructure). Deriving them means a vertical
cannot accidentally put a QA view in the audit schema, which is finding `S14`'s failure
mode expressed as arithmetic rather than as a review comment.

**The role model.** ARCHITECTURE.md §11.2 names nine roles. ``vertical.schema.json``
1.0 exposes six of them under ``[roles]`` and closes the table with
``additionalProperties: false``, so ``recaller``, ``auditor`` and ``qa`` cannot be named
by a binding at all. Rather than invent a config key the specification does not have,
the renderer *derives* every slot and lets ``[roles]`` override the six the spec can
express. The derivation is the rule §11.2 already follows:

* **agent and service roles are cluster-global constants** — ``agent_gate``,
  ``agent_projector``, ``agent_recaller``, ``svc_disposition``, ``auditor_ro``,
  ``quality_assurance``. They are not schema-scoped in §11.2 and they are not scoped
  here.
* **the three roles that own or administer a schema are schema-scoped** —
  ``<schema>_migrator``, ``<schema>_owner``, ``<schema>_auditor``.

For ``schema = "mainline"`` that reproduces §11.2's nine names exactly, with no table of
hard-coded vertical knowledge anywhere in the substrate. See this package's README for
the note asking the spec owner to add the three missing keys in the next MINOR.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

__all__ = [
    "ROLE_SLOTS",
    "SCHEMA_ZONES",
    "AuthoritySource",
    "Binding",
    "Capabilities",
    "Counter",
    "ObligationSource",
    "RoleSlot",
    "SchemaZone",
    "SubjectBinding",
    "VerticalMeta",
]

# Ordered: this is the order roles are created in, and therefore the order of the
# rendered `0006*` files. Migrator first because it is the identity that applies every
# later migration; owner second because ownership transfer at `0008*` needs it.
ROLE_SLOTS: tuple[str, ...] = (
    "migrator",
    "owner",
    "gate",
    "projector",
    "recaller",
    "disposer",
    "auditor",
    "reader",
    "qa",
)

# Slot -> (constant name | None, suffix used when the slot is schema-scoped).
_ROLE_DEFAULTS: dict[str, tuple[str | None, str]] = {
    "migrator": (None, "migrator"),
    "owner": (None, "owner"),
    "gate": ("agent_gate", "gate"),
    "projector": ("agent_projector", "projector"),
    "recaller": ("agent_recaller", "recaller"),
    "disposer": ("svc_disposition", "disposer"),
    "auditor": (None, "auditor"),
    "reader": ("auditor_ro", "reader"),
    "qa": ("quality_assurance", "qa"),
}

# The six slots `vertical.schema.json` 1.0 lets a binding name. `recaller`, `auditor`
# and `qa` are absent from that table, so they are derived and cannot be overridden.
_OVERRIDABLE: frozenset[str] = frozenset(
    {"gate", "projector", "disposer", "migrator", "owner", "reader"}
)

_ROLE_PURPOSE: dict[str, str] = {
    "migrator": "applies DDL and nothing else; holds no DML on any evidentiary table",
    "owner": (
        "owns every schema; NOLOGIN and unassumable, so no session can ever act as the "
        "owner and drop a trigger the gate depends on"
    ),
    "gate": (
        "the kernel's own identity: the only role that materialises an obligation, and "
        "the only writer of the subject state machine"
    ),
    "projector": (
        "INSERT on the blame closure and NOTHING else (finding S2). The role that "
        "computes ancestry cannot read a permit into existence"
    ),
    "recaller": (
        "proposes candidates over HTTP; holds NO INSERT on the obligation table, so the "
        "role that detects a precursor cannot write one (finding S1)"
    ),
    "disposer": (
        "the only role that disposes of an obligation, and never the role that materialised it"
    ),
    "auditor": (
        "the MCP identity: INSERT on the external attestation table only, SELECT on the "
        "audit views only (finding S13)"
    ),
    "reader": "read-only across business records and measurement; no write path anywhere",
    "qa": (
        "the per-named-person views only (finding S14). Never granted an MCP account, "
        "never granted the business schema"
    ),
}

# Slot -> suffix of the schema it is named after, and the five zones every vertical has.
SCHEMA_ZONES: tuple[tuple[str, str, str], ...] = (
    ("business", "", "business records: the gated subjects and everything they cite"),
    ("meas", "_meas", "measurement: silence, standing, model cache, external attestation"),
    ("audit", "_audit", "MCP-facing views, each shaped to 25 rows and 10 KiB"),
    ("qa", "_qa", "per-named-person views. NO MCP ACCOUNT, EVER (finding S14)"),
    ("ops", "_ops", "infrastructure: outbox, cursors, register signals"),
)


@dataclass(frozen=True, slots=True)
class RoleSlot:
    """One SQL role the kernel renders, with the sentence that says why it exists."""

    slot: str
    name: str
    nologin: bool
    purpose: str
    overridable: bool


@dataclass(frozen=True, slots=True)
class SchemaZone:
    """One of the five schemas a vertical occupies."""

    zone: str
    name: str
    purpose: str


@dataclass(frozen=True, slots=True)
class VerticalMeta:
    """The ``[vertical]`` table of ``vertical.toml``."""

    name: str
    spec_version: str
    schema: str
    output_dir: str
    license: str
    description: str


@dataclass(frozen=True, slots=True)
class Counter:
    """One projected obligation counter and the CHECK whose name is the exhibit."""

    column: str
    constraint: str
    source: str | None
    polarity: str
    offset_column: str | None


@dataclass(frozen=True, slots=True)
class SubjectBinding:
    """One gated subject kind."""

    kind: str
    table: str
    id_column: str
    epoch_column: str
    state_column: str
    completing_state: str
    transition_table: str
    event_table: str | None
    completion_table: str | None
    epoch_pin_constraint: str | None
    counters: tuple[Counter, ...]


@dataclass(frozen=True, slots=True)
class AuthoritySource:
    """One ``[[authority_source]]`` entry — the compile-time form of rule `P-2`."""

    projects: tuple[str, ...]
    relation: str
    key: tuple[str, ...]
    key_columns: tuple[str, ...]
    columns: tuple[str, ...]
    on_missing: Literal["raise"]
    raise_via: str
    strictest: dict[str, str | int | bool] = field(default_factory=dict)

    @property
    def relation_schema(self) -> str:
        """Schema half of the qualified authority relation."""
        return self.relation.split(".", 1)[0]

    @property
    def relation_table(self) -> str:
        """Table half of the qualified authority relation."""
        return self.relation.split(".", 1)[1]


@dataclass(frozen=True, slots=True)
class ObligationSource:
    """One ``[[obligation_source]]`` entry: a relation that feeds a subject counter."""

    relation: str
    counter: str
    subject_kinds: tuple[str, ...]
    dedupe_key_column: str | None
    bumps_epoch: bool


@dataclass(frozen=True, slots=True)
class Capabilities:
    """The render-time switches, and the path to the ground truth that decides them."""

    attestation: str
    stored_digest: str
    triggerdef: str
    isolation: str


@dataclass(frozen=True, slots=True)
class Binding:
    """A validated ``vertical.toml``, resolved against the kernel's role and zone models."""

    source: Path
    repo_root: Path
    vertical: VerticalMeta
    subjects: tuple[SubjectBinding, ...]
    authority_sources: tuple[AuthoritySource, ...]
    obligation_sources: tuple[ObligationSource, ...]
    capabilities: Capabilities
    emit_outbox: bool
    role_overrides: dict[str, str]
    conformance_profile: str | None
    skip_requires: tuple[str, ...]
    raw: dict[str, Any]

    @property
    def output_dir(self) -> Path:
        """Absolute path of the directory rendered SQL is written to."""
        return self.repo_root / self.vertical.output_dir

    @property
    def attestation_path(self) -> Path:
        """Absolute path of the ground-truth attestation JSON."""
        return self.repo_root / self.capabilities.attestation

    @property
    def zones(self) -> tuple[SchemaZone, ...]:
        """The five schemas this vertical occupies, in creation order."""
        return tuple(
            SchemaZone(zone=zone, name=f"{self.vertical.schema}{suffix}", purpose=purpose)
            for zone, suffix, purpose in SCHEMA_ZONES
        )

    @property
    def roles(self) -> tuple[RoleSlot, ...]:
        """The nine roles this binding renders, in creation order.

        Names come from ``[roles]`` for the six slots the specification's schema can
        express, and from the derivation described in this module's docstring for the
        other three. Nothing here consults the vertical's *name*: a substrate that knew
        what "MAINLINE" meant would not be a substrate.
        """
        out: list[RoleSlot] = []
        for slot in ROLE_SLOTS:
            constant, suffix = _ROLE_DEFAULTS[slot]
            default = constant if constant is not None else f"{self.vertical.schema}_{suffix}"
            overridable = slot in _OVERRIDABLE
            name = self.role_overrides.get(slot, default) if overridable else default
            out.append(
                RoleSlot(
                    slot=slot,
                    name=name,
                    nologin=slot == "owner",
                    purpose=_ROLE_PURPOSE[slot],
                    overridable=overridable,
                )
            )
        return tuple(out)

    def role(self, slot: str) -> str:
        """Return the SQL name of one role slot."""
        for entry in self.roles:
            if entry.slot == slot:
                return entry.name
        raise KeyError(slot)

    @property
    def subject_tables(self) -> frozenset[str]:
        """Unqualified names of every gated subject table in this binding."""
        return frozenset(subject.table for subject in self.subjects)

    @property
    def obligation_relations(self) -> frozenset[str]:
        """Qualified names of every declared obligation relation in this binding."""
        return frozenset(entry.relation for entry in self.obligation_sources)
