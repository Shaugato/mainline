<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
-->

# DEPLOY-SAFETY — the plan that makes the plan appliable, and the exposure bounded

**Lead:** deploy-safety · **Date:** 2026-08-13 · **Workers:** 8
**Standing order:** `terraform apply` is NEVER run here. `init`, `validate`, `plan`, `show`
and read-only AWS calls only. The orchestrator applies, after the founder re-authorises.

---

## 0 · What I measured before decomposing

Everything below is a call I made today from this machine under `AWS_PROFILE=mainline-dev`,
or a file I read at HEAD. Nothing is inherited from a board.

### 0.1 · The apply cannot succeed — measured, both regions

```
aws lambda get-account-settings --region ap-southeast-1
  AccountLimit.ConcurrentExecutions            10
  AccountLimit.UnreservedConcurrentExecutions  10
  AccountUsage.FunctionCount                    0

aws lambda get-account-settings --region ap-southeast-2
  AccountLimit.ConcurrentExecutions            10
  AccountUsage.FunctionCount                    1        (an unrelated project — DO NOT TOUCH)

aws service-quotas get-service-quota --service-code lambda --quota-code L-B99A9384 \
    --region ap-southeast-1
  QuotaName  "Concurrent executions"   Value 10.0   Adjustable true
```

The plan reserves 20. I regenerated it today and confirmed the number is still in it:

```
+ reserved_concurrent_executions = 20
+ threshold                      = 20      # the -concurrency alarm
Plan: 11 to add, 0 to change, 0 to destroy.
```

`PutFunctionConcurrency` is the sixth of eleven API calls in this apply. It will be
refused, and five resources will already exist when it is. **The plan artefact is sound;
the account it targets cannot run it.**

Two consequences the workers must carry, not re-derive:

* `min(20, 10) = 10`. The account ceiling *already* caps concurrency at 10. Setting
  `reserved_concurrent_executions = -1` therefore **does not raise the cost ceiling** — it
  removes an unappliable reservation and leaves the same physical bound in place. This is
  the one change in this whole wave that costs nothing and unblocks everything.
* The quota is `Adjustable: true`. **Raising it raises the worst case linearly.** Nobody
  requests an increase without re-reading §3 of this document first. Recording that here
  is part of the bound.

### 0.2 · The abuse tripwire cannot fire — measured

`aws_cloudwatch_metric_alarm.concurrency` is `ConcurrentExecutions > 20`. The metric's
physical ceiling is 10. The alarm is a control that looks present and is not — **the exact
defect `duration_p99`'s own `lifecycle.precondition` exists to forbid**, one resource
higher in the same file (`infra/modules/demo-api/main.tf:453-463`). The idiom was invented
here and then not applied to its neighbour.

`infra/modules/demo-api/variables.tf:388` (`reserved_concurrent_executions`) states:

> *"It reserves 20 of the account's 1 000 unreserved executions"*

The account has **10**, not 1 000. That sentence is why the defect survived review: it
describes a different account.

### 0.3 · Nothing bounds the cost — measured, and the audit's range reproduced

I reproduced the audit's USD 11,515–33,472 figure from first principles rather than
accepting it, and it holds. The inputs are measured, not assumed:

| Input | Measured value | Source |
|---|---|---|
| Concurrency ceiling | 10 | `get-account-settings`, above |
| Largest single response the origin can emit | **1,554,168 B** (`web/assets/index-BjAGxrVJ.js.map`) | `zipfile` over `out/lambda/mainline-demo-api-arm64.zip` |
| Whole web tree in the package | 3,571,990 B over 75 files | same |
| …of which source maps | **2,586,960 B over 18 files = 72.4 %** | same |
| Function URL auth | `NONE` | `evidence/deploy/terraform-plan-furl.txt:329` |

Sustained flood, 30 days, concurrency pinned at 10, every request fetching the 1.554 MB
source map:

```
invocation ≈ 100 ms → 100 rps → 155.4 MB/s → 402.9 TB / 30 d
  egress  10 TB @ $0.12  =  $1,200
          40 TB @ $0.085 =  $3,400
         100 TB @ $0.082 =  $8,200
        252.9 TB @ $0.08 = $20,232
  requests  259.2 M × $0.20/M  =  $52
  compute   259.2 M × 0.1 s × 0.5 GB × $0.0000133334 = $173
                                        TOTAL ≈ $33,257

invocation ≈ 300 ms →  33 rps → 134 TB / 30 d      TOTAL ≈ $11,538
```

**My independent arithmetic lands inside the audit's range to within 1 %.** The range is
not a guess; it is 30 days at concurrency 10 with a 100–300 ms invocation. Treat it as
measured.

The budget, read today:

```
aws budgets describe-budgets --account-id <account> --region us-east-1
  "My Monthly Cost Budget"              limit  10.00   actual 12.686   forecast 33.028
  "My Monthly Cost Budget - $5 limit"   limit   5.00   actual 12.686   forecast 33.028
  "My Zero-Spend Budget"                limit   1.00   actual 12.686   forecast 33.028

aws budgets describe-budget-actions-for-budget --budget-name "My Monthly Cost Budget"
  { "Actions": [] }
aws budgets describe-budget-actions-for-budget --budget-name "My Monthly Cost Budget - $5 limit"
  { "Actions": [] }
```

Three budgets, all three already breached by unrelated projects, **zero actions on any of
them**. They notify. They stop nothing. The founder's card is running ~3× its own budget
before this project adds a byte.

`docs/deploy/RUNBOOK.md` §8 currently ends *"Round it to two cents a month, and call the
worst case a dollar."* The worst case is **four to five orders of magnitude** above that
sentence. That sentence is the single most dangerous claim in the deploy documentation and
correcting it is not optional.

### 0.4 · No alarm has a reader — measured

All four alarms plan `alarm_actions = []`. `infra/modules/demo-api/main.tf:376-378` says
they exist to be read *"by the hourly `demo-health` workflow, which calls
`describe-alarms`"*.

**`demo-health.yml` does not call `describe-alarms`.** I grepped it: no `cloudwatch`, no
`aws`, and `permissions: contents: read` with no OIDC role and no AWS credentials anywhere
in the repository's workflows (`aws-evidence.yml` goes out of its way to *unset* every
`AWS_*` variable at line 193). **A CI-based alarm reader cannot be shipped, because no CI
credential exists to read with.** Any plan that assumes one is fiction.

Meanwhile all four carry `treat_missing_data = "notBreaching"`, so an idle demo displays
four green alarms where green means *"nobody called this function"*.

### 0.5 · Teardown's closing claim is broader than its evidence — measured

`scripts/deploy/teardown.sh:633` prints *"nothing this project created remains in account
$ACCOUNT"*. Its verify block re-reads **three** things: S3 buckets by prefix, the SSM
parameter, Lambda functions by prefix. The apply creates **seven** classes. Unverified:

| Resource | Name at apply |
|---|---|
| IAM role | `mainline-demo-api-exec` |
| CloudWatch log group | `/aws/lambda/mainline-demo-api` |
| CloudWatch alarms ×4 | `mainline-demo-api-{errors,throttles,duration-p99,concurrency}` |
| CloudWatch dashboard | `mainline-demo-api` |

`terraform destroy` (step 1) does delete them, so the orphan cost is **USD 0.00**. The
defect is not money. **The defect is that "nothing remains" is a claim with 43 % of its
subject unmeasured**, in a repository whose entire argument is that its claims are
checkable.

### 0.6 · The apply's two preconditions do not exist — measured

```
aws ssm describe-parameters --region ap-southeast-1  →  []          (no /mainline/* parameter)
aws s3api list-buckets                               →  7 buckets, none named mainline-*
```

