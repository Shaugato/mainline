<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: CC-BY-4.0
-->

# Cloud hardening — the plan the orchestrator should re-authorise

**Lead:** cloud-and-deploy · **Written 2026-08-14 on TRAPPOINT** · repo `D:/CoackroachDBxAWS/mainline`
· HEAD **`7535670`** (`evidence(cloud): re-seed CockroachDB Cloud and prove the demo there, not
only locally`), working tree clean at the moment of measurement (`git status --porcelain` printed
nothing).

**No `terraform apply` was run. No credential is printed, reconstructed or quoted anywhere in this
document. No floor was lowered, no ceiling raised, no assertion weakened, no known-red exemption
added.**

---

## 0 · My own baseline, measured before decomposing anything

### 0.1 The suite

```
D:/CoackroachDBxAWS/mainline/.venv/Scripts/python.exe -m pytest \
    verticals/mainline/apps/demo-api/tests --crdb=reuse -q -p no:randomly \
    --junitxml=<scratch>/baseline-default.xml
```

Read from the `<testsuite>` attributes of that XML, never from the terminal scroll:

| reading | tests | passed | failed | errors | skipped | time |
|---|---:|---:|---:|---:|---:|---:|
| **BEFORE · default order** (`-p no:randomly`) | **570** | **568** | **1** | **0** | **1** | 321.2 s |
| **BEFORE · randomised order** | **570** | **565** | **4** | **0** | **1** | 178.3 s |

**Neither reproduces the brief's stated baseline of 570 / 569 / 0 / 0, in either order.** Five
distinct node ids failed across the two readings, and **all five fail on one mechanism.** They are
named rather than rounded away:

| order | node id | assertion |
|---|---|---|
| default | `test_transitions.py::test_the_request_after_a_gate_run_is_not_a_503` | `'NOT PROVEN' == 'PROVEN'` |
| random | `test_gate_run.py::test_gate_run_verdict_is_proven` | same |
| random | `test_gate_run.py::test_every_table_row_count_is_identical_across_a_gate_run` | same |
| random | `test_gate_run.py::test_the_payload_proves_its_own_persistence_claim` | `assert False is True` |
| random | `test_gate_run.py::test_concurrent_runs_do_not_collide` | same |

Four of the five carry **one and the same failure string**:

```
AssertionError: ['the affected tables are NOT byte-identical before and after the run;
                  the transaction was supposed to persist nothing']
```

The skip is the pre-existing and correct one: `test_gate_run.py:1070`, *"jsonschema is not a
workspace dependency"*.

The workstation was quiet: `Get-Process python` showed six long-lived processes, all started
2026-08-13 (MCP servers), and **no concurrent pytest**. So this is not the four-agent contention
artefact `docs/diagnosis/retry-negative-control.md` §8 records.

`qa/cluster-known-red.json` lists only the first of the five, under `unstable`, at
`runs_observed: 22 / runs_failed: 1`. **On my reading it is 23 / 2, and the other four are not
listed at all.** See ruling **R2** — `unstable` is an exemption from the *ceiling* and from nothing
else, and it is not a verdict.

### 0.1.1 The mechanism, isolated — this is not a flake

`test_gate_run.py` run **alone**, default order, same cluster, same session:

```
27 passed, 1 skipped in 9.47s
```

**Green in isolation, four red in a randomised full suite.** So the failure is an *interaction*,
and the interaction is legible in the source. `gate_run.py:219` — `_FINGERPRINT_SQL` — is:

```sql
SELECT (SELECT count(*) FROM mainline.permit),
       (SELECT count(*) FROM mainline.permit_event),
       (SELECT count(*) FROM mainline.merge_record),
       … ten tables …
       (SELECT count(*) FROM mainline_ops.outbox)
```

**Ten unscoped, whole-table `count(*)`s.** Not scoped by `permit_id`, not scoped by run, not scoped
by anything — while `_PERMIT_ROW_SQL` immediately below it *is* scoped by `permit_id`. So **any**
row committed to **any** of those ten tables by **any** other caller, between the before-reading and
the after-reading, makes `POST /v1/demo/gate-run` answer **`verdict: NOT PROVEN`** with the sentence
*"the transaction was supposed to persist nothing"* — about a transaction that persisted nothing.

