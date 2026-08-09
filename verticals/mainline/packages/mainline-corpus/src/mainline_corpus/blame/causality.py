# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""Authoring causality: which event generated which clause revision, and what the record says.

This is decision **D7**: the answer key is written by the generator that created the causal
fact, never inferred afterwards.  Two independent draws produce every edge, and keeping them
independent is the whole design.

**Draw one — did this event generate this edit?**  A revision is a candidate only if the event
failed a control of the class the clause asserts.  That is the *mechanism join key*, and it is
a set operation over ``control_failure.control_class``, never a similarity over text.  Given a
candidate, the causal fact is drawn: ``P_INCIDENT_DRIVEN`` normally,
``P_INCIDENT_DRIVEN_WHEN_DECLARED`` when stage 1 already recorded that this revision followed
that named event.  Not 1.0 even then — a revision issued after an incident routinely also
carries clauses that had nothing to do with it, and a corpus that attributed every clause of an
incident revision to the incident would be marking its own homework.

**Draw two — did the causal fact leave a documentary trace?**  ``p_doc`` averages 0.55 and
varies with the kind of event and whether the gate armed: a regulator's improvement notice names
the clause it requires, a fatality's CAPA register is the most complete document a mine
produces, and a near-miss whose corrective action was a verbal briefing leaves nothing.  The
draw is what makes held-out asserted-link masking have real positives, and it is what gives the
Chapman capture-recapture estimator a residue to estimate.  Without it, channel A would see
either everything or nothing.

**The basis falls out of draw two, and the state falls out of the basis:**

======================  ==================================================  ===================
basis                   arises when                                          state
======================  ==================================================  ===================
``asserted_document``   the trace exists — a revision-history line, a CAPA   ``active``
                        action, an MOC citing the event, a notice
``asserted_human``      no trace, but an SME confirmed it under signature    ``active``
``derived_documentary`` no trace; two independent documentary facts          ``provisional``
                        co-locate it — the edit landed inside the window
                        and its delta touches the control that failed
``inferred_semantic``   no trace and no co-location: nothing but the         ``provisional``
                        mechanism and the words                              **never active**
======================  ==================================================  ===================

``inference_never_blocks`` is a shipped ``CHECK``.  Nothing here can emit an ``inferred_semantic``
edge in the ``active`` state — and the builder re-checks the emitted rows rather than trusting
this paragraph, because a generator that guards itself by intention has no guard.

**``p_link`` is not computed here** and its absence is registered, not papered over.  It is the
output of an isotonic calibration fitted on an adjudicated set; this module emits ``features`` —
the arithmetic incident-ingestion.md §7 names, kept in full — and the prose ``attribution`` that
a human is shown instead of a bare number.  The attribution is composed by a template from those
same features.  No model wrote it, and the corpus never says one did.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from .. import gazetteer as gaz
from .. import rng
from ..injectors.fleet import FleetGroup
from ..injectors.orphans import Orphan
from ..skeleton import clock
from ..skeleton.build import Skeleton
from . import params
from .clauses import ClauseUniverse
from .eventindex import EventFacts, EventIndex
from .model import BlameEdge, ClauseRevision
from .revisions import RevisionWalk, replace_cause

__all__ = ["CausalityResult", "attribution_of", "author"]

#: Deltas an incident can plausibly have generated.  An event does not cause a control to be
#: weakened; a corpus that said otherwise would be modelling fraud, and fraud is not what the
#: precursor gate is for.
_CAUSAL_DELTAS: frozenset[str] = frozenset({"introduce", "strengthen", "restate"})

#: Revisions an injector produced for a **structural** reason.  A retypeset renumbers a document
#: and a split moves obligations between documents; neither is a response to anything that
#: happened on the plant, and attributing one to an incident would put a fabricated causal fact
#: into the answer key at exactly the revisions the corpus uses to prove identity survives
#: reflow.  These revisions carry a documented non-incident cause instead, which is also what
#: makes them the natural population for the negative-control set.
_STRUCTURAL_INJECTORS: frozenset[str] = frozenset(
    {"retypeset", "document_split", "document_split_reflow"}
)

