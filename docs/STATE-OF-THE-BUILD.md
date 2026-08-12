<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: CC-BY-4.0
-->

# STATE OF THE BUILD

**Certified 2026-08-12 by the consolidation agent, at commit `f50efde`, after the
twenty-five-worker verification wave.** Deadline 2026-08-18.

Every number below was produced by a command this agent ran itself, on this machine or
against the live account, today. Nothing is copied from a worker's self-report: where a
worker's finding appears here it is because this agent re-ran the measurement and got the
same answer. Where a worker's claim did not survive, it says so.

The one paragraph a reader in a hurry needs:

> **The central claim is PROVEN and caveat-free. The Terraform plan replays byte-identical
> to its committed evidence. But the deploy is a NO-GO on two independently sufficient
> grounds: the plan cannot apply on this account, and the headline demo route returns
> `500`. Both have named one-line fixes, and this agent proved the second fix works. The
> repository is PUBLIC, there is no demo URL, and there is no video.**

---

## How to read this

| | meaning |
|---|---|
| **PROVEN** | this agent ran it today and watched it succeed; the artefact is named |
| **BUILT-BUT-UNPROVEN** | the code exists and is complete, but nothing has demonstrated it end to end |
| **BROKEN** | it exists and it does not work; the cause is named at `file:line` |
| **NOT BUILT** | it does not exist |

A red CI lane is not automatically bad. The discipline is that a lane reporting a true
incompleteness **stays red with a sharper message**. §4 separates the reds that are
defects from the reds that are honest instruments.

---

# 0 · THE DEPLOY DECISION — **NO-GO**

The founder has authorised the apply conditional on this verification returning GO. It
returns **NO-GO**. Two blockers, each independently sufficient. Neither is a judgement
call; both are measurements.

### 0.1 BLOCKER 1 — the plan cannot apply. It will fail half-way and leave a partial stack.

Measured by this agent, read-only, profile `mainline-dev`:

```console
$ aws lambda get-account-settings --region ap-southeast-1
  AccountLimit.ConcurrentExecutions           = 10
  AccountLimit.UnreservedConcurrentExecutions = 10
  AccountUsage.FunctionCount                  = 0
```

And from this agent's own fresh plan (not the committed file):

```
module.api[0].aws_lambda_function.this
  reserved_concurrent_executions = 20
```

A reservation of 20 cannot be satisfied by an account whose entire ceiling is 10, and AWS
additionally refuses any reservation that drops unreserved concurrency below its floor —
so on this account *any* positive reservation fails. The expected outcome of the
authorised apply is a failed `PutFunctionConcurrency` **after** the log group, role,
policy and role attachment have already been created: a partial apply with a tainted
function, which is the worst possible shape for a first deploy.

**The fix, exactly:** add `reserved_concurrent_executions = -1` to `module "api"` in
`infra/envs/demo/main.tf` (the block begins line 280). The cost ceiling is unchanged —
`min(20, account 10)` is 10 either way, and `ap-southeast-1` holds zero other functions,
so the account quota *is* the cap.

Two claims in the repository are falsified by this and must move with the fix:

* `infra/modules/demo-api/variables.tf:388` describes the variable as reserving "20 of the
  account's 1 000 unreserved executions". The account has **10**, not 1 000.
* `aws_cloudwatch_metric_alarm.concurrency` has `threshold = 20`. `ConcurrentExecutions`
  on this account can never exceed 10, so **the abuse tripwire is an alarm that cannot
  fire** — the exact defect `duration_p99`'s own `lifecycle.precondition` exists to forbid,
  reproduced one resource lower. Threshold must drop to 8.

### 0.2 BLOCKER 2 — the headline route returns `500`. Deploying now publishes a broken demo.

This agent invoked the real handler on the production `dict_row` path against a seeded
local database:

```
GET  /v1/health          -> 200
POST /v1/demo/gate-run   -> 500
{"error": {"kind": "internal_error", "resource": "demo_gate_run",
           "detail": "KeyError: 0", "status": 500}}
```

The traceback ends at `verticals/mainline/apps/demo-api/src/mainline_demo_api/refusal.py:235`:

```python
return (row[0] if row and isinstance(row[0], dict) else None), None
```

