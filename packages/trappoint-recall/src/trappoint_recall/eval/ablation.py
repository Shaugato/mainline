# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""The ablation matrix: the only honest answer to "why is any of this here?".

Every component of the recall stack costs latency, tokens or maintenance, and a stack
whose parts have never been removed one at a time is a stack of assumptions. The matrix
below is simultaneously the hackathon artefact and the diligence artefact (recall lead,
1):

* the **channel ladder** — A, A+B, A+B+C, A+B+C+D, +rerank, +SGA
* **cue vs narrative** embedding — the genuinely open question of whether
  Recurrence-Condition Cues beat contextualised narratives *in this domain*
* **prefix on/off** — whether the taxonomy-constrained arms earn their complexity
* **1024-d vs 256-d** — whether the coarse sweep can carry more of the load
* **beam sweep** — ``vector_search_beam_size``, where recall is bought with latency

This module runs a matrix; it does not implement a single one of those variants. A
:class:`BackendFactory` supplied by the caller turns an :class:`AblationArm` into a
backend, and the arm's fields are passed through verbatim so the factory — not the
harness — decides what "prefix off" means for its implementation.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Final, Literal, Protocol

from trappoint_recall.eval.backend import RetrievalBackend, ScoredCandidate
from trappoint_recall.eval.corpus import EvalCorpus
from trappoint_recall.eval.gates import GateResult, evaluate_g4alpha
from trappoint_recall.eval.harness import DEFAULT_K, MetricBundle, compute_metrics, run_evaluation
from trappoint_recall.eval.measurement import Measurement

__all__ = [
    "DEFAULT_MATRIX",
    "AblationArm",
    "AblationRow",
    "AblationTable",
    "BackendFactory",
    "FactoryCallable",
    "RetrievalBackend",
    "ScoredCandidate",
    "REPORTED_METRICS",
    "arm_by_id",
    "matrix_config",
    "run_ablation",
    "run_ablation_sync",
]

EmbeddingGenre = Literal["cue", "narrative"]
Dimensionality = Literal[1024, 256]

REPORTED_METRICS: Final[tuple[str, ...]] = (
    "retro_recall_at_1_sev5",
    "retro_recall_at_3_sev5",
    "retro_recall_at_10_sev5",
    "ndcg_at_10",
    "p_at_block",
    "nuisance_rate",
    "mean_blocking_checks_per_permit",
    "mrr",
)
"""Columns of the published table, in order. Recall first, cost last."""


@dataclass(frozen=True, slots=True)
class AblationArm:
    """One configuration of the recall stack.

    ``arm_id`` is stable and is what a report, a commit message and a conversation all
    use to name the same configuration.
    """

    arm_id: str
    label: str
    channels: tuple[str, ...] = ("A",)
    rerank: bool = False
    sga: bool = False
    embedding_genre: EmbeddingGenre = "cue"
    prefix: bool = True
    dim: Dimensionality = 1024
    beam_size: int = 8
    notes: str = ""

    def __post_init__(self) -> None:
        if not self.arm_id:
            raise ValueError("arm_id is mandatory")
        allowed = {"A", "B", "C", "C_sweep", "D"}
        unknown = set(self.channels) - allowed
        if unknown:
            raise ValueError(f"{self.arm_id}: unknown channels {sorted(unknown)}")
        if self.beam_size < 1:
            raise ValueError(f"{self.arm_id}: beam_size must be >= 1")
        if self.rerank and "C" not in self.channels and "C_sweep" not in self.channels:
            raise ValueError(
                f"{self.arm_id}: rerank without a probabilistic channel has nothing to rerank"
            )

    def config(self) -> dict[str, object]:
        return {
            "arm_id": self.arm_id,
            "label": self.label,
            "channels": list(self.channels),
            "rerank": self.rerank,
            "sga": self.sga,
            "embedding_genre": self.embedding_genre,
            "prefix": self.prefix,
            "dim": self.dim,
            "beam_size": self.beam_size,
            "notes": self.notes,
        }


