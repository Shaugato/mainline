<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: CC-BY-4.0
-->

# STATE OF THE BUILD

**Certified 2026-08-11 by the final certification agent, after the thirty-worker
completion wave.** Deadline 2026-08-18.

Every number in this document was produced by a command this agent ran itself, against
the live systems, today. Nothing here is copied from a worker's self-report. Where a
worker's claim did not survive re-measurement it is marked and corrected. Where something
could not be proven it says so, and says what is missing.

The one sentence a reader in a hurry needs:

> **The central claim is PROVEN and caveat-free. AWS is genuinely executed, end to end,
> and the ≥1-AWS-service rule is met with room to spare. There is no demo URL, and there
> is no video. Those two are the whole gap between this repository and a submission, and
> only one of them is engineering.**

---

## How to read this

Four dispositions, used strictly:

| | meaning |
|---|---|
| **PROVEN** | this agent ran it today and watched it succeed; the artefact is named |
| **BUILT-BUT-UNPROVEN** | the code exists and is complete, but nothing has demonstrated it end to end |
| **BROKEN** | it exists and it does not work; the cause is named |
| **NOT BUILT** | it does not exist |

A red CI lane is not automatically bad. This repository's discipline is that a lane
reporting a true incompleteness **stays red with a sharper message**. Section 4
separates the reds that are defects from the reds that are honest instruments.

---

# 1 · PROVEN

## 1.1 The gate refuses the merge, and the last caveat is gone

Run by this agent, `scripts/proof/gate_refusal.py`, against the pinned local v26.2.5
node. Verbatim:

```
cluster       CockroachDB CCL v26.2.5 (x86_64-pc-linux-gnu, built 2026/07/28 18:56:00)
database      w_qr_gate_refusal_proof
chain         271/271 applied, 0 failed, 58.197s
reached 0115  True
unproduced    (none) — every relation this tree references has a producer
PROJECTION    10/10 held — open_blocking 0->1 — gate_epoch 0->1 —
              outbox 'check_opened' severity 4 (client supplied 0)
REFUSAL       REFUSED [23514] gate_closed_when_issued (reported)
DRIFT         REFUSED [P0001] mainline.fn_permit_merge_gate (parsed)
ADMISSION     ADMITTED [00000]
caveats       (none) — nothing in this run is unproven-but-tolerated
VERDICT       PROVEN
```

Artefact: `evidence/gate-refusal/proof-20260811T074629Z.json`.

**`caveats (none)` is the load-bearing line.** Earlier proofs carried an
`open_blocking` caveat. It is gone: the counter is trigger-projected, and the outbox row
carries severity 4 while the client supplied 0 — the database overrode the client, which
is the entire thesis of the project demonstrated in one field.

## 1.2 The claim is falsifiable — I broke it on purpose

A green that cannot go red proves nothing. Two independent checks:

**Falsified by this agent.** `scripts/demo/claim_hygiene.py --check` against the
committed red fixture returned **21 violations and exit 1**; `--self-test` planted 4
violation families and the scanner fired on all 4.

**The gate's own negative controls ran green today**, in run `31470822444`:

| job / step | conclusion |
|---|---|
| `RED — the proof reports NOT PROVEN when the gate is removed` | success |
| `RED — the gate refuses a run where nothing was proved` | success |
| `RED — the proof reports a named FAILURE for every planted family` | success |

So the PROVEN in §1.1 is a measurement, not a tautology. `docs/ci/anti-vacuity.md`
records the full matrix, and it is honest about its own gaps — see §4.3.

## 1.3 AWS genuinely executed — this is the ≥1-service rule, met

**This agent invoked both models directly**, in `ap-southeast-2`, account
`0229REDACTED8246`:

| call | result |
|---|---|
| `amazon.titan-embed-text-v2:0` | **1024-dimension embedding**, `inputTextTokenCount: 5` |
| `au.anthropic.claude-haiku-4-5-20251001-v1:0` (Converse) | replied as instructed; **22 in / 14 out**, `stopReason: end_turn` |

The `ValidationException: Operation not allowed` recorded in earlier revisions of this
document is **gone**. That finding is now stale and is corrected here.

