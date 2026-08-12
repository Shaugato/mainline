<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
-->

# DEPLOY VERIFICATION — adversarial gate on the committed Terraform plan

**Lead:** deploy-verification lead. **Date:** 2026-08-11. **Scope:** return a defensible
**GO / NO-GO** on `terraform apply` of `infra/envs/demo` (committed plan
`evidence/deploy/terraform-plan-furl.{txt,json}`, 11 to add / 0 to change / 0 to destroy,
`ap-southeast-1`).

**Standing constraint for every worker: `terraform apply` is FORBIDDEN.** `init`,
`validate`, `plan`, `show`, and read-only AWS API calls only. No `aws ... create-*`,
`put-*`, `delete-*`, `update-*`, `tag-*`. No `gh` write. No writes to the CockroachDB Cloud
cluster. The local Docker node is the only database anyone may mutate.

---

## 0. WHAT I ESTABLISHED MYSELF, BEFORE DECOMPOSING

Read-only, on this machine, with profile `mainline-dev` against account `0229REDACTED8246`.
These are measurements, not readings of the repository's own prose.

### 0.1 THE PLAN CANNOT APPLY. Lambda concurrency quota is 10, and the plan reserves 20.

```
aws lambda get-account-settings --region ap-southeast-1
  AccountLimit.ConcurrentExecutions          = 10
  AccountLimit.UnreservedConcurrentExecutions = 10
  AccountUsage.FunctionCount                  = 0

aws service-quotas get-service-quota --service-code lambda --quota-code L-B99A9384
  QuotaName "Concurrent executions"  Value 10.0  Adjustable true  QuotaAppliedAtLevel ACCOUNT
```

`ap-southeast-2` reports the same pair (10 / 10). The committed plan sets
`reserved_concurrent_executions = 20` on `module.api[0].aws_lambda_function.this`. A
reservation larger than the account's entire concurrency ceiling cannot be satisfied, and
AWS additionally refuses any reservation that drops unreserved concurrency below its
documented floor. **The expected outcome of the authorised apply is a failed
`CreateFunction`,** after the log group, role, policy and attachment have already been
created — a partial apply, which is the worst shape for a first deploy.

This single fact also breaks two claims the module makes about itself:

* `reserved_concurrent_executions` is described as *"the only control here that actually
  STOPS a bill rather than reporting one"*. On this account the control cannot be set at
  all; the real ceiling is the account quota of 10.
* `aws_cloudwatch_metric_alarm.concurrency` fires above **20** concurrent executions.
  `ConcurrentExecutions` for this account can never exceed **10**. **The abuse tripwire is
  an alarm that cannot fire** — precisely the defect `duration_p99`'s own
  `lifecycle.precondition` exists to forbid, reproduced one resource lower.

This is a **NO-GO trigger** unless the plan changes. W4 owns confirming it and naming the
exact minimal fix; W5 owns the alarm consequence.

### 0.2 The public write surface is NOT "one transaction that ends in ROLLBACK"

`infra/modules/demo-api/main.tf` justifies `authorization_type = "NONE"` partly on *"the
handler's write surface is one transaction that ends in ROLLBACK"*. Reading the code that
will be deployed:

* `app._routes()` at HEAD returns **17** routes (the STATE's "16 routes, gate-run missing"
  defect is already fixed — `Route("POST", "/v1/demo/gate-run", "demo_gate_run")` is line
  186). Four of the seventeen are **kernel POSTs**: `materialise_checks`,
  `sign_disposition`, `merge_permit`, `suspend_permit`.
* `transitions.TRANSITION_RESOURCES` marks all four `mutates = True`, and their handlers
  call `conn.commit()` (`transitions.py:422, 560, 698, 861`). Only `demo_gate_run` rolls
  back.
* The single protection is `transitions._demo_guard`, which returns `423 Locked`
  **if and only if `subject_id == scenario.permit_id`**. Any *other* permit id is
  unprotected and commits.
* The DSN login is not read-only: `scripts/deploy/cloud_roles.py` grants `mainline_api`
  `UPDATE blocking_check`, `UPDATE change_request`, `INSERT ledger_intake` and
  `EXECUTE ON PROCEDURE mainline.merge_permit` (and siblings). The database will not
  refuse the write.

So the safety of the public URL reduces to an empirical question nobody has answered:
**does `mainline_demo` on the Cloud cluster contain any permit other than the seeded one,
and can an anonymous caller discover its id through `GET /v1/ledger` or `GET /v1/audit`?**
If yes, an unauthenticated stranger can irreversibly merge or suspend it. W2 owns this and
it is the second NO-GO trigger.

### 0.3 A documented CORS decision that the handler contradicts

The Function URL deliberately has no `cors` block, and the module argues at length that
adding `allow_origins = ["*"]` would turn *"any page may make a request and not read the
answer"* into *"may read it"*. But `app._response()` sets
`"access-control-allow-origin": "*"` on **every** response (`app.py:272`), which produces
exactly the widening the HCL says was refused. The security delta is small (there are no
credentials to steal) but the written justification is false as deployed, and this repo is
public. W2 owns it.

### 0.4 Account facts the plan's cost and blast-radius claims depend on

