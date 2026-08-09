# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""In-memory shapes stage 1b hands to itself, and the rows it serialises.

The split ``to_row()`` / ``to_registry_row()`` is stage 1's, kept deliberately: a ``to_row()``
carries only real, non-projected columns of a target table, and everything the generator knows
that the table has no column for goes into a registry file that no loader reads as a table.
Keeping the two apart is what makes the projected-column guard meaningful and what stops a
convenience field from turning into an ``INSERT`` nobody meant to write.

── WHAT IS EMITTED NULL, AND WHY EACH ONE IS A REFUSAL RATHER THAN A HOLE ────────────────────

``blame_edge`` has four ``NOT NULL``-ish obligations this worker deliberately does not satisfy,
and each is registered in ``pending.jsonl`` with the worker who closes it:

``commit_id``              ``NOT NULL REFERENCES commit_obj``.  A commit id is sha256 over the
                           JCS envelope and cannot be chosen.  Nothing in the corpus lane mints
                           the commit DAG, so every edge points at a commit that does not exist
                           yet and says so.
``p_link``                 ``scored_needs_features`` requires it on every non-asserted basis.
                           It is the output of an isotonic calibration fitted on an adjudicated
                           set (incident-ingestion.md §7) and belongs to the recall lane.  This
                           worker emits the **features** — the arithmetic, kept — and refuses to
                           invent the probability computed from them.  A corpus that supplied a
                           plausible ``p_link`` would launder a calibration one hop upstream,
                           which is the same defect class as writing a projected column.
``evidence_quote_sha256``  ``asserted_needs_quote`` requires it on ``asserted_document``.  It is
                           the digest of an exact, unique substring of a document that has not
                           been rendered.  Every asserted edge therefore carries a ``quote_ref``
                           instead — a stable reference the renderer binds to real text.
``review_sig``             ``human_needs_signature`` requires it on ``asserted_human``.  A
                           signature is custody's, and forging one in a fixture would make the
                           one column that proves a human was in the loop unfalsifiable.

The loader will be refused until those are bound, and it is right to refuse.  That is the same
posture ``skeleton/moc.py`` takes on ``change_request.merged_commit``.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from typing import Any

from ..skeleton import clock

__all__ = [
    "BlameEdge",
    "Clause",
    "ClauseRevision",
    "GoldRow",
    "PendingField",
    "ProposedRevision",
    "Row",
]

Row = dict[str, Any]

#: The four bases, in descending evidential strength (ARCHITECTURE.md §5.4,
#: ``mainline.blame_basis``).
BASES: tuple[str, ...] = (
    "asserted_document",
    "asserted_human",
    "derived_documentary",
    "inferred_semantic",
)

#: ``mainline.blame_state``.
STATES: tuple[str, ...] = ("active", "provisional", "dormant", "refuted")

#: ``mainline.control_delta``.
DELTAS: tuple[str, ...] = ("introduce", "strengthen", "restate", "weaken", "remove")

#: The gold set's three labels.
LABELS: tuple[str, ...] = ("true", "decoy", "negative_control")


@dataclass(frozen=True, slots=True)
class Clause:
    """One obligation, identified once and for ever by ``clause_uuid``.

    ``clause_key`` is the natural key the id is minted from and is *where the obligation was
    born*, never where it currently lives: ``MRD/PRO-MEC-014/7.3`` still names the spine clause
    in 2026, three documents and two numbering schemes later.  Any worker can recompute the id
    with ``rng.sid("clause", clause_key)`` without reading a byte of this output.
    """

    clause_key: str
    clause_uuid: str
    site_id: str
    site_code: str
    origin_doc_code: str
    origin_doc_id: str
    activity_root: str
    control_class: str
    barrier_role: str
    setpoint_key: str | None
    section: int
    position: int
    birth_label: str
    birth_revision_key: str
    birth_on: dt.date
    is_spine: bool

    def to_row(self) -> Row:
        # `birth_commit` is NOT NULL and is emitted null: no commit exists yet.  `head_commit`
        # and `retired_commit` are genuinely nullable pointers.
        return {
            "activity_root": self.activity_root,
            "birth_commit": None,
            "clause_uuid": self.clause_uuid,
            "head_commit": None,
            "retired_commit": None,
            "site_id": self.site_id,
        }

    def to_registry_row(self) -> Row:
        return {
            "activity_root": self.activity_root,
            "barrier_role": self.barrier_role,
            "birth_label": self.birth_label,
            "birth_on": clock.iso_date(self.birth_on),
            "birth_revision_key": self.birth_revision_key,
            "clause_key": self.clause_key,
            "clause_uuid": self.clause_uuid,
            "control_class": self.control_class,
            "is_spine": self.is_spine,
            "origin_doc_code": self.origin_doc_code,
            "origin_doc_id": self.origin_doc_id,
            "position": self.position,
            "section": self.section,
            "setpoint_key": self.setpoint_key,
            "site_code": self.site_code,
            "site_id": self.site_id,
        }