**The vectors are really in the vector-indexed table.** Against the live Cloud cluster
(`mainline-dev`, `aws-ap-southeast-1`), database `mainline_ann_evidence`:

```
SHOW INDEXES   ce_ann = (site_id ASC, activity_root ASC, embedding ASC)
rows           1534, of which 1534 have a non-null embedding
dimensions     1024
embed_model    amazon.titan-embed-text-v2:0
index_gen      titan-v2-1024-8b510425ae1d
```

**A hinted, prefix-constrained ANN traverses that index and returns the right
precursor.** This agent ran the committed judge-facing statement
(`evidence/aws/ann/the-one-query.sql`) and got the recorded result back exactly:

```
rank 1   FAI-2010-141   msha_fatality_report   2010-06-07   distance 0.494575
rank 2   FAI-2013-145                          2013-01-22   distance 0.497643
rank 3   FAI-2017-151                          2017-01-01   distance 0.505576
```

and its `EXPLAIN`, verbatim:

```
• vector search
    table: clause_embedding@ce_ann
    target count: 10
    prefix spans: [/'5b144fe2-…-2e3eb31497b6'/'/mill' - /'5b144fe2-…-2e3eb31497b6'/'/mill']
```

That is the whole claim in one plan: a **`vector search` node**, on **`ce_ann`**, with
**both prefix columns bound to exactly one value each**, returning the fatality precursor
that the permit's author could not have had.

**AWS's own telemetry corroborates it independently.** CloudWatch `AWS/Bedrock`
`Invocations` for the Titan model, queried by this agent:

```
2026-08-11T12:33 +10:00   Sum = 3330      (the corpus embedding pass)
2026-08-11T13:33 +10:00   Sum = 1053
2026-08-11T17:33 +10:00   Sum = 1         (this agent's own probe, minutes earlier)
```

The last row is this certification's own call, counted by Amazon rather than by us. Three
AWS services are therefore EXERCISED, not one: **Bedrock Runtime (Converse)**, **Bedrock
Embeddings (InvokeModel)**, **CloudWatch (GetMetricStatistics)**.

## 1.4 …and the recall number is modest, which the artefacts say plainly

The exhibit above is the **best of 96**, chosen by a rule written down before the numbers
were seen, and the file says so in its own header. The distribution over all 96 retro
permits, single-root arm, 95 % Wilson intervals, from
`evidence/aws/ann/ann-proof.json`:

| metric | measured |
|---|---|
| truth precursor hit@1 | **1/96 = 0.010** [0.002, 0.057] |
| truth precursor hit@3 | 5/96 = 0.052 [0.022, 0.116] |
| truth precursor hit@10 | **29/96 = 0.302** [0.219, 0.400] |
| any relevant (grade ≥ 2) hit@10 | 74/96 = 0.771 [0.677, 0.844] |
| MRR (any relevant) | 0.4439 |

**Say "in the top ten, three times in ten" and never "it finds the precursor."** The
retrieval is a useful assistant and a poor oracle. The artefact carries eight caveats
including the two that cost it most — the corpus is synthetic, and GT-06's counterfactual
did **not** reproduce (the optimizer chose `ce_ann` unhinted too at every size swept, so
the hint is defensible as a *pin* but cannot be called *necessary* at this scale). Those
caveats are the reason to trust the rest.

## 1.5 CockroachDB usage clears the bar, well past it

From `evidence/tool-usage/crdb-features.json`, re-derived from the tree today
(14 rows: 11 EXERCISED, 3 DESIGNED):

**Tools — 2 of 4 exercised** (the rule needs ≥ 2): `crdb_database` (the cluster itself),
`crdb_cloud_ccloud` (CLI, transcript in `evidence/ccloud/`). `crdb_managed_mcp` and
`crdb_agent_skills` are DESIGNED and honestly labelled.

**Features — 9 exercised**, and they are not decorative: `SERIALIZABLE`, triggers, CHECK
constraints, **vector index (C-SPANN)**, `AS OF SYSTEM TIME`, follower reads, row-level
security, `SHOW CREATE`, `crdb_internal`. Changefeeds are DESIGNED, not claimed.

