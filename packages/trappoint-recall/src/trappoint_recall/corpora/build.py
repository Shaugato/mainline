# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""The gold-set build: inputs in, G1/G2/G3/G4 + negative control + panel + GS0 out.

One function, :func:`build_goldsets`, drives the whole pipeline, and
``scripts/recall/build_goldsets.py`` is a thin argument parser over it. The orchestration
lives in the package rather than in the script so that it is importable by tests, typed
under mypy strict, and covered by the same review as everything else.

The build is **idempotent**: same inputs and same seed produce byte-identical outputs, and
``--check`` rebuilds into a temporary directory and diffs. That property is what makes the
committed gold sets reviewable — a diff means the data changed, never that a dictionary
iterated differently.

GS0 — the corpus the harness measures
--------------------------------------
GS0 is the union of the G4 retro permits and the routine replay, judged by G4's
distant supervision **overlaid** with G3's adjudicated human labels. G2 is excluded by
construction, not by filter: a calibrator-only label has no business inside a corpus a
release gate reads, and the invariant suite asserts its absence.

Where GS0 is written, and why not ``tests/fixtures/recall/gs0``
----------------------------------------------------------------
``tests/eval/recall/corpus_resolution.py`` will auto-select a corpus at
``tests/fixtures/recall/gs0``. GS0 is deliberately **not** written there. The harness's
satisfiability suite drives ``oracles.ShoutingBackend``, which fabricates distractor
document ids (``E-NEAR-<suffix>``, ``E-RELATED-<suffix>-a`` …) that exist only in the
harness's own self-test corpus. On a corpus with real regulator identifiers those
fabricated ids are unjudged, ``P@block`` skips them, and an indiscriminate blocker would
score 1.00 — turning a green test that proves the noise gates bite into a red one. Rather
than fabricate corpus documents to satisfy a test double, GS0 ships at
``goldsets/gs0`` and is opted into with ``TRAPPOINT_RECALL_CORPUS``.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Final

from trappoint_recall.corpora import g1_citations, g2_codes, g3_adjudicated, g4_retro
from trappoint_recall.corpora.canonical import digest_hex
from trappoint_recall.corpora.csb import load_au_regulator_alerts, load_csb_reports
from trappoint_recall.corpora.emit import (
    GoldSetMeta,
    overlay_judgements,
    write_json,
    write_jsonl,
    write_qrels,
)
from trappoint_recall.corpora.model import EventRecordSet
from trappoint_recall.corpora.msha import load_fatality_reports, parse_part50
from trappoint_recall.corpora.negative_control import synthesise_routine_replay
from trappoint_recall.corpora.panel import build_panel, save_panel
from trappoint_recall.corpora.provenance import (
    FixtureProvenance,
    FixtureRef,
    ProvenanceManifest,
    assert_harness_only,
    file_sha256,
)
from trappoint_recall.corpora.synthetic import CORPUS_GENESIS, DEFAULT_SEED, generate
from trappoint_recall.eval.corpus import EvalQuery
from trappoint_recall.eval.qrels import Judgement

__all__ = [
    "FIXTURE_LAYOUT",
    "BuildResult",
    "build_goldsets",
    "load_inputs",
    "regenerate_fixtures",
]

FIXTURE_LAYOUT: Final[Mapping[str, str]] = {
    "part50": "inputs/msha_part50.psv",
    "fatality_reports": "inputs/msha_fatality_reports.jsonl",
    "csb_reports": "inputs/csb_reports.jsonl",
    "au_alerts": "inputs/au_regulator_alerts.jsonl",
    "adjudication": "inputs/g3_adjudication.jsonl",
}
"""Where the committed inputs live, relative to the fixtures root."""

_ROUTINE_LIMIT: Final = 300
_G3_TRUTH_PAIRS: Final = 34
_G3_NEIGHBOUR_PAIRS: Final = 16
_LLM_MODEL_ID: Final = "claude-opus-5"
_LLM_PROMPT_VERSION: Final = "umbrela-recall-v1"

