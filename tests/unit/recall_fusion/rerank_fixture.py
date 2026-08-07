# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""The deterministic exposure cue and candidate set the rerank cassettes are keyed on.

Imported by both ``make_rerank_cassettes.py`` (which writes the cassettes) and
``test_rerank_listwise.py`` (which replays them), so the request digest computed at record
time and the one computed at replay time cannot drift apart. Editing anything here changes
every digest and the suite goes red until the cassettes are regenerated — which is the
intended cost of changing what the judge is shown.

The narratives are constructed, not real. They are shaped like MSHA and CSB material — a
mechanism, a precondition, a defeated control, a recurrence test — because the shape is what
the rubric reasons over, but no real fatality appears in a fixture.
"""

from __future__ import annotations

from typing import Final

from mainline_recall_agent.rerank.payload import ExposureCue, RerankCandidate

__all__ = [
    "CANDIDATES",
    "EXPOSURE_A",
    "EXPOSURE_B",
    "REF_TO_DOC",
    "SCENARIOS",
    "exposure_for",
]

EXPOSURE_A: Final = ExposureCue(
    ref="EXP-A",
    activity_path="processing/leach/barren-circuit",
    asset_class="pipework-and-instrumentation",
    facets={
        "mechanism": "instrument work on a live barren solution circuit with the chemistry "
        "interlock placed in bypass for calibration",
        "precondition": "the barren line remains in service and shares a return header with "
        "the wash-water circuit; no positive isolation is proposed",
        "control_failure": "the interlock that prevents incompatible streams meeting is "
        "deliberately not protecting for the duration of the work",
        "recurrence_test": "any work that bypasses a chemistry interlock on a circuit sharing "
        "a header with an acidic stream",
    },
)

EXPOSURE_B: Final = ExposureCue(
    ref="EXP-B",
    activity_path="processing/comminution/mill-reline",
    asset_class="grinding-mill",
    facets={
        "mechanism": "entry into a grinding mill shell to replace liner bolts after an "
        "electrical isolation is applied and tested",
        "precondition": "the charge is not confirmed level and the isolation certificate "
        "names electrical supply only",
        "control_failure": "no independent verification that stored gravitational energy has "
        "been dissipated before entry",
    },
)

CANDIDATES: Final[tuple[RerankCandidate, ...]] = (
    RerankCandidate(
        doc_id="EVT-0001",
        fused_rank=1,
        activity_path="processing/leach/barren-circuit",
        asset_class="pipework-and-instrumentation",
        facets={
            "mechanism": "hydrogen cyanide liberated when acidic wash water met "
            "cyanide-bearing barren solution inside a shared return header",
            "precondition": "a shared return header with no positive isolation while the pH "
            "interlock was overridden for maintenance",
            "control_failure": "the chemistry interlock that prevents the two streams meeting "
            "was overridden and no alternative isolation was applied",
            "recurrence_test": "recall on any work that overrides a chemistry interlock on a "
            "circuit that shares a line with an acidic stream",
        },
        also_matched=("EVT-0044", "EVT-0071"),
    ),
    RerankCandidate(
        doc_id="EVT-0002",
        fused_rank=2,
        activity_path="processing/comminution/mill-reline",
        asset_class="grinding-mill",
        facets={
            "mechanism": "a mill shell rotated under the weight of an unbalanced charge while "
            "a reline crew was inside the envelope",
            "precondition": "an isolation certificate naming electrical supply only, with no "
            "verification that the charge had been levelled",
            "control_failure": "the isolation scope was silent on stored gravitational energy",
        },
    ),
    RerankCandidate(
        doc_id="EVT-0003",
        fused_rank=3,
        activity_path="processing/reagents/acid-unloading",
        asset_class="pipework-and-instrumentation",
        facets={
            "mechanism": "acid spray at a coupling when residual pressure was released on "
            "breaking containment",
            "precondition": "no means of verifying that the line had been depressurised before "
            "the coupling was broken",
            "narrative": "A maintainer broke a coupling on an unloading line believing it "
            "drained. Residual pressure remained and a spray of dilute acid reached the "
            "shoulder and neck. Treatment was given on site and the line was re-verified.",
        },
    ),
)

REF_TO_DOC: Final[dict[str, str]] = {
    "C01": "EVT-0001",
    "C02": "EVT-0002",
    "C03": "EVT-0003",
}

#: Every recorded scenario, by the exposure reference that keys its cassette. The exposure
#: is what varies between the two cache scenarios: the system prefix must be byte-identical
#: across them, and the user turn must not be, or the cache assertion proves nothing.
SCENARIOS: Final[tuple[str, ...]] = (
    "cache_call_one",
    "cache_call_two",
    "refusal",
    "repair",
    "dead_letter",
    "demotion",
    "omission",
)


def exposure_for(scenario: str) -> ExposureCue:
    """One exposure cue per scenario, differing only in its reference.

    Holding the facets constant and varying only the reference is what makes the cache
    assertion meaningful: the system prefix bytes are identical across the two cache
    scenarios and the user turn is not, which is precisely the condition a prompt cache is
    supposed to exploit.
    """
    if scenario not in SCENARIOS:
        raise KeyError(f"unknown rerank scenario {scenario!r}; known: {list(SCENARIOS)}")
    slug = scenario.upper().replace("_", "-")
    return ExposureCue(
        ref=f"EXP-{slug}",
        activity_path=EXPOSURE_A.activity_path,
        asset_class=EXPOSURE_A.asset_class,
        facets=dict(EXPOSURE_A.facets),
    )
