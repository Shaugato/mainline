# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""The PER leaf: what is committed to, and the arithmetic that makes it reproducible.

Recall lead D10, verbatim::

    leaf = sha256(0x00 || JCS({ord, event_id, score_q, tau_applied, outcome}))
    score_q = round(p_relevant * 10**6) as an INTEGER

The integer is the whole ruling. ``p_relevant`` is a FLOAT8 in the database and a float in
the agent, and the *only* place its binary value is allowed to matter is the sort. Quantising
to micro-units before hashing means a receipt written by this implementation and a receipt
checked by a re-implementation in another language cannot disagree about a leaf because one
of them printed ``0.35000000000000003``.

Rounding is pinned, not inherited
---------------------------------
"round" is ambiguous across languages: Python's built-in :func:`round` is round-half-to-even,
JavaScript's ``Math.round`` is round-half-up (toward ``+Infinity``), Rust's ``f64::round`` is
round-half-away-from-zero. On a value that lands exactly on a half — which
``p_relevant = 0.0000005`` does not, but a calibrator emitting exact decimal knots very well
can — those three disagree. :func:`quantise_micro` therefore fixes the rule as **round half
up over the exact binary value of the double**, computed with :mod:`decimal` so it is exact
rather than approximately exact. The re-implementation instruction is one sentence, in
``spec/wire/candidate-commitment.md``, and it is unambiguous.

