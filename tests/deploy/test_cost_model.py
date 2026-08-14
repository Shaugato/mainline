# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""The reproduction gate, and the falsification that proves the gate can go red.

WHAT THIS FILE IS FOR
=====================

`scripts/deploy/cost_model.py` publishes a cost bound. The only thing that makes a
published bound reviewable is that it re-derives a number somebody already checked, from
the inputs that produced it. So the first test here is not about the new figures at all:

    **A model that cannot reproduce the old answer has no standing to produce a new one.**

`test_the_model_reproduces_every_published_headline` re-derives all six published figures
-- `docs/deploy/COST-BOUND.md`'s $33,251.87 / $11,701 and $31,049.79 / $10,949, and
`docs/leads/cost-finish-plan.md`'s $33,271 / $11,713 -- from the historic inputs. Only after
that does anything here look at a new layer.

AND THE GATE MUST BE ABLE TO FAIL
---------------------------------

A reproduction check that passes no matter what is worse than none, because it launders an
unchecked model as a checked one. `test_falsification__moving_one_tariff_constant_turns_the
_reproduction_red` therefore moves ONE constant in the tariff at a time -- the $0.12 first
egress tier, the request rate, the arm64 GB-second rate -- and requires the reproduction to
go red for each. It also requires the mutation to be a real mutation (the guard against a
falsification that silently mutates nothing and "passes").

THE TOLERANCE QUESTION, ANSWERED RATHER THAN WIDENED
-----------------------------------------------------

