# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""Gold set **GS0**: the answer key, its three row classes, and the schema it validates against.

One row per (event, clause) pair, and exactly three labels:

``true``              the corpus authored this causal fact.  ``basis`` records the strongest
                      edge the archive supports, ``channel_a_visible`` records whether the
                      citation resolver can see it, and ``generative_reason`` says in prose what
                      happened and why the record does or does not mention it.
``decoy``             an event that shares the asset, the window and the vocabulary of a true
                      precursor and differs in hazard energy and failed control class.  A
                      linker that scores this pair is matching words.
``negative_control``  a clause revision with a **documented non-incident cause** — a scheduled
                      review, a template migration, a regulatory update, a typo fix — paired
                      with the event a linker is most likely to attribute it to.  The
                      false-attribution rate over this set is the number a buyer's lawyer asks
                      for first, which is why the distractor is the nearest *plausible* event
                      and never a random one.

── WHY A NEGATIVE CONTROL CARRIES AN EVENT AT ALL ────────────────────────────────────────────

A revision with no cause is not a judgeable pair; it is an absence.  What is judgeable is
*"would the linker have attributed this revision to that event?"*, and that requires naming the
event.  So every negative control is a pair, and the pairing is adversarial by construction: the
distractor is preferentially an event that failed the very control class the clause asserts and
that landed inside the attribution window — the case the linker is most likely to get wrong,
not the case it is most likely to get right.

── WHAT THIS FILE DOES NOT CLAIM ─────────────────────────────────────────────────────────────

``p_link`` appears nowhere.  Neither does any measure of a linker's performance.  GS0 is ground
truth, not a score, and a synthetic gold set bounds a linker from above; ``README.md`` in the
answer-key directory says so in the first paragraph and it is not a disclaimer, it is the
correct reading of the number.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from ..injectors.decoys import Decoy
from ..skeleton import clock
from . import params
from .clauses import ClauseUniverse
from .eventindex import EventIndex
from .model import BlameEdge, ClauseRevision, GoldRow

__all__ = ["build_gold_set", "gs0_schema", "negative_controls"]

_SCHEMA_ID = "https://mainline.trappoint.dev/schemas/corpus/gs0-v1.json"


def _true_rows(
    edges: Sequence[BlameEdge], index: EventIndex, universe: ClauseUniverse
) -> list[GoldRow]:
    rows: list[GoldRow] = []
    for edge in edges:
        fact = index.get(edge.event_ref)
        clause = universe.by_key[edge.clause_key]
        rows.append(
            GoldRow(
                event_id=edge.event_id,
                event_ref=edge.event_ref,
                clause_uuid=edge.clause_uuid,
                clause_key=edge.clause_key,
                label="true",
                basis=edge.basis,
                state=edge.state,
                p_doc_trace=edge.p_doc_trace,
                channel_a_visible=edge.channel_a_visible,
                generative_reason=edge.generative_reason,
                decoy_of=None,
                documented_cause=None,
                control_class=edge.control_class,
                hazard_energy=edge.hazard_energy,
                severity_gate=edge.severity_gate,
                site_id=edge.site_id,
                site_code=edge.site_code,
                occurred_at=fact.occurred_at,
                revision_key=edge.revision_key,
                doc_code=universe.doc_code_at(clause.clause_key, edge.effective_on),
                effective_on=edge.effective_on,
                injector=edge.injector,
                quote_ref=edge.quote_ref,
            )
        )
    return rows


def _decoy_rows(
    decoys: Sequence[Decoy],
    index: EventIndex,
    universe: ClauseUniverse,
    revisions: Mapping[str, ClauseRevision],
) -> list[GoldRow]:
    rows: list[GoldRow] = []
    for decoy in decoys:
        fact = index.get(decoy.decoy_event_ref)
        revision = revisions.get(decoy.clause_key)
        clause = universe.by_key[decoy.clause_key]
        rows.append(
            GoldRow(
                event_id=decoy.decoy_event_id,
                event_ref=decoy.decoy_event_ref,
                clause_uuid=decoy.clause_uuid,
                clause_key=decoy.clause_key,
                label="decoy",
                basis=None,
                state=None,
                p_doc_trace=None,
                channel_a_visible=False,
                generative_reason=(
                    f"{decoy.decoy_event_ref} shares "
                    f"{', '.join(decoy.shared_assets)} with {decoy.twin_event_ref} and sits "
                    f"{abs(decoy.separation_days):.0f} days from it in the same era, so their "
                    f"surface language matches. It released {decoy.decoy_hazard_energy} rather "
                    f"than {decoy.twin_hazard_energy} and failed "
                    f"{', '.join(decoy.decoy_control_classes)}, which is disjoint from the "
                    "controls the true precursor failed. It did not write this clause; a linker "
                    "that returns it is matching vocabulary, not mechanism."
                ),
                decoy_of=decoy.twin_event_ref,
                documented_cause=None,
                control_class=clause.control_class,
                hazard_energy=decoy.decoy_hazard_energy,
                severity_gate=decoy.severity_gate,
                site_id=decoy.site_id,
                site_code=decoy.site_code,
                occurred_at=fact.occurred_at,
                revision_key="" if revision is None else revision.revision_key,
                doc_code="" if revision is None else revision.doc_code,
                effective_on=fact.occurred_at.date() if revision is None else revision.effective_on,
                injector="decoy",
                quote_ref=None,
            )
        )
    return rows


