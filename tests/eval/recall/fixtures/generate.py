# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""Generate the harness self-test corpus. Deterministic; committed output.

Run with ``python tests/eval/recall/fixtures/generate.py`` to regenerate
``harness_selftest/``. The output is committed so that the G4-alpha suite runs on data
under review rather than on data invented at collection time, and this script is
committed so the data can be regenerated and diffed.

**This is not a gold set.** It is synthetic, it contains no real incident, and it exists
for exactly one purpose: to make the G4-alpha assertions executable before
``recall-corpora-goldsets`` lands GS0. It is sized and shaped so that a *correct*
retriever passes all five gates (24 severity-5 retro permits gives a Wilson lower bound
of 0.862 at perfect recall, clearing the 0.80 floor) and a silent one fails all five.
A gate that nothing could satisfy is a wall, not a gate.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

OUT = Path(__file__).resolve().parent / "harness_selftest"

WALL = datetime(2026, 1, 1, tzinfo=UTC)
CORPUS_COMMIT = "sha256:9f2c1a7d4b8e05663c1f0a9d5e7b2c48a1d6f3079b4e8c25d0a6f1b3c7e9d24a"

# (activity_path, asset_class, mechanism, precondition, control_failure, recurrence_test)
SCENARIOS: list[tuple[str, str, str, str, str, str]] = [
    (
        "/underground/ground-support/rehabilitation",
        "jumbo",
        "unsupported backs collapse during re-entry after a seismic event",
        "re-entry permitted before the exclusion timer expired",
        "seismic re-entry protocol waived by shift supervisor without geotechnical sign-off",
        "is any re-entry timer being shortened on this level?",
    ),
    (
        "/surface/mobile-plant/haul-road",
        "haul-truck",
        "loss of retardation on a descending grade with a loaded tray",
        "brake cooling circuit isolated for a leak repair",
        "defect deferral applied to a service brake without an engineering assessment",
        "does any deferral on this fleet touch a braking subsystem?",
    ),
    (
        "/process/gas-plant/inlet-separation",
        "pressure-vessel",
        "hydrocarbon release from a flange opened under residual pressure",
        "isolation verified by valve position rather than by bleed to atmosphere",
        "positive isolation standard downgraded to double block and bleed",
        "is any isolation on this vessel verified by position only?",
    ),
    (
        "/underground/ventilation/auxiliary-fan",
        "fan",
        "irrespirable atmosphere at the face after auxiliary ventilation stopped",
        "gas monitoring alarm set above the statutory action level",
        "alarm setpoint raised to reduce nuisance trips",
        "has any gas alarm setpoint been raised on this circuit?",
    ),
    (
        "/surface/fixed-plant/conveyor",
        "conveyor",
        "entanglement at an unguarded return idler during belt tracking",
        "guard removed for tracking adjustment while the belt was live",
        "isolation exemption granted for live tracking work",
        "does any live-work exemption cover a rotating component?",
    ),
    (
        "/process/tank-farm/hydrocarbon-storage",
        "storage-tank",
        "seal fire on a floating roof following a lightning strike",
        "rim seal degraded past the inspection interval",
        "inspection interval extended without a risk assessment",
        "has any seal inspection interval been extended on this farm?",
    ),
    (
        "/underground/electrical/high-voltage",
        "switchgear",
        "arc flash during racking of an 11 kV breaker",
        "racking performed with the cubicle door open",
        "remote racking device unavailable and the control substituted by PPE",
        "is any HV racking being done without the remote device?",
    ),
    (
        "/surface/lifting/mobile-crane",
        "crane",
        "load drop from a failed synthetic sling during a tandem lift",
        "sling inspected visually only after prior shock loading",
        "discard criteria for shock-loaded slings removed from the procedure",
        "does any lifting gear register carry a shock-loading history?",
    ),
    (
        "/process/utilities/nitrogen",
        "vessel",
        "asphyxiation on entry to a nitrogen-purged confined space",
        "atmospheric test taken at the manway rather than at the working level",
        "multi-level gas testing requirement deleted from the entry permit",
        "is any confined-space test single-point on this unit?",
    ),
    (
        "/underground/haulage/rail",
        "locomotive",
        "collision at a junction after a signal was passed at danger",
        "interlocking bypassed for a maintenance movement",
        "bypass key control delegated below the authorised level",
        "is any interlocking bypass authorised below deputy level?",
    ),
    (
        "/surface/tailings/embankment",
        "tailings-dam",
        "piping failure through a poorly compacted starter embankment",
        "phreatic surface above the design line for three consecutive readings",
        "trigger action response plan escalation suppressed as instrument error",
        "has any TARP escalation been closed as instrument error?",
    ),
    (
        "/process/furnace/tap-hole",
        "furnace",
        "molten metal runout during tap-hole drilling",
        "tap-hole clay cure time shortened to recover production",
        "cure time minimum removed from the operating standard",
        "has any cure or hold time been shortened on this furnace?",
    ),
    (
        "/surface/workshop/tyre-handling",
        "tyre-handler",
        "zipper failure of a heated earthmover tyre during inflation",
        "inflation performed without a restraint cage after a heat event",
        "cage requirement made conditional on operator judgement",
        "is any inflation control conditional on judgement?",
    ),
    (
        "/underground/explosives/charging",
        "charge-unit",
        "premature initiation during charging of a wet hole",
        "sleep time exceeded for a nitrate-sensitised emulsion",
        "sleep-time limit relaxed for a specific product without supplier advice",
        "has any explosive sleep-time limit been relaxed?",
    ),
]


