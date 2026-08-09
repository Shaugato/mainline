# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""Stage 1b orchestration: build the causal world, run the injectors, write the answer key.

The order is fixed and each step depends only on what precedes it::

    skeleton              stage 1, rebuilt in memory (deterministic, no I/O beyond the gazetteer)
      -> event index      the one time-ordered view of the timeline
      -> split plans      which eight documents split, and when
      -> clause universe  identities, both numbering schemes, the migrations
      -> weakening chains four clauses, three MOCs each
      -> revision walk    one chronological pass; what each revision touched
      -> orphans          twelve clauses the archive never explains
      -> fleet siblings   nine canonical events written down at three sites each
      -> causality        which event generated which edit, and what the record says
      -> decoys           sixty pairs selected against the true edges
      -> gold set GS0     true, decoy and negative-control rows
      -> emission

Stage 1 is rebuilt rather than read off disk.  It is pure, it takes under two seconds, and a
stage that depended on another worker's output *directory* could not prove its own
reproducibility without first proving theirs.  ``--skeleton`` is accepted anyway, and when given
it is used as a **cross-check**: the rebuilt world's event and document sets must match the ones
on disk, and a mismatch is a refusal naming the first difference.  That turns "we both ran the
same generator" from an assumption into an assertion.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .. import gazetteer as gaz
from .. import rng
from ..injectors import churn, decoys, drift, fleet, orphans, retypeset, split, weakening
from ..skeleton import clock
from ..skeleton import params as skeleton_params
from ..skeleton.build import Skeleton, build_skeleton
from . import causality, clauses, goldset, params, revisions
from .emit import AnswerKeyEmitter, TableSpec
from .eventindex import EventIndex
from .model import PendingField, ProposedRevision

__all__ = ["AnswerKey", "BuildResult", "build_answer_key", "generate"]


@dataclass(frozen=True, slots=True)
class AnswerKey:
    """Everything stage 1b knows, before any of it is written down."""

    skeleton: Skeleton
    index: EventIndex
    universe: clauses.ClauseUniverse
    walk: revisions.RevisionWalk
    causality: causality.CausalityResult
    splits: tuple[split.SplitPlan, ...]
    chains: tuple[weakening.Chain, ...]
    orphans: tuple[orphans.Orphan, ...]
    fleet_groups: tuple[fleet.FleetGroup, ...]
    decoys: tuple[decoys.Decoy, ...]
    gold: tuple[Any, ...]
    proposed: tuple[ProposedRevision, ...]
    churn: dict[str, Any]


@dataclass(frozen=True, slots=True)
class BuildResult:
    out_dir: Path
    counts: dict[str, int]
    file_digests: dict[str, str]
    index_sha256: str
    blame_ratio: float
    basis_histogram: dict[str, int]


def _cross_check(skeleton: Skeleton, skeleton_dir: Path) -> str:
    """Compare the rebuilt stage-1 world against a tree on disk.  Refuse on the first difference."""
    events_path = skeleton_dir / "event.jsonl"
    docs_path = skeleton_dir / "doc_revision.jsonl"
    if not events_path.is_file() or not docs_path.is_file():
        raise FileNotFoundError(
            f"{skeleton_dir} is not a stage-1 tree: event.jsonl or doc_revision.jsonl is missing"
        )
    on_disk_events = {
        str(json.loads(line)["external_ref"])
        for line in events_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    }
    rebuilt_events = {event.external_ref for event in skeleton.events.events}
    if on_disk_events != rebuilt_events:
        only_disk = sorted(on_disk_events - rebuilt_events)[:3]
        only_memory = sorted(rebuilt_events - on_disk_events)[:3]
        raise RuntimeError(
            "the rebuilt stage-1 timeline disagrees with the tree on disk: "
            f"only on disk {only_disk}, only in memory {only_memory}. The answer key would "
            "point at events the corpus does not contain."
        )
    on_disk_revisions = {
        str(json.loads(line)["revision_key"])
        for line in docs_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    }
    rebuilt_revisions = {revision.revision_key for revision in skeleton.documents.revisions}
    if on_disk_revisions != rebuilt_revisions:
        raise RuntimeError(
            "the rebuilt revision cadence disagrees with the tree on disk; every clause revision "
            "in the answer key is keyed to one of these"
        )
    return f"ok: {len(rebuilt_events)} events, {len(rebuilt_revisions)} revisions"


