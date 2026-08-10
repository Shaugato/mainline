<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: CC-BY-4.0
-->

# `demo-api` — the Lambda behind `/v1/*`

One `python3.13` Lambda, one **IAM-only** Function URL, one execution role that can read
exactly one SSM parameter, one log group with a finite retention, four alarms and a
dashboard. Region `ap-southeast-1` (Singapore), beside the CockroachDB Cloud cluster.

It is the `/v1/*` half of the stack in [`docs/leads/deploy-plan.md`](../../../docs/leads/deploy-plan.md) §2.1.
S3 + CloudFront + OAC are `infra/modules/site` (W5); the env root that wires the two
together and runs the deploy is `infra/envs/demo` (W7).

```
 judge's browser ──► CloudFront ──/v1/*──► Lambda Function URL (AWS_IAM, OAC-signed)
                                                     │ pgwire, TLS, same region
                                                     ▼
                                CockroachDB Cloud Basic · mainline-dev · Singapore
```

**Why Singapore.** Lambda→CRDB in-region is single-digit milliseconds. The same call from
`ap-southeast-2` pays roughly 90 ms each way, and the gate surface makes six of them —
about 1.1 s of pure geography on the one screen the judges look at.

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

# 3. Plan
terraform init && terraform plan
```

```hcl
module "demo_api" {
  source = "../../modules/demo-api"

  package_path                = "${path.root}/../../out/lambda/mainline-demo-api-arm64.zip"
  cloudfront_distribution_arn = module.site.distribution_arn
  # dsn_parameter_name defaults to /mainline/demo/dsn
}
```

The Function URL must be created before CloudFront can point at it, and the CloudFront
ARN must exist before this module's `lambda:InvokeFunctionUrl` grant can name it. W7
resolves that with two applies, or by constructing the distribution ARN from a
`random`-free known id — either way it is the env root's problem, not this module's.

---

## Inputs

| Variable | Type | Default | What it is |
|---|---|---|---|
| `package_path` | `string` | *(required)* | Path to the zip from `scripts/deploy/build_lambda.*`. Must exist at plan time — `source_code_hash` is `filebase64sha256` of it. |
| `cloudfront_distribution_arn` | `string` | *(required)* | The **one** distribution allowed to invoke the Function URL. Becomes `SourceArn` on the grant. |
| `function_name` | `string` | `mainline-demo-api` | Fixes the log group, the alarm names and the dashboard name. |
| `architecture` | `string` | `arm64` | `arm64` or `x86_64`. **Must match the package.** Enforced by a `lifecycle.precondition`. |
| `dsn_parameter_name` | `string` | `/mainline/demo/dsn` | **Name only.** Leading slash optional and normalised. No wildcard accepted. |
| `ssm_kms_key_arn` | `string` | `""` | Empty = the account's `aws/ssm` key, scoped by condition instead of by resource. See [KMS](#the-kms-grant-is-scoped-by-condition-not-by-resource). |
| `restrict_kms_to_parameter` | `bool` | `true` | Add `kms:EncryptionContext:PARAMETER_ARN` to the `Decrypt` grant. |
| `demo_database` | `string` | `mainline_demo` | Published as `$MAINLINE_DEMO_DATABASE`. Declarative — see [environment](#environment-variables). |
| `scenario_permit_id` | `string` | `077a6fdd-…504d` | The permit the three beats drive. Published under two names — see [environment](#environment-variables). |
| `log_level` | `string` | `INFO` | Published as `$LOG_LEVEL` **and** wired into `logging_config.application_log_level`. |
| `memory_size` | `number` | `512` | MB. CPU scales with it; the free tier is not the binding constraint. |
| `timeout` | `number` | `25` | Seconds. Capped at 29 so the function always fails *before* CloudFront's 30 s origin read timeout. |
| `reserved_concurrent_executions` | `number` | `20` | Hard cost cap. `-1` = unreserved (and see the concurrency-alarm caveat). |
| `log_retention_days` | `number` | `7` | CloudWatch retention. `0` (never expire) is not offered. |
| `duration_p99_threshold_ms` | `number` | `20000` | p99 alarm threshold. |
| `concurrency_alarm_threshold` | `number` | `20` | Abuse tripwire. |
| `alarm_actions` | `list(string)` | `[]` | SNS topics. Empty on purpose — the alarms exist to be *read*. |
| `create_dashboard` | `bool` | `true` | First three dashboards per account are free. |
| `extra_environment` | `map(string)` | `{}` | Merged in. Cannot carry `MAINLINE_DSN`, a Lambda reserved name, or a key this module sets. |
| `tags` | `map(string)` | `{}` | Merged **under** the mandatory three, which a caller cannot override. |

There is deliberately **no** `function_url_authorization_type` variable and **no** variable
that can carry the DSN value. Both omissions are the point of the module.

## Outputs

| Output | Example | Used by |
|---|---|---|
| `function_name` | `mainline-demo-api` | `aws lambda get-function-configuration` |
| `function_arn` | `arn:aws:lambda:ap-southeast-1:…:function/mainline-demo-api` | teardown, judge pack |
| `function_url` | `https://abc123.lambda-url.ap-southeast-1.on.aws/` | the deploy report |
| `function_url_domain` | `abc123.lambda-url.ap-southeast-1.on.aws` | **W5's CloudFront origin `domain_name`** (rejects scheme and path) |
| `function_url_id` | `abc123` | origin id, log filters |
| `log_group_name` | `/aws/lambda/mainline-demo-api` | `aws logs tail` |
| `log_group_arn` | `arn:aws:logs:…:log-group:/aws/lambda/mainline-demo-api:*` | future subscription filter |
| `role_arn` / `role_name` | `…:role/mainline-demo-api-exec` | `aws iam get-role-policy` |
| `dsn_parameter_arn` | `arn:aws:ssm:ap-southeast-1:…:parameter/mainline/demo/dsn` | the deploy script, so `put-parameter` writes to exactly the ARN the policy grants |
| `architecture` | `arm64` | deploy report |
| `package_sha256_base64` | `0h5puChORMwV9wzxVmRP2KKkuq/B/bl7Ba7RYIF/KMU=` | deploy report |
| `alarm_names` | 4 names | W10's `describe-alarms` health cron |
| `dashboard_name` | `mainline-demo-api` or `null` | — |

