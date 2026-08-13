<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: Apache-2.0
-->

# LANE-CONTROLS — the plan

**Lead:** lane-controls. **Date:** 2026-08-14. **Tree:** `D:/CoackroachDBxAWS/mainline`,
branch `master`, HEAD `e944407`.

---

## 0. THE RULE THAT OUTRANKS EVERYTHING IN THIS DOCUMENT

A worker was once caught editing `demo_world.sql` to enrol a DERIVED credential id, so that
the SEED matched the CODE and a red test went green. Three negative controls caught it.

**When a test and the code disagree, never move whichever side is easier. Ask which side is
AUTHORITATIVE.** Changing a seed, fixture, ceiling, threshold, floor or expected value to
obtain a green converts a real defect into a permanent invisible one. If you believe a
fixture is wrong, say so in `still_broken` with evidence and leave it alone.

Applied to this lane specifically, the following edits are **forbidden outright**, in every
circumstance, regardless of what turns green:

| forbidden edit | why |
|---|---|
| lowering `COLLECTED_FLOOR`, `HERMETIC_FLOOR`, `CLUSTER_FLOOR`, `floor.min_executed` | each is a floor measured against a real run; lowering one is how a lane that ran nothing reports success |
| raising `floor.max_skipped` | a skip is indistinguishable from a pass on a dashboard; that is the whole defect this wave exists to end |
| deleting a `nodeids` entry from `qa/cluster-known-red.json` | the list is a CEILING; entries leave only in the commit that FIXES them |
| relaxing cell 3 of the 2×2 (`executed != before`) | if the plant is hermetically visible the answer is a DIFFERENT PLANT, never a looser assertion |
| relaxing cell 4's `caught_by` check to "non-zero is enough" | a red for an unrelated reason is not a falsifiability proof |
| `continue-on-error`, `|| true`, `-k`, `--deselect`, `xfail`, or a step-level `if:` that skips an assertion | banned repository-wide |
| moving the bites lane's artefacts INTO the checkout | the final `git status --porcelain` emptiness assertion is what proves the plant did not survive; it only works if nothing else writes into the tree |
| replacing `git status --porcelain` with `git diff` in the revert step | `git diff` cannot see an untracked leftover, which is one of the two ways a plant survives |

---

## 1. BASELINE — measured by this lead, from `--junitxml`, not from a terminal scroll

### 1.1 The suite, local, against the real cluster

```
.venv/Scripts/python.exe -m pytest verticals/mainline/apps/demo-api/tests \
    --crdb=reuse -q -p no:cacheprovider --junitxml=<report>
```

Working tree = HEAD `e944407` **plus uncommitted work** (46 modified files, 20+ untracked).
CockroachDB v26.2.5 at `127.0.0.1:26257`.

| measure | value |
|---|---|
| collected | **524** |
| executed | **523** |
| skipped | **1** |
| failures | **6** |
| errors | **63** |
| **passed** | **454** |
| wall time | 46.24 s |

The 63 errors are one cause, and the cause **is `commit_v2`**, measured:

> `KeyError: "'commit_v2' is not an identifier the deployed demo seed produces…"`, raised in
> the `payloads` fixture during SETUP — which is why they are errors and not failures.

The 6 failures: 4 in `test_response_contract.py` (the ceiling cascade), 1 in `test_reads.py`
(`assert [] == [0, 1]` — the ledger range read returns no leaves), 1 in
`test_seed_covers_every_console_resource.py::…[silence]`.

### 1.2 `scripts/ci/cluster_lane_report.py` against that JUnit — its first execution ever

```
inventory: 64 known, 64 still failing, 0 now passing, 3 declared unstable, 5 NEW
```

The five NEW are the four `test_response_contract.py` ceiling failures and the
`test_seed_covers_every_console_resource.py[silence]` failure.

**This is the single most important number in the baseline: 64 known, 64 still failing, 0 now
passing.** The inventory's node-id list is ACCURATE against the tree. Only its *prose* is
stale. See ruling R5.

### 1.3 CI at the clean checkout of HEAD `e944407` — the real verdicts

