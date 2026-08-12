<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: CC-BY-4.0
-->

# CI state — what GitHub actually says

**Re-measured 2026-08-12 by W10, at commit `1d41442` on `master`, on a repository that is
PUBLIC.** Every conclusion below is a run id you can open without an account. Every cause
is quoted from a real log I read in the same sitting I created it, not inferred from a
plan.

This document replaces the version published at `47f8aa2`. **Six of that version's claims
did not survive re-measurement** and are corrected in §5. (An unpublished intermediate
revision existed in the working tree between the two; it is superseded by this one and
never reached a commit.)

**One caveat governs the whole page, and it is stated once here.** `1d41442` is the last
commit on `master`. The repairs this wave produced — the egress fix, the lint work, the
sharper reds, the honest teardown transcript — sit in the working tree and on the
`w1/…`, `w2/…`, `w5/…`, `w7/…` branches, **uncommitted at the moment of measurement**. So
this board is the state the wave *inherited plus what it could prove on a branch*, not the
state it *left*. Every row measured on a branch says so, with the branch named. **The
first task after the wave's commit is to re-dispatch the six lanes marked §2.1, §4.2 and
§4.3 and replace their rows.** No row here is projected forward, and no repair is credited
before a run id exists for it.

**What a judge scanning the Actions tab needs to know first:** `master` shows **8 green
and 10 red**, and **three of those reds assert nothing about this repository** — they are
runner-network failures in jobs that never executed a single check. A red that means
nothing costs a reader the same attention as a real one. Those three are now diagnosed and
repaired on a branch (§2.1), and this page carries the **first measurement of the `ci`
lane's real content since `b0fe884`** (§2.2). It is not flattering and it is not supposed
to be.

---

## 0. Re-check it yourself

```bash
# every workflow's real conclusion on the default branch
gh run list --branch master --limit 200 --json databaseId,workflowName,conclusion,createdAt \
  --jq 'group_by(.workflowName)[] | max_by(.createdAt) | "\(.workflowName)|\(.conclusion)|\(.databaseId)"'

# one workflow's conclusion, job by job
gh run view <run-id> --json jobs --jq '.jobs[] | "\(.conclusion) :: \(.name)"'

# the precise cause of a red — the command every claim below rests on
gh run view <run-id> --log-failed
```

Every workflow in this repository declares `workflow_dispatch`, so any row here can be
re-created rather than merely re-read.

**Logs expire within hours on this repository.** Every run cited from `2026-08-11`
(`cloud-verify`, `nightly-differential`) now answers `log not found`. Where that is true
this page says so and makes no claim about the cause.

---

## 1. Every workflow, with its real conclusion

Latest run per workflow on `master`. A lane whose `paths:` filter did not match the last
few commits carries an older SHA — that is not staleness in the table, it is the lane
truthfully not having been asked.

| workflow | conclusion | run | at | §|
|---|---|---|---|---|
| `boundary` | success | 31596449113 | `1d41442` | §6 |
| `claims` | success | 31596451954 | `1d41442` | §6 |
| `console` | success | 31605711724 | `1d41442` | §6 |
| `judge-pack` | success | 31605705752 | `1d41442` | §6 |
| `mutation-ratchet` | success | 31596662350 | `1d41442` | §6 |
| `release-proof` | success | 31605714844 | `1d41442` | §6 |
| `skills` | success | 31605708672 | `1d41442` | §6 |
| `submission` | success | 31596458067 | `1d41442` | §4.1 |
| `aws-evidence` | failure | 31596455267 | `1d41442` | §3.5 |
| `ci` | failure | 31596249352 | `1d41442` | §2 |
| `cloud-verify` | failure | 31520085557 | `ca912eb` | §4.3 |
| `custody-chain` | failure | 31596645067 | `1d41442` | §3.1 |
| `db` | failure | 31596634515 | `1d41442` | §2.1, §4.2 |
| `db-schema` | failure | 31600802469 | `1d41442` | §3.3 |
| `demo-health` | failure | 31614091734 | `1d41442` | §3.4 |
| `nightly-differential` | failure | 31512623640 | `ca912eb` | §4.3 |
| `schema` | failure | 31616006380 | `1d41442` | §3.2 |
| `supply-chain` | failure | 31596446007 | `1d41442` | §2.1 |

**Score: 8 green, 10 red, 0 never-run.** (A nineteenth entry, `Dependabot Updates`, is
GitHub's own managed workflow and is not this repository's lane.)

Of the ten reds: **three were caused by the runner's network and assert nothing** — `ci`,
`supply-chain`, `db` (§2.1); **five report a true incompleteness and are meant to stay
red** — `aws-evidence`, `custody-chain`, `db-schema`, `demo-health`, `schema` (§3); and
**two are untidy and unmeasured** — `cloud-verify`, `nightly-differential` (§4.3). A sixth
declared red, the `g4alpha` gates, is not a workflow of its own and rides inside `ci`
(§3.6).

---

## 2. `ci` — and the first run since `b0fe884` in which every job executed

### 2.1 Why nine `ci` jobs, three `supply-chain` jobs and `db` all died in the same place

Run **31596249352**. Nine of twelve jobs failed. **Not one of the nine failed a repository
check.** The same failure took out `supply-chain` (all three jobs, run 31596446007) and
`db`'s single job (run 31596634515).