| Fact | Measured |
|---|---|
| Existing Lambda functions | **0** — no name collision on `mainline-demo-api` |
| CloudWatch alarms, `ap-southeast-1` | **0** — the 4 new alarms land inside the free 10 |
| CloudWatch dashboards, `ap-southeast-1` | **0** — inside the free 3 |
| SSM parameters under `/mainline/` | **none exist yet** — the DSN SecureString is unwritten, so a bare apply yields a function that answers `503 dsn_unset`, and `alias/aws/ssm` has no backing key yet |
| S3 buckets | 7, none of them `mainline-demo-tfstate-*` — **the state bucket does not exist**; `terraform init` with the S3 backend fails until `bootstrap_state.sh` runs |
| CloudFront distributions | **1** — `E2FCXK8NILPNWF`, created 2026-04-16, origin `checkout-platform-debd5edd-site`. The repo's claim that the account holds one pre-existing distribution is **TRUE** |
| AWS Budgets | `My Monthly Cost Budget`, limit **USD 10.00**, actual spend **USD 12.41**, forecast **USD 32.92** — **the account is already over its own budget before this stack exists** |

The last row is the one that changes the tone of the cost question. "~USD 0.02/month" is
being added to a card that is already running ~3x its configured budget from unrelated
projects, and no budget *action* was observed. W4 owns quantifying this properly.

### 0.5 What is genuinely sound (do not re-litigate; verify and move on)

* `dsn_access` names exactly one SSM ARN and exactly `ssm:GetParameter` — no
  `GetParameters`, no `GetParametersByPath`, no `DescribeParameters`, no wildcard path.
* No `MAINLINE_DSN` in the planned environment; `extra_environment` has a `validation`
  block that refuses it and the six keys the module sets. Terraform is given a *name*.
* No `MAINLINE_DEMO_ALLOW_MUTATION` in the planned environment — the demo-subject guard is
  armed.
* `aws_lambda_permission.cloudfront_invoke` is `count = 0` and genuinely absent from the
  plan's 11 resources (verified in `terraform-plan-furl.json`).
* `static_site` refuses `..` segments and asserts `is_relative_to(root)` after `resolve()`.
* Plan JSON: 11 `create`, 0 `update`, 0 `delete`; no CloudFront, S3 or CockroachDB resource
  of any kind. Nothing pre-existing is addressed.

### 0.6 Two disclosure rules that bind every worker

1. **Never print a credential.** Not the DSN, not `mainline_judge`'s password, not an
   access key — not to stdout, not into a file, not into a structured result. If a task
   needs the DSN, use it without echoing it. Two workers have already been blocked by the
   safety system for this.
2. **Never write the real 12-digit account id into a tracked file.** HEAD masks it as
   `0229REDACTED8246` across 13 files. Evidence JSON and Markdown produced by this pass must
   use `0229REDACTED8246` or `<account-id>`. Normalise before writing, not after.

---

## 1. STRATEGY

The plan's own prose is unusually good, which is the trap: it is easy to audit the
*argument* instead of the *artefact*. Every worker's finding must rest on a command that
was run, a byte that was read, or a published AWS price — never on the module's comments,
however well argued.

Sequencing: all five workers are independent and run in parallel. One coordination rule
prevents the only real collision:

> **Only W5 may run `terraform` in `infra/envs/demo`.** It mutates `.terraform/` and writes
> plan binaries. Everyone else reads `evidence/deploy/terraform-plan-furl.json`, which is
> the committed artefact under review anyway.

Second rule: **only W2 may touch a database.** It uses the local Docker node for mutation
proofs and is permitted read-only `SELECT` against the Cloud cluster for the enumeration
question in §0.2. Nobody else connects.

Each worker returns a verdict fragment in the same shape — `GO`, `GO-WITH-FIX` (naming the
exact edit), or `NO-GO` (naming what breaks) — so the lead's aggregate is an assembly, not
a re-derivation.

---

## 2. WORKERS

| id | title | owns |
|---|---|---|
| W1 | IAM: least privilege, proven by simulation | `docs/verify/deploy/iam-least-privilege.md`, `evidence/deploy/verify/iam-simulation.json` |
| W2 | The public surface: abuse it, route by route | `docs/verify/deploy/public-surface.md`, `evidence/deploy/verify/public-surface-probe.json` |
| W3 | The DSN, the state backend, blast radius and rollback | `docs/verify/deploy/secrets-and-blast-radius.md`, `evidence/deploy/verify/state-and-teardown-audit.json` |
| W4 | Cost, quotas and the economics of abuse | `docs/verify/deploy/cost-and-quota.md`, `evidence/deploy/verify/aws-quota-and-cost.json` |
| W5 | Alarms that can fire, and plan replay vs. the committed evidence | `docs/verify/deploy/alarms-and-plan-replay.md`, `evidence/deploy/verify/plan-replay-diff.txt`, `evidence/deploy/verify/alarm-reachability.json` |

File ownership is absolute and the sets are disjoint. No worker edits `infra/**`,
`verticals/**`, `scripts/**`, `.github/**` or any pre-existing tracked file: this is a
verification pass and its output is findings, not repairs. Nobody commits or pushes.

---

## 3. THE DECISION RULE

A **GO** requires all five of:

1. The plan applies cleanly on this account as written — i.e. §0.1 is either wrong or fixed.
2. No route reachable without authentication mutates committed state on the Cloud cluster,
   or leaks a credential, or discloses another project's data — proven by probe, not by
   reading the guard.
3. The DSN reaches the Lambda only as a KMS-encrypted SecureString read at runtime, and
   appears in no state file, no plan, no log, no committed file, and no public repository
   object.
4. A worst-case abusive caller's 30-day bill is bounded by a number the founder has seen
   and accepted, and the bound is enforced by a mechanism that exists.
5. Every alarm can reach its threshold, and something or someone reads it.

Anything short of that is **NO-GO with a named fix**. A delayed deploy costs hours.

---

*Written by the deploy-verification lead. The apply remains the orchestrator's; no worker
runs it.*
