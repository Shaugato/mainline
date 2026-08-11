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
> them a CloudFront distribution or an S3 bucket, and its total recurring cost is USD 0.00
> because every line sits inside a perpetual AWS free tier.**

**No `terraform apply` was run to produce any of this.** `init`, `validate`, `plan` and
`show` only. A previous worker ran an apply and was correctly stopped; the apply belongs to
the orchestrator, with the founder, after reading this page.

---

## 1 · The artefacts, and the commands that produced them

Terraform **v1.14.8**, provider `hashicorp/aws` **v6.58.0**, AWS profile `mainline-dev`
(read-only for a plan), region `ap-southeast-1`. Run `2026-08-11`; the plan's own
`timestamp` field says `2026-08-11T05:33:11Z`.

```bash
terraform -chdir=infra/envs/demo init -backend=false
terraform -chdir=infra/envs/demo validate
terraform -chdir=infra/envs/demo plan -no-color -var enable_cloudfront=false -out=tfplan-furl.binary
terraform -chdir=infra/envs/demo show -no-color -json tfplan-furl.binary
terraform -chdir=infra/envs/demo plan -no-color -var enable_cloudfront=true
```

| Artefact | Lines | Bytes | SHA-256 |
|---|---:|---:|---|
| `evidence/deploy/terraform-plan-furl.txt` | 376 | 18 290 | `d5e6c3f08298ed409de4b6a41cfa24d71e4b1525335e6703d1872992de5e9316` |
| `evidence/deploy/terraform-plan-furl.json` | 1 | 128 776 | `f2fe940bc292af3cc8f8695b6a46286952fe4ebb71ab704f4890c51c393616d9` |
| `evidence/deploy/terraform-plan-cloudfront.txt` | 755 | 32 853 | `6d7573a53fcf3f9ab1cad823cf767eed642bf58277dba08a2cac41aafb9c4970` |

Each file is the **verbatim** stdout+stderr of its command. Nothing was added, reordered or
removed.

### Why a temporary local backend was used, and what it touched

`backend.tf` declares an S3 backend. Terraform v1.14.8 refuses `plan` when a declared
backend has never been initialised, and `init -backend=false` deliberately does not
initialise one — so `init -backend=false` followed by `plan` fails with *"Backend
initialization required"*. The plans were therefore produced with a throwaway
`local_backend_override.tf` redirecting state to a scratch path **outside the repository**,
and that file was deleted immediately afterwards; `infra/envs/demo` contains seven files
and no override. No S3 state object was created, read, written or locked. State was empty
throughout, which is why every plan reads `0 to change, 0 to destroy`: there is nothing to
change or destroy yet.

### Was anything scrubbed?

**No.** The only redaction rule applied was "remove what Terraform itself marks
sensitive", and Terraform marked nothing sensitive: every `sensitive_values` object in the
JSON is empty or all-`false`, and the string `sensitive` does not appear in either human
plan. **I checked, and the plans contain no secret** — no DSN, no password, no access key,
no `postgresql://` URL, no private key. The single occurrence of the word "secret" in the
JSON is inside a module description that reads *"which are not secret"*.

Terraform never holds the CockroachDB DSN. It is given the SSM parameter **name**
(`/mainline/demo/cockroach_dsn`); the SecureString is written by `aws ssm put-parameter`
outside Terraform, so it cannot appear in a plan, in `terraform show`, or in the state
object.

The plans **do** contain the twelve-digit AWS account id — in IAM/SSM ARNs, in the derived
bucket name, and in `output.aws_account_id`. That is deliberate and is decision **D2**
(`docs/leads/ship-final.md` §1.6): the id is removed from every *executable* position
(defaults, backend examples, tfvars examples) and **kept** where it is *recorded evidence*,
which a committed plan is. An account id is an identifier, not a credential.

---

## 2 · THE SHIPPING PLAN — `enable_cloudfront = false`

`evidence/deploy/terraform-plan-furl.txt`, last line of the plan body:

```
Plan: 11 to add, 0 to change, 0 to destroy.
```