def negative_controls(
    universe: ClauseUniverse,
    revisions: Sequence[ClauseRevision],
    index: EventIndex,
    taken: frozenset[tuple[str, str]],
) -> list[GoldRow]:
    """Pair every candidate non-incident revision with its most plausible distractor.

    ``taken`` is the set of ``(clause_key, event_ref)`` pairs already spoken for by a true edge
    or a decoy.  A pair cannot be two things at once, and a negative control that is secretly a
    true edge is worse than no negative control: it puts a correct attribution into the
    false-attribution numerator.
    """
    clause_of = {clause.clause_key: clause for clause in universe.clauses}
    per_document: dict[str, int] = {}
    cap = max(4, params.NEGATIVE_CONTROL_TARGET // 12)

    scored: list[tuple[tuple[int, float, str], GoldRow]] = []
    for revision in revisions:
        if revision.cause_event_ref is not None:
            continue
        if revision.cause_kind not in params.NON_INCIDENT_CAUSE_WEIGHTS:
            continue
        clause = clause_of[revision.clause_key]
        window = index.preceding(
            revision.site_code,
            revision.effective_on,
            window_days=params.NEGATIVE_CONTROL_WINDOW_DAYS,
            min_severity=1,
        )
        if not window:
            continue
        matching = [
            fact
            for fact in window
            if clause.control_class in fact.control_classes
            and (revision.clause_key, fact.external_ref) not in taken
        ]
        pool = matching or [
            fact for fact in window if (revision.clause_key, fact.external_ref) not in taken
        ]
        if not pool:
            continue
        distractor = max(pool, key=lambda fact: (fact.severity_gate, fact.day))
        adversarial = 1 if matching else 0
        lag = clock.days_between(
            distractor.occurred_at,
            clock.coerce_datetime(revision.effective_on, origin="negative/effective_on"),
        )
        row = GoldRow(
            event_id=distractor.event.event_id,
            event_ref=distractor.external_ref,
            clause_uuid=revision.clause_uuid,
            clause_key=revision.clause_key,
            label="negative_control",
            basis=None,
            state=None,
            p_doc_trace=None,
            channel_a_visible=False,
            generative_reason=(
                f"{revision.doc_code} clause {revision.printed_label} was "
                f"{revision.control_delta}d on {clock.iso_date(revision.effective_on)} for a "
                f"documented non-incident reason ({revision.cause_kind.replace('_', ' ')}). "
                f"{distractor.external_ref} (severity_gate {distractor.severity_gate}) landed "
                f"{lag:.0f} days earlier at the same site and "
                + (
                    f"failed {clause.control_class}, so a linker joining on the mechanism will "
                    "surface it. It did not cause this edit."
                    if adversarial
                    else "is the nearest event a linker could reach for. It did not cause this "
                    "edit."
                )
            ),
            decoy_of=None,
            documented_cause=revision.cause_kind,
            control_class=clause.control_class,
            hazard_energy=distractor.event.hazard_energy,
            severity_gate=distractor.severity_gate,
            site_id=revision.site_id,
            site_code=revision.site_code,
            occurred_at=distractor.occurred_at,
            revision_key=revision.revision_key,
            doc_code=revision.doc_code,
            effective_on=revision.effective_on,
            injector=revision.injector,
            quote_ref=None,
        )
        scored.append(((-adversarial, -distractor.severity_gate, revision.revision_key), row))

    scored.sort(key=lambda item: (item[0], item[1].clause_key))
    chosen: list[GoldRow] = []
    seen: set[tuple[str, str]] = set()
    for _rank, row in scored:
        if len(chosen) >= params.NEGATIVE_CONTROL_TARGET:
            break
        pair = (row.clause_key, row.event_ref)
        if pair in seen:
            continue
        used = per_document.get(row.doc_code, 0)
        if used >= cap:
            continue
        per_document[row.doc_code] = used + 1
        seen.add(pair)
        chosen.append(row)

    if len(chosen) < params.NEGATIVE_CONTROL_FLOOR:
        # Second pass without the per-document cap: spread is a preference, the floor is not.
        for _rank, row in scored:
            if len(chosen) >= params.NEGATIVE_CONTROL_TARGET:
                break
            pair = (row.clause_key, row.event_ref)
            if pair in seen:
                continue
            seen.add(pair)
            chosen.append(row)

    if len(chosen) < params.NEGATIVE_CONTROL_FLOOR:
        raise RuntimeError(
            f"only {len(chosen)} negative controls could be paired, floor is "
            f"{params.NEGATIVE_CONTROL_FLOOR}. The false-attribution rate is the first number a "
            "buyer's lawyer asks for; a corpus that cannot state it over at least "
            f"{params.NEGATIVE_CONTROL_FLOOR} pairs cannot state it."
        )
    return chosen


def build_gold_set(
    universe: ClauseUniverse,
    revisions: Sequence[ClauseRevision],
    edges: Sequence[BlameEdge],
    decoys: Sequence[Decoy],
    index: EventIndex,
) -> tuple[GoldRow, ...]:
    """Assemble GS0 and refuse a pair that is judged two ways."""
    latest_by_clause: dict[str, ClauseRevision] = {}
    for revision in revisions:
        latest_by_clause[revision.clause_key] = revision

    rows = _true_rows(edges, index, universe)
    taken = {(row.clause_key, row.event_ref) for row in rows}
    decoy_rows = _decoy_rows(decoys, index, universe, latest_by_clause)
    for row in decoy_rows:
        pair = (row.clause_key, row.event_ref)
        if pair in taken:
            raise RuntimeError(
                f"{pair} is both a true edge and a decoy. A decoy must not have written the "
                "clause it shadows, or the false-positive it measures is a true positive."
            )
        taken.add(pair)
    rows.extend(decoy_rows)

    negatives = negative_controls(universe, revisions, index, frozenset(taken))
    for row in negatives:
        pair = (row.clause_key, row.event_ref)
        if pair in taken:  # pragma: no cover - `negative_controls` excludes them by construction
            raise RuntimeError(f"{pair} is judged twice")
        taken.add(pair)
    rows.extend(negatives)

    for row in rows:
        if not row.generative_reason.strip():
            raise RuntimeError(
                f"gold row {row.clause_key}/{row.event_ref} carries no generative_reason. A row "
                "that cannot say why it is gold is a row nobody can audit."
            )
    return tuple(sorted(rows, key=lambda row: (row.clause_key, row.event_ref, row.label)))


# ── the schema ───────────────────────────────────────────────────────────────────────────────


def _uuid_property(description: str) -> dict[str, Any]:
    return {"type": "string", "minLength": 36, "maxLength": 36, "description": description}


def gs0_schema() -> dict[str, Any]:
    """Build the JSON Schema every GS0 row validates against.

    Draft 2020-12, and deliberately restricted to keywords a hand-written walk can implement:
    ``type``, ``const``, ``enum``, ``required``, ``properties``, ``additionalProperties``,
    ``anyOf``, ``minLength``/``maxLength``, ``minimum``/``maximum``.  The recall lane validates
    its own gold sets with exactly such a walk rather than taking a dependency, and a schema this
    corpus's consumers cannot check without installing something is a schema that will not be
    checked.

    The three ``anyOf`` branches are where the label's meaning is enforced: a ``true`` row must
    carry a basis and a state, a ``decoy`` must name what it decoys and must not carry a basis,
    and a ``negative_control`` must name its documented non-incident cause.  Getting that wrong
    is how a gold set quietly starts counting a correct attribution as a false one.
    """
    bases = ["asserted_document", "asserted_human", "derived_documentary", "inferred_semantic"]
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": _SCHEMA_ID,
        "title": "MAINLINE corpus gold set GS0",
        "description": (
            "One judged (event, clause) pair per row. Authored by the generator that created the "
            "causal fact; see README.md in this directory for what the numbers computed over it "
            "do and do not mean."
        ),
        "type": "object",
        "additionalProperties": False,
        "required": [
            "channel_a_visible",
            "clause_key",
            "clause_uuid",
            "control_class",
            "doc_code",
            "effective_on",
            "event_id",
            "event_ref",
            "generative_reason",
            "hazard_energy",
            "label",
            "occurred_at",
            "revision_key",
            "severity_gate",
            "site_code",
            "site_id",
        ],
        "properties": {
            "basis": {
                "anyOf": [{"type": "null"}, {"enum": bases}],
                "description": "the strongest edge the archive supports; null unless label=true",
            },
            "channel_a_visible": {
                "type": "boolean",
                "description": (
                    "whether the citation resolver (channel A) can see this link. True exactly "
                    "when the basis is asserted_document."
                ),
            },
            "clause_key": {"type": "string", "minLength": 5},
            "clause_uuid": _uuid_property("uuid5(CORPUS_NS, 'clause:' || clause_key)"),
            "control_class": {"type": "string", "minLength": 3},
            "decoy_of": {
                "anyOf": [{"type": "null"}, {"type": "string", "minLength": 3}],
                "description": "the true precursor this decoy shadows",
            },
            "doc_code": {"type": "string"},
            "documented_cause": {
                "anyOf": [
                    {"type": "null"},
                    {
                        "enum": [
                            "regulatory_update",
                            "scheduled_review",
                            "template_migration",
                            "typo_fix",
                        ]
                    },
                ],
                "description": "the recorded non-incident reason a negative control was reissued",
            },
            "effective_on": {"type": "string", "minLength": 10, "maxLength": 10},
            "event_id": _uuid_property("uuid5(CORPUS_NS, 'event:' || event_ref)"),
            "event_ref": {"type": "string", "minLength": 3},
            "generative_reason": {
                "type": "string",
                "minLength": 40,
                "description": "prose, mandatory on every row, including the negatives",
            },
            "hazard_energy": {
                "enum": [
                    "gravity",
                    "pressure",
                    "electrical",
                    "thermal",
                    "chemical",
                    "kinetic",
                    "radiation",
                    "biological",
                ]
            },
            "injector": {"anyOf": [{"type": "null"}, {"type": "string", "minLength": 3}]},
            "label": {"enum": ["true", "decoy", "negative_control"]},
            "occurred_at": {"type": "string", "minLength": 20},
            "p_doc_trace": {
                "anyOf": [{"type": "null"}, {"type": "number", "minimum": 0.0, "maximum": 1.0}],
                "description": (
                    "the probability this causal fact left a documentary trace, recorded per row "
                    "so the capture-recapture estimator can state its own assumption"
                ),
            },
            "quote_ref": {"anyOf": [{"type": "null"}, {"type": "string", "minLength": 6}]},
            "revision_key": {"type": "string"},
            "severity_gate": {"type": "integer", "minimum": 0, "maximum": 5},
            "site_code": {"type": "string", "minLength": 3, "maxLength": 3},
            "site_id": _uuid_property("uuid5(CORPUS_NS, 'site:' || site_code)"),
            "state": {
                "anyOf": [
                    {"type": "null"},
                    {"enum": ["active", "provisional", "dormant", "refuted"]},
                ]
            },
        },
        "anyOf": [
            {
                "title": "true",
                "properties": {
                    "label": {"const": "true"},
                    "basis": {"enum": bases},
                    "state": {"enum": ["active", "provisional", "dormant", "refuted"]},
                    "p_doc_trace": {"type": "number", "minimum": 0.0, "maximum": 1.0},
                    "decoy_of": {"type": "null"},
                    "documented_cause": {"type": "null"},
                },
                "required": ["basis", "p_doc_trace", "state"],
            },
            {
                "title": "decoy",
                "properties": {
                    "label": {"const": "decoy"},
                    "basis": {"type": "null"},
                    "state": {"type": "null"},
                    "p_doc_trace": {"type": "null"},
                    "decoy_of": {"type": "string", "minLength": 3},
                    "documented_cause": {"type": "null"},
                    "channel_a_visible": {"const": False},
                },
                "required": ["decoy_of"],
            },
            {
                "title": "negative_control",
                "properties": {
                    "label": {"const": "negative_control"},
                    "basis": {"type": "null"},
                    "state": {"type": "null"},
                    "p_doc_trace": {"type": "null"},
                    "decoy_of": {"type": "null"},
                    "documented_cause": {
                        "enum": [
                            "regulatory_update",
                            "scheduled_review",
                            "template_migration",
                            "typo_fix",
                        ]
                    },
                    "channel_a_visible": {"const": False},
                },
                "required": ["documented_cause"],
            },
        ],
    }
