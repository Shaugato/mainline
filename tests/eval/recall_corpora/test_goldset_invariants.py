# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""The invariants a gold set must satisfy before any number computed on it means anything.

Six of them, and each one exists because of a specific way a retrieval evaluation quietly
becomes fiction:

1. **No gold pair leaks across the time wall.** A judged document that post-dates its
   query is the retriever being scored on its own future. Checked against every judgement,
   with all three predicates, and checked again by injecting a leak and requiring the
   builder to refuse it.
2. **G2 is calibrator-only.** The flag is on the file, the grade is below the relevance
   floor, the labels are unblinded, and GS0 contains none of them. Four barriers, because
   the failure mode — a precision figure that is really a measurement of the coding
   manual — is silent.
3. **Severity is never model-rated.** Refused at record construction, and the function
   that would infer it exists only to raise.
4. **Every qrels file validates against the published schema**, checked twice: once with
   an independent walk of the JSON Schema document, once through the Pydantic model the
   schema was generated from.
5. **The panel covers all eight hazard-energy classes** at mixed archival levels, and a
   configuration that misses any member cannot be certified.
6. **Fixture provenance is real and enforced.** Real regulator data may never carry a demo
   destination, every committed fixture's digest matches, and the corpus a demo would load
   says what it is.

Several assertions are written as *negative constructions* — build the violating object
and require an exception. Those are the ones that stay honest when someone deletes a
guard: an assertion about data passes vacuously once the data changes, while an assertion
that a refusal happens fails the moment the refusal is removed (PL-2).
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from corpora_paths import FIXTURES, GOLDSETS, GS0, QRELS_FILES
from trappoint_recall.corpora import g1_citations, g2_codes, g3_adjudicated, g4_retro
from trappoint_recall.corpora.build import (
    SYNTHETIC_PROVENANCE,
    build_goldsets,
    load_inputs,
)
from trappoint_recall.corpora.emit import (
    HEADLINE_FORBIDDEN_GOLD_SETS,
    META_PREFIX,
    HeadlineUseRefused,
    read_qrels_meta,
    refuse_headline_use,
)
from trappoint_recall.corpora.model import (
    HAZARD_ENERGY_CLASSES,
    CodedFields,
    EventRecord,
    EventRecordSet,
    SeverityRefused,
    infer_severity,
)
from trappoint_recall.corpora.panel import Panel
from trappoint_recall.corpora.provenance import (
    DemoTenantContamination,
    FixtureProvenance,
    ProvenanceManifest,
    assert_harness_only,
    file_sha256,
)
from trappoint_recall.corpora.thymogate import (
    PanelOutcome,
    ThymogateCertificate,
    ThymogateRefusal,
    certify_sync,
    config_digest,
)
from trappoint_recall.eval.backend import NullBackend, ScoredCandidate
from trappoint_recall.eval.corpus import EvalCorpus, EvalQuery
from trappoint_recall.eval.qrels import (
    BLOCKING_RELEVANCE_FLOOR,
    Judgement,
    load_qrels_jsonl,
    qrels_json_schema,
)
from trappoint_recall.eval.splits import SplitPolicy

MAX_FIXTURE_BYTES = 5 * 1024 * 1024
"""The committed corpora fixtures budget. A fixture tree nobody can clone is not a fixture."""


# ======================================================================================
# 1. The time wall
# ======================================================================================


def _g4_walls() -> Mapping[str, datetime]:
    walls: dict[str, datetime] = {}
    with (GOLDSETS / "g4_retro.queries.jsonl").open("r", encoding="utf-8") as handle:
        for raw in handle:
            line = raw.strip()
            if not line or line.startswith("//"):
                continue
            payload = json.loads(line)
            walls[str(payload["query_id"])] = datetime.fromisoformat(str(payload["wall"]))
    return walls


def test_no_g4_judgement_crosses_its_query_time_wall(records: EventRecordSet) -> None:
    """The money metric's ground truth must be invisible from the wrong side of *t*.

    All three predicates, conjunctively: ``occurred_at < t``, ``ingested_at < t``,
    ``corpus_commit <= t``. Any one alone is a leak — a report *published* after the
    fatality it would have prevented is a document from that permit's future even though
    the incident it describes happened before.
    """
    walls = _g4_walls()
    qrels = load_qrels_jsonl(GOLDSETS / "g4_retro.qrels.jsonl")
    commit = json.loads((GS0 / "split.json").read_text(encoding="utf-8"))["corpus_commit"]
    leaks: list[str] = []
    for judgement in qrels:
        wall = walls.get(judgement.query_id)
        assert wall is not None, f"{judgement.query_id}: judgement with no retro permit"
        record = records.get(judgement.doc_id)
        assert record is not None, f"{judgement.doc_id}: judged document is not in the corpus"
        reason = SplitPolicy(wall=wall, corpus_commit=commit).rejection_reason(
            record.to_split_record()
        )
        if reason is not None:
            leaks.append(f"{judgement.query_id} -> {judgement.doc_id}: {reason}")
    assert not leaks, "gold pairs visible across their own time wall:\n" + "\n".join(leaks[:20])


