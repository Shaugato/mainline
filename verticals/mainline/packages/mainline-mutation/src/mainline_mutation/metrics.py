# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""Aggregate results into the figures that get published.  Lower bounds only.

FOUR BREAKDOWNS, AND EACH ONE ANSWERS A DIFFERENT QUESTION
-----------------------------------------------------------
``per_class``
    "Which mutation does this system miss?"  The one an engineer acts on.
``per_family``
    "Which document family is it worst on?"  A kill rate that is high on permits
    and low on ventilation standards is two facts, and the aggregate is neither.
``per_class_family``
    The cross.  Sparse by construction — most classes touch a few families — so
    every cell carries its own denominator and most lower bounds are near zero.
    Published anyway: a cell with two trials that *looks* weak is more honest
    than a cell quietly folded into a bigger one.
``overall``
    One number per catalogue.  Two numbers, never one; decision D13 forbids an
    "accuracy" figure over both.

THE FALSE-IDENTITY-CHANGE RATE IS PUBLISHED AS A POINT ESTIMATE AND SAYS SO
----------------------------------------------------------------------------
The brief asks for it, and it is the complement of the SURVIVE preservation
rate.  Complementing a lower bound gives an *upper* bound, which would be the
optimistic direction for a false-positive rate — so the conservative figure for
the SURVIVE catalogue is the Wilson LOWER bound on **preservation**, and the
false-identity-change rate travels beside it explicitly labelled a point
estimate.  Both are in the artefact; only one is a claim.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Final

from .model import KILL, SURVIVE, ClassMetric, MutationKind, MutationResult
from .wilson import REPORT_DP, WilsonInterval, wilson_interval

__all__ = [
    "ALL_FAMILIES",
    "CatalogueMetric",
    "false_identity_change_rate",
    "false_weaken_rate",
    "metric_for",
    "per_class",
    "per_class_family",
    "per_family",
    "summarise",
    "surviving_classes",
]

#: The pseudo-family used for the "every family" rollup, so that a caller
#: reading ``per_class`` and ``per_class_family`` sees one shape.
ALL_FAMILIES: Final[str] = "*"


@dataclass(frozen=True, slots=True)
class CatalogueMetric:
    """The one headline figure for one catalogue, with its evidence."""

    kind: MutationKind
    successes: int
    trials: int
    interval: WilsonInterval
    outcome_counts: dict[str, int]


def metric_for(
    results: Sequence[MutationResult],
    *,
    kind: MutationKind,
    class_id: str,
    family: str,
    confidence: str,
) -> ClassMetric:
    """Compute one cell: successes over trials, with the Wilson interval."""
    successes = sum(1 for r in results if r.success)
    interval = wilson_interval(successes, len(results), confidence=confidence)
    return ClassMetric(
        kind=kind,
        class_id=class_id,
        family=family,
        successes=successes,
        trials=len(results),
        wilson_lower=interval.lower,
        point_estimate=interval.point,
        wilson_upper=interval.upper,
        confidence=confidence,
        outcome_counts=dict(Counter(r.outcome for r in results)),
    )


def _grouped(
    results: Iterable[MutationResult],
    key: str,
) -> dict[tuple[MutationKind, str], list[MutationResult]]:
    buckets: dict[tuple[MutationKind, str], list[MutationResult]] = {}
    for result in results:
        buckets.setdefault((result.kind, getattr(result, key)), []).append(result)
    return buckets


def per_class(results: Sequence[MutationResult], *, confidence: str) -> tuple[ClassMetric, ...]:
    """One figure per mutation class, across every family."""
    return tuple(
        metric_for(bucket, kind=kind, class_id=class_id, family=ALL_FAMILIES, confidence=confidence)
        for (kind, class_id), bucket in sorted(_grouped(results, "class_id").items())
    )


def per_family(results: Sequence[MutationResult], *, confidence: str) -> tuple[ClassMetric, ...]:
    """One figure per document family, across every class."""
    return tuple(
        metric_for(bucket, kind=kind, class_id=ALL_FAMILIES, family=family, confidence=confidence)
        for (kind, family), bucket in sorted(_grouped(results, "family").items())
    )


def per_class_family(
    results: Sequence[MutationResult], *, confidence: str
) -> tuple[ClassMetric, ...]:
    """The cross: one figure per (class, family) cell that has at least one trial."""
    buckets: dict[tuple[MutationKind, str, str], list[MutationResult]] = {}
    for result in results:
        buckets.setdefault((result.kind, result.class_id, result.family), []).append(result)
    return tuple(
        metric_for(bucket, kind=kind, class_id=class_id, family=family, confidence=confidence)
        for (kind, class_id, family), bucket in sorted(buckets.items())
    )


def summarise(
    results: Sequence[MutationResult], *, kind: MutationKind, confidence: str
) -> CatalogueMetric:
    """The headline figure for one catalogue."""
    subset = [r for r in results if r.kind == kind]
    successes = sum(1 for r in subset if r.success)
    return CatalogueMetric(
        kind=kind,
        successes=successes,
        trials=len(subset),
        interval=wilson_interval(successes, len(subset), confidence=confidence),
        outcome_counts=dict(Counter(r.outcome for r in subset)),
    )


def false_identity_change_rate(results: Sequence[MutationResult]) -> float:
    """The SURVIVE catalogue's manufactured-false-positive rate, as a POINT ESTIMATE.

    A rate, not a bound, and the docstring says so because the number does.  The
    conservative figure for this catalogue is the Wilson **lower** bound on
    preservation (:func:`summarise`), and complementing that bound would produce
    an upper bound on the failure rate — the optimistic direction for a
    false-positive number, which is exactly the direction this package refuses
    to publish anything in.
    """
    subset = [r for r in results if r.kind == SURVIVE]
    if not subset:
        return 0.0
    failed = sum(
        1 for r in subset if r.outcome in ("identity_changed", "identity_changed_and_false_weaken")
    )
    return round(failed / len(subset), REPORT_DP)


def false_weaken_rate(results: Sequence[MutationResult]) -> float:
    """The SURVIVE catalogue's manufactured-weakening rate.  Also a point estimate."""
    subset = [r for r in results if r.kind == SURVIVE]
    if not subset:
        return 0.0
    failed = sum(
        1 for r in subset if r.outcome in ("false_weaken", "identity_changed_and_false_weaken")
    )
    return round(failed / len(subset), REPORT_DP)


def surviving_classes(results: Sequence[MutationResult]) -> tuple[str, ...]:
    """KILL classes with at least one mutant that reached the gate undetected.

    The named residual risk.  ``done_when`` asks for the crippled run to report a
    kill rate below 1.0 *with a named surviving class*, and this is the naming.
    """
    return tuple(
        sorted({r.class_id for r in results if r.kind == KILL and r.outcome == "survived"})
    )
