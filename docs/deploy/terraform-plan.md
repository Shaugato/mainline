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
> **The shipping plan creates twenty-four resources — eleven in `module.api` and thirteen
> in `module.guard` — none of them a CloudFront distribution or an S3 bucket, and at demo
> traffic its recurring cost is USD 0.00 because every line sits inside a perpetual AWS
> free tier.**
>
> That sentence is about **what the plan creates**, not about **what the demo can be made
> to spend**. Those are different numbers and §4 keeps them apart, because conflating them
> is the mistake this documentation set has already made once.

**No `terraform apply` was run to produce any of this.** `init`, `validate`, `plan` and
`show` only. A previous worker ran an apply and was correctly stopped; the apply belongs to
the orchestrator, with the founder, after reading this page.

---

## 0 · What changed, and why this page was rewritten twice

### 0.1 · 2026-08-14 — the resource count moved, and this page had said it did not

**The correction this revision exists for.** The previous revision of this page stated, in
bold, that *"the resource count did not move"*. **That was false**, and it was false against
an artefact committed in the same repository, which anybody could open. The shipping plan
creates **24** resources, not eleven.

| | Previous revision said | The artefact says | Source |
|---|---:|---:|---|
| shipping plan (`enable_cloudfront = false`) | 11 | **24** | `evidence/deploy/terraform-plan-furl.txt:843` |
| upgrade plan (`enable_cloudfront = true`) | 22 | **35** | `evidence/deploy/terraform-plan-cloudfront.txt:1219` |

The cause was `module "guard"`, instantiated at `infra/envs/demo/main.tf:632` under
`count = var.enable_api ? 1 : 0`. It contributes **13** created resources to both plans. The
page was written before that instantiation landed and was never re-derived from the
regenerated artefact.

**The direction of the fix is not a matter of taste.** The committed plan artefact is
**authoritative** and this prose is **derived**. No plan was regenerated or reconfigured in
order to recover the old number, and the sentence was corrected rather than deleted —
`tests/deploy/test_cost_model.py::test_the_shipping_plan_count_is_actually_stated_somewhere_live`
exists to catch the deletion, and its docstring reads *"A claim deleted is not a claim
corrected."*

Four further claims on this page were stale against the same regenerated artefact and are
corrected in place. They are listed here rather than fixed silently, because a page that
quietly absorbs its own errors teaches a reader nothing about how far to trust the rest:

| Claim | Was | Is | Line |
|---|---:|---:|---|
| `aws_lambda_function.this` `memory_size` | 512 MB | **256 MB** | `furl.txt:290` |
| `aws_lambda_function.this` `timeout` | 15 s | **14 s** | `furl.txt:315` |
| `-duration-p99` alarm `threshold` | 12 000 ms | **13 500 ms** | `furl.txt:124` |
| `checks` objects in the JSON | 44 | **85** | `furl.json` |
| outputs / known / unknown | 17 / 13 / 4 | **30 / 22 / 8** | `furl.json` |
| `phase` output | `"2-cloudfront"` | **the output no longer exists** | `furl.json` |

### 0.2 · 2026-08-13 — the attribute wave (retained as history)

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

**That 2026-08-13 wave changed attribute values only, and the count was eleven when it
finished.** The count moved afterwards, when `module "guard"` was instantiated — see §0.1.
The old figure is quoted verbatim in `docs/deploy/JUDGE-PACK.md`,
`docs/deploy/OBSERVABILITY.md`, `docs/submission/DEVPOST.md`,
`docs/submission/JUDGE-START.md`, `docs/STATE-OF-THE-BUILD.md` and
`scripts/submission/check_submission_ready.py`; **each of those is stale for the same reason
this page was, and none of them is this page's to edit.** They are named here so the reader
knows the correction is incomplete outside this file, not so the reader assumes it is done.

**One correction this page owes its own reader, and it has now been owed twice.** The
line-count/byte/SHA-256 table in §1 first went stale at commit `1d41442`, which masked the
AWS account id across thirteen tracked files: masking rewrote these artefacts' bytes and
nobody recomputed the table, so a reader who ran `sha256sum` got three mismatches and no
explanation. **It would have gone stale a second time in this very commit** — regenerating
all four artefacts changes every hash — which is exactly how the first lapse happened, and
is why the table was recomputed as part of the same change rather than left for a follow-up.
Every row below was re-derived from the files as they now sit on disk, and §1.1 states how
to reproduce that in one command. **A hash table is worth nothing except in the commit that
recomputes it.**

---

## 1 · The artefacts, and the commands that produced them

