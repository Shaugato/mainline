# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""The change request's lifecycle, as a PLAN OF ACTS — deliberately not as a chain of events.

``mainline.cr_event`` is a compare-and-swap chain: ``UNIQUE (cr_id, prev_seq)`` makes a forked
history impossible, ``chain_digest`` is a ``STORED`` generated column the server computes, and
``mainline.fn_cr_event_chain`` (migration 0106) refuses any row whose ``prev_digest`` is not
byte-equal to the stored predecessor's ``chain_digest``.

That means a corpus **cannot** author this table, and the reason is worth stating plainly because
the temptation to try is real.  ``chain_digest`` is
``digest(prev_digest || payload::STRING::BYTES, 'sha256')`` — over *CockroachDB's* rendering of
JSONB, not Python's.  To emit a loadable chain we would have to reimplement that normaliser and
then stake the corpus's reproducibility on our copy never diverging from the server's.  A near
miss is refused; an exact hit is worse, because it would mean the digest chain no longer proves
that the server saw the payload it hashed.

Migration 0118 step 3 shows the shipped answer: ``mainline.merge_change_request`` **reads** the
predecessor's ``chain_digest`` out of the table rather than accepting one.  So this stage emits
an ordered plan — one row per act, with the actor, the instant, the edge and the surface to
execute it through — and the loader performs the acts so the chain is minted where it can only
honestly be minted.  ``seq``, ``prev_seq`` and ``prev_digest`` are registered pending against the
database itself, which is the only correct owner.

── WHAT THE PLAN IS ALLOWED TO CONTAIN ──────────────────────────────────────────────────────────
Every edge is drawn from ``params.TERMINAL_TRANSITIONS`` and re-checked against the seeded edge
set in migration ``0017b_subject_transition_seed.sql`` by ``verify.parse_legal_edges`` — the
table is the authority, not this file.  Two optional detours exist because they are the ordinary
form of the product's own mechanism:

``checks_materialised -> checks_materialised``
    a further precursor arrived while the gate was open; ``gate_epoch`` bumps.
``dispositioned -> checks_materialised``
    a precursor arrived *after* disposition; the gate re-opens.  This is the shape of the M8
    beat, occurring here in its unremarkable, everyday form so that the beat is a instance of a
    mechanism rather than a special case built for a camera.

── SEGREGATION OF DUTIES ────────────────────────────────────────────────────────────────────────
The person who opens a change request is never the person who disposes of it or merges it, and
every actor is employed at that site on that date.  A corpus whose author and approver are the
same signer would make every countersignature exhibit meaningless.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Sequence

from .. import rng
from ..blame.build import AnswerKey
from ..skeleton import clock
from ..skeleton.model import ChangeRequest, Person
from . import params
from .model import CrTransition
from .scope import ScopeResult

__all__ = ["LifecycleResult", "build_lifecycle"]

#: The surface each edge must be performed through.  The merge is a procedure call because the
#: gate, the clearance digest and the epoch pin all live inside it; everything else extends the
#: chain directly and lets the projection triggers do their work.
_EXECUTE_VIA: dict[tuple[str, str], str] = {
    ("dispositioned", "merged"): "mainline.merge_change_request",
}
_DEFAULT_EXECUTE_VIA = "mainline.cr_event"

#: ``merged_commit`` is ``BYTES NOT NULL`` on any merged change request
#: (``cr_merge_evidence``), and nothing in the corpus lane mints commits.  The merge act is
#: therefore blocked until the commit DAG exists — stated on the row rather than papered over,
#: because a merged change request with no merge evidence is exactly what the database should
#: refuse.
_MERGE_BLOCKERS: tuple[str, ...] = ("mainline.change_request.merged_commit",)

#: Rank floors, mirroring ``PeopleWorld.authors_at``: rank 2 and above may reissue a
#: controlled procedure, and an approver is drawn from rank 3 and above when the site has
#: one. A tradesperson neither reissues a procedure nor countersigns its merge.
_AUTHOR_RANK = 2
_APPROVER_RANK = 3