#: The documentary forms an asserted link takes, and their share.  Each is a real sentence type
#: in a real archive; the renderer binds ``quote_ref`` to an exact, unique substring of the
#: document that carries it.
_QUOTE_KINDS: tuple[str, ...] = (
    "revision_history_line",
    "capa_action",
    "moc_reference",
    "regulator_requirement",
    "investigation_recommendation",
)
_QUOTE_WEIGHTS: tuple[float, ...] = (0.34, 0.26, 0.16, 0.11, 0.13)

_NON_INCIDENT_CAUSES: tuple[str, ...] = tuple(sorted(params.NON_INCIDENT_CAUSE_WEIGHTS))
_NON_INCIDENT_WEIGHTS: tuple[float, ...] = tuple(
    params.NON_INCIDENT_CAUSE_WEIGHTS[key] for key in _NON_INCIDENT_CAUSES
)


@dataclass(frozen=True, slots=True)
class CausalityResult:
    edges: tuple[BlameEdge, ...]
    revisions: tuple[ClauseRevision, ...]
    p_doc_mean: float
    basis_histogram: dict[str, int]
    state_histogram: dict[str, int]

    @property
    def blame_ratio(self) -> float:
        return len(self.edges) / len(self.revisions) if self.revisions else 0.0


def _control_class_labels() -> Mapping[str, str]:
    return {
        str(entry["key"]): str(entry["label"])
        for entry in gaz.as_sequence(
            gaz.load("control_classes"), "classes", origin="control_classes.yaml"
        )
    }


def _p_doc_trace(fact: EventFacts, *, declared: bool) -> float:
    value = params.P_DOC_TRACE_BY_KIND.get(fact.event.kind, params.P_DOC_TRACE_BASE)
    if fact.severity_gate >= 4:
        value += params.P_DOC_TRACE_SEVERE_BONUS
    if declared:
        value += params.P_DOC_TRACE_DECLARED_BONUS
    return min(0.98, max(0.02, value))


def _features(
    *,
    fact: EventFacts,
    revision: ClauseRevision,
    clause_control_class: str,
    lag_days: float,
    doc_asset_classes: Sequence[str],
    event_asset_classes: Sequence[str],
    same_fonds: bool,
    author_present: bool,
) -> dict[str, Any]:
    """Compute the features incident-ingestion.md §7 names — the arithmetic, kept.

    ``days_between`` is a **monotone feature and not a decay weight**: a 2013 death is exactly as
    relevant today as it was in 2014, and a corpus that discounted it by age would be teaching
    the calibrator the one thing the product exists to refuse.
    """
    failed = sorted(fact.control_classes)
    intersection = 1 if clause_control_class in fact.control_classes else 0
    union = len(set(failed) | {clause_control_class})
    shared_classes = sorted(set(doc_asset_classes) & set(event_asset_classes))
    if same_fonds and shared_classes:
        lmb_level = 3
    elif same_fonds:
        lmb_level = 2
    else:
        lmb_level = 1
    direction = {
        "strengthen": 1.0,
        "introduce": 0.8,
        "restate": 0.4,
        "weaken": 0.0,
        "remove": 0.0,
    }[revision.control_delta]
    return {
        "anchor_overlap": len(shared_classes),
        "author_present_at_event": author_present,
        "cat_delta_direction_agreement": direction,
        "control_class_jaccard": round(intersection / union, 4) if union else 0.0,
        "days_between": round(lag_days, 2),
        "document_scope_match": bool(shared_classes),
        "failed_control_classes": failed,
        "lmb_activity_level": lmb_level,
        "setpoint_moved": revision.setpoint_to is not None
        and revision.setpoint_to != revision.setpoint_from,
        "severity_gate": fact.severity_gate,
    }