def test_every_retro_query_has_a_wall_and_it_precedes_the_corpus_head(gs0: EvalCorpus) -> None:
    head = gs0.split_policy.wall
    for query in gs0.by_kind("retro"):
        assert query.wall is not None, f"{query.query_id}: retro query with no wall"
        assert query.wall.tzinfo is not None
        assert query.wall <= head, f"{query.query_id}: wall {query.wall} is after the corpus head"


def test_a_leaking_pair_is_refused_by_the_builder(records: EventRecordSet) -> None:
    """Delete the wall check and this test goes red. That is what it is for.

    A judgement is fabricated for a document that post-dates its query's wall and
    ``assert_no_leakage`` is required to raise. An assertion over the committed data alone
    would pass vacuously the day the guard is removed and the data happens to be clean.
    """
    resolution = g1_citations.resolve_citations(
        g1_citations.citations_of(records.records), records
    )
    commit = "sha256:test"
    result = g4_retro.build_g4(records, resolution, corpus_commit=commit)
    permit = result.permits[0]
    future = max(
        (r for r in records if r.occurred_at > permit.wall),
        key=lambda r: r.occurred_at,
        default=None,
    )
    assert future is not None, "fixture corpus has no record after the first wall"
    poisoned = g4_retro.G4Result(
        permits=result.permits,
        judgements=(
            *result.judgements,
            Judgement(
                query_id=permit.query_id,
                doc_id=future.external_ref,
                grade=3,
                gold_set="G4",
                judged_by="authored",
            ),
        ),
        report=result.report,
    )
    with pytest.raises(g4_retro.TimeWallLeak) as caught:
        g4_retro.assert_no_leakage(poisoned, records, corpus_commit=commit)
    assert "occurred_at >= wall" in str(caught.value)


def test_no_retro_permit_text_contains_the_outcome() -> None:
    """A permit carrying "was fatally crushed" makes Retro-Recall trivial and meaningless.

    This is the single highest-leverage leak in the whole build: it inflates every recall
    number by an amount nobody can estimate afterwards, and it looks completely normal in
    a spot check because the text reads like an incident.
    """
    offenders: list[str] = []
    with (GOLDSETS / "g4_retro.queries.jsonl").open("r", encoding="utf-8") as handle:
        for raw in handle:
            line = raw.strip()
            if not line:
                continue
            payload = json.loads(line)
            text = str(payload["text"]).lower()
            for marker in g4_retro.OUTCOME_MARKERS:
                if marker in text:
                    offenders.append(f"{payload['query_id']}: contains {marker!r}")
                    break
    assert not offenders, "retro permits leak the outcome:\n" + "\n".join(offenders[:20])


def test_work_in_progress_extraction_stops_at_the_outcome() -> None:
    description = (
        "The crew was installing secondary ground support along the number four entry "
        "after a routine inspection identified a change in the immediate roof. The task "
        "had been planned at the pre-shift meeting. A section of the immediate roof "
        "detached and the operator was fatally injured."
    )
    work = g4_retro.extract_work_in_progress(description)
    assert work is not None
    assert "pre-shift meeting" in work
    assert "fatally" not in work.lower()
    assert g4_retro.extract_work_in_progress("The operator was fatally injured.") is None


# ======================================================================================
# 2. G2 is calibrator-only
# ======================================================================================


def test_g2_qrels_file_carries_the_calibrator_only_flag() -> None:
    """The flag is on line 1 of the data file, not in a sidecar that can be lost."""
    path = GOLDSETS / "g2_codes.qrels.jsonl"
    first = path.read_text(encoding="utf-8").splitlines()[0]
    assert first.startswith(META_PREFIX), "G2 qrels has no //!meta line"
    meta = read_qrels_meta(path)
    assert meta.gold_set == "G2"
    assert meta.calibrator_only is True
    assert meta.headline_forbidden_reason


def test_g2_grade_is_below_the_binary_relevance_floor() -> None:
    """Even with the flag ignored, the harness's own arithmetic refuses to count G2."""
    assert g2_codes.G2_GRADE < BLOCKING_RELEVANCE_FLOOR
    qrels = load_qrels_jsonl(GOLDSETS / "g2_codes.qrels.jsonl")
    assert {j.grade for j in qrels} == {g2_codes.G2_GRADE}
    assert not any(j.blinded for j in qrels), "a blinded G2 label could enter p_at_block"
    assert {j.judged_by for j in qrels} == {"distant_supervision"}