def _ladder() -> tuple[AblationArm, ...]:
    return (
        AblationArm(
            arm_id="L0-A",
            label="A only (deterministic ancestry)",
            channels=("A",),
            notes="Graph truth. No model in the path. The floor the product never drops below.",
        ),
        AblationArm(
            arm_id="L1-AB",
            label="A+B (ancestry + bonded severity-5)",
            channels=("A", "B"),
            notes="The degraded path. Bedrock throttled or refusing still blocks here.",
        ),
        AblationArm(
            arm_id="L2-ABC",
            label="A+B+C (+ prefix-constrained ANN)",
            channels=("A", "B", "C", "C_sweep"),
            notes="First probabilistic channel; fusion by RRF, no rerank.",
        ),
        AblationArm(
            arm_id="L3-ABCD",
            label="A+B+C+D (+ lexical BM25)",
            channels=("A", "B", "C", "C_sweep", "D"),
            notes="BM25 carries the identifier vocabulary: K-401, H2S, %LEL, OEM part numbers.",
        ),
        AblationArm(
            arm_id="L4-ABCD-rerank",
            label="A+B+C+D + listwise rerank",
            channels=("A", "B", "C", "C_sweep", "D"),
            rerank=True,
            notes="Dominates the S4 latency budget; its justification becomes evidence_summary.",
        ),
        AblationArm(
            arm_id="L5-ABCD-rerank-sga",
            label="A+B+C+D + rerank + severity-graded admission",
            channels=("A", "B", "C", "C_sweep", "D"),
            rerank=True,
            sga=True,
            notes="Severity lowers the evidence bar rather than inflating the score.",
        ),
    )


def _variations() -> tuple[AblationArm, ...]:
    full: tuple[str, ...] = ("A", "B", "C", "C_sweep", "D")
    arms: list[AblationArm] = [
        AblationArm(
            arm_id="V-narrative",
            label="full stack, narrative embedding",
            channels=full,
            rerank=True,
            sga=True,
            embedding_genre="narrative",
            notes="Open question: do cues beat contextualised narratives in this domain?",
        ),
        AblationArm(
            arm_id="V-noprefix",
            label="full stack, no taxonomy prefix",
            channels=full,
            rerank=True,
            sga=True,
            prefix=False,
            notes="Does the prefix earn its complexity, or is the coarse sweep enough?",
        ),
        AblationArm(
            arm_id="V-256d",
            label="full stack, 256-d only",
            channels=full,
            rerank=True,
            sga=True,
            dim=256,
            notes="Coarse-only. Cheaper index, and the honest cost is measured here.",
        ),
    ]
    arms.extend(
        AblationArm(
            arm_id=f"V-beam{beam}",
            label=f"full stack, beam size {beam}",
            channels=full,
            rerank=True,
            sga=True,
            beam_size=beam,
            notes="Recall bought with latency; the knee of this curve sets the shipped default.",
        )
        for beam in (1, 4, 8, 16, 32)
    )
    return tuple(arms)


DEFAULT_MATRIX: Final[tuple[AblationArm, ...]] = _ladder() + _variations()
"""Ladder then variations. Published in full, including the rows that look bad."""


class BackendFactory(Protocol):
    """Turns an arm into a backend. Supplied by whoever owns the retrieval stack.

    The parameter is positional-only so that a plain ``lambda arm: ...`` satisfies the
    protocol; requiring a keyword name would make the interface harder to implement for
    no benefit to the caller.
    """

    def __call__(self, arm: AblationArm, /) -> RetrievalBackend: ...


@dataclass(frozen=True, slots=True)
class AblationRow:
    """One arm's results."""

    arm: AblationArm
    bundle: MetricBundle
    gates: tuple[GateResult, ...]

    @property
    def gates_passed(self) -> int:
        return sum(1 for g in self.gates if g.passed)

    def measurement(self, metric: str) -> Measurement:
        return self.bundle[metric]

    def to_dict(self) -> dict[str, object]:
        return {
            "arm": self.arm.config(),
            "metrics": {m: self.bundle[m].to_dict() for m in REPORTED_METRICS},
            "conservation": self.bundle.conservation.to_dict(),
            "bonded_fatalities": self.bundle.bonded.to_dict(),
            "gates": [g.to_dict() for g in self.gates],
            "gates_passed": self.gates_passed,
            "gates_total": len(self.gates),
        }


