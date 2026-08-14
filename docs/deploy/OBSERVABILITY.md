<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: CC-BY-4.0
-->

# Observability — one heartbeat, seven alarms, and the only reader that can exist

> **CORRECTED 2026-08-14 (W6 `post-apply`) — the heading said "four alarms".** The stack
> plans **seven**: `module.api`'s four and `module.guard`'s three, and the guard's three
> are the ones wired to the stop. §3 has said seven since 2026-08-14; the heading and the
> reader's exit table had not caught up, and `scripts/deploy/aws_live_probe.py` was
> comparing against a hard-coded four. All three are corrected below and in that file.

**What watches this demo, by what, at what interval, what each signal means, what a judge
sees when the database is unreachable, and what it costs.**

Owner: W7 (deploy-safety) for this document and
[`scripts/deploy/aws_live_probe.py`](../../scripts/deploy/aws_live_probe.py). The heartbeat
workflow [`.github/workflows/demo-health.yml`](../../.github/workflows/demo-health.yml) is
owned elsewhere and is described here, not edited from here. The alarms and dashboard are
declared by [`infra/modules/demo-api`](../../infra/modules/demo-api); every threshold below
is read from that module's HCL rather than remembered.

**Nothing on this page is created yet.** `terraform apply` has not been run — the plan is
committed and the founder reviews it before any apply. So §3 and §5 describe *declarations*,
not resources, and say so in their own words. §2 is live today and is red today, on purpose.
[`PRE-APPLY.md`](PRE-APPLY.md) is the gate that runs before the apply that would change that.

**The one-line summary of this page:** the heartbeat is real and public, the alarms are real
but notify nobody, **there is no CI reader for the alarms and none can be built**, and the
reader that does exist is a command an operator runs on their own machine.

---

## 1. What is watched, by what, at what interval

| Subject | Watcher | Interval | Where the signal appears |
|---|---|---|---|
| `GET /` — the console is served | `demo-health.yml` | hourly | red X on the Actions tab |
| `GET /v1/health` — live, fresh, `ok: true` | `demo-health.yml` | hourly | red X + the body in the log |
| `POST /v1/demo/gate-run` — the four beats by SQLSTATE | `demo-health.yml` | hourly | red X + which beat moved |
| latency of all three | `demo-health.yml` | hourly | job summary table, every run |
| Lambda errors / throttles / p99 / concurrency | four CloudWatch alarms (declared) | 5-minute periods | CloudWatch console; **notifies nobody**; read with §3's command |
| the whole claim, end to end, from outside | `scripts/deploy/demo_acceptance.py` | at deploy time, and on demand | [`evidence/deploy/acceptance.json`](../../evidence/deploy/acceptance.json) |
| CockroachDB Cloud cluster metrics | **nothing** | — | see §7 |

Two watchers, deliberately. The cron answers *is it up and does it still refuse?*; the
alarms answer *is the function itself unhealthy?*. Neither can answer the other's question,
and a page that implied one of them covered both would be the most misleading document here.

**They are also unequal in an important way.** The cron runs itself, in public, on a
schedule. The alarms do not run anything — they sit in an account and change colour, and
somebody has to look. §3 is mostly about that asymmetry.

---

## 2. The heartbeat — `.github/workflows/demo-health.yml`

Hourly on the hour, and on demand via `workflow_dispatch`.

```
resolve the URL from docs/submission/SUBMISSION.json:demo_url
  (a workflow input or vars.DEMO_URL overrides it, for a staging host)

GET  /                     assert 200 and an HTML document
GET  /v1/health            assert 200, body.ok, server_date within 900s
POST /v1/demo/gate-run     assert 200 and the four beats:
                             1 read                     00000
                             2 merge                     23514  gate_closed_when_issued
                             3 projection_drift_attack   P0001  mainline.fn_permit_merge_gate
                             4 admit                     00000
                           assert persisted is false and verdict is PROVEN
record the latency of all three into the job summary
```

### It is red right now, and the red says which red it is

`docs/submission/SUBMISSION.json` holds `"demo_url": "UNRESOLVED"`, so the first step fails
with:

> no demo URL is published; this lane is red because the demo is not deployed, not
> because it is broken

That is the whole design of this lane. Before 2026-08-11 it failed in six to thirteen
seconds with a curl connection error against an unset repository variable — the same red for
a completely different reason, which is how a monitor teaches its readers to ignore it. **A
monitor whose red cannot distinguish "not deployed" from "deployed and down" is not a
monitor.**

> That first sentence is quoted verbatim from the workflow and from
> [`docs/CI-STATE.md`](../CI-STATE.md). It is not reworded here, and it should not be
> reworded there without changing all three.

**It goes green on its own the moment the URL exists.** The apply's publish stage writes
`demo_url`; the next scheduled run reads the file out of the checkout, finds a URL and starts
asserting. No repository variable, no secret, no edit to the workflow. The submission file is
the single place a demo URL is recorded, so it is the single place this job reads.

### Why the freshness assertion earns the job

A cached 200 is the classic false green: an edge object serves a valid health body for hours
after the database behind it has gone. `server_date` comes from `now()` **inside the health
statement**, so a body older than the window proves nothing has spoken to CockroachDB
recently, whatever the status line says. The endpoint is served `no-store`; this check is
what verifies that it actually is.

