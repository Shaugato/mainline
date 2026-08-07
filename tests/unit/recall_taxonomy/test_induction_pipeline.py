# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
"""Induction end to end on the committed fixture corpus, and its refusals.

What the green here does and does not mean is worth stating once, loudly, because the
numbers are seductive: the corpus is SYNTHETIC and the offline judge's rule table and the
corpus's confirmation labels come from one table (see
``tests/fixtures/recall_taxonomy/build_corpus.py``).  These tests prove the **pipeline** —
that the holdout is split before the judge sees anything, that variants merge, that the
classifier fits on merged labels, that scoring walks the tree to each level, that the
interval is a Wilson interval and that acceptance gates on its lower bound.  They prove
nothing whatever about a model's ability to label mining narratives; that measurement is
G1/G3/G4 on the MSHA and CSB corpora, with a live judge, and it is not this worker's.
"""

from __future__ import annotations

import json
import sys
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from unittest import mock

import pytest
from mainline_recall_agent.providers.errors import ModelRefusal, ProviderUnavailable
from mainline_recall_agent.providers.types import ResolvedModel, Usage
from mainline_recall_agent.taxonomy import (
    LEVEL_FILE,
    LEVEL_FONDS,
    LEVEL_SERIES,
    EvalPackageUnavailable,
    HoldoutTooSmall,
    InductionConfig,
    InductionDocument,
    InductionQualityError,
    InductionRun,
    Level1Register,
    RuleBasedInductionJudge,
    build_induction_prefix,
    check_label,
    holdout_split,
    run_induction,
    score_holdout,
)
from mainline_recall_agent.taxonomy.schemas import LabelProposalBatch, MergeDecision

SITE = "11111111-1111-4111-8111-111111111111"
RUN_AT = datetime(2026, 8, 4, tzinfo=UTC)


class _Wrapper:
    """Base for judges that delegate to the committed rule table and then misbehave."""

    def __init__(self, inner: RuleBasedInductionJudge) -> None:
        self._inner = inner

    @property
    def resolved_model(self) -> ResolvedModel:
        return self._inner.resolved_model

    @property
    def last_usage(self) -> Usage | None:
        return self._inner.last_usage

    @property
    def is_semantic(self) -> bool:
        return False

    def judge(
        self, system_blocks: Sequence[Any], user_payload: dict[str, Any], schema: type[Any]
    ) -> Any:
        return self._inner.judge(system_blocks, user_payload, schema)


class InventingJudge(_Wrapper):
    """Returns an off-register level-1 code for every third document."""

    def judge(
        self, system_blocks: Sequence[Any], user_payload: dict[str, Any], schema: type[Any]
    ) -> Any:
        answer = super().judge(system_blocks, user_payload, schema)
        if schema is not LabelProposalBatch:
            return answer
        mutated = [
            label.model_copy(update={"activity_root": "MUE-99"})
            if index % 3 == 0
            else label
            for index, label in enumerate(answer.labels)
        ]
        return LabelProposalBatch(labels=mutated)


class ThingLabellingJudge(_Wrapper):
    """Returns equipment names as file labels for most documents."""

    def judge(
        self, system_blocks: Sequence[Any], user_payload: dict[str, Any], schema: type[Any]
    ) -> Any:
        answer = super().judge(system_blocks, user_payload, schema)
        if schema is not LabelProposalBatch:
            return answer
        mutated = [
            label.model_copy(update={"file_label": "haul truck"}) if index % 2 else label
            for index, label in enumerate(answer.labels)
        ]
        return LabelProposalBatch(labels=mutated)


class BatchRefusingJudge(_Wrapper):
    """Refuses the first propose batch, then behaves."""

    def __init__(self, inner: RuleBasedInductionJudge) -> None:
        super().__init__(inner)
        self.refused = 0

    def judge(
        self, system_blocks: Sequence[Any], user_payload: dict[str, Any], schema: type[Any]
    ) -> Any:
        if schema is LabelProposalBatch and self.refused == 0:
            self.refused += 1
            raise ModelRefusal("the model declined this batch", request_digest="stub")
        return super().judge(system_blocks, user_payload, schema)


class MergeUnavailableJudge(_Wrapper):
    """Answers phase 1 and is unavailable for phase 2."""

    def judge(
        self, system_blocks: Sequence[Any], user_payload: dict[str, Any], schema: type[Any]
    ) -> Any:
        if schema is MergeDecision:
            raise ProviderUnavailable("no route to the judge on the merge leg")
        return super().judge(system_blocks, user_payload, schema)