**That is not a test-only problem, and it is why this is the first item in this wave.** On Cloud,
`mainline_demo` is one shared live database and the demo URL is bounded-but-open by the founder's
choice. Two judges pressing the button at the same moment is precisely this interaction — and
`test_concurrent_runs_do_not_collide`, the test named for that case, is one of the four. **The
demo can answer NOT PROVEN in front of a judge, for a reason that is not a defect in the gate.**

**And the fix direction is NOT to scope the count down.** See ruling **R2**.

### 0.2 CockroachDB Cloud, reached from this workstation, read-only

```
current_database : mainline_demo          (selected BY NAME, never from the DSN path segment)
current_user     : mainline-sql
version          : CockroachDB CCL v26.2.5
isolation        : serializable
mainline.defeater_option : 6 rows
crdb_internal.gossip_nodes : REFUSED, sqlstate 42501
connect time     : 3.19 s
```

Then, because the whole of worker W1's feasibility turns on it, one bounded write probe — create
an empty scratch database and drop it again, touching nothing in `mainline_demo`:

```
OK   CREATE DATABASE IF NOT EXISTS w_lead_privprobe     2.99 s
OK   DROP   DATABASE IF EXISTS w_lead_privprobe         1.39 s
```

`mainline-sql` therefore **can** build and drop a scratch database on Cloud. The 271-file chain is
*not* required for a contention plant, which is what makes W1 affordable (`evidence/deploy/
cloud-chain.json` records the chain at **359.1 s** against this cluster; a plant that rebuilt it
per race would be unaffordable and nobody would run it twice).

### 0.3 AWS, read-only

```
aws sts get-caller-identity --profile mainline-dev
  → arn:aws:iam::<account>:user/mainline-dev

aws lambda get-function --function-name mainline-demo-api --region ap-southeast-1
  → ResourceNotFoundException: Function not found
```

**The stack is unapplied.** That is the correct reading for today and it is what makes the
empty-state equivalence in `scripts/deploy/plan_repro.sh` stage 2 still valid — and what makes
W6's post-apply verifier a thing that must be proven *by fault injection*, because there is no
stack to prove it against (ruling **R8**).

Terraform **1.14.8** windows_amd64; AWS CLI **2.32.21**. `evidence/deploy/terraform-plan-furl.json`
parses to **25 `resource_changes`, 24 of them creates** — `module.api[0]` and `module.guard[0]` —
with **seven** `aws_cloudwatch_metric_alarm` resources, every one of them
`treat_missing_data = "missing"` and `actions_enabled = true`, the concurrency alarm at threshold
**8**.

### 0.4 What the two orders together establish

The two readings disagree about *which* tests fail and agree about *why*. Taken together they say
three things, none of which either reading says alone:

1. **The defect is real and is on the headline path.** Five node ids, one mechanism, both orders.
2. **It is an interaction, not a flake** — `test_gate_run.py` is green in isolation in 9.47 s.
3. **The published baseline of 569 passed / 0 failed cannot be reproduced warm at HEAD**, in either
   order, on a quiet workstation. A number that only appears under conditions nobody can restate is
   not a baseline. §0.1 is the BEFORE this wave is measured against.

---

## 1 · Rulings

Each names the authority it was ruled from. These bind every worker.

### R1 — "It needs Cloud" is dead, and so is "the credential is not here"

**The CockroachDB Cloud credential is present on this workstation.** `.env` at the repository root
carries `COCKROACH_DSN` pointing at `mainline-dev-31219.j77.aws-ap-southeast-1.cockroachlabs.cloud:26257`,
`sslmode=verify-full`. It is gitignored (`.gitignore:6`) and untracked (`git ls-files --error-unmatch
.env` → *did not match any file*). I connected with it read-only and the numbers are in §0.2.

**Authority: the environment, measured.** `docs/deploy/CLOUD-40001.md` §3 states *"no
`CRDB_CLOUD_DSN`, `MAINLINE_*`, `COCKROACH_*`, `TRAPPOINT_*` or `CLOUD*` variable exists in this
environment — … returns a count of **0**"* and builds a five-item UNPROVEN list on top of it. That
sentence was true when written and is **false now**. The environment is authoritative; the document
is derived. **W1 corrects the document against the environment — never the reverse.** No worker in
this wave may write "this cannot be tested without Cloud", and no worker may write "the credential
is not available".