The window is 900 seconds and deliberately generous. It is a staleness detector, not a
clock-skew detector — a GitHub runner and a CockroachDB node in Singapore have no guaranteed
relationship between their clocks. A `server_date` in the *future* is reported as a
**warning** naming clock skew, not as a staleness failure, because sending whoever is on call
to look for the wrong thing is its own failure mode.

### Why it now drives the gate, when the previous version refused to

The previous version argued that calling `gate-run` on a schedule was hundreds of needless
`SERIALIZABLE` transactions against a Basic cluster with a spend cap, to re-establish
something that does not silently change. Two facts moved:

* **It does silently change.**
  [`evidence/deploy/acceptance.json`](../../evidence/deploy/acceptance.json) recorded the
  demo's headline endpoint answering **404 for days** while every other surface was green,
  because the route was missing from `app._routes()`. A liveness check that never touched it
  could not have seen that, and did not.
* **The transaction is rolled back and nothing accumulates.** The four beats share one
  transaction that ends in `ROLLBACK`. The acceptance prover establishes that from *outside*
  by re-reading `GET /v1/permits/{id}` after each run and comparing `open_blocking`, `state`,
  `gate_epoch` and `head_seq` — see §6. There is no state for two runs to collide over and
  nothing to clean up.

The cadence is therefore **hourly, not half-hourly**: 24 gate runs a day, ~200 across the
whole judging window, against a Basic cluster whose free monthly allowance is **50 M RU**
(Cockroach Labs' published figure; this page previously said 100 M, which was wrong — see
[`docs/verify/deploy/cost-and-quota.md`](../verify/deploy/cost-and-quota.md) §3.1, which
caught it).

### It opens nothing when it passes

No issue, no comment, no notification, no artefact. A monitor that produces output on a
healthy system trains its readers to ignore its output. The only signal is the red X on a
scheduled run — which is what a maintainer already watches for, and which, on a public
repository, is visible to the judges too.

### No `continue-on-error`, no `|| true`, no `set +e`

[`docs/HONESTY.md`](../HONESTY.md) bans them and this workflow contains none. The previous
version carried one `|| true` on the curl that fetched the health body; it is gone. curl's
exit status is now allowed to fail the step under `set -euo pipefail`, and the HTTP status is
captured with `--write-out` and asserted separately, so a **transport failure** and a **500**
stay different reds. A step that cannot fail asserts nothing.

The one `if: always()` in the file is on the step that writes the latency table. It reports;
it does not suppress. The job's conclusion is still whatever the assertions decided, and a
red run carries its timings — a 200 that took nine seconds is the shape of a problem that has
not become an outage yet.

---

## 3. The four CloudWatch alarms — what they mean, and who reads them

Declared by `infra/modules/demo-api`. All four are 5-minute periods, 1 evaluation period,
named `${function_name}-<suffix>`. ~~and all four plan `alarm_actions = []`.~~
**CORRECTED 2026-08-14 — that clause was false.** All four now plan
`alarm_actions = (known after apply)`
([`terraform-plan-furl.txt:68,98,131,164`](../../evidence/deploy/terraform-plan-furl.txt)),
because `infra/envs/demo/main.tf:586` feeds them `local.guard_stop_topic_actions` — the cost
guard's SNS topic. See the corrected §"If you want to be paged" below; the `[]` reading
survived from before `module "guard"` was instantiated.

**These four are not all the alarms the stack plans.** `module.guard[0]` declares three more
(`-invocations-burst`, `-invocations-hourly`, `-log-ingestion`, at
`terraform-plan-furl.txt:541,575,609`), so a `describe-alarms` against an applied stack
returns **seven**, not four. This section is scoped to the four `demo-api` declares; the
guard's three are documented in `docs/deploy/COST-BOUND.md`.

| Alarm | Metric | Statistic | Threshold | Dimension | What a breach means |
|---|---|---|---|---|---|
| `-errors` | `Errors` | `Sum` | `> 0` | `FunctionName` | The Lambda **raised**. The handler is written never to raise — refusals are a `200` with a `REFUSED` verdict, failures are a JSON problem document — so one datapoint is a real defect, not load. |
| `-throttles` | `Throttles` | `Sum` | `> 0` | `FunctionName` | Invocations were refused. With no per-function reservation this means the **account** ceiling of 10 was reached in `ap-southeast-1`. Do not go looking for a per-function cap to raise; there isn't one. Reaches the caller as a bodiless `429`. |
| `-duration-p99` | `Duration` | `p99` | `> 13 500 ms` | `FunctionName` | The slow tail, approaching the 14 s timeout. On this stack that is almost always the pgwire round trip to Singapore, not the handler — `/v1/health` reports connect time separately and is the first thing to read. |
| `-concurrency` | `ConcurrentExecutions` | `Maximum` | `> 8` | **none — account-level** | **An abuse tripwire, not a capacity signal.** A judging session is a handful of browsers making four requests each; 8 concurrent executions is not reachable by legitimate use of this demo. |

Two of those cells are recent repairs, and both are the same defect wearing different hats:

* **The `-concurrency` threshold was 20, against a metric whose physical ceiling is 10.**
  `ConcurrentExecutions` cannot exceed the account's Lambda concurrency quota, so an alarm
  above it could never breach. It is now `8`, and a `lifecycle.precondition` **refuses at
  plan time** any threshold not strictly below `var.account_concurrency_ceiling` — the same
  idiom `duration_p99` already used against the function timeout, finally applied to its
  immediate neighbour.
