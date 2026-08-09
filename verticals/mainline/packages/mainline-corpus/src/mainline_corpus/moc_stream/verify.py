# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""Stage 1c's own falsification pass.

Every check here is one the database would eventually run — a CHECK constraint, a foreign key, a
trigger, or a state machine encoded as a foreign-key target.  Running them in the generator does
not make the database's version redundant; it makes the diagnosis cheap.  A ``cr_clause`` row
with an unknown relation should be a named refusal from a generator that can point at the change
request, not a ``23514`` three workers downstream with a constraint name and no context.

Two disciplines are borrowed deliberately:

**SKIP is reported as loudly as FAIL.** ``parse_legal_edges`` reads the seeded edge set out of
``0017b_subject_transition_seed.sql`` — the authority for what transitions exist. On a checkout
without the migration tree it cannot, and it says so; it never degrades to "assume the edges in
``params`` are right", because the entire value of the check is that ``params`` might be wrong.

**Ratios, never totals** (decision D10). Coverage is asserted inside a band. A corpus tweak that
moves the number by three must not turn CI red, because a founder who learns to ignore red CI has
lost the only alarm they have.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from itertools import pairwise
from pathlib import Path

from ..blame.build import AnswerKey
from ..skeleton import clock
from . import params
from .lifecycle import LifecycleResult
from .model import SCOPE_RELATIONS, CrTransition, MocDossier
from .scope import ScopeResult

__all__ = ["Check", "VerifyReport", "parse_legal_edges", "run_checks"]

#: The loadable shape of one ``mainline.cr_clause`` row.  Asserted as an exact set: a column that
#: appeared here without anyone noticing would be a column the loader hands to the database.
_CR_CLAUSE_COLUMNS: frozenset[str] = frozenset({"clause_uuid", "commit_id", "cr_id", "relation"})

#: Fraction of the register that may end up with no declared scope.
#:
#: The floor is not zero and should not be: a great many approved changes alter plant, a drawing
#: or a setting and never touch a controlled clause, and a corpus in which every register entry
#: edits a procedure would be a corpus nobody in the industry recognises. The ceiling is what
#: stops the opposite failure — a register that declares almost nothing leaves ``open_blocking``
#: with nothing to count and the change-request half of the gate untested.
#:
#: Set with real headroom above the observed value on purpose (decision D10): an assertion that
#: sits two points from its bound turns red on an unrelated tweak, and a founder who learns to
#: ignore red CI has lost the only alarm they have.
_MAX_UNSCOPED_FRACTION = 0.45

#: Fraction of acts that may be performed by the change request's own originator, where a thin
#: site left nobody else employed on that date. Above this, segregation of duties is decorative.
_MAX_SEGREGATION_EXCEPTION_FRACTION = 0.02

#: Revision drivers an authored binding may NEVER claim, stated here as a literal rather than as
#: the complement of ``params.ADMISSIBLE_R5_DRIVERS``.
#:
#: ``incident`` — the blame lane authored the causal story of those edits, and re-attributing one
#: to a change record would contradict our own answer key.
#: ``retypeset`` — the 2016 reflow was one project, not three hundred approved changes.
#: ``introduce`` — a document's first issue predates any register that could have approved it.
_BLAME_OWNED_DRIVERS: frozenset[str] = frozenset({"incident", "introduce", "retypeset"})

_SEED_ROW = re.compile(
    r"\(\s*'(?P<kind>[a-z_]+)'\s*,\s*'(?P<from>[a-z_]+)'\s*,\s*'(?P<to>[a-z_]+)'\s*\)"
)


@dataclass(frozen=True, slots=True)
class Check:
    """One assertion and its outcome.  ``SKIP`` always carries a reason."""

    check_id: str
    status: str  # PASS | FAIL | SKIP
    detail: str

    def __post_init__(self) -> None:
        if self.status not in {"PASS", "FAIL", "SKIP"}:
            raise ValueError(f"{self.check_id}: unknown status {self.status!r}")
        if self.status == "SKIP" and not self.detail:
            raise ValueError(
                f"{self.check_id}: a SKIP with no reason is indistinguishable from a PASS"
            )


@dataclass(frozen=True, slots=True)
class VerifyReport:
    checks: tuple[Check, ...]

    @property
    def failed(self) -> tuple[Check, ...]:
        return tuple(check for check in self.checks if check.status == "FAIL")

    @property
    def skipped(self) -> tuple[Check, ...]:
        return tuple(check for check in self.checks if check.status == "SKIP")

    def summary(self) -> dict[str, int]:
        counts = {"FAIL": 0, "PASS": 0, "SKIP": 0}
        for check in self.checks:
            counts[check.status] += 1
        return counts

    def raise_on_failure(self) -> None:
        if not self.failed:
            return
        first = self.failed[0]
        raise RuntimeError(
            f"stage 1c refused its own output: {first.check_id} — {first.detail} "
            f"({len(self.failed)} failing check(s) in total)"
        )