`db.py:309` opens every production connection with `row_factory=dict_row`. The query is
`SELECT trappoint.explain_refusal(...)`, whose single column CockroachDB names
`explain_refusal`, so `row[0]` is `KeyError: 0`. It is reached by `gate_run._record_refusal`
on beats 2 and 3 of **every** gate run and by `transitions._refused` on **every** kernel
refusal. There is no path through the demo that avoids it.

**This agent proved the fix.** Taking the row's single *value* rather than its index — in
memory, without editing the file — turns the same request into:

```
POST /v1/demo/gate-run -> 200
  beat "merge" -> refused | 23514 | gate_closed_when_issued
  MUS: 1 obligation, severity 4, virulence blood_major
  NAA: dispose_obligations, cardinality 1
```

That is the headline demo beat, working. The fix is one line, it is correct, and nobody
owns the file — three sibling modules were repaired in this wave and this fourth was
recorded rather than edited because file ownership is absolute. **It must be assigned.**

### 0.3 What the decision rule required, and what it got

| # | GO condition | verdict |
|---|---|---|
| 1 | The plan applies cleanly on this account | **FAIL** — §0.1 |
| 2 | No unauthenticated route mutates committed state | **PASS, after a fix landed this wave** — §0.4 |
| 3 | The DSN reaches the Lambda only as a KMS SecureString, in no state/plan/log/commit | **PASS** |
| 4 | Worst-case abusive 30-day bill bounded by a number the founder has accepted, enforced by a mechanism that exists | **FAIL** — §0.5 |
| 5 | Every alarm can reach its threshold, and something reads it | **FAIL** — §0.1, §0.5 |

### 0.4 The one NO-GO that was fixed during this wave — and it was serious

`scenario_permit_id` defaulted to `077a6fdd-2167-559c-b2ff-8e3c8352504d`, the `uuid5`
derivation in `scenario.py:77`. **Nothing has ever seeded that id.** The only permit in
Cloud `mainline_demo` is `dec0de00-0006-4000-8000-000000000001`, and the same public
hostname hands that id out at `GET /bundle/manifest.json`.

`transitions._demo_guard` returns `423 Locked` **only** when `subject_id ==
scenario.permit_id`. Armed at an id no caller would ever send, the guard was inert, and the
four committing kernel POSTs — `materialise_checks`, `sign_disposition`, `merge_permit`,
`suspend_permit`, all `mutates = True`, all calling `conn.commit()` — were reachable by any
anonymous caller on a URL with `authorization_type = NONE`. The DSN login is not read-only:
`cloud_roles.py` grants `mainline_api` the `UPDATE`s and `EXECUTE ON PROCEDURE
mainline.merge_permit`. One anonymous request would have committed `dispositioned →
checks_materialised` and destroyed the demo's headline refusal, unrecoverably.

The default is now the row that is actually seeded, read back out of the database rather
than derived, and this agent confirmed the regenerated plan carries it:

```
MAINLINE_DEMO_PERMIT_ID      = dec0de00-0006-4000-8000-000000000001
MAINLINE_SCENARIO_PERMIT_ID  = dec0de00-0006-4000-8000-000000000001
```

Today the write surface is inert only because of the unrelated `KeyError: 0`. **Fixing
§0.2 without §0.4 already committed would have opened it.** They must land together.

### 0.5 Cost — the bound the founder has not yet seen

| scenario | 30-day cost |
|---|---|
| A judging session | **USD 0.00** (USD 0.0019 without free tier) |
| `demo-health` hourly cron, 30 days | **USD 0.00** (USD 0.053 without) |
| Sustained gate-run flood | **~USD 168** |
| **Sustained egress flood** | **USD 11,515 – 33,472** |

The last row is unbounded by any mechanism that exists on this account. The AWS Budget is
`My Monthly Cost Budget`, limit **USD 10.00**, actual spend **USD 12.41**, forecast **USD
32.92** — *the account is already at ~3x its own budget from unrelated projects*, and no
budget **action** is configured, so the budget notifies and stops nothing. The CockroachDB
`spend_limit` disables the *database* between roughly day 4 and day 14 of a flood; AWS
keeps metering while every request returns `500`. The two ceilings are not connected.

All four alarms plan with `alarm_actions = null`. There is no SNS topic, the repository is
public and holds zero secrets and zero variables, no workflow requests an OIDC token, and
the account trusts no GitHub OIDC provider. **After the apply the alarms are read by
exactly one thing: a human signing into the CloudWatch console.** With
`treat_missing_data = notBreaching`, an idle demo shows four green rows, where green means
"nobody called this function", not "this function is healthy".

