<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: CC-BY-4.0
-->

# STATE OF THE BUILD

**Re-certified 2026-08-14 — SEVENTH verification.** Every number on this page came from a
command run on this machine today, against the tree described immediately below. Suite
totals are read from `--junitxml` root elements and from nowhere else. Where a figure comes
from a committed artefact or a CI run rather than from a command of mine, the artefact or
run id is named on the same line. Deadline **2026-08-18**.

**VERDICT: NO-GO on the apply.** One criterion is missing, it is missing for one reason,
and the reason is not a defect in the product. See §1.

## 0 · The tree this page is certified against

Stated before anything else, because a verdict page that misnames its own tree cannot be
checked by anyone.

| | |
|---|---|
| local `HEAD` | `d098721` — *style(demo-api): the last unformatted file, and only its formatting* |
| `origin/master` | `7535670` — **four commits behind local HEAD** |
| working tree | **89 paths modified or untracked**, none of them staged |
| local CockroachDB | CCL **v26.2.5** on `127.0.0.1:26257`, container `trappoint-crdb`, up 35 h, healthy |
| interpreter | `D:/CoackroachDBxAWS/mainline/.venv/Scripts/python.exe` — Python 3.13, pytest 9.1.1, psycopg 3.3.4, ruff 0.16.1 |

**The single most important fact on this page: nothing in this wave has been pushed.** The
four commits above and all 89 working-tree paths exist only on TRAPPOINT. Every CI lane
result quoted below was measured at `7535670`, i.e. **before** the work that was written to
fix those lanes. No lane has ever executed the current tree.

---

## 1 · The verdict, against the six conditions for a GO

| # | Condition for GO | Status | Where it was measured |
|---|---|---|---|
| 1 | No shortcut | **MET** | §2, my own re-runs |
| 2 | Suite green in both orders | **MET** | §3, two `--junitxml` roots |
| 3 | A judge can sign | **MET** | §4, real handler against Cloud |
| 4 | Cluster lane green, skips at ceiling, 2×2 discriminating | **NOT MET** | §5 |
| 5 | Cloud proven | **MET** | §4 and §6 |
| 6 | Plan reproducible from a clean clone | **MET** | §7 |

**Five of six are met, and the sixth fails for a procedural reason rather than a product
defect: the fixes for both cluster lanes are written, are locally verified, and are
unpushed.** A lane cannot be green at a tree it has never run. This is a seventh NO-GO, and
the honest gap is small — see §10 for what closes it and how long it takes.

---

## 2 · NO SHORTCUTS — the first check, and it is clean

`git diff` over every seed, fixture, ceiling, floor, threshold, expected value and known-red
entry this wave touched. **Nothing moved an authoritative side to match a derived one. No
floor was lowered, no ceiling raised, and no exemption added — several were removed.**

### 2.1 Everything that moved, and which direction

| Artefact | Moved | Direction |
|---|---|---|
| `qa/ruff-ratchet.json` | RUF001 `tests/` 9→0, PLR0912 `scripts/` 2→0, RUF002 `tests/` 2→1, ARG002 1→0, E402 1→0 | **tighter** |
| `qa/reuse-ratchet.json` | `reuse_toml_patterns_matching_nothing` 5→1; `matching_only_untracked` 4 entries→0 | **tighter** |
| `qa/cluster-known-red.json` | `groups` → `[]`, `unstable` → `[]`; entries relocated to `superseded` | **exemptions removed** |
| `qa/cluster-known-red.json` `floor` | `min_executed` **518 unchanged**, `max_skipped` **1 unchanged** | **held** |
| `static_site.DEFAULT_MAX_RESPONSE_BYTES` | `136 * 1024 = 139_264` | **unchanged** |
| I3 falsification pin | 149,000 → **149,013** | **tighter** |
| `demo_world.sql`, `demo_permit.sql` | **byte-identical**, committed and uncommitted | **untouched** |

The four `unstable` entries the previous verification flagged — *"four broken tests
sheltering in the one category no ceiling polices"* — are **gone**, and the file now carries
its own reason for each departure under `superseded`. That is the pruning the sixth
verification asked for.