def test_headline_use_of_g2_is_refused() -> None:
    qrels = load_qrels_jsonl(GOLDSETS / "g2_codes.qrels.jsonl")
    with pytest.raises(HeadlineUseRefused) as caught:
        refuse_headline_use(qrels, metric="p_at_block")
    assert "G2" in str(caught.value)
    # ... and the same call over a reportable gold set does not raise.
    refuse_headline_use(load_qrels_jsonl(GOLDSETS / "g4_retro.qrels.jsonl"), metric="p_at_block")


def test_gs0_contains_no_calibrator_only_judgement(gs0: EvalCorpus) -> None:
    present = {j.gold_set for j in gs0.qrels}
    assert not (present & HEADLINE_FORBIDDEN_GOLD_SETS), (
        f"GS0 carries calibrator-only labels {sorted(present & HEADLINE_FORBIDDEN_GOLD_SETS)}; "
        "a release gate reads this corpus"
    )


# ======================================================================================
# 3. Severity is never model-rated
# ======================================================================================


def test_no_corpus_record_carries_a_model_rated_severity(records: EventRecordSet) -> None:
    bases = {r.severity_basis for r in records}
    assert bases <= {"coded_field", "regulator_class"}, (
        f"corpus carries severity bases {sorted(bases)}. A loader may only carry a "
        "severity the regulator wrote; anything else launders a model's opinion past "
        "ARCHITECTURE 5.4 CHECK model_cannot_arm."
    )


def test_constructing_a_model_rated_record_is_refused(records: EventRecordSet) -> None:
    sample = records.records[0]
    with pytest.raises(ValueError, match="model_cannot_arm"):
        EventRecord.model_validate(sample.model_dump() | {"severity_basis": "model_rated"})
    with pytest.raises(ValueError, match="severity_basis"):
        EventRecord.model_validate(sample.model_dump() | {"severity_basis": "human_rated"})


def test_infer_severity_exists_only_to_raise() -> None:
    with pytest.raises(SeverityRefused) as caught:
        infer_severity("a very bad thing happened and someone died")
    assert "model_cannot_arm" in str(caught.value)


def test_every_severity_5_record_says_who_rated_it(records: EventRecordSet) -> None:
    for record in records.fatal():
        assert record.coded.degree_of_injury, (
            f"{record.external_ref}: severity 5 with no coded field naming the rating. "
            "The gate arms on severity 5; the field that armed it must be nameable."
        )


# ======================================================================================
# 4. Schema conformance
# ======================================================================================


def _validate(instance: object, schema: Mapping[str, object], *, path: str = "$") -> list[str]:
    """A small, explicit JSON Schema walk over the keywords ``qrels-v1`` actually uses.

    Written here rather than pulled in as a dependency: ``trappoint-recall`` ships four
    dependencies on purpose, and a schema check that cannot run because a library is
    missing is a schema check that does not run. Unsupported keywords are ignored, and the
    Pydantic model is validated alongside so nothing rests on this walk alone.
    """
    errors: list[str] = []
    if "anyOf" in schema:
        branches = schema["anyOf"]
        assert isinstance(branches, list)
        if all(_validate(instance, b, path=path) for b in branches if isinstance(b, dict)):
            errors.append(f"{path}: matches no branch of anyOf")
        return errors
    if "const" in schema and instance != schema["const"]:
        errors.append(f"{path}: expected const {schema['const']!r}, got {instance!r}")
    if "enum" in schema:
        allowed = schema["enum"]
        assert isinstance(allowed, list)
        if instance not in allowed:
            errors.append(f"{path}: {instance!r} not in enum {allowed}")
    expected = schema.get("type")
    if isinstance(expected, str):
        types: Mapping[str, type | tuple[type, ...]] = {
            "object": dict,
            "array": list,
            "string": str,
            "integer": int,
            "number": (int, float),
            "boolean": bool,
            "null": type(None),
        }
        wanted = types[expected]
        ok = isinstance(instance, wanted) and not (
            expected in ("integer", "number") and isinstance(instance, bool)
        )
        if not ok:
            errors.append(f"{path}: expected {expected}, got {type(instance).__name__}")
            return errors
    if isinstance(instance, str):
        minimum_length = schema.get("minLength")
        if isinstance(minimum_length, int) and len(instance) < minimum_length:
            errors.append(f"{path}: shorter than minLength {minimum_length}")
    if isinstance(instance, int) and not isinstance(instance, bool):
        low = schema.get("minimum")
        high = schema.get("maximum")
        if isinstance(low, (int, float)) and instance < low:
            errors.append(f"{path}: {instance} < minimum {low}")
        if isinstance(high, (int, float)) and instance > high:
            errors.append(f"{path}: {instance} > maximum {high}")
    if isinstance(instance, dict):
        properties = schema.get("properties", {})
        assert isinstance(properties, dict)
        for name in schema.get("required", []) or []:
            if name not in instance:
                errors.append(f"{path}: missing required property {name!r}")
        if schema.get("additionalProperties") is False:
            for key in instance:
                if key not in properties:
                    errors.append(f"{path}: additional property {key!r} is not allowed")
        for key, value in instance.items():
            subschema = properties.get(key)
            if isinstance(subschema, dict):
                errors.extend(_validate(value, subschema, path=f"{path}.{key}"))
    return errors


