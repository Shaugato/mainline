<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: CC-BY-4.0
-->

# DEPLOY-SAFETY — W8's verification: the plan the founder re-authorises is the plan that will run

**Worker:** W8 (regenerate the plan, reconcile every consumer) · **Date:** 2026-08-13
**Standing order obeyed:** `terraform apply` was **never** run — not with `-target`, not to
check. `init`, `validate`, `plan`, `show` and read-only AWS calls only.

---

## 0 · The one page for the orchestrator

### What the founder is being asked to re-authorise

An apply of **eleven resources**, all inside `module.api`, all prefixed `mainline-demo-`,
in `ap-southeast-1`, from
[`evidence/deploy/terraform-plan-furl.txt`](../../evidence/deploy/terraform-plan-furl.txt):

```
Plan: 11 to add, 0 to change, 0 to destroy.
```

**The count is the same count he saw before. Five attribute values inside it are not.**

### What changed since he last saw it

| # | Attribute | Was | Is | What it does to his exposure |
|---|---|---|---|---|
| 1 | `aws_lambda_function.reserved_concurrent_executions` | `20` | **`-1`** | **Nothing.** `min(20, 10) = 10`; the account ceiling already bound this function at 10. What changes is that the apply can now *complete* — `PutFunctionConcurrency(20)` is refused on an account whose ceiling is 10, and it is call six of eleven, so the old plan died with five resources already created |
| 2 | `-concurrency` alarm `threshold` | `20` | **`8`** | **Improves it.** An alarm at 20 above a metric ceiling of 10 could never breach. At 8 it can. It is still a tripwire — it reports, it does not stop |
| 3 | `-concurrency` alarm `dimensions` | `{ FunctionName = "mainline-demo-api" }` | **absent** | **Improves it.** At `-1` Lambda does not dependably publish the per-function `ConcurrentExecutions` metric; the account aggregate is the one that exists. `AccountUsage.FunctionCount = 0` in this region, so the aggregate *is* this function — and the alarm's own description says so, and says when that stops being true |
| 4 | `treat_missing_data`, **all four** alarms | `notBreaching` | **`missing`** | **Improves it.** `notBreaching` showed four green alarms on an idle demo, where green meant "nobody called this function" |
| 5 | `lifecycle.precondition` on the `-concurrency` alarm | absent | **present** | **Improves it.** A threshold at or above the ceiling is now refused *at plan time*, with the measured value named. Verified by negative control in §5 |

Plus one correction that is not an attribute: the **CloudFront** plan artefact was still
recording the pre-fix `scenario_permit_id` (`077a6fdd-…`). It now records
`dec0de00-0006-4000-8000-000000000001`, the id the demo cluster actually holds. §4.

### The honest summary in three sentences

**Nothing in this wave loosened anything.** One change (`-1`) removes a request AWS would
have refused, and the physical bound is identical before and after it. Four changes convert
controls that *looked* present into controls that can actually fire.

**Nothing in this wave bounded the cost either.** The plan still creates a Function URL with
`authorization_type = NONE`, and the only real limiter on request rate is the account's
`ConcurrentExecutions` ceiling of **10** — an AWS default nobody chose, and
`Adjustable: true`. `docs/deploy/COST-BOUND.md` is the document that costs that, and it is
the one to read before authorising.

**The apply still cannot succeed today, for reasons outside the plan.** Two preconditions do
not exist in the account: the SSM SecureString and the Terraform state bucket. §6.

---

## 1 · What was regenerated, and from what

Three artefacts, from the working tree **after** W1, W2 and W3 landed:

| Artefact | Shape | Lines | Bytes | SHA-256 |
|---|---|---:|---:|---|
| `evidence/deploy/terraform-plan-furl.txt` | `enable_cloudfront = false` | 373 | 18 771 | `c56203b2826c499549fca90ecb5dd6a561b1d04a39b15f08c09b6ad461fe1493` |
| `evidence/deploy/terraform-plan-furl.json` | same plan, `show -json` | 1 | 148 082 | `1de80520a7f202b485c89facbacd031bf40e9a6f824d195b568aebd172a039d6` |
| `evidence/deploy/terraform-plan-cloudfront.txt` | `enable_cloudfront = true` | 752 | 33 362 | `fac4727cf46b830ddd5b6642987c9487b2c4a75e5a2409a6664b0c1adaadc773` |