def _scenario(i: int) -> tuple[str, str, str, str, str, str]:
    return SCENARIOS[i % len(SCENARIOS)]


def build() -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    queries: list[dict[str, object]] = []
    qrels: list[dict[str, object]] = []

    def judge(query_id: str, doc_id: str, grade: int, note: str) -> None:
        qrels.append(
            {
                "query_id": query_id,
                "doc_id": doc_id,
                "grade": grade,
                "scale": "umbrela-0-3",
                "gold_set": "HARNESS-SELFTEST",
                "judged_by": "authored",
                "blinded": True,
                "notes": note,
            }
        )

    # --- 24 severity-5 retro permits, 12 of them carrying a bonded fatality -------------
    for n in range(1, 25):
        qid = f"Q-RETRO-{n:04d}"
        path, asset, mech, pre, ctrl, test = _scenario(n - 1)
        wall = datetime(2023, 1, 1, tzinfo=UTC) + timedelta(days=37 * n)
        truth = f"E-PRECURSOR-{n:04d}"
        bonded = [f"E-BONDED-{n:04d}"] if n % 2 == 0 else []
        queries.append(
            {
                "query_id": qid,
                "kind": "retro",
                "text": (
                    f"Permit to work: {path.rsplit('/', 1)[-1].replace('-', ' ')} on {asset}. "
                    f"Scope includes work where {mech}."
                ),
                "site_id": f"SITE-{(n % 3) + 1}",
                "activity_path": path,
                "asset_class": asset,
                "severity": 5,
                "wall": wall.isoformat(),
                "truth_doc_id": truth,
                "bonded_sev5": bonded,
                "facets": {
                    "mechanism": mech,
                    "precondition": pre,
                    "control_failure": ctrl,
                    "recurrence_test": test,
                    "narrative": f"{mech}; {pre}; {ctrl}",
                },
                "blinded": True,
            }
        )
        judge(qid, truth, 3, "authored precursor: shares mechanism and precondition")
        for b in bonded:
            judge(qid, b, 3, "bonded severity-5 event on the same activity node")
        judge(qid, f"E-NEAR-{n:04d}", 2, "shares the mechanism, different precondition")
        judge(qid, f"E-RELATED-{n:04d}-a", 1, "same asset class, different recurrence condition")
        judge(qid, f"E-RELATED-{n:04d}-b", 1, "same site, unrelated mechanism")
        judge(qid, f"E-IRRELEVANT-{n:04d}", 0, "no shared mechanism and no shared precondition")

    # --- 4 severity-4 retro permits, so the severity filter is exercised ----------------
    for n in range(1, 5):
        qid = f"Q-RETRO4-{n:04d}"
        path, asset, mech, pre, ctrl, test = _scenario(n + 6)
        wall = datetime(2024, 3, 1, tzinfo=UTC) + timedelta(days=61 * n)
        truth = f"E-PRECURSOR4-{n:04d}"
        queries.append(
            {
                "query_id": qid,
                "kind": "retro",
                "text": (
                    f"Permit to work: {path.rsplit('/', 1)[-1].replace('-', ' ')} on {asset}. "
                    f"Scope includes work where {mech}."
                ),
                "site_id": f"SITE-{(n % 3) + 1}",
                "activity_path": path,
                "asset_class": asset,
                "severity": 4,
                "wall": wall.isoformat(),
                "truth_doc_id": truth,
                "bonded_sev5": [],
                "facets": {
                    "mechanism": mech,
                    "precondition": pre,
                    "control_failure": ctrl,
                    "recurrence_test": test,
                    "narrative": f"{mech}; {pre}; {ctrl}",
                },
                "blinded": True,
            }
        )
        judge(qid, truth, 3, "authored precursor at severity 4")
        judge(qid, f"E-RELATED4-{n:04d}", 1, "same asset class, different recurrence condition")

    # --- 40 routine permits: the negative control for nuisance rate --------------------
    routine_tasks = [
        ("planned inspection", "no energy source broken, no confined space"),
        ("lubrication round", "guards in place, plant running under standard controls"),
        ("housekeeping", "no plant interaction"),
        ("instrument calibration", "loop isolated under a standing procedure"),
        ("filter change", "vendor procedure, no process breach"),
    ]
    for n in range(1, 41):
        qid = f"Q-ROUTINE-{n:04d}"
        path, asset, *_ = _scenario(n - 1)
        task, why = routine_tasks[n % len(routine_tasks)]
        queries.append(
            {
                "query_id": qid,
                "kind": "routine",
                "text": (f"Permit to work: {task} on {asset} at {path}. Uneventful replay: {why}."),
                "site_id": f"SITE-{(n % 3) + 1}",
                "activity_path": path,
                "asset_class": asset,
                "severity": None,
                "wall": None,
                "truth_doc_id": None,
                "bonded_sev5": [],
                "facets": {"narrative": f"{task}: {why}"},
                "blinded": True,
            }
        )
        # Plausible-but-wrong neighbours. A backend that blocks on these is both noisy
        # and imprecise, and the two gates will say so independently.
        judge(qid, f"E-DISTRACTOR-{n:04d}-a", 0, "same asset class only; no shared mechanism")
        judge(qid, f"E-DISTRACTOR-{n:04d}-b", 1, "same site; routine task shares no precondition")

    return queries, qrels


