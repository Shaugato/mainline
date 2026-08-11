# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""The frozen feature vector, and the digest that makes it re-derivable by a stranger.

``mainline_meas.recall_candidate.features`` is a JSONB column that a plaintiff's expert will
read. For that column to be worth anything, three things have to be true at once:

1. the **order and meaning** of the slots is fixed and versioned, so a number recorded in
   2026 still means the same thing in 2031;
2. the recorded payload **names its own spec** — :data:`FEATURE_SPEC_SHA256` travels in every
   row, so a reader can tell whether the vector in front of them was built by this code;
3. the mapping from a facet name to its one-hot slot is **in the record**, not in a header
   file, because the facet vocabulary belongs to the deployment and this package holds none.

Point 3 is why :data:`FEATURE_SPEC_SHA256` covers slot *names* and arity but not facet
names: ``trappoint-recall`` is Apache-2.0 substrate and carries no MAINLINE vocabulary, so
the caller supplies an ordered five-element facet vocabulary and its digest is recorded
beside the spec digest. Both are needed to re-derive the vector; neither is sufficient.

**Severity has no slot, and that is the design.** ARCHITECTURE 6.4: *severity lowers the
evidence bar; it never inflates the score.* If severity were a feature it would flow into
the raw score, through the calibrator, and out as an inflated ``p_relevant`` — the exact
score-boosting move the product refuses. Severity enters exactly once, in
:mod:`trappoint_recall.fusion.sga`, as the choice of threshold.
``tests/unit/recall_fusion/test_featurespec.py`` asserts no slot mentions it, and
``test_no_severity_multiplication.py`` asserts no expression in this package multiplies by
it.

**Why a scalar, then isotonic.** Isotonic regression is univariate. The feature vector is
collapsed to one raw score by :func:`raw_score`, a plain weighted sum whose weights come
from the signed policy row, and the calibrator is fitted on *that* scalar. Stating the link
function explicitly beats hiding it inside a fitted multivariate model: the weights are an
exhibit, and monotone-in-evidence is a property a reader can check by eye.
"""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Final, Literal

__all__ = [
    "FACET_SLOT_COUNT",
    "FEATURE_NAMES",
    "FEATURE_SPEC",
    "FEATURE_SPEC_SHA256",
    "FEATURE_SPEC_VERSION",
    "FEATURE_WIDTH",
    "RERANK_NOT_RANKED",
    "RERANK_NOT_RELEVANT",
    "RERANK_RELEVANT",
    "FeatureSlot",
    "FeatureVector",
    "InvalidFeatureVector",
    "build_features",
    "facet_onehot",
    "facet_vocabulary_sha256",
    "raw_score",
]

FEATURE_SPEC_VERSION: Final = "trappoint.recall.featurespec/1"
"""Bumped only by a change that would make an older reader misinterpret a stored vector.
Changing it invalidates every fitted calibrator, which is the intended cost."""

FACET_SLOT_COUNT: Final = 5
"""Five facets: the arity is frozen here, the names are the deployment's."""

RERANK_NOT_RANKED: Final = -1.0
"""The judge never saw this candidate, or declined it. Distinct from a negative verdict:
*not asked* and *asked and refused* must not collapse into one number."""
RERANK_NOT_RELEVANT: Final = 0.0
RERANK_RELEVANT: Final = 1.0

SlotKind = Literal["continuous", "ordinal", "binary", "bitmask"]


@dataclass(frozen=True, slots=True)
class FeatureSlot:
    """One position in the frozen vector."""

    name: str
    kind: SlotKind
    note: str

    def spec_entry(self) -> dict[str, str]:
        """Return the part of the slot that enters the digest; the note is prose and does not."""
        return {"name": self.name, "kind": self.kind}


FEATURE_SPEC: Final[tuple[FeatureSlot, ...]] = (
    FeatureSlot(
        "rrf_score",
        "continuous",
        "Weighted reciprocal-rank fusion over channels C, C_sweep and D. Rank-derived, so "
        "it carries no channel's raw score distribution.",
    ),
    FeatureSlot(
        "best_arm_rank",
        "ordinal",
        "Best 1-based position across contributing arms. 0 when no arm returned it (a "
        "candidate that arrived by another route).",
    ),
    FeatureSlot(
        "scope_level",
        "ordinal",
        "Archival level of the arm that produced the best rank. Deeper levels are narrower "
        "bonds and stronger evidence.",
    ),
    FeatureSlot("facet_onehot_0", "binary", "Facet slot 0 of the caller's ordered vocabulary."),
    FeatureSlot("facet_onehot_1", "binary", "Facet slot 1 of the caller's ordered vocabulary."),
    FeatureSlot("facet_onehot_2", "binary", "Facet slot 2 of the caller's ordered vocabulary."),
    FeatureSlot("facet_onehot_3", "binary", "Facet slot 3 of the caller's ordered vocabulary."),
    FeatureSlot("facet_onehot_4", "binary", "Facet slot 4 of the caller's ordered vocabulary."),
    FeatureSlot(
        "rerank_verdict",
        "ordinal",
        "-1 not ranked, 0 not_relevant, 1 relevant. The listwise judge's verdict after the "
        "mechanism-and-precondition citation rule has been enforced.",
    ),
    FeatureSlot(
        "rerank_confidence",
        "continuous",
        "Ordinal evidence strength from the judge, mapped into [0, 1]. An ordinal, not a "
        "probability: it is an INPUT to calibration, never an output of it.",
    ),
    FeatureSlot(
        "control_class_overlap",
        "continuous",
        "Jaccard overlap between the controls the past event defeated and the controls the "
        "proposed work touches, in [0, 1].",
    ),
    FeatureSlot(
        "asset_class_match",
        "binary",
        "1 when the asset classes agree. Weak on its own: a mechanism crosses equipment.",
    ),
    FeatureSlot(
        "channel_mask",
        "bitmask",
        "Bitwise OR of the channels that returned this candidate (C=1, C_sweep=2, D=4). "
        "Agreement across channels is evidence; the mask preserves which.",
    ),
    FeatureSlot(
        "coarse_only",
        "binary",
        "1 when the 256-d coarse sweep was the only channel that found it. Never blocking "
        "unless severity is 5 (ARCHITECTURE 6.4), so the admission rule needs it explicitly.",
    ),
)

