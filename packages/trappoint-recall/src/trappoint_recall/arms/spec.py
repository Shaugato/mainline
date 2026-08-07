# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""The value objects an arm set is made of.

An **arm** is one fully-constrained approximate-nearest-neighbour query: every prefix column
bound to a literal, its own ``k``, its own fusion weight, its own query vector. An **arm set**
is the ``UNION ALL`` of those arms plus exactly one coarse sweep, and it is bounded — because
an unbounded arm set is how a system walks off ``optimizer_span_limit`` and degrades to a
scan that nobody is watching.

Overflow is never a silent drop. It is an :class:`ArmCapExceeded` record, carried on the arm
set, which the caller writes to its silence ledger with the arithmetic that produced it.
"""

from __future__ import annotations

import math
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import Enum
from typing import Any, ClassVar

from .binding import VectorTable

__all__ = [
    "AncestorChain",
    "ArmCapExceeded",
    "ArmKind",
    "ArmSet",
    "ArmSpec",
    "DroppedArm",
    "PrefixBinding",
    "PrefixValue",
    "ScopeRef",
    "SqlForm",
]

#: A prefix value is a UUID or a short token. Both are rendered as literals; nothing else is
#: accepted, because a prefix value that cannot be rendered as a literal cannot constrain the
#: index and would silently become a scan.
PrefixValue = uuid.UUID | str


class ArmKind(str, Enum):
    """Scoped arms are taxonomy-constrained; there is exactly one coarse arm, ever."""

    SCOPED = "scoped"
    COARSE = "coarse"


class SqlForm(str, Enum):
    """Three renderings of the same arm, for three different jobs.

    ``EXECUTE`` is the shape that runs on the hot path: the query vector is a **placeholder**
    bound by the driver, so a 1024-dimension vector costs a few bytes of statement text
    instead of ten kilobytes of it.

    ``LITERAL`` is the same statement with the vector inlined. It exists because ``EXPLAIN``
    over a public endpoint has no parameter-binding channel.

    ``EXPLAIN_MCP`` is ``LITERAL`` with the projected distance expression removed, so the
    vector literal appears **once** rather than twice. That halving is what keeps a
    1024-dimension arm inside the Managed MCP 16 384-character statement cap with measured
    headroom. The elision is only legitimate because the two forms are proven to produce the
    same plan skeleton and the same plan digest — an assertion, not an assumption; see
    ``tests/integration/recall_index/test_ix02_plan_pgwire.py``.
    """

    EXECUTE = "execute"
    LITERAL = "literal"
    EXPLAIN_MCP = "explain_mcp"


@dataclass(frozen=True, slots=True)
class PrefixBinding:
    """One prefix column bound to one specific value. There is no other legal shape.

    A range, an inequality or an unbound column means the vector index is not used at all —
    which in a recall gate is not a performance regression but an unreachable precursor.
    """

    column: str
    value: PrefixValue


@dataclass(frozen=True, slots=True)
class ScopeRef:
    """One archival level of one ancestor chain: a level number and the scope it names."""

    level: int
    scope_id: uuid.UUID

    def __post_init__(self) -> None:
        if self.level < 0:
            raise ValueError(f"level must be non-negative, got {self.level}")


@dataclass(frozen=True, slots=True)
class AncestorChain:
    """The resolved ancestors of one subject, deepest level first.

    ``chain_id`` is the caller's own stable name for the chain (an activity node id, a permit
    slice id) and appears in every generated ``arm_id``, so that a dropped arm can be traced
    back to the subject it would have covered.
    """

    chain_id: str
    scopes: tuple[ScopeRef, ...]

    def __post_init__(self) -> None:
        if not self.chain_id:
            raise ValueError("chain_id must be non-empty: it names the dropped arm's subject")
        if not self.scopes:
            raise ValueError(f"ancestor chain {self.chain_id!r} is empty")
        levels = [s.level for s in self.scopes]
        if len(set(levels)) != len(levels):
            raise ValueError(
                f"ancestor chain {self.chain_id!r} repeats a level ({levels}). One cue row "
                "per archival level is the whole point of the level-materialised bond; two "
                "rows at one level would mean two arms searching the same K-means tree."
            )

    @classmethod
    def of(cls, chain_id: str, scopes: Mapping[int, uuid.UUID]) -> AncestorChain:
        """Build from ``{level: scope_id}``, deepest level first."""
        ordered = tuple(
            ScopeRef(level=level, scope_id=scopes[level]) for level in sorted(scopes, reverse=True)
        )
        return cls(chain_id=chain_id, scopes=ordered)

    @property
    def max_level(self) -> int:
        return max(s.level for s in self.scopes)


@dataclass(frozen=True, slots=True)
class ArmSpec:
    """One fully-constrained arm, ready to render.

    ``query_vector`` is held as a tuple of floats rather than a rendered string so that the
    same arm can be rendered as a placeholder statement for execution and as a literal
    statement for ``EXPLAIN`` without two sources of truth for the numbers.
    """

    arm_id: str
    kind: ArmKind
    table: VectorTable
    prefix: tuple[PrefixBinding, ...]
    query_vector: tuple[float, ...]
    k: int
    weight: float
    level: int
    facet: str | None
    chain_id: str | None

    def __post_init__(self) -> None:
        if len(self.prefix) != self.table.prefix_arity:
            raise ValueError(
                f"arm {self.arm_id!r} binds {len(self.prefix)} prefix columns but "
                f"{self.table.index_ref} has {self.table.prefix_arity}. Every prefix column "
                "must be constrained to a specific value or the index is not used."
            )
        for binding, column in zip(self.prefix, self.table.prefix_columns, strict=True):
            if binding.column != column:
                raise ValueError(
                    f"arm {self.arm_id!r} binds prefix column {binding.column!r} where the "
                    f"index declares {column!r}; prefix order is part of the index, not a "
                    "presentation choice."
                )
        if len(self.query_vector) != self.table.dimensions:
            raise ValueError(
                f"arm {self.arm_id!r} carries a {len(self.query_vector)}-dimension vector "
                f"against a {self.table.dimensions}-dimension column"
            )
        if self.k < 1:
            raise ValueError(f"arm {self.arm_id!r} has k={self.k}; k must be >= 1")

    @property
    def prefix_values(self) -> tuple[PrefixValue, ...]:
        return tuple(b.value for b in self.prefix)


@dataclass(frozen=True, slots=True)
class DroppedArm:
    """An arm the cap refused to emit. Every field exists to make the drop attributable."""

    arm_id: str
    chain_id: str | None
    level: int
    facet: str | None
    scope_id: str | None
    weight: float

    def as_dict(self) -> dict[str, Any]:
        return {
            "arm_id": self.arm_id,
            "chain_id": self.chain_id,
            "level": self.level,
            "facet": self.facet,
            "scope_id": self.scope_id,
            "weight": self.weight,
        }


@dataclass(frozen=True, slots=True)
class ArmCapExceeded:
    """The record a caller must write when the arm cap bites.

    This type deliberately carries no ledger vocabulary and no table names: the substrate
    states *what happened and by how much*, and the deployment decides which of its own rows
    that becomes. :meth:`arithmetic` is the JSON-able body; :attr:`reason` is the single
    string a deployment is expected to reuse as its ledger reason code.
    """

    cap: int
    requested: int
    emitted: int
    dropped: tuple[DroppedArm, ...]

    #: The one string a deployment is expected to reuse as its ledger reason code. A class
    #: variable, not a field: it is a fact about this type, not a value a caller may set.
    reason: ClassVar[str] = "cap_exceeded"

    def arithmetic(self) -> dict[str, Any]:
        """Everything needed to re-derive the drop from the policy, and nothing else."""
        return {
            "reason": self.reason,
            "cap": self.cap,
            "requested": self.requested,
            "emitted": self.emitted,
            "dropped_count": len(self.dropped),
            "dropped": [d.as_dict() for d in self.dropped],
        }


@dataclass(frozen=True, slots=True)
class ArmSet:
    """The generated arm set: scoped arms, at most one sweep, and the overflow record.

    The sweep is not one of the scoped arms and is never dropped by the cap. It is the
    insurance against taxonomy-induction error — the arm that finds an event the taxonomy
    filed in the wrong tree — so a cap that could delete it would delete the one arm whose
    job is to cover the failure of all the others.
    """

    scoped: tuple[ArmSpec, ...]
    sweep: ArmSpec | None
    cap_exceeded: ArmCapExceeded | None
    policy_digest: str

    @property
    def arms(self) -> tuple[ArmSpec, ...]:
        return self.scoped if self.sweep is None else (*self.scoped, self.sweep)

    @property
    def degraded(self) -> bool:
        """True when the cap dropped at least one arm — the caller's ``arms_degraded``."""
        return self.cap_exceeded is not None

    @property
    def arm_ids(self) -> tuple[str, ...]:
        return tuple(a.arm_id for a in self.arms)

    def by_id(self, arm_id: str) -> ArmSpec:
        for arm in self.arms:
            if arm.arm_id == arm_id:
                return arm
        raise KeyError(arm_id)

    def tables(self) -> tuple[VectorTable, ...]:
        seen: list[VectorTable] = []
        for arm in self.arms:
            if arm.table not in seen:
                seen.append(arm.table)
        return tuple(seen)

    def __len__(self) -> int:
        return len(self.arms)


def as_uuid(value: PrefixValue) -> uuid.UUID:
    """Parse strictly. A prefix value that is not a real UUID must fail here, not in SQL."""
    if isinstance(value, uuid.UUID):
        return value
    return uuid.UUID(str(value))


def normalise_vector(values: Sequence[float]) -> tuple[float, ...]:
    """Coerce to a tuple of finite floats; refuse NaN and infinity.

    A non-finite coordinate does not raise in most embedding pipelines — it silently makes
    every distance ``NaN``, which sorts unpredictably and returns an arbitrary top-k. That
    failure is indistinguishable from "the corpus held nothing relevant", which is the exact
    failure this domain exists to refuse.
    """
    out: list[float] = []
    for i, raw in enumerate(values):
        coordinate = float(raw)
        if not math.isfinite(coordinate):
            raise ValueError(
                f"query vector coordinate {i} is {raw!r}; a non-finite coordinate makes every "
                "distance NaN and turns an empty result into an unattributable silence"
            )
        out.append(coordinate)
    return tuple(out)
