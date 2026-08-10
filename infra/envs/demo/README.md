<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: CC-BY-4.0
-->

# `infra/envs/demo` — the Terraform root that owns the demo URL

One distribution, one hostname, two origins, and no custom domain. This root composes
[`../../modules/demo-site`](../../modules/demo-site) and
[`../../modules/demo-api`](../../modules/demo-api) and produces the single string the
hackathon submission form asks for:

```
https://dXXXXXXXX.cloudfront.net
```

You almost never run `terraform` here by hand. `scripts/deploy/deploy.ps1` (or `.sh`)
runs it as stage 6 of nine, and `docs/deploy/RUNBOOK.md` is the page to read first. This
file is for the person who wants to know what the HCL does and why it is shaped this way.

> ## ⛔ This root cannot apply on account `022950218246` today
>
> A real apply on 2026-08-10 created seven resources and then AWS refused the eighth:
>
> ```
> Error: creating CloudFront Distribution: ... StatusCode: 403,
> RequestID: 3e63e30d-8c5b-441b-a01b-b70085eba504, AccessDenied:
> Your account must be verified before you can add new CloudFront resources.
> ```
>
> The same refusal comes from a bare `aws cloudfront create-distribution` with a minimal
> config and no Terraform involved, from an identity holding `AdministratorAccess`. It is
> an **AWS account-level verification hold**, not a defect in this root or in either
> module, and only AWS Support can lift it. See
> [`docs/deploy/RUNBOOK.md`](../../../docs/deploy/RUNBOOK.md) — the banner at the top says
> what to do about it. Everything below is correct and verified as far as the hold allows.

---

## The five files

| File | What it holds |
|---|---|
| `versions.tf` | `terraform >= 1.10`, `aws >= 5.60 < 7.0`, and the reason for each floor |
| `backend.tf` | S3 backend, `use_lockfile = true`, **no DynamoDB table**, bucket supplied at `init` |
| `variables.tf` | Nine variables, every one with a default that works on account `022950218246` |
| `main.tf` | The provider, the two modules, and the wiring |
| `outputs.tf` | What the deploy and teardown scripts read back |

`terraform.tfvars.example` is a copy-if-you-want; you do not need it, because the defaults
are the values the deploy script uses.

---

## Quick start

```bash
# 1. the state bucket — Terraform cannot create the bucket it stores its state in
scripts/deploy/bootstrap_state.sh --bucket mainline-demo-tfstate-022950218246

# 2. init against it
cd infra/envs/demo
terraform init \
  -backend-config="bucket=mainline-demo-tfstate-022950218246" \
  -backend-config="region=ap-southeast-1"

# 3a. PHASE 1 — a working HTTPS URL with no Lambda at all
terraform apply -var enable_api=false

# 3b. PHASE 2 — the same URL, plus the live API
scripts/deploy/build_lambda.sh --arch arm64
terraform apply \
  -var enable_api=true \
  -var lambda_package_path=../../../out/lambda/mainline-demo-api-arm64.zip \
  -var lambda_architecture=arm64
```

Going from 3a to 3b is an **in-place update of the distribution, not a replacement**. The
hostname printed on day one is the hostname in the submission form on day eight.

---

## The dependency that looks like a cycle

The two modules refer to each other:

* `site` needs `api.function_url_domain` — to build the `/v1/*` origin
* `api` needs `site.distribution_arn` — to scope `aws_lambda_permission` to one
  distribution, so the `AWS_IAM` Function URL is invocable by our CloudFront and by
  nothing else on the internet

At the module level that reads as a cycle. At the resource level — the level Terraform's
graph actually works at — it is not one, **because the invoke grant is a separate resource
from the function**:

```
aws_lambda_function      (api) ─┐
aws_lambda_function_url  (api) ─┴─► aws_cloudfront_distribution (site)
                                                  │
                                    aws_lambda_permission (api) ◄─┘
```

That is the theory. **The theory alone would have shipped a broken root**, and the two
paragraphs below are the reason this section exists.

### Failure 1 — the splat really is a cycle

The first version reached the Function URL with a splat over the counted module:

```hcl
api_origin_domain = join("", module.api[*].function_url_domain)     # WRONG
```

`terraform plan`, Terraform v1.14.8:

```
Error: Cycle: module.site.output.distribution_arn (expand),
module.api.var.distribution_arn (expand), module.api.aws_lambda_permission.cloudfront,
module.api (close), local.api_origin_domain (expand),
module.site.var.api_origin_domain (expand), module.site.local.has_api (expand),
module.site.aws_cloudfront_distribution.this
```

Read the fourth element. **`module.api (close)`** is the whole-module node that a splat
over a `count`ed module depends on, and every resource in that module feeds it —
including `aws_lambda_permission`. So the splat says *"the distribution depends on
everything in the api module"*, which drags the permission back into the site's
dependencies and closes the loop.

An **indexed** reference does not touch the close node. It depends on that one output,
which depends on `aws_lambda_function_url` alone:

```hcl
api_origin_domain = try(module.api[0].function_url_domain, "")      # RIGHT
```

`try()` and not `var.enable_api ? module.api[0].… : ""`, because with `enable_api = false`
the count is zero and `module.api[0]` is an invalid index that a conditional does not
dodge. `try` catches exactly that error and yields `""`, which is the Phase-1 shape.

