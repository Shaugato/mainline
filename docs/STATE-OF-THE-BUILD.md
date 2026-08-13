<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: CC-BY-4.0
-->

# STATE OF THE BUILD

**Re-certified 2026-08-13 by the re-verification agent, at commit `802e7b7`, after the
second (twenty-five-worker) wave.** Deadline 2026-08-18.

This agent was instructed to assume the previous wave failed until it proved otherwise.
Every number below was produced by a command this agent ran itself, today, on this
machine or against the live account. No worker self-report is repeated here unless this
agent re-ran the measurement and got the same answer. Where a claim did not survive, it
says so and names what replaced it.

The one paragraph a reader in a hurry needs:

> **The gate proof is still PROVEN and caveat-free. The Terraform plan now applies —
> `reserved_concurrent_executions = -1` removed the one unappliable call, all 44
> preconditions pass, and all four alarms can physically reach their thresholds. The
> anonymous write hole is CLOSED and this agent proved it by re-opening it. But the
> deploy is still a NO-GO on two grounds: the headline demo answers `200` with its own
> verdict reading `NOT PROVEN` against the seed the deployment actually uses, and the
> worst-case cost is bounded by nothing that exists in this repository. The repository is
> PUBLIC, there is no demo URL, and there is no video.**

---

## How to read this

| | meaning |
|---|---|
| **PROVEN** | this agent ran it today and watched it succeed; the artefact is named |
| **BUILT-BUT-UNPROVEN** | the code exists and is complete, but nothing has demonstrated it end to end |
| **BROKEN** | it exists and it does not work; the cause is named at `file:line` |
| **NOT BUILT** | it does not exist |

A red CI lane is not automatically bad. The discipline is that a lane reporting a true
incompleteness **stays red with a sharper message**. §5 separates the reds that are
defects from the reds that are honest instruments.

---

# 0 · THE DEPLOY DECISION — **NO-GO**

The founder authorised the apply conditional on this verification returning GO. It
returns **NO-GO**. The two blockers from the first verification are both **CLEARED**. Two
different blockers replace them. Both are measurements, not judgement calls.

## 0.1 · Scorecard against the five GO conditions

| # | GO condition | Verdict | Evidence |
|---|---|---|---|
| 1 | the plan can physically apply | **PASS** | 11 to add, `applyable: true`, 44/44 checks pass, `reserved_concurrent_executions = -1` |
| 2 | the demo answers 200 on the production path | **PASS in letter, FAIL in substance** | 200 through the real handler on `dict_row` — but `verdict: NOT PROVEN` against the deployed seed |
| 3 | anonymous callers cannot mutate | **PASS** | four POSTs → `423`, and the guard is falsifiable — see §2 |
| 4 | every alarm can reach its threshold | **PASS** | 0/0/12000<15000/8<10 — see §3.3 |
| 5 | worst case bounded by a mechanism **in code** | **FAIL** | nothing in this repository bounds it; §4 |

**Two independently sufficient blockers: condition 2 in substance, and condition 5.**

## 0.2 · BLOCKER 1 — the demo returns 200 and reports `NOT PROVEN` on the deployed seed

`POST /v1/demo/gate-run` reaches the four beats and answers `200`. Its own verdict field
reads `NOT PROVEN`, because **beat 4 fails a foreign key against the seed the deployment
actually runs on**. A judge who presses the one button the demo exists for reads the
product failing.

Measured through `mainline_demo_api.app.handler` — the real Lambda entry point, on a
`db.connection()` opened with `row_factory=dict_row` — against a local database carrying
the cloud demo seed (`dec0de00-…`, `external_ref DEMO-PTW-0001`) and the `deploy_chain`
marker, with **exactly the environment `terraform plan` publishes** (`MAINLINE_DEMO_PERMIT_ID`
and nothing else):

```
POST /v1/demo/gate-run  ->  200   VERDICT = NOT PROVEN
   beat 1 read                     outcome=read       sqlstate=00000  matched=True
   beat 2 merge                    outcome=refused    sqlstate=23514  matched=True
   beat 3 projection_drift_attack  outcome=refused    sqlstate=P0001  matched=True
   beat 4 admit                    outcome=refused    sqlstate=23503  matched=False
   failures: ["beat 4 (admit): expected {'outcome':'admitted','sqlstate':'00000'},
              observed outcome='refused' sqlstate='23503'
              constraint='disposition_signer_credential_id_fkey'"]
```

### The cause, pinned to the byte

`gate_run._DISPOSITION_SQL` supplies `signer_credential_id = _sha("cred", "signer")`. The
two seeders mint different credential ids for their signers, and only one of them matches:

```
gate_run passes  signer_credential_id       = 487adc50409e8811b1f12055ee183ce9d8548f11262807d01776fb67cd09c765
gate_run passes  countersigner_credential_id= 916b6121c8188a00ec5deff08e61ea034a58ed16d8ec85115c40cf7cb049d7fb

scripts/proof/gate_refusal.py  (the TEST fixture's seeder)
   proof.signer          487adc50409e8811b1f12055ee183ce9d8548f11262807d01776fb67cd09c765  <== MATCHES
   proof.countersigner   916b6121c8188a00ec5deff08e61ea034a58ed16d8ec85115c40cf7cb049d7fb  <== MATCHES

verticals/mainline/db/seeds/demo/demo_world.sql  (the CLOUD seeder — digest('mainline-demo/credential/…'))
   demo.signer           ff356d1461921438bbbc5d644db8793669cb948a46bddc2e8fb5ebef959bdf0c
   demo.countersigner    8d7b089f4c0aec7d890810a5aca3ebd9f57e2ae8786e2749e576200019b18ebe
```

`scenario.from_env()` defaults `signer_sub` to `"demo.signer"`, which is the person
`demo_world.sql` seeds — so the *person* resolves and the *credential* does not.

### Why 291 green tests cannot see it

`verticals/mainline/apps/demo-api/tests` passes **291 passed, 1 skipped** on this machine,
including `test_gate_run_verdict_is_proven`. It passes because the fixture seeds the
history with `scripts/proof/gate_refusal.py`, whose credential digests are the ones
`gate_run` expects. **No test in this repository runs the demo against `demo_world.sql`.**
The suite proves the demo works against the seeder it shares constants with, and says
nothing about the seed the Lambda will meet.

This is the *permit-id near-miss pattern, recurring*: the previous wave closed the named
instance (`MAINLINE_DEMO_PERMIT_ID`, now published by Terraform at
`dec0de00-0006-4000-8000-000000000001`) and did not close the class. Three of the four
identifiers `scenario.from_env()` reads are still unpublished by the module:

| variable | published by Terraform? | falls back to | load-bearing? |
|---|---|---|---|
| `MAINLINE_DEMO_PERMIT_ID` | **yes** | `demo_uuid("permit")` | yes — the guard arms on it |
| `MAINLINE_DEMO_SITE_ID` | no | `demo_uuid("site")` = `c333eb17-…` | **no** — projected away by `fn_disposition_project` (measured: setting it alone changes nothing) |
| `MAINLINE_DEMO_SIGNER_SUB` | no | `"demo.signer"` | **yes** — decides beat 4 |
| `MAINLINE_DEMO_COUNTERSIGNER_SUB` | no | `"demo.countersigner"` | **yes** — decides beat 4 |

The fix is one of: seed the credential rows `gate_run` derives, derive the credential id
from the signer the way `demo_world.sql` does, or publish the signer variables and seed to
match. **Which one is a decision for the owner of `gate_run.py` and `demo_world.sql`, not
for this agent**, because all three change what the demo asserts.

## 0.3 · BLOCKER 2 — nothing in this repository bounds the bill

See §4. In one line: the only bound in force is an **AWS account concurrency quota of 10
that nobody in this repository chose and that AWS marks `Adjustable: true`**. Worst case
**USD 33,250 for thirty days**. The in-code per-response ceiling refuses zero of the 75
served objects. `docs/deploy/COST-BOUND.md` is honest and thorough and it is a document; a
bound in a document is not a bound.

## 0.4 · What the first NO-GO blocked, and is now CLEARED

| First-wave blocker | Status today | Proof |
|---|---|---|
| the plan cannot apply — `PutFunctionConcurrency` refused on a ceiling of 10, five resources in | **CLEARED** | `reserved_concurrent_executions = -1`; the provider makes no such call; `applyable: true` |
| the headline demo route returns `500` (`KeyError: 0`) | **CLEARED** | `200` through the real handler on `dict_row`; the row-factory ratchet finds **zero** findings under `mainline_demo_api/` |
| the write guard armed at an id no caller would send | **CLEARED, and falsifiably** | §2 |

---

# 1 · THE DEMO — the production path

**PROVEN that it answers, on the path a Lambda takes.** Not a test double: this agent
imported `mainline_demo_api.app.handler`, let `db.connection()` open the connection
itself, asserted `conn.row_factory` is `dict_row`, and sent a payload-format-2.0 event.

```
production connection row_factory = <function dict_row at 0x…>
POST /v1/demo/gate-run   -> 200
GET  /v1/permits/{id}    -> 200
GET  /v1/ledger          -> 200
GET  /v1/audit           -> 200
GET  /v1/health (cold)   -> 200  ok=True
```

Against the *proof* seeder's history with all four scenario variables set, the same call
returns `200` with **`VERDICT = PROVEN`, `failures: []`, beat 4 `admitted` `00000`**. So
the four beats are correct code; §0.2 is a seed/constant contract defect, not a logic one.

## 1.1 · The row-factory sweep — **CLEAN on the production path**

`scripts/qa/row_factory_ratchet.py` exits 0. **Zero findings under
`verticals/mainline/apps/demo-api/src/mainline_demo_api/`.** 16 findings remain across the
tree: 13 in test modules, 1 in `mainline_custody_patrol/collect.py:376` (`both_shapes`),
2 in `scripts/deploy/capture_demo_bundle.py:870,875` (`mutates_connection_row_factory`).

## 1.2 · **BROKEN — the warm connection is left in a state `db.py` does not own**