### 2.2 The frozen seed — the check closest to the cardinal sin, re-run by me

Two frozen-seed hashes were re-baselined this wave. A re-baseline of a seed hash is exactly
the shape of the offence this repository exists to refuse, so I did not accept the argument
on file — I re-ran the control myself:

```
$ python scripts/ci/plant_cluster_defect.py --plant seed-credential-swap
$ pytest tests/ci/test_demo_seed_is_frozen.py --crdb=none -q
FAILED ...::test_the_deployed_seed_files_have_not_changed[demo_world.sql]
FAILED ...::test_the_seed_derives_the_demo_credentials_from_their_names
2 failed, 1 passed in 0.46s
$ python scripts/ci/plant_cluster_defect.py --revert
   reverted 'seed-credential-swap': demo_world.sql restored byte-for-byte (sha256 78158939baf0...)
$ pytest tests/ci/test_demo_seed_is_frozen.py --crdb=none -q
3 passed in 0.29s
$ git status --porcelain   # over the seeds and the plant directory
(empty)
```

**The guard discriminates.** `demo_world.sql`, the file the plant edits, goes red;
`demo_permit.sql`, which it does not touch, stays green; the derivation control fires; the
revert is byte-exact. The hash is a reading *of* a file and is never authoritative *over*
it, the seed files themselves were not edited by this wave, and the re-baseline is therefore
a re-measurement rather than a repair.

### 2.3 The one authoritative artefact that DID move — examined, and accepted

`contracts/gate-run.schema.json` changed the field the verdict keys on, from
`persistence_check.identical` to `persistence_check.self_persisted`. **A committed JSON
schema is authoritative for what the demo must carry, so this deserves the hardest look on
the page**, and a weakening here would be worth more than every green below.

It is not a weakening, on four independent grounds I checked rather than read:

1. **The ten unscoped counts are byte-identical.** I diffed `_FINGERPRINT_SQL` directly: ten
   `count(*)`s over the same ten tables, no `WHERE permit_id` added, `_FINGERPRINT_TABLES`
   intact. Run-scoped evidence was **added beside** them, never in place of them.
2. **The defect it fixes is real and reproduced.** `identical` is a statement about the whole
   database; it is false whenever *any* other caller commits. `docs/diagnosis/gate-run-fingerprint.md`
   constructs the writer and attributes every appeared row to a permit that is not the run's
   subject. On a bounded-but-open demo URL, one judge signing while another presses gate-run
   would tell the second judge the demo persisted something. That is a contract gap.
3. **It falsified its own plan's prediction.** The plan named "two judges pressing the button
   at once" as the cause; measured, both runs return `PROVEN`, so it is not — and the repair
   that prediction would have justified (serialising the endpoint) would have destroyed the
   property that lets fifty judges share one history.
4. **The new claim can still fail, and is made to.** `test_a_run_that_really_persists_is_caught`
   forces a real commit and requires `self_persisted is True` and verdict `NOT PROVEN`. It
   passed in both of my full-suite runs. Its first draft did not fire and was strengthened
   rather than kept — recorded on the page.

A count delta caused by somebody else is now reported as `concurrent_writes` instead of
being charged to the run. **`identical` is still computed and still in the payload.**

### 2.4 The deployed-tree constants — re-recorded, and the ceiling did not move

Eight assertions were re-recorded from a build proven to reproduce byte-for-byte from
`git archive HEAD`. The order was reproducibility first, numbers second. The **derived**
ceiling `139,264` did not move (`1.10 × 124,177 = 136,594.7` → next 8 KiB boundary → the
same 139,264), and the one pin that had to move became **tighter**. This is a re-derivation,
not a relaxation.

---

## 3 · The suite — PROVEN, green in both orders

Read from `--junitxml` root elements. Run with the sanctioned `MAINLINE_W4_DATABASE`
override, because the scratch database is named from a fingerprint of its own inputs and two
concurrent sessions otherwise share one database — the hazard that corrupted a reading
earlier in this wave.