@dataclass(frozen=True, slots=True)
class ClauseRevision:
    """One clause, as it stood after one document revision touched it.

    This is the corpus-scaffolding half of ``mainline.clause_version``: the columns that are
    facts about *history* rather than about text.  ``raw_text``, ``canon_text``, ``canon_sha256``
    and the whole M2 BLOODLINE group are absent — the first three because no prose exists yet,
    the last four because they are projected from the blame ancestry by a trigger and a corpus
    that supplied them would make the gate read a number the writer chose.
    """

    clause_key: str
    clause_uuid: str
    revision_key: str
    site_id: str
    site_code: str
    doc_code: str
    doc_id: str
    effective_on: dt.date
    rev_no: int
    ordinal: int
    printed_label: str
    template_generation: int
    control_delta: str
    delta_basis: str
    driver: str
    author_sub: str
    author_separated: bool
    cause_kind: str
    cause_event_ref: str | None
    injector: str | None
    setpoint_key: str | None = None
    setpoint_from: float | None = None
    setpoint_to: float | None = None

    @property
    def key(self) -> str:
        return f"{self.revision_key}#{self.clause_key}"

    def to_row(self) -> Row:
        return {
            "author_separated": self.author_separated,
            "author_sub": self.author_sub,
            "cause_event_ref": self.cause_event_ref,
            "cause_kind": self.cause_kind,
            "clause_key": self.clause_key,
            "clause_uuid": self.clause_uuid,
            "control_delta": self.control_delta,
            "delta_basis": self.delta_basis,
            "doc_code": self.doc_code,
            "doc_id": self.doc_id,
            "driver": self.driver,
            "effective_on": clock.iso_date(self.effective_on),
            "injector": self.injector,
            "ordinal": self.ordinal,
            "printed_label": self.printed_label,
            "rev_no": self.rev_no,
            "revision_key": self.revision_key,
            "setpoint_from": self.setpoint_from,
            "setpoint_key": self.setpoint_key,
            "setpoint_to": self.setpoint_to,
            "site_code": self.site_code,
            "site_id": self.site_id,
            "template_generation": self.template_generation,
        }


@dataclass(frozen=True, slots=True)
class ProposedRevision:
    """A clause change that lives on a branch and has never been merged.

    ``MOC-2026-0413`` is the only one that matters on camera: it proposes restoring the spine
    clause's setpoint from 135 to 150, the CAT lattice reads that as ``weaken``, the ancestry
    holds a severity-4 event, and the merge is refused.  It is emitted separately from
    ``clause_revision.jsonl`` because a proposal that appeared in the merged history would make
    the refusal a lie — the whole beat is that this change did **not** land.
    """

    ref_name: str
    cr_external_ref: str
    clause_key: str
    clause_uuid: str
    site_id: str
    doc_code: str
    proposed_on: dt.date
    control_delta: str
    delta_basis: str
    setpoint_key: str | None
    setpoint_from: float | None
    setpoint_to: float | None
    rationale_kind: str

    def to_row(self) -> Row:
        return {
            "clause_key": self.clause_key,
            "clause_uuid": self.clause_uuid,
            "control_delta": self.control_delta,
            "cr_external_ref": self.cr_external_ref,
            "delta_basis": self.delta_basis,
            "doc_code": self.doc_code,
            "proposed_on": clock.iso_date(self.proposed_on),
            "rationale_kind": self.rationale_kind,
            "ref_name": self.ref_name,
            "setpoint_from": self.setpoint_from,
            "setpoint_key": self.setpoint_key,
            "setpoint_to": self.setpoint_to,
            "site_id": self.site_id,
        }


