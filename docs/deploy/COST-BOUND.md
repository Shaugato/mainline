<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
-->

# COST-BOUND — what the demo can cost, what actually bounds it, and the one command that stops it

**Owner:** W6 (deploy-safety) · **Measured:** 2026-08-13, this machine, `AWS_PROFILE=mainline-dev`
**Model re-derived as a program:** 2026-08-14 · `scripts/deploy/cost_model.py` →
[`evidence/deploy/cost/cost-model.json`](../../evidence/deploy/cost/cost-model.json)
**Status:** decision material. Nothing in this document has been applied. No `terraform apply`
was run to produce it, and no mutating AWS call was made.

> **§0.3 supersedes every byte figure in this document, including §0.1's and §0.2's.** It
> records that the artefact all of them are read from describes a build no commit in this
> repository reproduces, names the reproducible build's figures, and says exactly which
> published dollar figures move and by how much. **No digit anywhere in this file was
> retyped to it, and §0.3 says why that would have been the wrong motion.**
>
> **§0.4 is the same act performed for the package-and-verify wave, 2026-08-15, and its answer
> is that nothing moved.** No package was rebuilt into the deploy path and nothing was
> redeployed, so the tree every figure here is about is the tree that was there before — the
> zip was re-opened and re-measured to check that rather than assume it, and **§0.3's pending
> regeneration is still the only outstanding correction to these cells**. §0.4 carries the one
> figure that
> will move them when a LIVE console ships — **124,177 B → ~~129,404 B~~ on the wire**, read off
> a packaged zip rather than a `dist/` tree — what that does to R1/R3/R4/R6, and why raising the
> response ceiling to admit it is a decision this page does not take.
>
> **§0.5 turns that prediction into a measurement, 2026-08-15, and CORRECTS it by four bytes.**
> A LIVE console has since been packaged into the deploy path:
> `out/lambda/mainline-demo-api-arm64.zip`,
> `sha256 6802872f805740dd1a7de891eca7a8d1cf6c11f5eb5b639aec5677f5d78ae13b`,
> `--console-transport live`, `MAINLINE_BUILD_ID=b822fdc`. Its entry chunk measures
> **129,400 B** on the wire — §0.4 predicted `129,404 B` from a `--console-transport both`
> build that was superseded, and the two are four bytes apart. **That package has not been
> deployed**, so §0.1's ladder is unchanged and is still priced from the bytes the Function URL
> is serving. §0.5 records the packaged measurement, ruling **R10** — which keeps the ceiling at
> **139,264 B** and demotes its derivation to provenance — and the headroom figure that replaces
> the derivation window as this page's live warning.
>
> **§0, §0.1 and §0.2 supersede the arithmetic below them.** §1–§9 are preserved as the
> **reproduction baseline** — `scripts/deploy/cost_model.py` must re-derive §2.2's
> $33,251.87 and §1.2's $11,701 / $31,049.79 / $10,949 from the inputs that produced them
> *before* it is allowed to publish anything in §0.1, and
> `tests/deploy/test_cost_model.py` fails the build if it cannot. Where §1–§9 and §0.1
> disagree, §0.1 is later and measured; §1–§9 are kept because a bound nobody can re-derive
> is not a bound, and deleting the old answer would destroy the only thing the new one can
> be checked against.
>
> **Where a §1–§9 sentence has since become false, it is struck through or annotated in
> place, never removed** (**§1**, **§2.1**, **§2.2**, §3.2, §3.3, **§3.4**, §3.6,
> **§3.7**, §5, §5.1, §6, §9). A claim
> deleted is not a claim corrected, and the corrections are only checkable against the claims
> they correct. *(§1 and §3.7 were added to this list on 2026-08-14. §1 was annotated in the
> same wave; its omission here is exactly why §1 read as current when it is historical, and an
> enumeration that does not enumerate is the same defect one level up. **§2.1, §2.2 and §3.4
> were added on 2026-08-14 in the re-verification pass, for the identical reason:** each
> carried a `1,554,168 B` or a `2,586,960 B` in running arithmetic and named **neither** of
> the two trees below, and this list named none of the three. **No digit in any of them moved.
> Only the tree each one names was added.** The same pass named the tree on §0's ceiling row,
> §0.1's ceiling bullet, §5.1's ceiling row and §6's L3 recommendation — §0 and §0.1 are the
> superseding side rather than the preserved baseline, so they are deliberately **not** added
> to a §1–§9 list, and §6's L3 correction is covered by §6's entry, already here.)*
>
> **Every byte figure in this document names its tree, and there are two.** The packer's
> **input** tree — 75 entries, 3,571,990 B, 18 source maps — is the pre-strip baseline §2.2's
> $33,251.87 reproduces from. The **deployed** package — 114 entries, 1,274,342 B, **0** source
> maps — is what the origin can actually emit, and it is therefore the authoritative side of
> every cost and ceiling claim, because cost is bytes leaving the deployed origin
> (`docs/decisions/response-ceiling-authoritative-tree.md` §1). Both trees are recorded in
> [`evidence/deploy/cost/package-shape.json`](../../evidence/deploy/cost/package-shape.json)
> as `architectures[].before` and `architectures[].after`. **A figure that does not name its
> tree is wrong, whichever tree it came from.**
>
> **§0.1 is the one table.** Every figure in it is a lookup into
> `evidence/deploy/cost/cost-model.json`, named cell by cell in that table's last column. If
> a cell and the JSON disagree, **the JSON is authoritative and the cell is the defect** —
> the fix is to re-read the model, never to retype the model to match the prose.

---

## 0 · The answer in five lines

The demo's origin is a Lambda Function URL with `authorization_type = NONE`. The account can
run **10** concurrent executions. The published figure for one month of sustained abuse was

> ~~**USD 11,700 – 33,250**~~ — **a floor, and it is understated about 7×.**

That range assumed a **100 ms** invocation. Nobody had measured one.
[`docs/deploy/LATENCY.md`](LATENCY.md) since measured every beat over a real socket: the
static beats — the *only* beats a flood uses — run at **5.66 ms** and **14.11 ms** p50, an
order of magnitude faster. Egress and requests scale as **1/duration**. Putting the measured
number into the same arithmetic gives **USD 229,805 / 30 d** for the package as it stood, and
that is the honest "today" the founder was never given.

**What has changed since, and what has not:**

| | then | now |
|---|---|---|
| invocation duration | 100 ms, assumed | **5.66 / 14.11 ms, measured** |
| source maps in the package | 18 files, 2,586,960 B | **0 — the strip is the default in both builders** |
| largest servable response | 1,554,168 B | **124,127 B** on the wire (gzip sibling) |
| response ceiling | 2 MiB, above everything it governed | **139,264 B**, unchanged and binding — ~~derived from the **deployed** tree~~ **CORRECTED 2026-08-15 (R10, §0.5): CHOSEN by the derivation over the 2026-08-14 tree, KEPT by interface I3** |
| the stop | described | **built _and instantiated_** — `infra/modules/cost-guard`, three alarms → SNS → `PutFunctionConcurrency(0)`, wired into the environment root at `infra/envs/demo/main.tf:631` |

The claim that **exactly one real bound exists and it is an AWS account default nobody
chose** was true when written and is **no longer true**: the response ceiling binds, the
rate limiter runs as the first statement of the handler, and the stop exists in code **and
in the environment root**.

This section used to end *"the one thing that has not changed is that the guard is not
instantiated"*. **That sentence was true when written and is false now**, and it is
corrected rather than deleted because it is the finding this wave closed: `module "guard"`
is declared, the shipping plan moved **11 → 24**, and the demo function's alarms carry the
stop topic. §0.2 records that from the tree and from the committed plan artefact, with the
one consequence no plan can settle. §0.1 is the whole ladder; §3 is the original menu; §6 is
the original recommendation.

---

## 0.1 · THE TABLE — worst case USD before and after, per layer, with the residual and the trade

**This is the one table.** The ladder L0–L5 is **worst case USD / 30 d**; L6 onward each name
their own window in their own row, because they are not monthly quantities and printing them
as though they were would be a lie of units. Nothing that belongs in it lives in a footnote —
including row **T**, which is not a dollar figure and is in the table anyway.

Every figure below is produced by `scripts/deploy/cost_model.py` and re-derivable with
`python scripts/deploy/cost_model.py`. Convention: **`audit-decimal`** (GB = 10⁹, tiers at
10,000 / 50,000 / 150,000 GB) — the conservative reading, the one that reproduces §2.2. The
`binary-gb-api-tiers` column is in the JSON for every row and runs ~6.6 % lower.

**THIS IS A MODEL BOUND, NOT A FORECAST.** Every row holds concurrency pinned at the account
ceiling of 10 and divides by a measured duration, which assumes AWS *sustains* the resulting
egress. Row L1 assumes **708 rps × 1,554,168 B = 1.10 GB/s out of ten 512 MB execution
environments** — and **that 1,554,168 B is the packer's INPUT tree**, `architectures[].before`,
the pre-strip baseline L1 exists to price (§1 I4). **It is not a body the deployed origin can
emit**; L1 is the honest *"before"* and the deployed figures are rows L2 and below.
**Nobody has observed that**, here or anywhere in this repository's evidence.
It is what the tariff and the ceiling *permit*, not what AWS would deliver. The `GB/s` column
is printed so every row can be disbelieved individually.

**Every scalar carries its window.** The ladder is 30 d; the stop and the in-window residual
are priced over the window named in their own row, because a dollar figure quoted without
the interval it accrued over is the same defect as the 100 ms assumption — a number that
looks like an answer and is missing its denominator.

| # | Layer / residual — **window** | Before | **After** | ÷ | GB/s | Bounds — and what it does **not** bound | `cost-model.json` |
|---|---|---:|---:|---:|---:|---|---|
| L0 | the published headline, 100 ms **assumed** — **30 d** | — | **$33,251.87** | — | 0.155 | nothing; it is the baseline. Superseded: a floor understated ~6.9× | `…layers` `L0-modelled-100ms` |
| L1 | **the same flood at the measured 14.106 ms** — **30 d** | $33,251.87 | **$229,804.98** | **×6.91 ↑** | **1.102** | nothing. *No lever was applied here.* The only edit is that the duration is now a measurement — this is the honest **"before"** | `…layers` `L1-measured-duration` |
| L2 | strip source maps — already shipped, default in both builders — **30 d** | $229,804.98 | **$160,667.84** | ÷1.43 | 0.766 | bytes/request, **÷3.59**. **Not** the request rate, which **rose ×2.49** and gave most of it back | `…layers` `L2-strip-source-maps` |
| L3 | serve the `.gz` sibling on the wire — **30 d** | $160,667.84 | **$47,363.92** | ÷3.39 | 0.219 | bytes on the wire, and duration does **not** fall with it. **Not** the request rate | `…layers` `L3-gzip-on-the-wire` |
| L4 | `memory_size` 512 → 256 MB — **SHIPPED, not proposed** — **30 d** | $47,363.92 | **$47,277.52** | ÷1.002 | 0.219 | compute only — **$86.40**, 0.2 %. **Not** the other 99.8 %. **The plan already ships `memory_size = 256`** (`evidence/deploy/terraform-plan-furl.txt:290`), so this row prices a lever that is *taken*, not one on offer | `…layers` `L4-memory-512-to-256` |
| L5 | the in-code rate bound (100 rps fleet-wide) — **30 d** | $47,277.52 | **$4,172.63** | ÷11.33 | 0.013 | egress from a paced caller. **Not the invocation charge** — a 429 is a billed invocation, and $1,002 of what remains is requests + compute | `…layers` `L5-rate-bound` |
| L6 | **THE STOP** — **one 5 min window** | $47,277.52 | **$8.01** | **÷5,902** | 0.219 | everything, from the moment it lands. **Not** the interval before it lands — which is rows R4–R6 | `the_stop.rows` `stop-5min` |
| L6′ | the stop — **one 1 h window** | $47,277.52 | **$96.13** | ÷492 | 0.219 | as above, an hour of not looking | `the_stop.rows` `stop-1h` |
| R1 | **residual — paced under both alarms** — **24 h** Budgets lag | — | **$5.44** | — | — | the 124,127 B gzip sibling, which is what the **139,264 B** ceiling admits. Bounded only by Cost Explorer's lag | `residual.worst_usd` |
| R2 | residual — paced — **8 h** Budgets lag | — | $1.81 | — | — | the near edge of the same lag | `residual.rows` `residual-gzip-sibling-8h` |
| R3 | residual — paced, **30 d**, if nobody looks at all | — | **$564.04** | — | — | nothing looks at it; this is the unattended month | `residual.if_nobody_looks_for_30_days_usd` |
| R3′ | *counterfactual:* R1 if the ceiling were raised above 433,396 B — **24 h** | — | $18.80 | ×3.5 ↑ | — | published because the ceiling is a code constant one commit from moving | `residual.rows` `residual-identity-24h`, = `residual.worst_if_the_ceiling_were_lifted_usd` |
| R3″ | same counterfactual — **8 h** | — | $6.27 | ×3.5 ↑ | — | the near edge of the same counterfactual | `residual.rows` `residual-identity-8h` |
| R4 | **residual — in-window, at flood rate (1,767 rps)** — **per 60 s of detection lag** | — | **$1.60** | — | 0.219 | **a floor.** It counts the burst alarm's own evaluation window (`period 60 × evaluation_periods 1`) and **nothing after it** | `…in_window.published_figures` `floor` |
| R5 | same — **per 75 s**, the only two terms with a read-only upper bound | — | $2.00 | — | 0.219 | the alarm window **plus** the **guard responder's** configured 15 s timeout — `infra/modules/cost-guard/variables.tf :: responder_timeout`, **a different function from demo-api, whose timeout is 14 s**. **Still not the answer** — five delivery-path terms are unbounded and additive | `…published_figures` `bounded-terms-only` |
| R6 | same, as a rate — **USD per minute of detection lag** | — | **$1.6022 / min** | — | 0.219 | linear: a window this short never leaves egress tier 1, so any lag budget prices by multiplying | `…in_window.usd_per_minute_of_detection_lag` |
| **T** | **THE TRADE — what the stop costs that is not measured in dollars** | — | **not a dollar figure** | — | — | **THE GUARD CONVERTS A COST ATTACK INTO AN AVAILABILITY ATTACK.** The URL is `authorization_type = NONE` by the founder's explicit choice, so **anyone at all** can trip the burst alarm, and the responder's stop is **not aimed at attackers** — it stops **the demo, for everyone**, at reserved concurrency 0, until a human runs `scripts/deploy/kill_switch.{sh,ps1} --restore`. **An outage is recoverable by one command and an unbounded bill is not — and it is still a trade.** | `residual.the_trade_this_makes` |

