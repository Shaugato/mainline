# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
"""TnT-LLM's two phases, with level 1 held frozen underneath them.

``arXiv:2403.12173`` (TnT-LLM) proposes taxonomies in two phases: generate per-document
labels over a sample, then iteratively merge and refine them into a taxonomy, and only then
bulk-assign the full corpus with a cheap classifier.  MAINLINE adopts the shape and pins one
end of it: **level 1 never moves**.  Levels 2 and 3 are induced here; level 1 comes from the
buyer's Material Unwanted Event register and is refused if it is anything else
(:mod:`~mainline_recall_agent.taxonomy.register`).

Three properties of this module are load-bearing rather than incidental.

**Every proposed label goes through the validator, and rejections are counted.**  A model
that returns things instead of functions must not quietly have its survivors kept: that
publishes a taxonomy shaped by the validator rather than by the corpus.  When the rejection
rate crosses :attr:`InductionConfig.max_rejection_rate` the run raises, because the fix is a
prompt, not a filter.

**A judge failure is degradation, never silence.**  A batch the model refuses or
dead-letters is recorded as a failed batch and the run continues with the rest; a refused
*merge* falls back to the deterministic clustering in
:mod:`~mainline_recall_agent.taxonomy.merge`.  Both facts land on the version record.  The
alternative — an exception that aborts the induction — costs the whole taxonomy for one bad
response, and the alternative to *that* — pretending the batch was empty — is how a silent
extraction failure becomes a silent memory gap.

**Off-register level-1 answers are refused, not repaired.**  The register is in the cached
system prefix and the model is told never to invent a code.  When it does anyway, the
proposal is dropped with reason ``off_register``.  Mapping it to the nearest code would put
an incident in a K-means tree chosen by a similarity function nobody reviewed.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Final, cast

from mainline_recall_agent.providers.errors import ProviderError
from mainline_recall_agent.providers.system_blocks import SystemPrefix
from mainline_recall_agent.providers.types import JudgeProvider

from .errors import InductionQualityError
from .labels import check_label, normalise_label
from .merge import DEFAULT_MIN_SUPPORT, DEFAULT_SIMILARITY, LabelCandidate, cluster_labels
from .models import (
    LEVEL_FILE,
    LEVEL_FONDS,
    LEVEL_SERIES,
    ActivityNode,
    TaxonomySnapshot,
    derive_scope_id,
)
from .register import Level1Register
from .schemas import LabelProposalBatch, MergeDecision, MergeGroup

__all__ = [
    "InductionConfig",
    "InductionDocument",
    "MergeOutcome",
    "Proposal",
    "ProposalPool",
    "Rejection",
    "SnapshotBuild",
    "assign_leaves",
    "build_snapshot",
    "merge_and_refine",
    "propose_labels",
]

#: ``research/05-architecture/diachronic-recall.md`` §3: "sample ~2k narratives".
DEFAULT_SAMPLE_SIZE: Final[int] = 2000


def _system_argument(prefix: SystemPrefix) -> Sequence[Any]:
    """Hand the judge the prefix object, typed to match the Protocol.

    ``JudgeProvider.judge`` declares ``system_blocks: Sequence[Any]``, but the shipped
    implementation (``BedrockClaudeJudge``) *refuses* a raw sequence on purpose: passing a
    bare list would bypass the stability contract that makes the cache breakpoint real.
    So the value that must be passed is the ``SystemPrefix`` itself, and the cast records
    that the Protocol's annotation is looser than its only implementation.  Narrowing the
    Protocol is the providers worker's change to make, not this module's.
    """
    return cast(Sequence[Any], prefix)


@dataclass(frozen=True, slots=True)
class InductionDocument:
    """One narrative, plus the human confirmation labels when the corpus carries them.

    The ``truth_*`` fields are **never** shown to the judge.  They exist for the holdout
    confirmation in :mod:`~mainline_recall_agent.taxonomy.holdout`, and
    :func:`propose_labels` sends only ``doc_id``, ``title`` and ``narrative``.
    """

    doc_id: str
    title: str
    narrative: str
    truth_activity_root: str = ""
    truth_series: str = ""
    truth_file: str = ""

    def wire(self) -> dict[str, str]:
        return {"doc_id": self.doc_id, "title": self.title, "narrative": self.narrative}

    @property
    def text(self) -> str:
        return f"{self.title}\n{self.narrative}"


@dataclass(frozen=True, slots=True)
class InductionConfig:
    """Everything about a run that a reader would need in order to reproduce it."""

    sample_size: int = DEFAULT_SAMPLE_SIZE
    batch_size: int = 25
    max_merge_rounds: int = 3
    min_support: int = DEFAULT_MIN_SUPPORT
    similarity_threshold: float = DEFAULT_SIMILARITY
    max_rejection_rate: float = 0.25

    def to_dict(self) -> dict[str, Any]:
        return {
            "sample_size": self.sample_size,
            "batch_size": self.batch_size,
            "max_merge_rounds": self.max_merge_rounds,
            "min_support": self.min_support,
            "similarity_threshold": self.similarity_threshold,
            "max_rejection_rate": self.max_rejection_rate,
        }


@dataclass(frozen=True, slots=True)
class Rejection:
    """One proposed label the validator refused, with the reason code."""

    doc_id: str
    level: int
    label: str
    reason: str
    detail: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "doc_id": self.doc_id,
            "level": self.level,
            "label": self.label,
            "reason": self.reason,
            "detail": self.detail,
        }


@dataclass(frozen=True, slots=True)
class Proposal:
    """One document's surviving phase-1 placement."""

    doc_id: str
    activity_root: str
    series_label: str
    file_label: str
    confidence: float = 1.0