``tau_applied`` is quantised the same way and lands in the leaf under its own name. It is not
the sort key, so it could in principle have been a float — but the custody payload profile
(ruling CU-5) refuses binary floats in a hashed preimage, and a leaf that is canonicalisable
by one profile and not the other is a trap for whoever wires PER into the ledger next.
"""

from __future__ import annotations

import hashlib
import math
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from typing import Final

from trappoint_recall.per.canon import canonicalise_leaf
from trappoint_recall.per.errors import InvalidLeaf, UnsortedCandidates

__all__ = [
    "LEAF_MEMBER_NAMES",
    "MICRO",
    "OUTCOMES",
    "RAISED_OUTCOMES",
    "CandidateScore",
    "Leaf",
    "assert_score_sorted",
    "leaf_hash",
    "leaf_preimage",
    "leaves_from_candidates",
    "quantise_micro",
    "sort_candidates",
]

#: The quantisation denominator. ``score_q = 750000`` is ``p_relevant = 0.75``.
MICRO: Final = 1_000_000

#: The five member names, frozen. Adding a sixth changes every historical leaf hash, so it is
#: a new leaf version with its own domain tag, never an edit to this tuple.
LEAF_MEMBER_NAMES: Final[tuple[str, ...]] = (
    "event_id",
    "ord",
    "outcome",
    "score_q",
    "tau_applied",
)

#: ``mainline_meas.recall_candidate.outcome``'s closed vocabulary (ARCHITECTURE 5.7).
OUTCOMES: Final[tuple[str, ...]] = ("blocking", "advisory", "silenced", "deduped")

#: The outcomes that reached a human. ``theta`` is the lowest score among these — see
#: :func:`~trappoint_recall.per.receipt.derive_theta_q`.
RAISED_OUTCOMES: Final[frozenset[str]] = frozenset({"blocking", "advisory"})

#: RFC 4122 text form, lowercased. The leaf commits to the *text*, so the text is pinned.
_UUID_TEXT: Final[re.Pattern[str]] = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"
)

#: RFC 6962 §2.1 domain separation. Identical to the custody ledger's leaf tag, so a PER leaf
#: and a ledger leaf can never be confused for one another inside the same tree.
_LEAF_TAG: Final = b"\x00"


def quantise_micro(value: float) -> int:
    """Return ``value`` in units of 1e-6, rounding halves up over the exact double.

    Args:
        value: a probability or threshold in ``[0.0, 1.0]``.

    Returns:
        The integer ``round_half_up(exact(value) * 10**6)``.

    Raises:
        InvalidLeaf: if ``value`` is not finite or lies outside ``[0.0, 1.0]``.
    """
    if not math.isfinite(value):
        raise InvalidLeaf(f"{value!r} is not a finite probability")
    if not 0.0 <= value <= 1.0:
        raise InvalidLeaf(
            f"{value!r} is outside [0, 1]; PER quantises calibrated probabilities and "
            "thresholds, never raw distances"
        )
    exact = Decimal(value) * MICRO
    return int(exact.quantize(Decimal(1), rounding=ROUND_HALF_UP))


@dataclass(frozen=True, slots=True)
class CandidateScore:
    """One scored candidate, as the orchestrator holds it before commitment."""

    event_id: str
    p_relevant: float
    tau_applied: float
    outcome: str

    def __post_init__(self) -> None:
        """Refuse a candidate the commitment could not describe."""
        if not _UUID_TEXT.match(self.event_id):
            raise InvalidLeaf(
                f"event_id {self.event_id!r} is not lowercase RFC 4122 text; the leaf commits "
                "to the text, so a mixed-case or braced rendering is a different leaf"
            )
        if self.outcome not in OUTCOMES:
            raise InvalidLeaf(
                f"outcome {self.outcome!r} is outside the closed vocabulary {OUTCOMES}"
            )
        # Both raise InvalidLeaf on a non-probability; called for the check, not the value.
        quantise_micro(self.p_relevant)
        quantise_micro(self.tau_applied)


@dataclass(frozen=True, slots=True)
class Leaf:
    """A positioned leaf. ``ord`` is 1-based, as ARCHITECTURE 5.7's ``s`` and ``n`` are."""

    ord: int
    event_id: str
    score_q: int
    tau_applied_q: int
    outcome: str

    def __post_init__(self) -> None:
        """Refuse a leaf whose fields could not have come from a real candidate."""
        if self.ord < 1:
            raise InvalidLeaf(f"ord is 1-based; got {self.ord}")
        if not _UUID_TEXT.match(self.event_id):
            raise InvalidLeaf(f"event_id {self.event_id!r} is not lowercase RFC 4122 text")
        if not 0 <= self.score_q <= MICRO:
            raise InvalidLeaf(f"score_q {self.score_q} is outside [0, {MICRO}]")
        if not 0 <= self.tau_applied_q <= MICRO:
            raise InvalidLeaf(f"tau_applied {self.tau_applied_q} is outside [0, {MICRO}]")
        if self.outcome not in OUTCOMES:
            raise InvalidLeaf(f"outcome {self.outcome!r} is outside {OUTCOMES}")

    def member(self) -> dict[str, int | str]:
        """The JCS object this leaf hashes. Member *names* are D10's, verbatim."""
        return {
            "ord": self.ord,
            "event_id": self.event_id,
            "score_q": self.score_q,
            "tau_applied": self.tau_applied_q,
            "outcome": self.outcome,
        }

    def to_json(self) -> dict[str, int | str]:
        """Wire form. Identical to :meth:`member`: the disclosed leaf *is* the preimage."""
        return self.member()

    @classmethod
    def from_json(cls, document: Mapping[str, object]) -> Leaf:
        """Rebuild a leaf from its wire form, refusing anything the profile excludes."""
        missing = [name for name in LEAF_MEMBER_NAMES if name not in document]
        if missing:
            raise InvalidLeaf(f"leaf is missing member(s) {missing}")
        extra = [name for name in document if name not in LEAF_MEMBER_NAMES]
        if extra:
            raise InvalidLeaf(
                f"leaf carries member(s) {extra} outside the frozen profile "
                f"{list(LEAF_MEMBER_NAMES)}; an extra member changes the hash"
            )
        ordinal = document["ord"]
        score_q = document["score_q"]
        tau_q = document["tau_applied"]
        event_id = document["event_id"]
        outcome = document["outcome"]
        if (
            isinstance(ordinal, bool)
            or isinstance(score_q, bool)
            or isinstance(tau_q, bool)
            or not isinstance(ordinal, int)
            or not isinstance(score_q, int)
            or not isinstance(tau_q, int)
        ):
            raise InvalidLeaf("ord, score_q and tau_applied must be integers, not floats")
        if not isinstance(event_id, str) or not isinstance(outcome, str):
            raise InvalidLeaf("event_id and outcome must be strings")
        return cls(
            ord=ordinal,
            event_id=event_id,
            score_q=score_q,
            tau_applied_q=tau_q,
            outcome=outcome,
        )


