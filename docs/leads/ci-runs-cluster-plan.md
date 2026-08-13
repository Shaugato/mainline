<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: CC-BY-4.0
-->

# CI RUNS THE CLUSTER — the lead's plan

**Lead:** CI-runs-the-cluster. **Written 2026-08-13 on TRAPPOINT**, against the working tree at
`D:/CoackroachDBxAWS/mainline`, HEAD `073dfea`, with `.venv/Scripts/python.exe` (pytest 9.1.1)
and the pinned local node **CockroachDB CCL v26.2.5** on `127.0.0.1:26257`.

**Every number in §1 was measured by this lead in this sitting**, with the command printed
beside it. Nothing is inherited from a recorded board, and nothing is projected.

---

## 0. THE RULE THAT BINDS EVERY WORKER ON THIS PLAN

A previous worker on this repository was caught editing `verticals/mainline/db/seeds/demo/demo_world.sql`
to enrol a credential id that an application constant happened to derive — making the SEED match
the CODE so that a red test went green. Three independent negative controls caught it; one said
so in as many words: *"the seed has been reshaped to match an application constant."* It was
reverted.

> **When a test and the code disagree, the resolution is almost never to move whichever side is
> easier. Ask which side is AUTHORITATIVE.** In that case the database owned
> `signer_credential_id` because it is a FOREIGN KEY onto `mainline.signing_credential`, so the
> code had to RESOLVE it and the seed had to stay exactly as it was.
>
> **Changing a seed, fixture, ceiling, threshold, or expected value to obtain a green is the
> single most damaging thing you can do in this repository**, because it converts a real defect
> into a permanent invisible one. If you believe a fixture is genuinely wrong, say so in your
> `still_broken` report with your evidence, and leave it alone.

This rule is repeated verbatim in all six worker briefs. It is not boilerplate. This wave is
*specifically* about the machinery that lets an invisible defect stay invisible, so a shortcut
taken here is worse than a shortcut taken anywhere else in the repository.

**Also binding on every worker:**

- **NEVER `terraform apply`.** `init` / `validate` / `plan` / `show` and read-only AWS calls only.
- **NEVER weaken `docs/HONESTY.md`, `docs/CI-STATE.md`, a ratchet, or an assertion.**
  `continue-on-error` and `|| true` are banned in `.github/workflows/`; there is one surviving
  legitimate `|| true` (`db.yml:564`, container cleanup) and you may not add a second.
- **NEVER edit recorded evidence to silence a checker.** Fix the checker.
- **NEVER print a credential.**
- **Run the full demo-api suite under `--crdb=reuse` before and after your change, and report
  both numbers.** A fix that breaks a passing test is worse than the defect it fixed.

---

## 1. BASELINE — measured by this lead, 2026-08-13, before any decomposition

### 1.1 The demo-api suite, both ways

```
$ .venv/Scripts/python.exe -m pytest verticals/mainline/apps/demo-api/tests --crdb=none -q
258 passed, 186 skipped in 13.11s

$ .venv/Scripts/python.exe -m pytest verticals/mainline/apps/demo-api/tests --crdb=reuse -q
3 failed, 377 passed, 1 skipped, 63 errors in 45.95s
```

444 tests both ways. **186 of them — 41.9% of the suite that covers the product's headline path —
have never executed in CI even once.**

The single skip under `--crdb=reuse` is not a cluster skip:
`test_gate_run.py:945` — *"jsonschema is not a workspace dependency."* So the executable
population under a cluster is **443**.

Note the drift against the orchestrator's recorded `375 passed, 5 failed, 63 errors`: this
lead measured `377 passed, 3 failed`. The two failures that differ are
`test_transitions.py::test_the_request_after_a_gate_run_is_not_a_503` and its neighbour, which
are the known cross-test-contamination pair. **The lane must therefore not treat a fixed failure
list as deterministic** — see W2's known-red design, §3.2.

### 1.2 Collection, and the stale tally in `ci.yml`

```
$ .venv/Scripts/python.exe -m pytest --collect-only -q --crdb=none            → 9838 collected
$ ... -m "g4alpha or pl2_red"                                                 → 15 / 9838 (9823 deselected)
$ ... -m "not (g4alpha or pl2_red)"                                           → 9823 / 9838 (15 deselected)
$ ... verticals/mainline/apps/demo-api/tests                                  → 444 collected
```

`ci.yml:124-129` records `13 collected / 9240 deselected`, total `9253`, and sets
`RED_FLOOR: "13"` at line 601. **The declaration is 585 tests and 2 red-by-design cases stale.**
`docs/HONESTY.md:632` and `docs/CI-STATE.md:401` both publish
`8467-8468 passed, 839 skipped, 13 deselected` — sum `9324`, which is the collection total from
*before* the `verticals/*/apps/demo-api/tests` testpath landed. **Both published splits predate
the change that added this suite.**

### 1.3 Where the cluster actually is, and where it is not

The scope brief says "all 18 workflows run `pytest --crdb=none`". Measured, the truth is sharper
and worse:

```
$ for f in .github/workflows/*.yml; do grep -c 'docker run -d' "$f"; done
9 of 18 workflows stand up a CockroachDB container:
  cloud-verify(1) custody-chain(3) db-schema(1) db(1) mutation-ratchet(1)
  nightly-differential(2) release-proof(2) schema(2)

$ grep -rn "demo-api" .github/workflows/          → NO MATCHES, in any file.
```

`ci.yml` has 11 jobs and **zero** clusters; it is the only workflow that runs the whole-repo
`testpaths` collection, and it runs it `--crdb=none`. Nine workflows *do* have a cluster, and
**not one of them names `verticals/mainline/apps/demo-api/tests`.**

The honest one-sentence statement of the finding is therefore:

> **No lane in this repository executes a single cluster-backed demo-api test. The only lane
> that runs the whole-repo collection runs it with no cluster, so those 186 tests skip; and no
> lane that has a cluster is pointed at that directory.**

### 1.4 The second finding, which nobody has written down yet

```
30 pytest invocations across 9 workflow files.
 5 declare a --crdb mode (4 in ci.yml, 1 in release-proof.yml).
25 run at the default mode `auto`.
```

`auto` means *"reuse a cluster that answers; start one if none does."* So 25 CI steps silently
either reuse whatever happens to be listening or start their own container, and **the file does
not say which**. `conftest.py`'s own header records what that costs: thirteen concurrent private
nodes, all exiting 7/8, taking the shared node down, and a run that *wedged rather than failed*.
A lane whose cluster posture is implicit cannot be audited, and cannot be ratcheted.

### 1.5 The census script is blind in the same place the testpath was

`scripts/qa/report_test_state.py:143` — `for pattern in ("packages/*", "verticals/*/packages/*")`.
`verticals/*/apps/*` is absent, so `qa/test-state.json` (26 targets, 8845 tests) **does not contain
a single demo-api row**. This is the *third* occurrence of one defect class, one directory level
across, after `testpaths = ["tests", "packages"]` (2026-08-10) and
`testpaths += verticals/*/packages/*/tests` (2026-08-13).

### 1.6 The whole-repo hermetic run — the number that has never been published

This is the exact command `ci.yml`'s `hermetic-tests` job runs, plus `-ra` so the skips carry
their reasons. Run by this lead in this sitting, 524 s wall clock:

```
$ .venv/Scripts/python.exe -m pytest --crdb=none -q -m "not (g4alpha or pl2_red)" -ra
1 failed, 8835 passed, 987 skipped, 15 deselected, 2 warnings in 524.01s (0:08:44)
```

`1 + 8835 + 987 + 15 = 9838`, which is the collection total in §1.2. **987 of 9838 tests —
10.0% of everything this repository collects — do not execute in CI.** Classifying every
`SKIPPED [n] file:line: reason` line by its reason string:

```
973  skipped for want of a CockroachDB      (98.6% of all skips)
 14  skipped for anything else              (OPA binary, live-AWS opt-in, an uncommitted SBOM,
                                             a nightly arm, sentence-transformers weights)
 35  distinct skip reason strings
```

The 973 cluster skips, by test root:

| root | cluster skips | is any of it run against a cluster in CI? |
|---|---:|---|
| `tests/integration` | 539 | partly — `custody-chain.yml` runs `tests/integration/custody`; the ~250 in `tests/integration/schema` are named by no lane |
| `packages/trappoint-conformance` | 187 | **no** — `schema.yml` runs `unweld/` and four named files, *not* `tests/test_conformance_cases.py`, which is where 181 of these live |
| `verticals/mainline/apps/demo-api` | 186 | **no lane anywhere** |
| `packages/trappoint-diagnose` | 17 | **no** |
| `tests/concurrency` | 15 | partly — `nightly-differential.yml` runs one file |
| `tests/release` | 15 | partly — `release-proof.yml` runs one file |
| `packages/trappoint-model` | 11 | ? |
| `packages/trappoint-testkit` | 2 | **no** |
| `tests/unit` | 1 | **no** |

**The right-hand column is a hypothesis, not a measurement, and W4 must not inherit it.**
This lead tried to derive it mechanically, by checking whether each skipped file's path or any
prefix of it appears in a non-comment line of any workflow. That method returned
`968 covered / 19 uncovered`, which is **nonsense**: `demo-api/tests/conftest.py` came back
"covered by eleven workflows" because the substring `verticals` occurs in eleven files. The
method is recorded here so it is not tried again. **The only sound way to answer that column is
to execute each lane's exact pytest argv against a cluster and record which node ids it runs.**
See W4's brief, §"the trap".

---

## 2. WHAT THIS WAVE MUST BE TRUE AT THE END

1. A judge opening the Actions tab can see a lane named for a cluster, that stood up
   `cockroachdb/cockroach:v26.2.5`, **asked the running server what version it was**, and ran the
   443 executable demo-api tests against it.
2. That lane is **provably falsifiable**: a defect that only a cluster can see makes it red, and
   the same defect leaves the hermetic lane green. Both halves asserted, in CI, every run.
3. The skip count is a **ratchet**. Every test that skips for want of a cluster is either executed
   by a named lane, or is on an explicitly enumerated `unlanded` list with a reason, and that list
   is a ceiling that may only shrink.
4. Every pytest invocation in `.github/workflows/` **says which side of the cluster line it is on**.
5. `docs/CI-STATE.md` publishes the honest split with numbers that were measured, not inherited.
6. `custody-chain`, `schema` and `demo-health` are **still red**, with the cause in the first
   clause of the message GitHub renders.

---

## 3. THE SIX WORKERS

Paths are **literally enumerated and disjoint**. No two workers write the same file. Where one
worker consumes another's interface, the interface is specified verbatim in both briefs so the
two can be built in parallel.

### 3.0 Two contracts fixed here, so four workers can build against them without waiting

**CONTRACT A — the pytest-lane marker.** Every step in any file under `.github/workflows/` that
invokes pytest carries, as a comment line inside that step's `run:` block or in the comment block
immediately above the step's `- name:`, exactly one of:

```
# trappoint:pytest-lane=hermetic    — the invocation passes --crdb=none. No cluster is obtained
#                                     and none may be started; cluster tests skip with a reason.
# trappoint:pytest-lane=cluster     — the invocation passes --crdb=reuse AND the enclosing job
#                                     starts a pinned node before it AND asserts an executed floor.
# trappoint:pytest-lane=spawn       — the invocation passes --crdb=auto and deliberately lets the
#                                     testkit start its own container. Costs a container; declared.
# trappoint:pytest-lane=unlanded reason="<one sentence>"
#                                   — this invocation's cluster-backed tests are known to skip and
#                                     no lane runs them. Counted against a shrinking ceiling.
```

