# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""Checking this package's arithmetic against independent third-party implementations.

The Wilson interval and the nDCG in :mod:`trappoint_recall.eval.measurement` and
:mod:`trappoint_recall.eval.metrics` are implemented here rather than imported, so that
a reader with the standard library can follow them. That choice buys legibility and
costs a check: nothing stops a hand-rolled statistic from being subtly wrong.

So the same quantities are recomputed with **scipy** (normal quantile, and the exact
Wilson closed form) and **scikit-learn** (``ndcg_score``, linear gains) and required to
agree. Both are hard dependencies of this distribution: an optional cross-check is a
cross-check that is quietly unavailable in the one environment where it mattered.

The imports are dynamic so that a missing wheel produces
:class:`CrosscheckUnavailable` with a legible message rather than an import error at
collection time in a lane that was only ever going to compute a Wilson bound.
"""

from __future__ import annotations

import importlib
from collections.abc import Sequence
from dataclasses import dataclass
from types import ModuleType
from typing import Literal

from trappoint_recall.eval.measurement import normal_ppf, wilson_interval
from trappoint_recall.eval.metrics import dcg

__all__ = [
    "CrosscheckResult",
    "CrosscheckUnavailable",
    "crosscheck_all",
    "crosscheck_ndcg",
    "crosscheck_normal_quantile",
    "crosscheck_wilson",
]

NORMAL_QUANTILE_TOLERANCE = 1e-9
"""Relative, not absolute. In the extreme tails (p within 1e-6 of 0 or 1) the input float
itself has already lost the information the quantile needs, so both implementations are
accurate only to a relative bound there. Over the range release gates actually use
(0.90 to 0.99) the two agree to machine precision, which the test suite asserts separately."""

WILSON_TOLERANCE = 1e-12
NDCG_TOLERANCE = 1e-9


class CrosscheckUnavailable(RuntimeError):
    """Raised when a required third-party reference implementation cannot be imported."""


def _require(module_name: str) -> ModuleType:
    try:
        return importlib.import_module(module_name)
    except ImportError as exc:  # pragma: no cover - environment defect
        raise CrosscheckUnavailable(
            f"{module_name} is a declared dependency of trappoint-recall and is required "
            "for the metric cross-check. Install the package's dependencies; do not skip "
            "the check."
        ) from exc


@dataclass(frozen=True, slots=True)
class CrosscheckResult:
    """One comparison: what we computed, what the reference computed, how far apart."""

    name: str
    reference: str
    max_difference: float
    tolerance: float
    samples: int
    difference_kind: Literal["absolute", "relative"] = "absolute"

    @property
    def agrees(self) -> bool:
        return self.max_difference <= self.tolerance

    def render(self) -> str:
        verdict = "AGREES" if self.agrees else "DISAGREES"
        symbol = "|delta|" if self.difference_kind == "absolute" else "|delta|/|ref|"
        return (
            f"[{verdict}] {self.name} vs {self.reference}: max {symbol} = "
            f"{self.max_difference:.3e} over {self.samples} samples "
            f"(tolerance {self.tolerance:.0e})"
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "reference": self.reference,
            "max_difference": self.max_difference,
            "difference_kind": self.difference_kind,
            "tolerance": self.tolerance,
            "samples": self.samples,
            "agrees": self.agrees,
        }


def crosscheck_normal_quantile() -> CrosscheckResult:
    """Compare :func:`normal_ppf` against ``scipy.stats.norm.ppf``."""
    stats = _require("scipy.stats")
    probabilities = [
        1e-6,
        1e-4,
        0.001,
        0.01,
        0.025,
        0.05,
        0.1,
        0.25,
        0.4,
        0.5,
        0.6,
        0.75,
        0.9,
        0.95,
        0.975,
        0.99,
        0.999,
        1 - 1e-4,
        1 - 1e-6,
    ]
    worst = 0.0
    for p in probabilities:
        reference = float(stats.norm.ppf(p))
        delta = abs(normal_ppf(p) - reference)
        worst = max(worst, delta if reference == 0.0 else delta / abs(reference))
    return CrosscheckResult(
        name="normal_ppf",
        reference="scipy.stats.norm.ppf",
        max_difference=worst,
        tolerance=NORMAL_QUANTILE_TOLERANCE,
        samples=len(probabilities),
        difference_kind="relative",
    )


def _reference_wilson(k: int, n: int, z: float) -> tuple[float, float]:
    p = k / n
    z2 = z * z
    denom = 1.0 + z2 / n
    centre = (p + z2 / (2.0 * n)) / denom
    half = z * ((p * (1.0 - p) / n + z2 / (4.0 * n * n)) ** 0.5) / denom
    return (max(0.0, centre - half), min(1.0, centre + half))


def crosscheck_wilson() -> CrosscheckResult:
    """Compare :func:`wilson_interval` against the closed form driven by scipy's z."""
    stats = _require("scipy.stats")
    z = float(stats.norm.ppf(0.975))
    cases = [
        (k, n)
        for n in (1, 2, 5, 17, 50, 200, 1000)
        for k in (0, 1, n // 2, n - 1, n)
        if 0 <= k <= n
    ]
    worst = 0.0
    for k, n in cases:
        lo, hi = wilson_interval(k, n)
        ref_lo, ref_hi = _reference_wilson(k, n, z)
        worst = max(worst, abs(lo - ref_lo), abs(hi - ref_hi))
    return CrosscheckResult(
        name="wilson_interval",
        reference="closed form with scipy z",
        max_difference=worst,
        tolerance=WILSON_TOLERANCE,
        samples=len(cases),
    )


def crosscheck_ndcg() -> CrosscheckResult:
    """Compare this package's DCG (linear gains) against ``sklearn.metrics.ndcg_score``.

    scikit-learn implements linear gains only, which is why
    :func:`~trappoint_recall.eval.metrics.ndcg_at_k` carries a ``gain="linear"`` mode:
    a cross-check that could not run against the reference would not be a cross-check.
    The shipped default remains exponential gains, the TREC convention for a graded
    scale where grade 3 means "this is the precursor".
    """
    metrics_module = _require("sklearn.metrics")
    cases: Sequence[tuple[Sequence[int], Sequence[float]]] = (
        ([3, 2, 1, 0, 0], [0.9, 0.8, 0.7, 0.6, 0.5]),
        ([0, 0, 1, 2, 3], [0.9, 0.8, 0.7, 0.6, 0.5]),
        ([3, 0, 0, 0, 2], [0.95, 0.7, 0.6, 0.55, 0.5]),
        ([1, 1, 1, 1, 1], [0.5, 0.4, 0.3, 0.2, 0.1]),
        ([3, 3, 0, 0, 0], [0.99, 0.98, 0.10, 0.05, 0.01]),
    )
    worst = 0.0
    for grades, scores in cases:
        order = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)
        ranked_gains = [float(grades[i]) for i in order]
        ideal_gains = sorted((float(g) for g in grades), reverse=True)
        idcg = dcg(ideal_gains)
        ours = 0.0 if idcg <= 0.0 else dcg(ranked_gains) / idcg
        reference = float(metrics_module.ndcg_score([list(grades)], [list(scores)]))
        worst = max(worst, abs(ours - reference))
    return CrosscheckResult(
        name="ndcg (linear gains)",
        reference="sklearn.metrics.ndcg_score",
        max_difference=worst,
        tolerance=NDCG_TOLERANCE,
        samples=len(cases),
    )


def crosscheck_all() -> tuple[CrosscheckResult, ...]:
    """Run every cross-check. Raises :class:`CrosscheckUnavailable` if a reference is missing."""
    return (crosscheck_normal_quantile(), crosscheck_wilson(), crosscheck_ndcg())