def _proposed_revisions(
    skeleton: Skeleton, universe: clauses.ClauseUniverse, walk: revisions.RevisionWalk
) -> tuple[ProposedRevision, ...]:
    """Emit the 2026 weakening that lives on a branch and never merges.

    This is the film's refusal.  ``MOC-2026-0413`` proposes restoring the OEM setpoint on the
    spine clause; the lattice reads a raise as ``weaken``; the ancestry holds a severity-4 event;
    the merge is refused.  It is emitted in its own file because a proposal that appeared in the
    merged clause revisions would make the refusal a lie — the whole beat is that this change did
    **not** land.
    """
    spine = gaz.as_mapping(gaz.load("anchors"), "spine", origin="anchors.yaml")
    dates = gaz.as_mapping(spine, "dates", origin="anchors.yaml/spine")
    opened = clock.coerce_date(
        dates["weaken_moc_opened"], origin="anchors.yaml/spine/dates/weaken_moc_opened"
    )
    key = universe.spine_clause_key
    clause = universe.by_key[key]
    history = walk.by_clause()[key]
    current = next(
        (row.setpoint_to for row in reversed(history) if row.setpoint_to is not None), None
    )
    if current is None:
        raise RuntimeError("the spine clause carries no setpoint value; the 2026 beat has no delta")
    target = float(spine["setpoint_oem"])
    if current >= target:
        raise RuntimeError(
            f"the spine clause stands at {current} and the 2026 MOC proposes {target}; that is "
            "not a weakening and beat 2 has nothing to refuse"
        )
    change_ref = next(
        entry["external_ref"]
        for entry in gaz.as_sequence(gaz.load("anchors"), "change_requests", origin="anchors.yaml")
        if str(entry.get("intent")) == "weaken"
    )
    del skeleton
    return (
        ProposedRevision(
            ref_name=f"cr/{change_ref}",
            cr_external_ref=str(change_ref),
            clause_key=key,
            clause_uuid=clause.clause_uuid,
            site_id=clause.site_id,
            doc_code=universe.doc_code_at(key, opened),
            proposed_on=opened,
            control_delta="weaken",
            delta_basis="lattice",
            setpoint_key=clause.setpoint_key,
            setpoint_from=current,
            setpoint_to=target,
            rationale_kind="spurious_trips_at_summer_ambient",
        ),
    )


#: ``reason_code -> (table, column, owner, reason)``.  One string, one place: the register
#: carries the code on every row and ``pending_reasons.json`` carries the prose once.
PENDING_REASONS: dict[str, tuple[str, str, str, str]] = {
    "clause.birth_commit": (
        "mainline.clause",
        "birth_commit",
        "the worker that mints the commit DAG (commit_obj / commit_edge / ref)",
        (
            "commit_id is sha256 over the JCS envelope and cannot be chosen. Nothing in the "
            "corpus lane mints commits, so every clause points at a commit that does not exist "
            "yet and says so rather than inventing thirty-two bytes."
        ),
    ),
    "clause_version.canon_text": (
        "mainline.clause_version",
        "canon_text",
        "corpus-render-cache",
        (
            "History first, text second. raw_text, canon_sha256 and anchor_set follow from the "
            "same act of rendering this clause and are closed with it. Every offset in this "
            "system is into canon_text, so a digest of anything else would make every span in "
            "the corpus point at the wrong sentence."
        ),
    ),
    "blame_edge.commit_id": (
        "mainline.blame_edge",
        "commit_id",
        "the worker that mints the commit DAG (commit_obj / commit_edge / ref)",
        "An edge is bound to the commit that landed the edit, and no commit exists yet.",
    ),
    "blame_edge.p_link": (
        "mainline.blame_edge",
        "p_link",
        "recall lane calibration (isotonic fit on the adjudicated set)",
        (
            "CHECK scored_needs_features requires p_link on every non-asserted basis. It is the "
            "output of a calibration this corpus does not perform; the features it would be "
            "computed from are emitted in full on the edge. Supplying a plausible probability "
            "would launder a calibration one hop upstream, which is the same defect class as "
            "writing a projected column."
        ),
    ),
    "blame_edge.evidence_quote_sha256": (
        "mainline.blame_edge",
        "evidence_quote_sha256",
        "corpus-render-cache",
        (
            "CHECK asserted_needs_quote requires the digest of an exact, unique substring of a "
            "document that has not been rendered. The quote_ref names which sentence to bind; "
            "the corpus does not invent the sentence."
        ),
    ),
    "blame_edge.review_sig": (
        "mainline.blame_edge",
        "review_sig",
        "custody lane (signing credential and cosignature)",
        (
            "CHECK human_needs_signature guards the only column proving a human was in the loop. "
            "A fixture signature would make it unfalsifiable, which is worse than an absent one."
        ),
    ),
}