The marker is a **comment**, so any checker that reads it must read the file as **raw text**, not
through a YAML parser — PyYAML discards comments, and these files are 60% comment by volume.

**CONTRACT B — the cluster stand-up sequence.** Copy it from `db-schema.yml:310-450`; do not
invent one. It is five steps and the fourth is the one that matters:

1. `Read the ONE version constant out of compose.yaml` — parse the line tagged
   `trappoint:crdb-image-pin`. **Never restate `v26.2.5` in a workflow file.** `db.yml` counts
   restated image literals against a ceiling being driven down.
2. `Pull the image and record its digest` — assert against `vars.CRDB_IMAGE_DIGEST` when set.
3. `Start a single-node CockroachDB` — `docker run -d --name <unique> -p 127.0.0.1:26257:26257 …
   start-single-node --insecure --store=type=mem,size=2GiB`. **`--listen-addr` must stay absent**;
   the node refuses to start with `0.0.0.0` and binds unreachably with `localhost`.
4. **`The server that answered IS the pinned version`** — `SELECT version()` through
   `docker exec`, compared against the tag the step-1 output resolved, expectation *derived* and
   never written out. Steps 1-3 catch a pin that failed to *arrive*; only this step catches a pin
   that arrived as different bytes. Skipping it makes the whole lane a measurement of an unknown
   engine wearing this lane's name.
5. Publish the DSN under **all four spellings** the tree checks —
   `MAINLINE_TEST_DSN`, `COCKROACH_URL`, `CRDB_URL`, `TRAPPOINT_DSN` — then run pytest with
   `--crdb=reuse`. `reuse`, never `auto`: a lane that would silently start its own container when
   its `docker run` failed is a lane that cannot report that its cluster is missing.

---

### W1 — THE NUMBER: what CI skips, measured and published

**Owns, and nothing else:**
- `scripts/qa/ci_skip_census.py` (new)
- `qa/ci-skip-census.json` (new)
- `docs/ci/skip-census.md` (new)
- `scripts/qa/report_test_state.py`
- `qa/test-state.json`

**Depends on:** nothing. Start immediately.

**Done when:** `python scripts/qa/ci_skip_census.py --check` reproduces `qa/ci-skip-census.json`
from a fresh run; `scripts/qa/report_test_state.py --list-targets` names
`verticals/mainline/apps/demo-api`; `qa/test-state.json` carries a demo-api row for both passes,
added through the file's existing `merges` mechanism and not by regenerating the whole census.

---

### W2 — THE LANE: a real cluster, running the real suite

**Owns, and nothing else:**
- `.github/workflows/cluster-tests.yml` (new)
- `qa/cluster-known-red.json` (new)
- `scripts/ci/cluster_lane_report.py` (new)

**Depends on:** nothing. Start immediately.

**Done when:** the workflow is dispatched on `master` and its log shows a `v26.2.5` server
answering `SELECT version()`, `443` demo-api tests executed against it, and a failure list
classified `known` / **`NEW`** — with the job's exit status equal to pytest's, unmodified.

---

### W3 — FALSIFIABILITY: the 2×2, asserted every run

**Owns, and nothing else:**
- `.github/workflows/cluster-lane-bites.yml` (new)
- `scripts/ci/plant_cluster_defect.py` (new)
- `tests/ci/test_demo_seed_is_frozen.py` (new)
- `docs/ci/cluster-lane-falsifiability.md` (new)

**Depends on:** nothing. Start immediately.

**Done when:** all four cells of the 2×2 in §3.2 of the brief are asserted in one CI job, the job
is green only when the top-right cell (plant present, `--crdb=none`, **GREEN**) holds, and the
working tree is proven clean by `git diff --exit-code` after the plant is reverted.

---

### W4 — THE RATCHET: a skipped test can never again read as green

**Owns, and nothing else:**
- `scripts/qa/skip_ratchet.py` (new)
- `qa/skip-ratchet.json` (new)
- `.github/workflows/ci.yml`

**Depends on:** W1 (census JSON schema — pinned verbatim in the brief so W4 need not wait),
W6 (checker CLI name — likewise pinned).

**Done when:** `scripts/qa/skip_ratchet.py` is red against a planted skip increase *and* against
a planted unlanded test, both demonstrated; `ci.yml`'s `9240/13` tally is replaced with a
freshly measured one; `RED_FLOOR` is raised to the measured 15 with evidence that all 15 fail.

---

### W5 — THE PUBLICATION: the honest split

**Owns, and nothing else:**
- `docs/CI-STATE.md`
- `docs/HONESTY.md`
- `docs/ci/test-collection.md`

**Depends on:** W1, W2, W3, W4, W6. Runs last.

**Done when:** every number on the page is sourced to a command run in the same sitting; the
board carries the two new lanes with real run ids; the 186-of-444 split is published; and a
`git diff` of `docs/HONESTY.md` shows only numbers replaced by measured numbers, with no
adjective softened and no claim removed.

---

### W6 — EVERY PYTEST STEP DECLARES WHICH SIDE OF THE LINE IT IS ON

**Owns, and nothing else:**
- `scripts/qa/check_pytest_lanes.py` (new)
- `qa/pytest-lanes.json` (new)
- `docs/ci/pytest-lanes.md` (new)
- `.github/workflows/aws-evidence.yml`, `boundary.yml`, `claims.yml`, `cloud-verify.yml`,
  `console.yml`, `custody-chain.yml`, `db-schema.yml`, `db.yml`, `demo-health.yml`,
  `judge-pack.yml`, `mutation-ratchet.yml`, `nightly-differential.yml`, `release-proof.yml`,
  `schema.yml`, `skills.yml`, `submission.yml`, `supply-chain.yml`

