# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""Stage 1 orchestration: build the deterministic world and write it out.

Order matters and is fixed:

    sites -> taxonomy -> assets -> people -> events -> documents -> change requests

``documents`` runs after ``events`` because a revision's *driver* depends on whether a
severity-4-or-worse event landed in the same fonds shortly before it; ``change requests`` run
last because they touch documents.  Nothing runs before ``sites``, because every id in the
corpus hangs off a site.

Two verification passes run before anything is written, and both are cheap:

* ``_verify_citations`` re-checks that every citation in the gazetteer still claims a
  ``REGULATORY_CITATION`` anchor from the *shipped* extractor.  If ``mainline_domain`` is not
  importable the check is skipped and says so in ``index.json`` — never silently.
* ``_verify_severity`` re-derives ``severity_gate`` from ``max(actual, potential_admitted)`` over
  every emitted event and refuses to write a corpus containing a row that would be rejected by
  ``model_cannot_arm``.  The generator already asserts this per row; doing it again over the
  finished set is the difference between "the code intended to" and "the output does".
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .. import gazetteer as gaz
from .. import rng
from . import clock, params
from .assets import AssetWorld, build_assets
from .documents import DocumentWorld, build_documents
from .emit import Emitter, TableSpec
from .events import EventWorld, build_events
from .moc import MocWorld, build_mocs
from .model import PendingField
from .people import PeopleWorld, build_people
from .sites import SiteWorld, build_sites
from .taxonomy import TaxonomyWorld, build_taxonomy

__all__ = ["Skeleton", "SkeletonResult", "build_skeleton", "generate"]


@dataclass(frozen=True, slots=True)
class Skeleton:
    """Everything stage 1 knows, before it is written anywhere."""

    sites: SiteWorld
    taxonomy: TaxonomyWorld
    assets: AssetWorld
    people: PeopleWorld
    events: EventWorld
    documents: DocumentWorld
    mocs: MocWorld
    citation_check: str

    def pending(self) -> list[PendingField]:
        return [*self.sites.pending(), *self.events.pending, *self.mocs.pending]


@dataclass(frozen=True, slots=True)
class SkeletonResult:
    """What the caller gets back: where it went, and what is in it."""

    out_dir: Path
    counts: dict[str, int]
    severity_histogram: dict[str, int]
    file_digests: dict[str, str]
    index_sha256: str


# ── the table specifications ─────────────────────────────────────────────────────────────────

