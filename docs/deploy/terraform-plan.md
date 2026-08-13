<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: CC-BY-4.0
-->

# The committed Terraform plan — read back in prose

**This page exists to be reviewed before anybody types `terraform apply`.** It describes,
resource by resource, exactly what the two committed plans would create, what they would
cost, and what they would *not* create. Nothing here is a summary written from memory:
every number below was read out of the committed artefacts named beside it, and the
commands that produced those artefacts are printed in full.

> ## The one sentence that matters
>
> **The shipping plan creates eleven resources, all of them inside `module.api`, none of
> them a CloudFront distribution or an S3 bucket, and at demo traffic its recurring cost is
> USD 0.00 because every line sits inside a perpetual AWS free tier.**
>
> That sentence is about **what the plan creates**, not about **what the demo can be made
> to spend**. Those are different numbers and §4 keeps them apart, because conflating them
> is the mistake this documentation set has already made once.

**No `terraform apply` was run to produce any of this.** `init`, `validate`, `plan` and
`show` only. A previous worker ran an apply and was correctly stopped; the apply belongs to
the orchestrator, with the founder, after reading this page.

---

## 0 · What changed on 2026-08-13, and why this page was rewritten

The three artefacts were **regenerated from the tree at HEAD-plus-the-deploy-safety-wave**,
and this page was recomputed from them. This is not housekeeping. Three workers changed
values that the previously committed plan recorded, so the previously committed plan was no
longer the plan that would run — and *the number the founder re-authorises has to be the
number that will run.*

| Attribute | Was | Is | Why |
|---|---|---|---|
| `aws_lambda_function.reserved_concurrent_executions` | `20` | **`-1`** | 20 is unappliable: the account's measured `ConcurrentExecutions` ceiling is 10, and AWS refuses every positive reservation on it. `min(20, 10) = 10`, so this **does not raise the ceiling** — it removes a request that would have failed on the sixth of eleven API calls |
| `-concurrency` alarm `threshold` | `20` | **`8`** | a threshold of 20 sits *above* a metric ceiling of 10 and can never breach — a control that looks present and is not |
| `-concurrency` alarm `dimensions` | `{ FunctionName = … }` | **absent** | at `-1` there is no per-function reservation and Lambda does not dependably publish the per-function `ConcurrentExecutions` metric; the alarm is now account-level, and the plan's `alarm_description` says so and says when that stops being valid |
| `treat_missing_data`, all four alarms | `notBreaching` | **`missing`** | `notBreaching` renders an idle demo as four green alarms, where green means "nobody called this function" |
| `checks` in the JSON | 41 objects | **44 objects** | three new plan-time guards, named in §2 |
| `MAINLINE_*_PERMIT_ID` in the CloudFront plan | `077a6fdd-…-8e3c8352504d` | **`dec0de00-0006-4000-8000-000000000001`** | the FURL artefact had already been regenerated after the permit-id fix; **the CloudFront artefact had not**, and was still recording the uuid5 default nothing has ever seeded |

**The resource count did not move: `Plan: 11 to add, 0 to change, 0 to destroy` still holds,
and so does `Plan: 22 to add, 0 to change, 0 to destroy`.** That string is quoted verbatim
in `docs/deploy/JUDGE-PACK.md`, `docs/submission/DEVPOST.md`, `docs/submission/JUDGE-START.md`,
`docs/STATE-OF-THE-BUILD.md` and `scripts/submission/check_submission_ready.py`. This wave
changed attribute values only.

**One correction this page owes its own reader.** The line-count/byte/SHA-256 table in §1
had been stale since commit `1d41442`, which masked the AWS account id across thirteen
tracked files. Masking rewrote these artefacts' bytes and nobody recomputed the table, so a
reader who ran `sha256sum` got three mismatches and no explanation. The table below is
recomputed from the files as they now sit on disk, and §1.1 states how to re-derive it in
one command.

---

## 1 · The artefacts, and the commands that produced them