Terraform **v1.14.8**, `hashicorp/aws` **v6.58.0**, `AWS_PROFILE=mainline-dev`,
`ap-southeast-1`. The JSON's own `timestamp` is `2026-08-13T03:42:22Z`.

The recipe is recorded in full in
[`docs/deploy/terraform-plan.md`](../deploy/terraform-plan.md) §1. Two facts about it belong
here as well:

* **`terraform init -backend=false` is not sufficient on this tree.** `backend.tf` declares
  S3, and after `-backend=false` a `plan` refuses with *"Changes to backend configurations
  require reinitialization"*. A throwaway `backend_override.tf` pointing at a **scratch path
  outside the repository**, plus `init -reconfigure`, is what works.
* **`backend_override.tf` is not in the tree, and never was committed.** It was written,
  used and deleted; `infra/envs/demo` holds its seven files and nothing else. The plan binary
  (`tfplan-furl.binary`) was deleted too, and the `.terraform/terraform.tfstate` backend
  marker was removed afterwards, so `terraform plan` in that directory now answers
  *"Backend initialization required … Initial configuration of the requested backend
  \"s3\""* — the honest pre-state, which forces the next operator to init deliberately.

**The scratch state path was empty after every run.** A `plan` writes no state. No S3 object
was created, read, written or locked.

---

## 2 · Before → after, every attribute this wave moved

Diffed against the artefacts as committed at HEAD (line-ending normalised, so the diff is
content only).

### 2.1 · `aws_lambda_function.this` — `evidence/deploy/terraform-plan-furl.txt:279`

```diff
-      + reserved_concurrent_executions = 20
+      + reserved_concurrent_executions = -1
```

Measured today, independently of the lead's numbers, under `AWS_PROFILE=mainline-dev`:

```
aws lambda get-account-settings --region ap-southeast-1
  AccountLimit.ConcurrentExecutions            10
  AccountLimit.UnreservedConcurrentExecutions  10
  AccountUsage.FunctionCount                    0

aws lambda get-account-settings --region ap-southeast-2
  AccountLimit.ConcurrentExecutions            10
  AccountLimit.UnreservedConcurrentExecutions  10
  AccountUsage.FunctionCount                    1     (an unrelated project — DO NOT TOUCH)

aws service-quotas get-service-quota --service-code lambda --quota-code L-B99A9384 \
    --region ap-southeast-1
  QuotaName "Concurrent executions"   Value 10.0   Adjustable true
```

`min(20, 10) = 10`. **The ceiling is the same number before and after this line changed.**

### 2.2 · `aws_cloudwatch_metric_alarm.concurrency` — `…furl.txt:52-78`

```diff
-      + alarm_description  = "Abuse tripwire: more than 20 concurrent executions. …"
+      + alarm_description  = "Abuse tripwire: more than 8 concurrent Lambda executions in
+                              ap-southeast-1, against a measured account ceiling of 10. …
+                              ACCOUNT-LEVEL, NOT PER-FUNCTION: no FunctionName dimension …
+                              If a second function ever lands in ap-southeast-1, this
+                              becomes a genuine account aggregate and must be revisited."
-      + dimensions         = {
-          + "FunctionName" = "mainline-demo-api"
-        }
-      + threshold          = 20
-      + treat_missing_data = "notBreaching"
+      + threshold          = 8
+      + treat_missing_data = "missing"
```

The removal of `dimensions` is the **only** structural change in the whole plan: it is why
the FURL artefact is three lines shorter than it was, and it is the source of the −3 line
shift that §5 reconciles.