A defect this agent found by running the sequence a console performs, and which no test in
the repository asserts against.

`db.py:306` opens every production connection with `autocommit=True`.
`transitions._prepare` (`transitions.py:293-294`) and `transitions._demo_gate_run`
(`transitions.py:1032-1033`) set `conn.autocommit = False` on that **shared module-scope
connection and never restore it**. `handle_transition`'s contract is that it leaves no
transaction in progress — and it honours that — but the invariant the rest of the module
relies on is the *flag*, not the transaction.

`health.py:106` states the assumption in as many words: *"`db._open` opens with
`autocommit=True`, so the failed statement leaves no transaction to roll back."* Health
deliberately runs a statement that may raise `42P01` and recovers from it. Under
`autocommit=False` that recovery is gone.

Measured, one warm process, real handler:

```
health (cold)                  -> 200   autocommit=True  tx=IDLE
POST /v1/demo/gate-run         -> 200   autocommit=False tx=IDLE      <-- leaked here
GET  /v1/permits/{id}          -> 200   autocommit=False
GET  /v1/ledger                -> 200   autocommit=False
GET  /v1/health                -> 503   [25P02] current transaction is aborted
POST /v1/checks/{id}/disposition -> 423 (guard)          autocommit=False   <-- leaks here too
GET  /v1/health                -> 503   [25P02]
```

**On a database that carries the `deploy_chain` marker — i.e. the deployed cluster —
this does not produce a 503.** It produces something quieter: health answers `200` and the
connection is left `INTRANS`, an idle-in-transaction session held across warm invocations
and never committed or rolled back. That is precisely the condition `transitions.py:1118`
warns about in its own comment — *"inheriting an idle-in-transaction session is how a demo
starts answering 40001 to requests that never conflicted with anything."*

So the deployed symptom is a pinned read snapshot and a `40001` amplifier that **the
health alarm cannot see**, and the dev symptom is a hard `503`. Reads survive; health and
any statement that legitimately fails do not.

The fix is at the cause and is small — restore `autocommit` on the way out of
`handle_transition`, after the rollback the function already performs — but it is
`transitions.py` and it changes the transaction discipline of the write path, so it is
named here rather than patched by a verifier. **It is not a GO blocker on its own; it is a
correctness defect on the artefact being deployed.**

Note the shape: `row_factory_ratchet.py` has a rule named `mutates_connection_row_factory`
for exactly this defect class applied to `row_factory`, and no rule for `autocommit`. The
instance was closed; the class was not.

---

# 2 · THE GUARD — anonymous callers cannot mutate. **PROVEN, and falsifiable.**

All four committing kernel POSTs, driven anonymously through the real handler at the
seeded demo subject, on the production `dict_row` connection:

```
merge_permit         -> 423  demo_subject_write_protected
suspend_permit       -> 423  demo_subject_write_protected
materialise_checks   -> 423  demo_subject_write_protected
sign_disposition     -> 423  demo_subject_write_protected
```

Reproduced identically against the cloud seed (`dec0de00-0006-…`) with only
`MAINLINE_DEMO_PERMIT_ID` published — the deployed configuration. And
`verticals/mainline/apps/demo-api/tests/test_demo_guard_anonymous.py` is **13/13 green**
against a live CockroachDB v26.2.5 node.

## 2.1 · A green test proves nothing until it can go red. Two plants.

**Plant A — remove the fail-closed branch only.** `_demo_guard` step 3
(`if _demo_subject_is_established(conn, scenario): return None`) replaced by an
unconditional `return None`, i.e. the code exactly as it stood before this wave:

```
1 failed, 12 passed
FAILED test_the_four_posts_are_refused_with_the_permit_id_variable_unset
  Got: {'merge_permit': (409, None), 'suspend_permit': (409, None),
        'materialise_checks': (200, None), 'sign_disposition': (200, None)}
```

**`materialise_checks` → 200 and `sign_disposition` → 200.** That is the near-miss
reproduced on demand: an anonymous caller closing the very obligation the gate proof turns
on, on a URL with `authorization_type = NONE`. The lane sees it.

**Plant B — disarm the guard entirely** (`_mutation_allowed()` → always true):

```
7 failed, 6 passed
```

Both plants reverted; `transitions.py` restored byte-for-byte (the diffstat returned to
`146 insertions(+), 13 deletions(-)`), and the suite returns to 13/13.

## 2.2 · What the guard now closes, and what it still rests on

`_demo_guard` fails closed: a write path that cannot establish which subject is the
protected one refuses rather than permits. That is a **class**, not an instance — it also
catches a mistyped override, a deploy pointed at the wrong database, and a hand-edited
Lambda environment. The deployed configuration additionally arms it correctly:
`terraform plan` publishes `MAINLINE_DEMO_PERMIT_ID = dec0de00-0006-4000-8000-000000000001`,
the id the seed actually minted.

---

# 3 · THE PLAN — **PROVEN it can apply. Not applied.**