| order | tests | passed | failed | errors | skipped | time |
|---|---|---|---|---|---|---|
| default (`-p no:randomly`) | **576** | **575** | **0** | **0** | **1** | 211.1 s |
| randomised | **576** | **575** | **0** | **0** | **1** | 212.5 s |

The one skip is `test_gate_run.py::test_payload_validates_against_the_json_schema` —
*"jsonschema is not a workspace dependency"*, which has nothing to do with the database.

**The baseline in the brief was 570 / 569. The suite GREW by six tests and stayed green** —
the six are the new controls this wave added (the persistence plant, the concurrent-committer
tripwire, the two-judge falsification, the 40001 controls). No neighbour was broken.

---

## 4 · A judge can sign — PROVEN, driven by me through the real handler

Not read from an artefact. I served the **real** `mainline_demo_api.app` handler through
`scripts/deploy/local_furl.py` against **CockroachDB Cloud**, with `--database mainline_demo`
supplied explicitly because the committed DSN's path segment says `defaultdb` — the
documented trap — and drove the acceptance from outside.

```
HEALTH        200        cluster CockroachDB CCL v26.2.5, database mainline_demo
GATE RUN 1    HTTP 200   READ     [00000]
                         REFUSED  [23514] gate_closed_when_issued        (reported)
                         REFUSED  [P0001] mainline.fn_permit_merge_gate  (parsed)
                         ADMITTED [00000]
              persisted false   verdict PROVEN
GATE RUN 2    HTTP 200   same four beats, persisted false, verdict PROVEN
REPEATABLE    True   (stable projection of two runs)
UNCHANGED     True   open_blocking=1 state=dispositioned gate_epoch=1 head_seq=2
VOCABULARY    …0007  3 option(s), 1 generation, 2ccb08a3d9d1f89e…
VOCABULARY    …000d  3 option(s), 1 generation, d9c837c25bb174d1…
NOT A CONSTANT True   (2 vocabularies, 2 distinct digests)
VERDICT       PROVEN (phase2)
```

**`NOT A CONSTANT True` is the load-bearing line for signing**: two obligations return two
*different* defeater vocabularies, served from `mainline.defeater_option`'s own rows to a
caller holding no credentials. A hard-coded list would produce one digest twice. The judge
can refuse, materialise, choose a defeater, sign, and be admitted.

**Two advisories are correctly carried and are not defects:**

* The target answers `x-mainline-emulator: local_furl`. This proves the handler, the site
  and the gate. **It does not prove a public demo URL exists** — none does, and
  `SUBMISSION.json` correctly holds `UNRESOLVED`.
* `/v1/health` reports `migrations_applied=0`. That is a true count of the wrong ledger:
  the Cloud database was built by `cloud_chain.py`, which records into
  `trappoint.deploy_chain`, while health counts `trappoint.schema_migration`. The
  non-null `schema_fingerprint` is the identifier that moves when the schema does.

---

## 5 · The cluster lane — THE ONE BLOCKER

Both lanes were read WARM. **Neither has ever run at the current tree**, because the current
tree has never been pushed. What follows is `7535670`, the newest commit CI has seen.

### 5.1 `cluster-tests` — run 31770005759

**The skip defect the sixth verification named is FIXED.** The lane now builds the
deployment package itself (step *"Build the deployed package the ratchets read"* — green), so
the nine tree-reading assertions no longer skip:

```
cluster lane: 570 collected, 569 executed, 1 skipped, 8 failed, 0 errored
bundle_manifest: mainline-demo-api-arm64.zip sha256=5a071ce1869d30be… VERDICT PASS
```

**Skips are 1, against a ceiling of 1 — at the ceiling, and the ceiling was not raised.**
Executed 569 against a floor of 518. The lane was right to error before, and it was fixed
the way the rule demands: by building the package, not by raising the ceiling.

The **8 failures are all one finding** — the deployed-tree constants named a `console/dist`
no commit reproduces. All eight are in `test_response_contract.py` and `test_static_site.py`.
**Commit `f68abb7` re-records exactly those eight** (§2.4) and is unpushed. Those same eight
assertions pass in both of my full-suite runs at the current tree.