@pytest.mark.parametrize("path", QRELS_FILES, ids=lambda p: Path(p).name)
def test_every_qrels_line_validates_against_the_published_schema(path: Path) -> None:
    schema = qrels_json_schema()
    failures: list[str] = []
    n = 0
    with path.open("r", encoding="utf-8") as handle:
        for lineno, raw in enumerate(handle, start=1):
            line = raw.strip()
            if not line or line.startswith("//"):
                continue
            n += 1
            payload = json.loads(line)
            errors = _validate(payload, schema, path=f"{path.name}:{lineno}")
            failures.extend(errors)
            Judgement.model_validate(payload)  # the model the schema was generated from
            if len(failures) > 10:
                break
    assert n > 0, f"{path}: no judgements; an empty gold set gates nothing"
    assert not failures, "schema violations:\n" + "\n".join(failures[:10])


def test_the_schema_walk_actually_bites() -> None:
    """A validator that never rejects anything is a validator nobody should trust."""
    schema = qrels_json_schema()
    good = {"query_id": "Q", "doc_id": "E", "grade": 2, "gold_set": "G4", "judged_by": "human"}
    assert not _validate(good, schema)
    assert _validate({**good, "grade": 9}, schema)
    assert _validate({**good, "judged_by": "vibes"}, schema)
    assert _validate({**good, "unexpected": 1}, schema)
    assert _validate({k: v for k, v in good.items() if k != "doc_id"}, schema)


@pytest.mark.parametrize("path", QRELS_FILES, ids=lambda p: Path(p).name)
def test_every_qrels_file_declares_its_governing_metadata(path: Path) -> None:
    meta = read_qrels_meta(path)
    assert meta.n_judgements == len(load_qrels_jsonl(path))
    assert meta.provenance.tenant_use == "harness_only"
    assert meta.basis


# ======================================================================================
# 5. The THYMOGATE panel
# ======================================================================================


def test_panel_covers_all_eight_hazard_energy_classes(panel: Panel) -> None:
    covered = {item.hazard_energy for item in panel.items}
    assert covered == set(HAZARD_ENERGY_CLASSES), (
        f"panel covers {sorted(covered)}; the eight classes of the vertical's "
        "control_failure CHECK list are an obligation, because aggregate recall averages "
        "over exactly the class that kills someone"
    )


def test_panel_mixes_archival_levels_and_is_all_fatal(panel: Panel) -> None:
    assert len({item.scope_level for item in panel.items}) >= 2
    assert all(item.severity == 5 for item in panel.items)
    assert panel.digest == json.loads(
        (FIXTURES / "thymogate_panel.json").read_text(encoding="utf-8")
    )["panel_digest"]


def test_a_panel_missing_a_hazard_class_cannot_be_constructed(panel: Panel) -> None:
    short = [item for item in panel.ordered_items if item.hazard_energy != "radiation"]
    with pytest.raises(ValueError, match="radiation"):
        Panel(
            panel_id=panel.panel_id,
            corpus_commit=panel.corpus_commit,
            built_by=panel.built_by,
            statement=panel.statement,
            items=tuple(short),
        )


def test_a_single_level_panel_cannot_be_constructed(panel: Panel) -> None:
    flattened = [item.model_copy(update={"scope_level": 3}) for item in panel.ordered_items]
    with pytest.raises(ValueError, match="scope level"):
        Panel(
            panel_id=panel.panel_id,
            corpus_commit=panel.corpus_commit,
            built_by=panel.built_by,
            statement=panel.statement,
            items=tuple(flattened),
        )


class _PanelOracle:
    """Recalls every panel item as a blocking check. The only configuration that certifies."""

    name = "panel-oracle"

    def __init__(self, *, skip: str | None = None) -> None:
        self.skip = skip

    async def retrieve(self, query: EvalQuery, k: int) -> list[ScoredCandidate]:
        del k
        if query.truth_doc_id is None or query.truth_doc_id == self.skip:
            return []
        return [
            ScoredCandidate(
                doc_id=query.truth_doc_id,
                rank=1,
                p_relevant=0.97,
                tau_applied=0.35,
                outcome="blocking",
                severity=5,
                channel="B",
                origin="bonded",
            )
        ]


def test_a_configuration_that_recalls_every_panel_item_is_certified(panel: Panel) -> None:
    certificate = certify_sync(
        _PanelOracle(),
        panel,
        configuration={"embed_model": "bge-large-en-v1.5", "tau": {"5": 0.35}, "beam": 32},
        issued_at=datetime(2026, 8, 7, tzinfo=UTC),
    )
    assert certificate.certified
    assert certificate.verdict == "pass"
    assert certificate.n_missed == 0
    assert certificate.panel_digest == panel.digest
    assert certificate.panel_size == len(panel.ordered_items)