class LifecycleResult:
    """Every planned act, indexed by change request."""

    __slots__ = ("_by_cr", "transitions")

    def __init__(self, transitions: Sequence[CrTransition]) -> None:
        self.transitions = tuple(transitions)
        by_cr: dict[str, list[CrTransition]] = {}
        for item in self.transitions:
            by_cr.setdefault(item.cr_external_ref, []).append(item)
        self._by_cr = {
            ref: tuple(sorted(items, key=lambda entry: entry.step)) for ref, items in by_cr.items()
        }

    def for_cr(self, external_ref: str) -> tuple[CrTransition, ...]:
        return self._by_cr.get(external_ref, ())

    def edge_histogram(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for item in self.transitions:
            label = f"{item.from_state}->{item.to_state}"
            counts[label] = counts.get(label, 0) + 1
        return dict(sorted(counts.items()))


def _plan_edges(cr: ChangeRequest, stream: rng.Stream) -> list[tuple[str, str]]:
    """Return the ordered edges this change request walks, detours included."""
    base = params.TERMINAL_TRANSITIONS.get(cr.state)
    if base is None:
        raise RuntimeError(
            f"{cr.external_ref}: no transition path to terminal state {cr.state!r}. Either the "
            "register grew a state or subject_transition did; neither may be guessed here"
        )
    edges = list(base)
    if len(edges) == 1:
        # draft -> abandoned. A subject that skipped the gate has no gate to re-open.
        return edges

    # A re-materialisation happens while the gate is open, i.e. immediately after the first
    # `draft -> checks_materialised`.
    if rng.unit(stream) < params.EPOCH_BUMP_PROBABILITY:
        edges.insert(1, ("checks_materialised", "checks_materialised"))

    # A re-open happens after a disposition, so it is inserted after the FIRST arrival at
    # `dispositioned` and is followed by a fresh materialisation and a fresh disposition.
    if rng.unit(stream) < params.REOPEN_PROBABILITY:
        first_disposition = next(
            index for index, edge in enumerate(edges) if edge[1] == "dispositioned"
        )
        edges[first_disposition + 1 : first_disposition + 1] = [
            ("dispositioned", "checks_materialised"),
            ("checks_materialised", "dispositioned"),
        ]
    return edges


def _lags(edges: Sequence[tuple[str, str]], stream: rng.Stream) -> list[float]:
    out: list[float] = []
    for edge in edges:
        window = params.STEP_LAG_DAYS.get(edge)
        if window is None:
            raise RuntimeError(f"no lag window declared for the edge {edge[0]} -> {edge[1]}")
        low, high = window
        out.append(low + rng.unit(stream) * (high - low))
    return out


def _moments(cr: ChangeRequest, lags: Sequence[float]) -> list[dt.datetime]:
    """Strictly increasing instants from ``opened_at``, compressed to fit inside ``NOW``.

    Compression rather than truncation: a change request opened three weeks before the corpus
    ends still has to reach its terminal state, because stage 1 already recorded that it did.
    Dropping the tail would leave a ``merged`` row whose plan never merges, which is a
    contradiction inside our own fixtures.
    """
    total = sum(lags)
    if total <= 0.0:
        raise RuntimeError(f"{cr.external_ref}: a lifecycle with no elapsed time is not a history")
    available = clock.days_between(cr.opened_at, clock.NOW)
    if available <= 0.0:
        raise RuntimeError(
            f"{cr.external_ref} opened at {clock.iso(cr.opened_at)}, at or after the corpus's "
            "NOW; stage 1 must not place a change request in the future"
        )
    # One second per act is the floor, so the chain stays strictly increasing after compression.
    floor_days = len(lags) / clock.SECONDS_PER_DAY
    scale = 1.0 if total <= available else max(available * 0.98, floor_days) / total

    out: list[dt.datetime] = []
    cursor = cr.opened_at
    for lag in lags:
        step = dt.timedelta(seconds=max(1, round(lag * scale * clock.SECONDS_PER_DAY)))
        cursor = cursor + step
        out.append(cursor)
    if out[-1] > clock.NOW:
        raise RuntimeError(
            f"{cr.external_ref}: the compressed plan still ends at {clock.iso(out[-1])}, after "
            f"{clock.iso(clock.NOW)}; the corpus would contain an act that has not happened"
        )
    return out


def _pick_actor(
    key: AnswerKey,
    cr: ChangeRequest,
    moment: dt.datetime,
    *,
    exclude: frozenset[str],
    stream: rng.Stream,
) -> Person:
    """Somebody employed at that site on that date, preferring seniority and never ``exclude``.

    The fallbacks widen in one direction only — first drop the exclusion, then drop the
    employed-at-the-time filter — and each widening is a smaller claim than the one before, so a
    thin site never produces an actor who was not at the site at all.
    """
    people = key.skeleton.people
    employed = people.authors_at(cr.site_code, moment)
    candidates = tuple(person for person in employed if person.signer_sub not in exclude)
    if not candidates:
        candidates = employed
    if not candidates:
        candidates = tuple(
            person for person in people.at(cr.site_code) if person.rank >= _AUTHOR_RANK
        )
    if not candidates:
        raise RuntimeError(
            f"{cr.external_ref}: nobody at {cr.site_code} could have acted on "
            f"{clock.iso(moment)}; an act with no actor is not an act"
        )
    senior = tuple(person for person in candidates if person.rank >= _APPROVER_RANK)
    return rng.pick(stream, senior if senior else candidates)


def _payload(
    cr: ChangeRequest, edge: tuple[str, str], step: int, scope: ScopeResult
) -> dict[str, object]:
    """Return the act's structural payload.

    Keys only, never prose.  Every sentence a human reads in this corpus is hand-authored once
    under ``fixtures/corpus/authored/`` and checked byte-equal across four files; a fifth copy
    living inside a JSONB payload would be a fifth thing that can drift.
    """
    return {
        "declared_clause_count": len(scope.for_cr(cr.external_ref)),
        "external_ref": cr.external_ref,
        "from_state": edge[0],
        "intent": cr.intent,
        "ref_name": cr.ref_name,
        "step": step,
        "subject_kind": "change_request",
        "target_ref": cr.target_ref,
        "to_state": edge[1],
    }


def _role_for(edge: tuple[str, str]) -> str:
    if edge[1] == "abandoned":
        return "originator"
    if edge[0] == "draft":
        return "originator"
    if edge[1] == "merged":
        return "merge_authority"
    if edge[1] == "dispositioned":
        return "disposer"
    if edge[1] == "closed":
        return "closer"
    return "materialiser"


def build_lifecycle(key: AnswerKey, scope: ScopeResult) -> LifecycleResult:
    """Plan every change request's acts, in order, with actors and instants."""
    transitions: list[CrTransition] = []
    for cr in sorted(key.skeleton.mocs.change_requests, key=lambda item: item.external_ref):
        plan_stream = rng.sub_stream("moc_stream.lifecycle", cr.external_ref)
        actor_stream = rng.sub_stream("moc_stream.actor", cr.external_ref)
        edges = _plan_edges(cr, plan_stream)
        moments = _moments(cr, _lags(edges, plan_stream))

        excluded = {cr.author_sub}
        for step, (edge, moment) in enumerate(zip(edges, moments, strict=True), start=1):
            role = _role_for(edge)
            if role == "originator":
                actor = key.skeleton.people.get(cr.author_sub)
            else:
                actor = _pick_actor(
                    key, cr, moment, exclude=frozenset(excluded), stream=actor_stream
                )
                excluded.add(actor.signer_sub)
            transitions.append(
                CrTransition(
                    cr_id=cr.cr_id,
                    cr_external_ref=cr.external_ref,
                    site_id=cr.site_id,
                    site_code=cr.site_code,
                    step=step,
                    from_state=edge[0],
                    to_state=edge[1],
                    at=moment,
                    actor_sub=actor.signer_sub,
                    actor_role=role,
                    payload=_payload(cr, edge, step, scope),
                    execute_via=_EXECUTE_VIA.get(edge, _DEFAULT_EXECUTE_VIA),
                    blocked_by=_MERGE_BLOCKERS if edge[1] == "merged" else (),
                )
            )
    return LifecycleResult(transitions)