**Explicitly NOT owned:** `.github/workflows/ci.yml` (W4), `cluster-tests.yml` (W2),
`cluster-lane-bites.yml` (W3). Those three workers write Contract A markers in their own files.

**Depends on:** nothing. Start immediately.

**Done when:** all 30 pytest invocations carry a Contract A marker; `check_pytest_lanes.py`
refuses an unmarked one and refuses a `cluster` marker in a job with no pinned node; **no lane's
effective `--crdb` mode changed** (proven per lane in `docs/ci/pytest-lanes.md`); and
`custody-chain`, `schema`, `demo-health` are still red with the cause in the first clause.

---

## 4. THE TRAP THIS WAVE MUST NOT FALL INTO

**The new lane will be RED on the day it lands.** That is correct and it must stay that way —
`3 failed, 63 errors` are real defects owned by other leads in this wave. Two failure modes to
refuse by name:

1. **Do not make the lane green by narrowing it.** Deselecting `test_reads.py`, marking the 63
   `xfail`, or adding `-k` to dodge the failures converts a visible defect into an invisible one.
   That is the exact failure this whole wave exists to end.
2. **Do not let the known-red inventory become a suppression.** `qa/cluster-known-red.json` may
   only enrich the *message*. **The job's exit status is pytest's exit status.** W3's bites job
   asserts that a planted defect still fails the lane *even when its node id is added to the
   inventory*. If that control cannot be built, delete the inventory.

**And the anti-vacuity trap specific to W3:** the lane is already red, so "plant a defect and
watch it go red" proves nothing against the whole suite. W3 must run the 2×2 against a subset
that is **green today** — measured this sitting, `test_credentials.py test_gate_run.py
test_transitions.py` are green under `--crdb=reuse` — and the plant must be one the *hermetic*
lane cannot see. **The `transitions.py` `_sha("cred","signer")` reversion is the WRONG plant**:
the ratchet `test_no_module_derives_a_credential_id` catches it statically, under `--crdb=none`,
so the top-right cell of the 2×2 would be red and the proof would collapse. The right plant is
the **seed-side** one — the reverted `demo_world.sql` credential swap — which is invisible to
every hermetic test and fatal to a cluster-backed one.

---

## 5. ORDER OF WORK

```
now ──┬── W1  census                    ─┐
      ├── W2  the cluster lane           ├─→ W4 ratchet ─→ W5 publication
      ├── W3  falsifiability             │
      └── W6  lane declarations         ─┘
```

W1, W2, W3, W6 are fully parallel and share no file. W4 needs W1's JSON schema and W6's checker
name — both are pinned verbatim in W4's brief, so W4 can be written in parallel and only its
final verification waits. W5 is the publication pass and runs last, because a page of numbers
measured before the other five landed is exactly the failure `docs/CI-STATE.md`'s own §0.2
warns about.

## 6. THE MEASUREMENT EVERY WORKER REPEATS

Before and after your change, both numbers in your report:

```
.venv/Scripts/python.exe -m pytest verticals/mainline/apps/demo-api/tests --crdb=reuse -q
.venv/Scripts/python.exe -m pytest verticals/mainline/apps/demo-api/tests --crdb=none  -q
```

This lead's baseline, 2026-08-13, HEAD `073dfea`:

| pass | result |
|---|---|
| demo-api, `--crdb=none` | **258 passed, 186 skipped** (444 collected) |
| demo-api, `--crdb=reuse` | **3 failed, 377 passed, 1 skipped, 63 errors** (443 executed) |
| whole repo, `--crdb=none -m "not (g4alpha or pl2_red)"` | **1 failed, 8835 passed, 987 skipped, 15 deselected** in 524 s |
| whole repo, collection | **9838** collected; `15 / 9823` on the RED_SELECTOR split |

## 7. THE ONE-LINE VERDICT THIS WAVE IS ANSWERING

> **987 of 9838 tests do not execute in CI. 973 of those 987 are waiting on a database.
> 186 of them are the product's headline path, and no lane in this repository has ever
> pointed a cluster at them.**

---

## 8. THE SIX BRIEFS, IN FULL

Every brief below opens with the rule in §0. It is repeated, not referenced, on purpose.

### W1 — THE NUMBER

**The no-shortcut rule.** A previous worker edited `demo_world.sql` so a seed would match an
application constant and a red test would go green; three negative controls caught it and it was
reverted. When a test and the code disagree, ask which side is AUTHORITATIVE — do not move
whichever is easier. **Changing a seed, fixture, ceiling, threshold or expected value to obtain a
green is the single most damaging thing you can do here**, because it turns a real defect into a
permanent invisible one. If you believe a fixture is genuinely wrong, say so in `still_broken`
with evidence and leave it alone.

Your job is THE NUMBER: establish by measurement exactly which tests do not execute in CI, and
publish it in a form a checker can consume.

Context you may rely on and need not re-derive. `ci.yml`'s `hermetic-tests` job runs
`uv run --frozen --all-packages pytest --crdb=none -m "not (g4alpha or pl2_red)" -q --durations=10`.
That is the only lane in this repository that runs the whole-repo `testpaths` collection. This lead
ran it locally at HEAD `073dfea`: `1 failed, 8835 passed, 987 skipped, 15 deselected in 524.01s`,
against `9838` collected. 973 of the 987 skips carry a reason naming a cluster / CockroachDB / DSN;
14 do not; there are 35 distinct reason strings. `docs/HONESTY.md:632` and `docs/CI-STATE.md:401`
both publish `839 skipped` out of a `9324` collection — from before `verticals/*/apps/demo-api/tests`
entered `testpaths`. You are not fixing those pages (W5 owns them); you are producing the
measurement they will cite.