### 2.3 · `aws_cloudwatch_metric_alarm.throttles` — `…furl.txt:145-174`

```diff
-      + alarm_description  = "The reserved-concurrency cap is refusing invocations. Either
-                              the demo is under more load than a judging session produces,
-                              or reserved_concurrent_executions is set too low. …"
+      + alarm_description  = "Lambda is refusing invocations: the concurrency ceiling is
+                              biting. At reserved_concurrent_executions = -1 there is no
+                              per-function reservation, so this means the ACCOUNT ceiling
+                              of 10 in ap-southeast-1 was reached - do not go looking for a
+                              per-function cap to raise. …"
-      + treat_missing_data = "notBreaching"
+      + treat_missing_data = "missing"
```

The old text would have sent an operator hunting for a per-function cap that no longer
exists. That is the class of defect this whole wave is about.

### 2.4 · `errors` and `duration_p99` — `…furl.txt:113-142`, `…furl.txt:81-110`

```diff
-      + treat_missing_data = "notBreaching"
+      + treat_missing_data = "missing"
```

Nothing else on either alarm moved. `duration_p99` keeps `threshold = 12000` under the
15 000 ms timeout, still enforced by the precondition that invented the idiom.

### 2.5 · Plan-time guards — `evidence/deploy/terraform-plan-furl.json#/checks`

**41 check objects → 44.** No check was removed. The three additions, all reporting
`"status": "pass"`:

| New check | Kind | Refuses |
|---|---|---|
| `var.lambda_reserved_concurrency` | `var` | any value outside `-1` or `0…1000` at the root |
| `module.api.var.account_concurrency_ceiling` | `var` | a ceiling below 1 |
| `module.api.aws_cloudwatch_metric_alarm.concurrency` | `resource` | `concurrency_alarm_threshold >= account_concurrency_ceiling` |

Across all 44 objects: **30 instances, every one `pass`**; the other 14 report
`instances: 0`, which is what a check inside a `count = 0` module looks like.
`applyable: true`, `complete: true`, `errored: false`.

---

## 3 · The resource count did not move — both shapes

```
evidence/deploy/terraform-plan-furl.txt:336        Plan: 11 to add, 0 to change, 0 to destroy.
evidence/deploy/terraform-plan-cloudfront.txt:713  Plan: 22 to add, 0 to change, 0 to destroy.
```

Mechanically, from the JSON: `resource_changes` has **11 entries, every one `["create"]`**,
`planned_values.root_module` holds zero resources directly and one child module
(`module.api[0]`), and `aws_cloudfront` appears in **no** `resource_changes` entry. The
eleven addresses are byte-identical to the eleven the previous artefact carried.

The two other configurations, re-measured today for completeness:

| `enable_cloudfront` | `enable_api` | Result |
|---|---|---|
| `true` | `false` | `Plan: 9 to add, 0 to change, 0 to destroy` |
| `false` | `false` | **Refused at plan** — `Error: Module output value precondition failed` on `output "demo_url"`, `infra/envs/demo/outputs.tf:61` |

`terraform validate` → `Success! The configuration is valid.`
`terraform fmt -check -recursive infra/` → exit 0, no output.

**Nobody added a resource.** The five documents that quote `Plan: 11 to add, 0 to change,
0 to destroy` verbatim — `docs/deploy/JUDGE-PACK.md`, `docs/submission/DEVPOST.md`,
`docs/submission/JUDGE-START.md`, `docs/STATE-OF-THE-BUILD.md` and
`scripts/submission/check_submission_ready.py` — are **not** touched by this wave and their
quoted string still holds.

---

## 4 · Masking, verified

**One transformation, applied mechanically:** the twelve-digit AWS account id → the literal
`0229REDACTED8246`, the repository convention established by commit `1d41442` (84
occurrences across 13 files). Applied 6 times in the FURL plan, 20 in its JSON, 13 in the
CloudFront plan.