### 5.2 `cluster-lane-bites` — run 31770005766

**The 2×2 discriminated. All four cells passed:**

```
✓ Cell 1/4 — plant ABSENT, cluster:   the subset is GREEN today
✓ Cell 2/4 — plant ABSENT, hermetic:  GREEN, and 7 tests actually ran
✓ Cell 3/4 — plant PRESENT, hermetic: STILL GREEN, and the same 7 ran
✓ Cell 4/4 — plant PRESENT, cluster:  RED, and the named control is what failed
✓ The inventory cannot suppress a failure, even when it names every one
✓ The frozen-seed guard is RED against this edit
✓ Revert the plant, and prove the tree is where it started
X The frozen-seed guard is GREEN again          <- the only red
-  The 2x2, as one table                        <- SKIPPED as a consequence
```

**Cell 3 is the load-bearing cell and it passed the same count as cell 2** — 7 executed on
both trees, which is what proves the hermetic lane could not have seen the defect. The lane
then died on step 18 for an unrelated reason: `898ad55` changed the seed and did not
re-measure the freeze in the same commit, so the guard was red at a clean tree. **The guard
was right.** Because the summary step deliberately carries no `if: always()`, step 19 was
skipped and **the 2×2 table has still never been published**.

`5e6932e` re-measures those two hashes after the four-part control (§2.2) and is unpushed.

### 5.3 What this means

| Question the brief asks | Answer |
|---|---|
| Are skips at the ceiling of 1? | **Yes** — 1 of 1, at `7535670`. Fixed by building the package in-lane. |
| Did the 2×2 complete? | **All four cells passed**; the summary step was skipped, so the table is still unpublished. |
| Does plant-present/hermetic pass the same count as plant-absent? | **Yes** — 7 executed, 7 passed, both cells. |
| Is the known-red list true against its tree? | **Yes, by being empty** — both groups pruned, floors held. |
| Is the lane green? | **No.** Both remaining reds have written, locally-verified, **unpushed** fixes. |

---

## 6 · Cloud — PROVEN, and the 40001 loop is proven *reached*

Cloud is re-seeded and the demo is proven there (§4, reproduced by me today).

The 40001 retry path is exercised against Cloud with a genuine negative control —
`evidence/deploy/cloud-contention.json`, 12 rounds per arm on Cloud and local in one sitting:

| reading | Cloud | local |
|---|---|---|
| rounds with 40001 | 12 / 12 | 12 / 12 |
| restart reason | `RETRY_SERIALIZABLE` ×12 | `RETRY_SERIALIZABLE` ×12 |
| **callers where `run_gate` ACTUALLY retried** | **12** | **12** |
| callers where record and spy disagree | **0** | **0** |
| retry budget exhausted | 0 | 0 |

**The spy is the point.** A `RecordingObserver` records whether the loop was entered rather
than assuming it, so "the retry path is exercised" is measured, not inferred. Node topology
is explicitly **not** read: `crdb_internal` and `system` are restricted on Basic tier, and
the census says so rather than reporting a privilege refusal as a topology.

---

## 7 · The plan — reproducible, 24 resources, nothing applied

Run by me today at the current tree, read-only:

```
validate     Success! The configuration is valid.
fresh plan   Plan: 24 to add, 0 to change, 0 to destroy.
committed    evidence/deploy/terraform-plan-furl.txt says Plan: 24 to add
G6           reserved_concurrent_executions = -1
G7           0 occurrence(s) of twelve zeros
```

The wrapper's refusal control is falsifiable and I ran it: **`apply`, `destroy`, `import`,
`taint`, `force-unlock`, `state`, `plan -destroy` — seven refusals, seven exits of 2.**

Clean-clone reproduction is recorded in `evidence/deploy/lead/plan-repro-fresh-clone.json`
at `7535670`, reaching the same `Plan: 24 to add` from a directory never previously used.
**`infra/` has not changed since**: the only edits are comments in `backend.tf` and
`README.md`, which I verified carry zero non-comment additions. The partial-backend gap the
sixth verification named is closed.

