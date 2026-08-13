# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""The IN-WINDOW residual: what a flood spends before the stop lands, and how it is bounded.

WHAT THIS FILE IS FOR
=====================

`tests/deploy/test_cost_model.py` is the referee for the whole cost model and is not
touched here. This file guards exactly one new thing: `residual.in_window`, the answer to
a question nobody in this repository had priced -- **how much can be spent INSIDE one
CloudWatch alarm evaluation window, before `PutFunctionConcurrency(0)` takes effect?**

THE FAILURE MODE THESE CONTROLS EXIST TO CATCH
-----------------------------------------------

The published USD 33,251.87 headline was wrong because it multiplied a real tariff by a
100 ms invocation duration **nobody had measured**. The identical mistake was available
here in an identical shape: publish `60 s x rate` and call it the residual. That silently
sets **every** term between the CloudWatch period closing and the stop taking effect --
metric publication, alarm evaluation, SNS delivery, responder cold start, reserved
concurrency propagation -- to **zero seconds**, which nobody has measured either.

So the model publishes a RATE and a LAG BUDGET, and these tests hold it to that:

* `test_the_detection_floor_is_read_out_of_the_hcl_and_not_a_literal` and
  `test_the_first_alarm_to_fire_is_derived_and_not_named` mutate the Terraform and require
  the published figure to move.
* `test_datapoints_to_alarm_is_never_treated_as_a_multiplier` mutates
  `datapoints_to_alarm` and requires the figure NOT to move -- it is the M of an M-of-N
  evaluation, not a factor in the detection time, and multiplying by it is right here only
  by the coincidence that it equals 1.
* `test_every_lag_term_is_either_sourced_or_named_as_an_unknown` and
  `test_the_model_does_not_claim_to_have_bounded_the_whole_path` require the unmeasured
  terms to be **named**, not guessed and not omitted. A model that quietly closed its own
  unknowns would pass a smaller test file and be exactly as wrong as the 100 ms figure.
* `test_the_rate_is_priced_from_tier_1_and_not_by_averaging_the_24_hour_figure` guards the
  cheap wrong shortcut: `flood_rate_24h_for_contrast_usd / 1440` is 13.6 % low, because a
  24-hour flood reaches egress tiers a 60-second window never sees.

AND THE PACED RESIDUAL IS NOT REPLACED
---------------------------------------

`test_cost_model.py::test_the_residual_is_computed_at_the_hourly_alarm_threshold_not_at_
flood_rate` is correct and stays green: a caller pacing under the alarms is a different
attacker from a flood. `test_the_in_window_figure_is_additive_to_the_paced_one` asserts
both exposures are published together, so neither can be quoted where the other belongs.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.deploy import cost_model as cm

REPO_ROOT = cm.REPO_ROOT


@pytest.fixture(scope="module")
def model() -> dict:
    built = cm.build_model()
    assert built["ok"] is True, "the reproduction gate failed; nothing downstream is reviewable"
    return built


@pytest.fixture(scope="module")
def in_window(model) -> dict:
    return model["residual"]["in_window"]


# ─────────────────────────────────────────────────────────────────────────────────────────
# Mutation helpers. Every falsification below asserts that its mutation IS a mutation,
# because a falsification that silently changes nothing "passes" and proves nothing.
# ─────────────────────────────────────────────────────────────────────────────────────────


def _alarm_body(text: str, alarm: str) -> str:
    body = cm._hcl_block(
        text, rf'resource\s+"aws_cloudwatch_metric_alarm"\s+"{alarm}"\s*\{{'
    )
    assert body is not None, f"no aws_cloudwatch_metric_alarm.{alarm} block in the HCL"
    return body


def _mutate_alarm(tmp_path: Path, monkeypatch, alarm: str, old: str, new: str) -> None:
    """Rewrite one attribute inside ONE alarm block and point the model at the copy."""
    text = cm.COST_GUARD_MAIN.read_text(encoding="utf-8")
    body = _alarm_body(text, alarm)
    assert body.count(old) == 1, (
        f"{old!r} appears {body.count(old)} times in the {alarm} block; this mutation "
        "would not be an unambiguous mutation and the falsification would prove nothing"
    )
    mutated = text.replace(body, body.replace(old, new, 1), 1)
    assert mutated != text, "the mutation changed nothing"
    path = tmp_path / "main.tf"
    path.write_text(mutated, encoding="utf-8", newline="\n")
    monkeypatch.setattr(cm, "COST_GUARD_MAIN", path)