The corollary that costs something: the five items §3 lists as UNPROVEN are now **testable**, so
leaving them unproven is a choice rather than a constraint, and W1 and W3 are dispatched to close
the ones that are in scope.

### R2 — The gate-run persistence check is AUTHORITATIVE. It is not scoped down to obtain a green.

This is the ruling most likely to be quietly disobeyed, so it is stated with its authority in full.

The obvious "fix" for §0.1.1 is to scope `_FINGERPRINT_SQL`'s ten `count(*)`s by `permit_id`, or to
diff only rows this run could have written. **That is forbidden.** The committed JSON schema
`verticals/mainline/apps/demo-api/contracts/gate-run.schema.json` defines
`persistence_check` in its own words:

> *"Row counts over **every table the four beats can write**, taken before the transaction opened
> and after it was rolled back, plus `mainline.permit`'s own columns — because the attack beat
> mutates a column without changing a count."*

and `docs/deploy/gate-run-contract.md` §3 states the intent that produced it: *"A claim that
nothing persisted should be checked against everything, not …"*.

**Authority: the ratified tiebreaker — "the console and the committed JSON schemas are
authoritative for what the demo must carry; the seed and the tests are BOTH checked against them,
and either may lose."** The schema is one of the two authoritative artefacts named there. It asks
for the broad check **on purpose**, and it gives the reason: a narrow check cannot see the attack
beat. Narrowing it to make five tests pass is moving the authoritative side to match a derived one,
and it would delete the demo's only evidence for its central claim while leaving the claim in the
payload.

So the ruling has two halves:

* **The check stays broad.** No `WHERE permit_id = …` is added to `_FINGERPRINT_SQL`. No table is
  removed from `_FINGERPRINT_TABLES`. No tolerance, no "allow a delta of one", no retry-until-equal.