**No `terraform apply` was run. No AWS resource was created, changed or deleted.**

---

## 8 · The board, by category

### PROVEN — measured today at this tree

* The demo-api suite: 576 / 575 / 0F / 0E / 1S, **both orders**.
* The gate proof, caveat-free: chain **271/271**, PROJECTION **10/10**, REFUSAL **23514**,
  DRIFT **P0001**, ADMISSION **00000**, `VERDICT PROVEN`.
* A judge can sign, through the real handler against Cloud, with two distinct vocabularies.
* Cloud demo `PROVEN` ×2, repeatable, permit projection unchanged.
* 40001 on Cloud, with the retry loop proven reached by a spy.
* `terraform plan` = 24 to add, matching the committed artefact; seven mutating verbs refused.
* `scripts/aws/verify_evidence.py`: **1024 assertions across 40 of 40 invariants, PASS**.
* `check_reuse.py`: 7576 tracked files, 0 uncovered, no counted number rose.
* `skip_ratchet` and `row_factory_ratchet`: exit 0; unlanded 730 against a ceiling of 730.
* `test_docs_are_true.py`: 44 passed.
* The frozen-seed guard, and its plant, re-run by me.

### BUILT-BUT-UNPROVEN — written and locally verified, never executed by CI

* **The `cluster-tests` constant fix** (`f68abb7`) — the eight failures pass locally.
* **The `cluster-lane-bites` seed re-measure** (`5e6932e`) — the guard passes locally.
* **The whole 89-path working tree**, including the gate-run contract change, the Cloud
  hardening, the post-apply verifier and the document repairs.
* **The 2×2 summary table** — the cells passed; the table has never rendered.

### BROKEN — genuinely red, with owners

* **`schema` and `db`** — RED BY DESIGN. Two objects are referenced by the reference vertical
  and created by no file in it: **`trappoint_ref.event`** and **`trappoint_ref.clause`**.
  Only a `CREATE TABLE` migration for each turns these green; narrowing the matrix or
  dropping the foreign key is explicitly refused by the lane. KERNEL domain.
* **`db-schema`** — 5 invariants HELD pending: **MI06, MI10, MI21, MI22, MI27**. None may be
  promoted; the ledger names the absent object and the too-weak owning test for each.
* **`ci`** — `ruff format` counted ratchet. CI at `7535670` measured **14** unformatted files
  against a hard-gate baseline of 0. See §9: this number **cannot be measured on TRAPPOINT**.
* **`submission`** — licence census on the clone path.

### NOT BUILT

* **There is no deployed demo URL.** No `terraform apply` has run; `SUBMISSION.json` holds
  `UNRESOLVED`. `demo-health` has failed every scheduled run today for exactly this reason
  and says so — it goes green on its own once a URL exists. This is the expected pre-apply
  state, not a defect.

---

## 9 · A measurement trap this workstation sets, recorded so the next worker does not fall in

**`ruff format` cannot be measured truthfully on TRAPPOINT.** Locally the ratchet refuses
with 196 flagged files and six blown hard gates. That reading is false:

* **Zero of the 196 were touched by this wave.** They are spread across packages the wave
  never opened.
* I proved the mechanism on a flagged file: it holds CRLF on disk; converted to LF it is
  *"1 file already formatted"*, unconverted it is *"1 file would be reformatted"*.
* Git for Windows ships `core.autocrlf=true` at system scope, so the index holds LF, the
  worktree holds CRLF, and **`git status` stays clean** — the same trap `f68abb7` documents
  for the console build.
* CI, on Linux with LF, measured **14** — not 196.

**The repository still ships no `.gitattributes` pinning `*.py text eol=lf`.** The
fresh-clone evidence already recommended this and it is still not owned by anyone. Until it
exists, a Windows worker will keep reading a lint catastrophe that does not exist — and,
worse, could "fix" 196 files that were never broken.

A second trap worth repeating: `python script.py | tail` returns **`tail`'s** exit status. I
read `ruff_ratchet` as exit 0 through a pipe when it genuinely exits 1.