def _mutate_variable(tmp_path: Path, monkeypatch, variable: str, old: str, new: str) -> None:
    text = cm.COST_GUARD_VARIABLES.read_text(encoding="utf-8")
    body = cm._hcl_block(text, rf'variable\s+"{variable}"\s*\{{')
    assert body is not None, f"no variable {variable!r} block in the HCL"
    assert body.count(old) == 1, (
        f"{old!r} appears {body.count(old)} times in the {variable} block; the mutation "
        "would not be unambiguous"
    )
    mutated = text.replace(body, body.replace(old, new, 1), 1)
    assert mutated != text, "the mutation changed nothing"
    path = tmp_path / "variables.tf"
    path.write_text(mutated, encoding="utf-8", newline="\n")
    monkeypatch.setattr(cm, "COST_GUARD_VARIABLES", path)


# ─────────────────────────────────────────────────────────────────────────────────────────
# 1. THE FLOOR. Read from the stack, derived rather than named, and labelled a FLOOR.
# ─────────────────────────────────────────────────────────────────────────────────────────


def test_the_detection_floor_is_period_times_evaluation_periods(in_window):
    """R1's arithmetic, checked against the HCL rather than against a remembered 60."""
    guard_main = cm.COST_GUARD_MAIN.read_text(encoding="utf-8")
    first = in_window["detection"]["first_alarm_to_fire"]
    period = cm.terraform_alarm_attribute(guard_main, first, "period")
    evaluations = cm.terraform_alarm_attribute(guard_main, first, "evaluation_periods")
    assert period is not None and evaluations is not None

    assert in_window["detection"]["floor_s"] == float(period * evaluations)
    assert in_window["detection"]["formula"] == (
        "worst_case_detection_s = period x evaluation_periods"
    )


def test_the_detection_floor_follows_the_hcl_and_is_not_a_literal(tmp_path, monkeypatch):
    """Double the burst alarm's period and the published residual must double with it.

    A model carrying `60` as a literal would keep publishing a detection window the stack
    no longer has, which is precisely how the 100 ms figure survived for as long as it did.
    """
    before = cm.build_model()["residual"]["in_window"]
    assert before["detection"]["floor_s"] == 60.0

    _mutate_alarm(tmp_path, monkeypatch, "invocations_burst", "period              = 60", "period              = 120")
    after = cm.build_model()["residual"]["in_window"]

    assert after["detection"]["floor_s"] == 120.0
    assert after["published_figures"][0]["detection_lag_s"] == 120.0
    assert after["published_figures"][0]["usd"] == pytest.approx(
        before["published_figures"][0]["usd"] * 2.0, rel=1e-9
    )
    # The RATE is a property of the flood, not of the alarm, so it must NOT move.
    assert after["usd_per_minute_of_detection_lag"] == pytest.approx(
        before["usd_per_minute_of_detection_lag"], rel=1e-9
    )


def test_datapoints_to_alarm_is_never_treated_as_a_multiplier(tmp_path, monkeypatch):
    """R1, guarded from the other side: M-of-N's M is not a factor in the detection time.

    `datapoints_to_alarm = 1` today, so multiplying by it would be invisible. This moves it
    to 3 and requires the floor to stay where it is. If the floor tripled, the model would
    be reading M as a number of periods, which is a different alarm from the one deployed.
    """
    before = cm.build_model()["residual"]["in_window"]

    _mutate_alarm(
        tmp_path,
        monkeypatch,
        "invocations_burst",
        "datapoints_to_alarm = 1",
        "datapoints_to_alarm = 3",
    )
    after = cm.build_model()["residual"]["in_window"]

    assert after["detection"]["candidates"][0]["datapoints_to_alarm"] == 3, (
        "the mutation did not reach the model, so this control proves nothing"
    )
    assert after["detection"]["floor_s"] == before["detection"]["floor_s"]
    assert after["published_figures"][0]["usd"] == pytest.approx(
        before["published_figures"][0]["usd"], rel=1e-12
    )


def test_the_floor_is_the_whole_period_and_not_the_time_to_cross_the_threshold(in_window):
    """A datapoint does not exist until its period closes.

    At the flood rate the burst threshold is crossed in under two seconds. Publishing that
    as the detection time would understate the exposure by ~35x.
    """
    detection = in_window["detection"]
    first = next(
        c for c in detection["candidates"] if c["alarm"] == detection["first_alarm_to_fire"]
    )
    assert first["seconds_to_cross_the_threshold"] < detection["floor_s"]
    assert detection["floor_s"] == float(first["period_s"] * first["evaluation_periods"])
    assert "does not exist until its period closes" in detection["why_the_floor_is_the_whole_period"]