### 0.6 What is genuinely sound — verified, do not re-litigate

This agent re-ran `terraform init -backend=false`, `terraform validate` and a full
`terraform plan` from an isolated `TF_DATA_DIR`:

```
Terraform has been successfully initialized!
Success! The configuration is valid.
Plan: 11 to add, 0 to change, 0 to destroy.
```

Compared attribute-by-attribute against `evidence/deploy/terraform-plan-furl.json`:
**11/11 addresses identical, all `create`, and exactly one attribute differs — the IAM
policy string, differing only in the account id, which the committed evidence masks.**
After masking, byte-identical. The committed plan is honest.

* `dsn_access` grants exactly `ssm:GetParameter` on exactly one parameter ARN — no
  `GetParameters`, no `GetParametersByPath`, no wildcard path — plus `kms:Decrypt`
  conditioned on both `kms:EncryptionContext:PARAMETER_ARN` and `kms:ViaService`. The
  `Resource: "*"` on `kms:Decrypt` is *stricter* than naming the key, proven from that
  key's live policy.
* No `MAINLINE_DSN` in the planned environment; Terraform is given a *name*. A `validation`
  block refuses it and the six keys the module sets.
* No `MAINLINE_DEMO_ALLOW_MUTATION`; the demo-subject guard is armed.
* `aws_lambda_permission.cloudfront_invoke` is `count = 0` and genuinely absent.
* No CloudFront, S3, or CockroachDB resource of any kind. Nothing pre-existing is addressed.
* The DSN appears in no plan, no state, no log, no committed file, and in none of the 48
  commits. No `mainline_judge` password and no real AWS key either.

### 0.7 The order of operations, if the founder wants a URL

1. Fix `refusal.py:235` (§0.2) — one line, proven.
2. Set `reserved_concurrent_executions = -1`, drop the concurrency alarm threshold to 8,
   and correct the "1 000 unreserved" sentence (§0.1).
3. Accept, in writing, the USD 11.5k–33.5k egress bound — or cap it. There is no mechanism
   on this account that bounds it today.
4. Re-plan, re-verify, then apply.

**No worker, and not this agent, may run `terraform apply`.** The apply is the
orchestrator's.

---

# 1 · PROVEN

## 1.1 The gate refuses the merge, caveat-free

Run by this agent today, `scripts/proof/gate_refusal.py`, against the pinned local v26.2.5
node. Verbatim:

```
cluster       CockroachDB CCL v26.2.5 (x86_64-pc-linux-gnu, built 2026/07/28 18:56:00, go1.25.5)
database      w_qr_gate_refusal_proof
chain         271/271 applied, 0 failed, 51.035s
reached 0115  True
unproduced    (none) — every relation this tree references has a producer
PROJECTION    10/10 held — open_blocking 0->1 — gate_epoch 0->1 — outbox 'check_opened' severity 4 (client supplied 0)
REFUSAL       REFUSED [23514] gate_closed_when_issued (reported)
DRIFT         REFUSED [P0001] mainline.fn_permit_merge_gate (parsed)
ADMISSION     ADMITTED [00000]
caveats       (none) — nothing in this run is unproven-but-tolerated
VERDICT       PROVEN
```

Evidence: `evidence/gate-refusal/proof-20260812T172318Z.json`. **No caveat.** The database
refuses the merge because an obligation is open, it refuses a hand-rolled bypass of the
gate function, and it admits the legal path. The severity-4 outbox row while the client
supplied 0 is the projection asserting itself over caller input.

## 1.2 The Terraform plan is what it says it is

§0.6. 11 to add, 0 to change, 0 to destroy, replayed by this agent and diffed
attribute-by-attribute to a single masked-account-id difference.

## 1.3 Bedrock genuinely executes

Four live calls in `ap-southeast-2`, `calls_failed: []`, each with the AWS request id it
returned: `sts:GetCallerIdentity`, `bedrock:ListFoundationModels`,
`bedrock-runtime:InvokeModel` (Titan v2, 1024-d, L2 norm 1.00000006),
`bedrock-runtime:Converse` (`au.anthropic.claude-haiku-4-5`, `end_turn`). Total probe spend
USD 0.00006. Evidence: `evidence/deploy/aws-live.json`, `evidence/aws/probe/`.

`cohere.embed-v4:0` is refused on-demand and its only inference profile is
`global.cohere.embed-v4:0` — a **residency violation**. The in-region answer is
`cohere.embed-english-v3`. This is disclosed, not worked around.