def _pending_row(code: str, key: str, facts: dict[str, Any]) -> PendingField:
    table, column, owner, _reason = PENDING_REASONS[code]
    return PendingField(
        table=table, key=key, column=column, owner=owner, reason_code=code, facts=facts
    )


def _pending(key: AnswerKey) -> list[PendingField]:
    """Register everything this stage deliberately left null, and who closes it."""
    out: list[PendingField] = []
    for clause in key.universe.clauses:
        out.append(
            _pending_row(
                "clause.birth_commit",
                clause.clause_key,
                {
                    "birth_on": clock.iso_date(clause.birth_on),
                    "origin_doc_code": clause.origin_doc_code,
                },
            )
        )
    for revision in key.walk.revisions:
        out.append(
            _pending_row(
                "clause_version.canon_text",
                revision.key,
                {
                    "control_delta": revision.control_delta,
                    "printed_label": revision.printed_label,
                    "setpoint_to": revision.setpoint_to,
                },
            )
        )
    for edge in key.causality.edges:
        out.append(
            _pending_row("blame_edge.commit_id", edge.key, {"revision_key": edge.revision_key})
        )
        if edge.basis not in ("asserted_document", "asserted_human"):
            out.append(_pending_row("blame_edge.p_link", edge.key, {"basis": edge.basis}))
        if edge.basis == "asserted_document":
            out.append(
                _pending_row(
                    "blame_edge.evidence_quote_sha256",
                    edge.key,
                    {"quote_ref": edge.quote_ref, "quote_ref_kind": edge.quote_ref_kind},
                )
            )
        if edge.basis == "asserted_human":
            out.append(
                _pending_row("blame_edge.review_sig", edge.key, {"reviewed_by": edge.reviewed_by})
            )
    return out


def _spine_document(key: AnswerKey) -> dict[str, Any]:
    """Assemble the spine's dated structural facts as ids and dates only — never as prose.

    ``corpus-spine-authored`` writes every word that appears on camera and
    ``test_camera_strings_agree`` checks the 2013 commit message across four files.  A fifth copy
    of any sentence here would be a fifth thing that can drift, so this document carries keys,
    uuids and dates and nothing a human reads aloud.
    """
    spine = gaz.as_mapping(gaz.load("anchors"), "spine", origin="anchors.yaml")
    dates = gaz.as_mapping(spine, "dates", origin="anchors.yaml/spine")
    clause_key = key.universe.spine_clause_key
    clause = key.universe.by_key[clause_key]
    history = key.walk.by_clause()[clause_key]
    edges = [edge for edge in key.causality.edges if edge.clause_key == clause_key]
    return {
        "clause_key": clause_key,
        "clause_uuid": clause.clause_uuid,
        "clause_uuid_derivation": f'uuid5(CORPUS_NS, "clause:{clause_key}")',
        "dates": {
            name: clock.iso_date(clock.coerce_date(value, origin="spine"))
            for name, value in sorted(dates.items())
        },
        "blame_edges": [
            {
                "basis": edge.basis,
                "channel_a_visible": edge.channel_a_visible,
                "event_ref": edge.event_ref,
                "quote_ref": edge.quote_ref,
                "state": edge.state,
            }
            for edge in edges
        ],
        "label_2011": key.universe.g1_label(clause_key),
        "label_2016": key.universe.g2_label(clause.origin_doc_code, clause_key),
        "label_2019": key.universe.migrations[clause_key].to_label,
        "proposed_2026": [item.to_row() for item in key.proposed],
        "revisions": [
            {
                "control_delta": row.control_delta,
                "doc_code": row.doc_code,
                "effective_on": clock.iso_date(row.effective_on),
                "printed_label": row.printed_label,
                "revision_key": row.revision_key,
                "setpoint_from": row.setpoint_from,
                "setpoint_to": row.setpoint_to,
                "template_generation": row.template_generation,
            }
            for row in history
        ],
        "statement": (
            "One obligation, twenty-two years, three documents and two numbering schemes. The "
            "uuid above is constant across every row of `revisions`; every printed label in that "
            "list is different from at least one other. That is the claim beat 1 shows."
        ),
    }