---

## 10 · The founder's next actions

### 10.1 Only he can do these

1. **Decide whether the unpushed wave is pushed.** Four commits and 89 working-tree paths sit
   only on TRAPPOINT. Nothing below is knowable until they are on `master`. This is the
   whole of the remaining distance to a GO on condition 4.
2. **Re-authorise the apply after the lanes are green.** The standing authorisation does not
   survive a plan change, and the plan is unchanged at 24 — but it also does not survive a
   NO-GO. No worker may apply.
3. **Accept or reject the gate-run contract amendment** (§2.3). It is the one authoritative
   artefact this wave moved. My review says it is earned; the decision to move a committed
   contract is the founder's, not a verifier's.
4. **Decide the two KERNEL migrations are in scope for the deadline** — `trappoint_ref.event`
   and `trappoint_ref.clause`. They are four days from the deadline and gate three lanes.
5. **Own the cost decision.** USD **1.60/min** in-window, **564/30 d** unattended, against
   ~229,805 unbounded. Unchanged this wave and still a judgement, not a measurement.

### 10.2 Engineering remaining, in the order that unblocks the most

| # | Work | Unblocks | Estimate |
|---|---|---|---|
| 1 | **Push the wave and read both cluster lanes warm** | conditions 4; `ci`, `aws-evidence` | 10 min CI, ~45 min with triage |
| 2 | Confirm the 2×2 table finally renders (step 19 is reached only when step 18 is green) | the lane's entire argument | included in 1 |
| 3 | Two `CREATE TABLE` migrations in `packages/trappoint-sql/refvertical/sql/` | `schema`, `db` | half a day, KERNEL |
| 4 | Promote or re-scope MI06/MI10/MI21/MI22/MI27 | `db-schema` | half a day |
| 5 | Add `.gitattributes` pinning `*.py text eol=lf` (and `*.tf`) | makes lint measurable on Windows | 15 min |
| 6 | Give `db` the readable-diagnosis treatment `cluster-tests` got (engine log to its own file) | a lane whose red can be read | 1 hour |
| 7 | Fix the residual `ruff format` files CI actually sees (14, not 196) | `ci` | 1 hour, **on Linux or against LF** |
| 8 | Licence census on the clone path | `submission` | 1 hour |

**None of this is on the apply's critical path except item 1.** Items 3–8 are lanes that
must be green to submit, not to deploy.

---

## 11 · What I did not do

* I did not run `terraform apply`, and made no mutating AWS call.
* I did not print, rotate or record a credential; the one DSN this page names is masked.
* I did not edit a seed, a fixture, a ceiling, a floor or a known-red entry. The plant I ran
  reverted byte-for-byte and I verified the tree afterwards.
* I did not push anything. The decision in §10.1 item 1 is the founder's.

---

## 12 · Verdict

**NO-GO on the apply.**

Five of the six conditions for a GO are met. The sixth — *the cluster lane green, with skips
at the ceiling and the 2×2 discriminating* — is not, and the reason is procedural rather
than a defect in the product: the commits that fix both lanes (`5e6932e`, `f68abb7`, and the
lint and formatting work in `c9a7253`) have never been pushed, so no lane has executed a tree
containing them. The last tree CI saw is `7535670`.

The verdicts this page supersedes are preserved rather than deleted: the sixth verification
recorded `NO-GO` at `073dfea`, and the wave landed on top of `eefae1c`. This is the seventh
consecutive NO-GO, and each of the six before it was right.

**Nothing on this page authorises an apply.** The apply authorisation is the founder's, is
conditional on a GO, and does not survive a NO-GO.

---

**Seventh verification: NO-GO.** Five of six conditions are met and the build is the closest
it has been — a judge can sign against Cloud, the suite is green in both orders, the gate
proof is caveat-free, the plan reproduces at 24, and the skip defect and the 2×2 both did
what they were built to do. **The sixth condition fails because the work that fixes the two
cluster lanes has never been pushed, and a lane cannot be green at a tree it has never run.**
That is roughly an hour of CI and triage away, not a rebuild.