* **The `-concurrency` alarm carries no `FunctionName` dimension, and the absence is the
  fix.** Lambda publishes the *per-function* `ConcurrentExecutions` metric dependably only
  for functions that have reserved concurrency, and this account refuses every positive
  reservation, so a dimensioned alarm would sit in `INSUFFICIENT_DATA` forever. Undimensioned
  it evaluates the account aggregate for the region, which Lambda always publishes — and
  `aws lambda list-functions --region ap-southeast-1` returns `[]`, so this module creates
  the region's first function and the account aggregate **is** its concurrency. **The day a
  second function lands in `ap-southeast-1` that stops being true**, and the repair is a
  `metric_query` that filters to this function — never a raised threshold.

> **CORRECTED 2026-08-14 — the `-duration-p99` row said `> 12 000 ms` "approaching the 15 s
> timeout". Both numbers were stale, and the document lost to the artefact.** The committed
> plan reports `threshold = 13500`
> ([`terraform-plan-furl.txt:124`](../../evidence/deploy/terraform-plan-furl.txt)) and
> `timeout = 14` (`:315`), confirmed a second time in the plan-known `api_published_bounds`
> object at `:864` (`duration_p99_threshold_ms = 13500`) and `:875` (`timeout_seconds = 14`).
> **The committed plan artefact is authoritative and this prose is derived**
> (`docs/leads/docs-and-cloud-plan.md` RULING 4); the evidence file was not touched.
>
> The pair is not arbitrary and the gap is the point: `:868` records
> `modelled_worst_legitimate_duration_ms = 13022`, so the threshold sits **above** the worst
> duration a legitimate request is modelled to take and **below** the timeout. An alarm under
> 13,022 ms would page on success; one at or above 14,000 ms could never breach, because the
> function is killed at the timeout first. That second failure mode is the one
> `duration_p99`'s `lifecycle.precondition` refuses at plan time.

### What a state means — and why `INSUFFICIENT_DATA` is the honest answer

All four alarms set **`treat_missing_data = "missing"`**. That word decides what every colour
on this page means, so it is worth one table:

| State | What it means here | Is it good news? |
|---|---|---|
| `OK` | The metric was published, and it stayed under the threshold. | **Yes** — something was measured and it was fine. |
| `ALARM` | The metric was published and crossed the threshold. | No. §3's table says what each breach means. |
| `INSUFFICIENT_DATA` | **The metric was not published at all.** Nobody invoked the function in the window. | Neither. It is the *expected* state of an idle demo, and the correct state for a stack that has just been applied and not yet visited. |

**This used to be dishonest, and the fix is one word.** All four alarms previously set
`treat_missing_data = "notBreaching"`, under which a window with no datapoints is scored as
*not breaching* and the alarm shows `OK`. An idle demo therefore displayed **four green
alarms**, and the one thing an operator reads off a green alarm — *"I looked, it is
healthy"* — was false: nobody had called the function, so nothing had been measured. Under
`missing` an unexercised demo reads `INSUFFICIENT_DATA`, which is true and which prompts the
next question instead of closing it.

The price is that a demo nobody has visited does not show green. That is not a price.

> **So do not read `INSUFFICIENT_DATA` as a fault, and do not read it as health.** It is the
> alarm saying *"I have nothing to report because nothing happened."* On a demo that a judge
> has just used, it means something is wrong with the *metric*, not the demo — which is a
> different investigation.

### The alarms notify nobody, and that is deliberate

`alarm_actions` defaults to `[]`. There is no SNS topic, no email, no pager. Wiring a
notification channel for an eight-day demo means creating a topic, confirming a subscription,
and remembering to tear both down.

**The alarms exist to be read.** The question this section exists to answer honestly is: *by
what?*

### There is **no CI reader**, and there cannot be one

An earlier version of the module said these alarms would be read *"by the hourly
`demo-health` workflow, which calls `describe-alarms`"*. **That was false**, and it is worth
being precise about why it could not have been true:

```
$ grep -ci cloudwatch .github/workflows/demo-health.yml
1                              # a comment pointing at §4 of this page. No API call.
$ grep -n '^permissions:' -A2 .github/workflows/demo-health.yml
131:permissions:
132:  contents: read             # no id-token, so no OIDC
$ grep -rn 'aws-actions/configure-aws-credentials\|AWS_ACCESS_KEY\|role-to-assume' .github/workflows/
                               # (no output — not one workflow configures AWS credentials)
$ grep -rn 'AWS_' .github/workflows/
.github/workflows/aws-evidence.yml:  env -u AWS_PROFILE -u AWS_ACCESS_KEY_ID -u AWS_SECRET_ACCESS_KEY \
.github/workflows/aws-evidence.yml:      -u AWS_SESSION_TOKEN -u AWS_ROLE_ARN -u AWS_REGION -u AWS_DEFAULT_REGION \
.github/workflows/aws-evidence.yml:  echo "verified with no ~/.aws, no AWS_* variable and no database DSN …"
```

**Three matches, all on one `env -u …` invocation, and all of them *unsetting*.**
`aws-evidence.yml` deletes `$HOME/.aws` and strips every `AWS_*` variable on purpose, to prove
its verification runs on a machine with no account. (Line numbers are omitted deliberately:
they move, the fact does not. Re-run the greps — that is the point of printing them.)