# --------------------------------------------------------------------------------------
# The reference run
# --------------------------------------------------------------------------------------


def test_level_one_is_the_whole_register_and_stays_frozen(
    induction: InductionRun, register: Level1Register
) -> None:
    fonds = induction.snapshot.at_level(LEVEL_FONDS)
    assert len(fonds) == len(register.codes)
    assert {node.activity_root for node in fonds} == set(register.roots)
    for node in fonds:
        assert node.frozen is True
        assert node.induced_by == "icmm_mue"
        assert node.parent_scope is None


def test_levels_two_and_three_are_induced_and_functionally_labelled(
    induction: InductionRun,
) -> None:
    series = induction.snapshot.at_level(LEVEL_SERIES)
    files = induction.snapshot.at_level(LEVEL_FILE)
    assert series and files
    for node in (*series, *files):
        assert node.induced_by == "llm_induced"
        assert node.frozen is False
        assert check_label(node.label).ok, node.label
    # Every file hangs off a series that is in the snapshot, and every series off a fonds.
    for node in files:
        parent = induction.snapshot.by_scope(node.parent_scope or "")
        assert parent is not None and parent.level == LEVEL_SERIES


def test_variants_were_merged_rather_than_multiplied(
    induction: InductionRun, fixtures_dir: Path
) -> None:
    """The rule table has 24 leaves; its re-worded variants must fold back into them."""
    rules = json.loads(
        (fixtures_dir / "offline_induction_rules.json").read_text(encoding="utf-8")
    )
    canonical_leaves = {rule["file_label"] for rule in rules["rules"]}
    assert len(induction.snapshot.at_level(LEVEL_FILE)) == len(canonical_leaves) == 24
    for label in canonical_leaves:
        assert induction.snapshot.resolve_label(label, level=LEVEL_FILE) is not None

    snapshot = induction.snapshot
    merged_away = [
        key
        for key, scope in snapshot.aliases.items()
        if (node := snapshot.by_scope(scope)) is not None and node.label != key
    ]
    assert merged_away, "at least one re-worded proposal must have been folded"
    for key in merged_away:
        # A merged wording stays resolvable: historical bonds and human confirmation
        # labels were written against it, and losing it turns a rename into a miss.
        assert snapshot.resolve_label(key) is not None


def test_the_holdout_is_reported_with_wilson_bounds_and_gates_on_the_lower_bound(
    induction: InductionRun,
) -> None:
    report = induction.holdout
    assert report is not None
    assert report.n == 300
    for measurement in (report.fonds_level, report.series_level, report.file_level):
        assert measurement.defined
        assert measurement.interval_method == "wilson"
        assert measurement.lower <= measurement.value <= measurement.upper
        assert measurement.n == 300
        assert measurement.split_policy_id == "taxonomy-holdout-sha256"
    assert report.gate_on == "lower"
    assert report.file_floor == 0.85
    assert report.fonds_floor == 0.95
    assert report.accepted is True
    assert "SYNTHETIC" in report.corpus_provenance
    assert "wilson" in report.render()


def test_acceptance_uses_the_lower_bound_and_the_looser_reading_is_visible(
    induction: InductionRun, corpus: list[InductionDocument]
) -> None:
    """At n = 300 the two readings genuinely differ, and the report says which it used."""
    by_id = {document.doc_id: document for document in corpus}
    held = [by_id[doc_id] for doc_id in induction.holdout_doc_ids]
    assert induction.holdout is not None
    floor = induction.holdout.file_level.value

    strict = score_holdout(
        build=induction.build,
        classifier=induction.classifier,
        documents=held,
        split_policy_id="taxonomy-holdout-sha256",
        corpus_provenance="SYNTHETIC",
        file_floor=floor,
        fonds_floor=0.0,
        gate_on="lower",
    )
    loose = score_holdout(
        build=induction.build,
        classifier=induction.classifier,
        documents=held,
        split_policy_id="taxonomy-holdout-sha256",
        corpus_provenance="SYNTHETIC",
        file_floor=floor,
        fonds_floor=0.0,
        gate_on="value",
    )
    assert strict.accepted is False
    assert loose.accepted is True
    assert strict.gate_on == "lower" and loose.gate_on == "value"


