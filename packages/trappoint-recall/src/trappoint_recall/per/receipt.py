# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""The silence receipt: ``(candidate_root, theta, s, n)`` plus the boundary pair.

What the receipt says
---------------------
The candidate multiset is committed as a **score-sorted** RFC 6962 tree. Disclosing the root,
``theta``, ``s``, ``n`` and inclusion paths for the leaves at ordinals ``s`` and ``s+1``
establishes two things and reveals nothing else:

1. **the cut is where the receipt says it is** — leaf ``s`` scored at or above ``theta`` and
   leaf ``s+1`` scored below it, both proved against the committed root; and
2. **nothing was hand-excluded** — every leaf carries its own ordinal, so removing,
   inserting or reordering any candidate changes every subsequent ordinal and therefore the
   root. There is no edit that preserves both sortedness and the commitment.

The suppressed candidates' identities, texts and scores stay undisclosed. That is the point:
a privilege log that had to publish the privileged material would not be a privilege log.

What ``theta`` is
-----------------
Severity-Graded Admission uses a **different** ``tau`` per severity, so no single threshold
describes the admission rule and pretending otherwise would be the exact species of
overclaim this mechanism exists to refuse. ``theta`` is therefore defined as *the lowest
score the system actually showed a human* — the minimum ``score_q`` over the ``blocking`` and
``advisory`` leaves — and each leaf carries its own ``tau_applied`` so the severity-graded
arithmetic stays auditable per candidate. The claim ``every leaf beyond position s scored
below theta`` is then exactly true, and the stronger claim nobody can support is never made.

Where nothing at all was raised, ``theta`` sits one micro-unit above the highest score
present, so ``s = 0`` — "we showed no one anything, and here is the commitment to everything
we scored."

What it does not say
--------------------
See :data:`PER_BOUND_SENTENCE`. It is not a caveat in a footnote; it is a field in the
receipt, a CI-grepped string in ``spec/wire/candidate-commitment.md``, and the reason
``index_generation`` is carried here at all.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Final

from trappoint_recall.per.errors import (
    BoundaryInconsistent,
    ExhaustionOverclaim,
    InvalidProof,
)
from trappoint_recall.per.leaf import (
    MICRO,
    RAISED_OUTCOMES,
    CandidateScore,
    Leaf,
    assert_score_sorted,
    leaf_hash,
    leaves_from_candidates,
)
from trappoint_recall.per.merkle import SHA256_BYTES, audit_path, merkle_root

__all__ = [
    "CERTIFICATE_VERDICTS",
    "PER_BOUND_SENTENCE",
    "PER_VERSION",
    "BoundaryLeaf",
    "BoundaryProof",
    "SilenceReceipt",
    "build_receipt",
    "derive_theta_q",
]

#: Bumped only when the leaf profile or the tree construction changes, which would invalidate
#: every historical receipt. Carried in the wire form so a verifier dispatches rather than
#: guesses.
PER_VERSION: Final = 1

#: **CI-grepped, verbatim.** ``spec/wire/candidate-commitment.md``, this module, the README
#: and the exhibit renderer must all carry this string byte-for-byte. A proof that overclaims
#: is worse than no proof.
PER_BOUND_SENTENCE: Final = "PER proves exhaustion of the retrieval that ran, not of the corpus."

#: ``mainline_meas.recall_certificate.verdict``'s closed vocabulary (migration 0087).
CERTIFICATE_VERDICTS: Final[tuple[str, ...]] = ("complete", "partial", "UNDETERMINED")


def derive_theta_q(leaves: Sequence[Leaf]) -> int:
    """Return the quantised boundary threshold implied by ``leaves``.

    The lowest ``score_q`` among the raised (``blocking`` / ``advisory``) leaves; one above
    the highest score present when nothing was raised; ``0`` for an empty candidate set.
    """
    raised = [leaf.score_q for leaf in leaves if leaf.outcome in RAISED_OUTCOMES]
    if raised:
        return min(raised)
    if leaves:
        return max(leaf.score_q for leaf in leaves) + 1
    return 0


