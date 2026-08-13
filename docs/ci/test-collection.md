<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: CC-BY-4.0
-->

# Test collection: what a default `pytest` reaches, and what it did not

**Worker:** W3, demo-correctness wave. **Measured 2026-08-13 on TRAPPOINT**, against the
working tree at `D:/CoackroachDBxAWS/mainline` with `.venv/Scripts/python.exe` (pytest 9.1.1,
`trappoint-testkit` 0.1.0) and the pinned local node **CockroachDB CCL v26.2.5** on
`127.0.0.1:26257`. Every number below is the output of a command printed beside it, run in the
same sitting as this file. Nothing is carried forward from a recorded board.

---

## 1. The measurement

```
$ .venv/Scripts/python.exe -m pytest verticals/mainline/apps/demo-api/tests --collect-only -q
228 tests collected

$ .venv/Scripts/python.exe -m pytest --collect-only -q
9324 tests collected
```

The 228 were **not** among the 9324. `pyproject.toml` declared

```toml
testpaths = ["tests", "packages", "verticals/*/packages/*/tests"]
```

and the third glob resolves to four directories, every one of them under
`verticals/mainline/packages/`. The demo API's tests live under `verticals/mainline/apps/`,
which matched nothing. A second, independent declaration —
`verticals/mainline/apps/demo-api/pyproject.toml` line 78, `testpaths = ["tests"]` — meant the
suite ran perfectly *when someone named its path*, and never otherwise.

**This is the second occurrence of one defect class.** The comment above the declaration records
the first: until 2026-08-10 `testpaths` read `["tests", "packages"]`, and 146 tests across
`mainline-anchor`, `mainline-custody-patrol` and `mainline-sequencer` had never run in a default
invocation. That fix reached `verticals/*/packages/*` and stopped one directory level short of
`verticals/*/apps/*`.

### What the gap cost

`verticals/mainline/apps/demo-api/tests/test_row_factory_contract.py` is 627 lines written
specifically to catch a `dict_row`/`tuple_row` defect, and it carries an explicit diagnosis
naming `mainline_demo_api/refusal.py:235`. It had never executed in CI or in a default `pytest`
invocation. `evidence/deploy/acceptance.json` records what shipped instead: two
`500 … internal_error · resource=demo_gate_run · KeyError: 0`, and the verdict `NOT PROVEN`.

The contract that would have caught the 500 was written, committed, and never collected.
**A test that is not collected is not enforcement**, and that sentence — not any property of the
test itself — is the finding this document exists to record.

### Before and after, taken in one sitting

The tree moved *while this was being measured*: other workers landed
`tests/unit/aws/test_verify_evidence_account_id.py`, W1 landed
`verticals/mainline/apps/demo-api/tests/test_refusal_row_factory.py`, and W5 extended
`test_reads.py`. A pair of raw totals taken hours apart would therefore be arithmetic about other
people's commits. The honest form is the **triple, taken in one sitting**, which is invariant
under that drift, because `-o` overrides the ini value for one run and both halves see the same
working tree seconds apart:

```
$ OLD='testpaths=tests packages verticals/*/packages/*/tests'

$ pytest --collect-only -q                 | grep -c '::'    # after
9584
$ pytest --collect-only -q -o "$OLD"       | grep -c '::'    # before, same tree
9341
$ pytest --collect-only -q verticals/mainline/apps/demo-api/tests | grep -c '::'
243
```

`9584 − 9341 = 243`, exactly the demo-api total: the change adds that suite and moves nothing
else. The head-of-wave pair, for the record, was **9324 → 228 uncollected**; both totals rose as
W1 and W5 landed files while this was being measured, which is why the triple is the number that
matters and the pair is not.

Per module, counted through the root declaration — identical to the standalone route, which is
the point:

| module | tests |
|---|---|
| `test_envelope.py` | 47 |
| `test_gate_run.py` | 21 |
| `test_reads.py` | 74 |
| `test_refusal_row_factory.py` | 13 |
| `test_routes_gate_run.py` | 11 |
| `test_row_factory_contract.py` | 14 |
| `test_static_site.py` | 41 |
| `test_transitions.py` | 22 |

---

## 2. The declaration, and why it names the app instead of globbing it

```toml
testpaths = [
    "tests",
    "packages",
    "verticals/*/packages/*/tests",
    "verticals/*/apps/demo-api/tests",   # ← added 2026-08-13
]
```