SYNTHETIC_PROVENANCE: Final = FixtureProvenance(
    corpus_class="synthetic_replica",
    tenant_use="harness_only",
    source_name="MAINLINE synthetic replica corpus",
    licence="Apache-2.0",
    generator=f"trappoint_recall.corpora.synthetic:{DEFAULT_SEED}",
    notes=(
        "Invented records shaped like MSHA Part 50 extracts, MSHA fatality investigation "
        "reports, CSB reports and Australian state-regulator alerts. No real incident, no "
        "real person, no real operation. harness_only even though it is synthetic: a "
        "corpus that models fatalities has no place in a demo tenant either."
    ),
)

PERMIT_PROVENANCE: Final = FixtureProvenance(
    corpus_class="synthetic_permit",
    tenant_use="harness_only",
    source_name="MAINLINE routine-permit replay",
    licence="Apache-2.0",
    generator="trappoint_recall.corpora.negative_control",
    notes=(
        "No real permit corpus exists to draw from and one would be commercially "
        "confidential if it did. The replay draws its sites, activity paths and asset "
        "classes from the incident corpus so the nuisance denominator is adversarial."
    ),
)


def _read_jsonl(path: Path) -> tuple[dict[str, object], ...]:
    rows: list[dict[str, object]] = []
    if not path.is_file():
        raise FileNotFoundError(f"required input not found: {path}")
    with path.open("r", encoding="utf-8") as handle:
        for lineno, raw in enumerate(handle, start=1):
            line = raw.strip()
            if not line or line.startswith("//"):
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"{path}:{lineno}: not valid JSON: {exc}") from exc
            if not isinstance(payload, dict):
                raise TypeError(f"{path}:{lineno}: expected a JSON object")
            rows.append(payload)
    return tuple(rows)


@dataclass(frozen=True, slots=True)
class BuildResult:
    """Everything the build produced, plus the report that describes it."""

    records: EventRecordSet
    g1: g1_citations.CitationResolution
    g1_judgements: tuple[Judgement, ...]
    g2_judgements: tuple[Judgement, ...]
    g2_report: g2_codes.G2Report
    g3: g3_adjudicated.G3Result
    g4: g4_retro.G4Result
    routine: tuple[EvalQuery, ...]
    gs0_queries: tuple[EvalQuery, ...]
    gs0_judgements: tuple[Judgement, ...]
    corpus_commit: str
    report: Mapping[str, object]


def load_inputs(root: Path, *, provenance: FixtureProvenance) -> EventRecordSet:
    """Load all four corpora from a fixtures or cache root and merge them.

    Raises:
        FileNotFoundError: naming the first missing input. The build never silently
            proceeds on three corpora out of four: a gold set missing a whole corpus is a
            different gold set, not a smaller one.
    """
    part50 = parse_part50(
        root / FIXTURE_LAYOUT["part50"],
        provenance=provenance,
        corpus_commit_at=CORPUS_GENESIS,
    )
    fatalities = load_fatality_reports(
        _read_jsonl(root / FIXTURE_LAYOUT["fatality_reports"]),
        provenance=provenance,
        corpus_commit_at=CORPUS_GENESIS,
    )
    csb = load_csb_reports(
        _read_jsonl(root / FIXTURE_LAYOUT["csb_reports"]),
        provenance=provenance,
        corpus_commit_at=CORPUS_GENESIS,
    )
    alerts = load_au_regulator_alerts(
        _read_jsonl(root / FIXTURE_LAYOUT["au_alerts"]),
        provenance=provenance,
        corpus_commit_at=CORPUS_GENESIS,
    )
    merged = part50.merged_with(fatalities, source="msha")
    merged = merged.merged_with(csb, source="msha+csb")
    return merged.merged_with(alerts, source="msha+csb+au")


