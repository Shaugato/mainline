# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""The calibrator: knots round-trip to 1e-12, stay monotone, and never a pickle.

The claim under test is the one a stranger has to be able to check: given
``recall_policy.calibrator``, twenty lines of standard-library arithmetic reproduce every
``p_relevant`` the gate ever recorded. The tolerance is 1e-12 against sklearn's own
``predict`` because the knots are exactly the estimator's thresholds and the interpolation
between them is exactly the estimator's interpolation.
"""

from __future__ import annotations

import json
import random

import pytest

from trappoint_recall.fusion.calibration import (
    CALIBRATOR_SCHEMA,
    MIN_CALIBRATION_SAMPLES,
    CalibrationRefused,
    CalibrationSample,
    IsotonicCalibrator,
    assert_disjoint_folds,
    brier_score,
    calibration_report,
    evaluate_knots,
    expected_calibration_error,
    fit_isotonic,
    maximum_calibration_error,
    reliability_diagram,
)

FIT_FOLDS = ("2019H1", "2019H2", "2020H1")
EVAL_FOLDS = ("2020H2", "2021H1")


def _samples(
    n: int, folds: tuple[str, ...], *, seed: int, gold_set: str = "G3"
) -> list[CalibrationSample]:
    """A monotone-ish labelled set: P(relevant) rises with the raw score."""
    rng = random.Random(seed)  # noqa: S311 - fixture data, not a key
    out: list[CalibrationSample] = []
    for index in range(n):
        score = rng.uniform(-2.0, 3.0)
        probability = 1.0 / (1.0 + pow(2.718281828459045, -(score - 0.4)))
        out.append(
            CalibrationSample(
                score=score,
                label=1 if rng.random() < probability else 0,
                fold=folds[index % len(folds)],
                doc_id=f"EVT-{seed}-{index:04d}",
                gold_set=gold_set,
            )
        )
    return out


@pytest.fixture(scope="module")
def fit_samples() -> list[CalibrationSample]:
    return _samples(400, FIT_FOLDS, seed=17)


@pytest.fixture(scope="module")
def eval_samples() -> list[CalibrationSample]:
    return _samples(200, EVAL_FOLDS, seed=91)


@pytest.fixture(scope="module")
def calibrator(fit_samples: list[CalibrationSample]) -> IsotonicCalibrator:
    return fit_isotonic(
        fit_samples,
        fit_folds=list(FIT_FOLDS),
        split_policy_id="TB-2020-07-01-deadbeef",
        feature_spec_sha256="0" * 64,
        note="unit fixture",
    )


# --------------------------------------------------------------------------------------
# The knots
# --------------------------------------------------------------------------------------


def test_the_knots_are_monotone_non_decreasing(calibrator: IsotonicCalibrator) -> None:
    assert all(calibrator.y[i] <= calibrator.y[i + 1] for i in range(calibrator.n_knots - 1))
    assert all(calibrator.x[i] < calibrator.x[i + 1] for i in range(calibrator.n_knots - 1))
    assert all(0.0 <= value <= 1.0 for value in calibrator.y)


def test_the_serialised_knots_round_trip_through_json_to_1e_12(
    calibrator: IsotonicCalibrator,
) -> None:
    document = json.loads(json.dumps(calibrator.to_json()))
    restored = IsotonicCalibrator.from_json(document)
    assert restored.n_knots == calibrator.n_knots
    for original, recovered in zip(calibrator.x, restored.x, strict=True):
        assert abs(original - recovered) <= 1e-12
    for original, recovered in zip(calibrator.y, restored.y, strict=True):
        assert abs(original - recovered) <= 1e-12
    grid = [-3.0 + index * 0.005 for index in range(1400)]
    for score in grid:
        assert abs(calibrator.predict_one(score) - restored.predict_one(score)) <= 1e-12


def test_the_pure_python_evaluator_agrees_with_sklearn_to_1e_12(
    calibrator: IsotonicCalibrator, fit_samples: list[CalibrationSample]
) -> None:
    """The stranger's twenty lines must produce the estimator's numbers, not near them."""
    from sklearn.isotonic import IsotonicRegression  # noqa: PLC0415

    estimator = IsotonicRegression(increasing=True, out_of_bounds="clip", y_min=0.0, y_max=1.0)
    estimator.fit([s.score for s in fit_samples], [float(s.label) for s in fit_samples])
    document = calibrator.to_json()
    grid = [-4.0 + index * 0.003 for index in range(3000)]
    theirs = estimator.predict(grid)
    for score, expected in zip(grid, theirs, strict=True):
        assert abs(evaluate_knots(document, score) - float(expected)) <= 1e-12


def test_the_evaluator_needs_only_the_knots(calibrator: IsotonicCalibrator) -> None:
    """No provenance, no schema key, no library. Just x, y and arithmetic."""
    bare = {"x": list(calibrator.x), "y": list(calibrator.y)}
    for score in (-5.0, 0.0, 0.77, 12.0):
        assert evaluate_knots(bare, score) == calibrator.predict_one(score)


def test_out_of_range_scores_clip_rather_than_extrapolate(
    calibrator: IsotonicCalibrator,
) -> None:
    assert calibrator.predict_one(-1e6) == calibrator.y[0]
    assert calibrator.predict_one(1e6) == calibrator.y[-1]


def test_the_serialised_artefact_is_json_and_declares_its_schema(
    calibrator: IsotonicCalibrator,
) -> None:
    """A pickle is neither auditable nor safe to load from a column several roles can write."""
    document = calibrator.to_json()
    assert document["schema"] == CALIBRATOR_SCHEMA
    assert document["out_of_bounds"] == "clip"
    assert document["increasing"] is True
    assert isinstance(document["x"], list) and isinstance(document["y"], list)
    json.dumps(document)  # must be plain JSON, with no custom encoder


def test_the_provenance_records_the_split_the_folds_and_the_feature_spec(
    calibrator: IsotonicCalibrator,
) -> None:
    provenance = calibrator.provenance
    assert provenance["split_policy_id"] == "TB-2020-07-01-deadbeef"
    assert provenance["fit_folds"] == sorted(FIT_FOLDS)
    assert provenance["feature_spec_sha256"] == "0" * 64
    assert provenance["calibration_set_sha256"]
    assert "exchangeable" in str(provenance["assumption"])


def test_an_unknown_schema_is_refused_rather_than_guessed_at(
    calibrator: IsotonicCalibrator,
) -> None:
    document = calibrator.to_json()
    document["schema"] = "somebody.elses.calibrator/9"
    with pytest.raises(CalibrationRefused, match="unknown calibrator schema"):
        IsotonicCalibrator.from_json(document)


@pytest.mark.parametrize(
    ("x", "y", "message"),
    [
        ((0.0, 1.0), (0.5, 0.4), "non-decreasing"),
        ((1.0, 0.0), (0.1, 0.2), "strictly increasing"),
        ((0.0,), (0.5,), "at least two knots"),
        ((0.0, 1.0), (0.1, 1.4), "outside"),
    ],
)
def test_a_malformed_knot_set_is_refused(
    x: tuple[float, ...], y: tuple[float, ...], message: str
) -> None:
    with pytest.raises(CalibrationRefused, match=message):
        IsotonicCalibrator(x=x, y=y)


# --------------------------------------------------------------------------------------
# The fit refuses the things that would make p_relevant meaningless
# --------------------------------------------------------------------------------------


def test_a_sample_from_outside_the_declared_fit_folds_is_refused() -> None:
    samples = _samples(60, FIT_FOLDS, seed=3) + _samples(10, ("2021H1",), seed=4)
    with pytest.raises(CalibrationRefused, match="leak"):
        fit_isotonic(
            samples,
            fit_folds=list(FIT_FOLDS),
            split_policy_id="TB-x",
            feature_spec_sha256="a" * 64,
        )


def test_too_few_samples_are_refused() -> None:
    with pytest.raises(CalibrationRefused, match="below the floor"):
        fit_isotonic(
            _samples(MIN_CALIBRATION_SAMPLES - 1, FIT_FOLDS, seed=5),
            fit_folds=list(FIT_FOLDS),
            split_policy_id="TB-x",
            feature_spec_sha256="a" * 64,
        )


def test_a_single_class_calibration_set_is_refused() -> None:
    samples = [
        CalibrationSample(score=float(index), label=0, fold="2019H1", doc_id=f"d{index}")
        for index in range(40)
    ]
    with pytest.raises(CalibrationRefused, match="single class"):
        fit_isotonic(
            samples,
            fit_folds=["2019H1"],
            split_policy_id="TB-x",
            feature_spec_sha256="a" * 64,
        )


def test_a_constant_score_column_is_refused() -> None:
    samples = [
        CalibrationSample(score=1.0, label=index % 2, fold="2019H1", doc_id=f"d{index}")
        for index in range(40)
    ]
    with pytest.raises(CalibrationRefused, match="same raw score"):
        fit_isotonic(
            samples,
            fit_folds=["2019H1"],
            split_policy_id="TB-x",
            feature_spec_sha256="a" * 64,
        )


def test_a_sample_with_no_fold_cannot_exist() -> None:
    with pytest.raises(CalibrationRefused, match="declares no fold"):
        CalibrationSample(score=0.5, label=1, fold="")


def test_a_graded_label_is_refused_because_isotonic_fits_a_probability() -> None:
    with pytest.raises(CalibrationRefused, match="binary labels"):
        CalibrationSample(score=0.5, label=3, fold="2019H1")


# --------------------------------------------------------------------------------------
# The leak guard
# --------------------------------------------------------------------------------------


def test_overlapping_folds_are_refused_by_the_guard() -> None:
    with pytest.raises(CalibrationRefused, match="its own fold"):
        assert_disjoint_folds(FIT_FOLDS, ("2020H1", "2020H2"))


def test_a_report_on_the_fit_fold_is_refused(
    calibrator: IsotonicCalibrator, fit_samples: list[CalibrationSample]
) -> None:
    with pytest.raises(CalibrationRefused, match="its own fold"):
        calibration_report(
            calibrator,
            fit_samples,
            fit_folds=list(FIT_FOLDS),
            split_policy_id="TB-x",
            feature_spec_sha256="a" * 64,
        )


# --------------------------------------------------------------------------------------
# Reliability
# --------------------------------------------------------------------------------------


def test_the_report_scores_only_held_out_folds(
    calibrator: IsotonicCalibrator, eval_samples: list[CalibrationSample]
) -> None:
    report = calibration_report(
        calibrator,
        eval_samples,
        fit_folds=list(FIT_FOLDS),
        split_policy_id="TB-2020-07-01-deadbeef",
        feature_spec_sha256="0" * 64,
        synthetic=True,
    )
    assert set(report.eval_folds) == set(EVAL_FOLDS)
    assert set(report.fit_folds).isdisjoint(report.eval_folds)
    assert report.n == len(eval_samples)
    assert 0.0 <= report.brier <= 1.0
    assert 0.0 <= report.ece <= 1.0
    assert report.mce >= report.ece - 1e-12
    assert sum(b.n for b in report.bins) == report.n


def test_the_markdown_artefact_stamps_synthetic_and_preliminary(
    calibrator: IsotonicCalibrator, eval_samples: list[CalibrationSample]
) -> None:
    report = calibration_report(
        calibrator,
        eval_samples,
        fit_folds=list(FIT_FOLDS),
        split_policy_id="TB-x",
        feature_spec_sha256="0" * 64,
        synthetic=True,
        preliminary=True,
    )
    text = report.to_markdown()
    assert "SYNTHETIC CALIBRATION SET" in text
    assert "PRELIMINARY" in text
    assert "95% interval" in text


def test_every_populated_bin_carries_a_wilson_interval_around_its_rate() -> None:
    bins = reliability_diagram([0.05, 0.06, 0.95, 0.97], [0, 0, 1, 1])
    populated = [b for b in bins if b.n > 0]
    assert len(populated) == 2
    for one in populated:
        assert one.observed_lower <= one.observed_rate <= one.observed_upper


def test_a_perfect_forecaster_scores_zero_on_every_summary() -> None:
    predicted = [0.0, 0.0, 1.0, 1.0]
    labels = [0, 0, 1, 1]
    bins = reliability_diagram(predicted, labels)
    assert brier_score(predicted, labels) == 0.0
    assert expected_calibration_error(bins) == 0.0
    assert maximum_calibration_error(bins) == 0.0


def test_an_empty_evaluation_fold_is_refused_rather_than_reported_as_a_measurement(
    calibrator: IsotonicCalibrator,
) -> None:
    with pytest.raises(CalibrationRefused, match="empty evaluation fold"):
        calibration_report(
            calibrator,
            [],
            fit_folds=list(FIT_FOLDS),
            split_policy_id="TB-x",
            feature_spec_sha256="0" * 64,
        )