`terraform init` / `validate` / `plan` re-run by this agent today, Terraform v1.14.8,
AWS provider v6.58.0, profile `mainline-dev`, account `022950218246`. **No `apply` was
run and no mutating AWS call was made.**

> Note for whoever reproduces this: `terraform plan` under 1.14 refuses to run after
> `init -backend=false`, which is how the committed evidence was produced. This agent
> copied `infra/` to a scratch directory, removed `backend.tf` there, and planned against
> an empty local state. The repository was not touched.

```
Success! The configuration is valid.
Plan: 11 to add, 0 to change, 0 to destroy.
applyable = true   complete = true   errored = false
44 check blocks, all pass
```

## 3.1 · The eleven addresses

```
module.api[0].aws_cloudwatch_dashboard.this[0]
module.api[0].aws_cloudwatch_log_group.this
module.api[0].aws_cloudwatch_metric_alarm.concurrency
module.api[0].aws_cloudwatch_metric_alarm.duration_p99
module.api[0].aws_cloudwatch_metric_alarm.errors
module.api[0].aws_cloudwatch_metric_alarm.throttles
module.api[0].aws_iam_role.this
module.api[0].aws_iam_role_policy.dsn_access
module.api[0].aws_iam_role_policy_attachment.basic_execution
module.api[0].aws_lambda_function.this
module.api[0].aws_lambda_function_url.this
```

**Diff from the committed plan artefact: none.** Address sets identical; every audited
attribute — `reserved_concurrent_executions`, `timeout`, `memory_size`, `architectures`,
`runtime`, `handler`, `environment`, `authorization_type`, `cors`, all four thresholds,
`retention_in_days` — byte-equal to `evidence/deploy/terraform-plan-furl.json`. The
committed artefact replays.

## 3.2 · `reserved_concurrent_executions` — the first blocker, cleared

`-1`. The provider issues no `PutFunctionConcurrency`, so the sixth of eleven API calls
that previously failed against `AccountLimit.ConcurrentExecutions = 10` is not made at
all. `min(20, 10) = 10` — the account already capped this function at 10, so removing the
reservation **removes an unappliable call and changes no cost ceiling**. It does not raise
exposure and it does not lower it.

## 3.3 · Every alarm can physically reach its threshold — **PROVEN**

| alarm | metric · stat | threshold | ceiling the metric cannot exceed | reachable |
|---|---|---|---|---|
| `-errors` | `Errors` · Sum | `> 0` | none (unbounded counter) | **yes** |
| `-throttles` | `Throttles` · Sum | `> 0` | none (unbounded counter) | **yes** |
| `-duration-p99` | `Duration` · p99 | `> 12000 ms` | `timeout` = 15 s = 15000 ms | **yes**, 12000 < 15000 |
| `-concurrency` | `ConcurrentExecutions` · Max, **no `FunctionName` dimension** | `> 8` | account quota = 10 | **yes**, 8 < 10 |

Both non-trivial cases are enforced by `precondition` blocks in the module, not by
comment: `duration_p99_threshold_ms < timeout * 1000` and
`concurrency_alarm_threshold < account_concurrency_ceiling`. Both appear in the 44 passing
checks. The concurrency alarm deliberately carries no `FunctionName` dimension, because at
`reserved_concurrent_executions = -1` Lambda does not dependably publish the per-function
metric — an alarm on a metric that is never emitted is the same defect as a threshold
above a ceiling.

**These alarms REPORT. None of them stops anything.** See §4.

## 3.4 · IAM — least privilege, confirmed from this agent's own plan

```json
{"Sid": "ReadTheDemoDsnParameter",
 "Action": "ssm:GetParameter", "Effect": "Allow",
 "Resource": "arn:aws:ssm:ap-southeast-1:022950218246:parameter/mainline/demo/cockroach_dsn"}
{"Sid": "DecryptThatParameterAndNothingElse",
 "Action": "kms:Decrypt", "Effect": "Allow", "Resource": "*",
 "Condition": {"StringEquals": {
    "kms:EncryptionContext:PARAMETER_ARN": "arn:aws:ssm:…:parameter/mainline/demo/cockroach_dsn",
    "kms:ViaService": "ssm.ap-southeast-1.amazonaws.com"}}}
```

`Resource: "*"` on `kms:Decrypt` is **stricter** than naming the key, because the two
conditions bind the decryption to one parameter ARN through one service. No DSN appears in
the plan, the state or any output. `MAINLINE_DSN_PARAM` carries a name; never a value.

## 3.5 · The Function URL

`authorization_type = NONE`, `cors = []`, `invoke_mode = BUFFERED`. The handler sets no
`access-control-allow-origin`, so the module and the runtime now agree — under DECISION D1
the console and the API are one origin and no CORS is needed. Reachable by anyone;
readable by script from an arbitrary page only if a `cors` block is added. It is not.

---

# 4 · THE COST BOUND — **what is in code, and what is not**

## 4.1 · Bounds that exist in code

