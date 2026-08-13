<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: CC-BY-4.0
-->

# Test-blindness wave — the plan, and what the lead measured before writing it

**Lead:** TEST-BLINDNESS LEAD. **Written 2026-08-13 on TRAPPOINT**, against the working
tree at `D:/CoackroachDBxAWS/mainline`, HEAD `2dc5c86`, branch `master`, with
`.venv/Scripts/python.exe` (pytest 9.1.1). Every number in §1 is the output of a command
printed beside it. **Nothing here is carried forward from a recorded board**, and where a
previously-recorded number no longer reproduces, §1 says so.

---

## 0. The rules every analyst in this wave works under

Read this before opening a file. It is not boilerplate; a violation corrupts another
worker's commit.

1. **YOU ARE READ-ONLY.** A separate 24-worker wave is editing this repository *right
   now*. The ONLY file you may create or modify is the ONE output file named in your
   brief, under `docs/diagnosis/`. Nothing else. Not a fix, not a typo, not a
   reformat.
2. **No `git add`, `git commit`, `git checkout`, `git stash`, `git restore`,** or any
   command that changes the working tree. `git log`, `git show`, `git diff`,
   `git blame`, `git cat-file` are fine and you will need them.
3. **No `terraform apply`.** `plan`, `validate`, `show` only. No AWS call that creates,
   modifies or deletes. Read-only `aws`/`gh` calls are fine.
4. **No formatters, no `--fix`, no codemods.** Running `ruff check` without `--fix` is
   fine; running `ruff format` is not.
5. **Never print a credential** into your output or any file.
6. **You may** run `pytest` (it does not mutate tracked files), run read-only SQL, and
   `CREATE DATABASE d_<your_id>` on the LOCAL node
   (`postgresql://root@localhost:26257/defaultdb?sslmode=disable`) only.
7. **Scratch files go in your scratchpad**, never in the repo. If you need a pytest
   plugin, a tracer or a script, write it to the scratchpad and reach it with
   `PYTHONPATH` (Windows separator is `;`) and `-p yourplugin`. Do not add a file to
   the repo to make a measurement possible.
8. **Your deliverable is evidence, not a fix.** Naming a defect precisely — file:line
   on *each* side of the divergence, the command, its real output, the failure a judge
   would see, an honest severity — is worth more than repairing it.
9. **A clean slice is a real result.** If your subject area holds nothing, say so
   plainly and show the sweep that establishes it. Inventing findings to look busy is
   the worst possible outcome of this wave.
10. **The tree moves under you.** Re-measure rather than trusting §1, and if a number
    below no longer reproduces, report the discrepancy — that is itself a finding.
11. **Rank honestly.** Severity ladder used across this wave:
    **CRITICAL** = a judge or a user hits a wrong answer or a 500 on the deployed demo;
    **HIGH** = a green check asserts nothing, so a real defect of this class could ship
    unnoticed today; **MEDIUM** = a real weakness with a plausible path to a wrong
    green; **LOW** = a latent trap that needs another change to bite; **COSMETIC** =
    wording, naming, tidiness. A cosmetic mismatch filed as CRITICAL costs the next
    wave more than it saves.

---

## 1. What the lead measured, so nine analysts do not re-derive it

### 1.1 The collection hole named in the brief is **CLOSED at HEAD**. Do not re-report it.

```
$ .venv/Scripts/python.exe -m pytest --collect-only -q | tail -1
9670 tests collected in 19.11s
```

`pyproject.toml:129-134` now reads

```toml
testpaths = ["tests", "packages", "verticals/*/packages/*/tests",
             "verticals/*/apps/demo-api/tests"]
```

and a file-level census confirms the declaration is now complete:

```
$ pytest --collect-only -q | grep '::' | sed 's|::.*||' | sort -u   -> 375 files
$ find . -name 'test_*.py' (excluding .venv, node_modules, .git)    -> 375 files
$ comm -13 collected onDisk                                          -> (empty)
```

**Every `test_*.py` on disk is collected by a default `pytest`.** The 228-test
`verticals/mainline/apps/demo-api/tests` hole, including the 627-line
`test_row_factory_contract.py`, is fixed. `test_refusal_row_factory.py` now exists
beside it. So does a rewritten `verticals/mainline/apps/demo-api/tests/conftest.py`
(1143 lines) whose docstring states it applies `demo_world.sql` + `demo_permit.sql`
through `scripts/deploy/seed_demo.py`'s own `apply_seeds`, which closes the beat-4
signer-FK seam for that suite.

**The consequence for this wave:** the question is no longer *"what is not
collected?"* — it is **"what is collected and still cannot fail?"** Slices W1 and W2
still verify the collection/selection story end to end, because file-level parity is
not nodeid-level parity, but the headline defect is spent. Spend your effort past it.

### 1.2 Nobody has ever measured line coverage of this repository.

```
$ .venv/Scripts/python.exe -c "import importlib.util as u; \
  [print(m, bool(u.find_spec(m))) for m in ['coverage','pytest_cov','mutmut','xdist']]"
coverage False
pytest_cov False
mutmut False
xdist False

$ grep -n 'coverage\|pytest-cov' pyproject.toml uv.lock   ->   (no matches)
```

Not installed, and **not in `uv.lock`** — so it has never been installed in CI either.
The founder's question *"what fraction of production code paths does the collected
suite actually execute?"* has, at HEAD, **no answer and no instrument**. Against
**680 non-test `*.py` files / 175,154 lines** under `packages/` + `verticals/`.

`mainline-mutation` is **not** a substitute: its `operators/`, `paraphrase.py` and
`lattice_injection.py` mutate *domain semantics and hand-authored cassettes*, not
source. `mutation-ratchet.yml` therefore measures whether the nine-rule lattice
catches weakened obligations — a real and good measurement — and measures **nothing**
about whether the Python suite would notice a changed line of `refusal.py`.