`…layers` is `conventions["audit-decimal"].layers[]`, matched on `label`; `…in_window` is
`residual.in_window`. **Every figure above is a lookup, not a retyping** — if a cell and the
JSON disagree, the JSON is authoritative and the cell is the defect.

> **RE-VERIFIED 2026-08-14, cell by cell, against the committed
> [`cost-model.json`](../../evidence/deploy/cost/cost-model.json).** Every dollar figure,
> every `÷`/`×` factor and every `GB/s` value above resolves to the lookup named in its own
> last column, and **no cell disagreed with the JSON**, so nothing here was moved in either
> direction. Also confirmed: **every ladder row L0–L5 carries both a before and an after**
> (L0's before is `—` because it *is* the baseline, which its own row says); **every row
> names its window** — L0–L5 `30 d`, L6 `5 min`, L6′ `1 h`, R1/R3′ `24 h`, R2/R3″ `8 h`, R3
> `30 d`, R4 `60 s`, R5 `75 s`, R6 `per minute`; and the residual rows carry `—` in the
> *before* column because they are residuals of the after state, not levers with a before.
> The supporting prose reproduces too: 1,766.784 rps → "1,767", 708.918 → "708", 1.698 s →
> "1.70 s", `$1,993.99`, `$0.000151`, `$1.3847/min` at **13.57 %** understatement,
> `$5.5364/min` lifted-ceiling, and the whole sensitivity ladder **1.60 / 3.20 / 4.81 / 8.01
> / 16.02 / 24.03**. One wording note, recorded rather than silently normalised: row **T**
> opens *"THE GUARD CONVERTS…"* where the JSON's `the_trade_this_makes` opens *"THIS
> CONVERTS…"*. The claim is the same and the JSON is the authority; the row names the
> mechanism rather than saying "this", and no figure depends on it.

**Row T is a row and not a footnote, deliberately.** It was a blockquote under this table
until 2026-08-14, which is a footnote wearing a heading. A trade the founder accepted on the
condition that the numbers are honest has to sit in the same table as the numbers, or the
reader who scans the table and stops has been told the good half.

**Read the column downward and four things are not arguable.**

1. **The byte levers are self-limiting, and the table has to show it.** L2 cut bytes **3.59×**
   and the bill **1.43×**. A smaller object is faster to serve, so the request rate rose
   **2.49×** and ate two thirds of the saving. Every byte lever on a concurrency-bound
   origin behaves this way. L4 is worth taking *because it is duration-independent*, not
   because it is large — **and it has been taken**: the shipping plan reads
   `memory_size = 256` (`evidence/deploy/terraform-plan-furl.txt:290`), so L4 is a record of
   a decision, not an offer.
2. **Every byte lever multiplied together still leaves five figures.** $229,805 → $47,278.
3. **The stop is the whole answer**, and it is the only lever whose effect is not eroded by
   the rate rising to meet it.
4. **The two residuals are added, not swapped.** R1–R3 and R4–R6 describe **two different
   attackers**, and both are real: R1–R3 is a caller who *paces under every threshold* and is
   therefore caught only by Budgets; R4–R6 is a *flood* that trips the burst alarm and bills
   at full rate until the stop lands. Quoting the flood figure at a paced caller overstates
   it by two orders of magnitude; quoting the paced figure at a flood understates it.
   (`residual.in_window.additive_to_the_paced_residual_not_a_replacement`.)

### R1–R3 — the paced residual, computed at the alarm line and not at flood rate

The caller worth arguing about **paces under both `Invocations` alarms** and is therefore
caught only by AWS Budgets, on an 8–24 h Cost Explorer lag.

The binding line is the **hourly** alarm: `invocations_hourly_threshold = 15,000` over a
3,600 s period = **4.1667 rps** (the burst alarm permits 3,000/60 s = 50 rps, so it is not
what binds). `GreaterThanThreshold` means a caller *at* the line does not breach.

**Quoting $1,993.99 here would be wrong.** That is
`residual.flood_rate_24h_for_contrast_usd` — the 24-hour figure at *flood* rate — and a
caller under the alarm is by definition not at flood rate. It overstates R1 by **367×** and
describes a caller the burst alarm catches in the first minute. *(This paragraph said
"$2,002" until 2026-08-14. The model says $1,993.99, the model is authoritative, and the
prose was moved to it — not the other way round.)*

### R4–R6 — the in-window residual: how much is spent before the stop lands

`residual.in_window` answers the question nobody had quantified: **how much can be spent
inside one CloudWatch alarm evaluation window, before `PutFunctionConcurrency(0)` takes
effect?**

* **Flood rate** = concurrency ceiling 10 ÷ the measured 5.66 ms `asset_js` p50 =
  **1,766.784 rps**. The in-code rate limiter does not reduce it: its counter is
  per-execution-environment with no shared store, so a distributed flood defeats it — the
  same reason L6 is priced upstream of L5 and takes its "before" from L4.
* **Detection floor** = `period × evaluation_periods` = 60 × 1 = **60 s**, from the burst
  alarm. `datapoints_to_alarm` is the **M of an M-of-N evaluation, not a multiplier**;
  multiplying by it is harmless here only because it happens to equal 1, and would silently
  overstate the floor the day either alarm is retuned. At flood rate the 3,000 threshold is
  crossed in **1.70 s**, but the datapoint does not exist until the period *closes*, so the
  worst case is the **full** period and not the time-to-threshold.
* **Why R4 is a floor and not the answer.** Publishing `60 s × rate` as *the* residual would
  assume every term between the period closing and the stop landing costs zero seconds —
  the identical shape of error as the $33,251.87 headline, which multiplied a real tariff by
  an invocation duration nobody had measured. Of the seven terms in
  `residual.in_window.lag_budget`, **two carry a read-only bound** (the 60 s alarm window,
  read from HCL; the **guard responder's** 15 s configured timeout, read from HCL
  (`infra/modules/cost-guard/variables.tf :: responder_timeout` — **not** demo-api's, which is
  14 s) — and that one bounds
  *one attempt* of its invoke phase, not the path) and **five are named as unknowns rather
  than guessed**: metric publication delay, alarm evaluation delay, SNS delivery to the
  responder, the responder's async retry if it is itself throttled, and reserved-concurrency
  propagation. AWS publishes no numeric upper bound for any of the five, and none can be
  measured without an apply.
* **The one term that *is* bounded without any AWS documentation**: the in-flight drain. At
  the instant the stop lands at most 10 invocations are in flight and each serves at most one
  more response — **$0.000151**. It is priced so that "in-flight requests still drain" cannot
  be gestured at as if it were the missing term. It is not; the delivery-path terms are.
* **Do not obtain this by dividing the 24-hour flood figure by 1,440.** That yields
  $1.3847/min and **understates the correct rate by 13.57 %**, because the 24-hour figure
  accumulates enough volume to reach the $0.085 and $0.082 egress tiers that a window of
  minutes never reaches. Every window here is priced **directly from tier 1**, which is this
  file's stated convention and errs conservative.
  (`residual.in_window.the_wrong_way_to_get_this`.)

Sensitivity, all from `residual.in_window.sensitivity`, linear at **$1.6022/min** because no
window this short leaves egress tier 1 — so **the founder can price any lag budget by
multiplying**: 60 s **$1.60** · 120 s $3.20 · 180 s $4.81 · 300 s **$8.01** · 600 s $16.02 ·
900 s $24.03.

### What this table depends on that could move

* **The response ceiling is a code constant.** ~~derived from the DEPLOYED tree.~~
  **CORRECTED 2026-08-15 under ruling R10 (§0.5): 139,264 B was CHOSEN by the derivation over
  the 2026-08-14 tree and is KEPT by interface I3. It is no longer re-derivable from the tree
  of record, and this page does not claim it is.** What binds is unchanged: the straddle, I3,
  and exactly one identity object refused.
  `static_site.DEFAULT_MAX_RESPONSE_BYTES` is
  **139,264 B** today and is read at model time, not copied. Raise it above 433,396 B — the
  largest identity object of the tree `package-shape.json` records — and the
  reachable residual is **3.5×** larger (R1 → R3′) and the in-window rate moves with it
  ($1.6022 → $5.5364 per minute). Both cases are published for exactly that reason.
  *(That counterfactual only grows against the package of record, whose largest identity object
  is 457,123 B — §0.5. The **$18.80** above is the figure the model computed from its own input
  and is not retyped to it.)*
* **The durations are workstation-loopback p50s.** `LATENCY.md` measures the cloud column at
  up to **2.2×** the local one. The *local* figure is used because it is faster, therefore a
  higher request rate, therefore the larger bill.
* **The guard is instantiated, and the stop rows are therefore reachable.** This bullet read
  *"The guard is not instantiated … it does not yet"* until 2026-08-14 and was **false against
  its own repository**. §0.2 records the instantiation from the tree and from the committed
  plan artefact. What is still open is not the instantiation but one consequence of it, which
  §0.2 names and no plan can settle.

---

## 0.2 · The guard **is** instantiated — read from the tree, confirmed in the plan

**This document said three times that it was not.** §0 said *"the guard is not instantiated
in the environment root"*; §0.1's last bullet said *"It does not yet"*; §5.1's table row said
**BUILT, NOT INSTANTIATED** and *"there is no `module "guard"` in `infra/envs/demo/main.tf`,
so `var.alarm_actions` is `[]`"*. Every one of those was true when written and **all three
are false against this tree**. They are corrected in place rather than deleted, because the
finding they record — *coded and not instantiated is indistinguishable, on a plan output,
from not existing* — is the reason the module was wired in at all.

### What is in the tree

| Fact | Value | Read from |
|---|---|---|
| the module block | `module "guard" {` on **line 631**, `source = "../../modules/cost-guard"` on **632**, closing `}` on **652** | `infra/envs/demo/main.tf` |
| its instantiation condition | `count = var.enable_api ? 1 : 0` on **line 633** — present in every configuration that has an API, which is the shipping one | same |
| `resource` blocks the module declares | **14** | `infra/modules/cost-guard/main.tf` |
| …of which **created** under shipping defaults | **13** | `evidence/deploy/terraform-plan-furl.json` |
| the 14th, and why it is absent | `aws_sns_topic_subscription.email` is **`for_each = toset(var.notification_emails)`** (`cost-guard/main.tf:337–338`), and `guard_notification_emails` defaults to **empty** — so it has zero instances, by design | `infra/envs/demo/variables.tf:619` |
| the demo function's alarms | `alarm_actions = local.guard_stop_topic_actions` (`main.tf:586`) = `try([module.guard[0].sns_topic_arn], [])` (`main.tf:292`) — **no longer the constant `[]`**. The plan renders it *unknown*, not empty (`plan-shape.json`: `alarm_actions_known_at_plan = false`), because the ARN does not exist until apply | `infra/envs/demo/main.tf` |

**11 + 14 = 25, and the plan says 24. That is not an off-by-one; it is the email
subscription**, and it was confirmed against the plan JSON rather than assumed:
`evidence/deploy/terraform-plan-furl.json` carries **24 creates + 1 read**, of which
**13 are `module.guard[0].*`** and **11 are not**. The 13 are the SNS topic, its policy, the
responder's subscription, the responder's log group, role, role-policy, policy attachment,
the responder function, its SNS invoke permission, the budget, and the three metric alarms.

### What that did to the shipping plan

The count moved **11 → 24**. `evidence/deploy/terraform-plan-furl.txt` reads
`Plan: 24 to add, 0 to change, 0 to destroy.` at line 843, and the JSON above is the same
run decomposed. **11 is no longer supported by any committed plan artefact** and this
document quotes it only as history, never as a current count.

**The other configuration agrees, and that is the check that matters.** The CloudFront
variant's artefact was regenerated on 2026-08-14 and moved **22 → 35** — the same **+13**,
with the same 13 `module.guard[0].*` addresses over 22 non-guard resources. Two independent
configurations both gaining exactly the guard's 13 is what rules out an off-by-one that
happens to net out. *(Until that regeneration the CloudFront artefact still reported 22 and
was stale; a count read off it before 04:43 would have been a pre-instantiation number.
Read the shipping count off the **FURL** artefact — the CloudFront one describes a
configuration this demo does not ship, because this account is refused CloudFront, §3.8.)*

### The one consequence no plan can settle, recorded rather than assumed

Arming `alarm_actions` on the demo function points **all four** of that module's alarms at
the stop topic — `-errors`, `-throttles`, `-duration-p99` and `-concurrency`. Only the last
is unambiguously a cost signal; **the other three are health signals, and stopping on them is
a self-inflicted outage.** That is done knowingly, on the ranking in row **T**: the URL is
already `authorization_type = NONE`, so anyone can already trip the guard's own burst alarm
and stop the demo — these four widen the set of ways it can happen, they do not create it.

And there is a hazard that **no `terraform plan` can decide.** The guard's SNS topic policy
admits `cloudwatch.amazonaws.com` under an `ArnLike` on `aws:SourceArn` naming exactly the
guard's **own three** alarm ARNs (`cost-guard/main.tf`, sid `TheseThreeAlarmsMayPublishAStop`).
**None of demo-api's four alarms is in that list.** Whether they can publish therefore rests
on the policy's first statement — SNS's default idiom, `Principal AWS:*` narrowed by
`AWS:SourceOwner` — and settling it takes a real breach on a real apply. Both outcomes are
recorded because they are opposite defects:

* **admitted** → the four alarms stop the demo, as described above;
* **denied** → the four alarms carry an action SNS refuses, which `describe-alarms` renders
  **identically to a delivered one** — a control that looks present and is not, which is the
  exact defect this document exists to refuse.

`evidence/deploy/cost/plan-shape.json` records both ARN sets side by side, under
`open_hazard_topic_policy_source_arn`: `alarms_named_in_the_topic_policy` holds the guard's
three, `alarms_pointed_at_the_topic_but_not_named_in_it` holds demo-api's four. The question
therefore lives in the evidence rather than in one worker's head. **Nothing here has been
applied**, so this is written as an open question and not as a result.

---

## 0.3 · WHICH ARTEFACT EVERY BYTE FIGURE HERE WAS MEASURED FROM, AND WHEN — and the finding that it describes a build nobody can reproduce

**Owner of this section:** W6 (ci-green), 2026-08-14 · **Finding it records:** W1's, commit
`f68abb7` · **Status:** open, and the action that closes it is **not W6's to take**.

### The artefact, named and dated

Every byte figure in this document — §0's summary table, §0.1's ceiling and residual rows,
§1's I4–I7, §2's worked arithmetic, §3.2/§3.3/§3.4's block figures — is a lookup into **one**
artefact:

| | |
|---|---|
| **Artefact** | [`evidence/deploy/cost/package-shape.json`](../../evidence/deploy/cost/package-shape.json), `architectures[]` where `architecture == "arm64"` |
| **Measured on** | the project Windows workstation, CPython 3.13.14, zlib 1.3.1 |
| **Measured at HEAD** | **`2dc5c86`** — *not* the HEAD this document is being read at |
| **Produced by** | `scripts/deploy/build_lambda.sh --arch arm64`, then `scripts/deploy/bundle_manifest.py <zip> --strict` |
| **Recorded by** | W2 of the cost-bound wave |

That row — *measured at `2dc5c86`* — is the whole of this section. It was never stated in this
document before today, and stating it is what makes the next paragraph visible.

### The finding: `package-shape.json` records a `console/dist` that no commit produces

W1 of this wave followed **R1's non-negotiable order** — *prove the build reproduces first,
re-record the numbers second* — and proved both halves. Reproduced from a clean export:

```
git archive HEAD verticals/mainline/apps/console   → empty directory
pnpm install --frozen-lockfile                     (pnpm 11.5.3, the version package.json names)
pnpm exec vite build --mode demo                   CI=true, MAINLINE_BUILD_ID unset,
                                                   MAINLINE_ATTESTATION unset
                                                   — the exact environment
                                                   .github/actions/build-demo-package
                                                   establishes
bash scripts/deploy/build_lambda.sh --arch arm64   over that export
```

emits `assets/index-DzVoV1YM.js` at **433,564 B byte for byte**, with all 49 `dist/` entries
matching the CI lane's own build (run `31770005759`) by name and size. **So the build is
deterministic**, which is R1's second branch and the one that permits re-recording.

And the tree `package-shape.json` describes matches **no commit** — not by name and not by
size. W1 built three clean historical exports to check: `5ddaa3a` → 432,707 B
`index-BGqw2TVV.js`; `4d948dd` → 433,564 B `index-BTaIOv1P.js`; `7535670` → 433,564 B
`index-DzVoV1YM.js`. The artefact declares 433,396 B `index-BjAGxrVJ.js`. It came from a
`console/dist` dated 2026-08-10 21:04 that no commit emits.

### Old → new, every figure this document quotes

| figure | `package-shape.json` @ `2dc5c86` — **what this document says** | the reproducible build @ HEAD — **what is true** | Δ | **the package of record** (`6802872f…`) — a THIRD console, measured 2026-08-15 |
|---|---:|---:|---:|---:|
| **deployed** `web/` bytes | 1,274,342 | **1,274,743** | +401 | **1,308,536** |
| **deployed** identity | 57 / 985,030 B | 57 / **985,306 B** | +276 | **57 / 1,012,812 B** |
| **deployed** `.gz` siblings | 57 / 289,312 B | 57 / **289,437 B** | +125 | **57 / 295,724 B** |
| **deployed** largest identity | 433,396 B `index-BjAGxrVJ.js` | **433,564 B** `index-DzVoV1YM.js` | +168 | **457,123 B** `index-BH5dfAvF.js` |
| **deployed** largest on the wire | 124,127 B `…js.gz` | **124,177 B** `index-DzVoV1YM.js.gz` | +50 | **129,400 B** `index-BH5dfAvF.js.gz` |
| **deployed** source maps | 0 / 0 B | **0 / 0 B** | — | **0 / 0 B** |
| **input** `web/` bytes over 75 files | 3,571,990 | **3,566,324** | −5,666 | **3,643,912** over 75 |
| **input** source maps over 18 files | 2,586,960 B (72.4235 %) | **2,581,018 B** (**72.37 %**) | −5,942 | **2,631,100 B** over 18 |
| **input** largest object (`…js.map`) | 1,554,168 B `index-BjAGxrVJ.js.map` | **1,551,887 B** `index-DzVoV1YM.js.map` | **−2,281** | not recorded — the sidecar carries totals, not a largest-object row |

> **THE FOURTH COLUMN IS A DIFFERENT CONSOLE, NOT A THIRD OPINION ABOUT THE FIRST TWO — added
> 2026-08-15.** Columns 2 and 3 are two readings of a **2026-08-14-generation** console, and
> the finding that separates them (one describes a build no commit produces) is unchanged.
> Column 4 is the console rebuilt with the LIVE transport and packaged the next day —
> `out/lambda/mainline-demo-api-arm64.zip`, `sha256 6802872f…`, `--console-transport live`,
> `MAINLINE_BUILD_ID=b822fdc` — read by this worker out of the zip's central directory, with
> the `input` rows taken from that build's own sidecar
> (`out/lambda/mainline-demo-api-arm64.zip.json` → `package_shape.web_before`,
> `source_maps_removed`). **It changes no cell to its left and closes no open action**: §0.3's
> regeneration of `package-shape.json` and `cost-model.json` is still owed, and it is still not
> this worker's file. **Nothing in column 4 has been deployed** — §0.5 is the full record.

**That last row was printed as a gap, and the gap is now closed.** W1's re-derivation had
covered every aggregate and both wire figures but not the input tree's largest single object
— the `.js.map` that §2.1 and §2.2 price from — so `1,554,168 B` stood as the one figure in
this document that had been neither confirmed nor replaced, and it is the one the
**$33,251.87** reproduction runs on.

> **RE-DERIVED 2026-08-14 by W5 (plan-truth), at HEAD `d098721`.** Walked the packer's input
> tree as `build_lambda.sh` composes it — `verticals/mainline/apps/console/dist/` mounted at
> `web/`, plus `…/console/fixtures/bundles/demo-cloud` at `web/bundle/` (the script's own
> header, lines 22–23) — and measured every entry with `os.path.getsize`:
>
> | input `web/` tree, measured today | value | `package-shape.json` `…before.web` says |
> |---|---:|---:|
> | entries | **75** | 75 — **agrees** |
> | bytes | **3,566,324** | 3,571,990 |
> | source maps | **18 / 2,581,018 B** | 18 / 2,586,960 B |
> | **largest object** | **1,551,887 B** `web/assets/index-DzVoV1YM.js.map` | 1,554,168 B `index-BjAGxrVJ.js.map` |
> | largest non-map | **433,564 B** `web/assets/index-DzVoV1YM.js` | 433,396 B `index-BjAGxrVJ.js` |
>
> **The entry count reproduces exactly at 75, and every aggregate reproduces W1's figures to
> the byte** — which is what makes the new largest-object number trustworthy rather than a
> fourth opinion: the same walk that re-derived `3,566,324` and `2,581,018` produced
> `1,551,887`, and those two were already independently confirmed above.
>
> **`1,554,168 B` is nevertheless still what this document's cells say, on purpose.** It is
> the value in `evidence/deploy/cost/package-shape.json`, that artefact is the authority
> `tests/deploy/test_docs_are_true.py` reads these figures out of rather than typing them,
> and **`evidence/deploy/cost/` is not W5's to write** — the same boundary that stopped W6.
> Retyping the prose to a number the artefact does not carry is moving the derived side away
> from its authority, which is the motion this repository's standing rule forbids, and the
> checker would catch it. **What changes here is that the figure is no longer *unknown*: it
> is measured, it is −2,281 B, and it is recorded beside the cell it will eventually
> replace.**
>
> **The action this hands on, unchanged in substance and now fully quantified:** regenerate
> `package-shape.json` and `cost-model.json` from the reproducible build, then re-read this
> document's cells from them. Every figure that regeneration must carry is now written down
> — there is no longer a row anybody has to go and measure first.
>
> **Nothing in §2.2's arithmetic moves today**, because the cells did not move. When it does
> move, it moves by **−2,281 ÷ 1,554,168 = −0.147 %**, and the direction is worth stating in
> advance so it cannot be presented as a saving later: the headline gets **smaller**, from
> **$33,251.87** toward **$33,203**, and *~229,805 unbounded* toward *~229,467*. **A bound
> that shrinks by a seventh of a percent is still the same bound**, and no decision in §3 or
> §5 turns on it.

> **THE DEPLOYED COLUMN, CONFIRMED AGAINST THE SHIPPED ZIP ITSELF — 2026-08-14, W5.** The
> table above labels its right-hand column *"the reproducible build @ HEAD"*, which is a
> **rebuild**. The question that column cannot answer on its own is whether the package the
> deployment would actually upload is that build. So it was opened directly:
> `zipfile.ZipFile('out/lambda/mainline-demo-api-arm64.zip')`, every entry under `web/`.
>
> | deployed `web/` tree, read out of the zip | measured | the table above |
> |---|---:|---:|
> | entries | **114** | 114 |
> | bytes | **1,274,743** | 1,274,743 |
> | **source maps** | **0 / 0 B** | 0 / 0 B |
> | identity | **57 / 985,306 B** | 57 / 985,306 B |
> | `.gz` siblings | **57 / 289,437 B** | 57 / 289,437 B |
> | largest identity object | **433,564 B** `web/assets/index-DzVoV1YM.js` | 433,564 B |
> | **largest object on the wire** | **124,177 B** `web/assets/index-DzVoV1YM.js.gz` | 124,177 B |
>
> **Every deployed row reproduces to the byte, so the shipped package IS the reproducible
> build** — the rebuild and the artefact are the same tree, and the deployed column is no
> longer resting on an inference.
>
> **And the zip is tied to the plan, not merely to this page.** The same 7,703,067-byte file
> hashes to `base64(sha256(…)) = Evy6etabL/6CQLHsv3Y3RNlEHhIwkQn3+riKxi37zCc=`, which is
> exactly the `source_code_hash` carried by `aws_lambda_function.this` in
> `evidence/deploy/terraform-plan-furl.txt`, regenerated the same day
> (`docs/deploy/terraform-plan.md`, *"Both counts, as measured"*). **The tree this section
> measures, the package the plan would upload, and the bytes a judge's browser would receive
> are one artefact, and that chain is now checkable end to end.**
>
> > **THAT CHAIN HAS SINCE PARTED IN ONE LINK, AND ONLY ONE — annotated 2026-08-15.**
> > **Every measurement in this blockquote stands**, of the package it names: `12fcba7a…`,
> > 7,703,067 B, which is still the artefact the origin is answering with, so *"the bytes a
> > judge's browser would receive"* is unchanged. What is no longer true is *"the package the
> > plan would upload"*: the file at `out/lambda/mainline-demo-api-arm64.zip` was rebuilt on
> > 2026-08-15 and is now `sha256 6802872f…`, so an apply today would upload a **different**
> > tree — 1,308,536 B of `web/`, entry chunk 457,123 B identity / 129,400 B on the wire, and
> > a `source_code_hash` the committed plan artefact does not carry. **§0.5 measures it**;
> > re-running `terraform plan` is not this page's action and was not taken.
>
> **This is the column every cost claim on this page is priced from**, because cost is bytes
> leaving the origin — `docs/decisions/response-ceiling-authoritative-tree.md` §1, the same
> reasoning that makes the **139,264 B** response ceiling correct. **The deployed package
> holds zero source maps**, so `1,554,168 B` — a source map — is not a body this origin can
> emit at all, and the ceiling still admits the 124,177 B sibling while refusing the 433,564 B
> identity form. `0 < 124,177 < 139,264 < 433,564` holds, and **exactly one** identity object
> is refused.

### Why not one digit above was retyped into the prose

The obvious motion — replace every `124,127` with `124,177` and be done — is the wrong one,
for a reason worth writing down because it is the shape of the rule that outranks every task
in this repository.

`tests/deploy/test_docs_are_true.py` does not *type* these figures. It **reads them out of
`package-shape.json`** (`input_tree_byte_figures()`, `deployed_tree_figures()`) and then
checks how this document labels them. So the artefact is the authority and this document is
the derived side — which is exactly what this file's own §0.1 already says about
`cost-model.json`: *"if a cell and the JSON disagree, the JSON is authoritative and the cell
is the defect."*

Retyping the prose to W1's numbers while the artefact stood would have:

1. made the prose disagree with the artefact this document declares authoritative;
2. turned this document's own before/after rows into **offences** under
   `input_tree_figures_sourced_to_the_deployed_package`, because that checker recognises a
   deployed figure only by matching the artefact's value; and
3. left every dollar figure in §0.1 — each of which `scripts/deploy/cost_model.py` computed
   **from 124,127** — sitting beside an input it was not computed from. An arithmetic that no
   longer closes is a worse defect than an input that is 50 B stale.

**The correct motion is to regenerate `package-shape.json` and `cost-model.json` from the
reproducible build and then re-read this document's cells from them.** Those two files are
under `evidence/deploy/cost/` and are not W6's to write. **This is reported to the lead as
the open action, and named here so the next reader does not mistake the delta for a typo.**

### What moves when that regeneration happens, and what does not

**Does not move.** `static_site.DEFAULT_MAX_RESPONSE_BYTES == 136 * 1024 == 139,264` — W1
re-derived it and the rounding absorbed the growth: 1.10 × 124,177 = 136,594.7, and the next
8 KiB boundary is still 17 × 8192 = **139,264**. Had it not absorbed it, the answer would have
been a smaller artefact and never a larger ceiling. The invariant
`0 < 124,177 < 139,264 < 433,564` holds, and **exactly one** identity object is still refused.

> **THE CONSTANT STILL DOES NOT MOVE; THE ARITHMETIC ABOVE IS NOW DATED — 2026-08-15, R10.**
> Both readings in that paragraph are of the **2026-08-14** tree, and they were correct of it.
> Over the package of record (`sha256 6802872f…`, §0.5) the invariant reads
> `0 < 129,400 < 139,264 < 457,123` — still one identity object refused of 57 — while
> `1.10 × 129,400` no longer rounds back onto 139,264. **The ceiling is unchanged and was not
> re-derived**; under ruling R10 the derivation is the record of how it was CHOSEN, and
> interface I3 is what it is asserted against. §0.5 carries both, measured.

**Moves, and by how little.** Every deployed-tree dollar figure scales by
124,177 ÷ 124,127 = **1.000403**, i.e. **+0.040 %**:

| row | published | after regeneration | survives at published precision? |
|---|---:|---:|---|
| R1 — paced residual, 24 h | $5.44 | $5.4422 | **yes** |
| R3 — unattended 30 d | **$564.04** | $564.27 | rounds to **$564**, so the standing "564/30 d" holds |
| R4 — in-window floor, 60 s | **$1.60** | $1.6006 | **yes** |
| R6 — per minute of detection lag | **$1.6022 / min** | $1.6028 / min | **yes — the standing USD 1.60/min is unaffected** |

**Untouched entirely.** §0.1 rows **L0–L5**, §1.2's $11,701 / $31,049.79 / $10,949, §2.2's
**$33,251.87** and L1's **$229,804.98** are priced from the **input** tree's 1,554,168 B, not
from any deployed figure. The headline *~229,805 unbounded* therefore does not move on this
finding — it moves only if the input tree's largest object is re-derived to something else,
which is the gap the table above prints.

**So the standing cost residual is intact and is restated here unchanged: USD 1.60 / min
in-window, USD 564 / 30 d unattended, against ~229,805 unbounded.**

---

## 0.4 · THE PACKAGE-AND-VERIFY WAVE MOVED NO FIGURE ON THIS PAGE — and the one measurement that will

**Recorded 2026-08-15 by W6 (docs-true).** A wave that rebuilds the console is a wave that
moves every byte figure here, so a page that says nothing after one is a page a reader must
assume is stale. This section says what happened, which is: **nothing, on purpose**, plus one
number that has now been measured in advance of the decision it forces.

### Nothing moved, because nothing was rebuilt or redeployed

~~`out/lambda/mainline-demo-api-arm64.zip` on disk is the artefact the Function URL is serving,
and it is unchanged — `sha256 12fcba7ad69b2ffe…`.~~ **CORRECTED 2026-08-15: that sentence was
true when written and is false about the path now.** The package it describes,
`sha256 12fcba7ad69b2ffe…`, is still the artefact the Function URL is answering with — **that
half stands and nothing was redeployed** — but the file at that path was later rebuilt and now
holds `sha256 6802872f…` (§0.5). **Name the package by digest, not by path**: one path has
carried two artefacts inside one day, which is the whole reason §0.5 exists. Read with
`zipfile` over its `web/` entries on 2026-08-15, the `12fcba7a…` package carries every row
§0.3's deployed column already carries:

    114 entries · 1,274,743 B · 0 source maps
    identity  57 /   985,306 B      .gz siblings  57 / 289,437 B
    largest identity   433,564 B  web/assets/index-DzVoV1YM.js
    largest on the wire 124,177 B  web/assets/index-DzVoV1YM.js.gz
    zip 7,703,067 B over 250 entries

**So §0.1's ladder, §0.3's deltas and the standing residual are all still priced from the tree
that is actually serving.** The wave's finding was about *which console* was compiled into
those bytes — a REPLAY artefact rather than a LIVE one — and a transport selection is not a
byte count. `evidence/deploy/APPLIED.md` records that finding; no dollar figure on this page
turns on it.

### The measurement that will move them, taken before the decision rather than after

A LIVE console that can drive the headline beat needs a seventeenth declared resource and a
23,138 B `gate-run.schema.json` imported as raw text on the critical path. That has landed in
the **source**, and the cost was measured on the **packaged** bytes rather than on a `dist/`
tree — the packer's `web/` entries out of a zip, which is the only tree an origin can emit
from. Built 2026-08-15, `--console-transport both`, `MAINLINE_BUILD_ID=b822fdc`, zip
`sha256 56d6730b8b55…`, to a **scratch path**; `out/lambda/mainline-demo-api-arm64.zip` was
left untouched, so nothing in the suite describes a tree that does not exist.

**SUPERSEDED LATER THE SAME DAY, AND THE TABLE STAYS — §0.5.** What is measured below is a
`--console-transport both` build at a scratch path. What now occupies the deploy path is a
`--console-transport live` build, `sha256 6802872f…`, whose entry chunk measures
**129,400 B** on the wire against the `129,404 B` below — four bytes, one build input, two
different content hashes. **No digit in this table is retyped**; §0.5 carries the packaged
figures and the ruling that goes with them.

| | deployed today (`12fcba7a…`) | the LIVE rebuild (`56d6730b…`) | Δ |
|---|---:|---:|---:|
| `web/` entries | 114 | 114 | 0 |
| `web/` bytes | 1,274,743 | **1,308,123** | +33,380 |
| identity objects | 57 / 985,306 B | 57 / **1,012,489 B** | +27,183 |
| `.gz` siblings | 57 / 289,437 B | 57 / **295,634 B** | +6,197 |
| entry chunk, identity | 433,564 B `index-DzVoV1YM.js` | **457,123 B** `index-CwHiUgyV.js` | **+23,559** |
| **entry chunk, on the wire — `g`** | **124,177 B** | **129,404 B** | **+5,227 B, +4.21 %** |
| identity objects over 139,264 B | 1 | 1 | 0 |

> **Two readings of the same growth exist and they are 33 gzipped bytes apart, on purpose.**
> `evidence/deploy/console-repro.json` → `runs["worktree-phase2"]` records **457,037 B /
> 129,371 B** for a `dist/` built without `MAINLINE_BUILD_ID` (so `buildId` compiles to the
> three characters `dev`) and with `VITE_MAINLINE_API_BASE` alone. The row above is the
> **packaged** artefact built the way a deploy would build it, with the real seven-character
> build id. **The packaged figure is the one this page prices from** — cost is bytes leaving
> the origin, and the origin serves the package. The earlier reading is kept because two
> measurements of one quantity that differ by a build input are how you find out which input
> the number depends on.

**(THIS PARAGRAPH WAS WRITTEN ON 2026-08-15 AND SUPERSEDED THE SAME DAY — the ruling that
settles it is the blockquote immediately below, and the window it argues from is retired.)**

**129,404 B is outside the window that keeps the authoritative ceiling derivable.**
`static_site.DEFAULT_MAX_RESPONSE_BYTES == 136 * 1024 == 139,264` re-derives from
`ceil(floor(1.10·g) / 8192) · 8192` for exactly `119,158 ≤ g ≤ 126,604`; the `g` of the
package that is answering — 124,177 B, 2026-08-14 — sits
2,427 B below the upper edge and the rebuild clears it by **2,800 B**. Re-derived from the new
figure the arithmetic yields **147,456** — and `I3` would still be satisfied
(`129,404 ≤ 139,264 < 155,284.8`), which is precisely what makes this the dangerous case:
**the derivation does not refuse a bigger bundle, it accommodates one.** What breaks is not the
bound but the *tightness* that makes 139,264 a consequence of the tree rather than a number
somebody liked. Raising a ceiling to fit an artefact is the motion this repository forbids, so
it was not taken: **R4 directs a STOP and a report, and that is what happened** —
`docs/decisions/response-ceiling-authoritative-tree.md` §9 is the report, and all three
declaring test files still carry the **deployed** package's numbers.

> **THE STOP ABOVE IS CLOSED, AND THE WINDOW IN IT IS SUPERSEDED — 2026-08-15, ruling R10**
> (`docs/leads/reconcile-constants-plan.md` §1). The lead resolution R4 was waiting for is:
> **the ceiling stays at 139,264 and the derivation is demoted to a dated record of how that
> number was CHOSEN.** The paragraph above is kept because it is the report that produced the
> ruling, and because it states the danger correctly — *a derivation with a rounding step
> accommodates a bigger bundle rather than refusing one.* That is precisely why it is not the
> law: `ceil(floor(1.10·g)/8192)·8192` returns 139,264 for **every** `g` in
> `[119,158, 126,604]`, so `derive(g) == C` never asserted that the ceiling was right — it
> asserted that the console was inside a 7,447-byte pre-image band, which is a **bundle-size
> budget wearing a ceiling's clothes**, and this repository already owns one of those
> (`verticals/mainline/apps/console/scripts/check-budgets.ts`).
>
> **Do not read `119,158 ≤ g ≤ 126,604` anywhere on this page as a live constraint.** It is
> retired as one. The live law is the straddle, interface I3 and exactly-one-refusal — all
> three measured true against the package of record in §0.5 — and the live *warning* is that
> section's headroom line: **9,864 gzipped bytes** remain before the origin would 413 its own
> entry chunk.

**What it would do to the published residual, if the ceiling were raised to admit it.** Rows
R1/R3/R4/R6 are priced from the gzip sibling, so they scale by `129,404 ÷ 124,177 = 1.042093`:

| row | published | at 129,404 B | survives at published precision? |
|---|---:|---:|---|
| R1 — paced residual, 24 h | $5.44 | $5.6690 | **no** — rounds to $5.67 |
| R3 — unattended 30 d | **$564.04** | $587.78 | **no** — the standing "564/30 d" becomes 588 |
| R4 — in-window floor, 60 s | **$1.60** | $1.6673 | **no** — rounds to $1.67 |
| R6 — per minute of detection lag | **$1.6022 / min** | $1.6696 / min | **no** — the standing USD 1.60/min becomes 1.67 |

**None of those figures is published here as current.** They are what the page would carry
*after* a decision nobody has taken, computed now so that the decision is made against its
price rather than after it. **§0.1 is unchanged and USD 1.60 / min in-window and USD 564 / 30 d
unattended remain the standing numbers**, because the tree they are priced from is the tree
that is deployed.

**The honest exit, named rather than implied.** The answer to an object that will not fit is a
smaller artefact — the contract registry and the verifier are on the critical path by a
decision `docs/deploy/console-build.md` §2 records and defends, and a lazy boundary drawn
differently is a change to that decision, not to this ceiling. Whichever way it goes, it is
`docs/decisions/response-ceiling-authoritative-tree.md`'s to record and the lead's to rule.

---

## 0.5 · THE PACKAGE OF RECORD IS A LIVE-TRANSPORT BUILD — measured 2026-08-15, and the ceiling did not move

**Recorded 2026-08-15 by W4 (cost-and-latency pages).** §0.4 predicted this section and named
the figure it would carry; the prediction was taken over a scratch `--console-transport both`
build. This section replaces it with a measurement of the package that is actually in the
deploy path, and states every claim as a **property first and a measurement second**, so that
the next console growth falsifies a number rather than a sentence.

**Read from the zip's own central directory by this worker before anything here was written**,
with `zipfile` over the `web/` entries of
`out/lambda/mainline-demo-api-arm64.zip`, whose SHA-256 was recomputed over the file:
`6802872f805740dd1a7de891eca7a8d1cf6c11f5eb5b639aec5677f5d78ae13b`.

### There are now THREE trees on this page and every figure names which one it is

| tree | what it is | entry chunk | identity | on the wire |
|---|---|---|---:|---:|
| **the origin's package** — `sha256 12fcba7a…` | the bytes the Function URL is answering with; read off the wire 2026-08-14 (`evidence/deploy/judge-walk.json`) and re-taken 2026-08-15 (`evidence/deploy/APPLIED.md`). Its console compiles the `REPLAY` transport | `assets/index-DzVoV1YM.js` | 433,564 B | **124,177 B** |
| **the package of record** — `sha256 6802872f…` | `out/lambda/mainline-demo-api-arm64.zip` as it sits in the deploy path on 2026-08-15, built `--console-transport live` with `MAINLINE_BUILD_ID=b822fdc`. **Nothing has been applied and nothing redeployed**, so this tree is on no origin — the row above, `assets/index-DzVoV1YM.js` in `REPLAY`, is still what answers | `assets/index-BH5dfAvF.js` | 457,123 B | **129,400 B** |
| the packer's **input** tree | `architectures[].before` of `package-shape.json` — the pre-strip baseline §2.2's reproduction runs from, and nothing else | — | — | — |

### The package of record, measured — a dated column beside §0.4's, not a rewrite of it

| | the origin's package (`12fcba7a…`) | **the package of record (`6802872f…`), measured 2026-08-15** | Δ |
|---|---:|---:|---:|
| `web/` entries | 114 | **114** | 0 |
| `web/` bytes | 1,274,743 | **1,308,536** | +33,800 |
| identity objects | 57 / 985,306 B | **57 / 1,012,812 B** | +27,506 |
| `.gz` siblings | 57 / 289,437 B | **57 / 295,724 B** | +6,294 |
| source maps in the package | 0 / 0 B | **0 / 0 B** | 0 |
| entry chunk, identity | 433,564 B `index-DzVoV1YM.js` | **457,123 B `index-BH5dfAvF.js`** | +23,559 |
| **entry chunk, on the wire — `g`** | **124,177 B** | **129,400 B** | **+5,223 B, +4.20 %** |
| 2nd largest identity | `surface-BcxWkbKu.js`, 51,266 B | **`surface-0lG8KzXw.js`, 51,266 B** | 0 B, different file |
| `index.html` / `index.html.gz` | 4,655 B / 2,123 B | **4,655 B / 2,122 B** | 0 / −1 |
| identity objects over the 139,264 B ceiling | 1 | **1** | 0 |

**Provenance of each column, because they were not taken by the same hand.** The right column
was measured here, from the zip named above, by the worker who wrote this section. The left
column is §0.3's and §0.4's re-reading of the `12fcba7a…` package, except `index.html.gz`
at 2,123 B, which is `docs/leads/reconcile-constants-plan.md` §0.1's measurement of it and is
quoted rather than re-taken. **The one-byte `index.html.gz` delta is the only cell in this
table that rests on somebody else's reading**, and it is named so that nobody has to guess.

The packer's **input** tree for this build measures **75 entries / 3,643,912 B** with
**18 source maps / 2,631,100 B** stripped, per the build's own sidecar
`out/lambda/mainline-demo-api-arm64.zip.json` → `package_shape`. It is recorded for
completeness and **nothing on this page is priced from it**; §1's I4/I6/I7 and §2.2's
reproduction stay pinned to `package-shape.json`, which is their authority and is not this
worker's file.

### The ceiling: what is law, what is provenance, and what this page will no longer say

**Ruling R10** (`docs/leads/reconcile-constants-plan.md` §1) governs every ceiling sentence
here: *"`DEFAULT_MAX_RESPONSE_BYTES` remains `136 * 1024 == 139_264`, unchanged, not raised,
not lowered. The live law is interface I3 and the straddle. The derivation is preserved as a
dated record of how 139,264 was CHOSEN … and is no longer asserted against the current tree."*

Properties first, measurements second, each against `6802872f…` on 2026-08-15:

* **The ceiling refuses exactly one identity object of the tree it governs.** Measured: **1 of
  57**. Today that object is `assets/index-BH5dfAvF.js` at **457,123 B**.
* **The straddle holds**, `0 < g < C < I`. Measured: `0 < 129,400 < 139,264 < 457,123`.
* **Interface I3 holds in both halves** — the origin can serve its own site, and the ceiling
  may not float free of what it governs. Measured:
  `129,400 ≤ 139,264 < 1.20 × 129,400 = 155,280`.
* **The derivation is provenance.** `139,264` was CHOSEN over the **2026-08-14** tree, where
  `g = 124,177`: `floor(1.10 × 124,177) = 136,594 → 17 × 8,192 = 139,264`. Over the package of
  record the same arithmetic emits `floor(1.10 × 129,400) = 142,340 → 18 × 8,192 = 147,456`.
  **That is not the ceiling, and it is not a proposal to make it one.** A cost bound is not
  raised so that a formula agrees; the founder accepted this deploy on the condition that
  bounds exist in code, and 139,264 is byte-identical to what it always was.

**The number with teeth is the headroom, and it is the one to watch.**

```
headroom = 139,264 − 129,400 = 9,864 gzipped bytes      (it was 15,087)
```

**A console growth of more than 9,864 gzipped bytes on the entry chunk puts `g` above `C`, and
the origin then answers 413 to its own entry chunk on every path.** That is an outage, not a
cost finding, and `_assert_i3`'s lower half is what catches it. **This replaces R4's window
`119,158 ≤ g ≤ 126,604` as the live constraint on this page** — the window is retired (§0.4's
blockquote says why) and no sentence here may carry it as a rule.

**The I3 ratio moved `139,264 / 124,177 = 1.121` → `139,264 / 129,400 = 1.076`, and that is
the SAFE direction.** The `1.20` ratchet exists against the ratio **climbing** — a ceiling
drifting so far above the tree that it refuses nothing. A ratio falling toward 1.0 is a bound
biting harder, not a bound being loosened. The compression cut moved with it,
`457,123 / 129,400 = 3.5326` against `3.4915`.

### What this does to §0.1 — nothing yet, and exactly this much on the day it deploys

**The package of record has not been deployed**, so §0.1 is unchanged and is still priced from
the tree that is answering. Rows R1/R3/R4/R6 are priced from the gzip sibling, so on the day it
is deployed they scale by `129,400 ÷ 124,177 = 1.042061`:

| row | published | at 129,400 B | survives at published precision? |
|---|---:|---:|---|
| R1 — paced residual, 24 h | $5.44 | $5.6688 | **no** — rounds to $5.67 |
| R3 — unattended 30 d | **$564.04** | $587.76 | **no** — the standing "564/30 d" becomes 588 |
| R4 — in-window floor, 60 s | **$1.60** | $1.6673 | **no** — rounds to $1.67 |
| R6 — per minute of detection lag | **$1.6022 / min** | $1.6696 / min | **no** — the standing USD 1.60/min becomes 1.67 |

**§0.4 computed this same column at `129,404` and got $5.6690 / $587.78 / $1.6673 / $1.6696.**
Four bytes in 129,400 move nothing at any published precision, which is the whole of the
correction and is worth one line rather than an argument. **No figure in §0.1 was retyped**:
that table is a lookup into `cost-model.json`, the JSON is authoritative, and the day this
package deploys the model is re-run rather than the prose edited.

**The standing residual is therefore unchanged and is restated here as such: USD 1.60 / min
in-window, USD 564 / 30 d unattended, against ~229,805 unbounded.**

### Three things this section deliberately does not say

* **It does not say the ceiling was re-derived.** It was not.
  `verticals/mainline/apps/demo-api/src/mainline_demo_api/static_site.py` was not opened by
  this wave and `136 * 1024` is unchanged in it.
* **It does not propose 147,456.** That arithmetic is recorded because it is what changed, and
  recording it is how a reader can check that it was refused rather than quietly taken.
* **It does not call the larger entry chunk a defect.** The console grew because a seventeenth
  declared resource and its 23,138 B contract landed on the critical path — a decision
  `docs/deploy/console-build.md` §2 records and defends. A smaller entry chunk would be a
  better console and is legitimate work on its own merits; it is not a remedy this ceiling
  requires, and re-cutting the artefact to make a formula come out is the same error as
  re-cutting the formula, pointed the other way.

---

## 1 · The measured inputs

> **ANNOTATED 2026-08-14 — I4, I6 AND I7 DESCRIBE THE PACKER'S *INPUT* TREE, AND THEY SAID
> OTHERWISE.** All three were sourced to *"`zipfile` over
> `out/lambda/mainline-demo-api-arm64.zip`"* — the **deployed** zip — and written in the
> present tense (*"Largest response the origin **can emit**"*). That zip has held **zero
> source maps** since the strip became the build default (§3.2). This is the worst way for a
> claim to be false: it names an artefact a reader can open in thirty seconds and be told the
> opposite.
>
> **The digits are correct and are not retyped.** They are true measurements of the
> **pre-strip input tree**, recorded as such in
> [`evidence/deploy/cost/package-shape.json`](../../evidence/deploy/cost/package-shape.json)
> under `architectures[].before`, and they are **load-bearing**. `1,554,168 B` is the input
> §2.2's **$33,251.87** is re-derived from, which
> `tests/deploy/test_cost_model.py::test_the_model_reproduces_every_published_headline` fails
> the build over; it is also the byte count §0.1 row **L1**'s **×6.91** correction — the
> largest honesty finding in this document — is built on. Retyping them would break the
> reproduction this document's own header promises and erase that finding. **What was false is
> the tense and the sourcing.** Those are corrected in place, and the deployed-tree figure is
> printed beside each row.
>
> | | files | bytes | source maps | `.gz` siblings | largest object |
> |---|---:|---:|---:|---:|---:|
> | `architectures[].before` — the packer's **input** tree, pre-strip | 75 | 3,571,990 | 18 / 2,586,960 B | 0 | **1,554,168 B** `index-BjAGxrVJ.js.map` |
> | `architectures[].after` — the **deployed** package, today | 114 | 1,274,342 | **0 / 0 B** | 57 / 289,312 B | 433,396 B identity / **124,127 B** gz |
>
> **Both columns are true, of different trees**, and neither may be quoted without naming
> which. Cost is bytes leaving the deployed origin, so every ceiling and cost claim is the
> **after** column (`docs/decisions/response-ceiling-authoritative-tree.md` §1); the
> **before** column is the pre-strip baseline the reproduction runs from and nothing else.
> The `x86_64` architecture carries byte-identical `web/` figures in the same artefact.

Every row is a command I ran today, not a figure inherited from a board or an audit. **Rows
I4–I7 are dated 2026-08-13 and are annotated above: they measure the input tree, not the
package that ships.**

| # | Input | Measured value | How |
|---|---|---|---|
| I1 | Account concurrency ceiling, `ap-southeast-1` | **10** (`ConcurrentExecutions`, `UnreservedConcurrentExecutions`) | `aws lambda get-account-settings --region ap-southeast-1` |
| I2 | Same, `ap-southeast-2` | **10**, `FunctionCount 1` (an unrelated live project — do not touch) | `aws lambda get-account-settings --region ap-southeast-2` |
| I3 | The quota behind I1 | `L-B99A9384` "Concurrent executions" = **10.0**, **`Adjustable: true`** | `aws service-quotas get-service-quota --service-code lambda --quota-code L-B99A9384` |
| I4 | ~~Largest response the origin can emit~~ **Largest object in the packer's INPUT tree** (pre-strip) | **1,554,168 B** — `web/assets/index-BjAGxrVJ.js.map`. **Deployed tree today: 433,396 B** identity (`index-BjAGxrVJ.js`) and **124,127 B** on the wire as its `.gz` sibling; **the map is not in the package at all** | ~~`zipfile` over `out/lambda/mainline-demo-api-arm64.zip`~~ → `evidence/deploy/cost/package-shape.json` `architectures[].before.web.largest_identity_object`; deployed figure from `architectures[].after.web` |
| I5 | Largest **non-map** asset — **the same object in both trees** | **433,396 B** — `web/assets/index-BjAGxrVJ.js`. A browser receives the **124,127 B** `.gz` sibling; the **139,264 B** ceiling refuses the identity form (§3.3) | `architectures[].before.web` (largest non-map) and `architectures[].after.web.largest_identity_object` — **both 433,396** |
| I6 | ~~Whole served tree~~ **Whole `web/` tree in the packer's INPUT tree** | **3,571,990 B** over **75** files. **Deployed tree today: 1,274,342 B over 114 entries** — 57 identity / 985,030 B plus 57 `.gz` siblings / 289,312 B | ~~same~~ → `architectures[].before.web`; deployed figure from `architectures[].after.web` |
| I7 | …of which source maps — **in the INPUT tree** | **2,586,960 B** over **18** files = **72.4235 %**. **Deployed tree today: 0 B over 0 files** — stripping is the default in both builders (§3.2) | ~~same~~ → `architectures[].before.web.source_maps`; deployed figure from `architectures[].after.web.source_maps`, which reads `0 / 0` |
| I8 | Function URL auth | `NONE` | `evidence/deploy/terraform-plan-furl.txt:`~~329~~ **351** *(the `aws_lambda_function_url.this` block opens at 349)* |
| I9 | Function shape | `mainline-demo-api`, arm64, `memory_size = `~~512~~ **256**, `timeout = `~~15~~ **14**, `reserved_concurrent_executions = `~~20~~ **-1** | `evidence/deploy/terraform-plan-furl.txt:`~~264-301~~ **276-348** — the `aws_lambda_function.this` block; `memory_size` at **:290**, `reserved_concurrent_executions` at **:296**, `timeout` at **:315** |

**I8 and I9 moved because the artefact is authoritative and this prose is derived.** The
values struck through above were the pre-plan shape; `evidence/deploy/terraform-plan-furl.txt`
is the committed plan artefact and it is the side that decides. The old line citation in I8
(`:329`) was never re-checked after the plan was regenerated, which is the kind of rot that is
invisible until a reviewer follows the citation, lands on an unrelated line, and stops trusting
the rest of the page.

> **I8 AND I9'S CITATIONS RE-CHECKED AFTER THE 2026-08-14 REGENERATION — W5.**
> `evidence/deploy/terraform-plan-furl.txt` was regenerated at HEAD `d098721` (see
> `docs/deploy/terraform-plan.md`, *"Both counts, as measured"*), and the paragraph above is
> precisely the reason not to assume the line numbers survived it. **All six were opened and
> every one still resolves:** `:351` `authorization_type = "NONE"` (block opens at `:349`),
> `:290` `memory_size = 256`, `:296` `reserved_concurrent_executions = -1`, `:315`
> `timeout = 14`, and `:124` `threshold = 13500` for the `-duration-p99` alarm. The file kept
> its **934** lines through the regeneration, so the numbering did not shift.
>
> **I4–I7's figures were re-derived in the same sitting and are NOT retyped here.** §0.3
> carries them: the input tree measures **75 entries / 3,566,324 B / 18 maps / 2,581,018 B**
> with a largest object of **1,551,887 B**, and the deployed zip measures **114 entries /
> 1,274,743 B / 0 maps**, largest identity **433,564 B**, largest on the wire **124,177 B**.
> *(Those are the 2026-08-14 package, `sha256 12fcba7a…`, which is the one answering. The
> package of record on disk since 2026-08-15, `sha256 6802872f…`, measures 114 entries /
> 1,308,536 B / 0 maps, largest identity 457,123 B, largest on the wire 129,400 B — §0.5.)*
> The cells above still read `package-shape.json`'s values because that artefact is the
> authority `tests/deploy/test_docs_are_true.py` reads them out of, and it is not this
> worker's to regenerate. **The rows are labelled and sourced correctly, which is the defect
> that was actually open here** — I4 and I6 once claimed the *deployed* tree, sourced to a zip
> anyone could open and be told the opposite. **They no longer do**, and §0.3 now names the
> deployed figure for each.

Two facts from I4–I7 that decide most of this document:

* `web/` is the **only** servable tree in the package (the other top-level entries are
  `mainline_demo_api/`, `psycopg/`, `psycopg_binary/` and their dist-infos — code, not
  routes). So the flood target is fully enumerated above. *(True of both trees. The deployed
  one holds 114 entries rather than 75 because every compressible entry gained a `.gz`
  sibling and every source map was dropped.)*
* ~~**Exactly one file in the entire package is ≥ 512 KiB, and it is a source map.**~~
  **True of the INPUT tree only.** Every non-map asset was, and still is, ≤ 433,396 B.
  ~~That single fact is what makes L3 cost-free (§3.3).~~ **It is also what made the 512 KiB
  form of L3 worthless**: in the deployed package **nothing is ≥ 512 KiB at all**, so that
  line would have refused *zero* of 114 entries once the strip landed. The ceiling in force is
  **139,264 B** — ~~derived from the deployed tree rather than chosen~~ **CORRECTED 2026-08-15
  (R10, §0.5): CHOSEN over the 2026-08-14 tree and KEPT by interface I3** — and it refuses even
  the 433,396 B identity bundle. A ceiling above everything it governs is a decoration, not a
  control — the correction is recorded in §3.3 and the reasoning it replaces is kept there.

### 1.1 · The tariff, read from the Pricing API rather than from memory

```
aws pricing get-products --service-code AWSDataTransfer --region us-east-1 \
    --filters Type=TERM_MATCH,Field=fromLocation,Value="Asia Pacific (Singapore)" \
              Type=TERM_MATCH,Field=transferType,Value="AWS Outbound"
```

`sku SDHP4R7WGBVJPQPY`, `effectiveDate 2026-06-01`, `publicationDate 2026-07-20`:

| beginRange | endRange | USD / GB | Description as returned |
|---|---|---|---|
| 0 | 10240 | **0.12** | first 10 TB / month, *beyond the global free tier* |
| 10240 | 51200 | **0.085** | next 40 TB / month |
| 51200 | 153600 | **0.082** | next 100 TB / month |
| 153600 | Inf | **0.080** | greater than 150 TB / month |

Lambda, same API (`--service-code AWSLambda`, `regionCode ap-southeast-1`):

| Usage type | Rate | Meaning |
|---|---|---|
| `APS1-Request` | **$0.0000002 / request** | = **$0.20 per million** |
| `APS1-Lambda-GB-Second` | $0.0000166667 / $0.0000150000 / **$0.0000133334** | volume tiers |

The arm64 GB-second rate for `ap-southeast-1` is **$0.0000133334** and our volume
(≈ 1.3 × 10⁷ GB-s/month) sits far inside tier 1. I did not isolate the ARM-specific SKU
through the API's pagination, and I am not going to pretend I did: **compute is 0.5 % of
this bill** (§2.2), so even a 100 % error in that rate moves the total by half a percent.
The number that matters is the egress tariff above, and that one is measured.

### 1.2 · One correction to the inherited arithmetic

The tier boundaries come back as **10240 / 51200 / 153600**, not 10,000 / 50,000 / 150,000.
Those are `10×1024`, `50×1024`, `150×1024` — **binary**. AWS prints the unit as "GB" and
means GiB. The lead's §0.3 and the audit both tiered on decimal boundaries with
`1 GB = 10⁹ B`.

This is not a rounding quibble; it moves the total by ~7 %. I therefore compute **both** and
say which is which:

| Convention | Worst case (100 ms) | Best case (300 ms) |
|---|---|---|
| Decimal (`1 GB = 10⁹ B`, decimal tiers) — **conservative, reproduces the audit** | **$33,252** | **$11,701** |
| Measured tariff (`1 GB = 2³⁰ B`, binary tiers, 100 GB free) — **more likely actual** | $31,050 | $10,949 |

**I headline the decimal figure**, because a bound that understates is not a bound. The
7 % gap between the conventions is an order of magnitude smaller than the **3×** spread
that comes from the invocation-time assumption, and **no lever's ranking changes under
either**. So the convention question is recorded and then set aside.

---

## 2 · The arithmetic, reproduced from first principles

> **ANNOTATED 2026-08-14 — THIS WHOLE SECTION IS PRICED ON THE PACKER'S *INPUT* TREE, AND IT
> IS SUPPOSED TO BE.** The `1,554,168 B` in §2.1's model and §2.2's egress line is
> `architectures[].before.web.largest_identity_object` —
> [`evidence/deploy/cost/package-shape.json`](../../evidence/deploy/cost/package-shape.json) —
> the **pre-strip** baseline, and it is **load-bearing**: `scripts/deploy/cost_model.py` must
> re-derive **$33,251.87** from exactly this input before it is allowed to publish anything in
> §0.1, and `tests/deploy/test_cost_model.py::test_the_model_reproduces_every_published_headline`
> fails the build if it cannot. **No digit here moved and none may.**
>
> **What was missing is the label, and this is the whole of the correction.** Neither line
> named its tree, and this document's own header says *"a figure that does not name its tree
> is wrong, whichever tree it came from"* — so a reader could reasonably have taken §2 as an
> account of what the shipping origin can put on the wire. **It is not.** The deployed
> package holds **zero** source maps, its largest identity object is **433,396 B** and the
> largest body it actually emits is the **124,127 B** `.gz` sibling (`architectures[].after`).
> The corrected ladder that starts from the deployed tree is **§0.1 rows L2–L6**, not this
> section. §2 is the reproduction baseline and nothing else.

### 2.1 · The model

The attacker holds concurrency at the ceiling and fetches the largest asset every time.
No credential, no rate limit, no CAPTCHA — the URL is `authorization_type = NONE`.

```
concurrency               10                      (I1, and it is a hard ceiling)
invocation duration       100 ms … 300 ms         (the span of a static-asset read)
request rate              10 / 0.100 = 100 rps  …  10 / 0.300 = 33.3 rps
bytes per request         1,554,168 B             (I4 — the packer's INPUT tree, pre-strip)
window                    30 d = 2,592,000 s
```

100 rps × 1,554,168 B × 2,592,000 s = **402.84 TB** (decimal) / **375,174 GiB** (measured tariff)

**That 1,554,168 B is `architectures[].before.web.largest_identity_object`** — the packer's
**input** tree. The deployed package does not contain that object; see the annotation under
§2's heading for why the figure stays and what it is for.

### 2.2 · Tier by tier, the 100 ms case

Decimal convention — the headline:

| Tier | Volume | Rate | Cost |
|---|---|---|---|
| first 10 TB | 10,000 GB | $0.120 | $1,200.00 |
| next 40 TB | 40,000 GB | $0.085 | $3,400.00 |
| next 100 TB | 100,000 GB | $0.082 | $8,200.00 |
| beyond 150 TB | 252,840 GB | $0.080 | $20,227.23 |
| **egress** | **402,840 GB** | | **$33,027.23** |
| requests | 259.2 M × $0.20/M | | $51.84 |
| compute | 259.2 M × 0.1 s × 0.5 GB × $0.0000133334 | | $172.80 |
| | | **TOTAL** | **$33,251.87** |

Measured-tariff convention, same flood:

| Tier | Volume | Rate | Cost |
|---|---|---|---|
| 0 – 10240 | 10,240 GB | $0.120 | $1,228.80 |
| 10240 – 51200 | 40,960 GB | $0.085 | $3,481.60 |
| 51200 – 153600 | 102,400 GB | $0.082 | $8,396.80 |
| > 153600 | 221,474 GB | $0.080 | $17,717.94 |
| **egress** (after 100 GB free) | **375,074 GB** | | **$30,825.14** |
| requests + compute | | | $224.64 |
| | | **TOTAL** | **$31,049.79** |

The 300 ms case is the same egress model at one third the rate: **$11,701** / **$10,949**.

### 2.3 · Agreement with the audit

| Source | Range |
|---|---|
| The 31-agent audit | $11,515 – $33,472 |
| Lead's §0.3 | $11,538 – $33,257 |
| **This document, decimal** | **$11,701 – $33,252** |
| This document, measured tariff | $10,949 – $31,050 |

Independently derived, my decimal figures land **within 1.6 %** of the audit at the low end
and **within 0.7 %** at the high end. **The range is not a guess. It is 30 days at
concurrency 10 with a 100–300 ms invocation, and it reproduces.**

### 2.4 · The arithmetic was checked twice, in two languages

The egress tiering was implemented a second time as SQL against the local CockroachDB
v26.2.5 node (scratch database `w_w6`, table `egress_tier`), independently of the Python:

```
baseline-100ms   billedGB=  375174   SQL egress = $30,833.12
baseline-300ms   billedGB=  125058   SQL egress = $10,766.76
L2-strip-100ms   billedGB=  104621   SQL egress = $ 9,090.92
```

The two implementations agree to **$7.98**, which is exactly the 100 GB global free tier
priced at the marginal rate ($0.08 × 100 = $8.00) — the SQL version does not model the free
tier and the Python one does. A disagreement of precisely the term one side omits is the
result you want from a cross-check.

### 2.5 · What the flood does **not** touch

It never reaches CockroachDB. The target is the static tree; `/v1/*` is not involved. So the
**CockroachDB Basic $25 cap bounds the database and nothing else** — it is a real bound on a
resource that is not under attack. Nobody should count it toward this number.

---

## 3 · The menu

Worst case before any lever: **≈ $33,250 / 30 d** (best case of the same flood ≈ $11,700).
All deltas are against that.

| # | Lever | Worst case after | Bounds | Does **NOT** bound | Judge friction | Build cost |
|---|---|---|---|---|---|---|
| **L1** | `reserved_concurrent_executions = -1` | $33,250 (unchanged) | **nothing** — but required for any apply at all | anything | none | 0 |
| **L2** | Strip source maps (already built, off by default) | **≈ $9,900** | bytes/request, 3.586× | request rate | minified DevTools frames | 0 |
| **L3** | Handler response cap at 512 KiB (W4) | **≈ $9,900**, and **ratcheted** | bytes/request, permanently | request rate | **none** | 0 |
| **L4** | Per-IP throttle in the handler | ≈ **$230** vs one source | egress from one source (~7,000×) | a distributed flood; the invocation charge | none | 0 |
| **L5** | Shared-secret gate | ≈ **$230** | egress from every caller who has not read the submission | a determined attacker | one longer URL | 0 |
| **L6** | Budgets → SNS → responder → `PutFunctionConcurrency(0)` | ≈ **$1,100 already spent** | nothing in the first day | the first 8–24 h, which is where the money is | none | 0, +3 resources |
| **L7** | Timeout 15→5 s, memory 512→256 MB *(the shipping shape is **14 s / 256 MB** — §3.7)* | $33,165 | **0.28 %** of the bill | 99.7 % of it | worse cold starts | 0 |
| **L8** | `authorization_type = AWS_IAM` | **≈ $0** | everything — rejection is pre-invocation | nothing | **total: 403 to the judges** | 0 |
| **L9** | `PutFunctionConcurrency(0)` kill switch | **$0** from the moment it runs | everything, instantly | the time before somebody looks | none | 0 |

### 3.1 · L1 — `reserved_concurrent_executions = -1`

**This is not a cost lever. It is the lever that makes the apply possible at all**, and it is
in this menu only so nobody mistakes it for one.

The plan reserves **20**. The account ceiling is **10** (I1). `PutFunctionConcurrency` is the
sixth of eleven API calls in the apply; it will be refused, and five resources will already
exist when it is.

The cost consequence is the part people get backwards: `min(20, 10) = 10`. **The account
already caps concurrency at 10.** Setting `-1` removes an unappliable reservation and leaves
the identical physical bound in place. It **does not raise the ceiling**, and it does not
raise the worst case by one cent.

*Bounds:* nothing. *Does not bound:* anything. *Take it because the apply cannot run without
it, not because it is safety.*

### 3.2 · L2 — strip the source maps

> **SHIPPED. This section is the decision record; the switch has been thrown.** Stripping is
> now the **default** in both builders, `--keep-source-maps` / `-KeepSourceMaps` is the
> opt-out, and the artefact confirms it:
> [`evidence/deploy/cost/package-shape.json`](../../evidence/deploy/cost/package-shape.json)
> reads **0 source maps, 0 B** where it once read 18 files and 2,586,960 B. The sentence
> below — "it is off by default" — was true when written and is **false now**. See §0.1 L2
> for what it was actually worth: bytes fell 3.59× and the bill fell only 1.43×.

Already implemented as `--strip-source-maps` in `scripts/deploy/build_lambda.sh`
(lines 105, 122, 537, 583, 830) and `-StripSourceMaps` in the `.ps1`. It records
`source_maps: kept|stripped` in the manifest. ~~**It is off by default, on purpose**~~ — the
header at line 41 explains why, and that reasoning is sound: a judge opening DevTools sees
real component names.

* ~~Largest emittable response~~ **Largest object, INPUT tree → DEPLOYED package**:
  **1,554,168 → 433,396 B**, a factor of **3.586** (`architectures[].before` →
  `…after.web.largest_identity_object`). **433,396 B is still not an emittable response**: the
  139,264 B ceiling refuses the identity form and the origin puts the **124,127 B** `.gz`
  sibling on the wire (§3.3).
* Package: −2,586,960 B — ~~72.4 % of the served tree~~ **72.4 % of that INPUT tree**
  (2,586,960 ÷ 3,571,990), and **0 % of the served tree, because the maps are stripped before
  it exists**. Same correction, same reason, as `docs/deploy/lambda-bundle.md` §4.4.
* Worst case: **$33,250 → ≈ $9,900** (measured tariff: ≈ $9,300).

*Bounds:* bytes per request. *Does **not** bound:* the request rate, the invocation charge, or
any future asset that grows past 433 KB — stripping maps is a one-time subtraction, not a
ratchet. That is precisely what L3 adds.

**This is a founder decision, not a worker task.** Flipping the default changes the zip
hash and cascades into `evidence/deploy/lambda-bundle.json`, the dry-run evidence and the
manifest assertions. W6 costs it; the orchestrator executes it if it is taken.

### 3.3 · L3 — the handler response cap (W4)

A declared ceiling above which the handler returns 413 instead of a body.

> **SHIPPED, AND AT A DIFFERENT NUMBER THAN THIS SECTION PROPOSES.**
> `static_site.DEFAULT_MAX_RESPONSE_BYTES` is **139,264 B (136 KiB)**, not 512 KiB. The
> reasoning below — "at 512 KiB this costs literally nothing" — was the *problem*, not the
> recommendation: a ceiling that refuses nothing in the tree it governs is a decoration, and
> once the strip landed (§3.2) the 512 KiB line refused **zero** of 114 entries. The ceiling
> is ~~now **derived from the deployed tree** rather than chosen~~ **CORRECTED 2026-08-15
> (R10, §0.5): CHOSEN by the derivation over the 2026-08-14 tree and KEPT by interface I3,
> which is what it is asserted against today**, and it binds: it refuses the
> 433,396 B identity bundle, which every real browser avoids by sending
> `Accept-Encoding: gzip` and receiving the 124,127 B sibling instead. That consequence is
> deliberate and is stated loudly in `static_site.py` rather than avoided by picking a
> looser number.

**At 512 KiB = 524,288 B this costs literally nothing**, and I5/I6 are why — **every count in
the block below is over the packer's INPUT tree (`architectures[].before.web`, 75 entries),
which is the only tree that existed when this was written**:

```
largest non-map asset           433,396 B
proposed cap                    524,288 B
headroom                         90,892 B
assets in the INPUT tree >= cap         1   ← and it is a source map
```

*(That line read `assets in the package >= cap` until 2026-08-14. The digit is right and the
tree was unnamed: in the **deployed** package the same cap refuses **zero** of 114 entries,
which is the finding the blockquote above this block records.)*

So a 512 KiB cap **rejects exactly one file in the entire package**, and that file is the one
L2 removes anyway. Every legitimate asset passes untouched. Judge friction: **none**.

*Bounds:* bytes per request — **and ratchets it**, so the number can never silently grow when
someone adds an asset. *Does **not** bound:* the request rate. An attacker still gets
433,396 B per request, so L3-at-512-KiB and L2 have the **same** worst case; they differ in
that L3 is a guarantee and L2 is a build-time coincidence. **Take both.**

### 3.4 · L4 — per-IP throttle

A 429 body is ~200 B against 1,554,168 B — **the packer's INPUT tree's largest object,
pre-strip (§1 I4)**, because §3's whole menu is costed against the $33,250 pre-lever headline
— a **7,000×** collapse in egress from a single source. Worst case ≈ **$230**.

*(The ratio is unchanged and the digit is not retyped. **Against the tree that deploys the
collapse is smaller and the conclusion is the same**: ~200 B against the 124,127 B body the
origin actually emits is ~620×, and the $230 floor below is unaffected because it is
**invocation charges**, which no body-size lever touches.)*

Three honest limits:

1. **Lambda charges for the invocation whether it 429s or not.** At the $230 floor,
   **$172.80 is compute and $51.84 is requests — the egress rounds to zero inside the 100 GB
   free tier.** So $230 is not "the throttle's cost", it is *the cost of being invoked
   259 million times*, and **no body-size lever can go below it.** Only pre-invocation
   rejection (L8) or no invocation at all (L9) goes lower.
2. **A distributed flood defeats it outright.** Per-IP means per-IP.
3. **The counter is per-instance.** With up to 10 concurrent instances and no shared store,
   each instance sees roughly a tenth of one IP's traffic, so the effective threshold is
   ~10× looser than the number in the code. Shared state (DynamoDB, ElastiCache) would fix
   the approximation and would also break the 11-resource plan shape. Not worth it.

### 3.5 · L5 — shared-secret gate

A query parameter or header the handler requires. Worst case ≈ **$230** (the same floor, for
the same reason as L4).

**Be honest about what this is: it is obscurity, not authentication.** The token is public the
moment the submission publishes. It does not stop a determined attacker who reads the
Devpost entry. What it *does* stop is **every opportunistic scanner**, and a scanner sweeping
`*.lambda-url.*.on.aws` is overwhelmingly the realistic way this URL gets found — nobody is
targeting this project by name.

Judge friction: one longer URL in the submission form. That is the entire cost.

### 3.6 · L6 — the budget action, and why it cannot do what people think

**AWS Budgets cannot disable a Lambda function. There is no Lambda budget action.** The three
action types are:

1. apply an **IAM policy**,
2. apply an **SCP** — AWS Organizations only, which this account is not, and
3. stop **EC2 / RDS instances**.

So the only real path is **Budgets → SNS → a responder Lambda that calls
`PutFunctionConcurrency(0)`**. And that path inherits the thing that disqualifies it as a
bound: **Cost Explorer data lags 8–24 hours.** At ≈ $1,035–1,108 per day, the backstop fires
**after roughly $1,100 is already spent** — and that is the *optimistic* reading, because the
budget must first be breached before the action can trigger, and all three budgets are
**already breached** (§4).

*Bounds:* the second day onward. *Does **not** bound:* the first 8–24 hours, which is where
essentially all of the money is. **It is a backstop, not a bound**, and it must never be
presented on the same line as one.

~~If taken, it ships `count = 0` by default so the plan stays at 11 resources.~~

> **TAKEN, AND AT A DIFFERENT SHAPE THAN THIS SECTION PROPOSES.** It did **not** ship
> `count = 0`. `module "guard"` is instantiated at `infra/envs/demo/main.tf:631` under
> `count = var.enable_api ? 1 : 0`, so it is present in every configuration that has an API
> — which is the shipping one — and the plan moved **11 → 24**, not "stayed at 11" (§0.2).
> The reasoning above still stands where it was aimed: **Budgets** remains a backstop with an
> 8–24 h lag and must never be presented as a bound. What the module actually ships is three
> **CloudWatch alarms** on `Invocations` and log `IncomingBytes`, whose detection window is
> **60 s** rather than 8–24 h; the budget is one of its 13 resources and is the slowest of
> them. §0.1 rows R4–R6 price the fast path; row R1 prices what still escapes on the
> Budgets lag.

### 3.7 · L7 — reducing memory and timeout is **not** a cost control

> **THE SHIPPING NUMBERS ARE 14 s AND 256 MB, NOT 15 s AND 512 MB.** The committed plan
> artefact reads `timeout = 14` (`evidence/deploy/terraform-plan-furl.txt:315`),
> `memory_size = 256` (`:290`) and `reserved_concurrent_executions = -1` (`:296`). The
> "15 s" and "512 MB" below are the **pre-plan** shape this section argued against; they are
> kept because an argument is only checkable against the thing it argued about.
>
> **The reasoning is unchanged, and it is the reason the number is 14 s rather than 3 s.**
> `timeout` is a **reliability** bound, not a spend bound — Lambda bills actual duration, so
> the timeout is not in the cost arithmetic at any value. What moved is only the value, and it
> was chosen from measurement: the founder's requested 3 s is **0.80×** the corrected warm
> in-region gate-run p99 of ≈ 3,729 ms (`docs/deploy/LATENCY.md` §0, §3), so a 3 s timeout
> would **truncate the headline beat** — a far worse defect than a larger bill. Read every
> *"keep the 15 s timeout"* in this document as **keep the 14 s timeout**, for the same reason
> the sentence gave in the first place.

Say this plainly, because it is the most commonly mis-sold lever in the menu:

```
compute at 512 MB      $172.80    of  $33,251.87   =  0.52 %
compute at 256 MB      $ 86.40
saving                 $ 86.40    of  $33,251.87   =  0.28 %
```

**Halving the memory saves $86 out of $33,000.** And reducing the *timeout* from 15 s to 5 s
saves **exactly $0**, because Lambda bills actual duration and these invocations run
100–300 ms — the timeout is not in the arithmetic at all. What a timeout bounds is the blast
radius of one hung invocation, which is a *reliability* property, not a spend one.

Selling L7 as a cost bound would be the same defect this module's own
`lifecycle.precondition` exists to refuse: **a control that looks present and is not.**

One nuance, so this is not overstated: *after* L4/L5 land, compute is 77 % of the remaining
$230, and L7 would then matter proportionally. But by then the absolute number is two
hundred dollars, and L7 was never what got it there. **Reject L7 as a cost control. Keep the
~~15 s~~ 14 s timeout for the pgwire round trip it exists for** — 14 s is what the plan ships
(`evidence/deploy/terraform-plan-furl.txt:315`), and it is kept for a **reliability** reason,
not a spend one.

### 3.8 · L8 — `AWS_IAM` bounds everything, and breaks the submission

With `authorization_type = AWS_IAM`, an unsigned request is rejected by the Function URL auth
layer **before the function is invoked**: no invocation charge, no compute, empty body. The
worst case really is **≈ $0**. It is the only lever in this menu that bounds *everything*.

And it **403s the judges.** They have no credentials in this account and cannot sign SigV4.
The fix for that is a CloudFront distribution in front with an OAC — and **this account is
refused CloudFront**, which is the whole reason Decision D1 put the demo on a Function URL.

An `AWS_IAM` URL with no distribution is not a hardened demo. It is a 403 to everyone,
including the people the demo exists for. **Reject.**

*(Documented AWS behaviour, not measured on this account — confirming it requires deploying
the function.)*

### 3.9 · L9 — the kill switch

`PutFunctionConcurrency(0)`. Reserving zero makes the function stop accepting invocations
immediately; spend goes to **$0** the moment it lands.

It is also **the one reservation this account can still accept**: reserving 0 does not push
`UnreservedConcurrentExecutions` below its minimum, which is exactly what refuses every
positive value here (§3.1). So the account that cannot accept `reserved = 20` *can* accept
`reserved = 0`.

*Bounds:* everything, instantly. *Does **not** bound:* the interval before a human looks —
which is why L9 is the floor under the layered recommendation and never the whole of it.

Shipped as `scripts/deploy/kill_switch.sh` and `kill_switch.ps1` (§7).

**This is documented AWS behaviour, not measured on this account, and it ships labelled that
way** — measuring it requires a mutating call against a function that does not yet exist, and
this wave makes no mutating calls.

---

## 4 · The budgets, measured — and moving while I wrote this

```
aws budgets describe-budgets --account-id <masked> --region us-east-1
```

| Budget | Limit | Actual | Forecast |
|---|---|---|---|
| My Monthly Cost Budget | $10.00 | **$13.129** | $33.078 |
| My Monthly Cost Budget - $5 limit | $5.00 | **$13.129** | $33.078 |
| My Zero-Spend Budget | $1.00 | **$13.129** | $33.078 |

The lead measured `actual 12.686 / forecast 33.028` earlier the same day. **Six hours later
it is 13.129 / 33.078.** The spend is live and climbing from unrelated projects; the founder's
card is running **~3× its own budget before this project emits a single byte.**

And the part that matters:

```
aws budgets describe-budget-actions-for-budget --budget-name "My Monthly Cost Budget"
  { "Actions": [] }
aws budgets describe-budget-actions-for-budget --budget-name "My Monthly Cost Budget - $5 limit"
  { "Actions": [] }
aws budgets describe-budget-actions-for-budget --budget-name "My Zero-Spend Budget"
  { "Actions": [] }
```

**Three budgets. All three breached. Zero actions on any of them.** They send email. They stop
nothing. A budget with no action is a notification, and calling it a spend control is the
same category error as L7.

---

## 5 · What bounds the demo today

**This table is superseded. It is kept because the finding it records — "one real bound, and
it is an AWS default nobody chose" — is what caused everything above, and deleting it would
erase why any of this exists.** The live table is immediately below it.

| Claimed bound | Real? *(as of 2026-08-13, superseded)* | What it actually bounds |
|---|---|---|
| `reserved_concurrent_executions = 20` | **NO** — unappliable | nothing; the apply dies on it |
| Account ceiling of 10 | **YES** — and it is the only one | concurrency → rate → ≈ everything |
| `-concurrency` alarm at 20 | **NO** — threshold above a ceiling of 10 | nothing; it can never fire |
| CockroachDB Basic $25 cap | **YES**, but irrelevant | the database, which the flood never touches (§2.5) |
| The handler's rolled-back transaction | **YES** | database *state*, not spend |
| AWS Budgets ×3 | **NO** — no actions, already breached | nothing |

~~**One real bound, and it is an AWS default nobody chose.**~~ **No longer true.** Three code
bounds have landed since, and the reason the sentence survived so long is that all three
were *coded and not instantiated*, which on a plan output looks identical to absent. **They
are instantiated now** (§0.2); the sentence is kept struck through rather than removed
because the reason it survived is the finding.

### 5.1 · What bounds it now — live, 2026-08-14

| Bound | Real? | In force where | What it bounds |
|---|---|---|---|
| Account ceiling of 10 | **YES** | AWS account default, quota `L-B99A9384` | concurrency → request rate → everything |
| `DEFAULT_MAX_RESPONSE_BYTES = 139,264` | **YES** | `static_site.py`, code default | bytes per response, **and it binds** — ~~derived from the **deployed** tree, asserted against it~~ **CORRECTED 2026-08-15 (R10, §0.5): CHOSEN by the derivation over the 2026-08-14 tree; asserted today by the straddle, interface I3 and exactly-one-refusal** (`docs/decisions/response-ceiling-authoritative-tree.md` §1) |
| `ratelimit` global/per-IP token buckets | **YES, partially** | `app.py`, first statement of the handler | egress from a paced caller; **not** the invocation charge, and the counter is per execution environment |
| Source maps stripped | **YES** | both builders, default | the largest object that can exist, not the rate |
| `-invocations-burst` / `-hourly` / `-log-ingestion` alarms → SNS → `PutFunctionConcurrency(0)` | **BUILT _AND INSTANTIATED_** — *in plan; nothing is applied* | `infra/modules/cost-guard/`, instantiated at `infra/envs/demo/main.tf:631` under `count = var.enable_api ? 1 : 0` | the flood, from the moment the stop lands — worth **$8.01 per 5 min window** it does not land in (§0.1 R4–R6). This row read **BUILT, NOT INSTANTIATED** until 2026-08-14 and was false; §0.2 has the plan evidence |
| the demo function's own four alarms → the same stop topic | **YES in plan, and _unsettled_ in fact** | `alarm_actions = local.guard_stop_topic_actions`, `infra/envs/demo/main.tf:586` | possibly nothing: the guard's topic policy names only its **own three** alarm ARNs, and no plan can decide whether these four may publish (§0.2). Recorded, not assumed |
| `scripts/deploy/kill_switch.{sh,ps1}` | **YES**, manual | committed, never run in mutating mode | everything, from the moment a human runs it |
| AWS Budgets ×3 | **NO** — no actions, already breached | | nothing |
| CockroachDB Basic $25 cap | **YES**, but irrelevant | | the database, which the flood never touches (§2.5) |

**The finding has moved up one level twice, and the second move closed it.** It was
*documented and not implemented*; it became *implemented and not instantiated*, which a
reviewer reading `terraform plan` cannot tell apart from absent; it is now **instantiated,
and the plan says so** — `Plan: 24 to add, 0 to change, 0 to destroy.` at line 843 of
`evidence/deploy/terraform-plan-furl.txt`, up from 11. What is left is not a gap between the
code and the plan but a gap between the plan and reality: **nothing has been applied**, and
one consequence of the wiring (§0.2, the topic-policy question) cannot be settled until
something is.

---

## 6 · Recommendation

### Layer 1 — take now. Zero friction, zero dollars, no decision required.

* **L1** `reserved_concurrent_executions = -1`. Mandatory; the apply cannot run otherwise.
* **L3** response cap at ~~**512 KiB**~~ **139,264 B (136 KiB) — SHIPPED at that value**.
  ~~Rejects exactly one file in the package (§3.3)~~ — that was one file of the packer's
  **INPUT** tree, and the same 512 KiB line refuses **zero** of the 114 entries the
  **deployed** package holds. The value in force was ~~**derived from the deployed tree**~~
  **CORRECTED 2026-08-15 (R10, §0.5): CHOSEN by the derivation over the 2026-08-14 tree and
  KEPT by interface I3 over the tree of record**
  (§3.3, `docs/decisions/response-ceiling-authoritative-tree.md` §2.1) and it does
  make the bytes/request number a **ratchet** instead of a coincidence — which is the half of
  this recommendation that was right.
* **L2** strip source maps as the build default.
* Concurrency alarm at **8**, under the real ceiling, with a reader that exists.

**Worst case falls $33,250 → ≈ $9,900**, and L3 is what keeps it there.

### Layer 2 — recommended. One decision.

* **L5**, the shared-secret gate. **≈ $9,900 → ≈ $230** for the cost of one query parameter
  in the submission form.

It is obscurity, not authentication, and §3.5 says so — but the realistic threat is an
opportunistic scanner sweeping `on.aws`, and obscurity is a complete answer to a scanner.
Worth taking on those terms and no others.

### Layer 3 — arm the floor.

* **L9** as a one-command script, ready before the apply, not written during the incident.
* ~~**L6** default-off (`count = 0`), so the founder can enable it *knowing its 8–24 h lag*.~~
  **Superseded — it ships ON.** `module "guard"` is instantiated at
  `infra/envs/demo/main.tf:631` (§0.2), and the recommendation the founder is actually being
  asked to accept is therefore row **T** of §0.1: the stop is armed, and **anyone at all can
  trip it**.

### Reject

* **L8** — bounds everything and 403s the judges; CloudFront, the only fix, is refused here.
* **L7 as a cost control** — 0.28 % of the bill. Keep the ~~15 s~~ **14 s** timeout for its
  real reason: it is a **reliability** bound on one hung invocation, and at 3 s it would
  truncate the headline gate-run beat at 0.80× its measured p99 (§3.7).
  *(`memory_size` 512 → 256 MB is a separate matter and is **already shipped** —
  `evidence/deploy/terraform-plan-furl.txt:290`, §0.1 row L4. Rejecting L7 rejects the
  **claim that it is a cost control**, not the change.)*

### Residual after Layers 1–3

**≈ $230 / 30 d against a single source**, of which **$225 is Lambda invocation charges that
no body-size lever can touch** (§3.4). A distributed flood still reaches ≈ $9,900, bounded by
L3. Below that lies only L9, run by a human who is looking.

---

## 7 · The quota — read this before anyone opens a support case

```
L-B99A9384  "Concurrent executions"  Value 10.0  Adjustable: true
```

**Every dollar in this document scales with that number**, and very nearly linearly — the
egress tiers make it *slightly sub*-linear, because more of the volume lands in the $0.08
band. Computed, not extrapolated:

| Concurrency quota | Worst case / 30 d | vs. today |
|---|---|---|
| **10** (today) | **$33,252** | ×1.00 |
| 100 | $325,319 | ×9.78 |
| 1,000 — AWS's usual default, and the number `infra/modules/demo-api/variables.tf:388` wrongly claims this account has | **$3,245,987** | ×97.62 |

That last row is why the false sentence in `variables.tf` matters beyond tidiness: it
describes an account on which this demo's worst case is **three and a quarter million
dollars**.

The ceiling of 10 is not a limitation to be worked around. **It is the only thing standing
between this demo and a six- or seven-figure bill, and it got there by accident.**

> **DO NOT REQUEST A CONCURRENCY INCREASE ON THIS ACCOUNT.**
> Not for the demo, not for load testing, not "temporarily for judging". If a future
> change appears to need one, that change is wrong. Re-read §2 first.

---

## 8 · The kill switch

```bash
scripts/deploy/kill_switch.sh --dry-run                          # prints both calls, makes none
scripts/deploy/kill_switch.sh --status                           # read-only
scripts/deploy/kill_switch.sh --stop    --expect-account <id> --yes
scripts/deploy/kill_switch.sh --restore --expect-account <id> --yes
```

```powershell
scripts/deploy/kill_switch.ps1 -DryRun
scripts/deploy/kill_switch.ps1 -Status
scripts/deploy/kill_switch.ps1 -Stop    -ExpectAccount <id> -Yes
scripts/deploy/kill_switch.ps1 -Restore -ExpectAccount <id> -Yes
```

`--stop` sets reserved concurrency to **0**; `--restore` returns the function to
**unreserved**, which is what Terraform's `-1` means and is L1's value.

**The two directions are not the same API.** `-1` is a Terraform sentinel, not an API value:
`PutFunctionConcurrency` has a minimum of 0 and rejects -1. Removing a reservation is
`DeleteFunctionConcurrency`.

```
--stop     ->  aws lambda put-function-concurrency --reserved-concurrent-executions 0
--restore  ->  aws lambda delete-function-concurrency
```

A script that tried to restore by putting -1 would fail precisely when it was needed, so
both files say this at the top of themselves.

Both refuse without an explicit account assertion, in the same shape as `teardown.sh`
(decision D2 — no account id is written in either file). They go further than `teardown.sh`
in one respect: **they never print a raw account id either**, masking it first-four /
last-four, because their output is the kind that gets pasted into an incident thread.
`--dry-run` prints the exact API calls and makes none. Both verify by **re-reading the
reservation from AWS** rather than trusting the mutating call's exit code.

**Neither script has been run in mutating mode.** The function does not exist yet; there is
nothing to stop. They exist so that the first time anyone needs them is not also the first
time anyone writes them.

---

## 9 · What this document does not claim

* **L8 and L9 are documented AWS behaviour, not measured here.** Both require mutating calls
  against a function that does not exist. They ship labelled.
* **The $230 floor assumes the attacker keeps invoking after being rejected.** A rational one
  stops, and the real number is lower. The floor is the worst case, not the expectation.
* ~~**100 ms is an estimate.**~~ **Closed, and it was the largest error in this document.**
  `docs/deploy/LATENCY.md` measured every beat over a real socket: the static beats run at
  **5.66 / 14.11 ms** p50, not 100 ms. Because egress and requests scale as 1/duration, the
  headline was a **floor understated about 7×**. §0.1 carries the corrected ladder. The
  measurement is workstation-loopback and the cloud column runs up to 2.2× slower, which
  moves the bill *down*; the local figure is headlined because it is the conservative one.
* **The GB convention is unresolved to ±7 %** (§1.2), and the conservative side is headlined.
  It is now an **explicit input** with three named readings rather than an assumption —
  `scripts/deploy/cost_model.py` reproduces all three to their published precision, which is
  how the 0.06 % disagreement between this document and the lead's independent run was
  resolved: it was never floating-point tolerance, it was the tier-boundary choice.
* **The sustained egress rate in §0.1 is unobserved.** 1.1 GB/s out of ten 512 MB execution
  environments is what the tariff and the concurrency ceiling *permit*. Settling it needs one
  load test against a deployed function, which needs an apply, which no wave here performs.
  Every §0.1 figure is a **model bound** and is labelled so in the JSON payload itself.
* **Nothing here has been applied.** Every figure describes an exposure that does not exist
  yet, which is the only useful moment to read it.