Terraform **v1.14.8**, provider `hashicorp/aws` **v6.58.0**, AWS profile `mainline-dev`
(read-only for a plan), region `ap-southeast-1`. Run **2026-08-13**; the plan's own
`timestamp` field says `2026-08-13T03:42:22Z`.

```bash
cd infra/envs/demo

# A throwaway local backend, written OUTSIDE the repository and deleted immediately after.
cat > backend_override.tf <<'EOF'
terraform {
  backend "local" {
    path = "<scratch>/demo-plan.tfstate"
  }
}
EOF

AWS_PROFILE=mainline-dev terraform init -reconfigure -input=false
AWS_PROFILE=mainline-dev terraform validate
AWS_PROFILE=mainline-dev terraform plan  -no-color -input=false -var enable_cloudfront=false -out=tfplan-furl.binary
AWS_PROFILE=mainline-dev terraform show  -no-color -json tfplan-furl.binary
AWS_PROFILE=mainline-dev terraform plan  -no-color -input=false -var enable_cloudfront=true

rm -f backend_override.tf tfplan-furl.binary       # NEITHER is ever committed
```

`terraform init -backend=false` is **not** sufficient on this tree, and the earlier revision
of this page said it was. `backend.tf` declares an S3 backend, and with `-backend=false`
Terraform records "no backend" and then `plan` refuses with *"Changes to backend
configurations require reinitialization"*. `-reconfigure` against a local override is what
actually works, and it is the recipe above.

`infra/envs/demo` contains **seven** files and no override:
`README.md`, `backend.tf`, `main.tf`, `outputs.tf`, `terraform.tfvars.example`,
`variables.tf`, `versions.tf`. **No S3 state object was created, read, written or locked**,
and the scratch state path was still empty after every plan — a `plan` writes no state,
which is why all four configurations read `0 to change, 0 to destroy`: there is nothing to
change or destroy yet. The `.terraform/terraform.tfstate` backend marker was removed
afterwards, so the directory is back to *"Backend initialization required"* and the next
operator has to init deliberately.

| Artefact | Lines | Bytes | SHA-256 |
|---|---:|---:|---|
| `evidence/deploy/terraform-plan-furl.txt` | 373 | 18 771 | `c56203b2826c499549fca90ecb5dd6a561b1d04a39b15f08c09b6ad461fe1493` |
| `evidence/deploy/terraform-plan-furl.json` | 1 | 148 082 | `1de80520a7f202b485c89facbacd031bf40e9a6f824d195b568aebd172a039d6` |
| `evidence/deploy/terraform-plan-cloudfront.txt` | 752 | 33 362 | `fac4727cf46b830ddd5b6642987c9487b2c4a75e5a2409a6664b0c1adaadc773` |

Each file is the **verbatim** stdout+stderr of its command, byte for byte, with exactly one
transformation applied — the account-id mask of §1.2. Nothing was added, reordered or
removed. All three are **LF-terminated**, because that is what Terraform writes; two of them
previously carried CRLF, which was an artefact of the shell that captured them and not
something the tool emitted. A file described as verbatim should not have had its line
endings rewritten on the way to disk.

### 1.1 · Re-deriving the table

```bash
python - <<'PY'
import hashlib, pathlib
for p in ("evidence/deploy/terraform-plan-furl.txt",
          "evidence/deploy/terraform-plan-furl.json",
          "evidence/deploy/terraform-plan-cloudfront.txt"):
    b = pathlib.Path(p).read_bytes()
    print(f"{p}  lines={len(b.decode().splitlines())}  bytes={len(b)}  "
          f"sha256={hashlib.sha256(b).hexdigest()}")
PY
```

A plan artefact whose hash nobody can reproduce is a screenshot. This command is the
difference.

### 1.2 · What was scrubbed, and what was not

**One transformation, applied mechanically: the twelve-digit AWS account id is replaced by
the literal `0229REDACTED8246`** — 6 occurrences in the FURL plan, 20 in its JSON, 13 in the
CloudFront plan. That is the repository-wide convention established by commit `1d41442`
(84 occurrences across 13 files) and it is applied here for the same reason: an account
number is not a credential, but publishing one enables cross-account enumeration.