So: **no AWS credential exists in CI.** A CI-based alarm reader is not a feature that was
skipped for time. It is a feature that cannot be added without first putting a credential —
or an OIDC role — into the workflows of a **public** repository, to read four alarms on a
demo that lives for eight days. That trade is refused, and refusing it is the reason this
section exists rather than a `TODO`.

### The reader that does exist

One command, read-only, free, run by an operator against their own profile:

```bash
.venv/Scripts/python.exe scripts/deploy/aws_live_probe.py --alarms-only
```

It calls `sts:GetCallerIdentity` and `cloudwatch:DescribeAlarms --alarm-name-prefix
mainline-demo-api` in `ap-southeast-1` — **not** the Bedrock region — and prints every alarm
with its state, the meaning of that state, its threshold, its `treat_missing_data`, and how
many actions it has. It writes no evidence file unless you give it `--out`, and it refuses an
`--out` that would overwrite the Bedrock evidence.

Exit codes are the point:

| Exit | Meaning |
|---|---|
| `0` | AWS answered, **every alarm the Terraform modules declare** exists, none is in `ALARM`. |
| `1` | AWS would not answer — credentials, region, permissions. **Not a statement about the demo.** |
| `3` | AWS answered and **the answer is bad**: an alarm is in `ALARM`, or an expected alarm does not exist. |

`1` and `3` are different numbers because "fix my credentials" and "wake somebody up about
the demo" are different first moves.

#### CORRECTED 2026-08-14 — the expected set is DERIVED, and it used to be a hard-coded four

Until 2026-08-14, `scripts/deploy/aws_live_probe.py` carried, at what was then line 179,
`ALARM_SUFFIXES = ("-errors", "-throttles", "-duration-p99", "-concurrency")` — a literal four,
against a stack that plans seven. `docs/deploy/PRE-APPLY.md` §3 recorded this as a finding
against that file in the page's own words: *"after the apply this probe will report 'All 4
alarms exist and none is in ALARM' while never having looked at the three that matter most"*.
**The three it could not see are the guard's, and the guard's are the ones wired to the stop.**

The literal is gone. `derive_alarm_suffixes()` reads every
`alarm_name = "${var.<name>}-<suffix>"` out of `infra/modules/demo-api/main.tf` and
`infra/modules/cost-guard/main.tf`, counts the `aws_cloudwatch_metric_alarm` blocks in each
file, and **raises** if it could not read the name of every one of them — a module that grows an
alarm the pattern cannot parse makes the probe refuse rather than quietly grade against a short
set. The result is then cross-checked against
`evidence/deploy/terraform-plan-furl.json`; a disagreement is refused, because one of the two is
describing a tree that does not exist and the modules are authoritative.

Measured on this tree, 2026-08-14, the derivation returns **seven**:

```
mainline-demo-api-concurrency          mainline-demo-api-invocations-burst
mainline-demo-api-duration-p99         mainline-demo-api-invocations-hourly
mainline-demo-api-errors               mainline-demo-api-log-ingestion
mainline-demo-api-throttles
```

and the plan cross-check agrees on all seven. A run whose expected set cannot be derived exits
`1` with the verdict **`EXPECTED ALARM SET UNDERIVABLE - NO READING TAKEN`** — a third
incident distinct from "AWS would not answer" and from "the answer is bad news", because its
first move is different again: fix the tree, not the credential.

---

### The measurement that happens the moment the stack exists

`scripts/deploy/aws_live_probe.py --alarms-only` answers *"do the alarms exist and what colour
are they"*. It does **not** answer the question this section's own §"What a state means" makes
unavoidable: **can these alarms see anything at all?**

That is what `scripts/deploy/post_apply_verify.py` is for. Run it immediately after an apply:

```bash
.venv/Scripts/python.exe scripts/deploy/post_apply_verify.py \
    --out evidence/deploy/verify/post-apply.json
```

Nine checks, in order, each either **satisfied** or **not satisfied with a reason** — there is
no third state, no skip, and a check that could not be attempted does not soften the exit code:

1. the Function URL, resolved from `terraform output` and never from a hostname in the file;
2. HTTPS reached with the certificate **verified** (there is no way to turn that off);
3. `GET /v1/health` answering `200` with `ok=true`;
4. the four beats producing `00000` then `23514 gate_closed_when_issued` then `P0001` then `00000`;
5. the admission beat carrying a **server-computed** `clearance_digest`, against a request body
   of `{}` that supplied no digest and no seed;
6. **every alarm the modules declare exists**, each still `treat_missing_data = "missing"`;
7. **the alarms can SEE the invocations the program just made** — see below;
8. the kill switch stops the demo: `429`, **with no body**;
9. the kill switch restores it: `200` again.

#### Why check 7 exists, and why it does not ask the alarms to be green

Every alarm here ships `treat_missing_data = "missing"`. That is **correct and is not relaxed
by this program or by anything it recommends** — it is the one word that makes
`INSUFFICIENT_DATA` mean *"nothing was published"* instead of rendering as `OK`, which is what
`notBreaching` did.

The consequence is that "the alarm is not in `ALARM`" is compatible with "this alarm has never
received a datapoint and cannot fire". An alarm over a metric with no datapoints is **not
evidence**, whatever colour a console paints it. So check 7 asks a different question: it
brackets its own invocations with a timestamp window, then reads
`cloudwatch:GetMetricStatistics` for each alarm's metric and dimensions over that window, and
refuses if a metric an invocation **does** publish came back empty.

