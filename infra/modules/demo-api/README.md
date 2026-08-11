<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: CC-BY-4.0
-->

# `demo-api` — the Lambda that **is** the demo hostname

One `python3.13` Lambda, one Function URL whose authorisation type is now a variable
defaulting to **`NONE`**, one execution role that can read exactly one SSM parameter, one
log group with a finite retention, four alarms and a dashboard. Region `ap-southeast-1`
(Singapore), beside the CockroachDB Cloud cluster.

Under **decision D1** ([`docs/leads/ship-final.md`](../../../docs/leads/ship-final.md) §1.4)
this module is no longer half a stack. It is the whole demo origin: the console SPA, the
signed evidence bundle and `/v1/*` answer on one hostname, and that hostname is this
function's own URL.

**Why Singapore.** Lambda→CRDB in-region is single-digit milliseconds. The same call from
`ap-southeast-2` pays roughly 90 ms each way, and the gate surface makes six of them —
about 1.1 s of pure geography on the one screen the judges look at.

---

## The two shapes

`var.url_authorization_type` takes exactly two values. Everything else in the module is
identical between them.

### `NONE` — the default, and the demo

```
 judge's browser ──► https://<id>.lambda-url.ap-southeast-1.on.aws   HTTPS, AWS cert
                     │  AWS Lambda · python3.13 · 512 MB · 15 s      ONE origin
                     │
                     │   GET  /                → index.html (console SPA)
                     │   GET  /assets/*        → hashed js/css, immutable
                     │   GET  /bundle/*        → verified EvidenceBundle  (REPLAY)
                     │   GET  /v1/health       → liveness + cluster fingerprint
                     │   GET  /v1/*            → 12 read resources        (LIVE)
                     │   POST /v1/demo/gate-run→ four beats, one txn, rolled back
                     └──────────────┬──────────────────────────────────────────────
                                    │ pgwire · TLS · same region
                                    ▼
                CockroachDB Cloud Basic · mainline_demo · aws-ap-southeast-1

 aws_lambda_permission.cloudfront_invoke : count = 0 — ABSENT FROM THE PLAN
 cors block                              : ABSENT — same origin, nothing to allow
```

### `AWS_IAM` — the pre-D1 shape, kept and currently unbuildable

```
 judge's browser ──► CloudFront ──/v1/*──► Lambda Function URL (AWS_IAM, OAC-signed)
                          │                          │ pgwire, TLS, same region
                          └─default──► S3 (OAC)      ▼
                                        CockroachDB Cloud Basic · Singapore

 aws_lambda_permission.cloudfront_invoke : count = 1, principal cloudfront.amazonaws.com,
                                           SourceArn = var.cloudfront_distribution_arn
 an unsigned `curl` at the Function URL   : 403 Forbidden, empty body
```

### Why `NONE` is the default

Not preference. AWS refuses to create a CloudFront distribution on this account:

```
Error: creating CloudFront Distribution: ... StatusCode: 403,
RequestID: 3e63e30d-8c5b-441b-a01b-b70085eba504, AccessDenied:
Your account must be verified before you can add new CloudFront resources.
```

recorded in [`docs/deploy/RUNBOOK.md`](../../../docs/deploy/RUNBOOK.md):26 from a real
`terraform apply`, and reproduced from a bare `aws cloudfront create-distribution` with no
Terraform involved. The identity holds `AdministratorAccess`; this is an **account-level
verification hold**, liftable only by AWS Support, on a queue.

With no distribution there is no principal to grant `lambda:InvokeFunctionUrl` to. An
`AWS_IAM` Function URL is then not a hardened demo — it is a URL that answers `403` to
everyone, including the judges. So the module's central assumption inverts: the Function
URL **is** the hostname, and CloudFront becomes an optional upgrade.

**This is a real widening and the module does not dress it up.** A `NONE` URL is a public
gateway to a database. What actually bounds it is written down rather than assumed:

| bound | value | what it stops |
|---|---|---|
| `reserved_concurrent_executions` | `20` | a hard cap. The only control here that stops a bill instead of reporting one. |
| the handler's write surface | one txn, ends in `ROLLBACK` | the four beats leave no committed state; two judges cannot collide. |
| CockroachDB Basic `spend_limit` | $25 / 100 M RU | the database half of the bill has its own ceiling. |
| `<fn>-concurrency` alarm | `> 20` | the abuse tripwire, readable by `describe-alarms`. |
| `<fn>-throttles` alarm | `> 0` | says the cap is biting; a throttled Function URL invocation is HTTP 429. |

That is a smaller claim than *"invocable by one distribution and nothing else"*, and it is
the true one for this account.

### What changes if the hold lifts

Three lines, one apply, no rebuild:

```hcl
module "demo_api" {
  # ...
  url_authorization_type      = "AWS_IAM"
  cloudfront_distribution_arn = module.site.distribution_arn
}
```

The Function URL flips to `AWS_IAM` (an in-place update, not a replacement — `url_id` and
therefore the hostname survive), the `lambda:InvokeFunctionUrl` grant appears, and the URL
in the submission form changes from the `lambda-url` host to the distribution's. Nothing
in the package, the console build or the database changes: the SPA already sets
`base: './'` and uses hash routing, so it serves correctly from any prefix.

The console's `dist/` is untouched either way, which is the property that made D1 cheap.

---

## Quick start