_SPECS: tuple[TableSpec, ...] = (
    TableSpec(
        "site.jsonl",
        "mainline.site",
        lambda row: (str(row["site_code"]),),
        "the four sites; site_role is projected and is registered as pending",
    ),
    TableSpec(
        "site_registry.jsonl",
        None,
        lambda row: (str(row["code"]),),
        "corpus scaffolding: the authored facts about each site that mainline.site has no column for",
    ),
    TableSpec(
        "activity_node.jsonl",
        "mainline.activity_node",
        lambda row: (str(row["site_id"]), int(row["level"]), str(row["label"])),
        "the three-level archival taxonomy; level 1 is frozen and ICMM-MUE-anchored",
    ),
    TableSpec(
        "asset.jsonl",
        None,
        lambda row: (str(row["tag"]),),
        "corpus scaffolding: the asset registry that asset_edge's tags refer to",
    ),
    TableSpec(
        "asset_edge.jsonl",
        "mainline.asset_edge",
        lambda row: (
            str(row["site_id"]),
            str(row["from_tag"]),
            str(row["to_tag"]),
            str(row["kind"]),
        ),
        "the control-dependency / energy graph; edges point from source toward exposure",
    ),
    TableSpec(
        "permit_boundary.jsonl",
        "mainline.permit_boundary",
        lambda row: (str(row["permit_id"]), str(row["asset_tag"])),
        "what the crew declared they isolated on WO-88213",
    ),
    TableSpec(
        "person.jsonl",
        "mainline.person",
        lambda row: (str(row["signer_sub"]), str(row["effective_from"])),
        "the people the record names; ~30 percent carry separated_at",
    ),
    TableSpec(
        "doc.jsonl",
        "mainline.doc",
        lambda row: (str(row["site_id"]), str(row["doc_code"])),
        "36 controlled documents; open_token_count is projected and absent",
    ),
    TableSpec(
        "doc_registry.jsonl",
        None,
        lambda row: (str(row["site_id"]), str(row["doc_code"])),
        "corpus scaffolding: cadence, fonds, template generation and retypeset flags",
    ),
    TableSpec(
        "doc_revision.jsonl",
        None,
        lambda row: (str(row["revision_key"]),),
        "corpus scaffolding: the revision cadence the commit DAG is built from",
    ),
    TableSpec(
        "event.jsonl",
        "mainline.event",
        lambda row: (str(row["external_ref"]),),
        "the incident timeline; narrative and source_sha256 are pending by design",
    ),
    TableSpec(
        "event_registry.jsonl",
        None,
        lambda row: (str(row["external_ref"]),),
        "corpus scaffolding: activity, assets, hazard energy and severity admission per event",
    ),
    TableSpec(
        "control_failure.jsonl",
        "mainline.control_failure",
        lambda row: (str(row["failure_id"]),),
        "ICAM and bowtie normalised to one shape; evidence spans are pending by design",
    ),
    TableSpec(
        "change_request.jsonl",
        "mainline.change_request",
        lambda row: (str(row["external_ref"]),),
        "the MOC stream as a gated subject; the three counters are projected and absent",
    ),
    TableSpec(
        "change_request_registry.jsonl",
        None,
        lambda row: (str(row["external_ref"]),),
        "corpus scaffolding: declared intent, fonds and the documents each MOC touches",
    ),
    TableSpec(
        "pending.jsonl",
        None,
        lambda row: (str(row["table"]), str(row["key"]), str(row["column"])),
        "NOT NULL columns stage 1 deliberately left null, and the worker who fills each one",
    ),
)


def _verify_citations() -> str:
    """Re-check the gazetteer's citations against the shipped anchor extractor.

    Returns a human-readable status that is recorded in ``index.json``.  A skipped check says
    ``skipped``; it never says ``ok``.
    """
    try:
        from mainline_domain.anchors.extract import iter_anchors
    except ImportError as exc:  # pragma: no cover - depends on workspace layout
        return f"skipped: mainline_domain not importable ({exc.__class__.__name__})"

    misses: list[str] = []
    citations = gaz.as_mapping(gaz.load("citations"), "citations", origin="citations.yaml")
    for rows in citations.values():
        for row in rows:
            text = str(row["text"])
            if not any(anchor.cls.name == "REGULATORY_CITATION" for anchor in iter_anchors(text)):
                misses.append(text)
    if misses:
        raise gaz.GazetteerError(
            "citations.yaml contains entries the shipped anchor extractor no longer claims as "
            f"REGULATORY_CITATION: {sorted(set(misses))}. A citation the automaton cannot see is a "
            "citation that produces no identity anchor, which makes every clause comparison in "
            "that fonds fall through to fuzzy text without anything going red."
        )
    return "ok"


