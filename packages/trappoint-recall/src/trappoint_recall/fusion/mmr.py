# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""Maximal Marginal Relevance dedup, with the suppressed siblings returned rather than dropped.

Carbonell and Goldstein (1998), lambda = 0.7, cosine over cue embeddings. The departure
from textbook MMR is the return type, and it is the whole point of the module.

Textbook MMR *reorders*. Here it also *partitions*: a candidate whose similarity to an
already-selected representative reaches the redundancy threshold is not merely demoted, it
is recorded as a sibling of that representative and returned in
:attr:`MmrSelection.suppressed`. The caller writes one
``silence_ledger(reason='dedup_sibling')`` row per sibling and attaches the same list to the
check as ``also_matched``.

The reason is not tidiness. The same OEM alert lands on six sites and the same mechanism
recurs across a decade; showing a supervisor six near-identical checks guarantees a rubber
stamp, and showing one while *deleting* the other five guarantees a plaintiff's exhibit.
The third option — one representative, five named siblings, every one of them in the ledger
— is the only one that is both usable and defensible, so it is the only one this function
can express. There is no code path here that discards a candidate.

**Relevance normalisation, stated because it moves the result.** MMR mixes a relevance term
with a similarity term, so the two must be commensurate. RRF scores are rank-derived and sit
around ``1/(k+1)``, three orders below cosine; feeding them in raw would make lambda inert
and turn the selection into pure diversity. The default therefore min-max normalises
relevance across the candidate set before mixing. That transform is order-preserving and
deterministic, and it is disclosed here rather than buried, because it is a modelling choice
and not arithmetic.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Final

__all__ = [
    "DEDUP_SILENCE_REASON",
    "DEFAULT_LAMBDA",
    "DEFAULT_REDUNDANCY_THRESHOLD",
    "InvalidMmrInput",
    "MmrCandidate",
    "MmrSelection",
    "Representative",
    "SuppressedSibling",
    "cosine_similarity",
    "maximal_marginal_relevance",
]

DEFAULT_LAMBDA: Final = 0.7
"""ARCHITECTURE 6.4 / research 6.6. Relevance-weighted: diversity trims redundancy, it does
not drive the selection."""

DEFAULT_REDUNDANCY_THRESHOLD: Final = 0.90
"""Cosine at or above which a candidate is treated as a sibling of an already-selected
representative rather than as a distinct precursor.

**Unvalidated on the target corpus.** It is a policy value carried in ``recall_policy`` and
swept in the ablation, not a constant of nature; it sits below the 0.97 used for *ingest*
duplicate detection because retrieval redundancy is a looser relation than record identity.
"""

DEDUP_SILENCE_REASON: Final = "dedup_sibling"
"""The closed-vocabulary ``silence_ledger.reason`` the caller writes for every sibling."""


class InvalidMmrInput(ValueError):
    """A candidate set MMR cannot operate on: mismatched widths, a zero vector, a duplicate."""


@dataclass(frozen=True, slots=True)
class MmrCandidate:
    """One fused candidate with the cue embedding dedup is computed over.

    Attributes:
        doc_id: Event identifier.
        relevance: The fused relevance score, normally :attr:`FusedCandidate.rrf_score`.
        embedding: The cue-space vector. Dedup runs in the *cue* space, not the narrative
            space: two records of the same mechanism should collapse even when the
            investigators wrote nothing alike.
    """

    doc_id: str
    relevance: float
    embedding: tuple[float, ...]

    def __post_init__(self) -> None:
        if not self.doc_id:
            raise InvalidMmrInput("doc_id must be non-empty")
        if not math.isfinite(self.relevance):
            raise InvalidMmrInput(f"{self.doc_id}: relevance {self.relevance!r} is not finite")
        if not self.embedding:
            raise InvalidMmrInput(f"{self.doc_id}: empty embedding")
        for component in self.embedding:
            if not math.isfinite(component):
                raise InvalidMmrInput(f"{self.doc_id}: embedding has a non-finite component")


@dataclass(frozen=True, slots=True)
class Representative:
    """A candidate that survived dedup, and the siblings it stands for."""

    doc_id: str
    order: int
    relevance: float
    mmr_score: float
    max_similarity_to_selected: float
    also_matched: tuple[str, ...]

    def to_json(self) -> dict[str, object]:
        return {
            "doc_id": self.doc_id,
            "order": self.order,
            "relevance": self.relevance,
            "mmr_score": self.mmr_score,
            "max_similarity_to_selected": self.max_similarity_to_selected,
            "also_matched": list(self.also_matched),
        }