def build_answer_key(*, skeleton_dir: Path | None = None) -> AnswerKey:
    """Build the whole causal world in memory."""
    skeleton = build_skeleton()
    if skeleton_dir is not None:
        _cross_check(skeleton, skeleton_dir)

    index = EventIndex(skeleton)
    split_plans = split.plan(skeleton)
    universe = clauses.build_universe(skeleton, split_plans)
    chains = weakening.plan(skeleton, universe)
    walk = revisions.materialise(skeleton, universe, split_plans, chains, index)
    orphan_set = orphans.select(universe, walk, index)
    fleet_groups = fleet.plan(universe, walk, index)
    result = causality.author(skeleton, universe, walk, index, orphan_set, fleet_groups)

    true_pairs = [
        {
            "clause_key": edge.clause_key,
            "clause_uuid": edge.clause_uuid,
            "control_class": edge.control_class,
            "event_ref": edge.event_ref,
            "site_code": edge.site_code,
            "site_id": edge.site_id,
        }
        for edge in result.edges
    ]
    decoy_set = decoys.select(index, true_pairs)
    gold = goldset.build_gold_set(universe, result.revisions, result.edges, decoy_set, index)

    ratio = result.blame_ratio
    if not params.BLAME_RATIO_MIN <= ratio <= params.BLAME_RATIO_MAX:
        raise RuntimeError(
            f"blame_edges / clause_versions = {ratio:.3f}, outside "
            f"[{params.BLAME_RATIO_MIN}, {params.BLAME_RATIO_MAX}]. Below the band the corpus "
            "barely exercises the ancestry gate; above it, almost every clause is blood-written "
            "and the refusal stops looking rare. Move P_INCIDENT_DRIVEN, not the band."
        )

    walk_with_causes = revisions.RevisionWalk(
        revisions=result.revisions,
        retypeset_entries=walk.retypeset_entries,
        migration_entries=walk.migration_entries,
        chain_moves=walk.chain_moves,
        retired=walk.retired,
    )
    proposed = _proposed_revisions(skeleton, universe, walk_with_causes)
    churn_report = churn.report(
        skeleton,
        result.revisions,
        result.edges,
        frozenset(item.clause_key for item in orphan_set),
    )
    return AnswerKey(
        skeleton=skeleton,
        index=index,
        universe=universe,
        walk=walk_with_causes,
        causality=result,
        splits=split_plans,
        chains=chains,
        orphans=orphan_set,
        fleet_groups=fleet_groups,
        decoys=decoy_set,
        gold=gold,
        proposed=proposed,
        churn=churn_report,
    )


