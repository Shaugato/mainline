# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""Declared scope: which clauses each change request says it changes.

``mainline.cr_clause`` is the relation the change-request merge gate reads.  Without it a change
register is a list of titles: ``open_blocking`` has nothing to count, the MOC Ancestry Audit has
nothing to walk, and finding S16 — *the repository is the protected branch and the permit is one
of its refs* — has no enforcement surface on the document side at all.

Stage 1 emitted the register.  Stage 1b authored causality.  Neither emitted scope, and the two
anchored spine revisions were the only place in the corpus where a clause change pointed at a
change record.  This module closes that, under one discipline:

── THE VEHICLE IS NOT THE CAUSE ────────────────────────────────────────────────────────────────
A change request is the *administrative vehicle* through which an edit reaches a controlled
document.  A blame edge is a claim about what *caused* the edit.  They are different relations
with different evidential weight, and conflating them is how a provenance system starts asserting
things it cannot support.

So scope is bound from a document revision, never from an event, and ``incident`` is excluded
from the drivers this stage may bind (``params.ADMISSIBLE_R5_DRIVERS``).  Binding an MOC to an
incident-driven revision would assert that the change record produced an edit that the answer key
says an incident produced — a contradiction inside our own fixtures, and one that would train the
recall harness on a false positive it could never have detected.

── FIVE BASES, FOUR OF THEM READ RATHER THAN DRAWN ──────────────────────────────────────────────
=========================  ==========================================================
``skeleton:...``           stage 1 wrote ``DocRevision.driving_change_ref``
``injector:weakening_...`` each weakening step already names the MOC it hid behind
``injector:document_...``  each migrating clause already names its change record
``blame:proposed_...``     the 2026 proposal already names ``MOC-2026-0413``
``moc_stream:window``      authored HERE, and only where the four above are silent
=========================  ==========================================================

The union of the first four is taken whole; ``moc_stream:window`` runs only for a change request
the other four left with no scope at all.  ``MOC-2026-0413`` therefore keeps a declared scope of
exactly one clause, which is what makes ``open_blocking = 1`` a legible number on camera rather
than an arbitrary one.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Mapping, Sequence

from .. import rng
from ..blame.build import AnswerKey
from ..blame.model import Clause, ClauseRevision
from ..skeleton.model import ChangeRequest
from . import params
from .model import CrClause

__all__ = ["ScopeResult", "build_scope"]

#: Highest priority first.  Two bases proposing the same ``(change request, clause, relation)``
#: keep the higher one, so an authored draw can never displace a fact somebody else wrote down.
_BASIS_PRIORITY: tuple[str, ...] = (
    "skeleton:driving_change_ref",
    "blame:proposed_revision",
    "injector:weakening_chain",
    "injector:document_split",
    "moc_stream:window",
)


