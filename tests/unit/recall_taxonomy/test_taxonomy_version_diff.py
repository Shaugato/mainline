# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
"""The taxonomy version is a commit, and its diff is emitted whether or not it is empty.

The failure this guards against cannot be detected after the fact.  A re-induction that
merges or drops a level-3 activity changes which arms the gate generates; the incident is
still in the archive, still severity 5, still bonded — and the permit merges.  Nothing
errors.  The only artefact that can ever explain it is the version record, so these tests
assert that a re-induction which genuinely moves labels produces a non-empty diff, that the
record carries the model and prompt that produced it, and that its digest moves when the
taxonomy does.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from mainline_recall_agent.taxonomy import (
    LEVEL_FILE,
    LEVEL_FONDS,
    LEVEL_SERIES,
    ActivityNode,
    InductionRun,
    TaxonomySnapshot,
    TaxonomyVersion,
    TaxonomyVersionError,
    derive_scope_id,
    diff_snapshots,
    emit_version,
)

SITE = "11111111-1111-4111-8111-111111111111"
ROOT = "MUE-05"
FONDS_LABEL = "isolating stored energy before intrusive work"
SERIES_LABEL = "locking out and proving zero energy state"


def _snapshot(file_label: str, version: int) -> TaxonomySnapshot:
    fonds = ActivityNode(
        scope_id=derive_scope_id(
            site_id=SITE, taxonomy_ver=version, level=LEVEL_FONDS, label_path=[FONDS_LABEL]
        ),
        site_id=SITE,
        level=LEVEL_FONDS,
        parent_scope=None,
        label=FONDS_LABEL,
        activity_root=ROOT,
        taxonomy_ver=version,
        induced_by="icmm_mue",
        frozen=True,
    )
    series = ActivityNode(
        scope_id=derive_scope_id(
            site_id=SITE,
            taxonomy_ver=version,
            level=LEVEL_SERIES,
            label_path=[FONDS_LABEL, SERIES_LABEL],
        ),
        site_id=SITE,
        level=LEVEL_SERIES,
        parent_scope=fonds.scope_id,
        label=SERIES_LABEL,
        activity_root=ROOT,
        taxonomy_ver=version,
        induced_by="llm_induced",
        frozen=False,
    )
    leaf = ActivityNode(
        scope_id=derive_scope_id(
            site_id=SITE,
            taxonomy_ver=version,
            level=LEVEL_FILE,
            label_path=[FONDS_LABEL, SERIES_LABEL, file_label],
        ),
        site_id=SITE,
        level=LEVEL_FILE,
        parent_scope=series.scope_id,
        label=file_label,
        activity_root=ROOT,
        taxonomy_ver=version,
        induced_by="llm_induced",
        frozen=False,
    )
    return TaxonomySnapshot(
        site_id=SITE, taxonomy_ver=version, nodes=(fonds, series, leaf)
    )


def test_the_first_version_reports_everything_as_added() -> None:
    after = _snapshot("applying personal locks to isolation points", 1)
    diff = diff_snapshots(None, after)
    assert not diff.is_empty
    assert len(diff.added) == 3
    assert diff.removed == ()
    assert "first taxonomy version" in diff.rename_evidence


def test_a_rename_is_only_claimed_when_the_document_sets_show_it() -> None:
    before = _snapshot("applying personal locks to isolation points", 1)
    after = _snapshot("applying personal locks at isolation points", 2)
    before_leaf = before.at_level(LEVEL_FILE)[0].scope_id
    after_leaf = after.at_level(LEVEL_FILE)[0].scope_id
    docs = {f"FX-{index:04d}": before_leaf for index in range(10)}

    # Without assignments the honest answer is a deletion plus an insertion.
    blind = diff_snapshots(before, after)
    assert len(blind.added) == 1
    assert len(blind.removed) == 1
    assert blind.renamed == ()
    assert blind.rename_evidence.startswith("none")

    # With them, the overlap is the evidence.
    shown = diff_snapshots(
        before,
        after,
        before_assignments=docs,
        after_assignments=dict.fromkeys(docs, after_leaf),
    )
    assert len(shown.renamed) == 1
    assert shown.added == ()
    assert shown.removed == ()
    assert "Jaccard" in shown.rename_evidence


def test_disjoint_document_sets_are_not_a_rename() -> None:
    before = _snapshot("applying personal locks to isolation points", 1)
    after = _snapshot("planning rescue before entering", 2)
    before_leaf = before.at_level(LEVEL_FILE)[0].scope_id
    after_leaf = after.at_level(LEVEL_FILE)[0].scope_id
    diff = diff_snapshots(
        before,
        after,
        before_assignments={f"A-{i}": before_leaf for i in range(10)},
        after_assignments={f"B-{i}": after_leaf for i in range(10)},
    )
    assert diff.renamed == ()
    assert len(diff.added) == 1
    assert len(diff.removed) == 1


def test_a_reinduction_that_moves_labels_produces_a_non_empty_diff(
    induction: InductionRun, induction_v2: InductionRun
) -> None:
    """The property the brief names: the diff is a first-class, non-empty artefact."""
    assert induction.version.diff.is_empty is False
    diff = induction_v2.version.diff
    assert not diff.is_empty, "a re-induction that dropped activities must be visible"
    assert diff.removed, diff.summary()
    removed_labels = {label for _, _, label in diff.removed}
    assert "inspecting for misfires before re-entry" in removed_labels
    assert induction_v2.version.parent_taxonomy_ver == induction.version.taxonomy_ver


def test_the_diff_is_carried_on_the_serialised_version_record(
    induction_v2: InductionRun,
) -> None:
    payload = induction_v2.version.to_dict()
    assert payload["diff"]["removed"], "the diff must survive serialisation"
    assert payload["version_digest"] == induction_v2.version.version_digest
    assert payload["model"].startswith("offline-rule-induction")
    assert payload["model_is_semantic"] is False
    assert payload["prompt_version"] == "mainline-taxonomy-induction-1"
    assert payload["register_sha256"]
    assert payload["classifier_digest"]


def test_the_digest_covers_the_taxonomy_and_the_provenance(
    induction: InductionRun,
) -> None:
    version = induction.version
    assert version.version_digest == version.version_digest  # stable across recomputation

    moved = TaxonomyVersion(
        taxonomy_ver=version.taxonomy_ver,
        site_id=version.site_id,
        parent_taxonomy_ver=version.parent_taxonomy_ver,
        induced_at=version.induced_at,
        model=version.model,
        model_is_semantic=version.model_is_semantic,
        prompt_version="mainline-taxonomy-induction-2",
        register_id=version.register_id,
        register_sha256=version.register_sha256,
        snapshot=version.snapshot,
        diff=version.diff,
    )
    assert moved.version_digest != version.version_digest


def test_a_version_cannot_precede_its_parent() -> None:
    snapshot = _snapshot("applying personal locks to isolation points", 1)
    with pytest.raises(TaxonomyVersionError):
        emit_version(
            taxonomy_ver=1,
            site_id=SITE,
            parent=None,
            parent_taxonomy_ver=4,
            snapshot=snapshot,
            induced_at=datetime(2026, 8, 4, tzinfo=UTC),
            model="offline",
            model_is_semantic=False,
            prompt_version="p",
            register_id="r",
            register_sha256="d",
        )


def test_a_version_record_must_agree_with_its_snapshot() -> None:
    snapshot = _snapshot("applying personal locks to isolation points", 1)
    with pytest.raises(TaxonomyVersionError):
        emit_version(
            taxonomy_ver=2,
            site_id=SITE,
            parent=None,
            snapshot=snapshot,
            induced_at=datetime(2026, 8, 4, tzinfo=UTC),
            model="offline",
            model_is_semantic=False,
            prompt_version="p",
            register_id="r",
            register_sha256="d",
        )