def parse_legal_edges(repo_root: Path | None) -> frozenset[tuple[str, str]] | None:
    """Return the ``change_request`` edges seeded into ``mainline.subject_transition``.

    ``None`` means the migration could not be read, which is reported as ``SKIP``. The table is
    the authority for the state machine; this function never falls back to a copy.
    """
    if repo_root is None:
        return None
    candidate = (
        Path(repo_root)
        / "verticals"
        / "mainline"
        / "db"
        / "migrations"
        / "0017b_subject_transition_seed.sql"
    )
    if not candidate.is_file():
        return None
    try:
        text = candidate.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None
    edges = {
        (match.group("from"), match.group("to"))
        for match in _SEED_ROW.finditer(text)
        if match.group("kind") == "change_request"
    }
    return frozenset(edges) or None


def _check_scope_shape(scope: ScopeResult, key: AnswerKey) -> list[Check]:
    out: list[Check] = []
    known_clause_uuids = {clause.clause_uuid for clause in key.universe.clauses}
    known_cr_ids = {cr.cr_id for cr in key.skeleton.mocs.change_requests}

    bad_relation = [row.key for row in scope.rows if row.relation not in SCOPE_RELATIONS]
    out.append(
        Check(
            "MS-01",
            "FAIL" if bad_relation else "PASS",
            (
                f"cr_clause_relation_known: {bad_relation[:3]}"
                if bad_relation
                else f"every relation of {len(scope.rows)} rows is in {sorted(SCOPE_RELATIONS)}"
            ),
        )
    )

    primary_keys = [(row.cr_id, row.clause_uuid, row.relation) for row in scope.rows]
    duplicates = len(primary_keys) - len(set(primary_keys))
    out.append(
        Check(
            "MS-02",
            "FAIL" if duplicates else "PASS",
            (
                f"pk_cr_clause: {duplicates} duplicate (cr_id, clause_uuid, relation) tuple(s)"
                if duplicates
                else "every (cr_id, clause_uuid, relation) is unique"
            ),
        )
    )

    dangling = [
        row.key
        for row in scope.rows
        if row.clause_uuid not in known_clause_uuids or row.cr_id not in known_cr_ids
    ]
    out.append(
        Check(
            "MS-03",
            "FAIL" if dangling else "PASS",
            (
                f"fk_cr_clause_subject / fk_cr_clause_version would dangle: {dangling[:3]}"
                if dangling
                else "every declared row references a change request and a clause the corpus wrote"
            ),
        )
    )

    shape_errors = [row.key for row in scope.rows if set(row.to_row()) != _CR_CLAUSE_COLUMNS]
    out.append(
        Check(
            "MS-04",
            "FAIL" if shape_errors else "PASS",
            (
                f"emitted cr_clause row carries unexpected columns: {shape_errors[:3]}"
                if shape_errors
                else f"every emitted row carries exactly {sorted(_CR_CLAUSE_COLUMNS)}"
            ),
        )
    )

    no_commit = [row.key for row in scope.rows if row.to_row()["commit_id"] is not None]
    out.append(
        Check(
            "MS-05",
            "FAIL" if no_commit else "PASS",
            (
                f"commit_id was invented on {len(no_commit)} row(s): {no_commit[:3]}"
                if no_commit
                else "commit_id is null on every row and registered pending; nothing "
                "invented thirty-two bytes"
            ),
        )
    )
    return out


def _check_coverage(scope: ScopeResult, dossiers: Sequence[MocDossier]) -> list[Check]:
    total = len(dossiers)
    silent = tuple(item for item in dossiers if item.clause_count == 0)
    fraction = len(silent) / total if total else 1.0

    # A change request that never landed still declares what it WANTED to change — that
    # declaration is exactly what the gate reads before refusing it. So a silent proposal is not
    # a thin corpus, it is a contradiction, and it is asserted exactly rather than in a band.
    silent_proposals = sorted(
        item.external_ref
        for item in silent
        if item.terminal_state in params.PROPOSAL_TERMINAL_STATES
    )
    return [
        Check(
            "MS-06",
            "FAIL" if fraction > _MAX_UNSCOPED_FRACTION else "PASS",
            (
                f"{len(silent)}/{total} change requests declare no scope "
                f"({fraction:.2%}, ceiling {_MAX_UNSCOPED_FRACTION:.0%}); "
                f"{len(scope.rows)} declared clause rows in total"
            ),
        ),
        Check(
            "MS-14",
            "FAIL" if silent_proposals else "PASS",
            (
                f"a change request in a pre-merge state declares nothing: {silent_proposals[:3]}"
                if silent_proposals
                else "every change request still short of a merge declares what it wants to "
                "change, so the gate always has something to read"
            ),
        ),
    ]