The Lambda's `MAINLINE_DSN_PARAM` points at `/mainline/demo/cockroach_dsn`, which does not
exist. The S3 backend wants `mainline-demo-tfstate-<account>`, which does not exist. An
apply attempted right now fails at `terraform init` before it fails at concurrency.

### 0.7 · The plan regenerates — measured, with the recipe

`terraform init -backend=false` is **not sufficient** on this tree: `terraform plan` then
refuses with *"Changes to backend configurations require reinitialization"* because
`backend.tf` declares S3. The working recipe, which I ran today end to end:

```bash
cd infra/envs/demo
cat > backend_override.tf <<'EOF'
terraform {
  backend "local" {
    path = "<scratchpad>/demo-plan.tfstate"
  }
}
EOF
AWS_PROFILE=mainline-dev terraform init -reconfigure -input=false
AWS_PROFILE=mainline-dev terraform plan -no-color -input=false
rm -f backend_override.tf          # NEVER commit this file
```

Result today, unchanged from the committed evidence: `Plan: 11 to add, 0 to change,
0 to destroy.` Terraform v1.14.8, `hashicorp/aws v6.58.0`.

---

## 1 · The binding design constraints

Every worker obeys all five.

1. **THE PLAN STAYS AT 11 RESOURCES.** `Plan: 11 to add, 0 to change, 0 to destroy` is
   quoted verbatim in `docs/deploy/JUDGE-PACK.md`, `docs/submission/DEVPOST.md`,
   `docs/submission/JUDGE-START.md`, `docs/STATE-OF-THE-BUILD.md` and
   `scripts/submission/check_submission_ready.py`. This wave changes **attribute values**,
   never the resource set. Anything new (SNS topic, budget responder) ships `count = 0` by
   default so the shipping shape is byte-comparable. A worker who changes the count has
   broken five documents it does not own.
2. **NO `terraform apply`.** Not once, not with `-target`, not "just to check".
3. **No credential, DSN, password or raw account id in any output, file or result.** The
   account id is masked as `0229REDACTED8246` across tracked files (commit `1d41442`,
   84 occurrences, 13 files). Regenerated evidence gets the same treatment, and must also
   carry **zero** occurrences of `000000000000` — two checkers disagreed about whether
   twelve identical digits is a mask or a value, and the resolution recorded in
   `docs/CI-STATE.md:417` is to remove the digits, not relax either checker.
4. **No weakening of `docs/HONESTY.md`, `docs/CI-STATE.md`, a ratchet or an assertion.**
   No `continue-on-error`, no `|| true`. No recorded transcript is edited to satisfy a
   scanner — if a scanner is wrong, the scanner is fixed.
5. **Fix causes.** If a change makes something green, state which assertion now holds that
   did not. If it cannot be stated, the change is a symptom fix and is rejected.

### 1.1 · The near-miss this wave must not repeat

`scenario_permit_id` defaulted to a uuid5 nothing had ever seeded, while
`transitions._demo_guard` armed its 423 only at `subject_id == scenario.permit_id`. The
guard was armed at an id no caller would ever send, leaving four committing kernel POSTs
reachable anonymously on an `authorization_type = NONE` URL. That surface was inert only
because of an unrelated `KeyError`. **Fixing the 500 without the permit-id fix would have
opened the hole.**

Read that as a standing instruction, not history: in this codebase a "harmless" fix is
routinely load-bearing for a security property somewhere else. Before any worker changes a
default, a threshold or a header, it names what else reads that value.

---

## 2 · The exposure, stated once, honestly

The Function URL is `authorization_type = NONE`. What bounds it today:

| Claimed bound | Real? | What it actually bounds |
|---|---|---|
| `reserved_concurrent_executions = 20` | **NO** — unappliable | nothing; the apply dies on it |
| Account ceiling of 10 | **YES**, and it is the only one | concurrency, hence rate, hence ≈ everything |
| `-concurrency` alarm at 20 | **NO** — above a ceiling of 10 | nothing |
| CockroachDB Basic $25 cap | **YES** | the database side only; the flood target is the static tree, which never touches the DB |
| The handler's rolled-back transaction | **YES** | database *state*, not spend |
| AWS Budget | **NO** — no action, and already breached | nothing |