It requires datapoints only for `Invocations`, `Duration` and `ConcurrentExecutions` — the
metrics an invocation actually publishes. `Errors` and `Throttles` publish only when one occurs
and `IncomingBytes` lags log delivery, so those are **reported and not demanded**: a check that
required an `Errors` datapoint could only pass on a system that was erroring, and a verifier
that can only pass on a broken demo is worse than no verifier. That scope is itself pinned by a
control in `tests/deploy/test_post_apply_verify.py`, so widening it turns a test red rather than
turning the demo red.

#### It has never run against a stack, and it has been proven anyway

As this was written, `aws lambda get-function --function-name mainline-demo-api` answered
`ResourceNotFoundException`. A verifier that has never failed has never discriminated, so every
refusal branch is demonstrated **firing** in `tests/deploy/test_post_apply_verify.py` against
synthetic AWS and HTTP answers — a missing function, a null Function URL, an unverified
certificate, a `200` health body that says `ok: false`, each of the four beats carrying the
wrong SQLSTATE, an admission with no `clearance_digest`, four alarms where seven were declared,
an alarm whose metric has no datapoints, a `--stop` whose effect did not land, and a `429` that
never cleared. Each demonstration is paired with a **mutant** of the program with that one check
removed, which does *not* refuse the same input — so a check that stops discriminating turns its
own control red.

Its dry reading against the unapplied account is
[`evidence/deploy/verify/post-apply-dry.json`](../../evidence/deploy/verify/post-apply-dry.json):
**0 of 9 satisfied, exit 1**, with each check naming why. The account id is masked as
`<account>` throughout, including the first-four/last-four form `kill_switch.sh` prints — eight
of twelve digits published forever is a narrower search, not a private one.

**The kill-switch checks are the ones to read carefully.** `--kill-switch dry` is the default:
it drives `--status` and `--dry-run` and **nothing else**, and it reports checks 8 and 9 as
**not satisfied**, because a stop nobody performed is a stop nobody has evidence for. Dry is
honest; it is not green. `--kill-switch live` additionally requires `--yes` and is the only path
that mutates a live function.

**Run against this account today it exits `3`:**

```
alarms        prefix 'mainline-demo-api' in ap-southeast-1
  DOES NOT EXIST     mainline-demo-api-errors
  DOES NOT EXIST     mainline-demo-api-throttles
  DOES NOT EXIST     mainline-demo-api-duration-p99
  DOES NOT EXIST     mainline-demo-api-concurrency
  finding       NO alarm whose name begins 'mainline-demo-api' exists in ap-southeast-1.
                This is NOT a quiet system: it is an unapplied stack, or the wrong region,
                or the wrong account. An empty table is not a green one.
VERDICT       ALARM FINDING - SEE calls[].finding
```

That is correct: the stack is not applied. **An empty list rendered as a calm, empty table is
the same class of lie as four green alarms on an idle function**, which is why zero alarms is
a finding with its own exit code rather than a short table.

### If you want to be paged: what the founder must actually click

~~`var.alarm_actions` takes a list of ARNs. Setting it is one variable~~ — but the reader only
becomes real at the end of a chain, and **every link has to be verified, not assumed**:

> **CORRECTED 2026-08-14 — THERE IS NO `var.alarm_actions` FOR A FOUNDER TO SET.** This root
> declares no such variable: `grep 'variable "alarm_actions"' infra/envs/demo/variables.tf`
> returns nothing, and every occurrence of `var.alarm_actions` in
> `infra/envs/demo/main.tf` is inside a **comment**. It is an input of the *module*
> (`infra/modules/demo-api/variables.tf:1151`), and the root hard-wires it to the guard's
> topic at `main.tf:586`. A founder who followed the struck sentence would search for a
> variable that does not exist and conclude the documentation was for a different tree.
>
> **The one variable that does exist, and is the actual answer to this heading, is
> `guard_notification_emails`** — `infra/envs/demo/variables.tf:619`, `type = list(string)`,
> `default = []`, passed to the guard at `main.tf:649`. Setting it creates the
> `aws_sns_topic_subscription.email` instances that are the fourteenth resource type the
> guard declares and the one the shipping plan creates **zero** of. Steps 2–4 below are
> exactly what that variable automates and what still has to be confirmed by hand.