def _verify_vocabulary(taxonomy: TaxonomyWorld, assets: AssetWorld) -> None:
    """Cross-check the gazetteer against itself before anything is generated.

    Each of these is a way the vocabulary can drift into a state where the corpus still builds
    and quietly stops testing something:

    * a fonds with no citation produces clauses with no ``REGULATORY_CITATION`` anchor;
    * a fonds with no control class produces events whose ``control_class`` join key is empty,
      so every ``derived_documentary`` blame edge in that branch is unreachable;
    * a setpoint whose ``applies_to_classes`` names a class no asset has is a setpoint no clause
      can ever be written about;
    * a hazard energy outside the closed vocabulary is a ``CHECK`` violation at load time.

    None of these raise on their own later.  They raise here.
    """
    roots = set(taxonomy.roots())
    energies = {
        str(entry["key"])
        for entry in gaz.as_sequence(
            gaz.load("hazard_energies"), "energies", origin="hazard_energies.yaml"
        )
    }
    asset_classes = {asset.asset_class for asset in assets.assets}

    citations = gaz.as_mapping(gaz.load("citations"), "citations", origin="citations.yaml")
    stray = sorted(set(citations) - roots)
    if stray:
        raise gaz.GazetteerError(f"citations.yaml keys are not level-1 codes: {stray}")
    uncited = sorted(roots - set(citations))
    if uncited:
        raise gaz.GazetteerError(
            f"no citation declared for fonds {uncited}; clauses in that branch would carry no "
            "regulatory anchor and every identity comparison there would fall through to text"
        )

    classes = gaz.as_sequence(gaz.load("control_classes"), "classes", origin="control_classes.yaml")
    covered: set[str] = set()
    class_keys: set[str] = set()
    for entry in classes:
        key = str(entry["key"])
        class_keys.add(key)
        declared = {str(item) for item in entry["mue"]}
        if declared - roots:
            raise gaz.GazetteerError(
                f"control class {key} names unknown fonds {sorted(declared - roots)}"
            )
        covered |= declared
        bad = {str(item) for item in entry["hazard_energies"]} - energies
        if bad:
            raise gaz.GazetteerError(f"control class {key} names unknown energies {sorted(bad)}")
    uncontrolled = sorted(roots - covered)
    if uncontrolled:
        raise gaz.GazetteerError(
            f"no control class declared for fonds {uncontrolled}; events there could carry no "
            "control failure and the mechanism join key would be empty for that whole branch"
        )

    setpoints = gaz.as_sequence(gaz.load("setpoints"), "parameters", origin="setpoints.yaml")
    for entry in setpoints:
        key = str(entry["key"])
        if str(entry["control_class"]) not in class_keys:
            raise gaz.GazetteerError(
                f"setpoint {key} names control class {entry['control_class']!r}, which "
                "control_classes.yaml does not declare"
            )
        if str(entry["strengthen_direction"]) not in {"lower", "higher"}:
            raise gaz.GazetteerError(f"setpoint {key} has no usable strengthen_direction")
        orphan = {str(item) for item in entry["applies_to_classes"]} - asset_classes
        if orphan:
            raise gaz.GazetteerError(
                f"setpoint {key} applies to asset classes {sorted(orphan)} that no asset has; "
                "it is a setpoint no clause could ever be written about"
            )

    phrases = gaz.load("phrases")
    stems = gaz.as_mapping(phrases, "title_stems", origin="phrases.yaml")
    missing = sorted(set(params.EVENT_KINDS) - set(stems))
    if missing:
        raise gaz.GazetteerError(f"phrases.yaml declares no title stems for kinds {missing}")
    bands = gaz.as_mapping(phrases, "consequence_bands", origin="phrases.yaml")
    # YAML resolves the band keys to ints; normalise so the check works either way.
    band_levels = {int(level) for level in bands}
    absent = sorted(level for level in range(6) if level not in band_levels)
    if absent:
        raise gaz.GazetteerError(f"phrases.yaml has no consequence band for severities {absent}")


def _verify_severity(events: EventWorld) -> None:
    for event in events.events:
        if event.severity_gate != max(event.severity_actual, event.potential_admitted):
            raise RuntimeError(f"{event.external_ref}: severity_gate is not the max it claims")
        if event.severity_gate >= 4 and event.severity_basis == "model_rated":
            raise RuntimeError(
                f"{event.external_ref}: severity_gate {event.severity_gate} with basis "
                "'model_rated' would be refused by CHECK model_cannot_arm"
            )


