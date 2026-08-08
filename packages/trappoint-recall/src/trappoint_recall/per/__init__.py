# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""M3 — Proof of Exhausted Recall: the score-sorted commitment and its boundary disclosure.

The mechanism in three lines::

    leaf  = sha256(0x00 || JCS({ord, event_id, score_q, tau_applied, outcome}))
    node  = sha256(0x01 || left || right)                       # RFC 6962
    show  = (candidate_root, theta, s, n) + audit paths for ordinals s and s+1

``score_q = round_half_up(p_relevant * 10**6)`` as an **integer**, because float formatting
must never be able to break the sortedness the whole proof rests on.

What it refuses to let anyone do
--------------------------------
* **Retro-tune ``tau``.** The policy is anchored inside a cosigned checkpoint before a run may
  cite it (MI18), and the receipt names the policy version it ran under.
* **Hand-exclude a candidate.** Every leaf carries its ordinal, so a deletion renumbers every
  later leaf and changes the root — a root that was committed before the dispute existed.
* **Claim more than was searched.** :data:`~trappoint_recall.per.receipt.PER_BOUND_SENTENCE`
  is a field in the receipt, and :func:`~trappoint_recall.per.receipt.build_receipt` refuses
  to emit a receipt under an ``UNDETERMINED`` coverage certificate unless the caller
  explicitly marks it non-exhaustive.

Dependency floor
----------------
The standard library. Not ``pydantic``, not ``numpy``, not ``trappoint_jcs``. The person this
artefact is for does not trust us, so the tool they check it with cannot be ours to change.
"""

from __future__ import annotations

from trappoint_recall.per.canon import MAX_SAFE_INTEGER, canonicalise_leaf, serialise_member
from trappoint_recall.per.errors import (
    BoundaryInconsistent,
    ExhaustionOverclaim,
    InvalidLeaf,
    InvalidProof,
    NotCanonicalisable,
    PerRefused,
    RootMismatch,
    UnsortedCandidates,
)
from trappoint_recall.per.leaf import (
    LEAF_MEMBER_NAMES,
    MICRO,
    OUTCOMES,
    RAISED_OUTCOMES,
    CandidateScore,
    Leaf,
    assert_score_sorted,
    leaf_hash,
    leaf_preimage,
    leaves_from_candidates,
    quantise_micro,
    sort_candidates,
)
from trappoint_recall.per.merkle import (
    EMPTY_ROOT,
    LEAF_PREFIX,
    NODE_PREFIX,
    audit_path,
    merkle_root,
    node_hash,
    verify_audit_path,
)
from trappoint_recall.per.receipt import (
    CERTIFICATE_VERDICTS,
    PER_BOUND_SENTENCE,
    PER_VERSION,
    BoundaryLeaf,
    BoundaryProof,
    SilenceReceipt,
    build_receipt,
    derive_theta_q,
)
from trappoint_recall.per.verify import (
    Check,
    VerificationReport,
    leaves_from_disclosure,
    verify_receipt,
)

__all__ = [
    "CERTIFICATE_VERDICTS",
    "EMPTY_ROOT",
    "LEAF_MEMBER_NAMES",
    "LEAF_PREFIX",
    "MAX_SAFE_INTEGER",
    "MICRO",
    "NODE_PREFIX",
    "OUTCOMES",
    "PER_BOUND_SENTENCE",
    "PER_VERSION",
    "RAISED_OUTCOMES",
    "BoundaryInconsistent",
    "BoundaryLeaf",
    "BoundaryProof",
    "CandidateScore",
    "Check",
    "ExhaustionOverclaim",
    "InvalidLeaf",
    "InvalidProof",
    "Leaf",
    "NotCanonicalisable",
    "PerRefused",
    "RootMismatch",
    "SilenceReceipt",
    "UnsortedCandidates",
    "VerificationReport",
    "assert_score_sorted",
    "audit_path",
    "build_receipt",
    "canonicalise_leaf",
    "derive_theta_q",
    "leaf_hash",
    "leaf_preimage",
    "leaves_from_candidates",
    "leaves_from_disclosure",
    "merkle_root",
    "node_hash",
    "quantise_micro",
    "serialise_member",
    "sort_candidates",
    "verify_audit_path",
    "verify_receipt",
]