def test_a_configuration_that_misses_one_panel_item_cannot_be_certified(panel: Panel) -> None:
    victim = panel.ordered_items[0]
    certificate = certify_sync(
        _PanelOracle(skip=victim.must_recall_doc_id),
        panel,
        configuration={"embed_model": "bge-large-en-v1.5"},
        issued_at=datetime(2026, 8, 7, tzinfo=UTC),
    )
    assert not certificate.certified
    assert certificate.verdict == "fail"
    assert certificate.n_missed >= 1
    assert victim.item_id in certificate.render()
    with pytest.raises(ThymogateRefusal):
        certify_sync(
            _PanelOracle(skip=victim.must_recall_doc_id),
            panel,
            configuration={"embed_model": "bge-large-en-v1.5"},
            raise_on_fail=True,
        )


def test_a_pass_verdict_with_misses_cannot_be_constructed(panel: Panel) -> None:
    """The Python refusal mirrors the vertical's ``verdict_matches_arithmetic`` CHECK.

    Both are needed. The database refuses the row; this refuses the object, so a false
    certificate cannot be built in memory, rendered onto a slide, and never written.
    """
    outcomes = [
        PanelOutcome(
            item_id=item.item_id,
            hazard_energy=item.hazard_energy,
            scope_level=item.scope_level,
            must_recall_doc_id=item.must_recall_doc_id,
            recalled=False,
            miss_reason="not returned",
        )
        for item in panel.ordered_items
    ]
    with pytest.raises(ValueError, match="cannot be certified"):
        ThymogateCertificate(
            certificate_id="00000000-0000-0000-0000-000000000000",
            config_digest="0" * 64,
            panel_digest=panel.digest,
            panel_id=panel.panel_id,
            configuration_name="liar",
            criterion="blocking",
            k=10,
            panel_size=len(outcomes),
            n_missed=len(outcomes),
            verdict="pass",
            issued_at=datetime(2026, 8, 7, tzinfo=UTC),
            outcomes=tuple(outcomes),
            statement=panel.statement,
        )


def test_the_null_configuration_fails_every_panel_item(panel: Panel) -> None:
    certificate = certify_sync(
        NullBackend(),
        panel,
        configuration={},
        issued_at=datetime(2026, 8, 7, tzinfo=UTC),
    )
    assert certificate.n_missed == certificate.panel_size
    assert all(o.miss_reason for o in certificate.outcomes)


def test_config_digest_is_stable_and_float_sensitive() -> None:
    base = {"tau": {"5": 0.35, "4": 0.45}, "beam": 32}
    assert config_digest(base) == config_digest(dict(base))
    assert config_digest(base) != config_digest({**base, "beam": 64})
    assert config_digest(base) != config_digest({"tau": {"5": 0.36, "4": 0.45}, "beam": 32})


# ======================================================================================
# 6. Fixture provenance
# ======================================================================================


def test_real_regulator_data_can_never_be_demo_data() -> None:
    with pytest.raises(ValueError, match="refused"):
        FixtureProvenance(
            corpus_class="real_regulator",
            tenant_use="demo_tenant",
            source_name="MSHA fatality reports",
            licence="US federal work product",
        )


def test_assert_harness_only_refuses_a_real_corpus() -> None:
    real = FixtureProvenance(
        corpus_class="real_regulator",
        tenant_use="harness_only",
        source_name="MSHA fatality reports",
        licence="US federal work product",
    )
    with pytest.raises(DemoTenantContamination) as caught:
        assert_harness_only(real, context="loading the demo tenant")
    assert "fictional site" in str(caught.value)
    assert_harness_only(SYNTHETIC_PROVENANCE, context="loading the demo tenant")


def test_every_committed_fixture_matches_its_recorded_digest(
    manifest: ProvenanceManifest, fixtures_root: Path
) -> None:
    for ref in manifest.files:
        path = fixtures_root / ref.path
        assert path.is_file(), f"{ref.path} is listed in provenance.json and does not exist"
        assert file_sha256(path) == ref.sha256, (
            f"{ref.path} does not match its recorded digest. Either the fixture was edited "
            "by hand or the manifest is stale; both make the provenance claim unverifiable."
        )
        assert path.stat().st_size == ref.bytes


def test_no_committed_fixture_is_demo_safe(manifest: ProvenanceManifest) -> None:
    for ref in manifest.files:
        assert ref.provenance.tenant_use == "harness_only", (
            f"{ref.path} declares tenant_use={ref.provenance.tenant_use!r}. Every fixture "
            "here models fatalities; none of it belongs in a demo tenant, synthetic or not."
        )
        assert not ref.provenance.demo_safe
        assert not ref.provenance.is_real, (
            f"{ref.path} is real regulator data and is committed to this repository. Real "
            "corpora live in the gitignored cache; the committed fixtures are a synthetic "
            "replica."
        )


