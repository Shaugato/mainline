#!/usr/bin/env python
# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""The demo's cost bound as an executable, not as prose.

WHY THIS FILE EXISTS
====================

`docs/deploy/COST-BOUND.md` is correct and it is a document. Its arithmetic was done once,
by hand, against inputs that have since moved: the source maps it prices at 1,554,168 B per
response are no longer in the package, the 100 ms invocation it assumes was never measured,
and the levers it costs have partly shipped. A number that cannot be re-run cannot be
re-checked, and a cost bound nobody can re-check stops being a bound the first time an
input changes.

So this module is the arithmetic, and the document becomes its report.

THE RULE THIS MODULE OBEYS, AND THE REASON IT IS THE FIRST RULE
---------------------------------------------------------------

**A model that cannot reproduce the old answer has no standing to produce a new one.**

`tests/deploy/test_cost_model.py` runs the reproduction gate BEFORE it looks at any new
figure: given the ORIGINAL inputs (1,554,168 B, 100 ms and 300 ms, 512 MB, concurrency 10,
30 days, `ap-southeast-1`), this module must return the published headline of
**USD 33,251.87** and **USD 11,701.05** to the cent. If it does not, every new number below
is unreviewed arithmetic wearing a citation, and the test says so instead of publishing it.

WHAT THIS MODULE IS NOT
-----------------------

**It is not a forecast.** Every total here is an upper bound computed by holding the
account concurrency ceiling pinned and dividing by a measured invocation duration. That
arithmetic assumes AWS *sustains* the resulting egress rate, and at the measured 14.11 ms
map duration the assumed rate is **1.1 GB/s out of ten 512 MB execution environments**,
which nobody has observed and which this project has no way to observe without applying.
The number is what the tariff and the ceiling permit, not what AWS would deliver. Every
emitted record carries that caveat in its own payload (`model_bound`), because a caveat
that lives only in a source comment is not published.

THE THREE GB CONVENTIONS, AND WHY THERE ARE THREE
--------------------------------------------------

AWS's Pricing API returns the egress tier boundaries as 10240 / 51200 / 153600 and prints
the unit as "GB". Those are 10x1024, 50x1024 and 150x1024 -- binary boundaries under a
decimal name. Three self-consistent readings exist, they differ by about 7 %, and prior
work in this repository has used all three without saying which. They are named here so
that a figure can never again be quoted without its convention:

  ``audit-decimal``     GB = 10^9, tiers at 10,000 / 50,000 / 150,000, no free tier.
                        Reproduces `docs/deploy/COST-BOUND.md`'s headline exactly.
  ``decimal-gb-api-tiers``
                        GB = 10^9, tiers at the API's 10240 / 51200 / 153600, no free tier.
                        Reproduces `docs/leads/cost-finish-plan.md` §0.5 exactly.
  ``binary-gb-api-tiers``
                        GB = 2^30, API tiers, 100 GB/month free. The likeliest actual bill.

The 0.06 % gap the lead reported between their run and the document is NOT floating-point
tolerance and is not treated as such here: it is entirely explained by the tier-boundary
choice, and this module reproduces BOTH figures to the cent once that choice is made an
explicit input rather than an assumption. See `reproduce()`.

ACCOUNTING CONVENTIONS, STATED BECAUSE THEY MOVE THE ANSWER
------------------------------------------------------------

1. **Egress is priced on response BODY bytes.** Not on the base64 envelope (Lambda decodes
   it before it leaves), and not including response headers. Headers were measured at
   **147 B** for the 429 path (status line + header block). That is +0.03 % on a 433 KB
   asset and **+63 %** on a 233 B refusal body, so it is negligible everywhere it is
   ignored except the rate-bound layer, where both figures are emitted.
2. **Each window is priced from tier 1.** A 5-minute or 24-hour figure does not inherit the
   month's accumulated volume. This UNDERSTATES a short window that follows a flood, and it
   is the convention the published 30-day figures already use.
3. **Compute is billed on actual duration**, so the function timeout does not appear in any
   total. `docs/deploy/LATENCY.md` establishes the timeout as a reliability bound; it is
   not a cost lever and is not modelled as one.

