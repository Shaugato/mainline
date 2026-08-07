# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""The arm generator.

Given a constant site/tenant token, one or more resolved ancestor chains, and the query
vectors for the facets the exposure cue actually populated, emit the bounded arm set:

* one **fully-constrained** arm per (chain × archival level × populated facet) — every prefix
  column bound to a literal, each arm carrying its own ``k``, its own fusion weight and its
  own facet query vector;
* **exactly one** coarse sweep with only the constant tenant token bound — deliberately one
  big unpartitioned tree, insurance against taxonomy-induction error;
* and, when the cap bites, an :class:`~trappoint_recall.arms.spec.ArmCapExceeded` record
  naming every dropped arm.

The generator never returns fewer arms than it says it returned. Overflow is a record, not a
truncation, because a retrieval that quietly searched less of the corpus than the operator
believes is the precise failure a recall gate exists to make impossible.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Final

from .binding import VectorTable
from .policy import ArmPolicy
from .spec import (
    AncestorChain,
    ArmCapExceeded,
    ArmKind,
    ArmSet,
    ArmSpec,
    DroppedArm,
    PrefixBinding,
    PrefixValue,
    normalise_vector,
)

__all__ = [
    "SCOPED_PREFIX_ARITY",
    "SweepRequest",
    "generate_arm_set",
    "generate_arms",
]

#: A scoped arm binds exactly three prefix columns: the constant site/tenant token, the
#: archival scope, and the facet. Fewer would leave a prefix column unconstrained, which is
#: the documented condition under which the vector index is not used at all.
SCOPED_PREFIX_ARITY: Final = 3


@dataclass(frozen=True, slots=True)
class SweepRequest:
    """The coarse sweep: one constant prefix value, one vector, one table.

    Modelled as an explicit request rather than inferred, because a deployment that has not
    supplied a sweep should see an arm set with no sweep in it and decide what that means —
    not receive one silently synthesised from a value this package guessed.
    """

    tenant: PrefixValue
    query_vector: Sequence[float]
    table: VectorTable

    def __post_init__(self) -> None:
        if self.table.prefix_arity != 1:
            raise ValueError(
                f"the sweep table {self.table.index_ref} declares "
                f"{self.table.prefix_arity} prefix columns. The sweep exists to be ONE "
                "unpartitioned tree; a second prefix column would partition it and it would "
                "stop being insurance against the taxonomy being wrong."
            )


def _arm_id(chain_id: str, level: int, facet: str) -> str:
    return f"{chain_id}:L{level}:{facet}"


def generate_arm_set(
    *,
    site: PrefixValue,
    chains: Sequence[AncestorChain],
    facet_vectors: Mapping[str, Sequence[float]],
    policy: ArmPolicy,
    scoped_table: VectorTable,
    sweep: SweepRequest | None = None,
) -> ArmSet:
    """Emit the bounded arm set for one recall.

    ``facet_vectors`` holds **only** the facets the exposure cue populated. A facet the cue
    could not fill is not a facet with a zero vector: it is a facet with no query, and an arm
    with no query would return the nearest neighbours of nothing in particular and pollute
    the fusion with rank-ordered noise.

    Ordering: arms are emitted in descending fusion weight, then by the policy's facet
    priority, then deepest archival level first, then chain order, then arm id. Every tie is
    broken by a declared value, so two runs of the same policy over the same inputs emit
    byte-identical SQL — which is what makes the plan digest comparable at all.
    """
    if not chains:
        raise ValueError(
            "no ancestor chains were resolved. Channel C cannot be scoped to an ancestry "
            "that was never resolved; the caller must degrade to the deterministic channels "
            "and say so, rather than search everything."
        )
    if scoped_table.prefix_arity != SCOPED_PREFIX_ARITY:
        raise ValueError(
            f"{scoped_table.index_ref} declares {scoped_table.prefix_arity} prefix columns; "
            f"the scoped arm generator binds exactly {SCOPED_PREFIX_ARITY} (site, archival "
            "scope, facet). Change the binding or the index — this package will not guess "
            "which constraint to drop, because dropping one picks a K-means tree on the "
            "caller's behalf, and picking the tree is picking what is reachable."
        )

    vectors = {facet: normalise_vector(values) for facet, values in facet_vectors.items()}
    site_column, scope_column, facet_column = scoped_table.prefix_columns

    candidates: list[ArmSpec] = []
    for chain in chains:
        for scope in chain.scopes:
            k = policy.k_for(scope.level)
            for facet, vector in vectors.items():
                candidates.append(
                    ArmSpec(
                        arm_id=_arm_id(chain.chain_id, scope.level, facet),
                        kind=ArmKind.SCOPED,
                        table=scoped_table,
                        prefix=(
                            PrefixBinding(site_column, site),
                            PrefixBinding(scope_column, scope.scope_id),
                            PrefixBinding(facet_column, facet),
                        ),
                        query_vector=vector,
                        k=k,
                        weight=policy.weight_for(scope.level, facet),
                        level=scope.level,
                        facet=facet,
                        chain_id=chain.chain_id,
                    )
                )

    order = {chain.chain_id: i for i, chain in enumerate(chains)}
    candidates.sort(
        key=lambda arm: (
            -arm.weight,
            policy.facet_rank(arm.facet),
            -arm.level,
            order.get(arm.chain_id or "", len(order)),
            arm.arm_id,
        )
    )

    budget = policy.max_scoped_arms if sweep is not None else policy.max_arms
    kept = tuple(candidates[:budget])
    dropped_specs = candidates[budget:]

    cap_exceeded: ArmCapExceeded | None = None
    if dropped_specs:
        cap_exceeded = ArmCapExceeded(
            cap=policy.max_arms,
            requested=len(candidates) + (1 if sweep is not None else 0),
            emitted=len(kept) + (1 if sweep is not None else 0),
            dropped=tuple(
                DroppedArm(
                    arm_id=arm.arm_id,
                    chain_id=arm.chain_id,
                    level=arm.level,
                    facet=arm.facet,
                    scope_id=_scope_of(arm),
                    weight=arm.weight,
                )
                for arm in dropped_specs
            ),
        )

    sweep_arm: ArmSpec | None = None
    if sweep is not None:
        sweep_arm = ArmSpec(
            arm_id="sweep:L0:coarse",
            kind=ArmKind.COARSE,
            table=sweep.table,
            prefix=(PrefixBinding(sweep.table.prefix_columns[0], sweep.tenant),),
            query_vector=normalise_vector(sweep.query_vector),
            k=policy.sweep_k,
            weight=policy.sweep_weight,
            level=0,
            facet=None,
            chain_id=None,
        )

    return ArmSet(
        scoped=kept,
        sweep=sweep_arm,
        cap_exceeded=cap_exceeded,
        policy_digest=policy.digest(),
    )


def generate_arms(
    *,
    site: PrefixValue,
    chain: AncestorChain,
    facet_vectors: Mapping[str, Sequence[float]],
    policy: ArmPolicy,
    scoped_table: VectorTable,
    sweep: SweepRequest | None = None,
) -> ArmSet:
    """Single-chain convenience form — the shape the gate path uses for one activity node."""
    return generate_arm_set(
        site=site,
        chains=(chain,),
        facet_vectors=facet_vectors,
        policy=policy,
        scoped_table=scoped_table,
        sweep=sweep,
    )


def _scope_of(arm: ArmSpec) -> str | None:
    """The archival scope a scoped arm was bound to, as text, for the overflow record."""
    if arm.table.prefix_arity < 2:
        return None
    value = arm.prefix[1].value
    return str(value)
