# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
"""Degraded mode is the spine, and it must never regress.

> Channels A and B bypass the model entirely. A degraded run — Bedrock throttled, model
> refusal, guardrail block — completes on A+B only, records ``arms_degraded = true``, and
> **still blocks the merge**. *The gate refuses on graph truth alone.*

Three failures, injected independently, because a degradation ladder that is only reasoned
about is a degradation ladder that has never run:

===========================  =========================================================
Injection                    What it stands for
===========================  =========================================================
``FailingArmRunner``         Bedrock ``ThrottlingException`` on the cue embedding, an
                             embedder outage, or the arms failing to reach the cluster
``RefusingReranker``         ``stop_reason: "refusal"`` — plausible on a corpus of
                             cyanide leaching, H₂S and confined-space chemistry
``GuardrailBlockedReranker`` Bedrock Guardrails ``PROMPT_ATTACK`` blocking the listwise
                             call outright
===========================  =========================================================

Each must satisfy the same four things: the run completes, ``arms_degraded`` is recorded,
the silence rows are written in the same transaction, and ``open_blocking > 0``.

There is a green half to each pair as well. The last test removes the injection and asserts
the same harness produces an **un**-degraded run with more blocking checks, so "it still
blocks" is a statement about the degradation and not about a corpus that would have blocked
whatever happened.
"""

from __future__ import annotations

from collections.abc import Callable

import pytest
from _run_corpus import EXPECTED_COUNTS
from _run_fakes import (
    FailingArmRunner,
    GuardrailBlockedReranker,
    RefusingReranker,
)

from trappoint_recall.run.contract import CandidateSet

#: Each injection is a keyword the harness builder understands, so the three cases differ in
#: exactly one collaborator and in nothing else.
INJECTIONS: dict[str, dict[str, object]] = {
    "bedrock_throttled": {"arm_runner": FailingArmRunner()},
    "model_refusal": {"reranker": RefusingReranker()},
    "guardrail_block": {"reranker": GuardrailBlockedReranker()},
}


@pytest.fixture(params=sorted(INJECTIONS), ids=sorted(INJECTIONS))
def degraded(request, build_harness: Callable[..., object]):
    """One harness per injection, and the run it produced."""
    harness = build_harness(**INJECTIONS[request.param])
    return request.param, harness, harness.run()


def test_a_degraded_run_still_blocks_the_merge(degraded) -> None:
    """The one property the whole degradation ladder exists to preserve."""
    name, _harness, outcome = degraded
    assert outcome.open_blocking > 0, (
        f"{name}: a permit whose recall degraded must still carry obligations — the gate "
        "refuses on graph truth alone"
    )
    assert outcome.candidate_set.counts.n_blocking == outcome.open_blocking


def test_a_degraded_run_records_that_it_degraded(degraded) -> None:
    """``arms_degraded`` is on the run row and on the wire, not only in a log line."""
    name, harness, outcome = degraded
    assert outcome.arms_degraded is True, name
    assert outcome.candidate_set.arms_degraded is True

    run_row = harness.cluster.committed["recall_run"][0]
    assert run_row[12] is True, "recall_run.arms_degraded must be set in the stored row"


def test_a_degraded_run_completes_on_graph_truth(degraded) -> None:
    """Every surviving blocking check comes from channel A or channel B."""
    name, _harness, outcome = degraded
    blocking = [row for row in outcome.candidates if row.outcome == "blocking"]
    assert blocking, name
    for row in blocking:
        assert row.origin in {"deterministic_ancestry", "bonded"}, (
            f"{name}: {row.event_id} blocked on a probabilistic origin in a degraded run"
        )
        assert row.tau_applied == 0.0


def test_a_degraded_run_writes_its_silence_rows_in_the_same_transaction(degraded) -> None:
    """A degraded run is still a complete measurement record, or it is not a record."""
    name, harness, outcome = degraded
    assert len(harness.cluster.transactions) == 1, name
    assert harness.cluster.rolled_back == []

    counts = harness.cluster.committed_counts()
    assert counts["recall_run"] == 1
    assert counts["recall_certificate"] == 1
    assert counts["silence_receipt"] == 1
    assert counts["silence_ledger"] == len(outcome.silence)
    assert counts["silence_ledger"] > 0, (
        f"{name}: the reason the probabilistic channels produced nothing must be ledgered"
    )
    assert counts["recall_candidate"] == outcome.candidate_set.counts.n_candidates


