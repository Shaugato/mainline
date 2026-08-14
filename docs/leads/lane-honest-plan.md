<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
-->

# LANE-HONEST — making the cluster lane trustworthy end to end

**Lead:** the lane-honest lead. **Date:** 2026-08-14. **HEAD:** `eefae1c`, branch `master`,
working tree clean at the time every number below was taken.

This plan directs six workers. It does not do their work. Every number in it was measured by
this lead before decomposition, on this workstation or read out of a real GitHub Actions log,
and each carries the command or the run id that produced it.

---

## 0. THE RULE THAT OUTRANKS EVERY TASK, restated because this wave edits a recorded hash

A worker was once caught editing `demo_world.sql` to enrol a DERIVED credential id — making
the SEED match the CODE. **When a test and the code disagree, never move whichever side is
easier; ask which side is AUTHORITATIVE.** The ratified tiebreaker is that **the console and
the committed JSON schemas are authoritative for what the demo must carry, and the seed and
the tests are BOTH checked against them — either may lose.**

This wave contains one edit that *looks* exactly like the forbidden one: W2 replaces two
`sha256` constants in `tests/ci/test_demo_seed_is_frozen.py` so that a test stops failing.
Ruling **R2** below is the whole of the justification, and it is gated on a negative control
that runs **before** the edit. If that control does not come back clean, the answer is to
revert the seed, not to re-baseline the hash. Nothing else in this wave may move a recorded
value at all.

**Repeated in every worker brief, and repeated here so nobody has to go looking:**

> **NO SHORTCUTS.** Never lower `COLLECTED_FLOOR`, the skip ceiling, `RED_FLOOR`,
> `min_executed`, a known-red list or any ratchet to obtain a green. Never add
> `continue-on-error` or `|| true`. Never use `-k`, `--deselect`, `xfail` or a stubbed import
> to route around a failure. Never weaken an assertion or an error message. Never move an
> authoritative value to match a derived one. Never print a credential. Never
> `terraform apply`. If a fix is blocked, report the blockage in writing — a blocked task
> reported is worth more than a green obtained by editing the measurement.

---

## 1. BASELINE, measured before any decomposition

### 1.1 The full demo-api suite under a real cluster, on this workstation

```
.venv/Scripts/python.exe -m pytest verticals/mainline/apps/demo-api/tests \
  --crdb=reuse -q -p no:cacheprovider --junitxml=<report>
```

Read from the `<testsuite>` attributes of the JUnit XML, **never from a terminal scroll**:

| | |
|---|---|
| `tests` | **528** |
| `failures` | **1** |
| `errors` | **0** |
| `skipped` | **1** |
| executed (`tests` − `skipped`) | **527** |
| `time` | 170.528 s |

The one failure: `test_reads.py::test_the_disposition_carries_the_lattice_and_the_projected_requirements`.
The one skip: `test_gate_run.py::test_payload_validates_against_the_json_schema` —
*"jsonschema is not a workspace dependency"*.

This is the **BEFORE** number. Every worker reports the same command's numbers **AFTER**
their change. A fix that breaks a neighbour is worse than the defect.

### 1.2 The same suite in CI, run `31735341117` (cluster-tests, HEAD `eefae1c`)

```
cluster lane: 528 collected, 518 executed, 10 skipped, 1 failed, 0 errored
1 failed, 517 passed, 10 skipped in 154.21s (0:02:34)
```

**The delta between 1.1 and 1.2 is the whole of scope (a):** locally the deployed package is
built (`out/lambda/mainline-demo-api-arm64.zip`, 7,646,264 B, 2026-08-13 15:54), so 9
package-dependent assertions RUN. In CI they skip.

### 1.3 The whole-repository collection, on the pinned interpreter, at `eefae1c`

```
.venv/Scripts/python.exe -m pytest --crdb=none -m "g4alpha or pl2_red"       --collect-only -q
  ->    15/10150 tests collected (10135 deselected) in 17.18s
.venv/Scripts/python.exe -m pytest --crdb=none -m "not (g4alpha or pl2_red)" --collect-only -q
  -> 10135/10150 tests collected (   15 deselected) in 16.71s
```

