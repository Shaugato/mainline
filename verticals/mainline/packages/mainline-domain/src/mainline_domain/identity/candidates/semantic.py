# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""S4 — the **anchor-gated** ANN arm.  Cosine proposes; anchors dispose.

Two constraints shape this entire module, and both of them are refusals rather
than features.

**1. The anchor veto runs before the score.**  A semantic candidate at cosine
0.97 whose identity anchors *conflict* with the query is **rejected**, not
down-weighted.  This kills the dominant embedding failure mode — two
structurally identical clauses about different equipment — and it kills it in
the only direction that is safe.  A down-weighted candidate is still in the
pool; W8's assignment can still pick it if nothing better appears; blame still
lands on a clause about a different pump.  A rejected candidate is gone, its
rejection is a recorded row, and the ancestor it would have absorbed stays
unmatched — which is a blocking residue row, which is a louder gate than the
wrong match would ever have been.

The ordering is not a detail.  Because the veto is applied first, no
threshold in :class:`~.thresholds.StageBands` can resurrect a conflicting pair:
there is no number anyone can tune that reaches it.  The unit suite proves this
by construction — a *sub-threshold* conflicting pair is dropped for
``anchor_conflict``, not for ``auto_reject``.

**2. Every arm is fully constrained.**  CockroachDB's documented rule is that a
vector index is used only if *each* prefix column is constrained to a specific
value.  ``mainline.clause_embedding`` declares
``VECTOR INDEX ce_ann (site_id, activity_root, embedding vector_cosine_ops)``,
so an ancestry walk over several ``activity_root`` values is **N separate
single-value ANN queries** ``UNION ALL``'d and re-ranked here — never
``activity_root IN (...)``.

That is a design ruling, not a reading of the docs, and it is worth saying why
it survives the docs having softened: the vendor page now also says multiple
prefix values *may* be filtered with ``IN`` while keeping index acceleration.
"May" is the problem.  The claim this package makes about S4 is that its cost
does not grow with the corpus, and the evidence for that claim is
:mod:`.explain` asserting a ``vector search`` node with non-empty ``prefix
spans`` and no ``FULL SCAN`` — per arm, in CI.  A fan-out of single-value arms
has exactly one possible plan shape.  If the ``IN`` form is ever *measured* to
produce the same plan, adopting it is a small change and a measured one.

**No model call happens here.**  Embeddings arrive from committed fixtures or
from the ingest path; this package holds no SDK and reaches no network
(decision D1 / principle P7).  The ``<=>`` operator in :data:`ARM_SQL` is the
``VECTOR`` cosine-distance operator that pairs with ``vector_cosine_ops`` — it
is unrelated to the *trigram* ``<->`` family, which CockroachDB does not
support and which nothing in this domain uses.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from typing import Final
from uuid import UUID

from mainline_domain.contracts import (
    AnchorClass,
    AnchorSet,
    Candidate,
    PrefixArmRunner,
)

from .records import DroppedCandidate, StageResult, order_candidates
from .thresholds import DEFAULT_BANDS, StageBands

__all__ = [
    "ARM_SQL",
    "Arm",
    "MissingAnchorSetError",
    "arm_union_sql",
    "arms_for",
    "semantic_stage",
    "vector_literal",
]


def vector_literal(q: Sequence[float]) -> str:
    """Render an embedding as the ``'[1.0,2.0]'`` literal CockroachDB parses.

    ``repr`` per component, not ``str``: ``repr`` of a Python float round-trips
    exactly, and a query vector that lost a bit on the way to the server is a
    query vector whose neighbours are not reproducible.
    """
    if not q:
        raise ValueError("cannot build a vector literal from an empty sequence")
    return "[" + ",".join(repr(float(x)) for x in q) + "]"