def attribution_of(features: Mapping[str, Any], *, control_class_label: str, event_ref: str) -> str:
    """Compose the prose a human is shown from the decisive features.

    A bare probability never reaches a human (incident-ingestion.md §7).  This sentence is a
    deterministic rendering of the numbers above it — the same inputs always produce the same
    words — so it can be read as evidence of what the system computed rather than as something
    a model said about the case.
    """
    reasons: list[str] = []
    if features["control_class_jaccard"] > 0:
        reasons.append(f"the failed control class ({control_class_label}) matches")
    reasons.append(f"the change landed {features['days_between']:.0f} days after the event")
    if features["lmb_activity_level"] >= 3:
        reasons.append("the activity and the asset class both match at file level")
    elif features["lmb_activity_level"] == 2:
        reasons.append("the activity matches at fonds level")
    if features["cat_delta_direction_agreement"] >= 0.8:
        reasons.append("the edit strengthened the control that failed")
    if features["setpoint_moved"]:
        reasons.append("a numeric setpoint moved, so the direction is decidable")
    if features["author_present_at_event"]:
        reasons.append("the author was on site when it happened")
    body = "; ".join(reasons)
    return f"Proposed for {event_ref} because {body}."


def _generative_reason(
    *,
    fact: EventFacts,
    revision: ClauseRevision,
    basis: str,
    control_class_label: str,
    lag_days: float,
    injector: str | None,
) -> str:
    """Why this edge exists, in prose, mandatory on every gold-set row.

    It records what the generator *did*, not what a linker might conclude: the causal fact, the
    mechanism it acted through, and whether the archive says so.  A gold set whose rows cannot
    say why they are gold is a gold set nobody can audit.
    """
    trace = {
        "asserted_document": "the record states it, so channel A can resolve the link",
        "asserted_human": (
            "the record says nothing and an SME confirmed it under signature during "
            "adjudication, so channel A cannot see it"
        ),
        "derived_documentary": (
            "the record states nothing, but the edit landed inside the co-location window and "
            "its delta touches the control that failed"
        ),
        "inferred_semantic": (
            "the archive is silent and the co-location test cannot reach it, so the only "
            "available edge is an inference that may never block a permit"
        ),
    }[basis]
    tail = f" Injected by the {injector} injector." if injector else ""
    return (
        f"{fact.external_ref} (severity_gate {fact.severity_gate}, "
        f"{fact.event.hazard_energy}) failed {control_class_label}; "
        f"{revision.doc_code} clause {revision.printed_label} was "
        f"{revision.control_delta}d {lag_days:.0f} days later in response. {trace}.{tail}"
    )


def _reviewer_for(skeleton: Skeleton, site_code: str, moment: dt.datetime) -> str | None:
    candidates = skeleton.people.authors_at(site_code, moment)
    if not candidates:
        candidates = tuple(person for person in skeleton.people.at(site_code) if person.rank >= 2)
    if not candidates:
        return None
    stream = rng.stream(f"blame.reviewer/{site_code}/{clock.iso(moment)}")
    return rng.pick(stream, candidates).signer_sub


