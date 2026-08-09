# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
"""The boundary disclosure: exactly two leaves, and no third.

Disclosing ``(candidate_root, theta, s, n)`` plus inclusion paths for the leaves at ordinals
``s`` and ``s+1`` establishes that the cut is where the receipt says it is — leaf ``s`` scored
at or above ``theta`` and leaf ``s+1`` scored below it — while revealing nothing about the
suppressed set beyond the one leaf immediately past the line.

The reason this is a *proof* and not a claim is that an RFC 6962 audit path is bound to its
index. A path issued for ordinal ``s+1`` does not verify for ordinal ``s+2``, so the receipt
cannot be quietly re-pointed at a more convenient neighbour, and a receipt cannot disclose one
leaf while implying a different one sits at the boundary.

``s+2`` is therefore the load-bearing negative case, and it is asserted three ways:

1. the receipt does not disclose it at all;
2. the ``s+1`` path does not verify the ``s+2`` leaf, nor the ``s+1`` leaf at index ``s+2``;
3. a receipt forged to present the ``s+2`` leaf as the boundary pair is refused by the
   verifier, naming the check that caught it.

Point 3 needs point 2 to be about the *binding* rather than about ``s+2`` being unprovable,
so the correct ``s+2`` path is also constructed and shown to verify. Otherwise the failure
could be nothing more interesting than a truncated tree.
"""

from __future__ import annotations

from dataclasses import replace

from _run_corpus import EXPECTED_COUNTS

from trappoint_recall.per.leaf import CandidateScore, leaf_hash, leaves_from_candidates
from trappoint_recall.per.merkle import audit_path, merkle_root, verify_audit_path
from trappoint_recall.per.receipt import BoundaryLeaf, BoundaryProof
from trappoint_recall.per.verify import verify_receipt


def committed_leaves(outcome):
    """Rebuild the committed leaf sequence from the disclosed candidate rows."""
    return leaves_from_candidates(
        [
            CandidateScore(
                event_id=str(row.event_id),
                p_relevant=row.p_relevant,
                tau_applied=row.tau_applied,
                outcome=row.outcome,
            )
            for row in outcome.candidates
        ]
    )


def test_the_committed_sequence_reproduces_the_receipt_root(clean_outcome) -> None:
    """Green half: the tree the tests below reason about is the one the run committed."""
    leaves = committed_leaves(clean_outcome)
    hashes = [leaf_hash(leaf) for leaf in leaves]
    assert merkle_root(hashes) == clean_outcome.receipt.candidate_root
    assert len(leaves) == clean_outcome.receipt.n == EXPECTED_COUNTS["n_candidates"]


def test_the_cut_is_a_real_cut(clean_outcome) -> None:
    """Leaf ``s`` is at or above ``theta``; leaf ``s+1`` is below it."""
    receipt = clean_outcome.receipt
    leaves = committed_leaves(clean_outcome)
    assert 0 < receipt.s < receipt.n, "this corpus must have leaves on both sides of the cut"
    assert leaves[receipt.s - 1].score_q >= receipt.theta_q
    assert leaves[receipt.s].score_q < receipt.theta_q


def test_the_boundary_verifies_at_s_and_at_s_plus_one(clean_outcome) -> None:
    """Both halves of the disclosed pair reproduce the committed root."""
    receipt = clean_outcome.receipt
    leaves = committed_leaves(clean_outcome)
    hashes = [leaf_hash(leaf) for leaf in leaves]

    at_s = receipt.boundary.at_s
    at_next = receipt.boundary.at_s_plus_1
    assert at_s is not None
    assert at_next is not None

    assert at_s.index == receipt.s - 1
    assert at_next.index == receipt.s
    assert at_s.path == audit_path(at_s.index, hashes)
    assert at_next.path == audit_path(at_next.index, hashes)

    assert verify_audit_path(
        leaf_hash(at_s.leaf), at_s.index, receipt.n, at_s.path, receipt.candidate_root
    )
    assert verify_audit_path(
        leaf_hash(at_next.leaf), at_next.index, receipt.n, at_next.path, receipt.candidate_root
    )