def _corpus_commit(records: EventRecordSet) -> str:
    """A digest over the record identities and their three timestamps.

    Not a git commit: this package must be usable against a corpus that has never seen
    this repository. It is a *corpus state*, which is what
    :class:`~trappoint_recall.eval.splits.SplitPolicy` asks for.
    """
    return "sha256:" + digest_hex(
        [
            [
                r.external_ref,
                r.occurred_at.isoformat(),
                r.ingested_at.isoformat(),
                r.corpus_commit_at.isoformat(),
                r.severity_actual,
            ]
            for r in sorted(records, key=lambda r: r.external_ref)
        ]
    )


def _g3_from_g4(
    g4: g4_retro.G4Result, records: EventRecordSet
) -> tuple[tuple[g3_adjudicated.AdjudicationItem, ...], tuple[dict[str, object], ...]]:
    """Derive the adjudication worksheet and its confirmations from the retro pairs.

    Which pairs are adjudicated is a sampling decision and it is stated here rather than
    randomised: the truth pair of the first :data:`_G3_TRUTH_PAIRS` retro permits, then
    :data:`_G3_NEIGHBOUR_PAIRS` grade-2 neighbours. Truth pairs are never left unconfirmed
    and never graded below 2 — a downgraded truth pair would make the corpus refuse to
    load, and burying that decision in a random draw would make the refusal intermittent.
    """
    by_query = {p.query_id: p for p in g4.permits}
    truth_pairs: list[tuple[str, str, int]] = []
    neighbour_pairs: list[tuple[str, str, int]] = []
    for judgement in sorted(g4.judgements, key=lambda j: (j.query_id, -j.grade, j.doc_id)):
        permit = by_query.get(judgement.query_id)
        if permit is None:
            continue
        if judgement.doc_id == permit.truth_doc_id:
            truth_pairs.append((judgement.query_id, judgement.doc_id, 3))
        elif judgement.grade == 2:
            neighbour_pairs.append((judgement.query_id, judgement.doc_id, 2))

    selected = truth_pairs[:_G3_TRUTH_PAIRS] + neighbour_pairs[:_G3_NEIGHBOUR_PAIRS]

    items: list[g3_adjudicated.AdjudicationItem] = []
    rows: list[dict[str, object]] = []
    for index, (query_id, doc_id, human_grade) in enumerate(selected):
        permit = by_query[query_id]
        document = records.get(doc_id)
        if document is None:  # pragma: no cover - pairs come from the corpus
            continue
        is_truth = doc_id == permit.truth_doc_id
        # The LLM pre-label is deliberately generous on a slice of the neighbours: UMBRELA
        # reports exactly that bias, and a fixture where the model always agreed would make
        # the llm_more_generous counter untestable.
        llm_grade = human_grade
        if not is_truth and index % 5 == 1:
            llm_grade = min(3, human_grade + 1)
        elif not is_truth and index % 7 == 3:
            llm_grade = max(0, human_grade - 1)
        item = g3_adjudicated.AdjudicationItem(
            pair_id=f"G3-{index + 1:04d}",
            query_id=query_id,
            doc_id=doc_id,
            query_text=permit.text,
            doc_text=(document.work_description or document.narrative)[:1200],
            llm_grade=llm_grade,
            llm_rationale=(
                f"Shares the {document.hazard_energy} energy release and the coded "
                f"classification {document.coded.accident_classification!r} with the permit "
                "scope; the precondition is named in the work description."
            ),
            model_id=_LLM_MODEL_ID,
            prompt_version=_LLM_PROMPT_VERSION,
        )
        items.append(item)
        row = dict(item.worksheet_row())
        if not is_truth and index % 11 == 6:
            # Unconfirmed: stays an LLM label, tagged and refused by P@block.
            pass
        elif not is_truth and index % 13 == 9:
            # Two raters, no agreement, no adjudicator: excluded and counted.
            row.update(
                {
                    "rater_a": "adjudicator-a",
                    "grade_a": human_grade,
                    "rater_b": "adjudicator-b",
                    "grade_b": max(0, human_grade - 1),
                }
            )
        elif not is_truth and index % 9 == 4:
            # Two raters disagree, adjudicator breaks the tie.
            row.update(
                {
                    "rater_a": "adjudicator-a",
                    "grade_a": human_grade,
                    "rater_b": "adjudicator-b",
                    "grade_b": max(0, human_grade - 1),
                    "adjudicator": "adjudicator-c",
                    "grade_final": human_grade,
                    "confirmed_at": "2026-02-14T00:00:00+00:00",
                }
            )
        else:
            row.update(
                {
                    "rater_a": "adjudicator-a",
                    "grade_a": human_grade,
                    "rater_b": "adjudicator-b",
                    "grade_b": human_grade,
                    "confirmed_at": "2026-02-14T00:00:00+00:00",
                }
            )
        rows.append(row)
    return tuple(items), tuple(rows)


