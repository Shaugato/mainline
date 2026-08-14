<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: CC-BY-4.0
-->

# STATE OF THE BUILD

**Re-certified 2026-08-14 by the SIXTH re-verification agent**, against local `HEAD`
`eefae1c` **plus 37 modified and 13 untracked paths that have never been committed**.
`origin/master` is at `eefae1c`; every CI run that exists was taken at that commit, which
is the tree *before* this wave. Deadline 2026-08-18.

Five prior verifications returned NO-GO and each was right. This one was instructed to
assume the wave failed until it proved otherwise. Every number below came from a command
this agent ran on this machine today; suite totals are read from `--junitxml` root
elements and from nowhere else.

The paragraph a reader in a hurry needs:

> **This wave did the honest thing and it made the measured build worse.** The defeater
> vocabulary — the thing a judge chooses before signing — was being pinned by a hard-coded
> constant, `sha256(b"defeater-vocab")`. This wave found that, proved it against the
> deployed cloud fixture, and replaced it with a resolver that **reads the vocabulary from
> the database and refuses when there is none**. That is the correct repair and it is the
> same class of defect as the credential incident this repository's headline rule exists
> to prevent. **But the rows were never seeded.** `mainline.defeater_option` still holds
> **zero rows** in the demo world; the only `INSERT` into that table anywhere in the tree
> is inside `test_defeaters.py`. So a silent wrong value became **43 loud failures**, and
> the demo-api suite went from **527 passed / 1 failed / 0 errors** to
> **527 passed / 30 failed / 13 errors**. A judge still cannot sign — the wave's own
> evidence file says so, in the word `INCOMPLETE`. **This is a NO-GO for the sixth time,
> on one cause: the seed owes three rows, and the wave shipped the detector instead of
> the data.**

---

## 0 · The five GO conditions, scored

| condition | verdict | evidence |
|---|---|---|
| No shortcut taken | **PASS** | §1 — and this is a genuine pass, checked four ways |
| A judge can complete the signature path | **FAIL** | §2 — blocked at beat 4; beat 5 refuses again |
| Suite green in any order against a real cluster | **FAIL** | §3 — 30 failed / 13 errors sequential, 31 / 13 randomised |
| Cluster lane green, skips at ceiling, 2×2 completed | **PARTIAL / UNRUN** | §4 — the 2×2 **did** complete at `eefae1c`; every fix this wave wrote is **uncommitted and has never run in CI** |
| Plan reproducible from a clean clone | **PASS** | §6 |

Two of five. Both failures reduce to the same three missing rows.

---

## 1 · The shortcut check — PASSED

This is the check that outranks the rest, and it passes. Nothing authoritative was moved
to match anything derived.

### 1.1 The seed did not move

```
$ git diff HEAD -- verticals/mainline/db/seeds/demo/ | wc -l
0
```

`demo_world.sql` and `demo_permit.sql` are **byte-identical to `HEAD`**. The failing
assertion in `test_reads.py` is likewise untouched (`git status --porcelain` returns
nothing for it) and still demands the three defeater codes it always demanded. **The
easier side was available all wave and was not taken.**

### 1.2 The credential negative control is clean

Re-run by hand rather than trusted:

```
sha256(b'credsigner') = 487adc50409e8811b1f12055ee183ce9d8548f11262807d01776fb67cd09c765
occurrences in demo_world.sql: 0

demo_world.sql:124:    digest('mainline-demo/credential/demo.signer', 'sha256'),
demo_world.sql:132:    digest('mainline-demo/credential/demo.countersigner', 'sha256'),
```

Credentials are still enrolled as the digest of their **name**. The application-derived
constant appears **zero** times. The 2026-08-13 incident has not recurred.

### 1.3 The frozen-seed hash WAS re-baselined — in the correct direction

`tests/ci/test_demo_seed_is_frozen.py` moved both constants:

```
- "demo_world.sql":  50535d1db0ba…cfc07aee
+ "demo_world.sql":  e2aa9706ffca…173787bf
- "demo_permit.sql": 198d44ef6e84…df66dcc6
+ "demo_permit.sql": df3470cb2665…259c2d35
```

This is **not** the forbidden edit, and the distinction is the whole point of the rule. A
hash is *computed from* the file; the file is authoritative over the hash. The seeds
changed in `eefae1c` and that commit did not re-measure the freeze, which is why the bites
lane was red at a byte-for-byte clean tree. Moving the hash to the file is the derived side
following the authoritative one. The four-part negative control was re-run here (§1.2) and
is clean. Verified green now: `3 passed in 0.67s`.

### 1.4 What DID move, stated plainly