The `*` stays on the **vertical**, matching the line above it. It deliberately does **not** move
to the app, because the app segment is exactly where this repository's Python/TypeScript boundary
lies, and a wildcard cannot know which side of it a directory is on. Measured before choosing:

| `verticals/mainline/apps/…` | `tests/` holds | verdict |
|---|---|---|
| `console` | 148 entries, **zero** `*.py` — `setup.ts`, `browser/`, `unit/`, `vectors/` | a vitest suite; pytest must never be pointed at it |
| `steward` | no `tests/` at all — `prompts/`, `runbooks/` | nothing to collect |
| `demo-api` | 8 modules, all Python | the one Python app |

`verticals/*/apps/*/tests` would have handed the console's vitest tree to pytest. That is the same
category error `[tool.uv.workspace] members` already refuses two dozen lines higher in the same
file, for the same reason and in the same words.

Basename safety was checked before the line landed: `prepend` import mode names a test module by
its basename when its directory has no `__init__.py`, so a duplicate basename is an import error
rather than a silent miss. All demo-api module basenames are globally unique across `tests/`,
`packages/` and `verticals/`.

---

## 3. The second defect, which only the fix could expose: `from conftest import …`

Adding the testpath produced **three collection errors** on the first run:

```
ImportError: cannot import name 'RESOURCES_TS' from 'conftest'
    (D:\CoackroachDBxAWS\mainline\packages\trappoint-sql\tests\conftest.py)
ERROR verticals/mainline/apps/demo-api/tests/test_envelope.py
ERROR verticals/mainline/apps/demo-api/tests/test_reads.py
ERROR verticals/mainline/apps/demo-api/tests/test_routes_gate_run.py
```

**The mechanism.** Those three modules open with a bare `from conftest import …`. That is a
top-level absolute import, so it resolves through `sys.modules["conftest"]` — one slot, shared by
all 55 `conftest.py` files in this repository, none of which sits in a package. pytest handles the
ordinary case itself: `PytestPluginManager._importconftest` does `del sys.modules[conftestpath.stem]`
before importing the next one, with the comment *"conftest.py files there are not in a Python
package all have module name `conftest`, and thus conflict with each other"*. So a conftest loaded
**during descent** is in the slot when its own directory's modules are imported a moment later.

That guarantee does not extend to a conftest loaded as an **initial argument**, which is what a
`testpaths` entry is. pytest loads it up front via `_try_load_conftest`; when collection finally
reaches the directory, `_importconftest` short-circuits on `self.get_plugin(str(conftestpath))`
and returns the cached plugin **without touching `sys.modules` again**. Every conftest imported
during the intervening descent through `tests/` and `packages/` takes the slot in turn, and the
last one to arrive is the one the test modules get.

**This is a latent fault three other suites already carry.** `packages/mainline-mcp/tests`,
`tests/unit/moc_stream` and `tests/integration/recall_lexical` all use the bare import. It is
invisible to them only because they are reached by descent. Naming any two of them on one command
line reproduces it today, with no change to any file — measured 2026-08-13:

```
$ pytest tests/unit/moc_stream packages/mainline-mcp/tests --collect-only -q
ImportError: cannot import name 'read_jsonl' from 'conftest'
    (…\packages\mainline-mcp\tests\conftest.py)
147 tests collected, 1 error in 0.55s

$ pytest packages/mainline-mcp/tests tests/unit/moc_stream --collect-only -q
96 tests collected, 3 errors in 0.46s
```

**The fix**, in `verticals/mainline/apps/demo-api/tests/conftest.py` and nowhere else: claim the
name for exactly the window in which a collector under that directory is being collected, and hand
it straight back. `pytest_collectstart` and `pytest_collectreport` bracket `collector.collect()`
inside `runner.collect_one_node`, which is where a `Module`'s import happens, and a conftest's
collection hooks fire only for nodes beneath its own directory. So the window is precisely the
import of those modules and nothing else in the session. Setting the name once at conftest import
time would not survive the descent; leaving it set afterwards would inflict this same defect on
whatever collects next.

Verified handed back — after a full default collection, the slot belongs to whoever descent gave
it to, not to this directory:

```
  sys.modules['conftest'] = …\packages\trappoint-sql\tests\conftest.py
```