def author(
    skeleton: Skeleton,
    universe: ClauseUniverse,
    walk: RevisionWalk,
    index: EventIndex,
    orphans: Sequence[Orphan],
    fleet_groups: Sequence[FleetGroup],
) -> CausalityResult:
    """Decide every cause, draw every trace, and emit the blame edges."""
    labels = _control_class_labels()
    clause_of = {clause.clause_key: clause for clause in universe.clauses}
    docs_by_key = {(doc.site_code, doc.doc_code): doc for doc in skeleton.documents.docs}
    assets = skeleton.assets
    people = skeleton.people
    spine_key = universe.spine_clause_key
    spine_incident_ref = _spine_event_ref()

    declared_event: dict[str, str] = {
        revision.revision_key: revision.driving_event_ref
        for revision in skeleton.documents.revisions
        if revision.driving_event_ref is not None
    }
    orphan_by_revision = {(item.revision_key, item.clause_key): item for item in orphans}
    fleet_by_revision: dict[tuple[str, str], tuple[FleetGroup, str]] = {}
    for group in fleet_groups:
        for member in group.members:
            fleet_by_revision[(member.revision_key, member.clause_key)] = (
                group,
                group.canonical_event_ref,
            )

    edges: dict[tuple[str, str], BlameEdge] = {}
    bound: list[ClauseRevision] = []
    p_doc_values: list[float] = []

    for revision in walk.revisions:
        clause = clause_of[revision.clause_key]
        pair = (revision.revision_key, revision.clause_key)
        forced_ref: str | None = None
        injector = revision.injector
        forced_basis: str | None = None

        orphan = orphan_by_revision.get(pair)
        if orphan is not None:
            forced_ref = orphan.hidden_cause_ref
            forced_basis = "inferred_semantic"
            injector = "orphan"
        elif pair in fleet_by_revision:
            group, forced_ref = fleet_by_revision[pair]
            injector = "fleet_sibling"
        elif revision.clause_key == spine_key and revision.injector == "spine":
            forced_ref = spine_incident_ref
            forced_basis = "asserted_document"

        cause_ref = forced_ref
        declared = False
        if cause_ref is None:
            candidates = index.preceding(
                revision.site_code,
                revision.effective_on,
                window_days=params.CAUSAL_WINDOW_DAYS,
                control_class=clause.control_class,
                min_severity=1,
            )
            named = declared_event.get(revision.revision_key)
            structural = revision.injector in _STRUCTURAL_INJECTORS
            if candidates and revision.control_delta in _CAUSAL_DELTAS and not structural:
                declared = named is not None and any(
                    fact.external_ref == named for fact in candidates
                )
                draw = rng.unit(
                    rng.stream(f"blame.cause/{revision.revision_key}#{revision.clause_key}")
                )
                threshold = (
                    params.P_INCIDENT_DRIVEN_WHEN_DECLARED if declared else params.P_INCIDENT_DRIVEN
                )
                if draw < threshold:
                    if declared:
                        cause_ref = named
                    else:
                        cause_ref = max(
                            candidates, key=lambda fact: (fact.severity_gate, fact.day)
                        ).external_ref
        else:
            declared = declared_event.get(revision.revision_key) == cause_ref

        if cause_ref is None:
            kind_stream = rng.stream(
                f"blame.noncause/{revision.revision_key}#{revision.clause_key}"
            )
            cause_kind = _non_incident_cause(revision, kind_stream)
            bound.append(
                replace_cause(
                    revision, cause_kind=cause_kind, cause_event_ref=None, injector=injector
                )
            )
            continue

        fact = index.get(cause_ref)
        lag_days = clock.days_between(
            fact.occurred_at,
            clock.coerce_datetime(revision.effective_on, origin="blame/effective_on"),
        )
        bound.append(
            replace_cause(
                revision, cause_kind="incident", cause_event_ref=cause_ref, injector=injector
            )
        )

        edge_key = (revision.clause_key, cause_ref)
        if edge_key in edges:
            # One causal fact per (event, clause).  A later revision of the same clause by the
            # same event is the same fact restated, and blame_edge's primary key says so.
            continue

        p_doc = (
            1.0 if forced_basis == "asserted_document" else _p_doc_trace(fact, declared=declared)
        )
        p_doc_values.append(p_doc)
        trace_stream = rng.stream(f"blame.trace/{revision.clause_key}#{cause_ref}")
        traced = forced_basis == "asserted_document" or (
            forced_basis is None and rng.unit(trace_stream) < p_doc
        )

        doc = docs_by_key[(revision.site_code, revision.doc_code)]
        event_asset_classes = sorted(
            {assets.get(tag).asset_class for tag in fact.event.assets if assets.has(tag)}
        )
        author_person = people.get(revision.author_sub)
        author_present = author_person.effective_from <= fact.occurred_at and (
            author_person.separated_at is None or author_person.separated_at > fact.occurred_at
        )
        features = _features(
            fact=fact,
            revision=revision,
            clause_control_class=clause.control_class,
            lag_days=lag_days,
            doc_asset_classes=doc.asset_classes,
            event_asset_classes=event_asset_classes,
            same_fonds=fact.event.activity_root == clause.activity_root,
            author_present=author_present,
        )

        quote_ref: str | None = None
        quote_kind: str | None = None
        reviewed_by: str | None = None
        provisional_until: dt.datetime | None = None
        effective_at = clock.coerce_datetime(
            revision.effective_on, origin="blame/provisional_until"
        )

        if forced_basis == "inferred_semantic":
            basis, state = "inferred_semantic", "provisional"
        elif traced:
            basis, state = "asserted_document", "active"
            quote_stream = rng.stream(f"blame.quote/{revision.clause_key}#{cause_ref}")
            quote_kind = (
                "revision_history_line"
                if declared
                else rng.weighted(quote_stream, _QUOTE_KINDS, _QUOTE_WEIGHTS)
            )
            quote_ref = f"quote:{revision.revision_key}#{quote_kind}/{cause_ref}"
        else:
            human_stream = rng.stream(f"blame.human/{revision.clause_key}#{cause_ref}")
            if rng.unit(human_stream) < params.P_ASSERTED_HUMAN_OF_UNTRACED:
                basis, state = "asserted_human", "active"
                reviewed_by = _reviewer_for(skeleton, revision.site_code, clock.NOW)
            elif (
                lag_days <= params.DERIVED_WINDOW_DAYS
                and features["control_class_jaccard"] > 0
                and features["cat_delta_direction_agreement"] >= 0.4
            ):
                basis, state = "derived_documentary", "provisional"
                provisional_until = effective_at + dt.timedelta(days=params.PROVISIONAL_DAYS)
            else:
                basis, state = "inferred_semantic", "provisional"
                provisional_until = effective_at + dt.timedelta(days=params.PROVISIONAL_DAYS)

        if forced_basis == "inferred_semantic":
            provisional_until = effective_at + dt.timedelta(days=params.PROVISIONAL_DAYS)

        label = labels.get(clause.control_class, clause.control_class)
        edges[edge_key] = BlameEdge(
            event_ref=cause_ref,
            event_id=fact.event.event_id,
            clause_key=revision.clause_key,
            clause_uuid=clause.clause_uuid,
            basis=basis,
            state=state,
            site_id=clause.site_id,
            site_code=clause.site_code,
            revision_key=revision.revision_key,
            effective_on=revision.effective_on,
            severity_gate=fact.severity_gate,
            control_class=clause.control_class,
            hazard_energy=fact.event.hazard_energy,
            channel_a_visible=basis == "asserted_document",
            p_doc_trace=p_doc,
            generative_reason=_generative_reason(
                fact=fact,
                revision=revision,
                basis=basis,
                control_class_label=label,
                lag_days=lag_days,
                injector=injector,
            ),
            attribution=attribution_of(features, control_class_label=label, event_ref=cause_ref),
            features=features,
            evidence_doc_id=doc.doc_id if basis == "asserted_document" else None,
            quote_ref=quote_ref,
            quote_ref_kind=quote_kind,
            reviewed_by=reviewed_by,
            provisional_until=provisional_until,
            injector=injector,
            cross_site=fact.event.site_code != clause.site_code,
            lag_days=lag_days,
        )

    ordered = tuple(sorted(edges.values(), key=lambda edge: (edge.clause_key, edge.event_ref)))
    _assert_basis_graded_force(ordered)
    basis_histogram: dict[str, int] = {}
    state_histogram: dict[str, int] = {}
    for edge in ordered:
        basis_histogram[edge.basis] = basis_histogram.get(edge.basis, 0) + 1
        state_histogram[edge.state] = state_histogram.get(edge.state, 0) + 1

    mean = sum(p_doc_values) / len(p_doc_values) if p_doc_values else 0.0
    low, high = params.P_DOC_TRACE_MEAN_BAND
    if not low <= mean <= high:
        raise RuntimeError(
            f"the realised documentary-trace rate is {mean:.3f}, outside [{low}, {high}]. "
            "Decision D7 says roughly 55 % of causal facts leave a trace; a corpus at 0.9 makes "
            "held-out asserted-link masking trivial and a corpus at 0.2 leaves capture-recapture "
            "nothing to estimate."
        )

    return CausalityResult(
        edges=ordered,
        revisions=tuple(bound),
        p_doc_mean=round(mean, 4),
        basis_histogram=dict(sorted(basis_histogram.items())),
        state_histogram=dict(sorted(state_histogram.items())),
    )