| control | before | after | direction |
|---|---|---|---|
| `floor.min_executed` | 440 | **518** | **raised** — tighter |
| `floor.max_skipped` | 1 | 1 | unchanged |
| known-red `groups` | 2 groups / 64 node ids | **1 group / 1 node id** | **63 exemptions removed** — tighter |
| known-red `unstable` | 3 entries | **4 entries** | **one exemption ADDED** — looser |

Three of four movements tighten the instrument. **One does not**, and it is named here
rather than buried: `test_the_request_after_a_gate_run_is_not_a_503` was added to
`unstable`, the one category the ceiling does not police.

Two procedural notes a reader is owed:

* The 63 deletions are justified by a ruling called **R7**, written by this wave in
  `docs/leads/lane-honest-plan.md` — **an untracked file**. The fifth verification
  explicitly *refused* this deletion. The direction is nonetheless stricter (a deleted
  known-red entry must now pass), so this is recorded as a **procedural irregularity, not
  a shortcut**: the wave wrote its own permission slip, but it wrote it to make the lane
  harder to satisfy.
* `qa/cluster-known-red.json` itself states that **all four `unstable` node ids fail
  deterministically, 17 runs of 17, on this uncommitted tree**, and excludes those runs
  from the counts. That is candid, and it is also an exemption currently shielding four
  tests that are not flaky but broken. Confirmed by measurement: all four failed in both
  of my sequential runs.

---

## 2 · Can a judge finish the story? — **NO**

This is the beat the whole product exists to reach, and it does not arrive.

### 2.1 The wave's own evidence says so

`evidence/demo/judge-path-walk.json`, generated by this wave:

```json
"verdict": "INCOMPLETE",
"blocked_at": { "beat": 2,
  "reason": "the check offered no defeater vocabulary, so no judge could choose" },
"offered_vocabulary": [],
"signed": null
```

**Credit where it is due: the wave did not dress this up.** It drove the real handler, it
recorded the failure, and it published the failure as its own result.

### 2.2 Independently confirmed against the database

| database | `mainline.defeater_option` rows |
|---|---|
| `w3_demo_api_3b0aafc625f2` — built from `demo_world.sql` | **0** |
| `w2_defeaters_3b0aafc625f2` — built by `test_defeaters.py`'s own `INSERT` | 3 |

The vocabulary exists **only inside a test fixture's scratch database**. Repo-wide, the
sole `INSERT INTO mainline.defeater_option` is `test_defeaters.py:112`.

### 2.3 The five beats, as measured

| beat | what happened | verdict |
|---|---|---|
| 1 · refusal | `409`, `23514 gate_closed_when_issued` (**reported**, not parsed) | correct |
| 2 · materialise / offer | `200`, `defeater_options: 0`, `codes: []` | **blocked** |
| 3 · reject a non-member code | `422` — but refused for the *wrong reason*: the vocabulary was absent, so `require()` was never reached. **This control controlled nothing** | not proven |
| 4 · **sign** | `422 demo_history_not_seeded`. **No row written** | **FAILS** |
| 5 · admission | `409`, `23514` again — byte-identical to beat 1 | **arc never closes** |

The walk's own note on beat 5 is the honest summary: *a gate that always refuses is broken,
not safe.*

### 2.4 A document that is false about this repository

The refusal a judge would actually see says:

> *"Seed the vocabulary for this check — the demo history does so in
> `verticals/mainline/db/seeds/demo/demo_world.sql`"*

**`demo_world.sql` contains the string `defeater` zero times.** This sentence is in
`defeaters.py`'s exception text and in the `422` body, so it is a false claim shipped to
the one person it is addressed to. It must be corrected in the same commit that seeds the
rows.

---

## 3 · The suite — REGRESSED

All figures from `<testsuite>` attributes, never from a terminal scroll.

| run | collected | passed | failed | errors | skipped | wall |
|---|---|---|---|---|---|---|
| **baseline** (`eefae1c`, prior wave) | 528 | 527 | 1 | 0 | 0 | — |
| **this tree, sequential** | **570** | **527** | **30** | **13** | 0 | 198.1 s |
| **this tree, sequential (clean re-run)** | **570** | **527** | **30** | **13** | 0 | 181.5 s |
| **this tree, `--random-order`** | **570** | **526** | **31** | **13** | 0 | 177.6 s |

Two independent sequential runs agree **exactly**, so this is deterministic, not flake and
not contention. The wave added 42 tests (528 → 570), which is real work; it also turned
1 red into 43.

**Randomised order is worse by one** — 31 failures against 30. There is an order dependency
on top of the seed defect. The suite is **not green in any order**.

