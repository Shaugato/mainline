<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: CC-BY-4.0
-->

# AWS OUTSIDE THE LIVE REQUEST PATH — the census

**Worker:** W2 · **Lead plan:** `docs/submission/feature-census-plan.md` · **Date:** 2026-08-16
**Deadline:** 2026-08-18 17:00 EDT · **Scope:** every AWS service this project uses that is
**not** in the demo's request path.

W1 owns the live path. This file owns the other three states of ruling **R2** — `REPO`,
`APPLIED`, `DECLARED` — plus the fifth, negative state `NOT-AVAILABLE`. **No row here
duplicates a W1 row**; §1 states the boundary explicitly.

Nothing in this document was produced by a deploy. **No `terraform apply` was run, no AWS
API was called, no SSM parameter was written, no credential was read or printed, and nothing
was committed.** Every state below was assigned from a command run against the tree at
`5f57146` on 2026-08-16, and every command is printed beside its row.

---

## 0 · THE FIVE STATES, AND HOW TO READ THEM

Ruling **R2** fixes the vocabulary. It is the vocabulary
`scripts/submission/capture_tool_evidence.py` already emits, so this census and
`evidence/tool-usage/aws-services.json` cannot end up disagreeing in front of a judge.

| state | means | generator verdict |
|---|---|---|
| **LIVE** | in this demo's request path — **W1's file, not this one** | EXERCISED + a live-origin check |
| **REPO** | it ran, in this repository, and is **not** in the demo's request path | EXERCISED, no live-origin check |
| **APPLIED** | it exists in the AWS account, created by a real apply, and is not in the request path | EXERCISED via a Terraform state or a console artefact |
| **DECLARED** | written and Terraform-valid; **never created** | DESIGNED |
| **NOT-AVAILABLE** | checked on this platform and absent; no dependency taken | NOT-AVAILABLE |

**`APPLIED` is not `EXERCISED-in-anger`.** Seven alarms exist; no artefact in this repository
records one of them transitioning to `ALARM`. A budget exists; no notification has been
delivered. Every `APPLIED` row below says so in its own words, because *"it exists"* and
*"it has done its job"* are two different claims and only the first one is ours to make.

### The two regions, and why they matter to every row

| where | region | what runs there |
|---|---|---|
| the live demo | **`ap-southeast-1`** (Singapore) | Lambda, Function URL, SSM, the CockroachDB Cloud Basic cluster |
| every Bedrock artefact in this census | **`ap-southeast-2`** (Sydney) | Titan v2, Claude via `au.*` profiles, the CloudWatch metric census |

The two halves of this project's AWS use ran in **different regions on different days**. That
is the sharpest single check on ruling **R4**: the Bedrock work could not be in the demo's
request path, because it is not even in the demo's region.

    python -c "import json,pathlib;print(sum(1 for p in pathlib.Path('evidence/aws').rglob('*.json') if json.load(open(p,encoding='utf-8'))['region']=='ap-southeast-2'))"

prints `24` — and `evidence/aws/` holds exactly 24 JSON artefacts, so that is all of them.

---

## 1 · THE BOUNDARY WITH W1 — what is deliberately absent from this file

These are **LIVE** and belong to `docs/submission/census/aws-live-path.md`. They are named
here only so a reader can see the seam:

* **AWS Lambda — `mainline-demo-api`**, the function the URL invokes.
* **AWS Lambda Function URL** — `authorization_type = NONE`, the demo hostname itself.
* **AWS Systems Manager Parameter Store** — the DSN, reached by hand-rolled SigV4.
* **AWS IAM — the demo-api execution role** and its one-ARN `ssm:GetParameter` grant.
* **Amazon CloudWatch Logs — `/aws/lambda/mainline-demo-api`**, written by the handler.

This file covers the **second** Lambda, the **second** IAM role, the **second** log group,
and everything watching the first one from outside.

**One correction W1 will want.** The prior census
(`evidence/tool-usage/aws-services.json`) has **no distinct row for the Lambda Function
URL** — it is folded into `aws_lambda`. That is a live-path row and W1 owns proposing it.

**One service neither of us has a row for, deliberately: AWS X-Ray.** `X-Amzn-Trace-Id` appears
on every response with `Sampled=0`, injected by the Lambda service and not by us, and
`grep -rn "tracing_config\|xray\|AWSXRay" infra/` returns nothing. `aws-live-path.md` §4.5 owns
the refusal. It is named here only so that a reader auditing both census files sees the same
non-claim in both. **Never say "distributed tracing with X-Ray."**

---

## 2 · APPLIED — created by the real apply of 2026-08-14, and out of band from the request path

### The one apply, and the two artefacts that pin it

    evidence/deploy/APPLIED.md:14      terraform apply    24 created, 0 changed, 0 destroyed
    evidence/deploy/APPLIED.md:15      terraform state    37 resources
    evidence/deploy/APPLIED.md:18-21   "Eleven resources are the demo API; thirteen are the
                                        cost guard ... The guard was instantiated in this
                                        apply, which is why the plan is 24 and not the 22
                                        an earlier review saw."

The thirteen guard addresses are enumerated, by machine, in
`evidence/deploy/cost/plan-shape.json`:

    python -c "import json;print('\n'.join(r['address'] for r in json.load(open('evidence/deploy/cost/plan-shape.json',encoding='utf-8'))['resources']['module.guard[0]']))"

    module.guard[0].aws_budgets_budget.guard
    module.guard[0].aws_cloudwatch_log_group.responder
    module.guard[0].aws_cloudwatch_metric_alarm.invocations_burst
    module.guard[0].aws_cloudwatch_metric_alarm.invocations_hourly
    module.guard[0].aws_cloudwatch_metric_alarm.log_ingestion
    module.guard[0].aws_iam_role.responder
    module.guard[0].aws_iam_role_policy.responder_stop
    module.guard[0].aws_iam_role_policy_attachment.responder_basic
    module.guard[0].aws_lambda_function.responder
    module.guard[0].aws_lambda_permission.sns_invoke
    module.guard[0].aws_sns_topic.guard
    module.guard[0].aws_sns_topic_policy.guard
    module.guard[0].aws_sns_topic_subscription.responder

**Read that list for what is NOT in it.** Three resource *blocks* in the tree produce **fewer
instances than blocks** in the shipping shape, and the arithmetic in the lead plan's §0.4
counts blocks. A judge who counts the plan will get different numbers, so the difference is
stated here rather than left for them to find:

| resource block | blocks in tree | instances applied | why |
|---|---|---|---|
| `aws_sns_topic_subscription` | 2 | **1** | `.email` is `for_each` over `var.notification_emails`, which defaults to `[]` |
| `aws_lambda_permission` | 2 | **1** | `.cloudfront_invoke` is `count = 0` — there is no distribution to grant to (§4, D1) |
| `aws_cloudfront_origin_access_control` | 2 | **0** | the whole `module.site` is `count = 0` |

`module.api[0]` carries **11** addresses and **no** `aws_lambda_permission` among them, which
is the same fact read from the other end.

### The limit of every `APPLIED` claim in this section — read this before quoting any of them

**No program in this repository has ever read these resources back out of CloudWatch, SNS or
Budgets.** The evidence that they exist is the apply transcript at
`evidence/deploy/APPLIED.md:14` — 24 created — together with the plan that enumerates exactly
those 24 addresses. That is a strong chain and it is not a readback, and the difference is
worth one sentence rather than a later correction.

The program written to do the readback exists and **has only ever been run in dry mode against
an account where nothing had been applied yet**:

    python -c "import json;d=json.load(open('evidence/deploy/verify/post-apply-dry.json',encoding='utf-8'));print(d['generated_at'],d['verdict'],d['checks_satisfied'],'of',d['checks_total']);print([c['why'][:60] for c in d['checks'] if c['id']=='alarm_inventory'])"

    2026-08-14T09:09:58.242241+00:00 NOT SATISFIED 0 of 9
    ['7 of 7 declared alarms do not exist: mainline-demo-api-concur']

That run is **earlier than the plan it was meant to verify** — `plan-shape.json` timestamps the
regenerated plan at `2026-08-14T10:35:40Z` — so despite the filename it is a *pre*-apply
reading, and `kill_switch --status` exited `4`, meaning *the function does not exist*. It is
kept, and quoted here, because the artefact's own words are the right ones: **"An empty or
short table is not a green one."**