## 1.4 The route table is complete

`app._routes()` returns **17** routes, and `POST /v1/demo/gate-run → demo_gate_run` is
among them. The 404 defect recorded in earlier states is fixed. **Addressable is not the
same as working** — see §3.1.

## 1.5 The repository is public and the tree behind the URL is the audited tree

`github.com/Shaugato/mainline`, `visibility: PUBLIC`, Apache-2.0 resolved independently by
GitHub. This agent scanned every tracked file and every new artefact in this commit: **zero
occurrences of the real 12-digit account id**, zero real credentials. All DSN and password
strings in the new verification artefacts are placeholders or `***`-redacted.

---

# 2 · BUILT-BUT-UNPROVEN

* **The deployed stack.** Eleven resources planned, none created. `terraform apply` has
  never run. There is no MAINLINE Lambda, Function URL, log group, alarm or dashboard in
  the account.
* **The state backend.** `bootstrap_state.sh` is written and correct; the bucket
  `mainline-demo-tfstate-*` does not exist, so `terraform init` with the S3 backend fails
  until it runs. The committed plan was produced with `-backend=false`, which is documented.
* **The SSM SecureString.** No parameter exists under `/mainline/`. A bare apply yields a
  function that answers `503 dsn_unset`.
* **The end-to-end acceptance transcript.** `evidence/deploy/acceptance.json` reads `NOT
  PROVEN`: both gate runs returned `500 KeyError: 0`. Nothing in that file was relaxed to
  reach a green, which is the correct behaviour.
* **The unwelding matrix and the gate-source snapshot comparison.** Both are collateral of
  §3.3 — they do not run at all while the reference vertical's producers are absent, so
  their subjects are UNPROVEN, not failing. The `schema` lane says so in its own words.

---

# 3 · BROKEN

## 3.1 `POST /v1/demo/gate-run` returns `500` — the headline beat

`refusal.py:235`, `KeyError: 0`. Full detail and the proven fix in §0.2. **This is the
single highest-value line of code in the repository right now.** Owner: unassigned.

## 3.2 The canonicaliser has drifted from its pin

`packages/trappoint-jcs/src/trappoint_jcs/canon_v1.py` hashes to `d09036a8…`; the registry
and the committed reference bundle pin `260ed37d…`. This is **real drift the mechanism
caught**, and it is the dominant cause of the `ci` lane's failures — roughly eight of the
seventeen failing tests are this one fact, seen from eight angles:
`test_canonicaliser_registry_is_pinned_and_retained`, `test_verifier_determinism`,
`test_canon_identity`, `test_canon_identity_refuses_a_downgraded_canon_line`,
`test_checkpoint_body`, and three in `test_no_network.py`.

`trappoint-verify` on the committed bundle now reports `16 checks | 8 passed | 1 failed |
7 not checked`, exit 1 — moved from exit 2. `docs/HONESTY.md` records this against its own
census rather than absorbing it, which is the correct handling. The repair is owed by the
custody domain.

## 3.3 The reference vertical cannot be applied

`trappoint_ref.clause` and `trappoint_ref.event` are referenced by the rendered SQL and
created by no file in it. `trappoint migrate up --tree trappoint-ref` refuses at
`0058_blocking_check` with `42P01`. This is the same defect class as the seven unproduced
tables, **in the package that is supposed to be the forkable half**. The `schema` lane is
red for exactly this and refuses to be closed by narrowing the matrix, skipping the job or
dropping the foreign key. See §4.2 — this is the model red.

## 3.4 The migration manifest is stale

`packages/trappoint-migrate/tests/test_lockfile.py::test_the_committed_manifest_is_current`
fails: several files' `sha256` in the manifest disagree with the tree. Fix is mechanical —
`trappoint migrate lock --write`. This is also the whole of the `db-schema` red.

## 3.5 `submission.yml` carries four steps that cannot fail the lane, and the repo bans that

Verified by this agent at `.github/workflows/submission.yml:148,155,172,176` — three
`continue-on-error: true` and one `|| true`. Two are load-bearing in a way a downstream
decision step makes safe. **`The machine record` carries `continue-on-error: true` *and*
`|| true` on the same command and cannot fail under any input.** It is unfalsifiable by
construction, which is precisely what the standing discipline forbids. It should drop its
suppression or be merged into the step that already asserts something.