### 3.1 One cause, not many

Grouping every failure and error by message:

| cause | count |
|---|---|
| `DefeaterVocabularyAbsent` (directly, or a setup error caused by it) | **24+** |
| `assert 409 == 200` / `assert 422 == 200` — downstream of the same refusal | 4 |
| remainder in `test_transitions.py` / `test_row_factory_contract.py` | the rest |

`scripts/ci/cluster_lane_report.py` at this tree:

```
inventory: 1 known, 1 still failing, 0 now passing, 4 declared unstable, 38 NEW
::error title=38 NEW cluster failure(s)::…
```

**Seed the three rows and most of this table disappears.** That is the single highest-value
task remaining, exactly as the previous verification said — and it is still not done.

---

## 4 · The cluster lane — the fixes are real and **have never run**

### 4.1 The brief's premise was wrong: the 2×2 DID complete

Read from the real log of run `31735341050` (`cluster-lane-bites`, `eefae1c`), not from a
summary:

| cell | plant | lane | measured |
|---|---|---|---|
| 1 | absent | `--crdb=reuse` | `77 executed under a cluster (floor 77)` |
| 2 | absent | `--crdb=none` | `7 executed with no cluster (floor 7)` |
| 3 | **present** | `--crdb=none` | `7 passed, 71 skipped` — **7, the same count as cell 2** |
| 4 | **present** | `--crdb=reuse` | `3 failed, 74 passed` |

**All four cells completed.** Cell 3 passes the same count as cell 2, which is precisely
the property required: the hermetic lane **cannot** tell the planted tree from the clean
one, so the cluster lane is not redundant for this plant. Cell 4 names what bit:

```
['test_the_admission_is_a_green_this_database_could_have_refused',
 'test_the_deployed_seed_and_the_proof_seed_are_two_different_worlds',
 'test_the_deployed_seed_does_not_enrol_the_value_gate_run_used_to_derive']
```

The plant is caught by the **credential negative controls themselves**. This is a good
falsification and it should be recorded as achieved.

The job still failed — at step 19, the frozen-seed guard on the reverted tree, with the
stale-baseline defect described in §1.3. That is now fixed locally (`3 passed`).

### 4.2 What has not happened

**Every workflow change in this wave is uncommitted.** `gh run list` returns runs at
`eefae1c` only. Therefore:

| blocker | status |
|---|---|
| Build the package in the lane so the 10 skips fall to the ceiling of 1 | `.github/actions/build-demo-package/action.yml` is **written and unrun**. It is a careful action — it pins pnpm, verifies the pin arrived, and refuses an empty `web/`. CI has never executed it. |
| Skips at ceiling | **UNPROVEN in CI.** Last CI reading: **10 skips, ceiling 1.** Locally I measured **0 skips**, but only because `out/lambda/mainline-demo-api-arm64.zip` happens to exist on this workstation — which is the exact confound the action exists to remove. |
| 2×2 completed | **Achieved at `eefae1c`** (§4.1); the diagnosis and error-message improvements are unrun. |
| Known-red true against its tree | The file is **honest** — it names the defeater group `disposition-defeater-vocabulary-is-not-seeded` and reports `1 known, 1 still failing`. But 38 failures at this tree are **NEW** and outside it. |

---

## 5 · The 40001 retry loop — **REAL, and Cloud was NOT reached**

This is the best work in the wave and it deserves to be recorded as such.

* **The brief's premise was falsified, correctly.** `40001` is *not* Cloud-only. Six of six
  deliberate two-connection races against the **local single node** produced exactly one
  `40001` and one commit: `[control] unguarded census over 6 races: {'40001': 6, '00000': 6}`.
* **The unguarded shape was proved harmful**, not asserted to be: the loser's entire
  history vanished.
* **The adapter is real and spied**, not assumed: `[control] guarded: 12 commits, 6 retried 40001(s)`.
* `_seed_permit` no longer commits; `trappoint_testkit.txn.run_txn` owns the transaction and
  opens a **fresh connection per attempt**. A refusal (`23514`) is attempted **exactly
  once** and never retried — otherwise the refusal ledger stops counting anything.
* Every non-retried connection site carries a written reason at the site.
* I ran the concurrency tests: **9 passed in 188.01 s**.

**Cloud was not reached, and the wave says so in those words.** `docs/deploy/CLOUD-40001.md`:
*"This wave did NOT run the suite against CockroachDB Cloud. Not once."* The DSN is a
GitHub repository secret. The ruling forbids inferring a Cloud result, and forbids any
deliverable claiming that the local greens cover the Cloud case. **No such claim is made
here.** What Cloud adds — rate, clock-uncertainty restarts, `RETRY_WRITE_TOO_OLD` —
remains **unproven**, and the single-node greens in §5 are evidence about a single node
and about nothing else.