**There is no code-coverage instrument and no source-mutation instrument in this
repository.** Those are exactly the two instruments that make "the suite agrees with
the code because both are wrong" visible. W3 and W10 own the consequence.

### 1.3 CI's hermetic lane runs with **no cluster**, and the skip fraction is unpublished.

`.github/workflows/ci.yml:487,522,634` all run
`uv run --frozen --all-packages pytest --crdb=none …`.
`packages/trappoint-testkit/src/trappoint_testkit/plugin.py:172-174` — `--crdb=none`
means *"do not look, and make sure nothing else does either. Every cluster-backed test
… skips."* The lane splits on `RED_SELECTOR: "g4alpha or pl2_red"` (`ci.yml:142`), and
the comment at `ci.yml:124-125` records `9240 / 13` as measured on 2026-08-10 — a tally
taken **before** the 430-test growth to 9670, so it is already stale.

The lead started the real measurement:

```
$ .venv/Scripts/python.exe -m pytest --crdb=none -m "not (g4alpha or pl2_red)" -q -rs
```

and abandoned it as a lead-level task: **no `pytest-xdist`**, 16 CPUs unusable, a
24-worker wave saturating the box, and the run was at **4 % after ~10 minutes** —
roughly four hours wall-clock. **Timing numbers taken today are worthless**; do not
report wall-clock as a finding. Do report *counts*. W2 owns getting the pass/skip
split by the cheapest correct method (§W2 suggests two).

Statically, across `tests packages verticals`:

```
importorskip      85        pytest.skip(     159
skipif            20        xfail             18
mock/monkeypatch  54        conftest.py       55  (8,360 lines total)
```

### 1.4 5,176 test functions; **107 assert nothing**.

An AST sweep (scratchpad script, not committed) over every `def test_*` in
`tests/ packages/ verticals/`:

```
TOTAL test funcs: 5176
NO assert and NO pytest.raises/warns/deprecated_call: 107
```

Concentrated in `tests/boundary/` (≈46), `tests/integration/custody/`,
`tests/security/injection/`, `tests/unit/`. Many will delegate to a `_assert_*` helper
or `pytest.fail` and be perfectly sound — **the count is a starting list, not a finding
list**. W7 owns triaging all 107 individually and reporting the residue.

### 1.5 Thirteen shipped packages carry no in-package `tests/`.

```
packages/trappoint-recall
verticals/mainline/packages/{mainline-archivist, mainline-cartographer,
  mainline-cherrypick, mainline-corpus, mainline-delta-oracle, mainline-domain,
  mainline-fixity, mainline-mutation, mainline-quarantine, mainline-recall-agent,
  mainline-recall-fleet, mainline-steward}
verticals/mainline/apps/steward
```

Most are covered from the root `tests/` tree (`tests/unit/domain/…`,
`tests/unit/fixity/…`, `tests/unit/cartographer/…`). **Which are genuinely uncovered
is a measurement, not an inference** — W3 owns it.

### 1.6 CI: eighteen workflows, 12,334 lines, and the repository's own census says
eight lanes cannot prove they can fail.

`docs/ci/anti-vacuity.md` (2026-08-10) already carries a per-workflow negative-control
census and states: *"Seven lanes have a standing negative control after this wave,
against three before it. Eight of the eighteen workflows still have none."* Named as
having **none**: `ci`, `db`, `db-schema`, `custody-chain`, `schema`,
`nightly-differential`, `demo-health`; `boundary` is "partial"; `submission` is
"not examined". **W8 does not rewrite this census — W8 verifies it and extends it to
the axes it does not cover**: `paths:` filters, `if:` guards, `needs:` wiring, exit
codes captured into shell variables, missing `pipefail`, matrices that expand to zero.
Two facts the lead already has for W8:

- `grep -F 'continue-on-error' .github/workflows/*.yml` → **three hits, all inside
  prose or a summary string**; none is a real key. The ban holds at HEAD.
- Most lanes are `paths:`-filtered on push. `schema.yml:85-91` has **`pull_request:`
  with paths and no `push:` trigger at all**. `cloud-verify.yml` and `demo-health.yml`
  deliberately have no `push:` and say why. A path filter is a green that means
  "nothing ran" *by design* — the question W8 must answer is whether any filter
  excludes a path whose change could break that lane.

### 1.7 Where the two runtimes are.

Python: 375 test files / 9,670 nodeids. TypeScript: `verticals/mainline/apps/console`
is a pnpm workspace with its own `vitest.config.ts` and
`tests/{browser,unit/{a11y,ancestry-3d,app,data,design,diff,evidence,gate,perf,propagation,silence,verify},vectors}`,
driven by `pnpm run ci` in `console.yml`. It is deliberately outside `testpaths`
(pointing pytest at it would walk `node_modules/`) and it is **shipped product** — the
console is what a judge opens. Its coverage belongs to W3, its lane wiring to W8.

---

## 2. The shape, restated so ten briefs can be checked against it

> **A test agrees with the code because both draw on the same constant, the same
> module, or the same convenience path — and both diverge from what is actually
> deployed.**

Three known instances, and the *reason each was invisible*, which is the part that
generalises:

| # | Defect | Why the suite could not see it |
|---|---|---|
| 1 | `transitions._demo_guard` armed at a uuid5 nothing seeds; real permit is `dec0de00-…-0001` | **both 423 tests set the env var themselves first** — the test supplied the precondition the deployment does not |
| 2 | `refusal.py:235` `row[0]` vs `db.py:309` `row_factory=dict_row` | **tests connected with `tuple_row`** — the fixture chose a connection shape production never uses |
| 3 | `gate_run._DISPOSITION_SQL` `sha256("cred"+"signer")` vs `demo_world.sql` `digest('mainline-demo/credential/demo.signer')` | **291 tests ran against the proof seeder, which shares `gate_run`'s constants** — the world under test was built by the code under test |

