# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""The G4-alpha release gates, and the vacuity guards that stop silence from passing.

Four floors and one law (ARCHITECTURE.md 6.7, BUILD_PLAN.md K4):

===============================  ==========================================================
``retro_recall_at_3_sev5``       >= 0.90 point, Wilson lower bound >= 0.80
``p_at_block``                   >= 0.75 on the blinded adjudicated subset
``nuisance_rate``                <  0.03 on the routine-permit replay
``mean_blocking_checks_per_permit``  <= 1.0, hard cap 3 probabilistic per permit
``conservation_l3``              candidates = blocking + advisory + silenced + deduped
===============================  ==========================================================

Why three of these carry an extra condition
--------------------------------------------
Two of the four floors and the law are **trivially satisfied by a system that does
nothing**. A retriever that returns no candidates has a nuisance rate of 0.00, a mean
of 0.00 blocking checks per permit, and a conservation law that closes perfectly over
zero candidates. Written naively, three of the five G4-alpha gates would go green on an
empty implementation — and a suite that certifies silence is worse than no suite,
because it converts an absent product into a passing one.

So each of those three carries a companion condition, and each companion is taken from
the architecture rather than invented here:

* **nuisance rate** additionally requires a *sensitivity witness*: the same policy must
  have produced at least one probabilistic blocking check on the retro subset. The
  target was always the joint claim ``P@block >= 0.75 at Retro-Recall@3 >= 0.90``; a
  nuisance rate measured at zero sensitivity is not a point on that curve.
* **mean blocking checks** additionally requires **MI16**
  (``bonded_fatalities_all_blocking``): every severity-5 event bonded to the permit's
  activity node or an ancestor must come back blocking. Checked against *corpus* truth,
  never against the backend's declared counters.
* **conservation** additionally requires complete coverage and a non-empty universe.

These conditions make the gates strictly harder, never easier. Nothing here softens a
floor; the floors live in ``data/eval_floors.json`` and ratchet upward only.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from importlib.resources import files
from typing import Final, Literal

from trappoint_recall.eval.harness import MetricBundle
from trappoint_recall.eval.measurement import Measurement

__all__ = [
    "G4ALPHA_GATE_IDS",
    "FloorsError",
    "GateResult",
    "GateStatus",
    "evaluate_g4alpha",
    "load_floors",
    "overall_status",
]

GateStatus = Literal["PASS", "FAIL"]

G4ALPHA_GATE_IDS: Final[tuple[str, ...]] = (
    "retro_recall_at_3_sev5",
    "p_at_block",
    "nuisance_rate",
    "mean_blocking_checks_per_permit",
    "conservation_l3",
)
"""The five G4-alpha gates, in report order. Adding one is a design change, not a tweak."""


class FloorsError(RuntimeError):
    """Raised when the committed floors file is missing or malformed."""