@dataclass(frozen=True, slots=True)
class SuppressedSibling:
    """A candidate collapsed into a representative. Visible, ledgered, never deleted."""

    doc_id: str
    representative_id: str
    similarity: float
    relevance: float
    reason: str = DEDUP_SILENCE_REASON

    def to_silence_record(self) -> dict[str, object]:
        """Return the payload the caller writes to ``mainline_meas.silence_ledger``."""
        return {
            "reason": self.reason,
            "subject_id": self.doc_id,
            "score": self.relevance,
            "threshold": self.similarity,
            "arithmetic": {
                "representative_id": self.representative_id,
                "cosine_to_representative": self.similarity,
                "rule": "MMR dedup: collapsed into a representative and attached to it "
                "as also_matched",
            },
        }


@dataclass(frozen=True, slots=True)
class MmrSelection:
    """The complete partition of the input: representatives plus siblings, nothing lost."""

    representatives: tuple[Representative, ...]
    suppressed: tuple[SuppressedSibling, ...]
    lambda_value: float
    redundancy_threshold: float
    n_input: int

    def __post_init__(self) -> None:
        total = len(self.representatives) + len(self.suppressed)
        if total != self.n_input:
            raise InvalidMmrInput(
                f"MMR lost {self.n_input - total} candidate(s): {len(self.representatives)} "
                f"representatives + {len(self.suppressed)} siblings != {self.n_input} inputs. "
                "A dedup that drops a precursor is the failure this type exists to make "
                "impossible."
            )

    @property
    def conserved(self) -> bool:
        """Always true by construction; kept as a readable name for the assertion."""
        return len(self.representatives) + len(self.suppressed) == self.n_input

    def also_matched_for(self, doc_id: str) -> tuple[str, ...]:
        for representative in self.representatives:
            if representative.doc_id == doc_id:
                return representative.also_matched
        raise KeyError(f"{doc_id!r} is not a representative in this selection")

    def split_at(self, n: int) -> tuple[tuple[Representative, ...], tuple[Representative, ...]]:
        """Split representatives into the first ``n`` and the remainder.

        Used for the top-40 rerank slice. Returned as two tuples rather than one truncated
        one so the overflow is something the caller has to do something with — a slice that
        silently forgets its tail is how a candidate leaves the run without a ledger row.
        """
        if n < 0:
            raise InvalidMmrInput(f"split point must be non-negative, got {n}")
        return self.representatives[:n], self.representatives[n:]

    def to_json(self) -> dict[str, object]:
        return {
            "lambda": self.lambda_value,
            "redundancy_threshold": self.redundancy_threshold,
            "n_input": self.n_input,
            "n_representatives": len(self.representatives),
            "n_suppressed": len(self.suppressed),
            "representatives": [r.to_json() for r in self.representatives],
            "suppressed": [
                {
                    "doc_id": s.doc_id,
                    "representative_id": s.representative_id,
                    "similarity": s.similarity,
                    "relevance": s.relevance,
                    "reason": s.reason,
                }
                for s in self.suppressed
            ],
        }


def cosine_similarity(left: Sequence[float], right: Sequence[float]) -> float:
    """Cosine similarity, refusing the two inputs that would make it meaningless.

    Raises:
        InvalidMmrInput: on mismatched widths, or on a zero vector (whose angle to
            anything is undefined, and which would otherwise silently read as maximally
            dissimilar and defeat dedup).
    """
    if len(left) != len(right):
        raise InvalidMmrInput(
            f"embedding widths differ ({len(left)} vs {len(right)}); a similarity between "
            "two embedding spaces is a number with no meaning"
        )
    dot = 0.0
    left_norm = 0.0
    right_norm = 0.0
    for a, b in zip(left, right, strict=True):
        dot += a * b
        left_norm += a * a
        right_norm += b * b
    if left_norm <= 0.0 or right_norm <= 0.0:
        raise InvalidMmrInput("cosine similarity is undefined for a zero vector")
    value = dot / math.sqrt(left_norm * right_norm)
    # Guard against the few-ulp overshoot that unit-norm vectors produce, so a downstream
    # comparison against the threshold cannot depend on floating-point noise.
    return max(-1.0, min(1.0, value))


def _normalised_relevance(candidates: Sequence[MmrCandidate]) -> dict[str, float]:
    values = [c.relevance for c in candidates]
    low = min(values)
    high = max(values)
    if high - low <= 0.0:
        # Every candidate equally relevant: MMR degenerates to pure diversity ordering,
        # which is the correct behaviour and is stated rather than special-cased away.
        return {c.doc_id: 1.0 for c in candidates}
    span = high - low
    return {c.doc_id: (c.relevance - low) / span for c in candidates}


