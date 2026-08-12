<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
-->

# W4 — Cost, quotas, and the economics of abuse

**Worker:** W4. **Plan:** [`docs/leads/deploy-verify-plan2.md`](../../leads/deploy-verify-plan2.md).
**Date:** 2026-08-12. **Account:** `0229REDACTED8246`, profile `mainline-dev`.
**Evidence:** [`evidence/deploy/verify/aws-quota-and-cost.json`](../../../evidence/deploy/verify/aws-quota-and-cost.json).

No `terraform` command of any kind was run. No AWS write of any kind was run. The Cloud
cluster was not contacted. Every AWS number below came from a read-only API call made
today; every price came from the AWS Price List API or a dated fetch of a published page.

---

## 0 · The three sentences

1. **The apply fails, but not where the lead thought.** `CreateFunction` has no
   `ReservedConcurrentExecutions` parameter, so the function is created *successfully* and
   the failure lands one API call later, on `PutFunctionConcurrency`. Five of eleven
   resources exist afterwards — including the Lambda function itself, tainted in state.
2. **The fix is one line and it costs nothing.** `reserved_concurrent_executions = -1`.
   The reservation of 20 was never buying anything on this account: the account quota of
   **10** is already tighter than it. Requesting a quota increase would make the exposure
   *worse*, not better.
3. **"~USD 0.02/month, worst case under USD 1.00" is wrong about the worst case by four
   orders of magnitude.** A sustained abusive caller at the account ceiling costs
   **USD 168** in 30 days on the gate-run path, and **USD 11,800 – 33,500** on the path
   the abuser would actually choose. Nothing in the plan bounds the second number.

---

## 1 · THE BLOCKER, reproduced

### 1.1 The readings

```
$ aws lambda get-account-settings --region ap-southeast-1 --profile mainline-dev
  AccountLimit.ConcurrentExecutions           = 10
  AccountLimit.UnreservedConcurrentExecutions = 10
  AccountUsage.FunctionCount                  = 0

$ aws lambda get-account-settings --region ap-southeast-2 --profile mainline-dev
  AccountLimit.ConcurrentExecutions           = 10
  AccountLimit.UnreservedConcurrentExecutions = 10
  AccountUsage.FunctionCount                  = 1        <-- not 0

$ aws service-quotas get-service-quota --service-code lambda --quota-code L-B99A9384 \
      --region ap-southeast-1 --profile mainline-dev
  QuotaName "Concurrent executions"   Value 10.0
  Unit Count   Adjustable true   GlobalQuota false   QuotaAppliedAtLevel ACCOUNT
```

`ap-southeast-2` reports the identical pair. Both of the lead's readings reproduce exactly.

Two things the lead did not record, both read today:

| Reading | Command | Value |
|---|---|---|
| AWS's default for this quota | `get-aws-default-service-quota` | **1000.0** — this account is suppressed to 1 % of default |
| Increase requests ever filed | `list-requested-service-quota-change-history-by-quota` | **`RequestedQuotas: []`** — never requested |
| Functions in `ap-southeast-2` | `list-functions` | one, `cci-chage-enricher` (python3.12, 128 MB), unrelated to MAINLINE |

The deploy region `ap-southeast-1` genuinely holds zero functions, so the lead's
"no name collision" finding stands. The `FunctionCount = 0` claim is region-specific and
should be written as such.

### 1.2 What the committed plan asks for

From `evidence/deploy/terraform-plan-furl.json`, `module.api[0].aws_lambda_function.this`:

```
reserved_concurrent_executions = 20
memory_size = 512      timeout = 15      architectures = ["arm64"]      runtime = python3.13
logging_config = { log_format = "JSON", application_log_level = "INFO",
                   system_log_level = "WARN", log_group = "/aws/lambda/mainline-demo-api" }
```

The root does **not** set the input. It inherits the module default of `20`
(`infra/modules/demo-api/variables.tf:386`).

### 1.3 The documented rule

