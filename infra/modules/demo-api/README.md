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
                     │  AWS Lambda · python3.13 · 256 MB · 14 s      ONE origin
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
gateway to a database. What actually bounds it is written down rather than assumed — and
**this table used to be longer and wrong.** It listed five bounds and claimed
`reserved_concurrent_executions = 20` was *"a hard cap, the only control here that stops a
bill instead of reporting one"*. That sentence described an account nobody here has:

| claimed bound | real? | what it actually bounds |
|---|---|---|
| **account concurrency ceiling** = **10** | **YES — and it is the only one** | concurrency, hence request rate, hence egress, hence the bill. Measured (`account_concurrency_ceiling`). Also `Adjustable: true`: a bound nobody here chose and anybody here could remove. |
| `reserved_concurrent_executions` | **NO** | nothing. It defaulted to `20` above a ceiling of `10` — `min(20, 10) = 10` — so it never bound anything, and *every* positive value is refused outright at apply on this account. It is `-1` now. Its `0` setting **is** a real stop, but as a deliberately-run kill switch, not a standing cap. |
| `<fn>-concurrency` alarm | **NO**, by construction | nothing — an alarm reports, it does not stop. It shipped at `> 20` against a metric that tops out at `10`, so it could not even report. It is `> 8` on the account-level metric now, which makes it a working tripwire and still not a bound. |
| the handler's write surface | **YES**, for *state* | one txn ending in `ROLLBACK`: the four beats leave no committed state and two judges cannot collide. Not spend — the flood target is the static tree in the zip, which never opens a connection. |
| CockroachDB Basic `spend_limit` | **YES**, database side only | $25 / 100 M RU. Same reason: not in the path of the bytes. |
| `<fn>-throttles` alarm | **NO** | reports that the account ceiling is biting; a throttled Function URL invocation reaches the caller as HTTP 429. |