| run | lane | verdict | where |
|---|---|---|---|
| [31720235677](https://github.com/Shaugato/mainline/actions/runs/31720235677) | `cluster-tests` | **FAILURE, 34 s** | step *"Collection must cost a second, not a container"*, `exit code 2`, **and no diagnostic whatsoever** |
| [31720234309](https://github.com/Shaugato/mainline/actions/runs/31720234309) | `cluster-lane-bites` | **INVALID WORKFLOW FILE — 0 s, zero jobs, NEVER EXECUTED** | run is named by its file path, not by its `name:` key |
| [31720235703](https://github.com/Shaugato/mainline/actions/runs/31720235703) | `ci` | **FAILURE, 30 s** | `actionlint` red; `every checker this lane invokes exists` red; `PL-2` red-by-design; CI summary: *"11 lane(s) did not pass"* |

**Neither new lane has produced a single measurement.** The 2×2 that is supposed to make the
cluster lane mean something has never run once, in the project's history.

---

## 2. RULINGS — decided on the merits, in writing, BEFORE any worker acts

### R1 — the 2×2 lane has never executed, and `actionlint` already named why

`actionlint`, a control this repository already runs on every push, reported at HEAD:

```
.github/workflows/cluster-lane-bites.yml:95:16: context "runner" is not allowed here.
  available contexts are "github", "inputs", "matrix", "needs", "secrets", "strategy", "vars"
   95 |      ART: ${{ runner.temp }}
```

`runner` is available in `jobs.<id>.steps.*.env` and **not** in `jobs.<id>.env`. GitHub
rejects the file at parse time, which is why the run has zero jobs and a 0 s duration.

**RULING.** Repair by publishing `ART` from the plain environment variable `$RUNNER_TEMP`
inside an early `run:` step via `$GITHUB_ENV`. `$RUNNER_TEMP` needs no expression context and
resolves to the identical directory. **The out-of-tree property is load-bearing and must be
preserved byte-for-byte**: the job's final assertion is that `git status --porcelain` is
EMPTY, which is the strongest available statement that the plant did not survive precisely
because it catches an untracked leftover as well as a modified file. Relocating the four
JUnit reports and the doctored inventory into the checkout to dodge the context rule would
silently destroy that assertion. Do not do it.

Also fix the four `SC2153` shellcheck findings (the `subset` array is a case-variant of
`SUBSET`) by renaming the local array — `actionlint` is a gate and `continue-on-error` is
banned, so the lane cannot land while it is red.

**Process note for `docs/CI-STATE.md`:** actionlint caught this correctly and the file was
pushed anyway. The control worked; the workflow around it did not.

### R2 — `cluster-tests.yml`'s red is CORRECT; its SILENCE is the defect

Root cause of `exit code 2`, established by reading the committed tree:

```
$ git show e944407:verticals/mainline/apps/demo-api/tests/test_response_contract.py | sed -n 78p
from mainline_demo_api import app, db, logbudget, ratelimit, static_site
```

`logbudget.py`, `ratelimit.py` and `credentials.py` are **on disk but untracked** — they do
not exist at `e944407`. Collection raises `ImportError`; pytest exits 2.

The lane's assertion was right: the suite did not collect. But the step is
`set -euo pipefail`, so the shell aborts **on the pytest line**, and `tail -n 20
collected.txt` — the only thing that would have said *why* — is unreachable. The lane failed
with the words `Process completed with exit code 2` and nothing else.

**RULING.** Bracket **only** the pytest call with `set +e`, capture `rc`, restore `set -e`,
print `tail -n 40 collected.txt` when `rc` is non-zero, then `exit "$rc"`. This is the idiom
the very next step in the same file already uses for `--pytest-rc`. It strictly ADDS
diagnosis and adds **no** tolerance: the step still exits with pytest's status. This is not a
relaxation and must not be turned into one.

### R3 — HEAD is not a self-consistent tree, and that is why every new job is red

`e944407` committed **four** files (`ci.yml`, the two cluster workflows,
`test_response_contract.py`) and **none** of the files those four invoke or import:

| path | on disk | tracked at HEAD | needed by |
|---|---|---|---|
| `scripts/ci/cluster_lane_report.py` | yes | **no** | `cluster-tests.yml`, `cluster-lane-bites.yml` |
| `scripts/ci/plant_cluster_defect.py` | yes | **no** | `cluster-lane-bites.yml` |
| `qa/cluster-known-red.json` | yes | **no** | both lanes |
| `tests/ci/test_demo_seed_is_frozen.py` | yes | **no** | `cluster-lane-bites.yml` (assertion 6) |
| `scripts/qa/skip_ratchet.py` | yes | **no** | `ci.yml` |
| `qa/skip-ratchet.json`, `qa/ci-skip-census.json` | yes | **no** | `ci.yml` |
| `scripts/qa/check_pytest_lanes.py` | **ABSENT — never written** | no | `ci.yml` |
| `…/mainline_demo_api/{logbudget,ratelimit,credentials}.py` | yes | **no** | committed `test_response_contract.py` |

The commit message says the two workflows *"were written by the last wave and never
committed, so the lane it was dispatched to build has still never run."* The same defect was
then repeated one level down, on that lane's own dependencies.

**RULING.** This lane commits **only the lane-owned dependencies** — rows 1–7 above. The
demo-api source modules and test files in row 8 belong to the suite-green lead; this lead
RECORDS the finding and hands it over, and does not commit another lead's source.
Consequence, accepted deliberately: **`cluster-tests.yml`'s collection step stays RED until
row 8 lands.** That is the lane correctly reporting a real defect in the tree, which is what
it is for. Do not work around it, do not `-k` past it, do not stub the imports.

### R4 — `COLLECTED_FLOOR` may NOT be raised from a dirty-tree measurement

I measure 524 collected locally. CI at the clean checkout cannot collect **at all**. A floor
is a claim about what CI checks out, not about what happens to be on a developer's disk.

**RULING.** `COLLECTED_FLOOR` stays at **445**. It may be raised only in the same commit that
records a clean-checkout measurement above it. Lowering it is forbidden in all circumstances,
including the circumstance where the suite legitimately shrinks — that case is a conversation,
not an edit.

### R5 — the inventory's node-id list is CORRECT; only its PROSE is stale

Measured (§1.2): **64 known, 64 still failing, 0 now passing.** Every id the inventory names
still fails. But the group's `cause` field says `KeyError: "'cr_id' is not an identifier…"`
and the real message is `KeyError: "'commit_v2' is not an identifier…"`.

**RULING.** A `cause` field is a **description of an observation**, not an authoritative
expectation that anything is checked against. Correcting it against a fresh measurement is
therefore *not* moving an authoritative value to match a derived one — it is repairing a
record that has gone stale against its own tree, which is the defect, not the fix.

Three conditions bind that permission:

1. the correction must be **re-measured**, not inferred from this document;
2. the superseded text must be **preserved in-file**, per the convention the file's own
   `the_tree_moved_while_this_was_measured` block already establishes;
3. **the `nodeids` list may not be touched.** It is a CEILING. Entries leave it only in the
   commit that FIXES them, and that commit belongs to the suite-green lead. If they fix
   `commit_v2` and the 63 pass, `cluster_lane_report.py`'s CEILING check will fail the lane
   and demand the deletion by name — that is the design working, not a problem to pre-empt.

Coordination with the suite-green lead is mandatory and is recorded in W5's brief.

### R6 — *"Both properties are exercised by controls"* is FALSE; make it true, do not delete it

`cluster-tests.yml` asserts, of `scripts/ci/cluster_lane_report.py`:

> *"Both properties are exercised by controls; see that file."*

Verified by search: `cluster_lane_report` is named by two workflows and three documents and
by **no test**. "That file" contains no controls. The sentence is false today.

**RULING.** Write real hermetic unit controls **and** correct the sentence to point at the
file that actually holds them. Deleting the claim is the cheaper option and it is refused:
the property is load-bearing enough that the repository was willing to assert it, so it is
load-bearing enough to test.

**The controls MUST include a NEGATIVE control, and this is the most valuable one missing.**
I verified by construction that the report exits **0** on a synthetic green run against an
empty inventory:

```
cluster lane: 445 collected, 445 executed, 0 skipped, 0 failed, 0 errored
inventory: 0 known, 0 still failing, 0 now passing, 0 declared unstable, 0 NEW
EXIT=0
```

Every assertion this repository currently makes about that program is of the form *"it must
exit non-zero"*. A program hard-wired to `return 1` would satisfy all of them — and would
make `cluster-tests.yml` permanently, unfalsifiably red, which is the mirror image of the
green that cannot fail and is just as useless. A control suite that cannot discriminate in
**both** directions is not a control suite.

### R7 — item (e) of the brief is partly stale; the honest split is the part still missing

`ci.yml`'s tally is no longer `9240/13`. At `e944407` it was rewritten to
`15 / 9824 / 9839`, with a second reading three hours later of `15 / 9884 / 9899`, and the
`13 / 9240 / 9253` pair **kept in place and explicitly labelled superseded** — which is the
correct treatment and must not be undone.

What is still missing is the thing this lane actually publishes: **the demo-api suite's own
pass/skip split**, hermetic versus cluster, which no document states. Measured by this lead
for the cluster side (§1.1); the hermetic side and the delta are W5's.

### R8 — the digest pin is INERT in both new lanes, honestly

Both lanes resolve the image digest and assert it only `if [ -n "${EXPECTED}" ]`, where
`EXPECTED` is `vars.CRDB_IMAGE_DIGEST` — **which is unset**. The lanes say so out loud
(`::notice::CRDB_IMAGE_DIGEST is unset; the digest is recorded but not asserted`), so this is
declared, not hidden, and the design — assert the moment somebody records the real hash
rather than commit a fabricated one — is right.

**RULING.** Keep the mechanism. But a control that cannot fail today is a control that cannot
fail today, in this lead's own lane, and it goes on the CI-STATE.md inert list with the exact
condition that would activate it. Naming your own lane's soft spot is the price of naming
everybody else's.

---

## 3. WHAT "DONE" MEANS FOR THIS LANE

1. `cluster-lane-bites` **parses, starts, and reports a real verdict** — any verdict.
2. `cluster-tests` fails **legibly** or passes; never again `exit code 2` with no text.
3. `cluster_lane_report.py` has controls that can fail **in both directions**, and the
   sentence in `cluster-tests.yml` points at them.
4. The 2×2's discrimination is **measured**, not asserted — in particular the plant-present /
   hermetic cell, which must execute the same count as plant-absent.
5. `qa/cluster-known-red.json` describes the tree it ships with.
6. Every lane whose green cannot fail is **named** in `docs/CI-STATE.md`, including ours.

---

## 4. THE SIX WORKERS

Paths are literally enumerated and disjoint. **No worker may edit a path owned by another.**
If your work seems to require it, stop and report it — do not reach across.

| # | worker | owns |
|---|---|---|
| W1 | make the 2×2 parse and run | `.github/workflows/cluster-lane-bites.yml` |
| W2 | make `cluster-tests` diagnose; land the lane's dependencies | `.github/workflows/cluster-tests.yml`, `scripts/ci/cluster_lane_report.py`, `scripts/ci/plant_cluster_defect.py`, `tests/ci/test_demo_seed_is_frozen.py` |
| W3 | controls for the report, in both directions | `tests/ci/test_cluster_lane_report.py`, `tests/ci/test_plant_cluster_defect.py` |
| W4 | run the 2×2 locally; produce the discrimination evidence | `docs/ci/cluster-lane-falsifiability.md`, `evidence/ci/cluster-lane-2x2/` |
| W5 | unstale the inventory; publish the honest split | `qa/cluster-known-red.json`, `docs/ci/demo-suite-split.md` |
| W6 | the two missing checkers; the vacuity sweep | `scripts/qa/check_pytest_lanes.py`, `scripts/qa/skip_ratchet.py`, `qa/skip-ratchet.json`, `qa/ci-skip-census.json`, `docs/CI-STATE.md` |

Dependency order: **W1, W2, W6-part-1 in parallel → W3, W4, W5 → W6-part-2 (the sweep).**

Every worker reports full-suite `--crdb=reuse` numbers **before and after**, taken from
`--junitxml`, against this lead's baseline of §1.1: **524 / 523 / 1 / 6 / 63 / 454**. A fix
that breaks a neighbour is worse than the defect.

---

## 5. THE BRIEFS

### W1 — make the 2×2 parse, and let it run for the first time

**Owns exactly:** `.github/workflows/cluster-lane-bites.yml`

`cluster-lane-bites.yml` has **never executed**. Run
[31720234309](https://github.com/Shaugato/mainline/actions/runs/31720234309) at HEAD `e944407`
lasted 0 s, created zero jobs, and is titled by its file path rather than its `name:` key —
GitHub's signature for a workflow it refused to parse. `actionlint`, already running in
`ci.yml`, named the cause exactly: line 95, `ART: ${{ runner.temp }}`, where the `runner`
context is unavailable because that `env:` is job-level, not step-level.

Fix it by publishing `ART` from the plain shell variable `$RUNNER_TEMP` inside an early
`run:` step via `$GITHUB_ENV`. `$RUNNER_TEMP` needs no expression context and names the same
directory. Then fix the four `SC2153` shellcheck findings by renaming the local `subset`
array (it is a case-variant of `SUBSET`) — `actionlint` is a hard gate, `continue-on-error`
is banned, and the lane cannot land while it is red. Verify with a real `actionlint` run if
you can obtain the binary; otherwise verify by pushing and reading the `ci` lane's
`actionlint` job, and do not declare success from a local YAML parse — PyYAML accepted this
file happily, which is precisely why the bug shipped.

**The out-of-tree property is load-bearing.** The job's last act asserts `git status
--porcelain` is EMPTY, which is the strongest available statement that the planted defect did
not survive, because it catches an untracked leftover as well as a modified file. Four JUnit
reports and a doctored inventory written into the checkout would each be such a leftover. Do
not relocate artefacts into the tree to dodge the context rule; do not weaken that final
assertion to `git diff`, which cannot see untracked files.

Change nothing else in this file. In particular do not touch `HERMETIC_FLOOR`,
`CLUSTER_FLOOR`, the cell-3 equality, or cell 4's `caught_by` check — W4 is measuring those
and may hand you a re-measured number with evidence. **NO SHORTCUTS: when a test and the code
disagree, ask which side is authoritative; never move a floor, ceiling, fixture or expected
value to obtain a green. If you believe one is wrong, say so with evidence and leave it
alone.** Report the workflow's first real verdict, whatever colour it is — a red 2×2 that ran
is worth more than a green one that did not.

**Done when:** `cluster-lane-bites` appears in `gh run list` with a real job, a real duration
and a real conclusion, and `ci`'s `actionlint` job is green.

---

### W2 — make `cluster-tests` say why, and land the files it invokes

**Owns exactly:** `.github/workflows/cluster-tests.yml`, `scripts/ci/cluster_lane_report.py`,
`scripts/ci/plant_cluster_defect.py`, `tests/ci/test_demo_seed_is_frozen.py`

Two separate defects, both measured.

**(a) The lane fails without diagnosis.** Run
[31720235677](https://github.com/Shaugato/mainline/actions/runs/31720235677) died at *"Collection
must cost a second, not a container"* with `Process completed with exit code 2` and no other
text. The step is `set -euo pipefail`, so the shell aborts **on the pytest line**, and
`tail -n 20 collected.txt` — the only thing that would have said why — is unreachable. Repair:
bracket **only** the pytest call with `set +e`, capture `rc`, restore `set -e`, print
`tail -n 40 collected.txt` when `rc` is non-zero, then `exit "$rc"`. This is the idiom the
very next step in the same file already uses. It adds diagnosis and **no** tolerance. Do not
turn it into tolerance; the step must still exit with pytest's status.

**(b) The lane invokes files that do not exist at HEAD.** `scripts/ci/cluster_lane_report.py`,
`scripts/ci/plant_cluster_defect.py`, `qa/cluster-known-red.json` and
`tests/ci/test_demo_seed_is_frozen.py` are on disk and **untracked**. Commit the three you own
(W5 owns the inventory). Verify each carries its SPDX header first — `check_reuse.py` is a
gate. Do not modify their logic; they are correct. I ran `cluster_lane_report.py` against a
real JUnit and it classified 64 known / 64 still failing / 0 now passing / 3 unstable / 5 NEW,
and `plant_cluster_defect.py --status` answers correctly.

**Do not attempt to make the collection step green.** Its exit 2 has a real cause: the
committed `test_response_contract.py:78` imports `logbudget` and `ratelimit`, which are
untracked demo-api source modules owned by the suite-green lead. That is a genuine defect in
the tree and the lane is right to refuse. Record it and hand it over. `COLLECTED_FLOOR` stays
at **445** — I measure 524 locally but the clean checkout collects nothing, and a floor is a
claim about what CI checks out.

**NO SHORTCUTS: when a test and the code disagree, ask which side is authoritative; never
move a floor, ceiling, fixture or expected value to obtain a green.**

**Done when:** a failing `cluster-tests` run prints the collection error text in its log, the
three files are tracked, and full-suite `--crdb=reuse` is unchanged from 524/523/1/6/63/454.

---

### W3 — give the report controls that can fail, in BOTH directions

**Owns exactly:** `tests/ci/test_cluster_lane_report.py` (new),
`tests/ci/test_plant_cluster_defect.py` (new)

`cluster-tests.yml` asserts of `scripts/ci/cluster_lane_report.py`: *"Both properties are
exercised by controls; see that file."* I searched: that program is named by two workflows and
three documents and by **no test**. The sentence is false. Make it true.

Write hermetic tests (`--crdb=none`, no Docker, no network) that build synthetic JUnit XML and
synthetic inventories in `tmp_path` and call `main([...])` directly, asserting on the returned
exit code. Cover at minimum: **(1)** `--pytest-rc N` non-zero is final — a run in which every
failing node id is inventoried still exits `N`; **(2)** the dropped-status refusal — JUnit
records failures while `--pytest-rc 0` is claimed, and the program refuses; **(3)** the floor —
`executed < min_executed` fails even with `--pytest-rc 0`; **(4)** the skip ceiling; **(5)** the
CEILING — an inventoried node id that PASSED is a hard failure; **(6)** an `unstable` entry that
passed is a notice, not a failure; **(7)** every `Refusal` path — bad schema, missing `cause`,
an id in two groups, an id both known and unstable, `runs_failed >= runs_observed`, an
unresolvable `classname`; **(8)** a `Refusal` never exits 0.

**The most important test is the NEGATIVE control, and nothing in this repository has one.**
Every existing assertion about this program is *"it must exit non-zero"*. A program hard-wired
to `return 1` satisfies all of them, and would make `cluster-tests.yml` permanently
unfalsifiably red — the mirror image of a green that cannot fail, and just as useless. I
verified by construction that the program exits **0** on a green run against an empty
inventory, so the control is achievable: write it. A control suite that cannot discriminate in
both directions is not a control suite.

For `plant_cluster_defect.py`, test at least: `--plant` then `--revert` restores bytes
exactly; `--plant` twice refuses; `--revert` with no manifest refuses; a missing or duplicated
anchor refuses. Use a temp copy of the seed via `--root`; **never plant against the real
working tree in a test.**

**NO SHORTCUTS: when a test and the code disagree, ask which side is AUTHORITATIVE. If a
control you write goes red, that is a finding about `cluster_lane_report.py` — report it as one
in `still_broken`. Do not edit the program to match your test, and do not weaken your test to
match the program.**

**Done when:** both files pass under `--crdb=none`, at least one test proves exit 0 is
reachable, and deliberately breaking one line of `cluster_lane_report.py` turns at least three
of them red (state which line you tried and revert it).

---

### W4 — measure whether the 2×2 actually discriminates

**Owns exactly:** `docs/ci/cluster-lane-falsifiability.md`,
`evidence/ci/cluster-lane-2x2/` (new directory)

The 2×2 has never run. Its claim cannot be evaluated from CI, so **measure it here**, on this
box, against the local CockroachDB v26.2.5 at `127.0.0.1:26257`. Run all four cells manually
with `.venv/Scripts/python.exe -m pytest` over the same subset the workflow uses —
`test_credentials.py test_gate_run.py test_transitions.py` — writing a `--junitxml` for each
into `evidence/ci/cluster-lane-2x2/`, and take every number from the XML, never from a scroll.

Order: cell 1 (`--crdb=reuse`, no plant), cell 2 (`--crdb=none`, no plant), then
`scripts/ci/plant_cluster_defect.py --plant seed-credential-swap`, then cell 3
(`--crdb=none`), cell 4 (`--crdb=reuse`), then `--revert` **without fail** — the revert is
mandatory and its own assertions must pass. I verified the anchor exists exactly once in the
current `demo_world.sql` and that `--status` reports no plant, so the plant will apply.

**The interesting cell is 3, plant-present / hermetic.** It must execute exactly the number
cell 2 executed. That is the whole argument: it says the hermetic lane provably could not have
seen the defect. **If cell 3 comes back RED or with a different count, DO NOT relax the
assertion.** It means the plant is visible without a database, the cluster lane is redundant
for that defect, and the answer is a different plant. Report that outcome plainly — it is a
finding, not a failure of your task.

Also check cell 4 for the sharper question the workflow already asks: the plant's own manifest
declares `caught_by`, and that test must be among the failures. Verify it is, and verify by
inspection that no *other* subset test fails for an unrelated reason, which would make the
red ambiguous.

Note honestly in your write-up that the local tree is dirty (46 modified files) and that the
workflow's `git status --porcelain` cleanliness assertions cannot be exercised locally — they
are CI-only and will be validated when W1's fixed lane runs. Do not fake them.

**NO SHORTCUTS: never move a fixture, floor or expected value to obtain a green.** If
`HERMETIC_FLOOR` (7) or `CLUSTER_FLOOR` (77) no longer matches, report the measured numbers and
the reason; a floor may RISE with evidence, and may never fall to meet a disappointing run.

**Done when:** four JUnit files exist, the doc states each cell's executed/passed/failed from
the XML, cell 2 and cell 3 counts are compared explicitly, and `--status` reports no plant.

---

### W5 — unstale the inventory against its own tree, and publish the honest split

**Owns exactly:** `qa/cluster-known-red.json`, `docs/ci/demo-suite-split.md` (new)

Two jobs.

**(a) The inventory's PROSE is stale; its node-id LIST is not.** I measured this: running
`cluster_lane_report.py` against a real cluster-backed JUnit gave **64 known, 64 still
failing, 0 now passing, 3 declared unstable, 5 NEW**. Every id the file names still fails. But
the 63-entry group's `cause` reads `KeyError: "'cr_id' is not an identifier…"` and the real
message, measured, is `KeyError: "'commit_v2' is not an identifier the deployed demo seed
produces…"`. The `cr_id` cause was resolved by an earlier worker seeding a change-request row;
the fixture then moved to the next missing subject.

A `cause` field is a **description of an observation**, not an expectation anything is checked
against, so correcting it is not moving an authoritative value to match a derived one — it is
repairing a record that has gone stale against its own tree. Three conditions bind that: (i)
**re-measure it yourself**, do not copy the string from this document; (ii) **preserve the
superseded text in-file**, as the file's own `the_tree_moved_while_this_was_measured` block
already does; (iii) **do not touch `nodeids`.**

That list is a CEILING. Entries leave it only in the commit that FIXES them, and that commit
belongs to the **suite-green lead**. Coordinate with them before you write: if they remove the
63 in their fix, your job is only the prose and the `measured` block. If they have not, leave
all 64 in place. Adding an id is forbidden — the 5 NEW belong to the ceiling-cascade and
seed-coverage leads and must stay NEW so their owners see them.

**(b) Publish the split.** `ci.yml`'s tally is no longer `9240/13` — it was rewritten at
`e944407` to `15/9824/9839` with a second reading of `15/9884/9899`, the old pair kept and
labelled superseded, which is correct and must not be undone. What no document states is the
**demo-api suite's own** pass/skip split. Measure both sides yourself from `--junitxml`:
`--crdb=none` and `--crdb=reuse`, same paths, and write the delta. My cluster-side baseline is
**524 collected, 523 executed, 1 skipped, 6 failed, 63 errors, 454 passed**; the one skip is
`test_gate_run.py`'s jsonschema skip and has nothing to do with the database. Say plainly how
many tests the hermetic lane skips and what fraction of the suite that is — that number is the
reason this whole lane exists.

**NO SHORTCUTS: never move an authoritative value to match a derived one. Never lower
`floor.min_executed` or raise `floor.max_skipped`.**

**Done when:** the inventory's cause matches a measurement you took, `nodeids` is unchanged
except by the suite-green lead's own fix, and the split doc carries both numbers with the
commands that produced them.

---

### W6 — write the two missing checkers, then sweep for greens that cannot fail

**Owns exactly:** `scripts/qa/check_pytest_lanes.py` (new),
`scripts/qa/skip_ratchet.py`, `qa/skip-ratchet.json`, `qa/ci-skip-census.json`,
`docs/CI-STATE.md`

**Part 1 — the two checkers `ci.yml` invokes and cannot find.** `ci.yml`'s own
checker-registry job went red at HEAD naming them: `scripts/qa/skip_ratchet.py` is on disk but
**untracked**, and `scripts/qa/check_pytest_lanes.py` **does not exist at all**. Commit the
first (I ran it: it passes, `unlanded total 730 against a ceiling of 730`) along with its two
JSON inputs. Then write the second to the contract `ci.yml` states for it: *every pytest step
in `.github/workflows/` declares which side of the cluster line it is on*, via the
`# trappoint:pytest-lane=hermetic|cluster` comment marker. Read the workflow files as **raw
text** — PyYAML discards comments and these files are 60% comment by volume, which `ci.yml`
already warns about. Measure the current state before you write the ceiling: there are 12
markers today. The ceiling is whatever you measure, and it may only fall. A checker whose
ceiling is set above the current count refuses nothing and is the exact defect this task
exists to end.

**Part 2 — the sweep.** Find every lane whose green cannot fail and name it in
`docs/CI-STATE.md` with the condition that would make it falsifiable. Start from what I
already found and verify each yourself: **(i)** `vars.CRDB_IMAGE_DIGEST` is unset, so the
digest assertion in **both** new cluster lanes is inert today — it is declared honestly
in-file, and it still belongs on the list, because naming your own lane's soft spot is the
price of naming everybody else's; **(ii)** `cluster-lane-bites` produced a green-looking
absence for a whole day by not parsing at all — a lane that fails to start is not on anyone's
red list; **(iii)** `actionlint` correctly caught the bites bug and the file was pushed
anyway, which is a process finding, not a control finding. Then go further: look for steps
whose assertion is behind an `if:` that is never true, jobs that only `--collect-only`, report
steps that print without comparing, and any ceiling set above its measured value.

**NO SHORTCUTS: never weaken `HONESTY.md`, `CI-STATE.md`, a ratchet or an assertion, and never
move an authoritative value to match a derived one.** `CI-STATE.md` is shared and currently
modified in the working tree — append your section, do not rewrite others', and do not delete
an existing red from it. A red you cannot explain is a finding, not a line to remove.

**Done when:** `ci.yml`'s checker-registry job is green, `check_pytest_lanes.py` refuses a
deliberately unmarked pytest step you add and then remove, and `CI-STATE.md` names at least
the three findings above plus anything else you measure, each with its activation condition.
