# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
"""M4 CUE HORIZON — the certified null, and the exhaustion claim it is allowed to license.

The most dangerous output this system can produce is *"no precursors found"*, because to the
person reading it that is indistinguishable from *"there are none"*. So an empty or partial
retrieval result is representable **only** with a coverage certificate bound to an index
generation, and where coverage cannot be certified the verdict is ``UNDETERMINED`` and Proof
of Exhausted Recall may not claim exhaustion.

That last clause is enforced in code, not asserted in prose: :func:`build_receipt` refuses to
emit a receipt under an ``UNDETERMINED`` certificate unless the caller explicitly sets
``not_exhaustive``, and the flag then travels onto the wire and onto the exhibit. Four
independent routes to ``UNDETERMINED`` are exercised here, because each is a different thing
that really happens to a C-SPANN tree and each must reach the same refusal.

``complete`` gets its own test for the opposite reason. ANN is approximate; only an exhaustive
scan can establish that the corpus was seen, and migration 0087's
``complete_needs_a_basis_that_can_establish_it`` says so in the database. The same refusal is
made here so the overclaim never reaches the round trip.
"""

from __future__ import annotations

import pytest
from _run_corpus import INDEX_GENERATION, PLAN_DIGEST
from _run_fakes import FailingArmRunner, FixtureArmRunner, arm_outcome
from mainline_recall_agent.run.persist import NO_FINGERPRINT
from trappoint_recall.horizon.certificate import CoverageCertificate
from trappoint_recall.horizon.errors import CoverageRefused
from trappoint_recall.per.errors import ExhaustionOverclaim
from trappoint_recall.per.leaf import CandidateScore
from trappoint_recall.per.receipt import PER_BOUND_SENTENCE, build_receipt
from trappoint_recall.per.verify import verify_receipt
from trappoint_recall.run.contract import CandidateSet


def _arms(**kwargs):
    return FixtureArmRunner(
        arm_outcome(index_generation=INDEX_GENERATION, plan_digest=PLAN_DIGEST, **kwargs)
    )


UNDETERMINED_INJECTIONS = {
    "generation_moved_mid_run": {"generation_moves_to": "gen-2026-08-01T09:15:00Z"},
    "prefix_tree_uncountable": {"prefix_tree_counted": False},
    "index_not_traversed": {"index_traversed": False},
}


@pytest.mark.parametrize("injection", sorted(UNDETERMINED_INJECTIONS))
def test_uncertifiable_coverage_is_undetermined(build_harness, injection) -> None:
    """Three routes, one verdict. Each is a fact about the index, not an error in the run."""
    harness = build_harness(arm_runner=_arms(**UNDETERMINED_INJECTIONS[injection]))
    outcome = harness.run()

    assert outcome.certificate.verdict == "UNDETERMINED"
    assert outcome.certificate.permits_exhaustion_claim is False
    assert outcome.certificate.reasons, "an UNDETERMINED verdict must say what it could not see"


def test_a_degraded_run_cannot_certify_its_own_reach(build_harness) -> None:
    """The fourth route: the probabilistic channels never ran, so their reach is unknown."""
    harness = build_harness(arm_runner=FailingArmRunner())
    outcome = harness.run()

    assert outcome.arms_degraded is True
    assert outcome.certificate.verdict == "UNDETERMINED"
    assert outcome.certificate.coverage_basis == "unavailable"


@pytest.mark.parametrize("injection", sorted(UNDETERMINED_INJECTIONS))
def test_undetermined_forces_the_receipt_to_disclaim_exhaustion(
    build_harness, injection
) -> None:
    """The flag is on the receipt's face, on the wire, and in the verifier's report."""
    harness = build_harness(arm_runner=_arms(**UNDETERMINED_INJECTIONS[injection]))
    outcome = harness.run()

    assert outcome.receipt.certificate_verdict == "UNDETERMINED"
    assert outcome.receipt.not_exhaustive is True
    assert outcome.candidate_set.not_exhaustive is True
    assert outcome.candidate_set.certificate_verdict == "UNDETERMINED"

    report = verify_receipt(outcome.receipt.to_json())
    assert report.ok, report.to_text()
    bounded = next(
        check for check in report.checks if check.name == "exhaustion_claim_bounded"
    )
    assert bounded.ok
    assert PER_BOUND_SENTENCE in bounded.detail