## 1.6 Static gates that genuinely pass

`claims`, `judge-pack`, `release-proof`, `supply-chain`, `boundary`, `submission` — see
the board in §4. `boundary` is 121 passed / 6 skipped locally, and every skip **declares
itself NOT A PASS** rather than counting as one.

---

# 2 · BUILT-BUT-UNPROVEN

## 2.1 The demo application — written, complete, and never successfully run

`verticals/mainline/apps/demo-api` and the console exist in full. The Terraform is
written, `init`/`validate`/`plan` were run, and the plan output is committed
(`evidence/deploy/terraform-plan-furl.txt`, `…-furl.json`,
`…-cloudfront.txt`). **`terraform apply` has never been run** — correctly, since it is
reserved for the founder's approval.

This agent verified the consequence directly against AWS rather than inferring it:

```
aws lambda list-functions  ap-southeast-2  ->  cci-chage-enricher   (an unrelated project)
aws lambda list-functions  ap-southeast-1  ->  (none)
aws s3api list-buckets                     ->  no MAINLINE bucket
```

**There is no MAINLINE Lambda, no Function URL, no site bucket, in any region.** The
`demo_url` field in `docs/submission/SUBMISSION.json` holds `UNRESOLVED`, and that is the
truthful value. No URL is claimed anywhere in this document because none answers.

## 2.2 The video — script yes, film no

`docs/submission/VIDEO-KIT.md` holds the script, shot list and seeded state. The film
does not exist. **Only the founder can record it**; no agent may.

## 2.3 Judge access without a deployment

`verticals/mainline/demo/judge/MCP-CONFIG.md` documents two paths for a judge to read the
live Cloud ledger. It is correctly written — credentials are `${ENV}` interpolations, and
the page states plainly that the published key is not the one handed out. It is unproven
only because no judge has walked it.

---

# 3 · BROKEN

## 3.1 The demo API's own gate run reports NOT PROVEN

This is the most important entry in this document after §1.

`verticals/mainline/apps/demo-api` fails 7 of its own tests. Run by this agent:

```
AssertionError: ["beat 4 (admit): expected {'outcome': 'admitted', 'sqlstate': '00000'},
                  observed outcome='skipped'"]
assert 'NOT PROVEN' == 'PROVEN'
```

`evidence/deploy/acceptance.json` names both causes precisely, and both are real:

1. **`mainline_demo_api/db.py:309` opens every connection with `row_factory=dict_row`**,
   which `reads.py` and `health.py` rely on — but `gate_run.py:272` and
   `scenario.py:283` unpack the same rows **positionally**. Through the app's own
   connection `scenario.resolve()` binds the string `'check_id'` as a UUID and
   CockroachDB answers `22P02`.
2. **Two derivations of one identifier.** `gate_run.py` derives
   `signer_credential_id` as `sha256('cred' + 'signer')`; `demo_world.sql` seeds
   `digest('mainline-demo/credential/demo.signer', 'sha256')`. Beat 4 is refused
   `23503 disposition_signer_credential_id_fkey`.

**Nothing was relaxed to hide this.** It means the demo, if deployed today, would serve a
gate run that says NOT PROVEN. **Fixing this is the single highest-value piece of
engineering left**, because it stands between a working demo URL and the submission.

## 3.2 Four defects this certification found and fixed

Recorded because a wave that leaves defects behind will leave more.

**The entire test suite was unrunnable.** `tests/unit/aws/` and `tests/integration/aws/`
both carried `__init__.py`, so both claimed the top-level module name `aws`. The second
to import lost, and collection **aborted**:

```
ModuleNotFoundError: No module named 'aws.test_common_redaction'
```

A collection error stops the whole run, so all 9,281 collected tests went unmeasured.
Fixed at the cause. **Collection today: 9,324 tests, 0 errors.** The committed census
could not have caught this — it runs each target in a separate process, and its own
caveat list says cross-target basename collisions are "NOT measured here."

