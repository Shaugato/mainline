# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""In-memory shapes for stage 1c, and the two rules that decide what leaves them.

Rule 1 — **an emitted row carries only real, non-projected columns of its target table.**
``site_role``, ``head_seq``, ``gate_epoch``, ``open_blocking``, ``open_residue`` and
``open_conflicts`` are projections of ``mainline.change_request`` and appear nowhere here.  The
emitter's denylist is the enforcement; this module's job is not to hand it anything to catch.

Rule 2 — **what only the database can compute is emitted null and registered, never guessed.**
Two columns fall under it and they are worth naming precisely:

``cr_clause.commit_id``
    The declared scope is pinned to a *clause version*, not to a clause, so the foreign key is
    onto ``(clause_uuid, commit_id)``.  ``commit_id`` is sha256 over the JCS envelope and cannot
    be chosen; nothing in the corpus lane mints commits.  Every row therefore carries the natural
    key of the revision whose commit closes it (``commit_for_revision_key``), so the worker that
    does mint the DAG closes this deterministically rather than by search.

``cr_event.prev_digest`` / ``cr_event.seq``
    ``chain_digest`` is a ``STORED`` generated column computed by the server over CockroachDB's
    own ``JSONB::STRING`` rendering, and ``mainline.fn_cr_event_chain`` refuses any row whose
    ``prev_digest`` is not byte-equal to the predecessor's.  A corpus that guessed those bytes
    would be refused; a corpus that guessed them *correctly* would have reimplemented the
    server's normaliser in Python and staked reproducibility on the two never diverging.
    Migration 0118 step 3 shows the shipped answer: the merge procedure READS the predecessor's
    ``chain_digest``.  So this stage emits an ordered **plan of transitions**, not a ledger of
    events, and the loader executes it so that the chain is minted where it can only be minted.

That is why ``cr_transition_plan.jsonl`` declares ``table: null``.  It is not a table file that
happens to be incomplete — it is a different kind of artefact, and calling it ``cr_event.jsonl``
would invite exactly the direct-insert that the chain exists to prevent.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from typing import Any

from ..skeleton import clock

__all__ = [
    "SCOPE_BASES",
    "SCOPE_RELATIONS",
    "CrClause",
    "CrTransition",
    "MocDossier",
    "PendingField",
    "Row",
]

Row = dict[str, Any]

#: The closed relation vocabulary of ``mainline.cr_clause`` (migration 0053,
#: ``cr_clause_relation_known``).  A value outside this set is refused by the database, so it is
#: refused here, where the diagnosis is cheap.
SCOPE_RELATIONS: frozenset[str] = frozenset({"edits", "introduces", "retires"})

#: How a binding came to exist.  The first four read a fact another generator authored; only
#: ``moc_stream:window`` draws, and it draws only where the other four are silent.  The basis is
#: carried on every registry row because "who decided this" is the question a reviewer asks of a
#: provenance relation first, and a corpus that cannot answer it is asserting rather than showing.
SCOPE_BASES: frozenset[str] = frozenset(
    {
        "skeleton:driving_change_ref",
        "injector:weakening_chain",
        "injector:document_split",
        "blame:proposed_revision",
        "moc_stream:window",
    }
)


@dataclass(frozen=True, slots=True)
class CrClause:
    """One declared-scope row: what a change request says it changes, pinned to a version."""

    cr_id: str
    cr_external_ref: str
    site_id: str
    site_code: str
    clause_uuid: str
    clause_key: str
    relation: str
    basis: str
    realised: bool
    commit_for_revision_key: str
    effective_on: dt.date | None
    control_delta: str | None
    setpoint_key: str | None
    setpoint_from: float | None
    setpoint_to: float | None
    doc_code: str
    driver: str | None

    def __post_init__(self) -> None:
        if self.relation not in SCOPE_RELATIONS:
            raise ValueError(
                f"{self.cr_external_ref}/{self.clause_key}: relation {self.relation!r} is outside "
                f"{sorted(SCOPE_RELATIONS)}; cr_clause_relation_known would refuse the insert"
            )
        if self.basis not in SCOPE_BASES:
            raise ValueError(
                f"{self.cr_external_ref}/{self.clause_key}: basis {self.basis!r} is outside "
                f"{sorted(SCOPE_BASES)}"
            )

    @property
    def key(self) -> str:
        return f"{self.cr_external_ref}/{self.clause_key}/{self.relation}"

    def to_row(self) -> Row:
        """Return the loadable row.  ``commit_id`` is null and registered pending."""
        return {
            "clause_uuid": self.clause_uuid,
            "commit_id": None,
            "cr_id": self.cr_id,
            "relation": self.relation,
        }

    def to_registry_row(self) -> Row:
        """Corpus scaffolding: everything ``cr_clause`` has no column for."""
        return {
            "basis": self.basis,
            "clause_key": self.clause_key,
            "clause_uuid": self.clause_uuid,
            "commit_for_revision_key": self.commit_for_revision_key,
            "control_delta": self.control_delta,
            "cr_external_ref": self.cr_external_ref,
            "cr_id": self.cr_id,
            "doc_code": self.doc_code,
            "driver": self.driver,
            "effective_on": None
            if self.effective_on is None
            else clock.iso_date(self.effective_on),
            "realised": self.realised,
            "relation": self.relation,
            "setpoint_from": self.setpoint_from,
            "setpoint_key": self.setpoint_key,
            "setpoint_to": self.setpoint_to,
            "site_code": self.site_code,
            "site_id": self.site_id,
        }