```bash
# 1. Build the package (Windows PowerShell, or bash/Git Bash — both produce the same bytes)
pwsh scripts/deploy/build_lambda.ps1                  # arm64, the default
bash scripts/deploy/build_lambda.sh --arch arm64      # identical sha256

# 2. Write the DSN OUT OF BAND. Terraform never sees it.
aws ssm put-parameter --region ap-southeast-1 \
  --name /mainline/demo/dsn --type SecureString \
  --value 'postgresql://mainline-sql:...@...ap-southeast-1.cockroachlabs.cloud:26257/mainline_demo?sslmode=verify-full' \
  --overwrite

# 3. Init, validate, plan — from the env root, never from this directory
terraform -chdir=infra/envs/demo init -backend=false
terraform -chdir=infra/envs/demo validate
terraform -chdir=infra/envs/demo plan -out=demo.tfplan
```

**`terraform apply` is not run by any worker in this domain.** The plan is committed and
the orchestrator reviews it with the founder. See `docs/leads/ship-final.md` §2.2.

The D1 shape, in full — note that `cloudfront_distribution_arn` is now *absent*, not empty
by accident:

```hcl
module "demo_api" {
  source = "../../modules/demo-api"

  function_name = "mainline-demo-api"
  package_path  = "${path.root}/../../out/lambda/mainline-demo-api-arm64.zip"
  # url_authorization_type defaults to "NONE"
  # web_root               defaults to "/var/task/web"
  # dsn_parameter_name     defaults to "/mainline/demo/dsn"
}
```

---

## Inputs