**One real bound, and it is an AWS default nobody chose.** That is the finding.

---

## 3 · The cost menu — every lever, what it does and does not bound

This is the material the founder decides from. Worst case before any lever: **≈ $33,257 /
30 d** (best case of the flood: ≈ $11,538). Numbers are deltas against that.

| # | Lever | Worst case after | Bounds | Does **NOT** bound | Judge friction | Dollars to build |
|---|---|---|---|---|---|---|
| L1 | `reserved_concurrent_executions = -1` | $33,257 (unchanged) | nothing — but it is **required for any apply at all** | anything | none | 0 |
| L2 | Strip source maps (`--strip-source-maps`, **already built**, off by default) | **≈ $9,270** | bytes/request: 1,554,168 → 433,396 B = **3.59×** | request rate | DevTools shows minified frames instead of component names | 0 |
| L3 | Response-size cap in the handler (413 above a declared ceiling) | ≈ L2 if set at 512 KiB | bytes/request, **and ratchets it** so it can never silently grow | request rate | none if the ceiling is above every legitimate asset | 0 |
| L4 | Per-IP throttle in the handler | ≈ **$230** vs a single source | egress against one source: the 429 body is ~200 B, a ~7,000× collapse | a distributed flood; and Lambda charges for the invocation whether it 429s or not | none | 0 |
| L5 | Shared-secret gate (`?k=…` or a header) | ≈ **$230** | egress against every caller who has not read the submission | a determined attacker — the token is public the moment the submission publishes | **one longer URL in the form** | 0 |
| L6 | Budget action → SNS → responder Lambda → `PutFunctionConcurrency(0)` | ≈ **$1,100 already spent** when it fires | nothing in the first day | the first 8–24 h, which is where the money is | none | 0, but +3 resources |
| L7 | Timeout 15 s → 5 s, memory 512 → 256 MB | ≈ $33,170 | **0.3 %** of the bill | 99.7 % of the bill | worse cold starts | 0 |
| L8 | `authorization_type = AWS_IAM` | **≈ $0** | everything — rejection is pre-invocation, no charge, empty body | nothing | **total** — the judges get 403 and cannot open the demo; CloudFront, the only fix, is refused on this account | 0 |
| L9 | `reserved_concurrent_executions = 0` kill switch, run by hand | $0 from the moment it runs | everything, instantly | the time before somebody looks | none | 0 |

Three of these must be said out loud because they are commonly sold as what they are not:

* **A budget action cannot disable a Lambda function.** AWS Budgets actions apply an IAM
  policy, apply an SCP (Organizations only), or stop EC2/RDS instances. There is no Lambda
  action. The only real path is Budgets → SNS → a responder function that calls
  `PutFunctionConcurrency(0)`. Cost Explorer data lags 8–24 h, so at ~$1,100/day the
  backstop fires **after** ~$1,100 is spent. It is a backstop, not a bound, and L6's row
  says so.
* **Reducing memory and timeout is not a cost control here.** Compute is $173 of $33,257.
  Halving memory saves ~$86 out of ~$33,000. Selling L7 as a cost bound would be exactly
  the "control that looks present and is not" this module's own preconditions exist to
  refuse.
* **`reserved_concurrent_executions = 0` is the documented way to stop a function, and it
  is the one reservation this account can still accept** — reserving 0 does not decrease
  `UnreservedConcurrentExecutions` below its minimum, which is what refuses every positive
  value here. This is documented behaviour, **not measured on this account**, because
  measuring it requires a mutating call. It ships labelled that way.

### 3.1 · The recommendation

**Layer 1 — take now, zero friction, zero dollars, no decision needed:** L1 (mandatory),
L3 at 512 KiB, L2 as the build default, and the concurrency alarm at 8 with a reader.
Worst case falls to **≈ $9,270**, and L3 makes that number a ratchet rather than a
coincidence.

