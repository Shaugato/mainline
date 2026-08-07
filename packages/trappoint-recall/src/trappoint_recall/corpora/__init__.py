# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""Corpora and gold sets — the ground truth the whole recall domain is scored against.

Four corpora, normalised to one record shape:

``msha.parse_part50``          bar-delimited Part 50 extracts. Wide, coded, and terse:
                               ``NARRATIVE`` is ``VARCHAR2(384)``, which is why G2 lives
                               here and G1/G4 do not.
``msha.load_fatality_reports`` fatality investigation reports. The rich material, and the
                               source of the investigator citations G1 is built from.
``csb.load_csb_reports``       CSB investigation reports; severity from casualty counts.
``csb.load_au_regulator_alerts`` state-regulator alerts; severity from the regulator's
                               own classification.

Four gold sets, plus the negative control and the panel:

``g1_citations``   distant supervision from investigator citations. Resolved by exact
                   identifier plus an anchor check; unresolvable citations are dropped
                   with a counted reason and never guessed.
``g2_codes``       structured-code co-membership, grade 1, **calibrator-only** and
                   forbidden from any headline metric by a flag on the qrels file.
``g3_adjudicated`` UMBRELA 0-3 pre-labelling with a human-confirmation workflow, an
                   inter-rater agreement report, and LLM-only labels tagged so that
                   ``p_at_block`` refuses them.
``g4_retro``       the money metric: a permit synthesised from each fatality
                   investigation's own description of the work, with the time wall *t*
                   attached and enforced by predicates.
``negative_control`` a 24-month replay of routine, uneventful permits — the nuisance-rate
                   denominator.
``panel`` / ``thymogate`` the M5 AIRE-promiscuous panel and its certificate emitter. A
                   configuration that misses any panel item cannot be certified.

Two rules hold the whole subpackage up
---------------------------------------
**Severity is taken, never inferred.** :func:`~trappoint_recall.corpora.model.infer_severity`
exists only to raise, and :class:`~trappoint_recall.corpora.model.EventRecord` refuses a
``model_rated`` basis outright — one hop upstream of the vertical's own
``CHECK model_cannot_arm``.

**Real corpora are for the harness.** The demo tenant is synthetic, and a real fatality is
never presented as a fictional site's record. Enforced by
:class:`~trappoint_recall.corpora.provenance.FixtureProvenance`, which refuses to be
constructed with ``corpus_class='real_regulator'`` and any destination but the harness.
"""

from __future__ import annotations

from trappoint_recall.corpora.canonical import canonical_json, digest_hex
from trappoint_recall.corpora.emit import (
    HEADLINE_FORBIDDEN_GOLD_SETS,
    GoldSetMeta,
    HeadlineUseRefused,
    merge_judgements,
    overlay_judgements,
    read_qrels_meta,
    refuse_headline_use,
    write_qrels,
)
from trappoint_recall.corpora.g1_citations import (
    CitationResolution,
    RawCitation,
    build_g1_judgements,
    extract_citations,
    resolve_citations,
)
from trappoint_recall.corpora.g2_codes import (
    G2_GRADE,
    build_g2_judgements,
    build_g2_pairs,
)
from trappoint_recall.corpora.g3_adjudicated import (
    AdjudicationItem,
    AdjudicationReport,
    Confirmation,
    G3Result,
    emit_worksheet,
    ingest_confirmations,
)
from trappoint_recall.corpora.g4_retro import (
    G4Result,
    RetroPermit,
    TimeWallLeak,
    assert_no_leakage,
    build_g4,
    extract_work_in_progress,
)
from trappoint_recall.corpora.model import (
    HAZARD_ENERGY_CLASSES,
    CodedFields,
    EventRecord,
    EventRecordSet,
    HazardEnergy,
    LoadReport,
    SeverityRefused,
    infer_severity,
)
from trappoint_recall.corpora.negative_control import (
    NegativeControl,
    synthesise_routine_replay,
)
from trappoint_recall.corpora.panel import Panel, PanelItem, build_panel, load_panel, save_panel
from trappoint_recall.corpora.provenance import (
    DemoTenantContamination,
    FixtureProvenance,
    ProvenanceManifest,
    assert_harness_only,
    load_provenance_manifest,
)
from trappoint_recall.corpora.thymogate import (
    PanelOutcome,
    ThymogateCertificate,
    ThymogateRefusal,
    certify,
    certify_sync,
    config_digest,
)

__all__ = [
    "G2_GRADE",
    "HAZARD_ENERGY_CLASSES",
    "HEADLINE_FORBIDDEN_GOLD_SETS",
    "AdjudicationItem",
    "AdjudicationReport",
    "CitationResolution",
    "CodedFields",
    "Confirmation",
    "DemoTenantContamination",
    "EventRecord",
    "EventRecordSet",
    "FixtureProvenance",
    "G3Result",
    "G4Result",
    "GoldSetMeta",
    "HazardEnergy",
    "HeadlineUseRefused",
    "LoadReport",
    "NegativeControl",
    "Panel",
    "PanelItem",
    "PanelOutcome",
    "ProvenanceManifest",
    "RawCitation",
    "RetroPermit",
    "SeverityRefused",
    "ThymogateCertificate",
    "ThymogateRefusal",
    "TimeWallLeak",
    "assert_harness_only",
    "assert_no_leakage",
    "build_g1_judgements",
    "build_g2_judgements",
    "build_g2_pairs",
    "build_g4",
    "build_panel",
    "canonical_json",
    "certify",
    "certify_sync",
    "config_digest",
    "digest_hex",
    "emit_worksheet",
    "extract_citations",
    "extract_work_in_progress",
    "infer_severity",
    "ingest_confirmations",
    "load_panel",
    "load_provenance_manifest",
    "merge_judgements",
    "overlay_judgements",
    "read_qrels_meta",
    "refuse_headline_use",
    "resolve_citations",
    "save_panel",
    "synthesise_routine_replay",
    "write_qrels",
]