def build_goldsets(
    fixtures_root: Path,
    out_root: Path,
    *,
    provenance: FixtureProvenance = SYNTHETIC_PROVENANCE,
    destination_use: str = "harness_only",
    seed: str = DEFAULT_SEED,
) -> BuildResult:
    """Build every gold set from the committed inputs and write them under ``out_root``.

    Args:
        fixtures_root: Directory holding ``inputs/``.
        out_root: Where ``goldsets/``, ``goldsets/gs0/`` and ``thymogate_panel.json`` go.
        provenance: Travels onto every artefact.
        destination_use: ``harness_only`` or ``demo_tenant``. Real regulator data with a
            demo destination is refused outright.
        seed: Seed recorded in the build report.

    Returns:
        :class:`BuildResult`.

    Raises:
        DemoTenantContamination: if real regulator data is being built for a demo tenant.
    """
    if destination_use != "harness_only":
        assert_harness_only(provenance, context=f"building gold sets for {destination_use}")

    records = load_inputs(fixtures_root, provenance=provenance)
    corpus_commit = _corpus_commit(records)

    raw_citations = g1_citations.citations_of(records.records)
    resolution = g1_citations.resolve_citations(raw_citations, records)
    g1_judgements = g1_citations.build_g1_judgements(resolution)

    g2_pairs, g2_report = g2_codes.build_g2_pairs(records)
    g2_judgements = g2_codes.build_g2_judgements(g2_pairs, records)

    g4 = g4_retro.build_g4(records, resolution, corpus_commit=corpus_commit)

    adjudication_rows = _read_jsonl(fixtures_root / FIXTURE_LAYOUT["adjudication"])
    items = g3_adjudicated.worksheet_items_from_rows(adjudication_rows)
    confirmations = tuple(
        g3_adjudicated.Confirmation.model_validate(row) for row in adjudication_rows
    )
    g3 = g3_adjudicated.ingest_confirmations(items, confirmations)

    head = max(r.corpus_commit_at for r in records) + timedelta(days=1)
    control = synthesise_routine_replay(records, end=head, limit=_ROUTINE_LIMIT)

    panel = build_panel(g4.permits, records, corpus_commit=corpus_commit)

    # GS0: G4's distant supervision, overlaid with G3's adjudicated human labels.
    query_ids = {p.query_id for p in g4.permits}
    g3_for_gs0 = tuple(j for j in g3.judgements if j.query_id in query_ids)
    gs0_judgements = overlay_judgements(g4.judgements, g3_for_gs0)
    gs0_queries = (*g4.queries, *control.permits)

    written = _write_all(
        out_root,
        records=records,
        resolution=resolution,
        g1_judgements=g1_judgements,
        g2_judgements=g2_judgements,
        g2_report=g2_report,
        g3=g3,
        g4=g4,
        control_permits=control.permits,
        gs0_queries=gs0_queries,
        gs0_judgements=gs0_judgements,
        panel=panel,
        corpus_commit=corpus_commit,
        head=head,
        provenance=provenance,
    )

    report: dict[str, object] = {
        "seed": seed,
        "corpus_commit": corpus_commit,
        "provenance": provenance.model_dump(mode="json"),
        "loaders": records.report.to_dict(),
        "g1_citations": {
            **resolution.to_dict(),
            "n_judgements": len(g1_judgements),
            "note": (
                "Unresolvable citations are dropped by reason and never guessed. "
                "no_identifier means the investigator cited a prior incident without "
                "naming one; resolving it by proximity would manufacture ground truth."
            ),
        },
        "g2_codes": {
            **g2_report.to_dict(),
            "n_judgements": len(g2_judgements),
            "calibrator_only": True,
            "grade": g2_codes.G2_GRADE,
        },
        "g3_adjudicated": g3.report.to_dict(),
        "g4_retro": g4.report.to_dict(),
        "negative_control": control.report.to_dict(),
        "thymogate_panel": {
            "panel_id": panel.panel_id,
            "panel_digest": panel.digest,
            "panel_size": len(panel.ordered_items),
            "hazard_coverage": dict(panel.hazard_coverage),
            "scope_levels": sorted({i.scope_level for i in panel.ordered_items}),
        },
        "gs0": {
            "n_queries": len(gs0_queries),
            "n_retro": len(g4.permits),
            "n_routine": len(control.permits),
            "n_judgements": len(gs0_judgements),
            "n_blinded_human": sum(
                1 for j in gs0_judgements if j.blinded and j.judged_by == "human"
            ),
            "gold_sets_present": sorted({j.gold_set for j in gs0_judgements}),
        },
        "files": [str(p.relative_to(out_root)).replace("\\", "/") for p in written],
    }
    write_json(out_root / "goldsets" / "build_report.json", report)

    return BuildResult(
        records=records,
        g1=resolution,
        g1_judgements=g1_judgements,
        g2_judgements=g2_judgements,
        g2_report=g2_report,
        g3=g3,
        g4=g4,
        routine=control.permits,
        gs0_queries=gs0_queries,
        gs0_judgements=gs0_judgements,
        corpus_commit=corpus_commit,
        report=report,
    )


