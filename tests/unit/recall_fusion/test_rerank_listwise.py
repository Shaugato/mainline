# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""The listwise judge, replayed: citations for every admitted candidate, and a degraded path.

What these assertions are worth, stated plainly. The cassettes are **handwritten** — no AWS
credentials exist on this build machine, so no live Claude response was ever recorded. Every
claim below is therefore a claim about *our client*: that a refusal returns a degraded record
rather than an empty candidate list, that the repair path fires exactly once, that a
``relevant`` verdict with no citable mechanism is demoted, that the cache field is surfaced,
and that the system prefix bytes do not move between calls. Nothing here claims anything
about how the model behaves; the live claim belongs to the day-1 check against the resolved
``au.*`` inference profile.

The prefix-stability and cache-surfacing assertions are still the load-bearing ones, because
an un-asserted cache is usually a broken cache, and a prefix that drifts by one byte is a
cache that never hits and a bill that nobody can explain.
"""

from __future__ import annotations

import pytest
from mainline_recall_agent.providers.cassette import CassetteJudgeTransport, CassetteStore
from mainline_recall_agent.providers.errors import ProviderError
from mainline_recall_agent.providers.judge import BedrockClaudeJudge
from mainline_recall_agent.providers.registry import cassette_resolved_model
from mainline_recall_agent.providers.system_blocks import build_user_turn
from mainline_recall_agent.rerank.evidence import EvidenceRefused, evidence_summary
from mainline_recall_agent.rerank.listwise import ListwiseReranker
from mainline_recall_agent.rerank.payload import build_payload, take_top_k
from mainline_recall_agent.rerank.rubric import PROMPT_VERSION, build_rerank_prefix
from mainline_recall_agent.rerank.schema import (
    CandidateVerdict,
    DegradedRerank,
    ListwiseVerdict,
    RerankOutcome,
    enforce_citation_rule,
)
from rerank_fixture import CANDIDATES, EXPOSURE_B, exposure_for


class _StubJudge:
    """A judge with no transport at all, for the bookkeeping paths a cassette cannot reach.

    It is deliberately *not* a mock of the model: it returns a fixed, schema-valid answer so
    that the assertions around it are about the reranker's accounting — which candidates were
    shown, which were not, what reached the ledger — and never about what a model said.
    """

    def __init__(self, refs: tuple[str, ...]) -> None:
        self._refs = refs
        self.calls = 0

    @property
    def resolved_model(self) -> object:
        return cassette_resolved_model()

    @property
    def last_usage(self) -> None:
        return None

    def judge(
        self, _system_blocks: object, _user_payload: dict[str, object], _schema: type
    ) -> ListwiseVerdict:
        self.calls += 1
        return ListwiseVerdict(
            verdicts=[
                CandidateVerdict(
                    candidate_ref=ref,
                    relevance="not_relevant",
                    shared_mechanism="loss of containment of a corrosive liquid",
                    shared_precondition="insufficient_evidence",
                    justification="Stub verdict for an accounting test.",
                    evidence_strength="weak",
                )
                for ref in self._refs
            ]
        )


#: Pinned on the day the rubric was frozen. If this moves, every committed cassette misses,
#: the cache is cold for every request in the fleet, and the change had better be deliberate.
PINNED_PREFIX_DIGEST = "35ead25f1549a29b27649952f5d1efbdf97d12fbab59b9106f4502a1d3a6f65b"


def _reranker(store: CassetteStore) -> tuple[ListwiseReranker, BedrockClaudeJudge]:
    judge = BedrockClaudeJudge(
        resolved_model=cassette_resolved_model(),
        transport=CassetteJudgeTransport(store),
        prompt_version=PROMPT_VERSION,
    )
    return ListwiseReranker(judge=judge), judge


def _replay(store: CassetteStore, scenario: str) -> RerankOutcome | DegradedRerank:
    reranker, _ = _reranker(store)
    return reranker.rerank(exposure_for(scenario), CANDIDATES)


# --------------------------------------------------------------------------------------
# The frozen prefix
# --------------------------------------------------------------------------------------


@pytest.mark.frozen
def test_the_system_prefix_digest_is_pinned() -> None:
    assert build_rerank_prefix().prefix_digest() == PINNED_PREFIX_DIGEST


def test_the_cache_breakpoint_sits_on_the_last_system_block_only() -> None:
    wire = build_rerank_prefix().wire()
    assert [block.get("cache_control") for block in wire[:-1]] == [None, None]
    assert wire[-1]["cache_control"] == {"type": "ephemeral"}


def test_the_prefix_is_large_enough_to_be_worth_caching() -> None:
    assert build_rerank_prefix().likely_cacheable


def test_two_different_permits_send_byte_identical_system_arrays(
    cassette_store: CassetteStore,
) -> None:
    """The real cache-correctness property, and it needs no vendor to verify."""
    reranker, judge = _reranker(cassette_store)
    first, _ = build_payload(exposure_for("cache_call_one"), CANDIDATES)
    second, _ = build_payload(exposure_for("cache_call_two"), CANDIDATES)
    request_one = judge.build_request(
        system=reranker.prefix,
        messages=[build_user_turn(first)],
        schema=ListwiseVerdict,
    )
    request_two = judge.build_request(
        system=reranker.prefix,
        messages=[build_user_turn(second)],
        schema=ListwiseVerdict,
    )
    assert request_one["system"] == request_two["system"]
    assert request_one["messages"] != request_two["messages"]


# --------------------------------------------------------------------------------------
# The completion test: citations, and a warm cache on the second call
# --------------------------------------------------------------------------------------


def test_every_admitted_candidate_names_a_mechanism_and_a_precondition(
    cassette_store: CassetteStore,
) -> None:
    outcome = _replay(cassette_store, "cache_call_one")
    assert isinstance(outcome, RerankOutcome)
    assert outcome.relevant, "the fixture must admit at least one candidate"
    for admitted in outcome.relevant:
        assert admitted.cites_mechanism_and_precondition
        assert admitted.shared_mechanism.strip()
        assert admitted.shared_precondition.strip()
        assert admitted.justification.strip()
        summary = evidence_summary(admitted)
        assert summary.startswith("Shared mechanism:")
        assert "Shared precondition:" in summary


def test_the_second_call_reads_the_prefix_from_the_cache(
    cassette_store: CassetteStore,
) -> None:
    reranker, judge = _reranker(cassette_store)

    first = reranker.rerank(exposure_for("cache_call_one"), CANDIDATES)
    assert isinstance(first, RerankOutcome)
    assert first.usage["cache_creation_input_tokens"] > 0
    assert first.usage["cache_read_input_tokens"] == 0

    second = reranker.rerank(exposure_for("cache_call_two"), CANDIDATES)
    assert isinstance(second, RerankOutcome)
    assert second.usage["cache_read_input_tokens"] > 0
    assert judge.call_count == 2
    assert first.prefix_digest == second.prefix_digest


def test_the_two_cache_scenarios_really_are_two_different_requests(
    cassette_store: CassetteStore,
) -> None:
    """Otherwise the cache assertion would be one cassette replayed twice."""
    first = _replay(cassette_store, "cache_call_one")
    second = _replay(cassette_store, "cache_call_two")
    assert isinstance(first, RerankOutcome) and isinstance(second, RerankOutcome)
    assert first.request_digest != second.request_digest


# --------------------------------------------------------------------------------------
# The degraded path: a precursor the model declined to rank still blocks the merge
# --------------------------------------------------------------------------------------


def test_a_refusal_returns_a_degraded_record_rather_than_an_empty_candidate_list(
    cassette_store: CassetteStore,
) -> None:
    outcome = _replay(cassette_store, "refusal")
    assert isinstance(outcome, DegradedRerank)
    assert outcome.silence_reason == "model_refusal"
    assert outcome.arms_degraded is True
    assert set(outcome.doc_ids) == {c.doc_id for c in CANDIDATES}
    records = outcome.silence_records()
    assert len(records) == len(CANDIDATES)
    assert all(record["reason"] == "model_refusal" for record in records)
    assert all("still blocks" in record["arithmetic"]["consequence"] for record in records)


def test_two_schema_failures_dead_letter_after_exactly_two_calls(
    cassette_store: CassetteStore,
) -> None:
    reranker, judge = _reranker(cassette_store)
    outcome = reranker.rerank(exposure_for("dead_letter"), CANDIDATES)
    assert isinstance(outcome, DegradedRerank)
    assert outcome.silence_reason == "abstained"
    assert judge.call_count == 2, "one call, one repair, never a third"


def test_one_repair_attempt_recovers_without_degrading_the_run(
    cassette_store: CassetteStore,
) -> None:
    reranker, judge = _reranker(cassette_store)
    outcome = reranker.rerank(exposure_for("repair"), CANDIDATES)
    assert isinstance(outcome, RerankOutcome)
    assert outcome.attempts == 2
    assert judge.call_count == 2
    assert outcome.arms_degraded is False


def test_a_defect_in_our_own_code_crashes_rather_than_becoming_silence(
    cassette_store: CassetteStore,
) -> None:
    """``ProviderError`` with no ``silence_reason`` is a bug, and a bug must not look like
    the model declining."""
    reranker, _ = _reranker(cassette_store)
    with pytest.raises(ProviderError):
        # No cassette exists for this exposure: a CassetteMiss is a misconfiguration of the
        # fixture set, not a fact about the corpus.
        reranker.rerank(exposure_for("cache_call_one"), CANDIDATES[:1])


# --------------------------------------------------------------------------------------
# The citation rule
# --------------------------------------------------------------------------------------


def test_a_relevant_verdict_with_no_citable_mechanism_is_demoted(
    cassette_store: CassetteStore,
) -> None:
    outcome = _replay(cassette_store, "demotion")
    assert isinstance(outcome, RerankOutcome)
    demoted = [item for item in outcome.reranked if item.demoted]
    assert len(demoted) == 1
    assert demoted[0].relevance == "not_relevant"
    assert "cite both" in demoted[0].demotion_reason
    assert outcome.relevant == (), "nothing may be admitted on 'seems related'"


def test_a_demoted_verdict_cannot_be_turned_into_evidence(
    cassette_store: CassetteStore,
) -> None:
    outcome = _replay(cassette_store, "demotion")
    assert isinstance(outcome, RerankOutcome)
    demoted = next(item for item in outcome.reranked if item.demoted)
    with pytest.raises(EvidenceRefused):
        evidence_summary(demoted)


def test_one_sloppy_verdict_does_not_dead_letter_the_other_thirty_nine(
    cassette_store: CassetteStore,
) -> None:
    outcome = _replay(cassette_store, "demotion")
    assert isinstance(outcome, RerankOutcome)
    assert len(outcome.reranked) == len(CANDIDATES)


def test_a_verdict_naming_a_candidate_we_never_sent_is_dropped_and_reported() -> None:
    verdicts = [
        CandidateVerdict(
            candidate_ref="C99",
            relevance="relevant",
            shared_mechanism="liberation of a toxic gas in a shared line",
            shared_precondition="no positive isolation while the interlock is bypassed",
            justification="Injected or hallucinated identity.",
            evidence_strength="decisive",
        )
    ]
    reranked, unknown = enforce_citation_rule(verdicts, ref_to_doc={"C01": "EVT-0001"})
    assert reranked == ()
    assert unknown == ("C99",)


# --------------------------------------------------------------------------------------
# Omission: shown to the judge, no verdict returned
# --------------------------------------------------------------------------------------


def test_a_candidate_the_judge_skipped_is_recorded_not_dropped(
    cassette_store: CassetteStore,
) -> None:
    outcome = _replay(cassette_store, "omission")
    assert isinstance(outcome, RerankOutcome)
    assert outcome.unranked_refs == ("C03",)
    assert outcome.arms_degraded is True
    abstained = [r for r in outcome.silence_records if r["reason"] == "abstained"]
    assert [record["subject_id"] for record in abstained] == ["EVT-0003"]


# --------------------------------------------------------------------------------------
# What the model is and is not shown
# --------------------------------------------------------------------------------------


def test_the_payload_never_carries_severity() -> None:
    """Severity lowers the bar downstream. A judge that could see it would apply it too,
    and the effect would be counted twice with nothing in the record saying so."""
    payload, _ = build_payload(exposure_for("cache_call_one"), CANDIDATES)
    assert "severity" not in repr(payload).lower()


def test_the_payload_never_carries_an_event_identity() -> None:
    payload, mapping = build_payload(exposure_for("cache_call_one"), CANDIDATES)
    rendered = repr(payload)
    for doc_id in mapping.values():
        assert doc_id not in rendered
    assert set(mapping) == {"C01", "C02", "C03"}


def test_candidates_are_presented_in_fused_rank_order() -> None:
    payload, mapping = build_payload(exposure_for("cache_call_one"), CANDIDATES)
    refs = [entry["candidate_ref"] for entry in payload["candidates"]]
    assert refs == ["C01", "C02", "C03"]
    assert mapping["C01"] == "EVT-0001"


def test_the_rerank_depth_returns_its_overflow_rather_than_forgetting_it() -> None:
    kept, overflow = take_top_k(CANDIDATES, 2)
    assert len(kept) == 2 and len(overflow) == 1
    assert overflow[0].doc_id == "EVT-0003"


def test_the_overflow_reaches_the_ledger_as_cap_exceeded() -> None:
    reranker = ListwiseReranker(judge=_StubJudge(("C01", "C02")), top_k=2)
    outcome = reranker.rerank(exposure_for("cache_call_one"), CANDIDATES)
    assert isinstance(outcome, RerankOutcome)
    overflow = [r for r in outcome.silence_records if r["reason"] == "cap_exceeded"]
    assert [record["subject_id"] for record in overflow] == ["EVT-0003"]
    assert overflow[0]["arithmetic"]["rerank_depth"] == 2
    # Overflow past the rerank depth is designed behaviour, not degradation.
    assert outcome.arms_degraded is False


def test_a_facet_outside_the_closed_vocabulary_is_refused() -> None:
    from mainline_recall_agent.rerank.payload import RerankCandidate  # noqa: PLC0415

    with pytest.raises(ProviderError, match="outside the closed vocabulary"):
        RerankCandidate(
            doc_id="X",
            fused_rank=1,
            activity_path="a/b",
            asset_class="c",
            facets={"vibes": "seems bad"},
        )


def test_an_empty_candidate_list_is_refused_rather_than_paid_for() -> None:
    with pytest.raises(ProviderError, match="empty rerank"):
        build_payload(EXPOSURE_B, [])


# --------------------------------------------------------------------------------------
# The evidence text
# --------------------------------------------------------------------------------------


def test_suppressed_siblings_are_named_in_the_evidence_rather_than_hidden_by_it(
    cassette_store: CassetteStore,
) -> None:
    outcome = _replay(cassette_store, "cache_call_one")
    assert isinstance(outcome, RerankOutcome)
    admitted = outcome.relevant[0]
    summary = evidence_summary(admitted, also_matched=("EVT-0044", "EVT-0071"))
    assert "Also matched 2 materially similar records" in summary
    assert "EVT-0044" in summary and "EVT-0071" in summary


def test_a_not_relevant_verdict_has_no_evidence_summary(
    cassette_store: CassetteStore,
) -> None:
    outcome = _replay(cassette_store, "cache_call_one")
    assert isinstance(outcome, RerankOutcome)
    rejected = next(item for item in outcome.reranked if item.relevance == "not_relevant")
    with pytest.raises(EvidenceRefused, match="did not find relevant"):
        evidence_summary(rejected)


# --------------------------------------------------------------------------------------
# Cassette hygiene
# --------------------------------------------------------------------------------------


def test_every_committed_cassette_declares_itself_handwritten(
    cassette_store: CassetteStore,
) -> None:
    """No assertion in this file may claim anything about the model from these fixtures."""
    documents = cassette_store.iter_documents("judge")
    assert documents, "the rerank cassettes are not committed"
    assert all(document["provenance"] == "handwritten" for document in documents)