The collection is **10,150**. `ci.yml:124-126` records **9,839**. `RED_FLOOR` = **15** and it
did not move — which is the point of a floor. See ruling **R8**.

### 1.4 The frozen-seed guard, at clean HEAD, with no plant anywhere

```
.venv/Scripts/python.exe -m pytest tests/ci/test_demo_seed_is_frozen.py --crdb=none -q
  -> 2 failed, 1 passed in 0.52s
```

| file | hashes | `test_demo_seed_is_frozen.py` records |
|---|---|---|
| `demo_world.sql` (55,980 B) | `e2aa9706ffca80f269edaa77e1dc8224b26b52ef6c4b666c74076bcc173787bf` | `50535d1db0babf78a3cb4f50ec3d682b4034a5068fefcbb148c61950cfc07aee` |
| `demo_permit.sql` (28,889 B) | `df3470cb26659b4bb8a4b565447b279a1417ef773988843951aa9817259c2d35` | `198d44ef6e843fa6ddaec3620ad7c668f800a1ab5b7ef37cf73d63dcdf66dcc6` |

`test_the_seed_derives_the_demo_credentials_from_their_names` — the credential control —
**PASSES**. That is the third test and it is the one that matters. See **R2**.

---

## 2. RULINGS

Where the brief poses a question, this section rules on it in writing and names the authority
it ruled from. **No worker may act before reading the ruling that governs their file.**

### R1 — The brief's claim that `cluster-lane-bites` "has never completed one cell of its 2×2" is FALSE. All four cells passed.

**Authority:** the lane's own step assertions in run **31735341050** (push, `eefae1c`,
2026-08-13T19:20:30Z, 3m38s), read from the run log rather than from a summary.

| | plant ABSENT | plant PRESENT |
|---|---|---|
| `--crdb=none` | `7 passed, 71 skipped in 0.32s` → **7 executed, floor 7. GREEN ✓** | `7 passed, 71 skipped in 0.30s` → **7 executed, and `7 == 7`. GREEN ✓** |
| `--crdb=reuse` | `77 passed, 1 skipped in 109.21s` → **77 executed, floor 77. GREEN ✓** | `3 failed, 74 passed, 1 skipped in 76.12s` → **RED ✓** |

The lane printed, in its own words:

> `cell 3/4: 7 executed with the plant present; cell 2 ran 7`
> `the hermetic lane cannot tell the planted tree from the clean one`

> `cell 4/4: 3 failure(s)/error(s) under a cluster: ['test_the_admission_is_a_green_this_database_could_have_refused', 'test_the_deployed_seed_and_the_proof_seed_are_two_different_worlds', 'test_the_deployed_seed_does_not_enrol_the_value_gate_run_used_to_derive']`
> `the cluster lane is RED, and test_the_deployed_seed_does_not_enrol_the_value_gate_run_used_to_derive is what caught it`