## 3.6 Four `mypy` errors and a ruff-format regression

`packages/trappoint-recall/src/trappoint_recall/eval/bedrock_backend.py:1152,1153,1171,1172`
— `Found 4 errors in 1 file (checked 661 source files)`. The ruff ratchet reports **9
regressions**. Both were introduced by this wave's edits and both are mechanical.

## 3.7 `health` reports `migrations_applied: 0`

Measured by this agent on a seeded local database, and independently by a worker read-only
against Cloud `mainline_demo`: `trappoint.schema_migration` is **empty**, so `/v1/health`
answers `200` with `migrations_applied: 0` while the submission and `health.py`'s own
docstring say 271. `ok` stays `true` because it keys on the fingerprint. **A judge will
read that zero.** Nobody owns this number.

---

# 4 · CI — every workflow's real conclusion

Measured on commit `f50efde`, pushed by this agent, `gh run list --branch master`.
**13 push-triggered workflows: 7 green, 6 red.** Plus the scheduled `demo-health`, red.

| workflow | conclusion | class | why |
|---|---|---|---|
| `claims` | **success** | | |
| `supply-chain` | **success** | | |
| `judge-pack` | **success** | | |
| `submission` | **success** | see §4.3 | green here does **not** mean ready |
| `skills` | **success** | | |
| `release-proof` | **success** | | |
| `boundary` | **success** | | the A6 grep false positive is fixed |
| `ci` | **failure** | mixed | §4.1 |
| `db` | **failure** | fixable | 17 files use a floating image tag instead of the census pin |
| `db-schema` | **failure** | fixable | §3.4, `trappoint migrate lock --write` |
| `aws-evidence` | **failure** | **fixable — false positive** | §4.4 |
| `custody-chain` | **failure** | **intentional-and-precise** | checks 8, 11, 12 (`archive_object`, `ga…`, `webauthn`) unimplemented; 7/16 |
| `schema` | **failure** | **intentional-and-precise** | §3.3 — the model red |
| `demo-health` (cron) | **failure** | **intentional-and-precise** | there is no demo; `demo_url` is `UNRESOLVED` |

This is a real improvement on the previous board of ~7 green / ~10 red, and the
improvement is in *causes fixed*, not thresholds moved.

## 4.1 Inside `ci`

`17 failed, 8455 passed, 839 skipped, 13 deselected` in 318s. Job-level: `actionlint`,
`import-linter`, `lockfile`, `REUSE`, `RED BY DESIGN`, `sequence ban` all green; `PL-2`,
`mypy`, `ruff format`, `pytest --crdb=none` red.

* ~8 failures: the canonicaliser drift (§3.2) — **one cause**.
* `ruff_ratchet`: 9 regressions (§3.6) — fixable.
* `test_lockfile` (§3.4) — fixable.
* `test_live_cassettes`: a recorded body no longer hashes to its index row — fixable.
* `test_dm9_the_closure_is_read_only_through_the_view`: a file outside the three permitted
  ones touches `mainline.clause_blame_closure` in an executable position — **a real
  architectural violation**, not cosmetic.
* `test_k2_4/5/6`: missing artefacts and a missing `spec/CHANGELOG.md` entry — genuine
  incompleteness, correctly red.

**The `RED_SELECTOR` defect is fixed.** `pl2_red` is now registered and applied — 13 tests
collected by `-m "g4alpha or pl2_red"`, 9240 deselected, and the `RED BY DESIGN` job is
**green**, meaning the intentionally-red tests are red in their own lane and no longer
indistinguishable from regressions inside the general lane. That was the single worst CI
defect in the previous state and it is gone.

**The MI ratchet number is corrected.** This agent ran `scripts/mi_ratchet.py`:
`21 pending / 9 enforced`. The stale `28 of 30` string is corrected in `ci.yml:690` and
`docs/CI-STATE.md:352,561`; it survives only in superseded planning documents. The red
stays red, with the right number.

## 4.2 What an intentional red should look like

The `schema` lane is the standard. It names the missing producers, states *"what it is NOT:
a CI defect. It must not be closed by narrowing the matrix, skipping the job or dropping
the foreign key"*, explains that a live database can only ever surface the *first* missing
producer because `migrate up` stops at its first refusal, and declares that the static scan
is the only reader in the repository that can name the second. It then marks the two
downstream jobs as **collateral — UNPROVEN, not failing**. That is a red doing work.

