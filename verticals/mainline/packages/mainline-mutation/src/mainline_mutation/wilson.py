# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""The Wilson score interval, implemented directly, in six lines of arithmetic.

WHY THIS IS NOT A DEPENDENCY
----------------------------
The brief forbids adding ``statsmodels`` and the prohibition is not about wheel
size.  This module produces the only number this domain publishes about its own
residual risk, and that number has to survive an opposing expert with a
calculator.  ``proportion_confint(k, n, method='wilson')`` is a correct answer
from a black box; six lines whose preimage is written out below is an answer a
reader can check.

WHY THE LOWER BOUND AND NEVER THE POINT ESTIMATE
------------------------------------------------
Three of three mutants killed is a point estimate of 1.0 and a Wilson lower
bound of 0.44.  Publishing 1.0 there is not optimism, it is a false statement
about how much evidence exists — and this domain's whole argument is that a
number nobody can be wrong about beats a number that sounds good.  So every
public surface in this package — the JSON artefact, the CLI table, the SQL row —
carries ``kill_rate_wilson_lower`` and the point estimate travels beside it
clearly labelled as such.

THE INTERVAL, WRITTEN OUT
-------------------------
For ``k`` successes in ``n`` trials at two-sided confidence ``1 - alpha``, with
``z`` the standard normal quantile at ``1 - alpha/2``::

    p     = k / n
    denom = 1 + z**2 / n
    centre = (p + z**2 / (2n)) / denom
    half   = z * sqrt( p(1-p)/n + z**2/(4 n**2) ) / denom
    (lower, upper) = (centre - half, centre + half)

Wilson (1927), *Probable Inference, the Law of Succession, and Statistical
Inference*, JASA 22(158).  Nothing here is a contribution; the contribution is
that the harness reports the bound rather than the ratio.

DETERMINISM
-----------
The arithmetic is IEEE-754 double throughout and every operation is one of
``+ - * / sqrt``, all of which are correctly rounded by the standard, so the
result is bit-identical on any conforming platform.  :func:`wilson_lower` still
rounds to :data:`REPORT_DP` before it reaches a report, because a decimal string
is what gets compared between two runs and an 18th-digit difference in a
printed float is a difference a reader cannot act on.
"""

from __future__ import annotations

import math
from typing import Final

__all__ = [
    "REPORT_DP",
    "Z_BY_CONFIDENCE",
    "WilsonInterval",
    "wilson_interval",
    "wilson_lower",
]

#: Standard-normal two-sided quantiles, written out rather than computed, so
#: that the constant a published number depends on is visible in the diff that
#: changes it.  Values are ``scipy.stats.norm.ppf(1 - alpha/2)`` to 15 digits;
#: the harness never imports scipy, it just agrees with it.
Z_BY_CONFIDENCE: Final[dict[str, float]] = {
    "0.90": 1.6448536269514722,
    "0.95": 1.959963984540054,
    "0.99": 2.5758293035489004,
}

#: Decimal places every published proportion is rounded to.  Six is far more
#: precision than a sample of a few hundred mutants supports; it exists so that
#: two runs of the same seed compare equal as strings, not so that the sixth
#: digit means anything.
REPORT_DP: Final[int] = 6


class WilsonInterval:
    """A proportion, its interval, and the evidence it rests on.

    Deliberately not a ``NamedTuple``: a caller that unpacks this by position
    will one day unpack ``(lower, upper)`` in the order ``(upper, lower)`` and
    publish an over-confident number, and the attribute names are the whole
    defence against that.
    """

    __slots__ = ("confidence", "denominator", "lower", "numerator", "point", "upper")

    def __init__(
        self,
        *,
        numerator: int,
        denominator: int,
        point: float,
        lower: float,
        upper: float,
        confidence: str,
    ) -> None:
        """Store one computed interval.  Constructed only by :func:`wilson_interval`."""
        self.numerator = numerator
        self.denominator = denominator
        self.point = point
        self.lower = lower
        self.upper = upper
        self.confidence = confidence

    def as_dict(self) -> dict[str, object]:
        """Render for the JSON artefact, lower bound first because it is the claim."""
        return {
            "wilson_lower": self.lower,
            "point_estimate": self.point,
            "wilson_upper": self.upper,
            "numerator": self.numerator,
            "denominator": self.denominator,
            "confidence": self.confidence,
        }

    def __repr__(self) -> str:
        """Show the bound and the evidence, never the point estimate alone."""
        return (
            f"WilsonInterval(lower={self.lower}, point={self.point}, upper={self.upper}, "
            f"{self.numerator}/{self.denominator} @ {self.confidence})"
        )

    def __eq__(self, other: object) -> bool:
        """Compare on every field, so a report diff is a real diff."""
        if not isinstance(other, WilsonInterval):
            return NotImplemented
        return self.as_dict() == other.as_dict()

    def __hash__(self) -> int:
        """Hash the same tuple :meth:`__eq__` compares."""
        return hash(
            (self.numerator, self.denominator, self.point, self.lower, self.upper, self.confidence)
        )


def wilson_interval(
    numerator: int,
    denominator: int,
    *,
    confidence: str = "0.95",
) -> WilsonInterval:
    """Return the Wilson score interval for ``numerator`` successes in ``denominator`` trials.

    ``denominator == 0`` returns ``lower=0.0, point=0.0, upper=1.0``.  That is
    the honest answer for no evidence and it is deliberately the *worst* answer:
    a mutation class with no fixtures must not be able to raise a published
    kill rate, and returning ``lower=0.0`` means an unpopulated class visibly
    drags the aggregate down until somebody writes its fixture.

    :raises ValueError: on a negative trial count, a negative success count, a
        success count exceeding the trial count, or an unlisted confidence.
    """
    if denominator < 0:
        raise ValueError(f"denominator must be non-negative; got {denominator}")
    if numerator < 0:
        raise ValueError(f"numerator must be non-negative; got {numerator}")
    if numerator > denominator:
        raise ValueError(
            f"a proportion cannot exceed 1: {numerator} successes in {denominator} trials"
        )
    z = Z_BY_CONFIDENCE.get(confidence)
    if z is None:
        raise ValueError(
            f"confidence {confidence!r} is not one of {sorted(Z_BY_CONFIDENCE)}; the quantile "
            "table is written out on purpose so that the constant a published number depends "
            "on is visible in the diff that changes it"
        )

    if denominator == 0:
        return WilsonInterval(
            numerator=0,
            denominator=0,
            point=0.0,
            lower=0.0,
            upper=1.0,
            confidence=confidence,
        )

    n = float(denominator)
    p = numerator / n
    z2 = z * z
    denom = 1.0 + z2 / n
    centre = (p + z2 / (2.0 * n)) / denom
    half = z * math.sqrt(p * (1.0 - p) / n + z2 / (4.0 * n * n)) / denom

    lower = max(0.0, centre - half)
    upper = min(1.0, centre + half)
    return WilsonInterval(
        numerator=numerator,
        denominator=denominator,
        point=round(p, REPORT_DP),
        lower=round(lower, REPORT_DP),
        upper=round(upper, REPORT_DP),
        confidence=confidence,
    )


def wilson_lower(numerator: int, denominator: int, *, confidence: str = "0.95") -> float:
    """The lower bound alone — the only proportion this package lets a caller print bare."""
    return wilson_interval(numerator, denominator, confidence=confidence).lower
