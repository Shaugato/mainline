<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: CC-BY-4.0
-->

# `cost-guard` — the mechanism that can stop the demo

Before this module, **nothing in this repository could stop the demo function.** The only
bound in force was an AWS account concurrency quota of **10** that nobody chose and that
AWS marks `Adjustable: true`.

> **The USD 33,250 / 30 days this page used to quote was understated about sevenfold, and
> the correction is a measurement.** That figure assumed a 100 ms invocation.
> `docs/deploy/LATENCY.md` measured the static beats a flood is actually made of at
> **5.66 ms** and **14.11 ms**, and since `rate = concurrency / duration` the modelled
> worst case at the measured durations is **USD 229,759 per 30 days**
> (`docs/leads/cost-finish-plan.md` §0.5). Read it as a **model bound, not a forecast**:
> it assumes AWS sustains 708 rps × 1.55 MB of egress from ten execution environments,
> which nobody has observed. The direction of the correction is the point — the thing this
> module stops is larger than the page claimed, not smaller.

Everything else that looked like a bound was not one:

| Existing control | What it actually bounds |
|---|---|
| `log_retention_days = 7` | log **storage**. Ingestion is billed on arrival and retention does not refund a byte. |
| `timeout` | **one** invocation's wall clock. Lambda bills actual duration, so a 5.66 ms invocation costs the same under a 14 s timeout as under a 3 s one — **the timeout moves the bill by nothing.** It is a reliability bound and this page does not sell it as a cost one. |
| `memory_size` | **one** invocation's GB-seconds. Duration-independent and real, but it does not touch the rate — worth ≈ USD 86 out of USD 47,297, i.e. 0.2 %. |
| account concurrency = 10 | the **rate**, at a level worth USD 229,759 / 30 d at the measured durations. |

The worst case is `rate × bytes × time-until-something-stops-it`, and every one of those
left the third factor at **thirty days**. This module brings it to **minutes**.

---

## 1 · There is no Lambda budget action

A reader arriving here reasonably expects `aws_budgets_budget_action`. It exists, and
**it cannot stop a Lambda.** Its three action types, exhaustively:

| Action type | What it does | Why it does not help |
|---|---|---|
| `APPLY_IAM_POLICY` | attaches an IAM policy to users / groups / roles | it denies a **principal**. A Function URL with `authorization_type = NONE` is invoked by anonymous callers; there is no principal to deny. |
| `APPLY_SCP_POLICY` | attaches a Service Control Policy | requires AWS **Organizations**. This account is not in one, so the action type is unavailable here at all. |
| `RUN_SSM_DOCUMENTS` | runs `AWS-StopEC2Instance`, `AWS-StopRdsInstance`, … | EC2 and RDS. There is no Lambda document. |

So the path is not native, and this module builds it:

```
    AWS Budgets notification ──┐
    Invocations  Sum / 60 s  ──┼──►  ONE SNS topic  ──►  responder Lambda
    Invocations  Sum / 3600 s ─┤                              │
    Logs IncomingBytes / 300 s ┘                              ▼
                                     lambda:PutFunctionConcurrency(demo-api, 0)
```

**And the Budgets leg is a backstop, not a bound.** AWS Budgets evaluates against Cost
Explorer, which refreshes on an **8–24 hour lag**. A budget cannot stop anything inside a
day. The three CloudWatch alarms are what bound the bill; the budget catches what all
three miss, and anything this project did not model at all.

---

## 2 · The trade this module makes

**It converts a cost attack into an availability attack.**

Anyone who can generate 3,001 invocations in a minute can stop the demo. The URL is
`authorization_type = NONE` by the founder's explicit choice, so anyone at all can. The
function then stays stopped — reserved concurrency 0, every caller gets HTTP 429 with no
body from the handler — until a human runs:

```bash
scripts/deploy/kill_switch.sh --restore --expect-account <id> --yes
```

That script already exists and this module does not reimplement it.

