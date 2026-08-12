<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: CC-BY-4.0
-->

# W5 — Alarms that can fire, and the plan replayed against its own evidence

**Worker:** W5, deploy-verification pass. **Date:** 2026-08-12.
**Scope:** (1) re-run `init` / `validate` / `plan` / `show` and diff the result against
`evidence/deploy/terraform-plan-furl.{txt,json}`; (2) decide, for each of the four
CloudWatch alarms, whether it can actually fire and whether anybody reads it.

**No `terraform apply` was run.** `init`, `validate`, `plan`, `show` and read-only AWS
describe calls only. All fresh plan artefacts were written to a scratch directory outside
the repository; nothing under `evidence/deploy/` was overwritten. The AWS account id is
masked as `0229REDACTED8246` throughout, and no credential appears anywhere in this pass.

Raw evidence: [`evidence/deploy/verify/plan-replay-diff.txt`](../../../evidence/deploy/verify/plan-replay-diff.txt)
and [`evidence/deploy/verify/alarm-reachability.json`](../../../evidence/deploy/verify/alarm-reachability.json).

---

## The three sentences that matter

1. **The committed plan is real.** A fresh plan on this machine today is *byte-identical*
   to `terraform-plan-furl.json` once the account id is masked, the plan timestamp is
   normalised, and `relevant_attributes` is compared as the unordered set it is. Eleven
   resources, all `create`, **zero attribute drift**. The Lambda package has not drifted
   either: the planned `source_code_hash` equals `filebase64sha256` of the zip on disk.
2. **Three of the four alarms can fire. One cannot, ever.** `errors`, `throttles` and
   `duration_p99` are reachable. `mainline-demo-api-concurrency` breaches above **20**
   concurrent executions on an account whose Lambda concurrency ceiling is **10**. It is
   unfirable by arithmetic, and separately unfirable because the metric will not be
   emitted. It is decoration.
3. **Nobody reads any of them.** `alarm_actions` is empty, so nothing is notified; and the
   repository is public with **zero secrets, zero variables, zero environments**, the AWS
   account trusts **no** GitHub OIDC provider, and `demo-health.yml` contains no CloudWatch
   call at all. The module states in four places that the hourly workflow reads the alarms
   with `describe-alarms`. It does not, and it cannot.

---

## 1 · Plan replay

### 1.1 What was run, and what came back

`terraform init -backend=false` succeeds and `terraform validate` reports
`Success! The configuration is valid.` — but **`terraform plan` immediately afterwards
fails**, both in the repository and in a clean copy of `infra/` carrying nothing but the
committed lock file:

```
Error: Backend initialization required, please run "terraform init"
Reason: Initial configuration of the requested backend "s3"
```

This is not a defect. `docs/deploy/terraform-plan.md` already records it, in the paragraph
headed *"Why a temporary local backend was used"*: Terraform v1.14.8 refuses `plan` when a
declared backend has never been initialised. I reproduced it twice from a clean directory,
which confirms the documentation. The only wrinkle worth a one-line fix is that the
four-command block printed at the top of that same page is **not runnable as printed** —
the paragraph twenty lines below it is the operative instruction.

With the documented throwaway local backend override (state redirected to a scratch path,
**no S3 object created, read, written or locked**), the plan runs clean:

```
Plan: 11 to add, 0 to change, 0 to destroy.        ← line 339, fresh AND committed
```

### 1.2 The diff

| | committed | fresh |
|---|---|---|
| `resource_changes` | 11 | 11 |
| action set | `{create: 11}` | `{create: 11}` |
| update / delete / replace | 0 / 0 / 0 | 0 / 0 / 0 |
| `terraform_version` | 1.14.8 | 1.14.8 |
| `applyable` / `complete` / `errored` | true / true / false | true / true / false |

**JSON: byte-identical modulo mask.** Normalising only the account id (live → mask, never
the reverse), the plan `timestamp`, and `relevant_attributes` (32 entries each side,
set-equal, order randomised per run), the canonical SHA-256 of *everything else* is the
same string on both sides:

```
committed  d88bb44244e6eeeb88905944037452378666d3185a1007b34a08d7775543529b
fresh      d88bb44244e6eeeb88905944037452378666d3185a1007b34a08d7775543529b
```

**Not one attribute differs.**

**Text: two differences, both run-to-run noise.** (a) the interleave of the five concurrent
data-source `Reading...` lines at the top — same five sources, different order, because
Terraform walks them in parallel; (b) the `Saved the plan to:` trailer, which names a
different plan file. Lines 8 through 371 — every resource block, every attribute, every
`Changes to Outputs` entry — are identical character for character.

### 1.3 `source_code_hash` — the date paradox dissolves

The brief flagged that the evidence files carry `2026-08-12` mtimes while the zip is dated
`2026-08-11`. Measured:

```
planned source_code_hash        yF1/AKVXbkEt+wEkrZPEAQR1cBEXnQApNh2ajbW4pLA=
filebase64sha256 of the zip     yF1/AKVXbkEt+wEkrZPEAQR1cBEXnQApNh2ajbW4pLA=   EQUAL
```

The zip's manifest agrees a third time (`bytes_zipped` 7 989 296, `sha256` `c85d7f00…`, the
hex form of the same digest). **No drift.** The plan's internal timestamp is
`2026-08-11T05:33:11Z` = 15:33 local (UTC+10) and the zip's mtime is 15:42 local, nine
minutes *later* — so the zip was touched after the plan was made, and yet not one byte of
it changed.

The `2026-08-12 21:48` mtimes are the account-id masking pass, and I proved that pass was
content-preserving. Restoring the twelve digits and converting CRLF back to LF reproduces
the SHA-256s recorded in `docs/deploy/terraform-plan.md` **exactly**, for all three
artefacts:

| artefact | reconstructed bytes | reconstructed SHA-256 | matches the doc |
|---|---:|---|---|
| `terraform-plan-furl.txt` | 18 290 | `d5e6c3f0…5e9316` | ✅ |
| `terraform-plan-furl.json` | 128 776 | `f2fe940b…3616f9` | ✅ |
| `terraform-plan-cloudfront.txt` | 32 853 | `6d7573a5…9c4970` | ✅ |

Custody is complete. One honesty finding falls out of it: **the SHA-256s printed in
`docs/deploy/terraform-plan.md` no longer match the files as committed.** A stranger who
clones the public repo and runs `sha256sum` gets a mismatch on all three, and the same page
says *"Each file is the verbatim stdout+stderr of its command"*, which is now true only up
to the mask and a LF→CRLF conversion applied afterwards. One sentence of prose repairs it;
the artefacts themselves are sound.

### 1.4 The three `lifecycle.precondition` blocks all evaluate — proven by making them fail

The plan JSON's `checks` array reports `pass`, but a condition that is never reached also
never fails, so `pass` alone proves nothing. Each was perturbed in the scratch copy until
it **fired**:

| # | resource, line | perturbation | result |
|---|---|---|---|
| 1 | `aws_lambda_function`, `main.tf:290` | `-var lambda_architecture=x86_64` against the arm64 package | **fired** — *"…was built for a different architecture than var.architecture (x86_64)…"* |
| 2 | `aws_lambda_function`, `main.tf:295` | scratch manifest rewritten to `handler = "wrong_module.wrong.handler"` | **fired** — *"…declares a handler other than mainline_demo_api.app.handler…"* |
| 3 | `aws_cloudwatch_metric_alarm.duration_p99`, `main.tf:460` | `duration_p99_threshold_ms` 12 000 → 15 000 | **fired** — *"…this alarm could never breach - a control that looks present and is not."* |

All three are live plan-time controls. Every perturbation was made in the scratch copy and
reverted; **no file under `infra/` was modified.**