@dataclass(frozen=True, slots=True)
class AblationTable:
    """The published table. Markdown for humans, JSON for diffs."""

    corpus_label: str
    split_policy_id: str
    rows: tuple[AblationRow, ...]
    baseline_arm_id: str = "L0-A"
    notes: tuple[str, ...] = field(default_factory=tuple)

    def row(self, arm_id: str) -> AblationRow | None:
        for r in self.rows:
            if r.arm.arm_id == arm_id:
                return r
        return None

    def delta(self, arm_id: str, metric: str) -> float | None:
        """Point-estimate delta against the baseline arm, or ``None`` if not computable.

        A delta is a navigation aid, never a claim: two point estimates whose intervals
        overlap have not been shown to differ, and the rendered table prints the
        intervals next to the delta so the reader can see that for themselves.
        """
        base = self.row(self.baseline_arm_id)
        target = self.row(arm_id)
        if base is None or target is None:
            return None
        a = base.measurement(metric)
        b = target.measurement(metric)
        if not a.defined or not b.defined:
            return None
        return b.value - a.value

    def to_dict(self) -> dict[str, object]:
        return {
            "corpus": self.corpus_label,
            "split_policy_id": self.split_policy_id,
            "baseline_arm_id": self.baseline_arm_id,
            "metrics_reported": list(REPORTED_METRICS),
            "rows": [r.to_dict() for r in self.rows],
            "notes": list(self.notes),
        }

    def to_json(self, *, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, sort_keys=True) + "\n"

    def to_markdown(self) -> str:
        """Render the table with every cell carrying its interval.

        Cells are ``value [lo, hi]``. There is no mode that prints the point estimate
        alone; ``scripts/recall/no_bare_point_estimates.py`` would reject the output.
        """
        lines: list[str] = []
        lines.append("# Recall ablation table")
        lines.append("")
        lines.append(f"**Corpus:** {self.corpus_label}")
        lines.append(f"**Split policy:** `{self.split_policy_id}`")
        lines.append(f"**Baseline arm:** `{self.baseline_arm_id}`")
        lines.append("")
        lines.append(
            "Every cell is a point estimate with its 95% interval. Overlapping intervals "
            "have not been shown to differ, whatever the deltas suggest."
        )
        lines.append("")
        header = ["arm", "configuration", *REPORTED_METRICS, "gates"]
        lines.append("| " + " | ".join(header) + " |")
        lines.append("|" + "|".join(["---"] * len(header)) + "|")
        for row in self.rows:
            cells = [f"`{row.arm.arm_id}`", row.arm.label]
            for metric in REPORTED_METRICS:
                m = row.measurement(metric)
                if not m.defined:
                    cells.append("UNDEFINED")
                else:
                    cells.append(f"{m.value:.3f} [{m.lower:.3f}, {m.upper:.3f}] (n={m.n})")
            cells.append(f"{row.gates_passed}/{len(row.gates)}")
            lines.append("| " + " | ".join(cells) + " |")
        lines.append("")
        lines.append("## Arm notes")
        lines.append("")
        for row in self.rows:
            if row.arm.notes:
                lines.append(f"- `{row.arm.arm_id}` — {row.arm.notes}")
        if self.notes:
            lines.append("")
            lines.append("## Notes")
            lines.append("")
            lines.extend(f"- {n}" for n in self.notes)
        lines.append("")
        return "\n".join(lines)


async def run_ablation(
    factory: BackendFactory,
    corpus: EvalCorpus,
    *,
    matrix: Sequence[AblationArm] = DEFAULT_MATRIX,
    k: int = DEFAULT_K,
    concurrency: int = 8,
) -> AblationTable:
    """Run every arm of ``matrix`` against ``corpus`` and assemble the table.

    Arms run sequentially. An ablation whose arms contend for the same cluster measures
    contention, and the beam sweep in particular is a latency claim.
    """
    rows: list[AblationRow] = []
    for arm in matrix:
        backend = factory(arm)
        run = await run_evaluation(
            backend, corpus, k=k, concurrency=concurrency, config_id=arm.arm_id
        )
        bundle = compute_metrics(run, corpus)
        rows.append(AblationRow(arm=arm, bundle=bundle, gates=evaluate_g4alpha(bundle)))
    notes = [
        "Ablation is a deliverable, not a nicety: a stack whose parts have never been "
        "removed one at a time is a stack of assumptions.",
    ]
    if corpus.synthetic:
        notes.append("Corpus is SYNTHETIC; these rows characterise the harness, not the product.")
    if corpus.preliminary:
        notes.append("PRELIMINARY: no customer-grade floor is claimed at this checkpoint.")
    return AblationTable(
        corpus_label=corpus.label(),
        split_policy_id=corpus.split_policy_id,
        rows=tuple(rows),
        notes=tuple(notes),
    )


def run_ablation_sync(
    factory: BackendFactory,
    corpus: EvalCorpus,
    *,
    matrix: Sequence[AblationArm] = DEFAULT_MATRIX,
    k: int = DEFAULT_K,
    concurrency: int = 8,
) -> AblationTable:
    """Synchronous wrapper around :func:`run_ablation`."""
    return asyncio.run(run_ablation(factory, corpus, matrix=matrix, k=k, concurrency=concurrency))


FactoryCallable = Callable[[AblationArm], RetrievalBackend]
"""Structural alias for callers that prefer a plain callable to the Protocol."""


def arm_by_id(arm_id: str, *, matrix: Sequence[AblationArm] = DEFAULT_MATRIX) -> AblationArm:
    """Look up an arm by id, with the available ids in the error."""
    for arm in matrix:
        if arm.arm_id == arm_id:
            return arm
    known = ", ".join(a.arm_id for a in matrix)
    raise KeyError(f"unknown arm {arm_id!r}; matrix carries: {known}")


def matrix_config(matrix: Sequence[AblationArm] = DEFAULT_MATRIX) -> list[Mapping[str, object]]:
    """The matrix as plain data, for committing alongside a result set."""
    return [arm.config() for arm in matrix]
