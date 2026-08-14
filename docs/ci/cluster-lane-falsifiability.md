<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: CC-BY-4.0
-->

# The cluster lane's 2×2, measured — with the artefacts attached

**This document now carries THREE measurements of the same 2×2, and none replaces another.**

| | where | when | what it can say |
|---|---|---|---|
| [**§Z**](#z-the-four-cells-at-the-public-tip--run-31770005766-head-7535670) | GitHub Actions, `ubuntu-24.04`, fresh checkout, fresh container | run **31770005766**, 2026-08-14, HEAD **`7535670` — the public tip** | **all four cells at a CURRENT tree**, with the load-bearing cell measured rather than assumed |
| [**§A**](#a-the-lanes-first-complete-run-in-ci--run-31735341050) | GitHub Actions, `ubuntu-24.04`, fresh checkout, fresh container | run **31735341050**, 2026-08-13, HEAD `eefae1c` | the lane itself, end to end, including the `git status --porcelain` hygiene assertions that **cannot** be exercised locally |
| [**§0–§10**](#0-why-this-document-was-rewritten) | TRAPPOINT, local node, long-lived databases | 2026-08-14, HEAD `538193b` | the cells in far more depth — executed node-id **sets**, eight attempts, two plant/revert cycles, committed JUnit artefacts |

§Z is the newest and the only one taken at the tip a judge can fetch; §A measures the *lane*;
§0–§10 is deeper and measures the *claim*. §A.5 records, cell by cell, which of §5's five
findings the CI run reproduced and which it did not. Nothing in §A or §0–§10 has been edited
by §Z's author — §Z is added beside them, because a 2×2 re-run at a newer tree that overwrote
the older readings would destroy the only evidence that the lane behaves the same way twice.

---

## Z. The four cells at the public tip — run 31770005766, HEAD 7535670

**Worker:** D3, DOCS-TRUE wave, 2026-08-14. **Read out of the job log** with
`gh api "repos/Shaugato/mainline/actions/jobs/94673769513/logs"` — the whole job log, 1,756
lines, not `--log-failed` and not a summary page, **because the run published no 2×2 table**
for the reason §Z.4 gives.

| | |
|---|---|
| workflow | `.github/workflows/cluster-lane-bites.yml` |
| run | [`31770005766`](https://github.com/Shaugato/mainline/actions/runs/31770005766), event `push`, HEAD **`7535670`** — the public tip |
| job | *"the cluster lane bites, and the hermetic lane cannot"*, `2026-08-14T04:29:07Z` → `04:33:22Z` |
| conclusion | **failure — at step 19, and only there.** Steps **1–18 passed**; step **19 failed**; step **20 was skipped**; step **21 passed** |

### Z.0 What is new about this run, stated before the numbers

**The 2×2 had never completed at a current tree.** §A's run is at `eefae1c`, two commits
behind the tip; §0–§10 is a local measurement at `538193b`, a tree that no longer exists on
the remote. **At `7535670` all four cells ran and all four passed**, and so did the
inventory-cannot-suppress control and the frozen-seed guard's plant-present half.

The lane is still **red**, and the reason matters more than the colour: the failing step runs
**after** the plant has been reverted and the tree proved byte-for-byte clean, so it says
nothing at all about falsifiability. §Z.3 has it.

### Z.1 The four cells, as the run printed them

Every figure is the pytest summary line of that step, quoted:

| cell | plant | lane | the runner's own summary | verdict |
|---|---|---|---|---|
| **1/4** | ABSENT | cluster | `77 passed, 1 skipped in 113.10s (0:01:53)` | **GREEN** — the subset is healthy before anything is planted |
| **2/4** | ABSENT | hermetic | `7 passed, 71 skipped in 0.33s` | **GREEN**, and **7 tests actually ran** |
| **3/4** | PRESENT | hermetic | `7 passed, 71 skipped in 0.34s` | **STILL GREEN, and the SAME 7 ran** |
| **4/4** | PRESENT | cluster | `3 failed, 74 passed, 1 skipped in 110.63s (0:01:50)` | **RED, and the named control is what failed** |

### Z.2 THE LOAD-BEARING CELL IS 3/4, AND THIS IS WHAT IT MEANS

**The cell the entire lane exists to produce is cell 3: plant PRESENT, hermetic lane, passing
the SAME count as plant ABSENT.** Cell 4 going red is the easy half — a defect that a cluster
can see, seen by a cluster. Cell 3 is the half that is worth something: **it is the proof that
the hermetic lane COULD NOT have caught this defect**, and therefore that the cluster lane is
not redundant with the lane the repository already had.

Stated as an equation, from the two summary lines above:

```
cell 2  (plant ABSENT,  --crdb=none):  7 passed, 71 skipped     ← the control
cell 3  (plant PRESENT, --crdb=none):  7 passed, 71 skipped     ← the load-bearing cell
                                       ↑ IDENTICAL
```

**Read the failure modes of this cell in both directions, because only one of them is
obvious.**

* **If cell 3 went RED**, the hermetic lane *would* have caught the plant, the cluster lane
  would be proving nothing the repository did not already have, and the correct response is
  **a different plant** — a defect genuinely invisible without a database. **It is never a
  relaxed assertion.** Changing `executed == before` to `executed >= before`, or dropping the
  comparison, or narrowing the subset until the numbers agree, each converts a refuted claim
  into an unfalsifiable one. **A relaxed assertion here is not a weaker result; it is the
  absence of a result wearing the same colour.**
* **If cell 3 went GREEN because nothing ran** — 0 passed, 71 skipped — the equality would
  hold vacuously and the cell would assert nothing whatever. That is why the workflow's step
  name carries the count out loud (*"STILL GREEN, and the same 7 ran"*) and why §3's local
  measurement compares **node-id sets** and not just integers: a count equality can be
  satisfied by one test dropping out as another appears; a set equality cannot.

Both failure modes are guarded and neither fired. **The 7 is as load-bearing as the equality**,
and any future reading of this cell that reports the equality without the count has reported
half of it.

The seven node ids are enumerated in §3 above and are unchanged in this run. Two of them
deserve re-naming here because they are why the claim is not trivial:
`test_no_module_derives_a_credential_id` — the AST ratchet, which passes because the planted
derivation is in a **seed** and not in code — and
`test_the_seed_files_this_suite_runs_against_are_the_ones_the_deploy_applies`, which compares
file **names** and passes because only the bytes inside one file changed. **Two hermetic
controls whose names sound like they should have caught this ran, and could not.**

### Z.3 The one failing step, and why it is downstream of the argument

The job's step list, with the number and conclusion **GitHub itself records for each** —
quoted from `gh run view 31770005766 --json jobs --jq '.jobs[].steps[] | "\(.number) \(.conclusion) \(.name)"'`
rather than counted by hand, because a step ordinal depends on whether the describer counted
`Set up job` and this document has no business inventing its own numbering:

```
11  success  Cell 1/4 - plant ABSENT,  cluster:  the subset is GREEN today
12  success  Cell 2/4 - plant ABSENT,  hermetic: GREEN, and 7 tests actually ran
13  success  Plant the defect only a database can see
14  success  Cell 3/4 - plant PRESENT, hermetic: STILL GREEN, and the same 7 ran
15  success  Cell 4/4 - plant PRESENT, cluster:  RED, and the named control is what failed
16  success  The inventory cannot suppress a failure, even when it names every one
17  success  The frozen-seed guard is RED against this edit
18  success  Revert the plant, and prove the tree is where it started
19  FAILURE  The frozen-seed guard is GREEN again
20  skipped  The 2x2, as one table
21  success  The container's own account of the run
```

The failure, quoted:

```
2 failed, 1 passed in 0.18s
FAILED tests/ci/test_demo_seed_is_frozen.py::…[demo_permit.sql]
FAILED tests/ci/test_demo_seed_is_frozen.py::…[demo_world.sql]
```

with the lane's own error, which diagnoses itself correctly:

> *"`tests/ci/test_demo_seed_is_frozen.py` failed AFTER the revert, on a tree the step above
> proved byte-for-byte clean, so this is not about the plant. Either a deployed seed changed
> and the freeze was not re-measured in the same commit (the stale-baseline case: read which
> side moved, and note that **a hash computed FROM a file is never authoritative OVER that
> file**), or a deployed seed has been reshaped and the freeze is telling you so."*

**It is the stale-baseline case, and the guard was RIGHT.** Commit `898ad55` seeded
`mainline.defeater_option` into both deployed seed files and did not re-measure the freeze in
the same commit — which is precisely the omission `test_demo_seed_is_frozen.py` exists to
catch. From `898ad55` until the freeze is re-measured, those two hash assertions are red at a
**clean** tree, and **red with the plant and red without it discriminates nothing.**

**Note what the guard did NOT do.** It fired against the plant (step 17, green) and it fired
against the tip (step 18, red). Both firings are correct behaviour. The file's own
`HOW TO RE-BASELINE` procedure makes re-measurement conditional on a **four-part negative
control** run *before* the constants are touched — the seed diff carries no moved credential
line; the derivation control passes; `test_credentials.py` passes in full under
`--crdb=reuse`; and `demo_world.sql` still enrols exactly one signer as a digest of its NAME.
**All four must come back clean, and if any one does not, the answer is to revert the seed and
not to edit the recorded hash.** That is the incident this whole lane was built after.

### Z.4 The 2×2's own table has STILL never been published by a run

Step 19, *The 2×2, as one table*, was **skipped**, because it carries no `if: always()` and
step 18 failed. §A.4 recorded the same outcome at `eefae1c`; it has now happened at `7535670`
as well. **Three CI runs of this lane have produced all or most of the 2×2 and not one has
printed it.**

This is a real defect of the lane and it is named here rather than worked around:

> **A falsifiability argument whose conclusion is only reachable by reading nineteen step
> names one at a time is a falsifiability argument most people will not read.**

The fix is one `if: always()` on the summary step, in a workflow this documents wave does not
own. **It is not a fix to make step 18 pass**, and the two must not be confused: step 18 is
red for a real reason (§Z.3) and its cure is a re-measured freeze under the four-part control,
not a green obtained by reordering.

### Z.5 What this run does NOT establish

* **It is one run.** §6.7 of `docs/CI-STATE.md` and §10 below both say a single green does not
  refute a flake, and that applies to a single green 2×2 exactly as much as to anything else.
* **The plant is one plant.** Cell 3 proves the hermetic lane cannot see **this** defect. It
  is not a proof that the hermetic lane cannot see any seed-shaped defect, and no sentence in
  this document should be read as claiming that.
* **The cluster is a single node.** As everywhere else on this board, "cluster" means one
  pinned `cockroachdb/cockroach:v26.2.5` container. Nothing here exercises multi-node
  behaviour or the `40001` retry path.
* **The `.gitignore`-clean assertions are still the part only CI can make.** They passed here
  as they did in §A, and they remain unreproducible on a workstation that six workers share.

---

## A. The lane's first complete run in CI — run 31735341050

**Worker:** W2, lane-honest wave, 2026-08-14. **Read out of the run log** via
`gh run view 31735341050 --repo Shaugato/mainline --log`, not from a summary page — the run
published no step summary at all, for the reason §A.4 gives.

| | |
|---|---|
| workflow | `.github/workflows/cluster-lane-bites.yml` |
| run | [`31735341050`](https://github.com/Shaugato/mainline/actions/runs/31735341050), event `push`, HEAD `eefae1c` |
| job | *"the cluster lane bites, and the hermetic lane cannot"*, `2026-08-13T19:20:53Z` → `19:24:31Z` (**3 m 38 s**) |
| runner | `ubuntu-24.04` |
| image | `cockroachdb/cockroach:v26.2.5`, resolved to `sha256:771325a0586bf61d53322d24f5a6de8962568b0fc181fa45db364278e5961282` |
| the server's own answer | *"compose.yaml asked for v26.2.5; the server said: CockroachDB CCL v26.2.5 (x86_64-pc-linux-gnu, built 2026/07/28 18:56:00, go1.25.5)"* |
| conclusion | **failure — at the last step, and only there.** Steps 1–18 passed; step 19 failed; step 20 was skipped |

### A.1 The four cells, as the run printed them

Every figure below is a line the job echoed. `executed` is `collected − skipped`, which is
how the workflow computes it.

| cell | plant | `--crdb` | pytest's own line | collected | executed | skipped | verdict |
|---|---|---|---|---|---|---|---|
| **1/4** | absent | `reuse` | `77 passed, 1 skipped in 109.21s` | 78 | **77** | 1 | GREEN, floor 77, **margin 0** |
| **2/4** | absent | `none` | `7 passed, 71 skipped in 0.32s` | 78 | **7** | 71 | GREEN, floor 7, **margin 0** |
| **3/4** | present | `none` | `7 passed, 71 skipped in 0.30s` | 78 | **7** | 71 | **GREEN, and equal to cell 2** |
| **4/4** | present | `reuse` | `3 failed, 74 passed, 1 skipped in 76.12s` | 78 | 77 | 1 | **RED, for the named control** |

```
cell 1/4: 77 executed under a cluster (floor 77)
cell 2/4: 7 executed with no cluster (floor 7)
cell 3/4: 7 executed with the plant present; cell 2 ran 7
the hermetic lane cannot tell the planted tree from the clean one
cell 4/4: 3 failure(s)/error(s) under a cluster: ['test_the_admission_is_a_green_this_database_could_have_refused',
 'test_the_deployed_seed_and_the_proof_seed_are_two_different_worlds',
 'test_the_deployed_seed_does_not_enrol_the_value_gate_run_used_to_derive']
the cluster lane is RED, and test_the_deployed_seed_does_not_enrol_the_value_gate_run_used_to_derive is what caught it
```

Reduced to the shape the lane argues about:

|  | plant ABSENT | plant PRESENT |
|---|---|---|
| `--crdb=none`  | GREEN — 7 executed, 7 passed | **GREEN — 7 executed, 7 passed, the same count** |
| `--crdb=reuse` | GREEN — 77 executed, 77 passed | **RED — 3 failed, and `caught_by` is among them** |

**The load-bearing cell is the top-right one, and it passed.** The tree carried the exact
edit that put `23503 disposition_signer_credential_id_fkey` in front of a judge, and the
hermetic lane executed the same seven tests and reported success — which is the sentence
`cluster-tests.yml` exists to earn. Any claim that this lane "has never completed one cell of
its 2×2" is false, and correcting it is worth more than repeating it: **a passing 2×2 that
somebody restructures because a summary described it wrongly is the most expensive thing this
repository could lose.**

### A.2 The other two assertions, which are not cells

The 2×2 is four of the six things this job asserts. Both of the others also passed.

**Fifth — the known-red inventory cannot be turned into a silencer.** The job builds a copy
of `qa/cluster-known-red.json` as permissive as the schema allows (`min_executed: 0`,
`max_skipped: 10000`, every failing node id of cell 4 declared known) and requires the report
to stay non-zero anyway, twice:

```
cluster lane: 78 collected, 77 executed, 1 skipped, 3 failed, 0 errored
report exited 1 when told pytest exited 1
report exited 1 when told pytest exited 0
   ↳ the JUnit report records 3 failure(s) and 0 error(s) in its summary and 3 failing test
     case(s) in its body, but this program was told pytest exited 0. The caller is not
     passing pytest's real status to --pytest-rc, so the inventory would be deciding the
     verdict on its own.
the inventory could not suppress: neither with pytest's real status nor with a dropped one
```

**Sixth-A — the frozen-seed guard is RED against the plant.**
`the frozen-seed guard is red against the planted edit, as it must be`.

**And the tree went back.** `reverted 'seed-credential-swap': …restored byte-for-byte
(sha256 e2aa9706ffca…) and .plant-cluster-defect/ removed`, then `git diff --exit-code`
clean, `git status --porcelain` empty, `--status` → *"no plant is present"*, and
`the tree is byte-for-byte where it started`.

### A.3 Sixth-B — the one step that failed

| step | name | conclusion |
|---|---|---|
| 1–18 | everything above, including all four cells, the inventory control, the RED half of the guard, and the revert | **success** |
| **19** | **The frozen-seed guard is GREEN again** | **failure** — `2 failed, 1 passed in 0.17s` |
| 20 | The 2×2, as one table | *skipped* |
| 21 | The container's own account of the run | success (`if: failure()` diagnosis) |

That step runs **after** the revert, on a tree the step before it had just proved
byte-for-byte clean, so the failure had nothing to do with the plant:

```
assert 'e2aa9706ffca...76bcc173787bf' == '50535d1db0ba...61950cfc07aee'   demo_world.sql
assert 'df3470cb2665...a9817259c2d35' == '198d44ef6e84...d63dcdf66dcc6'   demo_permit.sql
```

Both seed files changed in `eefae1c` and `FROZEN` in `tests/ci/test_demo_seed_is_frozen.py`
was not re-measured in that commit. So the guard was red **with** the plant and red
**without** it, and a guard that fires either way discriminates nothing — sixth-A had
silently stopped being a proof, which is the same failure mode as a skip that reads as a
pass, viewed from the other side.

**Which side was authoritative.** `FROZEN` is a `sha256` *of* those files: a value computed
from a file cannot be authoritative over that file, so the hash is the derived side and the
seed is not. The file's own failure message says a re-baseline is allowed. But
re-baselining a hash to turn a red test green is also the exact shape of the edit this whole
lane exists to refuse, so the re-baseline was gated on a **four-part negative control that
ran before the constants were touched**, written out in full in that module's docstring:

1. `git diff 8e6a195..eefae1c` over both seeds shows **0** changed lines matching
   `signing_credential`, `credential_id` or `digest('mainline-demo/credential/` — out of 650
   changed lines (619 insertions, 31 deletions);
2. `test_the_seed_derives_the_demo_credentials_from_their_names` **passes** at HEAD;
3. `test_credentials.py` under `--crdb=reuse` is **17 tests, 0 failures, 0 errors, 0
   skipped** — including `…_does_not_enrol_the_value_gate_run_used_to_derive`;
4. `demo_world.sql` still enrols **exactly one** signer as
   `digest('mainline-demo/credential/demo.signer','sha256')` (line 124) and one
   countersigner (line 132), and `sha256(b"credsigner")` appears **0** times in the file.

All four came back clean, so the freeze was re-measured to
`e2aa9706…` / `df3470cb…`. Had any one of them failed, the answer was to revert the seed and
leave the hash alone. The superseded pair is kept in that file rather than deleted.

**An independent corroboration of the new baseline, from this very run.** The CI revert
printed `restored byte-for-byte (sha256 e2aa9706ffca…)` — on a Linux runner, from a fresh
`actions/checkout`, with no working tree of anyone's in sight. That is the same value
re-baselined into `FROZEN` from a Windows workstation, which is also the first evidence in
this repository that the `.gitattributes` `* -text` claim behind *"what is committed is what
is applied"* actually holds across the two platforms this project builds on.

### A.4 Why the run published no 2×2 table, and what changed

Step 20 — *"The 2×2, as one table"*, the only step that writes `$GITHUB_STEP_SUMMARY` — has
no `if:`, so when step 19 failed it was **skipped**. The run therefore published **no summary
at all**: a reader who opened it landed at the bottom of a 1,695-line log, on sixty lines of
CockroachDB session output, with `Process completed with exit code 1` as the entire
diagnosis, ~130 lines above. Four cells of a falsifiability proof had passed and no reader
could see it.

Three changes were made, and one deliberate non-change:

* step 19 now brackets pytest, keeps **pytest's own exit status**, and prints a named
  `::error` that separates the two possible causes — a stale baseline, or a reshaped seed —
  and points at the re-baseline procedure and its four-part precondition;
* step 17 (the RED half) now also names that procedure, because the one way *it* goes green
  without the guard being broken is somebody re-baselining `FROZEN` onto a **planted** tree,
  which is the forbidden edit exactly;
* step 20's table is now **read back out of the four JUnit reports** rather than restating
  `HERMETIC_FLOOR` and `CLUSTER_FLOOR`. It previously printed *"GREEN, 7+ executed"* — a
  statement about what the lane would have accepted, not about what it measured. A summary
  that cannot disagree with the run it summarises is decoration. The floors are printed
  beside the measurements so the margin is visible, and the step exits 1 rather than
  inventing a cell if a report it claims to summarise is missing;
* **step 20 still has no `if: always()`, on purpose.** Its heading is a verdict — *"the
  cluster lane is falsifiable"* — and a job that failed has not earned it. Skipping was the
  correct behaviour; the repair is to stop the last step failing, which is what the
  re-baseline does.

Neither floor moved. No cell was restructured. `scripts/ci/plant_cluster_defect.py` was not
touched. No assertion or error message was weakened.

### A.5 What this run settles about §5's local findings

| §5 finding | what CI run 31735341050 shows |
|---|---|
| **1** — unretried `40001` in `test_transitions.py::_seed_permit` | **Did not reproduce.** Cell 1 passed on its first and only attempt, 77 executed, 0 errors. **Not fixed — not observed.** `_seed_permit` still ends in a bare `commit()` with no retry loop, and one clean CI run on a single-node in-memory store is no evidence about a multi-node cluster. |
| **2** — fresh databases partially failing to build from inside a pytest session | **Did not reproduce, and the prediction it carried did not come true.** §5 warned this was *"the most likely reason `cluster-lane-bites` will not reach cell 4 on its first real run"*. In CI **every** database is fresh, in every cell, and both cluster cells skipped exactly **1** — the `jsonschema` skip — against a local baseline of 8 and 11. Cell 1 did not fall below `CLUSTER_FLOOR`. Worth keeping open: it is a nondeterministic defect that a single run cannot refute. |
| **3** — the frozen-seed guard is red at a clean tree, so its "green again" half cannot pass | **CONFIRMED in CI**, and it is the whole of this run's failure. **Discharged** by the re-baseline in §A.3. §5's instruction — that the judgement belonged to the file's owner and not to a worker who noticed the drift while measuring something else — is what routed it here, correctly. |
| **4** — both floors hold exactly, with zero margin | **Confirmed.** 77 against a floor of 77; 7 against a floor of 7, twice. Cell 4 also executed 77, so in CI it would have cleared `CLUSTER_FLOOR` too — but cell 4 is still not held to a floor, because `caught_by` is the stricter check. |
| **5** — the plant harness's hygiene properties | **Confirmed, and for the first time in the way that counts.** §6 recorded that the workflow's `git diff --exit-code` and empty-`git status --porcelain` assertions are CI-only and *"were not exercised"* locally, because that tree was dirty by 52 modified and 42 untracked files. In this run they ran, before and after, on a fresh checkout, and **passed**. That verdict was the only one that counted for them, and it is now in. |

One difference worth naming rather than smoothing over: **cell 4 in CI reproduces the
2026-08-13 reading, not either of §2's local attempts.** All three failures present at once,
with only the one `jsonschema` skip:

```
test_the_admission_is_a_green_this_database_could_have_refused
test_the_deployed_seed_and_the_proof_seed_are_two_different_worlds
test_the_deployed_seed_does_not_enrol_the_value_gate_run_used_to_derive   ← caught_by
```

§8 called that older reading *"plausible as the case where both fresh builds happened to
succeed"*. In CI both fresh builds did succeed, and the reading came back. That is a point
for the older measurement and against the idea that it was mis-transcribed.

### A.6 What this run does not establish, stated rather than left to be assumed

* **One run is not a distribution.** Everything above is `n = 1`. §5 finding 1 was measured
  at 1 red in 4 locally; a single green CI cell does not move that.
* **A single-node, in-memory CockroachDB is not CockroachDB Cloud.** Nothing here exercises
  the `40001 RETRY_SERIALIZABLE` path the deployed demo will meet under contention.
* **Cell 4 carries no executed floor.** Its verdict is the `caught_by` check. If cell 4 ever
  goes red *and* skips most of the subset, the `caught_by` assertion is what must catch it —
  and on §2's local attempt 1 it did exactly that, refusing a red run in which `caught_by`
  had been skipped rather than banking it as a proof.
* **This document reports the run; it did not run it.** The lane must be re-run at the
  re-baselined tree for §A.3 to be closed by CI rather than by a local reading. The local
  reading, taken 2026-08-14 on TRAPPOINT: with the plant applied,
  `2 failed, 1 passed` (rc 1, so sixth-A holds); after `--revert`, **`3 passed in 0.49s`**
  (so sixth-B holds). Both halves of the guard now discriminate, and the guard is now red
  *only* for the file the plant actually edits.

### A.7 Full-suite `--crdb=reuse`, before and after — and why the "after" is not comparable

All figures from `--junitxml`, read off the `<testsuite>` attributes.

| | when | collected | executed | skipped | fail | err | wall |
|---|---|---|---|---|---|---|---|
| **before** | 09:13 | 528 | 527 | 1 | **1** | **0** | 49.2 s |
| **control** — W2's three files reverted to HEAD | 10:05 | 556 | 556 | 0 | 22 | 23 | 220.3 s |
| **after** — W2's three files present | 10:11 | 556 | 546 | 10 | 21 | 13 | 151.3 s |

The tree moved a long way under this measurement, and the movement is **not this worker's**.
Between the "before" run and the others, four files appeared or changed under
`verticals/mainline/apps/demo-api/src/mainline_demo_api/` — `gate_run.py` and
`transitions.py` modified, `retry.py` and `defeaters.py` new — with mtimes of 09:21:26
through 09:25:39, i.e. **during** the first "after" attempt, plus a new
`tests/test_defeaters.py` (+28 collected). W2 wrote none of them.

So attribution was measured rather than asserted, back to back, by the strongest control
available: **run the suite with W2's three files reverted to HEAD, then run it again with
them present.**

```
red with W2 ABSENT but green with W2 PRESENT:  11   (all tests.test_defeaters, a module
                                                     another worker was writing between
                                                     the two runs)
red with W2 PRESENT but green with W2 ABSENT:   0   <- any entry here would be W2's
symmetric difference, excluding test_defeaters: []  <- the failing node-id SETS are IDENTICAL
```

Set equality, not count equality — a count can be satisfied by one test dropping out as
another appears. **W2's delta on the demo-api suite is exactly zero**, which is what a change
confined to `tests/ci/`, `.github/workflows/` and `docs/` should be. The 1-failure "before"
reading remains the honest baseline for this wave; the 21/13 in the "after" column belongs to
work in flight in other workers' files and is recorded here rather than quietly banked.

---

## The local 2×2 of 2026-08-14, preserved in full below

Everything from here down is the lane-controls wave's measurement, unchanged apart from four
dated pointers into §A. It is deeper than §A in every respect that does not require a runner.

---

**Worker:** W4, lane-controls wave. **Measured 2026-08-14 on TRAPPOINT**, working tree
`D:/CoackroachDBxAWS/mainline` at HEAD `538193b`, `.venv/Scripts/python.exe` (pytest 9.1.1),
against the local **CockroachDB CCL v26.2.5** on `127.0.0.1:26257`.

**Every number in this document was read out of a `--junitxml` file that is committed beside
it**, under `evidence/ci/cluster-lane-2x2/`. None was read off a terminal scroll. That is not
a stylistic preference: this suite is I/O-bound and prints nothing for minutes at a time, and
two healthy runs have already been killed by leads who believed they had hung.

The machine-readable form of everything below is
[`evidence/ci/cluster-lane-2x2/summary.json`](../../evidence/ci/cluster-lane-2x2/summary.json),
generated from the XML rather than typed in.

---

## 0. Why this document was rewritten

The previous revision of this file (2026-08-13) reported the same 2×2 as measured. It was
prose only — **no JUnit file, no artefact, nothing a reader could recount.** In the meantime
`.github/workflows/cluster-lane-bites.yml` was found never to have executed at all: it did
not parse, so its only run created zero jobs and lasted 0 s. The lane's central claim had
therefore produced zero evidence in the project's history.

This revision replaces the unbacked readings with measurements that ship their inputs. The
2026-08-13 readings are preserved in §8 rather than deleted, because the convention in this
repository is that a superseded measurement stays visible next to the one that replaced it.

**The headline is not the same as last time.** Cell 3 came back exactly as the lane predicts,
and more strongly than the lane asserts. Cell 4 came back red **twice, for different reasons**,
and on the first attempt it was red in a way the workflow's own assertion would have — and
should have — refused to accept as a proof.

---

## 1. What ran

The subset is the one `cluster-lane-bites.yml` names in `SUBSET`, run with the same argv
modulo `--crdb`:

```
SUB="verticals/mainline/apps/demo-api/tests/test_credentials.py
     verticals/mainline/apps/demo-api/tests/test_gate_run.py
     verticals/mainline/apps/demo-api/tests/test_transitions.py"

.venv/Scripts/python.exe -m pytest $SUB --crdb=<none|reuse> -q -p no:cacheprovider \
    --junitxml=evidence/ci/cluster-lane-2x2/<file>.xml
```

78 tests collect in every cell, in every attempt. The order was the one the brief fixes:
cell 1, cell 2, `--plant seed-credential-swap`, cell 3, cell 4, `--revert`.

---

## 2. The 2×2 as measured

Every row is `collected / executed / skipped / failures / errors / passed`, with `executed`
defined as `collected − skipped`, exactly as the workflow computes it.

| cell | plant | `--crdb` | artefact | collected | executed | skipped | fail | err | passed | rc | wall |
|---|---|---|---|---|---|---|---|---|---|---|---|
| **1** attempt 1 | absent | `reuse` | `junit-absent-cluster.xml` | 78 | 77 | 1 | 0 | **1** | 76 | **1** | 19.67 s |
| **1** attempt 2 | absent | `reuse` | `junit-absent-cluster-attempt2.xml` | 78 | 77 | 1 | 0 | 0 | **77** | 0 | 18.71 s |
| **1** attempt 3 | absent | `reuse` | `junit-absent-cluster-attempt3.xml` | 78 | 77 | 1 | 0 | 0 | **77** | 0 | 19.51 s |
| **1** attempt 4 | absent | `reuse` | `junit-absent-cluster-attempt4.xml` | 78 | 77 | 1 | 0 | 0 | **77** | 0 | 18.60 s |
| **2** | absent | `none` | `junit-absent-hermetic.xml` | 78 | **7** | 71 | 0 | 0 | **7** | 0 | 0.27 s |
| **3** | present | `none` | `junit-planted-hermetic.xml` | 78 | **7** | 71 | 0 | 0 | **7** | 0 | 0.26 s |
| **4** attempt 1 | present | `reuse` | `junit-planted-cluster.xml` | 78 | 67 | **11** | 2 | 2 | 63 | **1** | 121.92 s |
| **4** attempt 2 | present | `reuse` | `junit-planted-cluster-attempt2.xml` | 78 | 70 | **8** | **1** | 0 | 69 | **1** | 145.52 s |

Reduced to the shape the lane argues about:

|  | plant ABSENT | plant PRESENT |
|---|---|---|
| `--crdb=none`  | GREEN — 7 executed, 7 passed, 71 skipped | **GREEN — 7 executed, 7 passed, 71 skipped** |
| `--crdb=reuse` | GREEN — 77 executed, 77 passed (3 of 4 attempts) | **RED — and the test the plant names is what failed (attempt 2)** |

---

## 3. Cell 2 versus cell 3 — the comparison the whole wave turns on

This is the assertion the workflow makes (`executed != before` → fail), and it is the one the
brief singled out. Measured, from the two XML files:

```
cell 2 (plant ABSENT, --crdb=none):  executed = 7
cell 3 (plant PRESENT, --crdb=none): executed = 7
```

**VERDICT: the counts are EQUAL. The assertion holds, and the cell-3 equality must not be
relaxed — there was no pressure to relax it.**

The measurement is stronger than the assertion. The workflow compares two integers; this
worker compared the two **sets of executed node ids**, and they are identical — the same
seven tests by name, all seven passing, in both trees:

```
test_credentials.py::test_every_seed_file_this_suite_names_exists
test_credentials.py::test_gate_run_resolves_the_credentials_it_binds
test_credentials.py::test_no_module_derives_a_credential_id
test_credentials.py::test_the_credentials_are_resolved_before_the_beats_transaction_opens
test_credentials.py::test_the_migrations_directory_this_suite_builds_from_is_present
test_credentials.py::test_the_resolver_reads_the_table_its_refusals_name
test_credentials.py::test_the_seed_files_this_suite_runs_against_are_the_ones_the_deploy_applies
```

`summary.json` records this as `executed_nodeid_sets_identical: true`. A count equality could
in principle be satisfied by one test dropping out and another appearing; the set equality
cannot.

Two of those seven are worth naming, because they are the reason the claim is not trivial.
`test_no_module_derives_a_credential_id` is the AST ratchet — it walks the package for a
derived credential id and passes, because the planted derivation is in a **seed**, not in
code. `test_the_seed_files_this_suite_runs_against_are_the_ones_the_deploy_applies` compares
the deploy's `SEED_FILES` **list** against the suite's, and passes, because the file names did
not change — only the bytes inside one of them did. Two hermetic controls whose names sound
like they should have caught this ran, and could not. That is the sentence the cluster lane
exists to earn.

---

## 4. Cell 4 — red twice, and only once was it a proof

The workflow does not accept "pytest exited non-zero" as a falsifiability proof. It reads the
JUnit and requires that the test the plant's own manifest declares in `caught_by` —

```
verticals/mainline/apps/demo-api/tests/test_credentials.py
    ::test_the_deployed_seed_does_not_enrol_the_value_gate_run_used_to_derive
```

— is among the failures. Both attempts were red. They are not the same result.

### Attempt 2 — the clean proof

**1 failed, 69 passed, 8 skipped; the single failure is exactly `caught_by`, and nothing
else failed or errored.**

```
FAILED test_credentials.py::test_the_deployed_seed_does_not_enrol_the_value_gate_run_used_to_derive
```

The red is unambiguous by construction: there is no other failure it could be attributed to.
The workflow's `caught_by` assertion passes on this run.

### Attempt 1 — red, but the workflow would have refused it, correctly

**2 failed, 2 errored, 11 skipped — and `caught_by` was SKIPPED, not failed.**

| node id | outcome | caused by the plant? |
|---|---|---|
| `test_gate_run.py::test_the_admission_is_a_green_this_database_could_have_refused` | FAIL | **yes** — its own message is *"the deployed seed enrols the value gate_run used to DERIVE, so the divergence this control exists to exhibit does not exist in this database"* |
| `test_gate_run.py::test_the_deployed_seed_and_the_proof_seed_are_two_different_worlds` | FAIL | **yes** — *"the DEPLOYED seed enrols the derived credential id"*, `assert 1 == 0` |
| `test_transitions.py::test_sign_disposition_then_merge_commits` | ERROR | **no** — `40001 RETRY_SERIALIZABLE` on setup, see §5 finding 1 |
| `test_transitions.py::test_materialise_checks_issues_a_receipt_and_moves_the_subject` | ERROR | **no** — same `40001`, same fixture |
| `test_credentials.py::…_used_to_derive` **(`caught_by`)** | **SKIPPED** | n/a — its database did not build, see §5 finding 2 |

So on attempt 1 the lane would have printed *"the cluster lane went red for the wrong
reason"* and exited 1. **That is the design working.** A red cell that is red for an
unrelated reason is not a falsifiability proof, and the lane says so rather than banking it.

**The `caught_by` check is doing real work and must not be relaxed to "non-zero is enough".**
Attempt 1 is the concrete counter-example: a run that was red, that contained two genuine
plant-caused failures, and in which the named control never executed at all. "Non-zero is
enough" would have called that a proof.

---

## 5. Findings

Five things this measurement establishes that were not known before it. None of them is
repaired here — every one lives in a file another worker owns, and the rule that outranks
this document says a fixture you believe is wrong gets reported with evidence and left alone.

### Finding 1 — the subset's cluster cells carry an unretried `40001`, and it is the same defect twice

Cell 1 attempt 1 and both cell-4-attempt-1 errors are the **same** failure:

```
psycopg.errors.SerializationFailure: restart transaction:
  TransactionRetryError: retry txn (RETRY_SERIALIZABLE - failed preemptive refresh)
raised at  test_transitions.py:225  in  _seed_permit  ->  w4_conn.commit()
```

`test_transitions.py::_seed_permit` ends in a bare `w4_conn.commit()` with **no retry loop**.
`conftest._apply_seeds` deliberately calls the deployer's own `Applier`, *"whose loop retries
`40001` with backoff"*; this fixture has no such loop. The platform constraint for this
project names a `40001 RETRY_SERIALIZABLE` retry loop as required, and records that
single-node local Docker rarely triggers it — it triggered here, on a single local node,
**twice in eight subset runs**.

Measured rate in this sitting: **cell 1 was red on 1 of 4 attempts (77 executed each time,
76 passed once, 77 passed three times).**

Consequence for the lane, which W1 should know: cell 1 runs under `set -euo pipefail`, so a
red pytest aborts the step and the whole 2×2 stops before the plant is applied. That is the
correct behaviour — the lane refuses to measure against a dirty specimen — but it means the
bites lane will intermittently abort at cell 1 for a reason that has nothing to do with the
plant, and the answer is a retry loop in `_seed_permit`, **never a relaxed cell 1.**

*Owner: whoever owns `verticals/mainline/apps/demo-api/tests/test_transitions.py`. Not W4.*

### Finding 2 — the plant forces two fresh database builds, and one of the two partially failed both times

The demo-api fixture names its database for a fingerprint over every migration's bytes **and
every seed file's bytes**, so the planted seed builds a new pair of databases
(`w1_credentials_719f1a8d259b`, `w3_demo_api_719f1a8d259b`) rather than reusing the clean
ones. In **both** attempts exactly one of that pair partially failed to build:

| attempt | database that failed | migrations that did not apply | first failure reported |
|---|---|---|---|
| 1 | `w1_credentials_719f1a8d259b` | **160 of 271** | `0066a_one_live_disposition.sql [42P01] relation "mainline.disposition" does not exist` |
| 2 | `w3_demo_api_719f1a8d259b` | **78 of 271** | `0138_trg_cue_prefix_project.sql [42P01] relation "mainline.event_cue_embedding" does not exist` |

The fixture responds by **skipping** the tests that needed that database, with a named reason
— which is why attempt 1 skipped 11 and attempt 2 skipped 8, against a baseline of 1.

**This is not caused by the plant, and it is not caused by the migrations.** Two independent
reasons, one structural and one measured:

- *Structural.* `conftest._apply_chain` applies all 271 migrations **before** any seed is
  applied. The plant edits a seed. Seed content cannot reach the migration phase; it only
  changes the database's name.
- *Measured.* A control was run for this document: the same 271 migrations, through the same
  `discover()` loop with the same per-file autocommit, into throwaway databases in W4's own
  namespace, on a clean tree with no plant present. Result: **271 applied, 0 failed — twice.**
  See [`fresh-migration-build-control.json`](../../evidence/ci/cluster-lane-2x2/fresh-migration-build-control.json).

So the migration set is sound standalone, and fails partially only when built fresh **from
inside a pytest session**, nondeterministically, at a different migration each time. The
clean-seed cells never expose it because they adopt a database built long ago.

This matters well beyond the plant: **in CI every database is fresh, in every cell.** If this
reproduces on a runner, cell 1 will drop below `CLUSTER_FLOOR` and the lane will stop there.
It is the most likely reason `cluster-lane-bites` will not reach cell 4 on its first real run,
and it should be diagnosed before that verdict is read as a fault in the 2×2.

*Owner: whoever owns `verticals/mainline/apps/demo-api/tests/conftest.py`. Not W4.*

### Finding 3 — half of the frozen-seed guard is red all the time, so its "green again" step cannot pass

> **[2026-08-14, W2 — CONFIRMED IN CI AND NOW DISCHARGED. See §A.3.]** This is the whole of
> run `31735341050`'s failure, at its last step, with all four cells green. `FROZEN` has been
> re-measured to `e2aa9706…` / `df3470cb…` after the four-part negative control this finding
> correctly declined to skip. The paragraph below — *"the remedy is not to re-baseline these
> hashes to make my measurement green"* — is what routed the decision to the file's owner
> instead of to a passing worker, and it stands as written.

`cluster-lane-bites.yml` asserts the guard twice — red with the plant, green after the revert
— *"because a guard that is red against the plant proves nothing on its own if it is red all
the time."* Measured, in this sitting:

```
with the plant:   3 failed in 0.39 s
after --revert:   2 failed, 1 passed in 0.53 s      <- NOT green
```

The two that stay red are the hash assertions, and both baselines are stale against the tree
they ship with — including for a file **this plant never touches**:

| file | `FROZEN` records | on disk today (clean, no plant) |
|---|---|---|
| `demo_world.sql` | `50535d1db0babf78…` | `e2aa9706ffca80f2…` |
| `demo_permit.sql` | `198d44ef6e843fa6…` | `df3470cb26659b4b…` |

The half that **does** discriminate is the one designed never to need re-baselining:
`test_the_seed_derives_the_demo_credentials_from_their_names` was **red with the plant and
green without it**, which is exactly the behaviour the lane claims for the whole file.

Consequence: the bites lane's *"The frozen-seed guard is GREEN again"* step will fail on the
current tree, and its *"is RED against this edit"* step proves nothing today, because that
guard is red either way.

**The remedy is not to re-baseline these hashes to make my measurement green.** That file's
own comment says a re-baseline must arrive *"in the same commit"* as the seed change that
caused it, in front of a reviewer, and that judgement belongs to the file's owner and to the
lead who owns the in-flight seed addition — not to the worker who noticed the drift while
measuring something else.

*Owner: W2 (`tests/ci/test_demo_seed_is_frozen.py`). Not W4.*

### Finding 4 — both floors hold exactly, with zero margin

Neither floor was moved. Neither needed to be.

| floor | declared in `cluster-lane-bites.yml` | measured | margin |
|---|---|---|---|
| `HERMETIC_FLOOR` | `7` | 7 (cell 2), 7 (cell 3) | **0** |
| `CLUSTER_FLOOR` | `77` | 77, 77, 77, 77 (cell 1 ×4) | **0** |

Both are satisfied at exactly their declared value, in every attempt. A floor with zero
margin is doing its job — but it is worth stating plainly that **any test in this subset that
starts skipping takes the lane below its floor immediately.** Finding 2 is exactly such an
event: cell 4's attempts executed 67 and 70, both below 77. The workflow does not apply
`CLUSTER_FLOOR` to cell 4 (only to cell 1), so it would not have caught that; the `caught_by`
assertion caught attempt 1 instead, which is the check that matters there.

**Neither floor may fall.** They may rise in a commit that records a measurement above them.

### Finding 5 — the plant harness's safety properties held, twice, verified by hash

The plant was applied and reverted **twice**. Both times:

```
pre-plant   demo_world.sql  sha256 e2aa9706ffca80f269edaa77e1dc8224b26b52ef6c4b666c74076bcc173787bf
planted     demo_world.sql  sha256 21f8f9c2b40051869528a83a02d5a28c3b89d1668fc4492dfa216708baace179
post-revert demo_world.sql  sha256 e2aa9706ffca80f269edaa77e1dc8224b26b52ef6c4b666c74076bcc173787bf   -> BYTE FOR BYTE
```

and after each revert: `--status` → *"no plant is present"* (exit 0), `.plant-cluster-defect/`
removed, the anchor line present exactly once, and the replacement hex string present **zero**
times anywhere in the file. The final state of the tree is recorded in §7.

The `--revert` step was written to run unconditionally in this worker's scripts, with no
`set -e` in the enclosing shell, precisely so that a red cell could not skip it. It did not
need to be exercised that way, but it was available both times.

---

## 6. What could NOT be measured here, stated rather than faked

> **[2026-08-14, W2 — the verdict this section defers to is now in. See §A.2 and §A.5.]** The
> two cleanliness assertions ran in CI run `31735341050`, on a fresh checkout, before and
> after the plant, and **passed**: `git diff --exit-code` clean, `git status --porcelain`
> empty, `--status` → *"no plant is present"*, and the file restored byte-for-byte to
> `sha256 e2aa9706ffca…`. Nothing below is retracted — it was right not to claim them.

**The workflow's cleanliness assertions are CI-only and were not exercised.** The bites lane
brackets the plant with `git diff --exit-code` and an empty `git status --porcelain`, before
and after. This working tree is dirty by a wide margin — **52 modified and 42 untracked files
when this sitting opened, 51 and 42 when it closed** (the difference is other workers editing
the same tree concurrently, not this worker; the counts exclude the `evidence/ci/` directory
created here) — including 493 uncommitted added lines in `demo_world.sql` itself from another
lead's in-flight change. Both assertions would fail here for reasons that have nothing to do
with the plant.

They are therefore **not evaluated in this document, and nothing here should be read as
evidence that they pass.** They will be validated when W1's repaired lane runs on a clean
checkout, and that verdict is the only one that counts for them.

What was measured instead is the strongest local substitute, and it is weaker: the SHA-256 of
the edited file before and after, plus the harness's own `--status`, plus a grep for the
planted string. Those catch a plant that survived in the file. They do **not** catch an
untracked leftover elsewhere in the tree, which is the second of the two ways a plant
survives and is exactly why the workflow uses `git status --porcelain` rather than
`git diff`. That substitution must not be made in the workflow.

Two further limits, for the same reason:

- **`--crdb=reuse` against a long-lived local node is not `--crdb=reuse` against a fresh
  container.** Every clean-seed cell here adopted a cached database. Finding 2 is the
  consequence, and it means cells 1 and 2 as measured here are *easier* than their CI
  equivalents, not harder.
- **The tree moved underneath this measurement.** `test_reads.py` and
  `qa/cluster-known-red.json` were modified by another worker at 04:22 and 04:23, between the
  before and after full-suite runs recorded in §7. The subset this document measures does not
  include `test_reads.py`, and the eight cell artefacts were all written between 04:14 and
  04:30 against a `demo_world.sql` whose hash never changed except while planted — but the
  full-suite delta in §7 is **not** attributable to this worker, and is not claimed as such.

---

## 7. Full-suite `--crdb=reuse`, before and after

Both from `--junitxml`, whole `verticals/mainline/apps/demo-api/tests` directory.

| | collected | executed | skipped | failures | errors | passed | rc | wall |
|---|---|---|---|---|---|---|---|---|
| before (04:12) | 528 | 527 | 1 | 0 | **63** | **464** | 1 | 47.10 s |
| after (04:29) | 528 | 527 | 1 | 1 | **1** | **525** | 1 | 48.58 s |

**This improvement is not this worker's.** W4 changed no code, no test, no fixture, no seed,
no floor and no threshold — the only files written are `docs/ci/cluster-lane-falsifiability.md`
and the contents of `evidence/ci/cluster-lane-2x2/`. The 63 `commit_v2` errors were resolved
by another worker's edit to `test_reads.py` at 04:22, mid-measurement. It is recorded here
because the wave requires a before and an after, and an unattributed 61-test swing in a
shared tree is worth naming rather than quietly banking.

The two remaining reds in the "after" run:

- `test_transitions.py::test_sign_disposition_hands_the_shared_connection_back_in_autocommit`
  — ERROR, the same unretried `40001` as finding 1.
- `test_reads.py::test_the_disposition_carries_the_lattice_and_the_projected_requirements`
  — FAIL, in the module another worker was editing at the time.

The lead's baseline for this wave was **524 / 523 / 1 / 6 / 63 / 454**. The tree has moved
past it in both directions since; the pair above is the honest current reading.

---

## 8. Superseded: the 2026-08-13 readings

Kept, not deleted, per the convention this repository already uses for a measurement that has
been re-taken. These were reported by the CI-runs-the-cluster wave **without artefacts**, and
this document supersedes them:

```
cell 1  77 passed, 1 skipped in 23.08 s
cell 2   7 passed, 71 skipped in 0.60 s
cell 3   7 passed, 71 skipped in 0.93 s
cell 4   3 failed, 74 passed, 1 skipped in 175.44 s
        FAILED test_credentials.py::…_used_to_derive
        FAILED test_gate_run.py::test_the_admission_is_a_green_this_database_could_have_refused
        FAILED test_gate_run.py::test_the_deployed_seed_and_the_proof_seed_are_two_different_worlds
```

What today's re-measurement changes about them:

- **Cells 1, 2 and 3 reproduce.** The executed counts are identical (77 / 7 / 7) and cell 3
  still matches cell 2.
> **[2026-08-14, W2 — the 2026-08-13 cell-4 reading DOES reproduce, in CI. See §A.5.]** Run
> `31735341050` returned `3 failed, 74 passed, 1 skipped`, all three failures at once with
> only the `jsonschema` skip — exactly the reading below. The hypothesis in the second bullet
> is the right one: in CI both fresh builds succeeded.

- **Cell 4 does not reproduce as stated.** The 2026-08-13 reading has all three failures
  present at once with only the one jsonschema skip; neither attempt today reproduced that.
  Attempt 1 skipped `caught_by` entirely; attempt 2 failed `caught_by` alone and skipped the
  two `test_gate_run.py` controls. Finding 2 explains why the difference is possible, and the
  older reading is plausible as the case where **both** fresh builds happened to succeed.
- **The old §5 claim that the frozen-seed guard returns `3 passed in 0.29 s` after the revert
  is no longer true** — it is `2 failed, 1 passed`. See finding 3.

---

## 9. The plant, and the argument the 2×2 makes — unchanged, and re-verified today

`scripts/ci/plant_cluster_defect.py --plant seed-credential-swap` replaces one line of
`verticals/mainline/db/seeds/demo/demo_world.sql`, at line 124:

```sql
-    digest('mainline-demo/credential/demo.signer', 'sha256'),
+    decode('<sha256 of b"credsigner">', 'hex'),
```

This is not an invented defect; it is the **reverted** one. `gate_run` once bound
`sha256(b"credsigner")` as `signer_credential_id` while the deployed seed enrolled
`digest('mainline-demo/credential/demo.signer','sha256')`, and
`mainline.disposition.signer_credential_id` is a foreign key onto
`mainline.signing_credential (credential_id)` — so beat 4 failed `23503` against the database
that ships while the suite was green. A worker sent to fix it edited **the seed** to enrol the
constant the application derived, making the SEED match the CODE. Three negative controls
caught it. The database owns `credential_id`; the code reads it.

The replacement is **derived** in the harness (`hashlib.sha256(b"credsigner").hexdigest()`),
never written out as a literal — a second copy of a 32-byte constant is the defect class this
area of the repository keeps closing.

**The `transitions.py` reversion remains the wrong plant** and must not be added to the
catalogue: `test_no_module_derives_a_credential_id` is an AST walk that catches it statically
under `--crdb=none`. §3 confirms that ratchet executed and passed in both hermetic cells, so
it would indeed have gone red on a code plant and collapsed the argument into *"we planted
something both lanes can see."*

The harness's hygiene properties — snapshot-and-hash before touching the file, refuse to plant
over a plant, refuse an anchor matching zero or more than one line, refuse to revert a file
that changed while planted, re-hash after restoring, remove the snapshot directory, and never
use `git checkout --` (which restores from the index and would discard another lead's 493
uncommitted lines in this very file) — were exercised across two plant/revert cycles today and
held. Finding 5 records the hashes.

---

## 10. What a reader should take from this

1. **The hermetic lane provably cannot see this defect.** Cells 2 and 3 executed the same seven
   tests, by name, and all seven passed in both. Two hermetic controls whose names suggest they
   should have caught it ran and could not.
2. **The cluster lane does see it.** Cell 4 attempt 2 failed exactly one test, and it is the
   one the plant's own manifest names.
3. **The lane's refusal to accept an ambiguous red is not decoration.** Attempt 1 was red with
   two genuine plant-caused failures, and the workflow would still have refused it, because the
   named control had been skipped. Do not weaken that check to "non-zero is enough".
4. **Two defects stand between this lane and a green run in CI**, and neither is in a file this
   worker owns: an unretried `40001` in `test_transitions.py::_seed_permit` (finding 1) and a
   fresh-database build that partially fails from inside a pytest session (finding 2).
5. **One assertion in the lane cannot pass on the current tree** — the frozen-seed guard's
   "green again" half, because its two recorded hashes are stale (finding 3).
   **[2026-08-14, W2: fixed. The hashes were re-measured after the four-part negative
   control in §A.3; the guard is now `3 passed` at a clean tree and still red against the
   plant.]**
6. **Nothing was moved to obtain any of the above.** No floor, no ceiling, no fixture, no seed,
   no expected value. Where a control disagreed with the tree, the disagreement is written down
   above and the control was left alone.