def _non_incident_cause(revision: ClauseRevision, stream: rng.Stream) -> str:
    """Choose the documented non-incident reason this revision happened.

    Not a residual category: these are the four reasons a controlled document is actually
    reissued when nothing went wrong, and the negative-control set is drawn from exactly these
    rows.  The driver stage 1 recorded constrains the choice — a retypeset is a template
    migration and nothing else, and a regulator-driven revision is a regulatory update.
    """
    if revision.injector == "retypeset" or revision.driver == "retypeset":
        return "template_migration"
    if revision.driver == "regulator":
        return "regulatory_update"
    if revision.injector in ("document_split", "document_split_reflow"):
        return "template_migration"
    if revision.control_delta == "introduce":
        return "scheduled_review"
    return rng.weighted(stream, _NON_INCIDENT_CAUSES, _NON_INCIDENT_WEIGHTS)


def _assert_basis_graded_force(edges: Sequence[BlameEdge]) -> None:
    """Re-check ``inference_never_blocks`` over the emitted objects.

    The paragraph in this module's docstring says an inferred edge can never be active.  This
    function is that sentence made mechanical.  P2 applies to a generator's own guards: a rule
    enforced only by the intention of the code that writes the rows is not enforced.
    """
    offenders = [
        edge.key for edge in edges if edge.basis == "inferred_semantic" and edge.state == "active"
    ]
    if offenders:
        raise RuntimeError(
            f"{len(offenders)} inferred_semantic edge(s) are active, e.g. {offenders[:3]}. "
            "CHECK inference_never_blocks would refuse them, and it would be right: an inferred "
            "link that blocks a permit converts every model error into a rubber stamp."
        )
    unquoted = [
        edge.key for edge in edges if edge.basis == "asserted_document" and not edge.quote_ref
    ]
    if unquoted:
        raise RuntimeError(
            f"{len(unquoted)} asserted_document edge(s) carry no quote_ref, e.g. {unquoted[:3]}. "
            "CHECK asserted_needs_quote requires a bound quote, and the renderer needs the "
            "reference to bind one."
        )
    unsigned = [
        edge.key for edge in edges if edge.basis == "asserted_human" and not edge.reviewed_by
    ]
    if unsigned:
        raise RuntimeError(
            f"{len(unsigned)} asserted_human edge(s) name no reviewer, e.g. {unsigned[:3]}. "
            "CHECK human_needs_signature bites on the signature; naming who signed is the least "
            "the corpus can carry."
        )


def _spine_event_ref() -> str:
    """Read the 2013 gland-seal fire from the gazetteer rather than typing it here twice."""
    spine = gaz.as_mapping(gaz.load("anchors"), "spine", origin="anchors.yaml")
    for revision in gaz.as_sequence(spine, "revisions", origin="anchors.yaml/spine"):
        ref = revision.get("driven_by_event")
        if ref is not None:
            return str(ref)
    raise gaz.GazetteerError(
        "anchors.yaml declares no spine revision driven by an event. The 2013 seal fire writing "
        "the setpoint is the corpus's protagonist fact."
    )
