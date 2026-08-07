# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""In-memory shapes the stage-1 generators hand to each other.

These are *not* the emitted rows.  Emitted rows are plain dicts built by ``to_row()`` on each
shape, and they carry only real, non-projected columns of the target table.  Keeping the two
apart is what makes the projected-column guard meaningful: an internal field such as
``Asset.role`` or ``Event.major`` exists for the generator's own use and is never serialised
into a table file by accident, because serialisation is explicit.

``PendingField`` is the honest half of "history first, text second".  Stage 1 knows an event
happened, to which asset, releasing which energy, defeating which controls — it does not know
the narrative, because writing prose is stage 2's job, and it does not know
``source_sha256``, because the source document does not exist until stage 3.  Those columns are
``NOT NULL`` in the schema.  Rather than fill them with a plausible-looking value (a hash of
something that is not the raw bytes is a *lie in a custody column*), stage 1 emits ``null`` and
registers the gap here, naming the worker who closes it.  A loader that meets an unclosed gap is
refused, which is the correct behaviour and makes the pipeline's incompleteness visible instead
of fake.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from typing import Any

from . import clock

__all__ = [
    "ActivityNode",
    "Asset",
    "AssetEdge",
    "ChangeRequest",
    "ControlFailure",
    "Doc",
    "DocRevision",
    "Event",
    "PendingField",
    "PermitBoundary",
    "Person",
    "Site",
]

Row = dict[str, Any]


@dataclass(frozen=True, slots=True)
class Site:
    site_id: str
    code: str
    name: str
    full_name: str
    kind: str
    ref_slug: str
    tz_offset_hours: int
    commissioned_on: dt.date
    event_weight: float
    on_camera: bool

    @property
    def main_ref(self) -> str:
        return f"site/{self.ref_slug}/main"

    def to_row(self) -> Row:
        return {
            "code": self.code,
            "commissioned_on": clock.iso_date(self.commissioned_on),
            "full_name": self.full_name,
            "kind": self.kind,
            "main_ref": self.main_ref,
            "name": self.name,
            "on_camera": self.on_camera,
            "ref_slug": self.ref_slug,
            "site_id": self.site_id,
            "tz_offset_hours": self.tz_offset_hours,
        }


@dataclass(frozen=True, slots=True)
class ActivityNode:
    scope_id: str
    site_id: str
    site_code: str
    level: int
    parent_scope: str | None
    label: str
    activity_root: str
    taxonomy_ver: int
    induced_by: str
    frozen_node: bool

    def to_row(self) -> Row:
        return {
            "activity_root": self.activity_root,
            "frozen": self.frozen_node,
            "induced_by": self.induced_by,
            "label": self.label,
            "level": self.level,
            "parent_scope": self.parent_scope,
            "scope_id": self.scope_id,
            "site_id": self.site_id,
            "taxonomy_ver": self.taxonomy_ver,
        }


@dataclass(frozen=True, slots=True)
class Asset:
    tag: str
    site_id: str
    site_code: str
    family_id: str
    asset_class: str
    label: str
    service: str
    criticality: str
    activity_root: str
    hazard_energies: tuple[str, ...]
    role: str  # member | motor | instrument | accumulator | standalone

    def to_row(self) -> Row:
        return {
            "activity_root": self.activity_root,
            "asset_class": self.asset_class,
            "criticality": self.criticality,
            "family_id": self.family_id,
            "hazard_energies": list(self.hazard_energies),
            "label": self.label,
            "role": self.role,
            "service": self.service,
            "site_id": self.site_id,
            "tag": self.tag,
        }


@dataclass(frozen=True, slots=True)
class AssetEdge:
    site_id: str
    from_tag: str
    to_tag: str
    kind: str

    def to_row(self) -> Row:
        return {
            "from_tag": self.from_tag,
            "kind": self.kind,
            "site_id": self.site_id,
            "to_tag": self.to_tag,
        }


@dataclass(frozen=True, slots=True)
class PermitBoundary:
    permit_id: str
    permit_ref: str
    asset_tag: str
    isolation_point_id: str | None

    def to_row(self) -> Row:
        return {
            "asset_tag": self.asset_tag,
            "isolation_point_id": self.isolation_point_id,
            "permit_id": self.permit_id,
        }


