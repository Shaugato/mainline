# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""Proof that the G4-alpha gates are a gate and not a wall. These must be GREEN.

``test_g4alpha_gates.py`` is red, and red is only meaningful if green is reachable.
Three backends are run against the same corpus and the same floors:

* :class:`OracleBackend` — a correct retriever. Must pass **all five**. If it could
  not, the floors would be unreachable and the red suite would be theatre.
* :class:`ShoutingBackend` — blocks on everything. Must pass the recall gate and fail
  the three noise gates. If it passed them, the precision half of the design would be
  decorative and the product would ship a rubber stamp.
* :class:`DroppingBackend` — an oracle whose declared counters lose one candidate per
  run. Must fail the conservation law and nothing else. Nothing else in the suite would
  notice a candidate quietly disappearing between the counters and the candidate set.

These are deliberately **not** marked ``g4alpha``: the ``-m g4alpha`` lane reports the
state of the product, and these report the state of the harness.
"""

from __future__ import annotations

import pytest

from trappoint_recall.eval.corpus import EvalCorpus
from trappoint_recall.eval.gates import GateResult, evaluate_g4alpha, overall_status
from trappoint_recall.eval.harness import compute_metrics, run_evaluation_sync

from oracles import DroppingBackend, OracleBackend, ShoutingBackend


def _gates(backend: object, corpus: EvalCorpus) -> dict[str, GateResult]:
    run = run_evaluation_sync(backend, corpus, k=10)  # type: ignore[arg-type]
    bundle = compute_metrics(run, corpus)
    return {r.gate_id: r for r in evaluate_g4alpha(bundle)}


@pytest.fixture(scope="module")
def oracle_gates(corpus: EvalCorpus) -> dict[str, GateResult]:
    return _gates(OracleBackend(), corpus)


@pytest.fixture(scope="module")
def shouting_gates(corpus: EvalCorpus) -> dict[str, GateResult]:
    return _gates(ShoutingBackend(), corpus)


@pytest.fixture(scope="module")
def dropping_gates(corpus: EvalCorpus) -> dict[str, GateResult]:
    return _gates(DroppingBackend(), corpus)


# --------------------------------------------------------------------------------------
# A correct retriever passes
# --------------------------------------------------------------------------------------


def test_a_correct_retriever_passes_every_gate(oracle_gates: dict[str, GateResult]) -> None:
    failures = [g.render() for g in oracle_gates.values() if not g.passed]
    assert not failures, (
        "the G4-alpha floors are unreachable by a correct retriever, which would make "
        "the red suite a wall rather than a gate:\n" + "\n".join(failures)
    )
    assert overall_status(list(oracle_gates.values())) == "PASS"


def test_the_recall_floor_is_reachable_with_margin(oracle_gates: dict[str, GateResult]) -> None:
    """The corpus must be large enough that perfect recall clears the Wilson lower bound.

    At n severity-5 retro permits and perfect recall the Wilson lower bound is
    ``n / (n + z**2)``, so the 0.80 floor needs n >= 16. A corpus that could not clear
    its own floor would fail every retriever forever.
    """
    m = oracle_gates["retro_recall_at_3_sev5"].measurement
    assert m is not None and m.defined
    assert m.value == pytest.approx(1.0)
    assert m.lower >= 0.80, f"corpus too small: {m.render()}"


# --------------------------------------------------------------------------------------
# Blocking on everything must not pass
# --------------------------------------------------------------------------------------


def test_blocking_on_everything_passes_recall(shouting_gates: dict[str, GateResult]) -> None:
    assert shouting_gates["retro_recall_at_3_sev5"].passed, (
        "a retriever that returns everything must trivially satisfy recall; if it does "
        "not, the recall metric is broken rather than strict"
    )


def test_blocking_on_everything_fails_precision(shouting_gates: dict[str, GateResult]) -> None:
    result = shouting_gates["p_at_block"]
    assert not result.passed, f"P@block accepted an indiscriminate blocker: {result.render()}"


def test_blocking_on_everything_fails_the_nuisance_ceiling(
    shouting_gates: dict[str, GateResult],
) -> None:
    result = shouting_gates["nuisance_rate"]
    assert not result.passed, f"the nuisance ceiling accepted a blocker: {result.render()}"
    m = result.measurement
    assert m is not None and m.defined and m.value > 0.03


def test_blocking_on_everything_breaches_the_cap(shouting_gates: dict[str, GateResult]) -> None:
    result = shouting_gates["mean_blocking_checks_per_permit"]
    assert not result.passed
    assert "cap" in result.reason or "mean" in result.reason


def test_blocking_on_everything_still_conserves(shouting_gates: dict[str, GateResult]) -> None:
    """Noise is not a conservation failure. The law measures accounting, not judgement."""
    assert shouting_gates["conservation_l3"].passed


# --------------------------------------------------------------------------------------
# A dropped candidate is caught by the law and by nothing else
# --------------------------------------------------------------------------------------


def test_a_dropped_candidate_fails_only_the_conservation_law(
    dropping_gates: dict[str, GateResult],
) -> None:
    assert not dropping_gates["conservation_l3"].passed, (
        "a backend under-reporting its candidate count passed the conservation law; the "
        "declared and enumerated counters are no longer independent"
    )
    assert "enumerated" in dropping_gates["conservation_l3"].reason
    for gate_id in (
        "retro_recall_at_3_sev5",
        "p_at_block",
        "nuisance_rate",
        "mean_blocking_checks_per_permit",
    ):
        assert dropping_gates[gate_id].passed, (
            f"{gate_id} failed on a dropped counter; only the conservation law should "
            "notice, otherwise the gates are entangled"
        )


# --------------------------------------------------------------------------------------
# The corpus itself
# --------------------------------------------------------------------------------------


def test_corpus_carries_both_arms_of_the_experiment(corpus: EvalCorpus) -> None:
    """Retro permits and the routine negative control, plus bonded fatalities."""
    assert len(corpus.retro_severity_5) >= 16, "too few severity-5 retro permits for the floor"
    assert len(corpus.by_kind("routine")) >= 30, "too few routine permits to measure nuisance"
    bonded = sum(len(q.bonded_sev5) for q in corpus.queries)
    assert bonded > 0, "without bonded fatalities MI16 holds vacuously and the mean gate is blind"


def test_corpus_declares_what_it_is(corpus: EvalCorpus) -> None:
    """A synthetic corpus must say so, on every report it produces."""
    label = corpus.label()
    assert corpus.split_policy_id in label
    if corpus.synthetic:
        assert "SYNTHETIC" in label
    if corpus.preliminary:
        assert "PRELIMINARY" in label
