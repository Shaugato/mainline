# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""Band recall on a labelled near-duplicate corpus meets the S-curve at the knee.

The banding parameters carry an analytic promise —
``P(share ≥ 1 band) = 1 - (1 - J**8)**16``, knee at
``(1/16)**(1/8) = 0.70710678`` — and that promise is about *uniform shingle
sets*.  Real clause text is not uniform: 5-gram character shingles over "shall
isolate pump P-101A at ISOL-4471" are dominated by deontic boilerplate and by
tags, which is exactly the sort of structure that makes an analytic estimate
optimistic.

So the curve is **measured**, on a seeded corpus of labelled reflow mutations
whose true Jaccard is computed exhaustively, and the measurement is asserted
against the analytic prediction rather than against a remembered number.

The corpus is deterministic: the same seed produces the same 280 pairs in any
process, forever.  A calibration harness whose corpus drifts is a harness that
will one day report a knee that moved because the fixture moved.
"""

from __future__ import annotations

import pytest
from mainline_domain.identity.candidates.calibration import (
    MUTATION_CLASSES,
    LabelledPair,
    band_recall_curve,
    labelled_pairs,
)
from mainline_domain.identity.candidates.minhash import band_knee, s_curve_probability

SEED = 20260804
COUNT = 40
BANDS = 16
ROWS = 8
KNEE = band_knee(BANDS, ROWS)


@pytest.fixture(scope="module")
def corpus() -> tuple[LabelledPair, ...]:
    return labelled_pairs(seed=SEED, count=COUNT)


def _recall(pairs: tuple[LabelledPair, ...], predicate: object) -> tuple[int, float]:
    selected = [p for p in pairs if predicate(p.true_jaccard)]  # type: ignore[operator]
    if not selected:
        return 0, 0.0
    return len(selected), sum(1 for p in selected if p.shares_band) / len(selected)


@pytest.mark.slow
def test_the_corpus_spans_the_curve(corpus: tuple[LabelledPair, ...]) -> None:
    """A curve measured only above the knee is not a measurement of a knee."""
    assert len(corpus) >= 250
    assert {p.mutation for p in corpus} == set(MUTATION_CLASSES)
    below, _ = _recall(corpus, lambda j: j < 0.5)
    above, _ = _recall(corpus, lambda j: j >= 0.9)
    assert below >= 20, "no low-Jaccard pairs: the bottom of the curve is extrapolated"
    assert above >= 20, "no high-Jaccard pairs: the top of the curve is extrapolated"


@pytest.mark.slow
def test_the_auto_accept_region_is_not_missed(corpus: tuple[LabelledPair, ...]) -> None:
    """Pairs at J ≥ 0.85 are the ones S3 would auto-accept.  Banding must surface them.

    Analytic prediction at J = 0.85 is 0.9938.  A miss here is a near-duplicate
    the cascade never even looked at.
    """
    n, observed = _recall(corpus, lambda j: j >= 0.85)
    assert n >= 100
    assert observed >= 0.95, (
        f"band recall {observed:.3f} over {n} pairs at J >= 0.85; the analytic curve "
        f"predicts {s_curve_probability(0.85, BANDS, ROWS):.4f}"
    )


@pytest.mark.slow
def test_the_noise_region_does_not_flood_the_stage(corpus: tuple[LabelledPair, ...]) -> None:
    """Pairs at J ≤ 0.45 mostly must not become candidates.

    Analytic prediction at 0.45 is 0.0265.  If this fails, S3 is enumerating
    unrelated pairs and the stage's cost claim is void.
    """
    n, observed = _recall(corpus, lambda j: j <= 0.45)
    assert n >= 20
    assert observed <= 0.10, (
        f"band false-candidate rate {observed:.3f} over {n} pairs at J <= 0.45; the "
        f"analytic curve predicts {s_curve_probability(0.45, BANDS, ROWS):.4f}"
    )


@pytest.mark.slow
def test_the_transition_happens_at_the_configured_tau(corpus: tuple[LabelledPair, ...]) -> None:
    """The knee is *where the design says it is*, not merely somewhere.

    At the knee itself the analytic probability is ``1 - (1 - 1/b)**b`` = 0.6439.
    So the measurable statement is: the population above the knee is recalled
    far more often than the population below it, and both sit on the correct
    side of that value.
    """
    n_above, above = _recall(corpus, lambda j: j >= KNEE)
    n_below, below = _recall(corpus, lambda j: j < KNEE)
    at_knee = s_curve_probability(KNEE, BANDS, ROWS)

    assert n_above >= 100
    assert n_below >= 50
    assert above >= at_knee, (
        f"recall above the knee is {above:.3f}, below the analytic value at the knee "
        f"({at_knee:.4f}) — the S-curve's rising edge is not where 16x8 puts it"
    )
    assert below <= 0.30, f"recall below the knee is {below:.3f}; the curve has no shoulder"
    assert above - below > 0.5, "the transition is not sharp enough to be a knee"


@pytest.mark.slow
def test_observed_recall_is_monotone_in_jaccard(corpus: tuple[LabelledPair, ...]) -> None:
    """More alike must never mean less likely to be a candidate.

    Stated **cumulatively** — recall over ``J >= t`` as ``t`` rises — and not
    per bucket, for a reason worth writing down: per-bucket monotonicity is not
    a property of a finite sample.  A bucket holding 13 pairs has a binomial
    standard error near 0.13, so two adjacent thin buckets will invert by
    chance often enough to make the assertion flaky, and a flaky assertion
    teaches the next person to re-run rather than to look.  The cumulative
    form pools the samples, is what the S-curve actually claims, and is stable.
    """
    thresholds = (0.0, 0.3, 0.5, 0.6, 0.7, 0.8, 0.9)
    observed: list[tuple[float, int, float]] = []
    for t in thresholds:
        n, recall = _recall(corpus, lambda j, t=t: j >= t)  # type: ignore[misc]
        observed.append((t, n, recall))

    rendered = ", ".join(f"J>={t:.1f}: {r:.3f} (n={n})" for t, n, r in observed)
    values = [r for _, _, r in observed]
    assert values == sorted(values), f"cumulative band recall is not monotone: {rendered}"
    assert values[-1] >= values[0] + 0.2, f"the curve barely rises at all: {rendered}"


@pytest.mark.slow
def test_each_populated_bucket_tracks_the_analytic_curve(
    corpus: tuple[LabelledPair, ...],
) -> None:
    """Observed vs predicted, per bucket, within a stated tolerance.

    The tolerance is wide (0.30) and deliberately so: the prediction is
    evaluated at the bucket *midpoint* while the pairs are distributed across
    the bucket, and the curve is steep near the knee.  A tighter bound would be
    measuring the bucketing, not the banding.
    """
    failures: list[str] = []
    for bucket in band_recall_curve(corpus):
        if bucket.pairs < 15:
            continue
        predicted = bucket.predicted(BANDS, ROWS)
        if abs(bucket.observed - predicted) > 0.30:
            failures.append(
                f"[{bucket.lower:.1f},{bucket.upper:.1f}) n={bucket.pairs} "
                f"observed={bucket.observed:.3f} predicted={predicted:.3f}"
            )
    assert not failures, "buckets diverging from the S-curve:\n" + "\n".join(failures)


@pytest.mark.slow
def test_reflow_mutations_stay_above_the_knee(corpus: tuple[LabelledPair, ...]) -> None:
    """SURVIVE, in miniature: whitespace and punctuation must not break identity.

    These are the mutations a re-typeset document produces.  If banding loses
    them the cascade is manufacturing false positives out of formatting, which
    is the *other* failure direction and just as damaging as a missed weakening.
    """
    reflow = [p for p in corpus if p.mutation in {"whitespace", "punctuation"}]
    assert reflow
    missed = [p for p in reflow if not p.shares_band]
    assert not missed, (
        f"{len(missed)} of {len(reflow)} pure-reflow pairs shared no band; lowest true "
        f"Jaccard among them was {min(p.true_jaccard for p in missed):.3f}"
    )


@pytest.mark.slow
def test_the_corpus_is_reproducible(corpus: tuple[LabelledPair, ...]) -> None:
    """Same seed, same pairs, same band outcomes — in this process and any other."""
    again = labelled_pairs(seed=SEED, count=COUNT)
    assert again == corpus