Two properties are asserted over the result, and both are checkable:

* **zero occurrences of the real twelve digits** in any of the three files;
* **zero occurrences of `000000000000`.** Twelve identical digits is the one mask that two
  different checkers read two different ways — one as a redaction, one as a value — and the
  resolution recorded in `docs/CI-STATE.md` is to *remove the digits*, not to relax either
  checker. `scripts/aws/verify_evidence.py`'s `SEC-ACCOUNT-ID` and `SEC-ARN-ACCOUNT`
  invariants pass over all three files as committed.

The three twelve-digit runs a naive scan still finds are the final group of the demo permit
UUID `dec0de00-0006-4000-8000-000000000001`, which is a UUID and not an account.

**Nothing else was redacted, because Terraform marked nothing sensitive.** Every
`sensitive_values` object in the JSON is empty or all-`false`; the token `"sensitive"`
appears 26 times in the JSON and is `false` at every one of them; and the word `sensitive`
appears **zero** times in either human plan. **The plans contain no secret** — no DSN, no
password, no access key, no `postgresql://` URL, no private key. The word "secret" appears
twice in the JSON, both times inside module documentation that is *about* secrets not being
there: *"the \"secrets are not in Terraform state\" rule"* and *"which are not secret"*.

Terraform never holds the CockroachDB DSN. It is given the SSM parameter **name**
(`/mainline/demo/cockroach_dsn`); the SecureString is written by `aws ssm put-parameter`
outside Terraform, so it cannot appear in a plan, in `terraform show`, or in the state
object.

---

## 2 · THE SHIPPING PLAN — `enable_cloudfront = false`

`evidence/deploy/terraform-plan-furl.txt`, line 336 — the plan's summary line, immediately
after the last resource block and immediately before *Changes to Outputs*:

```
Plan: 11 to add, 0 to change, 0 to destroy.
```

The JSON agrees mechanically: `resource_changes` has **11 entries, every one
`["create"]`**, and `planned_values.root_module` holds **zero** resources directly with a
single child module, `module.api[0]`. `applyable: true`, `complete: true`, `errored: false`.

### Every resource, by type and name

| # | Address | Type | What it is |
|---|---|---|---|
| 1 | `module.api[0].aws_iam_role.this` | `aws_iam_role` | `mainline-demo-api-exec`, the execution role |
| 2 | `module.api[0].aws_iam_role_policy.dsn_access` | `aws_iam_role_policy` | `mainline-demo-api-dsn-read` — `ssm:GetParameter` on one parameter ARN plus a conditioned `kms:Decrypt` |
| 3 | `module.api[0].aws_iam_role_policy_attachment.basic_execution` | `aws_iam_role_policy_attachment` | `arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole` |
| 4 | `module.api[0].aws_lambda_function.this` | `aws_lambda_function` | `mainline-demo-api` · `python3.13` · `arm64` · 512 MB · 15 s · handler `mainline_demo_api.app.handler` · **`reserved_concurrent_executions = -1`** (line 279) · Zip |
| 5 | `module.api[0].aws_lambda_function_url.this` | `aws_lambda_function_url` | **`authorization_type = "NONE"`** (line 326), `invoke_mode = "BUFFERED"` — the demo hostname |
| 6 | `module.api[0].aws_cloudwatch_log_group.this` | `aws_cloudwatch_log_group` | `/aws/lambda/mainline-demo-api`, `retention_in_days = 7` |
| 7 | `module.api[0].aws_cloudwatch_metric_alarm.errors` | `aws_cloudwatch_metric_alarm` | `mainline-demo-api-errors` — `Errors > 0`, `treat_missing_data = "missing"` |
| 8 | `module.api[0].aws_cloudwatch_metric_alarm.throttles` | `aws_cloudwatch_metric_alarm` | `mainline-demo-api-throttles` — `Throttles > 0`, `treat_missing_data = "missing"` |
| 9 | `module.api[0].aws_cloudwatch_metric_alarm.duration_p99` | `aws_cloudwatch_metric_alarm` | `mainline-demo-api-duration-p99` — `Duration > 12000` ms, below the 15 000 ms timeout by precondition |
| 10 | `module.api[0].aws_cloudwatch_metric_alarm.concurrency` | `aws_cloudwatch_metric_alarm` | `mainline-demo-api-concurrency` — **`ConcurrentExecutions > 8`** (line 77), **no `dimensions` block**: account-level, not per-function |
| 11 | `module.api[0].aws_cloudwatch_dashboard.this[0]` | `aws_cloudwatch_dashboard` | `mainline-demo-api` |

