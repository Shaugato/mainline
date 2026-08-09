# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
"""Where the drift started — and the discipline of refusing to name a culprit.

ARCHITECTURE.md §5.8 states the constraint that shapes this module: *because
controls are lost and restored, monotonicity does not hold globally*. A plain
binary search over a plant's history is therefore invalid — the history is not
sorted, and a bisect over an unsorted predicate returns an arbitrary element with
a confident-looking name attached.

So the search is two stages.

**Stage 1 — PELT brackets the most recent GOOD → BAD segment.** Pruned Exact
Linear Time changepoint detection over the observation series, with an L2
(mean-shift) cost. Exact, and exact in the arithmetic sense as well: the cost is
computed over :class:`~fractions.Fraction` prefix sums, never floats. A
changepoint that moved because of floating-point summation order would be a
culprit that changed between two runs of the same patrol over the same data, and
this is a record a lawyer reads.

**Stage 2 — a skip-aware binary search inside that bracket.** Monotonicity is
assumed *only* inside the bracket, and the assumption is **asserted** by probing
both endpoints rather than trusted. If it fails, the function refuses.

**UNKNOWN is first class.** If the search terminates against a region the
historian cannot answer for, the result is a *range*: ``bisect_lo`` and
``bisect_hi`` populated, ``culprit_elem`` NULL. §5.8 again: *fabricating a named
culprit from an unobservable interval is how this product gets a customer sued.*
:class:`~mainline_fixity.types.BisectOutcome` refuses at construction to hold
both a culprit and a range, so there is no shape of this result that lets a
reader take the name and drop the width.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from fractions import Fraction
from typing import TYPE_CHECKING, Final, Literal

from .errors import BisectBracketEmpty
from .types import BisectOutcome

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence
    from decimal import Decimal
    from uuid import UUID

__all__ = [
    "DEFAULT_PENALTY",
    "Bracket",
    "Probe",
    "ProbeResult",
    "bisect_culprit",
    "bracket_last_regression",
    "pelt",
]

#: The changepoint penalty, stated rather than hidden.
#:
#: For a 0/1 compliance indicator the L2 cost of a segment of length *n* holding
#: *k* ones is ``k - k**2 / n``. An isolated single flip in a long run therefore has a
#: maximum cost reduction approaching 1, and splitting it out costs ``2·penalty``.
#: A penalty of 1 suppresses isolated single-sample flips and admits a sustained
#: run of two or more. Raising it makes the patrol slower to declare a regression.
#: It is a visible number with a derivation, not a tuned default — a patrol whose
#: sensitivity is a magic constant cannot be cross-examined about its sensitivity.
DEFAULT_PENALTY: Final[Fraction] = Fraction(1)

#: A bisect needs a good anchor and a bad anchor. One element is not a search.
_MIN_BRACKET: Final[int] = 2


class ProbeResult(StrEnum):
    """What one probe of one candidate element established.

    ``SKIP`` is not a failure. It is the historian saying the interval is inside a
    compression corridor, or that the tag was out of service, or that the export
    for that window never arrived. Treating it as ``BAD`` would manufacture a
    culprit; treating it as ``GOOD`` would exonerate one.
    """

    GOOD = "good"
    BAD = "bad"
    SKIP = "skip"


#: A probe answers *was the bad behaviour present at this element*. Pure by
#: contract: this module calls it, caches nothing, and assumes no ordering of
#: calls. The caller owns whatever I/O the answer takes.
Probe = "Callable[[UUID], ProbeResult]"


@dataclass(frozen=True, slots=True)
class Bracket:
    """The most recent GOOD → BAD transition, as half-open index bounds.

    ``lo`` indexes the last sample of the good segment; ``hi`` indexes the first
    sample of the bad one. ``changepoints`` and ``segment_means`` are kept so a
    reviewer can see the whole segmentation the bracket was chosen from, not just
    its answer — a changepoint detector whose intermediate result is discarded is
    a black box, and this one sits under a safety finding.
    """

    lo: int
    hi: int
    changepoints: tuple[int, ...]
    segment_means: tuple[Fraction, ...]

    @property
    def width(self) -> int:
        """Number of samples strictly between the good and bad anchors."""
        return self.hi - self.lo - 1


def pelt(values: Sequence[Decimal], *, penalty: Fraction = DEFAULT_PENALTY) -> tuple[int, ...]:
    """Segment ``values`` with Pruned Exact Linear Time changepoint detection.

    Returns the interior changepoint indices in increasing order: index ``c``
    means a new segment starts at ``values[c]``. An empty tuple means one segment.

    The cost of a segment is its L2 (sum-of-squared-deviations-from-the-mean)
    cost, computed from :class:`~fractions.Fraction` prefix sums so the result is
    bit-identical on every machine and in every year. The pruning rule is the
    standard one for a cost satisfying ``C(s,t) + C(t,u) ≤ C(s,u)``, which L2
    does; with ``K = 0`` the pruning is exact and the returned segmentation is the
    global optimum, not an approximation.

    Raises:
        ValueError: on an empty series, or a non-positive penalty. A penalty of
            zero puts a changepoint between every pair of samples and returns a
            segmentation that means nothing.
    """
    if not values:
        raise ValueError("PELT needs at least one observation; an empty series has no segments")
    if penalty <= 0:
        raise ValueError(
            f"penalty must be positive; got {penalty}. A zero penalty places a changepoint "
            f"between every pair of samples, which is a segmentation with no content"
        )

    n = len(values)
    exact = [Fraction(value) for value in values]
    prefix = [Fraction(0)] * (n + 1)
    prefix_sq = [Fraction(0)] * (n + 1)
    for index, value in enumerate(exact):
        prefix[index + 1] = prefix[index] + value
        prefix_sq[index + 1] = prefix_sq[index] + value * value

    def cost(start: int, end: int) -> Fraction:
        length = end - start
        if length <= 0:
            return Fraction(0)
        total = prefix[end] - prefix[start]
        return prefix_sq[end] - prefix_sq[start] - (total * total) / length

    best: list[Fraction] = [Fraction(0)] * (n + 1)
    best[0] = -penalty
    previous: list[int] = [0] * (n + 1)
    candidates: list[int] = [0]

    for end in range(1, n + 1):
        scored = [(best[start] + cost(start, end) + penalty, start) for start in candidates]
        # `min` on the (value, index) pair breaks ties toward the EARLIEST start,
        # so an ambiguous segmentation resolves the same way on every run.
        chosen_cost, chosen_start = min(scored)
        best[end] = chosen_cost
        previous[end] = chosen_start
        candidates = [
            start
            for value, start in scored
            # `value` already carries + penalty; subtract it back out for the
            # standard pruning inequality F(s) + C(s,t) <= F(t).
            if value - penalty <= best[end]
        ]
        candidates.append(end)

    points: list[int] = []
    cursor = n
    while cursor > 0:
        start = previous[cursor]
        if start > 0:
            points.append(start)
        cursor = start
    return tuple(reversed(points))


def bracket_last_regression(
    values: Sequence[Decimal],
    *,
    worse: Literal["higher", "lower"],
    penalty: Fraction = DEFAULT_PENALTY,
) -> Bracket | None:
    """Bracket the most recent transition into a worse segment, or return ``None``.

    ``worse`` says which direction of the segment mean is the bad one, and it
    comes from the parameter's ratified ``safe_direction`` — never from the shape
    of the data. A detector that decided for itself which end was bad would be
    deciding a safety question from a histogram.

    Returns ``None`` when no such transition exists in the series: either there is
    one segment, or every transition went the safe way. ``None`` is not "no
    drift"; it is "this series contains no regression to bracket", and the caller
    is responsible for not reading the first as the second.
    """
    points = pelt(values, penalty=penalty)
    if not points:
        return None

    boundaries = [0, *points, len(values)]
    means: list[Fraction] = []
    for index in range(len(boundaries) - 1):
        start, end = boundaries[index], boundaries[index + 1]
        segment = [Fraction(value) for value in values[start:end]]
        means.append(sum(segment, Fraction(0)) / len(segment))

    for index in range(len(means) - 1, 0, -1):
        left, right = means[index - 1], means[index]
        regressed = right > left if worse == "higher" else right < left
        if regressed:
            boundary = boundaries[index]
            return Bracket(
                lo=boundary - 1,
                hi=boundary,
                changepoints=points,
                segment_means=tuple(means),
            )
    return None


def bisect_culprit(
    elements: Sequence[UUID],
    probe: Callable[[UUID], ProbeResult],
) -> BisectOutcome:
    """Find the first element at which the bad behaviour is present, or return a range.

    ``elements`` is the ordered candidate set inside a bracket: the first must
    probe ``GOOD`` and the last must probe ``BAD``. Both endpoints are **probed**,
    not assumed — §5.8 says monotonicity does not hold globally, so the one place
    it is relied on is the one place it is checked.

    A ``SKIP`` at the midpoint is walked outward, alternating right then left,
    exactly as ``git bisect skip`` does. If every element strictly between the two
    anchors skips, the search terminates against an unobservable region and the
    answer is the pair ``(lo, hi)`` with no culprit.

    Returns:
        A :class:`~mainline_fixity.types.BisectOutcome` that is either a culprit
        or a range, never both.

    Raises:
        BisectBracketEmpty: fewer than two candidate elements.
        ValueError: an endpoint contradicted the bracket — the first element
            probed ``BAD`` or the last probed ``GOOD``. Answering anyway would be
            a binary search over an unsorted predicate.
    """
    if len(elements) < _MIN_BRACKET:
        first = str(elements[0]) if elements else "<none>"
        raise BisectBracketEmpty(first, first)

    probes = 0
    skipped = 0

    lo_element, hi_element = elements[0], elements[-1]
    lo_result = probe(lo_element)
    hi_result = probe(hi_element)
    probes += 2
    if lo_result is not ProbeResult.GOOD or hi_result is not ProbeResult.BAD:
        raise ValueError(
            f"bisect endpoints contradict the bracket: first element probed "
            f"{lo_result.value!r} (expected 'good') and last probed {hi_result.value!r} "
            f"(expected 'bad'). Monotonicity does not hold globally over a plant's "
            f"history, so a search whose endpoints disagree with its bracket would be a "
            f"binary search over an unsorted predicate"
        )

    lo, hi = 0, len(elements) - 1
    while hi - lo > 1:
        index, result, attempts = _first_answerable(elements, lo, hi, probe)
        probes += attempts
        if index is None or result is None:
            # Every candidate strictly inside (lo, hi) skipped. The honest answer is
            # the interval, and `attempts` is still counted: a bisect that reported
            # two probes for a search that made nine would be a bisect whose cost
            # nobody could audit.
            #
            # Both halves are tested even though `_first_answerable` returns them as
            # a pair, because the type checker cannot see that they are correlated
            # and a `cast` here would be an assertion about a helper rather than a
            # check of it.
            skipped += attempts
            return BisectOutcome(
                culprit=None,
                lo=elements[lo],
                hi=elements[hi],
                probes=probes,
                skipped=skipped,
            )
        skipped += attempts - 1
        if result is ProbeResult.BAD:
            hi = index
        else:
            lo = index

    return BisectOutcome(
        culprit=elements[hi],
        lo=None,
        hi=None,
        probes=probes,
        skipped=skipped,
    )


def _first_answerable(
    elements: Sequence[UUID],
    lo: int,
    hi: int,
    probe: Callable[[UUID], ProbeResult],
) -> tuple[int | None, ProbeResult | None, int]:
    """Probe from the midpoint outward until something answers, or nothing does.

    Returns ``(index, result, attempts)``, with ``index`` and ``result`` ``None``
    when every candidate strictly between ``lo`` and ``hi`` skipped. ``attempts``
    is returned in **both** cases, so the caller's probe and skip counters stay
    honest even on the path that gives up: a bisect that reported two probes for a
    search that made nine is a bisect whose cost nobody can audit.
    """
    midpoint = (lo + hi) // 2
    attempts = 0
    for offset in _outward(midpoint, lo, hi):
        attempts += 1
        result = probe(elements[offset])
        if result is not ProbeResult.SKIP:
            return offset, result, attempts
    return None, None, attempts


def _outward(midpoint: int, lo: int, hi: int) -> list[int]:
    """Return the indices strictly inside ``(lo, hi)``, ordered outward from ``midpoint``.

    Right before left at equal distance, which is arbitrary but **fixed**: an
    order that depended on anything else would make the probe sequence — and
    therefore the cost, and in a skip-heavy region the answer — depend on
    something the record does not contain.
    """
    order: list[int] = []
    if lo < midpoint < hi:
        order.append(midpoint)
    for step in range(1, hi - lo):
        right, left = midpoint + step, midpoint - step
        if lo < right < hi:
            order.append(right)
        if lo < left < hi:
            order.append(left)
    return order