**An A6 violation the previous wave recorded as a false positive.**
`scripts/deploy/aws_live_probe.py` set `temperature: 0.0` beside `maxTokens` in a Converse
request builder. It was a true finding. Removed: it reads as a promise that a model reply
is reproducible, which this project does not claim.

**A determinism-boundary breach (E3).**
`trappoint_recall.eval.bedrock_backend` constructed its own
`boto3.client("bedrock-runtime")`. `packages/trappoint-*` **is** the kernel plane — the
plane that must hold no model code path so a model cannot reach the gate — and the
module's own design note already said the package declares no AWS SDK. The kernel now
declares the protocol; the AWS plane supplies the transport. The removed branch was dead
on the live path.

**A hard-gate licence breach, and a ratchet that had risen.**
`evidence/deploy/lambda-bundle.json` spelled the SPDX tag out in prose; ending a sentence,
the full stop was read as part of the identifier, so the tree declared a fifth licence
`CC-BY-4.0.` that no file in `LICENSES/` defines. Separately,
`non_spdx_spelling.FSL-1.1-ALv2` had risen **1213 → 1254**: 44 files added since
2026-08-10 carried the non-conforming spelling that ruling L-1 exists to prevent. Those
44 — and only those — now carry `LicenseRef-`. **No baseline was lowered**: the measure
is 1210 against a floor of 1213, and `check_reuse.py` exits 0 over 7,402 tracked files.

## 3.3 The repository is not safe to flip public yet

`scripts/submission/audit_public_readiness.py`, run by this agent:

```
VERDICT: NOT READY — failing checks: secrets_tracked, secrets_history, absolute_paths
```

The flip is **irreversible** and publishes **all 45 commits on all 9 refs**, not the tree
at HEAD. Breakdown of the 122 unresolved findings:

| what | count | this agent's read |
|---|---|---|
| `aws_account_id` in 4 `evidence/deploy/` plan files | 78 | **real, and a decision — see §5.1** |
| `aws_access_key_id` shapes | 6 | in the redaction **test vectors** and the scanner's own source. Not credentials |
| `high_entropy_secret` | ~9 | cluster ids and `${ENV}` names; `MCP-CONFIG.md` inspected and clean |
| `abs_windows_path` | rest | directory layout; **9 files disclose the Windows account name `shaug`**, chiefly `qa/test-state.json` (52 pytest temp paths) |

No live credential was found in the tracked tree or in history by this agent. The blocker
is a disclosure decision plus housekeeping, not a leak — but it is a blocker.

---

# 4 · The CI board, measured

Pushed to `master` and observed. Commits: `6251c6e` (the wave), `56e3d92` (four
cause-fixes), `f3125ac` (boundary lint), `b0fe884` (REUSE / actionlint / format),
`27ac8aa` (this document), `57c477c` (the HONESTY.md ruff paragraph).

**The board below is `b0fe884`, the last commit on which all 13 workflows ran to
completion.** Two later runs are not usable as evidence: on `57c477c` three `ci` gate
jobs failed **in 2 seconds with zero steps executed** — a runner-allocation failure, not
a repository failure — and a re-run reproduced it. Nothing is claimed from those runs in
either direction.

## 4.1 Green — 6 of the 13 workflows that ran on `b0fe884`

`judge-pack` · `submission` · `boundary` · `supply-chain` · `release-proof` · `console`

(`claims` is green too, on `6251c6e`; its path filter did not re-trigger it.)

`boundary` and `submission` were **red before this pass and are green now** for real
reasons, not relaxations: an A6 violation and an E3 breach removed, two ruff findings
paid, and a licence ratchet returned below its floor without the floor being touched.

**`submission` green does not mean the submission is ready.** Its readiness gate is
**report-only until `2026-08-15T21:00:00Z`**, after which it blocks. On that date the
`UNRESOLVED` rows in §5 start failing CI.

## 4.2 Red, and correct to be red