def test_the_first_alarm_to_fire_is_derived_and_not_named(tmp_path, monkeypatch):
    """Make the burst alarm slower than the hourly one and the hourly one must take over."""
    before = cm.build_model()["residual"]["in_window"]
    assert before["detection"]["first_alarm_to_fire"] == "invocations_burst"

    _mutate_alarm(
        tmp_path, monkeypatch, "invocations_burst", "period              = 60", "period              = 7200"
    )
    after = cm.build_model()["residual"]["in_window"]

    assert after["detection"]["first_alarm_to_fire"] == "invocations_hourly"
    assert after["detection"]["floor_s"] == 3600.0


def test_the_model_refuses_to_publish_when_an_alarm_timing_cannot_be_read(tmp_path, monkeypatch):
    """No alarm timing, no figure. The residual is not published against invented timings."""
    _mutate_alarm(
        tmp_path,
        monkeypatch,
        "invocations_burst",
        "evaluation_periods  = 1",
        "evaluation_periodz  = 1",
    )
    with pytest.raises(ValueError, match="invocations_burst_evaluation_periods"):
        cm.build_model()


# ─────────────────────────────────────────────────────────────────────────────────────────
# 2. THE RATE. Priced from tier 1, reproduced independently, and linear.
# ─────────────────────────────────────────────────────────────────────────────────────────


def test_the_flood_rate_is_the_concurrency_ceiling_over_the_measured_duration(in_window):
    """Re-derived here from the evidence file rather than read back out of the model."""
    latency = json.loads(cm.LATENCY_BASELINE.read_text(encoding="utf-8"))
    js_ms = latency["targets"]["local"]["beats"]["asset_js"]["wall_ms"]["p50_ms"]
    expected = cm.ACCOUNT_CONCURRENCY_CEILING / (js_ms / 1000.0)

    assert in_window["flood_rate_rps"] == pytest.approx(expected, rel=1e-6)
    assert in_window["flood_rate_rps"] == pytest.approx(1766.784, rel=1e-4)


def test_the_rate_is_priced_from_tier_1_and_not_by_averaging_the_24_hour_figure(model, in_window):
    """R3: dividing the 24-hour flood figure by 1,440 understates this by ~13.6 %.

    The 24-hour figure accumulates enough egress to reach the $0.085 and $0.082 tiers,
    which a window of minutes never does. The wrong method is published beside the right
    one precisely so that anyone tempted by the shortcut can see what it costs.
    """
    assert in_window["every_window_priced_from_tier_1_only"] is True
    assert all(row["priced_from_tier_1_only"] for row in in_window["sensitivity"])

    wrong = in_window["the_wrong_way_to_get_this"]
    naive = model["residual"]["flood_rate_24h_for_contrast_usd"] / 1440.0
    assert wrong["usd_per_minute"] == pytest.approx(naive, abs=5e-4)
    assert wrong["usd_per_minute"] < in_window["usd_per_minute_of_detection_lag"]
    assert wrong["understates_the_correct_figure_by_percent"] > 13.0
    assert wrong["understates_the_correct_figure_by_percent"] == pytest.approx(
        (in_window["usd_per_minute_of_detection_lag"] - naive)
        / in_window["usd_per_minute_of_detection_lag"]
        * 100.0,
        abs=0.02,
    )


def test_the_residual_is_linear_in_the_detection_lag(in_window):
    """The useful property: any lag budget can be priced by multiplying one number."""
    rows = in_window["sensitivity"]
    assert len(rows) >= 5
    rate = in_window["usd_per_minute_of_detection_lag"]
    assert in_window["linear_in_lag"] is True

    for row in rows:
        assert row["usd_per_minute"] == pytest.approx(rate, rel=1e-6), (
            "the sensitivity table is not linear, so the published USD/minute is not a "
            "slope and multiplying by a lag budget would be wrong"
        )
        assert row["total_usd"] == pytest.approx(
            rate * row["detection_lag_s"] / 60.0, abs=0.01
        )
    assert [row["detection_lag_s"] for row in rows] == sorted(
        row["detection_lag_s"] for row in rows
    )
    assert rows[0]["detection_lag_s"] == in_window["detection"]["floor_s"]