## 4.3 A green that must not be misread

`submission` is **green**, and the submission is **not ready**. The readiness job is
*designed* not to fail before `2026-08-15T21:00:00Z`. `SUBMISSION.json` still holds
`UNRESOLVED` for **`demo_url` and `video_url`** — this agent read the file; `judge_access`
is resolved — and the gate itself exits 1 saying so. Between now and D-3 a green tick on
this lane carries no information about readiness. After D-3 it becomes blocking.

## 4.4 `aws-evidence` is red on a false positive — and it is poisoning an anti-vacuity job

The `SEC-ACCOUNT-ID` invariant flags any bare 12-digit number. It is firing on
`evidence/deploy/verify/aws-quota-and-cost.json:30`:

```
"AccountLimit.TotalCodeSize": 322122547200
```

That is 300 GiB in bytes — Lambda's code-storage quota, read straight from
`get-account-settings`. It is not an account id. The previous run failed the same way on
`999999999999`, an obvious placeholder. The invariant cannot distinguish a byte count from
an account number.

The consequence is worse than one red lane. The same workflow's mutation-testing job
reports `FAMILY red-for-the-wrong-reason: an unmutated copy of evidence/ already fails, so
every plant below would be red for a reason that is not its plant`. **While the baseline is
red, the anti-vacuity job in `aws-evidence` proves nothing.** Fix the checker (an allowlist
for quota-shaped integers, or compare against the account-id *format* in context), not the
evidence.

---

# 5 · ANTI-VACUITY — which greens are falsifiable

Three workers planted defects and checked that the lane went red for *that* defect.

| audit | result |
|---|---|
| `w9-judge-release-skills-console` | **26 promises tested, 21 falsified with a named red, 5 could not be** — 2 of those 5 *proved unfalsifiable*, with a run id |
| `w8-claims-boundary-submission` | every tested promise **falsified for the planted reason**; one step found unfalsifiable by construction (§3.5) |
| `w10-ci-supplychain-mutation` | declared reds confirmed still red; one control found unfalsifiable by construction and disclosed |

**Proven falsifiable** (a planted defect made them red, for the planted reason): the claims
gate, the boundary invariants, the submission readiness gate's blocking half, the release
proof, the skills lane, the console build, the supply-chain assertions, and — notably — the
gate proof itself: removing the gate turns `VERDICT PROVEN` into `VERDICT NOT PROVEN` with
the failing clause named, *and* the standing negative control notices its anchor has gone
and refuses to report a vacuous pass. That is the strongest single result in this audit.

**Could not be falsified**, each disclosed rather than counted as a pass:

* `submission.yml`'s `The machine record` — `continue-on-error` **and** `|| true` (§3.5).
* The `green`/`envelope` step in the judge pack — recorded as a finding, not a pass.
* The image-pin assertion — not falsifiable *in the direction that matters*: it would catch
  a pin that failed to arrive, but not a pin that was wrong when requested.
* `claims`' honesty card — falsifiable against the **fixture** corpus and falsified there;
  the real-corpus promise cannot be tested until `corpus.lock.json` is frozen. Today
  `gen_card.py` prints `BUILT FROM A FIXTURE — not for camera`.
* `aws-evidence`'s mutation family — vacuous today for the reason in §4.4.

---

# 6 · RULES MATRIX

| # | Rule | Verdict | Evidence / what is missing |
|---|---|---|---|
| **R1** | Public repo, open-source licence | **MET** | `visibility: PUBLIC`; `LICENSE` tracked, Apache-2.0 resolved by GitHub independently; `origin/master...HEAD` is `0 0` |
| **R2** | URL to a functional demo, free and unrestricted | **UNMET** | `demo_url` is `UNRESOLVED`. Both halves open: **the origin does not exist** (`apply` never run) and **the app does not answer** (§0.2, `500`). The access half *is* solved — judge credentials and pack exist |
| **R3** | Text description of features | **MET** | `docs/submission/DEVPOST.md`, 40 515 bytes, 6 175 words; prose gate reports 0 violations in this file |
| **R4** | Demo video under three minutes | **UNMET** | `video_url` is `UNRESOLVED`. Kit, VO, shot list and a CI validator for the 3-minute budget all exist. **Nothing in this repository can resolve this row** |
| **R5** | New project, inside the submission window | **MET** | First commit `f80fefd`, authored *and* committed `2026-08-05T22:47:47+10:00`; all commits pass on both dates |
| **R6** | ≥2 CockroachDB tools | **MET** — floor 2, three exercised | The database (v26.2.5, real refusal on a real cluster), CockroachDB Cloud + `ccloud`, the Managed MCP Server (15/16 pack questions PASS). Agent Skills reads DESIGNED and is not counted |
| **R7** | ≥1 AWS service | **MET** | Bedrock executes, `ap-southeast-2`, four HTTP 200s with request ids (§1.3) |
| **R8** | Documentation of which tools/services and how | **MET, regeneration owed** | `docs/TOOL-USAGE.md`, 80 819 bytes; 21/21 cited artefacts present on disk. `capture_tool_evidence.py --check` exits 1 on a stale `files_scanned` count — a regeneration owed, not a false claim |