@dataclass(frozen=True, slots=True)
class ProposalPool:
    """Phase-1 output, including everything that did not survive it."""

    proposals: tuple[Proposal, ...]
    rejections: tuple[Rejection, ...] = ()
    abstained: tuple[str, ...] = ()
    failed_batches: tuple[str, ...] = ()
    n_documents: int = 0

    @property
    def rejection_rate(self) -> float:
        considered = len(self.proposals) + len(self.rejections)
        return len(self.rejections) / considered if considered else 0.0

    def rejection_counts(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for rejection in self.rejections:
            counts[rejection.reason] = counts.get(rejection.reason, 0) + 1
        return dict(sorted(counts.items()))

    def candidates(self) -> list[LabelCandidate]:
        """The phase-2 input: every proposed label with the support behind it."""
        series: dict[tuple[str, str], int] = {}
        files: dict[tuple[str, str, str], int] = {}
        for proposal in self.proposals:
            key2 = (proposal.activity_root, proposal.series_label)
            series[key2] = series.get(key2, 0) + 1
            key3 = (proposal.activity_root, proposal.series_label, proposal.file_label)
            files[key3] = files.get(key3, 0) + 1
        out = [
            LabelCandidate(
                level=LEVEL_SERIES,
                activity_root=root,
                parent_label=None,
                label=label,
                support=support,
            )
            for (root, label), support in sorted(series.items())
        ]
        out.extend(
            LabelCandidate(
                level=LEVEL_FILE,
                activity_root=root,
                parent_label=parent,
                label=label,
                support=support,
            )
            for (root, parent, label), support in sorted(files.items())
        )
        return out


@dataclass(frozen=True, slots=True)
class MergeOutcome:
    """Phase-2 output plus how it was reached."""

    groups: tuple[MergeGroup, ...]
    rounds: int
    converged: bool
    fell_back: bool = False
    fallback_reason: str = ""


@dataclass(frozen=True, slots=True)
class SnapshotBuild:
    """A snapshot, the label index that assigns documents to it, and what was dropped."""

    snapshot: TaxonomySnapshot
    leaf_index: Mapping[tuple[str, str], str] = field(default_factory=dict)
    series_index: Mapping[tuple[str, str], str] = field(default_factory=dict)
    dropped_groups: tuple[str, ...] = ()


def _batched(items: Sequence[InductionDocument], size: int) -> Iterable[
    tuple[InductionDocument, ...]
]:
    for start in range(0, len(items), size):
        yield tuple(items[start : start + size])


def _sample(documents: Sequence[InductionDocument], size: int) -> tuple[
    InductionDocument, ...
]:
    """Take the first ``size`` documents in the caller's order.

    Not a random sample.  The caller owns the split policy — the harness's
    ``SplitPolicy`` decides what may be looked at and when — and a second, private RNG
    inside the induction would silently make the sample irreproducible and, worse, could
    draw a document from the wrong side of a time wall.
    """
    return tuple(documents[: max(size, 0)])


def propose_labels(
    *,
    judge: JudgeProvider,
    prefix: SystemPrefix,
    documents: Sequence[InductionDocument],
    register: Level1Register,
    config: InductionConfig | None = None,
) -> ProposalPool:
    """Phase 1: per-document activity labels, validated on the way back."""
    cfg = config or InductionConfig()
    sampled = _sample(documents, cfg.sample_size)
    proposals: list[Proposal] = []
    rejections: list[Rejection] = []
    abstained: list[str] = []
    failed: list[str] = []

    for index, batch in enumerate(_batched(sampled, max(cfg.batch_size, 1))):
        payload: dict[str, Any] = {
            "phase": "propose",
            "naming_rule": "a label names a function performed",
            "documents": [document.wire() for document in batch],
        }
        try:
            answer = judge.judge(_system_argument(prefix), payload, LabelProposalBatch)
        except ProviderError as exc:
            # Refusal, truncation, dead letter or an unavailable provider. The batch is
            # lost; the run is not. Which batch, and why, is on the version record.
            failed.append(f"batch {index}: {type(exc).__name__}: {exc.message}")
            continue
        for label in answer.labels:
            if label.insufficient_evidence:
                abstained.append(label.doc_id)
                continue
            if not register.contains(label.activity_root):
                rejections.append(
                    Rejection(
                        doc_id=label.doc_id,
                        level=LEVEL_FONDS,
                        label=label.activity_root,
                        reason="off_register",
                        detail=(
                            "level 1 is frozen to the buyer's register; an invented code "
                            "is a K-means tree nobody will search"
                        ),
                    )
                )
                continue
            series_verdict = check_label(label.series_label)
            if not series_verdict.ok:
                rejections.append(
                    Rejection(
                        doc_id=label.doc_id,
                        level=LEVEL_SERIES,
                        label=label.series_label,
                        reason=series_verdict.reason or "unknown",
                        detail=series_verdict.detail or "",
                    )
                )
                continue
            file_verdict = check_label(label.file_label)
            if not file_verdict.ok:
                rejections.append(
                    Rejection(
                        doc_id=label.doc_id,
                        level=LEVEL_FILE,
                        label=label.file_label,
                        reason=file_verdict.reason or "unknown",
                        detail=file_verdict.detail or "",
                    )
                )
                continue
            proposals.append(
                Proposal(
                    doc_id=label.doc_id,
                    activity_root=label.activity_root,
                    series_label=normalise_label(label.series_label),
                    file_label=normalise_label(label.file_label),
                    confidence=label.confidence,
                )
            )

    pool = ProposalPool(
        proposals=tuple(proposals),
        rejections=tuple(rejections),
        abstained=tuple(abstained),
        failed_batches=tuple(failed),
        n_documents=len(sampled),
    )
    if not pool.proposals:
        raise InductionQualityError(
            "phase 1 produced no surviving label proposals; there is nothing to induct a "
            "taxonomy from and an empty level 2/3 would leave every cue filed at the fonds",
            n_documents=len(sampled),
            rejected=len(rejections),
            abstained=len(abstained),
            failed_batches=len(failed),
        )
    if pool.rejection_rate > cfg.max_rejection_rate:
        raise InductionQualityError(
            "too many proposed labels failed the functional-label validator; keeping the "
            "survivors would publish a taxonomy shaped by the validator rather than by the "
            "corpus, so the prompt is the thing to fix",
            rejection_rate=round(pool.rejection_rate, 4),
            ceiling=cfg.max_rejection_rate,
            by_reason=pool.rejection_counts(),
        )
    return pool


def _groups_key(groups: Sequence[MergeGroup]) -> tuple[tuple[int, str, str, str], ...]:
    return tuple(
        sorted(
            (g.level, g.activity_root, g.parent_label or "", g.canonical_label)
            for g in groups
        )
    )


def merge_and_refine(
    *,
    judge: JudgeProvider,
    prefix: SystemPrefix,
    pool: ProposalPool,
    config: InductionConfig | None = None,
) -> MergeOutcome:
    """Phase 2: fold near-duplicates, iterate to a fixed point, then stop.

    Iteration is capped and the cap is reported.  A merge that has not converged is not an
    error — taxonomies genuinely oscillate between two near-equivalent groupings — but a
    caller that freezes a non-converged taxonomy should know it did, so ``converged`` is a
    field rather than a log line.
    """
    cfg = config or InductionConfig()
    candidates = pool.candidates()
    previous: tuple[tuple[int, str, str, str], ...] | None = None
    groups: list[MergeGroup] = []
    fell_back = False
    reason = ""
    rounds = 0
    # Membership has to accumulate across rounds. Round two sees only round one's canonical
    # wordings, so a group it forms lists those as its members and the *original* proposed
    # labels vanish -- and with them every document that was proposed under one, which then
    # falls back to its series and trains a class that should not exist. That bug is
    # invisible in the taxonomy and shows up only as file-level holdout accuracy, which is
    # why the expansion below is carried explicitly rather than recomputed.
    expansion: dict[tuple[int, str, str], frozenset[str]] = {
        (c.level, c.activity_root, c.label): frozenset({c.label}) for c in candidates
    }

    for _ in range(max(cfg.max_merge_rounds, 1)):
        rounds += 1
        payload: dict[str, Any] = {
            "phase": "merge",
            "min_support": cfg.min_support,
            "similarity_threshold": cfg.similarity_threshold,
            "candidates": [
                {
                    "level": candidate.level,
                    "activity_root": candidate.activity_root,
                    "parent_label": candidate.parent_label,
                    "label": candidate.label,
                    "support": candidate.support,
                }
                for candidate in candidates
            ],
        }
        try:
            decision: MergeDecision = judge.judge(
                _system_argument(prefix), payload, MergeDecision
            )
            groups = list(decision.groups)
        except ProviderError as exc:
            fell_back = True
            reason = f"{type(exc).__name__}: {exc.message}"
            groups = cluster_labels(
                candidates,
                min_support=cfg.min_support,
                threshold=cfg.similarity_threshold,
            )
        groups, expansion = _expand_members(_validated_groups(groups), expansion)
        key = _groups_key(groups)
        if key == previous:
            return MergeOutcome(
                groups=tuple(groups),
                rounds=rounds,
                converged=True,
                fell_back=fell_back,
                fallback_reason=reason,
            )
        previous = key
        candidates = [
            LabelCandidate(
                level=group.level,
                activity_root=group.activity_root,
                parent_label=group.parent_label,
                label=group.canonical_label,
                support=group.support,
            )
            for group in groups
        ]

    return MergeOutcome(
        groups=tuple(groups),
        rounds=rounds,
        converged=False,
        fell_back=fell_back,
        fallback_reason=reason,
    )


def _expand_members(
    groups: Sequence[MergeGroup], expansion: Mapping[tuple[int, str, str], frozenset[str]]
) -> tuple[list[MergeGroup], dict[tuple[int, str, str], frozenset[str]]]:
    """Rewrite each group's members to the original proposed labels behind them.

    Keyed by ``(level, activity_root, label)`` rather than by the parent as well: the parent
    wording is exactly what a later round may re-canonicalise, so including it would make
    the key unstable across the very rounds this map exists to survive.
    """
    expanded: list[MergeGroup] = []
    carried: dict[tuple[int, str, str], frozenset[str]] = {}
    for group in groups:
        members: set[str] = {group.canonical_label}
        for member in group.members:
            members |= expansion.get((group.level, group.activity_root, member), {member})
        rewritten = group.model_copy(update={"members": sorted(members)})
        expanded.append(rewritten)
        carried[(group.level, group.activity_root, group.canonical_label)] = frozenset(members)
    return expanded, carried


def _validated_groups(groups: Sequence[MergeGroup]) -> list[MergeGroup]:
    """Drop any group whose canonical wording is not a functional label.

    The merge phase can invent a canonical wording, so its output is validated exactly as
    phase 1's was.  A group dropped here takes its documents with it; they fall back to
    their surviving ancestor rather than being filed under a label that would have to be
    explained to an auditor.
    """
    kept: list[MergeGroup] = []
    for group in groups:
        if check_label(group.canonical_label).ok:
            kept.append(group)
    return kept


def build_snapshot(
    *,
    register: Level1Register,
    groups: Sequence[MergeGroup],
    site_id: str,
    taxonomy_ver: int,
) -> SnapshotBuild:
    """Turn merged groups into ``mainline.activity_node`` rows.

    Level 1 is the whole register, whether or not the corpus exercised every code.  The
    fonds set is the buyer's risk register, not a summary of what happened to be in this
    year's incident file, and a fonds that exists with no records under it is a correct
    statement about the register.
    """
    fonds = register.nodes(site_id=site_id, taxonomy_ver=taxonomy_ver)
    by_root = {node.activity_root: node for node in fonds}
    nodes: list[ActivityNode] = list(fonds)
    aliases: dict[str, str] = {}
    series_index: dict[tuple[str, str], str] = {}
    leaf_index: dict[tuple[str, str], str] = {}
    dropped: list[str] = []

    series_scope: dict[tuple[str, str], str] = {}
    for group in sorted(groups, key=lambda g: (g.activity_root, g.canonical_label)):
        if group.level != LEVEL_SERIES:
            continue
        parent = by_root.get(group.activity_root)
        if parent is None:
            dropped.append(f"series {group.canonical_label!r}: off-register activity_root")
            continue
        scope_id = derive_scope_id(
            site_id=site_id,
            taxonomy_ver=taxonomy_ver,
            level=LEVEL_SERIES,
            label_path=[parent.label, group.canonical_label],
        )
        nodes.append(
            ActivityNode(
                scope_id=scope_id,
                site_id=site_id,
                level=LEVEL_SERIES,
                parent_scope=parent.scope_id,
                label=group.canonical_label,
                activity_root=group.activity_root,
                taxonomy_ver=taxonomy_ver,
                induced_by="llm_induced",
                frozen=False,
            )
        )
        series_scope[(group.activity_root, group.canonical_label)] = scope_id
        for member in group.members:
            aliases[member] = scope_id
            series_index[(group.activity_root, member)] = scope_id
        series_index[(group.activity_root, group.canonical_label)] = scope_id

    for group in sorted(
        groups, key=lambda g: (g.activity_root, g.parent_label or "", g.canonical_label)
    ):
        if group.level != LEVEL_FILE:
            continue
        parent_key = (group.activity_root, group.parent_label or "")
        parent_scope = series_scope.get(parent_key)
        if parent_scope is None:
            dropped.append(
                f"file {group.canonical_label!r}: parent series "
                f"{group.parent_label!r} did not survive the merge"
            )
            continue
        parent_node = next(node for node in nodes if node.scope_id == parent_scope)
        scope_id = derive_scope_id(
            site_id=site_id,
            taxonomy_ver=taxonomy_ver,
            level=LEVEL_FILE,
            label_path=[by_root[group.activity_root].label, parent_node.label,
                        group.canonical_label],
        )
        nodes.append(
            ActivityNode(
                scope_id=scope_id,
                site_id=site_id,
                level=LEVEL_FILE,
                parent_scope=parent_scope,
                label=group.canonical_label,
                activity_root=group.activity_root,
                taxonomy_ver=taxonomy_ver,
                induced_by="llm_induced",
                frozen=False,
            )
        )
        for member in group.members:
            aliases[member] = scope_id
            leaf_index[(group.activity_root, member)] = scope_id
        leaf_index[(group.activity_root, group.canonical_label)] = scope_id

    snapshot = TaxonomySnapshot(
        site_id=site_id,
        taxonomy_ver=taxonomy_ver,
        nodes=tuple(
            sorted(nodes, key=lambda n: (n.level, n.activity_root, n.label))
        ),
        aliases=dict(sorted(aliases.items())),
        register_id=register.register_id,
        register_sha256=register.sha256,
    )
    return SnapshotBuild(
        snapshot=snapshot,
        leaf_index=leaf_index,
        series_index=series_index,
        dropped_groups=tuple(dropped),
    )


def assign_leaves(pool: ProposalPool, build: SnapshotBuild) -> dict[str, str]:
    """Map each phase-1 document to the scope it ended up in after the merge.

    Falls back to the series when the file label did not survive, and omits the document
    entirely when neither did.  An omitted document trains nothing: it is better for the
    bulk classifier to have never seen it than to have seen it under a label that the
    frozen taxonomy does not contain.
    """
    out: dict[str, str] = {}
    for proposal in pool.proposals:
        scope = build.leaf_index.get((proposal.activity_root, proposal.file_label))
        if scope is None:
            scope = build.series_index.get((proposal.activity_root, proposal.series_label))
        if scope is not None:
            out[proposal.doc_id] = scope
    return out