| Variable | Type | Default | What it is |
|---|---|---|---|
| `package_path` | `string` | *(required)* | Path to the zip from `scripts/deploy/build_lambda.*`. Must exist at plan time — `source_code_hash` is `filebase64sha256` of it. |
| **`url_authorization_type`** | `string` | **`NONE`** | `NONE` or `AWS_IAM`, and nothing else. `NONE` makes the Function URL public and therefore *the demo hostname*; `AWS_IAM` creates the CloudFront invoke grant. See [the two shapes](#the-two-shapes). |
| `cloudfront_distribution_arn` | `string` | `""` | The **one** distribution allowed to invoke the Function URL. Becomes `SourceArn` on the grant. Was required; is now optional, because under `NONE` there is no grant to scope. Required again — by a precondition — when `url_authorization_type = "AWS_IAM"`. |
| **`web_root`** | `string` | **`/var/task/web`** | Absolute path *inside the package* of the console SPA, published as `$MAINLINE_WEB_ROOT`. `/var/task` is `$LAMBDA_TASK_ROOT`; `web/` is where the build script puts `dist/`. |
| `function_name` | `string` | `mainline-demo-api` | Fixes the log group, the alarm names and the dashboard name. |
| `architecture` | `string` | `arm64` | `arm64` or `x86_64`. **Must match the package.** Enforced by a `lifecycle.precondition`. |
| `dsn_parameter_name` | `string` | `/mainline/demo/dsn` | **Name only.** Leading slash optional and normalised. No wildcard accepted. |
| `ssm_kms_key_arn` | `string` | `""` | Empty = the account's `aws/ssm` key, scoped by condition instead of by resource. See [KMS](#the-kms-grant-is-scoped-by-condition-not-by-resource). |
| `restrict_kms_to_parameter` | `bool` | `true` | Add `kms:EncryptionContext:PARAMETER_ARN` to the `Decrypt` grant. |
| `demo_database` | `string` | `mainline_demo` | Published as `$MAINLINE_DEMO_DATABASE`. Declarative — see [environment](#environment-variables). |
| `scenario_permit_id` | `string` | `077a6fdd-…504d` | The permit the three beats drive. Published under two names — see [environment](#environment-variables). |
| `log_level` | `string` | `INFO` | Published as `$LOG_LEVEL` **and** wired into `logging_config.application_log_level`. |
| `memory_size` | `number` | `512` | MB. CPU scales with it; the free tier is not the binding constraint. |
| `timeout` | `number` | **`15`** | Seconds. Was 25. See [the timeout is 15 s](#the-timeout-is-15-s-and-the-number-is-arithmetic). Still capped at 29 so every configuration stays valid for CloudFront's 30 s origin read timeout. |
| `reserved_concurrent_executions` | `number` | `20` | Hard cost cap. `-1` = unreserved (and see the concurrency-alarm caveat). |
| `log_retention_days` | `number` | `7` | CloudWatch retention. `0` (never expire) is not offered. **Unchanged by D1.** |
| `duration_p99_threshold_ms` | `number` | **`12000`** | p99 alarm threshold, 80 % of the 15 s timeout. Moved *because* the timeout moved — a 20 000 ms threshold on a 15 000 ms ceiling can never breach. A plan-time precondition refuses any value not strictly below `timeout × 1000`. |
| `concurrency_alarm_threshold` | `number` | `20` | Abuse tripwire. |
| `alarm_actions` | `list(string)` | `[]` | SNS topics. Empty on purpose — the alarms exist to be *read*. |
| `create_dashboard` | `bool` | `true` | First three dashboards per account are free. |
| `extra_environment` | `map(string)` | `{}` | Merged in. Cannot carry `MAINLINE_DSN`, a Lambda reserved name, or a key this module sets — now including `MAINLINE_WEB_ROOT`, which has its own variable. |
| `tags` | `map(string)` | `{}` | Merged **under** the mandatory three, which a caller cannot override. |

There is still **no** variable that can carry the DSN value, and there never will be; that
omission is the point of the module. The `url_authorization_type` variable **is** new, and
the reversal is explained at the top of `variables.tf` rather than quietly performed.

## Outputs

| Output | Example | Used by |
|---|---|---|
| **`authorization_type`** | `NONE` | read back **off the resource**, not off the variable. `terraform output -raw authorization_type` is the assertion the deploy report makes before it trusts `function_url`. |
| **`cloudfront_invoke_grant_created`** | `false` | mechanical proof that the `NONE` plan has no CloudFront-shaped resource. |
| `function_name` | `mainline-demo-api` | `aws lambda get-function-configuration` |
| `function_arn` | `arn:aws:lambda:ap-southeast-1:…:function/mainline-demo-api` | teardown, judge pack |
| `function_url` | `https://abc123.lambda-url.ap-southeast-1.on.aws/` | **the demo URL itself when `authorization_type = NONE`** — the value that goes in `SUBMISSION.json.demo_url` and the submission form. An origin, not a destination, under `AWS_IAM`. |
| `function_url_domain` | `abc123.lambda-url.ap-southeast-1.on.aws` | the `demo-site` CloudFront origin `domain_name` (rejects scheme and path). Only meaningful in the `AWS_IAM` shape. |
| `function_url_id` | `abc123` | origin id, log filters |
| `web_root` | `/var/task/web` | the deploy script, to assert the uploaded zip actually contains that directory |
| `log_group_name` | `/aws/lambda/mainline-demo-api` | `aws logs tail` |
| `log_group_arn` | `arn:aws:logs:…:log-group:/aws/lambda/mainline-demo-api:*` | future subscription filter |
| `role_arn` / `role_name` | `…:role/mainline-demo-api-exec` | `aws iam get-role-policy` |
| `dsn_parameter_arn` | `arn:aws:ssm:ap-southeast-1:…:parameter/mainline/demo/dsn` | the deploy script, so `put-parameter` writes to exactly the ARN the policy grants |
| `architecture` | `arm64` | deploy report |
| `package_sha256_base64` | `0h5puChORMwV9wzxVmRP2KKkuq/B/bl7Ba7RYIF/KMU=` | deploy report |
| `alarm_names` | 4 names | the hourly `demo-health` workflow's `describe-alarms` check |
| `dashboard_name` | `mainline-demo-api` or `null` | — |

---

## The decisions

### The grant is `count`-gated on the auth type — and *not* on the ARN

The `AWS_IAM` shape still creates exactly one grant, scoped to one distribution:

```hcl
resource "aws_lambda_permission" "cloudfront_invoke" {
  count = local.create_cloudfront_invoke_grant ? 1 : 0   # == (auth == "AWS_IAM")

  action                 = "lambda:InvokeFunctionUrl"
  principal              = "cloudfront.amazonaws.com"
  source_arn             = var.cloudfront_distribution_arn   # ONE distribution
  function_url_auth_type = var.url_authorization_type        # not hard-coded

  lifecycle {
    precondition {
      condition = var.cloudfront_distribution_arn != ""
      # ...
    }
  }
}
```

Without `source_arn` the statement would read "any CloudFront distribution in any account
may invoke this", which includes one an attacker creates in their own account and points
at our origin. That is why the empty ARN is refused rather than tolerated.

**Why the emptiness test is a precondition and not a second `count` conjunct.** The obvious
spelling — `count = auth == "AWS_IAM" && var.cloudfront_distribution_arn != "" ? 1 : 0` —
does not survive the way the env root wires this module. `infra/envs/demo/main.tf` passes
`module.site.distribution_arn`, which does not exist until the distribution does, so the
value is *unknown at plan time*, and a `count` may not depend on one. Measured on this
machine, Terraform v1.14.8, on a two-resource fixture using only the built-in
`terraform_data` provider:

```
$ terraform plan
Plan: 1 to add, 0 to change, 0 to destroy.

Error: Invalid count argument
  on main.tf line 7, in resource "terraform_data" "gated":
   7:   count = terraform_data.producer.output != "" ? 1 : 0

The "count" value depends on resource attributes that cannot be determined
until apply, so Terraform cannot predict how many instances will be created.
```

The same fixture with the count on a plan-time-known variable and the unknown value moved
into a `lifecycle.precondition` plans cleanly and defers the check to apply. That is the
shape shipped. `infra/envs/demo/main.tf` already carries the sibling of this failure — its
header records `Invalid count argument` for `demo-site` — so this is the second time the
same rule has been paid for in this stack, and it is now written down in both places.

Proven against the real module, all three shapes, `terraform plan` with live credentials
(read-only; **no apply**):

```
url_authorization_type = "NONE"            → Plan: 11 to add
    resources in module.api:
      aws_cloudwatch_dashboard.this[0]         aws_iam_role.this
      aws_cloudwatch_log_group.this            aws_iam_role_policy.dsn_access
      aws_cloudwatch_metric_alarm.concurrency  aws_iam_role_policy_attachment.basic_execution
      aws_cloudwatch_metric_alarm.duration_p99 aws_lambda_function.this
      aws_cloudwatch_metric_alarm.errors       aws_lambda_function_url.this
      aws_cloudwatch_metric_alarm.throttles
    cloudfront-shaped resources: []            ← the whole claim, mechanically

url_authorization_type = "AWS_IAM"         → Plan: 12 to add
    module.api.aws_lambda_permission.cloudfront_invoke[0]
      -> cloudfront.amazonaws.com
       | arn:aws:cloudfront::111122223333:distribution/E1EXAMPLE1EXAM
       | AWS_IAM

url_authorization_type = "AWS_IAM", no ARN → Error: Resource precondition failed
    var.cloudfront_distribution_arn is ""
    "...a grant to cloudfront.amazonaws.com with no SourceArn reads \"any CloudFront
     distribution in any account may invoke this URL\", including one an attacker creates."

url_authorization_type = "none"            → Error: Invalid value for variable
    "url_authorization_type must be exactly \"NONE\" ... or \"AWS_IAM\" ...
     No other value is accepted, and the empty string is not a synonym for either."
```

(The distribution ARN above is AWS's documentation placeholder account, not this one —
decision D2.)

### There is no `cors` block, and that is the narrowest thing that works

Under D1 the SPA and the API share one origin: `GET /` and `GET /v1/*` are the same
hostname, scheme and port. **Every request the console makes is same-origin**, so the
browser never sends an `Origin` header and never applies a CORS check. A
`cors { allow_origins = ["*"] }` block would therefore change nothing about whether the
demo works — and would change exactly one thing about what an attacker can do: it turns
"any page on the internet may make a no-credentials request to this URL and *not read the
answer*" into "any page on the internet may make one and read it".

A permissive CORS block nobody needs is an attack surface nobody audited. The plan
confirms the block is absent rather than empty:

```
url cors        []
url invoke_mode BUFFERED
```

If a future caller ever serves the console from a second hostname, the repair is a `cors`
block naming *that hostname*, in the same commit as the second hostname — never `*`.

### The timeout is 15 s, and the number is arithmetic

A cold invocation pays, in order: python3.13 runtime init; `import psycopg` plus
`psycopg_binary` (a 6.7 MB C extension being `dlopen`'d); one SigV4 `ssm:GetParameter` and
the KMS decrypt behind it; the TLS + pgwire connect to CockroachDB Cloud; then the four-beat
gate transaction, which is six round trips inside one `SAVEPOINT`/`ROLLBACK` envelope.

The one number **measured** rather than estimated is the connect: **2.91 s** from this
machine to `mainline-dev-31219.j77.aws-ap-southeast-1.cockroachlabs.cloud`
(`docs/leads/ship-final.md` §1.1). That is a *ceiling*, not the Lambda figure — it crosses
the public internet from Australia, where the function is in-region and pays single-digit
milliseconds per round trip. It is quoted because it is the only connect latency anyone has
observed against this cluster, and a budget built on the worst number available is the one
that survives being wrong.

2.91 s worst-case connect + a cold psycopg import measured in hundreds of milliseconds +
six in-region round trips + ~5 s of margin for the tail nobody has measured = **15 s**.

It is also 10 s *below* the previous default. 25 s was sized against CloudFront's 30 s
origin read timeout; with no CloudFront that constraint is not binding, and a demo that
hangs 25 s before failing is a demo whose tab is already closed. The 29 s validation
ceiling stays, so every configuration of this module remains valid for the `AWS_IAM` shape.

**The alarm moved with it, and it had to.** `duration_p99_threshold_ms` was 20 000 ms.
Lambda terminates the invocation at `timeout` and the `Duration` datapoint is capped there,
so a 20 000 ms alarm on a 15 000 ms ceiling can never breach — the exact shape of a control
that looks present and is not. The default is now 12 000 ms and the relationship is
enforced at plan time:

```
Error: Resource precondition failed
  on main.tf line 458, in resource "aws_cloudwatch_metric_alarm" "duration_p99":
 458:       condition     = var.duration_p99_threshold_ms < var.timeout * 1000
    │ var.duration_p99_threshold_ms is 20000
    │ var.timeout is 15

duration_p99_threshold_ms (20000 ms) is not below the function timeout (15 s = 15000 ms).
Lambda terminates the invocation at the timeout and the Duration datapoint is capped there,
so this alarm could never breach - a control that looks present and is not.
```

### The DSN is written out of band, and Terraform never holds it

`terraform.tfstate` is a **plaintext** record of every value Terraform manages. A
`aws_ssm_parameter` resource carrying a SecureString puts the password in the state file,
in the S3 state bucket, in every `terraform state pull`, and in the local `.terraform`
cache of anyone who has ever run a plan — an audience strictly wider than the parameter's
own. Marking it `sensitive` only stops it printing; it does not stop it being stored.

So the parameter is **not a resource in this module**. `scripts/deploy` writes it with
`aws ssm put-parameter --type SecureString` before the first apply. Terraform is given the
*name*; the execution role gets `ssm:GetParameter` on exactly the ARN derived from it; the
handler (`mainline_demo_api.db`) fetches it once per cold start over a SigV4-signed
`GetParameter` and caches it for the life of the execution environment. `terraform show`
cannot display the password because Terraform never held it.

`output "dsn_parameter_arn"` exists so the deploy script writes to precisely the ARN the
policy grants, rather than to a name that looks the same and normalises differently.

### The KMS grant is scoped by condition, not by resource

**Unchanged by D1.** `log_retention_days`, the SSM read grant and the KMS condition are
exactly as they were: the DSN is a SecureString written by the deploy script, never by
Terraform, and the execution role gets `ssm:GetParameter` + `kms:Decrypt` on that one
parameter ARN and nothing wider.

> **Disclosure note (decision D2).** The two blocks below are **recorded evidence** — a
> command and the bytes it returned on 2026-08-10 — so the account id stays. Everywhere it
> was an *executable default* or an assumption this module made, it is gone: nothing in
> `variables.tf`, `main.tf` or `outputs.tf` contains a literal account id, and every ARN
> the module builds is derived from `data.aws_caller_identity.current.account_id`.
>
> Measured after this change, with the id taken from STS rather than typed here —
> `ACCT=$(aws sts get-caller-identity --query Account --output text);
> grep -c "$ACCT" infra/modules/demo-api/*.tf` → **0, 0, 0, 0**; the same grep over
> `README.md` → **3 lines**, all inside the two evidence blocks immediately below (the
> `kms list-aliases` transcript, and the `PARAMETER_ARN` encryption
> condition). Those three lines are declared to the disclosure register that
> `docs/submission/DISCLOSURE-DECISIONS.yaml` holds, under the path
> `infra/modules/demo-api/README.md`, reason *"quoted AWS API output, retained because a
> redacted transcript is not a transcript"*. An undeclared occurrence stays `UNRESOLVED`
> and stays red; that is the point of the register.

Measured on 2026-08-10 in account `022950218246`:

```
$ aws kms list-aliases --region ap-southeast-1 \
    --query "Aliases[?AliasName=='alias/aws/ssm']"
[{"AliasName": "alias/aws/ssm",
  "AliasArn": "arn:aws:kms:ap-southeast-1:022950218246:alias/aws/ssm"}]
```

Note the absent `TargetKeyId`: the AWS-managed key **does not exist yet**. It is created
the first time a SecureString is written to the region. A `data "aws_kms_alias"` would
therefore fail the plan on a clean region — a chicken-and-egg in the one place a deploy
cannot afford one. IAM also refuses an *alias* ARN in a `Resource` element, so the alias
could not be named directly even if it resolved.

The grant is scoped by two conditions instead:

```json
{
  "Sid": "DecryptThatParameterAndNothingElse",
  "Action": "kms:Decrypt",
  "Resource": "*",
  "Condition": { "StringEquals": {
    "kms:ViaService": "ssm.ap-southeast-1.amazonaws.com",
    "kms:EncryptionContext:PARAMETER_ARN":
      "arn:aws:ssm:ap-southeast-1:022950218246:parameter/mainline/demo/dsn"
  }}
}
```

This is **tighter than naming the key would be**. The `aws/ssm` key protects *every*
SecureString in the account, so `Resource: <that key ARN>` alone would let this role
decrypt all of them. `PARAMETER_ARN` is the encryption context SSM sets on each
SecureString, so the grant reduces to "the ciphertext of this one parameter, and only when
SSM is the caller". Set `ssm_kms_key_arn` once the key exists to narrow the resource too.

**Honest limit:** this policy has been read, planned and diffed, but never exercised
against a live `Decrypt`, because the module has not been applied. If a cold start fails
with `AccessDeniedException` on `kms:Decrypt` — which `/v1/health` surfaces as
`dsn_unavailable` — set `restrict_kms_to_parameter = false` to fall back to the
`kms:ViaService` condition alone, which is still scoped to SSM-mediated decrypts in this
region.

### The log group is a resource, and there is no canary

Lambda creates `/aws/lambda/<name>` on first invocation if it does not exist, with **no
expiry**, owned by nothing. It survives `terraform destroy` and accrues storage forever.
So the group is declared here with a 7-day retention, and the function's
`logging_config.log_group` *references* it — the ordering is an edge in the dependency
graph, not a naming convention two resources happen to agree on:

```
$ terraform graph | grep lambda_function
"module.demo_api.aws_lambda_function.this" -> "module.demo_api.aws_cloudwatch_log_group.this"
"module.demo_api.aws_lambda_function.this" -> "module.demo_api.aws_iam_role_policy.dsn_access"
"module.demo_api.aws_lambda_function.this" -> "module.demo_api.aws_iam_role_policy_attachment.basic_execution"
```

**No CloudWatch Synthetics canary.** One canary at five-minute intervals is 8 640 runs a
month at $0.0012 = **$10.37/month — thirty times the cost of the entire rest of the
stack.** Health checking is a GitHub Actions cron against `/v1/health` —
`.github/workflows/demo-health.yml` — which costs nothing and whose failures are visible in
the repository the judges are already reading. It fails every hour today, correctly: there
is no deployed demo. It goes green on its own the moment there is one.

---

## Architecture: `arm64`, and the tag that makes it work

**Decision: `arm64`.** Roughly 20 % cheaper per GB-second, and it runs. But the recipe in
the brief does not produce it, and the reason is worth writing down.

Measured 2026-08-10 with `D:/CoackroachDBxAWS/mainline/.venv/Scripts/python.exe -m pip`:

| `--platform` | `psycopg-binary==3.3.4` | Wheel |
|---|---|---|
| `manylinux2014_x86_64` | ✅ | `…-cp313-cp313-manylinux2014_x86_64.manylinux_2_17_x86_64.whl` (5.2 MB) |
| `manylinux2014_aarch64` | ❌ | `ERROR: No matching distribution` — *"from versions: 3.2.2 … 3.2.13"* |
| `manylinux_2_17_aarch64` | ❌ | same error |
| `manylinux_2_28_aarch64` | ✅ | `…-cp313-cp313-manylinux_2_27_aarch64.manylinux_2_28_aarch64.whl` (6.7 MB) |

psycopg-binary 3.3.x **does** publish an aarch64 wheel; it just stopped tagging it for
glibc 2.17. `manylinux2014_aarch64` silently resolves back to 3.2.13, and the naive fix —
pinning the older version for arm64 only — would have shipped a different driver on each
architecture. So the build script carries a per-architecture tag table instead of one
string, and the arm64 build asks for glibc 2.28.

Lambda's `python3.13` runtime is Amazon Linux 2023 / **glibc 2.34**, which satisfies it.
Verified by unzipping each package inside the runtime image and importing:

```
$ docker run --rm --platform linux/arm64 -v .../out/lambda:/pkg:ro \
    --entrypoint /bin/bash public.ecr.aws/lambda/python:3.13 -c \
    'cd /tmp && python -m zipfile -e /pkg/mainline-demo-api-arm64.zip pkg && ...'
NAME="Amazon Linux"
VERSION="2023"
ldd (GNU libc) 2.34
aarch64
psycopg 3.3.4
impl binary            <- the C implementation loaded, not the pure-Python fallback
libpq 180000
handler status 503     <- app.handler answered; 503 because no DSN is set in the container
```

The same run on `--platform linux/amd64` prints `x86_64` and the same four lines, so
`architecture = "x86_64"` is a supported fallback and not a theory — build with
`--arch x86_64` and set the variable to match.

The packaged driver was then pointed at a **real CockroachDB v26.2.5 node** from inside
the runtime image (`-e MAINLINE_DSN=postgresql://root@host.docker.internal:26257/w_w6_tf_api`),
on both architectures:

```
x86_64   status 503  reason no_bookkeeping  seconds 0.0214
aarch64  status 503  reason no_bookkeeping  seconds 0.0856   (under qemu emulation)
```

The 503 is the correct answer and the point of the test: the scratch database has no
migration chain, so `health()` reports `relation "trappoint.schema_attestation" does not
exist`. Reaching that verdict requires the zip's `psycopg_binary` to have loaded, opened a
pgwire connection and run a query — which is the whole claim the package needs to support.

| | `arm64` (default) | `x86_64` |
|---|---|---|
| pip platform tag | `manylinux_2_28_aarch64` | `manylinux2014_x86_64` |
| files in zip | 130 | 129 |
| unzipped | 24 770 085 B (23.6 MB) | 20 004 257 B (19.1 MB) |
| zipped | 7 023 004 B (6.7 MB) | 5 437 534 B (5.2 MB) |
| sha256 | `d21e69b8…817f28c5` | `0ba1668a…9c6793b4` |

Both are far inside Lambda's 50 MB zipped / 250 MB unzipped limits.

**A mismatched package deploys cleanly and then fails every single invocation** with an
`ELFCLASS` error, because Lambda does not inspect the `.so` files at deploy time. That
failure mode is caught at *plan* time by a `lifecycle.precondition` reading the manifest
the build script writes beside the zip:

```
Error: Resource precondition failed
  │ var.architecture is "x86_64"
  │ var.package_path is "./../lambda/mainline-demo-api-arm64.zip"

The package manifest beside ./../lambda/mainline-demo-api-arm64.zip was built for a
different architecture than var.architecture (x86_64). Rebuild with
`scripts/deploy/build_lambda.sh --arch x86_64`; a mismatched package deploys cleanly and
then fails every invocation with an ELFCLASS error.
```

---

## The build scripts

`scripts/deploy/build_lambda.ps1` and `scripts/deploy/build_lambda.sh` are twins. Both:

1. `pip install --no-deps --no-compile --target … --platform <tag> --implementation cp
   --python-version 3.13 --only-binary=:all: psycopg==3.3.4 psycopg-binary==3.3.4`
   — both distributions named explicitly, because `--platform` refuses to resolve the
   `psycopg[binary]` extra marker on a cross-platform target build;
2. copy `verticals/mainline/apps/demo-api/src/mainline_demo_api` in;
3. prune `__pycache__`, `*.pyc`, `*.dist-info/RECORD`, `INSTALLER`, `REQUESTED`, and
   `tzdata` (never installed under `--no-deps`, removed if it appears);
4. **refuse** if `mainline_demo_api/app.py`, `psycopg/` or `psycopg_binary/` is missing;
5. zip with every entry timestamp fixed to the ZIP epoch, entries sorted, fixed modes and
   a fixed compression level;
6. print the sha256 and write `<zip>.json` beside the artefact.

**Reproducibility is not decoration.** Terraform decides whether to redeploy from
`source_code_hash = filebase64sha256(var.package_path)`. A zip whose bytes move because
the clock moved shows a Lambda update in *every* plan, which trains an operator to ignore
the plan four days before a deadline.

Measured, this machine, 2026-08-10 — three consecutive PowerShell runs and one Git Bash
run of the arm64 build:

```
build_lambda: sha256     d21e69b8284e44cc15f70cf156644fd8a2a4baafc1fdb97b05aed160817f28c5   (pwsh, run 1)
build_lambda: sha256     d21e69b8284e44cc15f70cf156644fd8a2a4baafc1fdb97b05aed160817f28c5   (pwsh, run 2)
build_lambda: sha256     d21e69b8284e44cc15f70cf156644fd8a2a4baafc1fdb97b05aed160817f28c5   (pwsh, run 3)
build_lambda: sha256     d21e69b8284e44cc15f70cf156644fd8a2a4baafc1fdb97b05aed160817f28c5   (bash)
```

Output lands in `out/lambda/` — `out/` is in `.gitignore`; `build/` is not.

The pruning and packing are done by an embedded Python program that is byte-identical in
both scripts — 112 lines, pure ASCII, `sha256 e3e8a22932c76aeb…e714dde47` extracted from
either file — which is why the two shells agree. Determinism is asserted *on one machine*:
the deflate stream depends on the zlib build, so two different machines are not guaranteed
to agree, and the module never claims they do.

`uv` is not used — it is not installed on this machine, and every `just` recipe that
shells out to `uv run` is dead here.

---

## Environment variables the function receives

| Name | Read by | Notes |
|---|---|---|
| `MAINLINE_DSN_PARAM` | `mainline_demo_api.db` | The SecureString's **name**, normalised with a leading slash. |
| `MAINLINE_DEMO_DATABASE` | **nothing** | Declarative. See below. |
| `MAINLINE_SCENARIO_PERMIT_ID` | **nothing** | The name this module was specified to publish. |
| `MAINLINE_DEMO_PERMIT_ID` | `mainline_demo_api.scenario.from_env` | The name the code actually reads. Same value. |
| **`MAINLINE_WEB_ROOT`** | `mainline_demo_api.app` | **New under D1.** Where the console SPA lives inside the package: `/var/task/web` (`$LAMBDA_TASK_ROOT` + the `web/` directory the build script writes). Load-bearing — this function serves `/` as well as `/v1/*`, and a wrong value gives the judges a 404 at `/` beside a perfectly green `/v1/health`. From `var.web_root`; also emitted as an output so the deploy script can assert the zip contains it. |
| `LOG_LEVEL` | **nothing** | Conventional name. `logging_config.application_log_level` is what filters. |
| *(anything in `extra_environment`)* | varies | e.g. `MAINLINE_DEMO_ALLOW_MUTATION`, `MAINLINE_DEBUG`. |

Three honest notes, because a variable that looks configured and behaves inert is worse
than one that is absent:

* **`MAINLINE_SCENARIO_PERMIT_ID` is not read by anything.** `scenario.py` builds its
  override names as `ENV_PREFIX + "PERMIT_ID"` where `ENV_PREFIX = "MAINLINE_DEMO_"`, so
  the name it reads is `MAINLINE_DEMO_PERMIT_ID`. This module sets **both**, to the same
  value, so the specified name is present *and* the override actually takes effect. The
  discrepancy is between this module's brief and W3/W4's implementation; it is recorded
  rather than resolved, because `scenario.py` is not this worker's file.
* **`MAINLINE_DEMO_DATABASE` is not read by anything either.** The database is carried by
  the DSN. It is set so `aws lambda get-function-configuration` states which database the
  function is *supposed* to be pointed at without anyone decrypting the DSN; `/v1/health`
  reports the database it actually reached, and a disagreement between the two is a
  finding. (It shares the `MAINLINE_DEMO_` prefix that `scenario.from_env` scans, but
  `DATABASE` is not one of the six identifiers that function reads, so there is no
  collision.)
* **`LOG_LEVEL` does not filter anything by itself.** `logging_config.log_format = "JSON"`
  plus `application_log_level` is what the managed runtime honours, and it is set from the
  same variable, so the two cannot drift.

`MAINLINE_DSN` — a DSN passed directly — is **rejected** by `extra_environment`'s
validation. It is the escape hatch `db.py` offers for local development, and letting it
through here would put the password back in Terraform state through the side door.

---

## Alarms and dashboard

The first ten CloudWatch alarms per account are free; these are four of them. None has an
action by default: an SNS topic whose email subscription nobody confirmed is a control
that looks present and is not. With no actions they still evaluate, still show state, and
are still readable by `aws cloudwatch describe-alarms`, which is what the `demo-health`
cron reads.

| Alarm | Metric | Condition | Why |
|---|---|---|---|
| `<fn>-errors` | `Errors` Sum | `> 0` over 5 min | The handler is written never to raise: refusals are 200s with a `REFUSED` verdict, failures are JSON problem documents. An `Errors` datapoint means it raised anyway. |
| `<fn>-throttles` | `Throttles` Sum | `> 0` over 5 min | The reserved-concurrency cap is biting. A throttled Function URL invocation reaches the caller as HTTP 429 with no body from the handler — user-visible and undiagnosable from the browser. |
| `<fn>-duration-p99` | `Duration` p99 | `> 12 000 ms` | Approaching the 15 s timeout (80 % of it). On this stack that is nearly always the pgwire round trip, not the handler — `/v1/health` reports connect time separately. A plan-time precondition refuses a threshold at or above the timeout. |
| `<fn>-concurrency` | `ConcurrentExecutions` Max | `> 20` | Abuse tripwire. A judging session is a few browsers making four requests each. |

All four use `treat_missing_data = "notBreaching"`: no invocations is not a failure, it is
a demo nobody is looking at yet.

**Caveat on the concurrency alarm.** Lambda emits per-function `ConcurrentExecutions`
dependably for functions that *have* reserved concurrency. `reserved_concurrent_executions`
defaults to `20` — which is also the real cost cap, the only control here that stops a
bill rather than reporting one — so the metric is emitted. Set it to `-1` and this alarm
can sit in `INSUFFICIENT_DATA` and prove nothing.

The dashboard carries a text header, invocations + errors, duration p50/p99 with the alarm
threshold and the timeout drawn as annotations, concurrency + throttles, and an alarm-state
widget. Its body was validated against the real API:

```
$ aws cloudwatch put-dashboard --dashboard-name mainline-demo-api-w6-validate \
    --dashboard-body file://dash.json
{ "DashboardValidationMessages": [] }
```

(then deleted immediately; it existed for about four seconds).

## Cost

Everything is inside a perpetual free tier. Lambda: 1 M requests and 400 000 GB-s/month
free, against 512 MB × ~300 ms × 10 000 requests = 1 536 GB-s. Logs: 7-day retention, far
under the 5 GB free ingest. Alarms: 4 of the first 10. Dashboard: 1 of the first 3. SSM
Parameter Store Standard: free. Function URL: no charge beyond the invocation.
**≈ $0.00/month**, and the reserved-concurrency cap means that stays true under abuse. The
full itemisation, re-checked under D1, is in `docs/leads/ship-final.md` §2.1 — removing
CloudFront and the site bucket from the request path made the bill *smaller*, not larger.

**One line of that arithmetic did change under D1 and it is worth stating rather than
burying.** Serving the SPA from this function means every static asset is now a Lambda
invocation instead of an S3 GET behind a CDN: an `index.html` plus a handful of hashed
`assets/*` per page load, against a 1 M request/month free tier. A judging session is
hundreds of requests, not hundreds of thousands. It is inside the free tier by three orders
of magnitude, and if it ever were not, `reserved_concurrent_executions` still bounds it.

## Terraform / OpenTofu

`hashicorp/aws >= 6.0.0, < 7.0.0`; Terraform `>= 1.6.0`. Resolved to provider **v6.58.0**
on the build machine. Nothing here is Terraform-only, so `tofu init && tofu plan` works
unchanged. The provider floor is 6.0 because this module reads
`data.aws_region.current.region`, the attribute that replaced the deprecated `.name`.

The floor stays at **1.6** and not 1.9 deliberately. The one place this module wanted a
cross-variable `validation` block — "`duration_p99_threshold_ms` must be below
`timeout × 1000`" — is expressed as a `lifecycle.precondition` instead, which has worked
since 1.2. Raising a module's Terraform floor to buy syntax is a cost paid by every
consumer; a precondition costs nothing and refuses at the same moment.

### The commands, and their output on this machine

Run from the **repository root**, after this change, `2026-08-11T00:16:29Z`, Terraform
v1.14.8 on windows_amd64:

```console
$ terraform -chdir=infra/envs/demo init -backend=false
Initializing modules...
Initializing provider plugins...
- Reusing previous version of hashicorp/aws from the dependency lock file
- Using previously-installed hashicorp/aws v6.58.0

Terraform has been successfully initialized!

You may now begin working with Terraform. Try running "terraform plan" to see
any changes that are required for your infrastructure. All Terraform commands
should now work.

If you ever set or change modules or backend configuration for Terraform,
rerun this command to reinitialize your working directory. If you forget, other
commands will detect it and remind you to do so if necessary.
                                                              # exit 0

$ terraform -chdir=infra/envs/demo validate
Success! The configuration is valid.                          # exit 0

$ terraform fmt -check -diff infra/modules/demo-api
                                                              # exit 0, no diff
```

And the outputs, from the `NONE`-shape plan above:

```
Changes to Outputs:
  + authorization_type              = "NONE"
  + cloudfront_invoke_grant_created = false
  + function_arn                    = (known after apply)
  + function_name                   = "mainline-demo-api"
  + function_url                    = (known after apply)
  + log_group_name                  = "/aws/lambda/mainline-demo-api"
  + role_arn                        = (known after apply)
  + web_root                        = "/var/task/web"

resources: 11
lambda_permission present: False
```

`authorization_type` is `"NONE"` at *plan* time — it is read off the resource, but the
provider knows the value without applying, which is what makes it usable as an assertion
before the deploy rather than after. `function_url` is `(known after apply)` and always
will be: the `url_id` is minted by AWS.

And the planned function configuration, from `terraform show -json`:

```
timeout          15
memory_size      512
architectures    ['arm64']
url auth_type    NONE
url cors         []            ← absent, not empty-permissive
url invoke_mode  BUFFERED
p99 threshold    12000
env MAINLINE_WEB_ROOT       = /var/task/web
env MAINLINE_DSN_PARAM      = /mainline/demo/dsn
env MAINLINE_DEMO_DATABASE  = mainline_demo
env MAINLINE_DEMO_PERMIT_ID = 077a6fdd-2167-559c-b2ff-8e3c8352504d
env MAINLINE_SCENARIO_PERMIT_ID = 077a6fdd-2167-559c-b2ff-8e3c8352504d
env LOG_LEVEL               = INFO
```

`validate` passes against the env root **as it stands today**, which still wires
`cloudfront_distribution_arn = module.site.distribution_arn`. That keeps working because
the variable is now optional rather than removed, and because nothing in this module
derives a `count` from it. Making the site module optional and committing a `plan` is
`infra/envs/demo`'s change, not this module's; the coordination note is in this worker's
completion notes.

## What has not been proved

In the spirit of [`docs/HONESTY.md`](../../../docs/HONESTY.md):

* **This module has never been applied.** Everything here is `validate`, `plan`, `graph`,
  and one real `PutDashboard` round trip. The three shapes above are real `terraform plan`
  runs against live AWS credentials — `plan` reads, it does not create. **No worker in this
  domain runs `terraform apply`** (`docs/leads/ship-final.md` §2.2).
* The `kms:Decrypt` grant has not been exercised against a live decrypt (see above).
* **No Function URL has ever been created by this module**, so neither shape's runtime
  behaviour is measured: "a `NONE` URL answers the public" and "an `AWS_IAM` URL answers
  403 to an unsigned `curl`" are both AWS's documented behaviour, not observations of *this*
  function. What *is* measured is which resources each shape plans, and with which
  attributes.
* `MAINLINE_WEB_ROOT = /var/task/web` is asserted, not verified end to end. It is correct
  if and only if the build script places the console at `web/` in the package root — W2's
  contract. The `web_root` output exists so the deploy script can check that claim against
  the actual zip instead of trusting this sentence.
* The 15 s timeout is reasoned from one measured number (2.91 s connect, from Australia,
  outside Lambda) plus estimates. No cold start has been timed inside the real Lambda
  service. If the `-duration-p99` alarm fires on day one, this paragraph is why.
* The `lambda:InvokeFunctionUrl` grant has not been exercised: no CloudFront distribution
  exists on this account and none can be created until AWS lifts the verification hold.
* The zip has been imported inside `public.ecr.aws/lambda/python:3.13` on both
  architectures and has opened a real pgwire connection to a **local** CockroachDB
  v26.2.5 node from there — but it has never been invoked by the real Lambda service, and
  never against the **Cloud** cluster in Singapore. The connect latency measured above is
  a Docker bridge, not a VPC.
* Reproducibility is asserted for one machine (three PowerShell runs plus one Git Bash
  run). Cross-machine determinism depends on the zlib build and is not claimed.