**1. `scripts/qa/ci_skip_census.py`.** Runs the hermetic lane's exact argv in a subprocess with
`--junit-xml`. JUnit, not `-ra`: it carries the skip reason as data rather than as a line you must
regex, and `-ra` truncates. Writes `qa/ci-skip-census.json` with schema id
`mainline.qa.ci-skip-census/1` and keys `generated_utc`, `generated_by`, `tool` (python + pytest
versions), `argv`, `collected`, `passed`, `failed`, `errored`, `skipped`, `deselected`, `roots`
(per-test-root rollup), and `skips`: **one entry per skipped test**, not per reason —
`{nodeid, file, line, reason, cluster_shaped}`. Scrub DSNs and temp paths out of reason strings the
way `report_test_state.py` already does with `_DSN_RE` / `_TMPPATH_RE`, so the census does not differ
between machines for no reason. `--check` re-runs and diffs against the committed file, exit 1 on
drift, so the file cannot go stale in silence.

**2. `docs/ci/skip-census.md`.** The census in prose, every number beside the command that produced
it, in the style of `docs/ci/test-collection.md`.

**3. `scripts/qa/report_test_state.py:143`** reads
`for pattern in ("packages/*", "verticals/*/packages/*")`. `verticals/*/apps/*` is absent, which is
why `qa/test-state.json`'s 26 targets contain no demo-api row at all. This is the **third**
occurrence of one defect class, one directory level across, after `testpaths = ["tests","packages"]`
(2026-08-10) and `+ verticals/*/packages/*/tests` (2026-08-13). Add the target the same narrow way
`pyproject.toml` does — **name the app, do not glob `apps/*`**: `verticals/mainline/apps/console/tests`
is a vitest suite with 148 entries and zero `.py` files, and handing it to pytest is the same
category error the `testpaths` comment already refuses in writing.

**4. `qa/test-state.json`.** Add demo-api rows for both passes via
`python scripts/qa/report_test_state.py --targets verticals/mainline/apps/demo-api`, folded in
through the file's existing `merges` mechanism. **Do not regenerate the whole census**: it takes
2414 s, it would rewrite 26 rows you did not measure, and other workers are writing to this tree.

Cautions. `filterwarnings = ["error", …]` is on, so a warning inside your subprocess is a hard
failure — that is intended; do not add a filter to quiet it. Carry `qa/test-state.json`'s own
caveat into yours: a whole-repo invocation and a per-target invocation collect differently, because
`prepend` import mode names a module by its basename.

**Done when:** `python scripts/qa/ci_skip_census.py --check` exits 0 on a clean tree;
`report_test_state.py --list-targets` prints `verticals/mainline/apps/demo-api`; `qa/test-state.json`
carries demo-api rows for `none` and `cluster`; and you report the §6 before/after pair.

---

### W2 — THE LANE

**The no-shortcut rule** — as stated in W1's brief, in full, and it binds you hardest of the six:
you are the worker with the most obvious route to a fake green.

You build the first CI job in this repository's history that points a real CockroachDB at the demo
API's test suite.

Baseline measured by this lead at HEAD `073dfea`:
`pytest verticals/mainline/apps/demo-api/tests --crdb=none -q` → **258 passed, 186 skipped**;
`--crdb=reuse` → **3 failed, 377 passed, 1 skipped, 63 errors** in 45.95 s. 444 collected, **443
executable** under a cluster — the single skip is `test_gate_run.py:945`, *"jsonschema is not a
workspace dependency"*, which has nothing to do with the database.
`grep -rn "demo-api" .github/workflows/` returns **nothing**. Nine of eighteen workflows stand up a
container and none is pointed here.

**Build the cluster with CONTRACT B, copied from `db-schema.yml:310-450`. Do not invent one.**
(1) Read the pin out of the line tagged `trappoint:crdb-image-pin` in `compose.yaml` —
**never restate `v26.2.5` in a workflow file**; `db.yml` counts restated image literals against a
ceiling being driven down. (2) Pull and record the digest, asserting `vars.CRDB_IMAGE_DIGEST` when
set. (3) `docker run -d --name <unique> -p 127.0.0.1:26257:26257 … start-single-node --insecure
--store=type=mem,size=2GiB` — **`--listen-addr` must stay absent**: `0.0.0.0` makes the node refuse
to start and `localhost` binds where a published port cannot reach. (4) **`The server that answered
IS the pinned version`** — `SELECT version()` through `docker exec`, compared against the tag step 1
resolved, expectation derived and never written out. Steps 1-3 catch a pin that failed to *arrive*;
only step 4 catches a pin that arrived as different bytes. (5) Publish the DSN under all four
spellings the tree checks — `MAINLINE_TEST_DSN`, `COCKROACH_URL`, `CRDB_URL`, `TRAPPOINT_DSN`.

Install with `uv sync --frozen --all-packages`. `mainline-demo-api` is deliberately **not** a
workspace member (`verticals/*/apps/*` is absent from `[tool.uv.workspace] members` because the
console beside it is a pnpm workspace). Its only dependencies are `psycopg==3.3.4` and
`psycopg-binary==3.3.4`, both already resolved in `uv.lock` through other members, and
`tests/conftest.py` puts `../src` on `sys.path` itself. **Verify that on the runner rather than
assuming it**: a `--collect-only -q` step that asserts 444 collected, before the real run.

Run `pytest verticals/mainline/apps/demo-api/tests --crdb=reuse -q --junit-xml=…`. **`reuse`, never
`auto`** — a lane that would quietly start its own container when its `docker run` failed cannot
report that its cluster is missing.