def _check_edges(lifecycle: LifecycleResult, legal: frozenset[tuple[str, str]] | None) -> Check:
    """Check every planned edge against the seeded ``subject_transition`` rows."""
    if legal is None:
        return Check(
            "MS-07",
            "SKIP",
            "0017b_subject_transition_seed.sql was not readable from the given --repo-root, so "
            "the planned edges could not be checked against the table that is the authority "
            "for them. Re-run with --repo-root pointed at the repository.",
        )
    illegal = sorted(
        {
            f"{item.from_state}->{item.to_state}"
            for item in lifecycle.transitions
            if item.edge not in legal
        }
    )
    return Check(
        "MS-07",
        "FAIL" if illegal else "PASS",
        (
            f"cr_legal_edge would refuse: {illegal}"
            if illegal
            else f"every planned edge is one of the {len(legal)} seeded change_request edges"
        ),
    )


def _check_chain(key: AnswerKey, lifecycle: LifecycleResult) -> Check:
    """Check that each plan is one contiguous, strictly increasing walk to its terminal state."""
    broken: list[str] = []
    for cr in key.skeleton.mocs.change_requests:
        acts = lifecycle.for_cr(cr.external_ref)
        if not acts:
            broken.append(f"{cr.external_ref}: no plan")
            continue
        if acts[0].from_state != "draft":
            broken.append(f"{cr.external_ref}: starts at {acts[0].from_state}")
        if acts[-1].to_state != cr.state:
            broken.append(
                f"{cr.external_ref}: ends at {acts[-1].to_state}, register says {cr.state}"
            )
        broken.extend(_broken_steps(cr.external_ref, acts))
    return Check(
        "MS-08",
        "FAIL" if broken else "PASS",
        (
            f"the plan is not a chain: {broken[:3]}"
            if broken
            else f"{len(lifecycle.transitions)} acts form one contiguous, strictly increasing "
            "chain per change request, ending in the register's terminal state"
        ),
    )


def _broken_steps(external_ref: str, acts: Sequence[CrTransition]) -> list[str]:
    """Report every successive pair that forks the history or fails to advance the clock."""
    out: list[str] = []
    for previous, following in pairwise(acts):
        if following.from_state != previous.to_state:
            out.append(
                f"{external_ref}: step {following.step} extends {following.from_state} "
                f"after {previous.to_state}"
            )
        if following.at <= previous.at:
            out.append(f"{external_ref}: step {following.step} does not advance the clock")
    return out


def _check_lifecycle(
    key: AnswerKey, lifecycle: LifecycleResult, legal: frozenset[tuple[str, str]] | None
) -> list[Check]:
    out: list[Check] = [
        _check_edges(lifecycle, legal),
        _check_chain(key, lifecycle),
    ]

    future = [item.key for item in lifecycle.transitions if item.at > clock.NOW]
    out.append(
        Check(
            "MS-09",
            "FAIL" if future else "PASS",
            (
                f"{len(future)} act(s) are planned after the corpus's NOW: {future[:3]}"
                if future
                else f"every act falls at or before {clock.iso(clock.NOW)}"
            ),
        )
    )

    unblocked_merges = [
        item.key
        for item in lifecycle.transitions
        if item.to_state == "merged" and not item.blocked_by
    ]
    wrong_surface = [
        item.key
        for item in lifecycle.transitions
        if item.to_state == "merged" and item.execute_via != "mainline.merge_change_request"
    ]
    problem = unblocked_merges + wrong_surface
    out.append(
        Check(
            "MS-10",
            "FAIL" if problem else "PASS",
            (
                f"a merge act is unblocked or bypasses the procedure: {problem[:3]}"
                if problem
                else "every merge act names mainline.merge_change_request and records that "
                "merged_commit does not exist yet"
            ),
        )
    )

    originator_acts = 0
    exceptions = 0
    for cr in key.skeleton.mocs.change_requests:
        for act in lifecycle.for_cr(cr.external_ref):
            if act.actor_role == "originator":
                originator_acts += 1
                continue
            if act.actor_sub == cr.author_sub:
                exceptions += 1
    reviewed = max(1, len(lifecycle.transitions) - originator_acts)
    ratio = exceptions / reviewed
    out.append(
        Check(
            "MS-11",
            "FAIL" if ratio > _MAX_SEGREGATION_EXCEPTION_FRACTION else "PASS",
            (
                f"{exceptions}/{reviewed} reviewing acts were performed by the originator "
                f"({ratio:.2%}, ceiling {_MAX_SEGREGATION_EXCEPTION_FRACTION:.0%})"
            ),
        )
    )
    return out