def maximal_marginal_relevance(
    candidates: Sequence[MmrCandidate],
    *,
    lambda_value: float = DEFAULT_LAMBDA,
    redundancy_threshold: float = DEFAULT_REDUNDANCY_THRESHOLD,
    normalise_relevance: bool = True,
) -> MmrSelection:
    """Partition ``candidates`` into representatives and their suppressed siblings.

    At each step the remaining candidate with the highest
    ``lambda * relevance - (1 - lambda) * max_similarity_to_already_selected`` is taken. If
    that candidate's similarity to its nearest representative reaches
    ``redundancy_threshold`` it becomes a sibling of that representative; otherwise it
    becomes a representative in its own right.

    Args:
        candidates: The fused set. Order is irrelevant; the result is deterministic.
        lambda_value: Relevance weight in ``[0, 1]``. 0.7 by ARCHITECTURE 6.4.
        redundancy_threshold: Cosine at or above which a candidate is a sibling.
        normalise_relevance: Min-max the relevance term before mixing. See the module
            docstring: rank-derived RRF scores are not on the cosine scale.

    Returns:
        An :class:`MmrSelection` whose two parts always sum to ``len(candidates)``.

    Raises:
        InvalidMmrInput: on a duplicate ``doc_id``, a bad lambda or threshold, or an
            embedding this function cannot compare.
    """
    if not 0.0 <= lambda_value <= 1.0:
        raise InvalidMmrInput(f"lambda must lie in [0, 1], got {lambda_value!r}")
    if not -1.0 <= redundancy_threshold <= 1.0:
        raise InvalidMmrInput(
            f"redundancy threshold is a cosine and must lie in [-1, 1], "
            f"got {redundancy_threshold!r}"
        )
    seen: set[str] = set()
    for candidate in candidates:
        if candidate.doc_id in seen:
            raise InvalidMmrInput(
                f"{candidate.doc_id!r} appears twice in the MMR input; deduplicate the "
                "fused set before dedup, or one document becomes its own sibling"
            )
        seen.add(candidate.doc_id)

    if not candidates:
        return MmrSelection(
            representatives=(),
            suppressed=(),
            lambda_value=lambda_value,
            redundancy_threshold=redundancy_threshold,
            n_input=0,
        )

    relevance = (
        _normalised_relevance(candidates)
        if normalise_relevance
        else {c.doc_id: c.relevance for c in candidates}
    )
    by_id = {c.doc_id: c for c in candidates}
    remaining = sorted(by_id, key=lambda doc_id: (-relevance[doc_id], doc_id))

    representatives: list[Representative] = []
    also_matched: dict[str, list[str]] = {}
    suppressed: list[SuppressedSibling] = []

    while remaining:
        best_id = ""
        best_mmr = -math.inf
        best_similarity = 0.0
        best_neighbour = ""
        for doc_id in remaining:
            similarity = 0.0
            neighbour = ""
            for representative in representatives:
                value = cosine_similarity(
                    by_id[doc_id].embedding, by_id[representative.doc_id].embedding
                )
                if neighbour == "" or value > similarity:
                    similarity = value
                    neighbour = representative.doc_id
            mmr = lambda_value * relevance[doc_id] - (1.0 - lambda_value) * similarity
            # Ties break on doc_id ascending, so the selection is reproducible.
            if mmr > best_mmr or (mmr == best_mmr and (best_id == "" or doc_id < best_id)):
                best_mmr = mmr
                best_id = doc_id
                best_similarity = similarity
                best_neighbour = neighbour

        remaining.remove(best_id)
        if best_neighbour and best_similarity >= redundancy_threshold:
            suppressed.append(
                SuppressedSibling(
                    doc_id=best_id,
                    representative_id=best_neighbour,
                    similarity=best_similarity,
                    relevance=by_id[best_id].relevance,
                )
            )
            also_matched[best_neighbour].append(best_id)
        else:
            also_matched[best_id] = []
            representatives.append(
                Representative(
                    doc_id=best_id,
                    order=len(representatives) + 1,
                    relevance=by_id[best_id].relevance,
                    mmr_score=best_mmr,
                    max_similarity_to_selected=best_similarity,
                    also_matched=(),
                )
            )

    finalised = tuple(
        Representative(
            doc_id=r.doc_id,
            order=r.order,
            relevance=r.relevance,
            mmr_score=r.mmr_score,
            max_similarity_to_selected=r.max_similarity_to_selected,
            also_matched=tuple(also_matched[r.doc_id]),
        )
        for r in representatives
    )
    return MmrSelection(
        representatives=finalised,
        suppressed=tuple(suppressed),
        lambda_value=lambda_value,
        redundancy_threshold=redundancy_threshold,
        n_input=len(candidates),
    )
