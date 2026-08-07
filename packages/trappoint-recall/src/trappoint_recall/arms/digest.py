# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""``index_plan_digest`` — a stable hash of *the shape of the plan that actually ran*.

A recall receipt records which plan the database chose, because the honest claim about an
approximate index is not *"the search was exhaustive"* but *"this is the structure that was
searched, and here is a hash by which you can tell whether it later changed"*.

**What is in the skeleton: node types and index names. Nothing else.**

Excluded, deliberately:

``estimated row count`` / ``rows read``
    Statistics move on their own. A digest that changed every time the table grew would tell
    an auditor nothing and would be dismissed the first time it changed for no reason.

``spans`` / ``prefix spans``
    They contain the literal prefix values, so they are different for every permit. A digest
    that differs per subject cannot answer *"did the plan change between these two runs?"*,
    which is the only question it exists to answer. The spans are asserted **non-empty** by
    :mod:`trappoint_recall.arms.explain`; they are simply not hashed.

``target count`` / ``distribution`` / ``vectorized``
    Execution parameters, not plan structure. ``target count`` follows ``k``, which is policy
    and is already recorded in the policy digest.

The digest is domain-separated and versioned. A digest with no domain tag is a hash that can
be confused with any other sha256 in the same record, and the separator costs one line.
"""

from __future__ import annotations

import hashlib
from collections.abc import Sequence
from typing import Final

from .explain import ExplainPlan, PlanNode

__all__ = [
    "PLAN_DIGEST_DOMAIN",
    "index_plan_digest",
    "plan_skeleton",
    "skeleton_text",
]

#: Domain separator and version tag. Changing the skeleton's contents REQUIRES bumping this,
#: because two different skeleton definitions that hash to different values must not look
#: like two different plans.
PLAN_DIGEST_DOMAIN: Final = b"trappoint-recall/index-plan-skeleton/v1\n"

#: Separates plans within a multi-arm digest. A byte that cannot appear in a skeleton line.
_PLAN_SEPARATOR: Final = "\x1e"


def _node_line(node: PlanNode) -> str:
    ref = node.table_ref or ""
    return f"{node.depth}\t{node.node_type}\t{ref}"


def plan_skeleton(plan: ExplainPlan) -> tuple[str, ...]:
    """The normalised skeleton of one plan: ``depth<TAB>node type<TAB>table@index``.

    Order is the plan's printed order, which is the optimizer's own tree order and therefore
    part of the structure being attested.
    """
    return tuple(_node_line(node) for node in plan.nodes)


def skeleton_text(plans: Sequence[ExplainPlan]) -> str:
    """The exact text that gets hashed — exposed so a stranger can re-derive the digest."""
    return _PLAN_SEPARATOR.join("\n".join(plan_skeleton(plan)) for plan in plans)


def index_plan_digest(plans: ExplainPlan | Sequence[ExplainPlan]) -> bytes:
    """sha256 over the domain tag and the normalised skeleton, for the run receipt.

    Accepts one plan or a sequence of them: a run that asserted its arms one at a time over a
    capped endpoint has one plan per arm, and its digest must cover all of them in emission
    order — otherwise an arm could be dropped from the proof without the digest moving.
    """
    sequence = (plans,) if isinstance(plans, ExplainPlan) else tuple(plans)
    if not sequence:
        raise ValueError(
            "refusing to digest an empty plan set: a receipt that attests to no plan at all "
            "would still produce a hash, and a hash of nothing is worse than no hash"
        )
    body = skeleton_text(sequence).encode("utf-8")
    return hashlib.sha256(PLAN_DIGEST_DOMAIN + body).digest()