@dataclass(frozen=True, slots=True)
class BlameEdge:
    """One authored causal fact: event *e* generated the obligation *c* carries.

    The row this serialises into is ``mainline.blame_edge`` minus the four values listed in the
    module docstring.  ``features`` is the arithmetic incident-ingestion.md §7 names, kept in
    full so the recall lane's calibration has inputs; ``attribution`` is the prose a human is
    shown, composed deterministically from those same features by
    :func:`mainline_corpus.blame.causality.attribution_of` — no model wrote it and the corpus
    never claims one did.
    """

    event_ref: str
    event_id: str
    clause_key: str
    clause_uuid: str
    basis: str
    state: str
    site_id: str
    site_code: str
    revision_key: str
    effective_on: dt.date
    severity_gate: int
    control_class: str
    hazard_energy: str
    channel_a_visible: bool
    p_doc_trace: float
    generative_reason: str
    attribution: str
    features: dict[str, Any]
    evidence_doc_id: str | None
    quote_ref: str | None
    quote_ref_kind: str | None
    reviewed_by: str | None
    provisional_until: dt.datetime | None
    injector: str | None
    cross_site: bool
    lag_days: float

    @property
    def key(self) -> str:
        return f"{self.clause_key}|{self.event_ref}|{self.basis}"

    def to_row(self) -> Row:
        """``mainline.blame_edge``, with the four unbindable values null and registered."""
        return {
            "attribution": self.attribution,
            "basis": self.basis,
            "clause_uuid": self.clause_uuid,
            "commit_id": None,
            "event_id": self.event_id,
            "evidence_doc_id": self.evidence_doc_id,
            "evidence_quote_sha256": None,
            "evidence_span": None,
            "features": self.features,
            "model_id": None,
            "p_link": None,
            "prompt_version": None,
            "provisional_until": (
                None if self.provisional_until is None else clock.iso(self.provisional_until)
            ),
            "review_sig": None,
            "reviewed_at": None,
            "reviewed_by": self.reviewed_by,
            "site_id": self.site_id,
            "state": self.state,
        }

    def to_registry_row(self) -> Row:
        return {
            "basis": self.basis,
            "channel_a_visible": self.channel_a_visible,
            "clause_key": self.clause_key,
            "clause_uuid": self.clause_uuid,
            "control_class": self.control_class,
            "cross_site": self.cross_site,
            "effective_on": clock.iso_date(self.effective_on),
            "event_id": self.event_id,
            "event_ref": self.event_ref,
            "generative_reason": self.generative_reason,
            "hazard_energy": self.hazard_energy,
            "injector": self.injector,
            "lag_days": round(self.lag_days, 2),
            "p_doc_trace": round(self.p_doc_trace, 4),
            "quote_ref": self.quote_ref,
            "quote_ref_kind": self.quote_ref_kind,
            "revision_key": self.revision_key,
            "severity_gate": self.severity_gate,
            "site_code": self.site_code,
            "state": self.state,
        }


@dataclass(frozen=True, slots=True)
class GoldRow:
    """One row of GS0: a judged (event, clause) pair and the reason it is judged that way.

    ``generative_reason`` is prose and is mandatory on every row, including the negatives.  A
    negative control whose reason says nothing is indistinguishable from a pair nobody looked
    at, and the false-attribution rate computed over "pairs nobody looked at" is not a number
    anybody should put in front of a buyer's lawyer.
    """

    event_id: str
    event_ref: str
    clause_uuid: str
    clause_key: str
    label: str
    basis: str | None
    state: str | None
    p_doc_trace: float | None
    channel_a_visible: bool
    generative_reason: str
    decoy_of: str | None
    documented_cause: str | None
    control_class: str
    hazard_energy: str
    severity_gate: int
    site_id: str
    site_code: str
    occurred_at: dt.datetime
    revision_key: str
    doc_code: str
    effective_on: dt.date
    injector: str | None
    quote_ref: str | None

    def to_row(self) -> Row:
        return {
            "basis": self.basis,
            "channel_a_visible": self.channel_a_visible,
            "clause_key": self.clause_key,
            "clause_uuid": self.clause_uuid,
            "control_class": self.control_class,
            "decoy_of": self.decoy_of,
            "doc_code": self.doc_code,
            "documented_cause": self.documented_cause,
            "effective_on": clock.iso_date(self.effective_on),
            "event_id": self.event_id,
            "event_ref": self.event_ref,
            "generative_reason": self.generative_reason,
            "hazard_energy": self.hazard_energy,
            "injector": self.injector,
            "label": self.label,
            "occurred_at": clock.iso(self.occurred_at),
            "p_doc_trace": None if self.p_doc_trace is None else round(self.p_doc_trace, 4),
            "quote_ref": self.quote_ref,
            "revision_key": self.revision_key,
            "severity_gate": self.severity_gate,
            "site_code": self.site_code,
            "site_id": self.site_id,
            "state": self.state,
        }


@dataclass(frozen=True, slots=True)
class PendingField:
    """A column stage 1b deliberately left null, and who fills it.

    Structurally similar to ``skeleton.model.PendingField`` and deliberately not imported from
    it: the two registers are reconciled against different row sets, and a shared class would
    invite a shared reconciliation that checks neither properly.

    The one shape difference is ``reason_code``.  Stage 1's register repeats the prose on every
    row; there are five thousand rows here and six distinct reasons, so the prose would be two
    megabytes of duplicated paragraphs in a committed fixture.  The code resolves against
    ``pending_reasons.json``, which is also the better discipline: one string, one place, and a
    reader who wants to change the wording changes it once.
    """

    table: str
    key: str
    column: str
    owner: str
    reason_code: str
    facts: dict[str, Any] = field(default_factory=dict)

    def to_row(self) -> Row:
        return {
            "column": self.column,
            "facts": self.facts,
            "key": self.key,
            "owner": self.owner,
            "reason_code": self.reason_code,
            "table": self.table,
        }