_SPECS: tuple[TableSpec, ...] = (
    TableSpec(
        "clause.jsonl",
        "mainline.clause",
        lambda row: (str(row["clause_uuid"]),),
        "every obligation; birth_commit is null and registered pending",
    ),
    TableSpec(
        "clause_registry.jsonl",
        None,
        lambda row: (str(row["clause_key"]),),
        "corpus scaffolding: the natural key, control class, setpoint and birth of each clause",
    ),
    TableSpec(
        "clause_revision.jsonl",
        None,
        lambda row: (str(row["revision_key"]), int(row["ordinal"]), str(row["clause_key"])),
        "one row per revision that touched a clause; the structural half of clause_version",
    ),
    TableSpec(
        "proposed_revision.jsonl",
        None,
        lambda row: (str(row["cr_external_ref"]), str(row["clause_key"])),
        "clause changes that live on a branch and never merged; the film's refusal",
    ),
    TableSpec(
        "blame_edge.jsonl",
        "mainline.blame_edge",
        lambda row: (str(row["clause_uuid"]), str(row["event_id"]), str(row["basis"])),
        "the authored causal facts; commit_id, p_link, quote digest and signature are pending",
    ),
    TableSpec(
        "blame_edge_registry.jsonl",
        None,
        lambda row: (str(row["clause_key"]), str(row["event_ref"]), str(row["basis"])),
        "corpus scaffolding: channel labels, the documentary-trace draw, and the generative reason",
    ),
    TableSpec(
        "gs0.jsonl",
        None,
        lambda row: (str(row["clause_key"]), str(row["event_ref"]), str(row["label"])),
        "gold set GS0: one judged (event, clause) pair per row",
    ),
    TableSpec(
        "pending.jsonl",
        None,
        lambda row: (str(row["table"]), str(row["key"]), str(row["column"])),
        "columns this stage deliberately left null, and the worker who closes each one",
    ),
    TableSpec(
        "injector_retypeset.jsonl",
        None,
        lambda row: (str(row["site_code"]), str(row["doc_code"]), str(row["clause_key"])),
        "injector 1: the 2016 reflow, label and ordinal on both sides, identity unchanged",
    ),
    TableSpec(
        "injector_document_split.jsonl",
        None,
        lambda row: (str(row["split_key"]), str(row["clause_key"])),
        "injector 2: which clauses left which document, under which change record",
    ),
    TableSpec(
        "injector_orphan.jsonl",
        None,
        lambda row: (str(row["clause_key"]),),
        "injector 3: clauses with no recorded origin, and the event that actually wrote them",
    ),
    TableSpec(
        "injector_weakening_chain.jsonl",
        None,
        lambda row: (str(row["chain_id"]), int(row["step_index"])),
        "injector 4: three MOCs, one clause, one direction, six years",
    ),
    TableSpec(
        "injector_decoy.jsonl",
        None,
        lambda row: (str(row["decoy_event_ref"]), str(row["clause_key"])),
        "injector 6: same asset and vocabulary, different energy and different failed control",
    ),
    TableSpec(
        "injector_fleet_sibling.jsonl",
        None,
        lambda row: (str(row["group_id"]), str(row["member_site"])),
        "injector 7: one canonical event, three sites, three bonds, one check",
    ),
    TableSpec(
        "injector_vocabulary_drift.jsonl",
        None,
        lambda row: (str(row["concept"]), int(row["era_index"])),
        "injector 8: the dated term-substitution schedule the renderer consumes",
    ),
    TableSpec(
        "injector_drift_pair.jsonl",
        None,
        lambda row: (str(row["pair_key"]),),
        "injector 8: the dated pairs corpus-embed-lift measures lexical against semantic recall on",
    ),
)