| lane | why | verdict |
|---|---|---|
| `aws-evidence` | 90 findings, **all** the undeclared account id of §5.1 | INTENTIONAL, and precise |
| `custody-chain` | 7 of 16 custody checks unimplemented | INTENTIONAL |
| `schema` | the reference vertical is missing a producer | INTENTIONAL |
| `demo-health` | no demo is deployed | INTENTIONAL — it is reporting §2.1 |
| `g4alpha` gates | retro-recall 0/24 on the offline fixture corpus; channel C only, with B and D absent by construction | INTENTIONAL |
| MI ratchet | 28/30 invariants | INTENTIONAL — the top-level incompleteness counter |
| `db`, `db-schema` | image-pin census, and a helper hand-listing migrations that omits 0110 and drops `0138a` because `"0138a".isdigit()` is False | **STILL FIXABLE** |
| `ci` | 4 of 12 jobs (was 5; `actionlint` and `REUSE` fixed here) | **MIXED — see below** |

Inside `ci`, the four remaining red jobs are not one thing:

* **`pytest --crdb=none`** — inherits the custody K2 reds above (missing
  `evidence/k2-checkpoint-cadence.json`, an unpinned canonicaliser hash, a DM-9
  violation). Same true incompleteness, surfacing in a second lane. INTENTIONAL.
* **`PL-2 — the red run is recorded`** and **`mypy · and the target list is complete`** —
  fixable, not examined in depth here. `mypy`'s gate is known to cover a small fraction
  of what mypy could check, which is itself the finding.
* **`ruff format`** — **half fixed, and the remaining half is a true red.** The formatter
  count went 7 files → 1 → **0 on the runner**: that half is done. But the same job's
  ratchet step reports `ruff check .` at **732 findings against a frozen floor of 671**,
  so the lint total has *risen* and `scripts/qa/ruff_ratchet.py` refuses the tree. **The
  floor was deliberately not re-frozen upward** — that is the one move that would silence
  a ratchet — so this lane stays red until the added findings are removed.

## 4.3 Anti-vacuity — the honest gaps

`docs/ci/anti-vacuity.md` records which lanes prove they can fail. Verified green on real
runs: `claims`, `judge-pack`, `console`, `release-proof`, `skills`, `supply-chain`,
`cloud-verify`.

**Greens this agent could not falsify, and will not pretend it could:** `ci`, `db`,
`db-schema`, `custody-chain`, `schema`, `nightly-differential` have **no** negative
control; `boundary` has only a partial one; `submission`'s was never examined. A green
from those six lanes is weaker evidence than a green from the seven above, and that
difference should be assumed until someone plants a violation in them.

---

# 5 · Rules-compliance matrix

| requirement | status | evidence / what is missing |
|---|---|---|
| New project inside the window | **MET** | first commit 2026-08-05 |
| OSS licence | **MET** | `LICENSE` (Apache-2.0) + `LICENSES/`; `check_reuse.py` exits 0 over 7,402 files, 0 uncovered |
| **Public repository** | **UNMET** | private; `audit_public_readiness.py` says NOT READY (§3.3). **Founder-only action** |
| **URL to a functional demo, free and unrestricted** | **UNMET** | no Lambda, no bucket, in any region (§2.1); and the app would answer NOT PROVEN if deployed (§3.1) |
| Text description | **MET** | `docs/submission/DEVPOST.md` |
| **Video < 3 min** | **UNMET** | script and shot list ready; **founder must record it** |
| ≥ 2 CockroachDB tools | **MET** | 2 tools + 9 features EXERCISED (§1.5) |
| **≥ 1 AWS service** | **MET, PROVEN** | 3 services exercised; Bedrock vectors in a C-SPANN index; CloudWatch corroborates independently (§1.3) |
| Documentation of which tools/services and **how** | **MET** | `docs/TOOL-USAGE.md` + machine census in `evidence/tool-usage/`, anchors re-derived today |

## 5.1 One judgement call only the founder can make

**Four files under `evidence/deploy/` publish the AWS account id `0229REDACTED8246`**, in
bare form and inside ARNs. Two committed artefacts currently disagree about whether that
is acceptable:

* `docs/deploy/terraform-plan.md` and decision **D2** say publication is deliberate: "an
  account id is an identifier, not a credential."
* `scripts/aws/verify_evidence.py` refuses it: "an account number is not a credential, and
  publishing one still enables cross-account enumeration."