---

## The four decisions

### The Function URL is `AWS_IAM`, never `NONE`

A `NONE` Function URL is a **public, unauthenticated gateway to a database**, on a URL
that stops being secret the first time a judge opens their browser's network tab. It is
also an unbounded bill: anyone who finds it can invoke it as often as they like, and every
invocation opens a pgwire connection to a CockroachDB Basic cluster with a spend cap.

With `authorization_type = "AWS_IAM"` plus the single grant below, the function is
invocable **through this CloudFront distribution and by nothing else**:

```hcl
resource "aws_lambda_permission" "cloudfront_invoke" {
  action                 = "lambda:InvokeFunctionUrl"
  principal              = "cloudfront.amazonaws.com"
  source_arn             = var.cloudfront_distribution_arn   # ONE distribution
  function_url_auth_type = "AWS_IAM"
}
```

Without `source_arn` the statement would read "any CloudFront distribution in any account
may invoke this", which includes one an attacker creates in their own account and points
at our origin. CloudFront signs each origin request with SigV4 under an Origin Access
Control; a plain `curl` at the Function URL gets `403 Forbidden` with an empty body.

There is no variable that can turn this off. A knob that makes authentication optional is
a knob somebody turns at 02:00 to make a `curl` work.

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
stack.** Health checking is a GitHub Actions cron against `/v1/health` (W10), which costs
nothing and whose failures are visible in the repository the judges are already reading.

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
are still readable by `aws cloudwatch describe-alarms`, which is what W10's cron reads.

| Alarm | Metric | Condition | Why |
|---|---|---|---|
| `<fn>-errors` | `Errors` Sum | `> 0` over 5 min | The handler is written never to raise: refusals are 200s with a `REFUSED` verdict, failures are JSON problem documents. An `Errors` datapoint means it raised anyway. |
| `<fn>-throttles` | `Throttles` Sum | `> 0` over 5 min | The reserved-concurrency cap is biting. A throttled invocation reaches the judge as a CloudFront 502. |
| `<fn>-duration-p99` | `Duration` p99 | `> 20 000 ms` | Approaching the 25 s timeout. On this stack that is nearly always the pgwire round trip, not the handler — `/v1/health` reports connect time separately. |
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
Parameter Store Standard: free. **≈ $0.00/month**, and the reserved-concurrency cap means
that stays true under abuse. The full itemisation is in `docs/leads/deploy-plan.md` §2.3.

## Terraform / OpenTofu

`hashicorp/aws >= 6.0.0, < 7.0.0`; Terraform `>= 1.6.0`. Resolved to provider **v6.58.0**
on the build machine. Nothing here is Terraform-only, so `tofu init && tofu plan` works
unchanged. The provider floor is 6.0 because this module reads
`data.aws_region.current.region`, the attribute that replaced the deprecated `.name`.

## What has not been proved

In the spirit of [`docs/HONESTY.md`](../../../docs/HONESTY.md):

* **This module has never been applied.** Everything below is `validate`, `plan`, `graph`,
  and one real `PutDashboard` round trip. `Plan: 12 to add, 0 to change, 0 to destroy`,
  no warnings.
* The `kms:Decrypt` grant has not been exercised against a live decrypt (see above).
* The `lambda:InvokeFunctionUrl` grant has not been exercised: no CloudFront distribution
  exists yet, so "a plain `curl` gets 403" is AWS's documented behaviour for an `AWS_IAM`
  Function URL, not something measured on *this* function.
* The zip has been imported inside `public.ecr.aws/lambda/python:3.13` on both
  architectures and has opened a real pgwire connection to a **local** CockroachDB
  v26.2.5 node from there — but it has never been invoked by the real Lambda service, and
  never against the **Cloud** cluster in Singapore. The connect latency measured above is
  a Docker bridge, not a VPC.
* Reproducibility is asserted for one machine (three PowerShell runs plus one Git Bash
  run). Cross-machine determinism depends on the zlib build and is not claimed.