> **Restore is `DeleteFunctionConcurrency`, not `PutFunctionConcurrency(-1)`.**
> The `-1` is a *Terraform* sentinel meaning "no reservation". The API's minimum is 0 and
> it rejects −1 outright, so a restore written as a put of −1 would fail exactly when it
> was needed. `scripts/deploy/kill_switch.sh` has the full note; read it before editing
> anything here.

The trade is the right one — an outage is recoverable by one command and a bill is not —
but it is a trade, and it lives in the residual table below rather than in a footnote.

**The responder can never undo the stop, and that is enforced three times:** its code
contains no restore call; `tests/deploy/test_cost_guard_responder.py` asserts the boto3
method name does not appear in the source at all; and the execution role carries an
explicit IAM **`Deny`** on `lambda:DeleteFunctionConcurrency`, which no `Allow` can
override. A stop that the stopped thing can undo is not a stop.

---

## 3 · What is created

Thirteen resources. **None is behind `count = 0`** — the finding that produced this wave
was that the bound was *documented and not implemented*, and a default-off stop is a
documented stop.

| Resource | Notes |
|---|---|
| `aws_sns_topic.guard` | one topic. Every publisher means the same thing, so they share it. |
| `aws_sns_topic_policy.guard` | replaces SNS's default policy; re-creates the account-owner statement, then admits `budgets.amazonaws.com` and `cloudwatch.amazonaws.com` under source conditions. |
| `aws_lambda_function.responder` | python3.13, arm64, 128 MB, 15 s. Source: `scripts/deploy/cost_guard_responder.py`, zipped at plan time. |
| `aws_cloudwatch_log_group.responder` | created **before** the function, so Lambda does not create an unowned, never-expiring group on first invocation. |
| `aws_iam_role.responder` + attachment + inline policy | see §4. |
| `aws_lambda_permission.sns_invoke` | scoped by `source_arn` to this topic only. |
| `aws_sns_topic_subscription.responder` | unconditional. This is the wire. |
| `aws_budgets_budget.guard` | one ACTUAL-cost notification to the topic. |
| 3 × `aws_cloudwatch_metric_alarm` | see §5. |

Plus `aws_sns_topic_subscription.email`, a `for_each` over `var.notification_emails`,
which **defaults to empty and gates nothing in the stop path**. It exists so a human learns
the demo was stopped. Note that an email subscription sits in `PendingConfirmation` until
somebody clicks the link, and Terraform reports it created either way — a control that
looks present and is not, which is why it is opt-in.