| mechanism | where | what it bounds | binding today? |
|---|---|---|---|
| `log_retention_days = 7` | `infra/envs/demo` | log **storage** | yes |
| `timeout = 15`, `memory_size = 512` | module | cost of **one** invocation | yes |
| `DEFAULT_MAX_RESPONSE_BYTES = 2 MiB` + `413` | `static_site.py:170`, `app.py::_too_large` | **bytes per response** | **NO — see below** |
| gate-run runs in one transaction that ends in `ROLLBACK` | `gate_run.py` | database writes | yes, and irrelevant to a flood |
| CockroachDB Basic `$25` cap | Cloud console | the **database** | yes, and the database is not the target |

**The per-response ceiling refuses nothing.** Measured over the deployable package:

```
web/ files      : 75    bytes 3,571,990
source maps     : 18    bytes 2,586,960   (72.4% of the served tree)
largest served  : web/assets/index-BjAGxrVJ.js.map   1,554,168 B
in-code ceiling : 2,097,152 B
served objects above the ceiling: 0
```

The ceiling sits **above** the largest object the origin can emit. It is a real mechanism,
correctly built, wired into the handler, and it is not a bound on anything that exists.

## 4.2 · What is unbounded

**Request rate. Total egress. CloudWatch Logs ingestion.** There is no throttle, no WAF,
no shared secret, no per-IP limit, and `authorization_type = NONE`. The only thing bounding
the flood is the **account's Lambda concurrency quota of 10** — measured
(`aws lambda get-account-settings`, `aws service-quotas get-service-quota --quota-code
L-B99A9384`), `Adjustable: true`, and chosen by AWS rather than by anyone here.

## 4.3 · The honest worst case, under the bounds that actually exist

**USD 33,250 for thirty days** (decimal convention, 100 ms invocations — the conservative
headline). Best case of the same flood, 300 ms invocations: **USD 11,700**.
`docs/deploy/COST-BOUND.md` derives this from the Pricing API, checks the tiering a second
time in SQL against a local CockroachDB node, and lands within 1.6 % of the 31-agent
audit's independent figure. This agent re-measured its three load-bearing inputs (the
concurrency ceiling, the largest served object, the served tree) and they hold.

**Every lever that would change this is documented and none is implemented:** L2 strip
source maps (built, off by default — the maps are still in the package), L3 lower the
handler cap to 512 KiB (the constant still reads 2 MiB), L4 per-IP throttle (absent from
`app.py`), L5 shared-secret gate (URL is `NONE`).

`COST-BOUND.md` says of itself: *"decision material. Nothing in this document has been
applied."* That is accurate, and it is why condition 5 fails.

> One correction this agent made to the record: `evidence/tool-usage/aws-services.json`
> claimed *"reserved_concurrent_executions caps the bill rather than reporting it."* That
> is false — it is `-1`. The row now says what actually bounds the bill, which is nothing
> in this repository.

---

# 5 · THE GATE PROOF — **PROVEN, caveat-free**

`scripts/proof/gate_refusal.py`, run by this agent today against the local pinned node.
Verbatim:

```
cluster       CockroachDB CCL v26.2.5 (x86_64-pc-linux-gnu, built 2026/07/28 18:56:00, go1.25.5)
database      w_qr_gate_refusal_proof
chain         271/271 applied, 0 failed, 58.553s
reached 0115  True
unproduced    (none) — every relation this tree references has a producer
PROJECTION    10/10 held · open_blocking 0->1 · gate_epoch 0->1 · outbox 'check_opened' severity 4 (client supplied 0)
REFUSAL       REFUSED [23514] gate_closed_when_issued (reported)
DRIFT         REFUSED [P0001] mainline.fn_permit_merge_gate (parsed)
ADMISSION     ADMITTED [00000]
caveats       (none) — nothing in this run is unproven-but-tolerated
VERDICT       PROVEN
evidence      evidence/gate-refusal/proof-20260813T042541Z.json
```

The proof builds its own database from the migration chain, so it is independent of every
scratch fixture in this repository. **This remains the strongest falsifiable result in the
build.**

---

# 6 · CI — measured warm, dispatched by this agent

Seventeen workflows dispatched at `0921e3b` / `2c35333` and read with
`gh run view --log-failed` while the logs were warm. `nightly-differential` is scheduled
and was not dispatched.

| lane | conclusion | classification |
|---|---|---|
| `submission` | **success** | |
| `boundary` | **success** | |
| `supply-chain` | **success** | |
| `claims` | **success** | |
| `cloud-verify` | **success** | |
| `console` | **success** | |
| `judge-pack` | **success** | |
| `release-proof` | **success** | |
| `skills` | **success** | |
| `mutation-ratchet` | **success** | |
| `aws-evidence` | **success** | **was failing; fixed by this agent — see §6.1** |
| `schema` | failure | **intentional and precise** — RED BY DESIGN, 2 missing producers named |
| `db` | failure | **intentional, collateral** — same two producers, `0058_blocking_check` `42P01` |
| `db-schema` | failure | **intentional and precise** — mi-ratchet: `MI27 is pending but its tests pass — promote it` |
| `custody-chain` | failure | **intentional and precise** — 7/16 checks bound; 7 named modules deferred to `verify-crypto` |
| `demo-health` | failure | **intentional and precise** — "no demo URL is published; red because the demo is not deployed, not because it is broken" |
| `ci` | failure | **mixed** — see §6.2 |

