<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: CC-BY-4.0
-->

# Can `ci`, `supply-chain` and `mutation-ratchet` say no?

**W10, 2026-08-12, base commit `1d41442` on `master`.** Eleven CI runs — four unmutated
controls and seven plants — every one created and read in the same sitting, because this
repository's Actions logs expire within hours.

Method, unchanged from W8 and W9: for each distinct promise a lane makes, plant one
violation that should break exactly that promise, push it to a throwaway branch,
dispatch the lane on that branch, and require the lane to go red **naming the thing that
was planted**. A lane that goes red for a different reason has not been falsified.

**No plant was ever pushed to `master`.** Every plant lived on a `w10-p-*` branch cut
from `w10-base`, which is itself cut from `1d41442`.

---

## 0. The obstacle these three lanes had that W8's and W9's did not

`ci` and `supply-chain` were both **red at `1d41442` before any check ran**. Nine `ci`
jobs and all three `supply-chain` jobs died inside `./.github/actions/setup-workspace`
with `connect ECONNREFUSED 54.185.253.63:443` (runs 31596249352 and 31596446007). A lane
that cannot start cannot be falsified: every plant would have produced a red identical
to the control's.

So `w10-base` is `1d41442` **plus one repair and nothing else**: the
`release-assets.githubusercontent.com:443` egress endpoint, added to
`.github/actions/setup-workspace/action.yml`, `supply-chain.yml`, `db.yml` and
`cloud-verify.yml` from **W1's** working tree, and — by me, for this experiment only —
to the ten `allowed-endpoints` lists in `ci.yml`.

**`ci.yml` belongs to W2, and the copy I patched exists only on a deleted branch.** The
`ci` results below therefore carry one caveat and it is stated once here: they were
measured on a tree that anticipates W2's repair. When W2's version of `ci.yml` lands,
the two `RED_SELECTOR` plants below should be re-dispatched against it. Nothing about
the plants themselves depends on the endpoint list.

### 0.1 The controls