Measured: `Plan: 13 to add, 0 to change, 0 to destroy` with `notification_emails = []`, and
all **five** `lifecycle` preconditions satisfied (three reachability checks, the
three-timescale check, and the budget's non-empty-filter check). There are fourteen
`resource` blocks; the fourteenth is the email `for_each`, which contributes zero.

---

## 4 · The responder's role: one action, one resource, no wildcards

```
Allow  lambda:PutFunctionConcurrency
       on  arn:<partition>:lambda:<region>:<account>:function:<guarded_function_name>

Deny   lambda:DeleteFunctionConcurrency
       on  *

+ arn:<partition>:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole
```

One action. Not `lambda:*`, not `lambda:Put*`. Not the read side either — the responder
never calls `GetFunctionConcurrency`, because `PutFunctionConcurrency(0)` is idempotent at
the API and a read-before-write would be a second call that can fail and a second decision
that can be wrong.

One resource, unqualified — no `:*` version suffix, no alias, no wildcard anywhere in it.
`lambda:PutFunctionConcurrency` operates on the unqualified function, so a qualified ARN
would grant nothing and the responder would fail closed at the worst possible moment.

The managed basic-execution policy is wildcarded over log groups. That is AWS's own policy
and the one wildcard attached to this role; narrowing it would also narrow what the runtime
may do at cold start. `infra/modules/demo-api` records the identical judgement for the same
attachment.

---

## 5 · The three alarms, and the arithmetic behind every threshold

A threshold nobody can reconstruct is a threshold nobody has checked. Full derivations are
in `variables.tf`; this is the summary.

### The modelled judging session

| | realistic (8 judges) | pessimistic (20 judges) |
|---|---|---|
| per judge, worst minute | 57 objects + 12 API calls = **69** | same |
| session worst **minute** | **552** | **1,380** |
| per judge, per hour | 5 page loads × 57 + 3 runs × 12 = **321** | same |
| session worst **hour** | **2,568** | **6,420** |

57 is not an estimate: it is the entire identity tree in the deployed package
(`out/lambda/mainline-demo-api-arm64.zip`, measured 2026-08-13 — 114 `web/` entries,
57 identity + 57 pre-compressed `.gz`, 0 source maps, largest identity object 433,396 B).
One browser with a cold cache cannot pull more than 57 objects out of this function.

### The three thresholds

| # | Metric | Window | Threshold | Margin (realistic / pessimistic) | Blind to floods slower than |
|---|---|---|---|---|---|
| A1 | `AWS/Lambda Invocations` Sum | 60 s | **3,000** | 5.43× / 2.17× | **200 ms** |
| A2 | `AWS/Lambda Invocations` Sum | 3600 s | **15,000** | 5.84× / 2.34× | **2,400 ms** |
| A3 | `AWS/Logs IncomingBytes` Sum | 300 s | **16,777,216 B** | 39× / 15.7× | n/a (bytes, not count) |

All three carry `treat_missing_data = "missing"`. **Green must mean measured-and-fine,
never not-measured.** Under `notBreaching` an idle demo shows three green alarms and the
one thing an operator reads off green — "I looked, it is healthy" — is false. Under
`missing` an unexercised demo reads `INSUFFICIENT_DATA`, which is the true state. Expect
exactly that on a demo nobody has visited.

None has `ok_actions`. An OK action on this topic would invoke the **stop** responder on
*recovery*. The responder refuses an OK transition on its own — the test proves it makes no
call for one — but the right place to not do that is where the action is chosen.

### Why A1 is 3,000 — re-derived 2026-08-13, and the old argument for it was wrong

**The argument this section used to make no longer holds.** It said 7,000 would be
invisible to the flood, because at the account ceiling of 10 a 60-second window can only
hold 7,000 invocations if each bills under 85.7 ms, and `docs/deploy/COST-BOUND.md` models
the flood at 100–300 ms. That reasoning was sound *given a modelled duration*, and the
duration has now been **measured**: the static beats a flood is made of are 5.66 ms and
14.11 ms, ×3.944 for the 256 MB core share → 22.3 ms and 55.6 ms. A 7,000 threshold would
in fact be visible to an `asset_js` flood, at 3.84× margin. **The old defence of 3,000 is
retracted.** Here is the one that survives measurement.

Two constraints pull opposite ways, and both are quoted as ratios rather than adjectives:

| Direction | Constraint | Value | Margin |
|---|---|---:|---:|
| **Down** — must clear a judging session, or the demo stops itself in front of the judges | pessimistic worst minute (20 judges × 69) | 1,380 /min | **2.17×** |
| Down | realistic worst minute (8 judges × 69) | 552 /min | 5.43× |
| **Up** — must sit below what a flood puts in the same 60 s, or it cannot fire | `asset_js` flood @ 22.3 ms — *the largest object that ships* | 26,878 /min | **8.96×** |
| Up | `asset_map` flood @ 55.6 ms — *0 maps ship; worst case if that changes* | 10,785 /min | 3.59× |
| Up | `index` flood @ 4.9 ms | 123,582 /min | 41.19× |
| Up | 429 refusal path @ 0.9 ms | 679,151 /min | 226.38× |

**The gap exists and it is 19.48× wide** — 1,380 at the floor, 26,878 at the binding roof.
Its geometric centre is 6,090, and **3,000 sits at 0.49× that centre**: deliberately biased
toward the stopping end, by `docs/leads/cost-finish-plan.md` §0.5's ranking — *an outage is
recoverable by one command and a bill is not.*

Under the old 100 ms assumption that band was `1,380 … 6,000`, a ratio of only **4.35×**,
and the threshold sat 2.17× above the floor and 2.00× below the roof — the two constraints
were within a factor of two of colliding. **Measuring the duration moved the roof out
4.48× and opened the band from 4.35× to 19.48×.** The number did not move; the reason it is
defensible did.

### A third constraint caps A1 at 3,510, and it is easy to trip over

`log_incoming_bytes_threshold` is derived **from** A1:
`evidence/deploy/cost/log-bytes.json` reads 3,000 out of `variables.tf` and turns it into
15,000 per 300 s, so both edges of that threshold's admissible band are proportional to
this one — `lower = 4,780.005 B × burst`, `upper = 26,305 B × burst`. The standing
16,777,216 B stays inside the band only for `638 < burst < 3,510`, and 3,000 is at 0.855×
that cap.

**Raising A1 above 3,510 without raising A3 makes A3 fire on traffic A1 deliberately
permits** — a second alarm that is a copy of the first at a lower number, which is the
exact shape A2's own precondition already forbids. The two move together or not at all.

### Reachability is checked at plan time, and the checks are not vacuous

Each alarm carries a `lifecycle.precondition` placing its threshold strictly below the
ceiling the metric can physically reach, plus one enforcing the three-timescale property.
Every term is a plain variable, so each costs one plan evaluation and no API call.

**Re-measured 2026-08-13 by `terraform plan` against a scratch root** (never applied), after
`log_bytes_per_invocation_ceiling` moved from a round 16,384 to W3's measured 5,261. With
the defaults the module plans **13 to add, 0 to change, 0 to destroy**. With each threshold
pushed past its ceiling, all four refuse — Terraform's own output, trimmed:

```
burst  = 70000   →  Error: Resource precondition failed
                    condition = var.invocations_burst_threshold < local.invocations_max_60s
                    │ local.invocations_max_60s is 60000
                    │ var.invocations_burst_threshold is 70000

hourly = 200000  →  Error: Resource precondition failed
                    condition = var.invocations_hourly_threshold
                                  < var.invocations_burst_threshold * 60
                    │ var.invocations_burst_threshold is 3000
                    │ var.invocations_hourly_threshold is 200000

logb   = 9 GB    →  Error: Resource precondition failed
                    condition = var.log_incoming_bytes_threshold < local.log_bytes_max_300s
                    │ local.log_bytes_max_300s is 1578300000
                    │ var.log_incoming_bytes_threshold is 9000000000

logb   = 2 GB    →  Error: Resource precondition failed   ← THE NEW ONE
                    │ local.log_bytes_max_300s is 1578300000
                    │ var.log_incoming_bytes_threshold is 2000000000
```

**The last case is the point.** Under the old 16,384 B per-invocation ceiling
`log_bytes_max_300s` was 4,915,200,000 and a 2 GB threshold would have been *admitted*.
Adopting W3's measured 5,261 B drops the ceiling to 1,578,300,000 and the check now refuses
it. Replacing a round number with a measured one made the precondition **stricter**, which
is the direction a reachability check should move in.

### `terraform validate` is not enough, and this is the measurement that shows it

`alarm_description` is capped by AWS at **1,024 characters**, and the provider enforces it
at **plan** time — the schema does not, so `validate` passes a description that `plan`
refuses. Measured here on 2026-08-13: an expanded `log_ingestion` description of ~1,480
characters passed `terraform validate` cleanly and then failed `terraform plan` with
`expected length of alarm_description to be in the range (0 - 1024)`. It was shortened; the
full argument lives in `variables.tf`, which has no such limit. **Any change to an
`alarm_description` in this module must be re-planned, not merely re-validated.**

---

## 6 · The budget: a **service** filter, not a tag filter, and here is why

The brief asked for a tag filter (`project = mainline`) *or* the Lambda and DataTransfer
services if tag filters are not available on this account. **They are not available.**
Measured read-only on 2026-08-13:

```
$ aws ce list-cost-allocation-tags --region us-east-1 --status Active
{"CostAllocationTags": []}

$ aws ce list-cost-allocation-tags --region us-east-1 \
      --query "CostAllocationTags[?TagKey=='project']"
[{"TagKey": "project", "Type": "UserDefined", "Status": "Inactive", ...}]
```

**Zero tags are active for cost allocation in this account.** The key `project` exists in
the inventory — AWS has seen it on resources — and it is `Inactive`. An inactive cost
allocation tag matches no cost records, so a `TagKeyValue` filter would produce a budget
that is syntactically perfect, applies cleanly, appears in the console, and reports
**0.00 USD forever**: the exact *control that looks present and is not* defect this wave
exists to close, wearing a billing hat.

Activating one is `ce:UpdateCostAllocationTagsStatus` — a **mutating** account-level call,
which no worker in this wave may make — and activation is **not retroactive**: AWS applies
the tag from the activation date forward and takes up to 24 h to populate.
`var.use_tag_cost_filter` exists for the day after that, and turning it on **before**
activating the tag turns the budget **off**, because AWS ANDs multiple cost filters.

So the filter is `Service ∈ {"AWS Lambda", "AWS Data Transfer", "AmazonCloudWatch"}`.

**One of those three strings is confirmed against this account and two are not**, and that
is stated rather than smoothed over:

```
$ aws ce get-dimension-values --region us-east-1 \
      --time-period Start=2026-07-01,End=2026-08-13 --dimension SERVICE
… "AmazonCloudWatch" …          ← present
                                 "AWS Lambda"        ← absent
                                 "AWS Data Transfer" ← absent
```

They are absent because the SERVICE dimension enumerates services that have **produced
cost**, and no Lambda function has ever billed in this account
(`aws lambda list-functions --region ap-southeast-1` → `[]`). The other two are AWS's
documented canonical names and are unverifiable here until the first invoice.
**After the first bill, settle it with that same command** and correct
`var.budget_service_filter_values` if either string is wrong.

`"AmazonCloudWatch"` also carries CloudWatch spend from anything else in the account, so
this budget is **wider than the demo**. That is deliberate: the wide error stops the demo
for an unrelated reason and is recoverable with one command; the narrow error is a bill
with no bound and no way to notice.

`cost_types` sets `include_credit = false` and `include_refund = false`. **A flood paid for
by credits is still a flood** — with credits included, covered spend reports as 0.00 and
this budget would never fire while the credit balance drained.

The notification is **`ACTUAL`, not `FORECASTED`**. Forecast fires earlier, and firing
earlier is exactly wrong here: this notification *stops the demo*. Stopping a live demo in
front of judges on a prediction that may not come true is worse than a day of Cost Explorer
lag.

---

## 7 · The residual table

Prices are AWS list rates as used by `docs/deploy/COST-BOUND.md`; **`scripts/deploy/cost_model.py` (W7) owns the price table** and this section is arithmetic over its inputs, not an independent price claim.

Every duration below is **measured** (`evidence/deploy/cost/latency-baseline.json`) and
corrected by the measured 3.944× core-share penalty at 256 MB
(`latency-baseline.json::cpu_share_probe`). Bytes are the **139,264 B wire ceiling** now in
force (`static_site.DEFAULT_MAX_RESPONSE_BYTES`, derived from the deployed tree).

| Scenario | Detected by | Time to stop | Cost per episode |
|---|---|---|---|
| Flood at the maximum physical rate (`asset_js`, 22.3 ms → 26,878/min) | A1 (60 s) | ~4 min (metric publication + evaluation + async invoke) | **≈ USD 1.4** |
| Caller pacing at 3,000/min, just under A1 | A2 (3600 s) | ≤ ~1 h (period-aligned evaluation) | **≈ USD 2.31** — 180,000 invocations × 139,264 B |
| Caller pacing under **both** invocation lines | AWS Budgets | **5.4 days** + 8–24 h Cost Explorer lag | **≤ USD 29.6** (the USD 25 limit plus up to one day of overshoot at **USD 4.61/day**) |
| Bytes decoupled from invocation count (traceback storm, a library logging per row) | A3 (300 s) | ~5–8 min | bounded by ingestion, not by count. Measured: 200 psycopg records = 75,800 wire B that the handler's own budget charges **zero** for |
| **Today, without this module** | nothing | **30 days** | **USD 229,759** at the measured durations (a model bound) |

**The Budgets row is the only one that is not a bound.** Cost Explorer refreshes on an
8–24 hour lag that no setting shortens, so that leg **cannot stop anything inside a day**.
It is a backstop for what the three alarms miss. The three alarms are the bound.

**And the residual is not only dollars.** Two entries belong in the same column:

* **The availability trade of §2.** The demo can be stopped by anyone, and stays stopped
  until a human restores it.
* **The responder competes for the same ten concurrent executions as the flood.** A
  positive reserved concurrency on the responder would guarantee it a slot and *AWS refuses
  one*: a reservation may not drop `UnreservedConcurrentExecutions` below the floor AWS
  keeps back, and with a total quota of 10 that floor is already violated. Under a
  saturating flood the responder's own invocation can be **throttled**. What saves the stop
  is that SNS invokes Lambda **asynchronously**: the event enters Lambda's async queue and
  throttled invocations are retried with backoff until `maximum_event_age_in_seconds`
  (default 21,600 s = 6 h). **The stop is delayed, not lost**, and the delay is not
  measurable without an apply, so it is not claimed. The repair is to raise the account
  concurrency quota, at which point a positive reservation becomes possible — a support
  ticket, not a code change, and no code change substitutes for it.

---

## 8 · The proof, because an untriggered action is indistinguishable from no action

Nobody in this wave may `terraform apply`, and nobody may make a mutating AWS call —
including `put-function-concurrency`, including "just to prove the responder works". A plan
can show that resources *would be* created; it can never show that the wire carries
anything.

So the proof is `tests/deploy/test_cost_guard_responder.py`:

```bash
.venv/Scripts/python.exe -m pytest tests/deploy/test_cost_guard_responder.py -q --crdb=none
# 31 passed
```

It feeds the responder the **real** AWS Budgets SNS envelope and the **real**
CloudWatch-alarm SNS envelope and asserts through `botocore.stub.Stubber` that **exactly
one** `PutFunctionConcurrency` is made, with `ReservedConcurrentExecutions = 0` and the
function name taken from the responder's own **environment** (never from the message — the
alarm envelope names the function in its `Trigger.Dimensions` and the responder must not
read it from there). And **none at all** for a malformed message, a foreign topic, an alarm
transitioning to `OK` or `INSUFFICIENT_DATA`, or a missing environment variable.