def build_skeleton() -> Skeleton:
    """Build the whole deterministic world in memory.  No I/O beyond reading the gazetteer."""
    for name in gaz.FILES:
        gaz.load(name)  # fail fast on a broken vocabulary, before any work

    citation_check = _verify_citations()

    sites = build_sites()
    taxonomy = build_taxonomy(sites)
    assets = build_assets(sites)
    _verify_vocabulary(taxonomy, assets)
    people = build_people(sites)
    events = build_events(sites, taxonomy, assets)
    documents = build_documents(sites, people, events)
    mocs = build_mocs(sites, people, documents)

    _verify_severity(events)
    return Skeleton(sites, taxonomy, assets, people, events, documents, mocs, citation_check)


def generate(out_dir: Path, *, repo_root: Path | None = None) -> SkeletonResult:
    """Build the world and write it to ``out_dir`` as JSONL plus ``index.json``."""
    skeleton = build_skeleton()
    emitter = Emitter(out_dir=Path(out_dir), repo_root=repo_root)

    payloads: dict[str, list[dict[str, Any]]] = {
        "site.jsonl": skeleton.sites.table_rows(),
        "site_registry.jsonl": skeleton.sites.registry_rows(),
        "activity_node.jsonl": skeleton.taxonomy.rows(),
        "asset.jsonl": skeleton.assets.asset_rows(),
        "asset_edge.jsonl": skeleton.assets.edge_rows(),
        "permit_boundary.jsonl": skeleton.assets.boundary_rows(),
        "person.jsonl": skeleton.people.rows(),
        "doc.jsonl": skeleton.documents.rows(),
        "doc_registry.jsonl": skeleton.documents.registry_rows(),
        "doc_revision.jsonl": skeleton.documents.revision_rows(),
        "event.jsonl": skeleton.events.rows(),
        "event_registry.jsonl": skeleton.events.registry_rows(),
        "control_failure.jsonl": skeleton.events.control_failure_rows(),
        "change_request.jsonl": skeleton.mocs.rows(),
        "change_request_registry.jsonl": skeleton.mocs.registry_rows(),
        "pending.jsonl": [item.to_row() for item in skeleton.pending()],
    }

    digests: dict[str, str] = {}
    counts: dict[str, int] = {}
    for spec in _SPECS:
        record = emitter.write(spec, payloads[spec.filename])
        digests[spec.filename] = record.sha256
        counts[spec.filename.removesuffix(".jsonl")] = record.rows

    pending_by_column: dict[str, int] = {}
    for item in skeleton.pending():
        key = f"{item.table}.{item.column}"
        pending_by_column[key] = pending_by_column.get(key, 0) + 1

    index_record = emitter.write_index(
        {
            "asset_graph_version": skeleton.assets.graph_version,
            "citation_anchor_check": skeleton.citation_check,
            "corpus_epoch": clock.iso(clock.EPOCH),
            "corpus_now": clock.iso(clock.NOW),
            "counts": dict(sorted(counts.items())),
            "gazetteer_sha256": gaz.checksum(),
            "generator_version": params.GENERATOR_VERSION,
            "moc_intent_histogram": skeleton.mocs.intent_histogram(),
            "pending_by_column": dict(sorted(pending_by_column.items())),
            "seed": MASTER_SEED_TEXT,
            "separated_fraction": round(skeleton.people.separated_fraction, 4),
            "severity_gate_histogram": skeleton.events.histogram(),
            "stage": "skeleton",
            "under_declared": {
                ref: list(tags) for ref, tags in sorted(skeleton.assets.under_declared.items())
            },
        }
    )

    return SkeletonResult(
        out_dir=Path(out_dir),
        counts=dict(sorted(counts.items())),
        severity_histogram=skeleton.events.histogram(),
        file_digests=dict(sorted(digests.items())),
        index_sha256=index_record.sha256,
    )


#: The seed as it is written down everywhere else — ``corpus.lock.json`` quotes ``"0xMAINLINE"``.
MASTER_SEED_TEXT: str = rng.MASTER_SEED.decode("ascii")