**Layer 2 — recommended, one decision:** L5, the shared-secret gate. It collapses the worst
case from ≈ $9,270 to ≈ $230 for the cost of one query parameter in the submission form.
It is obscurity, not authentication, and it is worth having anyway: it stops every
opportunistic scanner, which is what actually finds an `on.aws` hostname.

**Layer 3 — arm it:** L9 as a one-command script, plus L6 default-off so the founder can
turn it on knowing its lag.

**Reject:** L8 (breaks judging outright — an `AWS_IAM` URL with no distribution is not a
hardened demo, it is a 403 to everyone including the judges) and L7-as-a-cost-control.

**And the quota:** `L-B99A9384` is `Adjustable: true` at 10. Every dollar above is linear
in it. **Do not request an increase.** That sentence belongs in the runbook.

---

## 4 · The eight workers

Ownership is absolute and the path lists are literal. No worker opens a file another
worker owns; cross-file coupling is expressed through `depends_on` and a stated contract.

| # | Worker | Scope | Depends on |
|---|---|---|---|
| W1 | Root: make the plan appliable | (a) | — |
| W2 | Module variables: the false claim, the ceiling, threshold 8 | (b) | — |
| W3 | Module resources: preconditions, honest missing-data, the reader wiring | (b)(d) | W2 |
| W4 | Handler: CORS, and the response-size ratchet | (f)(c) | — |
| W5 | Teardown: the four missing verify checks | (e) | — |
| W6 | The cost bound: menu, kill switch | (c) | — |
| W7 | Runbook, pre-apply checklist, observability, the local alarm reader | (g)(d)(c) | W3, W6 |
| W8 | Regenerate the plan and reconcile every consumer | all | W1, W2, W3 |

### Files, disjoint and enumerated

```
W1  infra/envs/demo/main.tf
    infra/envs/demo/variables.tf
    infra/envs/demo/terraform.tfvars.example
    infra/envs/demo/README.md

W2  infra/modules/demo-api/variables.tf

W3  infra/modules/demo-api/main.tf
    infra/modules/demo-api/outputs.tf
    infra/modules/demo-api/README.md

W4  verticals/mainline/apps/demo-api/src/mainline_demo_api/app.py
    verticals/mainline/apps/demo-api/src/mainline_demo_api/static_site.py
    verticals/mainline/apps/demo-api/tests/test_static_site.py
    verticals/mainline/apps/demo-api/tests/test_response_contract.py        (new)

W5  scripts/deploy/teardown.sh

W6  docs/deploy/COST-BOUND.md                                              (new)
    scripts/deploy/kill_switch.sh                                          (new)
    scripts/deploy/kill_switch.ps1                                         (new)

W7  docs/deploy/RUNBOOK.md
    docs/deploy/OBSERVABILITY.md
    docs/deploy/PRE-APPLY.md                                               (new)
    scripts/deploy/aws_live_probe.py

W8  evidence/deploy/terraform-plan-furl.txt
    evidence/deploy/terraform-plan-furl.json
    evidence/deploy/terraform-plan-cloudfront.txt
    docs/deploy/terraform-plan.md
    scripts/submission/capture_tool_evidence.py
    docs/leads/deploy-safety-verify.md                                     (new)
```

Unowned and untouched by this wave, by design: `docs/HONESTY.md`, `docs/CI-STATE.md`,
`docs/deploy/JUDGE-PACK.md`, `docs/STATE-OF-THE-BUILD.md`, `docs/submission/*`,
`scripts/deploy/build_lambda.{sh,ps1}`, every `.github/workflows/*`. W6 **costs** the
source-map strip; it does not flip the build default, because that changes the zip hash and
cascades into `evidence/deploy/lambda-bundle.json`, the dry-run evidence and the manifest
assertions. The flip is a founder decision recorded in `COST-BOUND.md`, executed by the
orchestrator if taken.