By type: 1 × `aws_lambda_function`, 1 × `aws_lambda_function_url`, 1 × `aws_iam_role`,
1 × `aws_iam_role_policy`, 1 × `aws_iam_role_policy_attachment`,
1 × `aws_cloudwatch_log_group`, 4 × `aws_cloudwatch_metric_alarm`,
1 × `aws_cloudwatch_dashboard`. **Eleven.**

### The alarm that is not a bound, said once

Row 10 is a **tripwire**, not a cost control. It reports; it does not stop. Its threshold
of 8 is *below* the account's measured `ConcurrentExecutions` ceiling of 10 so that it can
actually breach, and that relationship is enforced at plan time rather than asserted in
prose — see the precondition in the next section. Row 4's `-1` is likewise **not a
loosening**: `min(20, 10) = 10` both before and after, so the physical bound on this
function is the same number it always was. What bounds spend, and what does not, is
`docs/deploy/COST-BOUND.md`'s subject, and this page does not restate it.

### What it would NOT create

* **No `aws_cloudfront_*` resource of any kind.** `resource_changes`, `planned_values` and
  `prior_state` contain zero. The identifier `aws_cloudfront_distribution` *does* appear in
  the JSON's `configuration` block, and in the `relevant_attributes` and `checks` derived
  from it — that block is the parsed HCL of the whole root, including the `count = 0`
  module, and Terraform emits it whether or not the module expands. The test that matters
  is `resource_changes`, and it is empty of CloudFront.
* **No S3 bucket.** No `aws_s3_bucket`, no public-access block, no versioning, no bucket
  policy. The console SPA and the signed EvidenceBundle ship *inside* the Lambda deployment
  package (`MAINLINE_WEB_ROOT = /var/task/web`), so there is no bucket in the request path.
* **No `aws_lambda_permission`.** The `cloudfront_invoke` grant is `count = 0`; the JSON's
  `checks` array shows `module.api.aws_lambda_permission.cloudfront_invoke` with
  **`instances: 0`** — absent from the plan, not present and inert. `output
  .cloudfront_invoke_grant_created` is `false`.
* **No SSM parameter, no KMS key, no Route 53 zone, no ACM certificate, no DynamoDB
  table, no WAF, no Synthetics canary.**
* **No secret of any kind.**

### Outputs this plan would produce

`planned_values.outputs` carries **17** outputs; `output_changes` marks **13** known at plan
time and **4** unknown.

Known at plan time:

```
api_authorization_type          = "NONE"
api_enabled                     = true
api_function_name               = "mainline-demo-api"
aws_account_id                  = "0229REDACTED8246"
aws_region                      = "ap-southeast-1"
cloudfront_invoke_grant_created = false
demo_url_source                 = "module.api[0].function_url (Lambda Function URL)"
distribution_arn                = null
distribution_domain_name        = null
distribution_id                 = null
dsn_parameter_name              = "/mainline/demo/cockroach_dsn"
enable_cloudfront               = false
site_bucket                     = null
```

Known only after apply: `demo_url`, `api_function_url`, `api_function_url_domain` and the
`deploy_summary` map that embeds them — an AWS-assigned Function URL id does not exist until
the resource does. The four `null`s above do not appear in the human plan's *Changes to
Outputs* block, because Terraform prints only outputs it is setting; they are visible in the
JSON, which is the artefact this paragraph is derived from.