"Made no call" is proved rather than inferred: the negative tests run against a `Stubber`
with an **empty queue**, so any call at all raises `UnStubbedResponseError`.

### The two envelopes are not the same kind of thing

This is the detail a responder written from memory gets wrong, and the test asserts it
directly:

* **CloudWatch** puts a JSON **document** in `Sns.Message` — `AlarmName`, `NewStateValue`,
  `Trigger`, …
* **AWS Budgets puts PLAIN TEXT in `Sns.Message`.** Not JSON. A human-readable paragraph
  beginning `AWS Budget Notification <date>` with `Budget Name:` / `Budgeted Amount:` /
  `Alert Threshold:` lines.

A responder that calls `json.loads` on both and lets the exception escape **drops the
entire Budgets leg**, silently, because that leg fires so rarely nobody would notice it
never worked.

### The falsification, which is what makes the rest mean anything

`test_falsification__deleting_the_stop_call_turns_the_proof_red` reads the responder's
source, deletes the stop call between its two anchor comments, executes the mutated module,
and asserts the same envelope now makes **no** call. If the anchors are ever removed, that
test fails loudly rather than mutating nothing and passing.

**Measured end to end.** With the stop call physically deleted from
`scripts/deploy/cost_guard_responder.py` on disk and the suite re-run:

