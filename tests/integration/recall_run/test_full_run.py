# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
"""A full recall run over the fixture corpus, end to end.

The claim under test is the domain's whole job in one sentence: *a permit in draft goes in,
and an integer on ``permit.open_blocking`` comes out, with every candidate accounted for and
every withheld warning ledgered.* Everything here is an assertion about that sentence.

The write is one transaction, and that is asserted rather than described. A run row without
its candidates asserts a partition nobody can inspect; a receipt without its run commits to a
population that does not exist; a ledger without its receipt is a list of withheld warnings
with no proof the list is complete — which is the only property that makes the ledger a
defence rather than a confession.
"""

from __future__ import annotations

import json
from uuid import UUID

from _run_corpus import (
    E_ANC_SEV5,
    E_BOND_SEV5,
    E_DUP,
    E_PROB_HI,
    E_PROB_SWEEP,
    EXPECTED_COUNTS,
    EXPECTED_OUTCOMES,
    EXPECTED_SILENCE_REASONS,
    PERMIT_ID,
    POLICY_VERSION,
)
from conftest import KERNEL_BASE_URL, Harness
from trappoint_recall.per.leaf import quantise_micro
from trappoint_recall.run.contract import BLOCKING_CAP_PROBABILISTIC, CandidateSet


def test_partition_is_exact(clean_outcome) -> None:
    """MI17 in longhand: candidates == blocking + advisory + silenced + deduped, exactly."""
    counts = clean_outcome.candidate_set.counts
    assert counts.model_dump() == EXPECTED_COUNTS
    assert counts.n_candidates == (
        counts.n_blocking + counts.n_advisory + counts.n_silenced + counts.n_deduped
    )


def test_every_candidate_lands_where_the_corpus_says(clean_outcome) -> None:
    """Each of the nine events reaches the outcome its branch of the arithmetic implies."""
    actual = {row.event_id: row.outcome for row in clean_outcome.candidates}
    assert actual == EXPECTED_OUTCOMES


def test_the_gate_gets_a_nonzero_integer(clean_outcome) -> None:
    """``open_blocking`` is what the whole domain exists to produce."""
    assert clean_outcome.open_blocking == EXPECTED_COUNTS["n_blocking"]
    assert clean_outcome.open_blocking > 0


def test_channels_a_and_b_are_uncapped_and_never_thresholded(clean_outcome) -> None:
    """Graph truth is admitted unconditionally: no tau is consulted and no cap applies."""
    deterministic = [
        row
        for row in clean_outcome.candidates
        if row.origin in {"deterministic_ancestry", "bonded"}
    ]
    assert len(deterministic) == 3
    for row in deterministic:
        assert row.outcome == "blocking", f"{row.event_id} is graph truth and must block"
        assert row.tau_applied == 0.0, "no threshold is consulted for channel A or B"


def test_a_bonded_fatality_is_always_blocking(clean_outcome) -> None:
    """MI16, checked in code before the CHECK ever sees the row."""
    outcomes = {row.event_id: row.outcome for row in clean_outcome.candidates}
    assert outcomes[E_ANC_SEV5] == "blocking"
    assert outcomes[E_BOND_SEV5] == "blocking"


def test_an_event_found_by_two_channels_is_one_candidate(clean_outcome) -> None:
    """``recall_candidate`` is keyed ``(run_id, event_id)``: a rediscovery is a union."""
    ids = [row.event_id for row in clean_outcome.candidates]
    assert len(ids) == len(set(ids))
    both = next(row for row in clean_outcome.candidates if row.event_id == E_ANC_SEV5)
    assert both.origin == "deterministic_ancestry", "channel A outranks channel B on origin"
    assert sorted(both.features["channels"]) == ["A", "B"], "both channels survive in features"


def test_the_probabilistic_cap_is_respected(clean_outcome) -> None:
    """Recall lead D2: the cap is scoped to probabilistic origins, and to those only."""
    probabilistic_blocking = sum(
        1
        for row in clean_outcome.candidates
        if row.outcome == "blocking" and row.origin == "recall_probabilistic"
    )
    assert probabilistic_blocking <= BLOCKING_CAP_PROBABILISTIC
    assert probabilistic_blocking == 2


def test_a_suppressed_sibling_is_attached_not_dropped(clean_outcome) -> None:
    """MMR dedup makes a sibling visible on its representative, never invisible."""
    duplicate = next(row for row in clean_outcome.candidates if row.event_id == E_DUP)
    assert duplicate.outcome == "deduped"
    assert duplicate.features["representative"] == str(E_PROB_HI)

    representative = next(
        candidate
        for candidate in clean_outcome.candidate_set.candidates
        if candidate.event_id == E_PROB_HI
    )
    assert E_DUP in representative.also_matched


def test_a_coarse_sweep_hit_never_blocks_below_severity_five(clean_outcome) -> None:
    """ARCHITECTURE 6.4: the 256-d sweep is insurance, not evidence enough to block on."""
    sweep = next(row for row in clean_outcome.candidates if row.event_id == E_PROB_SWEEP)
    assert sweep.outcome == "advisory"
    assert sweep.features["demotion"] == "coarse_sweep_below_severity_5"


