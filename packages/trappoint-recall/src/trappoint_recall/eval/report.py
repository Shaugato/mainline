# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""Rendering results so that the interval cannot be lost between here and a slide.

There is deliberately no "summary" mode that prints point estimates alone. Every
rendering path in this module emits ``value [lo, hi] (n=...)`` and stamps the split
policy, and the CI grep in ``scripts/recall/no_bare_point_estimates.py`` rejects any
document that does otherwise. The two controls are independent on purpose: one makes
the honest thing easy, the other makes the dishonest thing fail the build.

The G4-alpha status document doubles as the CI lane's artefact. It records RED or GREEN
explicitly — never "skipped" — because a gate that can be skipped is not a gate.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from datetime import UTC, datetime

from trappoint_recall.eval.gates import GateResult, overall_status
from trappoint_recall.eval.harness import MetricBundle

__all__ = [
    "PER_BOUND_STATEMENT",
    "gate_status_document",
    "render_gate_markdown",
    "render_metrics_markdown",
    "render_status_json",
]

PER_BOUND_STATEMENT = (
    "Proof of Exhausted Recall establishes that every candidate the retrieval returned "
    "and scored below theta is accounted for, that the score-sorted set was not "
    "hand-edited, and that tau was fixed before the run under an anchored policy. It "
    "does not prove exhaustion of the corpus: C-SPANN is approximate and its trees "
    "mutate on every insert."
)
"""Reproduced verbatim on every artefact that mentions recall completeness. A proof
that overclaims is worse than none."""


def _header(bundle: MetricBundle) -> list[str]:
    run = bundle.run
    lines = [
        f"**Corpus:** {run.corpus_name}",
        f"**Backend:** `{run.backend_name}`" + (f" (arm `{run.config_id}`)" if run.config_id else ""),
        f"**Split policy:** `{run.split_policy_id}`",
        f"**Depth requested:** k={run.k} over {len(run.results)} permits",
        f"**Run:** {run.started_at.isoformat()} to {run.finished_at.isoformat()} "
        f"({run.wall_seconds:.2f}s wall)",
    ]
    if run.synthetic:
        lines.append("**SYNTHETIC CORPUS** — these numbers characterise the harness, not the product.")
    if run.preliminary:
        lines.append("**PRELIMINARY** — no customer-grade floor is claimed at this checkpoint.")
    return lines


def render_metrics_markdown(bundle: MetricBundle) -> str:
    """Full metric report: every measurement with its interval, plus the two invariants."""
    lines: list[str] = ["# Recall evaluation", ""]
    lines.extend(_header(bundle))
    lines.append("")
    lines.append("## Measurements")
    lines.append("")
    lines.append("| metric | estimate | 95% interval | n | method |")
    lines.append("|---|---|---|---|---|")
    for name in sorted(bundle.measurements):
        m = bundle.measurements[name]
        if not m.defined:
            lines.append(f"| `{name}` | UNDEFINED | — | {m.n} | {m.undefined_reason} |")
        else:
            lines.append(
                f"| `{name}` | {m.value:.4f} | [{m.lower:.4f}, {m.upper:.4f}] | {m.n} | "
                f"{m.interval_method} |"
            )
    lines.append("")

    ranks = bundle.ranks
    lines.append("## Rank distribution of the truth precursor (severity 5)")
    lines.append("")
    lines.append("| bucket | count |")
    lines.append("|---|---|")
    for bucket, count in ranks.histogram().items():
        lines.append(f"| {bucket} | {count} |")
    lines.append("")
    median = ranks.percentile(50.0)
    p90 = ranks.percentile(90.0)
    lines.append(
        f"Found {len(ranks.ranks)} of {ranks.n}; median rank of found "
        f"{'n/a' if median is None else f'{median:.1f}'}, p90 "
        f"{'n/a' if p90 is None else f'{p90:.1f}'}."
    )
    lines.append("")

    cons = bundle.conservation
    lines.append("## Conservation law L3")
    lines.append("")
    lines.append(
        f"`candidates = blocking + advisory + silenced + deduped` — holds: **{cons.holds}**, "
        f"over {cons.total_candidates} candidates across {cons.covered_runs}/"
        f"{cons.expected_runs} runs"
        + (" (**VACUOUS**)" if cons.vacuous else "")
    )
    if cons.violations:
        lines.append("")
        for v in cons.violations[:10]:
            lines.append(f"- `{v.query_id}` ({v.kind}): {v.detail}")
        if len(cons.violations) > 10:
            lines.append(f"- ... and {len(cons.violations) - 10} more")
    lines.append("")

    bonded = bundle.bonded
    lines.append("## MI16 — bonded fatalities all blocking")
    lines.append("")
    lines.append(
        f"holds: **{bonded.holds}** — {bonded.blocking_bonded}/{bonded.expected_bonded} "
        "corpus-bonded severity-5 events returned blocking"
        + (" (**VACUOUS**: the corpus bonds none)" if bonded.vacuous else "")
    )
    if bonded.missing:
        lines.append("")
        for query_id, doc_id in bonded.missing[:10]:
            lines.append(f"- `{query_id}` did not block on bonded fatality `{doc_id}`")
        if len(bonded.missing) > 10:
            lines.append(f"- ... and {len(bonded.missing) - 10} more")
    lines.append("")

    if bundle.notes:
        lines.append("## Notes")
        lines.append("")
        lines.extend(f"- {n}" for n in bundle.notes)
        lines.append("")
    lines.append("---")
    lines.append("")
    lines.append(PER_BOUND_STATEMENT)
    lines.append("")
    return "\n".join(lines)