1. ~~**Create an SNS topic *outside this stack*.**~~ **No longer necessary, and no longer the
   recommendation.** `infra/modules/cost-guard/` now creates the topic
   (`aws_sns_topic.guard`), its access policy, the responder Lambda that calls
   `PutFunctionConcurrency(0)`, and all three alarms — and it **exports `sns_topic_arn`**,
   which is what `var.alarm_actions` on the demo-api module is meant to be fed.

   ~~The remaining gap is that `infra/envs/demo/main.tf` has **no `module "guard"` block**, so
   `var.alarm_actions` is still `[]` and every alarm on the demo function is actionless.~~
   ~~Instantiating it is strictly better and is the open item.~~

   > **CORRECTED 2026-08-14. THE STRUCK SENTENCE ASSERTED THE ABSENCE OF A BLOCK THAT IS IN
   > THE TREE, AND IT DID SO IN THE PARAGRAPH THAT EXPLAINS THIS PAGE'S OWN RATCHET.** The
   > block was instantiated and this page was not re-read. It is at
   > **`infra/envs/demo/main.tf:631`** (`module "guard" {`), `source = "../../modules/cost-guard"`
   > at `:632`, under `count = var.enable_api ? 1 : 0` at `:633`. The wiring completes:
   > `local.guard_stop_topic_actions = try([module.guard[0].sns_topic_arn], [])` at **`:292`**
   > is fed to the demo-api module's `alarm_actions` at **`:586`**.
   >
   > So `var.alarm_actions` is **not** `[]` and the four alarms are **not** actionless. What
   > replaces "actionless" is not "armed" but *unknown at plan time*: `try()` over a counted
   > module yields unknown, so the plan renders `alarm_actions = (known after apply)` and the
   > `api_alarm_actions_armed` output reads `(known after apply)` at
   > [`terraform-plan-furl.txt:846`](../../evidence/deploy/terraform-plan-furl.txt). This is
   > recorded as not fixable at `infra/envs/demo/outputs.tf:229`.
   >
   > **A DIFFERENT LINK IN THIS CHAIN IS STILL UNVERIFIED, AND IT IS NOT THE INSTANTIATION.**
   > The guard's SNS topic policy admits `cloudwatch.amazonaws.com` under an `ArnLike` on
   > `aws:SourceArn` naming exactly the guard's **own three** alarms. None of these four
   > `demo-api` alarms is in that list, and this root passes them the guard topic anyway.
   > Whether they may publish rests on the policy's first statement and **only an apply plus a
   > real breach settles it** (`infra/envs/demo/outputs.tf:187–196`). If they may not, four
   > alarms carry an action SNS denies — which `describe-alarms` cannot distinguish from one
   > that delivers. **UNRESOLVED**, and it stays that way until an apply happens;
   > `evidence/deploy/cost/plan-shape.json` records both ARN sets so the question outlives
   > this paragraph.

   **The resource count moved when it landed, and this document no longer guesses it.**
   **`Plan: 24 to add, 0 to change, 0 to destroy.`** is what
   [`evidence/deploy/terraform-plan-furl.txt:843`](../../evidence/deploy/terraform-plan-furl.txt)
   records **today**, and that file is the authority.

   ~~Until 2026-08-14 this sentence quoted a shipping count of **11** and said that was what
   the artefact recorded "today".~~ **It was not, and the 11 was not a typo:** it was the
   count *before* `module "guard"` was instantiated, and it is still exactly
   `module.api[0]`'s contribution. **`module.guard[0]` creates the other 13** — counted from
   the artefact's own `will be created` lines, 11 + 13 = 24 — which is why arming the alarms
   was never the one-variable change the top of this section promises. The CloudFront
   configuration reads **35**
   ([`terraform-plan-cloudfront.txt:1219`](../../evidence/deploy/terraform-plan-cloudfront.txt)).

   *(The stale figure is described above rather than re-quoted verbatim. The ratchet scans
   for the literal `Plan: N to add` form and cannot tell a historical citation from a live
   one, and the one exemption it carries is deliberately keyed to an unrelated variant so
   that a stale shipping count cannot be laundered through it. Reproducing the old string
   here would either re-break the test or require abusing that exemption; the correction is
   what matters and it is preserved in full.)*

   The count here and in the other documents that quote it is checked against the artefact by
   `tests/deploy/test_cost_model.py::test_the_shipping_plan_count_in_the_docs_matches_the_plan_evidence`,
   which went red the moment the plan was regenerated and this document still said 11 — **and
   that is how this correction was found.** The ratchet worked; the page it was documented on
   was the page failing it.
2. **Subscribe an address** — `aws sns subscribe --protocol email --notification-endpoint …`.
3. **Click the confirmation link AWS emails to that address.** This is the step that is
   actually a decision, and the one that gets skipped.
4. **Verify it, do not believe it.** Until the link is clicked, `list-subscriptions-by-topic`
   returns the literal string `PendingConfirmation` where the `SubscriptionArn` would be.

> **An unconfirmed subscription is a control that looks present and is not.** The alarm has
> an action. The action names a topic. The topic has a subscriber. The console shows all
> three. **And nobody is notified** — AWS silently drops delivery to an unconfirmed endpoint.
> That is the identical shape of defect as an alarm threshold above its metric's ceiling, and
> `duration_p99`'s `lifecycle.precondition` exists one resource away to refuse exactly it.
>
> `--alarms-only` reads every referenced topic's subscriptions and prints
> `UNCONFIRMED - NOTIFIES NOBODY` against any that are pending. The endpoint itself is never
> printed — only its protocol and a SHA-256 prefix, because a subscription endpoint is
> somebody's email address.

5. **Add the topic and its subscriptions to the teardown checklist in §8**, which already
   carries the line.

**The first ten CloudWatch alarms are free.** Four alarms cost $0.00.

---

## 4. Cost, itemised, and the canary that is not here

The obvious AWS answer to "watch a URL" is a CloudWatch Synthetics canary. Priced:

| | |
|---|---|
| One canary at 5-minute intervals | 8 640 runs/month |
| Rate | $0.0012 per run |
| **Monthly** | **$10.37** |
| Everything else in this stack | ≈ $0.03 |