def test_the_manifest_states_the_rule_in_prose(manifest: ProvenanceManifest) -> None:
    statement = manifest.statement.lower()
    assert "harness" in statement
    assert "demo tenant is synthetic" in statement
    assert "fictional site" in statement


def test_gs0_declares_that_it_is_synthetic_and_preliminary(gs0: EvalCorpus) -> None:
    assert gs0.synthetic is True
    assert gs0.preliminary is True
    label = gs0.label()
    assert "SYNTHETIC" in label
    assert "PRELIMINARY" in label
    assert "synthetic_replica" in gs0.provenance or "synthetic" in gs0.provenance.lower()


def test_the_fixture_tree_fits_in_the_budget(fixtures_root: Path) -> None:
    total = sum(p.stat().st_size for p in fixtures_root.rglob("*") if p.is_file())
    assert total <= MAX_FIXTURE_BYTES, (
        f"committed corpora fixtures are {total / 1024 / 1024:.1f} MB, over the "
        f"{MAX_FIXTURE_BYTES / 1024 / 1024:.0f} MB budget"
    )


# ======================================================================================
# G1: dropped, never guessed
# ======================================================================================


def test_citation_resolution_accounting_closes(records: EventRecordSet) -> None:
    raw = g1_citations.citations_of(records.records)
    resolution = g1_citations.resolve_citations(raw, records)
    assert resolution.n_input == len(raw)
    assert len(resolution.resolved) + resolution.n_dropped == resolution.n_input


def test_unresolvable_citations_are_dropped_by_reason_and_never_guessed(
    records: EventRecordSet,
) -> None:
    resolution = g1_citations.resolve_citations(
        g1_citations.citations_of(records.records), records
    )
    assert resolution.dropped, "no citation was dropped; the drop path is untested"
    assert "no_identifier" in resolution.dropped, (
        "no citation phrase without an identifier was extracted. Those exist in every real "
        "corpus, and extracting-then-dropping them is what makes 'never guessed' a fact "
        "rather than a claim."
    )
    for item in resolution.resolved:
        cited = records.get(item.cited_ref)
        citing = records.get(item.citing_ref)
        assert cited is not None and citing is not None
        assert cited.occurred_at < citing.occurred_at, (
            f"{item.citing_ref} cites {item.cited_ref}, which does not pre-date it"
        )
        assert item.anchor, f"{item.citing_ref} -> {item.cited_ref}: resolved with no anchor"


def test_g1_labels_are_distant_supervision_and_unblinded() -> None:
    qrels = load_qrels_jsonl(GOLDSETS / "g1_citations.qrels.jsonl")
    assert {j.judged_by for j in qrels} == {"distant_supervision"}
    assert not any(j.blinded for j in qrels), (
        "a blinded G1 label would enter p_at_block. A citation establishes a shared "
        "mechanism, not that a supervisor would have been shown the incident."
    )


# ======================================================================================
# G3: confirmation, tagging, disagreement
# ======================================================================================


def test_g3_llm_only_labels_are_tagged_and_refused_by_p_at_block() -> None:
    qrels = load_qrels_jsonl(GOLDSETS / "g3_adjudicated.qrels.jsonl")
    llm = [j for j in qrels if j.judged_by == "llm"]
    human = [j for j in qrels if j.judged_by == "human"]
    assert human, "G3 carries no human-confirmed label; there is nothing to report"
    assert all(not j.blinded for j in llm), (
        "an LLM-only label is blinded and would therefore be counted by p_at_block. "
        "Humans grade stricter than LLMs; an LLM-only precision headline is a "
        "measurement of the pre-labeller."
    )
    assert all(j.blinded for j in human)


def test_g3_reports_inter_rater_disagreement() -> None:
    meta = read_qrels_meta(GOLDSETS / "g3_adjudicated.qrels.jsonl")
    build = meta.build
    assert "cohens_kappa" in build
    assert "n_double_graded" in build
    assert int(build["n_double_graded"]) > 0  # type: ignore[arg-type]
    assert "n_unresolved" in build


def test_two_raters_who_disagree_are_never_averaged() -> None:
    item = g3_adjudicated.AdjudicationItem(
        pair_id="P-1",
        query_id="Q-1",
        doc_id="E-1",
        query_text="permit",
        doc_text="candidate",
        llm_grade=2,
        llm_rationale="shares the mechanism",
        model_id="claude-opus-5",
        prompt_version="umbrela-recall-v1",
    )
    split = g3_adjudicated.Confirmation(
        pair_id="P-1", rater_a="a", grade_a=3, rater_b="b", grade_b=1
    )
    assert split.resolved_grade is None
    result = g3_adjudicated.ingest_confirmations([item], [split])
    assert result.report.n_unresolved == 1
    assert not result.judgements, "an unadjudicated disagreement produced a judgement"


