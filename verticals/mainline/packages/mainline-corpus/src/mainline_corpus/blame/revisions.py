# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""Walk the whole revision cadence once, in date order, and emit what each revision touched.

The walk is **global and chronological**, not per document, and that is the only design decision
in this module worth arguing about.  Two things depend on it:

* a setpoint's value is a running state — 150 in 2011, 135 in 2013, and whatever three MOCs make
  of it by 2024 — so a clause's revisions must be produced in the order they happened, and a
  per-document walk would produce the ``STD-ISO-006`` half of the spine's life before the
  ``PRO-MEC-014`` half;
* a clause that migrates in 2019 is a member of two documents across the window, so "which
  document is this clause in" is a question about a date, not about a loop variable.

What comes out is ``clause_revision.jsonl``: one row per (revision, clause) the revision touched,
carrying the ordinal and printed label *at that moment*, the control delta, and — for a setpoint
clause — the value on both sides of the edit.  ``cause_kind`` and ``cause_event_ref`` are filled
in later by :mod:`mainline_corpus.blame.causality`; this module records what changed, not why.

That split is deliberate.  A module that decided both would be free to make the causes fit the
changes it had already invented, and the corpus's whole claim is that causality was authored
first and the record written second.
"""

from __future__ import annotations

import dataclasses
import datetime as dt
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from .. import gazetteer as gaz
from .. import rng
from ..injectors.split import SplitPlan
from ..injectors.weakening import Chain
from ..skeleton import clock
from ..skeleton.build import Skeleton
from . import params
from .clauses import ClauseUniverse
from .eventindex import EventIndex
from .model import Clause, ClauseRevision

__all__ = ["RevisionWalk", "materialise", "replace_cause"]

#: Probability that a weaken or remove on a clause with no numeric setpoint is recorded with
#: ``delta_basis = 'abstain_to_weaken'``.  The value means "the safe answer was recorded because
#: the text could not be read decisively" — in this corpus it records TEXTUAL OPACITY, never a
#: model abstention, because no model ran.  See the note on ``lattice+model`` in ``clauses.py``.
_P_OPAQUE: float = 0.34


@dataclass(frozen=True, slots=True)
class RevisionWalk:
    """Everything the walk produced."""

    revisions: tuple[ClauseRevision, ...]
    retypeset_entries: tuple[dict[str, Any], ...]
    migration_entries: tuple[tuple[SplitPlan, str, str, str], ...]
    chain_moves: dict[str, list[dict[str, Any]]]
    retired: dict[str, dt.date]

    def by_clause(self) -> dict[str, tuple[ClauseRevision, ...]]:
        grouped: dict[str, list[ClauseRevision]] = {}
        for revision in self.revisions:
            grouped.setdefault(revision.clause_key, []).append(revision)
        return {
            key: tuple(sorted(items, key=lambda r: (r.effective_on, r.revision_key)))
            for key, items in grouped.items()
        }


def _setpoint_table() -> Mapping[str, tuple[tuple[float, ...], str]]:
    out: dict[str, tuple[tuple[float, ...], str]] = {}
    for entry in gaz.as_sequence(gaz.load("setpoints"), "parameters", origin="setpoints.yaml"):
        out[str(entry["key"])] = (
            tuple(float(value) for value in entry["values"]),
            str(entry["strengthen_direction"]),
        )
    return out


def _strongest(values: Sequence[float], direction: str) -> float:
    return min(values) if direction == "lower" else max(values)


def _step(values: Sequence[float], direction: str, current: float, delta: str) -> float | None:
    """Move one notch.  ``None`` when the parameter is already at the end of its range."""
    ordered = sorted(values)
    try:
        index = ordered.index(current)
    except ValueError:  # pragma: no cover - the state only ever holds gazetteer values
        return None
    if direction == "lower":
        offset = -1 if delta == "strengthen" else 1
    else:
        offset = 1 if delta == "strengthen" else -1
    target = index + offset
    if not 0 <= target < len(ordered):
        return None
    return ordered[target]


def _doc_candidates(universe: ClauseUniverse) -> dict[tuple[str, str], tuple[Clause, ...]]:
    """Every clause that is ever a member of each document — origin plus migrated-in."""
    grouped: dict[tuple[str, str], list[Clause]] = {}
    for clause in universe.clauses:
        grouped.setdefault((clause.site_code, clause.origin_doc_code), []).append(clause)
        migration = universe.migrations.get(clause.clause_key)
        if migration is not None:
            grouped.setdefault((clause.site_code, migration.plan.target_doc_code), []).append(
                clause
            )
    return {key: tuple(items) for key, items in grouped.items()}


def _touch_weight(clause: Clause, recent_classes: frozenset[str], stream: rng.Stream) -> float:
    """How likely this clause is to be edited by this revision.

    A revision issued after something went wrong touches the clauses about the control that
    failed.  That is a *structural* preference, not an answer key: the weight makes those
    clauses more likely to be edited, and whether the edit is attributed to the event is decided
    later, independently, by ``causality.py``.  Keeping the two apart is what stops the corpus
    from marking its own homework.
    """
    weight = 1.0
    if clause.control_class in recent_classes:
        weight *= 3.4
    if clause.setpoint_key is not None:
        weight *= 1.25
    return weight * (0.75 + 0.5 * rng.unit(stream))


def materialise(
    skeleton: Skeleton,
    universe: ClauseUniverse,
    splits: Sequence[SplitPlan],
    chains: Sequence[Chain],
    index: EventIndex,
) -> RevisionWalk:
    """Produce every clause revision, in the order history produced it."""
    setpoints = _setpoint_table()
    spine = gaz.as_mapping(gaz.load("anchors"), "spine", origin="anchors.yaml")
    spine_oem = float(spine["setpoint_oem"])
    spine_post = float(spine["setpoint_post_incident"])
    spine_key = universe.spine_clause_key
    spine_incident_on = clock.coerce_date(
        gaz.as_mapping(spine, "dates", origin="anchors.yaml/spine")["strengthen_commit"],
        origin="anchors.yaml/spine/dates/strengthen_commit",
    )

    docs_by_key = {(doc.site_code, doc.doc_code): doc for doc in skeleton.documents.docs}
    candidates = _doc_candidates(universe)
    chain_by_revision: dict[str, list[Chain]] = {}
    for chain in chains:
        for step in chain.steps:
            chain_by_revision.setdefault(step.revision_key, []).append(chain)
    chain_clause_keys = {chain.clause_key for chain in chains}
    split_by_source = {plan.source_revision_key: plan for plan in splits}
    split_by_reflow = {
        plan.target_reflow_revision_key: plan
        for plan in splits
        if plan.target_reflow_revision_key is not None
    }
    migrating_by_plan: dict[str, list[Clause]] = {}
    for clause_key, migration in universe.migrations.items():
        migrating_by_plan.setdefault(migration.plan.key, []).append(universe.by_key[clause_key])

    # Setpoint state, initialised at birth.  Chain clauses start at the strong end of their
    # range so three weakening steps genuinely exist; the spine starts at the OEM value.
    state: dict[str, float] = {}
    for clause in universe.clauses:
        if clause.setpoint_key is None:
            continue
        values, direction = setpoints[clause.setpoint_key]
        if clause.clause_key == spine_key:
            state[clause.clause_key] = spine_oem
        elif clause.clause_key in chain_clause_keys:
            state[clause.clause_key] = _strongest(values, direction)
        else:
            picker = rng.stream(f"clause.setpoint/{clause.clause_key}")
            state[clause.clause_key] = float(rng.pick(picker, sorted(values)))

    people = skeleton.people
    ordered_revisions = sorted(
        (
            (revision.revision_key.split("/", 1)[0], revision)
            for revision in skeleton.documents.revisions
        ),
        key=lambda item: (item[1].effective_on, item[1].revision_key),
    )

    retired: dict[str, dt.date] = {}
    rows: list[ClauseRevision] = []
    retypeset_entries: list[dict[str, Any]] = []
    migration_entries: list[tuple[SplitPlan, str, str, str]] = []
    chain_moves: dict[str, list[dict[str, Any]]] = {}

    def _members(site_code: str, doc_code: str, on: dt.date) -> list[Clause]:
        pool = candidates.get((site_code, doc_code), ())
        return [
            clause
            for clause in pool
            if clause.birth_on <= on
            and retired.get(clause.clause_key, dt.date.max) > on
            and universe.doc_code_at(clause.clause_key, on) == doc_code
        ]

    def _ordinals(members: Sequence[Clause], doc_code: str, generation: int) -> dict[str, int]:
        ranked = sorted(members, key=lambda c: universe.sort_at(c.clause_key, doc_code, generation))
        return {clause.clause_key: position for position, clause in enumerate(ranked, start=1)}

    for site_code, revision in ordered_revisions:
        doc_key = (site_code, revision.doc_code)
        on = revision.effective_on
        generation = revision.template_generation
        author = people.get(revision.author_sub)
        author_separated = author.separated_at is not None and author.separated_at <= clock.NOW

        live = _members(site_code, revision.doc_code, on)
        if not live:
            continue
        ordinals = _ordinals(live, revision.doc_code, generation)

        touched: dict[str, tuple[str | None, str | None]] = {}
        for clause in live:
            if clause.birth_revision_key == revision.revision_key:
                touched[clause.clause_key] = ("introduce", None)

        is_retypeset = revision.driver == "retypeset" and doc_key in universe.retypeset_docs
        if is_retypeset:
            for clause in live:
                touched.setdefault(clause.clause_key, ("restate", "retypeset"))

        source_plan = split_by_source.get(revision.revision_key)
        if source_plan is not None and source_plan.source_doc_code == revision.doc_code:
            for clause in live:
                touched.setdefault(clause.clause_key, ("restate", "document_split_reflow"))
        reflow_plan = split_by_reflow.get(revision.revision_key)
        if reflow_plan is not None and reflow_plan.target_doc_code == revision.doc_code:
            for clause in live:
                # A clause that arrived under THIS split already has its migration row, emitted
                # against the source document's revision.  Restating it here as well would give
                # one obligation two versions for one change, and clause_version's
                # UNIQUE (clause_uuid, commit_id) says one commit says one thing.
                arriving = universe.migrations.get(clause.clause_key)
                if arriving is not None and arriving.plan.key == reflow_plan.key:
                    continue
                touched.setdefault(clause.clause_key, ("restate", "document_split_reflow"))

        for chain in chain_by_revision.get(revision.revision_key, ()):
            if any(clause.clause_key == chain.clause_key for clause in live):
                touched[chain.clause_key] = ("weaken", "weakening_chain")

        # The one authored edit: 2013-08-04, PRO-MEC-014, 150 -> 135 after the seal fire.
        if on == spine_incident_on and any(clause.clause_key == spine_key for clause in live):
            touched[spine_key] = ("strengthen", "spine")

        if not is_retypeset and source_plan is None and reflow_plan is None:
            edit_stream = rng.sub_stream("clause.touch", revision.revision_key)
            low, high = params.TOUCH_FRACTION_BY_DRIVER.get(
                revision.driver, params.TOUCH_FRACTION_BY_DRIVER["routine_review"]
            )
            fraction = low + rng.unit(edit_stream) * (high - low)
            wanted = max(1, min(len(live), round(len(live) * fraction)))
            recent = frozenset(
                control_class
                for fact in index.preceding(
                    site_code, on, window_days=params.CAUSAL_WINDOW_DAYS, min_severity=2
                )
                for control_class in fact.control_classes
            )
            weighted = sorted(
                live,
                key=lambda c: (
                    -_touch_weight(c, recent, rng.sub_stream(edit_stream, c.clause_key)),
                    c.clause_key,
                ),
            )
            for clause in weighted[:wanted]:
                touched.setdefault(clause.clause_key, (None, None))

        # ── emit, in reading order ───────────────────────────────────────────────────────────
        by_key = {clause.clause_key: clause for clause in live}
        for clause_key in sorted(touched, key=lambda key: ordinals[key]):
            clause = by_key[clause_key]
            hint, injector = touched[clause_key]
            delta_stream = rng.sub_stream("clause.delta", f"{revision.revision_key}#{clause_key}")
            delta = hint or rng.weighted(
                delta_stream,
                *_delta_choices(revision.driver),
            )
            if delta == "remove" and (
                clause.is_spine
                or clause_key in chain_clause_keys
                or clause_key in universe.migrations
            ):
                delta = "restate"
            # The spine's setpoint is 150 from 2011, 135 from 2013, and 135 until the 2026
            # proposal the merge refuses.  A drawn strengthen or weaken on either side would put
            # a third value on screen and contradict every other artefact that quotes this
            # clause — including `anchors.yaml`, the authored fixtures and the shot list.
            if clause.is_spine and on != spine_incident_on and delta != "introduce":
                delta = "restate"

            setpoint_from: float | None = None
            setpoint_to: float | None = None
            if clause.setpoint_key is not None:
                values, direction = setpoints[clause.setpoint_key]
                setpoint_from = state[clause_key]
                if clause_key == spine_key and on == spine_incident_on:
                    setpoint_to = spine_post
                elif delta in ("strengthen", "weaken"):
                    moved = _step(values, direction, setpoint_from, delta)
                    if moved is None:
                        delta = "restate"
                        setpoint_to = setpoint_from
                    else:
                        setpoint_to = moved
                else:
                    setpoint_to = setpoint_from
                state[clause_key] = setpoint_to

            basis_stream = rng.sub_stream("clause.basis", f"{revision.revision_key}#{clause_key}")
            delta_basis = _delta_basis(
                delta=delta,
                moved=setpoint_to is not None and setpoint_to != setpoint_from,
                driver=revision.driver,
                stream=basis_stream,
            )

            doc_code_now = universe.doc_code_at(clause_key, on)
            rows.append(
                ClauseRevision(
                    clause_key=clause_key,
                    clause_uuid=clause.clause_uuid,
                    revision_key=revision.revision_key,
                    site_id=clause.site_id,
                    site_code=site_code,
                    doc_code=doc_code_now,
                    doc_id=docs_by_key[(site_code, doc_code_now)].doc_id,
                    effective_on=on,
                    rev_no=revision.rev_no,
                    ordinal=ordinals[clause_key],
                    printed_label=universe.label_at(clause_key, doc_code_now, generation),
                    template_generation=generation,
                    control_delta=delta,
                    delta_basis=delta_basis,
                    driver=revision.driver,
                    author_sub=revision.author_sub,
                    author_separated=author_separated,
                    cause_kind="unassigned",
                    cause_event_ref=None,
                    injector=injector,
                    setpoint_key=clause.setpoint_key,
                    setpoint_from=setpoint_from,
                    setpoint_to=setpoint_to,
                )
            )
            if delta == "remove":
                retired[clause_key] = on
            if injector == "weakening_chain":
                for chain in chain_by_revision.get(revision.revision_key, ()):
                    if chain.clause_key != clause_key:
                        continue
                    chain_moves.setdefault(chain.chain_id, []).append(
                        {
                            "revision_key": revision.revision_key,
                            "setpoint_from": setpoint_from,
                            "setpoint_to": setpoint_to,
                        }
                    )
            if is_retypeset:
                previous = _ordinals(live, revision.doc_code, 1)
                retypeset_entries.append(
                    {
                        "clause_key": clause_key,
                        "clause_uuid": clause.clause_uuid,
                        "control_class": clause.control_class,
                        "doc_code": revision.doc_code,
                        "g1_ordinal": previous[clause_key],
                        "g1_printed_label": universe.g1_label(clause_key),
                        "g2_ordinal": ordinals[clause_key],
                        "g2_printed_label": universe.g2_label(revision.doc_code, clause_key),
                        "revision_key": revision.revision_key,
                        "site_code": site_code,
                    }
                )

        # ── the clauses that leave this document today ───────────────────────────────────────
        if source_plan is not None and source_plan.source_doc_code == revision.doc_code:
            target_code = source_plan.target_doc_code
            arrivals = [
                clause
                for clause in migrating_by_plan.get(source_plan.key, ())
                if clause.birth_on <= on and retired.get(clause.clause_key, dt.date.max) > on
            ]
            target_members = _members(site_code, target_code, on)
            target_ordinals = _ordinals(target_members, target_code, max(generation, 2))
            for clause in sorted(arrivals, key=lambda c: target_ordinals.get(c.clause_key, 10**6)):
                migration = universe.migrations[clause.clause_key]
                rows.append(
                    ClauseRevision(
                        clause_key=clause.clause_key,
                        clause_uuid=clause.clause_uuid,
                        revision_key=revision.revision_key,
                        site_id=clause.site_id,
                        site_code=site_code,
                        doc_code=target_code,
                        doc_id=docs_by_key[(site_code, target_code)].doc_id,
                        effective_on=on,
                        rev_no=revision.rev_no,
                        ordinal=target_ordinals.get(clause.clause_key, len(target_members) + 1),
                        printed_label=migration.to_label,
                        template_generation=max(generation, 2),
                        control_delta="restate",
                        delta_basis="lattice",
                        driver=revision.driver,
                        author_sub=revision.author_sub,
                        author_separated=author_separated,
                        cause_kind="unassigned",
                        cause_event_ref=None,
                        injector="document_split",
                        setpoint_key=clause.setpoint_key,
                        setpoint_from=state.get(clause.clause_key),
                        setpoint_to=state.get(clause.clause_key),
                    )
                )
                migration_entries.append(
                    (source_plan, clause.clause_key, migration.from_label, migration.to_label)
                )

    rows.sort(key=lambda row: (row.effective_on, row.revision_key, row.ordinal, row.clause_key))
    _assert_unique(rows)
    return RevisionWalk(
        revisions=tuple(rows),
        retypeset_entries=tuple(retypeset_entries),
        migration_entries=tuple(migration_entries),
        chain_moves=chain_moves,
        retired=retired,
    )


def _delta_choices(driver: str) -> tuple[tuple[str, ...], tuple[float, ...]]:
    weights = params.DELTA_WEIGHTS_BY_DRIVER.get(
        driver, params.DELTA_WEIGHTS_BY_DRIVER["routine_review"]
    )
    keys = tuple(sorted(weights))
    return keys, tuple(weights[key] for key in keys)


def _delta_basis(*, delta: str, moved: bool, driver: str, stream: rng.Stream) -> str:
    """How the delta verdict was reached — the audit trail, never a claim about a model.

    ``'lattice+model'`` is never emitted.  It means a model resolved an inconclusive lattice
    verdict, ``model_named_when_model_used`` would then require the model's id, and no model ran
    in this corpus.  Writing one down would put a false provenance claim in the one column whose
    job is to record whether a machine or a person decided.
    """
    if moved:
        return "lattice"
    if delta in ("weaken", "remove") and rng.unit(stream) < _P_OPAQUE:
        return "abstain_to_weaken"
    if driver in ("moc", "regulator") and rng.unit(stream) < 0.22:
        return "human"
    return "lattice"


def _assert_unique(rows: Sequence[ClauseRevision]) -> None:
    seen: set[tuple[str, str]] = set()
    for row in rows:
        key = (row.revision_key, row.clause_key)
        if key in seen:
            raise RuntimeError(
                f"clause {row.clause_key} is touched twice by revision {row.revision_key}. "
                "clause_version is UNIQUE (clause_uuid, commit_id): one commit may say at most "
                "one thing about one obligation, and a second row would mean it said two."
            )
        seen.add(key)


def replace_cause(
    revision: ClauseRevision, *, cause_kind: str, cause_event_ref: str | None, injector: str | None
) -> ClauseRevision:
    """Return ``revision`` with its authored cause bound.  Used only by ``causality``."""
    return dataclasses.replace(
        revision,
        cause_kind=cause_kind,
        cause_event_ref=cause_event_ref,
        injector=revision.injector or injector,
    )