def main() -> None:
    queries, qrels = build()
    OUT.mkdir(parents=True, exist_ok=True)

    with (OUT / "queries.jsonl").open("w", encoding="utf-8", newline="\n") as handle:
        for row in queries:
            handle.write(json.dumps(row, sort_keys=True) + "\n")

    with (OUT / "qrels.jsonl").open("w", encoding="utf-8", newline="\n") as handle:
        for row in qrels:
            handle.write(json.dumps(row, sort_keys=True) + "\n")

    (OUT / "split.json").write_text(
        json.dumps(
            {
                "kind": "temporally_blocked",
                "wall": WALL.isoformat(),
                "corpus_commit": CORPUS_COMMIT,
                "note": (
                    "Predicate-enforced wall: occurred_at < t AND ingested_at < t AND "
                    "corpus_commit <= t. AS OF SYSTEM TIME is refused (gc.ttlseconds=4h)."
                ),
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

    (OUT / "manifest.json").write_text(
        json.dumps(
            {
                "name": "harness-selftest",
                "preliminary": True,
                "synthetic": True,
                "provenance": (
                    "Authored by tests/eval/recall/fixtures/generate.py. Contains no real "
                    "incident data and no real person. Not a gold set: it exists so the "
                    "G4-alpha assertions are executable before GS0 lands, and it is sized "
                    "so a correct retriever passes and a silent one fails."
                ),
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

    n_retro5 = sum(1 for q in queries if q["kind"] == "retro" and q["severity"] == 5)
    n_bonded = sum(len(list(q["bonded_sev5"])) for q in queries)  # type: ignore[arg-type]
    print(
        f"wrote {len(queries)} queries ({n_retro5} severity-5 retro, {n_bonded} bonded "
        f"fatalities) and {len(qrels)} judgements to {OUT}"
    )


if __name__ == "__main__":
    main()