def render_gate_markdown(bundle: MetricBundle, results: Sequence[GateResult]) -> str:
    """The G4-alpha status page: RED or GREEN, with the reason for each verdict."""
    status = overall_status(results)
    passed = sum(1 for r in results if r.passed)
    lines: list[str] = [
        "# G4-alpha release gates",
        "",
        f"## Status: **{'GREEN' if status == 'PASS' else 'RED'}** ({passed}/{len(results)} gates passing)",
        "",
    ]
    lines.extend(_header(bundle))
    lines.append("")
    lines.append("| gate | status | floor | observed |")
    lines.append("|---|---|---|---|")
    for r in results:
        observed = (
            f"{r.measurement.value:.4f} [{r.measurement.lower:.4f}, {r.measurement.upper:.4f}] "
            f"(n={r.measurement.n})"
            if r.measurement is not None and r.measurement.defined
            else ("UNDEFINED" if r.measurement is not None else "invariant")
        )
        lines.append(f"| `{r.gate_id}` | **{r.status}** | {r.floor_repr} | {observed} |")
    lines.append("")
    lines.append("## Verdicts")
    lines.append("")
    for r in results:
        lines.append(f"### `{r.gate_id}` — {r.status}")
        lines.append("")
        if r.measurement is not None:
            lines.append(f"- measurement: {r.measurement.render()}")
        lines.append(f"- floor: {r.floor_repr}")
        lines.append(f"- reason: {r.reason}")
        lines.append("")
    lines.append("---")
    lines.append("")
    lines.append(
        "This suite is required to be RED before it is green. A test suite that has never "
        "failed asserts nothing about a product whose deliverable is a refusal."
    )
    lines.append("")
    lines.append(PER_BOUND_STATEMENT)
    lines.append("")
    return "\n".join(lines)


def gate_status_document(
    bundle: MetricBundle, results: Sequence[GateResult]
) -> dict[str, object]:
    """Machine-readable gate status. The artefact the CI lane records."""
    status = overall_status(results)
    return {
        "checkpoint": "G4alpha",
        "status": status,
        "lane_colour": "GREEN" if status == "PASS" else "RED",
        "gates_total": len(results),
        "gates_passed": sum(1 for r in results if r.passed),
        "generated_at": datetime.now(tz=UTC).isoformat(),
        "run": bundle.run.to_dict(),
        "gates": [r.to_dict() for r in results],
        "conservation": bundle.conservation.to_dict(),
        "bonded_fatalities": bundle.bonded.to_dict(),
        "measurements": {k: v.to_dict() for k, v in sorted(bundle.measurements.items())},
        "per_bound_statement": PER_BOUND_STATEMENT,
        "preliminary": bundle.run.preliminary,
        "synthetic": bundle.run.synthetic,
    }


def render_status_json(bundle: MetricBundle, results: Sequence[GateResult], *, indent: int = 2) -> str:
    return json.dumps(gate_status_document(bundle, results), indent=indent, sort_keys=True) + "\n"