* **The real question is what wrote the row**, and that is what W2 answers. The honest outcomes are:
  a concurrent *test* wrote it (then the suite's isolation is the defect); the handler itself wrote
  it (then the handler is the defect and the check just caught it — which is the check working);
  or a concurrent *caller* can write it (then **the contract has a gap**, because a global count
  cannot distinguish "I persisted something" from "somebody else did", and that gap is closed by
  argument on the record — a schema change, reviewed — never by a silent narrowing).

**If W2 concludes the contract must change, it says so in writing, names this ruling, and changes
the schema and the document together with the code.** A payload that keeps saying `persisted: false`
while the evidence behind it has been weakened is the worst available outcome and is worse than the
red.

Two further constraints follow:

* **No worker may add any node id to `qa/cluster-known-red.json`.** Not to `groups`, not to
  `unstable`, not for any reason, in this wave. Four of the five ids above are not in that file and
  they are not going in it — filing a failure on the day it is discovered is exactly what the
  file's own `what_this_file_may_never_become` forbids.
* W2 may **delete** the `test_the_request_after_a_gate_run_is_not_a_503` entry **only** in the
  commit that demonstrably fixes it, citing the fix by hash — the file's own rule, and lane-honest
  ruling R7's citation requirement.

**Authority for the numbers themselves: the `--junitxml` `<testsuite>` attributes of two runs I
executed at HEAD `7535670` on a quiet workstation** (§0.1), which outrank a number quoted in a
brief.

### R3 — Multi-node behaviour is proven by INDUCING contention, never by counting nodes

`SELECT count(*) FROM crdb_internal.gossip_nodes` as `mainline-sql` returns **`42501
InsufficientPrivilege`** (§0.2). **Authority: the cluster, measured, and the ratified statement in
this wave's brief.** Any evidence artefact that tries to establish "multi-node" by reading
`crdb_internal` or `system` is refused at review. The observable is the **SQLSTATE and the restart
reason**, produced by a race somebody constructed, counted over a stated number of rounds.

### R4 — When Cloud and local disagree, which side is authoritative?

**Ruling: Cloud is authoritative for what the DEMO will meet. Local is authoritative for what a
stranger can reproduce. Neither is edited to match the other, and neither is deleted when it
disagrees.**

**Authority:** the repository's ratified tiebreaker — *"the console and the committed JSON schemas
are authoritative for what the demo must carry; the seed and the tests are BOTH checked against
them, and either may lose"* — extended by the one fact that decides which cluster the demo must
carry: **the deployed Function URL reads CockroachDB Cloud.** `docs/deploy/CLOUD-40001.md` §7
already fixes, in advance, what each Cloud observation falsifies; that table is binding and is not
to be rewritten after a result arrives.

Consequences, stated so they cannot be negotiated later:

| Cloud observation | what moves | what may NEVER move |
|---|---|---|
| a SQLSTATE outside the modelled taxonomy | the **taxonomy** — `UnmodelledRefusal` surfaced it, which is the design working | the assertion that met it; and it is never swallowed |
| `RetryBudgetExhausted` at `max_attempts = 5` | the **policy** may be re-argued from a measured Cloud rate | the meaning of "undecided" — it is not a refusal and not a success |
| an uncaught `SerializationFailure` escaping a guarded path | **that path's coverage** — it is not wrapped whole from `BEGIN` | wrapping one `execute()`; `spec/errors.md` §2.1 calls that not-a-retry |
| a retry converges but row counts are short | the **whole-transaction claim** — something replayed a statement | the expected count |
| the suite passes with **zero** `40001` observed | **nothing** | reading it as "the guards were unnecessary" |

### R5 — A Cloud contention probe may write, but never into `mainline_demo`'s rows

**Ruling: contention probes create their own scratch database, prove they can drop it, and drop
it. The one exception is `POST /v1/demo/gate-run`, which is allowed to race against `mainline_demo`
because it is savepoint-fenced and rolls back — and that exception is conditional on the probe
asserting the affected-table fingerprint is byte-identical before and after.**

**Authority:** `evidence/deploy/cloud-seed.json` records, as committed evidence, the exact row
counts the demo carries on Cloud (`defeater_option` 6, `ledger_leaf` 4, `ledger_node` 3,
`ledger_checkpoint` 3, `permit` 1, `blocking_check` 2, `disposition` 0, `merge_record` 0, …). Those
counts are an authoritative expected value that HEAD's own commit message publishes. **A probe that
moves them falsifies committed evidence and breaks the demo the founder's card is paying for.**

If `CREATE DATABASE` is ever refused for `mainline-sql`, **that refusal is the result** and it is
reported as such. It is never routed around by writing into `mainline_demo`. (Measured today it is
not refused — §0.2.)

### R6 — A plan reproduction that stops before the plan prints its count has reproduced nothing

**Ruling: `terraform plan` is "reproducible from a clean clone" only when a genuinely fresh
`git clone` reaches `Plan: 24 to add, 0 to change, 0 to destroy.` — and the runbook that gets it
there must carry the build step IN ORDER, because the artefact the plan reads is gitignored.**

**Authority:** `evidence/deploy/lead/plan-repro-fresh-clone.json`, which records a fresh clone at
`eefae1c` completing stage 1, stage 2, `init -reconfigure` and `validate`, rendering the whole plan
diff, and *then* dying inside `filebase64sha256` on the absent
`out/lambda/mainline-demo-api-arm64.zip`. `scripts/deploy/plan_repro.sh` now refuses that
up-front with exit **10**, which is a **correct refusal and not a proof**. The same file records
a second hazard measured at first hand: on Windows without `core.longpaths`, `git clone` prints
*"Clone succeeded"*, leaves **1,131 of 7,548** tracked files on disk, and — because
`missing_under_infra_slash`, `missing_under_scripts_deploy`, `missing_under_evidence_deploy` and
`missing_under_docs_deploy` are all **0** — `init -backend=false` and `validate` both **succeed
against something that is not this repository**. A runbook that does not fence that is a runbook
that produces a confident wrong answer.

### R7 — `evidence/deploy/terraform-plan-cloudfront.{txt,json}` is stale and may not be cited

It records `Plan: 22 to add`. **Authority:** `docs/deploy/terraform-plan.md:782` already states
that this artefact *"predated guard instantiation entirely"* and that *"its recorded count of
twenty-two described a tree"* that no longer exists. The **tree is authoritative; a committed plan
artefact is derived from it.** W5 regenerates it. Regenerating a plan is a read-only operation and
is inside this wave's permissions; **changing the configuration so the old count comes back is
not, and is the forbidden edit in its purest form.**

The `furl` shape is already correct at **24** and is confirmed by my own parse of the JSON (§0.3);
`docs/deploy/{COST-BOUND,JUDGE-PACK,OBSERVABILITY,PRE-APPLY,RUNBOOK,terraform-plan}.md` already say
24. **The count `22` is not to be "corrected to 24" anywhere it correctly describes the CloudFront
shape's history** — it is superseded, recorded as superseded, and replaced by a measured number.

### R8 — A verifier that has never failed has never discriminated

**Ruling: `scripts/deploy/post_apply_verify.py` ships only with each of its refusals demonstrated
firing, by fault injection, before any apply. And `scripts/deploy/aws_live_probe.py`'s
four-of-seven alarm blindness is a DEFECT to fix, not a caveat to document.**

**Authority:** `docs/deploy/PRE-APPLY.md` §3 records the blindness in the page's own words —
`ALARM_SUFFIXES` is a hard-coded four while the plan creates **seven** alarms whose names begin
`mainline-demo-api`, *"so after the apply this probe will report 'All 4 alarms exist and none is in
ALARM' while never having looked at the three that matter most"* — **and the three it cannot see
are the guard's, which are the ones wired to the stop.** My parse of the plan JSON confirms the
seven by name (§0.3). `cluster-tests.yml`'s stated principle is the second authority: a control
that has quietly stopped discriminating must go red rather than pass.

### R9 — Nothing in this wave applies, and nothing in this wave rotates a credential

`init` / `validate` / `plan` / `show` and read-only AWS calls only. No `terraform apply`. No judge
password rotation. No credential value printed to a terminal, a file, a log or an evidence
artefact. Account ids are masked as `<account>` in everything tracked, per the convention at commit
`1d41442`. **Authority: this wave's brief and `docs/leads/ship-final.md` decision D2.**

### R10 — Two Cloud traps, restated as binding rules

1. **The committed DSN's path segment is `defaultdb`, not `mainline_demo`.** Every worker that
   opens a Cloud connection selects the database **by name** and confirms with
   `SELECT current_database()`. `scripts/deploy/seed_demo.py` already does exactly this and records
   `database_selection.selected_how` in `evidence/deploy/cloud-seed.json`; that is the pattern to
   copy. Reading the path segment verbatim and then counting `mainline.*` yields 0 and concludes
   the deployment is empty. **A worker that "fixes" a script by trusting the segment has produced a
   false negative about the live demo.**
2. **`crdb_internal` and `system` are RESTRICTED.** See R3.

---

## 2 · The board, re-read warm at HEAD — what has already moved

The lane statuses in the brief were all measured **before** the defeater and Cloud commits. Read
warm, here is what I can already establish from the tree without dispatching anyone:

| brief's claim | what the tree says at `7535670` |
|---|---|
| `cluster-tests`: 10 skips against a ceiling of 1, because the lane never builds the zip | **Already addressed at HEAD.** `.github/actions/build-demo-package/action.yml` exists and `cluster-tests.yml` invokes it; the job comment says so and its own text says *"THIS STEP DOES NOT WEAKEN THE SKIP CEILING; IT REMOVES THE REASON FOR THE SKIPS."* `qa/cluster-known-red.json`'s `floor.when_it_becomes_527` names the follow-on. **Not this wave's work; verify the log warm before believing either way.** |
| `qa/cluster-known-red.json` is stale, `unstable` grew to 4 | **Partly moved.** Live `groups` is now **one** entry of one node id (`test_reads.py::test_the_disposition_carries_the_lattice_and_the_projected_requirements`), and my baseline shows that node id **passing**. `unstable` is still 4, all in `test_transitions.py`, and **one of them failed in my baseline** (§0.1). Pruning the ceiling belongs to whoever fixes each entry — R2. |
| the suite is 569 passed / 0 failed in both orders | **Does not reproduce.** 568/1 default, 565/4 randomised, one mechanism, five ids — §0.1, §0.1.1. **This is the wave's first item.** |
| resource count 22 → 24 | **The `furl` shape is already 24 everywhere I can find it**, and my own parse of the JSON agrees. **The stale 22 is the CloudFront artefact** — R7, W5. |
| `terraform plan` not reproducible from a clean clone | **Half done.** `scripts/deploy/plan_repro.sh` exists, carries a refusal allowlist, a measured empty-state equivalence check and a new exit 10; a fresh clone got as far as the rendered diff. **The ordered chain that reaches `Plan: 24 to add` has never been walked from a fresh clone** — R6, W4. |
| `evidence/deploy/acceptance.json` | **Stale and wrong about the world.** Dated 2026-08-13, `"url": "http://127.0.0.1:8764"`, `"target_is_local_emulator": true`, **`"verdict": "NOT PROVEN"`** on ten failures at beat 4 (`23503 disposition_signer_credential_id_fkey`) — the defect the defeater commits fixed. The submission cannot cite this. W3. |
| `docs/deploy/CLOUD-40001.md` §3 | **Load-bearing sentence now false** — R1, W1. |
| `docs/deploy/LATENCY.md` / `scripts/deploy/measure_beats.py:212` | Still measures `asset_map` against `GET /assets/index-BjAGxrVJ.js.map`, which **the shipping origin answers 404**. LATENCY.md annotates it honestly (†, §0.1) but the harness still reports a refusal as *"largest emittable object"*. W6. |

**Nobody may take any row of that table on my word.** Each worker re-measures its own row first and
says so.

---

## 3 · The six workers

Paths are **owned exclusively and enumerated literally**. A worker touches nothing outside its list.
If a worker believes it must, it stops and reports rather than reaching across.

---

### W1 · `cloud-contention` — prove `40001` on the platform the demo actually runs on

**Owns, exclusively:**
- `scripts/deploy/cloud_contention.py` *(new)*
- `tests/concurrency/test_cloud_contention.py` *(new)*
- `evidence/deploy/cloud-contention.json` *(new)* and `evidence/deploy/cloud-contention.json.license` *(new)*
- `docs/deploy/CLOUD-40001.md` *(edit)*

**Depends on:** W3 (see the window rule below).

**Done when:** `evidence/deploy/cloud-contention.json` records, from a run against CockroachDB
Cloud `mainline_demo`/scratch, a census of at least 12 constructed races per arm with every
observed SQLSTATE and every observed restart reason, alongside the same census taken against the
local single node in the same sitting; `docs/deploy/CLOUD-40001.md` §3 no longer claims the
credential is absent; `tests/concurrency/test_cloud_contention.py` passes locally and **skips with
a named, non-vacuous reason** when no Cloud DSN is configured; and `tests/concurrency` +
`packages/trappoint-testkit/tests` run whole with no new failure against the pre-run reading.

**One interaction is expected and must be reported, not smoothed:** racing two `gate-run`s against
Cloud will very likely reproduce §0.1.1's `NOT PROVEN`, because `_FINGERPRINT_SQL` counts whole
tables and the two runs see each other. **That is W1's most valuable single result** — it turns
W2's local, order-dependent finding into a Cloud fact about two judges pressing at once. W1
**records** it and hands it to W2; W1 does **not** fix it, does not narrow the fingerprint, and
does not serialise the race to make it go away.

---

### W2 · `gate-run-persistence` — the five reds, one mechanism, and the retry-coverage census

**This is the wave's first item.** It is the demo's headline path and it can answer `NOT PROVEN`
in front of a judge.

**Owns, exclusively:**
- `verticals/mainline/apps/demo-api/src/mainline_demo_api/gate_run.py`
- `verticals/mainline/apps/demo-api/src/mainline_demo_api/transitions.py`
- `verticals/mainline/apps/demo-api/tests/test_gate_run.py`
- `verticals/mainline/apps/demo-api/tests/test_transitions.py`
- `verticals/mainline/apps/demo-api/contracts/gate-run.schema.json` — **only** under R2's second half
- `docs/deploy/gate-run-contract.md`
- `tests/concurrency/test_retry_coverage_census.py` *(new)*
- `docs/diagnosis/gate-run-fingerprint.md` *(new)*
- `qa/cluster-known-red.json` — **deletion only**, and only under R2

**Depends on:** nothing.

**Done when:** `docs/diagnosis/gate-run-fingerprint.md` names the mechanism that writes the row,
with the writer identified rather than hypothesised; the five node ids in §0.1 pass in **default
and randomised** order without `_FINGERPRINT_SQL` having been narrowed (R2); every multi-statement
transaction in the two source modules is either wrapped whole from `BEGIN` or is recorded in the
census with a stated reason why it must not be, each with a negative control proving the loop is
reached; and the full demo-api suite is re-measured in both orders from `--junitxml` and reported
BEFORE/AFTER against §0.1's **570 / 568 / 1 / 0 / 1** and **570 / 565 / 4 / 0 / 1**.

---

### W3 · `cloud-acceptance` — the whole judge path against Cloud, each beat with its SQLSTATE

**Owns, exclusively:**
- `scripts/deploy/demo_acceptance.py`
- `evidence/deploy/acceptance.json` and `evidence/deploy/acceptance.json.license`
- `evidence/deploy/cloud-acceptance.json` *(new)* and `evidence/deploy/cloud-acceptance.json.license` *(new)*
- `docs/deploy/JUDGE-PACK.md`

**Depends on:** nothing. **W1's `mainline_demo` arm waits for this worker's capture window to close.**

**Done when:** `evidence/deploy/cloud-acceptance.json` records a run against Cloud whose
`target_is_local_emulator` is `false`, whose verdict is `PROVEN`, whose four beats carry
`00000 → 23514 gate_closed_when_issued → P0001 → 00000` with a server-computed `clearance_digest`,
and which **additionally** walks the signature path now that the defeater vocabulary exists;
`evidence/deploy/acceptance.json` no longer presents a stale `NOT PROVEN` local-emulator run as the
project's acceptance evidence; and the before/after row counts on Cloud are byte-identical to
`evidence/deploy/cloud-seed.json`.

---

### W4 · `plan-repro` — reproducible from a clean clone, proven end to end, in order

**Owns, exclusively:**
- `scripts/deploy/plan_repro.sh`
- `docs/deploy/RUNBOOK.md`
- `docs/deploy/PRE-APPLY.md`
- `evidence/deploy/lead/plan-repro-fresh-clone.json`
- `infra/envs/demo/backend.tf`
- `infra/envs/demo/README.md`

**Depends on:** nothing.

**Done when:** a genuinely fresh `git clone` of `github.com/Shaugato/mainline` at the current
`master`, walked in the documented order on a machine that has never held this repository's
`out/` directory, reaches **`Plan: 24 to add, 0 to change, 0 to destroy.`** at exit 0 — and
`evidence/deploy/lead/plan-repro-fresh-clone.json` records every command, its exit code and the
count, with the account id masked.

---

### W5 · `plan-truth` — regenerate the artefacts, and make every count true of the tree

**Owns, exclusively:**
- `evidence/deploy/terraform-plan-furl.json`, `evidence/deploy/terraform-plan-furl.txt`
- `evidence/deploy/terraform-plan-cloudfront.json`, `evidence/deploy/terraform-plan-cloudfront.txt`
- `evidence/deploy/cost/plan-shape.json` and its `.license`
- `docs/deploy/terraform-plan.md`
- `docs/deploy/COST-BOUND.md`
- `docs/leads/cost-bound-plan.md`

**Depends on:** W4.

**Done when:** both plan artefacts are regenerated from the current tree through W4's proven
read-only path; the CloudFront artefact no longer says 22 and its supersession is recorded rather
than overwritten; `docs/deploy/terraform-plan.md` states both counts as measured; and
`docs/deploy/COST-BOUND.md` no longer contradicts its own summary on I4/I6.

---

### W6 · `post-apply` — the measurement that happens the moment the stack exists

**Owns, exclusively:**
- `scripts/deploy/post_apply_verify.py` *(new)*
- `scripts/deploy/aws_live_probe.py`
- `scripts/deploy/measure_beats.py`
- `scripts/deploy/kill_switch.sh`, `scripts/deploy/kill_switch.ps1`
- `tests/deploy/test_post_apply_verify.py` *(new)*
- `docs/deploy/LATENCY.md`
- `docs/deploy/OBSERVABILITY.md`
- `evidence/deploy/verify/post-apply-dry.json` *(new)* and its `.license`

**Depends on:** nothing.

**Done when:** `scripts/deploy/post_apply_verify.py` exists, runs today against the unapplied
account and **exits non-zero saying exactly which of its checks could not be satisfied and why**;
every refusal branch is demonstrated firing by fault injection in
`tests/deploy/test_post_apply_verify.py`; `aws_live_probe.py` sees all **seven** alarms; and
`evidence/deploy/verify/post-apply-dry.json` records the dry reading with the account masked.

---

## 4 · The no-shortcut rule — repeated in every brief, and here once for the record

> **When a test and the code disagree, ask which side is AUTHORITATIVE, never which is easier to
> move.** The console and the committed JSON schemas are authoritative for what the demo must carry;
> the seed and the tests are BOTH checked against them, and either may lose. **Never lower a floor,
> raise a skip ceiling, or add a known-red exemption to obtain a green.** A worker was once caught
> editing `demo_world.sql` to enrol a derived credential id — making the seed match the code. The
> negative controls caught it and it was reverted. The re-verification's first check is a
> `git diff` over every seed, fixture, ceiling and expected value asking **which side moved and why
> that one was derived.**

And the additions this wave earns:

* **No `continue-on-error`, no `|| true`, no defaulted return code.** Ever.
* **No `terraform apply`.** `init` / `validate` / `plan` / `show` and read-only AWS calls only.
* **No credential printed** — not to a terminal, not to a log, not into an evidence artefact. Account
  ids masked as `<account>`.
* **No node id added to `qa/cluster-known-red.json`** by anyone in this wave (R2).
* **A skip is not evidence.** A skip whose reason is "no cluster" or "no credential" is now a *false*
  reason on this workstation (R1) and will be read as a defect in the test, not in the environment.
* **Report full-suite `--crdb=reuse` numbers from `--junitxml` BEFORE and AFTER**, against §0.1's
  570 / 568 / 1 / 0 / 1. A fix that breaks a neighbour is worse than the defect. **The suite is
  silent for minutes — 321 s in my own run. Healthy runs have been killed for looking hung.**

---

## 5 · Sequencing

```
W2 ──┐  (local; independent)
W4 ──┼── W5            (plan artefacts regenerate through the proven repro path)
W6 ──┤  (independent; re-reads the plan JSON before its final evidence capture)
W3 ──┴── W1            (W1's mainline_demo arm waits for W3's capture window to close)
```

Only **one** worker drives writes against Cloud `mainline_demo` at a time, and today that is W3
first, then W1. W1's scratch-database arm and every local arm may run at any time.

**The workstation has ONE local CockroachDB.** Four concurrent full-suite runs against it produced
a 609.9 s wall time and a measurement nobody could interpret
(`docs/deploy/CLOUD-40001.md` §6). Full-suite runs are serialised; per-module runs may overlap.

---

## 6 · How this wave is verified before it is offered for re-authorisation

1. `git diff` over every seed, fixture, ceiling, floor and expected value in the wave — **which side
   moved, and why was that one derived?**
2. Full demo-api suite, `--crdb=reuse`, **default and randomised**, from `--junitxml`, against
   **570 / 568 / 1 / 0 / 1** (default) and **570 / 565 / 4 / 0 / 1** (randomised).
   Plus: `git diff` on `_FINGERPRINT_SQL` and `_FINGERPRINT_TABLES` — if either narrowed, R2 was
   broken and the wave is rejected regardless of the suite numbers.
3. `tests/concurrency` + `packages/trappoint-testkit/tests` run whole (83 tests / 1 legitimate skip
   at last measurement).
4. `grep` the wave's diff for `continue-on-error`, `|| true`, `xfail`, `deselect`, `-k`, and any
   change to `max_attempts`, `min_executed`, `max_skipped`, `COLLECTED_FLOOR`, `HERMETIC_FLOOR`,
   `CLUSTER_FLOOR` or `account_concurrency_ceiling`. Each hit is explained or reverted.
5. `terraform init -backend=false && terraform validate` in `infra/envs/demo`, plus W4's fresh-clone
   transcript reaching `Plan: 24 to add`.
6. Confirm **no `terraform apply`** appears in any transcript, and that
   `aws lambda get-function --function-name mainline-demo-api` still answers
   `ResourceNotFoundException`.
7. Confirm the Cloud row counts still match `evidence/deploy/cloud-seed.json` (R5).