FEATURE_NAMES: Final[tuple[str, ...]] = tuple(slot.name for slot in FEATURE_SPEC)
FEATURE_WIDTH: Final = len(FEATURE_SPEC)


def _canonical_json(payload: Any) -> bytes:
    """Compact, key-sorted, ASCII-escaped JSON. Two machines must agree byte for byte."""
    return json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False
    ).encode("utf-8")


def _feature_spec_sha256() -> str:
    return hashlib.sha256(
        _canonical_json(
            {
                "version": FEATURE_SPEC_VERSION,
                "facet_slots": FACET_SLOT_COUNT,
                "slots": [slot.spec_entry() for slot in FEATURE_SPEC],
            }
        )
    ).hexdigest()


FEATURE_SPEC_SHA256: Final[str] = _feature_spec_sha256()
"""Written into every ``recall_candidate.features`` payload. If it moves, every stored
vector was produced by a different spec and the calibrator fitted on the old one is void."""


class InvalidFeatureVector(ValueError):
    """A feature vector that cannot be built or cannot be trusted.

    Always raised rather than coerced: a silently clamped feature is a silently changed
    ``p_relevant``, and ``p_relevant`` is the number a supervisor is shown.
    """


def facet_vocabulary_sha256(vocabulary: Sequence[str]) -> str:
    """Digest of the ordered facet vocabulary, recorded beside the spec digest."""
    return hashlib.sha256(_canonical_json(list(vocabulary))).hexdigest()


def _validate_vocabulary(vocabulary: Sequence[str]) -> tuple[str, ...]:
    ordered = tuple(vocabulary)
    if len(ordered) != FACET_SLOT_COUNT:
        raise InvalidFeatureVector(
            f"the facet vocabulary must have exactly {FACET_SLOT_COUNT} entries to fill the "
            f"one-hot slots, got {len(ordered)}. The arity is frozen by the spec; the names "
            "are the deployment's."
        )
    if len(set(ordered)) != len(ordered):
        raise InvalidFeatureVector(f"the facet vocabulary repeats a name: {ordered}")
    if any(not name for name in ordered):
        raise InvalidFeatureVector("the facet vocabulary contains an empty name")
    return ordered


def facet_onehot(facet: str, vocabulary: Sequence[str]) -> tuple[float, ...]:
    """One-hot encode ``facet`` against the caller's ordered vocabulary.

    Raises:
        InvalidFeatureVector: if the facet is not in the vocabulary. An unknown facet is a
            taxonomy change that never reached the policy, and encoding it as all-zeros
            would hide that behind a plausible vector.
    """
    ordered = _validate_vocabulary(vocabulary)
    try:
        index = ordered.index(facet)
    except ValueError as exc:
        raise InvalidFeatureVector(
            f"facet {facet!r} is not in the declared vocabulary {ordered}. Encoding it as "
            "all-zeros would make an unmodelled facet look like a modelled one."
        ) from exc
    return tuple(1.0 if position == index else 0.0 for position in range(FACET_SLOT_COUNT))