---

## 4. The third defect, and the one that actually mattered: a run-killing hang

This is the finding that was not in any brief, and it only exists *because* the suite became
collectable.

Two modules under this directory do not consume the `admin_dsn` fixture. `test_gate_run.py:383`
and `test_row_factory_contract.py:198` each build their own DSN from the four environment names
and then fall back to a **hardcoded `127.0.0.1:26257`**.

Under `--crdb=none` the testkit clears those four names and installs `cluster.ProcessGuard`, which
blocks `docker` / `cockroach` from being **spawned**. It does not — and cannot — block a
`psycopg.connect` to a node that is **already listening**. Demonstrated directly, with all four
names cleared exactly as `--crdb=none` leaves them:

```
$ python -c "... clear the four DSN names ...; print(test_row_factory_contract._admin_dsn())"
_admin_dsn() with all four DSN names cleared -> 127.0.0.1:26257/defaultdb?sslmode=disable&connect_timeout=10
  and it ANSWERS: CockroachDB CCL v26.2.5
```

So on any machine where the compose node happens to be up — every developer laptop, and TRAPPOINT
itself — those modules dial a cluster the session explicitly declined to obtain. The consequence
is not merely "used the wrong node". Measured, in the first full `--crdb=none` run after the
testpath landed:

```
$ pytest --crdb=none -q
…                                                                        [ 99%]
+++++++++++++++++++++++ Timeout +++++++++++++++++++++++
  File "…\test_row_factory_contract.py", line 220, in w1_database
    report = proof.apply_chain(…)        # 271 migrations, inside a 120 s budget
  File "…\psycopg\waiting.py", line 265, in wait_select
EXIT=1
```

`pyproject.toml` sets `timeout = 120` and `timeout_method = "thread"`, and the thread method ends
the process with `os._exit`. **The entire 9583-test run died at 99%, after twelve minutes**,
because a suite that had just become collectable ignored `--crdb=none`. That is the
thirteen-clusters failure mode the repository-root `conftest.py` docstring exists to prevent,
re-entered through a newly-collected directory — and it is precisely what "no hang" meant.

### The fix, at the boundary where it can be stated once

`admin_dsn` already consults the testkit's decision and skips with its reason. That is a property
of a *fixture*, not of the *suite*, so a module that declines to use the fixture escapes it. The
rule is therefore enforced in `pytest_runtest_setup` in the directory's `conftest.py`, which fires
only for items beneath that directory: when the item carries `requires_cluster` and the session
obtained no cluster, it is skipped with the testkit's reason named.

It removes no coverage — see §6, where every one of those tests runs and passes against a real
cluster. It converts "silently uses a node the session refused, then hangs" into "skipped, with
the reason named", which is exactly the property `ci.yml`'s step *"The suite, with every cluster
test SKIPPED FOR A NAMED REASON"* claims, and which `ci.yml:40-47` asserts in prose. A module
added to this directory later inherits the rule without knowing it exists — the difference between
a fixed instance and a closed class.

The deeper cause — a hardcoded DSN fallback inside a test module — is **not fixed here**, because
those two modules belong to other workers. See §8.

---

## 5. The no-cluster lane, measured

`.github/workflows/ci.yml` refuses `-m "not requires_cluster"` on the stated ground that a marker
filter *deselects*, so a skipped test becomes indistinguishable from a deleted one. It uses
`--crdb=none`, which makes the fixture skip **and print why**.

```
$ pytest --crdb=none --collect-only -q
9584 tests collected          # exit 0, no errors

$ pytest -c pyproject.toml --crdb=none -q verticals/mainline/apps/demo-api/tests
99 passed, 144 skipped in 11.60s
```

— with the live v26.2.5 node answering on `127.0.0.1:26257` throughout, which is the condition
that produced the hang in §4. All 144 `requires_cluster` items skip with one named reason:

> the session obtained no CockroachDB, so this cluster-backed test is skipped rather than allowed
> to reach a node the session declined to obtain. trappoint-testkit says: `--crdb=none`: this
> session declined to obtain a CockroachDB, so every test that needs one is skipped rather than
> allowed to start a private container

Whole suite, with the same node still answering — the run that hung at 99% in §4:

```
$ pytest --crdb=none -q
22 failed, 8617 passed, 945 skipped, 2 warnings in 656.53s (0:10:56)
EXIT=1
```