**THE EXECUTED FLOOR is the point of the job, not a detail.** A lane that runs zero tests and exits
0 is worse than no lane. From the JUnit XML assert `tests − skipped ≥ 440` and `skipped ≤ 1`.
`release-proof.yml:219-320` records this exact defect being live in this repository — *"pytest exits
0 when every test skips"* — and built a control for it. Yours must too.

**CLASSIFY, DO NOT SUPPRESS.** `scripts/ci/cluster_lane_report.py` reads the JUnit XML and
`qa/cluster-known-red.json` and prints every failing/erroring node id as `known` or **`NEW`**.
**The job's exit status is pytest's exit status.** The report step may only ADD a failure, never
remove one: it exits 1 if any failure is NEW, and exits 1 if a node id on the known list PASSED —
the list is a ceiling that must reach empty. It never exits 0 on pytest's behalf. No
`continue-on-error`, no `|| true`, no moving the verdict into an `if: always()` step.

Today's known-red set, from this lead's run: 63 errors from `test_reads.py`'s `payloads` fixture
(`KeyError: 'cr_id' is not an identifier the deployed demo seed produces`);
`test_reads.py::test_an_undeclared_query_parameter_is_refused_rather_than_ignored`;
`test_refusal_row_factory.py::test_the_declined_branch_declines_identically_under_both_factories`
and `::test_the_savepoint_fence_survives_a_raise_inside_one_open_transaction`. **Note the
instability**: the orchestrator measured 5 failures where this lead measured 3, and
`test_transitions.py::test_the_request_after_a_gate_run_is_not_a_503` passes alone and fails in
suite. So the inventory is a **set-membership** test, never an expected-count test.

Write a Contract A `cluster` marker on every pytest step. You may **not** edit `demo_world.sql`, any
test, any fixture or any source file. If the suite cannot run in CI without such an edit, stop and
report it — that is a finding, not an obstacle.

**Done when:** dispatched on `master`; the log shows the server's own `SELECT version()` compared to
the compose pin; 443 executed; failures classified `known`/`NEW`; exit status is pytest's.

---

### W3 — FALSIFIABILITY

**The no-shortcut rule** — as stated in W1's brief, in full.

You prove the new lane can fail. A cluster lane that passes without a cluster is worse than no lane,
because it converts *"we do not know"* into *"we checked"*.

**THE 2×2.** Every run asserts all four cells:

| | plant ABSENT | plant PRESENT |
|---|---|---|
| `--crdb=none` | GREEN | **GREEN** ← the defect is invisible to today's CI. This cell is the whole argument. |
| `--crdb=reuse` | GREEN | **RED** ← the new lane sees it |

The job is green only if all four hold. **If the top-right cell comes back RED, your plant is one
the hermetic lane can already see** and the lane you are validating is redundant — pick a different
plant; do not adjust the assertion.

**WHICH PLANT.** The specimen is the reverted `demo_world.sql` credential swap.
`demo_world.sql:124` enrols `digest('mainline-demo/credential/demo.signer','sha256')` = `ff356d14…`;
a worker once edited that line to the `487adc50…` constant that `_sha("cred","signer")` derives, so
a red test would go green. Your plant makes the same edit, in the runner's working copy only. It is
invisible to every hermetic test and fatal to a cluster-backed one — exactly the property the 2×2
needs.

**DO NOT plant the `transitions.py` `_sha("cred","signer")` reversion.** The ratchet
`test_no_module_derives_a_credential_id` catches it STATICALLY, with no cluster, so the top-right
cell would be red and the proof would collapse. This lead checked. Do not spend the wave
rediscovering it.

**WHICH SUBSET.** The full demo-api suite is ALREADY RED today (3 failed, 63 errors — real defects
owned by other leads), so "plant a defect and watch it go red" proves nothing against it. Run the
2×2 against a subset that is GREEN today. Measured by this lead under `--crdb=reuse`:
`test_credentials.py`, `test_gate_run.py`, `test_transitions.py` are green — with
`test_transitions.py::test_the_request_after_a_gate_run_is_not_a_503` the one unstable member
(passes alone, fails in suite). Confirm the subset yourself; if that node id is unstable, drop that
single node id with a written note, **never the assertion**. Your job must assert the
plant-absent/`reuse` cell FIRST: if it is red, stop and say the subset is no longer clean, rather
than reporting a falsifiability proof you did not make.

**HYGIENE, not optional given this repository's history.** Before planting, `git diff --exit-code`
must be clean. Plant with `scripts/ci/plant_cluster_defect.py --plant seed-credential-swap`, which
edits in place and prints the exact diff; revert with `--revert`, which restores via
`git checkout --`; then `git diff --exit-code` again, and fail the job if the tree is dirty.
**The plant is never committed.** A bites workflow that leaves a planted defect in a tree somebody
merges is the worst outcome available to this wave.

**AND ADD THE GUARD THE HISTORY DEMANDS.** `tests/ci/test_demo_seed_is_frozen.py`, marked
`@pytest.mark.frozen` (already registered in `pyproject.toml`): record the SHA-256 of
`verticals/mainline/db/seeds/demo/demo_world.sql` and `demo_permit.sql`, fail when it changes, and
write the story into the docstring — a worker edited this file so a seed would match an application
constant, three negative controls caught it, and a change here is a deliberate re-baseline that must
be argued in a commit message. The basename must be globally unique across `tests/`, `packages/` and
`verticals/` (prepend import mode names a module by its basename); `test_demo_seed_is_frozen.py` is
free, checked by this lead. No `__init__.py` — the tree does not use them.

**Fifth assertion: the inventory cannot suppress.** Plant the defect, add its node id to a COPY of
`qa/cluster-known-red.json`, and assert W2's lane still exits non-zero. If W2's report script can be
made to exit 0 that way, that is a defect in W2's design and you report it rather than working
around it.

