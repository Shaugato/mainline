# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
"""One induction run, end to end, emitting a version record.

Order matters and is enforced by the signature: the holdout is split off **before** the
judge sees anything.  A taxonomy induced from the documents it is then confirmed against is
not confirmed, and the mistake is invisible in the resulting numbers — they simply come out
high.  ``run_induction`` therefore takes the whole corpus and does the split itself, rather
than accepting a pre-split pair a caller might have assembled in the wrong order.

The run always emits a :class:`~mainline_recall_agent.taxonomy.versioning.TaxonomyVersion`,
even when the diff is empty.  A re-induction that changed nothing is a fact worth having on
the record, because the next question after *"why did this permit stop blocking"* is *"what
ran, and when".*
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from mainline_recall_agent.providers.types import JudgeProvider

from .classifier import TaxonomyClassifier
from .holdout import DEFAULT_HOLDOUT_SIZE, HoldoutReport, holdout_split, score_holdout
from .induction import (
    InductionConfig,
    InductionDocument,
    MergeOutcome,
    ProposalPool,
    SnapshotBuild,
    assign_leaves,
    build_snapshot,
    merge_and_refine,
    propose_labels,
)
from .models import TaxonomySnapshot
from .prompts import INDUCTION_PROMPT_VERSION, build_induction_prefix
from .register import Level1Register
from .versioning import TaxonomyVersion, emit_version

__all__ = ["InductionRun", "run_induction"]


@dataclass(frozen=True, slots=True)
class InductionRun:
    """Everything one run produced, in the order a reader would want it."""

    version: TaxonomyVersion
    snapshot: TaxonomySnapshot
    build: SnapshotBuild
    classifier: TaxonomyClassifier
    pool: ProposalPool
    merge: MergeOutcome
    holdout: HoldoutReport | None
    train_doc_ids: tuple[str, ...]
    holdout_doc_ids: tuple[str, ...]
    assignments: Mapping[str, str]

    @property
    def accepted(self) -> bool:
        """False when there is no holdout: an unconfirmed taxonomy is not an accepted one."""
        return bool(self.holdout and self.holdout.accepted)


def run_induction(
    *,
    documents: Sequence[InductionDocument],
    register: Level1Register,
    judge: JudgeProvider,
    site_id: str,
    taxonomy_ver: int,
    parent: TaxonomySnapshot | None = None,
    parent_assignments: Mapping[str, str] | None = None,
    config: InductionConfig | None = None,
    holdout_size: int = DEFAULT_HOLDOUT_SIZE,
    split_policy_id: str = "taxonomy-holdout-sha256",
    corpus_provenance: str = "unstated",
    induced_at: datetime | None = None,
    gate_on: str = "lower",
    notes: str = "",
) -> InductionRun:
    """Split, induct, merge, fit, confirm, and emit the version record."""
    cfg = config or InductionConfig()
    prefix = build_induction_prefix(register)

    train_ids, holdout_ids = holdout_split(
        [document.doc_id for document in documents], holdout_size
    )
    by_id = {document.doc_id: document for document in documents}
    train = [by_id[doc_id] for doc_id in train_ids]
    held = [by_id[doc_id] for doc_id in holdout_ids]

    pool = propose_labels(
        judge=judge, prefix=prefix, documents=train, register=register, config=cfg
    )
    merged = merge_and_refine(judge=judge, prefix=prefix, pool=pool, config=cfg)
    build = build_snapshot(
        register=register,
        groups=merged.groups,
        site_id=site_id,
        taxonomy_ver=taxonomy_ver,
    )
    assignments = assign_leaves(pool, build)

    labelled = [(by_id[doc_id], scope) for doc_id, scope in sorted(assignments.items())]
    scope_labels = {node.scope_id: node.label for node in build.snapshot.nodes}
    classifier = TaxonomyClassifier.fit(
        texts=[document.text for document, _ in labelled],
        scopes=[scope for _, scope in labelled],
        labels=scope_labels,
    )

    holdout: HoldoutReport | None = None
    if held:
        holdout = score_holdout(
            build=build,
            classifier=classifier,
            documents=held,
            split_policy_id=split_policy_id,
            corpus_provenance=corpus_provenance,
            gate_on=gate_on,
        )

    identity = judge.resolved_model
    version = emit_version(
        taxonomy_ver=taxonomy_ver,
        site_id=site_id,
        parent=parent,
        snapshot=build.snapshot,
        induced_at=induced_at or datetime.now(UTC),
        model=identity.profile_id,
        model_is_semantic=bool(getattr(judge, "is_semantic", True)),
        prompt_version=INDUCTION_PROMPT_VERSION,
        register_id=register.register_id,
        register_sha256=register.sha256,
        config=_config_body(cfg, holdout_size, split_policy_id, corpus_provenance),
        before_assignments=parent_assignments,
        after_assignments=assignments,
        holdout=holdout.to_dict() if holdout else None,
        classifier_digest=classifier.digest(),
        rejection_counts=pool.rejection_counts(),
        rejected_labels=tuple(rejection.to_dict() for rejection in pool.rejections[:200]),
        abstained_documents=len(pool.abstained),
        failed_batches=pool.failed_batches,
        dropped_groups=build.dropped_groups,
        merge_rounds=merged.rounds,
        merge_converged=merged.converged,
        merge_fell_back=merged.fell_back,
        notes=notes,
    )
    return InductionRun(
        version=version,
        snapshot=build.snapshot,
        build=build,
        classifier=classifier,
        pool=pool,
        merge=merged,
        holdout=holdout,
        train_doc_ids=train_ids,
        holdout_doc_ids=holdout_ids,
        assignments=assignments,
    )


def _config_body(
    cfg: InductionConfig, holdout_size: int, split_policy_id: str, provenance: str
) -> dict[str, Any]:
    body = cfg.to_dict()
    body.update(
        {
            "holdout_size": holdout_size,
            "split_policy_id": split_policy_id,
            "corpus_provenance": provenance,
        }
    )
    return body
