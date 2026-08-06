# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""Property tests for the metric arithmetic. These must be GREEN.

The G4-alpha gates are red because no retriever exists yet. The arithmetic underneath
them has no such excuse: if ``Recall@10`` could come back below ``Recall@3``, or a
Wilson bound could sit outside its own interval, the red gates would be measuring
nothing and the green ones would eventually certify a bug.

Four properties, plus a cross-check against independent implementations:

1. ``lower <= value <= upper`` for every measurement this package can construct.
2. ``Recall@k`` is monotone non-decreasing in ``k``.
3. ``nDCG@k`` lies in [0, 1].
4. The conservation law is **exact integer arithmetic** — no float ever enters it.

Property-based rather than example-based because the interesting inputs are the ones
nobody thinks to write down: n = 0, k = n, a query whose only judgements are grade 0,
a tally that conserves by coincidence.
"""

from __future__ import annotations

from collections.abc import Sequence

import pytest
from hypothesis import assume, given, settings
from hypothesis import strategies as st

from trappoint_recall.eval.backend import QueryResult, RunTally, ScoredCandidate
from trappoint_recall.eval.corpus import EvalQuery
from trappoint_recall.eval.crosscheck import crosscheck_all
from trappoint_recall.eval.measurement import (
    Measurement,
    bootstrap_mean_interval,
    normal_ppf,
    wilson_interval,
)
from trappoint_recall.eval.metrics import (
    conservation,
    mean_blocking_checks_per_permit,
    mrr,
    ndcg_at_k,
    nuisance_rate,
    recall_at_k,
)
from trappoint_recall.eval.qrels import Judgement, QrelSet

SPLIT = "TB-TEST-00000000"
DOC_POOL = [f"E-{i:03d}" for i in range(8)]

OUTCOMES = ("blocking", "advisory", "silenced", "deduped")


def _query(query_id: str) -> EvalQuery:
    return EvalQuery(
        query_id=query_id,
        kind="routine",
        text="synthetic",
        site_id="SITE-1",
        activity_path="/test/path",
        asset_class="test-asset",
    )


def _result(query_id: str, docs: Sequence[str]) -> QueryResult:
    candidates = tuple(
        ScoredCandidate(
            doc_id=doc,
            rank=rank,
            p_relevant=max(0.0, 1.0 - 0.05 * rank),
            tau_applied=0.5,
            outcome=OUTCOMES[rank % len(OUTCOMES)],
            severity=(rank % 5) + 1,
            channel="C",
            origin="recall_probabilistic",
        )
        for rank, doc in enumerate(dict.fromkeys(docs), start=1)
    )
    return QueryResult(
        query=_query(query_id),
        candidates=candidates,
        declared_tally=RunTally.enumerate_from(candidates),
        backend_name="property",
    )


ranked_docs = st.lists(st.sampled_from(DOC_POOL), min_size=0, max_size=8, unique=True)
grade_map = st.dictionaries(st.sampled_from(DOC_POOL), st.integers(0, 3), max_size=8)


@st.composite
def corpora(draw: st.DrawFn) -> tuple[list[QueryResult], QrelSet]:
    n = draw(st.integers(min_value=1, max_value=5))
    results: list[QueryResult] = []
    judgements: list[Judgement] = []
    for i in range(n):
        qid = f"Q-{i:03d}"
        results.append(_result(qid, draw(ranked_docs)))
        for doc, grade in draw(grade_map).items():
            judgements.append(
                Judgement(
                    query_id=qid,
                    doc_id=doc,
                    grade=grade,
                    gold_set="PROPERTY",
                    judged_by="authored",
                    blinded=True,
                )
            )
    assume(judgements)
    return results, QrelSet.build(judgements)


# --------------------------------------------------------------------------------------
# 1. Interval containment
# --------------------------------------------------------------------------------------


@given(n=st.integers(min_value=0, max_value=5000), frac=st.floats(0.0, 1.0))
def test_wilson_bounds_contain_the_point_estimate(n: int, frac: float) -> None:
    k = int(round(frac * n))
    lo, hi = wilson_interval(k, n)
    assert 0.0 <= lo <= hi <= 1.0
    if n > 0:
        p = k / n
        # No epsilon. The interval provably contains the point estimate, and the
        # implementation clamps rather than emitting a bound a few ulps the wrong side.
        assert lo <= p <= hi


@given(n=st.integers(min_value=0, max_value=2000), frac=st.floats(0.0, 1.0))
def test_measurement_proportion_is_self_consistent(n: int, frac: float) -> None:
    k = int(round(frac * n))
    m = Measurement.proportion("prop", k, n, split_policy_id=SPLIT)
    assert m.lower <= m.value <= m.upper
    assert m.split_policy_id == SPLIT
    if n == 0:
        assert not m.defined
        assert m.undefined_reason
        assert not m.meets_floor(0.0)
    else:
        assert m.defined
        assert m.interval_method == "wilson"


@given(values=st.lists(st.floats(0.0, 5.0, allow_nan=False), min_size=1, max_size=40))
@settings(deadline=None, max_examples=40)
def test_measurement_mean_bounds_contain_the_point_estimate(values: list[float]) -> None:
    m = Measurement.mean("mean", values, split_policy_id=SPLIT)
    assert m.lower <= m.value <= m.upper
    assert m.interval_method == "bootstrap_percentile"
    assert m.n == len(values)


@given(values=st.lists(st.floats(0.0, 1.0, allow_nan=False), min_size=2, max_size=30))
@settings(deadline=None, max_examples=30)
def test_bootstrap_interval_is_deterministic(values: list[float]) -> None:
    first = bootstrap_mean_interval(values, label="det", resamples=500)
    second = bootstrap_mean_interval(values, label="det", resamples=500)
    assert first == second


@given(p=st.floats(1e-9, 1 - 1e-9, allow_nan=False, allow_infinity=False))
def test_normal_ppf_is_monotone_and_antisymmetric(p: float) -> None:
    assume(1e-9 < p < 1 - 1e-9)
    x = normal_ppf(p)
    assert normal_ppf(min(1 - 1e-12, p + 1e-9)) >= x - 1e-9
    if abs(p - 0.5) > 1e-6:
        assert normal_ppf(1.0 - p) == pytest.approx(-x, abs=1e-6)


# --------------------------------------------------------------------------------------
# 2. Recall@k monotone in k
# --------------------------------------------------------------------------------------


@given(data=corpora())
@settings(deadline=None, max_examples=60)
def test_recall_at_k_is_monotone_non_decreasing_in_k(
    data: tuple[list[QueryResult], QrelSet],
) -> None:
    results, qrels = data
    measurements = [recall_at_k(results, qrels, k, split_policy_id=SPLIT) for k in (1, 2, 3, 5, 10)]
    defined = [m for m in measurements if m.defined]
    assume(defined)
    values = [m.value for m in measurements if m.defined]
    for earlier, later in zip(values, values[1:], strict=False):
        assert later >= earlier - 1e-12, f"recall dropped as k grew: {values}"


@given(data=corpora())
@settings(deadline=None, max_examples=60)
def test_recall_at_k_never_leaves_the_unit_interval(
    data: tuple[list[QueryResult], QrelSet],
) -> None:
    results, qrels = data
    for k in (1, 3, 10):
        m = recall_at_k(results, qrels, k, split_policy_id=SPLIT)
        assert 0.0 <= m.value <= 1.0
        assert 0.0 <= m.lower <= m.upper <= 1.0


@given(data=corpora())
@settings(deadline=None, max_examples=40)
def test_mrr_is_bounded_by_one(data: tuple[list[QueryResult], QrelSet]) -> None:
    results, qrels = data
    m = mrr(results, qrels, split_policy_id=SPLIT)
    assert 0.0 <= m.value <= 1.0
    assert m.lower <= m.value <= m.upper


# --------------------------------------------------------------------------------------
# 3. nDCG in [0, 1]
# --------------------------------------------------------------------------------------


@given(data=corpora(), k=st.sampled_from([1, 3, 5, 10]), gain=st.sampled_from(["exponential", "linear"]))
@settings(deadline=None, max_examples=60)
def test_ndcg_is_in_the_unit_interval(
    data: tuple[list[QueryResult], QrelSet], k: int, gain: str
) -> None:
    results, qrels = data
    m = ndcg_at_k(results, qrels, k, split_policy_id=SPLIT, gain=gain)
    if not m.defined:
        return
    assert 0.0 <= m.value <= 1.0 + 1e-12
    assert 0.0 <= m.lower <= m.upper <= 1.0 + 1e-12


def test_ndcg_is_one_for_a_perfectly_ordered_ranking() -> None:
    results = [_result("Q-000", ["E-000", "E-001", "E-002"])]
    qrels = QrelSet.build(
        [
            Judgement(query_id="Q-000", doc_id="E-000", grade=3, gold_set="P", judged_by="authored"),
            Judgement(query_id="Q-000", doc_id="E-001", grade=2, gold_set="P", judged_by="authored"),
            Judgement(query_id="Q-000", doc_id="E-002", grade=1, gold_set="P", judged_by="authored"),
        ]
    )
    m = ndcg_at_k(results, qrels, 3, split_policy_id=SPLIT)
    assert m.value == pytest.approx(1.0)


def test_ndcg_is_below_one_for_an_inverted_ranking() -> None:
    results = [_result("Q-000", ["E-002", "E-001", "E-000"])]
    qrels = QrelSet.build(
        [
            Judgement(query_id="Q-000", doc_id="E-000", grade=3, gold_set="P", judged_by="authored"),
            Judgement(query_id="Q-000", doc_id="E-001", grade=2, gold_set="P", judged_by="authored"),
            Judgement(query_id="Q-000", doc_id="E-002", grade=1, gold_set="P", judged_by="authored"),
        ]
    )
    m = ndcg_at_k(results, qrels, 3, split_policy_id=SPLIT)
    assert m.value < 1.0


# --------------------------------------------------------------------------------------
# 4. Conservation is exact integer arithmetic
# --------------------------------------------------------------------------------------

counts = st.integers(min_value=0, max_value=10_000)


@given(blocking=counts, advisory=counts, silenced=counts, deduped=counts)
def test_conservation_holds_exactly_when_the_partition_sums(
    blocking: int, advisory: int, silenced: int, deduped: int
) -> None:
    total = blocking + advisory + silenced + deduped
    tally = RunTally(
        n_candidates=total,
        n_blocking=blocking,
        n_advisory=advisory,
        n_silenced=silenced,
        n_deduped=deduped,
    )
    assert tally.conserved
    assert tally.partition_sum == total


@given(
    blocking=counts,
    advisory=counts,
    silenced=counts,
    deduped=counts,
    delta=st.integers(min_value=1, max_value=1000),
)
def test_conservation_fails_for_any_non_zero_discrepancy(
    blocking: int, advisory: int, silenced: int, deduped: int, delta: int
) -> None:
    total = blocking + advisory + silenced + deduped
    tally = RunTally(
        n_candidates=total + delta,
        n_blocking=blocking,
        n_advisory=advisory,
        n_silenced=silenced,
        n_deduped=deduped,
    )
    assert not tally.conserved


def test_conservation_refuses_float_counters() -> None:
    """A float in the conservation law would make it approximately true. It is not."""
    with pytest.raises(TypeError, match="exact integer arithmetic"):
        RunTally(
            n_candidates=4.0,  # type: ignore[arg-type]
            n_blocking=1,
            n_advisory=1,
            n_silenced=1,
            n_deduped=1,
        )


def test_conservation_detects_a_dropped_candidate() -> None:
    """The declared counters and the enumerated candidates are independent by design."""
    result = _result("Q-000", ["E-000", "E-001", "E-002"])
    honest = result.enumerated_tally
    lying = RunTally(
        n_candidates=honest.n_candidates - 1,
        n_blocking=honest.n_blocking,
        n_advisory=honest.n_advisory,
        n_silenced=max(0, honest.n_silenced - 1),
        n_deduped=honest.n_deduped,
    )
    tampered = QueryResult(
        query=result.query,
        candidates=result.candidates,
        declared_tally=lying,
        backend_name="tampered",
    )
    report = conservation([tampered], split_policy_id=SPLIT)
    assert not report.holds
    assert any("enumerated" in v.detail for v in report.violations)


def test_conservation_over_zero_candidates_is_flagged_vacuous() -> None:
    empty = QueryResult(
        query=_query("Q-000"),
        candidates=(),
        declared_tally=RunTally(0, 0, 0, 0, 0),
        backend_name="empty",
    )
    report = conservation([empty], split_policy_id=SPLIT)
    assert report.holds
    assert report.vacuous, "a law that closed over nothing must not read as a pass"


def test_conservation_without_declared_counters_is_a_violation() -> None:
    result = _result("Q-000", ["E-000"])
    unpublished = QueryResult(
        query=result.query, candidates=result.candidates, declared_tally=None, backend_name="quiet"
    )
    report = conservation([unpublished], split_policy_id=SPLIT)
    assert not report.holds
    assert report.covered_runs == 0


# --------------------------------------------------------------------------------------
# Noise metrics
# --------------------------------------------------------------------------------------


def test_nuisance_rate_is_undefined_without_routine_permits() -> None:
    retro = QueryResult(
        query=EvalQuery(
            query_id="Q-R",
            kind="retro",
            text="t",
            site_id="S",
            activity_path="/a",
            asset_class="x",
            severity=5,
            wall=__import__("datetime").datetime(2025, 1, 1, tzinfo=__import__("datetime").UTC),
            truth_doc_id="E-000",
        ),
        candidates=(),
        declared_tally=RunTally(0, 0, 0, 0, 0),
    )
    m = nuisance_rate([retro], split_policy_id=SPLIT)
    assert not m.defined
    assert not m.under_ceiling(0.03)


def test_mean_blocking_counts_every_permit_including_quiet_ones() -> None:
    noisy = _result("Q-000", ["E-000", "E-001", "E-002", "E-003"])
    quiet = QueryResult(query=_query("Q-001"), candidates=(), declared_tally=RunTally(0, 0, 0, 0, 0))
    m = mean_blocking_checks_per_permit([noisy, quiet], split_policy_id=SPLIT)
    expected = len(noisy.blocking) / 2
    assert m.value == pytest.approx(expected)
    assert m.n == 2


# --------------------------------------------------------------------------------------
# Cross-check against independent implementations
# --------------------------------------------------------------------------------------


def test_arithmetic_agrees_with_scipy_and_scikit_learn() -> None:
    """The hand-rolled statistics are checked against the reference implementations.

    Not skipped when the wheels are missing: scipy and scikit-learn are declared
    dependencies precisely so this check can never be quietly unavailable.
    """
    for result in crosscheck_all():
        assert result.agrees, result.render()


def test_wilson_matches_the_textbook_case() -> None:
    """A worked example a reader can verify by hand: 24 successes in 24 trials."""
    lo, hi = wilson_interval(24, 24)
    assert lo == pytest.approx(0.8620, abs=5e-4)
    assert hi == pytest.approx(1.0)
