# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""Isotonic calibration, serialised as knots — never as a pickle.

``p_relevant`` is an exhibit. A raw cosine of 0.83 means nothing to a supervisor and less to
a court; a calibrated 0.83 means *of a hundred candidates that scored like this one, about
eighty-three were later judged genuine precursors*, and that sentence is only true if
someone fitted the mapping on labelled data and can show the fit.

Which is why the artefact is knots (recall lead D8):

* **A pickle is not auditable.** Nobody can read one, and nobody can re-derive
  ``p_relevant`` from one without running our code at our version.
* **A pickle is not safe to load.** ``recall_policy.calibrator`` is a JSONB column in a
  database several roles can write; unpickling from it would be arbitrary code execution
  behind an audit surface.
* **Knots are twenty lines of arithmetic.** :func:`evaluate_knots` takes the serialised
  document and a score and needs nothing but the standard library. A stranger with the
  policy row can reproduce every probability the gate ever showed.

The fit uses ``sklearn.isotonic.IsotonicRegression(increasing=True, out_of_bounds='clip')``
and then throws the estimator away, keeping ``(X_thresholds_, y_thresholds_)``. Between
knots the function is linear and outside the fitted range it clips — that is exactly what
sklearn's own ``predict`` does, so :func:`IsotonicCalibrator.predict_one` and
``IsotonicRegression.predict`` agree to floating-point noise. The unit suite pins that
agreement at 1e-12 rather than trusting the reading.