**`demo_url` resolves to the Function URL when CloudFront is off.** The plan proves this
without an apply, because `demo_url_source` is a plan-time-known string and it reads
`module.api[0].function_url (Lambda Function URL)`. Its shape is
`https://<id>.lambda-url.ap-southeast-1.on.aws`, with AWS's trailing slash trimmed so that
`<demo_url>/v1/health` cannot become `//v1/health`.

### Every precondition and validation passed

The JSON's `checks` array carries **44 check objects**. Thirty of them expanded to an
instance, and **all 30 report `"status": "pass"`**; the other 14 report `instances: 0`,
which is what a check inside a `count = 0` module looks like. It went from 41 objects to 44
in this wave, and the three additions are exactly the three guards the wave installed:

| New check | Kind | What it refuses |
|---|---|---|
| `var.lambda_reserved_concurrency` | `var` | anything outside `-1` or `0…1000` at the root, with an error message naming the measured ceiling of 10 |
| `module.api.var.account_concurrency_ceiling` | `var` | a ceiling below 1 — i.e. an account on which no Lambda can run |
| `module.api.aws_cloudwatch_metric_alarm.concurrency` | `resource` | **`concurrency_alarm_threshold >= account_concurrency_ceiling`** — an abuse alarm that sits at or above the ceiling the metric cannot exceed |

The third is the load-bearing one and it is **falsifiable**, not decorative. Planned from a
throwaway root outside this repository with `concurrency_alarm_threshold = 11` against
`account_concurrency_ceiling = 10`, Terraform refuses:

```
Error: Resource precondition failed
  on .../demo-api/main.tf line 621, in resource "aws_cloudwatch_metric_alarm" "concurrency":
 621:       condition     = var.concurrency_alarm_threshold < var.account_concurrency_ceiling
    │ var.account_concurrency_ceiling is 10
    │ var.concurrency_alarm_threshold is 11

concurrency_alarm_threshold (11) is not strictly below account_concurrency_ceiling (10).
Lambda throttles at the account's concurrency quota, so the ConcurrentExecutions datapoint
is capped at 10 and an alarm at or above it could never breach - a control that looks
present and is not …
```

Three older checks are still worth naming:

* `output.demo_url` — the precondition that refuses a configuration with no URL source.
* `module.api.var.url_authorization_type` — the two-value validation that admits only
  `NONE` and `AWS_IAM`.
* `module.api.aws_lambda_permission.cloudfront_invoke` — `instances: 0`, i.e. the grant's
  own precondition was never reached because the grant does not exist.

Every `module.site.*` check likewise reports `instances: 0`. **A count-gated module out of
the plan is visible in the artefact, mechanically, and does not have to be taken on
trust.**

### What the plan cost to produce

Six data-source reads, all read-only, all visible in the first twelve lines of the human
plan: `data.aws_caller_identity.current` and `module.api[0].data.aws_caller_identity
.current` (two `sts:GetCallerIdentity` calls), `module.api[0].data.aws_region.current` and
`module.api[0].data.aws_partition.current` (provider metadata, resolved locally), and
`module.api[0].data.aws_iam_policy_document.assume_role` and `.dsn_access` (rendered
locally by the provider, no API call). **No write, no state object, no lock.**

---

## 3 · THE UPGRADE PLAN — `enable_cloudfront = true`

`evidence/deploy/terraform-plan-cloudfront.txt`, line 713:

```
Plan: 22 to add, 0 to change, 0 to destroy.
```

**The plan succeeds.** It was not refused by a data source and there is no refusal to
record: every data source it reads is available to this identity, and the account's
inability to *create* a distribution is an apply-time refusal from the CloudFront API, not
a plan-time one. That distinction is the reason this file exists — the configuration is
provably correct and provably blocked by something outside it. It reads **seven** data
sources rather than six; the extra one is `module.site[0].data.aws_caller_identity
.current[0]`, which derives the bucket name.