Note the three are *distinct sub-shapes*: (1) the test supplies a precondition,
(2) the fixture substitutes a convenience path, (3) the expected value and the actual
value have one source. The ten slices below are cut so that each sub-shape has an owner
and no two analysts hunt the same sub-shape.

---

## 3. The ten slices

Each analyst writes **exactly one** file under `docs/diagnosis/`. Subject areas are
disjoint; where two touch, the boundary is stated explicitly in both briefs. Every brief
carries §0 by reference — **read §0 first**.

| id | title | output file |
|---|---|---|
| W1 | Collection & selection: every nodeid that never executes anywhere | `docs/diagnosis/collection-and-selection.md` |
| W2 | Skips, gates and lanes that run nothing | `docs/diagnosis/skips-and-silent-passes.md` |
| W3 | Executed-code coverage, both runtimes | `docs/diagnosis/executed-code-coverage.md` |
| W4 | Fixture world vs deployed world | `docs/diagnosis/fixture-vs-deployed-world.md` |
| W5 | Shared-constant collusion | `docs/diagnosis/shared-constant-collusion.md` |
| W6 | Mocks, doubles, cassettes and goldens | `docs/diagnosis/mocks-and-cassettes.md` |
| W7 | Tautologies: assertions that cannot fail on their own terms | `docs/diagnosis/tautological-tests.md` |
| W8 | CI lane vacuity: greens that mean nothing ran | `docs/diagnosis/ci-lane-vacuity.md` |
| W9 | Verifier circularity: do the checkers re-derive, or re-read? | `docs/diagnosis/evidence-verifier-circularity.md` |
| W10 | The counterfactual, and the smallest enforceable ruleset | `docs/diagnosis/structural-rules.md` |

**The boundaries, stated once, so nobody duplicates:**

- **W1 vs W2.** W1 owns *not collected* (deselection, ignore, path, config). W2 owns
  *collected then not executed* (skip, xfail, gated fixture).
- **W5 vs W7.** W5 owns collusion where the expected value's origin is **outside the
  test** — the module under test, a shared constant, a helper both sides import.
  W7 owns tautology where the origin is **inside the same test function or its own
  fixture**. If a test both sets a value and imports the constant, it belongs to W5.
- **W4 vs W6.** W4 owns *world construction* — DSNs, seeds, migrations, row factories,
  transaction state, cluster mode. W6 owns *behaviour substitution* — mocks,
  monkeypatched functions, fakes, recorded cassettes, golden files.
- **W8 vs W9.** W8 owns the **YAML**: triggers, filters, conditions, job graph, exit
  codes. W9 owns the **checkers those jobs invoke**: whether the program actually
  re-derives the fact or re-reads the file that asserted it.
- **W3 vs everyone.** W3 produces *numbers* (what executed). Everyone else produces
  *defects*. If W3 finds an uncovered module that is also a defect, W3 names it and
  points at the owning slice rather than analysing it.

---

### W1 — Collection & selection: every nodeid that never executes anywhere

**Output: `docs/diagnosis/collection-and-selection.md`**

Read §0. You are read-only; another wave is editing this repository right now; your
only writable file is the one above.

§1.1 establishes that all 375 `test_*.py` on disk are collected by a default `pytest`
at HEAD. **File-level parity is not nodeid-level parity, and a default `pytest` is not
the command CI runs.** Your job is to close that gap completely and to prove there is
no second, subtler exclusion of the same class.

Enumerate and check, each with file:line: `pyproject.toml` `testpaths`, `addopts`,
`norecursedirs`, `python_files`/`python_classes`/`python_functions`, `--strict-config`,
`--strict-markers`, `filterwarnings` (a `filterwarnings = ["error"]` entry can turn a
collection warning into a silent module-level error — check `-W` interactions); the
**sixteen per-package `pyproject.toml` `testpaths` declarations** listed in §1.5's
sibling grep (`packages/*/pyproject.toml`, `verticals/mainline/apps/demo-api:78`,
`verticals/mainline/packages/*`) and whether any of them shadows or contradicts the
root when someone runs `pytest` from inside that package or via
`uv run --package <name> pytest`; every `collect_ignore`, `collect_ignore_glob`,
`pytest_ignore_collect`, `pytest_collection_modifyitems` and `pytest_collectstart`
hook across the **55 `conftest.py`** files (`verticals/mainline/apps/demo-api/tests/conftest.py:133,139`
has both hooks — read what they do); every `--deselect`, `--ignore`, `-k` and `-m` in
`.github/workflows/`, `justfile`, `scripts/`, `qa/`, and any `Makefile`. **The
previously-found inert `--deselect` — a nodeid prefix that did not match because
rootdir resolution differed — is the exact failure mode to hunt: for every selector
you find, prove by running it that it selects the set its author intended, and report
the count it actually removes.**

Then do the nodeid-level census: `pytest --collect-only -q` for (a) the default
invocation, (b) `--crdb=none`, (c) `-m "not (g4alpha or pl2_red)"`, (d)
`-m "g4alpha or pl2_red"`, and (e) each per-package invocation CI uses. Assert that
(c) and (d) are exact complements of (a) — `ci.yml:124-125` claims they are, at a
tally that predates 430 new tests. Report any nodeid in (a) that is in neither.

Also check: duplicate test module basenames under `prepend` import mode (there is a
guard, `tests/release/test_no_duplicate_test_basenames.py` — verify it is not itself
vacuous, then hand it to W7 if it is); classes named `Test*` with `__init__` (pytest
silently skips them); parametrize ids that collapse; and any `test_*.py` outside the
four roots that a future move would strand. Finish with **one table: every declared
exclusion, its file:line, the nodeids it removes, and whether that removal is
intentional and correct.**