def _write_all(
    out_root: Path,
    *,
    records: EventRecordSet,
    resolution: g1_citations.CitationResolution,
    g1_judgements: Sequence[Judgement],
    g2_judgements: Sequence[Judgement],
    g2_report: g2_codes.G2Report,
    g3: g3_adjudicated.G3Result,
    g4: g4_retro.G4Result,
    control_permits: Sequence[EvalQuery],
    gs0_queries: Sequence[EvalQuery],
    gs0_judgements: Sequence[Judgement],
    panel: object,
    corpus_commit: str,
    head: datetime,
    provenance: FixtureProvenance,
) -> list[Path]:
    goldsets = out_root / "goldsets"
    written: list[Path] = []

    written.append(
        write_qrels(
            goldsets / "g1_citations.qrels.jsonl",
            g1_judgements,
            GoldSetMeta(
                gold_set=g1_citations.G1_GOLD_SET,
                calibrator_only=False,
                headline_forbidden_reason=(
                    "G1 may be reported for recall. It is not blinded, so p_at_block skips "
                    "it: a citation establishes a shared mechanism, not that a supervisor "
                    "would have been shown the incident."
                ),
                n_judgements=len(g1_judgements),
                basis="distant supervision from investigator citations",
                provenance=provenance,
                build=resolution.to_dict(),
            ),
        )
    )
    written.append(
        write_qrels(
            goldsets / "g2_codes.qrels.jsonl",
            g2_judgements,
            GoldSetMeta(
                gold_set=g2_codes.G2_GOLD_SET,
                calibrator_only=True,
                headline_forbidden_reason=(
                    "Same accident classification + injury source + equipment is a "
                    "plausible pair, not a relevant one. A precision figure over G2 "
                    "measures the coding manual. Calibrator only."
                ),
                n_judgements=len(g2_judgements),
                basis="structured-code co-membership",
                provenance=provenance,
                build=g2_report.to_dict(),
            ),
        )
    )
    written.append(
        write_qrels(
            goldsets / "g3_adjudicated.qrels.jsonl",
            g3.judgements,
            GoldSetMeta(
                gold_set=g3_adjudicated.G3_GOLD_SET,
                calibrator_only=False,
                headline_forbidden_reason=(
                    "Human-confirmed labels are blinded and are the only labels p_at_block "
                    "computes over. Unconfirmed LLM pre-labels in this file are tagged "
                    "judged_by='llm' and blinded=false, and the metric skips them."
                ),
                n_judgements=len(g3.judgements),
                basis="UMBRELA 0-3 pre-labelling with human confirmation",
                provenance=provenance,
                build=g3.report.to_dict(),
            ),
        )
    )
    written.append(
        write_qrels(
            goldsets / "g4_retro.qrels.jsonl",
            g4.judgements,
            GoldSetMeta(
                gold_set=g4_retro.G4_GOLD_SET,
                calibrator_only=False,
                headline_forbidden_reason=(
                    "G4 is the money metric and is reported. Every judgement carries its "
                    "query's time wall, enforced by predicates and re-checked by "
                    "assert_no_leakage."
                ),
                n_judgements=len(g4.judgements),
                basis="retro permits synthesised from the investigation's work description",
                provenance=provenance,
                build=g4.report.to_dict(),
            ),
        )
    )
    written.append(
        write_jsonl(
            goldsets / "g4_retro.queries.jsonl", (q.to_dict() for q in g4.queries)
        )
    )
    written.append(
        write_jsonl(
            goldsets / "g3_worksheet.jsonl",
            (
                {
                    "pair_id": j.query_id + "|" + j.doc_id,
                    "query_id": j.query_id,
                    "doc_id": j.doc_id,
                    "grade": j.grade,
                    "judged_by": j.judged_by,
                    "blinded": j.blinded,
                }
                for j in g3.judgements
            ),
        )
    )
    written.append(
        write_jsonl(
            goldsets / "negative_control.queries.jsonl",
            (q.to_dict() for q in control_permits),
        )
    )

    gs0 = goldsets / "gs0"
    written.append(write_jsonl(gs0 / "queries.jsonl", (q.to_dict() for q in gs0_queries)))
    written.append(
        write_jsonl(gs0 / "qrels.jsonl", (j.model_dump(mode="json") for j in gs0_judgements))
    )
    written.append(
        write_json(
            gs0 / "split.json",
            {
                "kind": "temporally_blocked",
                "wall": head.astimezone(UTC).isoformat(),
                "corpus_commit": corpus_commit,
                "note": (
                    "Corpus-level head. Each retro query additionally carries its own wall "
                    "t, enforced by the predicates occurred_at < t AND ingested_at < t AND "
                    "corpus_commit <= t. AS OF SYSTEM TIME is refused (gc.ttlseconds=4h, "
                    "recall lead D12)."
                ),
            },
        )
    )
    written.append(
        write_json(
            gs0 / "manifest.json",
            {
                "name": "GS0",
                "preliminary": True,
                "synthetic": provenance.corpus_class != "real_regulator",
                "provenance": (
                    f"{provenance.source_name} ({provenance.corpus_class}, "
                    f"{provenance.tenant_use}). Built by "
                    "trappoint_recall.corpora.build.build_goldsets from committed fixtures. "
                    "G2 is excluded by construction: a calibrator-only label has no place "
                    "in a corpus a release gate reads. Retro judgements are distant "
                    "supervision from investigator citations, overlaid with G3's "
                    "human-confirmed blinded labels, which are the only labels p_at_block "
                    "computes over."
                ),
            },
        )
    )

    save_panel(panel, out_root / "thymogate_panel.json")  # type: ignore[arg-type]
    written.append(out_root / "thymogate_panel.json")

    del records
    return written