```
10 failed, 21 passed
  FAILED …::test_real_envelope_makes_exactly_one_stop[cloudwatch-alarm-event0]
  FAILED …::test_real_envelope_makes_exactly_one_stop[aws-budgets-plain-text-event1]
  FAILED …::test_many_breaching_records_still_make_exactly_one_call
  FAILED …::test_falsification__deleting_the_stop_call_turns_the_proof_red
  … (file restored; 31 passed)
```

The 21 that still pass are the negative tests, which correctly assert that nothing is
called. **A test that cannot disagree with the code it tests proves nothing**, and this one
demonstrably can.

---

## 9 · Wiring it (for the env root)

```hcl
module "guard" {
  source                = "../../modules/cost-guard"
  guarded_function_name = module.demo_api.function_name
  tags                  = local.tags
}
```

### ⚠ `sns_topic_arn` is a **stop** topic, not a notification topic

Everything subscribed to it triggers `PutFunctionConcurrency(<guarded function>, 0)`.
`infra/modules/demo-api` has a single `var.alarm_actions` list that it wires into **all
four** of its alarms *and* into their `ok_actions`. Passing this ARN there means, in full:

| demo-api alarm | consequence of wiring this topic |
|---|---|
| `errors > 0` in 5 min | **one handler exception stops the demo** |
| `throttles > 0` in 5 min | one throttled invocation stops the demo |
| `duration_p99` over threshold | one slow CockroachDB round trip stops the demo |
| `concurrency` over threshold | stops the demo (arguably right) |
| every `OK` transition of all four | fires the stop responder again |