@dataclass(frozen=True, slots=True)
class BoundaryLeaf:
    """One half of the boundary pair: a leaf, its 0-based index, and its audit path."""

    leaf: Leaf
    index: int
    path: tuple[bytes, ...]

    def to_json(self) -> dict[str, Any]:
        """Wire form. Paths are lowercase hex so the receipt survives JSON transport."""
        return {
            "index": self.index,
            "leaf": self.leaf.to_json(),
            "path": [node.hex() for node in self.path],
        }

    @classmethod
    def from_json(cls, document: Mapping[str, Any]) -> BoundaryLeaf:
        """Rebuild from the wire form, refusing a path that is not 32-byte hex."""
        index = document.get("index")
        if isinstance(index, bool) or not isinstance(index, int) or index < 0:
            raise InvalidProof(f"boundary index {index!r} is not a non-negative integer")
        raw_path = document.get("path")
        if not isinstance(raw_path, list):
            raise InvalidProof("boundary path must be a list of hex sibling hashes")
        path: list[bytes] = []
        for node in raw_path:
            if not isinstance(node, str):
                raise InvalidProof("boundary path entries must be hex strings")
            try:
                decoded = bytes.fromhex(node)
            except ValueError as exc:
                raise InvalidProof(f"boundary path entry {node!r} is not hex") from exc
            if len(decoded) != SHA256_BYTES:
                raise InvalidProof(
                    f"boundary path entry {node!r} is {len(decoded)} bytes, not {SHA256_BYTES}"
                )
            path.append(decoded)
        leaf_document = document.get("leaf")
        if not isinstance(leaf_document, Mapping):
            raise InvalidProof("boundary entry carries no leaf object")
        return cls(leaf=Leaf.from_json(leaf_document), index=index, path=tuple(path))


@dataclass(frozen=True, slots=True)
class BoundaryProof:
    """The disclosed pair. Either half is absent exactly when its ordinal does not exist."""

    at_s: BoundaryLeaf | None
    at_s_plus_1: BoundaryLeaf | None

    def to_json(self) -> dict[str, Any]:
        """Wire form. Absent halves are ``null``, never omitted: absence is information."""
        return {
            "leaf_at_s": None if self.at_s is None else self.at_s.to_json(),
            "leaf_at_s_plus_1": (None if self.at_s_plus_1 is None else self.at_s_plus_1.to_json()),
        }

    @classmethod
    def from_json(cls, document: Mapping[str, Any]) -> BoundaryProof:
        """Rebuild from the wire form."""
        at_s = document.get("leaf_at_s")
        at_next = document.get("leaf_at_s_plus_1")
        return cls(
            at_s=None if at_s is None else BoundaryLeaf.from_json(at_s),
            at_s_plus_1=None if at_next is None else BoundaryLeaf.from_json(at_next),
        )