def regenerate_fixtures(fixtures_root: Path, *, seed: str = DEFAULT_SEED) -> Mapping[str, object]:
    """Write the committed inputs from the deterministic generator.

    Two passes, because the adjudication worksheet is derived from the retro pairs and
    those do not exist until the other three corpora have been loaded and G4 built. The
    second pass is what makes the committed G3 slice reference real pairs instead of
    invented ids.
    """
    corpus = generate(seed)
    inputs = fixtures_root / "inputs"
    inputs.mkdir(parents=True, exist_ok=True)

    part50_path = fixtures_root / FIXTURE_LAYOUT["part50"]
    part50_path.parent.mkdir(parents=True, exist_ok=True)
    with part50_path.open("w", encoding="utf-8", newline="") as handle:
        for line in corpus.part50_lines:
            handle.write(line + "\n")
    from trappoint_recall.corpora.emit import write_license_sidecar

    write_license_sidecar(part50_path)
    write_jsonl(fixtures_root / FIXTURE_LAYOUT["fatality_reports"], corpus.fatality_reports)
    write_jsonl(fixtures_root / FIXTURE_LAYOUT["csb_reports"], corpus.csb_reports)
    write_jsonl(fixtures_root / FIXTURE_LAYOUT["au_alerts"], corpus.au_alerts)

    records = load_inputs(fixtures_root, provenance=SYNTHETIC_PROVENANCE)
    resolution = g1_citations.resolve_citations(
        g1_citations.citations_of(records.records), records
    )
    g4 = g4_retro.build_g4(records, resolution, corpus_commit=_corpus_commit(records))
    _, rows = _g3_from_g4(g4, records)
    write_jsonl(fixtures_root / FIXTURE_LAYOUT["adjudication"], rows)

    return {
        "seed": seed,
        **dict(corpus.summary()),
        "adjudication_pairs": len(rows),
        "records_loaded": len(records),
        "g4_permits": len(g4.permits),
    }


