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
> place, never removed** (**§1**, §3.2, §3.3, §3.6, **§3.7**, §5, §5.1, §6, §9). A claim
> deleted is not a claim corrected, and the corrections are only checkable against the claims
> they correct. *(§1 and §3.7 were added to this list on 2026-08-14. §1 was annotated in the
> same wave; its omission here is exactly why §1 read as current when it is historical, and an
> enumeration that does not enumerate is the same defect one level up.)*
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
| response ceiling | 2 MiB, above everything it governed | **139,264 B**, derived from the tree and binding |
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
environments**. **Nobody has observed that**, here or anywhere in this repository's evidence.
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

* **The response ceiling is a code constant.** `static_site.DEFAULT_MAX_RESPONSE_BYTES` is
  **139,264 B** today and is read at model time, not copied. Raise it above 433,396 B and the
  reachable residual is **3.5×** larger (R1 → R3′) and the in-window rate moves with it
  ($1.6022 → $5.5364 per minute). Both cases are published for exactly that reason.
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
  **139,264 B**, derived from the deployed tree rather than chosen, and it refuses even the
  433,396 B identity bundle. A ceiling above everything it governs is a decoration, not a
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

### 2.1 · The model

The attacker holds concurrency at the ceiling and fetches the largest asset every time.
No credential, no rate limit, no CAPTCHA — the URL is `authorization_type = NONE`.

```
concurrency               10                      (I1, and it is a hard ceiling)
invocation duration       100 ms … 300 ms         (the span of a static-asset read)
request rate              10 / 0.100 = 100 rps  …  10 / 0.300 = 33.3 rps
bytes per request         1,554,168 B             (I4)
window                    30 d = 2,592,000 s
```

100 rps × 1,554,168 B × 2,592,000 s = **402.84 TB** (decimal) / **375,174 GiB** (measured tariff)

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

* Largest emittable response: **1,554,168 → 433,396 B**, a factor of **3.586**.
* Package: −2,586,960 B (72.4 % of the served tree).
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
> is now **derived from the deployed tree** rather than chosen, and it binds: it refuses the
> 433,396 B identity bundle, which every real browser avoids by sending
> `Accept-Encoding: gzip` and receiving the 124,127 B sibling instead. That consequence is
> deliberate and is stated loudly in `static_site.py` rather than avoided by picking a
> looser number.

**At 512 KiB = 524,288 B this costs literally nothing**, and I5/I6 are why:

```
largest non-map asset           433,396 B
proposed cap                    524,288 B
headroom                         90,892 B
assets in the package >= cap            1   ← and it is a source map
```

So a 512 KiB cap **rejects exactly one file in the entire package**, and that file is the one
L2 removes anyway. Every legitimate asset passes untouched. Judge friction: **none**.

*Bounds:* bytes per request — **and ratchets it**, so the number can never silently grow when
someone adds an asset. *Does **not** bound:* the request rate. An attacker still gets
433,396 B per request, so L3-at-512-KiB and L2 have the **same** worst case; they differ in
that L3 is a guarantee and L2 is a build-time coincidence. **Take both.**

### 3.4 · L4 — per-IP throttle

A 429 body is ~200 B against 1,554,168 B, a **7,000×** collapse in egress from a single
source. Worst case ≈ **$230**.

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
| `DEFAULT_MAX_RESPONSE_BYTES = 139,264` | **YES** | `static_site.py`, code default | bytes per response, **and it binds** — derived from the tree, asserted against it |
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
* **L3** response cap at **512 KiB**. Rejects exactly one file in the package (§3.3) and
  makes the bytes/request number a **ratchet** instead of a coincidence.
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