ARM_SQL: Final[str] = """
SELECT clause_uuid, commit_id, 1 - (embedding <=> %(q)s::VECTOR) AS cosine_similarity
  FROM mainline.clause_embedding
 WHERE site_id = %(site_id)s
   AND activity_root = %(activity_root)s
 ORDER BY embedding <=> %(q)s::VECTOR
 LIMIT %(k)s
""".strip()
"""**One** arm: both prefix columns bound to a specific value.

``<=>`` is cosine distance in ``[0, 2]``; ``1 - distance`` is the cosine
similarity the bands are expressed in.  The ``ORDER BY`` is on the vector
operator, which is what makes it an index-served ANN lookup rather than a sort
over a scan — the thing :mod:`.explain` exists to prove really happened.

**Unverified.**  This statement has not been executed against a CockroachDB
cluster at the time of writing: no cluster is reachable from the build machine
and AWS credentials are not valid.  Its shape follows the documented example
and the ``ce_ann`` declaration in ARCHITECTURE.md §5.3, and
``tests/integration/algorithms/candidates/test_arm_explain_live.py`` asserts
the plan the moment a cluster exists — skipping, loudly and with a reason, when
one does not.
"""


class MissingAnchorSetError(LookupError):
    """An ancestor's anchor set could not be resolved, so the veto cannot be evaluated.

    Raised, never absorbed.  P2: any value a gate reads is *enforced*, never
    trusted, and a trigger that cannot find its authoritative source raises
    rather than defaulting.  The application-side equivalent is this exception:
    a veto that fails open when its input is missing is not a veto, it is a
    comment.
    """


@dataclass(frozen=True, slots=True)
class Arm:
    """One fully-constrained C-SPANN arm: a specific site and a specific activity root."""

    site_id: UUID
    activity_root: str

    def params(self, q: Sequence[float], k: int) -> dict[str, object]:
        """Named parameters for :data:`ARM_SQL`."""
        return {
            "site_id": str(self.site_id),
            "activity_root": self.activity_root,
            "q": vector_literal(q),
            "k": k,
        }


def arms_for(site_id: UUID, activity_roots: Iterable[str]) -> tuple[Arm, ...]:
    """One arm per distinct activity root, in first-appearance order.

    De-duplicated because two identical arms are two identical queries, and
    ordered deterministically because the ``UNION ALL`` this feeds must produce
    the same statement text on every run — a statement that varies by set
    iteration order is a statement whose plan cannot be asserted.

    :raises ValueError: on an empty ``activity_root``.  An empty string is not
        "a specific value"; binding one would satisfy the syntax of the prefix
        rule while defeating its purpose.
    """
    seen: list[str] = []
    for root in activity_roots:
        if not root:
            raise ValueError(
                "activity_root must be a non-empty specific value: a C-SPANN prefix column "
                "that is not constrained to a specific value means the vector index is not used"
            )
        if root not in seen:
            seen.append(root)
    if not seen:
        raise ValueError("at least one activity_root is required; an arm set cannot be empty")
    return tuple(Arm(site_id, root) for root in seen)


def arm_union_sql(n_arms: int) -> str:
    """``n_arms`` fully-constrained ANN queries, ``UNION ALL``'d into one statement.

    Parameters are suffixed per arm (``site_id_0``, ``activity_root_0``, ``q_0``,
    ``k_0``, …) so that no two arms can accidentally share a binding, and so the
    statement text is a pure function of ``n_arms`` and can be asserted by a
    test.

    Re-ranking across arms happens in the application, not in the statement:
    ``ORDER BY`` over the union would force the optimiser to materialise every
    arm before returning anything, and — more importantly — the cross-arm
    ordering this package needs is by *cosine after the anchor veto*, which SQL
    cannot express because the veto is not in the database.
    """
    if n_arms < 1:
        raise ValueError(f"n_arms must be >= 1, got {n_arms}")
    return "\nUNION ALL\n".join(
        f"SELECT clause_uuid, commit_id, "  # noqa: S608 - fixed template, no input
        f"1 - (embedding <=> %(q_{i})s::VECTOR) AS cosine_similarity\n"
        f"  FROM mainline.clause_embedding\n"
        f" WHERE site_id = %(site_id_{i})s\n"
        f"   AND activity_root = %(activity_root_{i})s\n"
        f" ORDER BY embedding <=> %(q_{i})s::VECTOR\n"
        f" LIMIT %(k_{i})s"
        for i in range(n_arms)
    )