The JSON agrees mechanically: `resource_changes` has **11 entries, every one
`["create"]`**, and `planned_values.root_module` holds **zero** resources directly with a
single child module, `module.api[0]`.

### Every resource, by type and name

| # | Address | Type | What it is |
|---|---|---|---|
| 1 | `module.api[0].aws_iam_role.this` | `aws_iam_role` | `mainline-demo-api-exec`, the execution role |
| 2 | `module.api[0].aws_iam_role_policy.dsn_access` | `aws_iam_role_policy` | `mainline-demo-api-dsn-read` — `ssm:GetParameter` on one parameter ARN plus a conditioned `kms:Decrypt` |
| 3 | `module.api[0].aws_iam_role_policy_attachment.basic_execution` | `aws_iam_role_policy_attachment` | `arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole` |
| 4 | `module.api[0].aws_lambda_function.this` | `aws_lambda_function` | `mainline-demo-api` · `python3.13` · `arm64` · 512 MB · 15 s · `reserved_concurrent_executions = 20` · Zip |
| 5 | `module.api[0].aws_lambda_function_url.this` | `aws_lambda_function_url` | **`authorization_type = "NONE"`**, `invoke_mode = "BUFFERED"` — the demo hostname |
| 6 | `module.api[0].aws_cloudwatch_log_group.this` | `aws_cloudwatch_log_group` | `/aws/lambda/mainline-demo-api`, `retention_in_days = 7` |
| 7 | `module.api[0].aws_cloudwatch_metric_alarm.errors` | `aws_cloudwatch_metric_alarm` | `mainline-demo-api-errors` — `Errors > 0` |
| 8 | `module.api[0].aws_cloudwatch_metric_alarm.throttles` | `aws_cloudwatch_metric_alarm` | `mainline-demo-api-throttles` — `Throttles > 0` |
| 9 | `module.api[0].aws_cloudwatch_metric_alarm.duration_p99` | `aws_cloudwatch_metric_alarm` | `mainline-demo-api-duration-p99` — `Duration > 12000` ms |
| 10 | `module.api[0].aws_cloudwatch_metric_alarm.concurrency` | `aws_cloudwatch_metric_alarm` | `mainline-demo-api-concurrency` — `ConcurrentExecutions > 20` |
| 11 | `module.api[0].aws_cloudwatch_dashboard.this[0]` | `aws_cloudwatch_dashboard` | `mainline-demo-api` |

By type: 1 × `aws_lambda_function`, 1 × `aws_lambda_function_url`, 1 × `aws_iam_role`,
1 × `aws_iam_role_policy`, 1 × `aws_iam_role_policy_attachment`,
1 × `aws_cloudwatch_log_group`, 4 × `aws_cloudwatch_metric_alarm`,
1 × `aws_cloudwatch_dashboard`. **Eleven.**

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

Known at plan time:

```
api_authorization_type          = "NONE"
api_enabled                     = true
api_function_name               = "mainline-demo-api"
aws_account_id                  = "022950218246"
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

Known only after apply: `demo_url`, `api_function_url`, `api_function_url_domain` — an
AWS-assigned Function URL id does not exist until the resource does.

**`demo_url` resolves to the Function URL when CloudFront is off.** The plan proves this
without an apply, because `demo_url_source` is a plan-time-known string and it reads
`module.api[0].function_url (Lambda Function URL)`. Its shape is
`https://<id>.lambda-url.ap-southeast-1.on.aws`, with AWS's trailing slash trimmed so that
`<demo_url>/v1/health` cannot become `//v1/health`.

### Every precondition and validation passed

The JSON's `checks` array carries **41 entries, all `"status": "pass"`**, and
`applyable: true`, `complete: true`, `errored: false`. Three are worth naming:

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

`evidence/deploy/terraform-plan-cloudfront.txt`:

```
Plan: 22 to add, 0 to change, 0 to destroy.
```