def _check_spine(key: AnswerKey, scope: ScopeResult, lifecycle: LifecycleResult) -> list[Check]:
    refs = sorted({item.cr_external_ref for item in key.proposed})
    if not refs:
        return [
            Check(
                "MS-12",
                "SKIP",
                "the answer key holds no proposed revision, so there is no 2026 weakening whose "
                "declared scope could be checked. corpus-blame-key emits it; re-run that stage.",
            )
        ]
    ref = refs[0]
    declared = scope.for_cr(ref)
    acts = lifecycle.for_cr(ref)
    problems: list[str] = []
    if len(declared) != 1:
        problems.append(f"{ref} declares {len(declared)} clauses, not 1")
    elif declared[0].realised:
        problems.append(f"{ref} declares a realised change; the beat is that it did not land")
    if any(act.to_state == "merged" for act in acts):
        problems.append(f"{ref} plans a merge; the database refusing that merge is the beat")
    if acts and acts[-1].to_state != "dispositioned":
        problems.append(f"{ref} ends at {acts[-1].to_state}, not dispositioned")
    return [
        Check(
            "MS-12",
            "FAIL" if problems else "PASS",
            (
                "; ".join(problems)
                if problems
                else f"{ref} declares exactly one unrealised clause and its plan stops at "
                "dispositioned, so the merge is the database's to refuse"
            ),
        )
    ]


def _check_drivers(key: AnswerKey, scope: ScopeResult) -> list[Check]:
    """No authored binding may claim a revision the blame lane owns.

    Both halves are stated INDEPENDENTLY of ``params.ADMISSIBLE_R5_DRIVERS``, and that is the
    whole point. A check that compared the emitted rows against the same knob the generator drew
    from would move whenever the knob moved: widening the knob would widen the check, and the
    tautology would report ``PASS`` while the corpus re-attributed causation.

    The first half names the excluded document-revision drivers literally. The second does not
    look at drivers at all: it asks the walk whether the pinned clause revision was produced by
    an injector, because an injector-produced edit already has its change record named by the
    injector, and a drawn second vehicle would contest a story the corpus tells elsewhere.

    Note what is deliberately NOT asserted: that a declared clause revision carries no blame
    edge. An incident causes a change, the change goes through the register, and the register
    entry is the vehicle that carries it to the document — both facts are true at once, and a
    corpus that forbade the overlap would be modelling a change-management system nobody runs.
    """
    offenders = sorted(
        row.key
        for row in scope.rows
        if row.basis == "moc_stream:window"
        and row.driver is not None
        and row.driver in _BLAME_OWNED_DRIVERS
    )
    injected = {
        (revision.clause_key, revision.revision_key)
        for revision in key.walk.revisions
        if revision.injector is not None
    }
    # Only a REALISED binding claims a revision. An unrealised one pins the version it declares
    # it is editing, and the provenance of the version it read is nobody's claim but the walk's.
    contested = sorted(
        row.key
        for row in scope.rows
        if row.basis == "moc_stream:window"
        and row.realised
        and (row.clause_key, row.commit_for_revision_key) in injected
    )
    problems = offenders + contested
    return [
        Check(
            "MS-13",
            "FAIL" if problems else "PASS",
            (
                f"an authored binding claimed an edit another generator owns: drivers "
                f"{offenders[:3]}, injector-produced {contested[:3]}"
                if problems
                else f"no authored binding sits on a {sorted(_BLAME_OWNED_DRIVERS)} revision or "
                f"on an injector-produced edit, across {len(scope.rows)} declarations"
            ),
        )
    ]


def run_checks(
    key: AnswerKey,
    scope: ScopeResult,
    lifecycle: LifecycleResult,
    dossiers: Sequence[MocDossier],
    *,
    repo_root: Path | None = None,
) -> VerifyReport:
    """Run every stage-1c check and return the report."""
    legal = parse_legal_edges(repo_root)
    checks = [
        *_check_scope_shape(scope, key),
        *_check_coverage(scope, dossiers),
        *_check_lifecycle(key, lifecycle, legal),
        *_check_spine(key, scope, lifecycle),
        *_check_drivers(key, scope),
    ]
    return VerifyReport(tuple(sorted(checks, key=lambda item: item.check_id)))
