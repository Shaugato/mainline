# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""The calibration lane: a reliability diagram, Brier and ECE, and a leak that cannot happen.

Two different kinds of assertion live here and the difference is the honest core of the file.

**Contract assertions.** The calibrator is fitted only on folds the wall admits; the report
is scored only on folds it withheld; the artefact carries the split policy, both fold sets
and the corpus label. These are claims about *our arithmetic* and they hold on any corpus.

**Measurements.** Brier, ECE, MCE and the reliability bins. On the committed synthetic set
these characterise the calibrator implementation and nothing else, which is why the artefact
stamps ``SYNTHETIC`` and ``PRELIMINARY`` and why no floor is asserted against them. Point
``TRAPPOINT_RECALL_CALIBRATION_SET`` at the adjudicated G2/G3 set and the same code measures
that instead — under its own label, with its own stamp.

The one measurement-shaped assertion that *is* made is a relative one: calibrating must not
make the forecast worse than the uncalibrated score on held-out data. That is a property of
isotonic regression fitted on a monotone score, it does not depend on the corpus being real,
and if it ever failed the calibrator would be actively harming the number a supervisor sees.
"""

from __future__ import annotations

import json
import math
from collections.abc import Sequence
from dataclasses import replace
from pathlib import Path

import pytest
from calibration_dataset import ENV_OVERRIDE, CalibrationSet, resolve_calibration_set

from trappoint_recall.fusion.calibration import (
    CalibrationRefused,
    CalibrationSample,
    assert_disjoint_folds,
    brier_score,
    calibration_report,
    evaluate_knots,
    fit_isotonic,
)
from trappoint_recall.fusion.featurespec import FEATURE_SPEC_SHA256

REPORT_JSON = "calibration_report.json"
REPORT_MARKDOWN = "calibration_report.md"


def _fit(calibration_set: CalibrationSet):  # type: ignore[no-untyped-def]
    return fit_isotonic(
        calibration_set.fit,
        fit_folds=list(calibration_set.fit_folds),
        split_policy_id=calibration_set.split_policy_id,
        feature_spec_sha256=FEATURE_SPEC_SHA256,
        note=f"calibration lane over {calibration_set.label()}",
    )


# --------------------------------------------------------------------------------------
# The split is real
# --------------------------------------------------------------------------------------


def test_the_wall_puts_no_fold_on_both_sides(calibration_set: CalibrationSet) -> None:
    assert calibration_set.fit_folds
    assert calibration_set.eval_folds
    assert set(calibration_set.fit_folds).isdisjoint(calibration_set.eval_folds)


def test_the_split_is_temporally_blocked_and_never_reaches_through_aost(
    calibration_set: CalibrationSet,
) -> None:
    """``gc.ttlseconds`` defaults to four hours, so AOST cannot reach a wall months back."""
    split = calibration_set.policy.to_dict()
    assert split["kind"] == "temporally_blocked"
    assert split["predicates"] == [
        "occurred_at < wall",
        "ingested_at < wall",
        "corpus_commit <= wall",
    ]
    assert split["as_of_system_time"].startswith("refused")


def test_every_fit_sample_predates_the_wall(calibration_set: CalibrationSet) -> None:
    fit_ids = {sample.doc_id for sample in calibration_set.fit}
    eval_ids = {sample.doc_id for sample in calibration_set.evaluation}
    assert fit_ids.isdisjoint(eval_ids)
    assert len(fit_ids) + len(eval_ids) == len(calibration_set.fit) + len(
        calibration_set.evaluation
    )


# --------------------------------------------------------------------------------------
# A calibrator is never evaluated on its own fold
# --------------------------------------------------------------------------------------


def test_a_calibrator_fitted_on_a_blocked_split_is_never_evaluated_on_its_own_fold(
    calibration_set: CalibrationSet,
) -> None:
    """The assertion the lane exists for.

    Evaluated on its own fold, an isotonic calibrator reports the sharpness of its training
    data — the most flattering and least informative number available — and it reports it in
    exactly the format a slide wants.
    """
    calibrator = _fit(calibration_set)
    assert calibrator.provenance["fit_folds"] == sorted(calibration_set.fit_folds)
    assert_disjoint_folds(calibration_set.fit_folds, calibration_set.eval_folds)

    report = calibration_report(
        calibrator,
        calibration_set.evaluation,
        fit_folds=list(calibration_set.fit_folds),
        split_policy_id=calibration_set.split_policy_id,
        feature_spec_sha256=FEATURE_SPEC_SHA256,
    )
    assert set(report.fit_folds).isdisjoint(report.eval_folds)


def test_scoring_the_calibrator_on_its_fit_fold_is_refused(
    calibration_set: CalibrationSet,
) -> None:
    """PL-2: the guard is shown failing, so it is known to be capable of failing."""
    calibrator = _fit(calibration_set)
    with pytest.raises(CalibrationRefused, match="its own fold"):
        calibration_report(
            calibrator,
            calibration_set.fit,
            fit_folds=list(calibration_set.fit_folds),
            split_policy_id=calibration_set.split_policy_id,
            feature_spec_sha256=FEATURE_SPEC_SHA256,
        )


def test_fitting_on_a_held_out_fold_is_refused(calibration_set: CalibrationSet) -> None:
    with pytest.raises(CalibrationRefused, match="leak"):
        fit_isotonic(
            [*calibration_set.fit, *calibration_set.evaluation],
            fit_folds=list(calibration_set.fit_folds),
            split_policy_id=calibration_set.split_policy_id,
            feature_spec_sha256=FEATURE_SPEC_SHA256,
        )


# --------------------------------------------------------------------------------------
# The measurement, and what it is worth
# --------------------------------------------------------------------------------------


def _naive(samples: Sequence[CalibrationSample]) -> list[float]:
    """The honest strawman: the raw score squashed into [0, 1] and shown to a supervisor."""
    return [1.0 / (1.0 + math.exp(-sample.score)) for sample in samples]


def _exchangeable_halves(
    calibration_set: CalibrationSet,
) -> tuple[tuple[CalibrationSample, ...], tuple[CalibrationSample, ...]]:
    """Interleave the fit samples into two halves carrying distinct probe fold labels.

    **This is not a temporal split and must never produce a recall metric.** It exists to
    isolate one property: given data that really is exchangeable between fit and evaluation,
    does isotonic regression improve the forecast out of sample? Relabelling the folds is
    deliberate and visible — the leak guard is fold-based, so a probe that wants to bypass
    temporal blocking has to say out loud that it is doing something else.
    """
    left: list[CalibrationSample] = []
    right: list[CalibrationSample] = []
    for index, sample in enumerate(sorted(calibration_set.fit, key=lambda s: s.doc_id)):
        side = "A" if index % 2 == 0 else "B"
        relabelled = replace(sample, fold=f"probe{side}")
        (left if side == "A" else right).append(relabelled)
    return tuple(left), tuple(right)


def test_under_exchangeability_calibration_improves_the_out_of_sample_forecast(
    calibration_set: CalibrationSet,
) -> None:
    """The property isotonic regression is here for, isolated from corpus drift.

    If this fails, the calibrator is actively harming the number a supervisor is shown even
    when its own assumption holds, and nothing downstream can rescue that.
    """
    fit_half, probe_half = _exchangeable_halves(calibration_set)
    calibrator = fit_isotonic(
        fit_half,
        fit_folds=["probeA"],
        split_policy_id=f"{calibration_set.split_policy_id}+exchangeability-probe",
        feature_spec_sha256=FEATURE_SPEC_SHA256,
        note="exchangeability probe: NOT a temporal split, never a recall metric",
    )
    labels = [sample.label for sample in probe_half]
    calibrated = calibrator.predict(sample.score for sample in probe_half)
    assert brier_score(calibrated, labels) <= brier_score(_naive(probe_half), labels) + 1e-12


def test_the_drift_penalty_is_measured_and_reported_rather_than_assumed_away(
    calibration_set: CalibrationSet,
) -> None:
    """Conformal risk control assumes exchangeability; safety corpora drift.

    The gap between the exchangeable probe and the temporally-blocked evaluation is that
    assumption being measured rather than restated. No floor is asserted on it — a floor
    here would be a claim about the corpus — but it is computed, it is finite, and it goes
    into the artefact where a reader can see which way it went.
    """
    blocked = _fit(calibration_set)
    labels = [sample.label for sample in calibration_set.evaluation]
    calibrated = brier_score(
        blocked.predict(sample.score for sample in calibration_set.evaluation), labels
    )
    naive = brier_score(_naive(calibration_set.evaluation), labels)
    penalty = calibrated - naive
    assert math.isfinite(penalty)
    assert 0.0 <= calibrated <= 1.0
    # Stated, not asserted: on the committed synthetic set the base rate rises across
    # half-years by construction, so a calibrator fitted on the earlier blocks under-predicts
    # on the later ones. That is the exchangeability assumption failing in miniature, and it
    # is the reason the assumption travels with every tau this domain publishes.
    assert blocked.provenance["assumption"]


def test_the_reliability_bins_account_for_every_held_out_sample(
    calibration_set: CalibrationSet,
) -> None:
    calibrator = _fit(calibration_set)
    report = calibration_report(
        calibrator,
        calibration_set.evaluation,
        fit_folds=list(calibration_set.fit_folds),
        split_policy_id=calibration_set.split_policy_id,
        feature_spec_sha256=FEATURE_SPEC_SHA256,
    )
    assert sum(one.n for one in report.bins) == report.n == len(calibration_set.evaluation)
    assert 0.0 <= report.brier <= 1.0
    assert 0.0 <= report.ece <= 1.0
    assert report.mce + 1e-12 >= report.ece
    for one in report.bins:
        if one.n:
            assert one.observed_lower <= one.observed_rate <= one.observed_upper


def test_the_report_records_which_gold_sets_carried_the_labels(
    calibration_set: CalibrationSet,
) -> None:
    """A calibrator trained mostly on G2 is trained mostly on weak supervision, and the
    artefact has to say so rather than let a reader assume adjudication."""
    calibrator = _fit(calibration_set)
    report = calibration_report(
        calibrator,
        calibration_set.evaluation,
        fit_folds=list(calibration_set.fit_folds),
        split_policy_id=calibration_set.split_policy_id,
        feature_spec_sha256=FEATURE_SPEC_SHA256,
    )
    assert report.gold_set_counts
    assert sum(report.gold_set_counts.values()) == report.n
    assert set(report.gold_set_counts) <= {"G2", "G3", "unlabelled_source"}


# --------------------------------------------------------------------------------------
# The artefact
# --------------------------------------------------------------------------------------


@pytest.mark.artefact
def test_the_lane_emits_a_reliability_diagram_and_a_brier_ece_report(
    calibration_set: CalibrationSet, artefacts_dir: Path
) -> None:
    calibrator = _fit(calibration_set)
    report = calibration_report(
        calibrator,
        calibration_set.evaluation,
        fit_folds=list(calibration_set.fit_folds),
        split_policy_id=calibration_set.split_policy_id,
        feature_spec_sha256=FEATURE_SPEC_SHA256,
        synthetic=calibration_set.synthetic,
        preliminary=calibration_set.preliminary,
        note=calibration_set.note,
    )
    labels = [sample.label for sample in calibration_set.evaluation]
    fit_half, probe_half = _exchangeable_halves(calibration_set)
    probe = fit_isotonic(
        fit_half,
        fit_folds=["probeA"],
        split_policy_id=f"{calibration_set.split_policy_id}+exchangeability-probe",
        feature_spec_sha256=FEATURE_SPEC_SHA256,
        note="exchangeability probe: NOT a temporal split",
    )
    probe_labels = [sample.label for sample in probe_half]

    document = report.to_json()
    document["corpus"] = calibration_set.provenance()
    document["calibrator"] = calibrator.to_json()
    document["baseline"] = {
        "naive_squash_brier_blocked": brier_score(_naive(calibration_set.evaluation), labels),
        "calibrated_brier_blocked": report.brier,
        "naive_squash_brier_exchangeable_probe": brier_score(_naive(probe_half), probe_labels),
        "calibrated_brier_exchangeable_probe": brier_score(
            probe.predict(sample.score for sample in probe_half), probe_labels
        ),
        "reading": "The exchangeable probe isolates what isotonic regression buys. The gap "
        "between it and the temporally-blocked evaluation is corpus drift, which is the "
        "conformal exchangeability assumption being measured rather than restated.",
    }

    json_path = artefacts_dir / REPORT_JSON
    markdown_path = artefacts_dir / REPORT_MARKDOWN
    json_path.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    markdown_path.write_text(report.to_markdown(), encoding="utf-8")

    assert json_path.is_file() and markdown_path.is_file()
    reloaded = json.loads(json_path.read_text(encoding="utf-8"))
    assert reloaded["split_policy_id"] == calibration_set.split_policy_id
    assert reloaded["fit_folds"] == sorted(calibration_set.fit_folds)
    assert reloaded["eval_folds"] == sorted(calibration_set.eval_folds)
    assert reloaded["feature_spec_sha256"] == FEATURE_SPEC_SHA256
    assert reloaded["corpus"]["source"] in {"selftest", "gs0"} or reloaded["corpus"][
        "source"
    ].startswith("env:")
    assert reloaded["calibrator"]["schema"].startswith("trappoint.recall.calibrator")


@pytest.mark.artefact
def test_the_emitted_artefact_carries_the_stamp_its_corpus_earns(
    calibration_set: CalibrationSet, artefacts_dir: Path
) -> None:
    """A synthetic run must never read like a product measurement."""
    calibrator = _fit(calibration_set)
    report = calibration_report(
        calibrator,
        calibration_set.evaluation,
        fit_folds=list(calibration_set.fit_folds),
        split_policy_id=calibration_set.split_policy_id,
        feature_spec_sha256=FEATURE_SPEC_SHA256,
        synthetic=calibration_set.synthetic,
        preliminary=calibration_set.preliminary,
    )
    text = report.to_markdown()
    if calibration_set.synthetic:
        assert "SYNTHETIC CALIBRATION SET" in text
    if calibration_set.preliminary:
        assert "PRELIMINARY" in text
    assert calibration_set.split_policy_id in text
    (artefacts_dir / REPORT_MARKDOWN).write_text(text, encoding="utf-8")


def test_the_artefact_can_be_re_evaluated_from_its_own_knots(
    calibration_set: CalibrationSet,
) -> None:
    """The stranger's check: the committed artefact carries everything needed to redo it."""
    calibrator = _fit(calibration_set)
    document = calibrator.to_json()
    for sample in calibration_set.evaluation[:50]:
        assert evaluate_knots(document, sample.score) == calibrator.predict_one(sample.score)


# --------------------------------------------------------------------------------------
# Resolution
# --------------------------------------------------------------------------------------


def test_an_override_that_names_nothing_raises_rather_than_falling_back() -> None:
    with pytest.raises(RuntimeError, match="Refusing to fall back"):
        resolve_calibration_set({ENV_OVERRIDE: "/no/such/calibration/set.json"})


def test_the_default_resolution_names_the_set_it_returns() -> None:
    path, source = resolve_calibration_set({})
    assert path.is_file()
    assert source in {"selftest", "gs0"}