def semantic_stage(
    *,
    query_anchors: AnchorSet,
    query_embedding: Sequence[float],
    arms: Sequence[Arm],
    runner: PrefixArmRunner,
    k: int,
    anchors_of: Callable[[UUID, bytes], AnchorSet],
    bands: StageBands = DEFAULT_BANDS,
) -> StageResult:
    """Run the arm set, veto on anchors, then band on cosine.

    :param anchors_of: resolves an ancestor's :class:`AnchorSet` from its
        ``(clause_uuid, commit_id)``.  Anything it raises becomes
        :class:`MissingAnchorSetError`; it must never return an empty set to mean
        "unknown", because an empty set is *compatible with everything* and
        would turn the veto into a no-op for exactly the rows whose anchors the
        system failed to project.
    :param k: per-arm limit.  The arms are independent, so the union can return
        up to ``k * len(arms)`` rows before the veto.

    Duplicate hits across arms are collapsed on ``(clause_uuid, commit_id)``,
    keeping the highest cosine.  A clause version has exactly one
    ``activity_root``, so a duplicate means the caller built two arms for the
    same partition; keeping the max is the conservative resolution and costs
    nothing.
    """
    if k < 1:
        raise ValueError(f"k must be >= 1, got {k}")

    best: dict[tuple[UUID, bytes], Candidate] = {}
    for arm in arms:
        for hit in runner.ann(arm.site_id, arm.activity_root, query_embedding, k):
            key = (hit.ancestor_clause_uuid, hit.ancestor_commit)
            current = best.get(key)
            if current is None or hit.score > current.score:
                best[key] = hit

    kept: list[Candidate] = []
    dropped: list[DroppedCandidate] = []
    for (clause_uuid, commit_id), hit in sorted(
        best.items(), key=lambda kv: (kv[0][0].bytes, kv[0][1])
    ):
        # ---- the veto, before anything looks at the score ----------------
        try:
            ancestor_anchors = anchors_of(clause_uuid, commit_id)
        except Exception as exc:
            raise MissingAnchorSetError(
                f"no anchor set for ancestor clause {clause_uuid} at commit "
                f"{commit_id.hex()}: the S4 veto cannot be evaluated and this stage will "
                f"not fall open"
            ) from exc

        conflicts: frozenset[AnchorClass] = query_anchors.conflicting_classes(ancestor_anchors)
        if conflicts:
            names = ", ".join(sorted(c.value for c in conflicts))
            dropped.append(
                DroppedCandidate(
                    ancestor_clause_uuid=clause_uuid,
                    ancestor_commit=commit_id,
                    stage="S4",
                    reason="anchor_conflict",
                    detail={
                        "cosine": hit.score,
                        "conflicting_class_count": float(len(conflicts)),
                        "query_identity_anchor_count": float(len(query_anchors.identity_norms())),
                        "candidate_identity_anchor_count": float(
                            len(ancestor_anchors.identity_norms())
                        ),
                    },
                    note=(
                        f"rejected, not down-weighted: identity anchors conflict in "
                        f"{names}. The cosine was never consulted"
                    ),
                )
            )
            continue

        # ---- only now is the score allowed to matter ---------------------
        if hit.score < bands.semantic_reject:
            dropped.append(
                DroppedCandidate(
                    ancestor_clause_uuid=clause_uuid,
                    ancestor_commit=commit_id,
                    stage="S4",
                    reason="auto_reject",
                    detail={"cosine": hit.score},
                    note=(
                        f"anchor-compatible but cosine {hit.score:.4f} is below the "
                        f"auto-reject band {bands.semantic_reject}"
                    ),
                )
            )
            continue

        kept.append(
            Candidate(
                ancestor_clause_uuid=clause_uuid,
                ancestor_commit=commit_id,
                stage="S4",
                score=hit.score,
                features={
                    **dict(hit.features),
                    "cosine": hit.score,
                    "anchor_compatible": 1.0,
                },
            )
        )

    return StageResult(stage="S4", candidates=order_candidates(kept), dropped=tuple(dropped))