**It completes.** No `Timeout`, no `os._exit`, and 10:56 against the 12:29-and-killed of §4.
`22 + 8617 + 945 = 9584`, so every collected test reached a verdict.

**That is not a green, and it is not made one here.** The 22 classify exactly, against `ci.yml`'s
own `RED_SELECTOR: "g4alpha or pl2_red"`:

```
$ pytest --crdb=none --collect-only -q -m "g4alpha or pl2_red" | grep -c '::'
13
$ comm -12 <(the 22 ids) <(the 13 red-by-design ids) | wc -l
13
```

| | count | whose |
|---|---|---|
| red **by design** — `g4alpha` / `pl2_red`, run inverted by the `red-by-design` job | 13 | the board, as declared |
| `tests/integration/custody/test_k2_exit.py` — `custody-chain`, which this wave requires to STAY red | 5 | the board, as declared |
| `test_mi_blame.py::test_dm9…`, `test_lockfile.py::test_the_committed_manifest_is_current` | 2 | pre-existing, not this worker's |
| `tests/release/test_ruff_ratchet.py::test_the_ratchet_passes_on_the_real_tree` | 1 | pre-existing — see below |
| `test_envelope.py::test_no_web_framework_or_aws_sdk_is_imported` | 1 | §8, W4's |

**Exactly one of the 22 comes from the newly-collected suite**, and it is a defect in that test
rather than in the product (§8). The three `test_row_factory_contract.py` cases that landed on
`refusal.py:235` at the head of this wave are **gone**: W1's fix landed, and this is the first run
in which that could be observed at all.

The ruff ratchet red is **not caused by this change and not caused by this wave**. Its
`FORMAT REGRESSION … measured=241` is the committed-CRLF artefact the wave brief names: measured
here, `verticals/mainline/apps/demo-api/src/mainline_demo_api/gate_run.py` is `CRLF=706, LF=0` **at
HEAD**, unmodified in the worktree. The three files this worker owns were kept at the LF their own
HEAD blobs use, and none appears in the 56:

```
$ ruff format --check verticals/ | grep -c 'demo-api\tests\conftest.py'
0
$ ruff check   verticals/mainline/apps/demo-api/tests/conftest.py   → All checks passed!
$ ruff format --check verticals/mainline/apps/demo-api/tests/conftest.py → 1 file already formatted
```

### The node was never touched

The strongest evidence that the §4 fix does what it claims is not the skip census but the cluster
itself. `SHOW DATABASES` immediately before and immediately after the ten-minute `--crdb=none` run:

```
DB COUNT = 11      (before)
DB COUNT = 11      (after)
```

Identical, `w3_demo_api_*` included. Before the fix, `w1_database` was connecting to this node and
applying 271 migrations into it. A `--crdb=none` session now reaches it **zero times**.

The reason is scoped to this directory and leaks nowhere. Measured against a cluster-backed suite
outside it, which keeps its own wording:

```
$ pytest --crdb=none -q -rs packages/trappoint-testkit/tests
26 passed, 2 skipped in 4.07s
$ pytest --crdb=none -q -rs packages/trappoint-testkit/tests | grep -c "declined to obtain$"
0
```

### The root conftest's two seams still apply

`conftest.py` at the repository root exports `PGCONNECT_TIMEOUT` and the CockroachDB image pin at
**import** time, because anything that connects during collection must already have them, and 33
modules read `MAINLINE_CRDB_IMAGE` at module import. Measured on both routes with a probe plugin:

| | rootdir | root `conftest.py` loaded | `PGCONNECT_TIMEOUT` | `MAINLINE_CRDB_IMAGE` | testkit `STATE_KEY` |
|---|---|---|---|---|---|
| through root `testpaths` | repo root | **True** | `5` | `cockroachdb/cockroach:v26.2.5` | present |
| standalone (`pytest verticals/…/tests`) | `apps/demo-api` | **False** | `5` | `cockroachdb/cockroach:v26.2.5` | present |

The standalone route never loads the root conftest — its rootdir is the app, and `confcutdir`
stops there. It gets the timeout and the pin only because `trappoint_testkit.plugin` publishes
them too, at `pytest_configure` rather than at conftest import. **Collecting the suite through the
root declaration is what puts it behind the seam the thirteen-clusters incident installed**, rather
than behind a duplicate of it that happens to agree.

