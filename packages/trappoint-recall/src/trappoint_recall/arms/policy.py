# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""The arm policy: graded ``k``, per-arm fusion weight, and the cap that must bite.

Every number an arm carries comes from here, and this object comes from a signed, anchored
policy row — never from a constant in the retriever. That is the difference between *"we
chose a threshold"* and *"a threshold was chosen for us, by a named author, under a
signature"*, and it is the same argument that applies to ``tau``: an arm weight decides which
precursor outranks which, so it is an exhibit.

**Why the cap exists at all.** ``optimizer_span_limit`` bounds the spans the optimizer will
build for a constrained scan, and an arm set that grows past what the planner will constrain
degrades to a scan **silently**. In a recall gate a silently unused index is not a
performance regression; it is a precursor that stops being reachable with no row anywhere
that is wrong. A bounded set with a logged overflow is honest. An unbounded one is a latent
full scan.

**Reconciling the two statements of the bound.** The domain plan says *"arm set is bounded at
16 (levels 1–3 × populated facets, plus the coarse sweep)"*; the worker's completion test says
*"≤16 fully-literal-bound arms plus the coarse sweep"*. This module takes the stricter
reading — :attr:`ArmPolicy.max_arms` counts the **total** set, sweep included — so that the
number the operator sets is the number of index lookups the database is asked for. On the
case both statements describe (three levels × four facets) the two readings coincide: twelve
scoped arms and one sweep, thirteen in total, cap untouched.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Final

__all__ = [
    "ARM_POLICY_SCHEMA_VERSION",
    "ArmPolicy",
    "InvalidArmPolicy",
]

#: Bumped when the JSON shape changes in a way an older reader would misread. It is part of
#: the policy digest, so a run recorded under one shape can never be confused with another.
ARM_POLICY_SCHEMA_VERSION: Final = 1

#: The default total bound. Chosen to be small enough that the span count stays far below any
#: plausible ``optimizer_span_limit``, and large enough for three archival levels across the
#: full facet set. It is a policy value, not a law: the deployment sets it.
DEFAULT_MAX_ARMS: Final = 16


class InvalidArmPolicy(ValueError):
    """A policy document that cannot be trusted to produce arms.

    Every parse failure raises this rather than defaulting. A silently defaulted arm weight
    would mean the fusion ranking changed without a policy commit saying so.
    """


def _require(document: Mapping[str, Any], key: str) -> Any:
    if key not in document:
        raise InvalidArmPolicy(
            f"arm policy is missing required key {key!r}. Missing keys are a hard failure, "
            "never a default: a defaulted arm weight is a ranking change nobody signed."
        )
    return document[key]


def _int_keyed(raw: Any, *, what: str) -> dict[int, Any]:
    if not isinstance(raw, Mapping):
        raise InvalidArmPolicy(f"{what} must be an object keyed by archival level, got {raw!r}")
    out: dict[int, Any] = {}
    for key, value in raw.items():
        try:
            level = int(key)
        except (TypeError, ValueError) as exc:
            raise InvalidArmPolicy(f"{what} has a non-integer level key {key!r}") from exc
        out[level] = value
    if not out:
        raise InvalidArmPolicy(f"{what} is empty")
    return out