def test_the_holdout_never_trained_the_classifier(induction: InductionRun) -> None:
    assert set(induction.train_doc_ids).isdisjoint(induction.holdout_doc_ids)
    assert set(induction.assignments).issubset(set(induction.train_doc_ids))
    assert len(induction.holdout_doc_ids) == 300


def test_unclassifiable_documents_are_abstentions_not_guesses(
    induction: InductionRun,
) -> None:
    assert induction.pool.abstained, "the fixture carries narratives with no work in them"
    assert induction.pool.rejections == ()
    assert induction.holdout is not None
    assert induction.holdout.unresolvable_truth > 0


def test_a_rerun_is_byte_identical(
    corpus: list[InductionDocument],
    register: Level1Register,
    judge: RuleBasedInductionJudge,
    induction: InductionRun,
) -> None:
    """No RNG, no dict-order dependence: the same corpus produces the same digest."""
    again = run_induction(
        documents=corpus,
        register=register,
        judge=judge,
        site_id=SITE,
        taxonomy_ver=1,
        corpus_provenance=induction.version.config["corpus_provenance"],
        induced_at=induction.version.induced_at,
        notes=induction.version.notes,
    )
    assert again.version.version_digest == induction.version.version_digest
    assert again.classifier.digest() == induction.classifier.digest()


def test_the_induction_prefix_is_stable_and_cacheable(register: Level1Register) -> None:
    first = build_induction_prefix(register)
    second = build_induction_prefix(register)
    assert first.prefix_digest() == second.prefix_digest()
    assert first.likely_cacheable
    assert first.wire()[-1]["cache_control"] == {"type": "ephemeral"}


# --------------------------------------------------------------------------------------
# Refusals
# --------------------------------------------------------------------------------------


def test_an_invented_level_one_code_is_dropped_and_counted(
    corpus: list[InductionDocument],
    register: Level1Register,
    judge: RuleBasedInductionJudge,
) -> None:
    run = run_induction(
        documents=corpus,
        register=register,
        judge=InventingJudge(judge),
        site_id=SITE,
        taxonomy_ver=1,
        # The ceiling is raised for this run on purpose: the property under test is that an
        # off-register answer is dropped and COUNTED, and at the default ceiling the run
        # would (correctly) abort before the count could be inspected.
        config=InductionConfig(max_rejection_rate=0.5),
        corpus_provenance="SYNTHETIC",
        induced_at=RUN_AT,
    )
    counts = run.pool.rejection_counts()
    assert counts["off_register"] > 0
    assert "MUE-99" not in {node.activity_root for node in run.snapshot.nodes}
    assert run.version.to_dict()["rejection_counts"]["off_register"] > 0


def test_a_judge_that_returns_things_instead_of_functions_fails_the_run(
    corpus: list[InductionDocument],
    register: Level1Register,
    judge: RuleBasedInductionJudge,
) -> None:
    """Keeping the survivors would publish a taxonomy shaped by the validator."""
    with pytest.raises(InductionQualityError) as excinfo:
        run_induction(
            documents=corpus,
            register=register,
            judge=ThingLabellingJudge(judge),
            site_id=SITE,
            taxonomy_ver=1,
            corpus_provenance="SYNTHETIC",
            induced_at=RUN_AT,
        )
    assert excinfo.value.context["by_reason"]["equipment_or_place_term"] > 0
    assert excinfo.value.context["rejection_rate"] > 0.25


def test_a_refused_batch_is_recorded_and_the_run_continues(
    corpus: list[InductionDocument],
    register: Level1Register,
    judge: RuleBasedInductionJudge,
) -> None:
    stub = BatchRefusingJudge(judge)
    run = run_induction(
        documents=corpus,
        register=register,
        judge=stub,
        site_id=SITE,
        taxonomy_ver=1,
        corpus_provenance="SYNTHETIC",
        induced_at=RUN_AT,
    )
    assert stub.refused == 1
    assert len(run.version.failed_batches) == 1
    assert "ModelRefusal" in run.version.failed_batches[0]
    assert run.snapshot.at_level(LEVEL_FILE), "one lost batch must not cost the taxonomy"