```
actionlint / Install actionlint:
  curl: (7) Failed to connect to release-assets.githubusercontent.com port 443
  after 1 ms: Couldn't connect to server

the other eight / Run ./.github/actions/setup-workspace:
  ##[error]connect ECONNREFUSED 54.185.253.63:443
```

**The cause is now known, and it is not a regression in this repository.** From
`step-security/harden-runner`'s own post-step agent log, quoted in
`.github/actions/setup-workspace/action.yml`:

```
Downloading uv from "https://github.com/astral-sh/uv/releases/download/0.12.3/…"
Wed, 12 Aug 2026 12:26:48 GMT:domain not allowed: release-assets.githubusercontent.com.
```

GitHub now serves release-asset **bodies** from `release-assets.githubusercontent.com`.
The older `objects.githubusercontent.com`, which every `allowed-endpoints` list in this
repository named, no longer receives that redirect. `egress-policy: block` refused a
connection it could not match — **correct behaviour by a control doing its job.**
`supply-chain` had been green at `b0fe884` with no change to the workflow, to `uv.lock` or
to the composite action in between: the destination moved underneath a correct deny-list.

Two repairs were considered and rejected, and are recorded so neither is re-proposed:
`egress-policy: audit` retires the assertion instead of updating it, and a `uv-version`
pin would not have worked — the URL in the log already carries an exact version, because
`latest` had resolved against `api.github.com` one line earlier. **A version selects a
tag; it does not select a host.**

### 2.2 What `ci` says once it can start