def leaf_preimage(leaf: Leaf) -> bytes:
    """The canonical bytes hashed for ``leaf`` — RFC 8785 over D10's five members."""
    return canonicalise_leaf(leaf.member())


def leaf_hash(leaf: Leaf) -> bytes:
    """``sha256(0x00 || JCS(member))`` — RFC 6962 §2.1 leaf domain separation."""
    return hashlib.sha256(_LEAF_TAG + leaf_preimage(leaf)).digest()


def sort_candidates(candidates: Sequence[CandidateScore]) -> tuple[CandidateScore, ...]:
    """Return ``candidates`` in commitment order: score descending, then ``event_id``.

    The tie-break is not decoration. Two candidates that quantise to the same ``score_q``
    would otherwise be ordered by whatever the retrieval happened to emit, and a receipt
    rebuilt from ``recall_candidate`` on a different day would produce a different root for
    the same set. ``event_id`` ascending is total, stable and reproducible by a stranger.
    """
    return tuple(
        sorted(
            candidates,
            key=lambda candidate: (-quantise_micro(candidate.p_relevant), candidate.event_id),
        )
    )


def leaves_from_candidates(candidates: Sequence[CandidateScore]) -> tuple[Leaf, ...]:
    """Sort, position and quantise a candidate set into its committed leaf sequence.

    Raises:
        InvalidLeaf: if an ``event_id`` appears more than once. A duplicate would break the
            conservation law (MI17) and double-count the same precursor.
    """
    seen: set[str] = set()
    for candidate in candidates:
        if candidate.event_id in seen:
            raise InvalidLeaf(
                f"{candidate.event_id} appears twice in the candidate set; "
                "mainline_meas.recall_candidate is keyed (run_id, event_id) and the "
                "conservation law counts each candidate once"
            )
        seen.add(candidate.event_id)
    return tuple(
        Leaf(
            ord=position,
            event_id=candidate.event_id,
            score_q=quantise_micro(candidate.p_relevant),
            tau_applied_q=quantise_micro(candidate.tau_applied),
            outcome=candidate.outcome,
        )
        for position, candidate in enumerate(sort_candidates(candidates), start=1)
    )


def assert_score_sorted(leaves: Sequence[Leaf]) -> None:
    """Refuse a leaf sequence that is not in commitment order.

    Raises:
        UnsortedCandidates: on the first out-of-order pair, naming both ordinals.
        InvalidLeaf: if the ordinals are not ``1..n`` contiguous.
    """
    for position, leaf in enumerate(leaves, start=1):
        if leaf.ord != position:
            raise InvalidLeaf(
                f"leaf at position {position} claims ord={leaf.ord}; ordinals must be "
                "1..n contiguous or the boundary index means nothing"
            )
    for left, right in zip(leaves, leaves[1:], strict=False):
        if (-left.score_q, left.event_id) > (-right.score_q, right.event_id):
            raise UnsortedCandidates(
                f"leaf {left.ord} (score_q={left.score_q}, {left.event_id}) precedes leaf "
                f"{right.ord} (score_q={right.score_q}, {right.event_id}), which is out of "
                "commitment order. The boundary disclosure proves nothing over an unsorted "
                "sequence: its whole force is that no item can be hand-excluded without "
                "breaking sortedness."
            )
