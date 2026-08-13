<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
-->

# COST-BOUND — what the demo can cost, what actually bounds it, and the one command that stops it

**Owner:** W6 (deploy-safety) · **Measured:** 2026-08-13, this machine, `AWS_PROFILE=mainline-dev`
**Status:** decision material. Nothing in this document has been applied. No `terraform apply`
was run to produce it, and no mutating AWS call was made.

---

## 0 · The answer in five lines

The demo's origin is a Lambda Function URL with `authorization_type = NONE`. Its largest
single response is a **1,554,168-byte source map**. The account can run **10** concurrent
executions. Multiply those three facts by 30 days and the worst case is

> **USD 11,700 – 33,250** for one month of sustained abuse — against a card whose three
> budgets are set at $10, $5 and $1 and are **already breached** by unrelated projects.

Exactly **one** real bound exists today, and it is an AWS account default nobody chose. Every
other control that looks like a bound — the reserved concurrency, the abuse alarm, the AWS
Budgets — bounds nothing. §3 is the menu of levers that would change that; §6 is the
recommendation.

---

## 1 · The measured inputs

Every row is a command I ran today, not a figure inherited from a board or an audit.

| # | Input | Measured value | How |
|---|---|---|---|
| I1 | Account concurrency ceiling, `ap-southeast-1` | **10** (`ConcurrentExecutions`, `UnreservedConcurrentExecutions`) | `aws lambda get-account-settings --region ap-southeast-1` |
| I2 | Same, `ap-southeast-2` | **10**, `FunctionCount 1` (an unrelated live project — do not touch) | `aws lambda get-account-settings --region ap-southeast-2` |
| I3 | The quota behind I1 | `L-B99A9384` "Concurrent executions" = **10.0**, **`Adjustable: true`** | `aws service-quotas get-service-quota --service-code lambda --quota-code L-B99A9384` |
| I4 | Largest response the origin can emit | **1,554,168 B** — `web/assets/index-BjAGxrVJ.js.map` | `zipfile` over `out/lambda/mainline-demo-api-arm64.zip` |
| I5 | Largest **non-map** asset | **433,396 B** — `web/assets/index-BjAGxrVJ.js` | same |
| I6 | Whole served tree | **3,571,990 B** over **75** files under `web/` | same |
| I7 | …of which source maps | **2,586,960 B** over **18** files = **72.4235 %** | same |
| I8 | Function URL auth | `NONE` | `evidence/deploy/terraform-plan-furl.txt:329` |
| I9 | Function shape | `mainline-demo-api`, arm64, `memory_size = 512`, `timeout = 15`, `reserved_concurrent_executions = 20` | `evidence/deploy/terraform-plan-furl.txt:264-301` |

Two facts from I4–I7 that decide most of this document:

* `web/` is the **only** servable tree in the package (the other top-level entries are
  `mainline_demo_api/`, `psycopg/`, `psycopg_binary/` and their dist-infos — code, not
  routes). So the flood target is fully enumerated above.
* **Exactly one file in the entire package is ≥ 512 KiB, and it is a source map.** Every
  non-map asset is ≤ 433,396 B. That single fact is what makes L3 cost-free (§3.3).

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
| **L7** | Timeout 15→5 s, memory 512→256 MB | $33,165 | **0.28 %** of the bill | 99.7 % of it | worse cold starts | 0 |
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

Already implemented as `--strip-source-maps` in `scripts/deploy/build_lambda.sh`
(lines 105, 122, 537, 583, 830) and `-StripSourceMaps` in the `.ps1`. It records
`source_maps: kept|stripped` in the manifest. **It is off by default, on purpose** — the
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

If taken, it ships `count = 0` by default so the plan stays at 11 resources.

### 3.7 · L7 — reducing memory and timeout is **not** a cost control

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
15 s timeout for the pgwire round trip it exists for.**

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

| Claimed bound | Real? | What it actually bounds |
|---|---|---|
| `reserved_concurrent_executions = 20` | **NO** — unappliable | nothing; the apply dies on it |
| Account ceiling of 10 | **YES** — and it is the only one | concurrency → rate → ≈ everything |
| `-concurrency` alarm at 20 | **NO** — threshold above a ceiling of 10 | nothing; it can never fire |
| CockroachDB Basic $25 cap | **YES**, but irrelevant | the database, which the flood never touches (§2.5) |
| The handler's rolled-back transaction | **YES** | database *state*, not spend |
| AWS Budgets ×3 | **NO** — no actions, already breached | nothing |

**One real bound, and it is an AWS default nobody chose.** That is the finding.

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
* **L6** default-off (`count = 0`), so the founder can enable it *knowing its 8–24 h lag*.

### Reject

* **L8** — bounds everything and 403s the judges; CloudFront, the only fix, is refused here.
* **L7 as a cost control** — 0.28 % of the bill. Keep the 15 s timeout for its real reason.

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
* **100 ms is an estimate.** It is the fast end of a static-asset read from a warm arm64
  Lambda serving from its own package. Measured invocation timings would sharpen the range,
  and cannot be taken without deploying.
* **The GB convention is unresolved to ±7 %** (§1.2), and the conservative side is headlined.
* **Nothing here has been applied.** Every figure describes an exposure that does not exist
  yet, which is the only useful moment to read it.