**Done when:** the table exists, every selector has a measured removal count, and you
can state — with the command — either "no nodeid on disk fails to execute in every
lane" or the exact list that does.

---

### W2 — Skips, gates and lanes that run nothing

**Output: `docs/diagnosis/skips-and-silent-passes.md`**

Read §0. Read-only; concurrent wave; one output file.

W1 owns tests that are never *collected*. **You own tests that are collected and then
do not run** — and the headline number the founder asked for: of the 9,670 collected
nodeids, how many actually **execute** in the lane CI runs?

CI's hermetic lane is `pytest --crdb=none -m "not (g4alpha or pl2_red)"`
(`ci.yml:522`). `trappoint_testkit/plugin.py:172-174` makes `--crdb=none` skip every
cluster-backed test. §1.3 records that a full local run is ~4 hours today (no
`pytest-xdist`, 16 cores unusable, a 24-worker wave on the box). **Do not block on a
full run and do not report wall-clock times.** Two cheaper routes, use at least one and
say which: (i) run the suite **directory by directory** in parallel Bash calls,
collecting only the `N passed, M skipped` tally lines; (ii) write a scratchpad pytest
plugin implementing `pytest_report_teststatus`/`pytest_runtest_logreport` that appends
one line per outcome to a file, load it with `PYTHONPATH=<scratchpad>;… -p yourplugin`,
and run with `--co`-free but `-p no:cacheprovider`. Either way publish **passed /
skipped / xfailed / errored, and the skip reason histogram**, for both `--crdb=none`
and a run against the live local node.

Then audit every gate individually: **85 `importorskip`, 159 `pytest.skip(`, 20
`skipif`, 18 `xfail`**, plus the markers `requires_cluster`, `requires_aws`, `db`,
`schema`, `integration`, `slow`, `g4alpha`, `pl2_red` and every `pytest_runtest_setup`
hook in the 55 conftests (root `conftest.py:285` has one). For each, answer the
question that matters: **is this condition ALWAYS true in the lane that collects the
test?** An `importorskip("boto3")` in a lane that never installs `boto3` is a test that
has never run and never will; a `skipif(not os.environ.get("X"))` where no lane sets
`X` is the same defect wearing a different hat. Cross-reference each condition against
what `ci.yml`, `db.yml`, `db-schema.yml`, `boundary.yml`, `custody-chain.yml` and
`schema.yml` actually install and export.

Pay specific attention to: skips whose reason string is empty or generic; `xfail`
without `strict=True` (an xfail that starts passing is silent); `pytest.skip` called
from inside a fixture at *session* scope (skips a whole tree at once); and any test
that ends in a bare `return` under a condition, which is an undeclared skip that
reports as **passed**. That last pattern is the worst one — grep for it.

**Done when:** the pass/skip/xfail tally is published with the command that produced
it, and every one of the ~282 gate sites is classified as *sound*, *always-skips-in-
its-lane*, or *undeclared skip reporting as pass*, with file:line.

---

### W3 — Executed-code coverage, both runtimes

**Output: `docs/diagnosis/executed-code-coverage.md`**

Read §0. Read-only; concurrent wave; one output file. **You produce numbers, not
defect analyses** — when a number implicates a specific divergence, name it and point
at W4/W5/W6 rather than analysing it yourself.

§1.2 is your starting fact: **`coverage`, `pytest-cov`, `mutmut` and `pytest-xdist`
are all absent from the venv AND from `uv.lock`.** Line coverage of this repository has
never been measured, against 680 non-test `*.py` files and 175,154 lines. **Do not `pip
install` anything** — that mutates the shared `.venv` another wave is using. Use the
standard library: `sys.monitoring` (3.12+) or `sys.settrace`/`threading.settrace` in a
scratchpad pytest plugin loaded via `PYTHONPATH` + `-p`, recording executed
`(filename, lineno)` pairs to a scratchpad file. Verify your tracer against a file you
know is executed and one you know is not, and publish that calibration — an
uncalibrated coverage number is exactly the kind of unfalsifiable claim this wave
exists to eliminate.

Report, at minimum: **module-level** coverage (which of the 680 files had zero lines
executed) for the hermetic lane and, separately, for a run against the live local node;
then **function-level** for the modules that matter most —
`verticals/mainline/apps/demo-api/src/mainline_demo_api/*` (12 modules: `app.py`,
`credentials.py`, `db.py`, `envelope.py`, `gate_run.py`, `health.py`, `reads.py`,
`refusal.py`, `scenario.py`, `static_site.py`, `transitions.py`), and
`verticals/mainline/packages/mainline-gate-svc`. For the demo API specifically:
`app.py` is a **Lambda-style dispatcher** (it reads `event["requestContext"]["http"]`,
`rawPath`, `httpMethod` — see `app.py:231-272`), so enumerate its route table and
report, per route × method, whether any collected test reaches the handler **through
the dispatcher** rather than by calling the handler directly. A route reachable only by
direct call is a route whose dispatch, envelope and error mapping are untested — that
is precisely how the four committing kernel POSTs stayed open.