def load_floors() -> Mapping[str, object]:
    """Read the committed ``eval_floors.json`` shipped inside this package."""
    resource = files("trappoint_recall.eval").joinpath("data/eval_floors.json")
    try:
        payload = json.loads(resource.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:  # pragma: no cover - packaging defect
        raise FloorsError("eval_floors.json is missing from the installed package") from exc
    if not isinstance(payload, dict):
        raise FloorsError("eval_floors.json must contain a JSON object")
    gates = payload.get("gates")
    if not isinstance(gates, dict):
        raise FloorsError("eval_floors.json must carry a 'gates' object")
    missing = [g for g in G4ALPHA_GATE_IDS if g not in gates]
    if missing:
        raise FloorsError(f"eval_floors.json is missing gate definitions: {missing}")
    return payload


def _gate_spec(floors: Mapping[str, object], gate_id: str) -> Mapping[str, object]:
    gates = floors["gates"]
    if not isinstance(gates, dict):  # pragma: no cover - guarded by load_floors
        raise FloorsError("floors['gates'] is not an object")
    spec = gates[gate_id]
    if not isinstance(spec, dict):
        raise FloorsError(f"floors['gates'][{gate_id!r}] is not an object")
    return spec


def _as_float(spec: Mapping[str, object], key: str) -> float:
    value = spec.get(key)
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise FloorsError(f"floor {key!r} must be a number, got {value!r}")
    return float(value)


@dataclass(frozen=True, slots=True)
class GateResult:
    """One gate's verdict, with the reason spelled out whether it passed or failed.

    ``reason`` is written to be readable in a CI log by someone who was not in the room:
    it names the floor, the observed interval and, when the gate failed on a companion
    condition, which condition and why that condition exists.
    """

    gate_id: str
    status: GateStatus
    reason: str
    measurement: Measurement | None
    floor_repr: str
    evidence: Mapping[str, object]

    @property
    def passed(self) -> bool:
        return self.status == "PASS"

    def render(self) -> str:
        head = f"[{self.status}] {self.gate_id} (floor: {self.floor_repr})"
        body = self.measurement.render() if self.measurement else "no measurement"
        return f"{head}\n    {body}\n    {self.reason}"

    def to_dict(self) -> dict[str, object]:
        return {
            "gate_id": self.gate_id,
            "status": self.status,
            "reason": self.reason,
            "floor": self.floor_repr,
            "measurement": self.measurement.to_dict() if self.measurement else None,
            "evidence": dict(self.evidence),
        }


# --------------------------------------------------------------------------------------
# Individual gates
# --------------------------------------------------------------------------------------


def gate_retro_recall(bundle: MetricBundle, floors: Mapping[str, object]) -> GateResult:
    spec = _gate_spec(floors, "retro_recall_at_3_sev5")
    point_floor = _as_float(spec, "point_floor")
    lb_floor = _as_float(spec, "lower_bound_floor")
    m = bundle["retro_recall_at_3_sev5"]
    floor_repr = f"point >= {point_floor:.2f} AND Wilson LB >= {lb_floor:.2f}"

    if not m.defined:
        return GateResult(
            gate_id="retro_recall_at_3_sev5",
            status="FAIL",
            reason=f"measurement undefined: {m.undefined_reason}",
            measurement=m,
            floor_repr=floor_repr,
            evidence={"rank_distribution": bundle.ranks.to_dict()},
        )
    point_ok = m.meets_floor(point_floor, on="value")
    lb_ok = m.meets_floor(lb_floor, on="lower")
    if point_ok and lb_ok:
        reason = (
            f"point {m.value:.4f} >= {point_floor:.2f} and Wilson lower bound "
            f"{m.lower:.4f} >= {lb_floor:.2f} over n={m.n} severity-5 retro permits"
        )
        return GateResult(
            gate_id="retro_recall_at_3_sev5",
            status="PASS",
            reason=reason,
            measurement=m,
            floor_repr=floor_repr,
            evidence={"rank_distribution": bundle.ranks.to_dict()},
        )
    failures: list[str] = []
    if not point_ok:
        failures.append(f"point {m.value:.4f} < {point_floor:.2f}")
    if not lb_ok:
        failures.append(f"Wilson lower bound {m.lower:.4f} < {lb_floor:.2f}")
    return GateResult(
        gate_id="retro_recall_at_3_sev5",
        status="FAIL",
        reason=(
            "; ".join(failures)
            + f" over n={m.n} severity-5 retro permits. A miss here is a fatality exhibit."
        ),
        measurement=m,
        floor_repr=floor_repr,
        evidence={"rank_distribution": bundle.ranks.to_dict()},
    )


def gate_p_at_block(bundle: MetricBundle, floors: Mapping[str, object]) -> GateResult:
    spec = _gate_spec(floors, "p_at_block")
    point_floor = _as_float(spec, "point_floor")
    m = bundle["p_at_block"]
    floor_repr = f"point >= {point_floor:.2f} (G4-beta ratchets to Wilson LB)"
    if not m.defined:
        return GateResult(
            gate_id="p_at_block",
            status="FAIL",
            reason=(
                f"measurement undefined: {m.undefined_reason}. Precision cannot be inferred "
                "from an absence of blocking checks."
            ),
            measurement=m,
            floor_repr=floor_repr,
            evidence={},
        )
    if m.meets_floor(point_floor, on="value"):
        return GateResult(
            gate_id="p_at_block",
            status="PASS",
            reason=(
                f"point {m.value:.4f} >= {point_floor:.2f}, Wilson interval "
                f"[{m.lower:.4f}, {m.upper:.4f}] over n={m.n} blocking probabilistic checks"
            ),
            measurement=m,
            floor_repr=floor_repr,
            evidence={},
        )
    return GateResult(
        gate_id="p_at_block",
        status="FAIL",
        reason=(
            f"point {m.value:.4f} < {point_floor:.2f} over n={m.n} blocking probabilistic "
            "checks. The pre-committed response to a sustained miss is DEMOTE: channels C "
            "and D become advisory-only and the gate runs on A+B."
        ),
        measurement=m,
        floor_repr=floor_repr,
        evidence={},
    )


def gate_nuisance_rate(bundle: MetricBundle, floors: Mapping[str, object]) -> GateResult:
    spec = _gate_spec(floors, "nuisance_rate")
    ceiling = _as_float(spec, "ceiling")
    m = bundle["nuisance_rate"]
    floor_repr = f"point < {ceiling:.2f} AND sensitivity witness present"

    # The sensitivity witness: this policy must actually block on something in the retro
    # subset. Without it the nuisance rate is measured at zero sensitivity and is not a
    # point on the precision/recall curve the target describes.
    retro_blocking = sum(
        len(r.probabilistic_blocking) for r in bundle.run.results if r.query.kind == "retro"
    )
    evidence: dict[str, object] = {
        "retro_probabilistic_blocking_checks": retro_blocking,
        "retro_recall_at_3_sev5": bundle["retro_recall_at_3_sev5"].to_dict(),
    }
    if retro_blocking == 0:
        return GateResult(
            gate_id="nuisance_rate",
            status="FAIL",
            reason=(
                f"vacuous: nuisance rate is {m.value:.4f} but the same policy produced zero "
                "probabilistic blocking checks across the retro subset. A system that never "
                "blocks has a nuisance rate of zero and a recall of zero; the target is the "
                "joint claim (P@block at Retro-Recall@3), not the ceiling alone."
            ),
            measurement=m,
            floor_repr=floor_repr,
            evidence=evidence,
        )
    if not m.defined:
        return GateResult(
            gate_id="nuisance_rate",
            status="FAIL",
            reason=f"measurement undefined: {m.undefined_reason}",
            measurement=m,
            floor_repr=floor_repr,
            evidence=evidence,
        )
    if m.under_ceiling(ceiling, on="value"):
        return GateResult(
            gate_id="nuisance_rate",
            status="PASS",
            reason=(
                f"point {m.value:.4f} < {ceiling:.2f}, Wilson interval "
                f"[{m.lower:.4f}, {m.upper:.4f}] over n={m.n} routine permits, with "
                f"{retro_blocking} probabilistic blocking checks on the retro subset as the "
                "sensitivity witness"
            ),
            measurement=m,
            floor_repr=floor_repr,
            evidence=evidence,
        )
    return GateResult(
        gate_id="nuisance_rate",
        status="FAIL",
        reason=(
            f"point {m.value:.4f} >= {ceiling:.2f} over n={m.n} routine permits. A rule that "
            "breaches the nuisance ceiling is rejected rather than tuned."
        ),
        measurement=m,
        floor_repr=floor_repr,
        evidence=evidence,
    )


def gate_mean_blocking(bundle: MetricBundle, floors: Mapping[str, object]) -> GateResult:
    spec = _gate_spec(floors, "mean_blocking_checks_per_permit")
    ceiling = _as_float(spec, "ceiling")
    m = bundle["mean_blocking_checks_per_permit"]
    floor_repr = f"mean <= {ceiling:.2f} AND MI16 holds AND no permit over the cap of 3"
    bonded = bundle.bonded
    evidence: dict[str, object] = {"bonded_fatalities": bonded.to_dict()}

    if not bonded.holds:
        return GateResult(
            gate_id="mean_blocking_checks_per_permit",
            status="FAIL",
            reason=(
                f"MI16 bonded_fatalities_all_blocking is violated: {len(bonded.missing)} of "
                f"{bonded.expected_bonded} corpus-bonded severity-5 events did not come back "
                "blocking. A mean of "
                f"{m.value:.4f} blocking checks per permit is not a pass while a bonded "
                "fatality is missing; that is where 'a fatality never decays' lives."
            ),
            measurement=m,
            floor_repr=floor_repr,
            evidence=evidence,
        )
    if bonded.vacuous:
        return GateResult(
            gate_id="mean_blocking_checks_per_permit",
            status="FAIL",
            reason=(
                "vacuous: the corpus bonds no severity-5 events to any permit, so MI16 holds "
                "over nothing and the mean cannot distinguish a calibrated gate from a silent "
                "one. Evaluate against a corpus carrying bonded fatalities."
            ),
            measurement=m,
            floor_repr=floor_repr,
            evidence=evidence,
        )
    if not m.defined:
        return GateResult(
            gate_id="mean_blocking_checks_per_permit",
            status="FAIL",
            reason=f"measurement undefined: {m.undefined_reason}",
            measurement=m,
            floor_repr=floor_repr,
            evidence=evidence,
        )
    over_cap = m.detail.get("n_over_cap", 0)
    if isinstance(over_cap, int) and over_cap > 0:
        return GateResult(
            gate_id="mean_blocking_checks_per_permit",
            status="FAIL",
            reason=(
                f"{over_cap} permit(s) carry more than 3 probabilistic blocking checks. The cap "
                "is hard; overflow belongs in the silence ledger with its tau and its score."
            ),
            measurement=m,
            floor_repr=floor_repr,
            evidence=evidence,
        )
    if m.value <= ceiling:
        return GateResult(
            gate_id="mean_blocking_checks_per_permit",
            status="PASS",
            reason=(
                f"mean {m.value:.4f} <= {ceiling:.2f}, bootstrap interval "
                f"[{m.lower:.4f}, {m.upper:.4f}] over n={m.n} permits, with MI16 holding over "
                f"{bonded.expected_bonded} bonded severity-5 events"
            ),
            measurement=m,
            floor_repr=floor_repr,
            evidence=evidence,
        )
    return GateResult(
        gate_id="mean_blocking_checks_per_permit",
        status="FAIL",
        reason=(
            f"mean {m.value:.4f} > {ceiling:.2f} over n={m.n} permits. At ~250 permits/week and "
            "~4 minutes per disposition this is the rubber-stamping regime; the pre-committed "
            "response is CAP: tighten the SGA thresholds and the cap."
        ),
        measurement=m,
        floor_repr=floor_repr,
        evidence=evidence,
    )


def gate_conservation(bundle: MetricBundle, floors: Mapping[str, object]) -> GateResult:
    _gate_spec(floors, "conservation_l3")  # presence check; the law has no numeric floor
    report = bundle.conservation
    floor_repr = (
        "candidates = blocking + advisory + silenced + deduped, exactly, over every run, "
        "with complete coverage and a non-empty universe"
    )
    evidence: dict[str, object] = {"conservation": report.to_dict()}
    if not report.holds:
        first = report.violations[0]
        return GateResult(
            gate_id="conservation_l3",
            status="FAIL",
            reason=(
                f"{len(report.violations)} conservation violation(s); first: "
                f"{first.query_id}: {first.detail}"
            ),
            measurement=None,
            floor_repr=floor_repr,
            evidence=evidence,
        )
    if not report.coverage_complete:
        return GateResult(
            gate_id="conservation_l3",
            status="FAIL",
            reason=(
                f"coverage incomplete: {report.covered_runs} of {report.expected_runs} runs "
                "published counters. An unaccounted run is an unaccounted candidate set."
            ),
            measurement=None,
            floor_repr=floor_repr,
            evidence=evidence,
        )
    if report.vacuous:
        return GateResult(
            gate_id="conservation_l3",
            status="FAIL",
            reason=(
                f"vacuous: the law closed over {report.total_candidates} candidates across "
                f"{report.covered_runs} runs. 0 = 0 + 0 + 0 + 0 is true and asserts nothing; "
                "the claim is that every candidate the retrieval saw is accounted for, which "
                "requires candidates."
            ),
            measurement=None,
            floor_repr=floor_repr,
            evidence=evidence,
        )
    return GateResult(
        gate_id="conservation_l3",
        status="PASS",
        reason=(
            f"exact over {report.total_candidates} candidates across {report.covered_runs} "
            "runs, declared counters matching independently enumerated counters"
        ),
        measurement=None,
        floor_repr=floor_repr,
        evidence=evidence,
    )


_GATES: Final = {
    "retro_recall_at_3_sev5": gate_retro_recall,
    "p_at_block": gate_p_at_block,
    "nuisance_rate": gate_nuisance_rate,
    "mean_blocking_checks_per_permit": gate_mean_blocking,
    "conservation_l3": gate_conservation,
}


def evaluate_g4alpha(
    bundle: MetricBundle, *, floors: Mapping[str, object] | None = None
) -> tuple[GateResult, ...]:
    """Evaluate all five G4-alpha gates in report order."""
    spec = floors if floors is not None else load_floors()
    return tuple(_GATES[gate_id](bundle, spec) for gate_id in G4ALPHA_GATE_IDS)


def overall_status(results: Sequence[GateResult]) -> GateStatus:
    """``PASS`` only when every gate passed. Green requires all five."""
    return "PASS" if all(r.passed for r in results) else "FAIL"
