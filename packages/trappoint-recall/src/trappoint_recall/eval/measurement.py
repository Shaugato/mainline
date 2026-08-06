# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""The unit of every recall number: a point estimate that cannot be separated from
its interval, its sample size and the split policy that produced it.

Why this is a type and not a convention
---------------------------------------
``Retro-Recall@3 = 0.91`` is not a fact. ``Retro-Recall@3 = 0.91, 95% Wilson
[0.84, 0.95], n = 214, split TB-2024-11-01-a3f9`` is a fact. With ~200 adjudicated
pairs the interval is wide, and a release gate on the point estimate manufactures
false confidence in precisely the number that ends up in a sales deck
(BUILD_PLAN.md, G4-beta). Making :class:`Measurement` the only return type of every
metric in this package means the interval cannot be dropped by accident on the way
to a slide; :mod:`scripts.recall.no_bare_point_estimates` closes the same hole in
prose.

Interval methods, stated rather than assumed
--------------------------------------------
Wilson score intervals are correct for **binomial proportions** and nothing else.
``Retro-Recall@k``, ``P@block`` and the nuisance rate are proportions, so they get
Wilson. ``nDCG@10``, ``MRR`` and *mean blocking checks per permit* are means of
per-query quantities, not proportions; applying Wilson to them would be a category
error dressed up as rigour, so they get a deterministic bootstrap percentile
interval and say so in :attr:`Measurement.interval_method`.
"""

from __future__ import annotations

import hashlib
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Final, Literal

import numpy as np

__all__ = [
    "DEFAULT_CONFIDENCE",
    "IntervalMethod",
    "Measurement",
    "bootstrap_mean_interval",
    "normal_ppf",
    "undefined_measurement",
    "wilson_interval",
]

DEFAULT_CONFIDENCE: Final = 0.95
"""Two-sided confidence used by every release gate. Never widened to make a gate pass."""

BOOTSTRAP_RESAMPLES: Final = 10_000
"""Fixed. A resample count that moves with the result is a tuning knob on the interval."""

_FLOAT_SLACK: Final = 1e-9

IntervalMethod = Literal["wilson", "bootstrap_percentile", "none"]

# --------------------------------------------------------------------------------------
# Normal quantile, implemented here rather than imported
# --------------------------------------------------------------------------------------
# Acklam's rational approximation refined by one Halley step against math.erfc. This
# is deliberately not scipy: the z used by a release gate should be computable by a
# reader with the standard library and no wheels. scipy is still a declared dependency
# and trappoint_recall.eval.crosscheck asserts the two agree to 1e-12.

_A: Final = (
    -3.969683028665376e01,
    2.209460984245205e02,
    -2.759285104469687e02,
    1.383577518672690e02,
    -3.066479806614716e01,
    2.506628277459239e00,
)
_B: Final = (
    -5.447609879822406e01,
    1.615858368580409e02,
    -1.556989798598866e02,
    6.680131188771972e01,
    -1.328068155288572e01,
)
_C: Final = (
    -7.784894002430293e-03,
    -3.223964580411365e-01,
    -2.400758277161838e00,
    -2.549732539343734e00,
    4.374664141464968e00,
    2.938163982698783e00,
)
_D: Final = (
    7.784695709041462e-03,
    3.224671290700398e-01,
    2.445134137142996e00,
    3.754408661907416e00,
)
_P_LOW: Final = 0.02425


def normal_ppf(p: float) -> float:
    """Inverse CDF of the standard normal, accurate to ~1e-15 on (0, 1).

    Raises:
        ValueError: if ``p`` is not strictly inside (0, 1).
    """
    if not (0.0 < p < 1.0):
        raise ValueError(f"normal_ppf requires 0 < p < 1, got {p!r}")

    if p < _P_LOW:
        q = math.sqrt(-2.0 * math.log(p))
        x = (((((_C[0] * q + _C[1]) * q + _C[2]) * q + _C[3]) * q + _C[4]) * q + _C[5]) / (
            (((_D[0] * q + _D[1]) * q + _D[2]) * q + _D[3]) * q + 1.0
        )
    elif p <= 1.0 - _P_LOW:
        q = p - 0.5
        r = q * q
        x = (((((_A[0] * r + _A[1]) * r + _A[2]) * r + _A[3]) * r + _A[4]) * r + _A[5]) * q / (
            ((((_B[0] * r + _B[1]) * r + _B[2]) * r + _B[3]) * r + _B[4]) * r + 1.0
        )
    else:
        q = math.sqrt(-2.0 * math.log1p(-p))
        x = -(((((_C[0] * q + _C[1]) * q + _C[2]) * q + _C[3]) * q + _C[4]) * q + _C[5]) / (
            (((_D[0] * q + _D[1]) * q + _D[2]) * q + _D[3]) * q + 1.0
        )

    # One Halley refinement against the exact complementary error function.
    err = 0.5 * math.erfc(-x / math.sqrt(2.0)) - p
    u = err * math.sqrt(2.0 * math.pi) * math.exp(x * x / 2.0)
    return x - u / (1.0 + x * u / 2.0)


def _two_sided_z(confidence: float) -> float:
    if not (0.0 < confidence < 1.0):
        raise ValueError(f"confidence must be strictly inside (0, 1), got {confidence!r}")
    return normal_ppf(1.0 - (1.0 - confidence) / 2.0)


# --------------------------------------------------------------------------------------
# Intervals
# --------------------------------------------------------------------------------------


def wilson_interval(
    successes: int, n: int, *, confidence: float = DEFAULT_CONFIDENCE
) -> tuple[float, float]:
    """Wilson score interval for a binomial proportion.

    Chosen over the normal approximation because release gates live near p = 0.9 with
    n in the low hundreds, exactly where the Wald interval leaves [0, 1] and lies.

    ``n == 0`` returns the vacuous interval ``(0.0, 1.0)``. It is a *true* statement
    about a sample of size zero, and callers are expected to refuse to gate on it —
    see :func:`undefined_measurement`.
    """
    if n < 0:
        raise ValueError(f"n must be non-negative, got {n}")
    if not (0 <= successes <= n):
        raise ValueError(f"successes must satisfy 0 <= k <= n, got k={successes}, n={n}")
    if n == 0:
        return (0.0, 1.0)

    z = _two_sided_z(confidence)
    p = successes / n
    z2 = z * z
    denom = 1.0 + z2 / n
    centre = (p + z2 / (2.0 * n)) / denom
    half = z * math.sqrt(p * (1.0 - p) / n + z2 / (4.0 * n * n)) / denom
    lo = max(0.0, centre - half)
    hi = min(1.0, centre + half)
    # The Wilson score interval provably contains the point estimate, but at p = 0 or
    # p = 1 the closed form lands a few ulps the wrong side of it: at k = n the upper
    # bound evaluates to 0.9999999999999999. Clamping toward p restores a property the
    # mathematics already guarantees rather than widening any claim, and the property
    # test that found this asserts containment with no epsilon so it stays fixed.
    return (min(lo, p), max(hi, p))


def _seed_for(label: str, n: int) -> int:
    digest = hashlib.sha256(f"{label}:{n}".encode()).digest()
    return int.from_bytes(digest[:8], "big")


def bootstrap_mean_interval(
    values: Sequence[float],
    *,
    label: str,
    confidence: float = DEFAULT_CONFIDENCE,
    resamples: int = BOOTSTRAP_RESAMPLES,
) -> tuple[float, float]:
    """Deterministic bootstrap percentile interval for the mean of ``values``.

    The RNG seed is derived from ``label`` and ``len(values)`` by SHA-256, so the same
    evaluation produces the same interval on every machine and in every rerun. A
    non-reproducible confidence interval on an exhibit is not evidence.
    """
    n = len(values)
    if n == 0:
        return (0.0, 0.0)
    if n == 1:
        return (float(values[0]), float(values[0]))

    rng = np.random.default_rng(_seed_for(label, n))
    arr = np.asarray(values, dtype=np.float64)
    idx = rng.integers(0, n, size=(resamples, n))
    means = arr[idx].mean(axis=1)
    alpha = (1.0 - confidence) / 2.0
    lo = float(np.quantile(means, alpha))
    hi = float(np.quantile(means, 1.0 - alpha))
    return (lo, hi)


# --------------------------------------------------------------------------------------
# The type itself
# --------------------------------------------------------------------------------------

DetailValue = float | int | str | bool | None


@dataclass(frozen=True, slots=True)
class Measurement:
    """A number that carries everything needed to argue about it.

    Attributes:
        metric: Stable metric id, e.g. ``"retro_recall_at_3_sev5"``.
        value: The point estimate. Never published alone.
        lower: Lower bound of the two-sided interval at :attr:`confidence`.
        upper: Upper bound of the two-sided interval at :attr:`confidence`.
        n: Denominator. For proportions, the number of trials; for means, the number
            of per-query observations.
        split_policy_id: Identifier of the :class:`~trappoint_recall.eval.splits.SplitPolicy`
            that selected the evaluation set. A metric without a split policy is a
            number without an experiment.
        interval_method: How ``lower``/``upper`` were computed. ``"none"`` only ever
            appears on an undefined measurement.
        defined: ``False`` when the sample could not support the metric at all
            (empty denominator, insufficient judgement coverage). An undefined
            measurement never satisfies a floor and never clears a ceiling.
        undefined_reason: Required when ``defined`` is ``False``.
        detail: Free-form supporting counts. Numbers here are diagnostics, not claims.
    """

    metric: str
    value: float
    lower: float
    upper: float
    n: int
    split_policy_id: str
    confidence: float = DEFAULT_CONFIDENCE
    interval_method: IntervalMethod = "wilson"
    defined: bool = True
    undefined_reason: str | None = None
    detail: Mapping[str, DetailValue] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.n < 0:
            raise ValueError(f"{self.metric}: n must be non-negative, got {self.n}")
        if not (0.0 < self.confidence < 1.0):
            raise ValueError(f"{self.metric}: confidence must be inside (0, 1)")
        if self.lower > self.value + _FLOAT_SLACK:
            raise ValueError(f"{self.metric}: lower {self.lower} exceeds value {self.value}")
        if self.upper < self.value - _FLOAT_SLACK:
            raise ValueError(f"{self.metric}: upper {self.upper} is below value {self.value}")
        if not self.defined and not self.undefined_reason:
            raise ValueError(f"{self.metric}: an undefined measurement must carry a reason")
        if self.defined and self.interval_method == "none":
            raise ValueError(f"{self.metric}: a defined measurement must state an interval method")
        if not self.split_policy_id:
            raise ValueError(f"{self.metric}: split_policy_id is mandatory")

    # -- gate arithmetic ---------------------------------------------------------------

    def meets_floor(self, floor: float, *, on: Literal["lower", "value"] = "lower") -> bool:
        """True when this measurement clears ``floor``.

        ``on="lower"`` is the release-gate default: gate on the Wilson lower bound,
        never on the point estimate. An undefined measurement never clears a floor.
        """
        if not self.defined:
            return False
        observed = self.lower if on == "lower" else self.value
        return observed >= floor - _FLOAT_SLACK

    def under_ceiling(self, ceiling: float, *, on: Literal["upper", "value"] = "value") -> bool:
        """True when this measurement sits strictly under ``ceiling``.

        For a ceiling the conservative side of the interval is the *upper* bound; the
        G4-alpha checkpoint gates on the point estimate and reports the upper bound,
        and ``eval_floors.json`` records that G4-beta ratchets this to ``"upper"``.
        An undefined measurement never clears a ceiling.
        """
        if not self.defined:
            return False
        observed = self.upper if on == "upper" else self.value
        return observed < ceiling

    # -- rendering ---------------------------------------------------------------------

    def render(self) -> str:
        """One line, interval always attached. This is the only sanctioned rendering."""
        if not self.defined:
            return (
                f"{self.metric} = UNDEFINED ({self.undefined_reason}) "
                f"[n={self.n}, split={self.split_policy_id}]"
            )
        pct = round(self.confidence * 100)
        return (
            f"{self.metric} = {self.value:.4f} "
            f"[{self.lower:.4f}, {self.upper:.4f}] {pct}% {self.interval_method} "
            f"(n={self.n}, split={self.split_policy_id})"
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "metric": self.metric,
            "value": self.value,
            "lower": self.lower,
            "upper": self.upper,
            "n": self.n,
            "split_policy_id": self.split_policy_id,
            "confidence": self.confidence,
            "interval_method": self.interval_method,
            "defined": self.defined,
            "undefined_reason": self.undefined_reason,
            "detail": dict(self.detail),
        }

    # -- constructors ------------------------------------------------------------------

    @classmethod
    def proportion(
        cls,
        metric: str,
        successes: int,
        n: int,
        *,
        split_policy_id: str,
        confidence: float = DEFAULT_CONFIDENCE,
        detail: Mapping[str, DetailValue] | None = None,
    ) -> Measurement:
        """Build a Wilson-interval measurement from a binomial count."""
        if n == 0:
            return undefined_measurement(
                metric,
                split_policy_id=split_policy_id,
                reason="empty denominator: the sample contains no trials of this kind",
                confidence=confidence,
                detail=detail,
            )
        lo, hi = wilson_interval(successes, n, confidence=confidence)
        merged: dict[str, DetailValue] = {"successes": successes}
        if detail:
            merged.update(detail)
        return cls(
            metric=metric,
            value=successes / n,
            lower=lo,
            upper=hi,
            n=n,
            split_policy_id=split_policy_id,
            confidence=confidence,
            interval_method="wilson",
            detail=merged,
        )

    @classmethod
    def mean(
        cls,
        metric: str,
        values: Sequence[float],
        *,
        split_policy_id: str,
        confidence: float = DEFAULT_CONFIDENCE,
        detail: Mapping[str, DetailValue] | None = None,
    ) -> Measurement:
        """Build a bootstrap-interval measurement from per-observation values."""
        n = len(values)
        if n == 0:
            return undefined_measurement(
                metric,
                split_policy_id=split_policy_id,
                reason="empty denominator: the sample contains no observations",
                confidence=confidence,
                detail=detail,
            )
        point = float(np.mean(np.asarray(values, dtype=np.float64)))
        lo, hi = bootstrap_mean_interval(values, label=metric, confidence=confidence)
        # The bootstrap percentile interval can sit fractionally off the point estimate
        # on tiny samples; widen rather than lie about containment.
        lo = min(lo, point)
        hi = max(hi, point)
        return cls(
            metric=metric,
            value=point,
            lower=lo,
            upper=hi,
            n=n,
            split_policy_id=split_policy_id,
            confidence=confidence,
            interval_method="bootstrap_percentile",
            detail=dict(detail) if detail else {},
        )


def undefined_measurement(
    metric: str,
    *,
    split_policy_id: str,
    reason: str,
    confidence: float = DEFAULT_CONFIDENCE,
    detail: Mapping[str, DetailValue] | None = None,
) -> Measurement:
    """A measurement that exists, states that it could not be computed, and fails every gate."""
    return Measurement(
        metric=metric,
        value=0.0,
        lower=0.0,
        upper=1.0,
        n=0,
        split_policy_id=split_policy_id,
        confidence=confidence,
        interval_method="none",
        defined=False,
        undefined_reason=reason,
        detail=dict(detail) if detail else {},
    )