Run **[31615364211](https://github.com/Shaugato/mainline/actions/runs/31615364211)**, on
branch `w10-base` = `1d41442` + the endpoint repair and nothing else. **8 of 12 jobs
green.** This is the only current measurement of this lane's content.

| | job | |
|---|---|---|
| success | every checker this lane invokes exists | |
| success | actionlint | *(green for the first time — §2.1's `curl` now reaches its host)* |
| success | REUSE — every file names its licence | §6.2 |
| success | import-linter contracts · and no package outside them | untested |
| success | the sequence ban, repository-wide | §6.2 |
| success | the lockfile is authoritative · workspace membership | untested |
| success | PL-2 — the red run is recorded | untested |
| success | RED BY DESIGN, and it must stay red | §6.2 — **falsified twice** |
| failure | ruff format · the counted lint ratchet | §2.3 |
| failure | mypy · and the target list is complete | §2.4 |
| failure | pytest --crdb=none (no cluster, no credential, no network) | §2.5 |
| failure | CI summary | downstream of the three above |

**The branch was deleted; `ci.yml` belongs to W2 and the endpoint repair on it was mine
for the experiment only.** When W2's `ci.yml` lands this run must be re-created. Nothing
in §2.3–§2.5 depends on the endpoint list.

### 2.3 `ruff` — the format half is at zero, the lint half regressed by 17 rules

**Both halves measured on the runner, in the same job, in run 31615364211.**

```
ruff format --check:   1433 files already formatted
```

**Zero unformatted files.** This settles a claim that has confused three revisions of this
page: `ruff format --check .` on the founder's Windows workstation reports 243–245 files
would be reformatted, and **that number is a CRLF artefact** of a checkout with
`core.autocrlf=true` meeting `ruff.toml`'s `line-ending = "lf"`. Until today the "0" was
only ever measured on a local LF worktree. It is now measured on the runner. **Do not
quote the local format count as the tree's, and do not make the 249-file format commit
that number seems to ask for.**

The lint half is a real regression, introduced by `ca912eb`, and it is what fails the job:

```
LINT REGRESSION  rule=BLE001   tree=scripts/               baseline=0   measured=2  [HARD GATE]
LINT REGRESSION  rule=E402     tree=scripts/               baseline=0   measured=6  [HARD GATE]
LINT REGRESSION  rule=N803     tree=packages/trappoint-*   baseline=0   measured=2  [HARD GATE]
LINT REGRESSION  rule=N803     tree=tests/                 baseline=0   measured=2  [HARD GATE]
LINT REGRESSION  rule=PTH123   tree=scripts/               baseline=0   measured=2  [HARD GATE]
LINT REGRESSION  rule=PTH202   tree=scripts/               baseline=0   measured=1  [HARD GATE]
LINT REGRESSION  rule=RUF001   tree=packages/trappoint-*   baseline=0   measured=1  [HARD GATE]
LINT REGRESSION  rule=UP030    tree=scripts/               baseline=0   measured=5  [HARD GATE]
LINT REGRESSION  rule=PLR0912  tree=scripts/               baseline=2   measured=7
LINT REGRESSION  rule=PLR0915  tree=scripts/               baseline=1   measured=7
LINT REGRESSION  rule=D102/D105/D107/D401  tree=packages/trappoint-*   +21 across four rules
LINT REGRESSION  rule=E402     tree=tests/    1 -> 6      rule=ARG002  tree=tests/  1 -> 4
LINT REGRESSION  rule=E501     tree=scripts/  1 -> 2
```

**17 rules, 8 of them hard gates** — counted from the runner log, `17` rows carrying
`rule=` and `8` carrying `[HARD GATE]`. (A hard gate is a rule whose baseline is 0, so any
hit at all is a breach. `docs/leads/ci-green-plan2.md` §3.3 says "7 hard gates" in prose
while listing eight; the runner says eight and this page follows the runner.) Owners: W3
(`scripts/`), W4 (`packages/`, `tests/`), W2
(`qa/ruff-ratchet.json`, which **may fall and may never rise**). Two of these must not be
"fixed" by renaming: `modelId` and `contentType` in `bedrock_backend.py` are boto3 API
parameter names, and the `RUF001` hit in `tests/unit/domain/canon/test_idempotence.py` is
a deliberate Unicode test vector — the ambiguity is the thing under test. Both need a
`# noqa` that states the reason.

### 2.4 `mypy`

```
packages/trappoint-recall/src/trappoint_recall/eval/bedrock_backend.py:1140:29: error:
packages/trappoint-recall/src/trappoint_recall/eval/bedrock_backend.py:1141:28: error:
packages/trappoint-recall/src/trappoint_recall/eval/bedrock_backend.py:1159:29: error:
packages/trappoint-recall/src/trappoint_recall/eval/bedrock_backend.py:1160:28: error:
Found 4 errors in 1 file (checked 661 source files)
```

One file, four errors, all in the Bedrock backend that `ca912eb` added. Owner: W4.

### 2.5 `pytest --crdb=none` — 17 failed, and nine of them are one cause

```
17 failed, 8455 passed, 839 skipped, 13 deselected, 2 warnings in 326.98s (0:05:26)
```

The previous revision of this page quoted `21 failed, 8280 passed` from run 31462708400
and could not re-measure it. **This is the re-measurement.**

**Nine of the seventeen are the canonicaliser drift**, and it is the same finding §3.1
records against `custody-chain` — one drift, surfacing in three lanes:

```
FAILED tests/integration/custody/test_k2_exit.py::test_canonicaliser_registry_is_pinned_and_retained
  canon_v1: packages/trappoint-jcs/src/trappoint_jcs/canon_v1.py hashes to
  d09036a85b023c86e729a9307a834e2238910ee07798a45f4cae9d13887ad77a,
  registry pins 260ed37ddc610f1fb94ddce98998fe4ae5ce883698ad5c7033839cd258dcd659
```

and it cascades through `packages/trappoint-verify/tests/test_structural_checks.py`,
`test_no_network.py`, `test_checks_totality.py` and
`packages/trappoint-ledger/tests/test_checkpoint_body.py`. The remaining eight are
independent and each names its missing artefact:

```
FAILED tests/integration/custody/test_k2_exit.py::test_k2_4_… — MISSING ARTEFACT: evidence/k2-checkpoint-cadence.json
FAILED tests/integration/custody/test_k2_exit.py::test_k2_5_… — MISSING ENTRY: spec/CHANGELOG.md carries no line naming `wire/checkpoint.md` at v1.0
FAILED tests/integration/custody/test_k2_exit.py::test_k2_6_… — MISSING ARTEFACT: evidence/k2-migration-attestation.json
FAILED tests/integration/schema/test_mi_blame.py::test_dm9_the_closure_is_read_only_through_the_view
FAILED tests/release/test_ruff_ratchet.py::test_the_ratchet_passes_on_the_real_tree   (§2.3, the same 17 rules)
FAILED packages/mainline-agentkit/tests/test_live_cassettes.py::test_every_recorded_body_hashes_to_its_index_row
FAILED packages/trappoint-migrate/tests/test_lockfile.py::test_the_committed_manifest_is_current — run `trappoint migrate lock --write`
```

**None of these is a flake and none is a threshold.** Each is a named artefact that does
not exist or a recorded hash that no longer matches its source.

---

## 3. The reds that are meant to be red

Five workflow lanes, plus one declared red that rides inside `ci` (§3.6). Each names the
artefact that does not exist and the domain that owes it. **None of them may be made green
by weakening anything.**

### 3.1 `custody-chain` — 7 of 16 checks unimplemented, and one real drift

Run 31596645067. Confirmed off CI with the verifier this workstation already has:

```
$ .venv/Scripts/trappoint-verify verify --bundle evidence/reference-ledger/bundle.json
16 checks | 8 passed | 1 failed | 7 not checked
exit 1: 1 finding(s). This bundle does not verify.
```

and re-confirmed on the runner inside run 31615364211's pytest job, which prints the same
line: `16 checks | 8 passed | 1 failed | 7 not checked`.

The seven that **do not run** are the cryptographic half — log signature, RFC-3161
bracket, beacon, witness quorum, S3 object-lock, gate self-attestation, WebAuthn
re-verification. Each names its owner (`verify-crypto`) and prints what it *would* have
proved. **Missing artefact: seven crypto check implementations. Owner: custody domain.**

**The one FAILED check is not a not-implemented and is the more interesting half.**
`canonicaliser_identity` reports nine findings: the bundle's signed `canon_src_sha256` is
`260ed37d…` and the canonicaliser in the verifier now hashes to `d09036a8…`, so eight
checkpoints' signed `canon:` lines disagree with the code that would recompute them.
**That is exactly the drift the check exists to catch, and it is catching it.** It is
reported rather than repaired because `packages/trappoint-verify` and
`evidence/reference-ledger/` belong to the custody domain. **Missing artefact: either a
regenerated reference bundle or a restored `canon_v1.py`. Owner: custody domain.**

The CI run additionally fails `RFC 6962 merkle — vectors and properties`, `reference
bundle regenerates to zero diff`, and an exhibit-vocabulary check whose message is itself
the finding: `Quorum is q=1 over our own infrastructure, which is not adverse in the legal
sense.`

### 3.2 `schema` — the reference vertical has **two** missing producers, not one

Run 31596641256, re-dispatched as 31616006380 with the same result. **The previous
revision of this page named one object. The measured truth is two**, and CI has been
saying so all along:

```
##[error]2 object(s) referenced by packages/trappoint-sql/refvertical/sql and created by
nothing: trappoint_ref.clause, trappoint_ref.event

##[error]MISSING PRODUCER: trappoint_ref.clause -- consumed by 0066_disposition (FOREIGN
KEY target) -- expected: a CREATE TABLE migration in packages/trappoint-sql/refvertical/sql/
-- MAINLINE twin that already exists: verticals/mainline/db/migrations/0028_clause.sql
-- owner: KERNEL domain, docs/leads/kernel.md 1.1

##[error]trappoint_ref.event is referenced by 0058_blocking_check and created by no file
in packages/trappoint-sql/refvertical/sql. Owner: KERNEL domain, docs/leads/kernel.md 1.1
```

Reproduced locally against the pinned node in one command:

```
$ trappoint migrate up --dsn <local> --tree trappoint-ref \
    --migrations packages/trappoint-sql/refvertical/sql ; echo $?
trappoint migrate: REFUSED: 0058_blocking_check:
  [42P01] relation "trappoint_ref.event" does not exist
1
```

**Missing artefacts: two `CREATE TABLE` migrations, `trappoint_ref.clause` and
`trappoint_ref.event`. Owner: KERNEL domain, `docs/leads/kernel.md` §1.1.**

**This red has a consequence outside its own lane**, and `VERIFY.md` says so: the
reference-vertical conformance path a stranger is invited to run halts here.
`trappoint-conform --profile trappoint-ref` reports `0/45 · failed 6 · cannot_run 38 ·
error 1`. **The MAINLINE path is unaffected and proves the central claim on its own** —
`scripts/proof/gate_refusal.py` returns `271/271 applied, 0 failed … VERDICT PROVEN`.

### 3.3 `db-schema` — the catalogue, and `mi-red` at 21 of 30

Run 31600802469. Two jobs fail: `the catalogue is committed, current and well-formed` and
`mi-red and mi-green`.

**The MI ratchet stands at 21 of 30 pending, 9 enforced.** Re-derived on this machine
today:

```
$ .venv/Scripts/python.exe scripts/mi_ratchet.py | tail -1
21 pending / 9 enforced
```

**The red stays.** The test's own message is computed (`f"{len(pending)} of
{len(catalogue)}"`), so it has always printed the true number; what was stale was the
prose around it, and `ci.yml:702` now reads `21 of 30`. Nine invariants have been promoted
since that string said `28 of 30`; an intentional red seven invariants out of date is an
intentional red losing its precision.

`mi-red`'s failure is not a count. It refuses three invariants — `MI22`, `MI26`, `MI27` —
because they are recorded `pending` while every owning test passes, and it prints the
reason a promotion would be false:

```
REVIEW: promote only if one of the tests above makes an object above REFUSE. A test
that would still pass with that object dropped witnesses nothing, and an `enforced`
row recorded on it is the false green PL-2 exists to forbid.
```

**Missing artefacts: 21 invariant implementations, and a current
`verticals/mainline/db/invariants/mi_catalogue.yaml` projection. Owner: W6 for the
workflow and the ratchet's wording; `dm-functions-triggers` and the kernel projection
band for the invariants themselves.**

### 3.4 `demo-health` — no demo is deployed

Run 31614091734, and a new one every thirty minutes. The message is the best-worded red in
the tree and the model the others were brought up to:

```
no demo URL is published; this lane is red because the demo is not deployed, not
because it is broken. docs/submission/SUBMISSION.json holds demo_url=UNRESOLVED.
terraform apply has not been run — the plan is committed and the founder reviews it
before any apply. This job starts asserting, and can go green on its own, the moment
that field holds a URL. Nothing else has to change: no repository variable, no secret,
no edit to this workflow.
```

**Missing artefact: a deployed demo URL in `docs/submission/SUBMISSION.json`. Owner: the
orchestrator — the cure is a deployment, not a workflow edit.**

### 3.5 `aws-evidence` — the mask is now the finding

Run 31596455267:

```
[SEC-ACCOUNT-ID] evidence/deploy/deploy-dry-run.json:409: a bare 12-digit run
'999999999999' survives UUID/digest/decimal masking and has the shape of an AWS
account id. An account number is not a credential, and publishing one still enables
cross-account enumeration
```

**The account id was masked before the repository went public, and the mask itself trips
the checker.** The checker is right and must not be weakened. The subtlety is that lines
409/412 are a **recorded transcript of a real teardown dry-run**, in which `999999999999`
was the deliberately-wrong `--expect-account` value that provoked the refusal. Editing the
transcript to satisfy the scanner would turn real evidence into a forgery.

**Missing artefact: a re-run of the teardown dry-run with a non-account-shaped
expectation, recorded as it actually happened. Owner: W5.**

**W5's repair exists and is uncommitted.** In the working tree at the time of writing,
`evidence/deploy/deploy-dry-run.json` carries **zero** occurrences of `999999999999`
(`git show HEAD:` on the same file carries two) and
`evidence/deploy/terraform-plan-furl.json` carries zero occurrences of `000000000000`.
`aws-evidence.yml`'s own header records the method: *"`verify_evidence.py` was NOT relaxed
and no exclusion was added for the offending path — the dry-run was re-run with a
non-numeric expectation."* **That repair has no run id yet**, so this page keeps the red
and does not credit it. Re-dispatch `aws-evidence` after the wave's commit.

At HEAD, `scripts/submission/audit_public_readiness.py` flags the same shape in
`evidence/deploy/terraform-plan-furl.json`, where the mask is `000000000000`. Two checkers
disagreed about whether twelve identical digits is a mask or a value. Both were
defensible; **neither was silenced**, and the disagreement was recorded rather than
resolved by a page that owns neither. It is resolved in the working tree by removing the
digits, not by relaxing either checker.

The lane's second failure is its own negative control refusing to run, which is correct
and worth quoting because it is unusual:

```
FAMILY red-for-the-wrong-reason: an unmutated copy of evidence/ already fails, so
every plant below would be red for a reason that is not its plant
```

A planted-violation harness that fires while the unmutated control is already red proves
nothing. **It says so instead of counting the plants as caught.** §6.3 records that this
exact shape occurs a second time, in `supply-chain`.

### 3.6 `g4alpha` — the five recall gates, red by declaration

Not a workflow of its own; five cases in `tests/eval/recall/test_g4alpha_gates.py`,
carried by `ci`'s `RED BY DESIGN` job. Retro-recall on the offline fixture corpus does not
meet the gates and is declared RED until K4. **Missing artefact: recall quality that meets
the five gates. Owner: the recall domain, K4.**

---

## 4. The untidy reds

### 4.1 The licence migration finished, and `submission` went green

The published revision of this page recorded

```
REFUSED [RATCHET] metric=non_spdx_spelling.FSL-1.1-ALv2 baseline=1213 measured=1254
```

and called it "the **only** thing keeping `submission` red". **It is done.** Measured
2026-08-12 on this workstation:

```
$ .venv/Scripts/python.exe scripts/qa/check_reuse.py ; echo $?
  improved   metric=reuse_toml_patterns_matching_nothing baseline=5 measured=1
OK — 7402 tracked files, 0 uncovered, 4 licence texts, no counted number rose.
0
```

**No baseline was lowered and no ratchet was re-frozen upward** — the count came down to
meet the number that was already published, which is the only move a falling ratchet
permits. `submission` is green on `master` at `1d41442`, run 31596458067.

### 4.2 `db`'s pin restatement — still owed, and never measured at HEAD

`cloud-verify.yml` and `release-proof.yml` write the CockroachDB image literal in order to
compare it against `compose.yaml`, and `db`'s HARD check over six OWNED harness files
refuses that correctly. The repair is unchanged: extract it the way
`trappoint_migrate.crdb.pinned_image` already does — find the `trappoint:crdb-image-pin`
marker, take the first `image:` line within the next three — which spells no image literal
at all and takes the census `restated` count from 25 to 19 without a ceiling moving.

**`db` has not reached that check on any run at `1d41442`** — its only job died in
`setup-uv` (§2.1). The finding is carried forward from run 31463897045 at `47f8aa2` rather
than re-observed. **Owner: W1. Its next run is the measurement that matters.**

`db.yml` deliberately does not absorb these lines into its census. An earlier attempt
(`f229c1b`) taught the census to treat them as a self-policing guard and was reverted whole
in `47f8aa2`, because `db.yml`'s own comment says an exclusion list "is a place to hide a
real regression".

### 4.3 `cloud-verify` and `nightly-differential` — red, at an older commit, logs expired

Both last ran at `ca912eb` on `2026-08-11`, two commits behind `HEAD`, and
`gh run view --log-failed` now answers `log not found` for each. The job names are readable
and the causes are not:

* `cloud-verify` 31520085557 — `is there a Cloud cluster to verify against? (and can it say
  no?)` and `a real 40001 RETRY_SERIALIZABLE, and the loop that must not swallow it` failed;
  two jobs skipped behind them, including `SKIPPED — no Cloud cluster secret`.
* `nightly-differential` 31512623640 — `differential · read-committed`, `differential ·
  serializable` and `64 parallel merges of one subject` failed.

**This page makes no claim about why.** Both need a live cluster this wave did not
provision. What is still true of `nightly-differential` by construction is that the lane
refuses to report green on a skip: a cluster is running in the job, so a skip means the
suite could not reach it.

---

## 5. Claims in the published version of this document that did not survive

The published version was measured at `47f8aa2`. Six of its claims are now false. They are
listed rather than silently overwritten, because a page that only ever agrees with itself
teaches a reader nothing about how much to trust it.

### 5.1 "`claims`, `boundary` and `submission` are RED"

**False.** All three are **green** at `1d41442` — runs 31596451954, 31596449113 and
31596458067 — and green again on unmutated throwaway branches cut from it
(W8: 31604450388, 31604455314, 31604458802), and green a third time after a plant was
reverted (31607037059, 31607033539, 31607040186). `submission`'s cure is §4.1;
`boundary`'s was the two lint findings the previous revision named, since paid.

### 5.2 "`supply-chain` is green"

**False, and it went the bad way.** It failed at `1d41442`, run 31596446007, all three
jobs, for the §2.1 network cause. It is **green again** once that is repaired — run
[31615368325](https://github.com/Shaugato/mainline/actions/runs/31615368325), 4 of 4 jobs
— on a branch carrying only the endpoint fix.

### 5.3 "`schema` — the reference vertical has no producer" (singular)

**Understated.** CI names **two**: `trappoint_ref.clause` as well as `trappoint_ref.event`.
Corrected in §3.2 with the log line.

### 5.4 "REUSE is the only thing keeping `submission` red"

**Survives as a diagnosis and is now spent as a finding**: the migration finished,
`check_reuse.py` returns `OK — 7402 tracked files, 0 uncovered`, and `submission` is green
(§4.1).

### 5.5 "`ruff format` — 243/245 files would be reformatted"

**A CRLF artefact of the founder's workstation, not a property of the tree.** The runner
reports `1433 files already formatted` (run 31615364211, §2.3). The published revision
carried the local number without that qualification. **The lint half, however, regressed by
17 rules with 8 hard gates and is real** — also §2.3.

### 5.6 "`supply-chain`'s proof is the weakest of any green lane"

**False at `1d41442`, and this is the correction that matters most for §6.** The lane
carries a step named `RED — four planted violations, each refused BY NAME` which writes the
assertion to a file, runs it against four mutated copies of both witnesses, and requires
each to be refused with a named title and a named needle. Its proof is now among the
stronger ones. It has a different weakness, which is new and is recorded in §6.3.

### 5.7 Two claims that survived re-measurement

Kept here so the list is not read as a list of only failures.

* **"`RED_SELECTOR` is half-connected; `pl2_red` is registered nowhere"** — repaired on
  2026-08-10 and verified today. `pl2_red` is registered at `pyproject.toml:112` carrying
  `scripts/mi_ratchet.py`'s `PL2_RED_MARKER_DESCRIPTION` verbatim, and applied to eight
  cases. `-m "g4alpha or pl2_red"` collects `13/9324`; `hermetic-tests` runs the exact
  complement. §6.2 proves the guard that keeps it that way.
* **"The MI ratchet stands at 21 of 30, not 28 of 30"** — re-derived today,
  `21 pending / 9 enforced`. Carried into §3.3 as current state rather than as a
  correction. The surviving `28 of 30` strings live in superseded planning documents under
  `docs/leads/`, which are records of what was planned and are not re-based.

---

## 6. Anti-vacuity — which greens are load-bearing, and which are not proven

**A green that cannot fail is worth less than an honest red, and the Actions tab is
public.** Three workers did nothing this wave but try to break the green lanes: establish
that the unmutated tree is green, plant one violation per promise, dispatch from a
throwaway branch, and require the lane to go red *naming the plant*. **No plant was ever
pushed to `master`**, and every plant branch was deleted after its log was read.

The rule this section is written under: **possession of a job called `RED — …` is not a
falsification.** Only a run id in which a lane went red for a planted reason is. A lane
without one is named unproven, and that is a successful outcome for a worker rather than a
failed one.

### 6.1 Falsification, lane by lane

| lane | falsified? | the strongest single experiment | run |
|---|---|---|---|
| `boundary` | **yes** | E1/E2/E3/E4 each planted separately — no model IAM, no network path, no code path, no prompt path | 31605107711, 31605111824, 31605115674, 31605119482 |
| `claims` | **yes** | one MNC-01 sentence appended to `README.md` → `[MNC-01-rls-vs-rogue-admin] README.md:298` | 31605707995 |
| `submission` | **yes** | the gate must import with nothing installed — `import jsonschema` at module top | 31606023333 |
| `judge-pack` | **yes**, 3 of 4 jobs | a negative loses `must_fail_because` | 31605910666 |
| `release-proof` | **yes** | the gate weakened to a tautology → `VERDICT NOT PROVEN` with the failing clause named | 31604562363 |
| `skills` | **yes** | the reference gate weakened; a merge claim; a dangling marketplace path | 31604638902 |
| `console` | **yes** | a 3D import planted in the EVIDENCE register → `pnpm run ci` refuses | 31604695307 |
| `mutation-ratchet` | **yes** | `--disable` made a no-op → `PL-2 FAILED: disabling R1_DEONTIC did not lower the kill rate`, both arms `wilson_lower = 0.909774` | [31615605021](https://github.com/Shaugato/mainline/actions/runs/31615605021) |
| `supply-chain` | **yes**, twice | `boto3` added to `mainline-gate-svc`'s lock edge → `resolves model SDK distribution(s) ['boto3', 'botocore']` | [31615598216](https://github.com/Shaugato/mainline/actions/runs/31615598216) |
| `supply-chain` | **yes** (the vacuity guard itself) | `mainline-domain` dropped → `did not name ['mainline-domain']`, refused by **both** witnesses independently | [31615601879](https://github.com/Shaugato/mainline/actions/runs/31615601879) |
| `ci` (per job) | **partly** | §6.2 | |
| `aws-evidence` | n/a — red | its own negative control is refusing to run, correctly (§3.5) | 31596455267 |

Full evidence, with every plant, every quoted log line and every branch name:
`docs/ci/anti-vacuity/w8-claims-boundary-submission.md`,
`docs/ci/anti-vacuity/w9-judge-release-skills-console.md`,
`docs/ci/anti-vacuity/w10-ci-supplychain-mutation.md`.

### 6.2 `ci` is a lane where the question is per-job, and five jobs are unproven

`ci`'s summary tick answers nothing about any individual promise. Of the eight jobs green
in run 31615364211:

| job | falsified? | run |
|---|---|---|
| `RED BY DESIGN, and it must stay red` — the **floor** | **yes** | [31615590317](https://github.com/Shaugato/mainline/actions/runs/31615590317) |
| `RED BY DESIGN` — the **empty-collection** guard | **yes** | [31615594567](https://github.com/Shaugato/mainline/actions/runs/31615594567) |
| `the sequence ban, repository-wide` | **yes** | [31616522487](https://github.com/Shaugato/mainline/actions/runs/31616522487) |
| `REUSE — every file names its licence` | **yes**, with a scope note below | [31616891891](https://github.com/Shaugato/mainline/actions/runs/31616891891) |
| `every checker this lane invokes exists` | **UNPROVEN** | — |
| `actionlint` | **UNPROVEN** | — |
| `import-linter contracts · and no package outside them` | **UNPROVEN** | — |
| `the lockfile is authoritative · workspace membership` | **UNPROVEN** | — |
| `PL-2 — the red run is recorded` | **UNPROVEN** | — |

**The two `RED BY DESIGN` results are the most important in this section**, because the
failure they guard against has already happened in this repository once. `ci.yml`'s own
header states the mechanism: *"a `-m` name that no test carries fails silently and green"*,
and between the day the selector was written and 2026-08-10 it reached only the five
`g4alpha` cases while eight tests printing `PL-2 RED, as intended.` failed inside the
general regression lane, indistinguishable from a regression.

Partial collapse — `RED_SELECTOR` reduced to `"g4alpha"`, the exact pre-2026-08-10 state:

```
selected 5 test(s) -> 5 red · 0 green · 0 not measured
##[error]only 5 declared red(s) actually failed; the floor is 13
```

Total collapse — `RED_SELECTOR: "g4alpha_typo or pl2_redd"`, names no test carries:

```
pytest exited 5
##[error]'-m g4alpha_typo or pl2_redd' collected NO tests, so this job would have
reported 'every declared red is still red' over the empty set.
```

These are caught by **different code** — the floor counts `<failure>` elements in a JUnit
report that a zero-collection run never writes — so neither guard is redundant. In the
control run the same job was green with `13 failed, 9311 deselected in 18.00s`.
**`RED_FLOOR` genuinely refuses.**

`the sequence ban` was planted with a three-line migration containing
`CREATE SEQUENCE mainline.w10_plant_seq;` and returned five separate named findings on it,
including the planted one:

```
0999_w10_plant.sql:3: banned-token:create-sequence — 'CREATE SEQUENCE' — a sequence
makes a gap ambiguous; the ledger is gap-free by CAS so a gap MEANS tampering
```

**A scope note on `REUSE`, because the first plant against it was ill-chosen and did not
falsify anything.** An unlicensed file added under `docs/` left the job **green**, and
that is correct: `REUSE.toml` carries blanket annotations over `docs/**`, `qa/**`,
`evidence/**`, `packages/**`, `scripts/**`, `spec/**`, `skills/**`, `tests/**`,
`verticals/**`, `infra/**` and `.github/**`, and the spec's `precedence = "closest"` means
those annotations fill gaps without overriding the 2 602 headers on disk. So the job's real
promise is *"every tracked file is **covered**"*, not *"every file **names** its licence"*,
and **no new file inside an existing top-level tree can make it fail.** The falsification
that does work plants a file at the repository root, outside every blanket — run
31616891891, with `the sequence ban` green in the same run as its in-run control:

```
UNCOVERED — resolve a licence or annotate (1):
    W10-PLANT-UNLICENSED.md
REFUSED [RATCHET] metric=uncovered_by_top_level_directory.<root> baseline=0 measured=1 [HARD GATE: baseline is 0]
```

The metric name confirms the scope: coverage is ratcheted **per top-level directory**, and
`<root>` is the only bucket with an empty blanket. **The plant that failed to falsify is
reported here rather than dropped**, because a plant that lands in a covered directory and
is then presented as a caught violation is the same error the `aws-evidence` control exists
to catch.

### 6.3 Two green steps that cannot be observed refusing

Named because a reader of the Actions tab will otherwise credit them with more than they
assert. Neither is a lane that lies; each is a place where a green tick means less than its
name suggests.

**`supply-chain`'s `GREEN — the assertion, over the REAL resolved set`.** In both plants
of §6.1 this step was **skipped**, because the step above it —
`RED — four planted violations` — copies the real witnesses and refuses if the *copies* are
already dirty:

```
##[error]COPIES ARE NOT CLEAN: byte copies of the two witnesses are already refused, so
no refusal below is attributable to a plant
```

That refusal is correct — the harness declined to claim it had caught a plant while its
control was dirty, and it appended the real checker output so `boto3` and
`mainline-domain` are still named in the log. But the consequence is that the step the
§8.2 claim nominally rests on **has never been observed refusing and cannot be, on any
input that would make it refuse.** Its green means "the red half passed", not "the real
closure was checked today". Moving the red half after the green half, or giving the green
half `if: always()`, fixes it. Owner: W1.

**`boundary`'s three `RED — …` steps** (W8 §4.1): each is masked by a `pytest` step
earlier in the same job that asserts a strict superset and fails first. Each was proven
able to refuse only by disabling the step above it — runs 31605577907, 31607324400,
31607357953. **This is redundancy, not vacuity; every property is enforced.** But the same
sentence applies: a reader who sees `RED — …` green and concludes "that step watched
something refuse today" is wrong.

### 6.4 Promises measured as **unfalsifiable**, not merely untested

Stronger than "unproven": each has a run id showing the lane **green over a real
violation**.

1. **`release-proof` — "the image pin agrees with `compose.yaml`", for any tag not shaped
   `v<N>.<N>.<N>`.** Run 31605452346, **success**, with `compose.yaml` pinning
   `cockroachdb/cockroach:latest-v26.2` while the job printed `using
   cockroachdb/cockroach:v26.2.5` and called that agreement. Falsifiable only for
   same-shaped tags (31605448626, failure). W1's rewrite of `release-proof.yml` fixes it.
2. **`judge-pack` — the `envelope` cross-check.** Run 31605705752, success, printing
   `cross-check: NOT RUN … This is not a pass.` `mainline_mcp` is not installed by this
   lane, so the second implementation of the envelope **has never been consulted in CI**.
3. **`console` — "the pin that was requested is the pin that arrived".** Run 31605487354,
   success at `packageManager: pnpm@11.5.2` / `pnpm on PATH: 11.5.2`. The check compares a
   field with the pnpm installed *from that field*. No edit to `package.json` can make it
   red.
4. **`submission`'s `The machine record` step** carries `continue-on-error: true` **and**
   `|| true` on the same command and cannot fail the lane under any input. The repository
   bans both constructs. Two other `continue-on-error` steps in that file are load-bearing
   in a way a proven decision step makes safe; this one is not.

### 6.5 Everything else this section does not claim

* `supply-chain`'s `an SBOM for every distribution` and `pip-audit over the locked set`
  stayed green in every run above and **nothing was planted against either**. Unproven.
* `mutation-ratchet`'s three other measurement-did-not-happen conditions — a catalogue
  class with no operator, a drifted paraphrase cassette, a class that produced no trial —
  are **unproven**. Only "the injection point stopped injecting" was planted.
* `boundary`'s fleet matrix has **no shipped subject**: `spec/agents/fleet.yaml` does not
  exist, so `test_shipped_fleet_register_exists` skips on every run and the matrix is
  asserted against a fixture. Green there means "a reference register satisfies the
  matrix", not "the fleet we ship does".
* `boundary`'s `E3-SBOM-CURRENT-ABSENT` and E1's two live IAM tests skip on every run.
  Declared, visible in the log, and not a pass.
* W9 lists six further promises verified to still bite but not independently planted.

### 6.6 Checkers that prove themselves outside CI

```
$ .venv/Scripts/python.exe scripts/qa/check_reuse.py --self-test
7 of 7 scenarios behaved as declared: the checker passes a complete tree and refuses
each of the 6 planted violations.

$ python -I -S scripts/submission/audit_public_readiness.py --self-test | tail -1
SELF-TEST PASSED: 9 families, 9 fired, 0 missed; 35 disposition/strength assertions, 0 failed
```

and `tests/release/test_ruff_ratchet.py` records, in its own module docstring, the two runs
in which the ratchet was neutered and the exact assertions that went red.

Every plant branch from all three workers was deleted after its log was read. The public
repository holds `master` and nothing this section created.

---

## 7. What this wave did **not** achieve

Stated plainly, because the honest floor is worth more than a flattering total.

1. **`demo-health` needs a deployment.** It is not a workflow edit. `terraform apply` has
   not been run; the plan is committed and reviewed and the apply is the orchestrator's.
2. **`schema` and `custody-chain` owe real artefacts** — two `CREATE TABLE` migrations
   (§3.2) and seven crypto check implementations plus a canonicaliser reconciliation
   (§3.1). This wave made them say so more precisely. It did not make them green and must
   not.
3. **`cloud-verify` and `nightly-differential` need a live cluster** this wave did not
   provision. Their plumbing is repaired; their conclusions are next wave's measurement.
4. **`db` was never measured at HEAD** (§4.2). Its finding is carried forward, not
   re-observed.
5. **The `ci` lane's repair is not on `master`.** Everything in §2.2–§2.5 was measured on a
   branch carrying an endpoint fix to a file W2 owns. It must be re-created against W2's
   `ci.yml`.
6. **17 lint rules and 4 mypy errors are open** (§2.3, §2.4), and `qa/ruff-ratchet.json`
   was not rebaselined to hide any of them. A residual that survives the wave is named
   here, not baselined away.
7. **Five `ci` jobs and two `supply-chain` jobs have no falsification** (§6.2, §6.5).
8. **The `g4alpha` gates and the MI ratchet stay red by declaration** (§3.6, §3.3).

Nothing in this list is a ratchet to be raised or a check to be softened. Every one of them
is a thing that does not exist yet, a line that is written twice and should be written
once, or a runner that could not reach the internet.