Stated honestly for completeness: three further `checks` entries report `pass` with **zero
instances** — `aws_lambda_permission.cloudfront_invoke`, `aws_cloudfront_distribution.site`
and `aws_s3_bucket.site`. Their preconditions were not exercised by this plan. That is
correct for `url_authorization_type = "NONE"`; it just must not be cited as a control that
was checked here.

---

## 2 · The four alarms

Every field below was read out of the plan JSON. Every account fact was read with a
read-only AWS call under profile `mainline-dev`, region `ap-southeast-1`.

| alarm | metric | stat | period | eval | threshold | operator | missing data | verdict |
|---|---|---|---:|---:|---:|---|---|---|
| `-errors` | `Errors` | `Sum` | 300 | 1 | `> 0` | GreaterThanThreshold | `notBreaching` | **REACHABLE** |
| `-throttles` | `Throttles` | `Sum` | 300 | 1 | `> 0` | GreaterThanThreshold | `notBreaching` | **REACHABLE** |
| `-duration-p99` | `Duration` | `p99` (extended) | 300 | 1 | `> 12 000 ms` | GreaterThanThreshold | `notBreaching` | **REACHABLE** |
| `-concurrency` | `ConcurrentExecutions` | `Maximum` | 300 | 1 | `> 20` | GreaterThanThreshold | `notBreaching` | **UNFIRABLE** |

`datapoints_to_alarm` is unset on all four, so it defaults to `evaluation_periods` = 1.
`actions_enabled = true` on all four, and `alarm_actions` / `ok_actions` /
`insufficient_data_actions` are **all empty**.

### 2.1 `errors` — reachable, and blind to the outage you will actually get

`Errors` is emitted for every function on every invocation, unconditionally. It reaches 1
on an init/import failure (a wrong-architecture psycopg wheel), on a 15 s timeout, on OOM
at 512 MB, and on any exception escaping `app.handler` — the POST branch at `app.py:450`
catches **only** `psycopg.Error`, so anything else raised inside
`transitions.handle_transition` propagates. Reachable.

But the handler is written never to raise on *application* failure: `db.DsnUnavailable`
becomes a `503` problem document (`app.py:346`) and the read branch catches bare `Exception`
(`app.py:383`). **The single most likely failure of a first deploy — no SSM SecureString at
`/mainline/demo/cockroach_dsn`, so every request answers `503 dsn_unset` — produces
`Errors = 0` and leaves this alarm sitting in OK.** The alarm is real; it is blind to the
outage the founder is most likely to hit on day one. `/v1/health` is the only thing that
sees it.

### 2.2 `throttles` — reachable, and earlier than intended

`Throttles` carries the `FunctionName` dimension for every invocation rejected with a 429,
whether the binding limit is the function's reserved concurrency or the **account's**
ceiling. It does not depend on reserved concurrency being set. So it is reachable — and on
this account it fires at **10** simultaneous invocations, not at the 20 the description
implies. This turns out to be the one alarm that genuinely catches the abuse case the
concurrency alarm was written for.

### 2.3 `duration_p99` — reachable, with 3 000 ms of headroom, and guarded

`Duration` is emitted once per invocation. It is capped at the 15 000 ms timeout, and
12 000 < 15 000 leaves a real band; a timed-out invocation itself reports ≈15 000 ms, above
the threshold. Terraform does not set `evaluate_low_sample_count_percentiles`, and AWS
defaults it to `evaluate`, so a **single** invocation over 12 s in a five-minute window
breaches — p99 of a small sample is its maximum. Reachable, and protected by the
precondition proven live in §1.4.

### 2.4 `concurrency` — structurally unfirable, three ways

```
aws service-quotas get-service-quota --service-code lambda --quota-code L-B99A9384 \
    --region ap-southeast-1
  QuotaName "Concurrent executions"   Value 10.0   Adjustable true   ACCOUNT level

aws lambda get-account-settings --region ap-southeast-1
  AccountLimit.ConcurrentExecutions           = 10
  AccountLimit.UnreservedConcurrentExecutions = 10
  AccountUsage.FunctionCount                  = 0
```