**Temporal blocking is enforced at fit time.** :func:`fit_isotonic` refuses a sample whose
fold is not in the declared fit folds, and :func:`assert_disjoint_folds` refuses an
evaluation that reaches into a fold the calibrator was fitted on. A calibrator scored on its
own fold reports the sharpness of its training set, which is the most flattering and least
informative number available.
"""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Final

from trappoint_recall.eval.measurement import DEFAULT_CONFIDENCE, wilson_interval

__all__ = [
    "CALIBRATOR_SCHEMA",
    "DEFAULT_RELIABILITY_BINS",
    "MIN_CALIBRATION_SAMPLES",
    "CalibrationRefused",
    "CalibrationReport",
    "CalibrationSample",
    "IsotonicCalibrator",
    "ReliabilityBin",
    "assert_disjoint_folds",
    "brier_score",
    "calibration_report",
    "evaluate_knots",
    "expected_calibration_error",
    "fit_isotonic",
    "maximum_calibration_error",
    "reliability_diagram",
]

CALIBRATOR_SCHEMA: Final = "trappoint.recall.calibrator.isotonic/1"
"""Written into ``recall_policy.calibrator``. A reader that does not know this schema must
refuse the row rather than guess at the arrays."""

MIN_CALIBRATION_SAMPLES: Final = 20
"""Below this an isotonic fit is a memorisation of the calibration set. Deliberately low,
because it is a floor against nonsense rather than a claim of sufficiency — the honest
sample-size statement is the Wilson interval on every bin of the reliability diagram."""

DEFAULT_RELIABILITY_BINS: Final = 10
"""Equal-width bins on [0, 1]. Fixed, because a bin count chosen after seeing the result is
a tuning knob on the headline calibration error."""

_KNOT_TOLERANCE: Final = 1e-12
"""Monotonicity slack. Isotonic output is monotone by construction; this absorbs the last
few ulps of the pool-adjacent-violators arithmetic without absorbing a real inversion."""


class CalibrationRefused(ValueError):
    """A fit or an evaluation that would produce a number nobody should rely on.

    Every one of these is a refusal rather than a degraded result, because the failure mode
    is a plausible-looking probability on an exhibit.
    """


@dataclass(frozen=True, slots=True)
class CalibrationSample:
    """One labelled observation: a raw score, a binary label, and the fold it came from.

    Attributes:
        score: The scalar from :func:`~trappoint_recall.fusion.featurespec.raw_score`.
        label: 1 when the pair was judged a genuine precursor at or above the relevance
            floor, 0 otherwise.
        fold: Temporal block identifier. The unit of the blocked split, and the thing the
            leak guard checks.
        doc_id: Optional identity, carried for the audit trail only.
        gold_set: Which gold set the label came from (``G2`` weak co-membership, ``G3``
            adjudicated). Recorded because a calibrator trained mostly on G2 is trained
            mostly on weak supervision and the report must say so.
    """

    score: float
    label: int
    fold: str
    doc_id: str = ""
    gold_set: str = ""

    def __post_init__(self) -> None:
        if not math.isfinite(self.score):
            raise CalibrationRefused(f"sample {self.doc_id!r} has non-finite score")
        if self.label not in (0, 1):
            raise CalibrationRefused(
                f"sample {self.doc_id!r} has label {self.label!r}; isotonic calibration to a "
                "probability needs binary labels. Graded relevance is thresholded at the "
                "published relevance floor before it reaches here."
            )
        if not self.fold:
            raise CalibrationRefused(
                f"sample {self.doc_id!r} declares no fold. A sample with no temporal block "
                "cannot be kept out of its own evaluation."
            )


@dataclass(frozen=True, slots=True)
class IsotonicCalibrator:
    """A monotone piecewise-linear map from raw score to ``p_relevant``, as knots.

    Attributes:
        x: Knot abscissae, strictly increasing.
        y: Knot ordinates, non-decreasing, each in ``[0, 1]``.
        provenance: Everything needed to argue about the fit: the split policy, the folds,
            the feature-spec digest, the sample counts and the calibration-set digest.
    """

    x: tuple[float, ...]
    y: tuple[float, ...]
    provenance: Mapping[str, Any] = field(default_factory=dict)
    increasing: bool = True
    out_of_bounds: str = "clip"

    def __post_init__(self) -> None:
        if len(self.x) != len(self.y):
            raise CalibrationRefused(
                f"knot arrays differ in length: {len(self.x)} vs {len(self.y)}"
            )
        if len(self.x) < 2:
            raise CalibrationRefused(
                "a calibrator needs at least two knots; one knot is a constant probability, "
                "which is a refusal to calibrate rather than a calibration"
            )
        if self.out_of_bounds != "clip":
            raise CalibrationRefused(
                f"out_of_bounds must be 'clip', got {self.out_of_bounds!r}. Extrapolating an "
                "isotonic fit past its support invents probability where there was no data."
            )
        if not self.increasing:
            raise CalibrationRefused(
                "the calibrator must be increasing: the raw score is constructed to be "
                "monotone in evidence, and a decreasing fit would mean the score is inverted"
            )
        for index in range(len(self.x) - 1):
            if not self.x[index] < self.x[index + 1]:
                raise CalibrationRefused(
                    f"knot abscissae must be strictly increasing; x[{index}]={self.x[index]!r} "
                    f"is not below x[{index + 1}]={self.x[index + 1]!r}"
                )
            if self.y[index] > self.y[index + 1] + _KNOT_TOLERANCE:
                raise CalibrationRefused(
                    f"knot ordinates must be non-decreasing; y[{index}]={self.y[index]!r} "
                    f"exceeds y[{index + 1}]={self.y[index + 1]!r}"
                )
        for value in self.y:
            if not 0.0 <= value <= 1.0:
                raise CalibrationRefused(f"knot ordinate {value!r} is outside [0, 1]")
        for value in self.x:
            if not math.isfinite(value):
                raise CalibrationRefused("knot abscissa is not finite")

    @property
    def n_knots(self) -> int:
        return len(self.x)

    def predict_one(self, score: float) -> float:
        """Piecewise-linear interpolation between knots, clipped outside the fitted range."""
        return evaluate_knots(self.to_json(), score)

    def predict(self, scores: Iterable[float]) -> tuple[float, ...]:
        document = self.to_json()
        return tuple(evaluate_knots(document, score) for score in scores)

    def to_json(self) -> dict[str, Any]:
        """Return the exact JSON object stored in ``recall_policy.calibrator``."""
        return {
            "schema": CALIBRATOR_SCHEMA,
            "increasing": self.increasing,
            "out_of_bounds": self.out_of_bounds,
            "interpolation": "linear_between_knots",
            "x": list(self.x),
            "y": list(self.y),
            "provenance": dict(self.provenance),
        }

    @classmethod
    def from_json(cls, document: Mapping[str, Any]) -> IsotonicCalibrator:
        schema = document.get("schema")
        if schema != CALIBRATOR_SCHEMA:
            raise CalibrationRefused(
                f"unknown calibrator schema {schema!r}; refusing to guess at the arrays"
            )
        x = document.get("x")
        y = document.get("y")
        if not isinstance(x, list) or not isinstance(y, list):
            raise CalibrationRefused("calibrator document is missing its knot arrays")
        provenance = document.get("provenance")
        return cls(
            x=tuple(float(value) for value in x),
            y=tuple(float(value) for value in y),
            provenance=dict(provenance) if isinstance(provenance, Mapping) else {},
            increasing=bool(document.get("increasing", True)),
            out_of_bounds=str(document.get("out_of_bounds", "clip")),
        )

    def digest(self) -> str:
        """sha256 over the knots alone, so a policy row can be checked against a fit."""
        payload = json.dumps(
            {"x": list(self.x), "y": list(self.y)},
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
        return hashlib.sha256(payload).hexdigest()


def evaluate_knots(document: Mapping[str, Any], score: float) -> float:
    """Evaluate a serialised calibrator. Standard library only, no sklearn, no numpy.

    This is the function a stranger runs. It is deliberately self-contained and deliberately
    short: given ``recall_policy.calibrator`` and a raw score, it returns the exact
    ``p_relevant`` the gate recorded.

    Args:
        document: The object produced by :meth:`IsotonicCalibrator.to_json`.
        score: The raw score to map.

    Raises:
        CalibrationRefused: on a malformed document or a non-finite score.
    """
    x = document["x"]
    y = document["y"]
    if len(x) != len(y) or len(x) < 2:
        raise CalibrationRefused("calibrator document does not carry a usable knot set")
    if not math.isfinite(score):
        raise CalibrationRefused(f"cannot calibrate a non-finite score: {score!r}")
    if score <= x[0]:
        return float(y[0])
    if score >= x[-1]:
        return float(y[-1])
    low = 0
    high = len(x) - 1
    while high - low > 1:
        middle = (low + high) // 2
        if x[middle] <= score:
            low = middle
        else:
            high = middle
    span = x[high] - x[low]
    slope = (y[high] - y[low]) / span
    return float(slope * (score - x[low]) + y[low])


def assert_disjoint_folds(fit_folds: Iterable[str], eval_folds: Iterable[str]) -> None:
    """Refuse an evaluation that reaches into a fold the calibrator was fitted on.

    Raises:
        CalibrationRefused: if the two fold sets intersect.
    """
    overlap = sorted(set(fit_folds) & set(eval_folds))
    if overlap:
        raise CalibrationRefused(
            f"fold(s) {overlap} appear in both the fit set and the evaluation set. A "
            "calibrator scored on its own fold reports the sharpness of its training data; "
            "the temporally-blocked split exists precisely to make that impossible."
        )


def fit_isotonic(
    samples: Sequence[CalibrationSample],
    *,
    fit_folds: Sequence[str],
    split_policy_id: str,
    feature_spec_sha256: str,
    weights_sha256: str = "",
    note: str = "",
    fitted_at: datetime | None = None,
) -> IsotonicCalibrator:
    """Fit an isotonic calibrator on a temporally-blocked fit set and return its knots.

    Args:
        samples: Labelled observations. Every one must belong to a declared fit fold.
        fit_folds: The temporal blocks this calibrator is allowed to learn from.
        split_policy_id: Identifier of the
            :class:`~trappoint_recall.eval.splits.SplitPolicy` that produced the blocks.
        feature_spec_sha256: The feature spec the raw scores were built under. Recorded so a
            calibrator can never be applied to vectors from a different spec.
        weights_sha256: Digest of the policy weights used by ``raw_score``.
        note: Free text for the provenance record.
        fitted_at: Override for the timestamp, for reproducible artefacts.

    Raises:
        CalibrationRefused: on an empty or single-class sample, a sample from outside the
            declared fit folds, or fewer than two distinct scores.
    """
    # Deferred deliberately: importing this module must stay cheap, because everything else
    # in it — including the evaluator a stranger runs — needs nothing but the standard
    # library. sklearn is a declared dependency and is used here, at fit time, only.
    from sklearn.isotonic import IsotonicRegression  # noqa: PLC0415

    declared = set(fit_folds)
    if not declared:
        raise CalibrationRefused("fit_folds is empty: a calibrator with no declared fold "
                                 "cannot be kept out of its own evaluation")
    stray = sorted({s.fold for s in samples} - declared)
    if stray:
        raise CalibrationRefused(
            f"sample(s) from fold(s) {stray} were handed to a fit declared over "
            f"{sorted(declared)}. This is the leak the temporal split exists to prevent."
        )
    if len(samples) < MIN_CALIBRATION_SAMPLES:
        raise CalibrationRefused(
            f"{len(samples)} calibration samples is below the floor of "
            f"{MIN_CALIBRATION_SAMPLES}; an isotonic fit on fewer is a lookup table"
        )
    positives = sum(s.label for s in samples)
    if positives == 0 or positives == len(samples):
        raise CalibrationRefused(
            f"the calibration set has a single class ({positives} positive of "
            f"{len(samples)}); there is no probability to fit"
        )
    scores = [s.score for s in samples]
    if len({round(value, 15) for value in scores}) < 2:
        raise CalibrationRefused(
            "every calibration sample has the same raw score; the fit would be a constant"
        )

    estimator = IsotonicRegression(
        increasing=True, out_of_bounds="clip", y_min=0.0, y_max=1.0
    )
    estimator.fit(scores, [float(s.label) for s in samples])
    knots_x = [float(value) for value in estimator.X_thresholds_]
    knots_y = [float(value) for value in estimator.y_thresholds_]

    # Pool-adjacent-violators can emit repeated abscissae on tied inputs. Collapsing them to
    # the last ordinate reproduces the step the estimator itself evaluates, and keeps the
    # serialised knots strictly increasing so the stored artefact is unambiguous.
    collapsed_x: list[float] = []
    collapsed_y: list[float] = []
    for abscissa, ordinate in zip(knots_x, knots_y, strict=True):
        if collapsed_x and abscissa == collapsed_x[-1]:
            collapsed_y[-1] = ordinate
            continue
        collapsed_x.append(abscissa)
        collapsed_y.append(ordinate)

    by_fold: dict[str, int] = {}
    by_gold_set: dict[str, int] = {}
    for sample in samples:
        by_fold[sample.fold] = by_fold.get(sample.fold, 0) + 1
        key = sample.gold_set or "unlabelled_source"
        by_gold_set[key] = by_gold_set.get(key, 0) + 1

    provenance: dict[str, Any] = {
        "method": "isotonic_regression",
        "library": "scikit-learn IsotonicRegression(increasing=True, out_of_bounds='clip')",
        "split_policy_id": split_policy_id,
        "fit_folds": sorted(declared),
        "feature_spec_sha256": feature_spec_sha256,
        "weights_sha256": weights_sha256,
        "n_samples": len(samples),
        "n_positive": positives,
        "samples_by_fold": dict(sorted(by_fold.items())),
        "samples_by_gold_set": dict(sorted(by_gold_set.items())),
        "calibration_set_sha256": calibration_set_sha256(samples),
        "fitted_at": (fitted_at or datetime.now(UTC)).isoformat(timespec="seconds"),
        "note": note,
        "assumption": "The calibration set is assumed exchangeable with the population the "
        "gate will see. Safety corpora drift; recalibrate on a schedule and record the "
        "commit.",
    }
    return IsotonicCalibrator(
        x=tuple(collapsed_x), y=tuple(collapsed_y), provenance=provenance
    )


def calibration_set_sha256(samples: Sequence[CalibrationSample]) -> str:
    """Digest of the exact labelled set a calibrator was fitted on.

    Order-independent by construction (the entries are sorted), so two runs over the same
    set agree regardless of how the rows were assembled.
    """
    entries = sorted(
        (sample.doc_id, sample.fold, sample.gold_set, repr(sample.score), sample.label)
        for sample in samples
    )
    payload = json.dumps(entries, separators=(",", ":"), allow_nan=False).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


# --------------------------------------------------------------------------------------
# Reliability: the diagram, and the two scalar summaries that never replace it
# --------------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ReliabilityBin:
    """One bin of the reliability diagram, with a Wilson interval on the observed rate."""

    lower: float
    upper: float
    n: int
    mean_predicted: float
    observed_rate: float
    observed_lower: float
    observed_upper: float

    @property
    def gap(self) -> float:
        return self.observed_rate - self.mean_predicted

    def to_json(self) -> dict[str, float | int]:
        return {
            "lower": self.lower,
            "upper": self.upper,
            "n": self.n,
            "mean_predicted": self.mean_predicted,
            "observed_rate": self.observed_rate,
            "observed_lower": self.observed_lower,
            "observed_upper": self.observed_upper,
            "gap": self.gap,
        }


def _binned(
    predicted: Sequence[float], labels: Sequence[int], n_bins: int, confidence: float
) -> tuple[ReliabilityBin, ...]:
    if n_bins < 2:
        raise CalibrationRefused(f"a reliability diagram needs at least 2 bins, got {n_bins}")
    buckets: list[list[tuple[float, int]]] = [[] for _ in range(n_bins)]
    for probability, label in zip(predicted, labels, strict=True):
        if not 0.0 <= probability <= 1.0:
            raise CalibrationRefused(f"predicted probability {probability!r} is outside [0, 1]")
        index = min(int(probability * n_bins), n_bins - 1)
        buckets[index].append((probability, label))
    out: list[ReliabilityBin] = []
    for index, bucket in enumerate(buckets):
        lower = index / n_bins
        upper = (index + 1) / n_bins
        if not bucket:
            out.append(
                ReliabilityBin(
                    lower=lower,
                    upper=upper,
                    n=0,
                    mean_predicted=0.0,
                    observed_rate=0.0,
                    observed_lower=0.0,
                    observed_upper=1.0,
                )
            )
            continue
        successes = sum(label for _, label in bucket)
        interval = wilson_interval(successes, len(bucket), confidence=confidence)
        out.append(
            ReliabilityBin(
                lower=lower,
                upper=upper,
                n=len(bucket),
                mean_predicted=sum(p for p, _ in bucket) / len(bucket),
                observed_rate=successes / len(bucket),
                observed_lower=interval[0],
                observed_upper=interval[1],
            )
        )
    return tuple(out)


def reliability_diagram(
    predicted: Sequence[float],
    labels: Sequence[int],
    *,
    n_bins: int = DEFAULT_RELIABILITY_BINS,
    confidence: float = DEFAULT_CONFIDENCE,
) -> tuple[ReliabilityBin, ...]:
    """Equal-width reliability bins, each with a Wilson interval on the observed rate."""
    return _binned(predicted, labels, n_bins, confidence)


def brier_score(predicted: Sequence[float], labels: Sequence[int]) -> float:
    """Mean squared error of the probability forecast. Lower is better; 0.25 is a coin."""
    if not predicted:
        raise CalibrationRefused("the Brier score of an empty sample is not a number")
    total = 0.0
    for probability, label in zip(predicted, labels, strict=True):
        total += (probability - label) ** 2
    return total / len(predicted)


def expected_calibration_error(bins: Sequence[ReliabilityBin]) -> float:
    """Sample-weighted mean absolute gap between predicted and observed."""
    total = sum(b.n for b in bins)
    if total == 0:
        raise CalibrationRefused("the ECE of an empty sample is not a number")
    return sum(b.n * abs(b.gap) for b in bins) / total


def maximum_calibration_error(bins: Sequence[ReliabilityBin]) -> float:
    """Worst populated bin. The number that matters when one band feeds the gate."""
    populated = [b for b in bins if b.n > 0]
    if not populated:
        raise CalibrationRefused("the MCE of an empty sample is not a number")
    return max(abs(b.gap) for b in populated)


@dataclass(frozen=True, slots=True)
class CalibrationReport:
    """The emitted artefact: a diagram, two summaries, and the folds that produced them."""

    split_policy_id: str
    fit_folds: tuple[str, ...]
    eval_folds: tuple[str, ...]
    n: int
    n_positive: int
    brier: float
    ece: float
    mce: float
    bins: tuple[ReliabilityBin, ...]
    calibrator_digest: str
    feature_spec_sha256: str
    synthetic: bool
    preliminary: bool
    gold_set_counts: Mapping[str, int] = field(default_factory=dict)
    note: str = ""

    def to_json(self) -> dict[str, Any]:
        return {
            "schema": "trappoint.recall.calibration_report/1",
            "split_policy_id": self.split_policy_id,
            "fit_folds": list(self.fit_folds),
            "eval_folds": list(self.eval_folds),
            "n": self.n,
            "n_positive": self.n_positive,
            "brier": self.brier,
            "ece": self.ece,
            "mce": self.mce,
            "bins": [b.to_json() for b in self.bins],
            "calibrator_digest": self.calibrator_digest,
            "feature_spec_sha256": self.feature_spec_sha256,
            "gold_set_counts": dict(self.gold_set_counts),
            "synthetic": self.synthetic,
            "preliminary": self.preliminary,
            "note": self.note,
        }

    def to_markdown(self) -> str:
        """Render a reliability diagram a reader can check without a plotting library."""
        lines = ["# Recall calibration report", ""]
        if self.synthetic:
            lines.append(
                "**SYNTHETIC CALIBRATION SET** - these numbers characterise the calibrator "
                "implementation, not the product."
            )
        if self.preliminary:
            lines.append(
                "**PRELIMINARY** - no customer-grade calibration is claimed at this checkpoint."
            )
        lines.extend(
            [
                "",
                f"**Split policy:** `{self.split_policy_id}`",
                f"**Fit folds:** {', '.join(self.fit_folds) or 'none'}",
                f"**Evaluation folds:** {', '.join(self.eval_folds) or 'none'}",
                f"**Calibrator digest:** `{self.calibrator_digest}`",
                f"**Feature spec:** `{self.feature_spec_sha256}`",
                "",
                (
                    f"**Brier:** {self.brier:.4f} | **ECE:** {self.ece:.4f} | "
                    f"**MCE:** {self.mce:.4f} | n = {self.n} ({self.n_positive} positive)"
                ),
                "",
                "## Reliability diagram",
                "",
                "| bin | n | mean predicted | observed | 95% interval | gap |",
                "|---|---:|---:|---:|---|---:|",
            ]
        )
        for b in self.bins:
            if b.n == 0:
                lines.append(
                    f"| [{b.lower:.1f}, {b.upper:.1f}) | 0 | - | - | - | - |"
                )
                continue
            lines.append(
                f"| [{b.lower:.1f}, {b.upper:.1f}) | {b.n} | {b.mean_predicted:.4f} | "
                f"{b.observed_rate:.4f} | [{b.observed_lower:.4f}, {b.observed_upper:.4f}] | "
                f"{b.gap:+.4f} |"
            )
        lines.extend(
            [
                "",
                (
                    "A gap whose Wilson interval straddles zero is not evidence of "
                    "miscalibration at that band; a gap whose interval excludes zero is."
                ),
                "",
            ]
        )
        if self.note:
            lines.extend([self.note, ""])
        return "\n".join(lines)


def calibration_report(
    calibrator: IsotonicCalibrator,
    eval_samples: Sequence[CalibrationSample],
    *,
    fit_folds: Sequence[str],
    split_policy_id: str,
    feature_spec_sha256: str,
    n_bins: int = DEFAULT_RELIABILITY_BINS,
    confidence: float = DEFAULT_CONFIDENCE,
    synthetic: bool = False,
    preliminary: bool = True,
    note: str = "",
) -> CalibrationReport:
    """Score a calibrator on held-out folds, refusing any overlap with the fit folds.

    Raises:
        CalibrationRefused: if the evaluation folds intersect the fit folds, or if the
            evaluation sample is empty.
    """
    if not eval_samples:
        raise CalibrationRefused(
            "no held-out samples: a calibration report on an empty evaluation fold is not a "
            "measurement, and reporting it as one would be worse than reporting nothing"
        )
    eval_folds = tuple(sorted({s.fold for s in eval_samples}))
    assert_disjoint_folds(fit_folds, eval_folds)

    predicted = calibrator.predict(s.score for s in eval_samples)
    labels = [s.label for s in eval_samples]
    bins = reliability_diagram(predicted, labels, n_bins=n_bins, confidence=confidence)
    gold_set_counts: dict[str, int] = {}
    for sample in eval_samples:
        key = sample.gold_set or "unlabelled_source"
        gold_set_counts[key] = gold_set_counts.get(key, 0) + 1

    return CalibrationReport(
        split_policy_id=split_policy_id,
        fit_folds=tuple(sorted(set(fit_folds))),
        eval_folds=eval_folds,
        n=len(eval_samples),
        n_positive=sum(labels),
        brier=brier_score(predicted, labels),
        ece=expected_calibration_error(bins),
        mce=maximum_calibration_error(bins),
        bins=bins,
        calibrator_digest=calibrator.digest(),
        feature_spec_sha256=feature_spec_sha256,
        synthetic=synthetic,
        preliminary=preliminary,
        gold_set_counts=dict(sorted(gold_set_counts.items())),
        note=note,
    )