@dataclass(frozen=True, slots=True)
class CrTransition:
    """One planned act on a change request.

    Not a ``cr_event`` row.  ``seq``, ``prev_seq``, ``prev_digest`` and ``chain_digest`` are
    absent by construction — see this module's docstring — and ``execute_via`` names the surface
    through which the loader must perform the act so that the database mints them itself.
    """

    cr_id: str
    cr_external_ref: str
    site_id: str
    site_code: str
    step: int
    from_state: str
    to_state: str
    at: dt.datetime
    actor_sub: str
    actor_role: str
    payload: dict[str, Any]
    execute_via: str
    blocked_by: tuple[str, ...]

    @property
    def edge(self) -> tuple[str, str]:
        return (self.from_state, self.to_state)

    @property
    def key(self) -> str:
        return f"{self.cr_external_ref}#{self.step:02d}"

    def to_row(self) -> Row:
        return {
            "actor_role": self.actor_role,
            "actor_sub": self.actor_sub,
            "at": clock.iso(self.at),
            "blocked_by": list(self.blocked_by),
            "cr_external_ref": self.cr_external_ref,
            "cr_id": self.cr_id,
            "execute_via": self.execute_via,
            "from_state": self.from_state,
            "payload": self.payload,
            "site_code": self.site_code,
            "site_id": self.site_id,
            "step": self.step,
            "subject_kind": "change_request",
            "to_state": self.to_state,
        }


@dataclass(frozen=True, slots=True)
class MocDossier:
    """One change request, rolled up: what it declares, what it did, and what should refuse it.

    ``precursor_severity_max_from_answer_key`` is the highest ``severity_gate`` among the blame
    edges the answer key holds against this change request's declared clauses.  It is a
    PREDICTION about what the database will project, written down so the two can be compared —
    never a value the database reads.  It is not ``sev_max`` and it is not loaded anywhere; the
    projection is derived by trigger from ``clause_blame_closure`` or the corpus is wrong, which
    is exactly where that disagreement should surface.
    """

    cr_id: str
    external_ref: str
    site_id: str
    site_code: str
    ref_name: str
    target_ref: str
    intent: str
    terminal_state: str
    anchored: bool
    opened_at: dt.datetime
    author_sub: str
    doc_codes: tuple[str, ...]
    clause_count: int
    relation_histogram: dict[str, int]
    basis_histogram: dict[str, int]
    realised_scope: bool
    weakening_steps: int
    transition_count: int
    epoch_bumps: int
    reopened: bool
    last_transition_at: dt.datetime | None
    precursor_events: tuple[str, ...]
    precursor_severity_max_from_answer_key: int | None

    def to_row(self) -> Row:
        return {
            "anchored": self.anchored,
            "author_sub": self.author_sub,
            "basis_histogram": dict(sorted(self.basis_histogram.items())),
            "clause_count": self.clause_count,
            "cr_id": self.cr_id,
            "doc_codes": list(self.doc_codes),
            "epoch_bumps": self.epoch_bumps,
            "external_ref": self.external_ref,
            "intent": self.intent,
            "last_transition_at": (
                None if self.last_transition_at is None else clock.iso(self.last_transition_at)
            ),
            "opened_at": clock.iso(self.opened_at),
            "precursor_events": list(self.precursor_events),
            "precursor_severity_max_from_answer_key": self.precursor_severity_max_from_answer_key,
            "realised_scope": self.realised_scope,
            "ref_name": self.ref_name,
            "relation_histogram": dict(sorted(self.relation_histogram.items())),
            "reopened": self.reopened,
            "site_code": self.site_code,
            "site_id": self.site_id,
            "target_ref": self.target_ref,
            "terminal_state": self.terminal_state,
            "transition_count": self.transition_count,
            "weakening_steps": self.weakening_steps,
        }


@dataclass(frozen=True, slots=True)
class PendingField:
    """A ``NOT NULL`` column this stage deliberately left null, and who closes it.

    Shaped like ``blame.model.PendingField`` — ``reason_code`` resolving against
    ``pending_reasons.json`` — because there are three distinct reasons and thousands of rows,
    and repeating a paragraph per row would put megabytes of duplicated prose in a fixture.
    Deliberately not imported from either sibling: the three registers are reconciled against
    different row sets, and a shared class invites one reconciliation that checks none of them.
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