**The plan succeeds.** It was not refused by a data source and there is no refusal to
record: every data source it reads is available to this identity, and the account's
inability to *create* a distribution is an apply-time refusal from the CloudFront API, not
a plan-time one. That distinction is the reason this file exists — the configuration is
provably correct and provably blocked by something outside it.

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

Outputs flip in exactly the two places the design says they should:

```
api_authorization_type          = "AWS_IAM"      (was "NONE")
cloudfront_invoke_grant_created = true           (was false)
demo_url_source                 = "module.site[0].distribution_domain_name (CloudFront)"
site_bucket                     = "mainline-demo-site-022950218246"
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
Whole-system total ≈ **USD 0.02–0.03/month**, worst case under USD 1.00. The founder's
ceiling is ~USD 5/month.

The one line item with no natural ceiling is a CloudWatch log group set to never expire.
`log_retention_days` is 7 and its validation refuses `0`.

---

## 5 · The four configurations, measured

All on this machine, 2026-08-11, Terraform v1.14.8 + `hashicorp/aws v6.58.0`, real
credentials:

| `enable_cloudfront` | `enable_api` | Result |
|---|---|---|
| `false` **(default)** | `true` | `Plan: 11 to add, 0 to change, 0 to destroy` — **ships** |
| `true` | `true` | `Plan: 22 to add, 0 to change, 0 to destroy` |
| `true` | `false` | `Plan: 9 to add, 0 to change, 0 to destroy` — site with no API |
| `false` | `false` | **Refused at plan.** `Error: Module output value precondition failed` on `output "demo_url"` |

The fourth row is intentional. With both switches off the root creates nothing, so
`demo_url` has no source; returning `""` would be a demo URL nobody can visit, presented as
if it were one. The message names the fix.

Also clean: `terraform fmt -check -recursive infra/` exits 0 with no output, and
`terraform validate` prints `Success! The configuration is valid.`

---

## 6 · The review checklist, for the orchestrator and the founder

Before any `terraform apply`:

1. **The plan file is the one you are applying.** Re-run
   `plan -var enable_cloudfront=false -out=<file>` and confirm `Plan: 11 to add`. A plan
   older than the code is not evidence.
2. **`authorization_type` is `NONE` on purpose.** The Function URL is public. What bounds
   it is not authentication: `reserved_concurrent_executions = 20` is a hard cap, the demo
   transaction is rolled back, the CockroachDB Basic `spend_limit` is a ceiling, and the
   `-concurrency` alarm fires at 20. `infra/modules/demo-api/README.md` states the exposure
   plainly rather than calling a public URL private.
3. **Eleven resources, all prefixed `mainline-demo-`.** `scripts/deploy/teardown.sh` keys
   its refusal on that prefix and on `project=mainline`, which `default_tags` applies to
   every taggable resource in the plan.
4. **Nothing is destroyed and nothing is changed.** `0 to change, 0 to destroy` in both
   plans. Nothing pre-existing in an account holding four unrelated live projects is
   touched.
5. **The SSM SecureString must exist before the apply**, or the function starts and fails
   on its first database call. The role is granted `ssm:GetParameter` on
   `/mainline/demo/cockroach_dsn` and nothing else.
6. **Do not apply the CloudFront plan** until AWS Support confirms the verification hold is
   lifted. It would create ten resources and fail on the eleventh.

---

## 7 · Provenance

Everything on this page is derived from the three committed artefacts and nothing else:

* `evidence/deploy/terraform-plan-furl.txt` — §2's counts, resource list and outputs
* `evidence/deploy/terraform-plan-furl.json` — §2's `resource_changes`, `checks`,
  `planned_values`, `sensitive_values` and `timestamp` claims
* `evidence/deploy/terraform-plan-cloudfront.txt` — §3 in full

The 403 transcript in §3 is quoted from `docs/deploy/RUNBOOK.md` line 26, which records the
2026-08-10 apply. The cost basis in §4 is AWS's published free-tier allowances plus the
usage model in `docs/leads/ship-final.md` §2.1; it is an **estimate**, and it is the only
estimate on this page.
