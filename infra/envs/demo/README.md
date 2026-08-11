<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: CC-BY-4.0
-->

# `infra/envs/demo` — the Terraform root that owns the demo URL

One hostname, and `var.enable_cloudfront` decides which resource owns it. This root
composes [`../../modules/demo-api`](../../modules/demo-api) and — optionally —
[`../../modules/demo-site`](../../modules/demo-site), and produces the single string the
hackathon submission form asks for:

```
https://<id>.lambda-url.ap-southeast-1.on.aws        enable_cloudfront = false  (default)
https://dXXXXXXXX.cloudfront.net                     enable_cloudfront = true
```

You almost never run `terraform` here by hand. `scripts/deploy/deploy.ps1` (or `.sh`)
runs it as one stage of nine, and `docs/deploy/RUNBOOK.md` is the page to read first. This
file is for the person who wants to know what the HCL does and why it is shaped this way.
The committed plans are read back in prose in
[`docs/deploy/terraform-plan.md`](../../../docs/deploy/terraform-plan.md).

> ## ⛔ `enable_cloudfront = true` cannot apply on this AWS account today
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
> an **AWS account-level verification hold on new CloudFront resources**, not a defect in
> this root or in either module, and only AWS Support can lift it. See
> [`docs/deploy/RUNBOOK.md`](../../../docs/deploy/RUNBOOK.md).
>
> **This root is not blocked by that.** Decision D1
> ([`docs/leads/ship-final.md`](../../../docs/leads/ship-final.md) §1.4) moved the hostname
> to the Lambda Function URL, `var.enable_cloudfront` defaults to `false`, and the default
> configuration plans eleven resources of which none is a `aws_cloudfront_*`. The
> distribution is an upgrade you apply the day the hold lifts.

---

## The two shapes

```
  enable_cloudfront = false  (DEFAULT — decision D1)

    judge ──► https://<id>.lambda-url.ap-southeast-1.on.aws     HTTPS, AWS-issued cert
              AWS Lambda · python3.13 · authorization_type=NONE  ONE origin, no CORS
                GET  /                 → console SPA (from the zip)
                GET  /bundle/*         → signed EvidenceBundle    REPLAY source
                GET  /v1/*             → 12 read resources        LIVE source
                POST /v1/demo/gate-run → the four beats, one txn, rolled back
                                │ pgwire · TLS · same region
                                ▼
              CockroachDB Cloud Basic · mainline_demo · aws-ap-southeast-1


  enable_cloudfront = true   (upgrade, blocked by the AWS hold above)

    judge ──► https://dXXXXXXXX.cloudfront.net                   HTTPS, CloudFront cert
                default behaviour → S3 (OAC, private)            console + bundle
                /v1/*             → Lambda FURL (OAC, AWS_IAM)   the live API
```

Flipping the variable moves the hostname **and** flips the Function URL's
`authorization_type` in the same breath — one expression in `main.tf` does both, so the two
halves cannot disagree. The public hostname changes with it, so the submission form has to
be updated; that is the trade the default declines to make on a support queue's schedule.

---

## The six files

| File | What it holds |
|---|---|
| `versions.tf` | `terraform >= 1.10`, `aws >= 5.60 < 7.0`, and the reason for each floor |
| `backend.tf` | S3 backend, `use_lockfile = true`, **no DynamoDB table**, bucket supplied at `init` |
| `variables.tf` | Ten variables, every one with a working default; `enable_cloudfront` is the switch |
| `main.tf` | The provider, the two modules, and the wiring — including the cycle rules |
| `outputs.tf` | What the deploy and teardown scripts read back; everything site-shaped is nullable |
| `terraform.tfvars.example` | Copy-if-you-want. You do not need it; the defaults are what the deploy script uses. |

### No account id is written down anywhere here

`<account-id>` below is a placeholder. Decision **D2**
([`ship-final.md`](../../../docs/leads/ship-final.md) §1.6): where the twelve-digit account
number was an *executable* value — a `variables.tf` default, a `backend-config` example, a
tfvars example — it is removed, because such a value is correct on exactly one machine.
Inside Terraform it is derived from `data.aws_caller_identity.current.account_id`; outside
it, from:

```bash
aws sts get-caller-identity --query Account --output text
```

`output.aws_account_id` publishes the derived value, and `scripts/deploy/bootstrap_state.sh`
prints the finished `-backend-config` line once you hand it the bucket name, so the digits
are copied rather than remembered. Where the id appears as **recorded evidence** — a quoted
apply refusal, a committed plan — it stays, because scrubbing a measurement is the one
thing `docs/HONESTY.md` will not do. The plans under `evidence/deploy/` therefore contain
it, in ARNs and in `output.aws_account_id`, and that is deliberate.