---

## 6 · The plan — **REPRODUCIBLE**

`evidence/deploy/lead/plan-repro-fresh-clone.json`, from two independently taken fresh
clones of the public repository:

| clone | shape | exit | count | committed artefact | agree |
|---|---|---|---|---|---|
| `D:/_fc/mainline` (autocrlf=true) | furl | 0 | 24 to add, 0 change, 0 destroy | 24 | ✔ |
| `D:/_fc/mainline` | cloudfront | 0 | 35 to add | 35 | ✔ |
| `D:/_fc/mainline-lf` (autocrlf=false) | furl | 0 | 24 to add | 24 | ✔ |
| `D:/_fc/mainline-lf` | cloudfront | 0 | 35 to add | 35 | ✔ |

* **Nothing was applied. Zero mutating AWS calls.** Seven refusals (`apply`, `destroy`,
  `import`, `taint`, `force-unlock`, `state`, `plan -destroy`), seven exits of 2.
* Residue after every run: `git status --short` **0 rows**, override removed, `.terraform`
  state removed.
* Preconditions seen every run: `reserved_concurrent_executions = -1`, twelve-zero mask
  occurrences **0**.
* Byte comparison: sizes match exactly (44,742 / 336,459 / 59,308 / 366,494). The **only**
  non-chatter difference is `source_code_hash`, because the clone did not build the zip.

**Two real gaps were found and written down rather than smoothed over:** `out/` and
`console/dist/` are gitignored, and `filebase64sha256` is evaluated at *plan* time — so a
fresh clone hits this before it hits the backend refusal. `plan_repro.sh` now exits **10**
naming `build_lambda.sh`. That is a genuine improvement to reproducibility.

---

## 7 · Gate proof — **PROVEN**, caveat-free

Re-run by this agent, not quoted:

```
chain         271/271 applied, 0 failed, 105.899s
reached 0115  True
unproduced    (none) — every relation this tree references has a producer
PROJECTION    10/10 held — open_blocking 0->1 — gate_epoch 0->1
REFUSAL       REFUSED [23514] gate_closed_when_issued (reported)
DRIFT         REFUSED [P0001] mainline.fn_permit_merge_gate (parsed)
ADMISSION     ADMITTED [00000]
caveats       (none) — nothing in this run is unproven-but-tolerated
VERDICT       PROVEN
```

Note the distinction that matters: this proof **admits** in its own synthetic world. The
demo world does not, because of §2. The gate mechanism is sound; the demo's data is not
complete.

---

## 8 · Documents vs the tree

| document | claim | verdict |
|---|---|---|
| `docs/deploy/COST-BOUND.md` I4 / I6 | the 1,554,168 B and 3,571,990 B figures | **CORRECTED.** Both are now explicitly relabelled as the packer's **INPUT** tree pre-strip, struck through where they previously claimed to be the served tree, with the deployed figures stated beside them (433,396 B identity / **124,127 B** on the wire; 1,274,342 B over 114 entries; **0** source maps) |
| `docs/deploy/LATENCY.md` | the `.map` beat | **CORRECTED.** Annotated in place: *"The DEPLOYED origin answers 404 to this path."* The transcript was annotated, not edited — editing a transcript to make a citation resolve would be falsifying evidence |
| `docs/deploy/terraform-plan.md` | line citations | Two off-by-one citations corrected (`main.tf:632` → `631`); one transcript annotated rather than rewritten |
| **`defeaters.py` refusal text** | *"the demo history does so in `demo_world.sql`"* | **FALSE — NEW.** See §2.4. `demo_world.sql` contains no defeater rows |
| `qa/cluster-known-red.json` | the `unstable` labels | **True but incomplete** — the file itself warns the four entries are deterministically failing on this tree |

---

## 9 · The rules matrix

| rule | held? | evidence |
|---|---|---|
| Never move an authoritative value to match a derived one | **HELD** | §1.1, §1.2, §1.3 |
| Never lower `COLLECTED_FLOOR`, the skip ceiling, or a known-red list to obtain a green | **HELD** | floor **raised** 440→518; 63 exemptions **removed**; one added and named (§1.4) |
| Never `terraform apply` | **HELD** | 0 mutating AWS calls; 7 refusals measured (§6) |
| Never print a credential | **HELD** | account id masked `0229REDACTED8246` throughout; no credential in any artefact read |
| Never weaken `HONESTY.md`, `CI-STATE.md`, a ratchet or an assertion | **HELD** | the failing assertion in `test_reads.py` is untouched and still red |
| `continue-on-error` / `\|\| true` banned | **HELD** | the bites lane uses `set +e` / explicit `rc` capture and **exits with pytest's status** |
| Report full-suite numbers before and after | **HELD** | §3 — and the answer is that this wave made them worse |
| A skip is indistinguishable from a green tick | **AT RISK** | 0 skips locally only because a gitignored zip exists on this workstation; CI's last real reading is **10 against a ceiling of 1** |