def write_provenance_manifest(
    fixtures_root: Path, *, seed: str = DEFAULT_SEED
) -> ProvenanceManifest:
    """Digest every committed fixture file and write ``provenance.json``.

    The manifest is the artefact the invariant suite checks: every listed file exists,
    every digest matches, and no entry combines real regulator data with a demo
    destination.
    """
    entries: list[FixtureRef] = []
    roles = {
        FIXTURE_LAYOUT["part50"]: "MSHA Part 50 bar-delimited extract (G2 source)",
        FIXTURE_LAYOUT["fatality_reports"]: "Fatality investigation reports (G1/G4 source)",
        FIXTURE_LAYOUT["csb_reports"]: "CSB investigation reports",
        FIXTURE_LAYOUT["au_alerts"]: "Australian state-regulator safety alerts",
        FIXTURE_LAYOUT["adjudication"]: "Returned G3 adjudication worksheet slice",
    }
    for relative, role in roles.items():
        path = fixtures_root / relative
        if not path.is_file():
            raise FileNotFoundError(f"cannot digest a missing fixture: {path}")
        text = path.read_text(encoding="utf-8")
        records = sum(1 for line in text.splitlines() if line.strip())
        if relative.endswith(".psv"):
            records = max(0, records - 1)
        entries.append(
            FixtureRef(
                path=relative,
                sha256=file_sha256(path),
                bytes=path.stat().st_size,
                records=records,
                role=role,
                provenance=(
                    PERMIT_PROVENANCE
                    if "permit" in relative
                    else SYNTHETIC_PROVENANCE
                ),
            )
        )
    manifest = ProvenanceManifest(
        generated_by="trappoint_recall.corpora.build.write_provenance_manifest",
        seed=seed,
        statement=(
            "Real corpora are for the evaluation harness. The demo tenant is synthetic. A "
            "real fatality is never presented as a fictional site's record. Every fixture "
            "below is a synthetic replica; the real corpora are fetched by "
            "scripts/recall/fetch_corpora.py into a gitignored cache and are never "
            "committed. corpus_class='real_regulator' with tenant_use='demo_tenant' is "
            "refused at construction time, not warned about."
        ),
        files=tuple(entries),
    )
    write_json(fixtures_root / "provenance.json", manifest.model_dump(mode="json"))
    return manifest