@dataclass(frozen=True, slots=True)
class ArmPolicy:
    """Graded ``k``, per-arm weight, facet priority, and the total arm bound.

    ``k`` is graded by level because the trees are graded by level: a file-level prefix
    partitions a small K-means tree and a fonds-level prefix a large one, so the same ``k``
    at both levels asks for very different amounts of work and returns evidence of very
    different strength.

    ``facet_priority`` is the deterministic tie-break used when the cap bites and two arms
    carry the same weight. It is supplied by the deployment: this package holds no facet
    vocabulary of its own.
    """

    k_by_level: Mapping[int, int]
    weight_by_level: Mapping[int, float]
    facet_weight: Mapping[str, float]
    facet_priority: tuple[str, ...]
    sweep_k: int
    sweep_weight: float
    max_arms: int = DEFAULT_MAX_ARMS

    def __post_init__(self) -> None:
        if self.max_arms < 1:
            raise InvalidArmPolicy(f"max_arms must be >= 1, got {self.max_arms}")
        for level, k in self.k_by_level.items():
            if k < 1:
                raise InvalidArmPolicy(f"k at level {level} must be >= 1, got {k}")
        for level in self.k_by_level:
            if level not in self.weight_by_level:
                raise InvalidArmPolicy(f"level {level} has a k but no weight")
        if self.sweep_k < 1:
            raise InvalidArmPolicy(f"sweep k must be >= 1, got {self.sweep_k}")
        if len(set(self.facet_priority)) != len(self.facet_priority):
            raise InvalidArmPolicy(f"facet_priority repeats a facet: {self.facet_priority}")

    # ── lookups ──────────────────────────────────────────────────────────────────────────

    def k_for(self, level: int) -> int:
        try:
            return self.k_by_level[level]
        except KeyError as exc:
            raise InvalidArmPolicy(
                f"no k declared for archival level {level}; the policy knows levels "
                f"{sorted(self.k_by_level)}. An undeclared level is a taxonomy change that "
                "never reached the policy, which is exactly the drift this refuses to absorb."
            ) from exc

    def weight_for(self, level: int, facet: str) -> float:
        try:
            level_weight = self.weight_by_level[level]
        except KeyError as exc:
            raise InvalidArmPolicy(f"no weight declared for archival level {level}") from exc
        try:
            facet_weight = self.facet_weight[facet]
        except KeyError as exc:
            raise InvalidArmPolicy(
                f"no weight declared for facet {facet!r}; the policy knows "
                f"{sorted(self.facet_weight)}"
            ) from exc
        # Rounded so that the same policy produces byte-identical arm weights on every
        # machine: the weight is persisted beside a candidate and compared across runs.
        return round(float(level_weight) * float(facet_weight), 6)

    def facet_rank(self, facet: str | None) -> int:
        """Position in the declared priority order; unknown facets sort last, stably."""
        if facet is None:
            return len(self.facet_priority)
        try:
            return self.facet_priority.index(facet)
        except ValueError:
            return len(self.facet_priority)

    @property
    def max_scoped_arms(self) -> int:
        """The scoped budget once the sweep's reserved slot is taken out."""
        return max(0, self.max_arms - 1)

    # ── serialisation ────────────────────────────────────────────────────────────────────

    def as_document(self) -> dict[str, Any]:
        """The canonical JSON shape — what a policy row's ``arms`` column holds."""
        return {
            "schema_version": ARM_POLICY_SCHEMA_VERSION,
            "max_arms": self.max_arms,
            "k_by_level": {str(level): k for level, k in sorted(self.k_by_level.items())},
            "weight_by_level": {
                str(level): weight for level, weight in sorted(self.weight_by_level.items())
            },
            "facet_weight": dict(sorted(self.facet_weight.items())),
            "facet_priority": list(self.facet_priority),
            "sweep": {"k": self.sweep_k, "weight": self.sweep_weight},
        }

    def digest(self) -> str:
        """A stable hex digest of the policy, recorded beside every generated arm set.

        Serialised with sorted keys and no whitespace so the digest depends on the values and
        not on how the document was written.
        """
        body = json.dumps(self.as_document(), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(body.encode("utf-8")).hexdigest()

    @classmethod
    def from_document(cls, document: Mapping[str, Any]) -> ArmPolicy:
        """Parse a policy row's ``arms`` document. Every key is required."""
        version = _require(document, "schema_version")
        if version != ARM_POLICY_SCHEMA_VERSION:
            raise InvalidArmPolicy(
                f"arm policy schema_version is {version!r}, this reader implements "
                f"{ARM_POLICY_SCHEMA_VERSION}. Refusing to guess."
            )
        k_by_level = {
            level: int(value)
            for level, value in _int_keyed(
                _require(document, "k_by_level"), what="k_by_level"
            ).items()
        }
        weight_by_level = {
            level: float(value)
            for level, value in _int_keyed(
                _require(document, "weight_by_level"), what="weight_by_level"
            ).items()
        }
        raw_facet_weight = _require(document, "facet_weight")
        if not isinstance(raw_facet_weight, Mapping) or not raw_facet_weight:
            raise InvalidArmPolicy("facet_weight must be a non-empty object")
        facet_weight = {str(k): float(v) for k, v in raw_facet_weight.items()}
        raw_priority = _require(document, "facet_priority")
        if not isinstance(raw_priority, Sequence) or isinstance(raw_priority, (str, bytes)):
            raise InvalidArmPolicy("facet_priority must be an array of facet names")
        sweep = _require(document, "sweep")
        if not isinstance(sweep, Mapping):
            raise InvalidArmPolicy("sweep must be an object with k and weight")
        return cls(
            k_by_level=k_by_level,
            weight_by_level=weight_by_level,
            facet_weight=facet_weight,
            facet_priority=tuple(str(f) for f in raw_priority),
            sweep_k=int(_require(sweep, "k")),
            sweep_weight=float(_require(sweep, "weight")),
            max_arms=int(_require(document, "max_arms")),
        )

    @classmethod
    def graded(
        cls,
        *,
        facet_priority: Sequence[str],
        k_by_level: Mapping[int, int] | None = None,
        weight_by_level: Mapping[int, float] | None = None,
        facet_weight: Mapping[str, float] | None = None,
        sweep_k: int = 24,
        sweep_weight: float = 0.4,
        max_arms: int = DEFAULT_MAX_ARMS,
    ) -> ArmPolicy:
        """The architecture's stated grading, with the deployment's facet vocabulary.

        ``k`` defaults to the decided values — file 12, series 12, fonds 8 — and the level
        weights encode *"a file-level hit outweighs a fonds-level hit"* as arithmetic rather
        than as a sentence. Facet weights default to 1.0 for every facet the caller declares,
        so that a deployment that has not yet calibrated per-facet weights gets a policy whose
        neutrality is visible rather than one with numbers somebody made up.
        """
        priority = tuple(facet_priority)
        if not priority:
            raise InvalidArmPolicy("facet_priority must name at least one facet")
        return cls(
            k_by_level=dict(k_by_level or {3: 12, 2: 12, 1: 8}),
            weight_by_level=dict(weight_by_level or {3: 1.0, 2: 0.85, 1: 0.6}),
            facet_weight=dict(facet_weight or {facet: 1.0 for facet in priority}),
            facet_priority=priority,
            sweep_k=sweep_k,
            sweep_weight=sweep_weight,
            max_arms=max_arms,
        )