**$10.37 ÷ $0.03 ≈ 345. A canary would cost roughly three hundred times the entire rest of
the deployment, to check one URL.** (Against the ≈ $0.02 whole-stack figure in
[`RUNBOOK.md` §8.1](RUNBOOK.md#81--steady-state---002month) it is ≈ 500×. An earlier version
of this page and the comment at the head of `demo-health.yml` both say *thirty* times; the
division above is the arithmetic, and thirty is an order of magnitude short of it. The
workflow comment is not this document's to edit.)

It is refused, and the GitHub Actions cron replaces it at a lower sampling rate
with three properties a canary does not have: it asserts the four SQLSTATEs rather than a
status code; it fails **in public**, in the repository the judges are already reading; and it
costs nothing on a public repository.

| Line | Basis | USD/month |
|---|---|---|
| CloudWatch alarms | 4; first 10 free | 0.00 |
| CloudWatch dashboard | first 3 free | 0.00 |
| CloudWatch Logs | 7-day retention, far inside the 5 GB free ingest | 0.00 |
| GitHub Actions cron | public repository | 0.00 |
| CockroachDB RU for 24 gate runs/day | one rolled-back transaction each, inside the free allowance | 0.00 |
| CloudWatch Synthetics canary | **refused** — see above | ~~10.37~~ |
| **Total observability** | | **0.00** |

**Observability is free. The demo is not, and the two numbers must not be added in the
reader's head.** The whole stack's *steady-state* bill is ≈ $0.02/month
([`RUNBOOK.md` §8.1](RUNBOOK.md#81--steady-state---002month)). Its *adversarial* bill —
a Function URL with `authorization_type = NONE`, bounded only by an account concurrency
ceiling of 10 — is **USD 11,538–33,257 over 30 days**, and the arithmetic is in
[`COST-BOUND.md`](COST-BOUND.md). Nothing on this page bounds that number; the `-concurrency`
alarm at 8 only *notices* it, and only if somebody runs §3's reader.

---

## 5. The dashboard and the logs

**Dashboard** — one, named for the function, declared by the same module: invocations,
errors, duration with the p99 threshold drawn on it as an annotation, concurrent executions
with the abuse tripwire drawn on it, and the four alarm widgets. Drawing the thresholds as
annotations is the point: a duration graph without its alarm line requires the reader to
remember the number.

**A dashboard is not a reader either.** It renders when somebody opens it. Everything §3 says
about who is watching applies here unchanged.

**Logs** — CloudWatch Logs, `retention_in_days = 7`.

Seven days is chosen, not defaulted. It covers the whole judging window with room to spare,
keeps ingest far inside the 5 GB free tier, and — the part that matters for a public demo —
means nothing a judge's browser generated is retained a week after they generated it. `never
expire` is the AWS default and would quietly keep a request log forever for a demo that
exists for eight days.

**The handler logs no DSN, no password, and no query string that could carry one.**
`redact()` in `scripts/deploy/cloud_chain.py` (defined at `:219`) is the single chokepoint
for anything that could — written here as a path plus a function because
`scripts/deploy/cloud_chain.redact` is neither a file nor an importable dotted name; the
module path is `scripts.deploy.cloud_chain.redact`, as `scripts/deploy/__init__.py:20`
writes it — and
`scripts/deploy/__init__.py` states the rule for the whole package.
`scripts/deploy/local_furl.py` prints the DSN through `redact_dsn()` for the same reason, and
it is the one line of that banner most likely to be on a screen share.

---

## 6. What a judge sees when the database is unreachable

**Never a blank screen, and never a lie.** What they actually see depends on what the console
build carried, and the three cases are enumerated in
`verticals/mainline/apps/console/src/app/source-select.ts`:

| The build carries | What loads | Badge |
|---|---|---|
| a live API **and** a bundle | LIVE, with a control that switches to REPLAY | `LIVE` → `REPLAY` when switched |
| a bundle only | the signed EvidenceBundle, no backend in the request path | `REPLAY` |
| a live API only | the live surfaces; a database failure renders as a named transport failure on each one | `LIVE` |
| neither | every surface renders its own **NO SOURCE** panel | — |

The badge is read off `transport.describe().mode`, on the object that actually holds the
bytes (`src/app/HonestyChrome.tsx:58`), not off the selection — so it cannot say `LIVE` about
bytes that came from a bundle.

### There is no automatic failover, and that is the honest design

A console that silently switched to the bundle when the API failed would be showing a judge
**yesterday's data under a live badge**. `source-select.ts` therefore makes the choice from
the build and from `?source=`, which can only select between sources the build already
carries. When the database is unreachable, a LIVE build shows the failure — the API answers
`503 database_unreachable` with the SQLSTATE in the body, and `src/data/transport.ts`
classifies a non-2xx with no parseable envelope as a `status` transport failure and shows it.
The judge then switches to REPLAY themselves, with the control or with
`#/gate?source=replay`, and the badge changes because the transport did.

### The build that ships must be the demo build — a cross-domain note

The `dist/` committed at `verticals/mainline/apps/console/dist` was **not** built with
`--mode demo`: `grep -o 'bundle/' dist/assets/index-*.js` finds nothing, while
`grep -o 'NO SOURCE'` finds the panel. A console built with neither source shows that panel
on every surface — the honest rendering, and not the one a judge should get. The build that
ships must be the one [`console-build.md`](console-build.md) §1 specifies:

```bash
VITE_MAINLINE_API_BASE=/ pnpm exec vite build --mode demo
```

`.env.demo` already supplies `VITE_MAINLINE_BUNDLE_URL=./bundle/`, so that command produces
the first row of the table above: LIVE by default, REPLAY one click away, both on one origin.
**This is a cross-domain note, not a change this page can make** — the console build belongs
to the bundle domain.

`scripts/deploy/local_furl.py --bundle-dir …` stages the bundle under `/bundle/` in a
temporary copy of the web root so the REPLAY surface can be exercised locally before that
artefact exists.

---

## 7. What is NOT observed, and should be said

* **CockroachDB Cloud metrics are not scraped.** Basic exposes a metrics endpoint; nothing
  here reads it. The demo's database health is inferred from `/v1/health` answering, which is
  a weaker statement than "the cluster is healthy" and is written here so nobody reads more
  into a green cron than it carries.
* **The spend cap is the real backstop on the database side, and only there.**
  `spend_limit` is a hard ceiling: the cluster stops before the bill grows. It is a cost
  control, not an alarm, there is no alert on approaching it — and it bounds **nothing** on
  the AWS side, because the flood target in `COST-BOUND.md` is the static web tree, which
  never touches the database.
* **There is no CloudFront to watch.** DECISION D1 removed it: this account is under an AWS
  verification hold that refuses new distributions, and the demo URL is a Lambda Function
  URL. A previous version of this page described CloudFront 4xx/5xx rates; there is no
  distribution and that paragraph is gone.
* **No alarm can tell you the gate stopped refusing.** No CloudWatch metric expresses "a
  `CHECK` constraint is still attached". Only the four-beat assertion can, which is why §2
  makes it hourly and why `demo_acceptance.py` makes it a deploy gate. That is the one claim
  in the submission, and it is the one thing metrics cannot see.
* **Nothing watches the Bedrock path.** The recall agent's embedding calls are outside the
  demo's request path; `evidence/deploy/aws-live.json` records that they execute, and nothing
  monitors them continuously.
* **Nothing watches the spend in real time.** The three AWS Budgets on this account are set
  at $10, $5 and $1, are **already breached** by unrelated projects, and carry
  `{"Actions": []}` — they notify and stop nothing. Cost Explorer lags 8–24 h. See
  [`COST-BOUND.md`](COST-BOUND.md) §3.6 and §4.

---

## 8. Teardown checklist

Run after judging closes. **Order matters**: the database credential is revoked before the
infrastructure that used it is destroyed, so nothing is left holding a live login.

```bash
# 1. Revoke the judge credential on the Cloud cluster
psql "$COCKROACH_DSN" -c 'DROP USER mainline_judge'

# 2. Revoke the API credential
psql "$COCKROACH_DSN" -c 'DROP USER mainline_api'

# 3. Destroy the AWS stack (filters on the project tag and refuses otherwise).
#    Its step 3 ALSO deletes the SSM parameter /mainline/demo/cockroach_dsn, and refuses
#    any parameter name that is not under /mainline/. Do not delete it separately: an
#    earlier version of this checklist did, naming a parameter (/mainline-demo/dsn) that
#    has never existed, so the step reported success while deleting nothing.
bash scripts/deploy/teardown.sh

# 4. Confirm the parameter is gone — assert the TYPE, never --with-decryption
aws ssm describe-parameters --region ap-southeast-1 --query 'Parameters[].Name' \
    --profile mainline-dev
#    expect: []

# 5. Confirm nothing survives that carries the prefix
aws resourcegroupstaggingapi get-resources \
    --tag-filters Key=project,Values=mainline \
    --profile mainline-dev --region ap-southeast-1

# 6. Confirm the alarms are gone, with the same reader that watched them
.venv/Scripts/python.exe scripts/deploy/aws_live_probe.py --alarms-only
#    expect exit 3 and four DOES NOT EXIST lines — the pre-apply reading, restored
```

Then, by hand, because each is a deliberate decision rather than a script's:

- [ ] **Set `demo_url` back to `UNRESOLVED`** in `docs/submission/SUBMISSION.json`, so the
      health cron reverts to the "not deployed" red rather than failing against a URL that no
      longer exists. A permanently red scheduled workflow trains people to ignore a red
      scheduled workflow.
- [ ] **Unset the `DEMO_URL` repository variable** if one was ever set as an override.
- [ ] **Rotate `CC_API_KEY`** — the Cloud service-account key. §4 of
      [`JUDGE-PACK.md`](JUDGE-PACK.md) records that this key can `create_database` on the
      cluster; it was used for measurement during the build and should not outlive it.
- [ ] **Drop the `mainline_demo` database**, or delete the cluster, once the evidence files
      are archived. Everything in it is synthetic, so this is housekeeping rather than a data
      obligation.
- [ ] **Confirm the CloudWatch log group is gone.** `teardown.sh` removes it; a log group
      that outlives its function is the most commonly orphaned resource in an AWS teardown,
      and it keeps costing.
- [ ] If `alarm_actions` was wired to SNS, **delete the topic and its subscriptions** — both.
      A confirmed email subscription outlives the topic's usefulness and keeps a stranger's
      address in an account they have forgotten about.

### What teardown will not touch

The AWS account holds four unrelated projects — including a CloudFront distribution belonging
to none of them. Everything this deployment creates carries the `mainline-demo-` name prefix
and the tag `project=mainline`, and `teardown.sh` filters on the tag and **refuses to
proceed** if the filter returns resources it did not expect. Step 5 above is the independent
confirmation of that, run after the fact rather than trusted in advance.