@dataclass(frozen=True, slots=True)
class Person:
    signer_sub: str
    given: str
    surname: str
    display_name: str
    org_key: str
    org_name: str
    role_key: str
    role_label: str
    rank: int
    home_site: str
    effective_from: dt.datetime
    separated_at: dt.datetime | None
    enrolment_assurance: str
    tickets: tuple[str, ...]
    competency_source_id: str
    competency_sha256: str
    identity_source: str

    def to_row(self) -> Row:
        return {
            "competency_sha256": self.competency_sha256,
            "competency_snapshot": {
                "authorisations": list(self.tickets),
                "display_name": self.display_name,
                "full_name": f"{self.given} {self.surname}",
                "home_site": self.home_site,
                "role": self.role_label,
            },
            "competency_source_id": self.competency_source_id,
            "effective_from": clock.iso(self.effective_from),
            "enrolment_assurance": self.enrolment_assurance,
            "identity_source": self.identity_source,
            "org": self.org_name,
            "rank": self.rank,
            "separated_at": None if self.separated_at is None else clock.iso(self.separated_at),
            "signer_sub": self.signer_sub,
        }


@dataclass(frozen=True, slots=True)
class Doc:
    doc_id: str
    site_id: str
    site_code: str
    doc_code: str
    title: str
    family: str
    activity_root: str
    asset_classes: tuple[str, ...]
    first_issued: dt.date
    cadence_years: float
    retypeset_2016: bool
    state: str
    superseded_by: tuple[str, ...] | None
    anchor: str | None
    fleet_sibling: bool
    template_generation: int

    def to_row(self) -> Row:
        # `open_token_count` is PROJECTED and is deliberately absent.
        return {
            "doc_code": self.doc_code,
            "doc_id": self.doc_id,
            "site_id": self.site_id,
            "state": self.state,
            "superseded_by": None if self.superseded_by is None else list(self.superseded_by),
            "title": self.title,
        }

    def to_registry_row(self) -> Row:
        """Corpus scaffolding: the authored facts about the document that `doc` has no column for."""
        return {
            "activity_root": self.activity_root,
            "anchor": self.anchor,
            "asset_classes": list(self.asset_classes),
            "cadence_years": self.cadence_years,
            "doc_code": self.doc_code,
            "doc_id": self.doc_id,
            "family": self.family,
            "first_issued": clock.iso_date(self.first_issued),
            "fleet_sibling": self.fleet_sibling,
            "retypeset_2016": self.retypeset_2016,
            "site_id": self.site_id,
            "template_generation": self.template_generation,
        }


@dataclass(frozen=True, slots=True)
class DocRevision:
    revision_key: str
    doc_id: str
    doc_code: str
    site_id: str
    rev_no: int
    effective_on: dt.date
    driver: str
    author_sub: str
    template_generation: int
    driving_event_ref: str | None
    driving_change_ref: str | None = None

    def to_row(self) -> Row:
        return {
            "author_sub": self.author_sub,
            "doc_code": self.doc_code,
            "doc_id": self.doc_id,
            "driver": self.driver,
            "driving_change_ref": self.driving_change_ref,
            "driving_event_ref": self.driving_event_ref,
            "effective_on": clock.iso_date(self.effective_on),
            "rev_no": self.rev_no,
            "revision_key": self.revision_key,
            "site_id": self.site_id,
            "template_generation": self.template_generation,
        }


@dataclass(frozen=True, slots=True)
class ControlFailure:
    failure_id: str
    event_id: str
    event_ref: str
    control_class: str
    barrier_role: str
    failure_mode: str
    icam_tier: str
    hazard_energy: str

    def to_row(self) -> Row:
        # `evidence_span` and `quote_sha256` are NOT NULL in §5.4 and are offsets into a narrative
        # that stage 1 has not written.  They are emitted null and registered as pending.
        return {
            "barrier_role": self.barrier_role,
            "control_class": self.control_class,
            "evidence_span": None,
            "event_id": self.event_id,
            "failure_id": self.failure_id,
            "failure_mode": self.failure_mode,
            "hazard_energy": self.hazard_energy,
            "icam_tier": self.icam_tier,
            "quote_sha256": None,
        }


