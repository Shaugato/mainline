# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
"""The user turn: the top-40 fused candidates, quarantined and referred to by opaque tokens.

Three decisions are implemented here, all of them about what the model is *not* shown.

**Opaque references, not event identities.** Candidates are labelled ``C01``..``C40`` and the
mapping back to real event identities never leaves this process. Three reasons, in
increasing order of importance: a UUID is tokens spent on nothing; an identifier in the
prompt is a handle an injected narrative could name ("ignore the record with identifier
..."); and an opaque, position-derived label keeps the payload shape stable, which keeps the
request digest — and therefore the cassette — meaningful.

**The top forty, and the rest accounted for.** :func:`take_top_k` returns the kept slice
*and* the overflow, because a truncation that returns one list is a truncation whose tail
nobody has to think about. The overflow goes to the ledger as ``cap_exceeded``; it does not
evaporate.

**Facets, bounded.** Each facet is trimmed at :data:`MAX_FACET_CHARS`. A cue is specified at
about sixty tokens, so anything near the bound is a whole narrative leaking into a cue field
upstream; trimming keeps one listwise call inside its latency budget, and the trim is
recorded on the payload so a reader can tell a short cue from a cut one.

The whole payload is wrapped by ``providers.system_blocks.build_user_turn`` in a
sentinel-tagged span with an explicit instruction that its contents are data. That is
ARCHITECTURE 8.4 layer 2, and it applies here because every string in this payload was
written by a third party.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Final

from mainline_recall_agent.providers.errors import ProviderError
from mainline_recall_agent.providers.types import FACETS

__all__ = [
    "MAX_FACET_CHARS",
    "TOP_K_RERANK",
    "ExposureCue",
    "RerankCandidate",
    "build_payload",
    "candidate_ref_for",
    "take_top_k",
]

TOP_K_RERANK: Final[int] = 40
"""ARCHITECTURE 6.6: the listwise rerank runs over the top-40 fused candidates and dominates
the S4 budget (4 s p50 / 20 s p95)."""

MAX_FACET_CHARS: Final[int] = 600
"""Per-facet character bound in the payload. A cue is ~60 tokens by specification."""

_TRIM_MARKER: Final[str] = " [trimmed]"


@dataclass(frozen=True, slots=True)
class ExposureCue:
    """The permit side: what the proposed work would create.

    Emitted by the cue synthesiser on the *permit* side using the same facets and the same
    template as the event side (recall.md D3). If the two sides drift apart the whole design
    quietly degrades to narrative search, which is why both are built from ``FACETS``.
    """

    ref: str
    activity_path: str
    asset_class: str
    facets: Mapping[str, str]

    def __post_init__(self) -> None:
        _validate_facets(self.facets, what=f"exposure cue {self.ref!r}")
        if not self.ref:
            raise ProviderError("the exposure cue needs a reference the judge can echo")


@dataclass(frozen=True, slots=True)
class RerankCandidate:
    """One fused candidate, in the shape the judge is shown it.

    ``doc_id`` is present for the join back and is deliberately **not** put in the payload.
    ``fused_rank`` sets the order the candidates are presented in and the reference each one
    receives.
    """

    doc_id: str
    fused_rank: int
    activity_path: str
    asset_class: str
    facets: Mapping[str, str]
    also_matched: tuple[str, ...] = ()
    extra: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.doc_id:
            raise ProviderError("a rerank candidate needs an event identity to join back to")
        if self.fused_rank < 1:
            raise ProviderError(f"{self.doc_id}: fused_rank is 1-based, got {self.fused_rank}")
        _validate_facets(self.facets, what=f"candidate {self.doc_id!r}")


def _validate_facets(facets: Mapping[str, str], *, what: str) -> None:
    unknown = sorted(set(facets) - set(FACETS))
    if unknown:
        raise ProviderError(
            f"{what} carries facet(s) {unknown} outside the closed vocabulary {list(FACETS)}; "
            "an unmodelled facet in the prompt is a taxonomy change that never reached the "
            "policy",
            unknown=unknown,
        )
    if not facets:
        raise ProviderError(f"{what} has no facets; there is nothing to judge")


def candidate_ref_for(position: int) -> str:
    """``C01``-style opaque reference for a 1-based presentation position."""
    if position < 1:
        raise ProviderError(f"candidate positions are 1-based, got {position}")
    return f"C{position:02d}"


def take_top_k(
    candidates: Sequence[RerankCandidate], k: int = TOP_K_RERANK
) -> tuple[tuple[RerankCandidate, ...], tuple[RerankCandidate, ...]]:
    """Split into the slice the judge sees and the overflow the ledger takes.

    Returned as two tuples on purpose: the overflow is something the caller has to dispose
    of, and a helper that returned only the kept slice would make forgetting it the default.
    """
    if k < 1:
        raise ProviderError(f"the rerank depth must be at least 1, got {k}")
    ordered = tuple(sorted(candidates, key=lambda c: (c.fused_rank, c.doc_id)))
    return ordered[:k], ordered[k:]


def _trim(text: str) -> tuple[str, bool]:
    stripped = " ".join(text.split())
    if len(stripped) <= MAX_FACET_CHARS:
        return stripped, False
    return stripped[: MAX_FACET_CHARS - len(_TRIM_MARKER)] + _TRIM_MARKER, True


def _facet_block(facets: Mapping[str, str]) -> tuple[dict[str, str], bool]:
    """Facets in the frozen ``FACETS`` order, so the payload bytes do not depend on dict order."""
    out: dict[str, str] = {}
    trimmed = False
    for facet in FACETS:
        value = facets.get(facet)
        if value is None:
            continue
        text, was_trimmed = _trim(value)
        if not text:
            continue
        out[facet] = text
        trimmed = trimmed or was_trimmed
    return out, trimmed


def build_payload(
    exposure: ExposureCue, candidates: Sequence[RerankCandidate]
) -> tuple[dict[str, Any], dict[str, str]]:
    """Build the judge's user payload and the reference-to-event mapping.

    Returns:
        The payload (which goes inside the quarantined span of the user turn) and the
        ``candidate_ref -> doc_id`` mapping, which stays here.

    Raises:
        ProviderError: on an empty candidate list, or on two candidates sharing an event
            identity — one event judged twice in one listwise call would produce two verdicts
            for one check.
    """
    if not candidates:
        raise ProviderError(
            "the listwise judge was handed no candidates; an empty rerank is not a rerank, "
            "and calling the model to confirm it would be paying for silence"
        )
    seen: set[str] = set()
    for candidate in candidates:
        if candidate.doc_id in seen:
            raise ProviderError(
                f"{candidate.doc_id!r} appears twice in one listwise call", doc_id=candidate.doc_id
            )
        seen.add(candidate.doc_id)

    exposure_facets, exposure_trimmed = _facet_block(exposure.facets)
    entries: list[dict[str, Any]] = []
    mapping: dict[str, str] = {}
    for position, candidate in enumerate(
        sorted(candidates, key=lambda c: (c.fused_rank, c.doc_id)), start=1
    ):
        ref = candidate_ref_for(position)
        mapping[ref] = candidate.doc_id
        facet_block, trimmed = _facet_block(candidate.facets)
        entries.append(
            {
                "candidate_ref": ref,
                "activity_path": exposure_or(candidate.activity_path),
                "asset_class": exposure_or(candidate.asset_class),
                "facets": facet_block,
                "facets_trimmed": trimmed,
                "also_matched_count": len(candidate.also_matched),
            }
        )

    payload: dict[str, Any] = {
        "task": "listwise_precursor_relevance",
        "exposure": {
            "ref": exposure.ref,
            "activity_path": exposure_or(exposure.activity_path),
            "asset_class": exposure_or(exposure.asset_class),
            "facets": exposure_facets,
            "facets_trimmed": exposure_trimmed,
        },
        "candidates": entries,
    }
    return payload, mapping


def exposure_or(text: str) -> str:
    """Normalise a free-text field, substituting the closed vocabulary's absence marker.

    An empty activity path or asset class is absence of information, and saying so is better
    than sending an empty string that reads as a claim about the world.
    """
    stripped = " ".join(text.split())
    return stripped or "insufficient_evidence"
