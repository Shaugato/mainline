<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: CC-BY-4.0
-->

# STATE OF THE BUILD

**Certified 2026-08-11 by the final certification agent, after the thirty-worker
completion wave. Re-measured in part on 2026-08-12 by `w10-stale-sweep` at commit
`1d41442`; every re-measured section says so in its own heading.** Deadline 2026-08-18.

Every number in this document was produced by a command an agent ran itself, against the
live systems, on the date its section names. Nothing here is copied from a worker's
self-report. Where a claim did not survive re-measurement it is marked and corrected.
Where something could not be proven it says so, and says what is missing.

The one sentence a reader in a hurry needs:

> **The central claim is PROVEN and caveat-free. AWS is genuinely executed, end to end,
> and the ≥1-AWS-service rule is met with room to spare. The repository is PUBLIC. There
> is no demo URL, and there is no video. Those two are the whole gap between this
> repository and a submission, and only one of them is engineering.**

**Three things this document said on 2026-08-11 that are no longer true, corrected in
place and not deleted:** the repository is no longer private (§3.3, §5); the MI ratchet
does not stand at 28/30 (§4.2); and the CI board in §4 describes a commit five behind
`HEAD`, with §4.4 carrying the re-measurement.

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

**A second, independent probe corroborates it, and it is the one to cite** because it
records AWS request ids rather than only outcomes.
[`evidence/deploy/aws-live.json`](../evidence/deploy/aws-live.json), written by
`scripts/deploy/aws_live_probe.py` at `2026-08-11T01:11:53Z` against profile
`mainline-dev` in `ap-southeast-2`, made **four calls and none failed**:

| call | request id | result |
|---|---|---|
| `sts:GetCallerIdentity` | `04018eca-8928-459e-92a6-edffe73e34df` | HTTP 200, 339.3 ms |
| `bedrock:ListFoundationModels` | `d8c940e8-6fa9-44d7-970d-73a5d1e6b792` | HTTP 200, **64 models offered in region** |
| `bedrock-runtime:InvokeModel` `amazon.titan-embed-text-v2:0` | `b4d826e9-03ba-4368-9687-f00cc28a98ef` | HTTP 200, **1024 dimensions**, L2 norm 1.0, 13 input tokens |
| `bedrock-runtime:Converse` `au.anthropic.claude-haiku-4-5-20251001-v1:0` | `3c7a283c-9f67-4d98-aa8f-26490d54d32d` | HTTP 200, `stop_reason: end_turn`, 16 in / 8 out |

`calls_attempted: 4`, `calls_failed: []`, `total_seconds: 1.75`, verdict
**`AWS BEDROCK EXECUTED`**. The whole probe cost well under USD 0.01.

**That artefact names this document by section number, and the number has moved.** Its
`supersedes` field says *"`docs/STATE-OF-THE-BUILD.md` 3.3 recorded `ValidationException:
Operation not allowed` for every Bedrock call and concluded that no AWS service had ever
executed"*. That was true of the revision the probe was written against; the correction
landed in **§1.3, this section**, before the artefact was read, and §3.3 has since been
reused for the public-readiness record. Both are stated so a reader following the
artefact's pointer does not conclude the correction was never made. The artefact's own
`embedding_note` is worth copying as a habit: it stores dimension, first eight components,
L2 norm and a SHA-256 of the whole array rather than 1,024 floats, because those four
values are enough to recognise the vector again and are three orders of magnitude smaller.

**One thing this probe does not prove, and must not be read as proving.** Four Bedrock
calls in `ap-southeast-2` say nothing about Lambda, CloudFront, S3, KMS, IAM roles or SSM.
Those remain DESIGNED — `terraform apply` has never been run — and §2.1 is unchanged.

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

## 3.3 The repository was not safe to flip public — a record of what was true, and when

**This section was titled "The repository is not safe to flip public yet" and it is
superseded. The repository has been PUBLIC since `2026-08-11`.** It is rewritten rather
than deleted for two reasons: the movement is part of the evidence, and the findings it
enumerates did not go away when the flip happened — **a public repository still owes its
readers a disclosure register**, and this is where the register's headline lives.

### What it said, and on what date

On `2026-08-11`, at `ead0f7c` and earlier, `scripts/submission/audit_public_readiness.py`
printed:

```
VERDICT: NOT READY — failing checks: secrets_tracked, secrets_history, absolute_paths
```

122 unresolved findings. **That red was correct, it was acted on, and it went green before
the flip** — the flip-time reading was `8 checks, 7 PASS, 1 INFO, 0 FAIL; 0 unresolved,
77 allowlisted, 92 disclosed`, and `docs/submission/PUBLIC-FLIP-CHECKLIST.md` is the ticked
list. The account id was masked at `HEAD` (84 occurrences across 13 files) beforehand.

### The findings themselves, which the flip did not retract

They are a **disclosure register**, not a blocker, and they are now permanent:

| what | flip-time disposition | still true today |
|---|---|---|
| the AWS account id in `evidence/deploy/` plan files | masked at `HEAD`; kept in six documentation files as recorded evidence, declared per path | yes — §5.1 is the decision, and it can no longer be reversed |
| the same id in commits `5ddaa3a` and `e518787` | **Option A: accepted in writing**, fourteen `history-already-pushed` register entries; `git filter-repo` refused | yes — permanently readable via `git log -p` |
| `aws_access_key_id` shapes | the redaction **test vectors** and the `AKIA…EXAMPLE` id AWS prints in its own public documentation. Not credentials | yes |
| `high_entropy_secret` | cluster ids, model ids and `${ENV}` names; `MCP-CONFIG.md` inspected and clean | yes |
| `abs_windows_path` | directory layout, plus **9 files disclosing the Windows account name `shaug`** — chiefly `qa/test-state.json` (52 pytest temp paths) | yes — still exactly nine files |

**No live credential was found in the tracked tree or in history, then or now.** The
`bearer_or_jwt` family returns zero unresolved findings over 7,402 tracked files and
1,010,052 added lines. No GitHub token, no Slack token, no CockroachDB Cloud API key, and
no private key outside the deliberately published `NOT-SECRET` set.

### Where the register stands on 2026-08-12, one day after the flip

The audit now has a **post-flip mode** — the same eight checks, the same detectors, the
same findings, reported as a standing register in which every finding carries a disposition
(`repaired`, `recorded-not-repaired`, `waived-with-reason`, `undisposed`) instead of a
verdict. Its detector fingerprint is unchanged at `9cdd7b45…`, which is what proves the
mode did not buy its report by widening anything.

```
$ python scripts/submission/audit_public_readiness.py | grep -A1 'finding(s), every'
214 finding(s), every one of them carried over from the checks above:
  repaired                  23   recorded-not-repaired  57
  waived-with-reason        80   undisposed             54