| Assertion | furl.txt | furl.json | cloudfront.txt |
|---|---:|---:|---:|
| occurrences of the real twelve digits | **0** | **0** | **0** |
| occurrences of `000000000000` | **0** | **0** | **0** |
| occurrences of `0229REDACTED8246` | 6 | 20 | 13 |
| occurrences of `postgresql://`, `password`, `AKIA`/`ASIA`+16, `BEGIN PRIVATE` | 0 | 0 | 0 |
| the word `sensitive`, any case | 0 | 99 | 0 |
| …of which `"sensitive": true` | 0 | **0** | 0 |

`scripts/aws/verify_evidence.py` passes `SEC-ACCOUNT-ID`, `SEC-ARN-ACCOUNT`,
`SEC-DSN-PASSWORD`, `SEC-ACCESS-KEY` and `SEC-CENSUS-NOTE` over all three files as
committed. **No checker was relaxed to get there** — the resolution recorded in
`docs/CI-STATE.md` for the twelve-identical-digits disagreement is to remove the digits, not
to soften either reader, and that is what was done.

The three twelve-digit runs a naive `\d{12}` scan still finds are the last group of the demo
permit UUID `dec0de00-0006-4000-8000-000000000001`. A UUID is not an account.

### 4.1 · The stale permit id in the CloudFront artefact — closed

`evidence/deploy/permit-id-agreement.json:240` recorded, as an open finding owned by nobody
in that wave:

> `evidence/deploy/terraform-plan-cloudfront.txt:311,313` still carry
> `077a6fdd-2167-559c-b2ff-8e3c8352504d`

That was true at HEAD. **Two committed plans of the same module disagreed about the id the
demo guard is armed at**, because only the FURL artefact had been regenerated after the
permit-id fix. Both now read `dec0de00-0006-4000-8000-000000000001`, at
`terraform-plan-cloudfront.txt:308,310` and `terraform-plan-furl.txt:305,307`. The finding
is closed by regeneration, not by editing the artefact.

---

## 5 · Consumers reconciled

### 5.1 · Owned, and done

**`docs/deploy/terraform-plan.md`** — rewritten from the regenerated artefacts. Its
line-count/byte/SHA-256 table (§1) is recomputed and now ships with the one-command recipe
that re-derives it, because **that table had been wrong since commit `1d41442`**: masking
rewrote the artefacts' bytes and nobody updated the hashes, so a reader who ran `sha256sum`
got three mismatches and no explanation. Every line citation in the page was re-anchored
(77, 279, 326, 336 in the FURL plan; 305/307/308/310 for the permit ids; 713 in the
CloudFront plan), and every claim about the JSON (`checks`, `resource_changes`,
`output_changes`, `sensitive_values`) was re-derived. §4 was split into "what the created
resources cost to exist" and "what the demo can be made to spend", and §6's checklist no
longer sells `reserved_concurrent_executions` as a bound.

**`scripts/submission/capture_tool_evidence.py`** — three fixes:

| Row | Was | Now | Why |
|---|---|---|---|
| `aws_lambda` anchor | `infra/modules/demo-api/main.tf:310` | `…:333` | W3's rewrite slid `:310` onto a prose comment. `:333` is `authorization_type = var.url_authorization_type` — the decision the row turns on |
| `aws_ssm_parameter_store` anchor | `infra/modules/demo-api/main.tf:192` | `…:215` | `:192` had slid onto a bare `}`. `:215` is `actions = ["ssm:GetParameter"]` |
| `aws_lambda` `how` prose | *"reserved_concurrent_executions caps the bill rather than reporting it … the concurrency alarm is the tripwire"* | the account ceiling of 10 named as the only real limiter, the reservation named as **not** a control, the alarm named as a tripwire that reports and does not stop | **the old sentence is now false, and it was misleading before it was false** |

All **26** anchors across `CRDB_ROWS` and `AWS_ROWS` resolve to a real line **and** their
declared subject. The three in-prose citations into the plan resolve exactly:

```
evidence/deploy/terraform-plan-furl.txt:326 -> + authorization_type = "NONE"
evidence/deploy/terraform-plan-furl.txt:279 -> + reserved_concurrent_executions = -1
evidence/deploy/terraform-plan-furl.txt:77  -> + threshold                             = 8
```

`ruff check` and `ruff format --check` are clean on the file.

### 5.2 · The negative control for the new precondition

Not required by W8's brief, but it is the falsifiable half of §2.5 and it was cheap. Planned
from a **throwaway root in scratch space outside this repository**, calling the module by
absolute path with `concurrency_alarm_threshold = 11` and `account_concurrency_ceiling = 10`
— so no tracked file was edited to produce a red:

```
Error: Resource precondition failed
  on .../demo-api/main.tf line 621, in resource "aws_cloudwatch_metric_alarm" "concurrency":
 621:       condition     = var.concurrency_alarm_threshold < var.account_concurrency_ceiling
    │ var.account_concurrency_ceiling is 10
    │ var.concurrency_alarm_threshold is 11

concurrency_alarm_threshold (11) is not strictly below account_concurrency_ceiling (10).
… an alarm at or above it could never breach - a control that looks present and is not …
The ceiling is MEASURED, not assumed … Raising the ceiling variable to silence this message
without raising the real quota re-creates the exact defect it exists to refuse.
```

**The guard fires, and its message names the ceiling of 10.** The wave's "done means" for
this item holds.

### 5.3 · NOT owned — stale citations this regeneration created, listed for the orchestrator

The `dimensions` block leaving the `-concurrency` alarm shifted every FURL line after 78 by
exactly **−3**, and the CloudFront artefact by the same **−3**. Eight citations in files W8
does not own are now off by three. **None of them is wrong about a fact; each is wrong about
a line number, except the two marked ✗, which are wrong about a value.**

| File | Cites | Should cite | Note |
|---|---|---|---|
| `docs/deploy/COST-BOUND.md:43` | `…furl.txt:329` | `…furl.txt:326` | `authorization_type = NONE` — claim still true |
| `docs/deploy/COST-BOUND.md:44` | `…furl.txt:264-301` **and states `reserved_concurrent_executions = 20`** | `…furl.txt:261-298`, and the value is **`-1`** | ✗ **value, not just line.** This is the document the founder reads to decide; input I9 now describes a plan that no longer exists |
| `docs/TOOL-USAGE.md:993` | `…furl.txt:329` | `…furl.txt:326` | |
| `docs/deploy/JUDGE-PACK.md:632` | `…furl.txt:308,310` | `…furl.txt:305,307` | permit ids |
| `docs/submission/JUDGING-AXES.md:152` | `…furl.txt` line `339` for the `Plan:` line | line **336** | `339` now lands on `api_authorization_type = "NONE"` — it resolves and says the wrong thing, which is worse than not resolving |
| `docs/leads/submission-final-plan2.md:98` | `…furl.txt:304-312` | `…furl.txt:301-309` | the env block |
| `evidence/deploy/permit-id-agreement.json:116,117` | `…furl.txt:308 and :310` | `…furl.txt:305 and :307` | ✗ **recorded evidence — do not hand-edit.** The record is a true statement about the artefact as it stood on 2026-08-12; the right repair is a superseding record, not a rewrite |
| `evidence/tool-usage/aws-services.json:304` | `…furl.txt:329` | `…furl.txt:326` | regenerated, not hand-edited — see 5.4 |

`docs/leads/deploy-safety-plan.md:84,393` carries the same `:329` / `:308,310` anchors. It is
the lead's own record of what was true when the wave was planned and is left alone.

### 5.4 · NOT owned, and BLOCKING — the census must be regenerated once, after the wave lands

`scripts/aws/verify_evidence.py` currently **fails** on the tree, with two `CEN-ANCHORS`
errors:

```
[CEN-ANCHORS] evidence/tool-usage/aws-services.json#rows.aws_lambda: anchor
  infra/modules/demo-api/main.tf:310 quotes 'authorization_type = var.url_authorization_type'
  but that line now reads '# invocation - Lambda accepts the deployment happily and fails at
  request time, which'; the citation has silently retargeted
[CEN-ANCHORS] evidence/tool-usage/aws-services.json#rows.aws_ssm_parameter_store: anchor
  infra/modules/demo-api/main.tf:192 quotes 'actions = ["ssm:GetParameter"]' but that line
  now reads '}'; the citation has silently retargeted
```

**The generator is fixed (§5.1). Its committed output is not**, and CI reads the output.

The fix is one command:

```bash
python scripts/submission/capture_tool_evidence.py
```

**W8 deliberately did not run it, and the reason is sequencing, not squeamishness.** That
census is a documented *pure function of the whole tree* — `scan.files_scanned` already moved
from 7 388 to 7 410 because of files this wave and two parallel waves added. Regenerating it
mid-wave bakes a snapshot that goes stale the moment the next file lands. It must be run
**once, after the last file in the tree settles**, and the run must be checked for one
platform artefact: on Windows the writer converts
`evidence/tool-usage/*.json.license` from LF to CRLF, a two-byte change in two REUSE
sidecars that are not this wave's subject. Restore those two files if that happens.

After the regeneration, `verify_evidence.py` should report no `CEN-ANCHORS` failures — the
generator's anchors have already been verified to resolve on their subject, all 26 of them.

---

## 6 · What is still not true, and is not W8's to fix

The plan is now appliable **as a plan**. The account is still not ready, and this was
re-measured today:

| Precondition | State | Blocks |
|---|---|---|
| SSM SecureString `/mainline/demo/cockroach_dsn` | **absent** — `describe-parameters` returns `[]` | the function starts and fails on its first database call |
| S3 state bucket `mainline-demo-tfstate-…` | **absent** — no bucket matches `mainline-*` | `terraform init` fails before the apply begins |
| CloudFront account verification hold | **in force** | the 22-resource shape only; not the shipping shape |

`docs/deploy/PRE-APPLY.md` (W7) lists these in order with the read-only command that proves
each. **Do not apply anything until that page's gate is green.**

And the sentence that belongs in every hand-off: **`L-B99A9384` is `Adjustable: true` at
10, and every dollar of the worst case is linear in it. Nobody requests a concurrency quota
increase on this account without reading `docs/deploy/COST-BOUND.md` first.**

---

## 7 · Reproducing this

```bash
# 1 · the artefacts hash to what docs/deploy/terraform-plan.md §1 records
python - <<'PY'
import hashlib, pathlib
for p in ("evidence/deploy/terraform-plan-furl.txt",
          "evidence/deploy/terraform-plan-furl.json",
          "evidence/deploy/terraform-plan-cloudfront.txt"):
    b = pathlib.Path(p).read_bytes()
    print(p, len(b.decode().splitlines()), len(b), hashlib.sha256(b).hexdigest())
PY

# 2 · the counts, verbatim
grep -n '^Plan:' evidence/deploy/terraform-plan-furl.txt \
                 evidence/deploy/terraform-plan-cloudfront.txt

# 3 · the moved attributes: one -1, one 8, four "missing"
grep -n 'reserved_concurrent_executions\|treat_missing_data\|threshold  *=' \
        evidence/deploy/terraform-plan-furl.txt | grep -v alarm_description

# 4 · the masking. `grep -c` exiting 1 with three `:0` lines IS the pass.
grep -c '000000000000' evidence/deploy/terraform-plan-furl.txt \
                       evidence/deploy/terraform-plan-cloudfront.txt \
                       evidence/deploy/terraform-plan-furl.json
python scripts/aws/verify_evidence.py          # SEC-* pass; CEN-ANCHORS until §5.4 is run

# 5 · every census anchor resolves on its subject
python scripts/submission/capture_tool_evidence.py --print >/dev/null && echo "anchors OK"
```

`backend_override.tf` appears in none of it. It is not in the tree, it was never committed,
and **no `terraform apply` was run at any point in producing this document.**