---

## 10 · Status of every component

### PROVEN
* The gate refusal, drift and admission mechanism — `PROVEN`, caveat-free, 271/271 migrations (§7).
* `40001` reproducibility on a single node, and the retry adapter that survives it — 6/6 races, 9 tests passing (§5).
* Terraform plan reproducibility — 24 / 35, four runs, two clones, zero mutating calls (§6).
* The cluster lane's 2×2 falsifiability argument — all four cells, cell 3 = cell 2 (§4.1).
* The cost bound, with the residual quantified and the documents now honest (§8).

### BUILT-BUT-UNPROVEN
* `.github/actions/build-demo-package/` — written, careful, **never run in CI**.
* Every workflow fix in this wave — uncommitted, so no CI run exists at this tree.
* `mainline_demo_api.defeaters` — correct, well-argued, and currently only able to demonstrate its refusal path.
* CockroachDB **Cloud** behaviour — explicitly and correctly unproven.

### BROKEN
* **The judge signature path.** Beat 4 refuses; beat 5 never admits (§2).
* **The demo-api suite** — 30 failed / 13 errors sequential, 31 / 13 randomised (§3).
* `defeaters.py`'s refusal text, which points a judge at a file that does not contain the rows (§2.4).

### NOT BUILT
* **The three `mainline.defeater_option` rows in `demo_world.sql`.** This is the whole blocker.
* Any run of this wave's tree in CI — nothing is committed.

---

## 11 · The founder's next actions

### Only he can do

1. **Trigger `cloud-verify` with `CRDB_CLOUD_DSN`.** The secret is reachable by CI only; no
   worker can obtain it and none must try. Until this runs, every `40001` claim is
   single-node. This is the last genuinely unknown thing in the build.
2. **Decide whether `eefae1c` + this working tree gets committed as-is.** As of now the
   published repository does **not** contain a wave that makes the suite redder. Committing
   the detector without the data publishes 43 failures; committing neither publishes a
   silent wrong digest. **The right order is: seed the rows, then commit both together.**
3. **Confirm the demo's authoritative defeater vocabulary.** The console contract
   (`console/contracts/disposition.schema.json`) and the console fixture are authoritative
   over both the seed and the tests. Somebody must rule which codes the demo offers before
   the rows are written — that is a product decision, not an engineering one.

### Engineering remaining

1. **Seed `mainline.defeater_option` in `demo_world.sql`** — three rows for check
   `dec0de00-0007-4000-8000-000000000001`, one shared `vocab_sha256` across the generation,
   with the codes ruled in (3) above. Re-baseline the frozen hash **in the same commit**,
   running the four-part negative control first. *Expected effect: ~24 of 43 reds clear and
   the judge path closes.*
2. **Fix `defeaters.py`'s refusal text** in that same commit (§2.4).
3. **Re-run the walk** and expect `judge-path-walk.json` to reach `"signed"` non-null and
   beat 5 to **admit**.
4. **Chase the residual reds** in `test_transitions.py` / `test_row_factory_contract.py`
   that are *not* downstream of the vocabulary, plus the one order-dependent failure that
   only appears under `--random-order`.
5. **Commit the workflows and push**, so `cluster-tests` and `cluster-lane-bites` finally
   run at this tree — that is the only way the 10 → 1 skip claim becomes true rather than
   intended.
6. **Delete the `unstable` entry added this wave** once the contamination behind it is
   fixed, and empty the last known-red group in the commit that seeds the rows — the file
   already says that is what it is waiting for.

---

## 12 · Verdict

**NO-GO — the sixth.**

It is a *better* NO-GO than the five before it. The shortcut check passes on its strongest
evidence yet; a real defect that had been invisible behind green tests was found and
correctly diagnosed; `40001` was falsified as Cloud-only and guarded properly; the plan
reproduces from a clean clone; the 2×2 completed; and the documents that were false about
this repository were corrected rather than argued with.

But the product's central claim is that a human being can look at a refusal, choose a
defeater, sign, and watch the gate open. **On this tree, they cannot.** Three rows stand
between this build and its own story, and this wave shipped the thing that detects their
absence instead of the rows themselves.