What it *does* settle, and settles well: the seven alarm names derived from the two Terraform
modules and the seven alarm names in the plan JSON **agree exactly**
(`context.alarm_set_provenance.cross_check.agree = true`). That is a naming check, not an
existence check, and this census does not spend it as one.

**Note for W7 and W1:** `aws-live-path.md` §4.4 cites this file as cross-checking the seven
alarms. That citation is correct *for the name agreement* and would be misread as a live
inventory. One clause — *"names cross-checked against the plan"* — closes it.

---

### A1 · Amazon SNS — the stop topic

**state:** APPLIED
**what it is:** one SNS topic, one topic policy that replaces SNS's default entirely, and one
Lambda subscription. Everything that publishes to it means the same thing — *stop the demo* —
so the responder does not have to know which alarm spoke.
**where:** `infra/modules/cost-guard/main.tf:198` (topic), `:322` (policy), `:541`
(subscription). Topic policy statements at `:240–320`: `AccountOwnerManagesThisTopic`,
`AwsBudgetsMayPublishAStop`, `TheseThreeAlarmsMayPublishAStop`.
**verify in 60s:**

    grep -n 'resource "aws_sns_topic' infra/modules/cost-guard/main.tf

first line `198:resource "aws_sns_topic" "guard" {`. That the topic *exists in the account*
is `evidence/deploy/APPLIED.md:14` plus the thirteen addresses above; with the account,
`aws sns get-topic-attributes --topic-arn "$(terraform output -raw guard_sns_topic_arn)"`.
**say this:** *"An SNS topic is applied in the account. It is a stop topic, not a notification
topic: its one confirmed subscriber is a Lambda that reserves zero concurrency on the demo
function, and its policy names the three alarms allowed to publish rather than using a
wildcard."*
**never say:** *"SNS alerts us."* Nobody is subscribed by email —
`var.guard_notification_emails` defaults to `[]` and the module's own comment explains why: an
unconfirmed email subscription is a control that looks present and is not. The demo can stop
without anyone being told; `scripts/deploy/kill_switch.sh --status` is the compensating step.
Also never say the topic has ever carried a message: no artefact records a publish.

---

### A2 · AWS Budgets — the days timescale

**state:** APPLIED
**what it is:** one `COST` budget, **USD 25.00 monthly**, `ACTUAL` (not `FORECASTED`),
`GREATER_THAN 100 %`, publishing to the same stop topic as the alarms. Scoped by a **Service**
cost filter (`AWS Lambda`, `AWS Data Transfer`, `AmazonCloudWatch`), with credits and refunds
**excluded** from the evaluated cost.
**where:** `infra/modules/cost-guard/main.tf:553–637`; defaults in
`infra/modules/cost-guard/variables.tf` (`budget_limit_usd = 25.0`,
`budget_time_period_start = "2026-08-01_00:00"`).
**verify in 60s:**

    grep -nE '^\s+default\s+=' infra/modules/cost-guard/variables.tf

prints **22 lines** — every variable's default. These ten are the ones that decide behaviour;
the other twelve are names, tags, log levels and the responder's own shape:

    217:  default     = 10          <- account_concurrency_ceiling
    258:  default     = 10          <- fastest_invocation_ms
    314:  default     = 5261        <- log_bytes_per_invocation_ceiling
    415:  default     = 3000        <- invocations_burst_threshold
    502:  default     = 15000       <- invocations_hourly_threshold
    626:  default     = 16777216    <- log_incoming_bytes_threshold
    695:  default     = 25.0        <- budget_limit_usd
    713:  default     = "2026-08-01_00:00"
    778:  default     = ["AWS Lambda", "AWS Data Transfer", "AmazonCloudWatch"]
    974:  default     = []          <- notification_emails, and see "never say" below

(the `<-` annotations are this document's; the line numbers and the values are the file's).
Every threshold in the
guard is left at the module's own default **on purpose** — those defaults were derived in that
module's `variables.tf` from measured beat durations, a measured per-invocation log term and a
read-only Cost Explorer query, each with a `lifecycle.precondition` checking it for
reachability. Restating them in the environment would create two places that can disagree
about one derivation.
**say this:** *"A USD 25/month AWS Budget is applied, and it is wired to the stop rather than
to an inbox. It evaluates ACTUAL cost with promotional credit excluded, because a flood paid
for by credits is still a flood."*
**never say:** *"The budget caps our spend."* It does not cap anything. AWS Budgets evaluates
against Cost Explorer on an **8–24 hour lag AWS documents and no setting shortens**
(`evidence/deploy/cost/plan-shape.json` → `stop_path.hop_4_budget_backstop`). It is the
backstop; the two invocation alarms are the bound. And never say it has fired.

**Why this budget publishes to a stop topic instead of to an inbox — measured, not asserted.**
`evidence/deploy/verify/aws-quota-and-cost.json` records a read-only
`aws budgets describe-budgets` against this account on 2026-08-12. It found **three
pre-existing budgets** — limits USD 10, 5 and 1 — every one of them **already in `ALARM` and
having been for months** (actual spend USD 12.41 against all three), and
`describe-budget-actions-for-budget` returned **`0` actions across all three**. The artefact's
own reading is the sentence to use: *"A budget that is permanently breached carries no
information about a new stack, and none of them can stop anything."* That is the failure mode
this one is built not to have. See §3, R6 for the row that owns those read-only calls.

---

### A3 · Amazon CloudWatch — seven metric alarms, on four metrics, across three timescales

**state:** APPLIED
**what it is:** **seven** alarms, not the four the prior census names. Four watch the demo
function's health and abuse surface; three are the cost guard's, on three timescales, each
bounding what the faster one lets through.

| alarm | namespace / metric | stat | period | threshold |
|---|---|---|---|---|
| `mainline-demo-api-errors` | `AWS/Lambda` `Errors` | Sum | 300 s | > 0 |
| `mainline-demo-api-throttles` | `AWS/Lambda` `Throttles` | Sum | 300 s | > 0 |
| `mainline-demo-api-duration-p99` | `AWS/Lambda` `Duration` | **p99** | 300 s | > 13,500 ms |
| `mainline-demo-api-concurrency` | `AWS/Lambda` `ConcurrentExecutions` | Maximum | 300 s | > 8 |
| `mainline-demo-api-invocations-burst` | `AWS/Lambda` `Invocations` | Sum | **60 s** | > 3,000 |
| `mainline-demo-api-invocations-hourly` | `AWS/Lambda` `Invocations` | Sum | **3600 s** | > 15,000 |
| `mainline-demo-api-log-ingestion` | **`AWS/Logs`** `IncomingBytes` | Sum | 300 s | > 16,777,216 B |

Two properties are worth a judge's attention and neither is decoration:

1. **All seven use `treat_missing_data = "missing"`, never `notBreaching`.** An idle demo
   reads `INSUFFICIENT_DATA`, which is the true state. Under `notBreaching` it would read
   green, and the one thing an operator takes from green — *"I looked, it is healthy"* —
   would be false. `infra/modules/cost-guard/main.tf:650–667` rule (a).
2. **Every alarm whose metric has a physical ceiling carries a plan-time `precondition`
   placing its threshold strictly below that ceiling.** A threshold at or above a ceiling the
   metric cannot reach does not fire late — *it cannot fire*. **Five of the seven carry one**,
   seven preconditions between them (`duration_p99` and `invocations_hourly` carry two each);
   `-errors` and `-throttles` carry none and correctly so, because `Sum > 0` on a metric AWS
   emits unconditionally has no ceiling to sit above. The account's Lambda concurrency quota is
   **10**, measured, so `ConcurrentExecutions` is capped at 10 and the concurrency alarm at
   **20** — the module's old default — bounded nothing whatsoever until it was moved to 8.
   `demo-api/main.tf:684, 695, 826`; `cost-guard/main.tf:699, 733, 739, 788`.

**where:** `infra/modules/demo-api/main.tf:581, 615, 648, 757`;
`infra/modules/cost-guard/main.tf:673, 707, 752`.
**verify in 60s:**

    python -c "import json;d=json.load(open('evidence/deploy/cost/plan-shape.json',encoding='utf-8'))['alarms'];print(len(d));[print(v['alarm_name'],v['namespace'],v['metric_name'],v['statistic'] or v['extended_statistic'],v['period_seconds'],v['threshold'],v['treat_missing_data']) for v in d.values()]"