def test_the_builder_refuses_to_claim_exhaustion_under_undetermined(clean_outcome) -> None:
    """The red half: without ``not_exhaustive`` the receipt cannot be built at all."""
    scores = [
        CandidateScore(
            event_id=str(row.event_id),
            p_relevant=row.p_relevant,
            tau_applied=row.tau_applied,
            outcome=row.outcome,
        )
        for row in clean_outcome.candidates
    ]
    kwargs = {
        "run_id": str(clean_outcome.run_id),
        "permit_id": str(clean_outcome.permit_id),
        "policy_version": clean_outcome.receipt.policy_version,
        "index_generation": clean_outcome.receipt.index_generation,
        "corpus_root": clean_outcome.receipt.corpus_root,
    }

    with pytest.raises(ExhaustionOverclaim) as raised:
        build_receipt(scores, certificate_verdict="UNDETERMINED", **kwargs)
    assert PER_BOUND_SENTENCE in str(raised.value)

    # The green half of the same pair: the identical call, honestly flagged, succeeds.
    receipt, _leaves = build_receipt(
        scores, certificate_verdict="UNDETERMINED", not_exhaustive=True, **kwargs
    )
    assert receipt.not_exhaustive is True


def test_a_receipt_that_claims_exhaustion_under_undetermined_fails_verification(
    clean_outcome,
) -> None:
    """A hand-edited receipt is caught by the verifier as well as by the builder."""
    document = clean_outcome.receipt.to_json()
    document["certificate_verdict"] = "UNDETERMINED"
    document["not_exhaustive"] = False

    report = verify_receipt(document)
    assert not report.ok
    assert "exhaustion_claim_bounded" in {check.name for check in report.failures}


def test_the_wire_contract_refuses_an_unflagged_undetermined_set(clean_outcome) -> None:
    """The same law at the payload shape: the kernel is never handed the overclaim."""
    document = clean_outcome.candidate_set.model_dump(mode="json")
    document["certificate_verdict"] = "UNDETERMINED"
    document["not_exhaustive"] = False

    with pytest.raises(ValueError, match="UNDETERMINED"):
        CandidateSet.model_validate(document)


def test_complete_needs_a_basis_that_can_establish_it() -> None:
    """ANN is approximate. Only an exhaustive scan can support the word ``complete``."""
    with pytest.raises(CoverageRefused, match="complete_needs_a_basis_that_can_establish_it"):
        CoverageCertificate(
            index_generation=INDEX_GENERATION,
            index_fingerprint=bytes(32),
            coverage_basis="index_arms_plus_sweep",
            verdict="complete",
            reasons=("every arm traversed its index",),
        )


def test_an_uncertified_certificate_row_records_the_sentinel_fingerprint(
    build_harness,
) -> None:
    """``index_fingerprint`` is NOT NULL, and an unknown fingerprint is 32 zero bytes."""
    harness = build_harness(
        arm_runner=_arms(generation_moves_to="gen-2026-08-01T09:15:00Z")
    )
    harness.run()

    row = harness.cluster.committed["recall_certificate"][0]
    # INSERT_CERTIFICATE_SQL order: run_id, index_generation, fingerprint hex, basis, verdict.
    assert row[2] == NO_FINGERPRINT.hex()
    assert row[3] == "fingerprint_mismatch"
    assert row[4] == "UNDETERMINED"


def test_a_certified_run_records_a_real_fingerprint(harness) -> None:
    """The clean path stores the digest the exhibit will later be checked against."""
    harness.run()
    row = harness.cluster.committed["recall_certificate"][0]
    assert row[2] != NO_FINGERPRINT.hex()
    assert len(row[2]) == 64
    assert row[4] == "partial"