def test_the_rate_reproduces_independently_of_the_model(in_window):
    """Priced here with a fresh Flood so a bug in the block's own plumbing cannot hide."""
    convention = cm.CONVENTIONS[cm.HEADLINE_CONVENTION]
    cost = cm.price(
        cm.Flood(
            label="independent",
            concurrency=cm.ACCOUNT_CONCURRENCY_CEILING,
            duration_ms=json.loads(cm.LATENCY_BASELINE.read_text(encoding="utf-8"))["targets"][
                "local"
            ]["beats"]["asset_js"]["wall_ms"]["p50_ms"],
            request_bytes=in_window["priced_object_bytes"],
            memory_mb=256,
            window_s=60.0,
        ),
        convention,
        apply_free_tier=False,
    )
    assert cost.total_usd == pytest.approx(
        in_window["usd_per_minute_of_detection_lag"], abs=0.005
    )
    assert len(cost.tiers) == 1, "a 60-second window left egress tier 1; the linearity claim is false"


# ─────────────────────────────────────────────────────────────────────────────────────────
# 3. THE LAG BUDGET. Every term sourced or NAMED as unknown. Nothing estimated.
# ─────────────────────────────────────────────────────────────────────────────────────────

_ALLOWED_BASES = {"read-from-hcl", "unknown"}


def test_every_lag_term_is_either_sourced_or_named_as_an_unknown(in_window):
    """The rule R2 exists for: bound it, or name it. Never guess it.

    A term with a number and no source is a guess wearing a citation -- the exact shape of
    the 100 ms invocation duration that made the published headline wrong.
    """
    terms = in_window["lag_budget"]["terms"]
    assert terms, "the lag budget is empty"

    for term in terms:
        assert term["basis"] in _ALLOWED_BASES, (
            f"{term['term']} carries basis {term['basis']!r}. Only a value read out of this "
            "repository's own Terraform or an explicit unknown may be published here."
        )
        assert term["what_it_covers"].strip()

        if term["basis"] == "read-from-hcl":
            assert isinstance(term["seconds"], (int, float))
            assert term["seconds"] > 0
            source = term["source"]
            path = source.split(" ")[0].split("::")[0].strip()
            assert (REPO_ROOT / path).exists(), f"{term['term']} cites {path}, which does not exist"
        else:
            assert term["seconds"] is None, (
                f"{term['term']} is declared unknown but carries a number. An unknown with a "
                "number in it is a guess."
            )
            assert term["why_unknown"].strip()
            assert term["what_would_bound_it"].strip()


def test_the_model_does_not_claim_to_have_bounded_the_whole_path(in_window):
    """If this ever goes red because there are no unknowns left, they were MEASURED.

    Until then, silence about the delivery path would be the same error as assuming a
    100 ms invocation: an unmeasured term quietly set to zero.
    """
    budget = in_window["lag_budget"]
    derived = [t["term"] for t in budget["terms"] if t["basis"] == "unknown"]
    assert budget["unknown_terms"] == derived
    assert budget["unknown_term_count"] == len(derived)
    assert budget["unknown_term_count"] >= 1, (
        "no lag term is unknown, which would mean the alarm-to-stop path has been measured. "
        "If that is now true, replace this assertion with the measurement and its source; "
        "do not delete it."
    )

    for expected in (
        "metric_publication_delay",
        "alarm_evaluation_delay",
        "sns_delivery_to_the_responder",
        "reserved_concurrency_propagation",
    ):
        assert expected in budget["unknown_terms"], (
            f"{expected} vanished from the lag budget. A term dropped is a term set to "
            "zero, and this figure's whole point is that it is not."
        )

    assert "NO upper bound on the total lag is published" in budget["therefore"]


def test_the_bounded_seconds_sum_only_the_terms_that_carry_a_bound(in_window):
    budget = in_window["lag_budget"]
    expected = sum(t["seconds"] for t in budget["terms"] if t["basis"] != "unknown")
    assert budget["bounded_seconds"] == pytest.approx(expected, rel=1e-9)
    assert budget["bounded_terms"] == [
        t["term"] for t in budget["terms"] if t["basis"] != "unknown"
    ]
    assert budget["bounded_seconds"] > in_window["detection"]["floor_s"], (
        "the bounded lag does not exceed the alarm window, so no term beyond the alarm is "
        "being counted at all"
    )