**One real bound on spend, and it is an AWS default nobody chose.** That is a much smaller
claim than *"invocable by one distribution and nothing else"*, and it is the true one for
this account. The arithmetic of what that costs in the worst case, and the menu of levers
that would add a second bound, is [`docs/deploy/COST-BOUND.md`](../../../docs/deploy/COST-BOUND.md).
Because the worst case is **linear** in the ceiling, nobody requests a concurrency quota
increase on this account without reading that document first.

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
| `scenario_permit_id` | `string` | `dec0de00-…0001` | The permit the three beats drive — the row `seed_demo.py` actually seeds, read back out of `mainline_demo` on 2026-08-12. Published under two names — see [environment](#environment-variables). |
| **`demo_signer_sub`** | `string` | **`demo.signer`** | The principal beat 4 signs as, published as `$MAINLINE_DEMO_SIGNER_SUB`. **The seed is authoritative, not this default:** `verticals/mainline/db/seeds/demo/demo_world.sql:125` inserts it into `mainline.signing_credential.signer_sub`. Load-bearing — `fn_disposition_project` joins `mainline.person` on it (`0102_fn_disposition_project.sql:155`). Refuses the empty and the padded string, because `scenario.from_env` computes `.strip() or "demo.signer"` and a blank value is a silent revert, not an unset. |
| **`demo_countersigner_sub`** | `string` | **`demo.countersigner`** | The second principal beat 4 countersigns as, published as `$MAINLINE_DEMO_COUNTERSIGNER_SUB`. Authoritative source `demo_world.sql:133`; joined on at `0102_fn_disposition_project.sql:174`. **Must differ from `demo_signer_sub`** — the database refuses a self-countersignature (`needs_second_signer`, `0066_disposition.sql:176`), so a plan-time precondition on the function refuses it first. |
| `log_level` | `string` | **`WARN`** | The **application** level. Published as `$LOG_LEVEL` **and** wired into `logging_config.application_log_level`. Was `INFO`; ingestion is billed on arrival and a working handler was measured emitting p50 = 0 bytes of its own per invocation, so the level only decides how loud a *misbehaving* one may be. The **system** level is a different field, hard-coded to `WARN` because that is the quietest its enum allows, and AWS publishes no level-to-event mapping — so `platform.start`/`platform.report` are counted as present. |
| `memory_size` | `number` | **`256`** | MB. Was `512`, justified by a sentence that was false ("lowering this makes cold starts worse *without making the bill smaller*"). It is the **only** lever that is duration-independent: it halves compute outright and roughly halves the flood rate. It costs a slower cold start on a judge's first click, and there is **no measurement of a 256 MB Lambda anywhere in this evidence.** |
| `timeout` | `number` | **`14`** | Seconds. Was 25, then 15. A **reliability** bound — Lambda bills actual duration, so this moves the bill by nothing. See [the timeout is 14 s](#the-timeout-is-14-s-it-is-a-reliability-bound-and-the-number-is-arithmetic). Still capped at 29 so every configuration stays valid for CloudFront's 30 s origin read timeout. |
| **`max_response_bytes`** | `number` | **`139264`** | Published as `$MAINLINE_MAX_RESPONSE_BYTES`. Mirrors `static_site.DEFAULT_MAX_RESPONSE_BYTES = 136 * 1024`, which is **derived from the deployed tree**: 1.122x the largest `.gz` object that ships (124,127 B). Measured on **wire** bytes, not on the 33 %-larger base64 envelope. |
| **`rate_global_rps`** / **`rate_global_burst`** | `number` | **`10`** / **`100`** | Published as `$MAINLINE_RATE_GLOBAL_RPS` / `_BURST`. Mirror `ratelimit.DEFAULT_GLOBAL_RPS` / `_BURST`. Per **execution environment**, so the fleet bound is `rps x account_concurrency_ceiling` = 100 rps. This is the first order-of-magnitude lever in the whole cost model and it was running unpublished. |
| **`rate_ip_rps`** / **`rate_ip_burst`** | `number` | **`5`** / **`50`** | Published as `$MAINLINE_RATE_IP_RPS` / `_BURST`. Mirror `ratelimit.DEFAULT_IP_RPS` / `_BURST` — half the global pair. Bounds a **caller**, not an attacker. |
| **`log_budget_bytes`** | `number` | **`4096`** | Published as `$MAINLINE_LOG_BUDGET_BYTES`. Mirrors `logbudget.DEFAULT_BUDGET_BYTES`. **Raising it requires raising `cost-guard`'s `log_incoming_bytes_threshold` proportionally** — that threshold is derived from it. |
| `reserved_concurrent_executions` | `number` | **`-1`** | **Was `20`, and `20` cannot be applied on this account.** `-1` = reserve nothing, draw from the account pool. Not a cost cap and never was — `min(20, 10) = 10`. `0` is the documented kill switch. |
| `log_retention_days` | `number` | `7` | CloudWatch retention. `0` (never expire) is not offered. **Unchanged by D1.** |
| `duration_p99_threshold_ms` | `number` | **`13500`** | p99 alarm threshold. Was `12000`, and it went **up** because the alarm now **acts**: `infra/envs/demo` wires a stop topic into `alarm_actions`, so a breach is an outage rather than a red square. Pinned by **two** plan-time preconditions into `13,022 < T < 14,000` — a floor so a cold start cannot stop the demo, a ceiling because Lambda caps the `Duration` datapoint at the timeout. |
| **`modelled_worst_legitimate_duration_ms`** | `number` | **`13022`** | The **unconditional** floor under the row above. `docs/deploy/LATENCY.md` §5.1's binding case: a **cold** start at 256 MB with a 2x worse tail. It is a **model, not a measurement**, and it is labelled that way in `LATENCY.md` too — if an apply ever yields real `Duration` percentiles, this is the number to replace. It was written conditional on `alarm_actions` first and the conditional form was **measured not to fire**; see below. |
| `concurrency_alarm_threshold` | `number` | **`8`** | Abuse tripwire, on the **account-level** `ConcurrentExecutions` metric. **Was `20`, above a physical ceiling of `10`** — an alarm that could not fire. A plan-time precondition refuses any value not strictly below `account_concurrency_ceiling`. |
| **`account_concurrency_ceiling`** | `number` | **`10`** | The account's measured Lambda concurrency quota — the maximum `ConcurrentExecutions` can physically take, and the bound every concurrency threshold here must sit strictly below. A variable and not a `data` lookup so both sides of the precondition are known at *plan* time and the plan stays byte-reproducible. A caller on another account sets it to what `get-account-settings` returns for theirs. |
| `alarm_actions` | `list(string)` | `[]` | SNS topics notified on ALARM, on **all four** alarms. The module default is still empty, but **`infra/envs/demo` passes the cost guard's STOP topic**, so in the shipping configuration a breach of any of the four takes the demo down until a human runs `kill_switch.sh --restore`. See [these four now STOP the demo](#these-four-now-stop-the-demo-and-one-consequence-is-refused-rather-than-accepted). |
| **`ok_actions`** | `list(string)` | `[]` | SNS topics notified on **recovery**. A separate list since this wave: all four alarms used to read `ok_actions = var.alarm_actions`, which with a stop topic in it means a stop fired by the demo getting *better*. The default is byte-for-byte what the old expression evaluated to in every configuration that existed. |
| `create_dashboard` | `bool` | `true` | First three dashboards per account are free. |
| `extra_environment` | `map(string)` | `{}` | Merged in. Cannot carry `MAINLINE_DSN`, a Lambda reserved name, or a key this module sets — now including `MAINLINE_WEB_ROOT`, the two signer subs, and the six `MAINLINE_*` bounds, each of which has its own variable. `local.environment` is `merge(extra_environment, {…module keys…})` and `merge`'s last argument wins, so a key set in both would be silently discarded; the validation makes that a plan-time refusal instead. |
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
| `alarm_names` | 4 names | `aws cloudwatch describe-alarms --alarm-names <these>`, from a workstation that **has** a credential — `scripts/deploy/aws_live_probe.py`. **Not** the `demo-health` workflow: it has no AWS credential and neither does any other workflow here. All four return `INSUFFICIENT_DATA` until the demo is exercised, by design. |
| **`alarm_arns`** | 4 ARNs | to be **compared against `cost-guard`'s `alarm_arns`**. The guard's topic policy admits `cloudwatch.amazonaws.com` only for its own three alarm ARNs; none of these four is in that list, and the env root points them at that topic anyway. Whether they can publish rests on the policy's default `Principal AWS:*` statement, and only an apply settles it. |
| **`published_bounds`** | 15 fields, **all plan-known** | "what is actually in force?" in one command, instead of unzipping a 7.6 MB package to read a Python constant. `alarm_actions_armed` is deliberately **not** a field here: it cannot be plan-known, and one unknown field renders the whole object `(known after apply)`. |
| **`alarm_actions_armed`** / **`ok_actions_armed`** | `true` / `false` | `(known after apply)` — `try()` over a counted module yields unknown. The wiring itself is provable from the plan's `configuration` section; see `evidence/deploy/cost/plan-shape.json`. |
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

**And the handler now agrees, which it did not before.** This reasoning used to hold only
at the Terraform layer: the Function URL had no `cors` block, but the handler itself set
`access-control-allow-origin` on the responses it built — so the header the infrastructure
declined to add was added one layer down, and the argument above was true of the plan and
false of the running demo. On an `authorization_type = NONE` URL that wildcard is the
difference between *"any page on the internet may make a no-credentials request to this URL
and **not read** the answer"* and *"…and **read** it"* — every `/v1/*` envelope, error
detail and SQLSTATE, readable by script from anywhere. The handler no longer emits it
(`mainline_demo_api.app`, and `tests/test_response_contract.py` asserts its absence), so
**"no `cors` block, nothing to allow" is now consistent end to end** — one origin at the
URL, one origin in the response, and no third place where a header could reappear.

If a future caller ever serves the console from a second hostname, the repair is a `cors`
block naming *that hostname*, in the same commit as the second hostname — never `*` — and
it belongs at *this* layer, not in the handler.

### The timeout is 14 s, it is a RELIABILITY bound, and the number is arithmetic

> **It moved from 15 s to 14 s on 2026-08-13, and `memory_size` from 512 MB to 256 MB with
> it.** The paragraphs below are the original cold-path reasoning and they are kept because
> the *shape* of the argument is unchanged: a cold invocation pays runtime init, a psycopg
> import, an SSM read with a KMS decrypt behind it, a TLS+pgwire connect, and then six round
> trips. What changed is that `docs/deploy/LATENCY.md` **measured** those terms instead of
> bounding them by the only figure anyone had. §5.1's binding case — a cold start at 256 MB
> with a 2x worse tail — is 13,022.9 ms, and 14 s is the smallest whole second that clears
> it, by 1.07x.
>
> **This number is not a spend bound and nobody may sell it as one.** Lambda bills actual
> duration, so a 5.66 ms invocation costs exactly the same at 14 s as at 3 s. The 3 s that
> was asked for is refused on arithmetic: it is 0.80x the warm in-region `gate_run` p99
> corrected to Lambda (3,729 ms) and would truncate the headline beat — the only beat that
> writes anything and the one on screen — with no cold start and no `40001` retry involved.
> A truncated headline beat is a far worse defect than a larger bill, and here it is not
> even a trade.
>
> **The 2.91 s figure below is superseded, not deleted.** It was a workstation-to-Singapore
> connect across the public internet from Australia and it was honestly labelled a ceiling
> rather than the Lambda figure. `LATENCY.md` §3 method B is the in-region correction.



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

Measured on 2026-08-10 in account `0229REDACTED8246`:

```
$ aws kms list-aliases --region ap-southeast-1 \
    --query "Aliases[?AliasName=='alias/aws/ssm']"
[{"AliasName": "alias/aws/ssm",
  "AliasArn": "arn:aws:kms:ap-southeast-1:0229REDACTED8246:alias/aws/ssm"}]
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
      "arn:aws:ssm:ap-southeast-1:0229REDACTED8246:parameter/mainline/demo/dsn"
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
| **`MAINLINE_DEMO_SIGNER_SUB`** | `mainline_demo_api.scenario.from_env` | **New.** The principal beat 4 signs as. From `var.demo_signer_sub`; the authoritative value is `demo_world.sql:125`. See the fourth note below — this one was **load-bearing and unpublished**, which is worse than inert. |
| **`MAINLINE_DEMO_COUNTERSIGNER_SUB`** | `mainline_demo_api.scenario.from_env` | **New.** The principal beat 4 countersigns as. From `var.demo_countersigner_sub`; authoritative value `demo_world.sql:133`. Must differ from the signer — a plan-time precondition refuses equality. |
| *(no `MAINLINE_DEMO_SITE_ID`)* | — | **Deliberately absent.** `scenario.from_env` reads a `SITE_ID` override, but `fn_disposition_project` projects the site away (invariant I02, `gate_run.py:106-111`), so publishing it would be an override that looks configured and is inert. |
| **`MAINLINE_WEB_ROOT`** | `mainline_demo_api.app` | **New under D1.** Where the console SPA lives inside the package: `/var/task/web` (`$LAMBDA_TASK_ROOT` + the `web/` directory the build script writes). Load-bearing — this function serves `/` as well as `/v1/*`, and a wrong value gives the judges a 404 at `/` beside a perfectly green `/v1/health`. From `var.web_root`; also emitted as an output so the deploy script can assert the zip contains it. |
| `LOG_LEVEL` | **nothing** | Conventional name. `logging_config.application_log_level` is what filters. `WARN` since this wave. |
| **`MAINLINE_MAX_RESPONSE_BYTES`** | `mainline_demo_api.static_site.max_response_bytes()` | **New.** `139264`. The wire-byte ceiling on any single response. Mirrors `DEFAULT_MAX_RESPONSE_BYTES = 136 * 1024`, itself derived from the deployed tree at 1.122x the largest shipping `.gz` object. |
| **`MAINLINE_RATE_GLOBAL_RPS`** / **`_BURST`** | `mainline_demo_api.ratelimit` | **New.** `10` / `100`, per execution environment — fleet bound `10 x 10 = 100 rps`. The first order-of-magnitude lever in the cost model, and it was running unpublished. |
| **`MAINLINE_RATE_IP_RPS`** / **`_BURST`** | `mainline_demo_api.ratelimit` | **New.** `5` / `50`. Bounds a caller, not an attacker. |
| **`MAINLINE_LOG_BUDGET_BYTES`** | `mainline_demo_api.logbudget` | **New.** `4096` per invocation. Raising it requires raising `cost-guard`'s `log_incoming_bytes_threshold` proportionally. |
| *(anything in `extra_environment`)* | varies | e.g. `MAINLINE_DEMO_ALLOW_MUTATION`, `MAINLINE_DEBUG`. |

Five honest notes, because a variable that looks configured and behaves inert is worse
than one that is absent — and, as the fourth and fifth record, a *load-bearing* variable
that is never published at all is worse than either:

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
* **The two signer subs were load-bearing and unpublished, and that is the worse defect,
  not the milder one.** `scenario.from_env` reads `MAINLINE_DEMO_SIGNER_SUB` and
  `MAINLINE_DEMO_COUNTERSIGNER_SUB` (`scenario.py:209-212`) and falls back to the constants
  `"demo.signer"` / `"demo.countersigner"` compiled into the application. This module
  published **neither**, so the only beat that writes a disposition ran on values no
  deployed configuration named. The values were *correct* — they equal what
  `demo_world.sql:125,133` seeds — but they agreed with the seed by coincidence, and a
  database seeded with different principals would have failed beat 4 with **nothing in
  `aws lambda get-function-configuration` to point at.** `MAINLINE_SCENARIO_PERMIT_ID`
  above is an override that looks configured and is inert; this was the reverse, and the
  reverse is harder to diagnose because there is no wrong value to find. They are published
  now, so the expectation is readable off the deployed function and a divergence between
  Terraform and the seed is a diff between two named things. **The seed remains
  authoritative in both directions:** if the two disagree, the fix is this module's default,
  never `demo_world.sql`.
* **The six `MAINLINE_*` bounds were ENFORCED and UNREADABLE, which is the same defect one
  notch milder.** `static_site.py`, `ratelimit.py` and `logbudget.py` each carry a real,
  enforced bound and each reads an environment variable that overrides it. This module
  published **none** of them, so all six ran on constants compiled into the application. An
  operator asking *"what response ceiling is this function actually enforcing?"* had to
  unzip a 7.6 MB deployment package and read a Python constant; `get-function-configuration`
  answered nothing. That is not a wrong value — it is the absence of a question. **The
  application is authoritative and Terraform mirrors it**, the same rule the two subs follow
  toward the seed, pointed the other way: each default cites the constant it copies, and a
  published value that *disagrees* with the code would be worse than none, because the
  environment variable wins at runtime while reading like documentation. **Publishing does
  not disarm:** every parser falls back to its compiled-in default on a value it cannot
  read — `float("inf")` and `float("nan")` both parse, which is exactly why
  `ratelimit._rate()` is not a bare `try: float(...)` — so the worst a typo does is revert
  to the previous behaviour, and a `validation` block refuses the typo at plan time anyway.

`MAINLINE_DSN` — a DSN passed directly — is **rejected** by `extra_environment`'s
validation. It is the escape hatch `db.py` offers for local development, and letting it
through here would put the password back in Terraform state through the side door.

---

## Alarms and dashboard

The first ten CloudWatch alarms per account are free; these are four of them. The module
still defaults `var.alarm_actions` to `[]` — an SNS topic whose email subscription nobody
confirmed is a control that looks present and is not — **but `infra/envs/demo` no longer
leaves it empty.** Read the next subsection before the table.

| Alarm | Metric | Condition | Why |
|---|---|---|---|
| `<fn>-errors` | `Errors` Sum, per function | `> 0` over 5 min | The handler is written never to raise: refusals are 200s with a `REFUSED` verdict, failures are JSON problem documents. An `Errors` datapoint means it raised anyway. |
| `<fn>-throttles` | `Throttles` Sum, per function | `> 0` over 5 min | The account concurrency ceiling is biting. A throttled Function URL invocation reaches the caller as HTTP 429 with no body from the handler — user-visible and undiagnosable from the browser. |
| `<fn>-duration-p99` | `Duration` p99, per function | `> 13 500 ms` | Approaching the 14 s timeout. On this stack that is nearly always the pgwire round trip, not the handler — `/v1/health` reports connect time separately. **Two plan-time preconditions:** `< timeout × 1000` always, and `> modelled_worst_legitimate_duration_ms` whenever the alarm has an action. |
| `<fn>-concurrency` | `ConcurrentExecutions` Max, **account-level** | `> 8` | Abuse tripwire, against a measured ceiling of **10**. A judging session is a few browsers making four requests each. **Plan-time precondition:** threshold must be `< account_concurrency_ceiling`. |

### These four now STOP the demo, and one consequence is refused rather than accepted

`infra/envs/demo` passes `module.guard[0].sns_topic_arn` as `var.alarm_actions`. That topic
is a **stop** topic: everything subscribed to it invokes a responder that calls
`lambda:PutFunctionConcurrency(ReservedConcurrentExecutions=0)` on this function. So in the
shipping configuration a breach of any row above takes the demo down — `HTTP 429`, no body,
to everyone — until a human runs `scripts/deploy/kill_switch.{sh,ps1} --restore`.

**Three of the four are health signals and stopping on them is a self-inflicted outage.**
`infra/modules/cost-guard/outputs.tf` says exactly that about the ARN it exports, and it is
right. The env root wires it anyway under a ranking this project states out loud
(`docs/leads/cost-finish-plan.md` §0.5): *an outage is recoverable by one command and a bill
is not.* Under the founder's bounded-but-open posture the URL has no authentication, so
anyone can already trip the guard's own burst alarm; these four widen the set of ways that
can happen, they do not create it. **That trade belongs in a residual column, and
`docs/deploy/COST-BOUND.md` is where it is costed.**

**The one consequence that ranking does not excuse is `-duration-p99` firing on a cold
start.** A cold start is not abuse and not an incident — it is a judge's first click. At
`memory_size = 256` the modelled cold path is 6,511 ms and its 2x tail binding case is
13,022.9 ms (`docs/deploy/LATENCY.md` §5.1), so the old 12,000 ms threshold would have
stopped the demo on it. The alarm therefore carries a **floor** as well as its ceiling:

```
                 13,022 ms                  13,500 ms         14,000 ms
   ------------------|-------------------------|-----------------|-------------->
   modelled worst legitimate            the threshold      timeout x 1000
   (cold @ 256 MB, 2x tail)                                (Duration is capped here)
          |                                                       |
          +-- below this, a cold start STOPS the demo             +-- at or above this,
                                                                      the alarm CANNOT fire
```

Both edges are `lifecycle.precondition`s, checked at plan time, costing one evaluation and
no API call. If the band is ever empty, the finding is that `timeout` is too small for
`memory_size` — *never* that a precondition should be widened.

**The floor is UNCONDITIONAL, and the reason is a measurement of my own first attempt.** It
was written as `length(var.alarm_actions) == 0 || <the comparison>`, so that an alarm which
only *reports* would not carry a floor. That reasoning is fine and the expression did not
work: `infra/envs/demo` reaches the stop topic through
`try([module.guard[0].sns_topic_arn], [])`, `try()` returns a **wholly unknown** value when
its argument contains an unknown, and **Terraform defers an unknown precondition to apply
instead of failing the plan.** Planting the violation is what found it:

```console
$ terraform plan -var api_duration_p99_threshold_ms=12000   # the OLD default
Plan: 24 to add, 0 to change, 0 to destroy.          # <- should have been refused
$ terraform plan -var api_duration_p99_threshold_ms=13022   # exactly ON the floor
Plan: 24 to add, 0 to change, 0 to destroy.          # <- should have been refused
```

A precondition that cannot be evaluated at plan time is *a control that looks present and is
not* — the exact defect the rule at the head of this section exists to refuse — so the guard
clause was **deleted, not repaired**, leaving two plain variables. Re-run after the fix, all
four edges exercised:

```console
$ terraform plan -var api_duration_p99_threshold_ms=12000   Error: Resource precondition failed
$ terraform plan -var api_duration_p99_threshold_ms=13022   Error: Resource precondition failed
$ terraform plan -var api_duration_p99_threshold_ms=13023   Plan: 24 to add   # one ms inside
$ terraform plan -var api_duration_p99_threshold_ms=14000   Error: Resource precondition failed
$ terraform plan                                            Plan: 24 to add   # 13 500, shipping
```

**What the unconditional form costs:** a caller with `alarm_actions = []` can no longer set a
deliberately sensitive p99 warning below the modelled worst legitimate invocation. That is a
smaller loss than it sounds — an alarm that fires on every cold start is noise whether or not
it acts — and the honest repair is to lower `modelled_worst_legitimate_duration_ms` to a
figure you have *measured*, which carries the threshold down with it.

### `ok_actions` is a separate list, and it is empty

All four alarms used to read `ok_actions = var.alarm_actions`. Under the old empty default
that was invisible; with a stop topic in the list it means **every recovery of every alarm
fires the stop responder again** — a stop triggered by the demo getting better. The
responder refuses an OK transition on its own, but `infra/modules/cost-guard` states the
rule this module was the exception to: the place to not do that is where the action is
chosen, and the responder's refusal is the second belt rather than the first.

`var.ok_actions` defaults to `[]`, which is byte-for-byte what the expression evaluated to in
every configuration that previously existed. **Nothing is weakened by the split**; what
changed is that arming one list no longer arms the other by accident.

### The rule, stated once so it is not re-derived

> **Any alarm on a metric with a known physical ceiling carries a plan-time
> `lifecycle.precondition` placing its threshold strictly below that ceiling.**

A threshold at or above a ceiling the metric cannot exceed does not fire *late* — it
**cannot fire**. It draws a red line on the dashboard, reports a green alarm to
`describe-alarms`, and stops nothing: *a control that looks present and is not.* Both sides
of every such comparison are plain variables, so the check costs one plan evaluation and no
API call.

Two of the four alarms have such a ceiling and both now carry the precondition —
`duration_p99` against `timeout × 1000` (Lambda caps the `Duration` datapoint at the
timeout) and `concurrency` against `account_concurrency_ceiling` (Lambda throttles at the
account quota, so `ConcurrentExecutions` is capped there). `errors` and `throttles` carry
none, and that is not an omission: both are `> 0` on unbounded counters, so there is no
ceiling for a threshold to sit under.

**The concurrency alarm is the reason the rule is written down.** It shipped at `> 20`
against a metric whose physical ceiling is `10` — the identical defect `duration_p99`'s own
precondition already refused, one resource lower in the same file. The idiom was invented
here and then not applied to its immediate neighbour. Measured, this machine, Terraform
v1.14.8, against the real module:

```console
$ terraform plan -var thr=9      # strictly below the ceiling
Plan: 11 to add, 0 to change, 0 to destroy.                       # exit 0

$ terraform plan -var thr=10     # EQUAL to the ceiling — still cannot fire
Error: Resource precondition failed                               # exit 1

$ terraform plan -var thr=20     # the value that actually shipped
Error: Resource precondition failed                               # exit 1
  on .terraform/modules/api/main.tf line 620, in resource "aws_cloudwatch_metric_alarm" "concurrency":
 620:       condition     = var.concurrency_alarm_threshold < var.account_concurrency_ceiling
    │ var.account_concurrency_ceiling is 10
    │ var.concurrency_alarm_threshold is 20

concurrency_alarm_threshold (20) is not strictly below account_concurrency_ceiling (10).
Lambda throttles at the account's concurrency quota, so the ConcurrentExecutions datapoint
is capped at 10 and an alarm at or above it could never breach - a control that looks
present and is not: a red line on the dashboard, a green alarm in describe-alarms, and
nothing at all between a public Function URL and the bill. ...
```

### The concurrency alarm is **account-level**, and that is a fix, not a shortcut

It carries **no `FunctionName` dimension**. Lambda publishes the *per-function*
`ConcurrentExecutions` metric dependably only for functions that **have** reserved
concurrency, and `reserved_concurrent_executions` is `-1` (this account refuses every
positive reservation). A per-function alarm would therefore sit in `INSUFFICIENT_DATA`
indefinitely — the same defect as an unreachable threshold, wearing a different hat. The
module's own variable description said so and the alarm shipped the dimension anyway, which
documents a defect rather than fixing one.

The justification for the account-level metric is **measured**, not assumed:

```console
$ aws lambda get-account-settings --region ap-southeast-1
  AccountLimit.ConcurrentExecutions            10
  AccountLimit.UnreservedConcurrentExecutions  10
  AccountUsage.FunctionCount                    0

$ aws lambda list-functions --region ap-southeast-1 --query 'Functions[].FunctionName'
  []
```

**Zero functions exist in `ap-southeast-1`.** This module creates the first one, so the
account-level metric in this region *is* this function's metric — not an approximation of
it, the same number.

**The invalidating condition, stated because it is not hypothetical.** The moment a
*second* Lambda function is created in `ap-southeast-1`, this alarm stops being this
function's concurrency and becomes a true account aggregate: it would breach on somebody
else's traffic and stay silent while this function's own share sat below the line. If that
day comes the repair is a `metric_query` block filtering to this function, or a reserved
concurrency on the other function — **not a raised threshold.** (`ap-southeast-2` already
holds one unrelated function, which is exactly why this reasoning is region-scoped and why
the count above was re-read rather than assumed.)

### All four treat missing data as `missing`, not `notBreaching`

> **Green must mean measured-and-fine, never not-measured.**

Under `notBreaching` an idle demo displays **four green alarms**, and the one thing an
operator reads off a green alarm — *"I looked, it is healthy"* — is then false: nobody
called the function, so nothing was measured. Under `missing` an unexercised demo reads
`INSUFFICIENT_DATA`, which is the true state and the one that prompts the next question
instead of closing it. The price of the honest setting is that a demo nobody has visited
does not show green. That is not a price.

A consequence for anyone asserting on these alarms: **`INSUFFICIENT_DATA` is not a pass.**
Only `OK` is, and only after traffic.

### Who reads the alarms — there is no CI reader, because there is no CI credential

This section used to say the alarms were read *"by the hourly `demo-health` workflow, which
calls `describe-alarms`"*. **It does not, and no workflow in this repository could.**
`.github/workflows/demo-health.yml` makes outbound HTTP requests against `/v1/health` and
declares `permissions: contents: read`; it contains no `cloudwatch` call, no
`aws-actions/configure-aws-credentials` step and no `id-token: write`. **No workflow in this
repository has an AWS credential at all** — the only `AWS_*` mention anywhere under
`.github/workflows` is an `env -u` in `aws-evidence.yml` that *unsets* every one of them, on
purpose, to prove the evidence verifier needs no account.

A CI-based alarm reader cannot be shipped because there is no CI credential to read with,
and a document naming a reader that does not exist is worse than naming none: it retires the
question. The readers that actually exist:

| Reader | Needs a credential? | Notes |
|---|---|---|
| the CloudWatch console | yes (a human session) | — |
| the dashboard's alarm widget | yes | fifth widget, all four ARNs at a glance — why the dashboard earns its free slot |
| `scripts/deploy/aws_live_probe.py` | yes | run from a workstation that **has** one |
| an SNS topic via `var.alarm_actions` | n/a | **In `infra/envs/demo` this is now the cost guard's STOP topic, whose subscriber is a Lambda and needs no confirmation.** The "unconfirmed subscription" caveat still applies to any *human-facing* topic and is why the module's default stays empty. **One hazard is open and no plan can settle it:** the guard's topic policy admits `cloudwatch.amazonaws.com` under an `ArnLike` on `aws:SourceArn` naming exactly the guard's own three alarm ARNs, and none of these four is in that list. Whether they can publish rests on the policy's first statement (SNS's default `Principal AWS:*` narrowed by `AWS:SourceOwner`). If they cannot, four alarms carry an action SNS denies — which `describe-alarms` renders identically to one that delivers. `terraform output api_alarm_arns` / `guard_alarm_arns` print the two sets; `evidence/deploy/cost/plan-shape.json` records them side by side. |

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
free, against **256 MB** × ~300 ms × 10 000 requests = **768 GB-s** (it was
512 MB × ~300 ms = 1 536 GB-s before `memory_size` halved; the free tier was never the
binding constraint in either case — see `var.memory_size`). Logs: 7-day retention, far
under the 5 GB free ingest. Alarms: 4 of the first 10. Dashboard: 1 of the first 3. SSM
Parameter Store Standard: free. Function URL: no charge beyond the invocation.
**≈ $0.00/month under judging load.** The full itemisation, re-checked under D1, is in
`docs/leads/ship-final.md` §2.1 — removing CloudFront and the site bucket from the request
path made the bill *smaller*, not larger.

> **That figure is the expected case, and it is not a bound.** This paragraph used to add
> *"and the reserved-concurrency cap means that stays true under abuse"*, which was false
> twice over: `reserved_concurrent_executions` is `-1`, and at `20` it never capped
> anything either (`min(20, 10) = 10`). Under a **sustained flood** against a public
> `authorization_type = NONE` URL the 30-day worst case is **four to five orders of
> magnitude above $0.00**, because the flood target is the static tree in the package —
> egress, which no alarm and no reservation here stops. The arithmetic, its measured
> inputs and the menu of levers that would add a real bound are in
> [`docs/deploy/COST-BOUND.md`](../../../docs/deploy/COST-BOUND.md). Read it before
> treating the free-tier line above as a ceiling.

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

And the planned function configuration, from `terraform show -json` — **re-run on
2026-08-13** after `demo_signer_sub` and `demo_countersigner_sub` were added, so the two
new lines below are read out of a real plan rather than predicted from the diff:

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
env MAINLINE_DEMO_PERMIT_ID = dec0de00-0006-4000-8000-000000000001
env MAINLINE_SCENARIO_PERMIT_ID = dec0de00-0006-4000-8000-000000000001
env MAINLINE_DEMO_SIGNER_SUB        = demo.signer
env MAINLINE_DEMO_COUNTERSIGNER_SUB = demo.countersigner
env LOG_LEVEL               = INFO
```

**Six of those lines moved on 2026-08-13 and eight lines were added.** The block above is
kept as the dated record it is; the block below is the same read taken from the plan the
env root produces today, and every difference has a derivation behind it rather than a
preference:

```
timeout          14            ← was 15. LATENCY.md §5.1: smallest whole second clearing
                                 the binding case (cold at 256 MB, 2× tail) of 13,022.9 ms.
                                 A RELIABILITY bound. Lambda bills actual duration, so this
                                 moves the bill by NOTHING.
memory_size      256           ← was 512. The only lever in the menu that is
                                 duration-independent. Costs a slower cold start on a
                                 judge's first click, and that cost is stated not buried.
architectures    ['arm64']
url auth_type    NONE
url cors         []            ← absent, not empty-permissive
url invoke_mode  BUFFERED
p99 threshold    13500         ← was 12000, and it went UP because the alarm now ACTS.
                                 Pinned by two plan-time preconditions into
                                 13,022 < T < 14,000: a floor so a cold start cannot stop
                                 the demo, a ceiling so the alarm can still fire.
system log level WARN          ← unchanged, and already the quietest value its enum allows
env LOG_LEVEL               = WARN          ← was INFO
env MAINLINE_WEB_ROOT       = /var/task/web
env MAINLINE_DSN_PARAM      = /mainline/demo/cockroach_dsn
env MAINLINE_DEMO_DATABASE  = mainline_demo
env MAINLINE_DEMO_PERMIT_ID = dec0de00-0006-4000-8000-000000000001
env MAINLINE_SCENARIO_PERMIT_ID = dec0de00-0006-4000-8000-000000000001
env MAINLINE_DEMO_SIGNER_SUB        = demo.signer
env MAINLINE_DEMO_COUNTERSIGNER_SUB = demo.countersigner
env MAINLINE_MAX_RESPONSE_BYTES = 139264    ← NEW
env MAINLINE_RATE_GLOBAL_RPS    = 10        ← NEW
env MAINLINE_RATE_GLOBAL_BURST  = 100       ← NEW
env MAINLINE_RATE_IP_RPS        = 5         ← NEW
env MAINLINE_RATE_IP_BURST      = 50        ← NEW
env MAINLINE_LOG_BUDGET_BYTES   = 4096      ← NEW
```

> **The six new keys were ENFORCED AND UNREADABLE, which is a worse state than an inert
> override.** `static_site.py`, `ratelimit.py` and `logbudget.py` each carry a real bound and
> each reads an environment variable that overrides it. This module published none of them,
> so all six ran on constants compiled into the application: correct, in force, and invisible
> to `aws lambda get-function-configuration`. The permit-id note further down calls an
> override that looks configured and is inert "the worst of the three possible states"; a
> bound that is in force and unreadable is the second worst, because an operator cannot
> discover that there is a question to ask.
>
> **The application is authoritative and Terraform mirrors it** — the same rule the two
> signer subs follow toward `demo_world.sql`, pointed the other way. Each default cites the
> constant it copies. A published value that DISAGREES with the code is worse than none,
> because the environment variable wins at runtime while reading like documentation.
>
> **Publishing does not disarm.** Every parser falls back to its compiled-in default on a
> value it cannot read — `float("inf")` and `float("nan")` both parse, which is exactly why
> `ratelimit._rate()` is not a bare `try: float(...)` — so the worst a typo does is revert to
> the previous behaviour. The `validation` blocks refuse the typo at plan time anyway,
> because a silent revert is still an override that looks configured and is not.

> **The two subs are additions, and the plan was otherwise byte-identical.** *(Dated
> record. The env root's plan is `Plan: 24 to add` today, because `module "guard"` was
> instantiated afterwards and adds thirteen resources — see
> `infra/envs/demo/README.md`. The measurement below is left as it was taken.)* The env root
> was planned twice on 2026-08-13 against the same package — once from `HEAD`, once with
> this change — and diffed: `Plan: 11 to add, 0 to change, 0 to destroy` both times, and the
> **only** substantive hunk is the two new keys in `environment.variables`. The check tally
> went **44/44 pass → 48/48 pass**, the four additions being
> `var.demo_signer_sub` / `var.demo_countersigner_sub` at the root and the same two inside
> `module.api`; nothing was removed and nothing moved from pass. The new
> `lifecycle.precondition` on `aws_lambda_function.this` adds no check *object* — Terraform
> groups conditions under the resource — which is why the resource count stays at 6.
>
> **All three new refusals were exercised, not asserted.** `-var 'demo_signer_sub='` and
> `-var 'demo_signer_sub= demo.signer '` are both refused with `Invalid value for variable`
> (a blank value is `.strip() or "demo.signer"`, i.e. a silent revert to the in-code
> constant, and a padded one is stripped before use so the published string is not the
> string the handler matched on); `-var 'demo_countersigner_sub=demo.signer'` is refused
> with `Resource precondition failed` naming
> `verticals/mainline/db/migrations/0066_disposition.sql:176`. A control that cannot refuse
> is not a control.

> **The two permit lines were `077a6fdd-2167-559c-b2ff-8e3c8352504d` until 2026-08-12.**
> That is `scenario.py:77`'s uuid5 fallback and **no row with that id has ever been
> seeded**: a read-only `SELECT permit_id::string, state::string, open_blocking,
> head_seq, gate_epoch FROM mainline.permit ORDER BY permit_id` against the live
> `mainline-dev` / `mainline_demo` cluster returns **exactly one row**,
> `dec0de00-0006-4000-8000-000000000001 | dispositioned | 1 | 2 | 1`. Deploying the old
> default would have answered `422 demo_history_not_seeded` to every judge. The default in
> `variables.tf` was corrected, the env-root plan was re-run, and the whole exchange —
> query, verbatim rows, before/after values, plan diff — is
> [`evidence/deploy/permit-id-agreement.json`](../../../evidence/deploy/permit-id-agreement.json).
>
> `MAINLINE_DSN_PARAM = /mainline/demo/dsn` above is **this module's own default** (see
> the variables table). The env root overrides it to `/mainline/demo/cockroach_dsn`, which
> is what `evidence/deploy/terraform-plan-furl.txt` — the artefact of record for the
> deploy — actually plans. Both are correct for their respective runs.

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
* **No alarm has ever evaluated.** `treat_missing_data = "missing"`, the account-level
  dimensioning and the concurrency precondition are all proved at *plan* time — the
  precondition by three real refusals at thresholds 9/10/20, the other two by reading the
  planned attributes back out of `terraform show -json`. That the account-level
  `ConcurrentExecutions` metric *is* this function's metric follows from
  `AccountUsage.FunctionCount = 0` and an empty `list-functions` in `ap-southeast-1`, both
  read today — but no datapoint has been published, because nothing has been applied.
* **The modified dashboard body was not re-validated against `PutDashboard`.** The
  concurrency widget's metric entry lost its `FunctionName` dimension pair to match the
  alarm. `jsonencode` cannot emit malformed JSON, and CloudWatch's metric-array format
  documents the dimension pairs as optional (a metric named with none references the
  aggregate) — but the provider marks `dashboard_body` **unknown at plan time**, so the
  planned bytes cannot be read back, and confirming the API accepts them needs
  `aws cloudwatch put-dashboard`, a **mutating** call this wave is forbidden to make. The
  earlier `{ "DashboardValidationMessages": [] }` transcript above validated a *different*
  body. If the apply rejects this widget, this bullet is why.
* **No Function URL has ever been created by this module**, so neither shape's runtime
  behaviour is measured: "a `NONE` URL answers the public" and "an `AWS_IAM` URL answers
  403 to an unsigned `curl`" are both AWS's documented behaviour, not observations of *this*
  function. What *is* measured is which resources each shape plans, and with which
  attributes.
* **`MAINLINE_DEMO_SIGNER_SUB` and `MAINLINE_DEMO_COUNTERSIGNER_SUB` are checked against the
  seed *file*, not against the deployed cluster.** The two defaults were not read off the
  source line and retyped — the seed's own bytes were executed. On 2026-08-13 the full
  chain (54 `trappoint-ref` + **271** `mainline` migrations) was applied to a scratch
  database on the local CockroachDB **v26.2.5** node, `demo_world.sql` was applied to it,
  and the database was asked what it holds:

  ```
  SELECT signer_sub, encode(credential_id,'hex') FROM mainline.signing_credential ORDER BY signer_sub;
    demo.countersigner   8d7b089f4c0aec7d…
    demo.signer          ff356d1461921438…
  SELECT signer_sub FROM mainline.person ORDER BY signer_sub;
    ['demo.countersigner', 'demo.signer']
  ```

  Both Terraform defaults equal what the seed actually inserts. **Nobody has run that
  `SELECT` against `mainline-dev` / `mainline_demo` in Singapore in this wave** —
  `scripts/deploy/seed_demo.py` applies the same bytes, so the cloud values follow by
  argument and not by observation of the cloud row. And what Terraform now guarantees is
  narrower than "the demo works", so it is worth stating exactly: the deployed function
  **publishes** the pair, so a divergence between this configuration and the seed is visible
  in `aws lambda get-function-configuration` instead of surfacing as a constraint failure
  inside beat 4.
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