The first three are **health** signals, not cost signals. The three alarms in *this* module
already point at this topic, unconditionally, with no `ok_actions`; `demo-api`'s four exist
to be read.

### The env root needs `hashicorp/archive` in its lock file

This module adds one provider. `infra/envs/demo/.terraform.lock.hcl` currently pins only
`hashicorp/aws`, so the first `terraform init` after adding the `module "guard"` block must
be `terraform init -upgrade` (or `terraform providers lock`) to record `hashicorp/archive`.
Without it, `plan` fails with *"Inconsistent dependency lock file"*.

`versions.tf` carries the measurement that made `data.archive_file` safe here after it was
refused in `demo-api`: the provider writes a **fixed** entry timestamp (`2049-01-01`), so
the archive is a function of the source bytes alone and a fresh `git clone` — which does
not preserve mtimes — does not plan a redeploy. `output_file_mode = "0644"` pins the other
half: without it the same source produces different bytes on Windows (`0666`) and Linux
(`0644`), and the planning machine would show a Lambda update that changed no code.

---

## 10 · Operating it

```bash
# What is in force right now, without decoding anything:
terraform output -json thresholds

# Did it fire, and why?
aws logs tail /aws/lambda/<name>-guard-responder --follow
#   one JSON line per decision: stopped / refused / ignored, with the reason

# Alarm state (expect INSUFFICIENT_DATA on an unvisited demo — that is the true state):
aws cloudwatch describe-alarms --alarm-names \
    mainline-demo-api-invocations-burst \
    mainline-demo-api-invocations-hourly \
    mainline-demo-api-log-ingestion

# Put it back:
scripts/deploy/kill_switch.sh --status
scripts/deploy/kill_switch.sh --restore --expect-account <id> --yes
```

### If a notification never reaches the responder

The topic policy's `aws:SourceAccount` / `aws:SourceArn` conditions are transcribed from
AWS's documented examples and **are not verified on this account**, because verifying them
requires an apply and a real breach. Their failure mode is the dangerous direction — a
condition on a key the service does not populate denies the publish, and a denied publish is
a stop that silently never happens.

**Symptom:** the alarm shows `ALARM`, or the budget shows breached, and the topic shows
zero deliveries. **Repair:** drop the `condition` block from the failing statement in
`data.aws_iam_policy_document.topic` — not the principal.

---

## 11 · What has no mechanism at all, stated so nobody looks for one later

* **There is no Function-URL-level rate control.** AWS WAF does not attach to Lambda
  Function URLs (only CloudFront, ALB, API Gateway, AppSync and Cognito). The only
  Function-URL knob is `authorization_type`, which the founder ruled out. In-process rate
  limiting (W4) is the substitute, and it does **not** bound the invocation charge — Lambda
  bills a 429 like any other invocation. That is why this module exists.
* **There is no Lambda budget action.** §1.
* **Log ingestion has no native ceiling.** A log group has retention, not a quota. The only
  bounds are bytes-emitted-per-invocation (W4) and stopping the thing emitting them (A3).