Twenty-two = the eleven above, **plus** `module.api[0].aws_lambda_permission
.cloudfront_invoke[0]`, **plus** ten in `module.site[0]`:

| # | Address | Type |
|---|---|---|
| 12 | `module.api[0].aws_lambda_permission.cloudfront_invoke[0]` | `aws_lambda_permission` |
| 13 | `module.site[0].aws_s3_bucket.site` | `aws_s3_bucket` |
| 14 | `module.site[0].aws_s3_bucket_public_access_block.site` | `aws_s3_bucket_public_access_block` |
| 15 | `module.site[0].aws_s3_bucket_ownership_controls.site` | `aws_s3_bucket_ownership_controls` |
| 16 | `module.site[0].aws_s3_bucket_versioning.site` | `aws_s3_bucket_versioning` |
| 17 | `module.site[0].aws_s3_bucket_server_side_encryption_configuration.site` | `aws_s3_bucket_server_side_encryption_configuration` |
| 18 | `module.site[0].aws_s3_bucket_lifecycle_configuration.site[0]` | `aws_s3_bucket_lifecycle_configuration` |
| 19 | `module.site[0].aws_s3_bucket_policy.site` | `aws_s3_bucket_policy` |
| 20 | `module.site[0].aws_cloudfront_origin_access_control.s3` | `aws_cloudfront_origin_access_control` |
| 21 | `module.site[0].aws_cloudfront_origin_access_control.api[0]` | `aws_cloudfront_origin_access_control` |
| 22 | `module.site[0].aws_cloudfront_distribution.site` | `aws_cloudfront_distribution` |

Plus one data source read during apply — `module.site[0].data.aws_iam_policy_document.site`,
the bucket policy, which cannot be rendered until the distribution ARN exists. A data read
is not a created resource and is not counted in the 22.

The `module.api[0]` half of this plan carries **the same four attribute changes as §2** —
`reserved_concurrent_executions = -1` (line 279), the `-concurrency` alarm at `threshold = 8`
with no `dimensions` block (line 77), and `treat_missing_data = "missing"` on all four
alarms. The two shapes do not disagree about the Lambda.

**And this artefact carried a stale permit id until 2026-08-13.** Its
`MAINLINE_DEMO_PERMIT_ID` and `MAINLINE_SCENARIO_PERMIT_ID` (lines 308 and 310; the FURL
plan carries the same pair at lines 305 and 307) read
`077a6fdd-2167-559c-b2ff-8e3c8352504d` — the uuid5 derivation nothing has ever seeded —
where the FURL artefact had already been regenerated to
`dec0de00-0006-4000-8000-000000000001`, the id the demo cluster actually holds. Two
committed plans of the same module disagreed about the id the demo guard is armed at, and
only one of them had been refreshed. They agree now.

Outputs flip in exactly the two places the design says they should:

```
api_authorization_type          = "AWS_IAM"      (was "NONE")
cloudfront_invoke_grant_created = true           (was false)
demo_url_source                 = "module.site[0].distribution_domain_name (CloudFront)"
site_bucket                     = "mainline-demo-site-0229REDACTED8246"
phase                           = "2-cloudfront" (was "2-furl")
```

**One variable moves the hostname and the authorisation model together.** That is
`main.tf`'s `url_authorization_type = var.enable_cloudfront ? "AWS_IAM" : "NONE"`, and it
is the whole architectural switch.

### What this plan would run into, at apply time, today

The eighth resource AWS refused on 2026-08-10:

```
Error: creating CloudFront Distribution: operation error CloudFront:
CreateDistributionWithTags, https response error StatusCode: 403,
RequestID: 3e63e30d-8c5b-441b-a01b-b70085eba504, AccessDenied:
Your account must be verified before you can add new CloudFront resources.
To verify your account, please contact AWS Support and include this error message.
```