@dataclass(slots=True)
class Event:
    event_id: str
    external_ref: str
    site_id: str
    site_code: str
    kind: str
    occurred_at: dt.datetime
    ingested_at: dt.datetime
    title: str
    scope_id: str
    activity_root: str
    activity_series: str
    activity_file: str
    assets: tuple[str, ...]
    hazard_energy: str
    severity_actual: int
    severity_potential: int
    severity_gate: int
    severity_basis: str
    potential_admitted: int
    admission_reason: str
    fatal_potential_trigger: bool
    consequence_proxy: dict[str, Any]
    source_object_key: str
    canon_version: int
    major: bool
    anchored: bool
    summary_facts: tuple[str, ...] = field(default_factory=tuple)
    fleet_sibling_of: str | None = None

    def to_row(self) -> Row:
        # `narrative`, `source_sha256` and `severity_span` are NOT NULL / span columns that
        # depend on rendered text.  Emitted null; registered as pending.  `cluster_id` is
        # genuinely nullable — dedup clustering is an ingestion output, not a corpus fact.
        return {
            "canon_version": self.canon_version,
            "cluster_id": None,
            "consequence_proxy": self.consequence_proxy,
            "event_id": self.event_id,
            "external_ref": self.external_ref,
            "ingested_at": clock.iso(self.ingested_at),
            "kind": self.kind,
            "narrative": None,
            "occurred_at": clock.iso(self.occurred_at),
            "severity_actual": self.severity_actual,
            "severity_basis": self.severity_basis,
            "severity_gate": self.severity_gate,
            "severity_potential": self.severity_potential,
            "severity_span": None,
            "site_id": self.site_id,
            "source_doc_id": None,
            "source_object_key": self.source_object_key,
            "source_sha256": None,
            "title": self.title,
        }

    def to_registry_row(self) -> Row:
        """Corpus scaffolding: the structural facts `event` has no column for.

        ``corpus-blame-key`` reads this to author causality, and ``corpus-render-cache`` reads it
        to render a narrative that is *about the same event the structure describes*.
        """
        return {
            "activity_file": self.activity_file,
            "activity_root": self.activity_root,
            "activity_series": self.activity_series,
            "admission_reason": self.admission_reason,
            "anchored": self.anchored,
            "assets": list(self.assets),
            "event_id": self.event_id,
            "external_ref": self.external_ref,
            "fatal_potential_trigger": self.fatal_potential_trigger,
            "fleet_sibling_of": self.fleet_sibling_of,
            "hazard_energy": self.hazard_energy,
            "major": self.major,
            "potential_admitted": self.potential_admitted,
            "scope_id": self.scope_id,
            "site_id": self.site_id,
            "summary_facts": list(self.summary_facts),
        }


@dataclass(frozen=True, slots=True)
class ChangeRequest:
    cr_id: str
    external_ref: str
    site_id: str
    site_code: str
    ref_name: str
    target_ref: str
    state: str
    opened_at: dt.datetime
    intent: str
    activity_root: str
    doc_codes: tuple[str, ...]
    author_sub: str
    anchored: bool

    def to_row(self) -> Row:
        # `site_role`, `head_seq`, `gate_epoch`, `open_blocking`, `open_residue` and
        # `open_conflicts` are PROJECTED and deliberately absent.  `merged_commit` is null
        # because stage 1 mints no commits; a `merged` row with a null merge evidence is exactly
        # what `cr_merge_evidence` should refuse until the commit exists.
        return {
            "cr_id": self.cr_id,
            "external_ref": self.external_ref,
            "merged_commit": None,
            "opened_at": clock.iso(self.opened_at),
            "ref_name": self.ref_name,
            "site_id": self.site_id,
            "state": self.state,
            "target_ref": self.target_ref,
        }

    def to_registry_row(self) -> Row:
        return {
            "activity_root": self.activity_root,
            "anchored": self.anchored,
            "author_sub": self.author_sub,
            "cr_id": self.cr_id,
            "doc_codes": list(self.doc_codes),
            "external_ref": self.external_ref,
            "intent": self.intent,
            "site_id": self.site_id,
        }


@dataclass(frozen=True, slots=True)
class PendingField:
    """A ``NOT NULL`` column stage 1 deliberately left null, and who fills it."""

    table: str
    key: str
    column: str
    owner: str
    reason: str
    facts: dict[str, Any]

    def to_row(self) -> Row:
        return {
            "column": self.column,
            "facts": self.facts,
            "key": self.key,
            "owner": self.owner,
            "reason": self.reason,
            "table": self.table,
        }