**(a) Arithmetic.** The alarm breaches on `Maximum(ConcurrentExecutions) > 20`. No function
in this account can reach 11, let alone 21. The condition is false by construction, in every
five-minute window, at any level of abuse. The abuse tripwire cannot detect abuse.

**(b) Emission.** The plan sets `reserved_concurrent_executions = 20`. A reservation of 20
cannot be satisfied by an account whose entire ceiling is 10, and AWS refuses any
reservation that drops `UnreservedConcurrentExecutions` below its floor — this account
reports the whole ceiling, 10, as unreserved, so there is no room to take *any* of it at any
value ≥ 1. The only settable value is `-1`. Without reserved concurrency, AWS does not
dependably emit per-function `ConcurrentExecutions`, so the alarm has nothing to evaluate.
**The module's own `alarm_description` says exactly this** — the warning it prints about
itself is the condition it will actually be deployed in. (Whether the apply survives that
reservation at all is W4's finding; from here it is only the alarm consequence that matters.)

**(c) The missing-data policy makes it worse, not better.** The description warns the alarm
*"can sit in `INSUFFICIENT_DATA` and prove nothing"*. It will not: `treat_missing_data =
notBreaching` converts that silence into **OK**. An alarm that proves nothing while
*looking* like it proves something is strictly the worse of the two outcomes the module
considered.

> **The irony, one resource away.** `aws_cloudwatch_metric_alarm.duration_p99` carries a
> `lifecycle.precondition` whose error message reads *"this alarm could never breach — a
> control that looks present and is not."* That precondition exists to forbid exactly this
> class of defect. It is proven live. It does not cover the alarm defined 6 lines below it.

**Exact minimal fix.** Either edit alone leaves a hole; the pair closes it:

```hcl
# infra/modules/demo-api/variables.tf — concurrency_alarm_threshold
- default     = 20
+ default     = 8        # below the account's ConcurrentExecutions ceiling of 10

# infra/modules/demo-api/main.tf — on aws_cloudwatch_metric_alarm.concurrency,
# mirroring the block already on duration_p99
  lifecycle {
    precondition {
      condition     = var.concurrency_alarm_threshold < var.account_concurrency_ceiling
      error_message = "concurrency_alarm_threshold (…) is not below the account's Lambda concurrency ceiling (…). ConcurrentExecutions can never exceed the ceiling, so this alarm could never breach — a control that looks present and is not."
    }
  }
```

with a new `variable "account_concurrency_ceiling" { default = 1000 }` passed as `10` from
`infra/envs/demo`. The third option is to **delete the concurrency alarm** and name
`mainline-demo-api-throttles` as the abuse tripwire in the module README and
`docs/deploy/OBSERVABILITY.md` — one fewer alarm, and the one that remains works.

---

## 3 · Who reads the alarms? Measured: nobody automated.

`alarm_actions = []`. No SNS topic is created by this plan. **Nothing is notified.** Every
reader has to go and look. There are two candidates, and only one is real.

**Real: the dashboard.** `main.tf:589` renders a `type = "alarm"` widget listing all four
alarm ARNs, and the plan's `configuration` block confirms `dashboard_body` references
`aws_cloudwatch_metric_alarm.{errors,throttles,duration_p99,concurrency}.arn`. A human
signed into the CloudWatch console sees four states at a glance. That is a genuine reader —
console-only, pushing nothing, and nobody is looking at it at 03:00.

**Not real: `demo-health.yml`.** The module says in four places that the hourly workflow
calls `describe-alarms`:

| claim | location |
|---|---|
| *"by the hourly `demo-health` workflow, which calls `describe-alarms`"* | `infra/modules/demo-api/main.tf:377` |
| *"still readable by `aws cloudwatch describe-alarms` — which is what the `demo-health` cron reads"* | `infra/modules/demo-api/variables.tf:452` |
| *"for `aws cloudwatch describe-alarms --alarm-names` in the hourly `demo-health` workflow"* | `infra/modules/demo-api/outputs.tf:133` |
| *"the hourly `demo-health` workflow's `describe-alarms` check"* | `infra/modules/demo-api/README.md:207` |

**The workflow does none of this.** It contains no `cloudwatch`, no `describe-alarms`, no
`configure-aws-credentials`, no `role-to-assume`, no `aws-region`, and no `secrets.`
reference. Its only external input is `vars.DEMO_URL`. Every step is an *unauthenticated*
HTTP request to the demo URL: `GET /`, `GET /v1/health`, `POST /v1/demo/gate-run`, then a
latency record. Repository-wide, `describe-alarms` has exactly one executable hit —
`scripts/aws/cloudwatch_evidence.py:693` — and no workflow invokes it with credentials.

### 3.1 Can GitHub Actions authenticate to AWS at all? No.

```
gh secret list                                    → empty (exit 0)
gh variable list                                  → empty (exit 0)
gh api …/actions/secrets    → {"total_count":0,"secrets":[]}
gh api …/actions/variables  → {"variables":[],"total_count":0}
gh api …/environments       → {"total_count":0,"environments":[]}
aws iam list-open-id-connect-providers → {"OpenIDConnectProviderList": []}
aws iam list-roles, trust policy naming token.actions.githubusercontent.com → []
no workflow declares  permissions: id-token: write
```

The repository is **public**, holds **zero** secrets and **zero** variables, no workflow
requests an OIDC token, the account trusts **no** GitHub OIDC provider, and there is no role
for a workflow to assume. The single AWS-shaped step in the whole of `.github/` is
`aws-evidence.yml:169`, which *unsets* every AWS variable on purpose to prove that lane is
hermetic.

**Therefore: after the apply, the four alarms will be read by exactly one thing — a human
signing into the CloudWatch console.** There is no automated reader, and there is no path by
which one could exist without first adding a secret or an OIDC role to a public repository.

(Related, and it lands on the same workflow: `vars.DEMO_URL` does not exist either, so
`demo-health.yml` falls back to `docs/submission/SUBMISSION.json`, whose `demo_url` is still
the deliberate `UNRESOLVED` token.)

---

## 4 · `treat_missing_data = notBreaching` on a demo with no traffic

Missing datapoints are evaluated as if within the threshold, so an alarm with **no data**
does not sit in `INSUFFICIENT_DATA` — it goes to **OK**.

A judging demo is idle almost all of the time. No invocations means no `Errors`, no
`Throttles`, no `Duration`, no `ConcurrentExecutions` — so **all four alarms read OK, and
the dashboard shows four green rows.** Green here means *"nobody has called this function"*,
not *"this function is healthy"*, and nothing on the widget distinguishes the two.

That is the correct trade for `errors` and `throttles`: an idle demo genuinely is not
failing, and the alternative would be a permanently-red dashboard. It is the **wrong** trade
for `concurrency`, where missing data is the *expected steady state* and OK is therefore a
permanent false reassurance. The honest disclosure — one line in
`docs/deploy/OBSERVABILITY.md` — is that on this stack an OK alarm means *"no breaching
datapoint **or** no datapoint at all"*, and only `/v1/health` tells you which.

---

## Verdict

**GO-WITH-FIX** — the plan replays byte-identically to its committed evidence with zero package drift and three live preconditions, and three of four alarms can fire; before apply, make three edits: `infra/modules/demo-api/variables.tf` `concurrency_alarm_threshold` default `20 → 8`, add the mirror `lifecycle.precondition` on `aws_cloudwatch_metric_alarm.concurrency` (`var.concurrency_alarm_threshold < var.account_concurrency_ceiling`, new variable passed as `10`), and delete the four claims that `demo-health` reads the alarms with `describe-alarms` — it does not, and on a public repository with zero secrets and no OIDC provider it cannot.