**This is a load-bearing three-token expression.** `one(...)`, `join("", ...)` and
`coalesce(...)` all reintroduce the splat, and the cycle with it.

### Failure 2 — a `count` that depends on an unknown

With the cycle gone, the next plan produced:

```
Error: Invalid count argument
  on ../../modules/demo-site/main.tf line 52, in resource
  "aws_cloudfront_origin_access_control" "api":
  52:   count = local.has_api ? 1 : 0

The "count" value depends on resource attributes that cannot be determined until apply.
```

A Lambda Function URL's hostname does not exist until apply, so `api_origin_domain != ""`
is not a plan-time-known boolean and nothing may `count` on it. Hence **two inputs where
one would read more elegantly**: `enable_api` is the plan-time boolean everything counts
on, and `api_origin_domain` is used strictly as a *value* inside a resource body, where an
unknown is fine.

### The result, measured

Against the real `demo-site` and `demo-api` modules, Terraform v1.14.8, AWS provider
v6.58.0, on this machine:

```
terraform validate                     Success! The configuration is valid.
terraform plan -var enable_api=false   Plan:  9 to add, 0 to change, 0 to destroy.
terraform plan -var enable_api=true    Plan: 22 to add, 0 to change, 0 to destroy.
```

**One plan, one apply, no cycle, in both phases.** No two-stage apply is needed and none
is shipped. HCL that only works the second time you run it is not shipped either.

---

## Module contract

This root is the only caller of both modules, so this section is normative. Two of these
clauses exist *only* because the harness above found them; they are not style.

### `demo-site`

| Input | Type | Meaning |
|---|---|---|
| `name_prefix` | string | Composed into resource names. Must keep the `mainline-demo-` prefix. |
| `bucket_name` | string | Explicit, globally unique, private. |
| `enable_api` | bool | **Plan-time known.** The only thing `count`/`for_each` may key on. |
| `api_origin_domain` | string | Bare hostname, no scheme, no path. May be unknown at plan time. `""` means no second origin. |
| `price_class` | string | |
| `tags` | map | Merged on top of `default_tags`. |

Required outputs: `bucket_name`, `distribution_id`, `distribution_arn`,
`distribution_domain_name`.

> **The module must not derive `count` or `for_each` from `api_origin_domain != ""`.**
> See Failure 2.

### `demo-api`

| Input | Type | Meaning |
|---|---|---|
| `function_name` | string | The whole Lambda name; also fixes the log group, alarms and dashboard. |
| `package_path` | string | The zip from `build_lambda.{sh,ps1}`. |
| `architecture` | string | Must match the zip. |
| `dsn_parameter_name` | string | **Name only.** Terraform never holds the DSN. |
| `cloudfront_distribution_arn` | string | The `SourceArn` on the one invoke grant. |
| `log_retention_days` | number | |
| `tags` | map | |

Required outputs: `function_name`, `function_url_domain`.

> **`aws_lambda_permission` must be the module's ONLY reference to
> `var.cloudfront_distribution_arn`.** If the function, the Function URL, the role or the
> log group ever reads it, the cycle is real and no amount of indexing saves it.

---

## What is deliberately absent

| Not here | Why |
|---|---|
| **DynamoDB lock table** | `use_lockfile = true` is native S3 locking since Terraform 1.10. Saves $0.25/month and, more usefully, one stateful resource teardown would have to find. |
| **Route 53 zone + ACM certificate** | A hosted zone is $0.50/month, and an ACM cert for CloudFront must be issued in `us-east-1`, which means a second provider alias. `https://dXXXXXXXX.cloudfront.net` is valid HTTPS and free. |
| **Any secret** | The CockroachDB DSN goes to SSM Parameter Store as a SecureString written by `aws ssm put-parameter`. Terraform is given the parameter *name*. A Terraform-managed secret is a plaintext secret in the state file. |
| **CloudWatch Synthetics canary** | One canary at five-minute intervals is 8,640 runs a month at $0.0012 — **$10.37/month**, thirty times the cost of everything else here combined. |
| **A committed `.tfvars`** | Every default already works. |

---

## OpenTofu

Everything in this root is in the common subset: `hashicorp/aws` only, no
`terraform { encryption { … } }` block, no Terraform Cloud block, no provider aliases.

```bash
tofu init -backend-config="bucket=mainline-demo-tfstate-022950218246"
tofu apply -var enable_api=false
```

works unchanged. Terraform v1.14.8 is what is installed on the build machine and OpenTofu
is not, so **Terraform is what the claims in this file were measured with**; the OpenTofu
commands above are stated as compatible, not as verified. That distinction is the point of
`docs/HONESTY.md` and it applies to this page too.

---

## Outputs, and who reads them

| Output | Consumer |
|---|---|
| `demo_url` | the submission form; `demo_acceptance.py`; stage 7's HTTPS check |
| `deploy_summary` | `deploy.sh` / `deploy.ps1` — one `terraform output -json` instead of nine |
| `distribution_id` | the CloudFront invalidation in stage 7 |
| `site_bucket` | `aws s3 sync` in stage 7; `teardown.sh` step 2 |
| `api_function_name` | `aws logs tail /aws/lambda/<this>` when `/v1/health` is unhappy |
| `aws_account_id` | the deploy script's refusal to run outside `022950218246` |

None of them is sensitive, and none of them can be, because Terraform never held a
credential.