**The load-bearing cell — plant-present/hermetic passing the SAME count as plant-absent —
PASSED.** The plant is invisible to the hermetic lane and visible to the cluster lane, which
is exactly the claim the lane exists to make. The fifth assertion (the inventory could not
suppress the failure, neither with pytest's real status nor with a dropped one) passed. The
sixth-A assertion (the frozen-seed guard is RED against the plant) passed. The revert produced
a byte-for-byte clean tree — `git diff --exit-code` clean and `git status --porcelain` empty.

**Consequence for the wave:** the 2×2 does not need building. It needs *preserving* and
*publishing*. W2 must not restructure it, must not change `HERMETIC_FLOOR` or `CLUSTER_FLOOR`,
and must not touch the plant. **A worker who "fixes" a passing 2×2 has destroyed the most
expensive control in this repository.**

### R2 — The bites lane's single failure is a STALE FREEZE BASELINE. The hash is the derived side, and the re-baseline is authorised by the test itself — after a negative control.

**Authority:** `tests/ci/test_demo_seed_is_frozen.py`'s own printed contract, and §1.4's
measurement at a clean tree.

The step that failed is the LAST one: *"The frozen-seed guard is GREEN again"*, which runs
**after** the revert, on a tree the job itself proved byte-clean. It reported
`2 failed, 1 passed in 0.17s` against the same two hashes recorded in §1.4. Reproduced
locally at clean HEAD: identical.

**Which side moved?** The seed files did. Both changed in `eefae1c`
(`git log --oneline -3 -- <both seeds>` → `eefae1c`, `8e6a195`, `b0fe884`), and `FROZEN` at
`tests/ci/test_demo_seed_is_frozen.py:99-102` is a `sha256` **of** those files. A value
computed from a file cannot be authoritative over that file. The test says so in the message
it prints:

> *"THIS IS A QUESTION, NOT A VERDICT. These files are meant to grow, and a re-baseline is
> allowed — replace the hash in `tests/ci/test_demo_seed_is_frozen.py` IN THE SAME COMMIT as
> the seed change, and make that commit message say what changed in the seed and why."*

**THE NEGATIVE CONTROL IS MANDATORY AND RUNS BEFORE THE EDIT.** The same file also says:

> *"WHAT IS NOT ALLOWED is editing these bytes to make a failing test pass … If the change you
> are re-baselining is of that shape, revert it instead."*

So W2 must, and must record in the file, all four of:

1. `git diff 8e6a195..eefae1c -- verticals/mainline/db/seeds/demo/demo_world.sql verticals/mainline/db/seeds/demo/demo_permit.sql` shows **zero** changed lines matching
   `signing_credential`, `credential_id`, or `digest('mainline-demo/credential/`.
2. `test_the_seed_derives_the_demo_credentials_from_their_names` **PASSES at HEAD** — measured,
   §1.4, it does.
3. `verticals/mainline/apps/demo-api/tests/test_credentials.py` passes in full under
   `--crdb=reuse`.
4. The seed still enrols **exactly one** credential as
   `digest('mainline-demo/credential/demo.signer','sha256')`, counted from the file.

If **any** of those four fails, **STOP, do not edit the hash, and report**. That is the
forbidden edit wearing this task's clothes.

### R3 — W2 re-baselines now and does not wait for the defeater-option seed work.

**Authority:** this lead, from the repository's own doctrine that a control nobody can read is
a control that has stopped working.

Another lead owns blocker #1 — seeding `mainline.defeater_option` — and that will change
`demo_world.sql` again, breaking the freeze a second time. The temptation is to wait. **Do
not.** The guard is red at HEAD *right now*, on a clean tree, for a reason no reader can
distinguish from "the guard is broken", and it is the only thing standing between
`cluster-lane-bites` and a full green. A guard that is red for an unexplained reason is a
guard people learn to ignore; that is the same failure mode as a ceiling nobody lowers, viewed
from the other side.

W2 therefore re-baselines **and** adds an explicit `HOW TO RE-BASELINE` procedure block to the
module docstring, so the next lead does it in the same commit rather than leaving it. W2 also
records in that block that the seed lead will need to do exactly this again, and why that is
correct rather than churn.

### R4 — The 10 skips decompose into 9 package-dependent and 1 unrelated. The ceiling of 1 is exactly right and does not move. The brief names two modules; the log names three.

**Authority:** run `31735341117`'s own `short test summary info`, quoted verbatim.

| source | skips | cause |
|---|---|---|
| `test_envelope.py:1016` | 1 | *"no deployment package has been built in this tree"* |
| `test_response_contract.py:893` | 3 | *"the deployed package is not built"* |
| `test_response_contract.py:1144` | 1 | *"the deployed package is not built"* |
| `test_response_contract.py:1210` | 1 | *"the deployed package is not built"* |
| `test_static_site.py:930` | 3 | *"the deployed package … is not built"* |
| `test_gate_run.py:945` | 1 | *"jsonschema is not a workspace dependency"* — **nothing to do with the database** |
| | **10** | |

Building the package takes **10 → 1**, landing exactly ON the ceiling. **`test_envelope.py` is
the third module and the brief does not name it.** A worker who fixes only
`test_response_contract.py` and `test_static_site.py` lands at 2 against a ceiling of 1 and
will be tempted to raise the ceiling. **The ceiling does not move.** Corroborated by §1.1: with
the package present locally, the suite skips exactly one test, and it is the jsonschema one.

### R5 — The freshly-built artefact is authoritative over any byte count derived from it. The CEILING is authoritative over the artefact.

**Authority:** `docs/decisions/response-ceiling-authoritative-tree.md`, cited at
`test_response_contract.py:846`; and this wave's already-true list.

Building in-lane will execute nine assertions that have **never run in CI**. They may fail.
That is not a reason to stop — it is the reason to do it. If they fail because a fresh
`vite build` produces different asset sizes from constants recorded in the tests, then:

* the recorded byte count is the **derived** side (it is a measurement *of* the artefact) and
  may be re-recorded, **naming the build that produced it**;
* `136 * 1024 = 139,264` — the response ceiling — is the **authoritative** side and **does not
  move**, per the already-true list;
* if a fresh build's largest served object **exceeds** the ceiling, that is a real cost
  regression, the lane is right to go red, and the answer is a smaller artefact. **Never a
  bigger ceiling.**

If the nine fail for any *other* reason, W1 reports it and does not paper over it.

### R6 — The lane's diagnosis is drowned at the END, not in the middle, and the fix is ordering and folding — never removal.

**Authority:** measured by this lead over the full 1,023-line log of run `31735341117`.

| region | lines | content |
|---|---|---|
| the assertion that failed | 830 | one line |
| `FAILURES` block + verdict | 760–919 | the actual diagnosis |
| `docker logs … tail -60` | 943–1003 | **60 lines of `4@util/log/event_log.go:90`** |
| GitHub echoing `run:` bodies | 186 lines total | mostly this repo's (excellent, long) step comments |

A reader who opens a failed run lands at the **bottom** and sees CockroachDB's session log. The
one failing assertion is ~180 lines above it. That is why the orchestrator had to grep.

**The container log is NOT deleted and NOT quieted.** `cluster-tests.yml` and `db.yml` both
argue for it in writing, and when the suite fails for a reason that is about the database it is
the only place that shows up. Suppressing CockroachDB's stderr with a log filter would silence
exactly the case it exists for. The fix is four additive changes, none of which removes an
assertion:

1. wrap the container log in `::group::` / `::endgroup::` so the UI collapses it;
2. make `--summary` carry the failing node ids **and their assertion text** — `$GITHUB_STEP_SUMMARY`
   renders at the **top** of the run page, which is where a reader actually lands;
3. upload the JUnit XML and the raw pytest stdout as a job artifact, so `gh run download`
   yields a clean file instead of 1,023 lines of interleaved log;
4. move long rationale out of `run:` bodies into `#` comments **above** the step — GitHub
   echoes the body and does not echo the comment. The prose is kept in full; it just stops
   being printed twice per run.

### R7 — `qa/cluster-known-red.json`: 63 of 64 inventoried ids now PASS. A fix that has ALREADY LANDED discharges the "only the fixing commit may delete" rule, and the deletion must cite that commit by hash. The three `unstable` entries are NOT deleted on three passes.

**Authority:** run `31735341117` (`528 collected, 518 executed, 10 skipped, 1 failed, 0 errored`),
this lead's §1.1 local reading (`1 failed`), and the file's own `policy` block.

The inventory's own rule — *"Entries leave it only in the commit that FIXES them"* — exists to
stop a ceiling falling for free, i.e. to stop somebody deleting an entry that nobody fixed. It
does **not** mean an inventory must stay stale forever because the fixing commit forgot to prune
it. Here the fix is committed at HEAD: `eefae1c` landed the `demo_world.sql` build-out, the
`payloads` fixture builds, and the `commit_v2` KeyError recorded as the group's `cause` fires
for nothing. **I rule that a landed, identifiable fix discharges the rule, and the deletion must
cite `eefae1c` by hash in the entry that records it.** A ceiling that cannot fall even when the
work is provably done is not a ratchet, it is a monument.

Concretely:

* `reads-payloads-fixture-refuses-to-invent-a-subject` — **split, then shrink.** The one still
  failing id, `test_the_disposition_carries_the_lattice_and_the_projected_requirements`, moves
  to a NEW group whose `cause` is the measured one (`assert set() == {'MECHANISM_PRESENT_AND_VERIFIED','SCOPE_EXCLUDES_HAZARD'}`;
  `mainline.defeater_option` holds zero rows) and whose `owner` is the demo-seed lead. The other
  62 ids are **deleted**, citing `eefae1c`. The old group's `cause` and `status_at_handoff` are
  preserved in a `superseded` block, per this file's own convention for superseded numbers.
* `reads-undeclared-query-parameter` — **deleted**, same measurement, same reasoning. It has
  passed in every reading since 2026-08-14T04:11Z.
* `floor.min_executed` **rises 440 → 518** — the CI-measured executed count. It rises to the
  **CI** number, not the local 527, so that a lane which legitimately skips differently is not
  tripped for the wrong reason. A note records that it rises to 527 in the commit that proves
  527, which is W1's. **`max_skipped` stays 1.**
* the three `unstable` entries are **NOT deleted.** An `unstable` entry is a claim about a
  *distribution*, and three passes do not refute it. The schema itself requires
  `runs_observed`/`runs_failed`, so the honest action is to **add observations**, not to remove
  the entry. W4 measures; W3 records the measured counts.
* the `unstable` list aims at **3** node ids. `test_transitions.py` holds **30** tests, of which
  **21** take the shared `w4_conn` connection. **Justify 3 or widen it** — W4 measures the family
  and either widens the list to the measured set or writes down, with the counts, why the 3 are
  the whole of it. "The brief said 13" is not a measurement; W4 measures the number.

### R8 — `ci.yml`'s `13 / 9240 / 9253` is a deliberately preserved superseded reading and must NOT be deleted. The LIVE numbers are stale, by 311, not 430.

**Authority:** `ci.yml:145-153`'s own words, and §1.3's re-measurement.

`ci.yml:152` and `ci.yml:653` carry `13 / 9240 / 9253` **inside a block headed** *"THE TWO
SUPERSEDED READINGS ARE KEPT, because the difference between them is the defect each pair of
jobs was built to end, and a number replaced in place teaches nobody anything."* Deleting them
is the edit this repository forbids. The brief's framing of them as stale is **wrong** and I
rule it so.

The **live** figures are `ci.yml:124-126` and `:660` — `15 / 9824 / 9839`. §1.3 measures
`15 / 10135 / 10150`. So the collection moved **9,839 → 10,150 (+311)** and `RED_FLOOR` = 15
**did not move**, which is precisely what the floor's own comment predicted. W6 **APPENDS**
§1.3 as a third dated reading beside the other two. W6 does not overwrite either block and does
not touch `RED_FLOOR`.

### R9 — `docs/CI-STATE.md` §6's headline sentence is now FALSE, and correcting it is the single most valuable edit on that page.

**Authority:** run `31735341117` executed 518 cluster-backed demo-api tests.

§6 is titled *"The cluster line: no lane in this repository has ever executed a cluster-backed
demo-api test"*. That is no longer true. §6.4 already asks *"What would end it, and the number
to check when it lands"* — this is that landing. W6 rewrites §6 to record it **with the measured
pass/skip split** and does **not** delete §6.1–6.3's measurements: they become the "before", and
a page that deletes its own superseded numbers stops being evidence.

### R10 — Not in this wave, and named so nobody silently absorbs them.

These are real and belong to other leads. No worker in this wave may edit them, and no worker
may route around them:

* **`mainline.defeater_option` holds zero rows.** The seed owes those rows. Owner: the demo-seed
  lead. This wave records it as a one-entry known-red group (R7) and does nothing else to it.
  **The assertion at `test_reads.py:414` is NOT weakened.**
* **`docs/deploy/COST-BOUND.md` I4/I6 and `docs/leads/cost-bound-plan.md:25,28`** are false about
  this repository. Owner: the cost lead. W1's fresh build will produce the correct numbers as a
  side effect and must **report** them, not edit those documents.
* **`docs/deploy/LATENCY.md`** measures a beat against a `.map` URL the origin now 404s. Owner:
  the deploy lead.
* **Nothing exercises the 40001 retry loop.** `_seed_permit` at `test_transitions.py:224`
  commits ~29 statements with no retry; `test_gate_run.py:143` names its scratch database
  `w_w4_api_transitions` with a fixed string. W4 will trip over both while measuring stability
  and must **report** them with evidence rather than fix them.

---

## 3. THE SIX WORKERS — disjoint, literally enumerated paths

No two workers write the same path. Where one worker needs another's output, the interface is
named here so neither has to guess.

| # | worker | owns, literally | depends on |
|---|---|---|---|
| W1 | the lane builds what it tests | `.github/workflows/cluster-tests.yml`, `.github/actions/build-demo-package/action.yml`, `docs/ci/cluster-lane-package.md` | W5 |
| W2 | the freeze tells the truth about the tree it reads | `tests/ci/test_demo_seed_is_frozen.py`, `.github/workflows/cluster-lane-bites.yml`, `docs/ci/cluster-lane-falsifiability.md` | — |
| W3 | the inventory falls to the one entry still true | `qa/cluster-known-red.json`, `qa/README.md` | W4 |
| W4 | the unstable family, measured rather than inherited | `evidence/qa/transitions-stability.json`, `docs/ci/transitions-contamination.md` | — |
| W5 | the diagnosis a reader can find | `scripts/ci/cluster_lane_report.py`, `scripts/ci/lane_log_digest.py`, `docs/ci/cluster-lane-diagnosis.md` | — |
| W6 | the board, swept and re-measured | `docs/CI-STATE.md`, `.github/workflows/ci.yml` | W1, W3 |

### The one cross-worker interface, fixed here so W1 and W5 do not block each other

`scripts/ci/lane_log_digest.py` (W5 writes it, W1 calls it). CLI, fixed by this plan:

```
python scripts/ci/lane_log_digest.py \
  --junit <path to junit xml> \
  --stdout <path to captured pytest stdout> \
  [--summary <path, appended as Markdown>] \
  [--max-failures N]     # default 20
```

Exit status **0 always** — it is diagnosis and decides nothing; the verdict stays with
`cluster_lane_report.py`. It prints, in this order: the one-line totals; then for each failing
node id, the id and the assertion text extracted from the JUnit `<failure>` body, truncated with
an explicit marker rather than silently; then the skip census grouped by message. When
`--summary` is given it appends the same content as Markdown.

---

## 4. WHAT "DONE" MEANS FOR THE WAVE

1. `cluster-tests.yml`'s own JUnit reports **≤ 1 skipped** with the ceiling still at **1**, and
   the nine package-dependent assertions have an outcome recorded — pass or fail, named.
2. `cluster-lane-bites` is **green end to end**, with all four cells and all six assertions
   intact and unweakened, and the four measured cells written into
   `docs/ci/cluster-lane-falsifiability.md`.
3. `qa/cluster-known-red.json` names only defects that are actually failing, its `floor` has
   risen, and its `unstable` list carries measured `runs_observed`/`runs_failed`.
4. A reader who opens a failed cluster run sees the failing assertion **without scrolling or
   grepping**.
5. `docs/CI-STATE.md` §6 is true, and every green whose refusal capability is unproven is named
   with the measured pass/skip split.
6. **Full-suite `--crdb=reuse` numbers reported BEFORE and AFTER by every worker**, taken from
   `--junitxml`, checking the `tests=` attribute rather than assuming a fast run did not run.
   The BEFORE is §1.1: **528 / 527 executed / 1 skipped / 1 failed / 0 errors**.