---

## 5 · Already true — measured, not assigned

These were in the brief and are **already correct at HEAD**. No worker spends effort on
them; they are stated so the orchestrator does not re-open them.

1. **`--strip-source-maps` already exists.** `scripts/deploy/build_lambda.sh:105,416,537,583`
   implements it end to end, records `source_maps: kept|stripped` in the manifest, and its
   header at line 41 states why it defaults to *kept*. The **capability** is built; only
   the **default** is a decision, and that is L2 in the menu, not a worker task.
2. **The `alarm_actions` plumbing already exists.** `variables.tf:462` declares it and all
   four alarms already wire it into both `alarm_actions` and `ok_actions`. The gap is a
   *value* and a reader, not the wiring — W3/W7 supply those, and nobody re-plumbs.
3. **The `lifecycle.precondition` idiom already exists and is correct.**
   `main.tf:453-463` on `duration_p99`, with a plan-time condition and a diagnostic error
   message. W3 **extends** the existing idiom; it does not invent one.
4. **The `scenario_permit_id` fix is committed.** `variables.tf:251` defaults to
   `dec0de00-0006-4000-8000-000000000001`, and the plan carries it at
   `evidence/deploy/terraform-plan-furl.txt:308,310` under both
   `MAINLINE_DEMO_PERMIT_ID` and `MAINLINE_SCENARIO_PERMIT_ID`. Nothing to do.
5. **Teardown already verifies three of seven classes** (buckets, SSM parameter, Lambda
   functions) and already routes them through `aws_query`, which refuses to call an
   unreadable account an empty one (`teardown.sh:147-155`). W5 **adds four checks in the
   established shape**; it does not restructure the block.
6. **`terraform destroy` already deletes all seven classes.** The orphan cost is USD 0.00.
   W5 fixes a false claim, not a leak, and its commit message must say so.
7. **The runbook already documents creating both preconditions** — §5.1 (`bootstrap_state.sh`,
   with its measured first-run transcript and its refusal of any bucket name outside the
   `mainline-demo-` prefix) and §5.2 (`aws ssm put-parameter --type SecureString`, payload
   via a `0600` temp file so the DSN never enters an argument vector). §5.0's dry-run
   already makes a live read-only `describe-parameters` call for `/mainline/`. What is
   missing is **not** the procedure — it is the statement that *neither exists in this
   account right now* and an ordered, executable pre-apply gate. W7's task is narrowed
   accordingly.
8. **The plan is byte-reproducible today.** I regenerated it: `Plan: 11 to add, 0 to
   change, 0 to destroy`, same `reserved_concurrent_executions = 20`, same alarm
   thresholds. W8 inherits a verified recipe (§0.7) rather than discovering one.

---

## 6 · Done means

The wave is done when all of these hold, each checkable by a command:

* `terraform plan` from a clean `-reconfigure` shows `reserved_concurrent_executions = -1`
  and `Plan: 11 to add, 0 to change, 0 to destroy`.
* The `-concurrency` alarm plans `threshold = 8`, and a deliberately-raised threshold is
  **refused at plan time** with a message naming the ceiling of 10.
* No file claims the account has 1 000 unreserved executions.
* `access-control-allow-origin` appears in no response the handler builds.
* `teardown.sh --dry-run` names seven resource classes, and its closing sentence is exactly
  as broad as its evidence.
* `docs/deploy/RUNBOOK.md` §8 no longer contains the sentence *"call the worst case a
  dollar."*
* `docs/deploy/COST-BOUND.md` exists, carries the arithmetic of §0.3, and ends in a
  recommendation the founder can act on in one reading.
* `docs/deploy/PRE-APPLY.md` lists, in order, every precondition, with the read-only
  command that proves each — and states that today two of them are absent.
* The regenerated plan carries zero occurrences of the real account id and zero occurrences
  of `000000000000`.

**The number the founder re-authorises is the number that will run.** That is the whole
point of W8, and it is why W8 goes last.