**11 green / 17 measured**, up from the recorded 7/13. Every red carries a message a judge
can act on; none is a lane that went quiet.

## 6.1 · `aws-evidence` — a real regression, fixed at the cause

`CEN-ANCHORS` caught two citations in `evidence/tool-usage/aws-services.json` that address
`infra/modules/demo-api/main.tf` **by line number**. This wave moved 1372 lines of that
file, so both silently retargeted:

```
aws_lambda               main.tf:310 -> 333   "authorization_type = var.url_authorization_type"
aws_ssm_parameter_store  main.tf:192 -> 215   "actions = [\"ssm:GetParameter\"]"
```

Both quoted lines still exist verbatim; only their addresses moved. The **index** was
corrected — `must_contain` and `line_text` untouched, the scanner unmodified — and the
false cost claim in the same row was corrected (§4.3). Re-measured:
**`evidence/aws` PASSES, 896 assertions across 40 of 40 declared invariants.** The lane is
green warm.

## 6.2 · `ci` — four jobs, and what each one is

`8629 passed, 1003 skipped, **8 failed**` in the `--crdb=none` suite, measured warm at
`1738e65` **after** this agent's CRLF fix. It was `8628 passed, 9 failed` before it, and
the one that moved is `test_ruff_ratchet.py::test_the_ratchet_passes_on_the_real_tree` —
so the fix is confirmed at the test level as well as at the `ruff format` step.

| job | classification |
|---|---|
| `PL-2 — the red run is recorded` | **intentional** — the ADR asks for a `db` run in which CONFORMANCE itself went red; CONFORMANCE has never executed (it stops at the missing producer), so the field stays UNRECORDED rather than being filled with a different observation |
| `ruff format · the counted lint ratchet` | **regression, fixed by this agent** — §6.3 |
| `pytest --crdb=none` | **mixed** — 5 intentional, 2 fixed, 2 real defects — below |
| `RED BY DESIGN, and it must stay red` | success — the inverted lane holds |

The eight pytest failures that remain (the ninth was the CRLF ratchet, now green):

* **5 × `tests/integration/custody/test_k2_exit.py`** — K2.1/K2.2/K2.4/K2.5/K2.6 not met,
  each naming its missing artefact or matrix row. The `custody-chain` reds' twins.
  **Intentional and precise.**
* **`packages/mainline-agentkit/tests/test_live_cassettes.py::test_every_recorded_body_hashes_to_its_index_row`**
  — a recorded body no longer hashes to its index row
  (`11d32dd3a13f… != 136eec3462c2…`). **A real defect and the correct one to have.** A
  recorded transcript is evidence; this is the detector that says one was changed or an
  index went stale. **Do not fix it by editing either side without establishing which is
  wrong.** Owner: `mainline-agentkit`.
* **`verticals/mainline/apps/demo-api/tests/test_envelope.py::test_no_web_framework_or_aws_sdk_is_imported`**
  — **a vacuity defect, and the artefact is fine.** The test asserts a property of the
  *deployment package* and measures `sys.modules` of the *pytest process*. Adding
  `verticals/*/apps/demo-api/tests` to `testpaths` put it into the shared session for the
  first time, where `boto3`, `botocore`, `httpx` and `pydantic` are already imported by
  unrelated suites. This agent measured the package itself:

  ```
  arm64 zip top-level: psycopg_binary.libs, psycopg_binary, web, psycopg,
                       mainline_demo_api, and two dist-infos.  No boto3. No httpx.
                       No pydantic. No botocore.
  ```

  The claim is TRUE and the mechanism does not test it. Fix the mechanism (subprocess
  with `-I`, or read the built zip), not the claim.
* **`verticals/mainline/apps/demo-api/tests/test_response_contract.py::test_the_one_unmeasured_response_is_bounded_by_construction`**
  — `OSError: [Errno 36] File name too long`. The test builds a ~4 KiB filename; Linux
  `NAME_MAX` is 255. **A real platform defect in the test**, invisible on Windows.

## 6.3 · `ruff format` — CRLF in the index, not the working tree

The Linux runner reported **3** files; this Windows checkout reports 226. The 226 are the
working-tree artefact the brief warns about and are noise. The 3 are not:

```
i/crlf  w/crlf   scripts/qa/row_factory_ratchet.py
i/crlf  w/crlf   tests/unit/test_row_factory_ratchet.py
i/crlf  w/crlf   verticals/mainline/apps/demo-api/tests/test_row_factory_contract.py
i/lf    w/lf     scripts/qa/ruff_ratchet.py                    <- every other file
```

`i/crlf` is the **index**: three files this wave added were committed with CRLF into an
LF repository, so the runner checks out CRLF and ruff asks for LF at line 1. Converted to
LF; `git diff --cached --ignore-cr-at-eol` is **empty** — not one character of content
moved. This is the same defect commit `8006a18` fixed for `submission.yml`. **It is not
the repository-wide format commit the brief forbids.**