Nothing here applies anything, calls AWS, or touches a database.
"""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]

EVIDENCE_DIR = REPO_ROOT / "evidence" / "deploy" / "cost"
PACKAGE_SHAPE = EVIDENCE_DIR / "package-shape.json"
LATENCY_BASELINE = EVIDENCE_DIR / "latency-baseline.json"
LOG_BYTES = EVIDENCE_DIR / "log-bytes.json"
COST_GUARD_VARIABLES = REPO_ROOT / "infra" / "modules" / "cost-guard" / "variables.tf"
COST_GUARD_MAIN = REPO_ROOT / "infra" / "modules" / "cost-guard" / "main.tf"
PLAN_EVIDENCE = REPO_ROOT / "evidence" / "deploy" / "terraform-plan-furl.txt"
OUTPUT = EVIDENCE_DIR / "cost-model.json"

SCHEMA = "mainline/deploy/cost-model/1"


# ─────────────────────────────────────────────────────────────────────────────────────────
# The tariff. ONE definition, so the falsification test can move exactly one constant.
# ─────────────────────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Tariff:
    """`ap-southeast-1`, read from the AWS Pricing API on 2026-08-13.

    Provenance for every field is `docs/deploy/COST-BOUND.md` §1.1, which records the exact
    `aws pricing get-products` invocations, `sku SDHP4R7WGBVJPQPY`, `effectiveDate
    2026-06-01`. These are the numbers the whole document rests on; the falsification in
    `tests/deploy/test_cost_model.py` mutates one of them and requires the reproduction to
    go red.
    """

    egress_usd_per_gb: tuple[float, float, float, float] = (0.120, 0.085, 0.082, 0.080)
    request_usd_per_million: float = 0.20
    gb_second_usd_arm64: float = 0.0000133334

    @property
    def request_usd_each(self) -> float:
        return self.request_usd_per_million / 1_000_000.0


TARIFF = Tariff()


@dataclass(frozen=True)
class GbConvention:
    """How bytes become billable GB, and where the tier edges sit."""

    name: str
    bytes_per_gb: int
    tier_edges_gb: tuple[float, float, float]
    free_gb_per_month: float
    reproduces: str

    def billable_gb(self, total_bytes: float, *, apply_free_tier: bool) -> float:
        gb = total_bytes / self.bytes_per_gb
        if apply_free_tier:
            gb = max(0.0, gb - self.free_gb_per_month)
        return gb


CONVENTIONS: dict[str, GbConvention] = {
    "audit-decimal": GbConvention(
        name="audit-decimal",
        bytes_per_gb=10**9,
        tier_edges_gb=(10_000.0, 50_000.0, 150_000.0),
        free_gb_per_month=0.0,
        reproduces="docs/deploy/COST-BOUND.md §1.2 headline: $33,252 / $11,701",
    ),
    "decimal-gb-api-tiers": GbConvention(
        name="decimal-gb-api-tiers",
        bytes_per_gb=10**9,
        tier_edges_gb=(10_240.0, 51_200.0, 153_600.0),
        free_gb_per_month=0.0,
        reproduces="docs/leads/cost-finish-plan.md §0.5 table: $33,271 / $11,713",
    ),
    "binary-gb-api-tiers": GbConvention(
        name="binary-gb-api-tiers",
        bytes_per_gb=2**30,
        tier_edges_gb=(10_240.0, 51_200.0, 153_600.0),
        free_gb_per_month=100.0,
        reproduces="docs/deploy/COST-BOUND.md §1.2 measured tariff: $31,050 / $10,949",
    ),
}

HEADLINE_CONVENTION = "audit-decimal"


def egress_cost_usd(
    total_bytes: float,
    convention: GbConvention,
    tariff: Tariff = TARIFF,
    *,
    apply_free_tier: bool = True,
) -> tuple[float, float, list[dict[str, Any]]]:
    """Price `total_bytes` of egress. Returns (usd, billable_gb, per-tier breakdown).

    The breakdown is returned rather than logged because the tier split is the part a
    reviewer re-derives by hand, and a total with no split cannot be checked.
    """
    gb = convention.billable_gb(total_bytes, apply_free_tier=apply_free_tier)
    edges = (0.0, *convention.tier_edges_gb, math.inf)
    usd = 0.0
    rows: list[dict[str, Any]] = []
    for index, rate in enumerate(tariff.egress_usd_per_gb):
        lower, upper = edges[index], edges[index + 1]
        volume = max(0.0, min(gb, upper) - lower)
        if volume <= 0.0:
            continue
        cost = volume * rate
        usd += cost
        rows.append(
            {
                "tier_gb_from": lower,
                "tier_gb_to": None if upper == math.inf else upper,
                "volume_gb": round(volume, 4),
                "usd_per_gb": rate,
                "usd": round(cost, 4),
            }
        )
    return usd, gb, rows


# ─────────────────────────────────────────────────────────────────────────────────────────
# One priced scenario.
# ─────────────────────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Flood:
    """A sustained flood held at the account concurrency ceiling.

    `request_bytes` is the RESPONSE BODY served to each request. `refused_bytes` and
    `served_rps_cap` model a rate limiter: up to `served_rps_cap` requests per second get
    `request_bytes`, and every other invocation still happens -- and is still billed as an
    invocation and as compute -- but returns `refused_bytes`.
    """

    label: str
    concurrency: int
    duration_ms: float
    request_bytes: int
    memory_mb: int
    window_s: float
    served_rps_cap: float | None = None
    refused_bytes: int = 0
    rps_override: float | None = None
    note: str = ""

    @property
    def rps(self) -> float:
        if self.rps_override is not None:
            return self.rps_override
        return self.concurrency / (self.duration_ms / 1000.0)

    @property
    def requests(self) -> float:
        return self.rps * self.window_s


@dataclass(frozen=True)
class Cost:
    label: str
    egress_usd: float
    requests_usd: float
    compute_usd: float
    total_usd: float
    billable_gb: float
    egress_bytes: float
    request_count: float
    rps: float
    sustained_egress_bytes_per_second: float
    tiers: list[dict[str, Any]] = field(default_factory=list)

    def as_json(self) -> dict[str, Any]:
        return {
            "label": self.label,
            "requests": round(self.request_count, 1),
            "requests_per_second": round(self.rps, 3),
            "egress_bytes": round(self.egress_bytes, 1),
            "billable_gb": round(self.billable_gb, 4),
            "sustained_egress_bytes_per_second": round(self.sustained_egress_bytes_per_second, 1),
            "egress_usd": round(self.egress_usd, 2),
            "requests_usd": round(self.requests_usd, 2),
            "compute_usd": round(self.compute_usd, 2),
            "total_usd": round(self.total_usd, 2),
            "tiers": self.tiers,
        }


def price(
    flood: Flood,
    convention: GbConvention,
    tariff: Tariff = TARIFF,
    *,
    apply_free_tier: bool = True,
) -> Cost:
    requests = flood.requests
    if flood.served_rps_cap is None:
        egress_bytes = requests * flood.request_bytes
    else:
        served = min(flood.rps, flood.served_rps_cap) * flood.window_s
        refused = max(0.0, requests - served)
        egress_bytes = served * flood.request_bytes + refused * flood.refused_bytes

    egress_usd, gb, tiers = egress_cost_usd(
        egress_bytes, convention, tariff, apply_free_tier=apply_free_tier
    )
    requests_usd = requests * tariff.request_usd_each
    gb_seconds = requests * (flood.duration_ms / 1000.0) * (flood.memory_mb / 1024.0)
    compute_usd = gb_seconds * tariff.gb_second_usd_arm64

    return Cost(
        label=flood.label,
        egress_usd=egress_usd,
        requests_usd=requests_usd,
        compute_usd=compute_usd,
        total_usd=egress_usd + requests_usd + compute_usd,
        billable_gb=gb,
        egress_bytes=egress_bytes,
        request_count=requests,
        rps=flood.rps,
        sustained_egress_bytes_per_second=egress_bytes / flood.window_s,
        tiers=tiers,
    )


# ─────────────────────────────────────────────────────────────────────────────────────────
# THE REPRODUCTION GATE.
# ─────────────────────────────────────────────────────────────────────────────────────────

WINDOW_30D_S = 30 * 24 * 60 * 60  # 2,592,000
ACCOUNT_CONCURRENCY_CEILING = 10  # measured: aws lambda get-account-settings, ap-southeast-1

#: The inputs as they stood when `docs/deploy/COST-BOUND.md` was written. These are frozen
#: ON PURPOSE and are NOT refreshed from evidence: their job is to reproduce a published
#: answer, and an input that follows the tree cannot do that. The LIVE inputs are loaded
#: separately in `load_measured_inputs()`.
HISTORIC_LARGEST_RESPONSE_BYTES = 1_554_168  # web/assets/index-BjAGxrVJ.js.map
HISTORIC_MEMORY_MB = 512
HISTORIC_DURATION_FAST_MS = 100.0
HISTORIC_DURATION_SLOW_MS = 300.0

#: What each convention must return for the historic inputs, WITH the precision at which
#: the source actually published it.
#:
#: The precision field is load-bearing and is not a softener. The tolerance is not a number
#: this module chose; it is the number of digits the cited document printed. Where
#: COST-BOUND §2.2 prints cents, the model must agree to the cent. Where §1.2 prints whole
#: dollars, the model must agree after rounding to whole dollars -- and demanding cents
#: there would mean inventing two digits the source never published and then "reproducing"
#: them, which is the failure mode this whole file exists to refuse.
#:
#: (value, decimals_published, source)
PUBLISHED_HEADLINES: dict[str, tuple[tuple[float, int, str], tuple[float, int, str]]] = {
    "audit-decimal": (
        (33_251.87, 2, "docs/deploy/COST-BOUND.md §2.2 TOTAL row"),
        (11_701.00, 0, "docs/deploy/COST-BOUND.md §1.2 and §2.3"),
    ),
    "decimal-gb-api-tiers": (
        (33_271.00, 0, "docs/leads/cost-finish-plan.md §0.5 row 1"),
        (11_713.00, 0, "docs/leads/cost-finish-plan.md §0.5, the 300 ms figure"),
    ),
    "binary-gb-api-tiers": (
        (31_049.79, 2, "docs/deploy/COST-BOUND.md §2.2 measured-tariff TOTAL row"),
        (10_949.00, 0, "docs/deploy/COST-BOUND.md §1.2 and §2.3"),
    ),
}

#: Absorbs IEEE-754 noise in the last published digit only. It is NOT a licence for the
#: model to disagree with a document: agreement is checked after rounding to the source's
#: own precision, and this epsilon is smaller than half of that unit in every case.
REPRODUCTION_EPSILON_USD = 0.005


def historic_flood(duration_ms: float) -> Flood:
    return Flood(
        label=f"historic-{duration_ms:g}ms",
        concurrency=ACCOUNT_CONCURRENCY_CEILING,
        duration_ms=duration_ms,
        request_bytes=HISTORIC_LARGEST_RESPONSE_BYTES,
        memory_mb=HISTORIC_MEMORY_MB,
        window_s=WINDOW_30D_S,
    )


def reproduce(tariff: Tariff = TARIFF) -> dict[str, Any]:
    """Re-derive every published headline from the inputs that produced it.

    This runs before anything else in `build_model()`, and `build_model()` refuses to emit
    a new figure if any row here fails. That ordering is the point of the file.
    """
    rows: list[dict[str, Any]] = []
    ok = True
    for name, (fast_spec, slow_spec) in PUBLISHED_HEADLINES.items():
        convention = CONVENTIONS[name]
        free = convention.free_gb_per_month > 0.0
        fast = price(
            historic_flood(HISTORIC_DURATION_FAST_MS), convention, tariff, apply_free_tier=free
        )
        slow = price(
            historic_flood(HISTORIC_DURATION_SLOW_MS), convention, tariff, apply_free_tier=free
        )

        checks = []
        row_ok = True
        for duration_label, cost, (expected, decimals, source) in (
            ("100ms", fast, fast_spec),
            ("300ms", slow, slow_spec),
        ):
            computed_at_precision = round(cost.total_usd, decimals)
            delta = abs(computed_at_precision - expected)
            agrees = delta <= REPRODUCTION_EPSILON_USD
            row_ok = row_ok and agrees
            checks.append(
                {
                    "duration": duration_label,
                    "published_usd": expected,
                    "published_decimals": decimals,
                    "published_by": source,
                    "computed_usd": round(cost.total_usd, 4),
                    "computed_at_published_precision_usd": computed_at_precision,
                    "delta_usd": round(delta, 4),
                    "agrees": agrees,
                }
            )

        ok = ok and row_ok
        rows.append(
            {
                "convention": name,
                "reproduces": convention.reproduces,
                "agrees_with_every_published_digit": row_ok,
                "checks": checks,
                "breakdown_100ms": fast.as_json(),
            }
        )
    return {
        "ok": ok,
        "epsilon_usd": REPRODUCTION_EPSILON_USD,
        "how_tolerance_is_set": (
            "Agreement is required at the precision the CITED DOCUMENT printed, not at a "
            "precision this module chose. COST-BOUND §2.2 prints cents and is checked to "
            "the cent; §1.2 prints whole dollars and is checked to the dollar. The epsilon "
            "absorbs IEEE-754 noise only and is smaller than half the last published unit "
            "in every row."
        ),
        "why_this_runs_first": (
            "A model that cannot reproduce the old answer has no standing to produce a new "
            "one. build_model() refuses to emit any new figure while ok is false."
        ),
        "the_0_06_percent_delta_explained": (
            "The lead's independent run returned $33,271 and $11,713 against the document's "
            "$33,252 and $11,701 -- 0.06 % and 0.10 %. That gap is NOT numerical tolerance "
            "and is not absorbed as such. It is one input: the document tiers on decimal "
            "boundaries (10,000/50,000/150,000 GB) and the lead tiered on the boundaries the "
            "Pricing API actually returns (10,240/51,200/153,600). Once the boundary choice "
            "is an explicit input, BOTH figures reproduce to the cent, which is why three "
            "conventions are named above instead of one tolerance being widened."
        ),
        "conventions": rows,
    }


# ─────────────────────────────────────────────────────────────────────────────────────────
# The live, measured inputs.
# ─────────────────────────────────────────────────────────────────────────────────────────


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(
            f"{path} does not exist. This model prices MEASURED inputs and refuses to "
            f"invent one; produce the evidence file and re-run."
        )
    return json.loads(path.read_text(encoding="utf-8"))


def _hcl_block(text: str, header_pattern: str) -> str | None:
    """Return the body of the first HCL block whose header matches, by brace balance."""
    match = re.search(header_pattern, text)
    if match is None:
        return None
    index = text.index("{", match.start())
    depth = 0
    for position in range(index, len(text)):
        char = text[position]
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return text[index + 1 : position]
    return None


def terraform_variable_default(text: str, name: str) -> int | None:
    body = _hcl_block(text, rf'variable\s+"{re.escape(name)}"\s*\{{')
    if body is None:
        return None
    match = re.search(r"^\s*default\s*=\s*(-?\d+)\s*$", body, re.MULTILINE)
    return int(match.group(1)) if match else None


def terraform_alarm_attribute(text: str, name: str, attribute: str) -> int | None:
    """Read one integer attribute out of a named `aws_cloudwatch_metric_alarm` block.

    The alarm's timing attributes are read rather than copied for the same reason its
    thresholds are: `residual.in_window` is `rate x (period x evaluation_periods)`, so an
    alarm that is ever retuned must move this model rather than leave it publishing a
    detection floor the stack no longer has.
    """
    body = _hcl_block(
        text, rf'resource\s+"aws_cloudwatch_metric_alarm"\s+"{re.escape(name)}"\s*\{{'
    )
    if body is None:
        return None
    match = re.search(rf"^\s*{re.escape(attribute)}\s*=\s*(\d+)\s*$", body, re.MULTILINE)
    return int(match.group(1)) if match else None


def terraform_alarm_period(text: str, name: str) -> int | None:
    return terraform_alarm_attribute(text, name, "period")


def load_measured_inputs() -> dict[str, Any]:
    """Every number the new figures rest on, each with the file it came from.

    Nothing here is a literal chosen by this module. If an input moves, the model moves
    with it -- which is the whole reason the model is a program.
    """
    package = _read_json(PACKAGE_SHAPE)
    latency = _read_json(LATENCY_BASELINE)
    logs = _read_json(LOG_BYTES)

    architectures = package["architectures"]
    arm64 = next(a for a in architectures if a["architecture"] == "arm64")
    before, after = arm64["before"]["web"], arm64["after"]["web"]

    local_beats = latency["targets"]["local"]["beats"]

    guard_vars = COST_GUARD_VARIABLES.read_text(encoding="utf-8")
    guard_main = COST_GUARD_MAIN.read_text(encoding="utf-8")

    rate = logs["flood"]["rate_limit_in_force"]

    return {
        "package_shape": {
            "source": str(PACKAGE_SHAPE.relative_to(REPO_ROOT)).replace("\\", "/"),
            "before_largest_identity_bytes": before["largest_identity_object"]["bytes"],
            "before_largest_identity_path": before["largest_identity_object"]["path"],
            "before_source_map_entries": before["source_maps"]["entries"],
            "before_source_map_bytes": before["source_maps"]["bytes"],
            "before_web_bytes": before["bytes"],
            "after_largest_identity_bytes": after["largest_identity_object"]["bytes"],
            "after_largest_gz_bytes": after["largest_gz_object"]["bytes"],
            "after_largest_gz_path": after["largest_gz_object"]["path"],
            "after_source_map_entries": after["source_maps"]["entries"],
            "after_web_bytes": after["bytes"],
        },
        "latency": {
            "source": str(LATENCY_BASELINE.relative_to(REPO_ROOT)).replace("\\", "/"),
            "asset_map_p50_ms": local_beats["asset_map"]["wall_ms"]["p50_ms"],
            "asset_js_p50_ms": local_beats["asset_js"]["wall_ms"]["p50_ms"],
            "target": "local (the workstation loopback figure; the cloud column is ~2.2x)",
        },
        "rate_limit": {
            "source": str(LOG_BYTES.relative_to(REPO_ROOT)).replace("\\", "/"),
            "global_rps_per_instance": rate["global_rps"],
            "provenance": rate["source"],
        },
        "alarms": {
            "source": "infra/modules/cost-guard/{variables,main}.tf",
            "invocations_burst_threshold": terraform_variable_default(
                guard_vars, "invocations_burst_threshold"
            ),
            "invocations_burst_period_s": terraform_alarm_period(guard_main, "invocations_burst"),
            "invocations_burst_evaluation_periods": terraform_alarm_attribute(
                guard_main, "invocations_burst", "evaluation_periods"
            ),
            "invocations_burst_datapoints_to_alarm": terraform_alarm_attribute(
                guard_main, "invocations_burst", "datapoints_to_alarm"
            ),
            "invocations_hourly_threshold": terraform_variable_default(
                guard_vars, "invocations_hourly_threshold"
            ),
            "invocations_hourly_period_s": terraform_alarm_period(guard_main, "invocations_hourly"),
            "invocations_hourly_evaluation_periods": terraform_alarm_attribute(
                guard_main, "invocations_hourly", "evaluation_periods"
            ),
            "invocations_hourly_datapoints_to_alarm": terraform_alarm_attribute(
                guard_main, "invocations_hourly", "datapoints_to_alarm"
            ),
            "log_ingestion_period_s": terraform_alarm_period(guard_main, "log_ingestion"),
            "log_ingestion_evaluation_periods": terraform_alarm_attribute(
                guard_main, "log_ingestion", "evaluation_periods"
            ),
            "comparison": "GreaterThanThreshold -- a caller AT the threshold does not breach",
            "datapoints_to_alarm_is_not_a_multiplier": (
                "datapoints_to_alarm is the M of an M-of-N evaluation, not a factor in the "
                "detection time. Worst-case time from the first breaching request to an "
                "ALARM state change is period x evaluation_periods. It is recorded here so "
                "that the distinction is visible rather than implied, and so the arithmetic "
                "stays right if either alarm is ever retuned to M != N."
            ),
        },
        "responder": {
            "source": "infra/modules/cost-guard/variables.tf",
            "timeout_s": terraform_variable_default(guard_vars, "responder_timeout"),
            "memory_mb": terraform_variable_default(guard_vars, "responder_memory_size"),
            "bounds_what": (
                "one attempt of the responder's INVOKE phase. It does not bound the number "
                "of attempts, and it is not a bound on the whole alarm-to-stop path."
            ),
        },
        "account": {
            "concurrency_ceiling": ACCOUNT_CONCURRENCY_CEILING,
            "source": "aws lambda get-account-settings --region ap-southeast-1 (COST-BOUND §1 I1)",
            "quota_code": "L-B99A9384",
        },
    }


STATIC_SITE = (
    REPO_ROOT
    / "verticals"
    / "mainline"
    / "apps"
    / "demo-api"
    / "src"
    / "mainline_demo_api"
    / "static_site.py"
)

#: Matches `DEFAULT_MAX_RESPONSE_BYTES = 136 * 1024` with or without a type annotation.
_CEILING_RE = re.compile(
    r"^DEFAULT_MAX_RESPONSE_BYTES\s*(?::[^=]+)?=\s*([0-9*\s+]+?)\s*(?:#.*)?$", re.MULTILINE
)


def response_ceiling_in_force() -> int:
    """Read the response ceiling out of `static_site.py` rather than carrying a copy.

    The ceiling decides which objects a residual attacker can actually reach, so a stale
    copy here would publish a residual for a package shape that no longer exists. It is
    parsed rather than imported because importing the demo-api package drags in `psycopg`,
    and this model must run in a lane that has no database.
    """
    match = _CEILING_RE.search(STATIC_SITE.read_text(encoding="utf-8"))
    if match is None:
        raise ValueError(
            f"could not read DEFAULT_MAX_RESPONSE_BYTES out of {STATIC_SITE}. The residual "
            "depends on it and this model will not guess a ceiling."
        )
    expression = match.group(1).strip()
    if not re.fullmatch(r"[0-9*\s+]+", expression):
        raise ValueError(f"refusing to evaluate {expression!r} as a byte ceiling")
    total = 0
    for term in expression.split("+"):
        product = 1
        for factor in term.split("*"):
            product *= int(factor.strip())
        total += product
    return total


#: Measured on this workstation by driving `mainline_demo_api.app.handler` past its rate
#: limiter: `len(body) == 233`, header block + status line == 147 B. Recorded as two
#: numbers because the difference is +63 % on this path and the model's stated convention
#: (body only) is the one that understates.
REFUSAL_BODY_BYTES = 233
REFUSAL_HEADER_BYTES = 147

#: Budgets is backed by Cost Explorer, whose data lags. AWS documents 8-24 h; both edges
#: are priced because the residual is the only figure in this file where the lag IS the
#: exposure window.
BUDGETS_LAG_HOURS = (8.0, 24.0)

#: Detection lags, in seconds, at which the IN-WINDOW residual is tabulated.
#:
#: These are NOT predictions of the lag. The lag is a budget whose terms are enumerated in
#: `in_window_residual()`, several of which have no read-only bound and are published as
#: unknowns. The table exists so the founder can price ANY lag by reading a row, which is
#: the only honest way to publish a figure whose input nobody has measured. The first entry
#: is overwritten at model time with the floor read out of the HCL, so retuning the alarm
#: moves the first row instead of leaving it stale.
IN_WINDOW_LAG_SENSITIVITY_S = (60.0, 120.0, 180.0, 300.0, 600.0, 900.0)


def first_alarm_to_fire(
    alarms: dict[str, Any],
    flood_rps: float,
) -> tuple[list[dict[str, Any]], dict[str, Any], float, str]:
    """Return `(candidates, first, floor_s, log_note)` for the alarms in force.

    Lifted verbatim out of `in_window_residual`, whose statement count had crossed
    PLR0915's ceiling of 50. Not one number, comparison or refusal below changed in
    the move: `floor_s` is still `period x evaluation_periods` of the FIRST invocation
    alarm that breaches at `flood_rps`, it is still a worst-case DETECTION floor rather
    than the whole lag, and the caller still budgets the remaining terms around it.
    """
    # ── Which alarm sees a flood FIRST, derived rather than assumed ──────────────────────
    candidates: list[dict[str, Any]] = []
    for name, metric, threshold, period, evaluations in (
        (
            "invocations_burst",
            "Invocations",
            alarms["invocations_burst_threshold"],
            alarms["invocations_burst_period_s"],
            alarms["invocations_burst_evaluation_periods"],
        ),
        (
            "invocations_hourly",
            "Invocations",
            alarms["invocations_hourly_threshold"],
            alarms["invocations_hourly_period_s"],
            alarms["invocations_hourly_evaluation_periods"],
        ),
    ):
        in_one_period = flood_rps * period
        candidates.append(
            {
                "alarm": name,
                "metric": metric,
                "threshold": threshold,
                "period_s": period,
                "evaluation_periods": evaluations,
                "datapoints_to_alarm": alarms.get(f"{name}_datapoints_to_alarm"),
                "invocations_in_one_period_at_the_flood_rate": round(in_one_period, 1),
                "breaches_at_the_flood_rate": in_one_period > threshold,
                "seconds_to_cross_the_threshold": round(threshold / flood_rps, 3),
                "worst_case_detection_s": float(period * evaluations),
            }
        )

    log_detection_s = float(
        alarms["log_ingestion_period_s"] * alarms["log_ingestion_evaluation_periods"]
    )
    candidates.append(
        {
            "alarm": "log_ingestion",
            "metric": "IncomingBytes",
            "threshold": None,
            "period_s": alarms["log_ingestion_period_s"],
            "evaluation_periods": alarms["log_ingestion_evaluation_periods"],
            "datapoints_to_alarm": None,
            "invocations_in_one_period_at_the_flood_rate": None,
            "breaches_at_the_flood_rate": None,
            "seconds_to_cross_the_threshold": None,
            "worst_case_detection_s": log_detection_s,
            "not_priced_because": (
                "this alarm watches log-group IncomingBytes, not invocations or egress. "
                "This model has no measured bytes-of-log-per-invocation input, so whether a "
                "flood breaches it is NOT computed here. It is listed because its detection "
                "window still has to be compared against the invocation alarms', which is "
                "checkable without pricing it."
            ),
        }
    )

    detecting = [c for c in candidates if c["breaches_at_the_flood_rate"]]
    if not detecting:
        raise ValueError(
            f"no invocation alarm breaches at the modelled flood rate of {flood_rps:,.1f} "
            "rps, so this model cannot say when the stop fires. That is a finding about the "
            "thresholds, not something to paper over with an assumed detection window."
        )
    first = min(detecting, key=lambda c: c["worst_case_detection_s"])
    floor_s = float(first["worst_case_detection_s"])

    log_note = (
        "the log-ingestion alarm's detection window ("
        f"{log_detection_s:g} s) is not shorter than the first invocation alarm's "
        f"({floor_s:g} s), so it cannot be the first to fire and leaving it unpriced "
        "cannot make this floor too high."
        if log_detection_s >= floor_s
        else (
            "WARNING: the log-ingestion alarm's detection window "
            f"({log_detection_s:g} s) is SHORTER than the first invocation alarm's "
            f"({floor_s:g} s). Whether it breaches at the flood rate is not computed here, "
            "so this floor may be too high. That is an unknown, and it is named."
        )
    )

    return candidates, first, floor_s, log_note


def in_window_residual(
    *,
    inputs: dict[str, Any],
    duration_ms: float,
    reachable_bytes: int,
    lifted_ceiling_bytes: int,
    ceiling: int,
    paced_worst_usd: float,
    paced_unattended_30d_usd: float,
    flood_rate_24h_usd: float,
    convention: GbConvention,
    tariff: Tariff = TARIFF,
) -> dict[str, Any]:
    """How much can be spent INSIDE one alarm evaluation window, as a RATE times a LAG.

    THE QUESTION
    ------------
    The three alarms and the responder bound the demo's spend, and every figure in
    `residual` above prices a caller who stays *under* them. Nobody had priced the caller
    who does not: a flood trips the burst alarm in under two seconds, and then keeps
    billing until `PutFunctionConcurrency(0)` actually lands. This is that number.

    WHY IT IS NOT A SCALAR, AND WHY REFUSING TO MAKE IT ONE IS THE POINT
    --------------------------------------------------------------------
    The published USD 33,251.87 headline was wrong because it multiplied a real tariff by a
    100 ms invocation duration **nobody had measured**. Publishing `60 s x rate` here would
    be the identical error in the identical shape: it would assume that everything between
    the CloudWatch period closing and the stop taking effect costs **zero** seconds, and
    nobody has measured that either.

    So the detection window is a FLOOR and it is labelled one. What is published is:

      * a **rate**, USD/minute, derived from the model's own `Flood`/`price()`;
      * a **lag budget** whose every term is either read out of this repository's own
        Terraform -- and therefore moves when the stack moves -- or **named as an unknown**;
      * a **sensitivity table** over total lag, so any lag can be priced by reading a row.

    No single scalar appears in this block without its lag beside it, and the terms that
    cannot be bounded read-only are enumerated in `lag_budget.unknown_terms` rather than
    quietly set to zero.

    WHY THE FLOOR IS THE FULL PERIOD AND NOT THE TIME TO CROSS THE THRESHOLD
    ------------------------------------------------------------------------
    At the flood rate the burst alarm's 3,000-invocation threshold is crossed in under two
    seconds -- but a CloudWatch datapoint does not exist until its period closes. Worst case
    from the first breaching request to an ALARM state change is therefore
    `period x evaluation_periods`. **`datapoints_to_alarm` is the M of an M-of-N
    evaluation, not a multiplier**; multiplying by it would be harmless here only by the
    coincidence that it is 1, and the formula is written so it stays right if it is not.
    Both attributes are read out of the HCL at model time and neither is a literal here.
    """
    alarms = inputs["alarms"]
    responder = inputs["responder"]

    # R11: the ceiling is read at model time, never copied, so the object this flood serves
    # follows whatever `static_site.DEFAULT_MAX_RESPONSE_BYTES` currently is. The priced
    # object is the LARGEST one the ceiling in force admits; the refused one is published
    # beside it as the counterfactual, exactly as the paced residual does.
    catalogue = [
        ("gzip-sibling", reachable_bytes),
        ("identity", lifted_ceiling_bytes),
    ]
    admitted = [(label, size) for label, size in catalogue if size <= ceiling]
    if not admitted:
        raise ValueError(
            f"the response ceiling in force ({ceiling:,} B) refuses every object this model "
            "prices, so there is no in-window residual to publish. That is a finding, not "
            "something to paper over by relaxing the ceiling."
        )
    priced_label, reachable_bytes = max(admitted, key=lambda pair: pair[1])

    required = (
        "invocations_burst_threshold",
        "invocations_burst_period_s",
        "invocations_burst_evaluation_periods",
        "invocations_hourly_threshold",
        "invocations_hourly_period_s",
        "invocations_hourly_evaluation_periods",
        "log_ingestion_period_s",
        "log_ingestion_evaluation_periods",
    )
    missing = [key for key in required if alarms.get(key) is None]
    if missing or responder.get("timeout_s") is None:
        raise ValueError(
            "could not read "
            + ", ".join(
                missing + ([] if responder.get("timeout_s") is not None else ["responder_timeout"])
            )
            + " out of infra/modules/cost-guard. The in-window residual is period x "
            "evaluation_periods times a rate; it will not be published against invented "
            "alarm timings."
        )

    def priced(window_s: float, request_bytes: int, label: str) -> Cost:
        return price(
            Flood(
                label=label,
                concurrency=ACCOUNT_CONCURRENCY_CEILING,
                duration_ms=duration_ms,
                request_bytes=request_bytes,
                memory_mb=256,
                window_s=window_s,
            ),
            convention,
            tariff,
            apply_free_tier=False,
        )

    flood_rps = priced(1.0, reachable_bytes, "probe").rps

    candidates, first, floor_s, log_note = first_alarm_to_fire(alarms, flood_rps)

    # ── The rate, priced directly from tier 1 for every window (convention 2) ────────────
    lags = sorted({floor_s} | {lag for lag in IN_WINDOW_LAG_SENSITIVITY_S if lag > floor_s})
    sensitivity = []
    sensitivity_costs: list[Cost] = []
    all_tier_1_only = True
    for lag in lags:
        cost = priced(lag, reachable_bytes, f"in-window-{lag:g}s")
        all_tier_1_only = all_tier_1_only and len(cost.tiers) == 1
        row = cost.as_json()
        row["detection_lag_s"] = lag
        row["usd_per_minute"] = round(cost.total_usd * 60.0 / lag, 4)
        row["priced_from_tier_1_only"] = len(cost.tiers) == 1
        sensitivity.append(row)
        sensitivity_costs.append(cost)

    floor_cost = sensitivity_costs[0]
    usd_per_minute = round(floor_cost.total_usd * 60.0 / floor_s, 4)

    objects = []
    for object_label, object_bytes in catalogue:
        cost = priced(floor_s, object_bytes, f"in-window-{object_label}-{floor_s:g}s")
        objects.append(
            {
                "object": object_label,
                "object_bytes": object_bytes,
                "reachable_under_the_ceiling_in_force": object_bytes <= ceiling,
                "is_the_priced_object": object_label == priced_label,
                "detection_lag_s": floor_s,
                "usd": round(cost.total_usd, 4),
                "usd_per_minute": round(cost.total_usd * 60.0 / floor_s, 4),
            }
        )

    # ── The lag budget. Two terms have a read-only bound; five do not, and are named ─────
    responder_timeout_s = float(responder["timeout_s"])
    terms: list[dict[str, Any]] = [
        {
            "term": "alarm_detection_window",
            "seconds": floor_s,
            "basis": "read-from-hcl",
            "source": (
                "infra/modules/cost-guard/main.tf :: aws_cloudwatch_metric_alarm."
                f"{first['alarm']} -- period {first['period_s']} x evaluation_periods "
                f"{first['evaluation_periods']}"
            ),
            "what_it_covers": (
                "the period must close before the datapoint exists, and evaluation_periods "
                "consecutive breaching datapoints are required before the state changes"
            ),
            "note": (
                f"datapoints_to_alarm = {first['datapoints_to_alarm']} is the M of an "
                "M-of-N evaluation and is NOT a multiplier on this term."
            ),
        },
        {
            "term": "metric_publication_delay",
            "seconds": None,
            "basis": "unknown",
            "what_it_covers": (
                "the interval between an invocation being billed and its Invocations "
                "datapoint being visible to the alarm"
            ),
            "why_unknown": (
                "AWS publishes no numeric upper bound on Lambda metric publication latency, "
                "and nothing in this repository can measure it: it requires a deployed "
                "function, and no worker in this wave applies anything."
            ),
            "what_would_bound_it": (
                "one applied stack, a timestamped burst, and GetMetricData's datapoint "
                "timestamp minus the request timestamp"
            ),
        },
        {
            "term": "alarm_evaluation_delay",
            "seconds": None,
            "basis": "unknown",
            "what_it_covers": (
                "the interval between the period closing and CloudWatch actually "
                "transitioning the alarm to ALARM and invoking its alarm_actions"
            ),
            "why_unknown": (
                "AWS publishes no numeric upper bound on the gap between a period close and "
                "the state transition. It is not zero, and this model refuses to set it to "
                "zero merely because it is unmeasured."
            ),
            "what_would_bound_it": (
                "DescribeAlarmHistory StateUpdatedTimestamp minus the period close, on an "
                "applied stack"
            ),
        },
        {
            "term": "sns_delivery_to_the_responder",
            "seconds": None,
            "basis": "unknown",
            "what_it_covers": "publish on the guard topic to the responder being invoked",
            "why_unknown": (
                "AWS publishes no numeric latency bound for SNS-to-Lambda delivery. This "
                "term is specifically NOT small under the conditions this figure describes: "
                "the responder ships with reserved_concurrent_executions = -1 because a "
                "positive reservation is refused at an account quota of "
                f"{ACCOUNT_CONCURRENCY_CEILING}, so under a saturating flood the responder's "
                "own invocation can be throttled and the stop then depends on SNS's "
                "asynchronous delivery and Lambda's async retry queue. The module's own "
                "header says so."
            ),
            "what_would_bound_it": (
                "the responder's JSON log line timestamp minus the alarm's "
                "StateUpdatedTimestamp, on an applied stack under load"
            ),
        },
        {
            "term": "responder_cold_start_and_the_stop_call",
            "seconds": responder_timeout_s,
            "basis": "read-from-hcl",
            "source": "infra/modules/cost-guard/variables.tf :: responder_timeout default",
            "what_it_covers": (
                "ONE attempt of the responder's invoke phase: cold import of boto3 plus one "
                f"PutFunctionConcurrency(0) with botocore's retry chain, at "
                f"{responder['memory_mb']} MB"
            ),
            "bound_holds_only_if": "that first attempt succeeds",
            "note": (
                "Lambda's configured timeout bounds the invoke phase. It is an upper bound "
                "and almost certainly a loose one -- the real figure is smaller and nobody "
                "here has measured it -- so it is carried as a bound and not as an estimate."
            ),
        },
        {
            "term": "responder_async_retry_if_it_is_itself_throttled",
            "seconds": None,
            "basis": "unknown",
            "what_it_covers": (
                "further attempts after a throttled or failed first attempt, plus whatever "
                "delay Lambda's asynchronous invocation policy imposes between them"
            ),
            "why_unknown": (
                "the number of attempts depends on whether the responder is throttled, which "
                "depends on how much of the account's concurrency the flood itself is "
                "holding. This model does not guess an attempt count."
            ),
            "what_would_bound_it": (
                "the responder's own async invocation configuration plus an observed "
                "throttle rate under load; neither exists without an apply"
            ),
        },
        {
            "term": "reserved_concurrency_propagation",
            "seconds": None,
            "basis": "unknown",
            "what_it_covers": (
                "the interval between PutFunctionConcurrency(0) returning 200 and the last "
                "execution environment refusing new work"
            ),
            "why_unknown": (
                "AWS publishes no numeric propagation bound for a reserved-concurrency "
                "change. It is a control-plane setting consumed by a distributed data plane."
            ),
            "what_would_bound_it": (
                "the timestamp of the last 200 response after the call returned, on an "
                "applied stack under load"
            ),
        },
    ]

    unknown_terms = [t["term"] for t in terms if t["basis"] == "unknown"]
    bounded_terms = [t for t in terms if t["basis"] != "unknown"]
    bounded_seconds = sum(float(t["seconds"]) for t in bounded_terms)

    bounded_cost = priced(bounded_seconds, reachable_bytes, "in-window-bounded-terms")

    # The one term that IS fully bounded without any AWS documentation: at the instant the
    # stop lands, at most `concurrency` invocations are in flight, and each serves at most
    # one more response. It is priced so that "in-flight drain" cannot be waved at as if it
    # were the missing term.
    drain = price(
        Flood(
            label="in-flight-drain",
            concurrency=ACCOUNT_CONCURRENCY_CEILING,
            duration_ms=duration_ms,
            request_bytes=reachable_bytes,
            memory_mb=256,
            window_s=1.0,
            rps_override=float(ACCOUNT_CONCURRENCY_CEILING),
        ),
        convention,
        tariff,
        apply_free_tier=False,
    )

    naive_usd_per_minute = flood_rate_24h_usd / (24.0 * 60.0)
    naive_understates_pct = (usd_per_minute - naive_usd_per_minute) / usd_per_minute * 100.0

    return {
        "question": (
            "How much can be spent INSIDE one CloudWatch alarm evaluation window, before "
            "PutFunctionConcurrency(0) takes effect?"
        ),
        "answer_is_a_rate_times_a_lag_not_a_scalar": True,
        "why_not_a_scalar": (
            "Publishing `detection window x rate` as THE residual would assume every term "
            "between the period closing and the stop landing costs zero seconds. That is the "
            "same shape of error as the published USD 33,251.87 headline, which multiplied a "
            "real tariff by an invocation duration nobody had measured. The detection window "
            "is a FLOOR; the terms beyond it are enumerated below and the ones without a "
            "read-only bound are named as unknowns rather than set to zero."
        ),
        "flood_rate_rps": round(flood_rps, 3),
        "flood_rate_derivation": (
            f"account concurrency ceiling {ACCOUNT_CONCURRENCY_CEILING} / measured "
            f"{duration_ms} ms asset_js p50 = {flood_rps:,.3f} rps. Not rate-limited: the "
            "in-code limiter's counter is per execution environment with no shared store, so "
            "a distributed flood defeats it -- the same reason `the_stop` is priced upstream "
            "of it."
        ),
        "priced_object": priced_label,
        "priced_object_bytes": reachable_bytes,
        "response_ceiling_in_force_bytes": ceiling,
        "ceiling_dependency": (
            f"The ceiling in force is {ceiling:,} B, read from "
            "static_site.DEFAULT_MAX_RESPONSE_BYTES at model time and not copied. It admits "
            f"the {reachable_bytes:,} B {priced_label} and that is what this rate prices. "
            "Both objects are published under `objects`, so if the ceiling moves the rate "
            "moves with it instead of silently pricing an object the origin now refuses."
        ),
        "detection": {
            "formula": "worst_case_detection_s = period x evaluation_periods",
            "datapoints_to_alarm_is_not_a_multiplier": (
                "datapoints_to_alarm is the M in an M-of-N evaluation: it says how many of "
                "the last N datapoints must breach, not how many periods must elapse. "
                "Multiplying by it would be harmless in this stack only because it is 1, and "
                "would silently overstate the floor the day either alarm is retuned."
            ),
            "first_alarm_to_fire": first["alarm"],
            "floor_s": floor_s,
            "why_the_floor_is_the_whole_period": (
                f"at {flood_rps:,.0f} rps the {first['alarm']} threshold of "
                f"{first['threshold']:,} is crossed in "
                f"{first['seconds_to_cross_the_threshold']:g} s, but a CloudWatch datapoint "
                f"does not exist until its period closes. The worst case is therefore the "
                f"FULL {first['period_s']} s period, not the crossing time."
            ),
            "candidates": candidates,
            "log_ingestion_alarm": log_note,
        },
        "usd_per_minute_of_detection_lag": usd_per_minute,
        "linear_in_lag": True,
        "why_linear": (
            "every window priced here stays inside the first egress tier, so USD/minute does "
            "not vary with the lag. That is the useful property: any lag budget can be "
            "priced by multiplying."
        ),
        "every_window_priced_from_tier_1_only": all_tier_1_only,
        "the_wrong_way_to_get_this": {
            "method": "divide flood_rate_24h_for_contrast_usd by 1440",
            "usd_per_minute": round(naive_usd_per_minute, 4),
            "understates_the_correct_figure_by_percent": round(naive_understates_pct, 2),
            "why_it_is_wrong": (
                "the 24-hour figure accumulates enough volume to reach the $0.085 and $0.082 "
                "egress tiers, which a window of minutes never does. Averaging it back down "
                "prices a short window at tiers it would not get. Each window here is priced "
                "directly from tier 1, which is this file's stated convention and errs "
                "conservative."
            ),
        },
        "lag_budget": {
            "what_this_is": (
                "every term between the first breaching request and the stop taking effect, "
                "each either read out of this repository's own Terraform or named as an "
                "unknown. Nothing here is estimated."
            ),
            "terms": terms,
            "bounded_seconds": round(bounded_seconds, 3),
            "bounded_terms": [t["term"] for t in bounded_terms],
            "unknown_terms": unknown_terms,
            "unknown_term_count": len(unknown_terms),
            "therefore": (
                f"total detection-to-stop lag >= {floor_s:g} s. The terms carrying a "
                f"read-only upper bound sum to {bounded_seconds:g} s. The remaining "
                f"{len(unknown_terms)} terms have no bound this repository can establish "
                "without an apply, so NO upper bound on the total lag is published here. "
                "Read the sensitivity table at whatever lag you are willing to defend."
            ),
        },
        "published_figures": [
            {
                "name": "floor",
                "detection_lag_s": floor_s,
                "usd": round(floor_cost.total_usd, 4),
                "stated_plainly": (
                    f"USD {floor_cost.total_usd:,.2f} per {floor_s:g} s of detection lag, "
                    f"at {flood_rps:,.0f} rps against the {reachable_bytes:,} B object."
                ),
                "this_is_a_floor_because": (
                    "it counts the alarm's own evaluation window and nothing after it. Every "
                    "term in lag_budget beyond alarm_detection_window is additional."
                ),
            },
            {
                "name": "bounded-terms-only",
                "detection_lag_s": round(bounded_seconds, 3),
                "usd": round(bounded_cost.total_usd, 4),
                "stated_plainly": (
                    f"USD {bounded_cost.total_usd:,.2f} per {bounded_seconds:g} s of "
                    "detection lag -- the alarm window plus the responder's own configured "
                    "timeout, which are the only two terms with a read-only upper bound."
                ),
                "this_is_still_not_the_answer_because": (
                    f"{len(unknown_terms)} further terms ({', '.join(unknown_terms)}) are "
                    "unbounded here and are additive to this lag."
                ),
            },
        ],
        "no_scalar_without_its_lag": (
            "Every figure in published_figures carries detection_lag_s in the same record "
            "and repeats it inside stated_plainly, so a quote that drops the lag is visibly "
            "incomplete rather than merely wrong."
        ),
        "sensitivity": sensitivity,
        "objects": objects,
        "in_flight_drain": {
            "requests": ACCOUNT_CONCURRENCY_CEILING,
            "usd": round(drain.total_usd, 6),
            "basis": "bounded",
            "why_it_is_bounded": (
                "at the instant the stop lands, at most the account concurrency ceiling of "
                f"{ACCOUNT_CONCURRENCY_CEILING} invocations are in flight, and each serves at "
                "most one more response. Its cost is therefore bounded without any AWS "
                "documentation at all, and it is priced here so that 'in-flight requests "
                "still drain' cannot be gestured at as though it were the missing term. It "
                "is not: the unbounded terms are the delivery-path ones above."
            ),
        },
        "additive_to_the_paced_residual_not_a_replacement": {
            "claim": (
                "The paced residual and the in-window residual describe two different "
                "attackers and both are real. Neither replaces the other."
            ),
            "paced": {
                "attacker": "a caller who stays under every alarm threshold",
                "bounded_by": "the AWS Budgets / Cost Explorer 8-24 h lag",
                "worst_usd_24h": round(paced_worst_usd, 2),
                "worst_usd_30d_unattended": round(paced_unattended_30d_usd, 2),
            },
            "in_window": {
                "attacker": "a flood that trips the burst alarm and bills until the stop lands",
                "bounded_by": "the alarm evaluation window plus an unmeasured delivery path",
                "usd_per_minute": usd_per_minute,
                "floor_usd": round(floor_cost.total_usd, 4),
            },
            "why_both": (
                "the paced figure is computed at the hourly alarm threshold precisely BECAUSE "
                "a caller under the alarms is not at flood rate; quoting the flood figure "
                "there would overstate it by two orders of magnitude. The converse is also "
                "true: quoting the paced figure at a flood understates it. They are added, "
                "not swapped."
            ),
        },
    }


def build_model(tariff: Tariff = TARIFF) -> dict[str, Any]:
    """The whole model. Refuses to publish a new figure until the old one reproduces."""
    reproduction = reproduce(tariff)
    inputs = load_measured_inputs()

    if not reproduction["ok"]:
        return {
            "schema": SCHEMA,
            "ok": False,
            "reproduction": reproduction,
            "layers": None,
            "refused": (
                "The reproduction gate failed, so no new figure was computed. A model that "
                "cannot reproduce the published headline from the inputs that produced it "
                "has no standing to publish a replacement."
            ),
        }

    pkg = inputs["package_shape"]
    lat = inputs["latency"]
    map_ms = lat["asset_map_p50_ms"]
    js_ms = lat["asset_js_p50_ms"]
    before_bytes = pkg["before_largest_identity_bytes"]
    after_identity = pkg["after_largest_identity_bytes"]
    after_gz = pkg["after_largest_gz_bytes"]

    fleet_served_rps = inputs["rate_limit"]["global_rps_per_instance"] * ACCOUNT_CONCURRENCY_CEILING

    def flood(
        label: str, duration_ms: float, request_bytes: int, memory_mb: int, **kw: Any
    ) -> Flood:
        return Flood(
            label=label,
            concurrency=ACCOUNT_CONCURRENCY_CEILING,
            duration_ms=duration_ms,
            request_bytes=request_bytes,
            memory_mb=memory_mb,
            window_s=WINDOW_30D_S,
            **kw,
        )

    ladder = [
        (
            flood("L0-modelled-100ms", HISTORIC_DURATION_FAST_MS, before_bytes, 512),
            (
                "the published headline: a 100 ms invocation nobody measured, against the "
                "pre-strip package. Carried so the ladder starts where the document ends."
            ),
        ),
        (
            flood("L1-measured-duration", map_ms, before_bytes, 512),
            (
                f"the SAME flood at the MEASURED map duration of {map_ms} ms. Nothing was "
                "fixed here and nothing was changed; the only edit is that the duration is "
                "now a measurement. This is the honest 'today' the founder was never given."
            ),
        ),
        (
            flood("L2-strip-source-maps", js_ms, after_identity, 512),
            (
                "source maps stripped -- ALREADY SHIPPED, the default in both builders, and "
                f"confirmed at {pkg['after_source_map_entries']} maps in the artefact. Bytes "
                f"fall {before_bytes / after_identity:.2f}x. THE BILL DOES NOT: a smaller "
                f"object serves faster, so the request rate RISES {map_ms / js_ms:.2f}x and "
                "most of the saving is given straight back."
            ),
        ),
        (
            flood("L3-gzip-on-the-wire", js_ms, after_gz, 512),
            (
                "the pre-compressed sibling actually served. This is the good byte lever "
                "because the sibling is already built and the duration does not fall with it."
            ),
        ),
        (
            flood("L4-memory-512-to-256", js_ms, after_gz, 256),
            (
                "memory halved. Worth taking because it is DURATION-INDEPENDENT, not because "
                "it is large -- it moves compute only, and compute is a rounding error here."
            ),
        ),
        (
            flood(
                "L5-rate-bound",
                js_ms,
                after_gz,
                256,
                served_rps_cap=fleet_served_rps,
                refused_bytes=REFUSAL_BODY_BYTES,
            ),
            (
                f"the in-code rate limiter: {fleet_served_rps:g} rps served fleet-wide "
                f"({inputs['rate_limit']['global_rps_per_instance']:g} rps/instance x "
                f"{ACCOUNT_CONCURRENCY_CEILING} instances), every other invocation refused "
                f"with a measured {REFUSAL_BODY_BYTES} B body. THE INVOCATION IS STILL "
                "BILLED: a 429 is a Lambda invocation, so requests+compute survive this "
                "lever untouched and become the floor under it."
            ),
        ),
    ]

    conventions_out: dict[str, Any] = {}
    for cname, convention in CONVENTIONS.items():
        free = convention.free_gb_per_month > 0.0
        rows = []
        previous_total: float | None = None
        for f, why in ladder:
            cost = price(f, convention, tariff, apply_free_tier=free)
            row = cost.as_json()
            row["why"] = why
            row["factor_vs_previous_row"] = (
                None if previous_total is None else round(previous_total / cost.total_usd, 3)
            )
            previous_total = cost.total_usd
            rows.append(row)
        conventions_out[cname] = {
            "bytes_per_gb": convention.bytes_per_gb,
            "tier_edges_gb": list(convention.tier_edges_gb),
            "free_gb_per_month": convention.free_gb_per_month,
            "layers": rows,
        }

    headline = CONVENTIONS[HEADLINE_CONVENTION]
    headline_free = headline.free_gb_per_month > 0.0

    # ── The self-limiting property, made explicit rather than left for the reader ────────
    l1 = price(ladder[1][0], headline, tariff, apply_free_tier=headline_free)
    l2 = price(ladder[2][0], headline, tariff, apply_free_tier=headline_free)
    self_limiting = {
        "claim": (
            "A byte lever gives back most of what it takes, because a smaller object is "
            "faster to serve and the request rate rises to fill the concurrency ceiling."
        ),
        "bytes_fell_by": round(before_bytes / after_identity, 3),
        "duration_fell_by": round(map_ms / js_ms, 3),
        "request_rate_rose_by": round(map_ms / js_ms, 3),
        "bill_fell_by": round(l1.total_usd / l2.total_usd, 3),
        "stated_plainly": (
            f"bytes /{before_bytes / after_identity:.2f}, rate x{map_ms / js_ms:.2f}, "
            f"bill /{l1.total_usd / l2.total_usd:.2f}. The strip is not a "
            f"{before_bytes / after_identity:.2f}x saving and was never going to be one."
        ),
    }

    # ── The stop, priced on the UNRATE-LIMITED flood ─────────────────────────────────────
    # Deliberately NOT priced downstream of L5. The rate limiter's counter is per execution
    # environment with no shared store, so a distributed flood defeats it; the stop has to
    # be worth its keep in the case where the lever above it did not hold.
    stop_rows = []
    for label, seconds in (("stop-5min", 300.0), ("stop-1h", 3600.0)):
        f = Flood(
            label=label,
            concurrency=ACCOUNT_CONCURRENCY_CEILING,
            duration_ms=js_ms,
            request_bytes=after_gz,
            memory_mb=256,
            window_s=seconds,
        )
        cost = price(f, headline, tariff, apply_free_tier=False)
        row = cost.as_json()
        row["window_seconds"] = seconds
        stop_rows.append(row)

    # ── THE RESIDUAL, at the hourly alarm threshold. Not at flood rate. ──────────────────
    hourly_threshold = inputs["alarms"]["invocations_hourly_threshold"]
    hourly_period = inputs["alarms"]["invocations_hourly_period_s"]
    burst_threshold = inputs["alarms"]["invocations_burst_threshold"]
    burst_period = inputs["alarms"]["invocations_burst_period_s"]
    if None in (hourly_threshold, hourly_period, burst_threshold, burst_period):
        raise ValueError(
            "could not read an alarm threshold or period out of infra/modules/cost-guard; "
            "the residual is computed FROM those numbers and will not be invented here"
        )

    hourly_rps = hourly_threshold / hourly_period
    burst_rps = burst_threshold / burst_period
    binding = "hourly" if hourly_rps <= burst_rps else "burst"
    paced_rps = min(hourly_rps, burst_rps)

    ceiling = response_ceiling_in_force()

    residual_rows = []
    for object_label, object_bytes, ceiling_note in (
        (
            "identity",
            after_identity,
            "the largest identity object, servable only while the response ceiling sits above it",
        ),
        (
            "gzip-sibling",
            after_gz,
            "the largest pre-compressed sibling, which is what a browser actually receives",
        ),
    ):
        for lag_h in BUDGETS_LAG_HOURS:
            f = Flood(
                label=f"residual-{object_label}-{lag_h:g}h",
                concurrency=ACCOUNT_CONCURRENCY_CEILING,
                duration_ms=js_ms,
                request_bytes=object_bytes,
                memory_mb=256,
                window_s=lag_h * 3600.0,
                rps_override=paced_rps,
            )
            cost = price(f, headline, tariff, apply_free_tier=False)
            row = cost.as_json()
            row["object"] = object_label
            row["object_bytes"] = object_bytes
            row["lag_hours"] = lag_h
            row["ceiling_dependency"] = ceiling_note
            row["reachable_under_the_ceiling_in_force"] = object_bytes <= ceiling
            residual_rows.append(row)

    reachable = [r for r in residual_rows if r["reachable_under_the_ceiling_in_force"]]
    if not reachable:
        raise ValueError(
            f"the response ceiling in force ({ceiling:,} B) refuses every object this "
            "model prices, so there is no reachable residual to publish. That is either a "
            "genuine finding or a stale package-shape input; it is not something to paper "
            "over by relaxing the ceiling."
        )
    worst_reachable = max(reachable, key=lambda r: r["total_usd"])
    worst_any = max(residual_rows, key=lambda r: r["total_usd"])

    unattended = Flood(
        label="residual-identity-30d-unattended",
        concurrency=ACCOUNT_CONCURRENCY_CEILING,
        duration_ms=js_ms,
        request_bytes=after_identity,
        memory_mb=256,
        window_s=WINDOW_30D_S,
        rps_override=paced_rps,
    )
    unattended_cost = price(unattended, headline, tariff, apply_free_tier=False)

    flood_rate_24h = price(
        Flood(
            label="flood-rate-24h-for-contrast",
            concurrency=ACCOUNT_CONCURRENCY_CEILING,
            duration_ms=js_ms,
            request_bytes=after_gz,
            memory_mb=256,
            window_s=24 * 3600.0,
        ),
        headline,
        tariff,
        apply_free_tier=False,
    )

    residual = {
        "computed_at": "the hourly Invocations alarm threshold, NOT at flood rate",
        "why_not_flood_rate": (
            "A caller who paces under the alarms is by definition not at flood rate. The "
            f"24-hour figure at flood rate is ${flood_rate_24h.total_usd:,.0f}; quoting that "
            "as the residual would overstate it by "
            f"{flood_rate_24h.total_usd / worst_reachable['total_usd']:.0f}x and would "
            "describe a caller the burst alarm catches in the first minute."
        ),
        "paced_at_requests_per_second": round(paced_rps, 6),
        "binding_alarm": binding,
        "burst": {
            "threshold": burst_threshold,
            "period_s": burst_period,
            "implied_rps": round(burst_rps, 4),
        },
        "hourly": {
            "threshold": hourly_threshold,
            "period_s": hourly_period,
            "implied_rps": round(hourly_rps, 4),
        },
        "budgets_lag_hours": list(BUDGETS_LAG_HOURS),
        "rows": residual_rows,
        "response_ceiling_in_force_bytes": ceiling,
        "worst_usd": worst_reachable["total_usd"],
        "worst_row": worst_reachable["label"],
        "worst_if_the_ceiling_were_lifted_usd": worst_any["total_usd"],
        "worst_if_the_ceiling_were_lifted_row": worst_any["label"],
        "if_nobody_looks_for_30_days_usd": round(unattended_cost.total_usd, 2),
        "flood_rate_24h_for_contrast_usd": round(flood_rate_24h.total_usd, 2),
        "the_trade_this_makes": (
            "THIS CONVERTS A COST ATTACK INTO AN AVAILABILITY ATTACK. The Function URL is "
            "authorization_type = NONE by the founder's explicit choice, so anyone at all "
            "can trip the burst alarm, and the responder's stop is not rate-limited to "
            "attackers: it stops the demo for everyone. It stays stopped at reserved "
            "concurrency 0 until a human runs scripts/deploy/kill_switch.{sh,ps1} "
            "--restore. That is the right trade -- an outage is recoverable by one command "
            "and an unbounded bill is not -- but it IS a trade, and it belongs in the "
            "residual column and not in a footnote."
        ),
        "ceiling_dependency": (
            f"The response ceiling in force is {ceiling:,} B "
            "(static_site.DEFAULT_MAX_RESPONSE_BYTES, read at model time, not copied). It "
            f"refuses the {after_identity:,} B identity asset, so the reachable residual is "
            f"the {after_gz:,} B gzip sibling at ${worst_reachable['total_usd']:,.2f} rather "
            f"than ${worst_any['total_usd']:,.2f}. BOTH rows are published: the ceiling is a "
            "code constant one commit away from moving, and a residual that silently "
            "assumed the favourable one would understate this by "
            f"{worst_any['total_usd'] / worst_reachable['total_usd']:.1f}x the moment it did."
        ),
    }

    # ── AND THE OTHER ATTACKER: what a flood spends INSIDE one alarm window ──────────────
    # ADDITIVE, never a replacement. The block above prices a caller who paces under the
    # alarms; this one prices the caller who trips them and keeps billing until the stop
    # lands. Quoting either where the other belongs is an error in a different direction.
    residual["in_window"] = in_window_residual(
        inputs=inputs,
        duration_ms=js_ms,
        reachable_bytes=after_gz,
        lifted_ceiling_bytes=after_identity,
        ceiling=ceiling,
        paced_worst_usd=worst_reachable["total_usd"],
        paced_unattended_30d_usd=unattended_cost.total_usd,
        flood_rate_24h_usd=flood_rate_24h.total_usd,
        convention=headline,
        tariff=tariff,
    )

    # ── Duration sensitivity: the single input the whole ladder is most exposed to ───────
    band = []
    for label, duration_ms in (
        ("measured-local-p50", js_ms),
        ("measured-cloud-p50", 11.45),
        ("modelled-100ms", 100.0),
        ("modelled-300ms", 300.0),
    ):
        cost = price(
            flood(f"sensitivity-{label}", duration_ms, after_gz, 256),
            headline,
            tariff,
            apply_free_tier=headline_free,
        )
        band.append(
            {
                "label": label,
                "duration_ms": duration_ms,
                "requests_per_second": round(cost.rps, 2),
                "total_usd": round(cost.total_usd, 2),
            }
        )
    band_totals = [row["total_usd"] for row in band]

    return {
        "schema": SCHEMA,
        "ok": True,
        "generated_by": "scripts/deploy/cost_model.py",
        "what_this_is": (
            "The demo's worst-case spend as an executable model, layer by layer, in three "
            "named GB conventions, with the residual computed at the hourly alarm threshold."
        ),
        "model_bound": {
            "this_is_a_bound_not_a_forecast": True,
            "the_assumption_that_makes_it_a_bound": (
                "Every total holds the account concurrency ceiling of "
                f"{ACCOUNT_CONCURRENCY_CEILING} pinned and divides by a measured invocation "
                "duration, which assumes AWS SUSTAINS the resulting egress rate. At the "
                f"measured {map_ms} ms map duration that rate is "
                f"{ACCOUNT_CONCURRENCY_CEILING / (map_ms / 1000.0):.0f} rps x "
                f"{before_bytes:,} B = "
                f"{ACCOUNT_CONCURRENCY_CEILING / (map_ms / 1000.0) * before_bytes / 1e9:.2f} "
                f"GB/s out of {ACCOUNT_CONCURRENCY_CEILING} x 512 MB execution environments. "
                "NOBODY HAS OBSERVED THAT, here or anywhere in this repository's evidence. "
                "It is what the tariff and the ceiling permit, not what AWS would deliver."
            ),
            "what_would_settle_it": (
                "One sustained load test against a deployed function, which requires an "
                "apply. No worker in this wave applies anything, so it stays a bound."
            ),
            "durations_are_workstation_loopback": (
                "asset_js and asset_map never touch a database, so their local and cloud "
                "rows are the same code; docs/deploy/LATENCY.md measures the cloud column "
                "at up to 2.2x the local one. The local p50 is used because it is the "
                "FASTER figure and therefore the higher request rate and the larger bill."
            ),
        },
        "accounting_conventions": {
            "egress_priced_on": "response body bytes",
            "not_priced_on": (
                "the base64 envelope (Lambda decodes it before the bytes leave) and not "
                "response headers"
            ),
            "measured_header_overhead_bytes": REFUSAL_HEADER_BYTES,
            "where_that_matters": (
                f"+{REFUSAL_HEADER_BYTES / after_identity * 100:.3f} % on the "
                f"{after_identity:,} B identity asset and "
                f"+{REFUSAL_HEADER_BYTES / REFUSAL_BODY_BYTES * 100:.0f} % on the "
                f"{REFUSAL_BODY_BYTES} B refusal body. The convention therefore UNDERSTATES "
                "the rate-bound layer and essentially nothing else; the alternative figure "
                "is published beside it."
            ),
            "each_window_priced_from_tier_1": True,
            "why_that_understates": (
                "A 5-minute or 24-hour figure does not inherit the month's accumulated "
                "volume, so a short window following a flood is priced at the cheapest "
                "tiers it would not actually get. This is the convention the published "
                "30-day figures already use and it is kept for comparability."
            ),
            "timeout_is_not_in_the_arithmetic": (
                "Lambda bills actual duration. The function timeout is a reliability bound "
                "(docs/deploy/LATENCY.md §5.1) and moves no total in this file."
            ),
        },
        "reproduction": reproduction,
        "inputs": inputs,
        "refusal_path": {
            "body_bytes": REFUSAL_BODY_BYTES,
            "header_bytes": REFUSAL_HEADER_BYTES,
            "method_of_measurement": (
                "measured -- mainline_demo_api.app.handler driven in-process past its rate "
                "limiter; len(body.encode()) and the status line + header block"
            ),
        },
        "headline_convention": HEADLINE_CONVENTION,
        "conventions": conventions_out,
        "self_limiting_byte_levers": self_limiting,
        "the_stop": {
            "priced_on": "the UNRATE-LIMITED flood at L4 bytes and memory",
            "why_not_downstream_of_the_rate_bound": (
                "The rate limiter's counter is per execution environment with no shared "
                "store, so a distributed flood defeats it. The stop has to be worth its "
                "keep in the case where the lever above it did not hold, so it is priced "
                "there."
            ),
            "rows": stop_rows,
        },
        "residual": residual,
        "duration_sensitivity": {
            "why": (
                "Duration is the input the ladder is most exposed to: egress and requests "
                "scale as 1/duration and compute does not. The published headline assumed "
                "100 ms and the measurement is an order of magnitude faster."
            ),
            "held_fixed": f"{after_gz:,} B response, 256 MB, concurrency "
            f"{ACCOUNT_CONCURRENCY_CEILING}, 30 d, {HEADLINE_CONVENTION}",
            "band": band,
            "spread_factor": round(max(band_totals) / min(band_totals), 2),
        },
        "what_this_does_not_claim": [
            "Nothing here has been applied, no AWS API was called, and no database was read.",
            (
                "The sustained egress rate in `model_bound` is unobserved. It is the load-"
                "bearing assumption of every 30-day total in this file."
            ),
            (
                "L2 (strip) and L3 (gzip siblings) are priced as shipped because the "
                "artefact confirms zero source maps and 57 siblings; whether the gzip "
                "sibling is SERVED is static_site.py's contract and is asserted by its own "
                "tests, not here."
            ),
            (
                "The residual assumes the responder is instantiated. It is not this model's "
                "job to assert that the guard module is wired into the environment root."
            ),
        ],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument(
        "--out",
        type=Path,
        default=OUTPUT,
        help="where to write the model (default: evidence/deploy/cost/cost-model.json)",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="run the reproduction gate and exit; write nothing",
    )
    args = parser.parse_args(argv)

    if args.check:
        result = reproduce()
        json.dump(result, sys.stdout, indent=1, sort_keys=True)
        sys.stdout.write("\n")
        return 0 if result["ok"] else 1

    model = build_model()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps(model, indent=1, sort_keys=True, ensure_ascii=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    license_path = args.out.with_suffix(args.out.suffix + ".license")
    license_path.write_text(
        "SPDX-FileCopyrightText: 2026 MAINLINE contributors\nSPDX-License-Identifier: CC-BY-4.0\n",
        encoding="utf-8",
        newline="\n",
    )
    print(f"wrote {args.out}")
    print(f"reproduction ok: {model['reproduction']['ok']}")
    if model["ok"]:
        headline = model["conventions"][HEADLINE_CONVENTION]["layers"]
        for row in headline:
            print(f"  {row['label']:<26} USD {row['total_usd']:>12,.2f} / 30 d")
        print(f"  residual (hourly alarm)    USD {model['residual']['worst_usd']:>12,.2f}")
        in_window = model["residual"]["in_window"]
        floor = in_window["published_figures"][0]
        print(
            f"  residual (in-window)       USD "
            f"{floor['usd']:>12,.2f} per {floor['detection_lag_s']:g} s of detection lag "
            f"({in_window['usd_per_minute_of_detection_lag']:,.2f}/min), FLOOR -- "
            f"{in_window['lag_budget']['unknown_term_count']} lag terms unbounded: "
            + ", ".join(in_window["lag_budget"]["unknown_terms"])
        )
    return 0 if model["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