| lane | control | conclusion | what makes it a control |
|---|---|---|---|
| `supply-chain` | [31615368325](https://github.com/Shaugato/mainline/actions/runs/31615368325) | **success** | 4 of 4 jobs green on the unmutated `w10-base` tree |
| `mutation-ratchet` | [31615372338](https://github.com/Shaugato/mainline/actions/runs/31615372338) | **success** | unmutated `w10-base` |
| `mutation-ratchet` | [31596662350](https://github.com/Shaugato/mainline/actions/runs/31596662350) | **success** | unmutated `master` at `1d41442`; this lane does not use `setup-workspace`, so `w10-base` changes nothing it reads |
| `ci` | [31615364211](https://github.com/Shaugato/mainline/actions/runs/31615364211) | failure — **8 of 12 jobs green** | see below |

**`ci`'s control is a failure, and that does not spoil the experiment** — because the
job under test is green in it. `RED BY DESIGN, and it must stay red` passed in the
control with `13 failed, 9311 deselected in 18.00s`, and failed in both plants. That is
an *in-run* control of the kind W9 §0 argues is stronger than a same-SHA rerun: the four
red jobs in the control (`ruff format · the counted lint ratchet`, `mypy`, `pytest
--crdb=none`, `CI summary`) are red in the plant runs too, identically, and are not the
job any plant touched.

**Run 31615364211 is the first `ci` run since `b0fe884` in which every job actually
executed**, so it is also the only current measurement of that lane's real content. It
is reported in `docs/CI-STATE.md` §2 rather than here.

---

## 1. `ci` — the `RED BY DESIGN` vacuity guards

The brief named this the most important experiment in my set, and it is, because the
failure mode it guards against **has already happened once in this repository**:
`ci.yml`'s own header records that `RED_SELECTOR` reached only the five `g4alpha` cases
between the day it was written and 2026-08-10, while eight tests printing
`PL-2 RED, as intended.` failed inside the general regression lane. The header states the
mechanism in one sentence — *"a `-m` name that no test carries fails silently and
green"* — and `RED_FLOOR` is the guard that is supposed to make that impossible.

Nothing in the tree had ever shown that guard firing. Two plants, because the selector
can collapse two different ways and the two are caught by **different code**.

### 1.1 Partial collapse — the selector loses one marker

**Plant** (`w10-p-ci-floor`): one line of `ci.yml`.

```diff
-  RED_SELECTOR: "g4alpha or pl2_red"
+  RED_SELECTOR: "g4alpha"
```

This is the exact state the repository was in before 2026-08-10. pytest is perfectly
happy with it: the expression is valid, five tests are collected, all five fail, and a
job that only asked "did every selected test fail?" would answer yes and go green.

**Run [31615590317](https://github.com/Shaugato/mainline/actions/runs/31615590317) —
failure**, at `The verdict — every declared red is still red, and nothing else hid here`:

```
selected 5 test(s) -> 5 red · 0 green · 0 not measured
##[error]only 5 declared red(s) actually failed; the floor is 13
  This job asserts that a declared set is STILL RED. Below the floor it
  would be asserting that over almost nothing, which is the vacuous pass
  the floor exists to refuse.
```

Eight jobs were green in the same run. **`RED_FLOOR` genuinely refuses.** It is the only
thing in the tree that would have caught the 2026-08-10 defect, and it does.

### 1.2 Total collapse — a marker no test carries

**Plant** (`w10-p-ci-nomarker`): `RED_SELECTOR: "g4alpha_typo or pl2_redd"`. Neither
name is registered and neither is applied anywhere.

This is a genuinely different path from §1.1: with zero tests collected pytest never
writes a JUnit report at all, so `RED_FLOOR` — which counts `<failure>` elements in that
report — is never reached. The guard that has to fire is the exit-code case analysis in
the step above it.

Measured on this workstation first, because it is the claim the whole mechanism rests on:

```
$ .venv/Scripts/python.exe -m pytest --crdb=none -m "g4alpha_typo or pl2_redd" -q
9324 deselected in 11.84s
pytest exit=5
```

`--strict-markers` does not object. Nothing is collected. The run "succeeds" in the sense
that it produced no failure.

**Run [31615594567](https://github.com/Shaugato/mainline/actions/runs/31615594567) —
failure**, at `Run the declared set — the exit code is NOT the verdict`:

```
pytest exited 5
##[error]'-m g4alpha_typo or pl2_redd' collected NO tests, so this job would have
reported 'every declared red is still red' over the empty set. Either the
markers were removed from the suites, or the selector in ci.yml's env block
no longer names them. A vacuous pass here is worse than a red.
```

**Both halves of the guard fire, and they fire independently.** Deleting either would
leave a hole the other does not cover.

### 1.3 The local collection counts these two plants move

Measured on the pinned interpreter, `1d41442`, and consistent with the CI runs above:

```
-m "g4alpha or pl2_red"           13/9324 collected (9311 deselected)   [control]
-m "g4alpha"                       5/9324 collected (9319 deselected)   [§1.1 plant]
-m "g4alpha_typo or pl2_redd"      0      collected (9324 deselected)   [§1.2 plant]
```

### 1.4 The sequence ban

**Plant** (`w10-p-ci-seq-reuse`): `verticals/mainline/db/migrations/0999_w10_plant.sql`,
correctly licensed, three lines, containing `CREATE SEQUENCE mainline.w10_plant_seq;`.
The repository bans `CREATE SEQUENCE`, `nextval`, `SERIAL` and `unique_rowid()` outright,
and `the sequence ban, repository-wide` is the job that says so.

**Run [31616522487](https://github.com/Shaugato/mainline/actions/runs/31616522487) —
failure.** The job returned **five** separate named findings on those three lines,
including the planted one:

```
0999_w10_plant.sql:3: banned-token:create-sequence — 'CREATE SEQUENCE' — a sequence
makes a gap ambiguous; the ledger is gap-free by CAS so a gap MEANS tampering

0999_w10_plant.sql:1: allocation-unallocated — sits in band 0200-9999z, owner UNALLOCATED
0999_w10_plant.sql:1: missing-invariant-citation — the header comment cites no MInn or Inn
0999_w10_plant.sql:1: header-missing-key — no '-- MI:' line; four keys are mandatory
0999_w10_plant.sql:3: producer-absent — mainline.w10_plant_seq is referenced here and no
                      migration CREATEs it
```

A three-line file could not get past this job by accident.

### 1.5 REUSE — a plant that did **not** falsify, and what it taught instead

The same branch carried a second plant: `docs/w10-plant-unlicensed.md`, one sentence, no
SPDX header, aimed at `REUSE — every file names its licence`.

**That job stayed GREEN in run 31616522487, and it was right to.** `REUSE.toml` carries
blanket annotations over `docs/**`, `qa/**`, `evidence/**`, `packages/**`, `scripts/**`,
`spec/**`, `skills/**`, `tests/**`, `verticals/**`, `infra/**` and `.github/**`, with the
spec's `precedence = "closest"`, so those annotations fill gaps without touching the 2 602
headers on disk. **My plant landed inside a blanket and therefore planted nothing.**

I am recording the failed plant rather than deleting it, because presenting a plant that
landed in a covered directory as a caught violation is exactly the error
`aws-evidence`'s `FAMILY red-for-the-wrong-reason` control exists to catch.

The consequence is a **scope correction to the job's name**: its promise is *"every
tracked file is **covered**"*, not *"every file **names** its licence"*, and **no new file
inside an existing top-level tree can make it fail.**

**Re-plant** (`w10-p-ci-reuse2`): `W10-PLANT-UNLICENSED.md` at the repository root,
outside every blanket.

**Run [31616891891](https://github.com/Shaugato/mainline/actions/runs/31616891891) —
`REUSE — every file names its licence` failed**, while `the sequence ban,
repository-wide` stayed **green** in the same run:

```
UNCOVERED — resolve a licence or annotate (1):
    W10-PLANT-UNLICENSED.md
REFUSED [UNCOVERED] 1 tracked file(s) resolve no licence by header, by sidecar or by REUSE.toml
REFUSED [RATCHET] metric=uncovered_by_top_level_directory.<root> baseline=0 measured=1 [HARD GATE: baseline is 0]
REFUSED [RATCHET] metric=uncovered_total baseline=0 measured=1 [HARD GATE: baseline is 0]
```

The metric name is itself the confirmation: coverage is ratcheted **per top-level
directory**, and `<root>` is the only bucket whose baseline is 0 and whose blanket is
empty. The two runs are each other's in-run controls — each plant reds exactly one job and
leaves the other green.

---

## 2. `supply-chain` — the guard, and the claim behind it

`docs/CI-STATE.md` §6 said, before this revision, that `supply-chain` *"carries an
anti-vacuity guard (the resolved set must name the workspace members) rather than a
planted violation, and is the one green lane whose proof is weaker than the others'."*

**That was true when it was written and it is false at `1d41442`.** The lane carries a
step named `RED — four planted violations, each refused BY NAME`, which writes the
assertion to a file, runs it against four mutated copies of the two witnesses, and
requires each to be refused with a specific title and a specific needle. I verified this
rather than rediscovering it, as instructed. The correction is carried into
`docs/CI-STATE.md` §6.

That in-lane harness is a self-test of a checker. It does not answer the question this
document asks, which is whether **the lane** refuses a real violation of the tree. Two
plants, one for each branch of the assertion.

### 2.1 The §8.2 claim — a model SDK in the merge gate's resolved set

`ARCHITECTURE.md` §8.2 says no model can reach the merge gate. Four surfaces assert it;
this job asserts the fifth and hardest — the **resolved set**, a dependency that is
installed but not yet imported, invisible to the import graph, the AST scan and
`sys.modules`, and present in the image.

**Plant** (`w10-p-sc-model`): `boto3` added to `mainline-gate-svc`'s dependencies in
`uv.lock` (both the `dependencies` list and `[package.metadata].requires-dist`) and in
its `pyproject.toml`. `boto3` is already a locked distribution in this workspace, so this
is exactly the shape a real regression would take: a lockfile edge, no new resolution.

**Run [31615598216](https://github.com/Shaugato/mainline/actions/runs/31615598216) —
failure.** The job `SECURITY CLAIM — mainline-gate-svc's dependency closure contains no
model SDK` refused, by name:

```
##[error]mainline-gate-svc now resolves model SDK distribution(s) ['boto3', 'botocore'],
seen by uv tree (the workspace graph)
```

Note `botocore` in that list: the plant named one distribution and the deny-list caught
its transitive companion too, which is the property a closure check has and a
direct-dependency check does not. The other three jobs in the run stayed green, including
`uv.lock is fresh and describes this commit` — the plant is a *consistent* lock, so
`uv lock --check` had nothing to say. **A lockfile edit that adds a model SDK passes the
freshness check and is caught only here.**

### 2.2 Can the anti-vacuity guard itself fail?

This is the question the brief asked me to settle. The guard is
`REQUIRED = {"psycopg", "trappoint-core", "mainline-domain"}`, checked independently
against both witnesses, and its purpose is to refuse a clean result measured over the
wrong set. `supply-chain.yml` records six runs on 2026-08-10 in which it fired — but
those logs have expired and the claim could not be re-read.

**Plant** (`w10-p-sc-guard`): `mainline-domain` removed from `mainline-gate-svc`'s
dependencies, in `uv.lock` and in `pyproject.toml`.

**Run [31615601879](https://github.com/Shaugato/mainline/actions/runs/31615601879) —
failure.** Both witnesses refused, separately:

```
uv export (the pinned resolution) did not name ['mainline-domain'], so a clean result
from it would have been measured over the wrong set
  what it did name: ['mainline-gate-svc', 'psycopg', 'psycopg-binary', 'psycopg-pool',
                     'trappoint-core', 'typing-extensions', 'tzdata']

##[error]uv tree (the workspace graph) did not name ['mainline-domain'], so a clean
result from it would have been measured over the wrong set
```

**The guard can fail, and it fails twice over.** The two-witness repair described in
`supply-chain.yml:384-417` is real: the export and the tree each lost the member and each
said so on its own.

### 2.3 A finding: the green half is masked by the red half

In **both** plants the failing step was `RED — four planted violations, each refused BY
NAME`, and the step after it — `GREEN — the assertion, over the REAL resolved set`, which
is the step the §8.2 claim nominally rests on — was **skipped**. Step-level, identically
for runs 31615598216 and 31615601879:

```
success :: THE ASSERTION, written to a file so the red half and the green half are one
failure :: RED — four planted violations, each refused BY NAME
skipped :: GREEN — the assertion, over the REAL resolved set
skipped :: The tracked tree was never mutated
skipped :: The other surfaces, as the gate service itself asserts them
```

The cause is the red half's own first act: it copies the two real witnesses and checks
that the *copies* are clean before trusting any refusal below them. On a violating tree
they are not clean, so it stops:

```
##[error]COPIES ARE NOT CLEAN: byte copies of the two witnesses are already refused, so
no refusal below is attributable to a plant:
 …
This job is the assertion that claim rests on. Do not silence it.
Remove the dependency, or withdraw the claim everywhere it is made.
```

This is the same shape as `aws-evidence`'s `FAMILY red-for-the-wrong-reason` and as
W8 §4.1's three masked `RED — …` steps, and **it is correct behaviour, not a defect**:
the harness refused to claim it had caught a plant when the control was already dirty,
and it appended the real checker output so the true cause (`boto3`,
`mainline-domain`) is still in the log.

But two consequences should be recorded, because a reader of the Actions tab will meet
them:

1. The headline error on a real §8.2 breach is
   `resolved-set assertion is vacuous / COPIES ARE NOT CLEAN`, which reads as an
   instrument fault. The sentence that matters is eleven lines further down.
2. `GREEN — the assertion, over the REAL resolved set` **has never been observed
   refusing** and cannot be, in normal operation, because the step above it fails first
   on every input that would make it refuse. Its green tick means "the red half passed",
   not "the real closure was checked today". Moving the red half after the green half, or
   giving the green half `if: always()`, would fix both. `supply-chain.yml` is W1's file;
   this is reported, not edited.

---

## 3. `mutation-ratchet` — the one assertion in a lane that is not a gate

This lane is explicitly **never a gate**: `mainline-mutation run` exits 0 whatever the
kill rate is, and the workflow header says a threshold here would give the figure an
incentive to be high. So almost nothing in it *can* be falsified by making a number
worse — which is the point.

It makes exactly one assertion about numbers, and it is not about quality: the crippled
arm (lattice rule `R1_DEONTIC` switched off) must report a **strictly lower** kill rate
than the intact arm, and must name `deontic_downgrade` among its survivors. That asserts
the harness is measuring the lattice rather than measuring itself.

**Its conclusion at `1d41442` was unknown to the lead. Measured: run
[31596662350](https://github.com/Shaugato/mainline/actions/runs/31596662350), conclusion
`success`.**

**Plant** (`w10-p-mut-noop`): one line in
`mainline_mutation/lattice_injection.py`, immediately after the unknown-rule-id check —

```python
    disabled = frozenset()  # W10 PLANT: silently disable nothing
```

`--disable R1_DEONTIC` is still parsed, still validated, still recorded in the report and
still labels the arm `CRIPPLED`. It just stops doing anything. This is precisely the
failure the function's own docstring names: *"a typo would silently disable nothing and
the crippled run would report the intact number under a crippled label, which is the
worst possible failure for a red-before-green artefact."*

**Run [31615605021](https://github.com/Shaugato/mainline/actions/runs/31615605021) —
failure**, at `PL-2 — assert the crippled arm is WORSE and names its survivor`:

```
intact  KILL wilson_lower = 0.909774
crippled KILL wilson_lower = 0.909774
PL-2 FAILED: disabling R1_DEONTIC did not lower the kill rate. Either the injection
point does nothing, or the catalogue contains no mutation that R1_DEONTIC is the only
detector of. Both mean this harness asserts nothing.
```

Two identical Wilson lower bounds to six decimal places, and the lane refused. Control
[31615372338](https://github.com/Shaugato/mainline/actions/runs/31615372338): **success**
on the same tree without that line.

**`mutation-ratchet` is falsified caveat-free** — the only one of my three lanes for
which that is true, because it needed no borrowed repair to run at all.

---

## 4. What I could NOT falsify

### 4.1 Eight of `ci`'s twelve jobs

The control run 31615364211 has eight green jobs. I falsified three of them —
`RED BY DESIGN` (twice, by two different guards), `the sequence ban, repository-wide`, and
`REUSE — every file names its licence` (on the second attempt, §1.5).

**Five were not tested at all and are unproven by me**: `every checker this lane invokes
exists`, `actionlint`, `import-linter contracts · and no package outside them`,
`the lockfile is authoritative · workspace membership`, and `PL-2 — the red run is
recorded`. They are named in `docs/CI-STATE.md` §6.2 as unproven. No inference is offered
about them in either direction.

The four red jobs need no falsification — a job that is failing is observably able to
fail — but note that this makes `ci` a lane where the anti-vacuity question is
**per-job**, not per-lane, and the summary tick a reader sees on the Actions tab answers
neither.

### 4.2 `supply-chain`'s `GREEN — the assertion, over the REAL resolved set`

Unfalsifiable by construction, for the reason in §2.3: every input that would make it
refuse makes the step above it fail first. The *property* is enforced — my two plants
prove that — but this specific step has never been observed asserting anything.

### 4.3 `supply-chain`'s other two green jobs

`an SBOM for every distribution` and `pip-audit over the locked set` stayed green in
every run above, including both plant runs, and I planted nothing against either. The
SBOM job's `REUSE needs a licence for generated evidence too` step and `pip-audit`'s
advisory lookup are untested by me. **Unproven.**

### 4.4 `mutation-ratchet`'s measurement-did-not-happen conditions

The lane's header names four failure conditions besides PL-2: a catalogue class with no
operator, a drifted paraphrase cassette, a class that produced no trial, an injection
point that stopped injecting. My plant exercised the last of these *through* PL-2 — it is
what "the injection point does nothing" means — but I planted nothing against the first
three, and the measurement suite (`tests/e2e/mutation`, `tests/unit/domain/novelty`) ran
green untested. **Unproven.**

### 4.5 The `ci` results all carry W2's caveat

Restated from §0 because it belongs in this list too: `ci` was falsified on a tree
carrying an endpoint repair to a file I do not own. The plants are independent of that
repair, but no `ci` claim here has been observed against W2's actual `ci.yml`.

---

## 5. Every run in this document

| lane | branch (deleted) | plant | run | conclusion |
|---|---|---|---|---|
| `ci` | `w10-base` | none (control) | [31615364211](https://github.com/Shaugato/mainline/actions/runs/31615364211) | failure — 8/12 jobs green; `RED BY DESIGN` **green** |
| `supply-chain` | `w10-base` | none (control) | [31615368325](https://github.com/Shaugato/mainline/actions/runs/31615368325) | **success** |
| `mutation-ratchet` | `w10-base` | none (control) | [31615372338](https://github.com/Shaugato/mainline/actions/runs/31615372338) | **success** |
| `mutation-ratchet` | `master` | none (control) | [31596662350](https://github.com/Shaugato/mainline/actions/runs/31596662350) | **success** |
| `ci` | `w10-p-ci-floor` | `RED_SELECTOR` drops `pl2_red` | [31615590317](https://github.com/Shaugato/mainline/actions/runs/31615590317) | **failure** — `only 5 declared red(s) actually failed; the floor is 13` |
| `ci` | `w10-p-ci-nomarker` | markers no test carries | [31615594567](https://github.com/Shaugato/mainline/actions/runs/31615594567) | **failure** — `pytest exited 5` … `collected NO tests` |
| `ci` | `w10-p-ci-seq-reuse` | `CREATE SEQUENCE` in a migration; an unlicensed file under `docs/` | [31616522487](https://github.com/Shaugato/mainline/actions/runs/31616522487) | **failure** — `banned-token:create-sequence`; the REUSE half stayed green and planted nothing (§1.5) |
| `ci` | `w10-p-ci-reuse2` | an unlicensed file at the repository root | [31616891891](https://github.com/Shaugato/mainline/actions/runs/31616891891) | **failure** — `REUSE` red, the sequence ban green in the same run |
| `supply-chain` | `w10-p-sc-model` | `boto3` into the gate's closure | [31615598216](https://github.com/Shaugato/mainline/actions/runs/31615598216) | **failure** — `resolves model SDK distribution(s) ['boto3', 'botocore']` |
| `supply-chain` | `w10-p-sc-guard` | `mainline-domain` dropped | [31615601879](https://github.com/Shaugato/mainline/actions/runs/31615601879) | **failure** — `did not name ['mainline-domain']`, both witnesses |
| `mutation-ratchet` | `w10-p-mut-noop` | `--disable` made a no-op | [31615605021](https://github.com/Shaugato/mainline/actions/runs/31615605021) | **failure** — `PL-2 FAILED: … did not lower the kill rate` |

**Seven promises falsified with a named red; one plant that landed inside a REUSE.toml
blanket and falsified nothing, reported rather than dropped (§1.5); five areas explicitly
unproven (§4).** Every branch in this table was deleted after its log was read; none was
ever merged, and `master` never carried a plant.

Reproduce any row:

```bash
gh run view <run-id> --json jobs --jq '.jobs[] | "\(.conclusion) :: \(.name)"'
gh run view <run-id> --log-failed
```