@dataclass(frozen=True, slots=True)
class SilenceReceipt:
    """The row of ``mainline_meas.silence_receipt``, as a value a verifier can hold."""

    run_id: str
    permit_id: str
    policy_version: str
    index_generation: str
    corpus_root: bytes
    candidate_root: bytes
    theta_q: int
    s: int
    n: int
    boundary: BoundaryProof
    certificate_verdict: str
    not_exhaustive: bool
    per_version: int = PER_VERSION

    def __post_init__(self) -> None:
        """Refuse a receipt whose scalars contradict each other before it is ever written."""
        if not 0 <= self.s <= self.n:
            raise BoundaryInconsistent(
                f"boundary_sane: s={self.s}, n={self.n}; the database CHECK of the same name "
                "would refuse this row"
            )
        if len(self.candidate_root) != SHA256_BYTES or len(self.corpus_root) != SHA256_BYTES:
            raise BoundaryInconsistent(f"roots must be {SHA256_BYTES} bytes of SHA-256 output")
        if self.certificate_verdict not in CERTIFICATE_VERDICTS:
            raise BoundaryInconsistent(
                f"certificate verdict {self.certificate_verdict!r} is outside "
                f"{CERTIFICATE_VERDICTS}"
            )

    @property
    def theta(self) -> float:
        """The ``FLOAT8`` written to ``silence_receipt.theta``. ``theta_q`` is authoritative."""
        return self.theta_q / MICRO

    def to_json(self) -> dict[str, Any]:
        """Return the wire form the verifier and the CLI read."""
        return {
            "per_version": self.per_version,
            "run_id": self.run_id,
            "permit_id": self.permit_id,
            "policy_version": self.policy_version,
            "index_generation": self.index_generation,
            "corpus_root": self.corpus_root.hex(),
            "candidate_root": self.candidate_root.hex(),
            "theta": self.theta,
            "theta_q": self.theta_q,
            "s": self.s,
            "n": self.n,
            "boundary_proof": self.boundary.to_json(),
            "certificate_verdict": self.certificate_verdict,
            "not_exhaustive": self.not_exhaustive,
            "claim_bound": PER_BOUND_SENTENCE,
        }

    def to_json_text(self) -> str:
        """Pretty JSON, sorted, for the CLI and for committing next to an exhibit."""
        return json.dumps(self.to_json(), indent=2, sort_keys=True)

    @classmethod
    def from_json(cls, document: Mapping[str, Any]) -> SilenceReceipt:
        """Rebuild a receipt from its wire form, refusing anything structurally wrong."""

        def _text(name: str) -> str:
            value = document.get(name)
            if not isinstance(value, str):
                raise BoundaryInconsistent(f"receipt field {name!r} must be a string")
            return value

        def _count(name: str) -> int:
            value = document.get(name)
            if isinstance(value, bool) or not isinstance(value, int):
                raise BoundaryInconsistent(f"receipt field {name!r} must be an integer")
            return value

        def _digest(name: str) -> bytes:
            try:
                return bytes.fromhex(_text(name))
            except ValueError as exc:
                raise BoundaryInconsistent(f"receipt field {name!r} is not hex") from exc

        boundary_document = document.get("boundary_proof")
        if not isinstance(boundary_document, Mapping):
            raise BoundaryInconsistent("receipt carries no boundary_proof object")
        not_exhaustive = document.get("not_exhaustive", False)
        if not isinstance(not_exhaustive, bool):
            raise BoundaryInconsistent("not_exhaustive must be a boolean")
        version = document.get("per_version", PER_VERSION)
        if isinstance(version, bool) or not isinstance(version, int):
            raise BoundaryInconsistent("per_version must be an integer")
        if version != PER_VERSION:
            raise BoundaryInconsistent(
                f"receipt declares per_version={version}; this verifier implements "
                f"{PER_VERSION} and will not guess at another profile's leaf encoding"
            )
        return cls(
            run_id=_text("run_id"),
            permit_id=_text("permit_id"),
            policy_version=_text("policy_version"),
            index_generation=_text("index_generation"),
            corpus_root=_digest("corpus_root"),
            candidate_root=_digest("candidate_root"),
            theta_q=_count("theta_q"),
            s=_count("s"),
            n=_count("n"),
            boundary=BoundaryProof.from_json(boundary_document),
            certificate_verdict=_text("certificate_verdict"),
            not_exhaustive=not_exhaustive,
            per_version=version,
        )