Second runtime: `verticals/mainline/apps/console`. It has `vitest.config.ts` and a
populated `node_modules/`. Run its coverage the way the project already can
(`pnpm vitest run --coverage` if a provider is present; if none is, **say so — "the
console has never had its coverage measured either" is a finding**) and report per-file
zero-coverage for `src/`. Do not `pnpm install`; do not touch the lockfile.

Finally, resolve §1.5: for each of the 13 packages with no in-package `tests/`, state
whether it is covered from the root `tests/` tree and at what module-level percentage,
or genuinely at zero. `mainline-quarantine`, `mainline-delta-oracle` and
`mainline-recall-agent` are the ones the lead most expects to be surprising.

**Done when:** a table of every source file with zero executed lines exists, the
tracer's calibration is shown, the demo-API route × method matrix is complete, and the
console's number is either measured or its absence is stated.

---

### W4 — Fixture world vs deployed world

**Output: `docs/diagnosis/fixture-vs-deployed-world.md`**

Read §0. Read-only; concurrent wave; one output file.

You own **world construction**: every way a test's database, connection, schema, seed
or transaction state can differ from what is actually deployed. This is sub-shape (2)
and (3) from §2 — the `dict_row` 500 and the beat-4 signer FK. W6 owns behaviour
substitution (mocks, cassettes); leave those alone.

Start from the seam that already bit twice. `verticals/mainline/apps/demo-api/src/mainline_demo_api/db.py:309`
opens production connections with `row_factory=dict_row`. Sweep **every** fixture and
helper in the 55 `conftest.py` files and in `packages/trappoint-testkit` that opens a
psycopg connection, and record its `row_factory`, its `autocommit`, its isolation
level, its `application_name` and whether it wraps in a transaction the production path
does not. Any connection built with psycopg's default `tuple_row` while the production
path for that code is `dict_row` (or the reverse) is a finding, with both file:lines.
The brief also records that `transitions._prepare` / `_demo_gate_run` set
`conn.autocommit = False` on the shared connection and never restore it — check whether
any fixture masks that by handing out a fresh connection per test where production
reuses one.

Then the seeds. There are three worlds in this repository and they must be one:
`verticals/mainline/db/seeds/demo/{demo_world,demo_permit}.sql` (what
`scripts/deploy/seed_demo.py` applies to Cloud `mainline_demo`), the migration tree
`verticals/mainline/db/migrations/`, and whatever the proof/testkit seeders build.
§1.1 records that `verticals/mainline/apps/demo-api/tests/conftest.py` was rewritten to
call `seed_demo.apply_seeds` rather than restate it — **verify that claim by running
it**, and then ask the same question of every *other* suite: `tests/integration/`,
`tests/concurrency/`, `tests/release/`, `packages/trappoint-conformance`,
`verticals/mainline/packages/mainline-gate-svc/tests`. For each, name the seeder it
uses and diff the identifiers that seeder produces against `demo_world.sql`'s. The
signer-credential id is the known instance (`sha256("cred"+"signer")` = `487adc50…`
vs `digest('mainline-demo/credential/demo.signer')` = `ff356d14…`) — **look for the
others**: permit ids, obligation ids, commit ids, epoch pins, schema ids, decision
classes, retention classes, clearance levels.

Also check: `--crdb=auto|reuse|spawn|none` — does `reuse` against a database left over
from a previous run hand a suite a world it did not build (the fingerprint marker table
`w3_fixture.ready` is meant to prevent this; verify it does)? Does any fixture
`CREATE TABLE`/`INSERT` a row the deployed seed does not carry, which the demo-api
conftest explicitly forbids at its `_Seed.__missing__`? And do the local node
(v26.2.5, single node, `defaultdb`) and Cloud `mainline_demo` (Basic, aws-ap-southeast-1,
needs a 40001 retry loop, vector index only when hinted, `SEQUENCE`/`SERIAL`/
`unique_rowid()` banned, `FAMILY` reserved) differ in a way any fixture assumes away?

**Done when:** one table of every connection-opening fixture with its row factory /
autocommit / seeder, one table of every identifier that two worlds derive differently,
and a plain verdict on whether the demo-api conftest's "one world" claim holds.

---

### W5 — Shared-constant collusion

**Output: `docs/diagnosis/shared-constant-collusion.md`**

Read §0. Read-only; concurrent wave; one output file.

You own the purest form of the shape: **an assertion whose expected value is computed
by the same code that produces the actual value.** The boundary with W7: if the
expected value originates *outside the test function* — imported from the module under
test, imported from a constants module both sides share, or recomputed by a helper that
mirrors the production formula — it is yours. If it originates *inside the same test
function or its own fixture*, it is W7's. If both, it is yours.

The mechanical sweep that finds these: for every `assert <actual> == <expected>` in the
375 test files, resolve where `<expected>` comes from. Three patterns to hunt by name.
**(a) Imported constant.** `from mainline_demo_api.gate_run import _DISPOSITION_SQL`
and then asserting a hash that `_DISPOSITION_SQL` computed. Grep for test modules
importing private names (`_`-prefixed) from the module they test — that is the loudest
signal. **(b) Recomputed formula.** The test spells `sha256(b"cred" + b"signer")` or
`uuid5(NS, ...)` itself, matching the production line character for character; both are
wrong together the moment the deployed artefact uses a different derivation. The known
instances are the permit-id `uuid5` default in `scenario` and the signer credential id
in `gate_run._DISPOSITION_SQL`; grep the whole tree for `uuid5`, `sha256`, `blake2`,
`digest(`, `hexdigest`, `NAMESPACE_` and classify every co-occurrence in a test.
**(c) Round-trip identity.** `assert decode(encode(x)) == x` proves the pair is
self-consistent and proves nothing about the wire format a judge's browser sees — this
is endemic in JCS/canonicalisation suites (`packages/trappoint-jcs`), envelope suites
(`envelope.py`), and schema-id suites. For each, the fix-shape is a committed vector
file; report whether one exists.

For every finding, the report must show **both sides**: the production file:line that
computes the value, the test file:line that asserts it, and — decisively — **a third,
independent source of truth**, which is what makes it a defect rather than a style
note. For identifiers, that third source is `verticals/mainline/db/seeds/demo/*.sql`,
the live Cloud `mainline_demo` database, or the bytes the public hostname serves at
`/bundle/manifest.json`. If you cannot name a third source, the finding is at most
MEDIUM and you must say why.

Also sweep the error contract: HTTP status codes, `SQLSTATE`s (`23514`, `P0001`,
`00000`, `23503`, `40001`, `423`, `422`), refusal reason strings, and `schema_id`
values. `app.py:455,523` reference `SCHEMA_IDS.get(matched.key)` — check whether any
test asserts a schema id by importing `SCHEMA_IDS` rather than against the committed
contract under `verticals/mainline/apps/demo-api/contracts/`.

**Done when:** every co-occurrence of a derivation primitive in a test is classified,
and each finding names production line, test line, and independent third source.

---

### W6 — Mocks, doubles, cassettes and goldens

**Output: `docs/diagnosis/mocks-and-cassettes.md`**

Read §0. Read-only; concurrent wave; one output file.

You own **behaviour substitution**: anything that replaces a real callable, a real
service or a real response with a stand-in. W4 owns world construction (connections,
seeds, schema); do not duplicate it.

The static starting set is 54 sites matching `unittest.mock` / `MagicMock` /
`monkeypatch.setattr` across `tests packages verticals` — plus everything that grep
misses: `monkeypatch.setenv`, `monkeypatch.setitem`, `monkeypatch.delattr`,
`unittest.mock.patch` used as a decorator, `pytest.MonkeyPatch()` used directly,
hand-rolled fake classes, `botocore.stub.Stubber`, `responses`/`httpx` transports, and
recorded cassettes. For each, answer one question: **is the thing being replaced a
collaborator, or is it the subject?** A test that patches
`mainline_demo_api.transitions._demo_guard` and then asserts the guard fires has
asserted nothing about the guard. Report every case where the patch target and the
module under test are the same module.

The second question, which caught defect #1: **does the test supply a precondition the
deployment does not?** `monkeypatch.setenv` is the specific weapon —
`MAINLINE_DEMO_PERMIT_ID`, `MAINLINE_DEBUG` (`app.py:477`), `TRAPPOINT_DSN`,
`CRDB_CLOUD_DSN`, any `MAINLINE_*` / `TRAPPOINT_*` / `AWS_*`. For **every**
`setenv`/`delenv` in the tree, determine whether the deployed Lambda / the deployed
demo actually has that variable set, and to what. A test that sets an env var the
deployment leaves unset is testing a configuration that does not exist. Cross-check
against `infra/` (terraform `environment` blocks) and `scripts/deploy/`. **Publish the
full env-var table: name, who sets it in tests, who sets it in production, default in
code.** That table alone would have caught the permit-id near-miss.

Third: recorded artefacts. `tests/unit/domain/resolution/test_oracle_cassettes.py`,
`mainline-mutation`'s hand-authored cassettes, `verticals/mainline/apps/console/fixtures/`
and `tests/vectors/`, and any `*.golden`, `*.expected`, `*.snap` file. For each, find
out **who generated it**. A golden produced by running the code it now pins is a
regression detector, not a correctness check — that is legitimate, but it must be
labelled, and any lane that presents it as a correctness proof is a finding. A cassette
hand-authored from a real recorded response is much stronger; say which each one is,
with the commit that introduced it (`git log --diff-filter=A -- <path>`).

**Done when:** every substitution site is classified subject/collaborator, the env-var
table is complete on both sides, and every recorded artefact has a named provenance.

---

### W7 — Tautologies: assertions that cannot fail on their own terms

**Output: `docs/diagnosis/tautological-tests.md`**

Read §0. Read-only; concurrent wave; one output file.

You own tests that cannot fail for reasons **internal to the test**. Boundary with W5:
if the expected value comes from outside the test function, it is W5's; if the test
sets it, computes it, or asserts a property of a literal it just wrote, it is yours.

§1.4 hands you the first list: **107 of 5,176 `def test_*` functions contain no
`assert` and no `pytest.raises`/`warns`/`deprecated_call`**, concentrated in
`tests/boundary/` (≈46 — `test_ci_greps.py`, `test_e1_iam.py`, `test_e2_network.py`,
`test_e4_egress.py`, `test_fleet_matrix.py`), plus `tests/integration/custody/test_k2_exit.py`,
`tests/security/injection/test_layers.py`, `tests/concurrency/test_single_merge.py`,
`tests/release/test_no_duplicate_test_basenames.py`. **Triage all 107 individually.**
Most will delegate to a `_assert_*` helper or call `pytest.fail` — those are sound and
you should say so in one line each. The residue is the finding. Reproduce the sweep
yourself (an AST walk over `def test_*` in `tests/ packages/ verticals/`) rather than
trusting the count; the tree is moving.

Then the harder patterns, which no single grep finds — build an AST sweep for each and
publish the sweep:

- `assert x == x`, `assert True`, `assert 1`, `assert isinstance(x, X)` as the *sole*
  assertion, `assert x is not None` as the sole assertion on a value the test just
  constructed.
- **Assert-on-own-input:** the test writes `d = {"k": 1}`, passes `d` through a
  function, and asserts `result["k"] == 1`. Formally: the expected expression's free
  names all trace back to literals assigned earlier in the same function body.
- `try: … except Exception: pass` inside a test, and `except Exception: pytest.skip()`
  — a swallowed failure that reports green.
- A `with pytest.raises(Exception):` so wide that an `ImportError` or `TypeError` from
  a typo satisfies it. Report every `pytest.raises` whose exception class is
  `Exception`, `BaseException`, or has no `match=`.
- Loops that may iterate zero times around the only assertion (`for x in things:
  assert …` where `things` can be empty) — the classic vacuous truth. Check whether the
  test asserts `things` is non-empty first.
- `@pytest.mark.parametrize` with an empty or conditionally-empty argument list.
- Tests whose body is `pass`, `...`, or only a docstring.
- Helpers named `_assert_*` that contain no `assert` — the delegation that goes nowhere.

For every finding give file:line, the reason it cannot fail, and — the decisive
evidence — **a one-line mutation you did NOT apply that the test would not catch**,
stated as a sentence (e.g. "inverting the comparison at `refusal.py:212` leaves this
test green"). Do not edit the file to prove it; describe it. Rank by whether the
untested behaviour is on a deployed path.

**Done when:** all 107 are triaged, each additional AST sweep is published with its
hit count, and each surviving finding carries its un-caught mutation sentence.

---

### W8 — CI lane vacuity: greens that mean nothing ran

**Output: `docs/diagnosis/ci-lane-vacuity.md`**

Read §0. Read-only; concurrent wave; one output file. Read-only `gh` calls are
allowed and encouraged.

You own the **eighteen workflow YAML files** (12,334 lines) — triggers, filters,
conditions, the job graph, and shell wiring. W9 owns the *checkers* those jobs invoke;
when a checker is weak, name it and hand it to W9.

**Do not rewrite `docs/ci/anti-vacuity.md`.** It already carries a per-workflow
negative-control census (2026-08-10) whose own verdict is *"Eight of the eighteen
workflows still have none"* — naming `ci`, `db`, `db-schema`, `custody-chain`,
`schema`, `nightly-differential`, `demo-health` as having no negative control,
`boundary` as partial, `submission` as unexamined. **Verify that census against HEAD
and report every row that has changed**, then extend it along the axes it does not
cover:

1. **Triggers and path filters.** Most lanes are `paths:`-filtered on push.
   `schema.yml:85-91` has `pull_request:` with paths and **no `push:` trigger at all**.
   `cloud-verify.yml:52` and `demo-health.yml:104` deliberately have no `push:` and
   document why — do not "fix" them, but do check the documented reason still holds.
   For every `paths:` filter, ask: **is there a file whose change could break this lane
   and that the filter excludes?** A lane that does not run when its subject changes is
   a green that means nothing ran. Test-file paths, `conftest.py`, `pyproject.toml` and
   `uv.lock` are the usual omissions.
2. **Shell wiring.** GitHub's default bash shell runs with `-e` but **not**
   `-o pipefail` unless declared. Grep every `run:` block for a pipeline whose verdict
   is the last command (`… | tee`, `… | head`, `… | grep`) and report each one whose
   real exit code is discarded. `ci.yml:488,635` capture pytest's exit into
   `code=$?` — trace every such variable and prove the job actually fails on the bad
   values. `ci.yml:642-662` does this well; find the places that do not.
   §1.6: `continue-on-error` and `|| true` appear **only in prose** at HEAD — confirm
   and say so, because a clean sweep is a real result.
3. **Job graph.** Every `needs:`, every `if:` (especially `if: always()`,
   `if: success()`, `if: github.event_name == …`), every `outputs:` consumed by a later
   job. A job that reads `needs.x.outputs.verdict` and only fails on the literal
   `"fail"` passes when the producer crashed and emitted nothing. Every matrix — does
   any expand to zero entries, which GitHub reports as success?
4. **Assertions that cannot fail.** Steps that `echo` a claim into
   `$GITHUB_STEP_SUMMARY` without checking it (`ci.yml:1128-1135` prints a table of
   tallies — are those tallies *asserted* anywhere, or only printed?). Steps that
   upload an artifact nobody downloads. `grep -c` used where `grep -q` was meant.
   Assertions on a file that the step itself just wrote.
5. **The console lane.** `console.yml` has a strong negative control
   (`RED — pnpm run ci fails on every planted violation family`, seven families).
   Verify the green half actually runs `vitest` and that `pnpm run ci` chains with
   `&&` rather than `;` — check `verticals/mainline/apps/console/package.json`'s `ci`
   script character by character. A `;`-chained script reports the last command's
   status only.
6. **Required checks.** With read-only `gh`, report which of the 18 lanes are
   branch-protection required checks on `master`, and which are decorative. A lane
   nobody requires is a lane that can be red forever. Known intentional reds:
   `custody-chain` 7/16, `schema`, `demo-health` — treat those as correct and say so.

**Done when:** the anti-vacuity census is re-verified row by row against HEAD, each of
the six axes above has a published sweep, and every finding names workflow:line and the
green a maintainer would misread.

---

### W9 — Verifier circularity: do the checkers re-derive, or re-read?

**Output: `docs/diagnosis/evidence-verifier-circularity.md`**

Read §0. Read-only; concurrent wave; one output file.

W8 owns the YAML. **You own the programs the YAML invokes, and the committed artefacts
they check.** The question is one sentence: **does this checker independently re-derive
the fact, or does it re-read the file that asserted it?** A verifier that opens
`evidence/foo.json`, reads `"verdict": "PASS"`, and exits 0 is the shape of §2 wearing
a verifier's clothes — the artefact and the check have one source.

Subjects, each with its lane: `scripts/aws/verify_evidence.py` (`aws-evidence.yml` —
stdlib-only, hermetic, with a planted-defect job); the judge-pack validator
(`judge-pack.yml`, 9 pack mutations + an envelope job); the claim-hygiene scanner
(`claims.yml`, 21 rules, `--self-test` plants 4); `submission.yml`'s gate (recorded as
**not examined** by the anti-vacuity census — examine it); `release-proof.yml`'s proof
runner; `skills.yml`'s spec conformance and marketplace checks; `boundary.yml`'s
grep-based E1–E4 checks and `tests/boundary/test_ci_greps.py`; `scripts/mi_ratchet.py`
(MI01–MI30, and the `pl2-red` marker text it shares verbatim with
`pyproject.toml:markers` — a shared string is exactly the collusion shape, so check
whether anything actually asserts the two agree); `supply-chain.yml`'s closure check;
and `scripts/proof/`, `scripts/chain/`, `scripts/custody/`, `scripts/demo/`,
`scripts/qa/`, `scripts/submission/`.

For each checker, report four things. **(1) Source of truth**: what does it compare
against — a recomputation, a second independent implementation, a committed vector, or
the same file? **(2) Negative control**: does a planted defect make it exit non-zero
*and* name the family? The anti-vacuity page claims this for seven lanes — spot-check
at least three by running the checker against a **scratchpad copy** you mutate (never
the tracked tree). **(3) Coverage of its own declared invariants**: `aws-evidence.yml`
claims it "fails on any declared invariant that has neither a plant nor a written
exemption" — verify that meta-check exists and works. **(4) Staleness**: does the
checker compare against a figure that a human last updated by hand? `aws-evidence.yml:33-41`
openly declines to run `capture_tool_evidence.py --check` because `file_count` moves —
so the census's moving half is checked by nobody. State plainly what that leaves
unguarded.

Also examine the **evidence tree itself**: `evidence/deploy/acceptance.json` recorded
the `500 … KeyError: 0` that the suite missed. For each committed artefact under
`evidence/`, say whether any lane would notice if it went stale, and whether any
document's *prose* claims something no check asserts. The brief records the known
prose-vs-fact traps: `SEC-ACCOUNT-ID` false-positives on `322122547200`
(= 300 GiB in bytes), and the canon-drift pin `260ed37d` where the module is the
deviation, not the registry. Do not re-derive those; look for their siblings.

**Done when:** every checker has its four-field row, at least three negative controls
are re-run against scratchpad copies with their real output pasted, and every
unguarded claim in `evidence/` is named.

---

### W10 — The counterfactual, and the smallest enforceable ruleset

**Output: `docs/diagnosis/structural-rules.md`**

Read §0. Read-only; concurrent wave; one output file. **You are the answer to the
question the founder is really asking**, and you must not wait on the other nine —
your material is git history and HEAD, both of which you have.

**Part A — the counterfactual, reconstructed from history, not from memory.** For each
of the three known defects, use `git log -S`, `git log -G`, `git show` and `git blame`
to recover the *exact* state of the tree at the moment the defect was live, and then
prove — by quoting the test source as it stood — **why the suite could not have failed**.
Three specific reconstructions: (1) the permit-id near-miss — find the two 423 tests as
they were, quote the `monkeypatch.setenv` line in each, and show the guard's comparison
in `transitions._demo_guard`; (2) the `dict_row` 500 — find the connection helper the
tests used and quote its row factory beside `db.py:309`'s `dict_row` and
`refusal.py:235`'s `row[0]`; (3) the beat-4 signer FK — quote
`gate_run._DISPOSITION_SQL`'s derivation beside `demo_world.sql`'s `digest(...)` and
show the seeder the 291 tests used. Each reconstruction ends with one sentence: **the
minimum property the suite would have had to have.** Those three sentences are the
spine of Part B.

**Part B — the ruleset.** Design the **smallest** set of structural rules that makes
this class *impossible*, not merely fixed. Each rule must be stated so it could be
enforced **mechanically tomorrow**, which means each gets: a one-sentence statement; the
concrete mechanism (a pytest plugin hook, a conftest assertion, an AST sweep in
`tests/release/`, a CI step, a `ruff` rule, a schema); **the file it would live in**;
its expected false-positive rate and the escape hatch for legitimate exceptions; and —
the honesty requirement — **which of the three defects it would have caught, and which
it would NOT.** A rule that catches all three is suspicious; say so. Candidate
directions, which you should prune rather than adopt wholesale: a
production-connection-factory rule (tests may not open a database connection except
through the production helper); a no-private-import rule (a test may not import a
`_`-prefixed name from its subject); an environment-parity rule (the set of env vars
tests set must be a subset of what `infra/` provisions, asserted by a test); a
one-world rule (every suite that touches the demo domain seeds through
`seed_demo.apply_seeds`); a collection-census rule (the `docs/ci/test-collection.md`
command becomes a CI step); a coverage floor on deployed-path modules only; a
source-mutation lane (§1.2: none exists — cost it honestly, it is the only rule that
detects *unknown* instances of the shape rather than the three known ones); and a
negative-control-per-lane rule extending `docs/ci/anti-vacuity.md` to the eight lanes
that lack one.

**Part C — the sequencing.** Rank the rules by *(defects prevented) / (cost to
enforce)* and say which three a single subsequent wave should land first, and which are
worth deferring past the 2026-08-18 deadline. Be willing to write "this one is not
worth it" — a ruleset that is too expensive to adopt prevents nothing.

**Done when:** three reconstructions each quote period-accurate source, every proposed
rule names its enforcement file and its would-have-caught verdict against all three
defects, and Part C names the first three to land.

---

## 4. What this wave is NOT for

- **Not fixes.** Nobody in this wave edits a source file. Ten diagnosis files, then a
  separate wave fixes the complete list at once. That is the whole point: the previous
  three rounds each fixed one defect and each missed the next.
- **Not the known list.** The permit-id near-miss, the `dict_row` 500, the beat-4
  signer FK, the `testpaths` gap, the canon drift at `998c526`/`260ed37d`, the CRLF
  `ruff format` artefact, the `SEC-ACCOUNT-ID` false positive on `322122547200`, the
  cost envelope and the concurrency quota of 10 — all known, all recorded. Cite them as
  the shape; do not spend an analyst re-deriving them.
- **Not a rewrite of `docs/ci/anti-vacuity.md`, `docs/ci/test-collection.md` or
  `docs/ci/mechanical-sweeps.md`.** Those are prior art by earlier workers. Verify
  them, extend them, and report where HEAD has moved past them.
- **Not wall-clock.** A 24-worker wave is on this box. Report counts, not timings.