def test_the_worksheet_round_trips_through_a_human(tmp_path: Path) -> None:
    """Emit a worksheet, fill it in, ingest it. The workflow, not just its endpoints.

    The confirmation fields are emitted *blank*, which is what makes "the human agreed"
    and "the human never looked" two distinguishable states rather than the same absence.
    """
    items = [
        g3_adjudicated.AdjudicationItem(
            pair_id=f"P-{i}",
            query_id=f"Q-{i}",
            doc_id=f"E-{i}",
            query_text="permit to work on a pressurised assembly",
            doc_text="stored pneumatic energy released during inflation",
            llm_grade=3,
            llm_rationale="shares the mechanism and the precondition",
            model_id="claude-opus-5",
            prompt_version="umbrela-recall-v1",
        )
        for i in range(3)
    ]
    path = g3_adjudicated.emit_worksheet(items, tmp_path / "worksheet.jsonl")
    blank = g3_adjudicated.load_worksheet(path)
    assert len(blank) == 3
    assert all(c.resolved_grade is None for c in blank), (
        "an unfilled worksheet already carries grades; the emitted confirmation fields "
        "must start empty or an unreviewed pair is indistinguishable from a reviewed one"
    )
    assert (tmp_path / "worksheet.jsonl.license").is_file()

    filled = [
        g3_adjudicated.Confirmation(
            pair_id=item.pair_id, rater_a="a", grade_a=3, rater_b="b", grade_b=3
        )
        for item in items[:2]
    ]
    result = g3_adjudicated.ingest_confirmations(items, filled)
    assert result.report.n_confirmed == 2
    assert result.report.n_llm_only == 1
    human = [j for j in result.judgements if j.judged_by == "human"]
    llm = [j for j in result.judgements if j.judged_by == "llm"]
    assert len(human) == 2 and all(j.blinded for j in human)
    assert len(llm) == 1 and not llm[0].blinded


def test_cohens_kappa_is_undefined_rather_than_zero_on_a_single_category() -> None:
    kappa, reason = g3_adjudicated.cohens_kappa([(3, 3), (3, 3), (3, 3)])
    assert kappa is None
    assert reason is not None and "undefined" in reason


# ======================================================================================
# The corpus the gates read
# ======================================================================================


def test_gs0_loads_and_carries_both_arms(gs0: EvalCorpus) -> None:
    assert len(gs0.retro_severity_5) >= 16, "too few severity-5 retro permits for the floor"
    assert len(gs0.by_kind("routine")) >= 30, "too few routine permits to measure nuisance"
    assert sum(len(q.bonded_sev5) for q in gs0.queries) > 0, (
        "without bonded fatalities MI16 holds vacuously"
    )


def test_gs0_has_blinded_human_labels_for_the_precision_metric(gs0: EvalCorpus) -> None:
    blinded_human = [j for j in gs0.qrels if j.blinded and j.judged_by == "human"]
    assert blinded_human, (
        "GS0 carries no blinded human judgement, so p_at_block would be undefined over it "
        "and the precision gate could never be measured"
    )


def test_the_routine_replay_waives_no_control(gs0: EvalCorpus) -> None:
    """A routine permit that weakens a control belongs in the numerator, not the denominator."""
    forbidden = ("waive", "waived", "deferral", "downgrad", "exemption", "bypass")
    for query in gs0.by_kind("routine"):
        lowered = query.text.lower()
        for word in forbidden:
            assert word not in lowered or "no control is waived" in lowered, (
                f"{query.query_id}: routine permit mentions {word!r}; a permit that weakens "
                "a control ought to pull a precursor, and putting one in the negative "
                "control makes a correct gate look noisy"
            )


def test_the_routine_replay_is_drawn_from_the_incident_distribution(
    gs0: EvalCorpus, records: EventRecordSet
) -> None:
    sites = {r.site_ref for r in records}
    assets = {r.asset_class for r in records}
    routine = gs0.by_kind("routine")
    assert {q.site_id for q in routine} <= sites
    assert {q.asset_class for q in routine} <= assets
    assert len({q.site_id for q in routine}) > 1


# ======================================================================================
# Reproducibility
# ======================================================================================


def test_the_gold_sets_rebuild_byte_identically_from_the_committed_inputs(
    fixtures_root: Path, tmp_path: Path
) -> None:
    """A gold set that cannot be rebuilt from its inputs is a gold set nobody can review."""
    build_goldsets(fixtures_root, tmp_path, provenance=SYNTHETIC_PROVENANCE)
    compared = (
        "goldsets/g1_citations.qrels.jsonl",
        "goldsets/g2_codes.qrels.jsonl",
        "goldsets/g3_adjudicated.qrels.jsonl",
        "goldsets/g4_retro.qrels.jsonl",
        "goldsets/gs0/queries.jsonl",
        "goldsets/gs0/qrels.jsonl",
        "thymogate_panel.json",
    )
    differing = [
        relative
        for relative in compared
        if (tmp_path / relative).read_bytes() != (fixtures_root / relative).read_bytes()
    ]
    assert not differing, (
        "the committed gold sets are not the output of the committed inputs: "
        + ", ".join(differing)
    )