first line `7`, then seven rows carrying every column of the table above, each ending
`missing`. (The period lives under `period_seconds`; `statistic` is `null` on
`-duration-p99`, because a percentile goes in `extended_statistic` and Terraform requires
`statistic` to be unset when it is used — `infra/modules/demo-api/main.tf:662–663`.) And:

    grep -c "precondition {" infra/modules/demo-api/main.tf infra/modules/cost-guard/main.tf

prints `7` and `5` — twelve plan-time refusals across the two modules, of which seven are on
alarm thresholds and the rest on the function, the URL and the budget filter.
**say this:** *"Seven CloudWatch alarms are applied across four metrics and three timescales,
and the five whose metrics have a physical ceiling each carry a plan-time precondition proving
the threshold is reachable — an alarm whose threshold sits above what the metric can reach is a
control that looks present and is not, and Terraform refuses to plan one here."*
**never say:** *"Our alarms caught X"*, or anything implying an alarm has fired. **No artefact
in this repository records any of the seven transitioning to `ALARM`**, and none has been read
back from CloudWatch — see the standing caveat above §A1. They are created and unexercised.

---

### A4 · Amazon CloudWatch — one dashboard

**state:** APPLIED
**what it is:** one dashboard named for the function, **five widgets**: a text header stating
the runtime, the memory, the timeout, the Function URL's authorisation type and what actually
bounds it; three metric widgets (invocations+errors, duration p50/p99, concurrency+throttles);
and one **alarm-state** widget.
**where:** `infra/modules/demo-api/main.tf:841`.
**verify in 60s:**

    sed -n '841,978p' infra/modules/demo-api/main.tf | grep -cE '^\s+type\s+='

prints `5`.
**say this:** *"A CloudWatch dashboard is applied, and its header widget names the thing most
dashboards hide: the Function URL is unauthenticated, and what bounds it is the account's
measured concurrency ceiling of 10, not any control we chose."*
**never say:** *"The dashboard shows our live traffic."* No artefact records the dashboard
being read, and the prior census says so in the same words.

---

### A5 · AWS Lambda — the cost-guard responder (the **second** function)

**state:** APPLIED
**what it is:** a second `python3.13` / `arm64` Lambda, 128 MB, 15 s, subscribed to the stop
topic. Its only verb is
`lambda:PutFunctionConcurrency(ReservedConcurrentExecutions=0)` against exactly one function.
After it runs, the demo URL answers **HTTP 429 with no body** until a human runs
`scripts/deploy/kill_switch.{sh,ps1} --restore`.
**where:** `infra/modules/cost-guard/main.tf:469` (function),
`:529` (`aws_lambda_permission.sns_invoke`, pinned by `source_arn` to this one topic),
`:541` (subscription), source at `scripts/deploy/cost_guard_responder.py`.
**verify in 60s:**

    grep -n 'MAINLINE_COST_GUARD_TOPIC_ARN\|reserved_concurrent_executions = -1\|handler       =' infra/modules/cost-guard/main.tf

first line `477:  handler       = "cost_guard_responder.handler"`.
**say this:** *"A second Lambda is applied whose only job is to stop the first one. It refuses
every SNS record whose `TopicArn` is not the one topic it was given, and it holds `-1`
reserved concurrency because this account's quota of 10 makes every positive reservation
un-appliable."*
**never say:** *"The kill switch has been tested end to end in the account."* The responder's
refusal behaviour is unit-tested offline; **no artefact records a real breach, a real publish,
or a real `PutFunctionConcurrency` call.** The path is applied and unexercised.

---

### A6 · AWS IAM — a one-action grant with an explicit self-Deny

**state:** APPLIED
**what it is:** the responder's execution role. One `Allow`: `lambda:PutFunctionConcurrency`
on **one unqualified function ARN, no wildcard anywhere in it**. One `Deny`:
`lambda:DeleteFunctionConcurrency` on `*`.
**where:** `infra/modules/cost-guard/main.tf:426–467`, sids `StopExactlyOneFunction` and
`AndItMayNeverUndoItself`.
**verify in 60s:**

    grep -n 'StopExactlyOneFunction\|AndItMayNeverUndoItself\|lambda:PutFunctionConcurrency\|lambda:DeleteFunctionConcurrency' infra/modules/cost-guard/main.tf

**six lines.** The first two are prose — `51:` in the module's header diagram and `155:` in the
comment explaining the unqualified ARN. The four that are policy are
`428:    sid    = "StopExactlyOneFunction"`, `435:    actions = ["lambda:PutFunctionConcurrency"]`,
`442:    sid    = "AndItMayNeverUndoItself"` and
`458:    actions   = ["lambda:DeleteFunctionConcurrency"]`.
**say this:** *"The stop is enforced by IAM rather than by good behaviour: the responder's role
carries an explicit Deny on `DeleteFunctionConcurrency`, so even a responder rewritten to
restore itself cannot. A stop that can be undone by the thing being stopped is not a stop."*
**never say:** *"Least privilege everywhere."* The role also carries AWS's managed
`AWSLambdaBasicExecutionRole`, which is wildcarded over log groups. The module names that as
the one wildcard attached to the role and declines to narrow it.

---

### A7 · Amazon CloudWatch Logs — the responder's log group

**state:** APPLIED
**what it is:** `/aws/lambda/mainline-demo-api-guard-responder`, retention **30 days**,
created *before* the function on purpose: Lambda creates `/aws/lambda/<name>` on first
invocation with **no expiry, owned by nothing**, and it then survives `terraform destroy` and
accrues storage forever.
**where:** `infra/modules/cost-guard/main.tf:388`, `depends_on` at `:519–523`.
**verify in 60s:** `grep -n -B4 'resource "aws_cloudwatch_log_group" "responder"' infra/modules/cost-guard/main.tf`
**say this:** *"Both log groups in this stack are created by Terraform with a finite retention,
so neither is an orphan Lambda made and nobody owns."*
**never say:** anything about log *content* — the demo-api log group is W1's row.

---

### A8 · Amazon S3 — the Terraform state bucket, and native S3 locking

**state:** APPLIED
**what it is:** `mainline-demo-tfstate-<account>` — versioned, public access blocked on **all
four** settings, SSE-S3, tagged, noncurrent versions expiring at 30 days. It was the **first
mutating action of the whole deploy**, created by `scripts/deploy/bootstrap_state.sh` before
Terraform ran, because the plan cannot create the bucket it stores its own state in.
Locking is Terraform ≥ 1.10's **native S3 `use_lockfile`** — **there is no DynamoDB table in
this account and no `dynamodb_table` argument anywhere.**
**where:** `infra/envs/demo/backend.tf:94–99` (the `backend "s3"` block; its four arguments are
`:95–98`); recorded at `evidence/deploy/APPLIED.md:23–25`.
**verify in 60s:**

    grep -n 'use_lockfile\|dynamodb\|backend "s3"' infra/envs/demo/backend.tf

four lines: `76:` and `80:` are the comment that states there is no DynamoDB table and none is
wanted, `94:  backend "s3" {` opens the block, and `98:    use_lockfile = true` is the locking.
The block's four arguments are `key`, `region`, `encrypt = true` and `use_lockfile = true` —
and **no `dynamodb_table`**, which is the whole claim.
**say this:** *"State lives in a versioned, private, encrypted S3 bucket locked by S3 itself —
one fewer resource, one fewer bill line, and one fewer thing to remember to delete."*
**never say:** that this is the evidence store. **It carries no Object Lock configuration and
holds no checkpoint** — it is a deployment mechanic. The evidence store is §4, D3, and it has
never been created. The prior census already draws this distinction and it must not be blurred.

---

## 3 · REPO — real, exercised in this repository, and **not** in the demo's request path

### The R4 construction, stated once and then reused verbatim

Ruling **R4** fixes the wording for every row in this section, and the wording is checkable in
one command:

    grep -rn "boto3\|bedrock" verticals/mainline/apps/demo-api/src/ --include=*.py

    verticals/mainline/apps/demo-api/src/mainline_demo_api/db.py:26:importing boto3. Not because boto3 is unavailable — it is in the runtime image — but
    verticals/mainline/apps/demo-api/src/mainline_demo_api/db.py:27:because the deployment package's behaviour would then depend on which boto3 AWS shipped
    verticals/mainline/apps/demo-api/src/mainline_demo_api/retry.py:12:``psycopg-binary==3.3.4`` *and nothing else* — no boto3, no framework, no workspace