def build_receipt(
    candidates: Sequence[CandidateScore],
    *,
    run_id: str,
    permit_id: str,
    policy_version: str,
    index_generation: str,
    corpus_root: bytes,
    certificate_verdict: str,
    not_exhaustive: bool = False,
    theta_q: int | None = None,
) -> tuple[SilenceReceipt, tuple[Leaf, ...]]:
    """Build the commitment and its boundary disclosure.

    Args:
        candidates: the full scored candidate set, in any order. Sorting is done here so a
            caller cannot supply an order and thereby choose the cut.
        run_id: ``mainline_meas.recall_run.run_id``, as RFC 4122 text.
        permit_id: the gated subject.
        policy_version: the anchored ``recall_policy`` the run cited.
        index_generation: the ANN index generation observed during the run. Carried because
            of :data:`PER_BOUND_SENTENCE`, not for decoration.
        corpus_root: the ledger checkpoint root at the read timestamp.
        certificate_verdict: the M4 CUE HORIZON verdict for this run.
        not_exhaustive: set when the caller *knowingly* emits a receipt that claims no
            exhaustion. Required under an ``UNDETERMINED`` verdict.
        theta_q: override the derived boundary threshold. Supplied by a caller that already
            holds it; validated against the leaves either way.

    Returns:
        The receipt and the committed leaf sequence, in commitment order.

    Raises:
        ExhaustionOverclaim: verdict is ``UNDETERMINED`` and ``not_exhaustive`` is false.
        BoundaryInconsistent: a supplied ``theta_q`` leaves a raised candidate past ``s``.
        InvalidLeaf: a duplicate ``event_id``, or a field outside its range.
    """
    if certificate_verdict not in CERTIFICATE_VERDICTS:
        raise BoundaryInconsistent(
            f"certificate verdict {certificate_verdict!r} is outside {CERTIFICATE_VERDICTS}"
        )
    if certificate_verdict == "UNDETERMINED" and not not_exhaustive:
        raise ExhaustionOverclaim(
            "the coverage certificate for this run is UNDETERMINED, so the retrieval's own "
            "reach is unknown and PER may not claim exhaustion of it. Emit the receipt with "
            "not_exhaustive=True — which is recorded on the receipt's face — or certify "
            "coverage first. " + PER_BOUND_SENTENCE
        )

    leaves = leaves_from_candidates(candidates)
    assert_score_sorted(leaves)
    hashes = [leaf_hash(leaf) for leaf in leaves]
    root = merkle_root(hashes)
    n = len(leaves)

    resolved_theta_q = derive_theta_q(leaves) if theta_q is None else theta_q
    if resolved_theta_q < 0:
        raise BoundaryInconsistent(f"theta_q {resolved_theta_q} is negative")
    s = sum(1 for leaf in leaves if leaf.score_q >= resolved_theta_q)

    # The receipt's claim, enforced before it can be made: nothing that reached a human may
    # lie beyond the cut. With a derived theta this holds by construction; with a supplied
    # one it is exactly the thing a caller could get wrong, so it is checked rather than
    # assumed (P2 — a projection a gate reads is enforced, never trusted).
    for leaf in leaves:
        if leaf.outcome in RAISED_OUTCOMES and leaf.ord > s:
            raise BoundaryInconsistent(
                f"leaf {leaf.ord} was raised as {leaf.outcome!r} with score_q={leaf.score_q} "
                f"but lies beyond s={s} under theta_q={resolved_theta_q}. The receipt would "
                "assert that everything past s scored below theta while having shown someone "
                "one of those items."
            )

    def _boundary(ordinal: int) -> BoundaryLeaf | None:
        if not 1 <= ordinal <= n:
            return None
        index = ordinal - 1
        return BoundaryLeaf(leaf=leaves[index], index=index, path=audit_path(index, hashes))

    receipt = SilenceReceipt(
        run_id=run_id,
        permit_id=permit_id,
        policy_version=policy_version,
        index_generation=index_generation,
        corpus_root=corpus_root,
        candidate_root=root,
        theta_q=resolved_theta_q,
        s=s,
        n=n,
        boundary=BoundaryProof(at_s=_boundary(s), at_s_plus_1=_boundary(s + 1)),
        certificate_verdict=certificate_verdict,
        not_exhaustive=not_exhaustive,
    )
    return receipt, leaves