def test_an_unavailable_merge_leg_falls_back_and_says_so(
    corpus: list[InductionDocument],
    register: Level1Register,
    judge: RuleBasedInductionJudge,
) -> None:
    run = run_induction(
        documents=corpus,
        register=register,
        judge=MergeUnavailableJudge(judge),
        site_id=SITE,
        taxonomy_ver=1,
        corpus_provenance="SYNTHETIC",
        induced_at=RUN_AT,
    )
    assert run.merge.fell_back is True
    assert "ProviderUnavailable" in run.merge.fallback_reason
    assert run.version.to_dict()["merge"]["fell_back_to_deterministic_clustering"] is True
    assert run.snapshot.at_level(LEVEL_FILE)


def test_a_raised_support_floor_drops_thin_activities(
    corpus: list[InductionDocument],
    register: Level1Register,
    judge: RuleBasedInductionJudge,
    induction: InductionRun,
) -> None:
    sparse = run_induction(
        documents=corpus,
        register=register,
        judge=judge,
        site_id=SITE,
        taxonomy_ver=3,
        config=InductionConfig(min_support=40),
        corpus_provenance="SYNTHETIC",
        induced_at=RUN_AT,
    )
    assert len(sparse.snapshot.at_level(LEVEL_FILE)) < len(
        induction.snapshot.at_level(LEVEL_FILE)
    )
    assert len(sparse.snapshot.at_level(LEVEL_FONDS)) == len(register.codes)


def test_the_offline_judge_is_declared_non_semantic_on_the_record(
    induction: InductionRun,
) -> None:
    assert induction.version.model_is_semantic is False
    assert "NOT model-induced" in induction.version.render()


# --------------------------------------------------------------------------------------
# The holdout's own refusals
# --------------------------------------------------------------------------------------


def _holdout_documents(
    induction: InductionRun, corpus: list[InductionDocument]
) -> list[InductionDocument]:
    by_id = {document.doc_id: document for document in corpus}
    return [by_id[doc_id] for doc_id in induction.holdout_doc_ids]


def test_a_holdout_too_small_to_decide_is_refused(
    induction: InductionRun, corpus: list[InductionDocument]
) -> None:
    """Below the floor the interval is wider than the gap between the two thresholds."""
    with pytest.raises(HoldoutTooSmall):
        score_holdout(
            build=induction.build,
            classifier=induction.classifier,
            documents=_holdout_documents(induction, corpus)[:5],
            split_policy_id="taxonomy-holdout-sha256",
            corpus_provenance="SYNTHETIC",
        )


def test_an_unknown_gate_side_is_refused(
    induction: InductionRun, corpus: list[InductionDocument]
) -> None:
    with pytest.raises(HoldoutTooSmall):
        score_holdout(
            build=induction.build,
            classifier=induction.classifier,
            documents=_holdout_documents(induction, corpus),
            split_policy_id="taxonomy-holdout-sha256",
            corpus_provenance="SYNTHETIC",
            gate_on="upper",
        )


def test_without_the_eval_package_no_number_is_reported_at_all(
    induction: InductionRun, corpus: list[InductionDocument]
) -> None:
    """Refused rather than substituted: a bare point estimate is not an acceptable fallback."""
    blocked = dict.fromkeys(
        ["trappoint_recall", "trappoint_recall.eval", "trappoint_recall.eval.measurement"]
    )
    with (
        mock.patch.dict(sys.modules, blocked),
        pytest.raises(EvalPackageUnavailable) as excinfo,
    ):
        score_holdout(
            build=induction.build,
            classifier=induction.classifier,
            documents=_holdout_documents(induction, corpus),
            split_policy_id="taxonomy-holdout-sha256",
            corpus_provenance="SYNTHETIC",
        )
    assert "Wilson" in excinfo.value.message


def test_the_split_is_a_function_of_the_document_id_alone(
    corpus: list[InductionDocument],
) -> None:
    ids = [document.doc_id for document in corpus]
    train, held = holdout_split(ids, 300)
    reversed_train, reversed_held = holdout_split(list(reversed(ids)), 300)
    assert set(held) == set(reversed_held)
    assert set(train).isdisjoint(held)
    assert len(held) == 300
    # Growing the corpus must not move an existing document out of the holdout.
    grown, grown_held = holdout_split([*ids, "FX-9001", "FX-9002"], 300)
    assert set(grown_held) - set(held) <= {"FX-9001", "FX-9002"}
    assert len(grown) + len(grown_held) == len(ids) + 2