$ echo $?
3
```

**54 findings are undisposed and that is red.** They accumulated in files that landed during
the completion wave, none is a credential, and they are enumerated by owning domain in
`docs/submission/PUBLIC-READINESS.md` §1.9. Exit `3` means *this register is incomplete*,
deliberately not `1`, because `1` meant *do not flip* and that sentence has no referent now.

**One measurement changed direction when the flip happened.** The pre-flip audit counted
what would be published with `git log --all` — the conservative choice while the act was
still ahead, since it can only over-count. After the flip it is the wrong instrument:
`--all` on this workstation reaches **113 commits over 67 refs**, of which **61 commits on
56 local branches were never pushed**. What a visitor can read is **52 commits over 4
branches, 47 of them on `master`**.

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
| MI ratchet | **21 of 30 invariants pending, 9 enforced** — this row said 28/30 and was seven invariants out of date | INTENTIONAL — the top-level incompleteness counter, and the red **stays** |
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

## 4.4 The board re-measured on 2026-08-12, at `1d41442`

`gh run list --branch master --limit 120`, latest run per workflow. **8 green, 10 red.**

Green: `boundary` · `claims` · `console` · `judge-pack` · `mutation-ratchet` ·
`release-proof` · `skills` · **`submission`**.

`submission` is the movement worth naming: its only remaining red was the licence-spelling
ratchet, and `python scripts/qa/check_reuse.py` now exits 0 — `7402 tracked files, 0
uncovered, 4 licence texts, no counted number rose`, with `FSL-1.1-ALv2` at 1213 against a
floor of 1213. **No baseline was lowered; the migration closed the gap.**

**Two of the ten reds assert nothing about this repository**, and a judge reading the
Actions tab cannot see that without opening the logs. `supply-chain` and nine of `ci`'s
twelve jobs died in `astral-sh/setup-uv` on `connect ECONNREFUSED 54.185.253.63:443`, and
`ci`'s `actionlint` job on `curl: (7) Failed to connect to
release-assets.githubusercontent.com`. `db`'s single failing job died the same way. Those
are runner-network failures; nothing is claimed from them in either direction, which is the
same discipline §4 applied to the two-second gate-job failures on `57c477c`.

The remaining reds report real conditions and are covered in §4.2 and `docs/CI-STATE.md`.
**No `ci` run on `master` since `47f8aa2` has produced a usable measurement of this
repository** — the two runs before this one failed at the `checkers` gate with everything
after it skipped. That is the honest state of the `ci` lane and it is worth more than a
colour.

---

# 5 · Rules-compliance matrix

| requirement | status | evidence / what is missing |
|---|---|---|
| New project inside the window | **MET** | first commit 2026-08-05 |
| OSS licence | **MET** | `LICENSE` (Apache-2.0) + `LICENSES/`; `check_reuse.py` exits 0 over 7,402 files, 0 uncovered |
| **Public repository** | **MET** | flipped `2026-08-11`. `gh repo view Shaugato/mainline --json visibility` → `{"visibility":"PUBLIC"}`; signed-out `curl -sI` → `HTTP/1.1 200 OK`. 52 commits over 4 branches published; the standing disclosure register is §3.3 |
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
`docs/submission/DISCLOSURE-DECISIONS.yaml`. When this section was written those four files
were **not declared there**, so the `aws-evidence` red was correct under the project's own
ruling and this agent deliberately did not grant the exemption.

### 5.2 How it was settled, on 2026-08-11, before the flip

**Both resolutions were used, on different files.** Where the id was an *executable
default* it was **redacted** — `EXPECTED_ACCOUNT` in `deploy.sh`, variable defaults in
`variables.tf`, the S3 `backend-config` example, an interpolated bucket name — and the value
is now derived at run time from `aws sts get-caller-identity`. Where it is *recorded
evidence* it was **declared**: six paths, granted per path with a class, a date, a decider
and a reason, because a redacted transcript is not a transcript and a refusal with the
account elided cannot be matched against an AWS support case. The founder ratified both at
`PUBLIC-FLIP-CHECKLIST.md` item 8.

**The history half was settled as Option A, in writing.** The id is in commits `5ddaa3a`
and `e518787`, both already on `origin/master`. Fourteen `history-already-pushed` register
entries accept it rather than rewriting shared history, because `git filter-repo
--replace-text` plus a force-push would invalidate every commit SHA this repository's own
evidence artefacts cite, in order to hide a value that is not a credential.

**This is no longer reversible. It was settled before the flip, and the flip has happened.**

### 5.3 The mask is itself a finding, and the disagreement is left standing

`aws-evidence` is still red, and its message is now about the *replacement*:

```
[SEC-ACCOUNT-ID] evidence/deploy/deploy-dry-run.json:409: a bare 12-digit run
'999999999999' survives UUID/digest/decimal masking and has the shape of an AWS
account id
```

`scripts/submission/audit_public_readiness.py` flags the same shape in
`evidence/deploy/terraform-plan-furl.json`, where the mask is `000000000000`. Two checkers
disagree about whether twelve identical digits is a mask or a value. Both positions are
defensible; **neither was silenced to buy a green**, and recording the disagreement in a
document that owns neither checker is cheaper and more honest than picking a winner.

---

# 6 · The top three things to do next, in order

## 1 — Fix the demo API, then deploy *(engineering, then founder)*

**Step 3 of this list — flip public — was done on `2026-08-11`** and is struck from it.
52 commits over 4 branches are published; §3.3 is the standing disclosure register.

The order still matters: deploying the app in its current state produces a demo URL that
says **NOT PROVEN**, which is worse than no URL.

1. **Engineering:** fix the two defects in §3.1. Both are small and both are named down to
   the line — one `row_factory` mismatch, one identifier derived two ways. This is
   measured in hours, not days.
2. **Founder:** review the committed plan and approve `terraform apply`. The design costs
   ≈ USD 0.03/month; the ceiling is USD 5.
3. ~~**Founder:** settle §5.1, clear the `abs_windows_path` username disclosures, then flip
   public.~~ **DONE 2026-08-11.** §5.1 was settled (§5.2); the username disclosures were
   *recorded, not repaired*, which is a decision and not an omission. What remains is the
   54 undisposed findings that accumulated after the flip — hygiene, not a blocker, listed
   by owning domain in `docs/submission/PUBLIC-READINESS.md` §1.9.

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

## 8.1 What `w10-stale-sweep` changed on 2026-08-12, at `1d41442`

* §1.3 **extended**: `evidence/deploy/aws-live.json` — four Bedrock-plane calls with AWS
  request ids, `calls_failed: []`, verdict `AWS BEDROCK EXECUTED`. The artefact names this
  document's §3.3 as the thing it supersedes; that section number has since been reused,
  and both facts are stated so the pointer does not read as an uncorrected error.
* §3.3 **rewritten from a blocker into a dated record**. The heading claimed the repository
  was not safe to flip; the flip happened on `2026-08-11`. **Not one finding was dropped** —
  they are a disclosure register a public repository still owes its readers, and the
  post-flip audit reports all 214 of them with a disposition each, 54 of them undisposed
  and red.
* §4.2 **corrected**: the MI ratchet is **21 of 30 pending, 9 enforced**, not 28/30.
  `python scripts/mi_ratchet.py` prints `21 pending / 9 enforced`. The lane stays red; a
  sharper number is a sharper red.
* §4.4 **added**: the board at `1d41442` — 8 green, 10 red — with the two lanes whose reds
  are runner-network failures named, because a colour that means nothing is worse than no
  colour.
* §5 **corrected**: `Public repository` moved `UNMET` → `MET`, with the two commands that
  check it. `URL to a functional demo` is unchanged and still `UNMET`.
* §5.2 and §5.3 **added**: how the account-id decision was actually settled, and the
  disagreement between two checkers about whether twelve identical digits is a mask.
* §6 item 1 **updated**: the flip step is struck, done.

**One number was re-derived once and made consistent across all eight files this worker
owns.** It appeared as 38, 44, 45 and 53 in different places. Measured: `master` carries
**47** commits (`git rev-list --count origin/master`, corroborated by the GitHub API's
`rel="last"` page), the published surface is **52 commits over 4 branches**, and
`git log --all` on this workstation reaches 113 over 67 refs — a number about a machine,
not about a repository.