def generate(
    out_dir: Path, *, skeleton_dir: Path | None = None, repo_root: Path | None = None
) -> BuildResult:
    """Build the answer key and write it to ``out_dir``."""
    key = build_answer_key(skeleton_dir=skeleton_dir)
    emitter = AnswerKeyEmitter(out_dir=Path(out_dir), repo_root=repo_root)

    payloads: dict[str, list[dict[str, Any]]] = {
        "clause.jsonl": [clause.to_row() for clause in key.universe.clauses],
        "clause_registry.jsonl": [clause.to_registry_row() for clause in key.universe.clauses],
        "clause_revision.jsonl": [row.to_row() for row in key.walk.revisions],
        "proposed_revision.jsonl": [row.to_row() for row in key.proposed],
        "blame_edge.jsonl": [edge.to_row() for edge in key.causality.edges],
        "blame_edge_registry.jsonl": [edge.to_registry_row() for edge in key.causality.edges],
        "gs0.jsonl": [row.to_row() for row in key.gold],
        "pending.jsonl": [item.to_row() for item in _pending(key)],
        "injector_retypeset.jsonl": retypeset.schedule_rows(key.walk.retypeset_entries),
        "injector_document_split.jsonl": split.schedule_rows(key.walk.migration_entries),
        "injector_orphan.jsonl": orphans.schedule_rows(key.orphans),
        "injector_weakening_chain.jsonl": weakening.schedule_rows(key.chains, key.walk.chain_moves),
        "injector_decoy.jsonl": decoys.schedule_rows(key.decoys),
        "injector_fleet_sibling.jsonl": fleet.schedule_rows(key.fleet_groups),
        "injector_vocabulary_drift.jsonl": drift.schedule_rows(),
        "injector_drift_pair.jsonl": drift.pair_rows(),
    }

    digests: dict[str, str] = {}
    counts: dict[str, int] = {}
    for spec in _SPECS:
        record = emitter.write_table(spec, payloads[spec.filename])
        digests[spec.filename] = record.sha256
        counts[spec.filename.removesuffix(".jsonl")] = record.rows

    for filename, body, description in (
        (
            "gs0.schema.json",
            goldset.gs0_schema(),
            "the JSON Schema every gs0.jsonl row validates against",
        ),
        (
            "spine.json",
            _spine_document(key),
            "the spine's ids, labels and dates; no prose, because the prose lives in one place",
        ),
        (
            "injector_author_churn.json",
            key.churn,
            "injector 5: churn measured from stage 1's people, never re-derived",
        ),
        (
            "pending_reasons.json",
            {
                code: {
                    "column": column,
                    "owner": owner,
                    "reason": reason,
                    "table": table,
                }
                for code, (table, column, owner, reason) in PENDING_REASONS.items()
            },
            "the prose behind pending.jsonl's reason_code, written once",
        ),
    ):
        record = emitter.write_document(filename, body, description=description)
        digests[filename] = record.sha256

    label_histogram: dict[str, int] = {}
    for row in key.gold:
        label_histogram[row.label] = label_histogram.get(row.label, 0) + 1

    index_record = emitter.write_index(
        {
            "basis_histogram": key.causality.basis_histogram,
            "blame_ratio": round(key.causality.blame_ratio, 4),
            "channel_a_visible": sum(1 for edge in key.causality.edges if edge.channel_a_visible),
            "corpus_now": clock.iso(clock.NOW),
            "counts": dict(sorted(counts.items())),
            "cross_site_edges": sum(1 for edge in key.causality.edges if edge.cross_site),
            "gazetteer_sha256": gaz.checksum(),
            "generator_version": params.GENERATOR_VERSION,
            "gold_label_histogram": dict(sorted(label_histogram.items())),
            "injector_counts": {
                "decoys": len(key.decoys),
                "fleet_sibling_groups": len(key.fleet_groups),
                "negative_controls": label_histogram.get("negative_control", 0),
                "orphans": len(key.orphans),
                "retypeset_documents": len(
                    {
                        (row["site_code"], row["doc_code"])
                        for row in payloads["injector_retypeset.jsonl"]
                    }
                ),
                "split_documents": len(key.splits),
                "vocabulary_drift_pairs": len(payloads["injector_drift_pair.jsonl"]),
                "weakening_chains": len(key.chains),
            },
            "p_doc_trace_mean": key.causality.p_doc_mean,
            "seed": rng.MASTER_SEED.decode("ascii"),
            "skeleton_generator_version": skeleton_params.GENERATOR_VERSION,
            "stage": "blame",
            "state_histogram": key.causality.state_histogram,
        }
    )

    return BuildResult(
        out_dir=Path(out_dir),
        counts=dict(sorted(counts.items())),
        file_digests=dict(sorted(digests.items())),
        index_sha256=index_record.sha256,
        blame_ratio=round(key.causality.blame_ratio, 4),
        basis_histogram=key.causality.basis_histogram,
    )