def test_every_withheld_warning_is_ledgered(clean_outcome) -> None:
    """I13. Five silences, each carrying the arithmetic that produced it."""
    reasons = tuple(sorted(row.reason for row in clean_outcome.silence))
    assert reasons == EXPECTED_SILENCE_REASONS
    for row in clean_outcome.silence:
        assert row.arithmetic, f"{row.subject_id} was silenced with no arithmetic recorded"


def test_the_whole_record_lands_in_one_transaction(harness: Harness) -> None:
    """Five tables, one SERIALIZABLE transaction, nothing half-written."""
    harness.run()
    cluster = harness.cluster
    assert len(cluster.transactions) == 1, "the record must not be split across transactions"
    assert cluster.rolled_back == []
    assert cluster.committed_counts() == {
        "recall_run": 1,
        "recall_candidate": EXPECTED_COUNTS["n_candidates"],
        "recall_certificate": 1,
        "silence_receipt": 1,
        "silence_ledger": len(EXPECTED_SILENCE_REASONS),
    }


def test_the_run_row_carries_the_conserved_counters(harness: Harness) -> None:
    """The five integers written to ``recall_run`` are the ones the partition produced."""
    harness.run()
    row = harness.cluster.committed["recall_run"][0]
    # INSERT_RUN_SQL positional order: …, n_candidates, n_blocking, n_advisory, n_silenced,
    # n_deduped, arms_degraded, started_at, latency_ms.
    n_candidates, n_blocking, n_advisory, n_silenced, n_deduped = row[7:12]
    assert [n_candidates, n_blocking, n_advisory, n_silenced, n_deduped] == [
        EXPECTED_COUNTS["n_candidates"],
        EXPECTED_COUNTS["n_blocking"],
        EXPECTED_COUNTS["n_advisory"],
        EXPECTED_COUNTS["n_silenced"],
        EXPECTED_COUNTS["n_deduped"],
    ]
    assert n_candidates == n_blocking + n_advisory + n_silenced + n_deduped
    assert row[12] is False, "a clean run is not degraded"


def test_the_agent_never_writes_blocking_check(harness: Harness) -> None:
    """ARCHITECTURE 8.3 / finding S1, asserted over every statement the run issued."""
    harness.run()
    for sql in harness.cluster.all_sql:
        assert "blocking_check" not in sql, (
            "the recall agent holds no INSERT on blocking_check and must never issue one; "
            "it hands the kernel a candidate set and the kernel materialises obligations"
        )


def test_the_candidate_set_is_posted_to_the_kernel_once(harness: Harness) -> None:
    """One POST, to the one endpoint, carrying an idempotency key that is the run id."""
    outcome = harness.run()
    assert len(harness.transport.posts) == 1
    url, body, headers = harness.transport.posts[0]
    assert url == f"{KERNEL_BASE_URL}/v1/permits/{PERMIT_ID}/checks:materialise"
    assert headers["idempotency-key"] == str(outcome.run_id)

    posted = CandidateSet.model_validate_json(body)
    assert posted.counts == outcome.candidate_set.counts
    assert posted.policy_version == POLICY_VERSION
    assert posted.open_blocking == EXPECTED_COUNTS["n_blocking"]
    assert posted.arms_degraded is False
    assert posted.not_exhaustive is False

    assert outcome.materialise is not None
    assert outcome.materialise.open_blocking == EXPECTED_COUNTS["n_blocking"]


def test_the_posted_body_is_the_frozen_contract(harness: Harness) -> None:
    """Every blocking candidate carries the clause version its obligation will FK to."""
    outcome = harness.run()
    document = json.loads(harness.transport.posts[0][1])
    assert document["schema_version"] == 1
    for candidate in document["candidates"]:
        if candidate["outcome"] in {"blocking", "advisory"}:
            assert candidate["evidence_summary"].strip(), (
                "a candidate shown to a human carries the justification that becomes "
                "blocking_check.evidence_summary, which is NOT NULL"
            )
        UUID(candidate["clause_uuid"])
        assert len(candidate["commit_id"]) == 64


def test_the_receipt_commits_to_the_whole_candidate_set(clean_outcome) -> None:
    """``n`` is every candidate, and ``s`` is the cut at the lowest score a human was shown."""
    receipt = clean_outcome.receipt
    assert receipt.n == EXPECTED_COUNTS["n_candidates"]
    raised = [
        row
        for row in clean_outcome.candidates
        if row.outcome in {"blocking", "advisory"}
    ]
    assert receipt.theta_q == min(quantise_micro(row.p_relevant) for row in raised)
    assert receipt.s == len(raised)
    assert receipt.certificate_verdict == "partial"
    assert receipt.not_exhaustive is False


def test_coverage_is_partial_over_the_arms_that_actually_traversed(clean_outcome) -> None:
    """CUE HORIZON: ANN is approximate, so a clean run is ``partial`` and never ``complete``."""
    certificate = clean_outcome.certificate
    assert certificate.verdict == "partial"
    assert certificate.coverage_basis == "index_arms_plus_sweep"
    assert certificate.permits_exhaustion_claim is True
    assert certificate.index_fingerprint is not None
    assert len(certificate.index_fingerprint) == 32