@dataclass(frozen=True, slots=True)
class FeatureVector:
    """A validated vector plus the two digests needed to re-derive it."""

    values: tuple[float, ...]
    facet_vocabulary: tuple[str, ...]

    def __post_init__(self) -> None:
        if len(self.values) != FEATURE_WIDTH:
            raise InvalidFeatureVector(f"expected {FEATURE_WIDTH} features, got {len(self.values)}")
        for name, value in zip(FEATURE_NAMES, self.values, strict=True):
            if not math.isfinite(value):
                raise InvalidFeatureVector(f"feature {name!r} is not finite: {value!r}")
        _validate_vocabulary(self.facet_vocabulary)

    def as_mapping(self) -> dict[str, float]:
        return dict(zip(FEATURE_NAMES, self.values, strict=True))

    def to_json(self) -> dict[str, object]:
        """Return the exact payload written to ``mainline_meas.recall_candidate.features``."""
        return {
            "feature_spec": FEATURE_SPEC_VERSION,
            "feature_spec_sha256": FEATURE_SPEC_SHA256,
            "facet_vocabulary": list(self.facet_vocabulary),
            "facet_vocabulary_sha256": facet_vocabulary_sha256(self.facet_vocabulary),
            "names": list(FEATURE_NAMES),
            "vector": list(self.values),
        }

    @classmethod
    def from_json(cls, payload: Mapping[str, Any]) -> FeatureVector:
        """Rebuild a vector from a stored payload, refusing a spec mismatch.

        Raises:
            InvalidFeatureVector: if the payload was written under a different spec. A
                calibrator fitted on one spec has no meaning applied to another, and
                silently accepting the mismatch would make that invisible.
        """
        recorded_spec = payload.get("feature_spec_sha256")
        if recorded_spec != FEATURE_SPEC_SHA256:
            raise InvalidFeatureVector(
                f"stored feature vector declares spec {recorded_spec!r} but this build is "
                f"{FEATURE_SPEC_SHA256!r}. The two vectors are not comparable."
            )
        raw = payload.get("vector")
        vocabulary = payload.get("facet_vocabulary")
        if not isinstance(raw, list) or not isinstance(vocabulary, list):
            raise InvalidFeatureVector("stored feature payload is missing vector or vocabulary")
        return cls(
            values=tuple(float(value) for value in raw),
            facet_vocabulary=tuple(str(name) for name in vocabulary),
        )


def build_features(
    *,
    rrf_score: float,
    best_arm_rank: int,
    scope_level: int,
    facet: str,
    facet_vocabulary: Sequence[str],
    rerank_verdict: float,
    rerank_confidence: float,
    control_class_overlap: float,
    asset_class_match: bool,
    channel_mask: int,
    coarse_only: bool,
) -> FeatureVector:
    """Build the frozen vector, validating every slot against its declared domain.

    Raises:
        InvalidFeatureVector: on any out-of-domain value. Nothing is clamped.
    """
    if best_arm_rank < 0:
        raise InvalidFeatureVector(
            f"best_arm_rank is 1-based with 0 meaning 'no arm returned it', got {best_arm_rank}"
        )
    if scope_level < 0:
        raise InvalidFeatureVector(f"scope_level must be non-negative, got {scope_level}")
    if rerank_verdict not in (RERANK_NOT_RANKED, RERANK_NOT_RELEVANT, RERANK_RELEVANT):
        raise InvalidFeatureVector(
            f"rerank_verdict must be one of "
            f"{(RERANK_NOT_RANKED, RERANK_NOT_RELEVANT, RERANK_RELEVANT)}, "
            f"got {rerank_verdict!r}"
        )
    if not 0.0 <= rerank_confidence <= 1.0:
        raise InvalidFeatureVector(
            f"rerank_confidence is an ordinal mapped into [0, 1], got {rerank_confidence!r}"
        )
    if not 0.0 <= control_class_overlap <= 1.0:
        raise InvalidFeatureVector(
            f"control_class_overlap is a Jaccard index in [0, 1], got {control_class_overlap!r}"
        )
    if channel_mask < 0 or channel_mask > 7:
        raise InvalidFeatureVector(
            f"channel_mask is a 3-bit mask over (C, C_sweep, D), got {channel_mask}"
        )
    onehot = facet_onehot(facet, facet_vocabulary)
    values = (
        float(rrf_score),
        float(best_arm_rank),
        float(scope_level),
        *onehot,
        float(rerank_verdict),
        float(rerank_confidence),
        float(control_class_overlap),
        1.0 if asset_class_match else 0.0,
        float(channel_mask),
        1.0 if coarse_only else 0.0,
    )
    return FeatureVector(values=values, facet_vocabulary=tuple(facet_vocabulary))


def raw_score(vector: FeatureVector, weights: Mapping[str, float]) -> float:
    """Collapse the vector to the scalar the isotonic calibrator is fitted on.

    A plain weighted sum. The weights come from the signed ``recall_policy`` row, and every
    key must name a slot in :data:`FEATURE_SPEC`: an unrecognised key is refused rather than
    ignored, which is what makes it impossible to smuggle ``severity`` — or anything else
    outside the spec — into the score.

    Raises:
        InvalidFeatureVector: on an unknown or non-finite weight.
    """
    unknown = sorted(set(weights) - set(FEATURE_NAMES))
    if unknown:
        raise InvalidFeatureVector(
            f"unknown feature weight(s) {unknown}. The scored feature set is frozen by "
            f"{FEATURE_SPEC_VERSION}; anything outside it — severity above all — is refused, "
            "because severity lowers the evidence bar and must never inflate the score."
        )
    total = 0.0
    mapping = vector.as_mapping()
    for name, weight in weights.items():
        if not math.isfinite(weight):
            raise InvalidFeatureVector(f"weight for {name!r} is not finite: {weight!r}")
        total += weight * mapping[name]
    if not math.isfinite(total):
        raise InvalidFeatureVector("raw score overflowed to a non-finite value")
    return total