def test_the_responder_bound_is_read_from_terraform_and_not_a_literal(tmp_path, monkeypatch):
    """Move `responder_timeout` and the bounded-terms figure must move with it."""
    before = cm.build_model()["residual"]["in_window"]
    assert before["lag_budget"]["bounded_seconds"] == 75.0

    _mutate_variable(tmp_path, monkeypatch, "responder_timeout", "default     = 15", "default     = 45")
    after = cm.build_model()["residual"]["in_window"]

    assert after["lag_budget"]["bounded_seconds"] == 105.0
    bounded_after = next(
        f for f in after["published_figures"] if f["name"] == "bounded-terms-only"
    )
    assert bounded_after["detection_lag_s"] == 105.0

    # Priced independently at full precision rather than by multiplying the published
    # (4-decimal) rate, so this compares arithmetic and not two roundings of it.
    independent = cm.price(
        cm.Flood(
            label="bounded-105s",
            concurrency=cm.ACCOUNT_CONCURRENCY_CEILING,
            duration_ms=json.loads(cm.LATENCY_BASELINE.read_text(encoding="utf-8"))["targets"][
                "local"
            ]["beats"]["asset_js"]["wall_ms"]["p50_ms"],
            request_bytes=after["priced_object_bytes"],
            memory_mb=256,
            window_s=105.0,
        ),
        cm.CONVENTIONS[cm.HEADLINE_CONVENTION],
        apply_free_tier=False,
    )
    assert bounded_after["usd"] == pytest.approx(independent.total_usd, abs=0.0001)


def test_the_in_flight_drain_is_bounded_and_is_not_the_missing_term(in_window):
    """The one post-stop term that IS boundable without any AWS documentation.

    At most `concurrency` invocations are in flight when the stop lands. Pricing it stops
    "requests still drain" being waved at as though it were the unknown; it is four orders
    of magnitude below the alarm window, and the delivery-path terms are the real unknowns.
    """
    drain = in_window["in_flight_drain"]
    assert drain["basis"] == "bounded"
    assert drain["requests"] == cm.ACCOUNT_CONCURRENCY_CEILING
    floor_usd = in_window["published_figures"][0]["usd"]
    assert drain["usd"] < floor_usd / 1000.0


# ─────────────────────────────────────────────────────────────────────────────────────────
# 4. PUBLICATION. No scalar without its lag, and no replacement of the paced residual.
# ─────────────────────────────────────────────────────────────────────────────────────────


def test_no_scalar_is_published_without_its_lag_in_the_same_record(in_window):
    """R2's publication rule, enforced on the record rather than trusted to the reader."""
    assert in_window["answer_is_a_rate_times_a_lag_not_a_scalar"] is True
    figures = in_window["published_figures"]
    assert figures, "no figure is published at all"

    for figure in figures:
        lag = figure["detection_lag_s"]
        assert isinstance(lag, (int, float)) and lag > 0
        plainly = figure["stated_plainly"]
        assert f"{lag:g} s" in plainly, (
            f"{figure['name']} states a dollar figure without its lag in the same sentence"
        )
        assert f"{figure['usd']:,.2f}" in plainly

    floor = figures[0]
    assert floor["name"] == "floor"
    assert floor["detection_lag_s"] == in_window["detection"]["floor_s"]
    assert "this_is_a_floor_because" in floor


def test_the_floor_is_labelled_a_floor_and_the_reason_is_the_published_error(in_window):
    """The block must say WHY it refuses to publish `60 s x rate` as the answer."""
    why = in_window["why_not_a_scalar"]
    assert "33,251.87" in why
    assert "zero" in why.lower()
    assert "FLOOR" in why or "floor" in why


def test_the_in_window_figure_is_additive_to_the_paced_one(model, in_window):
    """R4: two different attackers, both real. Neither replaces the other.

    `test_cost_model.py` asserts the paced residual is NOT at flood rate and is right. This
    one is at flood rate. If a future edit ever collapses them into one number, whichever
    attacker it drops becomes invisible.
    """
    residual = model["residual"]
    additive = in_window["additive_to_the_paced_residual_not_a_replacement"]

    assert additive["paced"]["worst_usd_24h"] == pytest.approx(residual["worst_usd"], abs=0.01)
    assert additive["paced"]["worst_usd_30d_unattended"] == pytest.approx(
        residual["if_nobody_looks_for_30_days_usd"], abs=0.01
    )
    assert additive["in_window"]["usd_per_minute"] == pytest.approx(
        in_window["usd_per_minute_of_detection_lag"], rel=1e-9
    )

    # The paced block must still be the paced block: computed at the hourly alarm line.
    assert residual["binding_alarm"] == "hourly"
    assert residual["paced_at_requests_per_second"] == pytest.approx(
        residual["hourly"]["threshold"] / residual["hourly"]["period_s"], rel=1e-6
    )
    # And the two are genuinely different exposures, not two spellings of one.
    assert in_window["flood_rate_rps"] > residual["paced_at_requests_per_second"] * 100