---

# 7 · ANTI-VACUITY — which greens are falsifiable

## 7.1 · Proven falsifiable by planting a violation

| green | plant | what went red |
|---|---|---|
| the anonymous write guard (13/13) | remove `_demo_subject_is_established` step | 1 failed; `materialise_checks` and `sign_disposition` back to **200** |
| the anonymous write guard | disarm `_mutation_allowed` | 7 failed |
| the gate proof `PROVEN` | (previous wave, re-confirmed by construction) | removing the gate turns it NOT PROVEN with the clause named; the negative control notices its anchor vanished |
| `CEN-ANCHORS` in `aws-evidence` | this wave's own `main.tf` edits | it caught two silently retargeted citations unaided — a live falsification, not a planted one |
| `ruff format` ratchet | this wave's own CRLF files | caught 3 and only 3, on the platform that matters |
| the row-factory ratchet | it names 16 live findings today | a scanner that finds things is not vacuous |
| the mi-ratchet (`db-schema`) | it refuses `MI27` as *pending but passing* | it refuses a green as loudly as a red |

## 7.2 · Still unfalsifiable — named

* **`test_gate_run_verdict_is_proven` and the 291-test demo-api suite.** Green against the
  seeder they share constants with; **no test runs the demo against `demo_world.sql`**,
  the seed the deployment uses. §0.2 is precisely what that gap hides. **This is the most
  important unfalsifiable green in the build.**
* **`test_no_web_framework_or_aws_sdk_is_imported`.** Now *falsely* red; it cannot be
  falsified in either direction because it does not measure its subject (§6.2).
* **`demo-health`.** Cannot be anything but red until a URL exists. Honest, and it asserts
  nothing about the product today.
* **The `-errors`, `-throttles`, `-duration-p99` and `-concurrency` alarms.** Proven
  *reachable* by arithmetic against measured ceilings. Not proven to *fire*, because
  firing one needs an apply. **BUILT-BUT-UNPROVEN.**
* **The IAM policy's sufficiency.** Proven least-privilege by reading the plan; not proven
  *sufficient* — nothing has yet fetched the DSN through that role.
* **`cloud-verify` green.** It runs; this agent did not independently re-derive what it
  asserts about the Cloud cluster.

---

# 8 · THE MATRIX

## 8.1 · PROVEN

| thing | proof |
|---|---|
| the gate refuses, under attack, and admits when cleared | `gate_refusal.py`: 271/271, PROJECTION 10/10, `23514`, `P0001`, `00000`, caveats none, **PROVEN** |
| anonymous callers cannot mutate the four committing POSTs | four `423`s through the real handler; 13/13; falsified twice by plant |
| the demo route answers on the production `dict_row` path | `200` through `app.handler`; row-factory ratchet clean under `mainline_demo_api/` |
| the four beats are correct code | `PROVEN`, `failures: []`, beat 4 `admitted 00000` — against the proof seeder |
| the Terraform plan can apply | 11 to add, `applyable: true`, 44/44 checks, no drift from committed evidence |
| every alarm can reach its threshold | §3.3, two of them enforced by `precondition` |
| IAM is least-privilege and no DSN is anywhere | §3.4 |
| the deployment package carries no web framework and no AWS SDK | zip inspected: psycopg, psycopg_binary, web, mainline_demo_api only |
| `evidence/aws` is internally consistent | 896 assertions, 40/40 invariants, warm green |
| CockroachDB v26.2.5, 271 migrations, gc.ttlseconds 4500 | applied twice today |

## 8.2 · BUILT-BUT-UNPROVEN

| thing | what is missing |
|---|---|
| the whole AWS stack | **no apply has been run.** 11 resources planned, 0 exist |
| the four alarms and the dashboard | cannot fire without a function |
| the SSM DSN read path | no role exists; `db.py`'s hand-signed SigV4 has never fetched the live parameter |
| the console SPA served from the Function URL | no origin exists |
| the demo against the **cloud** seed | §0.2 — measured NOT PROVEN locally; never run against `mainline_demo` itself |
| `cohere.embed-english-v3` as the in-region answer | recorded; not re-measured by this agent |

## 8.3 · BROKEN

| thing | cause |
|---|---|
| `gate-run` verdict against the deployed seed | `gate_run._DISPOSITION_SQL` derives `signer_credential_id = sha256("cred"+"signer")`; `demo_world.sql` seeds `digest('mainline-demo/credential/demo.signer')`. `23503 disposition_signer_credential_id_fkey` |
| the warm connection's `autocommit` flag | `transitions.py:293-294` and `:1032-1033` set it `False` on the shared connection and never restore it (`db.py:306` opens `True`) |
| `test_no_web_framework_or_aws_sdk_is_imported` | measures `sys.modules` of a shared pytest session, not the package |
| `test_the_one_unmeasured_response_is_bounded_by_construction` | builds a filename longer than Linux `NAME_MAX` |
| one `mainline-agentkit` recorded cassette | body hash disagrees with its index row; which side is wrong is not established |
| `mainline_custody_patrol/collect.py:376` | reads a row both by position and by name; no declaration |
| `scripts/deploy/capture_demo_bundle.py:870,875` | mutates `conn.row_factory` on a live connection |