def test_the_boundary_does_not_verify_at_s_plus_two(clean_outcome) -> None:
    """The audit path is index-bound, which is the whole force of the disclosure."""
    receipt = clean_outcome.receipt
    leaves = committed_leaves(clean_outcome)
    hashes = [leaf_hash(leaf) for leaf in leaves]

    index_s_plus_1 = receipt.s
    index_s_plus_2 = receipt.s + 1
    assert index_s_plus_2 < receipt.n, "the corpus must extend past s+2 for this to assert"

    path_s_plus_1 = audit_path(index_s_plus_1, hashes)

    # The s+1 path, applied to the s+2 leaf.
    assert not verify_audit_path(
        leaf_hash(leaves[index_s_plus_2]),
        index_s_plus_2,
        receipt.n,
        path_s_plus_1,
        receipt.candidate_root,
    )
    # The s+1 leaf, presented at the s+2 position.
    assert not verify_audit_path(
        leaf_hash(leaves[index_s_plus_1]),
        index_s_plus_2,
        receipt.n,
        path_s_plus_1,
        receipt.candidate_root,
    )
    # And the failure is about the binding, not about s+2 being unprovable: its own path
    # verifies perfectly well. It is simply not in the receipt.
    assert verify_audit_path(
        leaf_hash(leaves[index_s_plus_2]),
        index_s_plus_2,
        receipt.n,
        audit_path(index_s_plus_2, hashes),
        receipt.candidate_root,
    )


def test_the_receipt_discloses_the_pair_and_nothing_further(clean_outcome) -> None:
    """Two leaves, named, and no third — the suppressed set stays suppressed."""
    document = clean_outcome.receipt.to_json()["boundary_proof"]
    assert set(document) == {"leaf_at_s", "leaf_at_s_plus_1"}
    disclosed = {
        document["leaf_at_s"]["leaf"]["ord"],
        document["leaf_at_s_plus_1"]["leaf"]["ord"],
    }
    assert disclosed == {clean_outcome.receipt.s, clean_outcome.receipt.s + 1}


def test_a_receipt_forged_to_present_s_plus_two_is_refused(clean_outcome) -> None:
    """Swapping the boundary for a more convenient neighbour is caught, and named."""
    receipt = clean_outcome.receipt
    leaves = committed_leaves(clean_outcome)
    hashes = [leaf_hash(leaf) for leaf in leaves]
    index_s_plus_2 = receipt.s + 1

    forged = replace(
        receipt,
        boundary=BoundaryProof(
            at_s=receipt.boundary.at_s,
            at_s_plus_1=BoundaryLeaf(
                leaf=leaves[index_s_plus_2],
                index=index_s_plus_2,
                path=audit_path(index_s_plus_2, hashes),
            ),
        ),
    )

    report = verify_receipt(forged.to_json())
    assert not report.ok
    names = {check.name for check in report.failures}
    assert "boundary_position[s+1]" in names, report.to_text()


def test_a_forged_pair_is_still_refused_against_the_disclosed_set(clean_outcome) -> None:
    """Full mode adds the check that the disclosed pair is the pair in the set."""
    receipt = clean_outcome.receipt
    leaves = committed_leaves(clean_outcome)
    hashes = [leaf_hash(leaf) for leaf in leaves]
    index_s_plus_2 = receipt.s + 1

    forged = replace(
        receipt,
        boundary=BoundaryProof(
            at_s=receipt.boundary.at_s,
            at_s_plus_1=BoundaryLeaf(
                leaf=leaves[index_s_plus_2],
                index=index_s_plus_2,
                path=audit_path(index_s_plus_2, hashes),
            ),
        ),
    )
    rows = [
        {
            "event_id": str(row.event_id),
            "p_relevant": row.p_relevant,
            "tau_applied": row.tau_applied,
            "outcome": row.outcome,
        }
        for row in clean_outcome.candidates
    ]
    report = verify_receipt(forged.to_json(), rows)
    assert not report.ok
    names = {check.name for check in report.failures}
    assert "boundary_matches_set" in names, report.to_text()