class ScopeResult:
    """Every declared-scope row, plus the index the lifecycle and dossier stages read."""

    __slots__ = ("_by_cr", "rows", "unscoped")

    def __init__(self, rows: Sequence[CrClause], unscoped: Sequence[str]) -> None:
        self.rows = tuple(rows)
        self.unscoped = tuple(unscoped)
        by_cr: dict[str, list[CrClause]] = {}
        for row in self.rows:
            by_cr.setdefault(row.cr_external_ref, []).append(row)
        self._by_cr = {
            ref: tuple(sorted(items, key=lambda item: (item.clause_key, item.relation)))
            for ref, items in by_cr.items()
        }

    def for_cr(self, external_ref: str) -> tuple[CrClause, ...]:
        return self._by_cr.get(external_ref, ())

    def relation_histogram(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for row in self.rows:
            counts[row.relation] = counts.get(row.relation, 0) + 1
        return dict(sorted(counts.items()))

    def basis_histogram(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for row in self.rows:
            counts[row.basis] = counts.get(row.basis, 0) + 1
        return dict(sorted(counts.items()))


def _revision_index(key: AnswerKey) -> dict[tuple[str, str], ClauseRevision]:
    """``(clause_key, revision_key) -> the clause revision``."""
    return {(row.clause_key, row.revision_key): row for row in key.walk.revisions}


def _by_clause(key: AnswerKey) -> dict[str, tuple[ClauseRevision, ...]]:
    return key.walk.by_clause()


def _site_of_revision_key(revision_key: str) -> str:
    return revision_key.split("/", 1)[0]


class _Binder:
    """Turns a ``(change request, clause)`` intention into a fully pinned row, or refuses."""

    def __init__(self, key: AnswerKey) -> None:
        self._key = key
        self._revisions = _revision_index(key)
        self._history = _by_clause(key)
        self._universe = key.universe
        self._retired = key.walk.retired

    def revision_for(self, clause_key: str, revision_key: str) -> ClauseRevision | None:
        """Return the clause revision at that document revision, or ``None`` if untouched."""
        return self._revisions.get((clause_key, revision_key))

    def _pin(self, clause_key: str, *, revision_hint: str | None, on: dt.date) -> ClauseRevision:
        """Return the clause version the declaration pins.

        The hint wins when the named revision really did touch this clause.  Otherwise the
        pinned version is the head at ``on`` — which is what "the version the change request
        declared it was editing" means, and what the ``(clause_uuid, commit_id)`` foreign key
        exists to nail down.
        """
        if revision_hint is not None:
            found = self._revisions.get((clause_key, revision_hint))
            if found is not None:
                return found
        history = self._history.get(clause_key)
        if not history:
            raise RuntimeError(
                f"clause {clause_key} has no revision in the walk; a clause with no version "
                "cannot be pinned and cr_clause's foreign key would have nothing to reference"
            )
        prior = [row for row in history if row.effective_on <= on]
        return prior[-1] if prior else history[0]

    def _relation(self, clause: Clause, revision: ClauseRevision, *, realised: bool) -> str:
        if not realised:
            # A proposal edits the version it names.  It has neither introduced nor retired
            # anything, because it has not landed — that is the whole point of the state it is in.
            return "edits"
        if revision.revision_key == clause.birth_revision_key:
            return "introduces"
        if self._retired.get(clause.clause_key) == revision.effective_on:
            return "retires"
        return "edits"

    def bind(
        self,
        cr: ChangeRequest,
        clause_key: str,
        *,
        basis: str,
        revision_hint: str | None,
        realised: bool,
    ) -> CrClause:
        clause = self._universe.by_key.get(clause_key)
        if clause is None:
            raise RuntimeError(
                f"{cr.external_ref} declares clause {clause_key}, which the clause universe does "
                "not contain; the corpus would emit a foreign key onto a row it never wrote"
            )
        if clause.site_code != cr.site_code:
            raise RuntimeError(
                f"{cr.external_ref} ({cr.site_code}) declares {clause_key} ({clause.site_code}); "
                "a change request at one site does not change another site's controlled document"
            )
        revision = self._pin(clause_key, revision_hint=revision_hint, on=cr.opened_at.date())
        relation = self._relation(clause, revision, realised=realised)
        return CrClause(
            cr_id=cr.cr_id,
            cr_external_ref=cr.external_ref,
            site_id=cr.site_id,
            site_code=cr.site_code,
            clause_uuid=clause.clause_uuid,
            clause_key=clause_key,
            relation=relation,
            basis=basis,
            realised=realised,
            commit_for_revision_key=revision.revision_key,
            effective_on=revision.effective_on if realised else None,
            control_delta=revision.control_delta if realised else None,
            setpoint_key=clause.setpoint_key,
            setpoint_from=revision.setpoint_from if realised else revision.setpoint_to,
            setpoint_to=revision.setpoint_to if realised else None,
            doc_code=self._universe.doc_code_at(clause_key, cr.opened_at.date()),
            driver=revision.driver if realised else None,
        )


def _authored_elsewhere(
    key: AnswerKey, binder: _Binder, by_ref: Mapping[str, ChangeRequest]
) -> list[CrClause]:
    """Bases R1-R4: every clause-to-change binding some other generator already wrote down."""
    out: list[CrClause] = []

    # R1 — stage 1 named the change record on the document revision itself.
    for revision in key.skeleton.documents.revisions:
        change_ref = revision.driving_change_ref
        if change_ref is None:
            continue
        cr = by_ref.get(change_ref)
        if cr is None:
            raise RuntimeError(
                f"revision {revision.revision_key} names change record {change_ref}, which is not "
                "in the register; stage 1 would have emitted a document change nobody approved"
            )
        touched = sorted(
            row.clause_key
            for row in key.walk.revisions
            if row.revision_key == revision.revision_key
        )
        for clause_key in touched:
            out.append(
                binder.bind(
                    cr,
                    clause_key,
                    basis="skeleton:driving_change_ref",
                    revision_hint=revision.revision_key,
                    realised=True,
                )
            )

    # R2 — each weakening step already names the MOC it hid behind.
    for chain in key.chains:
        for step in chain.steps:
            cr = by_ref.get(step.change_ref)
            if cr is None:
                raise RuntimeError(
                    f"weakening {chain.chain_id} step {step.step_index} names {step.change_ref}, "
                    "which is not in the register"
                )
            out.append(
                binder.bind(
                    cr,
                    chain.clause_key,
                    basis="injector:weakening_chain",
                    revision_hint=step.revision_key,
                    realised=True,
                )
            )

    # R3 — every migrating clause already names the change record that split its document.
    for plan_item, clause_key, _from_label, _to_label in key.walk.migration_entries:
        cr = by_ref.get(plan_item.change_ref)
        if cr is None:
            raise RuntimeError(
                f"split {plan_item.key} names {plan_item.change_ref}, which is not in the register"
            )
        out.append(
            binder.bind(
                cr,
                clause_key,
                basis="injector:document_split",
                revision_hint=plan_item.source_revision_key,
                realised=True,
            )
        )

    # R4 — the 2026 proposal that never merged.  This is the film's refusal, and its declared
    # scope is what `open_blocking` counts.
    for proposal in key.proposed:
        cr = by_ref.get(proposal.cr_external_ref)
        if cr is None:
            raise RuntimeError(
                f"proposed revision names {proposal.cr_external_ref}, which is not in the register"
            )
        out.append(
            binder.bind(
                cr,
                proposal.clause_key,
                basis="blame:proposed_revision",
                revision_hint=None,
                realised=False,
            )
        )
    return out


def _candidate_realised_revisions(
    key: AnswerKey, cr: ChangeRequest, used: Mapping[str, int]
) -> list[tuple[int, dt.date, str]]:
    """Reissues this change request could plausibly have been one of the vehicles for.

    Returned as ``(vehicles already claiming it, effective date, revision key)`` so the caller
    can take the least-loaded, earliest reissue: a change approved in March is implemented at the
    next reissue, not the one after it, and spreading across reissues keeps the register from
    piling every change onto the first document that happens to sort first.
    """
    opened = cr.opened_at.date()
    horizon = opened + dt.timedelta(days=params.SCOPE_WINDOW_DAYS)
    doc_codes = set(cr.doc_codes)
    out: list[tuple[int, dt.date, str]] = []
    for revision in key.skeleton.documents.revisions:
        if revision.doc_code not in doc_codes:
            continue
        if _site_of_revision_key(revision.revision_key) != cr.site_code:
            continue
        if revision.rev_no == 1:
            # A document's first issue is not a change to a controlled document; it is the
            # document coming into existence. Nothing approved it through a change register,
            # because there was nothing yet to change.
            continue
        if revision.driver not in params.ADMISSIBLE_R5_DRIVERS:
            continue
        if not opened <= revision.effective_on <= horizon:
            continue
        claimed = used.get(revision.revision_key, 0)
        if claimed >= params.MAX_VEHICLES_PER_REVISION:
            continue
        out.append((claimed, revision.effective_on, revision.revision_key))
    out.sort()
    return out


def _draw_count(stream: rng.Stream, available: int) -> int:
    sizes = sorted(params.SCOPE_SIZE_WEIGHTS)
    weights = [params.SCOPE_SIZE_WEIGHTS[size] for size in sizes]
    wanted = rng.weighted(stream, sizes, weights)
    return max(1, min(wanted, available))


def _authored_here(
    key: AnswerKey,
    binder: _Binder,
    change_requests: Sequence[ChangeRequest],
    already_scoped: Mapping[str, bool],
) -> tuple[list[CrClause], list[str]]:
    """Basis R5, for the change requests the other four bases left silent."""
    out: list[CrClause] = []
    unscoped: list[str] = []
    #: ``revision_key -> how many change requests already claim it``, capped by
    #: ``params.MAX_VEHICLES_PER_REVISION``.  A reissue consolidates several approved changes;
    #: an unbounded count would let one revision absorb the entire register.
    used_revisions: dict[str, int] = {}

    for cr in sorted(change_requests, key=lambda item: item.external_ref):
        if already_scoped.get(cr.external_ref, False):
            continue
        stream = rng.sub_stream("moc_stream.scope", cr.external_ref)

        if cr.state in params.REALISED_TERMINAL_STATES:
            candidates = _candidate_realised_revisions(key, cr, used_revisions)
            if not candidates:
                unscoped.append(cr.external_ref)
                continue
            revision_key = candidates[0][2]
            used_revisions[revision_key] = used_revisions.get(revision_key, 0) + 1
            # An injector-produced clause revision already has its change record named by the
            # injector that produced it — the weakening chain names three MOCs, the split names
            # the change that cut the document. A second, drawn vehicle for the same edit would
            # contest a story the corpus tells elsewhere, and the weaker basis would win nothing.
            touched = sorted(
                row.clause_key
                for row in key.walk.revisions
                if row.revision_key == revision_key and row.injector is None
            )
            if not touched:
                unscoped.append(cr.external_ref)
                continue
            count = _draw_count(stream, len(touched))
            for clause_key in sorted(rng.sample_without_replacement(stream, touched, count)):
                out.append(
                    binder.bind(
                        cr,
                        clause_key,
                        basis="moc_stream:window",
                        revision_hint=revision_key,
                        realised=True,
                    )
                )
            continue

        if cr.state not in params.PROPOSAL_TERMINAL_STATES:
            raise RuntimeError(
                f"{cr.external_ref} is in state {cr.state!r}, which is in neither "
                "REALISED_TERMINAL_STATES nor PROPOSAL_TERMINAL_STATES; scope has no rule for it"
            )

        # A change request that never landed still declares what it wanted to change, and that
        # declaration is precisely what the gate reads before refusing it.
        pools: list[tuple[str, ...]] = []
        for doc_code in sorted(cr.doc_codes):
            members = key.universe.members_at(cr.site_code, doc_code, cr.opened_at.date())
            live = tuple(sorted(clause.clause_key for clause in members))
            if live:
                pools.append(live)
        if not pools:
            unscoped.append(cr.external_ref)
            continue
        pool = rng.pick(stream, pools)
        count = _draw_count(stream, len(pool))
        for clause_key in sorted(rng.sample_without_replacement(stream, list(pool), count)):
            out.append(
                binder.bind(
                    cr,
                    clause_key,
                    basis="moc_stream:window",
                    revision_hint=None,
                    realised=False,
                )
            )
    return out, unscoped


def _dedupe(rows: Sequence[CrClause]) -> list[CrClause]:
    """One row per ``(cr_id, clause_uuid, relation)`` — the primary key of ``cr_clause``.

    Two bases proposing the same declaration is not a conflict, it is corroboration; the higher
    priority wins so the registry records the strongest available provenance for the binding.
    """
    rank = {basis: index for index, basis in enumerate(_BASIS_PRIORITY)}
    best: dict[tuple[str, str, str], CrClause] = {}
    for row in rows:
        pk = (row.cr_id, row.clause_uuid, row.relation)
        incumbent = best.get(pk)
        if incumbent is None or rank[row.basis] < rank[incumbent.basis]:
            best[pk] = row
    return [best[pk] for pk in sorted(best)]


def build_scope(key: AnswerKey) -> ScopeResult:
    """Bind every change request to the clauses it declares it changes."""
    change_requests = key.skeleton.mocs.change_requests
    by_ref = {cr.external_ref: cr for cr in change_requests}
    binder = _Binder(key)

    authored_elsewhere = _authored_elsewhere(key, binder, by_ref)
    scoped = {row.cr_external_ref: True for row in authored_elsewhere}
    authored_here, unscoped = _authored_here(key, binder, change_requests, scoped)

    rows = _dedupe([*authored_elsewhere, *authored_here])

    # The spine's refusal must be legible: exactly one declared clause, so `open_blocking = 1` on
    # camera is a number a viewer can hold in their head rather than a coincidence of a draw.
    spine_ref = next(
        (item.cr_external_ref for item in key.proposed),
        None,
    )
    if spine_ref is not None:
        declared = [row for row in rows if row.cr_external_ref == spine_ref]
        if len(declared) != 1:
            raise RuntimeError(
                f"{spine_ref} declares {len(declared)} clauses; the beat that shows a single "
                "blocking obligation needs exactly one, and R5 must not have run for it"
            )
        if declared[0].realised:
            raise RuntimeError(
                f"{spine_ref} declares a realised clause change; the whole beat is that this "
                "change did NOT land, and a realised scope row would make the refusal a lie"
            )
    return ScopeResult(rows, sorted(unscoped))