def test_a_degraded_run_names_the_failure_in_the_ledger(degraded) -> None:
    """*Why* the warning was withheld is the ledger's whole evidentiary value."""
    name, _harness, outcome = degraded
    reasons = {row.reason for row in outcome.silence}
    assert reasons & {"unreachable", "model_refusal"}, f"{name}: {sorted(reasons)}"
    for row in outcome.silence:
        assert row.arithmetic, f"{name}: a silence row with no arithmetic is a list, not a ledger"


def test_a_degraded_run_still_posts_a_valid_candidate_set(degraded) -> None:
    """The kernel is handed a well-formed set; degradation is declared, not hidden."""
    name, harness, outcome = degraded
    assert len(harness.transport.posts) == 1, name
    posted = CandidateSet.model_validate_json(harness.transport.posts[0][1])
    assert posted.arms_degraded is True
    assert posted.not_exhaustive is True, (
        "a run that could not certify its coverage must not present itself as exhausted"
    )
    assert posted.counts == outcome.candidate_set.counts
    assert posted.open_blocking > 0


def test_a_degraded_run_conserves_its_partition(degraded) -> None:
    """MI17 does not get a holiday because a model was unavailable."""
    _name, _harness, outcome = degraded
    counts = outcome.candidate_set.counts
    assert counts.n_candidates == (
        counts.n_blocking + counts.n_advisory + counts.n_silenced + counts.n_deduped
    )


def test_the_bonded_fatalities_survive_every_injection(degraded) -> None:
    """MI16 is structural. A fatality never decays, least of all because Bedrock was busy."""
    name, _harness, outcome = degraded
    bonded = [
        candidate for candidate in outcome.candidate_set.candidates if candidate.bonded_severity_5
    ]
    assert len(bonded) == 2, name
    assert all(candidate.outcome == "blocking" for candidate in bonded)


def test_a_candidate_the_judge_never_spoke_about_is_raised_and_labelled(
    build_harness,
) -> None:
    """A guardrail block must not abort the run — and must not fake a judge's citation.

    This is the case that would otherwise fail *closed in the wrong direction*: the wire
    contract refuses an empty ``evidence_summary``, so a run whose judge was blocked would
    raise a validation error and hand the permit no obligations at all. The candidate is
    raised instead, with a machine-derived justification that says in as many words that no
    shared mechanism is being asserted, and a ``features['evidence_source']`` marker so an
    auditor can separate the two kinds of text without reading them.
    """
    harness = build_harness(reranker=GuardrailBlockedReranker())
    outcome = harness.run()

    shown = [
        candidate
        for candidate in outcome.candidate_set.candidates
        if candidate.outcome in {"blocking", "advisory"}
    ]
    assert shown
    machine_derived = [
        candidate
        for candidate in shown
        if candidate.features.get("evidence_source") == "retrieval_only_no_judge_verdict"
    ]
    assert machine_derived, "the blocked judge left at least one candidate without a citation"
    for candidate in machine_derived:
        assert candidate.evidence_summary.strip()
        assert "NO shared mechanism" in candidate.evidence_summary
        assert "arms_degraded" in candidate.evidence_summary


def test_the_undegraded_run_blocks_strictly_more(harness) -> None:
    """The green half: without an injection the same corpus admits probabilistic blocks too.

    Without this, "it still blocks" could be true of a corpus that blocks unconditionally, and
    the three injections above would assert nothing about degradation at all.
    """
    outcome = harness.run()
    assert outcome.arms_degraded is False
    assert outcome.open_blocking == EXPECTED_COUNTS["n_blocking"] == 5
    probabilistic = [
        row
        for row in outcome.candidates
        if row.outcome == "blocking" and row.origin == "recall_probabilistic"
    ]
    assert len(probabilistic) == 2, (
        "the clean path must admit probabilistic blocking checks, or the degraded runs above "
        "are indistinguishable from it"
    )
