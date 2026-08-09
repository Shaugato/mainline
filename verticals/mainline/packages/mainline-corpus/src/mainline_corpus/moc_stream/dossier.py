# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""One row per change request: what it declares, what it did, and what should refuse it.

The dossier is corpus scaffolding — ``table: null``, loaded nowhere — and it exists for two
consumers.

``corpus-freeze-load``'s integration test needs to know, *without asking the database*, which
change requests carry a blood-written clause in their declared scope.  Comparing that prediction
against the projection the triggers actually derive is the one test that can catch a corpus which
disagrees with itself, and it only works if the prediction is computed independently.

``demo-harness``'s preflight needs the same list, so a beat can be re-pointed at a different MOC
without re-reading the whole answer key on capture day.

── THE FIELD THAT NEEDS ITS NAME DEFENDED ───────────────────────────────────────────────────────
``precursor_severity_max_from_answer_key`` is the highest ``severity_gate`` among the blame edges
GS0 holds against this change request's declared clauses.  It is deliberately not called
``sev_max``: ``sev_max`` is a projected column of ``mainline.clause_version``, written by a
trigger from ``clause_blame_closure`` and readable by a gate.  This is a prediction written down
so the projection can be checked against it.  If the two ever disagree the corpus is wrong, and
that is the correct place for the disagreement to surface — one hop earlier and it would be a
loader writing the number the gate reads, which is the defect class this product exists to
eliminate.
"""

from __future__ import annotations

from collections.abc import Sequence

from ..blame.build import AnswerKey
from ..blame.model import BlameEdge
from .lifecycle import LifecycleResult
from .model import MocDossier
from .scope import ScopeResult

__all__ = ["build_dossiers"]


def _edges_by_clause(edges: Sequence[BlameEdge]) -> dict[str, tuple[BlameEdge, ...]]:
    grouped: dict[str, list[BlameEdge]] = {}
    for edge in edges:
        grouped.setdefault(edge.clause_key, []).append(edge)
    return {
        clause_key: tuple(sorted(items, key=lambda item: (item.event_ref, item.basis)))
        for clause_key, items in grouped.items()
    }


def build_dossiers(
    key: AnswerKey, scope: ScopeResult, lifecycle: LifecycleResult
) -> tuple[MocDossier, ...]:
    """Roll every change request up against its scope, its plan and the answer key."""
    by_clause = _edges_by_clause(key.causality.edges)
    weakening_steps: dict[str, int] = {}
    for chain in key.chains:
        for step in chain.steps:
            if step.change_intent == "weaken":
                weakening_steps[step.change_ref] = weakening_steps.get(step.change_ref, 0) + 1

    out: list[MocDossier] = []
    for cr in sorted(key.skeleton.mocs.change_requests, key=lambda item: item.external_ref):
        declared = scope.for_cr(cr.external_ref)
        acts = lifecycle.for_cr(cr.external_ref)

        relations: dict[str, int] = {}
        bases: dict[str, int] = {}
        for row in declared:
            relations[row.relation] = relations.get(row.relation, 0) + 1
            bases[row.basis] = bases.get(row.basis, 0) + 1

        precursors: set[str] = set()
        severity = 0
        for row in declared:
            for edge in by_clause.get(row.clause_key, ()):
                # An inference that was never adjudicated is not a precursor anybody has to
                # dispose of; `inference_never_blocks` says so in the schema, and a dossier that
                # counted one would over-predict the refusal.
                if edge.state != "active":
                    continue
                precursors.add(edge.event_ref)
                severity = max(severity, edge.severity_gate)

        out.append(
            MocDossier(
                cr_id=cr.cr_id,
                external_ref=cr.external_ref,
                site_id=cr.site_id,
                site_code=cr.site_code,
                ref_name=cr.ref_name,
                target_ref=cr.target_ref,
                intent=cr.intent,
                terminal_state=cr.state,
                anchored=cr.anchored,
                opened_at=cr.opened_at,
                author_sub=cr.author_sub,
                doc_codes=cr.doc_codes,
                clause_count=len(declared),
                relation_histogram=relations,
                basis_histogram=bases,
                realised_scope=bool(declared) and all(row.realised for row in declared),
                weakening_steps=weakening_steps.get(cr.external_ref, 0),
                transition_count=len(acts),
                epoch_bumps=sum(
                    1
                    for act in acts
                    if act.edge
                    in (
                        ("checks_materialised", "checks_materialised"),
                        ("dispositioned", "checks_materialised"),
                    )
                ),
                reopened=any(act.edge == ("dispositioned", "checks_materialised") for act in acts),
                last_transition_at=acts[-1].at if acts else None,
                precursor_events=tuple(sorted(precursors)),
                precursor_severity_max_from_answer_key=severity if precursors else None,
            )
        )

    if not out:
        raise RuntimeError(
            "the change register is empty; stage 1c has nothing to scope, and the change-request "
            "half of the gate (finding S16) would ship with no corpus behind it at all"
        )
    return tuple(out)