An account-level verification hold on **new** CloudFront resources — the account already
carries one distribution from an unrelated project, created 2026-04-16, so the service
itself is not denied. Only AWS Support can lift it. **Do not apply this plan** until they
have; it would create the ten S3/OAC resources and then fail on the eleventh, which is
exactly what happened on 2026-08-10.

---

## 4 · What the apply would cost

**Two questions live here and they have different answers. Keep them apart.**

### 4.1 · What the created resources cost to exist, at demo traffic

Recurring, per month, at demo traffic (a judging round is a few hundred requests):

| Line | Basis | `enable_cloudfront = false` | `= true` |
|---|---|---:|---:|
| Lambda invocations + duration | free tier 1 M req + 400 000 GB-s; 512 MB × 300 ms × 10 k req = 1 536 GB-s | 0.00 | 0.00 |
| Lambda Function URL | no charge beyond the invocation | 0.00 | 0.00 |
| CloudWatch Logs | 7-day retention, far under the 5 GB free ingest | 0.00 | 0.00 |
| CloudWatch alarms | 4 alarms; first 10 standard alarms are free | 0.00 | 0.00 |
| CloudWatch dashboard | first 3 dashboards free | 0.00 | 0.00 |
| IAM role / policy / attachment | never billed | 0.00 | 0.00 |
| S3 site bucket | **not created** / one small versioned SPA build | — | ~0.01 |
| CloudFront | **not created** / free tier 1 TB egress + 10 M req | — | 0.00 |
| **Total created by this plan** | | **0.00** | **~0.01** |

Outside this plan and named for completeness: the Terraform state bucket (~USD 0.01/month,
created by `bootstrap_state.sh`, not by this root), the SSM Parameter Store SecureString
(Standard tier, USD 0.00, written by the deploy script), Bedrock (~USD 0.01/month), and
CockroachDB Cloud Basic (inside the free allowance, `spend_limit` is the hard ceiling).
Whole-system total at demo traffic ≈ **USD 0.02–0.03/month**.

### 4.2 · What the demo can be made to spend, which is a different number

**Nothing in §4.1 is a bound.** Every line there is a *usage-metered free tier*, and a free
tier bounds nothing once the usage leaves the tier. The Function URL is
`authorization_type = NONE`, the largest single object the origin will emit is a 1.55 MB
source map inside the deployment package, and the only real limiter on request rate is the
account's `ConcurrentExecutions` ceiling of 10 — an AWS default nobody chose, and
`Adjustable: true`.

**`docs/deploy/COST-BOUND.md` carries that arithmetic, its inputs and its levers, and it is
the document to read before authorising an apply.** It is not restated here, for one
reason: an earlier revision of this documentation set rounded the worst case to *"a dollar"*,
which was wrong by four to five orders of magnitude, and it was wrong precisely because a
free-tier table like §4.1 was allowed to answer a question it was never about.

The one line item in §4.1 with no natural ceiling is a CloudWatch log group set to never
expire. `log_retention_days` is 7 and its validation refuses `0`.

---

## 5 · The four configurations, measured

All re-run on this machine on **2026-08-13**, Terraform v1.14.8 + `hashicorp/aws v6.58.0`,
real credentials, against the tree that produced the artefacts above:

| `enable_cloudfront` | `enable_api` | Result |
|---|---|---|
| `false` **(default)** | `true` | `Plan: 11 to add, 0 to change, 0 to destroy` — **ships** |
| `true` | `true` | `Plan: 22 to add, 0 to change, 0 to destroy` |
| `true` | `false` | `Plan: 9 to add, 0 to change, 0 to destroy` — site with no API |
| `false` | `false` | **Refused at plan.** `Error: Module output value precondition failed` on `output "demo_url"`, `outputs.tf` line 61 |

The fourth row is intentional. With both switches off the root creates nothing, so
`demo_url` has no source; returning `""` would be a demo URL nobody can visit, presented as
if it were one. The message names the fix, in full:

```
enable_api and enable_cloudfront are both false, so this root creates no
resource that can serve a URL and demo_url has no source. Under decision D1
(docs/leads/ship-final.md 1.4) the Lambda Function URL IS the demo hostname:
set enable_api = true. …
```

Also clean, both re-run today: `terraform fmt -check -recursive infra/` exits 0 with no
output, and `terraform validate` prints `Success! The configuration is valid.`

---

## 6 · The review checklist, for the orchestrator and the founder

Before any `terraform apply`:

1. **The plan file is the one you are applying.** Re-run
   `plan -var enable_cloudfront=false -out=<file>` and confirm `Plan: 11 to add`. A plan
   older than the code is not evidence — and this page exists because that stopped being
   true once already.
2. **`authorization_type` is `NONE` on purpose, and the list of what bounds it is short.**
   The Function URL is public. What bounds it is **not** authentication, and — since
   2026-08-13 — it is **not** `reserved_concurrent_executions` either: that is `-1`, it was
   never appliable at `20`, and `min(20, 10) = 10` means it never changed the physical
   bound. What actually bounds the demo is the **account's `ConcurrentExecutions` ceiling of
   10** (measured, `Adjustable: true` — *do not request an increase without reading
   `docs/deploy/COST-BOUND.md`*), the handler's single rolled-back transaction (which bounds
   database *state*, not spend), and the CockroachDB Basic `spend_limit` (which bounds the
   database side only). The `-concurrency` alarm at 8 is a **tripwire**: it reports, it does
   not stop. `infra/modules/demo-api/README.md` states the exposure plainly rather than
   calling a public URL private.
3. **Eleven resources, all prefixed `mainline-demo-`.** `scripts/deploy/teardown.sh` keys
   its refusal on that prefix and on `project=mainline`, which `default_tags` applies to
   every taggable resource in the plan.
4. **Nothing is destroyed and nothing is changed.** `0 to change, 0 to destroy` in both
   plans. Nothing pre-existing in an account holding four unrelated live projects is
   touched.
5. **The SSM SecureString must exist before the apply**, or the function starts and fails
   on its first database call. The role is granted `ssm:GetParameter` on
   `/mainline/demo/cockroach_dsn` and nothing else. `docs/deploy/PRE-APPLY.md` lists this
   and the state bucket in order, with the read-only command that proves each — **and
   records that neither exists in this account today.**
6. **Do not apply the CloudFront plan** until AWS Support confirms the verification hold is
   lifted. It would create ten resources and fail on the eleventh.
7. **Read `docs/deploy/COST-BOUND.md` before authorising.** §4.2 says why: the free-tier
   table in §4.1 answers a question about existence, not about abuse, and the two numbers
   are four orders of magnitude apart.

---

## 7 · Provenance

Everything on this page is derived from the three committed artefacts and nothing else:

* `evidence/deploy/terraform-plan-furl.txt` — §2's counts, resource list, line citations
  (77, 279, 326, 336) and the `Plan:` line
* `evidence/deploy/terraform-plan-furl.json` — §2's `resource_changes`, `checks`,
  `planned_values`, `output_changes`, `sensitive_values` and `timestamp` claims
* `evidence/deploy/terraform-plan-cloudfront.txt` — §3 in full, including the line-713
  `Plan:` line and the permit ids at lines 308 and 310

Three things on this page are **not** from those artefacts and say so where they appear:
the four-configuration table in §5 and the `fmt`/`validate` results, which are transcripts
of commands re-run on 2026-08-13 and not committed as files; the precondition refusal quoted
in §2, which was planned from a throwaway root **outside this repository** so that no
tracked file had to be edited to produce a negative control; and the 403 transcript in §3,
which is quoted from `docs/deploy/RUNBOOK.md` and records the 2026-08-10 apply.

The cost basis in §4.1 is AWS's published free-tier allowances plus the usage model in
`docs/leads/ship-final.md` §2.1; it is an **estimate**, and it is the only estimate on this
page. §4.2 is not an estimate this page makes — it points at the document that makes it.