## 8.4 · NOT BUILT

| thing |
|---|
| a deployed demo URL |
| the submission video |
| the two missing reference-vertical producers — `trappoint_ref.clause`, `trappoint_ref.event` |
| seven `trappoint-verify` crypto checks (signature, tsa, beacon, witness, archive, attestation, webauthn) |
| any mechanism in code that bounds request rate, egress or spend |
| the console's `declare()` for `POST /v1/demo/gate-run` and its contract registration |

---

# 9 · RULES MATRIX

| rule | held? | evidence |
|---|---|---|
| never run `terraform apply` | **held** | `init`, `validate`, `plan`, `show` only; scratch copy, empty local state, no mutating AWS call |
| never print a credential | **held** | no DSN in any output, file or result; `db.redact` untouched; judge password not rotated |
| never weaken HONESTY.md, CI-STATE.md, a ratchet or an assertion | **held** | no ratchet baseline moved, no threshold relaxed, no assertion deleted. One evidence *claim* was corrected because it was measurably false, and the correction is stricter |
| `continue-on-error` / `\|\| true` banned; remove the last pair | **already done, verified** | zero live `continue-on-error:` directives repository-wide. The `submission.yml` pair is gone and replaced by a step that names the one outcome it tolerates. Remaining `\|\| true` are inside `grep -c` counts and one `docker rm -f` cleanup |
| never edit a recorded transcript to silence a scanner | **held** | the `aws-evidence` fix moved an *index*, not a quote; the cassette hash mismatch is reported, not edited |
| no TODOs | **held** | none added |
| fix causes, never symptoms | **held** | the three fixes are the anchor index, the false cost claim, and CRLF-in-index. The two product defects are named rather than patched, because both change what the product asserts |
| file ownership absolute | **held** | no `src/` product file modified |

---

# 10 · THE FOUNDER'S NEXT ACTIONS

## 10.1 · Only he can do these

1. **Decide the cost question.** The apply puts a public, unauthenticated origin on the
   internet whose worst case is **USD 33,250 for thirty days**, against a card whose
   budgets are already breached by unrelated projects. Nothing in this repository bounds
   it. This agent does not decide this and has not.
2. **If the answer is "proceed with a bound", choose the lever.** L3 (lower the handler
   cap to 512 KiB, permanent and zero judge friction) and L4 (per-IP throttle) are the two
   with the best ratio; L2 (strip source maps) costs DevTools frames. See
   `docs/deploy/COST-BOUND.md` §3.
3. **Re-authorise the apply, or not.** The previous authorisation was conditional on this
   verification returning GO. It returns NO-GO.
4. **AWS Support** — the CloudFront account verification hold. Only the account owner can
   open that case. Until it lifts, D1 stands and the Function URL is the hostname.
5. **The submission video.** Nobody else can record it.
6. **Decide whether a `NOT PROVEN` demo is shippable** if engineering cannot close §0.2
   before the 18th. It is a defensible thing to ship *with the honesty page saying so* —
   but that is a founder's call about the submission, not an engineer's about the code.

## 10.2 · Engineering remaining, in the order that unblocks the most

1. **Make the demo prove itself against the seed it will meet** (§0.2). Owner: `gate_run.py`
   + `demo_world.sql`. **And add the test that would have caught it**: run
   `POST /v1/demo/gate-run` against a database seeded by `demo_world.sql`, not only by
   `gate_refusal.py`. Without that test the fix is unfalsifiable.
2. **Restore `autocommit` on the way out of `handle_transition`** (§1.2), and extend
   `row_factory_ratchet.py` to the class it already half-covers: mutation of *any* shared
   connection attribute, not just `row_factory`.
3. **Implement the cost lever the founder chooses**, in code, with a test that fails when
   it is removed.
4. **Fix the two test-mechanism defects** (§6.2): make the package test measure the
   package, and give the response-contract test a filename Linux can hold.
5. **Establish which side of the agentkit cassette mismatch is wrong**, and fix that side.
6. **Land `trappoint_ref.clause` and `trappoint_ref.event`.** This single change turns
   `schema` and `db` green and lets `db`'s CONFORMANCE step execute for the first time,
   which is the observation `PL-2` in `ci` has been waiting for. **Three lanes, one fix.**
7. **Promote `MI27`** in `mi_catalogue.yaml`, or show that its owning tests witness nothing
   — `db-schema` refuses either way, which is the point.
8. Then, and only then: `terraform apply`, seed verification, `demo-health` green, video.

---

## 11 · What this agent changed

Three commits, all on `master`, all pushed:

| commit | what |
|---|---|
| `0921e3b` | the wave's 55 uncommitted files, so CI measures the real HEAD |
| `2c35333` | the two retargeted evidence anchors, and one measurably false cost claim |
| `802e7b7` | three files from CRLF back to LF; content byte-identical |

No product source file was modified. Both plants used to falsify the guard were reverted
and `transitions.py` verified byte-restored.
