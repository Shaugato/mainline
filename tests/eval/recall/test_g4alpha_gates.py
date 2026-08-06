# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""The five G4-alpha release gates. **These are required to be RED.**

    uv run pytest tests/eval/recall -m g4alpha

reports **5 FAILED** against :class:`~trappoint_recall.eval.backend.NullBackend`, and
that is the correct state of the repository until a retriever exists. Not errored, not
skipped, not xfailed — failed, with a message naming the floor and the observed value.

Why the suite is built first and left red
------------------------------------------
MAINLINE's deliverable is a **refusal**. For a product whose output is "no", a test
suite that has never been red asserts nothing: an empty implementation refuses
everything, and a suite that only ever ran green cannot tell that apart from a working
gate. PL-2 makes red-before-green structural rather than aspirational, and this file is
where it is enforced for the recall domain. The gates go green one channel at a time as
``recall-ann-arms-explain``, ``recall-lexical-bm25``, ``recall-fusion-admission`` and
``recall-orchestrator-per`` land.

Three of the five carry a companion condition, because three of the five are trivially
satisfied by a system that does nothing — see the module docstring of
:mod:`trappoint_recall.eval.gates`. The companions make the gates strictly harder.
Nothing here is softened to make a number pass, and
``tests/eval/recall/test_gate_satisfiability.py`` proves the floors are reachable by a
correct retriever, so red here means "not built yet", never "impossible".
"""

from __future__ import annotations

import pytest

from trappoint_recall.eval.backend import NullBackend
from trappoint_recall.eval.corpus import EvalCorpus
from trappoint_recall.eval.gates import GateResult, evaluate_g4alpha
from trappoint_recall.eval.harness import MetricBundle, compute_metrics, run_evaluation_sync

pytestmark = pytest.mark.g4alpha


@pytest.fixture(scope="module")
def bundle(corpus: EvalCorpus) -> MetricBundle:
    """Run the current retrieval implementation over the corpus.

    The default is :class:`NullBackend`: a complete, honest backend that returns
    nothing. Swap it for a real one by pointing the lane at a backend; the assertions
    below do not change and must not.
    """
    run = run_evaluation_sync(NullBackend(), corpus, k=10)
    return compute_metrics(run, corpus)


@pytest.fixture(scope="module")
def gates(bundle: MetricBundle) -> dict[str, GateResult]:
    return {result.gate_id: result for result in evaluate_g4alpha(bundle)}


def test_retro_recall_at_3_on_severity_5(gates: dict[str, GateResult]) -> None:
    """Retro-Recall@3 on severity-5 precursors >= 0.90, Wilson lower bound >= 0.80.

    The money metric, and the only one that measures what the product claims: for a
    fatality at time t, would the permit that preceded it have surfaced the precursor?
    A miss here is a fatality exhibit.
    """
    result = gates["retro_recall_at_3_sev5"]
    assert result.passed, result.render()


def test_precision_at_block(gates: dict[str, GateResult]) -> None:
    """P@block >= 0.75 on the blinded adjudicated subset.

    Precision of *probabilistic* blocking checks only; channels A and B block on graph
    truth and are not in the precision question. A false positive is a rubber stamp,
    and operators probability-match: response rate tracks the perceived true-alarm rate.
    """
    result = gates["p_at_block"]
    assert result.passed, result.render()


def test_nuisance_rate(gates: dict[str, GateResult]) -> None:
    """Nuisance rate < 3% on the routine-permit replay, at non-zero sensitivity.

    EEMUA 191 / ISA-18.2 translated to a permit budget. A rule that breaches this
    ceiling is rejected rather than tuned. The sensitivity witness is part of the gate
    because a system that never blocks has a nuisance rate of zero and a recall of zero.
    """
    result = gates["nuisance_rate"]
    assert result.passed, result.render()


def test_mean_blocking_checks_per_permit(gates: dict[str, GateResult]) -> None:
    """Mean blocking checks per permit <= 1.0, hard cap 3, with MI16 holding.

    ~250 permits/week at ~4 minutes of supervisor attention per disposition is ~4 noise
    hours/week at a mean of 1.0. MI16 (`bonded_fatalities_all_blocking`) is required
    alongside, checked against corpus truth rather than the backend's own counters,
    because a silent system also has a mean of zero.
    """
    result = gates["mean_blocking_checks_per_permit"]
    assert result.passed, result.render()


def test_silence_conservation_law(gates: dict[str, GateResult]) -> None:
    """L3: candidates = blocking + advisory + silenced + deduped, exactly.

    Exact integer arithmetic, over every run in the corpus, comparing the declared run
    counters against independently enumerated candidates — and over a non-empty
    universe, because 0 = 0 + 0 + 0 + 0 is true and asserts nothing. This is the
    offline twin of the `candidates_conserved` CHECK constraint (MI17).
    """
    result = gates["conservation_l3"]
    assert result.passed, result.render()