The lead's independent run returned $33,271 / $11,713 against the document's
$33,252 / $11,701 -- 0.06 % and 0.10 % -- and expected "a small documented delta". There is
none. The gap is one input: the document tiers on decimal boundaries (10,000/50,000/150,000
GB) and the lead tiered on the boundaries the AWS Pricing API actually returns
(10,240/51,200/153,600). Both reproduce EXACTLY once the boundary is an explicit input, so
this file asserts exact agreement at each source's own published precision instead of
widening a tolerance until two different answers both fit inside it. That distinction is
the whole difference between a cross-check and a rubber stamp.
"""

from __future__ import annotations

import copy
import dataclasses
import json
import re
from pathlib import Path

import pytest

from scripts.deploy import cost_model as cm

REPO_ROOT = cm.REPO_ROOT

#: THE RATCHET'S APERTURE. Every doc-truth check in this file and in
#: `tests/deploy/test_docs_are_true.py` sweeps exactly this list, so the list IS the
#: aperture and shrinking it is the same move as lowering a floor.
#:
#: It held six paths until 2026-08-14, and **none of them was under `docs/submission/`**.
#: That hole was not theoretical: `docs/submission/RULES-MATRIX.md` carried a shipping plan
#: count of `11` that no committed artefact supported, in the same file that explains this
#: very ratchet, and the sweep could not see it. `docs/submission/JUDGING-AXES.md` still
#: does. A judge reads the submission directory FIRST; excluding it from the ratchet
#: inverted the priority.
#:
#: The rule for membership, so the next person does not have to guess: a document belongs
#: here if a reader takes it as CURRENT TRUTH about this repository's deploy or its
#: submission. Lead plans under `docs/leads/` and dated verification records under
#: `docs/verify/` and `docs/diagnosis/` are deliberately NOT here -- they are records of
#: what was true on a date, and a ratchet that demanded they be re-typed would be demanding
#: that history be falsified.
LIVE_DOCS = (
    # The deploy surface: what would be created, what it costs, how it is watched.
    "docs/deploy/COST-BOUND.md",
    "docs/deploy/JUDGE-PACK.md",
    "docs/deploy/LATENCY.md",
    "docs/deploy/OBSERVABILITY.md",
    "docs/deploy/PRE-APPLY.md",
    "docs/deploy/RUNBOOK.md",
    "docs/deploy/terraform-plan.md",
    "docs/deploy/cloud-database.md",
    "docs/deploy/console-build.md",
    "docs/deploy/gate-run-contract.md",
    "docs/deploy/lambda-bundle.md",
    "docs/deploy/replay-fallback.md",
    "docs/deploy/unproduced-tables.md",
    # The two top-level pages a reviewer opens before anything else.
    "docs/STATE-OF-THE-BUILD.md",
    "docs/TOOL-USAGE.md",
    # The submission directory. A judge starts here, so the ratchet must too.
    "docs/submission/DEVPOST.md",
    "docs/submission/RULES-MATRIX.md",
    "docs/submission/JUDGE-START.md",
    "docs/submission/JUDGING-AXES.md",
    "docs/submission/FIRST-FIVE-MINUTES.md",
    "docs/submission/PUBLIC-READINESS.md",
    "docs/submission/RUNBOOK.md",
)


def markdown_paragraphs(text: str) -> list[list[tuple[int, str]]]:
    """Blank-line-separated blocks of `(line number, line)`.

    Shared with `tests/deploy/test_docs_are_true.py`. Several exemptions below and there
    are scoped to a paragraph rather than a line for one measured reason: this repository
    wraps prose at ~95 columns, so a sentence and the correction that annotates it
    routinely land on different lines. A table row, by contrast, is one line, so for tables
    "same paragraph" and "same row" coincide.
    """
    blocks: list[list[tuple[int, str]]] = []
    current: list[tuple[int, str]] = []
    for number, line in enumerate(text.splitlines(), start=1):
        if line.strip():
            current.append((number, line))
        elif current:
            blocks.append(current)
            current = []
    if current:
        blocks.append(current)
    return blocks


def markdown_sections(text: str) -> list[list[tuple[int, str]]]:
    """Blocks delimited by ATX headings, each including its own heading line."""
    blocks: list[list[tuple[int, str]]] = []
    current: list[tuple[int, str]] = []
    for number, line in enumerate(text.splitlines(), start=1):
        if line.startswith("#") and current:
            blocks.append(current)
            current = []
        current.append((number, line))
    if current:
        blocks.append(current)
    return blocks


# ─────────────────────────────────────────────────────────────────────────────────────────
# 1. THE REPRODUCTION GATE. Everything else in this file is downstream of it.
# ─────────────────────────────────────────────────────────────────────────────────────────


def test_the_model_reproduces_every_published_headline():
    """All six published figures, from the inputs that produced them, to the digit."""
    result = cm.reproduce()

    failures = [
        f"{row['convention']} / {check['duration']}: "
        f"{check['published_by']} published {check['published_usd']:,.2f} "
        f"({check['published_decimals']} dp) and the model computes "
        f"{check['computed_usd']:,.4f}, delta {check['delta_usd']}"
        for row in result["conventions"]
        for check in row["checks"]
        if not check["agrees"]
    ]
    assert not failures, (
        "The model does not reproduce a figure this repository has already published:\n  "
        + "\n  ".join(failures)
        + "\nA model that cannot reproduce the old answer has no standing to produce a new "
        "one. Do NOT relax the expectation to make this pass -- the expectations are the "
        "published documents and they are the authoritative side."
    )
    assert result["ok"] is True


def test_the_reproduction_covers_all_three_gb_conventions():
    """Three self-consistent readings of "GB" exist and prior work used all three.

    A single-convention reproduction would be a coincidence dressed as a check: it would
    pass while the other two readings, both of which have been quoted in this repository,
    silently disagreed.
    """
    result = cm.reproduce()
    covered = {row["convention"] for row in result["conventions"]}
    assert covered == {"audit-decimal", "decimal-gb-api-tiers", "binary-gb-api-tiers"}

    totals = {
        row["convention"]: row["checks"][0]["computed_usd"] for row in result["conventions"]
    }
    # They must actually differ, or the "three conventions" claim is decoration.
    assert len(set(round(v) for v in totals.values())) == 3, totals


def test_the_0_06_percent_delta_is_explained_rather_than_absorbed():
    """The lead's figure and the document's figure BOTH reproduce exactly.

    This is the test that would have caught the tempting shortcut: widening the tolerance
    to 0.1 % so that one model "reproduces" two different answers. Under that shortcut both
    conventions would compute the same number and this assertion fails.
    """
    audit = cm.price(
        cm.historic_flood(100.0), cm.CONVENTIONS["audit-decimal"], apply_free_tier=False
    )
    lead = cm.price(
        cm.historic_flood(100.0), cm.CONVENTIONS["decimal-gb-api-tiers"], apply_free_tier=False
    )
    assert round(audit.total_usd, 2) == 33_251.87
    assert round(lead.total_usd, 2) == 33_271.07
    assert audit.total_usd != lead.total_usd, (
        "The two conventions produced the same total, so the tier-boundary input is not "
        "actually being applied and the 'explained delta' claim is unsupported."
    )
    # And the explanation must be a difference in TIER EDGES, not in anything else.
    assert (
        cm.CONVENTIONS["audit-decimal"].bytes_per_gb
        == cm.CONVENTIONS["decimal-gb-api-tiers"].bytes_per_gb
    )
    assert (
        cm.CONVENTIONS["audit-decimal"].tier_edges_gb
        != cm.CONVENTIONS["decimal-gb-api-tiers"].tier_edges_gb
    )


# ─────────────────────────────────────────────────────────────────────────────────────────
# 2. THE FALSIFICATION. The gate above must be able to go red.
# ─────────────────────────────────────────────────────────────────────────────────────────

#: Each entry moves ONE tariff field. The multiplier is chosen large enough that no
#: rounding at any published precision could hide it, and the test asserts separately that
#: the mutation actually changed the object.
TARIFF_MUTATIONS = {
    "first_egress_tier_0.120_to_0.132": {"egress_usd_per_gb": (0.132, 0.085, 0.082, 0.080)},
    "last_egress_tier_0.080_to_0.088": {"egress_usd_per_gb": (0.120, 0.085, 0.082, 0.088)},
    "request_rate_0.20_to_0.22_per_million": {"request_usd_per_million": 0.22},
    "arm64_gb_second_rate_up_10_percent": {"gb_second_usd_arm64": 0.0000146667},
}


@pytest.mark.parametrize("name", sorted(TARIFF_MUTATIONS))
def test_falsification__moving_one_tariff_constant_turns_the_reproduction_red(name):
    """Move one published rate; the reproduction must fail.

    If this passes with a mutated tariff, the reproduction gate is not reading the tariff
    and every figure it certifies is uncertified.
    """
    mutated = dataclasses.replace(cm.TARIFF, **TARIFF_MUTATIONS[name])

    # Guard: a falsification that mutates nothing proves nothing.
    assert mutated != cm.TARIFF, (
        f"mutation {name!r} produced an identical tariff, so the assertion below would "
        "pass for the wrong reason"
    )

    assert cm.reproduce(cm.TARIFF)["ok"] is True, "baseline must be green before mutating"

    result = cm.reproduce(mutated)
    assert result["ok"] is False, (
        f"The tariff constant {name} was moved and the reproduction gate STAYED GREEN. "
        "That means the gate is not actually reading the tariff, so its agreement with "
        "the published headline is a coincidence and certifies nothing."
    )


def test_falsification__a_broken_tariff_stops_the_model_publishing_any_new_figure():
    """The ordering claim: the gate runs BEFORE new figures, not beside them."""
    broken = dataclasses.replace(cm.TARIFF, egress_usd_per_gb=(0.99, 0.99, 0.99, 0.99))
    model = cm.build_model(broken)
    assert model["ok"] is False
    assert model["layers"] is None, (
        "The model emitted layer figures while its reproduction gate was red. A new number "
        "published under a failed reproduction is exactly what this file exists to prevent."
    )
    assert "no standing" in model["refused"]


# ─────────────────────────────────────────────────────────────────────────────────────────
# 3. THE ARITHMETIC, cross-checked against an independent implementation.
# ─────────────────────────────────────────────────────────────────────────────────────────


def _tier_cost_naive(gb: float, edges, rates) -> float:
    """A deliberately dumb second implementation: walk the volume in 1 GB steps.

    Slow and obviously correct, which is the point of a cross-check. Used on small volumes
    only, where the step size cannot hide a boundary error.
    """
    total = 0.0
    remaining = gb
    position = 0.0
    bounds = list(edges) + [float("inf")]
    for index, rate in enumerate(rates):
        upper = bounds[index]
        while remaining > 0 and position < upper:
            step = min(1.0, remaining, upper - position)
            total += step * rate
            remaining -= step
            position += step
        if remaining <= 0:
            break
    return total


@pytest.mark.parametrize("gb", [0.0, 1.0, 9_999.0, 10_000.0, 10_001.0, 50_000.0, 60_000.0])
def test_the_tiering_agrees_with_an_independent_implementation(gb):
    convention = cm.CONVENTIONS["audit-decimal"]
    usd, billable, _ = cm.egress_cost_usd(
        gb * convention.bytes_per_gb, convention, apply_free_tier=False
    )
    assert billable == pytest.approx(gb)
    naive = _tier_cost_naive(gb, convention.tier_edges_gb, cm.TARIFF.egress_usd_per_gb)
    assert usd == pytest.approx(naive, abs=0.01)


def test_the_free_tier_applies_only_where_the_convention_declares_it():
    binary = cm.CONVENTIONS["binary-gb-api-tiers"]
    assert binary.free_gb_per_month == 100.0
    assert cm.CONVENTIONS["audit-decimal"].free_gb_per_month == 0.0
    with_free, gb_with, _ = cm.egress_cost_usd(
        200 * binary.bytes_per_gb, binary, apply_free_tier=True
    )
    without, gb_without, _ = cm.egress_cost_usd(
        200 * binary.bytes_per_gb, binary, apply_free_tier=False
    )
    assert gb_with == pytest.approx(100.0)
    assert gb_without == pytest.approx(200.0)
    assert without > with_free


def test_a_429_is_still_a_billed_invocation():
    """The floor the rate limiter cannot go below, asserted rather than described.

    A rate limiter collapses egress and leaves requests + compute exactly where they were.
    If this ever stops holding, someone has modelled a 429 as free and the rate-bound layer
    is understated.
    """
    common = dict(
        concurrency=10, duration_ms=5.66, request_bytes=124_127, memory_mb=256, window_s=2_592_000
    )
    unbounded = cm.price(cm.Flood(label="a", **common), cm.CONVENTIONS["audit-decimal"])
    bounded = cm.price(
        cm.Flood(label="b", served_rps_cap=100.0, refused_bytes=233, **common),
        cm.CONVENTIONS["audit-decimal"],
    )
    assert bounded.requests_usd == pytest.approx(unbounded.requests_usd)
    assert bounded.compute_usd == pytest.approx(unbounded.compute_usd)
    assert bounded.egress_usd < unbounded.egress_usd / 10


# ─────────────────────────────────────────────────────────────────────────────────────────
# 4. THE NEW FIGURES: what the model must say about itself.
# ─────────────────────────────────────────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def model():
    built = cm.build_model()
    assert built["ok"] is True
    return built


def test_the_model_labels_itself_a_bound_and_names_the_unobserved_assumption(model):
    """The caveat must be in the payload, not in a source comment.

    A model bound that is only labelled in prose gets quoted without its label the first
    time somebody reads the JSON.
    """
    bound = model["model_bound"]
    assert bound["this_is_a_bound_not_a_forecast"] is True
    assumption = bound["the_assumption_that_makes_it_a_bound"]
    assert "GB/s" in assumption
    assert "NOBODY HAS OBSERVED" in assumption
    assert "not what AWS would deliver" in assumption

    # And the assumption must be the real one: >= 1 GB/s at the measured map duration.
    measured_layer = next(
        r
        for r in model["conventions"][cm.HEADLINE_CONVENTION]["layers"]
        if r["label"] == "L1-measured-duration"
    )
    assert measured_layer["sustained_egress_bytes_per_second"] > 1e9


def test_the_headline_is_a_floor_understated_about_sevenfold(model):
    """The finding this wave exists for, asserted as a relationship not a literal."""
    layers = {
        r["label"]: r["total_usd"] for r in model["conventions"][cm.HEADLINE_CONVENTION]["layers"]
    }
    ratio = layers["L1-measured-duration"] / layers["L0-modelled-100ms"]
    assert 6.0 < ratio < 8.0, (
        f"the measured-duration bill is {ratio:.2f}x the modelled-100ms headline; the "
        "documented finding is 'about 7x'"
    )


def test_the_byte_levers_are_visibly_self_limiting(model):
    """Bytes fall much faster than the bill, and the table must show that.

    This is the property a reader will not believe unless the numbers are beside each
    other: the strip cut bytes 3.59x and the bill 1.43x.
    """
    s = model["self_limiting_byte_levers"]
    assert s["bytes_fell_by"] > 3.0
    assert s["request_rate_rose_by"] > 2.0
    assert s["bill_fell_by"] < 2.0
    assert s["bill_fell_by"] < s["bytes_fell_by"] / 2, (
        "the bill fell nearly as fast as the bytes, which would contradict the "
        "self-limiting finding this row exists to publish"
    )


def test_both_gb_conventions_are_published_for_every_layer(model):
    """"Both GB conventions" is a deliverable, not a footnote."""
    for name in ("audit-decimal", "decimal-gb-api-tiers", "binary-gb-api-tiers"):
        layers = model["conventions"][name]["layers"]
        assert len(layers) >= 6
        assert all(r["total_usd"] > 0 for r in layers)
    audit = {r["label"]: r["total_usd"] for r in model["conventions"]["audit-decimal"]["layers"]}
    binary = {
        r["label"]: r["total_usd"] for r in model["conventions"]["binary-gb-api-tiers"]["layers"]
    }
    assert audit.keys() == binary.keys()
    assert audit["L0-modelled-100ms"] != binary["L0-modelled-100ms"]


def test_the_duration_sensitivity_band_spans_measured_to_modelled(model):
    band = {row["label"]: row for row in model["duration_sensitivity"]["band"]}
    assert {"measured-local-p50", "measured-cloud-p50", "modelled-100ms", "modelled-300ms"} <= (
        band.keys()
    )
    # 1/duration: a faster invocation must cost MORE, not less.
    assert band["measured-local-p50"]["total_usd"] > band["modelled-100ms"]["total_usd"]
    assert band["modelled-100ms"]["total_usd"] > band["modelled-300ms"]["total_usd"]
    assert model["duration_sensitivity"]["spread_factor"] > 10


# ─────────────────────────────────────────────────────────────────────────────────────────
# 5. THE RESIDUAL. The number the wave is actually arguing about.
# ─────────────────────────────────────────────────────────────────────────────────────────


def test_the_residual_is_computed_at_the_hourly_alarm_threshold_not_at_flood_rate(model):
    """A caller under the alarm is by definition not at flood rate.

    Quoting the flood-rate figure as the residual overstates it by two orders of magnitude
    and describes a caller the burst alarm catches in the first minute.
    """
    residual = model["residual"]
    hourly = residual["hourly"]
    expected_rps = hourly["threshold"] / hourly["period_s"]

    assert residual["paced_at_requests_per_second"] == pytest.approx(expected_rps, rel=1e-6)
    assert residual["binding_alarm"] == "hourly"
    assert residual["paced_at_requests_per_second"] < residual["burst"]["implied_rps"], (
        "the hourly alarm must be the binding one for a slow burner; if the burst alarm "
        "binds instead, the residual is being computed at the wrong line"
    )

    # And the residual must be dramatically below the flood-rate figure it replaces.
    assert residual["worst_usd"] < residual["flood_rate_24h_for_contrast_usd"] / 50, (
        f"residual {residual['worst_usd']} is not far enough below the flood-rate figure "
        f"{residual['flood_rate_24h_for_contrast_usd']} for the distinction to be the "
        "point it is published as"
    )


def test_the_residual_publishes_both_the_reachable_and_the_lifted_ceiling_case(model):
    """The residual depends on a code constant, so it publishes what happens if it moves.

    `static_site.DEFAULT_MAX_RESPONSE_BYTES` currently refuses the 433 KB identity asset,
    which is why the reachable residual is the gzip sibling. That is one commit away from
    being false. A residual that published only the reachable row would understate itself
    by ~3.5x the moment the ceiling was raised, and nothing would say so -- so both rows
    ship, each flagged with whether the ceiling in force admits it.
    """
    residual = model["residual"]
    rows = residual["rows"]
    assert {row["object"] for row in rows} == {"identity", "gzip-sibling"}
    assert all("reachable_under_the_ceiling_in_force" in row for row in rows)

    # The ceiling must be READ from static_site.py, not carried as a copy.
    assert residual["response_ceiling_in_force_bytes"] == cm.response_ceiling_in_force()

    # Reachability must actually follow the ceiling rather than being a decorative flag.
    ceiling = residual["response_ceiling_in_force_bytes"]
    for row in rows:
        assert row["reachable_under_the_ceiling_in_force"] == (row["object_bytes"] <= ceiling)

    # The headline is the worst REACHABLE row; the counterfactual is published beside it.
    reachable = [r for r in rows if r["reachable_under_the_ceiling_in_force"]]
    assert reachable, "no residual row is reachable, which the model should have refused"
    assert residual["worst_usd"] == max(r["total_usd"] for r in reachable)
    assert residual["worst_if_the_ceiling_were_lifted_usd"] >= residual["worst_usd"]
    assert "ceiling_dependency" in residual


def test_the_residual_prices_both_edges_of_the_budgets_lag(model):
    lags = {row["lag_hours"] for row in model["residual"]["rows"]}
    assert lags == {8.0, 24.0}


def test_the_availability_trade_is_in_the_residual_and_not_a_footnote(model):
    """The stop converts a cost attack into an availability attack. Say so where it counts.

    `authorization_type = NONE` is the founder's explicit choice, so anyone at all can trip
    the burst alarm and stop the demo for everyone. That is the right trade and it is still
    a trade; burying it in a footnote is how a trade becomes a surprise.
    """
    trade = model["residual"]["the_trade_this_makes"]
    assert "COST ATTACK INTO AN AVAILABILITY ATTACK" in trade.upper()
    assert "authorization_type = NONE" in trade
    assert "kill_switch" in trade
    assert "--restore" in trade


def test_the_stop_is_not_priced_downstream_of_the_rate_limiter(model):
    """The rate limiter is per-instance with no shared store, so a distributed flood beats it.

    Pricing the stop downstream of a lever a distributed attacker defeats would understate
    the stop's value and, worse, would credit the rate limiter with holding when it does
    not.
    """
    stop = model["the_stop"]
    assert "distributed flood defeats it" in stop["why_not_downstream_of_the_rate_bound"]
    five_min = next(r for r in stop["rows"] if r["label"] == "stop-5min")
    one_hour = next(r for r in stop["rows"] if r["label"] == "stop-1h")
    assert one_hour["total_usd"] > five_min["total_usd"] * 10


# ─────────────────────────────────────────────────────────────────────────────────────────
# 6. RATCHETS. The model must follow its inputs, and the docs must follow the evidence.
# ─────────────────────────────────────────────────────────────────────────────────────────


def test_the_thresholds_the_model_prices_are_the_thresholds_terraform_declares(model):
    """If W4 moves an alarm threshold, this goes red rather than the model going stale.

    The residual is computed FROM the hourly threshold. A model carrying a copy of that
    number would keep publishing a residual for a line the stack no longer has.
    """
    guard_vars = cm.COST_GUARD_VARIABLES.read_text(encoding="utf-8")
    guard_main = cm.COST_GUARD_MAIN.read_text(encoding="utf-8")

    declared_hourly = cm.terraform_variable_default(guard_vars, "invocations_hourly_threshold")
    declared_burst = cm.terraform_variable_default(guard_vars, "invocations_burst_threshold")
    declared_hourly_period = cm.terraform_alarm_period(guard_main, "invocations_hourly")
    declared_burst_period = cm.terraform_alarm_period(guard_main, "invocations_burst")

    assert None not in (
        declared_hourly,
        declared_burst,
        declared_hourly_period,
        declared_burst_period,
    ), "a threshold or period could not be read out of infra/modules/cost-guard"

    residual = model["residual"]
    assert residual["hourly"]["threshold"] == declared_hourly
    assert residual["hourly"]["period_s"] == declared_hourly_period
    assert residual["burst"]["threshold"] == declared_burst
    assert residual["burst"]["period_s"] == declared_burst_period


def test_the_measured_inputs_come_from_evidence_and_not_from_literals(model):
    """Every byte count and duration the new layers price must be traceable to a file."""
    inputs = model["inputs"]
    package = json.loads(cm.PACKAGE_SHAPE.read_text(encoding="utf-8"))
    arm64 = next(a for a in package["architectures"] if a["architecture"] == "arm64")

    assert (
        inputs["package_shape"]["after_largest_gz_bytes"]
        == arm64["after"]["web"]["largest_gz_object"]["bytes"]
    )
    assert (
        inputs["package_shape"]["before_largest_identity_bytes"]
        == arm64["before"]["web"]["largest_identity_object"]["bytes"]
    )

    latency = json.loads(cm.LATENCY_BASELINE.read_text(encoding="utf-8"))
    beats = latency["targets"]["local"]["beats"]
    assert inputs["latency"]["asset_js_p50_ms"] == beats["asset_js"]["wall_ms"]["p50_ms"]
    assert inputs["latency"]["asset_map_p50_ms"] == beats["asset_map"]["wall_ms"]["p50_ms"]


def test_the_source_maps_are_gone_from_the_artefact(model):
    """"18 source maps still shipping" is false, and the model prices it as false.

    The strip is the default in both builders and the artefact confirms it. If a map ever
    returns to the package this goes red, which is the only way the claim stays true.
    """
    shape = model["inputs"]["package_shape"]
    assert shape["before_source_map_entries"] == 18
    assert shape["after_source_map_entries"] == 0
    assert shape["after_largest_identity_bytes"] < shape["before_largest_identity_bytes"]


def test_the_committed_model_matches_what_the_program_produces(model):
    """The evidence file is regenerated, never hand-edited.

    `docs/leads/cost-finish-plan.md` §1 names hand-editing recorded evidence as the second
    trap of this wave. This test is the tripwire for it: if somebody adjusts a figure in
    the JSON, it stops matching the program that claims to have produced it.
    """
    committed = json.loads(cm.OUTPUT.read_text(encoding="utf-8"))
    fresh = copy.deepcopy(model)
    assert committed["schema"] == cm.SCHEMA
    assert committed["reproduction"]["ok"] is True

    committed_layers = committed["conventions"][cm.HEADLINE_CONVENTION]["layers"]
    fresh_layers = fresh["conventions"][cm.HEADLINE_CONVENTION]["layers"]
    assert [r["label"] for r in committed_layers] == [r["label"] for r in fresh_layers]
    for c, f in zip(committed_layers, fresh_layers):
        assert c["total_usd"] == pytest.approx(f["total_usd"], abs=0.01), (
            f"committed {c['label']} = {c['total_usd']} but the program computes "
            f"{f['total_usd']}. Regenerate with `python scripts/deploy/cost_model.py`; do "
            "not edit the JSON."
        )
    assert committed["residual"]["worst_usd"] == pytest.approx(
        fresh["residual"]["worst_usd"], abs=0.01
    )


def test_the_evidence_file_carries_its_reuse_license_sidecar():
    sidecar = cm.OUTPUT.with_suffix(cm.OUTPUT.suffix + ".license")
    assert sidecar.exists(), f"{sidecar} is missing"
    text = sidecar.read_text(encoding="utf-8")
    assert "SPDX-License-Identifier:" in text


# ─────────────────────────────────────────────────────────────────────────────────────────
# 7. THE DOCUMENT RATCHET.
# ─────────────────────────────────────────────────────────────────────────────────────────

#: What a `terraform plan` transcript actually prints. Used to read the AUTHORITATIVE side
#: -- the committed artefacts -- because that is the only form they emit.
_PLAN_COUNT_VERBATIM = re.compile(r"Plan:\s*(\d+)\s*to add")

#: What a DOCUMENT may write, which is not the same thing. The `Plan:` prefix was optional
#: all along and nobody had noticed: `docs/submission/RULES-MATRIX.md` wrote the shipping
#: count as `committed: 11 to add, 0 to change, 0 to destroy` with no prefix, and the
#: ratchet read straight past it. A pattern that only catches the count when it is written
#: in one particular way is a pattern that teaches authors which spelling is unchecked.
#:
#: The negative lookbehind keeps `1,024 to add` and version-like `1.11 to add` out; the
#: count is a bare integer in both the artefact and every document that quotes it.
_PLAN_COUNT = re.compile(r"(?<![\d.,])(\d+)\s+to add\b")

#: The ONE documented exception, and it is narrow on purpose.
#:
#: `docs/deploy/terraform-plan.md` §5 tabulates four `enable_cloudfront`/`enable_api`
#: configurations, all re-run with real credentials on 2026-08-13. Two of them have
#: committed artefacts (11 for the shipping default, 22 for CloudFront); the site-only
#: variant was measured but its artefact was never committed, so its count is supported by
#: the document's own measurement note and by nothing in `evidence/`.
#:
#: The exception is keyed to that row's own words rather than to a count or a line number,
#: so it cannot be reused to launder a stale SHIPPING count: smuggling one through would
#: require writing "site with no API" next to it.
_UNARTEFACTED_VARIANT_MARKER = "site with no API"


def _plan_counts_supported_by_evidence() -> dict[int, list[str]]:
    """Every plan count any committed plan artefact currently reports."""
    supported: dict[int, list[str]] = {}
    for path in sorted((REPO_ROOT / "evidence").rglob("terraform-plan-*.txt")):
        for found in _PLAN_COUNT_VERBATIM.findall(
            path.read_text(encoding="utf-8", errors="replace")
        ):
            supported.setdefault(int(found), []).append(
                str(path.relative_to(REPO_ROOT)).replace("\\", "/")
            )
    assert supported, "no committed terraform plan artefact reports a resource count"
    return supported


def stale_plan_counts(relative: str, text: str, supported: set[int]) -> list[str]:
    """Every line in one document that quotes a count no committed artefact reports.

    A pure function over `(path, text, supported)` on purpose: the falsification tests
    below drive it with SYNTHETIC documents, which is the only way to show it going red for
    the right reason. A ratchet that has only ever been observed returning `[]` is
    indistinguishable from `return []`.
    """
    stale: list[str] = []
    for paragraph in markdown_paragraphs(text):
        blob = " ".join(line for _, line in paragraph)
        # The correction must be ADJACENT to the claim it corrects, because that is the
        # only place a reader looks for it. `Plan: 24` counts even without `to add`.
        corrected_here = (
            bool({int(f) for f in _PLAN_COUNT.findall(blob)} & supported)
            or bool({int(f) for f in _PLAN_COUNT_VERBATIM.findall(blob)} & supported)
            or any(int(f) in supported for f in re.findall(r"Plan:\s*(\d+)", blob))
        )
        for number, line in paragraph:
            if _UNARTEFACTED_VARIANT_MARKER in line:
                continue
            for found in _PLAN_COUNT.findall(line):
                if int(found) in supported or corrected_here:
                    continue
                stale.append(
                    f"{relative}:{number} says '{found} to add', which no committed plan "
                    f"artefact reports, and no line in its paragraph states a count that "
                    f"one does"
                )
    return stale


def test_the_shipping_plan_count_in_the_docs_matches_the_plan_evidence():
    """No live document may quote a resource count no committed artefact supports.

    THIS IS THE RATCHET THAT REPLACES A PREDICTION. W5 instantiates `module "guard"`, which
    moves the shipping count off 11. Nobody in this wave may guess the new number -- so
    instead of writing one, every live claim is tied to the committed plan artefacts. The
    moment W5 regenerates `evidence/deploy/terraform-plan-furl.txt`, 11 stops being
    supported by anything and this test goes red naming every document that still says it.

    A doc claim that disagrees with the evidence is stale whether or not anybody noticed,
    and the fix is ALWAYS to re-read the regenerated evidence -- never to edit the evidence
    to match the doc.

    TWO APERTURE GAPS CLOSED ON 2026-08-14, both measured rather than supposed:

    1. `LIVE_DOCS` held no `docs/submission/` file, so a stale count in the very directory
       a judge opens first was invisible here.
    2. `_PLAN_COUNT` required the literal prefix `Plan:`, and `RULES-MATRIX.md` wrote its
       count without one. Widening the list alone would still have missed it.

    THE HISTORY EXEMPTION, and why it cannot launder a stale count. The preservation rule
    requires a superseded claim to be *"struck through or annotated in place, never
    removed"*, so a document that says *"this bullet said `11 to add` until 2026-08-14"* is
    obeying the rules, not breaking them. Such a line is exempt only when the SAME
    PARAGRAPH also states a count a committed artefact supports -- the correction must be
    adjacent to the claim it corrects, because that is the only place a reader will find
    it. A stale count is precisely one whose paragraph never states the supported number,
    so the exemption cannot be used to smuggle one through; and the supported set is read
    from `evidence/` at run time, so when the artefact moves the exemption stops matching
    and every annotated paragraph is re-read.
    """
    supported = _plan_counts_supported_by_evidence()
    stale: list[str] = []
    for relative in LIVE_DOCS:
        path = REPO_ROOT / relative
        if not path.exists():
            continue
        stale.extend(
            stale_plan_counts(
                relative, path.read_text(encoding="utf-8", errors="replace"), set(supported)
            )
        )

    assert not stale, (
        "The committed plan artefacts report "
        + ", ".join(
            f"{count} ({'; '.join(sorted(set(where)))})"
            for count, where in sorted(supported.items())
        )
        + ".\nThese live claims quote a count nothing supports:\n  "
        + "\n  ".join(stale)
        + "\nRe-read the regenerated plan evidence and correct the documents. Do NOT edit "
        "the evidence file to match the documents."
    )


def test_falsification__a_count_written_without_the_plan_prefix_is_still_caught():
    """The measured aperture gap, synthesised. This is why `_PLAN_COUNT` was widened.

    `docs/submission/RULES-MATRIX.md` wrote its shipping count as
    `committed: 11 to add, 0 to change, 0 to destroy` -- no `Plan:` prefix -- and the old
    pattern read straight past it. Widening `LIVE_DOCS` alone would not have caught it, so
    both had to move, and both are asserted here rather than described.
    """
    supported = set(_plan_counts_supported_by_evidence())
    unsupported = max(supported) + 1_000  # cannot collide with a real artefact count

    prefixed = f"The stack plans `Plan: {unsupported} to add, 0 to change, 0 to destroy`.\n"
    bare = f"committed: {unsupported} to add, 0 to change, 0 to destroy\n"
    for label, fragment in (("with the prefix", prefixed), ("without it", bare)):
        assert stale_plan_counts("synthetic.md", fragment, supported), (
            f"a count of {unsupported} written {label} was not caught, so a document can "
            "quote a resource count no committed artefact supports simply by choosing a "
            "spelling. The committed plan artefact is the authoritative side."
        )

    # And a SUPPORTED count in either spelling must not be flagged, or the checker is
    # banning the sentence rather than checking the number.
    real = min(supported)
    assert not stale_plan_counts("synthetic.md", f"the plan is {real} to add today\n", supported)


def test_falsification__the_unartefacted_variant_exemption_cannot_launder_a_stale_count():
    """The one documented exception stays narrow, and this is what keeps it narrow.

    `terraform-plan.md` §5 tabulates a `site with no API` variant whose count was measured
    but whose artefact was never committed. The exemption is keyed to that row's own words,
    so smuggling a stale SHIPPING count through it would require writing "site with no API"
    beside it -- which is a lie a reader can see. This test asserts both halves: the marker
    still exempts its own row, and removing the marker un-exempts it.
    """
    supported = set(_plan_counts_supported_by_evidence())
    unsupported = max(supported) + 1_000

    exempt = (
        f"| `true` | `false` | `Plan: {unsupported} to add` -- {_UNARTEFACTED_VARIANT_MARKER} |\n"
    )
    assert not stale_plan_counts("synthetic.md", exempt, supported), (
        "the documented `site with no API` exemption stopped working, so the one variant "
        "this repository measured without committing an artefact now fails the ratchet. "
        "Re-read docs/deploy/terraform-plan.md §5 before touching this."
    )

    without_marker = exempt.replace(f" -- {_UNARTEFACTED_VARIANT_MARKER}", "")
    assert stale_plan_counts("synthetic.md", without_marker, supported), (
        "the same row without its marker was still exempt, so the exemption is not keyed "
        "to the row's own words and could be used to launder a stale shipping count."
    )


def test_falsification__an_annotated_history_needs_its_correction_in_the_same_paragraph():
    """The preservation rule is honoured, and it is not a free pass.

    A document MUST be able to say *"this bullet said `11 to add` until 2026-08-14"* -- the
    preservation rule requires the superseded claim to stay visible. It may do so only
    where the correction is adjacent, because a correction a reader never reaches is not a
    correction. This control asserts the exemption exists AND that it evaporates when the
    supported count is not in the same paragraph.
    """
    supported = set(_plan_counts_supported_by_evidence())
    unsupported = max(supported) + 1_000
    real = min(supported)

    adjacent = (
        f"The plan reads `Plan: {real} to add, 0 to change, 0 to destroy`.\n"
        f"*This bullet said `{unsupported} to add` until 2026-08-14.*\n"
    )
    assert not stale_plan_counts("synthetic.md", adjacent, supported), (
        "a superseded count recorded beside its correction was flagged, which would push "
        "an author to DELETE the history. A claim deleted is not a claim corrected."
    )

    orphaned = (
        f"The plan reads `Plan: {real} to add, 0 to change, 0 to destroy`.\n\n"
        f"*This bullet said `{unsupported} to add` until 2026-08-14.*\n"
    )
    assert stale_plan_counts("synthetic.md", orphaned, supported), (
        "the same history in a paragraph of its own was exempt, so the exemption reaches "
        "across the whole document and any stale count anywhere in a file that states the "
        "right one once would be laundered."
    )


def test_the_shipping_plan_count_is_actually_stated_somewhere_live():
    """The ratchet above only catches WRONG counts. This catches a vanished one.

    Deleting the sentence is the cheapest way to make a stale-claim test pass, so the
    shipping count must remain present in at least one live document.
    """
    shipping = {
        int(c)
        for c in _PLAN_COUNT_VERBATIM.findall(
            cm.PLAN_EVIDENCE.read_text(encoding="utf-8", errors="replace")
        )
    }
    assert len(shipping) == 1, f"{cm.PLAN_EVIDENCE} reports more than one count: {shipping}"
    expected = shipping.pop()

    stated_in = [
        relative
        for relative in LIVE_DOCS
        if (REPO_ROOT / relative).exists()
        and any(
            int(found) == expected
            for found in _PLAN_COUNT.findall(
                (REPO_ROOT / relative).read_text(encoding="utf-8", errors="replace")
            )
        )
    ]
    assert stated_in, (
        f"the shipping plan is 'Plan: {expected} to add' per "
        f"{cm.PLAN_EVIDENCE.relative_to(REPO_ROOT)}, and no live document says so. A claim "
        "deleted is not a claim corrected."
    )


def test_line_references_into_the_plan_evidence_point_at_the_plan_line():
    """`... at line N` must actually be the line.

    Added because this exact reference had drifted to 339 against a real line of 336 -- the
    kind of rot that is invisible until a reviewer follows the citation, finds an unrelated
    line, and stops trusting the rest of the document.

    WIDENED 2026-08-14 for the same reason `_PLAN_COUNT` was: the pattern required the word
    `at` and an 80-character window, and `docs/submission/JUDGING-AXES.md` writes the
    citation as ``line `339` `` after a full markdown link to the artefact -- which is
    roughly 120 characters on its own. A pattern that only sees one phrasing does not check
    the citation; it checks the phrasing, and it teaches authors which phrasing is
    unwatched. The window was measured, not guessed: 160 catches that citation and 200
    catches nothing further in any live document.
    """
    plan_lines = cm.PLAN_EVIDENCE.read_text(encoding="utf-8", errors="replace").splitlines()
    real = [n for n, line in enumerate(plan_lines, start=1) if _PLAN_COUNT_VERBATIM.search(line)]
    assert len(real) == 1, f"expected one plan-count line in {cm.PLAN_EVIDENCE}, found {real}"

    cited = re.compile(r"Plan:\s*\d+\s*to add[^\n]{0,160}?\bline\s*`?(\d+)`?")
    wrong: list[str] = []
    for relative in LIVE_DOCS:
        path = REPO_ROOT / relative
        if not path.exists():
            continue
        for number, line in enumerate(
            path.read_text(encoding="utf-8", errors="replace").splitlines(), start=1
        ):
            for found in cited.findall(line):
                if int(found) != real[0]:
                    wrong.append(f"{relative}:{number} cites line {found}, actual {real[0]}")
    assert not wrong, "stale line references into the plan evidence:\n  " + "\n  ".join(wrong)


def test_no_live_document_still_claims_the_two_mebibyte_ceiling():
    """`DEFAULT_MAX_RESPONSE_BYTES` has not been 2 MiB for a wave.

    A ceiling quoted at the wrong value is worse than no ceiling quoted, because a reader
    checks their asset against 2 MiB, ships it, and the handler answers 413.
    """
    in_force = cm.response_ceiling_in_force()
    assert in_force != 2 * 1024 * 1024, (
        "the ceiling really is 2 MiB again; this test's premise is gone and the docs "
        "should be re-read rather than this assertion adjusted"
    )

    # A line may MENTION 2 MiB -- the history is worth keeping -- but only if the same line
    # also states the value actually in force. That exemption cannot launder a stale claim,
    # because a stale claim is precisely one that does not carry the current number, and it
    # cannot rot either: when the ceiling moves again, the exempting text stops matching.
    in_force_forms = (f"{in_force:,}", str(in_force), f"{in_force // 1024} KiB")
    pattern = re.compile(r"DEFAULT_MAX_RESPONSE_BYTES[^|\n]{0,60}?\b2\s*MiB", re.IGNORECASE)

    offenders: list[str] = []
    for relative in LIVE_DOCS:
        path = REPO_ROOT / relative
        if not path.exists():
            continue
        for number, line in enumerate(
            path.read_text(encoding="utf-8", errors="replace").splitlines(), start=1
        ):
            if not pattern.search(line):
                continue
            if any(form in line for form in in_force_forms):
                continue  # states the ceiling in force on the same line: a history note
            offenders.append(f"{relative}:{number}: {line.strip()[:120]}")

    assert not offenders, (
        f"static_site.DEFAULT_MAX_RESPONSE_BYTES is {in_force:,} B and these live claims "
        "still say 2 MiB without stating it:\n  " + "\n  ".join(offenders)
    )