**D2 is a worker's decision, not the founder's**, and D2's own rule is that recorded
evidence may keep the value **only if declared per-path** in
`docs/submission/DISCLOSURE-DECISIONS.yaml`. Those four files are **not declared there**.
So the `aws-evidence` red is correct under the project's own ruling, and this agent
deliberately did **not** grant the exemption — publishing the founder's account number is
his call, not an agent's.

Two clean resolutions, both cheap:

* **Redact.** The digits carry no evidential weight; the plan means the same without them.
* **Declare.** Add the four paths to the register with a reason, and the lane goes green.

This must be settled **before** the flip, because the flip is irreversible.

---

# 6 · The top three things to do next, in order

## 1 — Fix the demo API, then deploy, then flip public *(engineering, then founder)*

The order matters: deploying the app in its current state produces a demo URL that says
**NOT PROVEN**, which is worse than no URL.

1. **Engineering:** fix the two defects in §3.1. Both are small and both are named down to
   the line — one `row_factory` mismatch, one identifier derived two ways. This is
   measured in hours, not days.
2. **Founder:** review the committed plan and approve `terraform apply`. The design costs
   ≈ USD 0.03/month; the ceiling is USD 5.
3. **Founder:** settle §5.1, clear the `abs_windows_path` username disclosures, then flip
   public. **Irreversible — 45 commits across 9 refs go public at once.**

## 2 — Record the video *(founder only)*

`docs/submission/VIDEO-KIT.md` has the script and the shot list. Two constraints from the
evidence: do **not** promise the AWS FIS game-day (specified, unrun), and describe recall
as *"in the top ten, three times in ten"* — never as *"it finds the precursor"* (§1.4).
The gate refusal is the moment worth filming; it is the one thing here that is
unambiguously proven.

## 3 — Close the remaining fixable reds *(engineering)*

`db` and `db-schema` are the only reds left that are neither intentional nor a founder
decision. The `db-schema` cause is already diagnosed: a test helper hand-lists a migration
subset that omits `0110` — the producer of `fn_candidate_project()` — and silently drops
`0138a` because `"0138a".isdigit()` is False. Everything else red in §4.2 should **stay**
red until the thing it reports is actually built.

---

# 7 · Appendix — the test census, both ways

The two methods disagree, and the disagreement is the finding.

**Whole suite, one process, measured today after the §3.2 fix:**

```
9,324 tests collected, 0 errors
```

Before the fix this number did not exist: collection aborted, and **no** test in the
repository could be run in a single process.

**Per-target census, committed, generated 2026-08-09** (`qa/test-state.json`,
26 targets, 40 minutes wall clock):

| pass | tests | passed | failed | errored | skipped |
|---|---|---|---|---|---|
| `none` (no cluster) | 8,845 | 8,065 | 44 | 0 | 736 |
| `cluster` | 7,187 | 6,960 | 29 | 182 | 16 |

The `cluster` pass also records 1 timed-out and 1 unmeasured target — it does not claim
those as passes.

**Why the two disagree, and which to trust.** The census runs each target as a separate
pytest process, which is why its own caveat says cross-target module-basename collisions
are "NOT measured here" — and why it ran green through the very defect that made the
whole-suite run impossible. Trust the census for per-area detail; trust the single-process
number for whether the suite runs at all. **Both are now stale in the same direction:**
the census predates 5 commits, including 44 licence-header corrections and the E3
refactor, and re-running it costs 40 minutes.

---

# 8 · What changed in this document

* §1.3 **corrected**: the earlier finding that "no AWS service has ever executed" is
  **stale and wrong**. Bedrock executes; three services are exercised; the ANN claim is
  reproduced end to end by this agent with the plan quoted.
* §1.4 **added**: the recall distribution, so the exhibit is never read as the average.
* §3.1 **promoted to BROKEN**: the demo API's own gate run reports NOT PROVEN.
* §3.2 **added**: four defects found and fixed during certification, including one that
  made the entire test suite unrunnable.
* §5.1 **added**: the account-id disclosure conflict, left unresolved on purpose because
  it is the founder's decision.
* §4.3 **sharpened**: the six lanes whose greens this agent could not falsify are named.