---

## Quick start

```bash
# 1. the state bucket — Terraform cannot create the bucket it stores its state in.
#    Derive the account rather than typing it; bootstrap_state.sh then prints the exact
#    -backend-config line for step 2 (add --print-backend-config to print without writing).
ACCOUNT="$(aws sts get-caller-identity --query Account --output text)"
scripts/deploy/bootstrap_state.sh --bucket "mainline-demo-tfstate-${ACCOUNT}"

# 2. init against it
cd infra/envs/demo
terraform init \
  -backend-config="bucket=mainline-demo-tfstate-<account-id>" \
  -backend-config="region=ap-southeast-1"

# 3. THE SHIPPING SHAPE — a public Function URL that is the demo hostname
scripts/deploy/build_lambda.sh --arch arm64
terraform apply \
  -var enable_cloudfront=false \
  -var lambda_package_path=../../../out/lambda/mainline-demo-api-arm64.zip \
  -var lambda_architecture=arm64

# 4. THE UPGRADE — only after AWS Support lifts the CloudFront hold
terraform apply -var enable_cloudfront=true    # …plus the same two lambda vars
```

To review without applying, and without touching state at all:

```bash
terraform init -backend=false
terraform validate
```

`plan` needs an initialised backend, so the committed plan evidence was produced with a
throwaway local backend pointed outside the repository. That is recorded in
[`docs/deploy/terraform-plan.md`](../../../docs/deploy/terraform-plan.md), which also
carries the SHA-256 of each artefact.

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

That is the theory. **The theory alone would have shipped a broken root**, and the three
sections below are the reason this page exists.

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
dodge. `try` catches exactly that error and yields `""`.

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

`var.enable_cloudfront` is a plain `bool` variable for the same reason, and that is why
`count = var.enable_cloudfront ? 1 : 0` on `module "site"` is safe: a variable is constant
by the time counts are evaluated.

### Failure 3 — the same trap, in mirror image

`module.site` is now counted too, so the reverse reference became an index as well. It is
written to the identical rule:

```hcl
cloudfront_distribution_arn = try(module.site[0].distribution_arn, "")   # RIGHT
cloudfront_distribution_arn = join("", module.site[*].distribution_arn)  # WRONG
```

The splat form would depend on `module.site (close)`, which every S3 resource and the
distribution feed — and the distribution depends, via `local.api_origin_domain`, on the api
module. The loop closes exactly as it did the first time, backwards. **Anything wired
between these two modules in future must go through `try()` and an index, in both
directions, or not be wired at all.** The same rule governs `outputs.tf`, where every
site-shaped output is `try(module.site[0].x, null)`.

### The result, measured

Terraform v1.14.8, `hashicorp/aws v6.58.0`, real AWS credentials, on this machine,
2026-08-11:

```
terraform validate                                    Success! The configuration is valid.
terraform plan -var enable_cloudfront=false           Plan: 11 to add, 0 to change, 0 to destroy.
terraform plan -var enable_cloudfront=true            Plan: 22 to add, 0 to change, 0 to destroy.
terraform plan -var enable_cloudfront=true  \
               -var enable_api=false                  Plan:  9 to add, 0 to change, 0 to destroy.
terraform plan -var enable_cloudfront=false \
               -var enable_api=false                  Error: Module output value precondition failed
terraform fmt -check -recursive infra/                (no output; exit 0)
```

**One plan, one apply, no cycle, in every configuration that builds anything.** The fourth
row is the intended refusal: with both switches off this root creates nothing, so
`demo_url` has no source and says so rather than returning `""`. The first two plans are
committed verbatim under `evidence/deploy/`.

---

## Module contract

This root is the only caller of both modules, so this section is normative. Three of these
clauses exist *only* because the harness above found them; they are not style.

### `demo-api` — owns the hostname in the default shape

| Input | Type | Meaning |
|---|---|---|
| `function_name` | string | The whole Lambda name; also fixes the log group, alarms and dashboard. |
| `url_authorization_type` | string | `"NONE"` or `"AWS_IAM"`. **Derived from `var.enable_cloudfront` — the single architectural switch.** |
| `package_path` | string | The zip from `build_lambda.{sh,ps1}`. Must exist at plan time; `source_code_hash` reads it. |
| `architecture` | string | Must match the zip. A mismatch is a clean plan, a clean apply, and `ELFCLASS` on the first request. |
| `dsn_parameter_name` | string | **Name only.** Terraform never holds the DSN. |
| `cloudfront_distribution_arn` | string | The `SourceArn` on the one invoke grant. `""` when there is no distribution. |
| `log_retention_days` | number | |
| `tags` | map | |