def test_the_priced_object_follows_the_response_ceiling_in_force(in_window):
    """R11: the ceiling is read at model time, so this rate follows another lead's ruling."""
    ceiling = cm.response_ceiling_in_force()
    assert in_window["response_ceiling_in_force_bytes"] == ceiling

    objects = in_window["objects"]
    assert {o["object"] for o in objects} == {"gzip-sibling", "identity"}
    for row in objects:
        assert row["reachable_under_the_ceiling_in_force"] == (row["object_bytes"] <= ceiling)

    priced = [o for o in objects if o["is_the_priced_object"]]
    assert len(priced) == 1
    assert priced[0]["object_bytes"] == in_window["priced_object_bytes"]
    assert priced[0]["reachable_under_the_ceiling_in_force"] is True
    assert priced[0]["object_bytes"] == max(
        o["object_bytes"] for o in objects if o["reachable_under_the_ceiling_in_force"]
    )


def test_lifting_the_ceiling_moves_the_rate_rather_than_being_ignored(tmp_path, monkeypatch):
    """If `DEFAULT_MAX_RESPONSE_BYTES` rises, the reachable object -- and the bill -- rise."""
    before = cm.build_model()["residual"]["in_window"]
    assert before["priced_object"] == "gzip-sibling"

    stub = tmp_path / "static_site.py"
    stub.write_text("DEFAULT_MAX_RESPONSE_BYTES = 2048 * 1024\n", encoding="utf-8", newline="\n")
    monkeypatch.setattr(cm, "STATIC_SITE", stub)
    after = cm.build_model()["residual"]["in_window"]

    assert after["priced_object"] == "identity"
    assert after["usd_per_minute_of_detection_lag"] > before["usd_per_minute_of_detection_lag"]
    identity_bytes = next(o["object_bytes"] for o in before["objects"] if o["object"] == "identity")
    assert after["priced_object_bytes"] == identity_bytes


# ─────────────────────────────────────────────────────────────────────────────────────────
# 5. THE EVIDENCE. Committed, licensed, and regenerated rather than hand-edited.
# ─────────────────────────────────────────────────────────────────────────────────────────


def test_the_committed_evidence_carries_the_in_window_block(in_window):
    """The published JSON must be what the program produces, figure for figure."""
    committed = json.loads(cm.OUTPUT.read_text(encoding="utf-8"))
    published = committed["residual"]["in_window"]

    assert published["detection"]["floor_s"] == in_window["detection"]["floor_s"]
    assert published["usd_per_minute_of_detection_lag"] == pytest.approx(
        in_window["usd_per_minute_of_detection_lag"], abs=0.0001
    )
    assert published["lag_budget"]["unknown_terms"] == in_window["lag_budget"]["unknown_terms"]
    assert published["lag_budget"]["bounded_seconds"] == in_window["lag_budget"]["bounded_seconds"]
    assert [f["usd"] for f in published["published_figures"]] == pytest.approx(
        [f["usd"] for f in in_window["published_figures"]], abs=0.0001
    )
    assert [row["total_usd"] for row in published["sensitivity"]] == pytest.approx(
        [row["total_usd"] for row in in_window["sensitivity"]], abs=0.01
    )


def test_every_evidence_file_in_the_cost_directory_carries_a_reuse_sidecar():
    """An unpublished or unlicensed evidence file in a public repo is a citation to nothing."""
    files = [
        path
        for path in sorted(cm.EVIDENCE_DIR.iterdir())
        if path.is_file() and path.suffix != ".license"
    ]
    assert files, f"{cm.EVIDENCE_DIR} is empty"
    for path in files:
        sidecar = path.with_suffix(path.suffix + ".license")
        assert sidecar.exists(), f"{path.name} has no REUSE .license sidecar"
        assert "SPDX-License-Identifier:" in sidecar.read_text(encoding="utf-8")