> "You can reserve up to the **Unreserved account concurrency** value minus 100. The
> remaining 100 units of concurrency are for functions that aren't using reserved
> concurrency."
> — [Configuring reserved concurrency for a function](https://docs.aws.amazon.com/lambda/latest/dg/configuration-concurrency.html), fetched 2026-08-12

> "You can reserve concurrency for as many functions as you like, as long as you leave at
> least 100 simultaneous executions unreserved for functions that aren't configured with a
> per-function limit."
> — [PutFunctionConcurrency API reference](https://docs.aws.amazon.com/lambda/latest/api/API_PutFunctionConcurrency.html), fetched 2026-08-12

**The documented minimum unreserved concurrency is 100.** On this account:
`10 − 100 = −90`. **No positive reservation is satisfiable.** Field reports from accounts
whose ceiling is 10 show AWS reporting the floor as `[10]` rather than `[100]`; the two
readings give the same answer here, because on this account the ceiling *is* the floor.

### 1.4 The correction: `CreateFunction` succeeds

> The lead wrote: *"The expected outcome of the authorised apply is a failed
> `CreateFunction`, after the log group, role, policy and attachment have already been
> created."*

That is wrong in a way that changes the blast radius. The
[CreateFunction API reference](https://docs.aws.amazon.com/lambda/latest/api/API_CreateFunction.html)
lists the request body in full and **`ReservedConcurrentExecutions` is not in it**. The
same page says so explicitly:

> "Function-level settings apply to both the unpublished and published versions of the
> function, and include tags (`TagResource`) and per-function concurrency limits
> (`PutFunctionConcurrency`)."

The `hashicorp/aws` provider therefore issues `CreateFunction`, waits for the function to
become `Active`, and *then* issues a separate `PutFunctionConcurrency`. Verified against
the exact provider build that would run this apply — the one already downloaded into
`infra/envs/demo/.terraform/` — by counting byte strings in the binary:

```
terraform-provider-aws_v6.58.0_x5.exe   (906,479,752 bytes)
  b'PutFunctionConcurrency'                    32 occurrences
  b'setting Lambda Function (%s) concurrency'   1 occurrence   <-- the post-create error wrapper
  b'reserved_concurrent_executions'             1 occurrence
```

### 1.5 The expected error, and where the apply breaks

**Error class:** `InvalidParameterValueException`, **HTTP 400**, from
**`PutFunctionConcurrency`** (not `CreateFunction`).

**Expected message shape:**

```
Error: setting Lambda Function (mainline-demo-api) concurrency: operation error Lambda:
PutFunctionConcurrency, https response error StatusCode: 400, RequestID: <uuid>,
InvalidParameterValueException: Specified ReservedConcurrentExecutions for function
decreases account's UnreservedConcurrentExecution below its minimum value of [10].
```

**The resource at which the apply breaks:** `module.api[0].aws_lambda_function.this`.

Dependency order read from `infra/modules/demo-api/main.tf`:

| # | Resource | Created? | Why |
|---|---|---|---|
| 1 | `aws_iam_role.this` | **yes** | no dependency |
| 2 | `aws_iam_role_policy.dsn_access` | **yes** | `role = aws_iam_role.this.id` (`:232`) |
| 3 | `aws_iam_role_policy_attachment.basic_execution` | **yes** | `role = aws_iam_role.this.name` (`:184`) |
| 4 | `aws_cloudwatch_log_group.this` | **yes** | no dependency |
| 5 | `aws_lambda_function.this` | **yes, then tainted** | `CreateFunction` → 201. `d.SetId()` runs *before* `PutFunctionConcurrency`, so the function exists in AWS **and** is written to state, marked tainted |
| 6 | `aws_lambda_function_url.this` | no | `function_name = aws_lambda_function.this.function_name` (`:304`) |
| 7–10 | the four `aws_cloudwatch_metric_alarm`s | no | `dimensions = { FunctionName = aws_lambda_function.this.function_name }` (`:389, :414, :437, :477`) |
| 11 | `aws_cloudwatch_dashboard.this[0]` | no | its `alarm` widget lists all four alarm ARNs (`:598–603`) |

**Five of eleven resources exist after the failure. Six do not.** The dashboard is *not*
independent — the alarm widget makes it depend transitively on the function.

One mercy: because `aws_lambda_function_url.this` is not created, the partial apply leaves
**nothing publicly reachable**. It is a mess to clean up, not an exposure. A second `apply`
after the fix will destroy and recreate the tainted function; nothing needs manual repair.

### 1.6 The fix — three candidates, one answer

| Option | Works? | Verdict |
|---|---|---|
| `reserved_concurrent_executions = -1` | yes | **RECOMMENDED** |
| a smaller positive reservation (5, 2, 1) | **no** | `10 − 100 = −90`; every positive value fails the same check. `0` passes the API but, in the module's own words, *"0 disables the function entirely"* |
| a quota increase on `L-B99A9384` | yes | **refuse for this deploy** — see below |

**Why the quota increase is the wrong answer.** It is `Adjustable: true` and has never been
requested, so it means a support round trip of unknown duration against a submission
deadline. Worse, it is the only option that *raises* the maximum bill. Today the account
ceiling of 10 is what actually caps compute; raise it to the AWS default of 1000 and the
reservation of 20 finally takes effect, doubling the sustained-abuse compute ceiling from
10 to 20 concurrent — **USD 167.47 → USD 334.94 per 30 days**, and the egress worst case
doubles with it. Asking AWS for more room is asking for a bigger blast radius.

**Why `-1` costs nothing.** The effective concurrency ceiling is
`min(reservation, account quota)`. With `20` it would be `min(20, 10) = 10`. With `-1` the
function draws from the account's 10 unreserved executions and the ceiling is `10`.
`ap-southeast-1` holds **zero** other functions, so nothing competes for the pool.
**The cost ceiling is identical either way — the reservation was never buying anything on
this account.**

**What the founder gives up.** The module documents the consequence honestly
(`variables.tf:381–383`, `README.md:653–657`): Lambda emits per-function
`ConcurrentExecutions` dependably for functions that *have* reserved concurrency, so with
`-1` the `-concurrency` alarm can sit in `INSUFFICIENT_DATA`. But that alarm is **already**
dead for an independent reason — its threshold is `> 20` against a metric that on this
account can never exceed `10`. Setting `-1` does not kill a working tripwire; it converts
an alarm that could never fire into an alarm with no data. Nothing real is lost.
`Throttles` is still emitted, and with the function unreserved it now throttles at the
account ceiling of 10 — so the *throttle* tripwire survives and is the one that matters.
(Repairing the concurrency alarm is W5's file; the honest repair is a threshold below 10.)

**The exact minimal edit** — one line, in the root, not the module:

```hcl
# infra/envs/demo/main.tf, inside module "api" (block begins at line 280)
  reserved_concurrent_executions = -1
```

Do **not** change the module default; that changes behaviour for every consumer.

### 1.7 A module claim this falsifies

`infra/modules/demo-api/variables.tf:378–379`:

> "It reserves 20 of the account's 1 000 unreserved executions, which the four unrelated
> projects in this account share; 2 % is the price of a demo that cannot be turned into a
> bill."

The account has **10** unreserved executions, not 1 000. The reservation is not 2 % of the
account — it is 200 % of it. The repository is public and this sentence is checkable by a
stranger with the AWS CLI.

---

## 2 · THE COST

### 2.1 Prices, with provenance

Queried today, **2026-08-12**, from the **AWS Price List API** (read-only) with
`--filters Type=TERM_MATCH,Field=regionCode,Value=ap-southeast-1`. The Price List API is
the publisher's own feed; it is preferred here over the marketing pages.

| Line | Usage type | Price (USD) |
|---|---|---|
| Lambda **arm64** compute, tier 1 (0 → 7.5 × 10⁹ GB-s) | `APS1-Lambda-GB-Second-ARM` | **0.0000133334** / GB-s |
| Lambda **arm64** requests | `APS1-Request-ARM` | **0.0000002** / request |
| *(x86 compute, for reference)* | `APS1-Lambda-GB-Second` | 0.0000166667 / GB-s |
| CloudWatch standard-resolution alarm | `APS1-CW:AlarmMonitorUsage` | **0.10** / alarm-month |
| CloudWatch Logs ingest, custom, Standard class | `APS1-DataProcessing-Bytes` | **0.70** / GB |
| CloudWatch Logs storage | `APS1-TimedStorage-ByteHrs` | **0.03** / GB-Mo |
| CloudWatch Logs Insights scan | `APS1-DataScanned-Bytes` | 0.007 / GB |
| Data transfer out to internet — first 10 TB | `APS1-DataTransfer-Out-Bytes` | **0.120** / GB |
| — next 40 TB | | 0.085 / GB |
| — next 100 TB | | 0.082 / GB |
| — beyond 150 TB | | 0.080 / GB |
| CloudWatch dashboard beyond the first 3 | *(not exposed by the API)* | **3.00** / dashboard-month |

Free-tier counts, from [aws.amazon.com/cloudwatch/pricing](https://aws.amazon.com/cloudwatch/pricing/)
(fetched 2026-08-12): **10** standard-resolution alarm metrics, **3** custom dashboards
(≤ 50 metrics each), **5 GB** of Logs covering ingestion, archive storage and Insights
scan. Data-transfer-out carries a **100 GB/month** global free allowance.

`ap-southeast-1` today holds **0 alarms, 0 dashboards, 0 `/aws/lambda` log groups**
(all three counted with `describe-alarms` / `list-dashboards` / `describe-log-groups`), so
the plan's 4 alarms and 1 dashboard land entirely inside the free counts. **USD 0.00.**

### 2.2 Does the free tier still apply to this account in 2026? Measured.

```
$ aws freetier get-account-plan-state --region us-east-1 --profile mainline-dev
  accountPlanType             = PAID
  accountPlanStatus           = ACTIVE
  accountPlanRemainingCredits = USD 0.00
```

The account is on the post-2025-07-15 **paid** plan with **zero remaining credits** — the
signup credits are gone, which is consistent with USD 12.41 of actual spend.

```
$ aws freetier get-free-tier-usage --region us-east-1 --profile mainline-dev
  AmazonCloudWatch  CW:Requests           limit 1,000,000 Requests  Always Free
  AmazonCloudWatch  DataProcessing-Bytes  limit 5.0 GB              Always Free
  AmazonCloudWatch  TimedStorage-ByteHrs  limit 5.0 GB-Mo           Always Free
  AWS Glue          Catalog-Request       limit 1,000,000           Always Free
  AWS KMS           KMS-Requests          limit 20,000              Always Free
```

**CloudWatch's always-free tier is confirmed live on this account today.** Lambda's is
**not** — but only because the API reports free-tier rows for services with usage this
month, and the account has had zero Lambda invocations anywhere this month. Absence is not
evidence of loss. AWS's Free Tier FAQ (fetched 2026-08-12) is explicit that paid-plan
accounts keep always-free offers: *"you will have access to all always free services and
short-term trials. Always free services allow you to use the product for free up to
specified limits as long as you are an AWS customer."* The Lambda pricing page states
*"The free tier includes one million requests and 400,000 GB-seconds per month."*

**It does not matter to any conclusion here.** Against the sustained-abuse figure, the
Lambda free tier is worth **USD 5.53**. Every number below is given with and without it.

### 2.3 The measured inputs

| Input | Value | Source |
|---|---|---|
| One `POST /v1/demo/gate-run` response | **9,576 bytes**, HTTP 200 | `evidence/deploy/acceptance.json` → `corroborating_run.checks.gate_runs[0]`, 2026-08-11 |
| Its wall time | **10,642.9 ms** (beats: 0.011 / 2,141.6 / 2,384.6 ms) | same |
| Handler log call sites in the whole package | **2** — `app.py:376` (`warning`), `app.py:384` (`exception`) | both on the failure path; a *successful* request emits nothing from the handler |
| Largest anonymously servable asset | **1,554,168 bytes** — `dist/assets/index-BjAGxrVJ.js.map` | `static_site.py:157` maps `.map` explicitly to `application/json`; well inside the 6 MB BUFFERED response limit |

**One honest caveat on the 10.6 s.** That run was made from a developer machine in
Australia against the Cloud cluster in `ap-southeast-1`. In-region — Lambda beside the
cluster — the wall time will be lower, and it is **unmeasured**, because no function is
deployed. Using 10.6 s is the conservative choice for a cost ceiling. It also means the
plan's own basis line, *"512 MB × 300 ms × 10 k req = 1 536 GB-s"*
(`docs/deploy/terraform-plan.md:265`), is **35× optimistic** on duration.

### 2.4 Scenario A — a judging session

Ten judges, each: 30 static/SPA requests at 0.12 s, 6 `/v1/*` reads at 0.4 s, 2 gate runs
at 10.6 s.

```
per judge : 30(0.12) + 6(0.4) + 2(10.6) = 27.2 s  ×  0.5 GB = 13.6 GB-s   (38 requests)
10 judges :                                        136 GB-s              (380 requests)

compute  : 136 × 0.0000133334               = USD 0.0018
requests : 380 × 0.0000002                  = USD 0.000076
egress   : ~40 MB                            inside the 100 GB free allowance
logs     : 380 × ~1.5 KB = 0.57 MB           inside the 5 GB free ingest (confirmed active)
```

**Total: USD 0.00 with the free tier; USD 0.0019 without any free tier at all.**

### 2.5 Scenario B — the `demo-health` hourly cron, 30 days

24 gate runs/day × 30 days = 720 gate runs, plus 720 `GET /v1/health`.

```
720 × 10.6 s × 0.5 GB = 3,816 GB-s
720 ×  0.4 s × 0.5 GB =   144 GB-s
                        ───────────
                        3,960 GB-s   over 1,440 requests

compute  : 3,960 × 0.0000133334 = USD 0.0528
requests : 1,440 × 0.0000002    = USD 0.000288
egress   : 720 × 9,576 B = 6.9 MB   free
logs     : 1,440 × ~1.5 KB = 2.2 MB free
```

**Total: USD 0.00 with the Lambda free tier (3,960 GB-s against 400,000 free);
USD 0.053/month with none.**

The conclusion — the cron is free — survives. The stated arithmetic does not.

### 2.6 Scenario C1 — SUSTAINED ABUSE at the account ceiling (the brief's shape)

Ten concurrent invocations — the account ceiling — of 15 s at 512 MB, for 30 days.

```
seconds in 30 days     = 2,592,000
concurrent-seconds     = 10 × 2,592,000       = 25,920,000 s
GB-seconds             = 25,920,000 × 0.5 GB  = 12,960,000 GB-s
invocations            = 25,920,000 / 15      =  1,728,000

compute  (with free)   : (12,960,000 − 400,000) × 0.0000133334 = USD 167.47
compute  (no free)     :  12,960,000           × 0.0000133334 = USD 172.80
requests (with free)   : ( 1,728,000 − 1,000,000) × 0.0000002 = USD   0.15
requests (no free)     :   1,728,000           × 0.0000002    = USD   0.35

egress   : 1,728,000 × 9,576 B = 16,547,328,000 B = 16.55 GB
           inside the 100 GB/month global free allowance      = USD   0.00

logs ingest (JSON format, INFO):
   the handler emits nothing on success; what is billed is the Lambda platform's
   JSON records (platform.start / platform.runtimeDone / platform.report), plus a
   timeout record at 15 s.  Band 1.2–5.0 KB per invocation.
      at 1.2 KB : 2.07 GB  → inside the 5 GB always-free      = USD   0.00
      at 5.0 KB : 8.64 GB  → (8.64 − 5) × 0.70                = USD   2.55
logs storage (7-day retention) : ingest × 7/30 = 0.48–2.02 GB-Mo
           inside the 5 GB-Mo always-free                      = USD   0.00
alarms 4 of 10 free, dashboard 1 of 3 free                     = USD   0.00
```

### **Total: USD 167.62 – 170.17 per 30 days. Headline: USD 168.**

Log ingest is *not* the driver. **Compute is 98 % of the bill**, and it is invariant in the
reservation: `min(20, 10) = 10` and `min(unreserved, 10) = 10`, so **USD 167.47 is the
compute ceiling whether `reserved_concurrent_executions` is `20`, `-1`, or anything
between.** This is the arithmetic behind the recommendation in §1.6.

### 2.7 Scenario C2 — the abuse an actual abuser would choose

Compute is invariant under `concurrency × wall-time × memory`. What is *not* invariant is
requests per second — and therefore **egress**. The Function URL serves the SPA, and
`static_site.MEDIA_TYPES` maps `.map` explicitly to `application/json` (`static_site.py:157`,
with a comment explaining the choice), so **`assets/index-BjAGxrVJ.js.map` — 1,554,168 bytes
— is anonymously fetchable**. Requesting it in a loop at the same ten concurrent slots
produces the same USD 167.47 of compute and a completely different egress bill.

Static-serve latency `L` is **unmeasured** — no function is deployed. Band 100–300 ms.

```
L = 300 ms :  requests = 10 × 2,592,000 / 0.300 =  86,400,000
              egress   = 86.4 M × 1,554,168 B   = 134,281 GB
              (134,281 − 100 free) = 134,181 GB
                 10,240 GB @ 0.120 =  1,228.80
                 40,960 GB @ 0.085 =  3,481.60
                 82,981 GB @ 0.082 =  6,804.44
                 egress            = USD 11,514.84
              requests 86.4 M × 0.0000002       = USD     17.28
              compute                            = USD    167.47
              logs 103.7 GB → (103.7−5) × 0.70   = USD     69.09
                                          TOTAL  = USD 11,768.68

L = 100 ms :  requests = 259,200,000 ; egress = 402,842 GB
                 10,240 @ 0.120 =  1,228.80
                 40,960 @ 0.085 =  3,481.60
                102,400 @ 0.082 =  8,396.80
                249,142 @ 0.080 = 19,931.36
                 egress          = USD 33,038.56
              requests USD 51.84 + compute USD 167.47 + logs USD 214.20
                                          TOTAL  = USD 33,472.07
```

### **Worst case: USD 11,769 – 33,472 per 30 days.**

Against `docs/deploy/terraform-plan.md:279` — *"worst case under USD 1.00"* — that is low
by a factor of **11,769× to 33,472×**.

Nothing in the plan bounds it. No CloudFront (excluded by the account's verification hold).
No WAF. No rate limit in the handler. No alarm on `BytesOut` or on `Invocations`. No budget
action. Reserved concurrency does not bound egress even when it can be set.

### 2.8 The budget

`aws budgets describe-budgets` returns **three** budgets, not one. All `COST` / `MONTHLY`,
all metric `UnblendedCost`, all filtered `NOT RECORD_TYPE IN (Credit, Refund)`, all
reporting the same actual and forecast.

| Budget | Limit | Actual | Forecast | Notifications | Subscribers | **Actions** |
|---|---:|---:|---:|---|---|---|
| `My Monthly Cost Budget` | 10.00 | 12.41 | 32.92 | ACTUAL > 85 %, ACTUAL > 100 %, FORECASTED > 100 % — **all in `ALARM`** | 1 × `EMAIL` | **`[]`** |
| `My Monthly Cost Budget - $5 limit` | 5.00 | 12.41 | 32.92 | the same three, all in `ALARM` | 1 × `EMAIL` | **`[]`** |
| `My Zero-Spend Budget` | 1.00 | 12.41 | 32.92 | ACTUAL > 0.01 `ABSOLUTE_VALUE` — `ALARM` | none returned | **`[]`** |

*(Subscriber addresses are deliberately not recorded. This repository is public.)*

`describe-budget-actions-for-budget` returns `Actions: []` for **every one of the three**.
There is no `aws budgets` mechanism on this account that can stop anything.

And every threshold is already breached, and has been for months. **A budget that is
permanently in `ALARM` carries no information about a new stack.** Adding this deploy
cannot change any budget's state, so no email will be sent that would not have been sent
anyway.

### 2.9 What the account is actually spending

`aws ce get-cost-and-usage`, by service:

| Month | Top lines (USD) |
|---|---|
| 2026-06 | EC2-Compute 9.06 · VPC 7.20 · KMS 2.99 · Tax 2.08 · EC2-Other 1.54 |
| 2026-07 | EC2-Compute 19.64 · VPC 7.44 · Tax 3.17 · KMS 3.00 · EC2-Other 1.54 |
| 2026-08 (to the 13th) | EC2-Compute 6.90 · VPC 2.63 · Tax 1.12 · KMS 1.06 · EC2-Other 0.54 · **Bedrock 0.1241** · S3 0.03 |

**`AWS Lambda` appears in no month.** The one existing function has never been billed.

One number worth stating plainly: the project's own **Bedrock spend is USD 0.1241
month-to-date** (Claude Haiku 4.5 0.0802, Bedrock 0.0267, Cohere Embed 4 0.0111, Cohere
Embed 3 English 0.0059, Claude Sonnet 4.5 0.0002). STATE records *"total probe spend USD
0.00006"*. I cannot attribute the difference — other sessions may have used Bedrock on the
same account — but **the "whole-system ≈ USD 0.02/month" claim is already exceeded roughly
6× by Bedrock alone, before a single Lambda exists.**

### 2.10 What bounds the bill, and what merely reports it

**Bounds it — stops spend:**

| Mechanism | What it bounds | Real? |
|---|---|---|
| AWS account Lambda concurrency quota = **10** (`L-B99A9384`, ACCOUNT level) | compute *rate*; caps sustained-abuse compute at USD 167.47/30 days | **yes** |
| `timeout = 15` | per-invocation duration | **yes** |
| CockroachDB Basic RU limit | database spend — the cluster is **disabled** when reached | **yes**, and it takes the demo down |
| `reserved_concurrent_executions` | **nothing on this account** | **no** — unsettable at 20, and looser than the account quota at any settable value |

**Reports only — stops nothing:**

* All four CloudWatch alarms. `alarm_actions` is `null` on every one of them in the
  committed plan. Nothing is notified and nothing acts.
* The `-concurrency` alarm specifically: threshold `> 20` against a metric that cannot
  exceed `10`. It cannot fire at all. *(W5 owns the repair.)*
* The dashboard. Somebody has to be looking at it.
* All three AWS Budgets. Zero actions, `EMAIL` subscribers only, all permanently in `ALARM`.
* The 100 GB/month data-transfer allowance. That is a discount, not a cap.

**Absent entirely:** no WAF, no handler rate limit, no CloudFront, no alarm on data
transfer out, **no cap on egress of any kind**.

---

## 3 · COCKROACHDB

### 3.1 The cap, and a discrepancy in the repository's own number

The cluster's configured `spend_limit` is **`2500` = USD 25.00/month**
(`docs/TOOL-USAGE.md:367, 372, 855` — the cluster JSON is parsed, not screen-scraped).

The repository states the free allowance as **100 M RU** in three places
(`docs/deploy/cloud-database.md:946`, `docs/deploy/OBSERVABILITY.md:113`,
`docs/TOOL-USAGE.md:856`). Cockroach Labs publishes, today:

> "Each pay-as-you-go CockroachDB Cloud organization is given $15 of resource consumption
> (equivalent to **50 million Request Units** and 10 GiB of storage) for free each month."
> — [Plan a CockroachDB Basic cluster](https://www.cockroachlabs.com/docs/cockroachcloud/plan-your-cluster-basic), fetched 2026-08-12

**The repo's 100 M is 2× the vendor's published 50 M.** Only the org's own Cloud Console
would settle which applies here, and nobody has read it. Both figures are carried through
below. RUs beyond the allowance cost **USD 0.20 per million**.

### 3.2 RU per `POST /v1/demo/gate-run` — an estimate, and it is labelled as one

From [Resource usage in CockroachDB Basic](https://www.cockroachlabs.com/docs/cockroachcloud/resource-usage-basic)
(fetched 2026-08-12): 1 RU = 2 read batches = 8 read requests = 64 KiB read payload;
1 RU = 1 write batch = 1 write request = 1 KiB write payload; **1 RU = 3 ms SQL CPU**;
1 RU = 1 KiB egress. Writes replicate 3× and each replica is counted separately.

| Term | RU | Basis |
|---|---:|---|
| egress | ~9 | the measured 9,576-byte response |
| reads | 10 – 50 | ten `count(*)` subqueries over a 27-row working set, plus the permit row and the site join |
| writes | 20 – 100 | `UPDATE mainline.permit`, `INSERT mainline.disposition`, and the writes inside `CALL mainline.merge_permit` — **all rolled back, but the intents are written and billed** — at 3 replicas and 1 KiB granularity |
| **SQL CPU** | **100 – 350** | the dominant term. Wall is 10,642.9 ms, but that includes ~90 ms RTT per statement from Australia. At 3–10 % of wall as SQL CPU (0.32–1.06 s) ÷ 3 ms |

**Estimate: 150 – 500 RU per gate run, central ≈ 300 RU.** This is the published formula
applied to a measured payload and a read code path. **It is not a metered reading and must
not be quoted as one.** One look at the RU chart in the CockroachDB Cloud Console would
settle it; nobody has taken it.

### 3.3 How long sustained abuse takes to exhaust it

The rate is bounded by the AWS concurrency ceiling of 10 divided by the measured 10.6 s
gate run: **0.943 gate runs/s = 81,510 per day.**

| RU/gate-run | RU/day | Free (50 M) | Free (100 M, repo) | Free + `spend_limit` (175 M) |
|---:|---:|---:|---:|---:|
| 150 | 12.2 M | 4.1 d | 8.2 d | **14.3 d** |
| **300** | **24.5 M** | **2.0 d** | **4.1 d** | **7.2 d** |
| 500 | 40.8 M | 1.2 d | 2.5 d | **4.3 d** |

`175 M RU = 50 M free + USD 25.00 ÷ USD 0.20 per M = 50 M + 125 M`.

**The cluster is disabled somewhere between day 4 and day 14 of a sustained flood; most
likely around day 7.**

### 3.4 What the judges see when it goes

> "If you reach your RU limit, your cluster will be **disabled** until you increase your RU
> limit or a new billing cycle begins."

Not throttled — **disabled**. Every handler DB call then raises, `app.py:384
_log.exception` fires, and the caller receives the JSON problem document with
`kind: "database_error"` — the exact shape already sitting in
`evidence/deploy/acceptance.json`, where the primary phase-2 run recorded two HTTP 500s
carrying `[22P02] error in argument for $2 …`. `GET /v1/health` reports a connect failure.

**Nobody is told.** The `-errors` alarm goes to `ALARM` with `alarm_actions = null`. The
only signal is the `demo-health` cron's red X on a public repository.

**And the bill does not stop.** The CockroachDB spend limit stops the *database*, not the
Lambda. AWS keeps metering at USD 167.47 per 30 days — or the egress figure — while every
request returns a 500. The two ceilings are not connected to each other in any way.

---

## 4 · VERDICT

**GO-WITH-FIX** — add `reserved_concurrent_executions = -1` to `module "api"` in
`infra/envs/demo/main.tf` (block begins line 280); without it the apply fails at
`module.api[0].aws_lambda_function.this` on `PutFunctionConcurrency` with
`InvalidParameterValueException` (400), leaving 5 of 11 resources created and the function
tainted, and with it the sustained-abuse ceiling is unchanged at USD 168/30 days for the
gate-run path and an unbounded USD 11,769–33,472/30 days for the egress path — a number the
founder has not yet seen and which no mechanism on this account can stop.