**Six MET, two UNMET.** Only R2 is a Stage One pass/fail. R2 is now the *only* rule
blocked by engineering, and §0.2 is the whole of that engineering.

---

# 7 · THE FOUNDER'S NEXT ACTIONS

## 7.1 Only he can do these

1. **Record the video (R4).** The kit is complete: VO, timings, seeded state, shot list,
   and the sentences that may not be said on camera. A CI validator already fails the build
   if the script drifts past three minutes. Nothing else in the repository can move this row.
2. **Decide the egress exposure (§0.5).** A sustained egress flood against a public,
   unauthenticated Function URL costs **USD 11,515–33,472 over 30 days**, and no mechanism
   on this account bounds it. The account is already at ~3x its own USD 10 budget. Either
   accept that number explicitly, or ask for a cap before the apply.
3. **Authorise the corrected plan.** The existing authorisation was conditional on this
   verification returning GO. It returns NO-GO, so that authorisation has not vested. Once
   §0.1 and §0.2 land, the plan changes and needs fresh approval.
4. **Approve the disclosure position.** The AWS account id is masked at `HEAD` but remains
   in already-pushed commit history, and the local Windows account name appears in nine
   files. Neither is a credential; both are now public. `docs/submission/PUBLIC-READINESS.md`
   is the register.

## 7.2 Engineering remaining — ranked

| # | task | size | blocks |
|---|---|---|---|
| 1 | `refusal.py:235` — take the row's value, not `row[0]` | **one line, fix proven** | R2, the demo, the acceptance transcript, the apply |
| 2 | `reserved_concurrent_executions = -1`; concurrency alarm threshold `20 → 8`; correct the "1 000 unreserved" sentence | 3 edits | the apply |
| 3 | Fix `SEC-ACCOUNT-ID` to not flag quota-shaped integers | small | `aws-evidence`, **and un-vacuums its mutation job** |
| 4 | `trappoint migrate lock --write` | mechanical | `db-schema`, one `ci` test |
| 5 | ruff ratchet (9 regressions) + 4 `mypy` errors in `bedrock_backend.py` | mechanical | `ci` |
| 6 | Re-pin or re-derive the canonicaliser (§3.2) | medium | ~8 `ci` tests, the reference bundle |
| 7 | Pin the image in the 17 census-flagged files | mechanical | `db` |
| 8 | Own the `migrations_applied: 0` number (§3.7) | small | judge-facing honesty |
| 9 | Drop the suppression on `submission.yml`'s `The machine record` (§3.5) | small | the standing discipline |
| 10 | `DM-9` closure-view violation | real | `ci` |
| 11 | Add the four missing teardown verify checks (role, log group, alarms, dashboard) | small | teardown's truthfulness, not the bill |

Items 1 and 2 are the whole distance between here and a deployable demo. Items 3–11 are
quality and do not block R2.

## 7.3 What must stay red

`custody-chain` (7/16 custody checks unimplemented), `schema` (the reference vertical's
missing producers), `demo-health` (there is no demo), the g4alpha recall gates, and the MI
ratchet at 9 enforced / 21 pending. Each reports a true incompleteness. **None of them may
be closed by narrowing a matrix, moving a threshold, adding `continue-on-error`, or
deleting a test.** If one of them goes green without the underlying work, that is a
regression in honesty, which is the only asset here that cannot be rebuilt in a week.

---

*Consolidation agent, 2026-08-12, commit `f50efde`. No `terraform apply` was run. No
credential was read, printed, or written. The AWS account id is masked throughout. The
repository is public: every claim above is checkable by a stranger, and that is the point.*