**Done when:** all four cells asserted in one job; the fifth assertion holds; the tree is proven
clean; the frozen-seed test passes and is demonstrably red against a one-byte edit.

---

### W4 — THE RATCHET

**The no-shortcut rule** — as stated in W1's brief, in full.

You make a skipped test unable to read as green ever again, and you repair the stale declarations in
`ci.yml`.

Measured facts you may rely on (this lead, HEAD `073dfea`): whole-repo hermetic run
`1 failed, 8835 passed, 987 skipped, 15 deselected` out of `9838` collected; 973 of 987 skips name a
cluster. `ci.yml:124-129` records `13 collected / 9240 deselected`, total `9253`; measured today the
split is **`15 / 9823`, total `9838`** — the declaration is 585 tests and 2 red-by-design cases
stale. `ci.yml:601` sets `RED_FLOOR: "13"` while 15 tests now carry `g4alpha` or `pl2_red`.

**1. `scripts/qa/skip_ratchet.py` + `qa/skip-ratchet.json`.** Shape them on
`scripts/qa/ruff_ratchet.py` / `qa/ruff-ratchet.json`, this repository's established ratchet idiom:
a measured baseline, a `policy` paragraph saying why a ratchet rather than a fix, a hard gate at 0,
and a `--rebaseline` that must be argued. It consumes W1's `qa/ci-skip-census.json`, schema
`mainline.qa.ci-skip-census/1`, keys
`{collected, passed, failed, errored, skipped, deselected, argv, roots, skips:[{nodeid,file,line,reason,cluster_shaped}]}`.
Rules in order of importance:

  a. **Every cluster-shaped skip must be attributed.** `qa/skip-ratchet.json` carries
     `lanes: {"<workflow>.yml#<job>": ["<root or node-id glob>", …]}` and
     `unlanded: [{pattern, count, reason, owner}]`. A cluster-shaped skip matching neither is a HARD
     FAILURE naming the node id. **This is the rule that makes the wave permanent**: after it lands,
     adding a cluster-backed test with no lane fails the build.
  b. The total `unlanded` count is a CEILING. It may fall. It may not rise.
  c. `skipped` per root is a ceiling too.
  d. A skip with an empty reason is a hard failure regardless of count — a skip with no reason is
     indistinguishable from a deleted test.

**2. `.github/workflows/ci.yml`.** Add `scripts/qa/skip_ratchet.py` and W6's
`scripts/qa/check_pytest_lanes.py` (CLI fixed: bare invocation → exit 0/1; `--list` prints the
marker census) to the `checkers` job's declarative registry at lines 182-183 and as run steps.
Replace the `9240/13` block at lines 121-141 with freshly measured numbers — **do not delete the
superseded ones**; that file's own convention (see its `1093 / 5 / 1098` paragraph) is to record
what was measured, when, and why it changed. Raise `RED_FLOOR` 13 → 15, **but only after running
`pytest --crdb=none -m "g4alpha or pl2_red"` and confirming all 15 actually fail**. Raising a floor
is strengthening and is allowed; lowering one is not. If fewer than 15 fail, the floor stays at 13
and you report the discrepancy in `still_broken` — a floor above the observed count makes the job
red for the wrong reason. Write Contract A `hermetic` markers on all four pytest steps here. Add a
row to the `summary` table (~line 1128) for W2's cluster lane, by workflow name, so a judge reading
the summary can see a cluster lane exists.

**THE TRAP.** This lead tried to derive the skip→lane map mechanically, by checking whether a
skipped file's path or any prefix of it appears in a non-comment line of any workflow. It returned
`968 covered / 19 uncovered`, which is **nonsense**: `demo-api/tests/conftest.py` came back "covered
by eleven workflows" because the substring `verticals` occurs in eleven files. **Path-grepping
cannot answer this question.** The only sound method is to lift each lane's exact pytest argv out of
the workflow file and RUN it locally with `--collect-only -q`, recording which node ids that argv
reaches. That is 30 invocations, enumerated in §1.4 of this plan, and it is the measurement the
entire ratchet rests on. Record the argv beside every `lanes:` entry so a reader can re-run it.

Two partial findings to **confirm, not inherit**: `schema.yml` runs
`packages/trappoint-conformance/unweld` and four named files, **not**
`tests/test_conformance_cases.py`, where 181 of the 187 conformance skips live. `db-schema.yml` runs
`packages/trappoint-migrate/tests`, **not** `tests/integration/schema/*`, where roughly 250
integration skips live. So the honest first version of `unlanded` is very likely a large, named,
shrinking list — not a small one. **A short `unlanded` list is a warning sign, not a success.**

**Done when:** the ratchet is demonstrably red against a planted new cluster-backed test with no
lane; demonstrably red against a planted skip-count increase; `ci.yml`'s tally is measured;
`RED_FLOOR` is correct with evidence; both checkers run in `checkers`.

---

### W5 — THE PUBLICATION

**The no-shortcut rule** — as stated in W1's brief, in full. You run LAST.

What is stale, measured by this lead at HEAD `073dfea`: `docs/CI-STATE.md:401` says
`4 failed, 8468 passed, 839 skipped, 13 deselected`; `docs/HONESTY.md:632` says
`5 failed, 8467 passed, 839 skipped, 13 deselected`. Both sum to **9324** — the collection total from
before `verticals/*/apps/demo-api/tests` entered `testpaths`. Measured today:
**`1 failed, 8835 passed, 987 skipped, 15 deselected` out of `9838`.** `docs/HONESTY.md:362` cites
`qa/test-state.json#totals.none.skipped` = 736 and `:365` cites 43 distinct skip reasons; W1 will
have added demo-api rows to that file, so **re-derive, do not do arithmetic**.