Required outputs: `function_name`, `function_url`, `function_url_domain`,
`authorization_type`, `cloudfront_invoke_grant_created`.

> **`aws_lambda_permission` must be the module's ONLY reference to
> `var.cloudfront_distribution_arn`.** If the function, the Function URL, the role or the
> log group ever reads it, the cycle is real and no amount of indexing saves it.

### `demo-site` — optional, `count`-gated, absent by default

| Input | Type | Meaning |
|---|---|---|
| `name_prefix` | string | Composed into resource names. Must keep the `mainline-demo-` prefix. |
| `bucket_name` | string | Explicit, globally unique, private. Derived from the account id at plan time. |
| `enable_api` | bool | **Plan-time known.** The only thing `count`/`for_each` may key on. |
| `api_origin_domain` | string | Bare hostname, no scheme, no path. May be unknown at plan time. `""` means no second origin. |
| `price_class` | string | |
| `tags` | map | Merged on top of `default_tags`. |

Required outputs: `bucket_name`, `distribution_id`, `distribution_arn`,
`distribution_domain_name`.

> **The module must not derive `count` or `for_each` from `api_origin_domain != ""`.**
> See Failure 2.
>
> **Every reference to its outputs must be indexed and wrapped in `try`.** See Failure 3.

---

## What is deliberately absent

| Not here | Why |
|---|---|
| **DynamoDB lock table** | `use_lockfile = true` is native S3 locking since Terraform 1.10. Saves $0.25/month and, more usefully, one stateful resource teardown would have to find. |
| **Route 53 zone + ACM certificate** | A hosted zone is $0.50/month, and an ACM cert for CloudFront must be issued in `us-east-1`, which means a second provider alias. Both a Function URL and `dXXXXXXXX.cloudfront.net` are valid HTTPS on an AWS-issued certificate, free. |
| **Any secret** | The CockroachDB DSN goes to SSM Parameter Store as a SecureString written by `aws ssm put-parameter`. Terraform is given the parameter *name*. A Terraform-managed secret is a plaintext secret in the state file. |
| **CloudWatch Synthetics canary** | One canary at five-minute intervals is 8,640 runs a month at $0.0012 — **$10.37/month**, thirty times the cost of everything else here combined. |
| **A committed `.tfvars`** | Every default already works. |
| **A literal account id** | Decision D2. Derived from STS everywhere it is needed. |

---

## OpenTofu

Everything in this root is in the common subset: `hashicorp/aws` only, no
`terraform { encryption { … } }` block, no Terraform Cloud block, no provider aliases.

```bash
tofu init -backend-config="bucket=mainline-demo-tfstate-<account-id>"
tofu apply -var enable_cloudfront=false
```

works unchanged. Terraform v1.14.8 is what is installed on the build machine and OpenTofu
is not, so **Terraform is what the claims on this page were measured with**; the OpenTofu
commands above are stated as compatible, not as verified. That distinction is the point of
`docs/HONESTY.md` and it applies to this page too.

---

## Outputs, and who reads them

| Output | Consumer | Null when |
|---|---|---|
| `demo_url` | the submission form; `demo_acceptance.py` | never — the precondition refuses the configuration instead |
| `demo_url_source` | the plan reviewer: names which expression won, at plan time | never |
| `enable_cloudfront` | the deploy report; the acceptance run's shape assertion | never |
| `deploy_summary` | `deploy.sh` / `deploy.ps1` — one `terraform output -json` instead of fourteen | never |
| `api_function_url` | the acceptance run; `curl` | `enable_api = false` |
| `api_authorization_type` | asserted against `enable_cloudfront`; a disagreement is a finding | `enable_api = false` |
| `api_function_name` | `aws logs tail /aws/lambda/<this>` when `/v1/health` is unhappy | `enable_api = false` |
| `distribution_id` | the CloudFront invalidation, when there is a distribution | `enable_cloudfront = false` |
| `site_bucket` | `aws s3 sync`; `teardown.sh` | `enable_cloudfront = false` |
| `aws_account_id` | the deploy script's account assertion. Read from STS at run time, not committed | never |

None of them is sensitive, and none of them can be, because Terraform never held a
credential. The committed plan was checked for secret-shaped values and carries none — see
[`docs/deploy/terraform-plan.md`](../../../docs/deploy/terraform-plan.md).