**Three hits, all of them comments, none of them an import, and none of them the word
`bedrock`.** The deployment package is `psycopg-binary==3.3.4` and nothing else; the deployed
zip's top-level members are `mainline_demo_api`, `psycopg`, `psycopg_binary`, `web` and a
dist-info directory (`evidence/deploy/verify/state-and-teardown-audit.json` →
`can_anything_set_MAINLINE_DSN_in_the_deployed_artefact.evidence`).

So the sentence every row below uses is: **it is real, it ran, and it is not in the demo's
request path.** That construction is already how this repository speaks about Bedrock, and it
reads as confidence rather than hedging.

---

### R1 · Amazon Bedrock — Claude inference through `au.*` inference profiles

**state:** REPO
**what it is:** `bedrock-runtime` `Converse` / `InvokeModel` against Australia-only inference
profiles in `ap-southeast-2`. The model id is **resolved at start-up from
`ListInferenceProfiles` and pinned into the run record — never hard-coded** — and any
identifier without the `au.` prefix is refused by the transport as a residency violation.
**where:** `packages/mainline-agentkit/src/mainline_agentkit/transport.py:273`;
`packages/trappoint-recall/src/trappoint_recall/eval/bedrock_backend.py` (1,403 lines, the
channel-C retriever whose vectors are Bedrock's and whose index is CockroachDB C-SPANN).
**the artefacts:** `evidence/aws/probe/raw-haiku-converse.json` — HTTP 200 with an AWS request
id, `stopReason end_turn`, 22 input / 8 output tokens. `evidence/aws/agent/live-run.json` —
**`leg_count = 7`** live legs through the same `au.*` profile, 17,429 input tokens, each
recorded as a cassette. `evidence/aws/agent/determinism.json` — those cassettes replayed twice
to a byte-identical decision hash, and a **tampered cassette refuses to load**.
`evidence/deploy/aws-live.json` — a second, independent transcript on a different day carrying
**AWS request id `3c7a283c-9f67-4d98-aa8f-26490d54d32d`**.
**verify in 60s:**

    python scripts/aws/agent_live.py --verify

Runs with **no credentials and no network**: it recomputes every cassette digest, asserts the
filename is the digest, and replays the decision twice. Run today, it prints **seven store
lines** — one `recall_live`, six `agentkit_live`, each `<digest> ok` — then:

    replay hashes equal: True
    verdict: PASS

exit `0`. Seven lines because there were seven live legs; that is the same `leg_count = 7`
read back from the cassettes rather than from the artefact that claims it.
**say this:** *"Amazon Bedrock is real in this repository: seven live Claude legs in Sydney,
each with an AWS request id, each recorded as a cassette that replays to a byte-identical
decision and refuses to load if tampered with. **It is not in the demo's request path** — the
demo's Lambda imports `psycopg` and nothing else, deliberately."*
**never say:** *"The demo runs on Bedrock."* It does not; the live URL makes no model call.
And never quote the live legs as running on the shipping model — they ran on
`claude-haiku-4-5` while the request builders target the pinned `claude-opus-5` generation,
and four builder fields are **refused on the wire** by haiku, named field by field in
`live-run.json` → `measured_wire_refusals`. Also: `refusal_behaviour.live_refusals_observed`
is **0**, so the refusal-degrades-the-run path was exercised against a *constructed* refusing
transport, not a model that said no.

---

### R2 · Amazon Bedrock — embeddings (Titan Text v2; the Cohere residency finding)

**state:** REPO
**what it is:** `amazon.titan-embed-text-v2:0` in `ap-southeast-2` producing **2,060 vectors
of width 1,024** for **177,345 input tokens**, enumerated one per row with a text digest, a
vector digest and a token count. Those vectors are then searched through CockroachDB's
`ce_ann` C-SPANN index — **1,080 rows searched** — which is the seam where the AWS half of
this project meets the CockroachDB half.
**where:**
`verticals/mainline/packages/mainline-recall-agent/src/mainline_recall_agent/providers/bedrock_titan.py:55`;
manifests at `evidence/aws/embeddings/manifest.json`, proof at `evidence/aws/ann/ann-proof.json`.
**the request ids:** `raw-titan-invoke.json` carries `6dcdcdf0-38d3-453f-a476-fa69b2d87863`,
HTTP 200, width 1,024, **L2 norm `1.00000006`**; `evidence/deploy/aws-live.json` carries
`b4d826e9-03ba-4368-9687-f00cc28a98ef` and records the same norm as `1.0` because that program
rounds and the probe does not. **The two figures are not in conflict and neither may be quoted
as the other.**
**the finding that is worth more than the success:** `cohere.embed-v4:0` is **refused
on-demand in `ap-southeast-2`** — `ValidationException`, HTTP 400, request id
`a826eb16-e813-45aa-932e-4696e9979087` (`evidence/aws/probe/raw-cohere-refusal.json`). The
only identifier on this account carrying that model is `global.cohere.embed-v4:0`, which AWS's
own description calls **global routing** and which `scripts/aws/_common.py::assert_in_region`
refuses. The in-region answer is `cohere.embed-english-v3`, and it carries its own limit:
Bedrock refuses any single text over 2,048 characters for it.
**verify in 60s:**

    python -c "import json;p=json.load(open('evidence/aws/probe/model-availability.json',encoding='utf-8'))['payload'];print(p['region'],p['foundation_models_total'],p['inference_profiles_total']);print(p['inference_profiles_by_routing_prefix']);print(p['embedding_models_on_demand_in_region'])"

    ap-southeast-2 64 29
    {'apac': 8, 'au': 8, 'global': 13}
    ['amazon.titan-embed-image-v1', 'amazon.titan-embed-text-v2:0', 'cohere.embed-english-v3', 'cohere.embed-multilingual-v3']

**say this:** *"Titan Text Embeddings v2 produced 2,060 real 1,024-dimension vectors in Sydney;
they are loaded into CockroachDB `VECTOR(1024)` columns and searched through a C-SPANN index
with both prefix columns bound. When a second embedding model turned out not to be servable
in-region without cross-region routing, we published the refusal and the request id rather
than switching to the global profile."*
**never say:** *"End-to-end Australian data residency."* `docs/submission/MUST-NOT-CLAIM.md`
§1 forbids it and states the true version: inference in Sydney `ap-southeast-2`, database in
Singapore `aws-ap-southeast-1`, because `ap-southeast-2` is Advanced-tier only on CockroachDB
Cloud. Also never quote the manifest as proof of the vectors themselves: **the corpus is
synthetic and the vector blobs live under a gitignored `out/`**, so the per-vector sha256 is
the checkable part.

---

### R3 · Amazon CloudWatch — the read-only `AWS/Bedrock` metric census

**state:** REPO
**what it is:** **110 `GetMetricStatistics` calls** against the `AWS/Bedrock` namespace in
`ap-southeast-2`, reading AWS's own counters back over this project's own model usage —
7,542 `Invocations` and 1,026,175 `InputTokenCount` for `amazon.titan-embed-text-v2:0`. **Each
Sum is taken at `Period` 300 and again at 3600 and required to agree**, because a Sum is
resolution-invariant and a disagreement would mean a clipped bucket.
`evidence/aws/cloudwatch/reconciliation.json` then subtracts this repository's own token
ledgers from AWS's counters and names every non-zero delta.
**this is the row the prior census gets wrong.** `evidence/tool-usage/aws-services.json` files
all of this under a single `aws_cloudwatch` row titled *"logs, four alarms, one dashboard"*.
Three things are wrong with that: the reading and the provisioning are **different services
used in different ways in different regions on different days**, there are **seven** alarms,
and the reader **provisioned nothing at all**.
**where:** `scripts/aws/cloudwatch_evidence.py:299` — `_guard`, registered on `before-call` for
every client the program builds, which **raises `ReadOnlyViolation` for any operation outside a
six-item allow-list before the request is signed**.
**verify in 60s:**

    python -c "import json;p=json.load(open('evidence/aws/cloudwatch/bedrock-metrics.json',encoding='utf-8'))['payload'];print(p['api_call_summary']);print(p['prohibitions'])"

first line
`{'DescribeAlarms': 1, 'GetCallerIdentity': 1, 'GetMetricStatistics': 110, 'GetModelInvocationLoggingConfiguration': 1, 'ListDashboards': 1, 'ListMetrics': 1}`,
and the prohibitions block asserts `alarms_created: false`, `dashboards_created: false`,
`log_groups_created: false`, `metric_filters_created: false`,
`models_invoked_by_this_program: false`, `terraform_apply_run: false`.
**say this:** *"We reconciled our own token accounting against AWS's counters and published
every place they disagree — the total AWS bill for the whole fleet is **USD 0.110479** across
6 models and 8,247 invocations, taken from AWS's numbers rather than ours, because when two
sources disagree about what you spent the honest one is the one that is not you."*
**never say:** that this reader provisioned or invoked anything. Its allow-list is enforced
before the request is signed, and the artefact records the complete call log.

---

### R4 · AWS Service Quotas and Lambda account settings — the number every threshold divides by

**state:** REPO
**what it is:** read-only `lambda get-account-settings` and
`service-quotas get-service-quota --service-code lambda --quota-code L-B99A9384`, in **both**
regions this project touches. Both return **10** concurrent executions, `Adjustable: true`.
That single measured number is what every reachability precondition in two Terraform modules
divides by, and it is what falsified a shipped alarm threshold of 20.
**where:** `evidence/deploy/verify/alarm-reachability.json` → `account_facts_measured`;
consumed as `var.account_concurrency_ceiling` in `infra/envs/demo/main.tf:393` and `:640`,
passed to **both** modules from one variable so they cannot hold different ideas of the quota.
**verify in 60s:**

    python -c "import json;print(json.dumps(json.load(open('evidence/deploy/verify/alarm-reachability.json',encoding='utf-8'))['account_facts_measured'],indent=1))"

first key `lambda_get_account_settings_ap_southeast_1` with `AccountLimit.ConcurrentExecutions: 10`.
**say this:** *"The cost bound is arithmetic over a measured account quota, not a guess: the
account ceiling is 10, we read it from two different AWS APIs in two regions, and Terraform
refuses at plan time to create any alarm whose threshold sits above what that ceiling makes
physically reachable."*
**never say:** *"We capped concurrency."* We did not and could not — AWS refuses every
positive reservation on an account whose ceiling is 10, so
`reserved_concurrent_executions = -1` is the only value that applies. The quota is
`Adjustable: true` and every dollar of the modelled worst case is linear in it;
`docs/deploy/COST-BOUND.md` is the standing warning against raising it.

---

### R5 · Policy-as-code over the Terraform plan — the S3/KMS custody gate that actually runs

**state:** REPO
**what it is:** **15 rules** — `OL-1…OL-5` (Object Lock), `IAM-1`, `IAM-2`, `KMS-1…KMS-4`,
`GT18-1`, `GT18-2` (single checkpoint bucket), `PLAN-1` (plan legibility) and `DESTROY-1` —
evaluated against `tofu show -json` plan documents. It is stdlib-only, needs nothing installed,
and it carries **16 committed fixtures**: one compliant plan that must pass all 15, and 15
deliberately-broken ones each of which must be refused **by the rule that declares it**.
**where:** `scripts/custody/check_evidence_plan.py`; fixtures at
`infra/policy/custody/fixtures/`; CI lane `.github/workflows/custody-chain.yml`.
**verify in 60s:**

    python scripts/custody/check_evidence_plan.py

    PASS OL-1      bucket-object-lock-at-creation  [compliant fixture]
    ...
    selftest OK — 15 rules — the compliant plan passes all of them and 15 deliberately-broken
    fixtures are each refused by the rule that declares them

exit `0`. Runs in about a second, with no cloud account.
**say this:** *"The custody controls on S3 Object Lock and the KMS signing key are enforced as
policy over the Terraform plan, and the gate has been observed refusing a broken plan for each
of its fifteen rules. A check that has never been red asserts nothing."*
**never say:** *"OPA/conftest enforces this."* **`infra/policy/custody/object_lock.rego` and
`kms_custody.rego` have never been executed** — 596 lines of Rego, and the file's own header
says so at line 22: `opa` is not installed on the machine they were written on, they have
never been run against the compliant fixture or the broken ones, and they are a specification
in the customer's dialect until a CI lane runs `conftest test` green. The **Python** gate is
the one with no caveat.

---

### R6 · AWS Cost Explorer and AWS Budgets — read-only, and the reason the guard exists

**state:** REPO
**what it is:** two read-only control-plane reads against the live account on **2026-08-12**,
by a worker who ran no apply and no write:

* `aws ce get-cost-and-usage --time-period Start=2026-05-01,End=2026-08-13 --granularity
  MONTHLY --metrics UnblendedCost --group-by Type=DIMENSION,Key=SERVICE` — four months of
  per-service spend, from which two facts fall out. **`AWS Lambda` is absent as a line item in
  every month** — the one function that existed on this account had never been billed. And
  Bedrock month-to-date reads **USD 0.1241**, against the **USD 0.00006** this repository's own
  probe accounting recorded, a gap the artefact declines to attribute rather than explain away.
* `aws budgets describe-budgets` and `describe-budget-actions-for-budget` — **three budgets,
  every one permanently in `ALARM`, `0` actions between them.**

**why it is a row and not a footnote:** the budget in §2 A2 is USD 25.00 wired to a stop topic.
Without this read that is a design assertion. With it, it is a correction of a measured
failure: the account already had three budgets that alarm forever and stop nothing, and the
one this project applied is the only one on the account with an action behind it.
**where:** `evidence/deploy/verify/aws-quota-and-cost.json` → `part_2b_the_budget`,
`part_4_account_spend_context`; the discipline block at the head of the same file records
`terraform_apply_run: false`, `aws_writes_run: false`, `credentials_printed: false`.
**verify in 60s:**

    python -c "import json;d=json.load(open('evidence/deploy/verify/aws-quota-and-cost.json',encoding='utf-8'))['part_2b_the_budget'];print(len(d['budgets']),'budgets');print([b['BudgetLimit_usd'] for b in d['budgets']]);print('actions:',d['budget_actions_across_all_three'])"

    3 budgets
    [10.0, 5.0, 1.0]
    actions: 0

**say this:** *"Before we wrote a budget we read the account's existing ones. There were
three, all of them permanently breached, none of them attached to a single action. Ours is
scoped to three services, evaluates ACTUAL cost with credit excluded, and publishes to a topic
whose only subscriber turns the demo off."*
**never say:** that we monitor spend continuously, or that any figure here is live. It is a
reading taken on **2026-08-12** and it has not been retaken. The account id is masked in the
artefact (`0229REDACTED8246`) and no credential appears in it.

---

## 4 · DECLARED — written, Terraform-valid, and never created

### D1 · Amazon CloudFront + Origin Access Control — **ruling R3, and the most dangerous row in this submission**

**state:** DECLARED
**what it is:** one distribution with **two** Origin Access Controls — one `s3`, one `lambda`,
both `signing_behavior = "always"` — that would front the private console bucket and the
`/v1/*` Lambda Function URL from a single hostname, with the Function URL then able to keep
`AWS_IAM` authorisation instead of `NONE`.

**AWS refused to create it.** A real `terraform apply` on **2026-08-10** created seven
resources and refused the eighth. The transcript is committed at
`infra/envs/demo/main.tf:37–52` and is quoted here verbatim, with only the leading `# `
comment markers of that file removed. *(The lead plan cites this passage as lines 38–52; both
are right — the sentence that introduces it begins on line 37 and the word "wrong." lands on
38. Quote whichever; the transcript itself is lines 41–45.)*

> is allowed to be able to take the URL down. The reasoning was right and the premise was
> wrong. A real `terraform apply` on 2026-08-10 created seven resources and AWS refused the
> eighth:
>
>     Error: creating CloudFront Distribution: operation error CloudFront:
>     CreateDistributionWithTags, https response error StatusCode: 403,
>     RequestID: 3e63e30d-8c5b-441b-a01b-b70085eba504, AccessDenied:
>     Your account must be verified before you can add new CloudFront resources.
>     To verify your account, please contact AWS Support and include this error message.
>
> The same refusal comes from a bare `aws cloudfront create-distribution` with a minimal
> config and no Terraform involved, from an identity holding `AdministratorAccess`. It is
> an ACCOUNT-LEVEL VERIFICATION HOLD ON NEW CLOUDFRONT RESOURCES — the account already has
> one distribution from an unrelated project, created 2026-04-16, so the hold is on new
> ones and not on the service. Only AWS Support can lift it, and the submission deadline
> is 2026-08-18.

**Decision D1** (`docs/leads/ship-final.md` §1.4) inverted the default in response: **the API
owns the hostname and the site is optional**, so nothing could hold the URL hostage. A Lambda
Function URL is HTTPS on an AWS-issued certificate, needs no account verification, no ACM and
no hosted zone, and one origin serving both the SPA and `/v1/*` means no CORS and one string
in the submission form.

Two consequences propagate out of that one AWS account setting, and both are visible in this
census rather than hidden:

* the Function URL carries `authorization_type = "NONE"` — there is no distribution, therefore
  no principal to grant `lambda:InvokeFunctionUrl` to;
* `module.api[0].aws_lambda_permission.cloudfront_invoke` is `count = 0` and is **absent from
  the plan**, not present and inert. The eleven `module.api[0]` addresses in
  `evidence/deploy/cost/plan-shape.json` contain no `aws_lambda_permission`.

**where:** `infra/modules/demo-site/main.tf:299` (distribution), `:273` and `:286` (the two
OACs); transcript at `infra/envs/demo/main.tf:37–52`; runbook at `docs/deploy/RUNBOOK.md:26`
and its Appendix A. Decision D1 is `docs/leads/ship-final.md:112` — *"§1.4 CloudFront cannot be
created on this account — the architecture must change"*.
**verify in 60s:**

    sed -n '37,52p' infra/envs/demo/main.tf

sixteen lines. The first is
`# is allowed to be able to take the URL down. The reasoning was right and the premise was`,
the fifth is `#     Error: creating CloudFront Distribution: operation error CloudFront:`, and
the last is ``# is 2026-08-18. `docs/deploy/RUNBOOK.md` line 26 carries the transcript.``
Then:

    python -c "import json;print([r['type'] for r in json.load(open('evidence/deploy/cost/plan-shape.json',encoding='utf-8'))['resources']['module.api[0]']])"

— no `aws_cloudfront_*` anywhere in the 24-resource shipping plan.
**say this:** *"The CloudFront distribution and both Origin Access Controls are written and
Terraform-valid, and `terraform plan` builds them: 35 resources with the flag on against 24
with it off. **AWS holds new CloudFront resources on this account pending verification** — a
403 we reproduced from a bare CLI call under AdministratorAccess — so decision D1 gave the
hostname to the Lambda Function URL, and nothing in this stack can hold the demo URL
hostage."*
**never say:** *"CloudFront serves the demo."* *"Behind CloudFront."* *"CDN-fronted."* *"Our
CDN."* **Any sentence implying CloudFront is in the request path is false**, and it is the
single easiest claim in this submission for a judge to falsify: one `dig` on the demo
hostname, or one look at the URL, settles it. W7 must diff the close block against this
paragraph specifically.

---

### D2 · Amazon S3 — the private demo-site bucket

**state:** DECLARED
**what it is:** seven resources for a **private** origin bucket: public access blocked on all
four settings (**including `ignore_public_acls`, the one people forget** — it is what
neutralises an ACL somebody else attaches), `BucketOwnerEnforced` so ACLs are off entirely,
versioning on, SSE-S3, and a lifecycle rule expiring noncurrent versions and aborting
incomplete multipart uploads at 7 days. It has never existed: it lives inside `module.site`,
whose `count` is `0` because `var.enable_cloudfront` is `false`.
**where:** `infra/modules/demo-site/main.tf:182, 195, 206, 217, 229, 244`; policy at `:503`.
**verify in 60s:**

    grep -c 'resource "aws_s3_bucket' infra/modules/demo-site/main.tf

prints `7`; then `grep -n 'module "site"' -A2 infra/envs/demo/main.tf` shows
`count = var.enable_cloudfront ? 1 : 0`.
**say this:** *"The static console has a private-origin S3 design that is written and planned
and was never applied, because the distribution that would have signed requests to it cannot
be created on this account. The console is served from the Lambda package instead."*
**never say:** *"We host the console on S3."* We do not. `GET /` on the live origin returns
bytes **from the deployment zip** — that is W1's row, and this bucket has never held an object.

---

### D3 · Amazon S3 + Object Lock (COMPLIANCE) — the evidence store

**state:** DECLARED
**what it is:** the checkpoint bucket for the tamper-evident ledger. `object_lock_enabled =
true` **at bucket creation** — which is the whole one-shot: `aws_s3_bucket_object_lock_
configuration` alone does *not* enable Object Lock on a bucket created without it, and there
is no API that retrofits it. Default retention is **COMPLIANCE mode**, which even the account
root cannot shorten. `prevent_destroy = true` on every resource in the module.
**where:** `infra/modules/evidence-store/main.tf:74` (`object_lock_enabled = true`), `:100`
(the COMPLIANCE rule), `:89`, `:113`, `:122`, `:132`, `:335`; root at `infra/envs/evidence/`,
the stack `10-indelible`.
**verify in 60s:** `sed -n '74,111p' infra/modules/evidence-store/main.tf` — first line
`resource "aws_s3_bucket" "evidence" {`, and `mode = "COMPLIANCE"` at `:105`.
**say this:** *"The evidence store is a COMPLIANCE-mode Object Lock bucket in a separate
account, written with `prevent_destroy` on every resource, and its rules are enforced as
policy over the plan before anything is applied (§3, R5). It has not been created."*
**never say:** *"Our evidence is under Object Lock."* It is not, and the exact size of the gap
is published rather than glossed. Offline bundle verification exits **`2`** — meaning
*everything that ran held, and at least one check did not run* — with **16 checks, 9 passed,
0 failed, 7 not checked** (`qa/test-state.json` →
`external_checks.custody_bundle_verification`). Check **8** `archive_object_lock` is one of the
seven, and `evidence/CUSTODY_ATTACK_MATRIX.md:80` carries its words verbatim:
`SKIP(offline: --s3 not given; archive metadata is a claim by us [nemesis-local fallback;
trappoint-verify has no runner for check 8 yet])`. In the same matrix, attack **A15**
`object_lock_downgrade` is **the one attack of fifteen that was not executed** — `SKIP(no-credentials)`,
`Latency: not run` — recorded as a row rather than dropped from the table. That honesty is the
asset; do not spend it.

    python -c "import json;c=json.load(open('qa/test-state.json',encoding='utf-8'))['external_checks']['custody_bundle_verification'];print(c['exit_code'],c['counts']);print([n['name'] for n in c['not_checked']])"

    2 {'failed': 0, 'not_checked': 7, 'passed': 9, 'total': 16}
    ['log_signature', 'rfc3161_upper_bound', 'beacon_lower_bound', 'witness_quorum', 'archive_object_lock', 'gate_self_attestation', 'webauthn_reverification']

---

### D4 · AWS KMS — an `ECC_NIST_P256` `SIGN_VERIFY` key

**state:** DECLARED
**what it is:** one asymmetric signing key for transparency-log checkpoints, plus an alias.
Three design choices are each load-bearing and each checked by a rule in §3's gate:
`enable_key_rotation = false` (AWS cannot rotate an asymmetric key at all, so `false` is the
only truthful value — and a rotated signing key silently invalidates historical
verification); `deletion_window_in_days = 30`, the **maximum**, because the window is the only
time anyone has to notice a scheduled deletion and cancel it; and a key policy that denies
`kms:ScheduleKeyDeletion` outside a break-glass role, because **crypto-shredding is document
destruction**.
**where:** `infra/modules/evidence-store/main.tf:477` (key), `:501` (alias), policy document
above it; the signer at `packages/trappoint-ledger/src/trappoint_ledger/signer.py:63`
(`KMS_SIGNING_ALGORITHM = "ECDSA_SHA_256"`, `MessageType=RAW` so KMS hashes the message
itself).
**verify in 60s:** `sed -n '477,504p' infra/modules/evidence-store/main.tf` — carries
`key_usage = "SIGN_VERIFY"`, `customer_master_key_spec = "ECC_NIST_P256"`,
`enable_key_rotation = false`, `deletion_window_in_days = 30`, `prevent_destroy = true`.
**say this:** *"The checkpoint signing key is specified as an asymmetric P-256 KMS key whose
destruction is denied outside a break-glass role, and four separate rules in a gate that has
been observed refusing each of them enforce that specification before an apply."*
**never say:** *"Checkpoints are signed by KMS."* **No key exists.** The signer is implemented
against an **injected client** and unit-tested offline; the live KMS signature check is one of
the seven cryptographic checks that did not run. The prior census reads `DESIGNED` for this
row and that reading is **confirmed by measurement, not merely carried forward**.

---

### D5 · AWS CloudTrail — custody of the custodian

**state:** DECLARED
**what it is:** one multi-region trail with `enable_log_file_validation = true` and **two
advanced event selectors** — all Management events, plus **Data** events narrowed by
`resources.ARN starts_with` the checkpoint bucket. The design point is unusually good and
worth stating: log-file validation produces **AWS's own signed digest chain** over the same
events, which is *weaker* than ours because AWS holds the key — **and useful for exactly that
reason: it is a chain we could not have forged.**
**where:** `infra/envs/evidence/main.tf:114–166`. Three accounts, not two: the application
account writes checkpoints, the evidence account holds them, the log-archive account records
who touched either.
**verify in 60s:**

    grep -rn 'resource "aws_cloudtrail"' infra --include=*.tf

single line `infra/envs/evidence/main.tf:114:resource "aws_cloudtrail" "evidence" {`.
**say this:** *"CloudTrail is specified into a third account with log-file validation on, so
that AWS produces an independent signed digest chain over the same events — deliberately one
we could not forge. It is written and has not been applied; **no trail exists in the
account**."*
**never say:** *"CloudTrail records our custody events."* **Nothing is recorded.** The prior
census reads `DESIGNED` and that is **confirmed by measurement**: one resource, one root
module, zero applies. `infra/envs/evidence/` has never been applied at all — it is also the
root whose OpenTofu `terraform { encryption { … } }` block is **absent and declared absent**
(`main.tf:32–40`), because HashiCorp Terraform 1.14 — the only validator on the build machine
— rejects it as an unsupported block type.

---

### D6 · Amazon EventBridge — **the weakest row in this census, and it is corrected downward**

**state:** DECLARED *(and it should probably not appear in the close block at all)*
**what it is:** the custody patrol and the steward's periodic sweeps are *described* as
scheduled invocations, and one YAML comment names EventBridge as the source of an
`occurrence_ts`.
**where:** `verticals/mainline/apps/steward/schedules.yaml:14` — a comment. **That is all
there is.**
**verify in 60s:**

    grep -rn "aws_cloudwatch_event\|aws_scheduler" infra --include=*.tf

**no output, exit 1.** There is no rule, no bus, no schedule and no target anywhere under
`infra/`.
**the correction:** every other `DECLARED` row above is a **real Terraform resource** that
`terraform plan` will build — CloudFront plans, S3 plans, KMS plans, CloudTrail plans. This one
is not. Today the schedule is a **container entrypoint**, not an EventBridge rule. Grouping it
with the other four flatters it.
**say this:** if it is said at all — *"Scheduled patrol runs are designed for EventBridge and
currently run from a container entrypoint. There is no EventBridge resource in the tree."*
**never say:** *"We use EventBridge."* **W7's recommendation from this desk: drop this row from
the close block.** It is the one line in the AWS list a judge could falsify with a single grep,
and the list is strong enough without it. Keeping a row we cannot defend costs more than the
logo is worth.

---

## 5 · NOT-AVAILABLE — checked, absent, and kept

### N1 · Amazon Bedrock Rerank

**state:** NOT-AVAILABLE
**what it is:** not offered in `ap-southeast-2`. The live control-plane census in
`evidence/aws/probe/model-availability.json` enumerates the **64 foundation models** and **29
inference profiles** that *are* offered, and Rerank is not among them.
**where:** `docs/HONESTY.md:1123` records the absence in a table row —
*"Bedrock Rerank in `ap-southeast-2` | **not available.** No dependency was taken on it"*; the
design that stood in for it is
`verticals/mainline/packages/mainline-recall-agent/src/mainline_recall_agent/rerank/listwise.py:77`.
**verify in 60s:**

    grep -ci "rerank" evidence/aws/probe/model-availability.json

prints `0` — the live control-plane listing offers no reranker at all.
**say this:** *"Bedrock Rerank is not offered in our region. We checked, we published the
control-plane listing that shows it, and we took no dependency on it — listwise reranking runs
on the Claude profile at high effort instead, and CockroachDB's own
`vector_search_rerank_multiplier` governs the ANN side."*
**never say:** that we *chose* not to use it after evaluating it. We could not have used it.
**This row is a credibility asset and it stays.** A services list that omits what you checked
and could not have is a list a judge cannot audit — and the row is cheap, because the
absence cost nothing: listwise reranking was designed onto the Claude profile *before* the
availability was checked.

---

## 6 · CORRECTIONS THE GENERATOR SHOULD ABSORB (ruling R6)

`evidence/tool-usage/aws-services.json` has **12 rows** and is the file `docs/TOOL-USAGE.md`
and the `claims.yml` / `submission.yml` ratchets read. Per **R6** these are proposed as prose
plus an exact detector, for a follow-up to add to
`scripts/submission/capture_tool_evidence.py`. **Nothing here edits the generator, weakens a
ratchet, or touches `HONESTY.md`, `CI-STATE.md` or `MUST-NOT-CLAIM.md`.**

| # | proposed key | state | detector |
|---|---|---|---|
| 1 | `aws_sns` | APPLIED | `grep -c 'resource "aws_sns_topic"' infra/modules/cost-guard/main.tf` = 1, plus the 13 addresses in `evidence/deploy/cost/plan-shape.json#/resources/module.guard[0]` |
| 2 | `aws_budgets` | APPLIED | `grep -c 'resource "aws_budgets_budget"' infra/modules/cost-guard/main.tf` = 1; limit from `variables.tf` `budget_limit_usd` default |
| 3 | `aws_cloudwatch_alarms` | APPLIED | `len(plan-shape.json#/alarms)` = **7** — split out of today's `aws_cloudwatch` row, whose title says "four alarms" |
| 4 | `aws_cloudwatch_dashboard` | APPLIED | `sed -n '841,978p' infra/modules/demo-api/main.tf \| grep -cE '^\s+type\s+='` = 5 widgets |
| 5 | `aws_lambda_cost_guard` | APPLIED | second `aws_lambda_function` — `grep -rn 'resource "aws_lambda_function"' infra --include=*.tf` returns 2 |
| 6 | `aws_s3_tfstate` | APPLIED | `evidence/deploy/APPLIED.md:23–25`; `grep -n 'use_lockfile' infra/envs/demo/backend.tf` |
| 7 | `aws_service_quotas` | REPO | `alarm-reachability.json#/account_facts_measured/service_quota_L_B99A9384_ap_southeast_1/Value` = 10.0 |
| 7b | `aws_cost_explorer` | REPO | `aws-quota-and-cost.json#/part_4_account_spend_context/command` is a real `aws ce get-cost-and-usage`; `#/part_2b_the_budget/budget_actions_across_all_three` = **0** across **3** pre-existing budgets. §3, R6 |
| 8 | *(amend)* `aws_cloudwatch` | REPO | keep the read-only metric census; **retitle** — it currently claims alarms it does not measure and undercounts them |
| 9 | *(amend)* `aws_eventbridge` | DECLARED, downgraded | detector is the **absence** grep in §4 D6; the basis line should state that no Terraform resource exists |
| 10 | *(amend)* `aws_cloudfront` | DECLARED | the existing basis is correct and complete; only the verdict word changes, `DESIGNED` → `DECLARED` under R2 |

**Confirmed by measurement and left exactly as they are:** `aws_bedrock_runtime`,
`aws_bedrock_embeddings`, `aws_bedrock_rerank`, `aws_s3_object_lock`, `aws_kms`,
`aws_cloudtrail`. The brief asked whether the last three, marked `DESIGNED`, are right. **They
are.** One `aws_cloudtrail` resource, one KMS key, one Object Lock configuration, zero applies
— checked today by the greps in §4, D3–D5.

---

## 7 · OPEN QUESTIONS FOR THE FOUNDER (ruling R7 — escalated, not guessed)

1. **The topic-policy hazard is unresolved and it is visible in the evidence.** The guard's SNS
   topic policy admits `cloudwatch.amazonaws.com` under an `ArnLike` naming exactly the guard's
   **own three** alarm ARNs. **None of the demo-api's four alarms is in that list**, and the
   root module wires the topic into all four of them. Whether they can publish rests on the
   policy's first statement — SNS's default idiom, `Principal AWS:*` narrowed by
   `AWS:SourceOwner` — and **no plan can settle it; it takes a real breach on a real apply.**
   Both outcomes are defects and they are opposite: *admitted* converts three health signals
   into self-inflicted outages; *denied* leaves four alarms carrying an action SNS refuses,
   which `describe-alarms` renders identically to a delivered one. Recorded at
   `evidence/deploy/cost/plan-shape.json` → `open_hazard_topic_policy_source_arn`. **The stated
   resolution is neither obvious option** — not unwiring the alarms, not widening the
   principal, but giving `cost-guard` an explicit additional-publisher list. **That is a code
   change and an apply. Out of scope by construction.**
2. **Does the founder want the CloudFront row in the film at all?** It is honest as written and
   it reads as strength. It is also the row most likely to be misheard. This desk's view: keep
   it in the written census, and in the film say only *"AWS holds new CloudFront on this
   account, so the Lambda Function URL owns the hostname"* — one sentence, no visual.
3. **The EventBridge row.** §4 D6 recommends dropping it from the close block. That is a
   founder-facing editorial call, not a measurement.
4. **Nobody has read the applied stack back.** `scripts/deploy/post_apply_verify.py` exists,
   declares **9** checks including an alarm inventory, an alarm-visibility probe and a live
   kill-switch stop/restore, and **has never been run against the applied account** — its one
   artefact is a dry run taken before the apply, `0 of 9`, `NOT SATISFIED`. Running it needs a
   working `terraform init -backend-config` and the credential, and the live kill-switch legs
   would deliberately **stop the demo** and require a human restore. **Out of scope by
   construction, and the founder's call whether to spend a demo outage on it before
   2026-08-18.** The safe half — `--kill-switch dry` plus the alarm inventory, with no stop —
   would turn every `APPLIED` row in §2 from "the apply says so" into "the account says so",
   and that is a Production-Readiness upgrade for a few minutes of read-only calls.

5. **`docs/HONESTY.md:1120` carries a clause the 2026-08-14 apply falsified, and this desk may
   not fix it.** The row reads:

       | What that verdict does **not** cover | S3, KMS, CloudTrail, Lambda, CloudFront, IAM
       roles, SSM Parameter Store, EventBridge — and CloudWatch as provisioned infrastructure
       rather than as metrics read back. All still DESIGNED; `terraform apply` has never been
       run |

   **`terraform apply` has been run.** `evidence/deploy/APPLIED.md:14` — *24 created, 0
   changed, 0 destroyed* — and Lambda, IAM, SSM and CloudWatch-as-infrastructure are all in
   the account. The list's *other* members are still accurate: S3-as-evidence-store, KMS,
   CloudTrail, CloudFront and EventBridge remain uncreated. So the fix is one clause, not the
   row. This matters more than a normal stale line because of **where it is**: a document
   called `HONESTY.md` is the first place a sceptical judge goes to test whether the project's
   self-description survives contact, and the one sentence there that is out of date is a
   sentence that under-claims. **Standing prohibition 6 forbids this worker from editing
   `HONESTY.md`.** Escalated verbatim, with the replacement clause a maintainer could paste:
   *"All were DESIGNED when this row was written; the apply of 2026-08-14 created Lambda, IAM,
   SSM and CloudWatch — S3-as-evidence-store, KMS, CloudTrail, CloudFront and EventBridge are
   still DESIGNED."* **Verify in 20 s:** `sed -n '1120p' docs/HONESTY.md` beside
   `sed -n '14p' evidence/deploy/APPLIED.md`.

**Untouched, as instructed:** the standing `materialise_checks` / `exposure_receipt` INSERT
gap. Widening the write surface of an unauthenticated endpoint is the founder's call and he
has not made it.

---

## 8 · WHAT THIS WORKER DID NOT DO

* **No `terraform apply`, no `terraform` at all**, no redeploy, no AWS API call of any kind, no
  SSM read or write. Every AWS fact above was read out of a committed artefact or out of the
  Terraform source.
* **No credential was read, echoed or printed.** No account id appears in this file.
* **No commit.** One file was written: `docs/submission/census/aws-repo-and-infra.md`.
* **No ratchet was touched.** `continue-on-error` and `|| true` appear nowhere in it.
* **No regression is possible from this change**, and that is checkable rather than asserted.
  The two documentation ratchets that scan `docs/submission/` use **explicit path allowlists**,
  not directory sweeps (`tests/deploy/test_cost_model.py:119–126`,
  `tests/deploy/test_docs_are_true.py:1361–1371`), and the submission prose scanner's target
  glob is `docs/submission/*.md` — **single level**
  (`scripts/submission/check_submission_prose.py:60–64`), which does not match
  `docs/submission/census/`. No test collects this path. `DEFAULT_MAX_RESPONSE_BYTES`, the
  console bundle-headroom guard, the gate proof and the 1070/1069/0/0 baseline are all
  untouched by a new markdown file in a directory nothing reads yet.
* **Three verifiers were run, read-only, and all three are green today** — see §9.

---

## 9 · PROVENANCE — every command this worker ran, and what it printed

Run on 2026-08-16 against the tree at `5f57146`, on Windows, with
`D:/CoackroachDBxAWS/mainline/.venv/Scripts/python.exe`. **None of them opens a socket to AWS,
reads a credential, or writes anything outside this one markdown file.** A judge can paste
any of them.

| # | command | first line / verdict | exit |
|---|---|---|---|
| 1 | `python scripts/aws/verify_evidence.py` | `1235 assertions across 40 of 40 declared invariants. PASS` | 0 |
| 2 | `python scripts/custody/check_evidence_plan.py` | `PASS OL-1 bucket-object-lock-at-creation [compliant fixture]` … `selftest OK — 15 rules` | 0 |
| 3 | `python scripts/aws/agent_live.py --verify` | 7 cassette lines, all `ok`; `replay hashes equal: True`; `verdict: PASS` | 0 |
| 4 | `grep -rn "boto3\|bedrock" verticals/mainline/apps/demo-api/src/ --include=*.py` | 3 hits, **all comments** (§3 preamble) | 0 |
| 5 | `grep -rn "aws_cloudwatch_event\|aws_scheduler" infra --include=*.tf` | *no output* — §4 D6 | **1** |
| 6 | `grep -c "precondition {" infra/modules/demo-api/main.tf infra/modules/cost-guard/main.tf` | `7` and `5` | 0 |
| 7 | `grep -rn 'resource "aws_lambda_function"' infra --include=*.tf` | 2 hits: `cost-guard/main.tf:469`, `demo-api/main.tf:326` | 0 |
| 8 | `grep -c 'resource "aws_s3_bucket' infra/modules/demo-site/main.tf` | `7` | 0 |
| 9 | `grep -ci "rerank" evidence/aws/probe/model-availability.json` | `0` | **1** |
| 10 | `sed -n '841,978p' infra/modules/demo-api/main.tf \| grep -cE '^\s+type\s+='` | `5` | 0 |
| 11 | the `plan-shape.json` alarm dump in §2 A3 | `7`, then 7 rows ending `missing` | 0 |
| 12 | the `region` census in §0 | `24` of `24` artefacts in `ap-southeast-2` | 0 |
| 13 | the `qa/test-state.json` custody dump in §4 D3 | `2 {'failed': 0, 'not_checked': 7, 'passed': 9, 'total': 16}` | 0 |
| 14 | the `aws-quota-and-cost.json` budget dump in §3 R6 | `3 budgets` / `[10.0, 5.0, 1.0]` / `actions: 0` | 0 |

Rows **5** and **9** exit non-zero **on purpose**: they are the two claims in this census that
are *absences*, and `grep` reports an absence as exit 1. A reader who sees a `0` there should
be suspicious of the claim, not reassured.

**Five corrections were made to this file's own earlier draft on the strength of those runs,
and they are listed rather than silently absorbed:** the cost-guard defaults grep prints 22
lines and not 12; the IAM grep in §2 A6 returns six lines whose *first* is a comment at `:51`,
not the sid at `:428`; `agent_live.py --verify` prints a cassette table and `verdict: PASS`,
not a field called `entries_checked`; the `backend "s3"` block opens at `:94`, not `:95`; and
the alarm-dump command did not print the period column its own table claimed. A census that
cannot survive its own verification commands is worth less than no census.