Terraform **v1.14.8**, providers `hashicorp/aws` **v6.58.0** and `hashicorp/archive`
**v2.8.0** (the guard's responder zip is built by `data.archive_file`), AWS profile
`mainline-dev` (read-only for a plan), region `ap-southeast-1`. Regenerated **2026-08-14**;
the plans' own `timestamp` fields say `2026-08-13T18:41:44Z` (FURL) and
`2026-08-13T18:42:39Z` (CloudFront) — those are UTC, and the local clock that wrote the
files was 2026-08-14 04:41/04:42 at UTC+10.

**The reproduction is now a script, not a recipe to retype.**
[`scripts/deploy/plan_repro.sh`](../../scripts/deploy/plan_repro.sh) reproduces either shape
(`--cloudfront` for the upgrade plan, `--json` to also emit `terraform show -json`) with no
mutating AWS call, and `docs/deploy/PRE-APPLY.md` is the document that owns the procedure.
It automates exactly the sequence below — write a local `backend_override.tf`,
`init -reconfigure`, `validate`, `plan`, `show -json`, and remove the override on any exit —
so the block is kept as a statement of shape, not as a second recipe to keep in sync.

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

`infra/envs/demo` contains **eight** files and **no `backend_override.tf`**:
`.terraform.lock.hcl`, `README.md`, `backend.tf`, `main.tf`, `outputs.tf`,
`terraform.tfvars.example`, `variables.tf`, `versions.tf`. (An earlier revision of this page
said seven, having silently skipped the dotfile; the lock file is tracked and is the thing
that pins the two provider versions named above, so it counts.)
**No S3 state object was created, read, written or locked**,
and the scratch state path was still empty after every plan — a `plan` writes no state,
which is why all four configurations read `0 to change, 0 to destroy`: there is nothing to
change or destroy yet. The `.terraform/terraform.tfstate` backend marker was removed
afterwards, so the directory is back to *"Backend initialization required"* and the next
operator has to init deliberately.

**Recomputed 2026-08-14 from the files as they now sit on disk.** All four moved in this
wave: the two FURL artefacts because the guard changed the plan, and the two CloudFront ones
because they were regenerated from a tree they had fallen a day behind (§3.1).

| Artefact | Lines | Bytes | SHA-256 |
|---|---:|---:|---|
| `evidence/deploy/terraform-plan-furl.txt` | 934 | 44 742 | `c6acbdde6a15cec6650c3771a20f2714299988ebd9bf31e8940b50f053959b10` |
| `evidence/deploy/terraform-plan-furl.json` | 1 | 336 459 | `5f0bb93c0f6e48a1c1fbf7e849461a3dc37cdc7ec724728622ff945490b06c46` |
| `evidence/deploy/terraform-plan-cloudfront.txt` | 1 314 | 59 308 | `57d8eb7675422cb7e1ba0216cf5f9331ffd3cb674565e1f2296b3f343c1ec757` |
| `evidence/deploy/terraform-plan-cloudfront.json` | 1 | 366 494 | `6b3971d2516fe691ef245f90c6d5178b2bebe1daf7f526926158d50118fe8da8` |

`terraform-plan-cloudfront.json` is **new in this wave** — the CloudFront shape previously
shipped as a human plan with no machine-readable twin, so none of §3's structural claims
could be checked mechanically. They can now.

Each file is the **verbatim** stdout+stderr of its command, byte for byte, with exactly one
transformation applied — the account-id mask of §1.2. Nothing was added, reordered or
removed. All four are **LF-terminated**, because that is what Terraform writes; two of them
previously carried CRLF, which was an artefact of the shell that captured them and not
something the tool emitted. A file described as verbatim should not have had its line
endings rewritten on the way to disk.

### 1.1 · Re-deriving the table

```bash
python - <<'PY'
import hashlib, pathlib
for p in ("evidence/deploy/terraform-plan-furl.txt",
          "evidence/deploy/terraform-plan-furl.json",
          "evidence/deploy/terraform-plan-cloudfront.txt",
          "evidence/deploy/terraform-plan-cloudfront.json"):
    b = pathlib.Path(p).read_bytes()
    print(f"{p}  lines={len(b.decode().splitlines())}  bytes={len(b)}  "
          f"sha256={hashlib.sha256(b).hexdigest()}")
PY
```

A plan artefact whose hash nobody can reproduce is a screenshot. This command is the
difference.

### 1.2 · What was scrubbed, and what was not

**One transformation, applied mechanically: the twelve-digit AWS account id is replaced by
the literal `0229REDACTED8246`** — **12** occurrences in the FURL plan, **37** in its JSON,
**19** in the CloudFront plan and **52** in its JSON. (Those four counts all rose with the
guard, which names the account in the responder's IAM policy, the SNS topic policy and the
budget filter.) That is the repository-wide convention established by commit `1d41442`
(84 occurrences across 13 files) and it is applied here for the same reason: an account
number is not a credential, but publishing one enables cross-account enumeration.

Two properties are asserted over the result, and both are checkable:

* **zero occurrences of the real twelve digits** in any of the four files;
* **zero occurrences of `000000000000`.** Twelve identical digits is the one mask that two
  different checkers read two different ways — one as a redaction, one as a value — and the
  resolution recorded in `docs/CI-STATE.md` is to *remove the digits*, not to relax either
  checker. `scripts/aws/verify_evidence.py`'s `SEC-ACCOUNT-ID` and `SEC-ARN-ACCOUNT`
  invariants pass over all four files as committed.

The only twelve-digit run a naive scan still finds in any of the four is `000000000001`, the
final group of the demo permit UUID `dec0de00-0006-4000-8000-000000000001`, which is a UUID
and not an account.

**Nothing else was redacted, because Terraform marked nothing sensitive.** Every
`sensitive_values` object in the JSON is empty or all-`false`; the literal key `"sensitive"`
appears **48** times in the FURL JSON and **49** times in the CloudFront JSON and is `false`
at every one of them, with **zero** `true` leaves anywhere in `before_sensitive`,
`after_sensitive` or `sensitive_values`; and the word `sensitive` appears **zero** times in
either human plan. **The plans contain no secret** — no DSN, no password, no access key, no
`postgresql://` URL, no private key. The word "secret" appears twice in each JSON, both times
inside module documentation that is *about* secrets not being there: *"the \"secrets are not
in Terraform state\" rule"* and *"which are not secret"*.

Terraform never holds the CockroachDB DSN. It is given the SSM parameter **name**
(`/mainline/demo/cockroach_dsn`); the SecureString is written by `aws ssm put-parameter`
outside Terraform, so it cannot appear in a plan, in `terraform show`, or in the state
object.

---

## 2 · THE SHIPPING PLAN — `enable_cloudfront = false`

The plan's summary line sits immediately after the last resource block and immediately
before *Changes to Outputs*. It reads `Plan: 24 to add, 0 to change, 0 to destroy.` at line
843 of `evidence/deploy/terraform-plan-furl.txt`:

```
Plan: 24 to add, 0 to change, 0 to destroy.
```

The JSON agrees mechanically, and the agreement is worth spelling out because the two
artefacts count slightly different things:

* `resource_changes` holds **25 entries — 24 `["create"]` and one `["read"]`.** The read is
  `module.guard[0].data.aws_iam_policy_document.topic`, a data source deferred to apply
  because the topic policy cannot be rendered until the topic ARN exists. **A data read is
  not a created resource**, which is why the summary line says 24 and not 25.
* `planned_values.root_module` holds **zero** resources directly, with two child modules:
  `module.api[0]` (11 managed) and `module.guard[0]` (13 managed **plus 1 data**). A reader
  counting `planned_values` naively gets 11 + 14 = 25 and concludes the guard shipped
  fourteen managed resources. It did not — the fourteenth entry there is the deferred data
  source, and §2.2 shows which of the module's fourteen `resource` blocks is genuinely
  absent.
* `applyable: true`, `complete: true`, `errored: false`.

### 2.1 · Every resource, by type and name

Line numbers are into `evidence/deploy/terraform-plan-furl.txt`.

**`module.api[0]` — eleven, the demo API itself:**

| # | Address | Type | What it is |
|---|---|---|---|
| 1 | `module.api[0].aws_iam_role.this` | `aws_iam_role` | `mainline-demo-api-exec`, the execution role (line 194) |
| 2 | `module.api[0].aws_iam_role_policy.dsn_access` | `aws_iam_role_policy` | `mainline-demo-api-dsn-read` — `ssm:GetParameter` on one parameter ARN plus a conditioned `kms:Decrypt` (236) |
| 3 | `module.api[0].aws_iam_role_policy_attachment.basic_execution` | `aws_iam_role_policy_attachment` | `arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole` (269) |
| 4 | `module.api[0].aws_lambda_function.this` | `aws_lambda_function` | `mainline-demo-api` · `python3.13` · `arm64` · **256 MB** (290) · **14 s** (315) · handler `mainline_demo_api.app.handler` · **`reserved_concurrent_executions = -1`** (296) · Zip |
| 5 | `module.api[0].aws_lambda_function_url.this` | `aws_lambda_function_url` | **`authorization_type = "NONE"`** (351), `invoke_mode = "BUFFERED"` (356) — the demo hostname |
| 6 | `module.api[0].aws_cloudwatch_log_group.this` | `aws_cloudwatch_log_group` | `/aws/lambda/mainline-demo-api`, `retention_in_days = 7` (51) |
| 7 | `module.api[0].aws_cloudwatch_metric_alarm.errors` | `aws_cloudwatch_metric_alarm` | `mainline-demo-api-errors` — `Errors > 0`, `treat_missing_data = "missing"` (128) |
| 8 | `module.api[0].aws_cloudwatch_metric_alarm.throttles` | `aws_cloudwatch_metric_alarm` | `mainline-demo-api-throttles` — `Throttles > 0` over 300 s, `missing` (161) |
| 9 | `module.api[0].aws_cloudwatch_metric_alarm.duration_p99` | `aws_cloudwatch_metric_alarm` | `mainline-demo-api-duration-p99` — p99 `Duration > 13 500` ms (124), below the 14 000 ms timeout by precondition |
| 10 | `module.api[0].aws_cloudwatch_metric_alarm.concurrency` | `aws_cloudwatch_metric_alarm` | `mainline-demo-api-concurrency` — **`ConcurrentExecutions > 8`** (91), **no `dimensions` block**: account-level, not per-function |
| 11 | `module.api[0].aws_cloudwatch_dashboard.this[0]` | `aws_cloudwatch_dashboard` | `mainline-demo-api` (33) |

**`module.guard[0]` — thirteen, the cost guard. This is the block the previous revision of
this page did not know existed.**

| # | Address | Type | What it is |
|---|---|---|---|
| 12 | `module.guard[0].aws_sns_topic.guard` | `aws_sns_topic` | `mainline-demo-api-guard`, display name `MAINLINE demo cost guard` (789) |
| 13 | `module.guard[0].aws_sns_topic_policy.guard` | `aws_sns_topic_policy` | lets CloudWatch alarms and Budgets publish to the topic (817) |
| 14 | `module.guard[0].aws_sns_topic_subscription.responder` | `aws_sns_topic_subscription` | `protocol = "lambda"` — **unconditional**, and the only subscription in the stop path (826) |
| 15 | `module.guard[0].aws_lambda_function.responder` | `aws_lambda_function` | `mainline-demo-api-guard-responder` · `python3.13` · `arm64` · 128 MB · 15 s · handler `cost_guard_responder.handler` (719) |
| 16 | `module.guard[0].aws_lambda_permission.sns_invoke` | `aws_lambda_permission` | `lambda:InvokeFunction` for principal `sns.amazonaws.com` (777) |
| 17 | `module.guard[0].aws_iam_role.responder` | `aws_iam_role` | `mainline-demo-api-guard-responder-exec` (643) |
| 18 | `module.guard[0].aws_iam_role_policy.responder_stop` | `aws_iam_role_policy` | the `PutFunctionConcurrency` grant — the permission that lets the stop happen (685) |
| 19 | `module.guard[0].aws_iam_role_policy_attachment.responder_basic` | `aws_iam_role_policy_attachment` | `AWSLambdaBasicExecutionRole` for the responder (712) |
| 20 | `module.guard[0].aws_cloudwatch_log_group.responder` | `aws_cloudwatch_log_group` | `/aws/lambda/mainline-demo-api-guard-responder`, `retention_in_days = 30` (524) |
| 21 | `module.guard[0].aws_cloudwatch_metric_alarm.invocations_burst` | `aws_cloudwatch_metric_alarm` | **STOPS THE DEMO.** `Invocations` Sum **> 3 000** over a **60 s** period, `evaluation_periods = 1`, `datapoints_to_alarm = 1` (541) |
| 22 | `module.guard[0].aws_cloudwatch_metric_alarm.invocations_hourly` | `aws_cloudwatch_metric_alarm` | **STOPS THE DEMO.** `Invocations` Sum **> 15 000** over a **3 600 s** period (575) |
| 23 | `module.guard[0].aws_cloudwatch_metric_alarm.log_ingestion` | `aws_cloudwatch_metric_alarm` | **STOPS THE DEMO.** `AWS/Logs` `IncomingBytes` Sum **> 16 777 216** B over 300 s (609) |
| 24 | `module.guard[0].aws_budgets_budget.guard` | `aws_budgets_budget` | `mainline-demo-api-guard` — **USD 25.00**, `MONTHLY`, one `ACTUAL` notification at 100 % (461) |

By type across both modules: 2 × `aws_lambda_function`, 1 × `aws_lambda_function_url`,
1 × `aws_lambda_permission`, 2 × `aws_iam_role`, 2 × `aws_iam_role_policy`,
2 × `aws_iam_role_policy_attachment`, 2 × `aws_cloudwatch_log_group`,
7 × `aws_cloudwatch_metric_alarm`, 1 × `aws_cloudwatch_dashboard`, 1 × `aws_sns_topic`,
1 × `aws_sns_topic_policy`, 1 × `aws_sns_topic_subscription`, 1 × `aws_budgets_budget`.
**Twenty-four.**

### 2.2 · Why 24 and not 25 — the fourteenth guard resource, named

`infra/modules/cost-guard/main.tf` declares **fourteen** `resource` blocks, and the shipping
plan gained **thirteen**. An off-by-one that happens to net out is exactly the kind of thing
this repository exists to catch, so the missing one is identified from the artefact rather
than assumed.

Diffing the module's fourteen declared `type.name` pairs against the thirteen that appear in
`resource_changes` under `module.guard[0]` leaves **exactly one** declared-but-not-planned
block and **zero** planned-but-not-declared:

```
DECLARED BUT NOT PLANNED: ['aws_sns_topic_subscription.email']
PLANNED BUT NOT DECLARED: []
```

`aws_sns_topic_subscription.email` is gated on the subscriber list:

```hcl
resource "aws_sns_topic_subscription" "email" {
  for_each = toset(var.notification_emails)
  ...
}
```

`infra/envs/demo/main.tf:649` passes `notification_emails = var.guard_notification_emails`,
and that root variable **defaults to empty**, so the `for_each` expands to zero instances and
the block contributes nothing to the plan. **11 + 14 = 25; 11 + 13 = 24.**

> **A correction to the expectation this check was set up against.** The delta was predicted
> to come from `count = length(var.notification_emails)`. The mechanism in the code is
> `for_each = toset(...)`, not `count = length(...)`. Both yield zero instances at the empty
> default, so the *number* is unaffected — but they are not interchangeable, and the
> difference is worth one sentence: `toset` **de-duplicates**, so with a list of subscribers
> the instance count is the number of *distinct* addresses, not `length()`. The prediction
> was right about the count and wrong about the reason, and the reason is what a reader would
> have to re-derive next time.

**This is a control that is deliberately absent, not one that was forgotten.** An
`aws_sns_topic_subscription` with `protocol = "email"` is created in `PendingConfirmation`;
AWS mails a confirmation link and delivers **nothing** until a human clicks it, and Terraform
reports it created either way and cannot click it. An unconfirmed subscription is a control
that looks present and is not. It gates nothing in the stop path — the responder's
subscription (row 14) is a Lambda and is unconditional — so the only thing an empty list
costs is that **the demo stops without anybody being told**, which is why
`docs/deploy/RUNBOOK.md`'s check step is `kill_switch.sh --status`.

### 2.3 · Which alarms report and which ones stop

The previous revision of this page could say, flatly, that nothing in the plan stopped
anything. **That is no longer true, and the distinction is now inside the plan rather than
outside it.**

* **Row 10 (`-concurrency`) is a tripwire.** It reports; it does not stop. Its threshold of
  8 is *below* the account's measured `ConcurrentExecutions` ceiling of 10 so that it can
  actually breach, and that relationship is enforced at plan time rather than asserted in
  prose — see the precondition in §2.6. Rows 7–9 are likewise reporting alarms.
* **Rows 21–23 stop the demo.** Each publishes to the guard topic (row 12), which invokes
  the responder (row 15) through an unconditional Lambda subscription (row 14), which holds
  `PutFunctionConcurrency` by row 18 and sets the demo function's reserved concurrency to
  **0**. Their own `alarm_description` strings begin `STOPS THE DEMO.`
* **Row 4's `-1` is not a loosening.** `min(20, 10) = 10` both before and after, so the
  physical bound on this function is the same number it always was.

**The stop is an availability action, and that is a trade, not a free win.** Reserved
concurrency 0 stops the demo *for everyone*, not just for whoever tripped it, and the URL is
`authorization_type = NONE` by the founder's explicit choice — so anyone at all can trip it.
It stays stopped until a human runs `scripts/deploy/kill_switch.{sh,ps1} --restore`. That is
the right trade, because an outage is recoverable by one command and an unbounded bill is
not. What bounds spend, and what it costs to bound it, is `docs/deploy/COST-BOUND.md`'s
subject, and this page does not restate it.

### 2.4 · What it would NOT create

* **No `aws_cloudfront_*` resource of any kind.** `resource_changes`, `planned_values` and
  `prior_state` contain zero. The identifier `aws_cloudfront_distribution` *does* appear in
  the JSON's `configuration` block, and in the `relevant_attributes` and `checks` derived
  from it — that block is the parsed HCL of the whole root, including the `count = 0`
  module, and Terraform emits it whether or not the module expands. The test that matters
  is `resource_changes`, and it is empty of CloudFront.
* **No S3 bucket.** No `aws_s3_bucket`, no public-access block, no versioning, no bucket
  policy. The console SPA and the signed EvidenceBundle ship *inside* the Lambda deployment
  package (`MAINLINE_WEB_ROOT = /var/task/web`), so there is no bucket in the request path.
* **No `aws_lambda_permission` *for CloudFront*.** The `cloudfront_invoke` grant is
  `count = 0`; the JSON's `checks` array shows
  `module.api.aws_lambda_permission.cloudfront_invoke` with **`instances: 0`** — absent from
  the plan, not present and inert. `output.cloudfront_invoke_grant_created` is `false`.
  **The plan does contain one `aws_lambda_permission`** — row 16,
  `module.guard[0].aws_lambda_permission.sns_invoke`, which lets SNS invoke the responder.
  The previous revision of this page said "No `aws_lambda_permission`" without qualification,
  which stopped being true the moment the guard was instantiated.
* **No SSM parameter, no KMS key, no Route 53 zone, no ACM certificate, no DynamoDB
  table, no WAF, no Synthetics canary.**
* **No secret of any kind.**
* **No email subscription** — §2.2.

### 2.5 · Outputs this plan would produce

`planned_values.outputs` carries **30** outputs; `output_changes` marks **22** known at plan
time and **8** unknown. (It was 17 / 13 / 4 before the guard; the guard added its own
output surface.)

Known at plan time, scalar values only:

```
api_authorization_type          = "NONE"
api_enabled                     = true
api_function_name               = "mainline-demo-api"
api_ok_actions_armed            = false
aws_account_id                  = "0229REDACTED8246"
aws_region                      = "ap-southeast-1"
cloudfront_invoke_grant_created = false
demo_url_source                 = "module.api[0].function_url (Lambda Function URL)"
distribution_arn                = null
distribution_domain_name        = null
distribution_id                 = null
dsn_parameter_name              = "/mainline/demo/cockroach_dsn"
enable_cloudfront               = false
guard_budget_name               = "mainline-demo-api-guard"
guard_enabled                   = true
guard_guarded_function_arn      = "arn:aws:lambda:ap-southeast-1:0229REDACTED8246:function:mainline-demo-api"
guard_responder_function_name   = "mainline-demo-api-guard-responder"
site_bucket                     = null
```

The remaining four known outputs are structured rather than scalar: `api_alarm_names`,
`api_published_bounds`, `guard_alarm_names` and `guard_thresholds`. **`guard_thresholds` is
the one to read before an apply** — it prints the numbers actually in force, so nothing has
to trust a copy of them in prose.

Known only after apply, **eight**: `demo_url`, `api_function_url`,
`api_function_url_domain`, `api_alarm_arns`, `api_alarm_actions_armed`, `guard_alarm_arns`,
`guard_sns_topic_arn`, and the `deploy_summary` map that embeds several of them — an
AWS-assigned Function URL id and an SNS topic ARN do not exist until the resources do. The
`null`s above do not appear in the human plan's *Changes to Outputs* block, because Terraform
prints only outputs it is setting; they are visible in the JSON, which is the artefact this
paragraph is derived from.

**There is no longer a `phase` output.** An earlier revision of this page quoted one; the
root no longer declares it, and a reader who ran `terraform output phase` would get an error.

**`demo_url` resolves to the Function URL when CloudFront is off.** The plan proves this
without an apply, because `demo_url_source` is a plan-time-known string and it reads
`module.api[0].function_url (Lambda Function URL)`. Its shape is
`https://<id>.lambda-url.ap-southeast-1.on.aws`, with AWS's trailing slash trimmed so that
`<demo_url>/v1/health` cannot become `//v1/health`.

### 2.6 · Every precondition and validation passed

The JSON's `checks` array carries **85 check objects** — 74 `var` validations, 10 `resource`
preconditions and 1 `output_value` precondition. **71 expanded to an instance and all 71
report `"status": "pass"`**; the other 14 report `instances: 0`, which is what a check inside
a `count = 0` module looks like.

The count went 41 → 44 in the 2026-08-13 attribute wave and **44 → 85 when the guard was
instantiated**. The `var` checks now break down as 20 at the root, 28 in `module.api`, 15 in
`module.guard` and 11 in `module.site` (the last group unexpanded).

**The four guard preconditions are the ones worth reading**, because each one refuses an
alarm that could never fire — the failure mode this whole module exists to avoid:

| Guard check | Instances | What it refuses |
|---|---|---|
| `module.guard.aws_cloudwatch_metric_alarm.invocations_burst` | 1 · pass | a burst threshold unreachable at the account's concurrency ceiling and fastest measured invocation |
| `module.guard.aws_cloudwatch_metric_alarm.invocations_hourly` | 1 · pass | an hourly threshold that the burst alarm would always beat to the stop |
| `module.guard.aws_cloudwatch_metric_alarm.log_ingestion` | 1 · pass | a log-bytes threshold below what normal traffic already emits |
| `module.guard.aws_budgets_budget.guard` | 1 · pass | a budget limit inconsistent with the cap the demo is authorised to spend |

The three checks the 2026-08-13 wave installed are still present and still pass:

| Check | Kind | What it refuses |
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

All fourteen zero-instance checks are `module.site.*` (eleven `var`, two `resource`) plus
`module.api.aws_lambda_permission.cloudfront_invoke`. **A count-gated module out of the plan
is visible in the artefact, mechanically, and does not have to be taken on trust.**

### 2.7 · What the plan cost to produce

**Twelve data-source reads at plan time**, all read-only, all visible in the first
twenty-four lines of the human plan — six of them added by the guard:

| Data source | Cost |
|---|---|
| `data.aws_caller_identity.current` | `sts:GetCallerIdentity` |
| `module.api[0].data.aws_caller_identity.current` | `sts:GetCallerIdentity` |
| `module.guard[0].data.aws_caller_identity.current` | `sts:GetCallerIdentity` |
| `module.api[0].data.aws_region.current`, `.aws_partition.current` | provider metadata, resolved locally |
| `module.guard[0].data.aws_region.current`, `.aws_partition.current` | provider metadata, resolved locally |
| `module.api[0].data.aws_iam_policy_document.assume_role`, `.dsn_access` | rendered locally by the provider, no API call |
| `module.guard[0].data.aws_iam_policy_document.responder_assume`, `.responder_stop` | rendered locally by the provider, no API call |
| `module.guard[0].data.archive_file.responder` | zips the responder source **locally** — no API call, and the reason `hashicorp/archive` is a provider dependency |

**Three `sts:GetCallerIdentity` calls and nothing else that touches AWS. No write, no state
object, no lock.**

One further data source is **deferred to apply** and appears in `resource_changes` as the
single `["read"]` entry: `module.guard[0].data.aws_iam_policy_document.topic`, the SNS topic
policy, which cannot be rendered until the topic ARN exists. It is why `resource_changes` has
25 entries for a 24-resource plan (§2).

---

## 3 · THE UPGRADE PLAN — `enable_cloudfront = true`

### 3.1 · This artefact was a day stale, and its old figure must not be carried forward

Until this wave, `evidence/deploy/terraform-plan-cloudfront.txt` was dated 2026-08-13 13:44
while the FURL artefacts were regenerated at 2026-08-14 01:57. **The CloudFront file
predated guard instantiation entirely.** Its recorded count of twenty-two described a tree
that no longer existed, and this page quoted it as though it were current.

It has been **regenerated, not re-quoted** — and it came back at the arithmetic the guard
predicts rather than at the old number, which is the outcome that would have been a finding
had it gone the other way:

| | Stale artefact (Aug 13 13:44) | Regenerated (Aug 14 04:42) |
|---|---:|---:|
| upgrade plan | 22 | **35** |
| `module.guard[0]` | absent | 13 |

`22 + 13 = 35`, and the plan says 35. **The guard reaches this configuration too** — it is
gated on `enable_api`, not on `enable_cloudfront`, so turning CloudFront on does not turn
the cost guard off. Had the regenerated file come back at 22, that would have meant the
guard was *not* reaching this shape, and it would have been recorded here as an open defect
rather than accepted.

### 3.2 · The plan, as regenerated

At line 1219 of `evidence/deploy/terraform-plan-cloudfront.txt`, the summary line reads:

```
Plan: 35 to add, 0 to change, 0 to destroy.
```

> The line number is written *before* the quoted summary here, and *after* it in §2,
> deliberately.
> `tests/deploy/test_cost_model.py::test_line_references_into_the_plan_evidence_point_at_the_plan_line`
> matches the phrase `Plan: N to add … at line M` and checks `M` against **the FURL
> artefact**, which is the only plan evidence it knows about. Written in that order, a
> citation into the *CloudFront* artefact would be checked against the wrong file and would
> fail for being right. The control is doing its job; it simply has one artefact in scope,
> and this is the phrasing that keeps a true citation out of its way rather than widening
> it.

**The plan succeeds.** It was not refused by a data source and there is no refusal to
record: every data source it reads is available to this identity, and the account's
inability to *create* a distribution is an apply-time refusal from the CloudFront API, not
a plan-time one. That distinction is the reason this file exists — the configuration is
provably correct and provably blocked by something outside it.

**35 = 12 in `module.api[0]` + 13 in `module.guard[0]` + 10 in `module.site[0]`.** The
`module.api[0]` count rises from 11 to 12 because the `cloudfront_invoke` grant expands here;
the guard's thirteen are exactly the rows 12–24 of §2.1, unchanged. The ten new ones:

| # | Address | Type |
|---|---|---|
| — | `module.api[0].aws_lambda_permission.cloudfront_invoke[0]` | `aws_lambda_permission` |
| 1 | `module.site[0].aws_s3_bucket.site` | `aws_s3_bucket` |
| 2 | `module.site[0].aws_s3_bucket_public_access_block.site` | `aws_s3_bucket_public_access_block` |
| 3 | `module.site[0].aws_s3_bucket_ownership_controls.site` | `aws_s3_bucket_ownership_controls` |
| 4 | `module.site[0].aws_s3_bucket_versioning.site` | `aws_s3_bucket_versioning` |
| 5 | `module.site[0].aws_s3_bucket_server_side_encryption_configuration.site` | `aws_s3_bucket_server_side_encryption_configuration` |
| 6 | `module.site[0].aws_s3_bucket_lifecycle_configuration.site[0]` | `aws_s3_bucket_lifecycle_configuration` |
| 7 | `module.site[0].aws_s3_bucket_policy.site` | `aws_s3_bucket_policy` |
| 8 | `module.site[0].aws_cloudfront_origin_access_control.s3` | `aws_cloudfront_origin_access_control` |
| 9 | `module.site[0].aws_cloudfront_origin_access_control.api[0]` | `aws_cloudfront_origin_access_control` |
| 10 | `module.site[0].aws_cloudfront_distribution.site` | `aws_cloudfront_distribution` |

`resource_changes` holds **37 entries — 35 creates and two `["read"]`**:
`module.guard[0].data.aws_iam_policy_document.topic` (as in §2) and
`module.site[0].data.aws_iam_policy_document.site`, the bucket policy, which cannot be
rendered until the distribution ARN exists. **A data read is not a created resource and is
not counted in the 35.**

The JSON also carries **85 check objects — the same 85 as the FURL plan, but with none of
them unexpanded**: 81 instances `pass` and 4 report `unknown`, which is what a precondition
reading an attribute that is not known until apply looks like. Nothing fails.

The `module.api[0]` half of this plan carries **the same attribute values as §2** —
`reserved_concurrent_executions = -1`, 256 MB, 14 s, the `-concurrency` alarm at
`threshold = 8` with no `dimensions` block, and `treat_missing_data = "missing"` on all four
API alarms. The two shapes do not disagree about the Lambda.

**And this artefact carried a stale permit id until 2026-08-13.** Its
`MAINLINE_DEMO_PERMIT_ID` and `MAINLINE_SCENARIO_PERMIT_ID` (now at lines 325 and 334; the
FURL plan carries the same pair at lines 323 and 332) once read
`077a6fdd-2167-559c-b2ff-8e3c8352504d` — the uuid5 derivation nothing has ever seeded —
where the FURL artefact had already been regenerated to
`dec0de00-0006-4000-8000-000000000001`, the id the demo cluster actually holds. Two
committed plans of the same module disagreed about the id the demo guard is armed at, and
only one of them had been refreshed. They agree now.

Outputs flip in exactly the places the design says they should:

```
api_authorization_type          = "AWS_IAM"      (was "NONE")
cloudfront_invoke_grant_created = true           (was false)
demo_url_source                 = "module.site[0].distribution_domain_name (CloudFront)"
site_bucket                     = "mainline-demo-site-0229REDACTED8246"
guard_enabled                   = true           (unchanged — the guard is not CloudFront-gated)
```

`output_changes` marks **19** known at plan time and **11** unknown, against 22 / 8 for the
FURL shape: the distribution's id, ARN and domain name are all apply-time values.

**One variable moves the hostname and the authorisation model together.** That is
`main.tf`'s `url_authorization_type = var.enable_cloudfront ? "AWS_IAM" : "NONE"`, and it
is the whole architectural switch.

### 3.3 · What this plan would run into, at apply time, today

What AWS refused on 2026-08-10:

```
Error: creating CloudFront Distribution: operation error CloudFront:
CreateDistributionWithTags, https response error StatusCode: 403,
RequestID: 3e63e30d-8c5b-441b-a01b-b70085eba504, AccessDenied:
Your account must be verified before you can add new CloudFront resources.
To verify your account, please contact AWS Support and include this error message.
```

An account-level verification hold on **new** CloudFront resources — the account already
carries one distribution from an unrelated project, created 2026-04-16, so the service
itself is not denied. Only AWS Support can lift it.

**Do not apply this plan** until they have. `aws_cloudfront_distribution.site` is the
resource that is refused, and it is one of the last things the graph reaches: everything in
`module.api[0]` and `module.guard[0]`, the bucket, and the S3/OAC resources that do not
depend on the distribution ARN would all be created first. The apply would then fail,
leaving a **partial stack** — which is exactly what happened on 2026-08-10.
`scripts/deploy/teardown.sh` is the way back out.

---

## 4 · What the apply would cost

**Two questions live here and they have different answers. Keep them apart.**

### 4.1 · What the created resources cost to exist, at demo traffic

Recurring, per month, at demo traffic (a judging round is a few hundred requests):

| Line | Basis | `enable_cloudfront = false` | `= true` |
|---|---|---:|---:|
| Lambda invocations + duration | free tier 1 M req + 400 000 GB-s; **256 MB** × 300 ms × 10 k req = **768 GB-s** | 0.00 | 0.00 |
| Lambda Function URL | no charge beyond the invocation | 0.00 | 0.00 |
| CloudWatch Logs | two groups, 7- and 30-day retention, far under the 5 GB free ingest | 0.00 | 0.00 |
| CloudWatch alarms | **7** alarms (4 API + 3 guard); first 10 standard alarms are free | 0.00 | 0.00 |
| CloudWatch dashboard | first 3 dashboards free | 0.00 | 0.00 |
| IAM roles / policies / attachments | never billed | 0.00 | 0.00 |
| **Guard responder Lambda** | invoked only when an alarm fires; 128 MB × 15 s worst case, inside the same free tier | 0.00 | 0.00 |
| **SNS topic + subscriptions** | first 1 M publishes free; the demo publishes only on an alarm transition | 0.00 | 0.00 |
| **AWS Budgets** | 1 budget; the first two budgets are free | 0.00 | 0.00 |
| S3 site bucket | **not created** / one small versioned SPA build | — | ~0.01 |
| CloudFront | **not created** / free tier 1 TB egress + 10 M req | — | 0.00 |
| **Total created by this plan** | | **0.00** | **~0.01** |

**The guard is free at demo traffic and that is the point of its shape** — it costs nothing
to have armed and only does work when something has already gone wrong. Note that the
alarm count is now 7 of the 10 free standard alarms; an eighth, ninth and tenth are free,
and an eleventh would begin to bill.

Outside this plan and named for completeness: the Terraform state bucket (~USD 0.01/month,
created by `bootstrap_state.sh`, not by this root), the SSM Parameter Store SecureString
(Standard tier, USD 0.00, written by the deploy script), Bedrock (~USD 0.01/month), and
CockroachDB Cloud Basic (inside the free allowance, `spend_limit` is the hard ceiling).
Whole-system total at demo traffic ≈ **USD 0.02–0.03/month**.

### 4.2 · What the demo can be made to spend, which is a different number

**Nothing in §4.1 is a bound.** Every line there is a *usage-metered free tier*, and a free
tier bounds nothing once the usage leaves the tier. The Function URL is
`authorization_type = NONE`.

**What limits the rate has changed since this section was first written, and the change is
the whole reason the resource count moved.** There are now two limiters, not one:

* the account's `ConcurrentExecutions` ceiling of **10** — an AWS default nobody chose, and
  `Adjustable: true`. It bounds the *rate*, not the *total*;
* the **cost guard** (rows 21–24), which bounds the *total* by stopping the function at
  reserved concurrency 0 when invocations, or log bytes, or the monthly budget cross a
  declared threshold.

The guard is not instantaneous, and the gap between "threshold crossed" and "stop landed" is
billable. **That residual is quantified in `docs/deploy/COST-BOUND.md`, not here** — this
page counts resources, and pricing them is a different document's job.

Two figures in the sentence above have moved since it was written, both in the safer
direction, and neither changes the conclusion:

* ~~the largest single object the origin will emit is a 1.55 MB source map~~ — **the source
  maps are stripped by default in both builders and there are 0 in the artefact.** The
  largest object the origin will emit is now **124,127 B** (the gzip sibling); the 433,396 B
  identity bundle is refused by the 139,264 B response ceiling.
* the *rate* limiter is unchanged, and that is the point: **bytes per request fell 12.5× and
  the bill did not**, because a smaller object serves faster and the request rate rises to
  refill the same concurrency ceiling. [`COST-BOUND.md` §0.1](COST-BOUND.md) prices that
  self-limiting property layer by layer.

**`docs/deploy/COST-BOUND.md` carries that arithmetic, its inputs and its levers, and it is
the document to read before authorising an apply.** It is not restated here, for one
reason: an earlier revision of this documentation set rounded the worst case to *"a dollar"*,
which was wrong by four to five orders of magnitude, and it was wrong precisely because a
free-tier table like §4.1 was allowed to answer a question it was never about.

The one line item in §4.1 with no natural ceiling is a CloudWatch log group set to never
expire. `log_retention_days` is 7 and its validation refuses `0`.

---

## 5 · The four configurations

The two committed shapes were regenerated on **2026-08-14** with Terraform v1.14.8 +
`hashicorp/aws v6.58.0` and real credentials, and each has an artefact in `evidence/`. The
other two rows were measured on **2026-08-13** and **their artefacts were never committed**,
so they are marked as such rather than presented as equally supported:

| `enable_cloudfront` | `enable_api` | Result | Artefact |
|---|---|---|---|
| `false` **(default)** | `true` | `Plan: 24 to add, 0 to change, 0 to destroy` — **ships** | `terraform-plan-furl.{txt,json}` |
| `true` | `true` | `Plan: 35 to add, 0 to change, 0 to destroy` | `terraform-plan-cloudfront.{txt,json}` |
| `true` | `false` | `Plan: 9 to add, 0 to change, 0 to destroy` — site with no API | **none — measured 2026-08-13, not re-measured since the guard landed** |
| `false` | `false` | **Refused at plan.** `Error: Module output value precondition failed` on `output "demo_url"`, `outputs.tf` line 61 | none — a refusal produces no plan |

**The third row is the one to distrust.** `module "guard"` is gated
`count = var.enable_api ? 1 : 0`, so at `enable_api = false` the guard contributes nothing
and the figure *should* be unchanged — but that is an argument, not a measurement, and the
row has not been re-run since the guard landed. It is carried here with its provenance
visible rather than silently refreshed to whatever arithmetic suggests.

The fourth row is intentional. With both switches off the root creates nothing, so
`demo_url` has no source; returning `""` would be a demo URL nobody can visit, presented as
if it were one. The message names the fix, in full:

```
enable_api and enable_cloudfront are both false, so this root creates no
resource that can serve a URL and demo_url has no source. Under decision D1
(docs/leads/ship-final.md 1.4) the Lambda Function URL IS the demo hostname:
set enable_api = true. …
```

Also clean, re-run on 2026-08-13: `terraform fmt -check -recursive infra/` exits 0 with no
output, and `terraform validate` prints `Success! The configuration is valid.` Both plans
regenerated on 2026-08-14 report `applyable: true`, `complete: true`, `errored: false`, so
`validate` cannot have regressed between them.

---

## 6 · The review checklist, for the orchestrator and the founder

Before any `terraform apply`:

1. **The plan file is the one you are applying.** Re-run
   `scripts/deploy/plan_repro.sh` and confirm `Plan: 24 to add`. A plan older than the code
   is not evidence — **and this page exists because that stopped being true twice**: once
   when attribute values drifted, and once when the count itself moved from 11 to 24 and
   this page went on saying it had not.
2. **`authorization_type` is `NONE` on purpose, and the list of what bounds it is no longer
   as short as it was.** The Function URL is public. What bounds it is **not**
   authentication, and — since 2026-08-13 — it is **not** `reserved_concurrent_executions`
   either: that is `-1`, it was never appliable at `20`, and `min(20, 10) = 10` means it
   never changed the physical bound. What bounds the demo is the **account's
   `ConcurrentExecutions` ceiling of 10** (measured, `Adjustable: true` — *do not request an
   increase without reading `docs/deploy/COST-BOUND.md`*), the handler's single rolled-back
   transaction (which bounds database *state*, not spend), the CockroachDB Basic
   `spend_limit` (the database side only), and — **new in this plan** — the **cost guard**,
   which is the first control in this stack that actually *stops* rather than reports. The
   `-concurrency` alarm at 8 remains a tripwire. `infra/modules/demo-api/README.md` states
   the exposure plainly rather than calling a public URL private.
3. **Twenty-four resources, all prefixed `mainline-demo-`.**
   `scripts/deploy/teardown.sh` keys its refusal on that prefix and on `project=mainline`,
   which `default_tags` applies to every taggable resource in the plan. **Confirm teardown
   covers the thirteen guard resources too** — they carry `component = cost-guard` where the
   API's carry `component = demo-api`, and both carry `project = mainline`.
4. **Nothing is destroyed and nothing is changed.** `0 to change, 0 to destroy` in both
   plans. Nothing pre-existing in an account holding four unrelated live projects is
   touched.
5. **The SSM SecureString must exist before the apply**, or the function starts and fails
   on its first database call. The role is granted `ssm:GetParameter` on
   `/mainline/demo/cockroach_dsn` and nothing else. `docs/deploy/PRE-APPLY.md` lists this
   and the state bucket in order, with the read-only command that proves each — **and
   records that neither exists in this account today.**
6. **Know that the guard can stop the demo, and know how to restart it.** Rows 21–23 set
   reserved concurrency to 0 for everyone, and `guard_notification_emails` is **empty by
   default**, so nobody is told. `scripts/deploy/kill_switch.{sh,ps1} --status` reports and
   `--restore` reverses it. Decide before the apply whether you want an email subscriber.
7. **Do not apply the CloudFront plan** until AWS Support confirms the verification hold is
   lifted. It would create most of the stack and fail on the distribution, leaving a partial
   deployment.
8. **Read `docs/deploy/COST-BOUND.md` before authorising.** §4.2 says why: the free-tier
   table in §4.1 answers a question about existence, not about abuse, and the two numbers
   are four orders of magnitude apart.

---

## 7 · Provenance

Everything on this page is derived from the **four** committed artefacts and nothing else:

* `evidence/deploy/terraform-plan-furl.txt` — §2's counts, resource list, line citations
  (33, 42, 51, 65, 91, 95, 124, 128, 161, 194, 236, 269, 276, 290, 296, 315, 323, 332, 349,
  351, 356, 461, 518, 524, 541, 575, 609, 643, 685, 712, 719, 777, 789, 817, 826) and the
  `Plan:` line at 843
* `evidence/deploy/terraform-plan-furl.json` — §2's `resource_changes`, `checks`,
  `planned_values`, `output_changes`, `sensitive_values` and `timestamp` claims, and the
  §2.2 declared-vs-planned diff
* `evidence/deploy/terraform-plan-cloudfront.txt` — §3's `Plan:` line at 1219 and the permit
  ids at lines 325 and 334
* `evidence/deploy/terraform-plan-cloudfront.json` — §3's `resource_changes`, per-module
  create counts, `checks` and `output_changes`

§2.2 additionally reads `infra/modules/cost-guard/main.tf` (the fourteen `resource` blocks
and the `for_each` on `aws_sns_topic_subscription.email`), `infra/modules/cost-guard/variables.tf`
and `infra/envs/demo/main.tf:632,649` — those are **source, not evidence**, and the diff
against the plan JSON is what turns them into a checked claim rather than a reading.

Four things on this page are **not** from those artefacts and say so where they appear: rows
three and four of the four-configuration table in §5 and the `fmt`/`validate` results, which
are transcripts of commands run on 2026-08-13 and not committed as files; the precondition
refusal quoted in §2.6, which was planned from a throwaway root **outside this repository**
so that no tracked file had to be edited to produce a negative control; the 403 transcript in
§3.3, which is quoted from `docs/deploy/RUNBOOK.md` and records the 2026-08-10 apply; and the
apply-ordering claim in §3.3, which is an argument from the dependency graph and not a
transcript of a failed apply at this resource count.

The cost basis in §4.1 is AWS's published free-tier allowances plus the usage model in
`docs/leads/ship-final.md` §2.1; it is an **estimate**, and it is the only estimate on this
page. §4.2 is not an estimate this page makes — it points at the document that makes it.

### 7.1 · What is still false elsewhere, and is not this page's to fix

The shipping count is quoted in several documents this page does not own. **As of this
revision they still say eleven**, and correcting this page did not correct them:

| Document | Status |
|---|---|
| `docs/deploy/JUDGE-PACK.md` | stale — two occurrences |
| `docs/deploy/OBSERVABILITY.md` | stale — one occurrence, **and no worker in this wave owns this file** |
| `docs/submission/DEVPOST.md`, `docs/submission/JUDGE-START.md`, `docs/STATE-OF-THE-BUILD.md`, `scripts/submission/check_submission_ready.py` | to be corrected alongside `JUDGE-PACK.md` |

`tests/deploy/test_cost_model.py::test_the_shipping_plan_count_in_the_docs_matches_the_plan_evidence`
reads all of them and **stays red until every one is corrected**. This page being right is
necessary and not sufficient.