What to publish. (1) The board gains W2's `cluster-tests` and W3's `cluster-lane-bites` with real run
ids obtained the way `CI-STATE.md` §0.1 demands: `gh workflow run`, then `gh run view <id>
--log-failed`, read warm, in one sitting, with each run's SHA checked against the tip afterwards.
(2) A new section stating the split plainly — 9838 collected, 987 skipped, 973 of them for want of a
cluster, 186 of those the demo-api suite — and the sentence that has never appeared on that page:
**no lane in this repository has ever executed a cluster-backed demo-api test.** Cite W1's
`qa/ci-skip-census.json` by key, the way §362 already cites `qa/test-state.json`. (3) The honest
reds stay red and their rows say so in the first clause; W6 is sharpening the messages inside
`custody-chain.yml`, `schema.yml` and `demo-health.yml`, and your rows must **quote the message
GitHub actually renders**, not paraphrase it. (4) `docs/ci/test-collection.md` gains the sequel: the
testpath fix landed, the suite is collected, and it still did not run — **collection is not
execution**. That is the sentence the whole wave turns on and that document is where it belongs.

Hard constraints. **`docs/HONESTY.md` may not be weakened**: a `git diff` of that file must show
only numbers replaced by freshly measured numbers, plus additions. No adjective softened, no claim
removed, no caveat deleted. If a claim there is now FALSE rather than stale, you replace it with the
true statement and say what changed — you do not delete it. **Every number is sourced to a command
run in the same sitting as the page**; that page's own §0.2 records the `tail -25` incident, where a
truncated pipeline turned five refusals into two and was caught only by re-running without the tail
against three different runs. Print the command beside the number. A recorded board is not evidence
and logs expire: re-create rather than re-read.

**Done when:** `git diff docs/HONESTY.md` shows only number replacements and additions; every table
row on `CI-STATE.md` cites a run id created in your sitting; and both the 186-of-444 and the
987-of-9838 splits are published with the commands that produced them.

---

### W6 — EVERY PYTEST STEP DECLARES ITS SIDE OF THE LINE

**The no-shortcut rule** — as stated in W1's brief, in full.

Measured by this lead: **30 pytest invocations across 9 workflow files; 5 declare a `--crdb` mode**
(4 in `ci.yml`, 1 at `release-proof.yml:289`); **25 run at the default `auto`** — "reuse a cluster
that answers, start one if none does". So 25 CI steps silently either reuse whatever is listening or
start their own container, and the file does not say which. `conftest.py`'s header records the cost:
thirteen concurrent private nodes, all exiting 7/8, taking the shared node down, and a run that
**wedged rather than failed**, with `timeout = 120` never firing because pytest-timeout's thread
method cannot interrupt a hang in session-scoped fixture setup. By file: `boundary` 7,
`custody-chain` 7, `ci` 4 (not yours), `nightly-differential` 3, `schema` 3, `db-schema` 2,
`release-proof` 2, `mutation-ratchet` 1, `supply-chain` 1.

**1.** Contract A marker on every pytest invocation in the 17 files you own.

**2.** An explicit `--crdb=` flag on every invocation — **and this is where you can do real damage,
so read it twice.** The flag you write must be the mode that lane resolves to **today**. A lane with
a `docker run` of the pinned node before its pytest step resolves to `auto`→reuse and becomes
`--crdb=reuse`. A lane with NO cluster whose tests currently start their own container resolves to
`auto`→spawn; writing `--crdb=reuse` there would turn passing tests into **SKIPS** — a silent
weakening, and precisely the "moved from INVISIBLE to SKIPPED" failure this entire wave exists to
end. That lane gets `--crdb=auto` and the `spawn` marker. **Determine the mode per lane by
measurement** — for each of the 25, record whether a `docker run -d` of the pin precedes it in the
same job — and write the finding into `docs/ci/pytest-lanes.md` **before** you touch the file. If
you cannot tell, mark it `unlanded` with a reason and leave the invocation alone.

**3. `scripts/qa/check_pytest_lanes.py`.** CLI exactly `python scripts/qa/check_pytest_lanes.py`
(exit 0/1) plus `--list`. W4 wires it into `ci.yml`'s `checkers` job, so the name and exit contract
are fixed and you may not change them. It must read workflow files as **raw text**: the marker is a
comment, PyYAML discards comments, and these files are 60% comment by volume. Rules — exactly one
marker per invocation; `hermetic` requires `--crdb=none`; `cluster` requires `--crdb=reuse` AND a
`docker run -d` of the compose pin earlier in the same job AND an executed-count assertion in that
job; `spawn` requires `--crdb=auto`; `unlanded` requires a non-empty `reason=`. `qa/pytest-lanes.json`
holds the `unlanded` ceiling and its enumerated list; the ceiling may fall, never rise.

**4.** `custody-chain.yml`, `schema.yml` and `demo-health.yml` **stay red**, with the cause in the
FIRST CLAUSE of the `::error title=` GitHub renders. Do not touch a threshold, a matrix, a selector
or an assertion in those files — message text only, plus your markers. `CI-STATE.md`'s board already
distinguishes "red on purpose" from "red on a defect"; your messages are what make that distinction
legible without opening the log.

You do **not** own `ci.yml` (W4), `cluster-tests.yml` (W2) or `cluster-lane-bites.yml` (W3); those
three write their own Contract A markers. If your checker is red against their files at the end of
the wave, **that is a real finding and you report it** — you do not edit their files and you do not
relax the rule.

**Done when:** 30 invocations carry 30 markers; the checker is demonstrably red against a
deliberately unmarked invocation and against a `cluster` marker in a job with no pinned node;
`docs/ci/pytest-lanes.md` records every lane's resolved mode BEFORE and AFTER and they are
identical; and the three honest reds are still red.