`_testkit_state(config)` reads `config.stash[STATE_KEY]`, and that path was verified to work on
both routes: the plugin is loaded once, by its `pytest11` entry point, so the `StashKey` identity
is the same object either way. It needed no change.

---

## 6. The control: the suite is not merely skipping, it passes

A skip census proves nothing about correctness on its own. Against the live node, with the same
declaration and the same conftest:

```
$ pytest -c pyproject.toml --crdb=reuse -q verticals/mainline/apps/demo-api/tests
242 passed, 1 skipped in 40.43s
```

Every `requires_cluster` item runs. The one skip is `test_gate_run.py:744`, which names its reason
(`jsonschema` is not a workspace dependency). **This is the first time this suite's verdict against
a real cluster has ever been a measured fact rather than an assumption** — and it is green,
including the three `test_row_factory_contract.py` cases that landed on `refusal.py:235` before W1
fixed it.

---

## 7. The rule that keeps this from happening a third time

Not a wider glob — a wider glob is what would have swallowed the console. A **census**: every
directory holding a `test_*.py`, diffed against every directory a default `pytest` actually
reaches. Empty output means the declaration covers the tree.

```sh
diff <(git ls-files --cached --others --exclude-standard -- '*/test_*.py' 'test_*.py' \
         | xargs -n1 dirname | sort -u) \
     <(pytest --collect-only -q | grep '::' | cut -d: -f1 | xargs -n1 dirname | sort -u)
```

`--cached --others --exclude-standard` so a test file that is written but not yet committed is
counted; the whole failure mode here is a suite that exists and is not reached.

```
$ diff <(…) <(…) ; echo "DIFF-EXIT=$?"
DIFF-EXIT=0
```

**Negative control — the census can fail, and it fails by naming the cause.** Re-run against the
declaration this change replaced:

```
$ diff <(…) <(pytest --collect-only -q -o 'testpaths=tests packages verticals/*/packages/*/tests' | …)
70d69
< verticals/mainline/apps/demo-api/tests
DIFF-EXIT=1
```

One line, and it is the directory. A check that cannot be made to fail on demand is not a check,
and this one fails on the exact defect it was written for.

Run it when a test root moves, when a vertical or an app is added, and when a distribution grows a
`tests/` directory. On Windows without git-bash:

```powershell
Get-ChildItem -Recurse -Directory -Filter tests |
  Where-Object { $_.FullName -notmatch 'node_modules|\.venv|\.git' } |
  ForEach-Object {
    $n = (Get-ChildItem $_.FullName -Filter 'test_*.py' -File).Count
    if ($n -gt 0) { "{0,4}  {1}" -f $n, $_.FullName }
  }
```

---

## 8. What is left, and whose it is

Two things this worker measured and deliberately did **not** fix, because the files belong to
other workers and the change would be an edit to a test module:

1. **The hardcoded DSN fallback.** `test_gate_run.py:383` and `test_row_factory_contract.py:198`
   build a DSN from the four environment names and fall back to `127.0.0.1:26257`, routing around
   `_testkit_state` entirely. §4's `pytest_runtest_setup` makes that harmless for the *session's*
   purposes — the items skip before the fallback is ever reached — but the fallback is still in
   the modules, and any code path that reaches it outside a `requires_cluster` item is unguarded.
   The consistent form is the one the rest of the suite uses: obtain the DSN from the `admin_dsn`
   fixture, which consults the session's decision. For W2 and W4.

2. **`test_envelope.py::test_no_web_framework_or_aws_sdk_is_imported` is a defect in the test**,
   exposed by collection rather than by any product change. It passes in isolation and fails in a
   shared session:

   ```
   AssertionError: the deployment package pulled in ['boto3', 'botocore', 'httpx', 'pydantic']
   ```

   The test imports three `mainline_demo_api` modules and then reads the **process-wide**
   `sys.modules`. In a shared session those four names are already there, imported by earlier
   suites, so the assertion proves "nothing in this pytest process imported boto3" — which is not
   the claim in its own docstring. While the suite ran only in its own process the gap was
   unobservable. The mechanism that matches the claim is a snapshot of `sys.modules` taken
   immediately before the three imports and diffed immediately after, or the three imports
   performed in a clean subprocess. `test_envelope.py` is W4's file and was not edited here.