def test_the_loaders_account_for_every_input_record(records: EventRecordSet) -> None:
    report = records.report
    assert report.n_kept + report.n_dropped == report.n_read
    assert report.n_kept > 0
    assert "unmapped_degree_of_injury" in report.dropped, (
        "no Part 50 row was dropped for an unmappable degree of injury; the fixture is "
        "supposed to contain UNCLASSIFIED rows so the drop path runs in CI"
    )


def test_the_build_refuses_a_demo_destination_for_real_data(
    fixtures_root: Path, tmp_path: Path
) -> None:
    real = FixtureProvenance(
        corpus_class="real_regulator",
        tenant_use="harness_only",
        source_name="MSHA",
        licence="US federal work product",
    )
    with pytest.raises(DemoTenantContamination):
        build_goldsets(fixtures_root, tmp_path, provenance=real, destination_use="demo_tenant")


# ======================================================================================
# The loaders are genuinely exercised by the fixtures
# ======================================================================================


def test_all_four_corpora_are_present_in_the_loaded_records(records: EventRecordSet) -> None:
    sources = {r.source for r in records}
    assert sources == {
        "msha_part50",
        "msha_fatality_report",
        "csb_report",
        "au_regulator_alert",
    }, f"only {sorted(sources)} loaded; a gold set missing a whole corpus is a different set"


def test_part50_records_are_marked_truncated(records: EventRecordSet) -> None:
    part50 = [r for r in records if r.source == "msha_part50"]
    assert part50
    assert all(r.narrative_truncated for r in part50)
    assert all(len(r.narrative) <= 384 for r in part50)


def test_fatality_reports_carry_a_work_description(records: EventRecordSet) -> None:
    reports = [r for r in records if r.source == "msha_fatality_report"]
    assert reports
    assert all(r.work_description for r in reports)
    assert all(not r.narrative_truncated for r in reports)


def test_a_part50_extract_missing_a_column_is_refused(tmp_path: Path) -> None:
    """Header-driven, never positional. A renamed column is a refusal on line 1."""
    from trappoint_recall.corpora.msha import Part50FormatError, parse_part50

    broken = tmp_path / "broken.psv"
    broken.write_text("DOCUMENT_NO|MINE_ID|ACCIDENT_DT\n1|2|01/01/2020\n", encoding="utf-8")
    with pytest.raises(Part50FormatError, match="narrative"):
        parse_part50(
            broken,
            provenance=SYNTHETIC_PROVENANCE,
            corpus_commit_at=datetime(2005, 1, 1, tzinfo=UTC),
        )


def test_a_regulator_alert_without_a_classification_is_dropped_not_rated() -> None:
    from trappoint_recall.corpora.csb import load_au_regulator_alerts

    rows: Sequence[Mapping[str, object]] = [
        {
            "external_ref": "XX-1",
            "classification": "a bad one",
            "incident_type": "Electrical",
            "occurred_at": "2020-01-01",
            "text": "something happened",
        }
    ]
    loaded = load_au_regulator_alerts(
        rows,
        provenance=SYNTHETIC_PROVENANCE,
        corpus_commit_at=datetime(2005, 1, 1, tzinfo=UTC),
    )
    assert len(loaded) == 0
    assert loaded.report.dropped == {"unmapped_regulator_class": 1}


def test_records_that_load_are_reloadable_from_a_second_pass(fixtures_root: Path) -> None:
    """Loading twice yields the same corpus digest — no hidden clock, no dict order."""
    first = load_inputs(fixtures_root, provenance=SYNTHETIC_PROVENANCE)
    second = load_inputs(fixtures_root, provenance=SYNTHETIC_PROVENANCE)
    assert [r.external_ref for r in first] == [r.external_ref for r in second]
    assert [r.occurred_at for r in first] == [r.occurred_at for r in second]


def test_an_event_record_refuses_ingest_before_occurrence(records: EventRecordSet) -> None:
    sample = records.records[0]
    payload = sample.model_dump()
    payload["ingested_at"] = sample.occurred_at - timedelta(days=1)
    with pytest.raises(ValueError, match="precedes occurred_at"):
        EventRecord.model_validate(payload)


def test_coded_fields_comembership_key_ignores_the_narrative() -> None:
    coded = CodedFields(
        accident_classification="Powered Haulage",
        injury_source="Haulage Truck",
        equipment="Haul Truck",
    )
    assert coded.comembership_key == ("powered haulage", "haulage truck", "haul truck")
